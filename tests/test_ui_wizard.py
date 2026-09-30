"""The setup wizard in a real browser: every step's Continue is reachable at the app's smallest window,
and choices open inside the wizard instead of sending you to other pages."""
import threading
import unittest

from playwright.sync_api import sync_playwright

from inky.server import serve
from tests.test_engine import make_engine


class WizardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.E = make_engine()
        cls.srv = serve(cls.E, port=0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}/"
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.E.close()

    def page(self, w, h):
        pg = self.browser.new_page(viewport={"width": w, "height": h})
        self.errors = []
        pg.on("pageerror", lambda e: self.errors.append(str(e)))
        return pg

    def on_step(self, pg, n):
        """The new step is on screen (not the last one's button, which is about to go)."""
        pg.wait_for_function(f"(document.querySelector('.wsteps li.on i') || {{}}).textContent === '{n}' && document.querySelector('#wnext')", timeout=20000)

    def walk(self, w, h):
        pg = self.page(w, h)
        pg.goto(self.url + "#/setup/1")
        self.on_step(pg, 1)
        for n in range(1, 7):
            self.assertTrue(pg.evaluate("location.hash").startswith(f"#/setup/{n}"), f"step {n} at {w}x{h}")
            nxt = pg.locator("#wnext")
            nxt.scroll_into_view_if_needed()
            box = nxt.bounding_box()
            self.assertTrue(box and box["y"] >= 0 and box["y"] + box["height"] <= h, f"Continue out of view on step {n} at {w}x{h}: {box}")
            if n < 6:
                nxt.click()
                pg.wait_for_function(f"location.hash.startsWith('#/setup/{n + 1}')")
                self.on_step(pg, n + 1)
        self.assertEqual(self.errors, [])
        pg.close()

    def test_every_step_reachable_small_and_large(self):
        self.walk(900, 600)
        self.walk(1280, 820)

    def test_choices_stay_in_the_wizard(self):
        pg = self.page(1280, 820)
        pg.goto(self.url + "#/setup/3")
        pg.wait_for_selector("[data-prov='openrouter']")
        self.assertGreater(pg.locator("[data-prov='openrouter'] .logo").count(), 0)
        pg.click("[data-prov='openrouter']")
        pg.wait_for_selector("#keyfield", state="visible")
        self.assertTrue(pg.evaluate("location.hash").startswith("#/setup/3"))
        pg.goto(self.url + "#/setup/2")
        pg.wait_for_selector("#pairurl", state="visible")
        pg.goto(self.url + "#/setup/5")
        pg.wait_for_selector("#tgtoken", state="visible")
        self.assertTrue(pg.evaluate("location.hash").startswith("#/setup/5"))
        self.assertEqual(self.errors, [])
        pg.close()

    def test_a_slow_page_doesnt_freeze_or_break_the_transition(self):
        """CI caught it: a page whose data takes over 4 s aborted the view transition (and froze the screen until then)."""
        import time
        from inky import server
        i = next(i for i, r in enumerate(server.ROUTES) if r[0] == "GET" and r[1].pattern == "^/api/setup$")
        method, rx, fn = server.ROUTES[i]
        server.ROUTES[i] = (method, rx, lambda *a, **k: (time.sleep(5), fn(*a, **k))[1])
        self.addCleanup(server.ROUTES.__setitem__, i, (method, rx, fn))
        pg = self.page(900, 600)
        pg.goto(self.url + "#/setup/1")
        self.on_step(pg, 1)
        pg.evaluate("location.hash = '#/setup/2'")
        self.on_step(pg, 2)
        self.assertEqual(self.errors, [])
        pg.close()

    def test_telegram_guided_in_the_wizard(self):
        """Paste the token, send /start (the fake already has one), and Inky finds you and says hello."""
        import os
        from http.server import ThreadingHTTPServer
        from unittest import mock
        from tests.test_connectors import Fake
        fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=fake.serve_forever, daemon=True).start()
        self.addCleanup(fake.shutdown)
        with mock.patch.dict(os.environ, {"TELEGRAM_API": f"http://127.0.0.1:{fake.server_port}"}):
            pg = self.page(1280, 820)
            pg.goto(self.url + "#/setup/5")
            pg.fill("#tgtoken", "123:abc")
            pg.click("#tgsave")
            pg.wait_for_function("document.querySelector('#tgmsg').textContent.includes('Found you')", timeout=15000)
        self.assertEqual(self.E.store.setting("telegram")["chat_id"], 4242)
        self.assertTrue(any(p.endswith("/sendMessage") for m, p, b in Fake.seen))
        self.assertEqual(self.errors, [])
        pg.close()


if __name__ == "__main__":
    unittest.main()
