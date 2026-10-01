"""docs/acceptance.md F2: the words people read on screen are plain. Jargon may appear in code, never in text shown to you."""
import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "inky" / "ui"
JARGON = re.compile(r"\b(skills?|selectors?|headless|LLM|regex|stack trace)\b", re.I)


def shown_text(js):
    """Text between tags (>…<) and in toasts: what ends up on screen."""
    nodes = re.findall(r">([^<>{}$`\"]{3,})<", js)
    toasts = [re.sub(r"\$\{[^}]*\}", "", t) for t in re.findall(r"toast\(\s*[`\"]([^`\"]+)[`\"]", js)]
    return [t.strip() for t in nodes + toasts if t.strip()]


class PlainWordsTest(unittest.TestCase):
    def test_no_jargon_on_screen(self):
        bad = [(f.name, t) for f in UI.glob("*.js") for t in shown_text(f.read_text(encoding="utf-8")) if JARGON.search(t)]
        self.assertEqual(bad, [])

    def test_connector_cards_are_plain(self):
        from inky import connectors
        from inky.mcp import PRESETS
        texts = [p.about for p in connectors.PROVIDERS.values()] + [p["about"] for p in PRESETS.values()]
        self.assertEqual([t for t in texts if JARGON.search(t)], [])


if __name__ == "__main__":
    unittest.main()
