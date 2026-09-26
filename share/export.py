"""Share an Inky agent as a bundle anyone can set up in their own n8n.

    .venv/bin/python share/export.py    # writes share/bundle/ and n8n/inky-main.json, n8n/inky-repair.json

The bundle holds the plan, the final rules and both workflows. It holds no keys, no credential ids, no Telegram chat
and no webhook path: those are placeholders that share/import.py fills in from the other person's own .env.
"""
import json
import os
import sys
from pathlib import Path

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

## Set it up with the API (2 minutes)

You need an n8n with the public API on, and in a `.env` file:
`N8N_BASE_URL`, `N8N_API_KEY`, `APIFY_TOKEN`, `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`,
`TELEGRAM_CHAT_ID` (or send /start to your bot first), and optionally `N8N_GMAIL_CREDENTIAL_ID`
(an existing Gmail OAuth2 credential in your n8n; without it drafts stay paused).

```bash
python share/import.py --dry-run     # checks this bundle and your .env, changes nothing
python share/import.py               # creates the credentials and both workflows, not published
python share/import.py --activate    # the same, and publishes them: it starts running every 15 minutes
```

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
    """Keys, credential ids, the chat and the webhook path of this installation that must never be in a bundle."""
    state = workflow.load_state()
    values = [os.environ.get(k) for k in SECRET_KEYS] + [c["id"] for c in state["credentials"].values()] + [state.get("best_path")]
    return [v[:4] + "…" for v in values if v and len(v) >= 6 and v in text]


def main():
    workflow.load_dotenv(ROOT / ".env")
    rules, main_wf, repair_wf = build()
    files = {
        "plan.json": json.loads((ROOT / "plan.json").read_text()),
        "rules.json": {"final": rules},
        "inky-main.json": main_wf,
        "inky-repair.json": repair_wf,
    }
    texts = {name: json.dumps(doc, ensure_ascii=False, indent=1) + "\n" for name, doc in files.items()}
    found = leaks("".join(texts.values()))
    if found:
        raise SystemExit(f"not written: the bundle would contain secrets of this installation ({', '.join(found)})")
    out = HERE / "bundle"
    out.mkdir(exist_ok=True)
    for name, text in texts.items():
        (out / name).write_text(text)
    (out / "README.md").write_text(README.format(name=main_wf["name"], sites=len(workflow.SOURCES), n_rules=len(rules)))
    (ROOT / "n8n").mkdir(exist_ok=True)
    (ROOT / "n8n" / "inky-main.json").write_text(texts["inky-main.json"])
    (ROOT / "n8n" / "inky-repair.json").write_text(texts["inky-repair.json"])
    print(f"wrote {out.relative_to(ROOT)}/ ({', '.join([*texts, 'README.md'])}) and n8n/inky-main.json, n8n/inky-repair.json")


if __name__ == "__main__":
    main()
