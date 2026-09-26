"""Share an Inky agent as a bundle anyone can set up in their own n8n.

    .venv/bin/python share/export.py                                          # writes share/bundle/ and n8n/inky-*.json
    .venv/bin/python share/export.py --out data/shared/my-agent --author Leo  # another bundle; the app's marketplace lists it

The bundle holds the plan, the final rules, both workflows and bundle.json (title, description, author, created_at).
It holds no keys, no credential or workflow ids, no Telegram chat, no webhook path and no n8n host: those are
placeholders that share/import.py fills in from the other person's own .env.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import workflow  # noqa: E402

CREDS = {role: {"id": f"INKY_{role.upper()}_CREDENTIAL", "name": name} for role, name in [
    ("apify", "Inky · Apify token"), ("telegram", "Inky · Telegram"), ("n8n", "Inky · n8n API"),
    ("openrouter", "Inky · OpenRouter"), ("gmail", "Gmail")]}
CHAT, MAIN, REPAIR, BEST_PATH = "INKY_TELEGRAM_CHAT_ID", "INKY_MAIN_WORKFLOW_ID", "INKY_REPAIR_WORKFLOW_ID", "INKY_BEST_PATH"
SECRET_KEYS = ("OPENROUTER_API_KEY", "APIFY_TOKEN", "N8N_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "N8N_GMAIL_CREDENTIAL_ID", "N8N_MCP_TOKEN")

README = """# Inky: {name}

Inky reads {sites} property sites every 15 minutes, scores every new home with fixed rules (no AI in the loop),
asks you on Telegram and, when you tap "Save as draft", writes a Gmail draft to the agent. It never sends anything.

| File | What it is |
|---|---|
| `plan.json` | What the person who shared this asked for: budget, cities, the kind of home. |
| `rules.json` | The {n_rules} rules Inky derived from real listings for that plan. |
| `inky-main.json` | The n8n workflow: Apify -> score -> Telegram -> Gmail draft, a daily digest, "Send me the best now". |
| `inky-repair.json` | The repair workflow: when a step breaks, GLM-5.3 rewrites that step's input, at most once an hour. |
| `bundle.json` | Title, one-line description, author and date, for the marketplace. |

## Set it up with the API (2 minutes)

You need an n8n with the public API on, and in a `.env` file:
`N8N_BASE_URL`, `N8N_API_KEY`, `APIFY_TOKEN`, `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`,
`TELEGRAM_CHAT_ID` (or send /start to your bot first), and optionally `N8N_GMAIL_CREDENTIAL_ID`
(an existing Gmail OAuth2 credential in your n8n; without it drafts stay paused).

```bash
python share/import.py --dry-run     # checks this bundle and your .env, changes nothing
python share/import.py               # creates the credentials and both workflows, not published
python share/import.py --activate    # the same, and publishes them: it starts running every 15 minutes
python share/import.py --no-credentials  # only needs N8N_BASE_URL and N8N_API_KEY: pick your own credentials in n8n
```

To check the import first, `python share/import.py --test` makes a throwaway copy: both workflows are created
inactive, named "... (import test)", with no credentials and Telegram, Gmail, the schedules and re-runs switched off.
It checks them in n8n, deletes them and confirms each is gone (GET -> 404). Nothing runs, nothing is sent.

## Or import by hand

In n8n: Workflows -> Import from file -> `inky-repair.json`, then `inky-main.json`. Open each red node and pick your
own credential (Apify: header auth `Authorization: Bearer <token>`; Telegram; n8n API; OpenRouter: header auth).
Replace `INKY_TELEGRAM_CHAT_ID` with your chat id, set the repair's "Run it again" to the main workflow, set the main
workflow's error workflow (Settings) to the repair one, and give the "Send me the best now" webhook a secret path.

Costs: about $0.23 of Apify per run at 60 listings per site (at most 120 runs a day), and a few cents of
OpenRouter only when a repair runs.
"""


def build():
    rules, zones, costs, research = workflow.inputs()
    main = workflow.main_workflow(rules, zones, costs, research["pln_per_eur"], CREDS, CHAT, REPAIR, "http",
                                  best_path=BEST_PATH, best=workflow.best_home(research))
    repair = workflow.repair_workflow(MAIN, CREDS, CHAT, workflow.actor_schemas())
    return rules, main, repair


def leaks(text):
    """Keys, credential ids, workflow ids, the webhook path and the n8n host of this installation: never in a bundle."""
    values = [os.environ.get(k) for k in SECRET_KEYS] + [urlsplit(os.environ.get("N8N_BASE_URL", "")).hostname]
    for state in (workflow.load_state(), workflow.load_state(staging=True)):
        values += [c["id"] for c in state["credentials"].values()] + [state.get(k) for k in ("best_path", "main", "repair")]
    return [v[:4] + "…" for v in values if v and len(v) >= 6 and v in text]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(HERE / "bundle"), help="the bundle folder; only the default also refreshes n8n/")
    p.add_argument("--author", help="your name, shown with the bundle in the marketplace")
    a = p.parse_args()
    workflow.load_dotenv(ROOT / ".env")
    rules, main_wf, repair_wf = build()
    plan = json.loads((ROOT / "plan.json").read_text())
    files = {
        "plan.json": plan,
        "rules.json": {"final": rules},
        "inky-main.json": main_wf,
        "inky-repair.json": repair_wf,
        "bundle.json": {"title": main_wf["name"].removeprefix("Inky · "), "description": plan["question"],
                        **({"author": a.author} if a.author else {}), "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    }
    texts = {name: json.dumps(doc, ensure_ascii=False, indent=1) + "\n" for name, doc in files.items()}
    found = leaks("".join(texts.values()))
    if found:
        raise SystemExit(f"not written: the bundle would contain secrets of this installation ({', '.join(found)})")
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (out / name).write_text(text)
    (out / "README.md").write_text(README.format(name=main_wf["name"], sites=len(workflow.SOURCES), n_rules=len(rules)))
    print(f"wrote {out}/ ({', '.join([*texts, 'README.md'])})")
    if out == (HERE / "bundle").resolve():  # the repo's own copy of both workflows (D5)
        (ROOT / "n8n").mkdir(exist_ok=True)
        (ROOT / "n8n" / "inky-main.json").write_text(texts["inky-main.json"])
        (ROOT / "n8n" / "inky-repair.json").write_text(texts["inky-repair.json"])
        print("and n8n/inky-main.json, n8n/inky-repair.json")


if __name__ == "__main__":
    main()
