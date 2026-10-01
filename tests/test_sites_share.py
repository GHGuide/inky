"""Sites found for a job, a draft that keeps only what you said, and share links with the agent inside."""
import unittest
from unittest import mock

from inky import library, sites
from tests.test_engine import make_engine

PAGE = """
<div class="result results_links"><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.zidarie.md%2Fro%2F&amp;rut=x">Zidarie &amp; bricks</a>
<a class="result__snippet" href="x">Showroom in <b>Chisinau</b></a></div>
<div class="result"><a class="result__a" href="https://duckduckgo.com/y.js?ad_domain=ads.example">An ad</a><a class="result__snippet" href="x">ad</a></div>
<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.facebook.com%2Fbricks">Bricks on Facebook</a><a class="result__snippet" href="x">social</a></div>
<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fcaramida.md%2F">Caramida.md</a><a class="result__snippet" href="x">furnizor</a></div>
<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fshop.zidarie.md%2Fx">Zidarie shop</a><a class="result__snippet" href="x">same site</a></div>
"""


class SitesTest(unittest.TestCase):
    def test_one_row_per_site_no_ads_or_social_and_the_guess_last(self):
        with mock.patch.object(sites.httpx, "post", return_value=mock.Mock(text=PAGE, raise_for_status=lambda: None)):
            rows = sites.suggest(["bricks Moldova", "caramida Chisinau"], guess="https://www.bricklink.com/")
        self.assertEqual([r["host"] for r in rows], ["zidarie.md", "caramida.md", "bricklink.com"])
        self.assertEqual(rows[0]["title"], "Zidarie & bricks")
        self.assertEqual(rows[0]["snippet"], "Showroom in Chisinau")
        self.assertTrue(rows[-1]["guess"])

    def test_no_search_working_says_so(self):
        with mock.patch.object(sites.httpx, "post", side_effect=sites.httpx.ConnectError("offline")):
            with self.assertRaises(RuntimeError):
                sites.suggest(["bricks"])


class DraftTest(unittest.TestCase):
    def test_only_limits_you_said_and_no_website_question(self):
        E = make_engine()
        self.addCleanup(E.close)
        E.llm.ask_json = lambda *a, **k: ({"name": "Brick Finder", "start_url": "https://www.bricklink.com", "every_minutes": 1440,
                                           "filters": [{"field": "country", "op": "==", "value": "Moldova"}, {"field": "wholesale", "op": "==", "value": True},
                                                       {"field": "price", "op": "<=", "value": 1}],
                                           "questions": ["Which website should it use?", "What quantity do you need?"], "search": ["caramida Moldova"]}, {})
        d = E.draft_bot("Find the cheapest wholesale bricks in Moldova")
        self.assertEqual([f["field"] for f in d["filters"]], ["country"])
        self.assertEqual(d["questions"], ["What quantity do you need?"])
        self.assertEqual((d["start_url"], d["guess"]), (None, "https://www.bricklink.com"))
        self.assertEqual(d["search"], ["caramida Moldova"])
        b = E.create_bot({**d, "start_url": "https://zidarie.md/", "more_sites": ["caramida.md", "not a site", "https://fortan.md"]})
        self.assertEqual(E.store.get("bots", b["id"])["site_queue"], ["https://caramida.md", "https://fortan.md"])


class ShareLinkTest(unittest.TestCase):
    def test_the_agent_travels_inside_the_link(self):
        E = make_engine()
        self.addCleanup(E.close)
        b = E.create_bot({"name": "Book Bargains", "goal": "Books under £20", "start_url": "https://books.toscrape.com/"})
        E.store.insert("skills", {"name": "Cheap books", "start_url": "https://books.toscrape.com/",
                                  "steps": [{"action": "extract", "text": "Read", "spec": {"item": "article", "fields": {"title": "h3"}}}]}, bot_id=b["id"], status="ok")
        r = library.share_code(E, b["id"], {"summary": "Cheap books"})
        self.assertEqual(r["mode"], "link")
        self.assertTrue(r["link"].startswith("inky://agent?d=") and len(r["link"]) < 4000)
        got = library.fetch(r["link"])
        self.assertEqual((got["bot"]["name"], len(got["skills"])), ("Book Bargains", 1))
        self.assertEqual(got["bot"]["memory"], [])  # never what it knows about you
        lst = library.listing_for(got, r["link"])
        self.assertTrue(lst["unverified"])
        for bad in ("inky://agent?d=", "inky://agent?d=bm90IHppcA", r["link"][:60]):
            with self.assertRaises(ValueError):
                library.fetch(bad)


if __name__ == "__main__":
    unittest.main()


class LearningChecksTest(unittest.TestCase):
    def test_stated_numbers_optional_steps_and_next_links(self):
        from inky import skills
        self.assertTrue(skills.said_number("150000", "Flats in Bari under 150k, remember balconies"))
        self.assertFalse(skills.said_number("0", "used e-bikes") or skills.said_number("500", "e-bikes under 1500"))
        cookie = {"action": "click", "text": "Accept cookies", "target": {"role": "button", "name": "Accepteren"}}
        price = {"action": "fill", "text": "Type minimum price", "target": {"role": "textbox", "name": "Prijs van"}}
        search = {"action": "fill", "text": "Type e-bike", "target": {"role": "searchbox", "name": "Zoeken"}}
        self.assertEqual([skills.is_optional(x) for x in (cookie, price, search)], [True, True, False])
        carousel = {"url": "https://shop.example/", "elements": [{"role": "button", "name": "Next", "href": ""}]}
        paging = {"url": "https://shop.example/bikes?page=1", "elements": [{"role": "link", "name": "Volgende", "href": "/bikes?page=2"}]}
        self.assertIsNone(skills.next_link(carousel))
        self.assertEqual(skills.next_link(paging)["name"], "Volgende")
        self.assertFalse(skills.named([{"link": "/a"}, {"link": "/b"}, {"link": "/c"}, {"title": None, "link": "/d"}]))
        self.assertTrue(skills.named([{"title": "Gazelle", "price": "€220"}, {"title": "Batavus"}, {"price": "€99"}]))

    def test_domains_for_sale_are_not_sites(self):
        from inky.sites import PARKED
        self.assertTrue(PARKED.search("mooiedomeinnaam.nl ebikeshop.nl is te koop"))
        self.assertTrue(PARKED.search("example.com This domain is for sale"))
        self.assertFalse(PARKED.search("shop.nl This e-bike is for sale, 2 years old"))
        self.assertFalse(PARKED.search("2dehands.be Fietsen te koop"))

    def test_word_rules(self):
        from inky import skills
        from inky.bots import stated
        job = {"title": "Senior Dev", "text": "Senior Dev Acme Remote (UK / EU)"}
        self.assertTrue(skills.keep(job, {"field": "text", "op": "contains", "value": "remote"}))
        self.assertTrue(skills.keep({"title": "Pi brings AI agents"}, {"field": "text", "op": "in", "value": ["AI", "LLM"]}))  # no text: its title
        self.assertFalse(skills.keep({"title": "Rain in Spain"}, {"field": "title", "op": "contains", "value": "ai"}))
        self.assertTrue(skills.has_word("£51.77 in stock", "£"))
        self.assertFalse(stated({"field": "text", "op": "contains", "value": "£"}, "books under £20"))  # a symbol is never your rule
        self.assertTrue(stated({"field": "text", "op": "contains", "value": "remote"}, "remote Python jobs"))
