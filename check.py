"""Check every key in .env with one free call each. Prints status only, never secrets."""
import os
import subprocess
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()
env = os.environ.get


def openrouter():
    r = httpx.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {env('OPENROUTER_API_KEY')}"})
    r.raise_for_status()
    d = r.json()["data"]
    return f"credit used ${d.get('usage', 0):.2f}, limit {d.get('limit')}"


def apify():
    r = httpx.get("https://api.apify.com/v2/users/me", headers={"Authorization": f"Bearer {env('APIFY_TOKEN')}"})
    r.raise_for_status()
    return f"user {r.json()['data']['username']}"


def n8n():
    base = env("N8N_BASE_URL", "").rstrip("/")
    r = httpx.get(f"{base}/api/v1/workflows", params={"limit": 1}, headers={"X-N8N-API-KEY": env("N8N_API_KEY")})
    r.raise_for_status()
    return "API reachable"


def telegram():
    t = env("TELEGRAM_BOT_TOKEN")
    me = httpx.get(f"https://api.telegram.org/bot{t}/getMe").json()
    if not me.get("ok"):
        raise RuntimeError(me.get("description"))
    chats = {u["message"]["chat"]["id"] for u in httpx.get(f"https://api.telegram.org/bot{t}/getUpdates").json().get("result", []) if "message" in u}
    if not chats and not env("TELEGRAM_CHAT_ID"):
        raise RuntimeError(f"bot @{me['result']['username']} has no chat yet: send /start to it")
    return f"bot @{me['result']['username']}, chat ids {sorted(chats) or env('TELEGRAM_CHAT_ID')}"


def tools():
    missing = [c for c in ("node",) if subprocess.run(["which", c], capture_output=True).returncode]
    if missing:
        raise RuntimeError(f"missing {', '.join(missing)}")
    return "node found"


failed = 0
for name, fn in [("OpenRouter", openrouter), ("Apify", apify), ("n8n", n8n), ("Telegram", telegram), ("Tools", tools)]:
    try:
        print(f"ok    {name}: {fn()}")
    except Exception as e:
        failed += 1
        msg = str(e)
        for k in ("OPENROUTER_API_KEY", "APIFY_TOKEN", "N8N_API_KEY", "TELEGRAM_BOT_TOKEN"):
            if env(k):
                msg = msg.replace(env(k), "<redacted>")
        print(f"FAIL  {name}: {type(e).__name__} {msg[:120]}")
sys.exit(1 if failed else 0)
