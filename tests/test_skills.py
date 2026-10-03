import re
import tempfile
import time
import unittest
import urllib.request

from inky import skills
from inky.computer import Computer
from inky.safety import classify
from tests import site_server


def idx(user, name):
    m = re.search(r"\[(\d+)\] \w+ “" + re.escape(name) + "”", user)
    return int(m.group(1)) if m else None


class ScriptedModel:
    """Stands in for a model: learns the CasaFacile search, and answers repairs as told."""

    def __init__(self, repair_answer=None):
        self.calls = 0
        self.repair_answer = repair_answer

    def ask_json(self, role, system, user, bot_id=None, **kw):
        self.calls += 1
        if system == skills.PICK_LIST_SYSTEM:
            return {"pick": 1}, {}
        if system == skills.EXTRACT_SYSTEM:
            return {"item": ".card", "fields": {"title": ".title", "price": ".price", "size": ".size", "link": "a.details@href"}}, {}
        if system == skills.REPAIR_SYSTEM:
            name, conf = self.repair_answer
            return {"index": idx(user, name), "confidence": conf, "why": "same place"}, {}
        steps = user.split("STEPS SO FAR:")[1].split("EXTRACTED:")[0]
        extracted = "EXTRACTED: yes" in user
        if "Accetta" in user and "Close cookies" not in steps:
            return {"action": "click", "index": idx(user, "Accetta"), "step": "Close cookies"}, {}
        if "Type Bari" not in steps:
            return {"action": "fill", "index": idx(user, "Comune"), "value": "Bari", "step": "Type Bari"}, {}
        if "Set max price" not in steps:
            return {"action": "fill", "index": idx(user, "Prezzo max"), "value": "150000", "step": "Set max price"}, {}
        if "Search" not in steps:
            return {"action": "click", "index": idx(user, "Cerca"), "step": "Search"}, {}
        if not extracted:
            return {"action": "extract"}, {}
        if idx(user, "Avanti") is not None:
            return {"action": "next_page", "index": idx(user, "Avanti"), "step": "Next page"}, {}
        return {"action": "done"}, {}


class ForgetfulModel(ScriptedModel):
    """Types the town, then wants to read the results without ever pressing Search."""

    def ask_json(self, role, system, user, bot_id=None, **kw):
        if system in (skills.PICK_LIST_SYSTEM, skills.EXTRACT_SYSTEM, skills.REPAIR_SYSTEM):
            return super().ask_json(role, system, user, bot_id, **kw)
        self.calls += 1
        steps = user.split("STEPS SO FAR:")[1].split("EXTRACTED:")[0]
        if "Accetta" in user and "Close cookies" not in steps:
            return {"action": "click", "index": idx(user, "Accetta"), "step": "Close cookies"}, {}
        if "Type Bari" not in steps:
            return {"action": "fill", "index": idx(user, "Comune"), "value": "Bari", "step": "Type Bari"}, {}
        return ({"action": "extract"} if "EXTRACTED: yes" not in user else {"action": "done"}), {}


class GotoModel(ForgetfulModel):
    """Says “goto Accetta” with the button's number instead of clicking it, and once “goes to” the page it's on."""

    def ask_json(self, role, system, user, bot_id=None, **kw):
        steps = user.split("STEPS SO FAR:")[1].split("EXTRACTED:")[0] if "STEPS SO FAR:" in user else ""
        if system == skills.LEARN_SYSTEM and "Accetta" in user and "Close cookies" not in steps:
            self.calls += 1
            if "already on that page" not in user:
                return {"action": "goto", "value": user.split("PAGE: ")[1].split(" — ")[1].split("\n")[0], "step": "Go to the home page"}, {}
            return {"action": "goto", "index": idx(user, "Accetta"), "value": "Accetta", "step": "Go to Close cookies"}, {}
        return super().ask_json(role, system, user, bot_id, **kw)


class DoubtfulModel(ScriptedModel):
    """Says the first results it's shown don't fit; the learner asks once per page, then reads if the model insists."""

    def __init__(self):
        super().__init__()
        self.asked = []

    def ask_json(self, role, system, user, bot_id=None, **kw):
        if system == skills.FIT_SYSTEM:
            self.asked.append(user)
            return {"fits": len(self.asked) > 1, "why": "children's bikes"}, {}
        return super().ask_json(role, system, user, bot_id, **kw)


class NoModel:
    def ask_json(self, *a, **k):
        raise AssertionError("replay must not call a model")


class Ctx:
    def __init__(self, comp, llm):
        self.computer, self.llm = comp, llm
        self.bot = {"id": 1, "rules": []}
        self.log, self.gated = [], []

    def emit(self, kind, text, **m):
        self.log.append((kind, text))

    def gate(self, step, el, page):
        self.gated.append(classify(step["action"], el, page)[0])

    def check(self):
        pass

    def corrections(self):
        return []


class SkillsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = site_server.start()
        cls.base = f"http://127.0.0.1:{cls.site.server_port}"
        cls.comp = Computer(1, tempfile.mkdtemp(), look={"speed": "turbo"})

    @classmethod
    def tearDownClass(cls):
        cls.comp.close()
        cls.site.shutdown()

    def layout(self, v):
        urllib.request.urlopen(f"{self.base}/__layout?v={v}").read()

    def learned(self):
        self.layout(1)
        model = ScriptedModel()
        skill = skills.learn(Ctx(self.comp, model), "Flats in Bari under 150k", self.base + "/")
        return skill, model

    def test_learn_then_replay_with_no_model(self):
        skill, model = self.learned()
        self.assertEqual([s["text"] for s in skill["steps"]][:4], ["Close cookies", "Type Bari", "Set max price", "Search"])
        self.assertTrue(skill["steps"][-1]["next_page"])
        self.assertGreaterEqual(model.calls, 4)  # it used the model to learn (results it finds by itself need fewer calls)
        out = skills.replay(Ctx(self.comp, NoModel()), skill)
        self.assertGreaterEqual(out["pages"], 2)
        self.assertTrue(all(skills.parse_num(i["price"]) <= 150000 for i in out["items"]))
        self.assertEqual(out["repairs"], [])

    def test_a_search_typed_but_never_sent_is_sent_for_it(self):
        self.layout(1)
        comp = Computer(2, tempfile.mkdtemp(), look={"speed": "turbo"})  # its own browser: the shared one's cookie banner stays for the other tests
        try:
            skill = skills.learn(Ctx(comp, ForgetfulModel()), "Flats in Bari", self.base + "/")
        finally:
            comp.close()
        texts = [s["text"] for s in skill["steps"]]
        self.assertEqual(texts[1:4], ["Type Bari", "Press Enter to search", texts[3]])
        self.assertTrue(texts[3].startswith("Read "))  # the results page, not the home page

    def test_goto_a_link_name_is_a_click_and_goto_here_is_no_step(self):
        self.layout(1)
        comp = Computer(3, tempfile.mkdtemp(), look={"speed": "turbo"})
        try:
            skill = skills.learn(Ctx(comp, GotoModel()), "Flats in Bari", self.base + "/")
        finally:
            comp.close()
        self.assertEqual([(s["action"], s["text"]) for s in skill["steps"]][:2], [("click", "Click Close cookies"), ("fill", "Type Bari")])

    def test_results_that_dont_fit_are_questioned_once_per_page(self):
        self.layout(1)
        comp = Computer(4, tempfile.mkdtemp(), look={"speed": "turbo"})
        model = DoubtfulModel()
        ctx = Ctx(comp, model)
        try:
            skill = skills.learn(ctx, "Flats in Bari under 150k", self.base + "/")
        finally:
            comp.close()
        self.assertEqual(len(model.asked), 1)  # one no, then it read the same page when the model insisted
        self.assertTrue(any(s["action"] == "extract" for s in skill["steps"]))

    def test_renamed_button_is_repaired_when_sure(self):
        skill, _ = self.learned()
        self.layout(3)
        ctx = Ctx(self.comp, ScriptedModel(repair_answer=("Trova", 0.92)))
        out = skills.replay(ctx, skill)
        self.assertEqual(out["repairs"][0]["to"], "Trova")
        self.assertGreater(len(out["items"]), 0)
        self.layout(1)

    def test_moved_button_stops_when_unsure(self):
        skill, _ = self.learned()
        self.layout(2)
        ctx = Ctx(self.comp, ScriptedModel(repair_answer=("Salva ricerca", 0.41)))
        with self.assertRaises(skills.NeedsHelp) as e:
            skills.replay(ctx, skill)
        self.assertEqual(e.exception.kind, "fix_failed")
        self.assertIn("41%", e.exception.body)
        self.layout(1)

    def test_safety_and_numbers(self):
        send = {"role": "button", "name": "Invia", "text": "Invia"}
        self.assertEqual(classify("click", send)[0], "irreversible")
        self.assertEqual(classify("click", {"role": "button", "name": "Cerca"})[0], "ok")
        self.assertEqual(classify("click", {"role": "button", "name": "Add to cart"})[0], "pay")
        self.assertEqual(classify("fill", {"role": "password", "type": "password"})[0], "password")
        # a form's own button: a sign-in whatever it says, a contact form even when it says "Continue", a search never
        login = {"post": True, "password": True, "personal": False, "submits": True}
        self.assertEqual(classify("click", {"role": "button", "name": "Accedi", "form": login})[0], "password")
        self.assertEqual(classify("press", {"role": "textbox", "name": "Email", "form": {**login, "submits": False}})[0], "password")
        contact = {"post": True, "password": False, "personal": True, "submits": True}
        self.assertEqual(classify("click", {"role": "button", "name": "Continue", "form": contact})[0], "irreversible")
        self.assertEqual(classify("press", {"role": "textbox", "name": "Message", "form": {**contact, "submits": False}})[0], "irreversible")
        search = {"post": False, "password": False, "personal": False, "submits": True}
        self.assertEqual(classify("press", {"role": "textbox", "name": "Search", "form": {**search, "submits": False}})[0], "ok")
        self.assertEqual(classify("click", {"role": "button", "name": "Go", "form": {**search, "post": True}})[0], "ok")  # an ASP.NET page
        self.assertEqual(classify("click", {"role": "button", "name": "Sign in"}, {"pw": True})[0], "password")
        self.assertEqual(classify("click", {"role": "link", "name": "Log in"}, {"pw": False})[0], "ok")  # only going to the sign-in page
        self.assertEqual(skills.parse_num("€ 78.915"), 78915)
        self.assertEqual(skills.parse_num("1.234,5 m²"), 1234.5)
        items = [{"price": "€ 90.000"}, {"price": "€ 200.000"}]
        self.assertEqual(skills.apply_filters(items, [{"field": "price", "op": "<=", "value": 150000}]), items[:1])


if __name__ == "__main__":
    unittest.main()


class Scroller:
    """A results page that shows 10 more each time it's scrolled to the bottom, up to `last` (None: it never ends)."""

    def __init__(self, last=None):
        self.n, self.last, self.acts = 10, last, []

    def call(self, fn, *a, **kw):
        if fn == "act":
            self.acts.append(a[0])
            self.n = self.n + 10 if self.last is None else min(self.n + 10, self.last)
        if fn == "extract":
            return [{"title": f"Bike {i}", "link": f"https://shop.example/p/{i}"} for i in range(self.n)]
        return {"url": "https://shop.example/bikes", "title": "Bikes", "elements": []}


class InfiniteScrollTest(unittest.TestCase):
    SKILL = {"name": "Bikes", "goal": "Find bikes", "start_url": "https://shop.example/bikes", "max_pages": 3, "steps": [
        {"action": "extract", "spec": {"item": "article", "fields": {"title": "h2", "link": "a@href"}}, "text": "Read 10 results"},
        {"action": "scroll", "target": None, "value": None, "text": "Scroll for more", "next_page": True, "optional": True}]}

    def replay(self, comp, **kw):
        return skills.replay(Ctx(comp, NoModel()), {**self.SKILL, **kw})

    def test_a_list_that_never_ends_stops_at_max_pages(self):
        comp = Scroller()
        out = self.replay(comp, max_pages=4)
        self.assertEqual((out["pages"], len(out["items"]), comp.acts), (4, 40, ["scroll"] * 3))  # only scrolls: never a click

    def test_it_stops_when_scrolling_brings_nothing_new(self):
        comp, t0 = Scroller(last=25), time.time()
        out = self.replay(comp, max_pages=10)
        self.assertEqual((out["pages"], len(out["items"]), len(comp.acts)), (3, 25, 3))  # the third scroll brought nothing
        self.assertLess(time.time() - t0, 8)  # it waited a few seconds for more, no longer


class RefusedPageTest(unittest.TestCase):
    def test_block_pages_are_recognised_and_normal_pages_are_not(self):
        blocked = {"title": "Attention Required! | Cloudflare", "heads": ["Sorry, you have been blocked"], "text": "You are unable to access bikefair.org", "elements": [{}] * 5}
        self.assertTrue(skills.refused_page(blocked))
        self.assertTrue(skills.refused_page({"title": "403 Forbidden", "heads": [], "text": "", "elements": []}))
        shop = {"title": "E-bikes", "heads": ["Used e-bikes"], "text": "Access denied? Call us. 48 bikes in stock", "elements": [{}] * 120}
        self.assertFalse(skills.refused_page(shop))  # a big real page that happens to use the words
        self.assertFalse(skills.refused_page({"title": "Books", "heads": ["All products"], "text": "A Light in the Attic £51.77", "elements": [{}] * 10}))
