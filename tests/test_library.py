"""The agent library: the checker (no secrets, no private data), the index, install from an index entry,
the domain guard in replay, and posting (gh, the web fallback) without anything leaving before the check passes."""
import json
import os
import stat
import tempfile
import unittest
from unittest import mock

from inky import library, skills
from tests.test_engine import make_engine


def bundle(**over):
    b = {"bundle": 1, "bot": {"name": "Book Bargains", "goal": "Books under £20", "look": {"kind": "cat", "color": "#7C6CF2"},
                                          "memory": [], "filters": [{"field": "price", "op": "<=", "value": 20}]},
         "skills": [{"name": "Cheap books", "site": "books.toscrape.com", "start_url": "https://books.toscrape.com/",
                     "steps": [{"action": "extract", "spec": {"item": "article", "fields": {"title": "h3 a@title"}}, "text": "Read 20 results"},
                               {"action": "goto", "value": "https://www.toscrape.com/about", "text": "Open about"}]}],
         "results": [], "messages": [], "cookies": []}
    b.update(over)
    return b


class CheckTest(unittest.TestCase):
    def test_clean_bundle_passes_with_domains(self):
        c = library.check(bundle())
        self.assertTrue(c["ok"], c["problems"])
        self.assertEqual(c["domains"], ["books.toscrape.com", "toscrape.com"])
        self.assertEqual(c["irreversible"], [])

    def test_private_things_and_secrets_fail_by_name(self):
        bad = bundle(cookies=[{"name": "sid"}], results=[{"title": "x"}], messages=[{"text": "hi"}])
        bad["bot"]["memory"] = ["Leo lives in Bari"]
        bad["skills"][0]["steps"] += [
            {"action": "fill", "value": "sk-or-v1-abcdefghijklmnopqrstuvwx", "text": "Type the key"},
            {"action": "fill", "value": "hunter2", "target": {"type": "password", "name": "Password"}, "text": "Type password"},
            {"action": "fill", "value": "ghp_abcdefghijklmnopqrstuvwxyz0123456789", "text": "Token"}]
        p = " | ".join(library.check(bad)["problems"])
        for word in ("sign-ins", "memory", "results", "chat", "API key", "password", "GitHub token"):
            self.assertIn(word, p)

    def test_irreversible_steps_are_listed(self):
        b = bundle()
        b["skills"][0]["steps"] += [{"action": "click", "text": "Submit the order", "target": {"role": "button", "name": "Submit"}},
                                    {"action": "click", "text": "Open details", "approved_always": True}]
        self.assertEqual(library.check(b)["irreversible"], ["Cheap books: Submit the order", "Cheap books: Open details"])


class IndexTest(unittest.TestCase):
    def test_index_is_built_from_the_agent_files_sorted_by_title(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "agents"))
        for title in ("Zebra Watch", "Apple Tracker"):
            b = bundle()
            b["bot"]["name"] = title
            b["listing"] = library.listing(b, {"author": "leo", "tags": ["shopping"]})
            with open(os.path.join(d, "agents", b["listing"]["slug"] + ".inky"), "w") as f:
                json.dump(b, f)
        idx = library.build_index(d)
        self.assertEqual([a["title"] for a in idx["agents"]], ["Apple Tracker", "Zebra Watch"])
        a = idx["agents"][0]
        self.assertEqual((a["file"], a["author"], a["sites"], a["reviewed"]), ("agents/apple-tracker.inky", "leo", ["books.toscrape.com", "toscrape.com"], True))


class InstallAndGuardTest(unittest.TestCase):
    def test_install_records_domains_and_refuses_unsafe_bundles(self):
        E = make_engine()
        self.addCleanup(E.close)
        bid = library.install(E, bundle())
        self.assertEqual(E.store.get("bots", bid)["allowed_domains"], ["books.toscrape.com", "toscrape.com"])
        with self.assertRaises(ValueError):
            library.install(E, bundle(cookies=[{"name": "sid"}]))

    def test_replay_stops_outside_the_agents_sites(self):
        class Comp:
            def __init__(self):
                self.url = None

            def call(self, m, *a, **k):
                if m == "open":
                    self.url = a[0]
                if m == "act" and a[0] == "goto":
                    self.url = a[2]
                return [] if m == "extract" else {"url": self.url, "elements": []}

        class Ctx:
            def __init__(self, allowed):
                self.computer, self.bot = Comp(), {"id": 1, "allowed_domains": allowed}

            def emit(self, *a, **k):
                pass

            def check(self):
                pass

        sk = {"start_url": "https://books.toscrape.com/", "steps": [{"action": "goto", "value": "https://shop.toscrape.com/x", "text": "sub"}]}
        skills.replay(Ctx(["books.toscrape.com"]), sk)  # a same-site subdomain is fine
        sk["steps"].append({"action": "goto", "value": "https://evil.example/steal", "text": "Leave"})
        with self.assertRaises(skills.NeedsHelp) as e:
            skills.replay(Ctx(["books.toscrape.com"]), sk)
        self.assertEqual(e.exception.kind, "blocked")
        self.assertIn("only works on books.toscrape.com", e.exception.title)
        skills.replay(Ctx(None), sk)  # your own bots have no fence


class PublishTest(unittest.TestCase):
    def make(self):
        library._login.clear()  # a fake gh per test, never your real one's cached name
        E = make_engine()
        self.addCleanup(E.close)
        b = E.create_bot({"name": "Book Bargains", "goal": "Books under £20", "start_url": "https://books.toscrape.com/"})
        E.store.insert("skills", {"name": "Cheap books", "site": "books.toscrape.com", "start_url": "https://books.toscrape.com/",
                                  "steps": [{"action": "extract", "spec": {"item": "article", "fields": {"title": "h3 a@title"}}, "text": "Read"}]},
                       bot_id=b["id"], status="ok")
        return E, b["id"]

    def test_without_gh_it_opens_githubs_new_file_page(self):
        E, bid = self.make()
        with mock.patch.object(library.shutil, "which", return_value=None):
            r = library.publish(E, bid, {"author": "leo"})
        self.assertEqual(r["mode"], "web")
        self.assertTrue(r["url"].startswith("https://github.com/GHGuide/inky/new/main/library/agents?filename=book-bargains.inky&value="))
        self.assertIn("Book Bargains", r["public"])  # you see exactly what becomes public

    @unittest.skipIf(os.name == "nt", "uses a shell script as a fake gh")
    def test_with_gh_it_forks_branches_commits_and_opens_a_pr(self):
        E, bid = self.make()
        d = tempfile.mkdtemp()
        log = os.path.join(d, "calls")
        gh = os.path.join(d, "gh")
        with open(gh, "w") as f:
            f.write(f"""#!/bin/sh
echo "$@" >> {log}
case "$*" in
  "auth status"*) exit 0 ;;
  "api user"*) echo leo-gh ;;
  *"git/ref/heads/main"*) echo abc123 ;;
  "pr create"*) echo https://github.com/GHGuide/inky/pull/7 ;;
esac
""")
        os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC)
        with mock.patch.dict(os.environ, {"PATH": d + os.pathsep + os.environ["PATH"]}):
            r = library.publish(E, bid, {"summary": "Cheap books daily"})
        self.assertEqual((r["mode"], r["url"]), ("pr", "https://github.com/GHGuide/inky/pull/7"))
        with open(log) as f:
            calls = f.read().splitlines()
        self.assertEqual(calls[0], "api user -q .login")  # the listing names who posted it
        calls = calls[1:]
        order = ["auth status", "repo fork GHGuide/inky", "api user", "git/ref/heads/main", "git/refs", "contents/library/agents/book-bargains.inky", "pr create"]
        at = [next(i for i, c in enumerate(calls) if o in c) for o in order]
        self.assertEqual(at, sorted(at), calls)

    def test_nothing_leaves_when_the_check_fails(self):
        E, bid = self.make()
        E.store.update("bots", bid, goal="log in with sk-or-v1-abcdefghijklmnopqrstuvwx")  # memory never leaves anyway
        with mock.patch.object(library.subprocess, "run") as run:
            r = library.publish(E, bid, {})
        self.assertEqual(r["mode"], "blocked")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
