"""Engine end to end with a scripted model: draft, chat actions, learn → replay, new-only results,
approval gate on a Send button, show-me-once, move between two engines, and MCP both ways."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

from inky.bots import Engine
from inky.llm import LLM
from inky.mcp import MCPClient
from inky.server import serve
from inky import transfer
from tests import site_server
from tests.test_skills import ScriptedModel


class FakeLLM(LLM):
    """Real LLM class, scripted answers. chat() answers chat prompts; ask_json() answers learn/extract/repair."""

    def __init__(self, store, keys, on_usage=None):
        super().__init__(store, keys, on_usage)
        self.scripted = ScriptedModel(repair_answer=("Salva ricerca", 0.3))
        self.chat_reply = {"reply": "OK", "actions": []}

    def roles(self):
        return {r: {"provider": "custom", "model": "scripted"} for r in ("learn", "chat", "repair", "smart")}

    def chat(self, role, messages, bot_id=None, **kw):
        if self.on_usage:
            self.on_usage(bot_id, {"role": role, "model": "scripted", "in": 10, "out": 5, "local": True})
        return json.dumps(self.chat_reply), {}

    def ask_json(self, role, system, user, bot_id=None, **kw):
        if self.on_usage:
            self.on_usage(bot_id, {"role": role, "model": "scripted", "in": 10, "out": 5, "local": True})
        if system.startswith("You turn a job"):
            return {"name": "Flat Hunter", "summary": "Flats in Bari", "goal": "Flats in Bari under 150k",
                    "start_url": None, "every_minutes": 15, "filters": [{"field": "price", "op": "<=", "value": 150000, "text": "under €150k"}]}, {}
        return self.scripted.ask_json(role, system, user, bot_id)


def make_engine():
    e = Engine(tempfile.mkdtemp())
    e.llm = FakeLLM(e.store, e.keys, on_usage=e._usage)
    return e


def wait(pred, t=60):
    end = time.time() + t
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.2)
    return False


class EngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = site_server.start()
        cls.base = f"http://127.0.0.1:{cls.site.server_port}"
        cls.E = make_engine()

    @classmethod
    def tearDownClass(cls):
        cls.E.close()
        cls.site.shutdown()

    def test_1_draft_chat_learn_replay(self):
        E = self.E
        d = E.draft_bot("Every morning find flats in Bari under 150k")
        d["start_url"] = self.base + "/"
        b = E.create_bot(d)
        self.assertEqual(b["name"], "Flat Hunter")
        self.assertEqual(b["filters"][0]["value"], 150000)
        E.llm.chat_reply = {"reply": "Done. Only 3 rooms or fewer.", "actions": [
            {"type": "add_rule", "text": "remember I like Libertà", "filter": None},
            {"type": "remember", "text": "Likes Libertà"}]}
        r = E.chat(b["id"], "remember I like Libertà")
        self.assertIn("Done", r["reply"])
        self.assertEqual(E.store.get("bots", b["id"])["memory"][0]["text"], "Likes Libertà")
        E.learn(b["id"], "Flats in Bari under 150k", self.base + "/")
        self.assertTrue(wait(lambda: not E.busy(b["id"]), 90))
        sk = E.store.find("skills", bot_id=b["id"])
        self.assertEqual(len(sk), 1)
        runs = E.store.find("runs", bot_id=b["id"])
        self.assertEqual(runs[0]["status"], "ok")          # the replay right after learning
        self.assertEqual(runs[0]["ai_calls"], 0)           # …used no AI
        first_new = runs[0]["new"]
        self.assertGreater(first_new, 0)
        E.run(b["id"])
        self.assertTrue(wait(lambda: not E.busy(b["id"]), 90))
        again = E.store.find("runs", bot_id=b["id"])[0]
        self.assertEqual((again["status"], again["new"], again["ai_calls"]), ("ok", 0, 0))
        type(self).bot_id = b["id"]

    def test_2_send_waits_for_approval(self):
        E = self.E
        b = E.create_bot({"name": "Invoice Chaser", "job": "send a message", "start_url": self.base + "/contact?id=1"})
        from inky.skills import descriptor
        comp = E.computer(b["id"])
        page = comp.call("open", self.base + "/contact?id=1")
        by = {e["name"]: e for e in page["elements"]}
        skill = {"name": "Send one", "start_url": self.base + "/contact?id=1", "steps": [
            {"action": "fill", "target": descriptor(by["Messaggio"]), "value": "Hello from a test", "text": "Write the message"},
            {"action": "click", "target": descriptor(by["Invia"]), "text": "Send it"}]}
        E.store.insert("skills", skill, bot_id=b["id"], status="ok")
        before = len(site_server.STATE["sent"])
        E.run(b["id"])
        self.assertTrue(wait(lambda: E.store.find("needs", bot_id=b["id"], status="open"), 30))
        need = E.store.find("needs", bot_id=b["id"], status="open")[0]
        self.assertIn("send it", need["title"].lower())
        self.assertIn("Hello from a test", need["body"])
        time.sleep(1)
        self.assertEqual(len(site_server.STATE["sent"]), before)   # nothing sent yet
        E.resolve(need["id"], "Approve")
        self.assertTrue(wait(lambda: not E.busy(b["id"]), 30))
        self.assertEqual(site_server.STATE["sent"][-1]["msg"], "Hello from a test")
        # deny path: nothing more is sent
        E.run(b["id"])
        self.assertTrue(wait(lambda: E.store.find("needs", bot_id=b["id"], status="open"), 30))
        E.resolve(E.store.find("needs", bot_id=b["id"], status="open")[0]["id"], "Deny")
        self.assertTrue(wait(lambda: not E.busy(b["id"]), 30))
        self.assertEqual(len(site_server.STATE["sent"]), before + 1)
        # deleting a bot that is waiting on you leaves nothing behind and sends nothing
        E.run(b["id"])
        self.assertTrue(wait(lambda: E.store.find("needs", bot_id=b["id"], status="open"), 30))
        E.delete_bot(b["id"])
        time.sleep(1)
        self.assertEqual([E.store.find(t, bot_id=b["id"]) for t in ("messages", "runs", "needs", "events")], [[], [], [], []])
        self.assertEqual(len(site_server.STATE["sent"]), before + 1)

    def test_3_failed_fix_then_show_me_once(self):
        E, bid = self.E, self.bot_id
        urllib.request.urlopen(self.base + "/__layout?v=2").read()
        E.run(bid)
        self.assertTrue(wait(lambda: not E.busy(bid), 60))
        need = next(n for n in E.store.find("needs", bot_id=bid, status="open") if n["kind"] == "fix_failed")
        self.assertEqual(need["confidence"], 0.3)
        E.resolve(need["id"], "Show me once")
        self.assertTrue(wait(lambda: E.runs[bid].paused.is_set(), 60))
        comp = E.computer(bid)
        page = comp.call("elements")
        filtri = next(e for e in page["elements"] if e["name"] == "Filtri")
        E.user_input(bid, "click", x=filtri["x"] + 5, y=filtri["y"] + 5)
        page = comp.call("elements")
        prezzo = next(e for e in page["elements"] if e["id"] == "prezzo_max")
        E.user_input(bid, "click", x=prezzo["x"] + 5, y=prezzo["y"] + 5)
        self.assertEqual(E.finish_show(bid), 2)
        self.assertTrue(wait(lambda: not E.busy(bid), 90))
        urllib.request.urlopen(self.base + "/__layout?v=1").read()


class ScreenModeTest(unittest.TestCase):
    """Your-screen mode: chat typed in the on-page panel reaches the bot and its reply comes back;
    a real mouse move pauses a run."""

    def test_overlay_chat_and_pause(self):
        os.environ["INKY_HEADLESS"] = "1"
        site = site_server.start()
        E = make_engine()
        try:
            b = E.create_bot({"name": "Screen Bot", "start_url": f"http://127.0.0.1:{site.server_port}/"})
            E.update_bot(b["id"], {"mode": "screen"})
            E.llm.chat_reply = {"reply": "Sure, skipping ground floors.", "actions": []}
            E.computer(b["id"])
            E._on_control(b["id"], {"type": "chat", "text": "skip ground floors"})
            msgs = [m["text"] for m in E.store.find("messages", bot_id=b["id"])]
            self.assertIn("skip ground floors", msgs)
            self.assertIn("Sure, skipping ground floors.", msgs)
            state = E.computers[b["id"]].call("overlay")
            chat = E.computers[b["id"]].overlay_state.get("chat", [])
            self.assertEqual(chat[-1]["text"], "Sure, skipping ground floors.")
            E.learn(b["id"], "Flats in Bari", f"http://127.0.0.1:{site.server_port}/")
            self.assertTrue(wait(lambda: E.runs[b["id"]].step, 30))
            E._on_control(b["id"], {"type": "user_input", "kind": "mouse"})
            self.assertTrue(E.runs[b["id"]].paused.is_set())
            self.assertTrue(E.bot_view(E.store.get("bots", b["id"]))["takeover"])
            E.control(b["id"], "stop")
        finally:
            E.close()
            site.shutdown()
            os.environ.pop("INKY_HEADLESS", None)


class ServerMCPTransferTest(unittest.TestCase):
    """Two engines over HTTP: MCP server tools against engine A, and moving a bot from A to B."""

    @classmethod
    def setUpClass(cls):
        cls.site = site_server.start()
        cls.base = f"http://127.0.0.1:{cls.site.server_port}"
        cls.A, cls.B = make_engine(), make_engine()
        cls.sa, cls.sb = serve(cls.A, port=0), serve(cls.B, port=0)
        for s in (cls.sa, cls.sb):
            threading.Thread(target=s.serve_forever, daemon=True).start()
        cls.ua, cls.ub = f"http://127.0.0.1:{cls.sa.server_port}", f"http://127.0.0.1:{cls.sb.server_port}"

    @classmethod
    def tearDownClass(cls):
        for s in (cls.sa, cls.sb):
            s.shutdown()
        cls.A.close()
        cls.B.close()
        cls.site.shutdown()

    def api(self, url, token, method, path, body=None):
        req = urllib.request.Request(url + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-Inky-Token": token, "Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=300).read())

    def test_token_required(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(self.ua + "/api/bots")
        self.assertEqual(e.exception.code, 401)
        # the page carries the token only for this computer's own browser, not a page on another host name
        local = urllib.request.urlopen(self.ua + "/").read().decode()
        self.assertIn(self.A.token, local)
        rebound = urllib.request.urlopen(urllib.request.Request(self.ua + "/", headers={"Host": "evil.example:8800"})).read().decode()
        self.assertNotIn(self.A.token, rebound)
        self.assertEqual(self.api(self.ua, "", "POST", "/api/pair", {"code": transfer.pair_code(self.A.token)})["token"], self.A.token)

    def test_inky_mcp_server_and_move(self):
        A = self.A
        b = A.create_bot({"name": "Flat Hunter", "goal": "Flats in Bari", "start_url": self.base + "/",
                          "filters": [{"field": "price", "op": "<=", "value": 150000}]})
        A.learn(b["id"], "Flats in Bari", self.base + "/")
        self.assertTrue(wait(lambda: not A.busy(b["id"]), 90))
        # Inky as an MCP server (what Claude Code / Codex would start)
        c = MCPClient([sys.executable, "-m", "inky.mcp_server"], env={"INKY_HOME": str(A.home), "INKY_URL": self.ua})
        c.start()
        names = [t["name"] for t in c.tools()]
        self.assertIn("message_bot", names)
        self.assertNotIn("approve", " ".join(names))
        out = c.call("list_bots")
        self.assertFalse(out["error"], out["text"])
        listed = json.loads(out["text"])
        self.assertEqual(listed[0]["name"], "Flat Hunter")
        res = json.loads(c.call("bot_results", {"bot": "flat hunter", "limit": 3})["text"])
        self.assertEqual(len(res), 3)
        c.close()
        # a shared bot file never carries sign-ins or chat; a move does
        shared = self.api(self.ua, A.token, "GET", f"/api/bots/{b['id']}/export")
        self.assertEqual((shared["cookies"], shared["messages"]), ([], []))
        self.assertTrue(shared["skills"])
        private = transfer.export_bot(A, b["id"], private=True)
        self.assertTrue(private["cookies"] and private["messages"])
        # pair A with B and move the bot
        code = transfer.pair_code(self.B.token)
        cid = self.api(self.ua, A.token, "POST", "/api/computers", {"url": self.ub, "code": code, "name": "Home server"})["id"]
        rid = transfer.move_bot(A, b["id"], cid)
        moved = self.B.store.get("bots", rid)
        self.assertEqual(moved["name"], "Flat Hunter")
        self.assertEqual(len(self.B.store.find("skills", bot_id=rid)), 1)
        self.assertEqual(A.store.get("bots", b["id"])["status"], "moved")
        runs = len(A.store.find("runs", bot_id=b["id"], limit=100))
        A.store.update("bots", b["id"], schedule={"every_minutes": 1})
        A.tick(time.time() + 3600)  # only its new server runs it on schedule
        self.assertFalse(A.busy(b["id"]))
        self.assertEqual(len(A.store.find("runs", bot_id=b["id"], limit=100)), runs)
        # calls to the moved bot on A are forwarded to B
        via_a = self.api(self.ua, A.token, "GET", f"/api/bots/{b['id']}")
        self.assertEqual(via_a["bot"]["remote"], "Home server")
        with self.assertRaises(urllib.error.HTTPError):
            self.api(self.ub, "wrong", "GET", "/api/bots")


if __name__ == "__main__":
    unittest.main()
