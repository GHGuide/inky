"""What a bot says in chat is true: answers about what it found come from its results, a screen switch is done in code
or honestly refused, "skip X" never becomes "only X", and a daily check keeps its time of day."""
import unittest

from tests.test_engine import make_engine


class ChatTruthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.E = make_engine()

    @classmethod
    def tearDownClass(cls):
        cls.E.close()

    def bot(self, **kw):
        return self.E.create_bot({"name": "Book Bargains", "goal": "Books under £20", "start_url": "https://books.toscrape.com/", **kw})["id"]

    def test_answers_come_from_what_it_found(self):
        E, bid = self.E, self.bot()
        self.assertEqual(E.chat(bid, "what is the cheapest book?")["reply"], "I haven’t found anything yet. I haven’t learned my site yet.")
        for t, p in (("In Her Wake", "£12.84"), ("Sharp Objects", "£47.82"), ("Olio", "£23.88")):
            E.store.insert("results", {"title": t, "price": p, "link": f"https://books.toscrape.com/{t}", "new": True}, bot_id=bid, key=t)
        self.assertIn("“In Her Wake” at £12.84", E.chat(bid, "what is the cheapest book?")["reply"])
        self.assertIn("“Sharp Objects” at £47.82", E.chat(bid, "which one is the most expensive?")["reply"])
        self.assertIn("3 things", E.chat(bid, "how many books did you find?")["reply"])
        E.chat(bid, "only keep under 30")  # your rules as they are now, not as they were at the last run
        self.assertIn("“Olio” at £23.88", E.chat(bid, "which one is the most expensive?")["reply"])
        self.assertIn("2 things that pass your rules", E.chat(bid, "how many did you find?")["reply"])

    def test_screen_is_switched_or_honestly_refused(self):
        E, bid = self.E, self.bot()
        E.store.set_setting("app", {**E.store.setting("app", {}), "screen_allowed": False})
        self.assertIn("can’t use your screen", E.chat(bid, "work on my screen from now on")["reply"])
        self.assertEqual(E.store.get("bots", bid)["mode"], "own")
        E.store.set_setting("app", {**E.store.setting("app", {}), "screen_allowed": True})
        self.assertIn("Done", E.chat(bid, "work on my screen from now on")["reply"])
        self.assertEqual(E.store.get("bots", bid)["mode"], "screen")
        E.chat(bid, "go back to your own computer")
        self.assertEqual(E.store.get("bots", bid)["mode"], "own")

    def test_skip_is_never_only(self):
        E, bid = self.E, self.bot()
        E.apply_action(bid, {"type": "add_rule", "text": "skip senior roles", "filter": {"field": "title", "op": "contains", "value": "senior"}})
        f = E.store.get("bots", bid)["filters"][-1]
        self.assertEqual(f["op"], "not_contains")
        E.apply_action(bid, {"type": "add_rule", "text": "remote only, no hybrid", "filter": {"field": "text", "op": "contains", "value": "remote"}})
        self.assertEqual(E.store.get("bots", bid)["filters"][-1]["op"], "contains")

    def test_daily_checks_keep_their_time(self):
        E = self.E
        bid = E.create_bot({"name": "Flats", "job": "Every evening, find flats in Bari", "every_minutes": 1440})["id"]
        self.assertEqual(E.store.get("bots", bid)["schedule"]["at"], "18:00")
        r = E.chat(bid, "every morning at 9")
        self.assertIn("09:00", r["reply"])
        self.assertEqual(E.store.get("bots", bid)["schedule"]["at"], "09:00")

    def test_plain_commands_do_what_they_say(self):
        E, bid = self.E, self.bot(every_minutes=1440)
        self.assertIn("only run when you ask", E.chat(bid, "only when I ask")["reply"])
        self.assertEqual(E.store.get("bots", bid)["schedule"]["every_minutes"], 0)
        E.chat(bid, "only keep under 15")
        self.assertIn("removed the rule", E.chat(bid, "forget that rule")["reply"])
        self.assertEqual(E.store.get("bots", bid)["filters"], [])
        from inky.bots import is_question
        self.assertTrue(is_question("📚📚🔥 any cheap ones? 😍"))
        with self.assertRaisesRegex(ValueError, "no connector called"):
            E.apply_action(bid, {"type": "delegate", "server": "Nobody", "tool": "x", "args": {}})

    def test_team_shows_milestones(self):
        E, bid = self.E, self.bot()
        E.store.message(bid, "bot", "🎉 10 runs on the job! I unlocked the scarf.", team=True)  # as check_level writes it
        E.store.message(bid, "bot", "Good night!", unprompted=True, team=True)  # as evening() writes it
        texts = [f["text"] for f in E.team_feed() if f["bot"] == bid]
        self.assertIn("Good night!", texts)
        self.assertTrue(any("unlocked the scarf" in t for t in texts))

    def test_a_draft_keeps_your_address_and_your_numbers(self):
        d = self.E.draft_bot("Every day, find flats in Bari under €150.000 on 127.0.0.1:8772")  # the scripted model leaves start_url empty
        self.assertEqual(d["start_url"], "http://127.0.0.1:8772")  # your own machine: http, as you wrote it
        self.assertEqual([f["value"] for f in d["filters"]], [150000])  # “150.000” is the 150000 you said


if __name__ == "__main__":
    unittest.main()
