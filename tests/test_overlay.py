"""The on-screen overlay: chat typing never reaches the page, Esc stops the bot, a real mouse pauses it,
and the bot's own actions don't count as you. Runs the overlay in a headless browser."""
import tempfile
import time
import unittest

from inky.computer import Computer
from tests import site_server


class OverlayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = site_server.start()
        cls.base = f"http://127.0.0.1:{cls.site.server_port}"
        cls.msgs = []
        cls.c = Computer(7, tempfile.mkdtemp(), look={"speed": "turbo"}, on_control=lambda bid, m: cls.msgs.append(m))
        cls.c.call("overlay", mode="screen", name="Bari Flats", pill={"title": "Bari Flats is using your screen", "sub": "step 3"})

    @classmethod
    def tearDownClass(cls):
        cls.c.close()
        cls.site.shutdown()

    def wait_for(self, kind, t=5):
        end = time.time() + t
        while time.time() < end:
            if any(m.get("type") == kind for m in self.msgs):
                return True
            time.sleep(0.1)
        return False

    def test_chat_is_isolated_and_controls_work(self):
        c = self.c
        page = c.call("open", self.base + "/")
        c.call("overlay", mode="screen", name="Bari Flats")
        by = {e["name"]: e["i"] for e in page["elements"]}
        # the bot's own clicks and typing are not "you"
        self.msgs.clear()
        c.call("act", "fill", by["Comune"], "Bari")
        time.sleep(0.6)
        self.assertFalse(any(m.get("type") == "user_input" for m in self.msgs))
        # open chat with Alt+C, type, send: the text reaches the bot, not the page
        pw = c.page
        c.call("user", "key", key="Alt+KeyC")
        c.q.put((lambda: pw.keyboard.type("skip ground floors"), (), {}, _Fut()))
        time.sleep(0.4)
        c.q.put((lambda: pw.keyboard.press("Enter"), (), {}, _Fut()))
        self.assertTrue(self.wait_for("chat"))
        chat = next(m for m in self.msgs if m.get("type") == "chat")
        self.assertEqual(chat["text"], "skip ground floors")
        self.assertEqual(c.call("extract", {"item": "form", "fields": {"v": "#comune@value"}})[0]["v"], "Bari")
        # a real mouse move pauses; Esc stops
        self.msgs.clear()
        c.q.put((lambda: (pw.mouse.move(600, 500), pw.mouse.move(640, 520)), (), {}, _Fut()))
        self.assertTrue(self.wait_for("user_input"))
        c.q.put((lambda: pw.keyboard.press("Escape"), (), {}, _Fut()))
        self.assertTrue(self.wait_for("stop"))


class _Fut:
    def set_result(self, r):
        pass

    def set_exception(self, e):
        raise e


if __name__ == "__main__":
    unittest.main()
