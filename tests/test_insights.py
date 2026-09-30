"""Insights without AI: trends, near-misses that become suggestions, recaps, the morning paper, and the rate limit."""
import time
import unittest
from datetime import datetime

from inky import insights
from inky.store import Store


def R(price, ts, **kw):
    return {"price": f"€ {price:,}".replace(",", "."), "ts": ts, **kw}


class InsightsTest(unittest.TestCase):
    def setUp(self):
        self.s = Store(":memory:")
        self.bid = self.s.insert("bots", {"name": "Bari Flats", "schedule": {"quiet_from": "23:00", "quiet_to": "07:00"}}, status="idle")
        self.now = datetime(2026, 9, 30, 9, 0).timestamp()

    def test_trend_needs_ten_each_week(self):
        wk = 7 * 86400
        old = [R(100000 + i * 1000, self.now - wk - 3600 * (i + 1)) for i in range(10)]
        new = [R(94000 + i * 1000, self.now - 3600 * i) for i in range(10)]
        t = insights.trend(old + new, "price", self.now)
        self.assertEqual(t["field"], "price")
        self.assertLess(t["pct"], -5)
        self.assertIsNone(insights.trend(new, "price", self.now))

    def test_near_miss_suggests_a_rounded_new_limit(self):
        f = [{"field": "price", "op": "<=", "value": 150000, "text": "under 150k"}]
        items = [R(152000, self.now), R(155000, self.now), R(190000, self.now), R(120000, self.now)]
        nm = insights.near_misses(items, f)
        self.assertEqual(len(nm["items"]), 2)
        self.assertEqual(nm["suggest"], 155000)
        self.assertIsNone(insights.near_misses([R(190000, self.now)], f))

    def test_rate_limit_quiet_hours_and_open_needs(self):
        b = self.s.get("bots", self.bid)
        self.assertTrue(insights.may_post(self.s, b, self.now))
        self.s.message(self.bid, "bot", "note", unprompted=True)
        self.assertFalse(insights.may_post(self.s, b, self.now + 60))
        self.assertFalse(insights.may_post(self.s, b, datetime(2026, 10, 1, 23, 30).timestamp()))
        self.s.insert("needs", {"kind": "decision"}, bot_id=self.bid, status="open")
        self.assertFalse(insights.may_post(self.s, b, datetime(2026, 10, 2, 10).timestamp()))

    def test_recap_counts_since(self):
        self.s.insert("runs", {"kind": "replay", "items": 14, "new": 2}, bot_id=self.bid, status="ok")
        r = insights.recap(self.s, time.time() - 60)
        self.assertEqual((r[0]["name"], r[0]["runs"], r[0]["results"], r[0]["new"]), ("Bari Flats", 1, 14, 2))

    def test_morning_paper_has_text_and_a_chip(self):
        b = self.s.get("bots", self.bid)
        b["filters"] = [{"field": "price", "op": "<=", "value": 150000, "text": "under 150k"}]
        for p in (152000, 154000):
            self.s.upsert_key("results", self.bid, f"k{p}", R(p, self.now, title="flat", passed=False))
        paper = insights.morning_paper(self.s, b, self.now)
        self.assertIn("Good morning", paper["text"])
        chip = paper["chips"][0]
        self.assertEqual(chip["apply"]["filters"][0]["value"], 155000)
        self.assertEqual(list(chip["apply"]), ["filters"])


if __name__ == "__main__":
    unittest.main()
