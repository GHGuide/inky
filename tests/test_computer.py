import tempfile
import unittest

from inky.computer import Computer
from tests import site_server


class ComputerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = site_server.start()
        cls.base = f"http://127.0.0.1:{cls.site.server_port}"
        cls.c = Computer(1, tempfile.mkdtemp(), look={"speed": "turbo"})

    @classmethod
    def tearDownClass(cls):
        cls.c.close()
        cls.site.shutdown()

    def test_index_act_extract_and_overlay(self):
        page = self.c.call("open", self.base + "/")
        names = {e["name"]: e for e in page["elements"]}
        self.assertIn("Comune", names)
        self.assertEqual(names["Comune"]["role"], "textbox")
        self.assertEqual(names["Cerca"]["role"], "button")
        self.c.call("act", "click", names["Accetta"]["i"])
        page = self.c.call("elements")
        by = {e["name"]: e["i"] for e in page["elements"]}
        self.c.call("act", "fill", by["Comune"], "Bari", step_text="4 · Type Bari")
        self.c.call("act", "click", by["Cerca"])
        self.assertIn("/results", self.c.call("url"))
        rows = self.c.call("extract", {"item": ".card", "fields": {"title": ".title", "price": ".price", "link": "a.details@href"}})
        self.assertEqual(len(rows), 10)
        self.assertTrue(rows[0]["link"].startswith("http"))
        self.c.call("overlay", name="Flat Hunter", frame="#E86F51")
        st = self.c.call("elements")
        self.assertFalse(any(e["tag"] == "inky-overlay" for e in st["elements"]))
        self.assertTrue(self.c.call("overlay", step="7 · Click Cerca"))
        self.assertIsNotNone(self.c.frame)

    def test_robot_check_detected(self):
        page = self.c.call("open", self.base + "/captcha")
        self.assertTrue(page["robot"])

    def test_forms_say_what_they_send(self):
        from inky.safety import classify
        page = self.c.call("open", self.base + "/login")
        btn = next(e for e in page["elements"] if e["name"] == "Accedi" and e["role"] == "button")
        self.assertEqual(classify("click", btn, page)[0], "password")
        page = self.c.call("open", self.base + "/contact?id=1")
        box = next(e for e in page["elements"] if e["role"] == "textbox")
        self.assertEqual(classify("press", box, page)[0], "irreversible")  # Enter in a contact form sends it

    def test_never_opens_files_or_inky_itself(self):
        from inky import computer
        with self.assertRaises(ValueError):
            self.c.call("open", "file:///etc/passwd")
        computer.SELF_PORTS.add(self.site.server_port)  # pretend the test site is this computer's Inky
        try:
            with self.assertRaises(ValueError):
                self.c.call("open", f"http://localhost:{self.site.server_port}/")
            with self.assertRaises(ValueError):
                self.c.call("act", "goto", None, self.base + "/")
        finally:
            computer.SELF_PORTS.discard(self.site.server_port)
        self.assertFalse(self.c.call("open", self.base + "/").get("robot"))


if __name__ == "__main__":
    unittest.main()
