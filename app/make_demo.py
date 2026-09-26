"""Regenerate data-demo/, the snapshot `app/serve.py --demo` serves: the app working for anyone who clones the repo,
without keys. No keys, no n8n ids or links, small enough to commit (checked: < 2 MB).

    .venv/bin/python app/make_demo.py                 # data/ + the live n8n and Apify numbers (read only); keeps the recorded replies
    .venv/bin/python app/make_demo.py --record        # also re-records interview, command and share: real GLM calls, about $0.05
    .venv/bin/python app/make_demo.py --record-build  # also records the steps of a staging deploy (Telegram, Gmail, schedules off)

The research replay costs nothing: derive.run(rescore=True) re-tests the saved GLM versions on a temp copy of data/.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import serve  # noqa: E402  (loads .env, moves to the repo root)
from dotenv import dotenv_values  # noqa: E402

OUT, DATA, MATCHES = serve.DEMO_DIR, serve.ROOT / "data", 60
serve.DATA = DATA
INTERVIEW = ["I have about €200,000 and want to earn rent from a flat abroad.",
             "Cash, no mortgage. Any of Porto, Bari or Łódź. A 1-2 bedroom flat that is ready to rent, to long-term local tenants, "
             "managed by a local agency. I don't want anything that needs big repairs."]


def trim(research):
    return {**research, "matches": research["matches"][:MATCHES]}


def scrub(obj):
    """n8n links and ids become placeholders; any key from .env left in the text stops the script."""
    text, ids = json.dumps(obj, ensure_ascii=False), set()
    base = os.environ.get("N8N_BASE_URL", "").rstrip("/")
    if base:
        text = text.replace(base, serve.DEMO_LINKS["base"]).replace(base.split("//")[-1], "your-n8n.example")
    for f in ("n8n.json", "n8n-staging.json"):  # workflow ids, the webhook path, credential ids
        s = serve.read_json(serve.N8N_STATE.with_name(f)) or {}
        ids |= {v for v in s.values() if isinstance(v, str)} | {c.get("id") for c in (s.get("credentials") or {}).values()}
    for i in sorted((i for i in ids if i and len(i) >= 6), key=len, reverse=True):
        text = text.replace(i, "N8N_ID")
    for k, v in dotenv_values(serve.ROOT / ".env").items():
        assert k == "OPENROUTER_MODEL" or not v or len(v) < 8 or v not in text, f"{k} would end up in data-demo/"
    return json.loads(text)


def record_interview():
    msgs, replies = [], []
    for text in INTERVIEW + ["Use your defaults for the rest."] * 4:
        msgs.append({"role": "user", "content": text})
        replies.append(serve.interview({"messages": msgs}))
        if replies[-1]["done"]:
            return replies
        msgs.append({"role": "assistant", "content": replies[-1]})
    return replies


def main():
    files = {
        "research.json": trim(json.loads((DATA / "research.json").read_text())),
        "rules.json": json.loads((DATA / "rules.json").read_text()),
        "zones.json": json.loads((DATA / "zones.json").read_text()),
        "race.json": json.loads((DATA / "race.json").read_text()),
        "plan.json": json.loads((serve.ROOT / "plan.json").read_text()),
        "program.json": json.loads((serve.ROOT / "teach" / "tecnocasa.program.json").read_text()),
        "executions.json": serve.executions()[:80],
        "run_detail.json": serve.run_detail(),
        "summary.json": serve.summary(),
        "end.json": serve.end(),
    }
    tmp = Path(tempfile.mkdtemp(prefix="inky-demo-"))
    (tmp / "raw").symlink_to((DATA / "raw").resolve())
    for f in ("research.json", "rules.json", "zones.json", "costs.json"):
        shutil.copy(DATA / f, tmp)
    events = []
    research, rules = serve.derive.run(events.append, data_dir=tmp, rescore=True)
    files["replies/research_run.json"] = events + [{"type": "done", "research": trim(research), "rules": rules}]
    shutil.rmtree(tmp)
    if "--record" in sys.argv:
        files["replies/interview.json"] = record_interview()
        r = serve.command({"text": "Only homes under €150,000", "dry_run": True})
        files["replies/command.json"] = {**{k: v for k, v in r.items() if k != "dry_run"}, "applied": False, "demo": True,
                                         "n8n_error": "demo mode: shown, not saved or pushed to n8n"}
        files["replies/share.json"] = serve.share({"to": "Sanne", "text": "Same idea, she lives in Utrecht"})
    if "--record-build" in sys.argv:
        kind, job = serve.build_run({"staging": True})
        steps = []
        done = job(steps.append)
        files["replies/build_run.json"] = steps + [{"type": "done", **done}]
    (OUT / "replies").mkdir(parents=True, exist_ok=True)
    for name, obj in files.items():
        (OUT / name).write_text(json.dumps(scrub(obj), ensure_ascii=False, indent=1))
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    missing = [n for n in ("interview", "command", "share", "build_run") if not (OUT / "replies" / f"{n}.json").exists()]
    print(f"wrote {OUT}: {size / 1e6:.2f} MB" + (f"; still missing replies/{', '.join(missing)} (--record / --record-build)" if missing else ""))
    assert size < 2e6, "data-demo/ must stay under 2 MB"


if __name__ == "__main__":
    main()
