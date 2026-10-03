"""What learning used to leave to the model, or to miss: results with no links (found by code now), a next page that's
only a bare “More” or marked rel="next", and more pages after the model said “done”."""
import shutil
import tempfile
import unittest

from inky import skills
from inky.computer import Computer
from tests import learn_site
from tests.test_learning import Ctx, Plan, step


class SaysDone(Plan):
    """A model that says “done” at once, as small models do on a page that already shows the results."""

    def ask_json(self, role, system, user, bot_id=None, **kw):
        if system in (skills.PICK_LIST_SYSTEM, skills.FIT_SYSTEM, skills.EXTRACT_SYSTEM, skills.REPAIR_SYSTEM):
            return super().ask_json(role, system, user, bot_id, **kw)
        self.calls["step"] += 1
        return {"action": "done"}, {}


class MoreLearningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = learn_site.start()
        cls.base = f"http://127.0.0.1:{cls.site.server_port}"
        cls.dir = tempfile.mkdtemp(prefix="inky-learn-more-")
        cls.comp = Computer(1, cls.dir, look={"speed": "turbo"})

    @classmethod
    def tearDownClass(cls):
        cls.comp.close()
        cls.site.shutdown()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_results_without_links_are_found_by_code(self):
        self.comp.call("open", self.base + "/notices")
        lists = self.comp.call("lists")
        best = max(lists, key=lambda l: l["count"])
        self.assertEqual(best["count"], 10)
        self.assertTrue(best["rows"][0]["title"].startswith("Town notice 1"), best["rows"][0])

    def test_a_bare_more_or_rel_next_is_the_next_page(self):
        for path, name in (("/notices", "More"), ("/hn", "More")):
            page = self.comp.call("open", self.base + path)
            nxt = skills.next_link(page)
            self.assertIsNotNone(nxt, path)
            self.assertEqual((nxt["name"], nxt["href"].split("?")[1]), (name, "p=2"))
        page = self.comp.call("open", self.base + "/notices")  # “More” about something else, linking nowhere paged, isn't it
        self.assertIsNone(skills.next_link({"url": page["url"], "elements": [{"role": "link", "name": "More", "href": "/about"}]}))

    def test_more_pages_after_the_model_says_done(self):
        ctx = Ctx(self.comp, SaysDone(), "Find town notices about road works")
        skill = skills.learn(ctx, "Find town notices about road works", self.base + "/notices")
        texts = [s["text"] for s in skill["steps"]]
        self.assertEqual(texts[0], "Read 10 results")
        self.assertEqual(texts[1:], ["Next page (More)"])
        out = skills.replay(Ctx(self.comp, SaysDone(), skill["goal"]), skill)
        self.assertEqual(len(out["items"]), 30)  # three pages, no model


if __name__ == "__main__":
    unittest.main()
