"""Learning on the kinds of pages a real user meets (tests/learn_site.py), with a scripted model and no network:
search forms, categories, pagination, prices, odd lists, banners, slow and broken pages, the pages learning must refuse,
and replay (no model unless a step breaks; one call to repair it)."""
import collections
import re
import shutil
import tempfile
import time
import unittest
import urllib.request

from inky import skills
from inky.computer import Computer
from inky.safety import classify
from tests import learn_site
from tests.test_skills import NoModel

def idx(user, name):
    """The number of the element called name in the model's table; "button:Search" picks the button, not the box."""
    role, _, name = name.rpartition(":") if re.match(r"^(button|link|textbox):", name) else ("", "", name)
    m = re.search(r"\[(\d+)\] " + (role or r"\w+") + " “" + re.escape(name) + "”", user)
    return int(m.group(1)) if m else None


KIND = {skills.PICK_LIST_SYSTEM: "pick", skills.FIT_SYSTEM: "fits", skills.EXTRACT_SYSTEM: "selectors", skills.REPAIR_SYSTEM: "repair"}


def step(action, name=None, value=None, label=None, tries=2):
    return {"action": action, "name": name, "value": value, "step": label or f"{action} {name or value}", "tries": tries}


class Plan:
    """A model that does its steps in order (each at most `tries` times, only when its element is on the page),
    then reads the results and says done. It answers learning's other questions as told."""

    def __init__(self, *steps, fits=None, repair=None, selectors=None):
        self.steps, self.fits, self.repair, self.selectors = list(steps), fits or (lambda sample: True), repair, selectors
        self.calls, self.tried = collections.Counter(), collections.Counter()

    def ask_json(self, role, system, user, bot_id=None, **kw):
        kind = KIND.get(system, "step")
        self.calls[kind] += 1
        if kind == "pick":
            return {"pick": 1}, {}
        if kind == "fits":
            ok = self.fits(user.split("RESULTS:")[1].lower())
            return {"fits": ok, "why": "fits" if ok else "a different kind of thing"}, {}
        if kind == "selectors":
            if not self.selectors:
                raise ValueError("no selectors")
            return self.selectors, {}
        if kind == "repair":
            name, conf = self.repair
            return {"index": idx(user, name), "confidence": conf, "why": "does the same"}, {}
        done = [ln.split(". ", 1)[-1] for ln in user.split("STEPS SO FAR:")[1].split("EXTRACTED:")[0].strip().splitlines()]
        for s in self.steps:
            i = idx(user, s["name"]) if s["name"] else None
            if s["step"] in done or self.tried[s["step"]] >= s["tries"] or (s["name"] and i is None):
                continue
            self.tried[s["step"]] += 1
            return {"action": s["action"], "index": i, "value": s["value"], "step": s["step"]}, {}
        return ({"action": "extract"} if "EXTRACTED: yes" not in user else {"action": "done"}), {}

    @property
    def total(self):
        return sum(self.calls.values())


class Ctx:
    """What learn/replay see. The gate works like the app's: a robot check, a password or paying stops it, and anything
    that can't be undone is asked (and the person says no here, so a test notices)."""

    def __init__(self, comp, llm, job="", filters=None):
        self.computer, self.llm = comp, llm
        self.bot = {"id": 1, "rules": [], "job": job, "filters": filters or []}
        self.gated, self.asked = [], []

    def emit(self, kind, text, **m):
        pass

    def gate(self, step, el, page):
        verdict = classify(step["action"], el, page)[0]
        self.gated.append((step.get("text"), verdict))
        if verdict == "robot":
            raise skills.NeedsHelp("robot", "robot check", "")
        if verdict == "password":
            raise skills.NeedsHelp("sign_in", "needs you to sign in", "")
        if verdict == "pay":
            raise skills.NeedsHelp("blocked", "stopped before paying", "")
        if verdict == "irreversible":
            self.asked.append(step.get("text"))
            raise skills.NeedsHelp("denied", f"asked before “{step.get('text')}”", "")

    def check(self):
        pass

    def corrections(self):
        return []


GENERIC = re.compile(r"^(details?|dettagli|view|more|read more|\(about\))$", re.I)


class LearningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = learn_site.start()
        cls.base = f"http://127.0.0.1:{cls.site.server_port}"
        cls.dirs = []
        cls.comp = cls.computer()

    @classmethod
    def computer(cls):
        d = tempfile.mkdtemp(prefix="inky-learn-")
        cls.dirs.append(d)
        return Computer(len(cls.dirs), d, look={"speed": "turbo"})

    @classmethod
    def tearDownClass(cls):
        cls.comp.close()
        cls.site.shutdown()
        for d in cls.dirs:
            shutil.rmtree(d, ignore_errors=True)

    def setUp(self):
        self.layout(1)

    def layout(self, v):
        urllib.request.urlopen(f"{self.base}/__layout?v={v}").read()

    # -------------------------------------------------------------- helpers
    def learn(self, path, job, *steps, comp=None, filters=None, **plan):
        model = Plan(*steps, **plan)
        ctx = Ctx(comp or self.comp, model, job, filters)
        skill = skills.learn(ctx, job, self.base + path)
        return skill, model, ctx

    def replay(self, skill, comp=None, model=None, filters=None):
        ctx = Ctx(comp or self.comp, model or NoModel(), skill["goal"], filters)
        return skills.replay(ctx, skill), ctx

    def texts(self, skill):
        return [s["text"] for s in skill["steps"]]

    def learned_and_repeats(self, path, job, *steps, n=None, priced=True, **kw):
        """Learn, then replay twice with no model: the same items both times, each with its own name (and price)."""
        skill, model, ctx = self.learn(path, job, *steps, **kw)
        self.assertEqual(ctx.asked, [], "asked before a step while learning")
        first, _ = self.replay(skill)
        second, _ = self.replay(skill)
        items = first["items"]
        keys = [skills.item_key(i) for i in items]
        self.assertEqual(len(keys), len(set(keys)), "results that merge into one")
        self.assertEqual(keys, [skills.item_key(i) for i in second["items"]], "the second run read something else")
        if n is not None:
            self.assertEqual(len(items), n)
        for it in items:
            self.assertTrue(it.get("title") and not GENERIC.match(it["title"]), f"a result without its own name: {it}")
            if priced:
                self.assertTrue(skills.parse_num(it.get("price")) is not None or skills.FREE.search(it.get("price") or ""), f"a price that doesn't read: {it}")
        return skill, model, first

    # -------------------------------------------------------------- searching
    def test_get_search_form(self):
        skill, model, out = self.learned_and_repeats("/find", "Find e-bikes", step("fill", "textbox:Search", "e-bike", "Type e-bike"),
                                                     step("click", "button:Search", label="Click Search"), n=25)
        self.assertEqual(self.texts(skill), ["Type e-bike", "Click Search", "Read 10 results", "Next page (Next ›)"])
        self.assertEqual(out["pages"], 3)
        self.assertLessEqual(model.total, 6)

    def test_max_pages_and_rules(self):
        skill, _, _ = self.learn("/find", "Find e-bikes", step("fill", "textbox:Search", "e-bike", "Type e-bike"), step("click", "button:Search", label="Click Search"))
        out, _ = self.replay(dict(skill, max_pages=2))
        self.assertEqual((out["pages"], len(out["items"])), (2, 20))
        cheap = skills.apply_filters(out["items"], [{"field": "price", "op": "<=", "value": 1000}])
        self.assertTrue(cheap and all(skills.parse_num(i["price"]) <= 1000 for i in cheap))

    def test_search_box_with_no_button(self):
        skill, _, _ = self.learned_and_repeats("/enter/", "Find e-bikes", step("fill", "textbox:Search", "e-bike", "Type e-bike"),
                                               step("press", "textbox:Search", "Enter", "Press Enter"), n=25)
        self.assertEqual(self.texts(skill)[:3], ["Type e-bike", "Press Enter", "Read 10 results"])

    def test_unsent_search_gets_enter(self):
        skill, _, _ = self.learned_and_repeats("/enter/", "Find e-bikes", step("fill", "textbox:Search", "e-bike", "Type e-bike"), n=25)
        self.assertEqual(self.texts(skill)[:3], ["Type e-bike", "Press Enter to search", "Read 10 results"])

    def test_aspnet_post_form_searches_without_asking(self):
        skill, _, ctx = self.learn("/aspx/", "Find e-bikes", step("fill", "Search bikes", "e-bike", "Type e-bike"), step("click", "button:Search", label="Click Search"))
        self.assertEqual(ctx.asked, [])
        self.assertEqual(self.texts(skill), ["Type e-bike", "Click Search", "Read 25 results"])
        out, rctx = self.replay(skill)
        self.assertEqual((len(out["items"]), rctx.asked), (25, []))

    def test_aspnet_form_parts(self):
        page = self.comp.call("open", self.base + "/aspx/")
        verdict = {e["name"]: classify("click" if e["role"] == "button" else "press", e, page)[0] for e in page["elements"] if e["form"] and e["role"] != "link"}
        self.assertEqual(verdict, {"Search bikes": "ok", "Search": "ok", "User name": "password", "Password": "password", "Log in": "password",
                                   "Newsletter": "irreversible", "Subscribe": "irreversible"})
        page = self.comp.call("open", self.base + "/contact")  # a contact form is still a contact form, whatever is inside it
        self.assertEqual(classify("click", next(e for e in page["elements"] if e["name"] == "Continue"), page)[0], "irreversible")

    def test_category_links_instead_of_search(self):
        skill, _, _ = self.learned_and_repeats("/cats/", "Find e-bikes", step("click", "E-bikes", label="Open E-bikes"), n=25)
        self.assertEqual(self.texts(skill)[:2], ["Open E-bikes", "Read 10 results"])

    # -------------------------------------------------------------- pagination
    def test_numbered_pages(self):
        _, _, out = self.learned_and_repeats("/numbered", "Find e-bikes")
        self.assertEqual((out["pages"], len(out["items"])), (3, 24))

    def test_load_more_button(self):
        _, _, out = self.learned_and_repeats("/more", "Find e-bikes")
        self.assertEqual(len(out["items"]), 25)  # every one once, though each “Load more” shows the earlier ones again

    def test_infinite_scroll_reads_what_is_shown(self):
        skill, _, out = self.learned_and_repeats("/scroll", "Find e-bikes")
        self.assertGreaterEqual(len(out["items"]), 10)
        self.assertFalse(any(s.get("next_page") for s in skill["steps"]))

    # -------------------------------------------------------------- prices, titles, odd lists
    def test_prices(self):
        _, _, out = self.learned_and_repeats("/prices", "Find bike deals")
        self.assertEqual([skills.parse_num(i["price"]) or 0 for i in out["items"]], [p for _, p in learn_site.PRICES])
        self.assertEqual(len(skills.apply_filters(out["items"], [{"field": "price", "op": "<=", "value": 100}])), 5)  # Free counts as 0

    def test_parse_num(self):
        for s, n in (("€ 1.234,56", 1234.56), ("$1,234.56", 1234.56), ("£12", 12), ("from €99", 99),
                     ("€100 – €200", 100), ("1 234,56 €", 1234.56), ("€ 78.915", 78915), ("Price on request", None), ("Free", None)):
            self.assertEqual(skills.parse_num(s), n, s)
        for price in ("Free", "Gratis", "€ 0", "£12"):  # free things pass a price limit
            self.assertTrue(skills.keep({"price": price}, {"field": "price", "op": "<=", "value": 20}), price)

    def test_results_without_prices(self):
        _, _, out = self.learned_and_repeats("/articles", "Find new articles about cycling", n=15, priced=False)
        self.assertNotIn("price", out["items"][0])

    def test_results_in_a_table(self):
        _, _, out = self.learned_and_repeats("/table", "Find e-bikes", n=12)
        self.assertEqual([skills.parse_num(i["price"]) for i in out["items"]], [b["price"] for b in learn_site.BIKES[:12]])

    def test_titles_never_details_or_view(self):
        _, _, out = self.learned_and_repeats("/details", "Find flats", n=9)
        self.assertTrue(out["items"][0]["title"].startswith("Flat on Via Roma 0"))
        _, _, out = self.learned_and_repeats("/details2", "Find bikes", n=9)
        self.assertTrue(out["items"][0]["title"].startswith("Red city bike"))

    def test_shared_links_dont_merge_results(self):
        _, _, out = self.learned_and_repeats("/quotes", "Find quotes about life", n=29, priced=False)
        self.assertEqual([i["title"] for i in out["items"]], [q["text"] for q in learn_site.QUOTES])

    def test_a_reading_step_on_shared_links_still_keeps_results_apart(self):  # one a model wrote, or learned before
        skill = {"name": "Quotes", "goal": "Find quotes", "start_url": self.base + "/quotes", "max_pages": 1, "steps": [
            {"action": "extract", "spec": {"item": "div.quote", "fields": {"title": "a.tag", "link": "a.tag@href", "text": ""}}, "text": "Read"}]}
        out, _ = self.replay(skill)
        self.assertEqual(len({skills.item_key(i) for i in out["items"]}), 10)

    # -------------------------------------------------------------- how pages behave
    def test_cookie_banner_over_the_page(self):
        comp = self.computer()
        try:
            skill, _, _ = self.learn("/cookie", "Find e-bikes", step("click", "Accept all", label="Close cookies"), step("fill", "textbox:Search", "e-bike", "Type e-bike"),
                                     step("click", "button:Search", label="Click Search"), comp=comp)
            self.assertEqual(self.texts(skill)[:4], ["Close cookies", "Type e-bike", "Click Search", "Read 10 results"])
            again, _ = self.replay(skill, comp=comp)  # the banner is gone now: that step is skipped
            self.assertEqual(len(again["items"]), 25)
        finally:
            comp.close()
        fresh, _ = self.replay(skill)  # a browser that never saw it: the banner is closed again
        self.assertEqual(len(fresh["items"]), 25)

    def test_results_that_come_after_the_page(self):
        _, model, out = self.learned_and_repeats("/late", "Find e-bikes", n=12)
        self.assertEqual(model.calls["selectors"], 0)  # it waited for the list instead of asking the model to guess one

    def test_redirects(self):
        for path in ("/old", "/jsredirect"):
            skill, _, out = self.learned_and_repeats(path, "Find e-bikes", n=25)
            self.assertEqual(skill["start_url"], self.base + path)

    def test_broken_address_stops_at_once(self):
        model = Plan(step("click", "Category 3"))
        with self.assertRaises(skills.NeedsHelp) as e:
            skills.learn(Ctx(self.comp, model, "Find e-bikes"), "Find e-bikes", self.base + "/missing")
        self.assertEqual((e.exception.kind, e.exception.title, model.total), ("learn_failed", "That page doesn’t exist", 0))

    def test_slow_page(self):
        t0 = time.time()
        self.learned_and_repeats("/slow", "Find e-bikes", n=25)
        self.assertGreater(time.time() - t0, 9)  # it really waited for each page

    # -------------------------------------------------------------- what learning refuses
    def test_home_feed_sell_and_log_in_are_refused(self):
        skill, model, out = self.learned_and_repeats(
            "/", "Find e-bikes under €1500", step("click", "Sell your bike"), step("click", "Log in"), step("click", "Post an ad"),
            step("fill", "textbox:Search", "e-bike", "Type e-bike"), step("click", "button:Search", label="Click Search"), fits=lambda s: "sofa" not in s, n=25)
        self.assertEqual(self.texts(skill)[:3], ["Type e-bike", "Click Search", "Read 10 results"])
        self.assertGreaterEqual(model.calls["fits"], 2)  # the feed was looked at, and turned down

    def test_category_menu_is_not_results(self):
        skill, _, out = self.learned_and_repeats("/menu", "Find e-bikes", step("extract", tries=1, label="Read"),
                                                 step("click", "E-bikes (743)", label="Open E-bikes"), n=25)
        self.assertEqual(self.texts(skill)[:2], ["Open E-bikes", "Read 10 results"])

    def test_wrong_kind_of_results_are_refused(self):
        skill, _, out = self.learned_and_repeats("/cat/kids", "Find e-bikes", step("click", "Categories", label="Open Categories"),
                                                 step("click", "E-bikes", label="Open E-bikes"), fits=lambda s: "boys" not in s, n=25)
        self.assertIn("e-bike", out["items"][0]["title"])

    def test_sign_in_wall_stops_and_types_nothing(self):
        with self.assertRaises(skills.NeedsHelp) as e:
            self.learn("/members", "Find members' deals", step("fill", "Email", "me@example.com"), step("fill", "Password", "hunter2"),
                       step("click", "Sign in"))
        self.assertEqual(e.exception.kind, "sign_in")
        self.assertIn("sign in", e.exception.title)
        typed = self.comp.call("extract", {"item": "input", "fields": {"v": "@value"}})
        self.assertEqual([r["v"] for r in typed], ["", ""])

    def test_robot_check_and_bot_refusal_stop_with_no_model(self):
        for path, kind in (("/robot", "robot"), ("/blocked", "blocked")):
            with self.assertRaises(skills.NeedsHelp) as e:
                self.learn(path, "Find e-bikes", step("click", "Search"))
            self.assertEqual(e.exception.kind, kind)

    # -------------------------------------------------------------- replay when the page changed
    def test_renamed_button_is_repaired_with_one_call(self):
        skill, _, _ = self.learn("/find", "Find e-bikes", step("fill", "textbox:Search", "e-bike", "Type e-bike"), step("click", "button:Search", label="Click Search"))
        self.layout(2)
        model = Plan(repair=("Go", 0.9))
        out, _ = self.replay(skill, model=model)
        self.assertEqual((model.total, out["repairs"][0]["to"], len(out["items"])), (1, "Go", 25))
        again, _ = self.replay(skill)  # the fixed step now replays with no model
        self.assertEqual(len(again["items"]), 25)

    def test_step_that_cant_be_fixed_stops(self):
        skill, _, _ = self.learn("/find", "Find e-bikes", step("fill", "textbox:Search", "e-bike", "Type e-bike"), step("click", "button:Search", label="Click Search"))
        self.layout(3)
        for answer in (("Where to?", 0.4), ("Go", 0.95)):  # unsure; or sure, but a button for a text box
            model = Plan(repair=answer)
            with self.assertRaises(skills.NeedsHelp) as e:
                self.replay(skill, model=model)
            self.assertEqual((e.exception.kind, model.total), ("fix_failed", 1))


class EngineLearningTest(unittest.TestCase):
    """The same, through the engine: what is stored, what is new, and when a repair is kept."""

    @classmethod
    def setUpClass(cls):
        from tests.test_engine import make_engine
        cls.site = learn_site.start()
        cls.base = f"http://127.0.0.1:{cls.site.server_port}"
        cls.E = make_engine()

    @classmethod
    def tearDownClass(cls):
        cls.E.close()
        cls.site.shutdown()

    def learned(self, path, goal, *steps):
        from tests.test_engine import wait
        E = self.E
        E.llm.scripted = Plan(*steps)
        bid = E.create_bot({"name": "Learner", "job": goal, "goal": goal, "start_url": self.base + path})["id"]
        E.learn(bid, goal, self.base + path)
        self.assertTrue(wait(lambda: not E.busy(bid), 120))
        return bid

    def run_once(self, bid, model=None):
        if model:
            self.E.llm.scripted = model
        self.E.run(bid, wait=True)
        return self.E.store.find("runs", bot_id=bid, limit=1)[0]

    def test_quotes_are_stored_one_each_and_a_second_run_finds_none_new(self):
        bid = self.learned("/quotes", "Find quotes about life")
        check = self.E.store.find("runs", bot_id=bid, limit=1)[0]
        stored = self.E.store.find("results", bot_id=bid, limit=100)
        self.assertEqual((check["items"], check["new"], check["ai_calls"], len(stored)), (29, 29, 0, 29))
        self.assertEqual(sorted(r["title"] for r in stored), sorted(q["text"] for q in learn_site.QUOTES))
        again = self.run_once(bid, NoModel())
        self.assertEqual((again["status"], again["items"], again["new"], again["ai_calls"]), ("ok", 29, 0, 0))

    def test_a_repair_is_kept_only_when_it_finds_results(self):
        bid = self.learned("/find", "Find e-bikes", step("fill", "textbox:Search", "e-bike", "Type e-bike"), step("click", "button:Search", label="Click Search"))
        try:
            urllib.request.urlopen(f"{self.base}/__layout?v=4").read()  # the button is gone; “Save search” only looks like one
            run = self.run_once(bid, Plan(repair=("Save search", 0.9)))
            sk = self.E.store.find("skills", bot_id=bid)[0]
            self.assertEqual((run["status"], run["ai_calls"]), ("needs_you", 1))
            self.assertEqual(sk["steps"][1]["target"]["name"], "Search")  # the old step stays
            urllib.request.urlopen(f"{self.base}/__layout?v=2").read()  # renamed to “Go”: that fix finds results, so it's kept
            run = self.run_once(bid, Plan(repair=("Go", 0.9)))
            sk = self.E.store.find("skills", bot_id=bid)[0]
            self.assertEqual((run["status"], run["ai_calls"], run["items"], sk["steps"][1]["target"]["name"]), ("ok", 1, 25, "Go"))
            again = self.run_once(bid, NoModel())
            self.assertEqual((again["status"], again["ai_calls"], again["new"]), ("ok", 0, 0))
        finally:
            urllib.request.urlopen(f"{self.base}/__layout?v=1").read()


if __name__ == "__main__":
    unittest.main()
