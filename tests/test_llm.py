import json
import os
import platform
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from inky.keys import Keys
from inky.llm import LLM, parse_json
from inky.store import Store


class FakeModel(BaseHTTPRequestHandler):
    reply = '```json\n{"ok": 1, "text": "a } inside"}\n```'

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeModel.last = body
        out = {"choices": [{"message": {"content": FakeModel.reply}}], "usage": {"prompt_tokens": 11, "completion_tokens": 5}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class LLMTest(unittest.TestCase):
    def test_parse_json_variants(self):
        self.assertEqual(parse_json('sure! {"a": {"b": 2}} done'), {"a": {"b": 2}})
        self.assertEqual(parse_json("<think>{no}</think>```json\n{\"x\": 1}\n```"), {"x": 1})

    def test_role_routes_to_custom_provider_and_counts_usage(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeModel)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        home = tempfile.mkdtemp()
        store = Store(os.path.join(home, "t.db"))
        store.set_setting("custom_provider", {"base": f"http://127.0.0.1:{srv.server_port}/v1"})
        seen = []
        llm = LLM(store, Keys(home, backend="file"), on_usage=lambda bot, u: seen.append(u))
        llm.set_role("chat", "custom", "fake-1")
        obj, usage = llm.ask_json("chat", "sys", "hi", bot_id=3)
        self.assertEqual(obj["text"], "a } inside")
        self.assertEqual((usage["in"], usage["out"], usage["model"]), (11, 5, "fake-1"))
        self.assertEqual(FakeModel.last["model"], "fake-1")
        self.assertEqual(len(seen), 1)
        srv.shutdown()

    def test_file_keys_are_private(self):
        home = tempfile.mkdtemp()
        k = Keys(home, backend="file")
        k.set("anthropic", "sk-test-000")
        self.assertEqual(k.get("anthropic"), "sk-test-000")
        if os.name == "posix":  # Windows has no Unix modes; the file lives in your own profile folder
            self.assertEqual(oct(os.stat(os.path.join(home, "keys.json")).st_mode & 0o777), "0o600")
        k.delete("anthropic")
        self.assertIsNone(k.stored("anthropic"))

    @unittest.skipUnless(platform.system() == "Darwin", "macOS keychain")
    def test_keychain_roundtrip(self):
        k = Keys(tempfile.mkdtemp(), backend="keychain", service="inky-selftest")
        k.set("custom", "sk-selftest-123")
        try:
            self.assertEqual(k.stored("custom"), "sk-selftest-123")
        finally:
            k.delete("custom")
        self.assertIsNone(k.stored("custom"))


if __name__ == "__main__":
    unittest.main()
