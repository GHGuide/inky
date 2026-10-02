"""Inky as an MCP server, the way Claude Code and Codex use it: the protocol details clients rely on, loose bot names,
"ask Codex to …" in chat, and making a bot from a sentence without the client waiting a minute."""
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

from inky import mcp_server
from inky.bots import handoff
from inky.mcp import MCPClient, SUPPORTED
from inky.server import serve
from tests import site_server
from tests.test_engine import make_engine, wait


class ProtocolTest(unittest.TestCase):
    """No engine running: what a client sees from the server itself."""

    def talk(self, *msgs):
        env = {"INKY_HOME": tempfile.mkdtemp(prefix="inky-mcp-"), "INKY_URL": "http://127.0.0.1:9", "PATH": "/usr/bin:/bin"}
        lines = "\n".join(m if isinstance(m, str) else json.dumps(m) for m in msgs) + "\n"
        out = subprocess.run([sys.executable, "-m", "inky.mcp_server"], input=lines, capture_output=True, text=True, env=env, timeout=60,
                             cwd=sys.path[0] or ".")
        return {r.get("id"): r for r in map(json.loads, out.stdout.splitlines())}

    def test_protocol(self):
        call = lambda i, name, args=None: {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args or {}}}
        r = self.talk("not json",
                      {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2099-01-01"}},
                      {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
                      {"jsonrpc": "2.0", "method": "notifications/initialized"},
                      {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
                      call(4, "approve", {"bot": "x"}),
                      call(5, "message_bot", {"bot": "books"}),
                      call(6, "run_skill", {"bot": "books"}),
                      call(7, "list_bots"))
        self.assertEqual(r[None]["error"]["code"], -32700)
        self.assertEqual(r[1]["result"]["protocolVersion"], SUPPORTED[0])  # one it speaks, not an echo
        self.assertEqual(r[2]["result"]["protocolVersion"], "2024-11-05")
        self.assertIn("list_bots", r[1]["result"]["instructions"])
        tools = {t["name"]: t for t in r[3]["result"]["tools"]}
        self.assertNotIn("approve", " ".join(tools))
        self.assertTrue(tools["list_bots"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["run_bot"]["annotations"]["readOnlyHint"])
        self.assertEqual(r[4]["error"]["code"], -32602)
        self.assertTrue(r[5]["result"]["isError"])
        self.assertIn("Missing text", r[5]["result"]["content"][0]["text"])
        # the old name still works, and "not running" is one plain sentence
        for i in (6, 7):
            self.assertTrue(r[i]["result"]["isError"])
            self.assertIn("Inky isn't running", r[i]["result"]["content"][0]["text"])


class FindBotTest(unittest.TestCase):
    BOTS = [{"id": 1, "name": "Book Bargains"}, {"id": 2, "name": "E-bike Hunter"}, {"id": 3, "name": "Python Jobs Remote"},
            {"id": 4, "name": "Flat Hunter"}]

    def test_loose_names(self):
        with mock.patch.object(mcp_server, "api", return_value={"bots": self.BOTS}):
            find = lambda ref: mcp_server.find_bot(ref)["id"]
            self.assertEqual(find("2"), 2)
            self.assertEqual(find("books"), 1)
            self.assertEqual(find("the ebike bot"), 2)
            self.assertEqual(find("python jobs"), 3)
            self.assertEqual(find("flat huntr"), 4)
            with self.assertRaisesRegex(mcp_server.Gone, "More than one bot fits"):
                find("hunter")
            with self.assertRaisesRegex(mcp_server.Gone, "No bot called"):
                find("weather")


class HandoffTest(unittest.TestCase):
    def test_named_agent_only(self):
        self.assertEqual(handoff("Ask Codex which of these is cheapest?"), ("codex", "which of these is cheapest"))
        self.assertEqual(handoff("please have Claude Code summarize these"), ("claude-code", "summarize these"))
        self.assertEqual(handoff("can you get claude-code to write a report"), ("claude-code", "write a report"))
        self.assertIsNone(handoff("ask me before buying"))
        self.assertIsNone(handoff("only keep under €500"))
        self.assertIsNone(handoff("ask codex"))


class MakeAndUseTest(unittest.TestCase):
    """A client makes a bot from a sentence, checks it and talks to it, all through MCP against a real engine."""

    @classmethod
    def setUpClass(cls):
        cls.site = site_server.start()
        cls.base = f"http://127.0.0.1:{cls.site.server_port}"
        cls.E = make_engine()
        cls.srv = serve(cls.E, port=0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.E.close()
        cls.site.shutdown()

    def test_create_run_message(self):
        c = MCPClient([sys.executable, "-m", "inky.mcp_server"], env={"INKY_HOME": str(self.E.home), "INKY_URL": self.url})
        c.start()
        try:
            out = c.call("create_bot", {"job": "Flats in Bari under 150k", "site": self.base + "/"})
            self.assertFalse(out["error"], out["text"])
            self.assertIn("Created Flat Hunter", out["text"])
            self.assertIn(self.base, out["text"])
            bid = self.E.store.find("bots")[0]["id"]
            self.assertTrue(wait(lambda: not self.E.busy(bid), 90))
            ran = c.call("run_bot", {"bot": "flats"})
            self.assertFalse(ran["error"], ran["text"])
            self.assertIn("results", json.loads(ran["text"])["checked"][0])
            said = c.call("message_bot", {"bot": "flat hunter", "text": "pause"})
            self.assertFalse(said["error"], said["text"])
            self.assertIn("Paused", said["text"])
            self.assertIn("No bot is being made", c.call("create_bot_status", {"id": "999"})["text"])
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main()
