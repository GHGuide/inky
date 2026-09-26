"""One command from keys to a running agent.

    uv run python build.py                 # everything: check, test scrape, full scrape, rules, n8n
    uv run python build.py --from derive   # resume at a step
    uv run python build.py --offline       # no keys, no spend: fixture data, offline rules, n8n dry run

Steps: check -> test-scrape (~$0.30) -> scrape (~$55, capped per job) -> derive (GLM-5.3) -> n8n.
Stops at the first failing step. Each step is also its own script.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PY = sys.executable
DATA = Path(os.environ.get("INKY_DATA", "data"))
STEPS = {
    "check": [PY, "check.py"],
    "test-scrape": [PY, "research.py"],
    "scrape": [PY, "research.py", "--full"],
    "derive": [PY, "derive.py"],
    "n8n": [PY, "workflow.py"],
}


def run(name, cmd):
    print(f"\n== {name}: {' '.join(Path(c).name if c == PY else c for c in cmd)}", flush=True)
    if subprocess.run(cmd).returncode != 0:
        raise SystemExit(f"stopped at '{name}'. Fix it, then: uv run python build.py --from {name}")
    if name == "test-scrape":
        empty = [f.stem for f in (DATA / "raw").glob("*.json") if not json.loads(f.read_text())]
        if empty:
            raise SystemExit(f"stopped: test scrape returned nothing for {', '.join(empty)}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start", choices=list(STEPS), default="check")
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()

    if args.offline:
        os.environ["INKY_DATA"] = "data-offline"
        run("fixtures", [PY, "test_pipeline.py", "--fixtures-only"])
        run("derive", [PY, "derive.py", "--offline"])
        run("n8n", [PY, "workflow.py", "--dry-run"])
        return
    names = list(STEPS)
    for name in names[names.index(args.start):]:
        run(name, STEPS[name])
    r = json.loads((DATA / "research.json").read_text())
    print(f"\nDone. {r['listings_read']} listings read, rules v1-v3: "
          + " -> ".join(str(v["matches"]) for v in r["versions"]) + " matches. The agent now runs every 15 minutes.")


if __name__ == "__main__":
    main()
