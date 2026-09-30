"""Every service the UI names has its real logo file, listed with its source, small and script-free."""
import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "inky" / "ui"


class LogoTest(unittest.TestCase):
    def test_every_logo_used_exists_and_is_sourced(self):
        js = (UI / "app.js").read_text(encoding="utf-8") + (UI / "views.js").read_text(encoding="utf-8")
        m = re.search(r"const LOGOS = \{(.*?)\n\};", js, re.S)
        self.assertIsNotNone(m, "LOGOS table missing in app.js")
        files = set()
        for slug, rest in re.findall(r'(\w+): \[("[^\]]*)\]', m.group(1)):
            parts = re.findall(r'"([^"]*)"|null', rest)
            files.add(parts[2] if len(parts) > 2 and parts[2] else slug)
        used = set(re.findall(r'logo\("(\w+)"', js))
        table = set(re.findall(r'(\w+): \[', m.group(1)))
        self.assertTrue(used <= table, f"logo() names missing from LOGOS: {used - table}")
        sources = (UI / "logos" / "SOURCES.md").read_text(encoding="utf-8")
        for f in files:
            p = UI / "logos" / f"{f}.svg"
            self.assertTrue(p.exists(), f"missing {p.name}")
            self.assertIn(p.name, sources, f"{p.name} not in SOURCES.md")
            svg = p.read_text(encoding="utf-8")
            self.assertLess(len(svg), 40_000)
            self.assertNotIn("<script", svg.lower())

    def test_no_letter_tiles_left(self):
        views = (UI / "views.js").read_text(encoding="utf-8")
        self.assertNotIn("label[0])}</span>", views)  # the old first-letter provider tiles


if __name__ == "__main__":
    unittest.main()
