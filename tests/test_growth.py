"""Growth: days on the job, streaks, time and AI saved, levels that unlock accessories, the diary."""
import unittest
from datetime import datetime, timedelta

from inky import growth


def run(day, ok=True, ai=0, steps=4):
    return {"ts": day.timestamp(), "status": "ok" if ok else "problem", "kind": "replay", "ai_calls": ai, "steps": steps}


class GrowthTest(unittest.TestCase):
    now = datetime(2026, 9, 30, 20)

    def test_streak_counts_consecutive_days_with_a_good_run(self):
        runs = [run(self.now - timedelta(days=d)) for d in (0, 1, 2, 4)] + [run(self.now - timedelta(days=3), ok=False)]
        s = growth.stats({"created": (self.now - timedelta(days=9)).timestamp()}, runs, [{"steps": [1, 2, 3, 4]}], self.now.timestamp())
        self.assertEqual((s["days"], s["streak"], s["runs"]), (10, 3, 4))
        self.assertEqual(s["ai_saved"], 16)
        self.assertGreater(s["hours_saved"], 0)

    def test_streak_survives_until_tonight(self):
        runs = [run(self.now - timedelta(days=d)) for d in (1, 2)]
        s = growth.stats({"created": (self.now - timedelta(days=5)).timestamp()}, runs, [], self.now.timestamp())
        self.assertEqual(s["streak"], 2)

    def test_levels_and_unlocks(self):
        runs = [run(self.now) for _ in range(52)]
        s = growth.stats({"created": self.now.timestamp()}, runs, [], self.now.timestamp())
        self.assertEqual(s["unlocked"], ["scarf", "party"])
        self.assertEqual(s["next"], {"at": 100, "acc": "star"})
        self.assertEqual(growth.level_up(9, 10), "scarf")
        self.assertIsNone(growth.level_up(10, 11))

    def test_diary_in_first_person(self):
        t = growth.diary_entry({"name": "Bari Flats", "look": {"kind": "octopus"}},
                               [{"kind": "fixed", "text": "Step 3 changed"}], [run(self.now), run(self.now)])
        self.assertIn("I ", t)
        self.assertIn("2 runs", t)
        self.assertIn("fixed", t.lower())
        self.assertIn("quiet", growth.diary_entry({"name": "X", "look": {"kind": "cat"}}, [], []).lower())


if __name__ == "__main__":
    unittest.main()
