"""Set up a shared Inky bundle in your own n8n, through its API.

    python share/import.py --dry-run         # checks the bundle and your .env, changes nothing
    python share/import.py                   # creates the credentials and both workflows, not published
    python share/import.py --activate        # the same, and publishes them: it starts running every 15 minutes
    python share/import.py --no-credentials  # both workflows without credentials: pick your own in n8n (needs only the n8n keys)
    python share/import.py --staging         # a copy named "... (staging copy)": Telegram, Gmail, schedules and re-runs off, never published
    python share/import.py --test            # a throwaway copy: created inactive as "... (import test)", checked, deleted, 404 confirmed
    python share/import.py --env other/.env --bundle share/bundle

Everything comes from your own .env: your n8n, your Apify, Telegram and OpenRouter keys. Nothing of the person who
shared the bundle is in it (share/export.py checks that).
"""
import argparse
import json
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import workflow  # noqa: E402

NEEDED = ["N8N_BASE_URL", "N8N_API_KEY", "APIFY_TOKEN", "TELEGRAM_BOT_TOKEN", "OPENROUTER_API_KEY"]
TEST = " (import test)"


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


def origin(url):
    """https://x.app.n8n.cloud/home/workflows -> https://x.app.n8n.cloud: a pasted browser URL works too."""
    u = urlsplit(url.strip() if "://" in url else f"https://{url.strip()}")
    return f"{u.scheme}://{u.netloc}"


def install(bundle, env, staging=False, activate=False, dry_run=False, say=print, credentials=True, suffix=" (staging copy)", made=None):
    """made collects the ids of what this creates as it goes ({credentials: {role: id}, main, repair}), so a caller can
    undo a half-done import. credentials=False creates none and strips them from every node (and pauses Gmail)."""
    made = {} if made is None else made
    env = {**env, **({"N8N_BASE_URL": origin(env["N8N_BASE_URL"])} if env.get("N8N_BASE_URL") else {})}
    missing = [k for k in (NEEDED if credentials else NEEDED[:2]) if not env.get(k)]
    main_wf = json.loads((bundle / "inky-main.json").read_text())
    repair_wf = json.loads((bundle / "inky-repair.json").read_text())
    gmail = env.get("N8N_GMAIL_CREDENTIAL_ID") if credentials else None
    say(f"Bundle: {main_wf['name']} ({workflow.steps(main_wf)} steps) and {repair_wf['name']} ({workflow.steps(repair_wf)} steps)")
    say(f"Target: {env.get('N8N_BASE_URL') or '?'} · Gmail drafts {'on' if gmail else 'paused (no Gmail credential)'}")
    if missing:
        raise SystemExit(f"Missing in the .env: {', '.join(missing)}")
    if dry_run:
        say(f"Dry run: would create {'4 credentials and ' if credentials else ''}both workflows"
            + (", then publish them" if activate and not staging else ", not published"))
        return {}
    api = workflow.N8n(env["N8N_BASE_URL"], env["N8N_API_KEY"])
    made.setdefault("credentials", {})

    def cred(role, type_, name, data):
        c = api.call("POST", "/credentials", json={"name": name, "type": type_, "data": data})
        made["credentials"][role] = c["id"]
        return c["id"]

    values = {"INKY_BEST_PATH": secrets.token_hex(16)}
    if credentials:
        values.update({
            "INKY_APIFY_CREDENTIAL": cred("apify", "httpHeaderAuth", "Inky · Apify token", {"name": "Authorization", "value": f"Bearer {env['APIFY_TOKEN']}"}),
            "INKY_TELEGRAM_CREDENTIAL": cred("telegram", "telegramApi", "Inky · Telegram", {"accessToken": env["TELEGRAM_BOT_TOKEN"]}),
            "INKY_N8N_CREDENTIAL": cred("n8n", "n8nApi", "Inky · n8n API", {"apiKey": env["N8N_API_KEY"], "baseUrl": f"{api.base}/api/v1"}),
            "INKY_OPENROUTER_CREDENTIAL": cred("openrouter", "httpHeaderAuth", "Inky · OpenRouter", {"name": "Authorization", "value": f"Bearer {env['OPENROUTER_API_KEY']}"}),
            "INKY_GMAIL_CREDENTIAL": gmail or "",
            "INKY_TELEGRAM_CHAT_ID": chat_of(env),
        })
        say("Created the credentials", " · ".join(made["credentials"]))
    elif env.get("TELEGRAM_CHAT_ID"):  # else the Telegram steps keep INKY_TELEGRAM_CHAT_ID for you to replace; Telegram is not called
        values["INKY_TELEGRAM_CHAT_ID"] = env["TELEGRAM_CHAT_ID"]
    main_wf = fill(main_wf, values)
    main_wf["settings"].pop("errorWorkflow", None)  # linked below, once the repair workflow exists
    for n in main_wf["nodes"] + repair_wf["nodes"]:
        if not credentials:
            n.pop("credentials", None)
        if not gmail and n["type"] == "n8n-nodes-base.gmail":
            n["disabled"] = True
            n.pop("credentials", None)
    if staging:
        workflow.stage(main_wf, main_wf["name"] + suffix)
    made["main"] = main_id = api.call("POST", "/workflows", json=main_wf)["id"]
    repair_wf = fill(repair_wf, {**values, "INKY_MAIN_WORKFLOW_ID": main_id})
    if staging:
        workflow.stage(repair_wf, repair_wf["name"] + suffix)
    made["repair"] = repair_id = api.call("POST", "/workflows", json=repair_wf)["id"]
    main_wf["settings"]["errorWorkflow"] = repair_id
    api.call("PUT", f"/workflows/{main_id}", json=main_wf)
    say("Created both workflows", f"{api.base}/workflow/{main_id}")
    if activate and not staging:
        api.call("POST", f"/workflows/{main_id}/activate")
        api.call("POST", f"/workflows/{repair_id}/activate")
        say("Published both workflows", "runs every 15 minutes, digest at 08:00")
    return {"main": main_id, "repair": repair_id, "credentials": made["credentials"], "base": api.base, "best_path": values["INKY_BEST_PATH"]}


def check(api, made, say=print):
    """The test copy as n8n has it: inactive, named '... (import test)', nothing that can message, draft, run on a clock or rerun."""
    for key in ("main", "repair"):
        wf = api.get(made[key])
        loud = [n["name"] for n in wf["nodes"] if (n["type"] in workflow.QUIET_TYPES or n["name"] == "Run it again") and not n.get("disabled")]
        assert wf["name"].endswith(TEST) and not wf.get("active") and not loud, (wf["name"], wf.get("active"), loud)
        assert not any(n.get("credentials") for n in wf["nodes"]), "the test copy has no credentials"
        say(f"Checked {key}", f"{wf['name']} · id {wf['id']} · inactive · {workflow.steps(wf)} steps · Telegram, Gmail, schedules off · no credentials")
    wf = api.get(made["main"])
    assert wf["settings"].get("errorWorkflow") == made["repair"], "main points at the imported repair workflow"


def remove(api, made, say=print):
    """Delete the test copy (only workflows this run made and named '... (import test)'), then GET each: it must be 404."""
    for key in ("main", "repair"):
        wid = made.get(key)
        if not wid:
            continue
        wf = api.get(wid)
        if wf and not wf["name"].endswith(TEST):
            raise SystemExit(f"not deleting {wid}: its name does not end with '{TEST}'")
        if wf:
            api.call("DELETE", f"/workflows/{wid}")
        r = api.http.get(f"/workflows/{wid}")
        assert r.status_code == 404, f"workflow {wid} still answers {r.status_code}"
        say(f"Deleted {key}", f"id {wid} · GET /workflows/{wid} -> 404")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bundle", default=str(HERE / "bundle"))
    p.add_argument("--env", default=".env", help="the .env with YOUR n8n and keys")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--activate", action="store_true", help="publish both workflows after creating them")
    p.add_argument("--staging", action="store_true", help="a copy: Telegram, Gmail, schedules and re-runs off, never published")
    p.add_argument("--no-credentials", action="store_true", help="create no credentials; pick your own in n8n afterwards")
    p.add_argument("--test", action="store_true", help="a throwaway copy with no credentials, never published: checked, then deleted")
    a = p.parse_args()
    say = lambda text, sub=None: print(text + (f" · {sub}" if sub else ""), flush=True)
    env = dotenv_values(a.env)
    if not a.test:
        out = install(Path(a.bundle), env, a.staging, a.activate, a.dry_run, say, credentials=not a.no_credentials)
        if out:
            print(f"main:   {out['base']}/workflow/{out['main']}\nrepair: {out['base']}/workflow/{out['repair']}")
        return
    made = {}
    try:
        install(Path(a.bundle), env, staging=True, dry_run=a.dry_run, say=say, credentials=False, suffix=TEST, made=made)
        if made.get("main"):
            check(workflow.N8n(origin(env["N8N_BASE_URL"]), env["N8N_API_KEY"]), made, say)
    finally:  # also after a failed check or a half-done import; the test creates no credentials
        if made.get("main"):
            remove(workflow.N8n(origin(env["N8N_BASE_URL"]), env["N8N_API_KEY"]), made, say)
    if made.get("main"):
        say("Import test passed", "both workflows were created, checked and deleted; nothing was published or sent")


if __name__ == "__main__":
    main()
