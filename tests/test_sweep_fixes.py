"""Engine fixes from the full sweep: only a clear yes goes ahead, your own rules are enforced, the model only does
what you asked, results are new only once, schedules and files are checked."""
import time
import unittest
from types import SimpleNamespace

from inky import library, skills
from inky.bots import Ctx, close_match, minutes, plain_error, rule_hit
from tests.test_engine import make_engine


class GateTest(unittest.TestCase):
    def ctx(self, rules, answer):
        E = SimpleNamespace(ask=lambda *a, **k: answer)
        c = Ctx.__new__(Ctx)
        c.e, c.bot_id, c.run = E, 1, None
        c.bot = {"name": "Flat Hunter", "rules": rules}
        c.computer = SimpleNamespace(call=lambda *a, **k: [])
        return c

    def test_only_a_clear_yes_goes_ahead(self):
        send = {"action": "click", "text": "Click Invia"}
        el = {"role": "button", "name": "Invia"}
        for answer in ("OK", "Skip", None, "Dismiss"):
            with self.assertRaises(skills.NeedsHelp, msg=answer):
                self.ctx([], answer).gate(send, el, {"url": "x"})
        self.ctx([], "Approve").gate(send, el, {"url": "x"})

    def test_your_rules_are_enforced(self):
        rules = [{"kind": "ask", "text": "Ask me first before contacting any agency"}, {"kind": "never", "text": "Never book a viewing"}]
        with self.assertRaises(skills.NeedsHelp) as e:  # an ask rule turns an ordinary click into a question (here: denied)
            self.ctx(rules, "Deny").gate({"action": "click", "text": "Click Contact agency"}, {"role": "link", "name": "Contact agency"}, {"url": "x"})
        self.assertEqual(e.exception.kind, "denied")
        with self.assertRaises(skills.NeedsHelp) as e:
            self.ctx(rules, "Approve").gate({"action": "click", "text": "Click Book viewing"}, {"role": "button", "name": "Book"}, {"url": "x"})
        self.assertEqual(e.exception.kind, "blocked")
        self.ctx(rules, "Deny").gate({"action": "click", "text": "Click Search"}, {"role": "button", "name": "Cerca"}, {"url": "x"})
        self.assertIsNone(rule_hit(rules, "ask", "Type Bari"))


class ActionsTest(unittest.TestCase):
    def setUp(self):
        self.E = make_engine()
        self.addCleanup(self.E.close)
        self.b = self.E.create_bot({"name": "Book Bargains", "goal": "books", "start_url": "https://books.toscrape.com/"})
        self.E.update_bot(self.b["id"], {"memory": [{"text": "I prefer paperbacks"}, {"text": "Budget is 20 pounds"}]})

    def test_no_learning_unless_asked_and_forget_is_precise(self):
        with self.assertRaises(ValueError):
            self.E.apply_action(self.b["id"], {"type": "learn", "url": "https://example.com"}, said="How many books did you find?")
        with self.assertRaises(ValueError):  # one letter never wipes everything
            self.E.apply_action(self.b["id"], {"type": "forget", "text": "a"}, said="forget a")
        self.E.apply_action(self.b["id"], {"type": "forget", "text": "paperbacks"}, said="forget that I like paperbacks")
        self.assertEqual([m["text"] for m in self.E.store.get("bots", self.b["id"])["memory"]], ["Budget is 20 pounds"])
        with self.assertRaises(ValueError):
            self.E.apply_action(self.b["id"], {"type": "add_automation", "when": "new_results", "server": "", "tool": ""}, said="add one")

    def test_library_agents_only_learn_their_sites(self):
        self.E.store.update("bots", self.b["id"], allowed_domains=["books.toscrape.com"])
        with self.assertRaises(ValueError):
            self.E.apply_action(self.b["id"], {"type": "learn", "url": "https://example.com"}, said="learn https://example.com")

    def test_rule_kinds_from_chat(self):
        self.E.apply_action(self.b["id"], {"type": "add_rule", "text": "Never buy anything", "kind": "never"}, said="never buy")
        self.assertIn({"kind": "never", "text": "Never buy anything"}, self.E.store.get("bots", self.b["id"])["rules"])


class ResultsAndScheduleTest(unittest.TestCase):
    def test_new_only_once_and_next_run(self):
        E = make_engine()
        self.addCleanup(E.close)
        b = E.create_bot({"name": "Watcher", "goal": "x", "start_url": "https://books.toscrape.com/", "every_minutes": 60})
        self.assertEqual(E.add_results(b["id"], [{"title": "A", "link": "/a"}], "test"), 1)
        self.assertEqual(E.add_results(b["id"], [{"title": "A", "link": "/a"}], "test"), 0)
        E.store.insert("skills", {"name": "s", "steps": [{"action": "extract", "spec": {}}], "start_url": "https://books.toscrape.com/"}, bot_id=b["id"], status="ok")
        E.store.update("bots", b["id"], schedule={"every_minutes": 60, "quiet_from": "", "quiet_to": ""})
        nxt = E.bot_view(E.store.get("bots", b["id"]))["next_run"]
        self.assertLess(abs(nxt - time.time()), 5)  # never ran: due now, not an hour that keeps moving
        self.assertEqual([minutes(x) for x in ("every morning", "hourly", -5, "30", None)], [1440, 60, 0, 30, 0])

    def test_in_takes_a_comma_list(self):
        self.assertTrue(skills.keep({"title": "Flat in Japigia"}, {"field": "title", "op": "in", "value": "Japigia, Madonnella"}))
        self.assertFalse(skills.keep({"title": "Flat in Libertà"}, {"field": "title", "op": "in", "value": "Japigia"}))


class FilesTest(unittest.TestCase):
    def test_private_hosts_and_plain_errors(self):
        self.assertTrue(library.private_host("192.168.1.5") and library.private_host("nas.local") and library.private_host("127.0.0.1"))
        self.assertFalse(library.private_host("books.toscrape.com"))
        self.assertIn("doesn’t exist", plain_error(Exception("Page.goto: net::ERR_NAME_NOT_RESOLVED at https://x")))
        self.assertTrue(close_match("paperbacks", "I prefer paperbacks") and not close_match("pa", "paperbacks"))
        self.assertIsNone(skills.web_address("Bari", "http://127.0.0.1:8766/"))
        self.assertEqual(skills.web_address("/page-2", "http://127.0.0.1:8766/search"), "http://127.0.0.1:8766/page-2")

    def test_import_names_and_bad_files(self):
        from inky import transfer
        E = make_engine()
        self.addCleanup(E.close)
        b = E.create_bot({"name": "Twin", "goal": "x"})
        bundle = transfer.export_bot(E, b["id"])
        self.assertEqual(E.store.get("bots", transfer.import_bot(E, bundle))["name"], "Twin 2")
        for bad in ([1, 2], {"inky_skill": 1}, {"bundle": 1}):
            with self.assertRaises(ValueError):
                transfer.import_bot(E, bad)


if __name__ == "__main__":
    unittest.main()
