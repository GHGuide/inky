"""Set up a shared Inky bundle in your own n8n, through its API.

    python share/import.py --dry-run     # checks the bundle and your .env, changes nothing
    python share/import.py               # creates the credentials and both workflows, not published
    python share/import.py --activate    # the same, and publishes them: it starts running every 15 minutes
    python share/import.py --env other/.env --bundle share/bundle
    python share/import.py --staging     # a test copy: "Inky · staging import ...", Telegram/Gmail/schedules off, never published

Everything comes from your own .env: your n8n, your Apify, Telegram and OpenRouter keys. Nothing of the person who
shared the bundle is in it (share/export.py checks that).
"""
import argparse
import json
import secrets
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import workflow  # noqa: E402

NEEDED = ["N8N_BASE_URL", "N8N_API_KEY", "APIFY_TOKEN", "TELEGRAM_BOT_TOKEN", "OPENROUTER_API_KEY"]


def chat_of(env):
    if env.get("TELEGRAM_CHAT_ID"):
        return env["TELEGRAM_CHAT_ID"]
    updates = httpx.get(f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/getUpdates", timeout=20).json().get("result", [])
    ids = [u["message"]["chat"]["id"] for u in updates if "message" in u]
    if not ids:
        raise SystemExit("No Telegram chat yet: send /start to your bot (or set TELEGRAM_CHAT_ID), then run again.")
    return str(ids[-1])


def fill(wf, values):
    """Replace the bundle's placeholders (credential ids, chat, workflow ids, webhook path) with this n8n's values."""
    text = json.dumps(wf, ensure_ascii=False)
    for k, v in values.items():
        text = text.replace(k, v)
    return json.loads(text)


def install(bundle, env, staging=False, activate=False, dry_run=False, say=print):
    missing = [k for k in NEEDED if not env.get(k)]
    main_wf = json.loads((bundle / "inky-main.json").read_text())
    repair_wf = json.loads((bundle / "inky-repair.json").read_text())
    gmail = env.get("N8N_GMAIL_CREDENTIAL_ID")
    say(f"Bundle: {main_wf['name']} ({workflow.steps(main_wf)} steps) and {repair_wf['name']} ({workflow.steps(repair_wf)} steps)")
    say(f"Target: {env.get('N8N_BASE_URL') or '?'} · Gmail drafts {'on' if gmail else 'paused (no N8N_GMAIL_CREDENTIAL_ID)'}")
    if missing:
        raise SystemExit(f"Missing in the .env: {', '.join(missing)}")
    if dry_run:
        say("Dry run: would create 4 credentials and both workflows" + (", then publish them" if activate and not staging else ", not published"))
        return {}
    api = workflow.N8n(env["N8N_BASE_URL"], env["N8N_API_KEY"])
    made = {}

    def cred(role, type_, name, data):
        c = api.call("POST", "/credentials", json={"name": name, "type": type_, "data": data})
        made[role] = c["id"]
        return c["id"]

    values = {
        "INKY_APIFY_CREDENTIAL": cred("apify", "httpHeaderAuth", "Inky · Apify token", {"name": "Authorization", "value": f"Bearer {env['APIFY_TOKEN']}"}),
        "INKY_TELEGRAM_CREDENTIAL": cred("telegram", "telegramApi", "Inky · Telegram", {"accessToken": env["TELEGRAM_BOT_TOKEN"]}),
        "INKY_N8N_CREDENTIAL": cred("n8n", "n8nApi", "Inky · n8n API", {"apiKey": env["N8N_API_KEY"], "baseUrl": f"{api.base}/api/v1"}),
        "INKY_OPENROUTER_CREDENTIAL": cred("openrouter", "httpHeaderAuth", "Inky · OpenRouter", {"name": "Authorization", "value": f"Bearer {env['OPENROUTER_API_KEY']}"}),
        "INKY_GMAIL_CREDENTIAL": gmail or "",
        "INKY_TELEGRAM_CHAT_ID": chat_of(env),
        "INKY_BEST_PATH": secrets.token_hex(16),
    }
    say("Created the credentials", " · ".join(made))
    main_wf = fill(main_wf, values)
    main_wf["settings"].pop("errorWorkflow", None)  # linked below, once the repair workflow exists
    if not gmail:
        for n in main_wf["nodes"]:
            if n["type"] == "n8n-nodes-base.gmail":
                n["disabled"] = True
                n.pop("credentials", None)
    if staging:
        workflow.stage(main_wf, "Inky · staging import main")
    main_id = api.call("POST", "/workflows", json=main_wf)["id"]
    repair_wf = fill(repair_wf, {**values, "INKY_MAIN_WORKFLOW_ID": main_id})
    if staging:
        workflow.stage(repair_wf, "Inky · staging import repair")
    repair_id = api.call("POST", "/workflows", json=repair_wf)["id"]
    main_wf["settings"]["errorWorkflow"] = repair_id
    api.call("PUT", f"/workflows/{main_id}", json=main_wf)
    say("Created both workflows", f"{api.base}/workflow/{main_id}")
    if activate and not staging:
        api.call("POST", f"/workflows/{main_id}/activate")
        api.call("POST", f"/workflows/{repair_id}/activate")
        say("Published both workflows", "runs every 15 minutes, digest at 08:00")
    return {"main": main_id, "repair": repair_id, "credentials": made, "base": api.base, "best_path": values["INKY_BEST_PATH"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bundle", default=str(HERE / "bundle"))
    p.add_argument("--env", default=".env", help="the .env with YOUR n8n and keys")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--activate", action="store_true", help="publish both workflows after creating them")
    p.add_argument("--staging", action="store_true", help="a test copy: Telegram, Gmail and schedules off, never published")
    a = p.parse_args()
    out = install(Path(a.bundle), dotenv_values(a.env), a.staging, a.activate, a.dry_run,
                  say=lambda text, sub=None: print(text + (f" · {sub}" if sub else "")))
    if out:
        print(f"main:   {out['base']}/workflow/{out['main']}\nrepair: {out['base']}/workflow/{out['repair']}")


if __name__ == "__main__":
    main()
