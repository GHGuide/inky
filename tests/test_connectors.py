"""Connectors against local fakes: the app finds your tools, Claude Code / Codex report sign-in,
Telegram finds your chat, n8n and Apify work as built-in tool providers behind the same delegate."""
import json
import os
import stat
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest import mock

from inky import connectors
from inky.keys import Keys
from inky.mcp import MCPManager
from inky.store import Store


class Fake(BaseHTTPRequestHandler):
    """Telegram (/bot<token>/…), n8n (/api/v1/…, /webhook/…) and Apify (/v2/…) in one server."""
    seen = []
    updates = None  # set by a test: what getUpdates returns

    def _send(self, obj, status=200):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        Fake.seen.append(("GET", self.path, dict(self.headers)))
        if self.path.endswith("/getMe"):
            return self._send({"ok": True, "result": {"username": "inky_test_bot"}})
        if "/getUpdates" in self.path and Fake.updates is not None:
            return self._send({"ok": True, "result": Fake.updates})
        if "/getUpdates" in self.path:
            return self._send({"ok": True, "result": [
                {"update_id": 1, "message": {"text": "hello", "chat": {"id": 111}}},
                {"update_id": 2, "message": {"text": "/start", "chat": {"id": 4242, "first_name": "Leo"}}}]})
        if self.path.startswith("/api/v1/workflows"):
            if self.headers.get("X-N8N-API-KEY") != "n8n-test":
                return self._send({"message": "unauthorized"}, 401)
            return self._send({"data": [{"id": "w1", "name": "Price alerts", "active": True}]})
        if self.path.startswith("/v2/users/me"):
            return self._send({"data": {"username": "leo", "plan": {"id": "FREE"}}})
        self._send({"error": "not found"}, 404)

    def do_POST(self):
        body = self._body()
        Fake.seen.append(("POST", self.path, body))
        if self.path.endswith("/sendMessage"):
            return self._send({"ok": True, "result": {"message_id": 9}})
        if self.path.endswith(("/answerCallbackQuery", "/editMessageText")):
            return self._send({"ok": True, "result": True})
        if self.path == "/api/v1/credentials":
            return self._send({"id": "c1", "name": body["name"]})
        if self.path == "/api/v1/workflows":
            return self._send({"id": "w2", "name": body["name"]})
        if self.path.startswith("/webhook/"):
            return self._send({"received": True})
        if "/run-sync-get-dataset-items" in self.path:
            return self._send([{"title": "Flat A", "price": 120000}, {"title": "Flat B", "price": 140000}])
        self._send({"error": "not found"}, 404)

    def log_message(self, *a):
        pass


def make_env():
    home = tempfile.mkdtemp()
    store = Store(os.path.join(home, "t.db"))
    keys = Keys(home, backend="file")
    return SimpleNamespace(store=store, keys=keys, home=home, token="Zq81-inky-secret", port=8800)


class ConnectorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Fake.seen = []
        self.env = mock.patch.dict(os.environ, {"TELEGRAM_API": self.base, "APIFY_API": self.base})
        self.env.start()
        self.addCleanup(self.env.stop)

    @unittest.skipIf(os.name == "nt", "uses a shell script as a fake program")
    def test_fix_path_adds_login_shell_and_common_dirs(self):
        d = tempfile.mkdtemp()
        shell = os.path.join(d, "fakeshell")
        with open(shell, "w") as f:
            f.write('#!/bin/sh\nprintf %s "/from/login/shell:/usr/bin"\n')
        os.chmod(shell, os.stat(shell).st_mode | stat.S_IEXEC)
        env = {"PATH": "/usr/bin:/bin", "HOME": d}
        connectors.fix_path(env, shell=shell)
        parts = env["PATH"].split(os.pathsep)
        self.assertEqual(parts[:2], ["/usr/bin", "/bin"])  # what you had stays first
        self.assertIn("/from/login/shell", parts)
        self.assertIn("/opt/homebrew/bin", parts)
        self.assertEqual(len(parts), len(set(parts)))

    @unittest.skipIf(os.name == "nt", "uses a shell script as a fake program")
    def test_claude_code_signed_out_says_how_to_fix(self):
        d = tempfile.mkdtemp()
        exe = os.path.join(d, "claude")
        with open(exe, "w") as f:
            f.write('#!/bin/sh\necho \'{"loggedIn": false}\'\n')
        os.chmod(exe, 0o755)
        E = make_env()
        E.mcp = MCPManager(E.store, E.home)
        connectors.STATUS_CACHE.clear()
        with mock.patch.dict(os.environ, {"PATH": d + os.pathsep + os.environ["PATH"]}):
            cc = next(c for c in connectors.status(E) if c["name"] == "claude-code")
        self.assertTrue(cc["installed"])
        self.assertFalse(cc["signed_in"])
        self.assertIn("sign in", cc["fix"].lower())

    def test_telegram_finds_your_chat_and_sends(self):
        E = make_env()
        tg = connectors.PROVIDERS["telegram"]
        self.assertEqual(tg.save(E, {"token": "123456789:AAfakeTokenForTestsOnly_0123456"})["bot"], "inky_test_bot")
        self.assertEqual(tg.find_chat(E), 4242)  # the chat that sent /start
        self.assertEqual(E.store.setting("telegram")["chat_id"], 4242)
        r = tg.test(E)
        self.assertTrue(r["ok"])
        self.assertEqual(Fake.seen[-1][2]["chat_id"], 4242)

    def test_telegram_buttons_answer_a_question_from_your_chat_only(self):
        E = make_env()
        tg = connectors.PROVIDERS["telegram"]
        tg.save(E, {"token": "123456789:AAfakeTokenForTestsOnly_0123456"})
        tg.find_chat(E)
        nid = E.store.insert("needs", {"kind": "decision", "title": "Send it?", "options": ["Approve", "Deny", "Show me once"]}, bot_id=1, status="open")
        tg.send(E, "Agency Note: Send it?", need=E.store.get("needs", nid))
        keys = [b["callback_data"] for row in Fake.seen[-1][2]["reply_markup"]["inline_keyboard"] for b in row]
        self.assertEqual(keys, [f"need:{nid}:0", f"need:{nid}:1"])  # “Show me once” needs the app, so it isn't offered
        chosen = []
        E.resolve = lambda n, d: (chosen.append((n, d)), E.store.update("needs", n, status="resolved", decision=d))
        Fake.updates = [{"update_id": 7, "callback_query": {"id": "q1", "data": f"need:{nid}:0", "message": {"message_id": 9, "chat": {"id": 111}, "text": "x"}}},
                        {"update_id": 8, "callback_query": {"id": "q2", "data": f"need:{nid}:1", "message": {"message_id": 9, "chat": {"id": 4242}, "text": "Send it?"}}},
                        {"update_id": 9, "callback_query": {"id": "q3", "data": f"need:{nid}:0", "message": {"message_id": 9, "chat": {"id": 4242}, "text": "Send it?"}}}]
        try:
            self.assertEqual(tg.poll(E), 1)
        finally:
            Fake.updates = None
        self.assertEqual(chosen, [(nid, "Deny")])  # a stranger's tap (chat 111) did nothing; the second tap came too late
        self.assertEqual(E.store.setting("telegram")["offset"], 10)
        notes = [b["text"] for m, p, b in Fake.seen if p.endswith("/answerCallbackQuery")]
        self.assertEqual(notes[-2:], ["Done: Deny", "That was already answered."])

    def test_n8n_lists_workflows_sends_skills_and_triggers(self):
        E = make_env()
        n8n = connectors.PROVIDERS["n8n"]
        self.assertFalse(n8n.save(E, {"url": self.base, "key": "wrong"})["ok"])
        r = n8n.save(E, {"url": self.base + "/", "key": "n8n-test"})
        self.assertTrue(r["ok"], r)
        self.assertIn("Price alerts", n8n.test(E)["text"])
        skill = {"id": 3, "bot_id": 1, "name": "Flats"}
        sent = n8n.send_skill(E, skill)
        self.assertEqual(sent["id"], "w2")
        wf = next(b for m, p, b in Fake.seen if p == "/api/v1/workflows")
        self.assertNotIn("Zq81-inky-secret", json.dumps(wf))  # the Inky token lives in an n8n credential, never in the workflow
        cred = next(b for m, p, b in Fake.seen if p == "/api/v1/credentials")
        self.assertEqual(cred["data"]["value"], "Zq81-inky-secret")
        out = n8n.call(E, "trigger", {"webhook_url": self.base + "/webhook/abc", "payload": {"new": 2}})
        self.assertFalse(out["error"])
        self.assertIn("received", out["text"])

    def test_apify_runs_an_actor(self):
        E = make_env()
        ap = connectors.PROVIDERS["apify"]
        self.assertTrue(ap.save(E, {"token": "apify-test"})["ok"])
        out = ap.call(E, "run_actor", {"actor": "apify/web-scraper", "input": {"q": 1}, "limit": 1})
        self.assertFalse(out["error"])
        self.assertEqual(json.loads(out["text"]), [{"title": "Flat A", "price": 120000}])
        path = next(p for m, p, b in Fake.seen if "run-sync" in p)
        self.assertIn("apify~web-scraper", path)

    def test_delegate_routes_to_builtin_providers(self):
        E = make_env()
        mgr = MCPManager(E.store, E.home)
        mgr.builtin = connectors.Builtins(E)
        connectors.PROVIDERS["apify"].save(E, {"token": "apify-test"})
        self.assertTrue(any(line.startswith("apify.run_actor(") for line in mgr.catalog()))
        with mock.patch.object(connectors.N8n, "call", return_value={"text": "ok", "error": False}) as called:
            self.assertEqual(mgr.call("n8n", "list_workflows", {})["text"], "ok")
        called.assert_called_once()

    def test_add_inky_to_codex_once(self):
        from inky.server import codex_add_inky
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "config.toml"), "w") as f:
            f.write('model = "gpt-5"')
        E = make_env()
        with mock.patch.dict(os.environ, {"CODEX_HOME": d}):
            first = codex_add_inky(E, None, {}, {})
            again = codex_add_inky(E, None, {}, {})
        text = open(os.path.join(d, "config.toml")).read()
        self.assertIn("[mcp_servers.inky]", first["wrote"])
        self.assertEqual(again["wrote"], "")
        self.assertEqual(text.count("[mcp_servers.inky]"), 1)
        self.assertTrue(text.startswith('model = "gpt-5"\n'))
        import tomllib
        self.assertEqual(tomllib.loads(text)["mcp_servers"]["inky"]["env"]["INKY_HOME"], E.home)


if __name__ == "__main__":
    unittest.main()
