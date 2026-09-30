import os
import tempfile
import unittest

from inky.store import Store
from inky.bus import Bus


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.s = Store(os.path.join(tempfile.mkdtemp(), "t.db"))

    def test_bot_roundtrip_and_update(self):
        bid = self.s.insert("bots", {"name": "Flat Hunter", "rules": [{"text": "euro only"}]}, status="idle")
        b = self.s.get("bots", bid)
        self.assertEqual(b["name"], "Flat Hunter")
        self.assertEqual(b["rules"][0]["text"], "euro only")
        self.s.update("bots", bid, status="working", name="FH")
        b = self.s.get("bots", bid)
        self.assertEqual((b["name"], b["status"]), ("FH", "working"))

    def test_needs_resolve_and_results_upsert(self):
        nid = self.s.insert("needs", {"title": "Send?"}, bot_id=1, status="open")
        self.assertEqual(len(self.s.find("needs", status="open")), 1)
        self.s.update("needs", nid, status="resolved", decision="approve")
        self.assertEqual(self.s.find("needs", status="open"), [])
        _, new = self.s.upsert_key("results", 1, "a", {"price": 1})
        _, again = self.s.upsert_key("results", 1, "a", {"price": 2})
        self.assertTrue(new)
        self.assertFalse(again)
        self.assertEqual(self.s.find("results", bot_id=1)[0]["price"], 2)

    def test_settings_and_bus(self):
        self.s.set_setting("setup_done", True)
        self.assertTrue(self.s.setting("setup_done"))
        bus = Bus()
        q = bus.subscribe()
        bus.publish("bot", id=1)
        self.assertEqual(q.get_nowait(), {"kind": "bot", "id": 1})


if __name__ == "__main__":
    unittest.main()
