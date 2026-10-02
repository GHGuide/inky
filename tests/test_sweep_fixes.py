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

    def test_never_rules_see_the_page_and_a_pause_holds_after_yes(self):
        import threading
        never = [{"kind": "never", "text": "never contact the agency"}]
        page = {"url": "http://x/contact?id=1", "title": "Contatta", "heads": ["Contatta l’agenzia"]}
        with self.assertRaises(skills.NeedsHelp) as e:  # its button only says "Invia": the page says what it's for
            self.ctx(never, "Approve").gate({"action": "click", "text": "Click Invia"}, {"role": "button", "name": "Invia"}, page)
        self.assertEqual(e.exception.kind, "blocked")
        c = self.ctx([], "Approve")
        c.run = SimpleNamespace(paused=threading.Event(), stop=True)  # you pressed Stop while it waited for your yes
        with self.assertRaises(skills.Stopped):
            c.gate({"action": "click", "text": "Click Invia"}, {"role": "button", "name": "Invia"}, {"url": "x"})

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


class AlwaysTest(unittest.TestCase):
    def test_always_is_saved_the_moment_you_choose_it(self):
        E = make_engine()
        self.addCleanup(E.close)
        b = E.create_bot({"name": "Sender", "goal": "send"})
        step = {"action": "click", "text": "Click Invia", "target": {"role": "button", "name": "Invia"}}
        sid = E.store.insert("skills", {"name": "Send", "steps": [dict(step)]}, bot_id=b["id"], status="ok")
        c = Ctx.__new__(Ctx)
        c.e, c.bot_id, c.bot = SimpleNamespace(store=E.store, ask=lambda *a, **k: "Always for this step"), b["id"], {"name": "Sender", "rules": []}
        c.run, c.computer = SimpleNamespace(skill_id=sid, check=False), SimpleNamespace(call=lambda *a, **k: [])
        c.gate(step, {"role": "button", "name": "Invia"}, {"url": "x"})
        self.assertTrue(E.store.get("skills", sid)["steps"][0].get("approved_always"))  # even if a later step fails, it won't ask again


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


    def test_questions_change_nothing_and_new_rules_only_add(self):
        bid = self.b["id"]
        with self.assertRaises(ValueError):
            self.E.apply_action(bid, {"type": "schedule", "every_minutes": 5}, said="Should you run every 5 minutes?")
        self.E.apply_action(bid, {"type": "schedule", "every_minutes": 60}, said="Could you check every hour?")
        self.assertEqual(self.E.store.get("bots", bid)["schedule"]["every_minutes"], 60)
        before = [r["text"] for r in self.E.store.get("bots", bid)["rules"]]
        reply = '{"reply": "Done", "actions": [{"type": "remove_rule", "text": "Buy or pay"}, {"type": "remember", "text": "Rule: x"}, {"type": "add_rule", "text": "Never buy anything"}]}'
        self.E.llm.chat = lambda *a, **k: (reply, {})
        self.E.chat(bid, "New rule: Never buy anything")
        b = self.E.store.get("bots", bid)
        self.assertEqual([r["text"] for r in b["rules"]], before + ["Never buy anything"])
        self.assertEqual(b["rules"][-1]["kind"], "never")
        self.assertEqual(len(b["memory"]), 2)
        self.E.llm.chat = lambda *a, **k: ('{"reply": "OK", "actions": []}', {})
        self.E.chat(bid, "New rule: price under 15")
        b = self.E.store.get("bots", bid)
        self.assertIn({"field": "price", "op": "<", "value": 15.0, "text": "price under 15"}, b["filters"])
        self.assertEqual(b["rules"][-1], {"kind": "filter", "text": "price under 15"})
        # the model's own version of the same limit never doubles it, and asking again doesn't add it twice
        dup = '{"reply": "OK", "actions": [{"type": "add_rule", "text": "price under 15", "filter": {"field": "price", "op": "<=", "value": "15"}}]}'
        self.E.llm.chat = lambda *a, **k: (dup, {})
        r = self.E.chat(bid, "New rule: price under 15")
        b = self.E.store.get("bots", bid)
        self.assertEqual(sum(1 for f in b["filters"] if f["field"] == "price"), 1)
        self.assertEqual([x["text"] for x in b["rules"]].count("price under 15"), 1)
        self.assertIn("already a rule: price under 15", r["done"])


    def test_what_did_you_do_offers_and_yes(self):
        bid = self.b["id"]
        def no_model(*a, **k):
            raise AssertionError("the recap never asks the model")
        self.E.llm.chat = no_model
        r = self.E.chat(bid, "so what did you do")
        self.assertIn("haven’t run yet", r["reply"])
        self.E.store.insert("runs", {"kind": "replay", "skill": "Cheap books", "items": 60, "matched": 14, "new": 14, "pages": 3, "ai_calls": 0}, bot_id=bid, status="ok")
        r = self.E.chat(bid, "So what did you do?")
        self.assertIn("I checked “Cheap books”", r["reply"])
        self.assertNotIn("AI", r["reply"])  # only worth saying when it was used
        # a question the model answers with a change: nothing changes, it offers a button, and “yes” does it
        self.E.llm.chat = lambda *a, **k: ('{"reply": "I’ll check every hour.", "actions": [{"type": "schedule", "every_minutes": 60}]}', {})
        self.E.chat(bid, "Should you check every hour?")
        m = self.E.store.find("messages", bot_id=bid, limit=1)[0]
        self.assertEqual(m["chips"], [{"label": "Yes, check every hour", "offer": 0}])
        self.assertNotIn("haven’t changed", m["text"])
        self.assertNotEqual(self.E.store.get("bots", bid)["schedule"]["every_minutes"], 60)
        self.E.llm.chat = no_model
        r = self.E.chat(bid, "i want that")
        self.assertEqual(self.E.store.get("bots", bid)["schedule"]["every_minutes"], 60)
        self.assertIn("check every hour", r["reply"])
        with self.assertRaises(ValueError):  # once only
            self.E.take_offer(bid, m["id"], 0)


    def test_plain_commands_need_no_model_and_limits_replace(self):
        from inky.bots import quick_command
        bid = self.b["id"]
        def no_model(*a, **k):
            raise AssertionError("plain commands never ask the model")
        self.E.llm.chat = no_model
        self.assertEqual(self.E.chat(bid, "only run when I ask")["reply"], "Done: I’ll only run when you ask.")
        self.assertEqual(self.E.store.get("bots", bid)["schedule"]["every_minutes"], 0)
        self.E.chat(bid, "every morning")
        self.assertEqual(self.E.store.get("bots", bid)["schedule"]["every_minutes"], 1440)
        self.E.chat(bid, "remember I like hardbacks")
        self.assertIn("You like hardbacks", [m["text"] for m in self.E.store.get("bots", bid)["memory"]])
        self.E.chat(bid, "forget that I like hardbacks")
        self.assertNotIn("You like hardbacks", [m["text"] for m in self.E.store.get("bots", bid)["memory"]])
        self.assertEqual(self.E.chat(bid, "stop")["reply"], "Nothing is running right now.")
        self.assertIsNone(quick_command("Should you check every 5 minutes?"))
        self.assertIsNone(quick_command("find me cheap books"))
        for t in ("under 20", "under 15"):
            self.E.apply_action(bid, {"type": "add_rule", "text": f"price {t}", "filter": {"field": "price", "op": "<", "value": int(t[-2:])}})
        b = self.E.store.get("bots", bid)
        self.assertEqual([f["value"] for f in b["filters"] if f["field"] == "price"], [15])
        self.assertNotIn("price under 20", [r["text"] for r in b["rules"]])


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

    def test_skill_edits_bump_the_version(self):
        from inky import server
        E = make_engine()
        self.addCleanup(E.close)
        b = E.create_bot({"name": "Twin", "goal": "x"})
        steps = [{"action": "goto", "text": "Open the site"}, {"action": "click", "text": "Click Next", "approved_always": True}]
        sid = E.store.insert("skills", {"name": "s", "steps": steps, "version": 1}, bot_id=b["id"], status="ok")
        ask_again = [steps[0], {**steps[1], "approved_always": False}]
        self.assertEqual(server.patch_skill(E, None, {}, {"steps": ask_again}, sid)["skill"]["version"], 2)
        self.assertEqual(server.patch_skill(E, None, {}, {"steps": ask_again[:1]}, sid)["skill"]["version"], 3)
        self.assertEqual(server.patch_skill(E, None, {}, {"name": "renamed"}, sid)["skill"]["version"], 3)  # only steps count


if __name__ == "__main__":
    unittest.main()


class HoldsUpTest(unittest.TestCase):
    def test_learning_whose_first_check_finds_nothing_is_not_kept(self):
        from unittest import mock
        from inky import skills as skills_mod
        E = make_engine()
        self.addCleanup(E.close)
        b = E.create_bot({"name": "Bikes", "goal": "find e-bikes", "start_url": "https://shop.example/"})
        learned = {"name": "Check shop.example", "start_url": "https://shop.example/", "steps": [{"action": "extract", "spec": {"item": "li"}, "text": "Read 9 results"}]}
        def empty_check(bid, sid, run, reason, repair_role="repair"):
            E.store.insert("runs", {"kind": "replay", "skill": "Check shop.example", "items": 0, "matched": 0}, bot_id=bid, status="ok")
        with mock.patch.object(skills_mod, "learn", lambda *a, **k: dict(learned)), mock.patch.object(E, "_replay", empty_check), \
                mock.patch.object(E, "computer", lambda bid: SimpleNamespace(call=lambda *a, **k: None)):
            E.learn(b["id"], "find e-bikes", "https://shop.example/").thread.join(30)
        self.assertEqual(E.store.find("skills", bot_id=b["id"]), [])  # not kept
        self.assertTrue(any("didn’t hold up" in m["text"] for m in E.store.find("messages", bot_id=b["id"])))
