"""Self-check for the race: pure helpers, then a real --dry-run (2 headless windows, 15 s, agent 2 steps).

    .venv/bin/python race/check.py
Needs network, Google Chrome and OPENROUTER_API_KEY in .env (the dry run spends about $0.03).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from race import layout, number, on_page, page_range  # noqa: E402

assert [page_range(12, i, 8) for i in range(8)] == [[1, 2], [3, 4], [5, 6], [7, 8], [9], [10], [11], [12]]
assert sum((page_range(64, i, 8) for i in range(8)), []) == list(range(1, 65))
assert page_range(3, 7, 8) == []
assert number("€ 240.000") == 240000 and number("99 Mq") == 99 and number("1,5") == 1.5 and number("3 locali, 2 bagni") == 3
assert number(None) is None and number("n.d.") is None
# every window on screen and no smaller than Chrome allows (500x375), on a big screen and on laptops
for scr in [(0, 25, 2560, 1415), (0, 33, 1800, 1071), (0, 25, 1512, 944), (0, 25, 1440, 875), (0, 25, 1280, 775)]:
    rects = layout(*scr, 8)
    assert len(rects) == 9 and all(w >= 500 and h >= 375 and x >= scr[0] and y >= scr[1] and x + w <= scr[0] + scr[2]
                                   and y + h <= scr[1] + scr[3] for x, y, w, h in rects), (scr, rects)
# the agent's listing counts only as a link that is really on the page, under that link
obs = {"url": "https://x.it/list.html", "elements": [[0, "a", "Trilocale in vendita", "https://x.it/vendita/1.html"], [1, "a", "Home", "https://x.it/"]]}
assert on_page("/vendita/1.html", obs) == on_page("https://x.it/vendita/1.html", obs) == "https://x.it/vendita/1.html"
assert on_page("https://x.it/fake/2.html", obs) is None and on_page("https://x.it/", obs) is None and on_page("", obs) is None

out = Path(tempfile.mkdtemp()) / "race.json"
subprocess.run([sys.executable, str(HERE / "race.py"), "--dry-run", "--out", str(out)], check=True, timeout=400)
r = json.loads(out.read_text())
assert set(r) >= {"at", "seconds", "compiled", "llm", "program"}, r.keys()
assert {"windows", "listings", "per_second", "model_calls"} <= set(r["compiled"]) and r["compiled"]["windows"] == 2
assert {"listings", "per_second", "model_calls", "cost_usd"} <= set(r["llm"])
assert r["compiled"]["listings"] > 0, "compiled side read nothing"
assert r["compiled"]["model_calls"] == 0
assert r["llm"]["model_calls"] > 0 and r["llm"]["cost_usd"] > 0, "agent got no answer from the model (key? network?)"
assert r["llm"]["cost_usd"] < 0.5
print(f"race check ok: compiled {r['compiled']['listings']} listings, agent {r['llm']['listings']} listings "
      f"in {r['llm']['model_calls']} calls (${r['llm']['cost_usd']:.3f})")
