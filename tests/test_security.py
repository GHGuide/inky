"""What a public release promises about the engine's own page and API."""
import re
import threading
import unittest
import urllib.request
from pathlib import Path

from inky.server import serve
from inky.transfer import pair_code
from tests.test_engine import make_engine

UI = Path(__file__).resolve().parent.parent / "inky" / "ui"


class SecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.E = make_engine()
        cls.srv = serve(cls.E, port=0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.E.close()

    def test_page_has_a_strict_policy_and_no_inline_handlers(self):
        r = urllib.request.urlopen(self.url + "/")
        csp = r.headers["Content-Security-Policy"]
        self.assertIn("script-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        for f in list(UI.glob("*.js")) + [UI / "index.html"]:  # inline handlers would be blocked by that policy
            self.assertIsNone(re.search(r"\son(click|load|error|input|change)=", f.read_text(encoding="utf-8")), f.name)
        self.assertNotIn("fonts.googleapis.com", (UI / "index.html").read_text(encoding="utf-8"))  # fonts are bundled

    def test_api_needs_the_token(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(self.url + "/api/bots")
        self.assertEqual(e.exception.code, 401)
        wrong = self.E.token[:-1] + ("y" if self.E.token.endswith("x") else "x")  # one in 64 tokens already ends in x
        req = urllib.request.Request(self.url + "/api/bots", headers={"X-Inky-Token": wrong})
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(req)

    def test_starting_never_looks_up_this_computers_name(self):
        # macOS holds that lookup ~30 s the first time a new app touches the network: a first launch sat waiting
        from unittest import mock
        import socket
        from inky.server import Server, Handler
        with mock.patch.object(socket, "getfqdn", side_effect=AssertionError("looked up the name")), \
                mock.patch.object(socket, "gethostbyaddr", side_effect=AssertionError("looked up the name")):
            srv = Server(("127.0.0.1", 0), Handler)
            srv.server_close()

    def test_pair_code_reveals_nothing_of_the_token(self):
        code = pair_code(self.E.token)
        self.assertEqual(len(code), 6)
        self.assertNotIn(code.lower(), self.E.token.lower())

    def test_requests_are_bounded(self):
        import http.client
        port = self.srv.server_port

        def send(path, body, headers=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.request("POST", path, body=body, headers=headers or {})
            r = c.getresponse()
            out = r.status, r.read()
            c.close()
            return out[0]
        self.assertEqual(send("/api/pair", b"x" * 5000), 413)  # before the token, only a pairing code fits
        tok = {"X-Inky-Token": self.E.token, "Content-Type": "application/json"}
        self.assertEqual(send("/api/bots/draft", b"[1, 2]", tok), 400)  # not an object
        self.assertEqual(send("/api/bots/draft", b"\xff\xfe", tok), 400)  # not UTF-8
        self.assertEqual(send("/api/bots/draft", b"[" * 100000 + b"]" * 100000, tok), 400)  # nested too deep

    def test_bots_never_open_files_or_inky_itself(self):
        from inky import computer
        self.assertIn(self.srv.server_port, computer.SELF_PORTS)
        for url in ("file:///etc/passwd", "javascript:alert(1)", f"http://127.0.0.1:{self.srv.server_port}/",
                    f"http://localhost:{self.srv.server_port}/api/state", f"http://[::1]:{self.srv.server_port}/"):
            with self.assertRaises(ValueError, msg=url):
                computer.safe_url(url)
        self.assertEqual(computer.safe_url("https://books.toscrape.com/"), "https://books.toscrape.com/")

    def test_a_file_import_is_checked_and_a_site_file_cant_open_local_files(self):
        import json
        tok = {"X-Inky-Token": self.E.token, "Content-Type": "application/json"}

        def post(path, body):
            req = urllib.request.Request(self.url + path, method="POST", data=json.dumps(body).encode(), headers=tok)
            try:
                return 200, json.loads(urllib.request.urlopen(req).read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        hostile = {"bundle": 1, "bot": {"name": "Deal Finder", "mode": "screen", "start_url": "https://books.toscrape.com/",
                                        "memory": [{"text": "x"}]}, "skills": [],
                   "cookies": [{"name": "sid", "value": "1", "domain": "books.toscrape.com", "path": "/"}]}
        code, r = post("/api/import", hostile)
        self.assertEqual(code, 200, r)
        b = self.E.store.get("bots", r["bot"]["id"])
        self.assertEqual((b["mode"], b["memory"], b.get("pending_cookies")), ("own", [], None))
        code, r = post(f"/api/bots/{b['id']}/skills/import", {"inky_skill": 1, "start_url": "https://books.toscrape.com/",
                                                              "steps": [{"action": "goto", "value": "file:///etc/passwd", "text": "x"}]})
        self.assertEqual(code, 400)
        self.assertIn("isn’t a web address", r["error"])
        for route in ("share-link", "publish"):  # posting in public needs the yes the app asks for, not just an API call
            code, r = post(f"/api/bots/{b['id']}/{route}", {"meta": {}})
            self.assertEqual(code, 400, route)
            self.assertIn("your yes", r["error"])


if __name__ == "__main__":
    unittest.main()
