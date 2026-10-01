import re
import tempfile
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
        self.assertEqual(skills.parse_num("€ 78.915"), 78915)
        self.assertEqual(skills.parse_num("1.234,5 m²"), 1234.5)
        items = [{"price": "€ 90.000"}, {"price": "€ 200.000"}]
        self.assertEqual(skills.apply_filters(items, [{"field": "price", "op": "<=", "value": 150000}]), items[:1])


if __name__ == "__main__":
    unittest.main()
