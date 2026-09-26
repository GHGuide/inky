"""Self-check of the teach piece: the learned program is well-formed, and it still runs with no model.

    .venv/bin/python teach/check.py

Validates teach/tecnocasa.program.json, runs run_program.py for 1 page through the shortcut (no browser),
asserts >= 10 listings with price and size, and that inky.js normalize() takes them.
"""
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROGRAM = HERE / "tecnocasa.program.json"
sys.path.insert(0, str(HERE))
from run_program import typed  # noqa: E402

DO = {"open", "click", "fill", "select", "extract", "next_page"}
STEP_TYPES = {None, "text", "number", "link", "loop"}
FIELDS = {"title", "price", "size_m2", "rooms", "zone", "url"}


def check_program(p):
    assert p["site"] == "tecnocasa.it" and p["city"] and p["start_url"].startswith("https://"), "site, city, start_url"
    datetime.fromisoformat(p["learned_at"])
    assert isinstance(p["llm_calls"], int) and p["llm_calls"] >= 1, "llm_calls"
    for i, s in enumerate(p["steps"], 1):
        assert s["n"] == f"{i:02d}" and s["do"] in DO and s["type"] in STEP_TYPES, f"step {s}"
        assert isinstance(s["label"], str) and s["label"], f"step {s['n']} has no label"
        assert s["target"] is None or ({"css", "role", "name"} <= set(s["target"]) and s["target"]["css"]), f"step {s['n']} target"
        assert s["do"] == "open" or s["target"], f"step {s['n']} needs a target"
    assert {"open", "extract", "next_page"} <= {s["do"] for s in p["steps"]}, "open, extract and next_page steps"
    f = p["item"]["fields"]
    assert p["item"]["selector"] and FIELDS <= set(f), "item selector and fields"
    for k, v in f.items():
        assert v["css"] and v["type"] in ("text", "int", "link"), f"field {k}"
    assert f["url"].get("attr") == "href" and f["url"]["type"] == "link", "url field"
    sc = p["shortcut"]
    if sc:
        assert sc["kind"] == "json_api" and sc["method"] in ("GET", "POST") and sc["url"].startswith("https://"), "shortcut"
        assert isinstance(sc["params"], dict) and sc["page_param"] and isinstance(sc["items_path"], str), "shortcut params"
        assert all(v.get("json") for v in f.values()), "every field needs a json key when there is a shortcut"


def normalized(items):
    """How many items inky.js normalize() turns into listings (the same code runs in n8n)."""
    js = ("const {normalize} = require(process.argv[1]); const items = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
          "process.stdout.write(String(items.filter(i => normalize(i, 4.3, {city: i.city, op: i.op})).length));")
    r = subprocess.run(["node", "-e", js, str(ROOT / "inky.js")], input=json.dumps(items), capture_output=True, text=True, check=True)
    return int(r.stdout)


def main():
    assert typed("€ 175.000", {"type": "int"}, "") == 175000
    assert typed("76 Mq", {"type": "int", "re": r"([\d.,]+)\s*Mq"}, "") == 76
    assert typed("Bari, Via Lembo - Santo Spirito", {"type": "text", "re": r".*-\s*(.+)$"}, "") == "Santo Spirito"
    assert typed("/vendita/1.html", {"type": "link"}, "https://www.tecnocasa.it/") == "https://www.tecnocasa.it/vendita/1.html"

    if not PROGRAM.exists():
        sys.exit("No program yet: run .venv/bin/python teach/learn.py first (opens Chrome, one GLM-5.3 call).")
    p = json.loads(PROGRAM.read_text())
    check_program(p)
    print(f"program ok: {len(p['steps'])} steps, fields {', '.join(p['item']['fields'])}, "
          f"shortcut {p['shortcut']['url'] if p['shortcut'] else 'none'}, {p['llm_calls']} GLM call(s)", flush=True)
    if not p["shortcut"]:
        print("no shortcut learned: skipped the no-browser run (try run_program.py --browser --pages 1)")
        return

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.json"
        subprocess.run([sys.executable, str(HERE / "run_program.py"), "--pages", "1", "--out", str(out)], check=True)
        items = json.loads(out.read_text())
    good = [i for i in items if isinstance(i["price"], int) and i["price"] > 1000 and isinstance(i["size_m2"], int) and i["size_m2"] > 10]
    assert len(good) >= 10, f"only {len(good)} of {len(items)} listings have a price and a size"
    n = normalized(items)
    assert n >= 10, f"inky.js normalize() kept only {n} of {len(items)}"
    print(f"ok: {len(good)} listings with price and size from 1 request, {n} normalise in inky.js")


if __name__ == "__main__":
    main()
