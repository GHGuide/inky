"""A bot's character goes into its chat prompt; safety wording always stays."""
import unittest
from datetime import datetime

from inky import persona


class PersonaTest(unittest.TestCase):
    def test_defaults_by_kind(self):
        p = persona.normalize({}, "octopus")
        self.assertIn("ink", p["quirk"])
        self.assertTrue(0 <= p["chatty"] <= 1 and 0 <= p["playful"] <= 1)
        self.assertEqual(persona.normalize({"chatty": 5}, "cat")["chatty"], 1.0)
        self.assertEqual(persona.normalize({"catchphrase": None}, "blob")["catchphrase"], persona.DEFAULTS["blob"]["catchphrase"])

    def test_prompt_has_name_time_memory_and_safety(self):
        bot = {"name": "Bari Flats", "look": {"kind": "octopus"}, "persona": {"catchphrase": "Inked and on it!"}}
        ev = [{"ts": datetime(2026, 9, 29, 10).timestamp(), "text": "14 results, 12 pass your rules, 2 new"}]
        s = persona.prompt_lines(bot, "Leo", datetime(2026, 9, 30, 8, 15), ev)
        self.assertIn("Leo", s)
        self.assertIn("morning", s)
        self.assertIn("Tue", s)
        self.assertIn("Inked and on it!", s)
        self.assertIn(persona.SAFETY, s)

    def test_no_name_no_problem(self):
        s = persona.prompt_lines({"name": "X", "look": {"kind": "blob"}}, "", datetime(2026, 9, 30, 22), [])
        self.assertNotIn("call the user", s)
        self.assertIn("night", s)
        self.assertIn(persona.SAFETY, s)


if __name__ == "__main__":
    unittest.main()
