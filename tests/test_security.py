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
        req = urllib.request.Request(self.url + "/api/bots", headers={"X-Inky-Token": self.E.token[:-1] + "x"})
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


if __name__ == "__main__":
    unittest.main()
