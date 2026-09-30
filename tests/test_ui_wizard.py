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

    def walk(self, w, h):
        pg = self.page(w, h)
        pg.goto(self.url + "#/setup/1")
        pg.wait_for_selector("#wnext")
        for n in range(1, 7):
            self.assertTrue(pg.evaluate("location.hash").startswith(f"#/setup/{n}"), f"step {n} at {w}x{h}")
            nxt = pg.locator("#wnext")
            nxt.scroll_into_view_if_needed()
            box = nxt.bounding_box()
            self.assertTrue(box and box["y"] >= 0 and box["y"] + box["height"] <= h, f"Continue out of view on step {n} at {w}x{h}: {box}")
            if n < 6:
                nxt.click()
                pg.wait_for_function(f"location.hash.startsWith('#/setup/{n + 1}')")
                pg.wait_for_selector("#wnext")
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


if __name__ == "__main__":
    unittest.main()
