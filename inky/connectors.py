"""Connectors: every outside service Inky talks to, each with a status, a real test and a fix when it fails.
Claude Code, Codex and any other MCP server go through inky.mcp. Telegram, n8n and Apify are built in: they
offer tools shaped like an MCP server's, so delegate, automations and the approval gate treat them the same."""
import glob
import json
import os
import re
import shutil
import subprocess
import time

import httpx

COMMON_DIRS = ["/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin", "~/.npm-global/bin", "~/.bun/bin", "~/.cargo/bin",
               "~/.claude/local", "~/.nvm/versions/node/*/bin", "~/.volta/bin", "/Applications/Docker.app/Contents/Resources/bin"]


def fix_path(env=os.environ, shell=None):
    """An app opened from the Dock gets a bare PATH, so claude, codex, ollama, docker and gh look missing.
    Add your login shell's PATH and the usual install folders after what's already there."""
    parts = [p for p in env.get("PATH", "").split(os.pathsep) if p]
    if os.name != "nt":  # Windows apps already get the full user PATH
        try:
            out = subprocess.run([shell or env.get("SHELL") or "/bin/zsh", "-ilc", 'printf %s "$PATH"'], capture_output=True,
                                 text=True, timeout=3, stdin=subprocess.DEVNULL).stdout.strip()
            if out:
                parts += out.splitlines()[-1].split(os.pathsep)  # the last line: rc files may print greetings first
        except Exception:
            pass
        home = env.get("HOME") or os.path.expanduser("~")
        for d in COMMON_DIRS:
            d = home + d[1:] if d.startswith("~") else d
            parts += sorted(glob.glob(d)) if "*" in d else [d]
    env["PATH"] = os.pathsep.join(dict.fromkeys(p for p in parts if p))
    return env["PATH"]


# ---------------------------------------------------------------- Claude Code and Codex: installed? signed in?
STATUS_CACHE = {}
INSTALL = {"claude-code": ("Install Claude Code, then come back.", "https://docs.anthropic.com/en/docs/claude-code/setup"),
           "codex": ("Install Codex, then come back.", "https://github.com/openai/codex#quickstart")}


def _run(cmd, timeout=5):
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        return subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except Exception:
        return None


def signed_in(name):
    """True, False, or None when we can't tell. Cached for 30 s: the CLIs take a moment to answer."""
    hit = STATUS_CACHE.get(name)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    val = None
    if name == "claude-code":
        r = _run(["claude", "auth", "status"])
        if r and r.stdout.strip():
            try:
                val = bool(json.loads(r.stdout).get("loggedIn"))
            except ValueError:
                val = r.returncode == 0
    elif name == "codex":
        r = _run(["codex", "login", "status"])
        val = None if r is None else r.returncode == 0
    STATUS_CACHE[name] = (time.time(), val)
    return val


def status(E):
    out = []
    for s in E.mcp.servers():
        from inky.mcp import PRESETS
        v = {"name": s["name"], "label": s["label"], "about": s["about"], "kind": "mcp", "preset": s["preset"],
             "overridden": bool(s["preset"] and s["command"] != PRESETS[s["name"]]["command"]),
             "logo": {"claude-code": "claude", "codex": "codex"}.get(s["name"], "mcp"), "command": s["command"],
             "installed": s["installed"], "enabled": s["enabled"], "connected": s["connected"], "tools": s["tools"],
             "signed_in": None, "detail": "", "fix": "", "fix_url": ""}
        if s["name"] in INSTALL:
            if not s["installed"]:
                v.update(detail="Not installed on this computer.", fix=INSTALL[s["name"]][0], fix_url=INSTALL[s["name"]][1])
            else:
                v["signed_in"] = signed_in(s["name"])
                if v["signed_in"] is False and s["name"] == "claude-code":
                    v.update(detail="Signed out. Its file and shell tools work; handing it a whole task needs you signed in.",
                             fix="Open a terminal, run claude and sign in.")
                elif v["signed_in"] is False:
                    v.update(detail="Signed out.", fix="Open a terminal, run codex login and sign in.")
        elif not s["installed"]:
            v.update(detail=f"“{s['command'][0]}” isn’t on this computer.", fix="Install it, or check the command.")
        if s.get("error") and not s["connected"]:
            v.update(detail=f"Last try: {s['error']}", fix=v["fix"] or "Check the command and its settings, then Connect again.")
        out.append(v)
    out += [p.view(E) for p in PROVIDERS.values()]
    return out


def test(E, name):
    """A real check: list an MCP server's tools, or ask a built-in service who you are."""
    if name in PROVIDERS:
        return PROVIDERS[name].test(E)
    if not E.mcp.known(name):
        return {"ok": False, "text": f"There’s no connector called {name}."}
    try:
        E.mcp.save(name, enabled=True)
        tools = E.mcp.tools(name)
        return {"ok": True, "text": f"Connected. {len(tools)} tools: " + ", ".join(t["name"] for t in tools[:12])}
    except Exception as e:
        return {"ok": False, "text": str(e)[:300]}


# ---------------------------------------------------------------- built-in providers
def _err(e, service, url=""):
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        return f"{service} refused the key ({code})." if code in (401, 403) else f"{service} answered {code}."
    if isinstance(e, httpx.RequestError):
        return f"Couldn’t reach {service}{' at ' + url if url else ''}."
    return str(e)[:200]


class Provider:
    name = label = logo = about = ""
    fields = []

    def configured(self, E):
        return False

    def tools(self):
        return []

    def view(self, E):
        on = self.configured(E)
        return {"name": self.name, "label": self.label, "logo": self.logo, "about": self.about, "kind": "builtin",
                "installed": True, "enabled": on, "connected": on, "signed_in": None, "fields": self.fields,
                "tools": [t["name"] for t in self.tools()], "detail": self.detail(E), "fix": "", "fix_url": "", "values": self.values(E)}

    def values(self, E):
        """Non-secret settings you saved, so a form can show them again."""
        return {}

    def detail(self, E):
        return "Connected." if self.configured(E) else "Not set up yet."


class Telegram(Provider):
    name, label, logo = "telegram", "Telegram", "telegram"
    about = "Your bots message you and ask you things on your phone."
    fields = [{"key": "token", "label": "Bot token from @BotFather", "secret": True, "placeholder": "123456789:AA…"}]

    def api(self, token, method):
        return f"{os.environ.get('TELEGRAM_API', 'https://api.telegram.org')}/bot{token}/{method}"

    def configured(self, E):
        return bool(E.keys.get("telegram") and E.store.setting("telegram", {}).get("chat_id"))

    def detail(self, E):
        tg = E.store.setting("telegram", {})
        if not E.keys.get("telegram"):
            return "Not set up yet."
        if not tg.get("chat_id"):
            return f"Send /start to {'@' + tg['bot'] if tg.get('bot') else 'your bot'} in Telegram to finish."
        return f"Messages go to you through {'@' + tg['bot'] if tg.get('bot') else 'your bot'}."

    def save(self, E, values):
        token = (values.get("token") or "").strip()
        if not token:
            return {"ok": False, "text": "Paste the token from @BotFather first."}
        if not re.match(r"^\d{5,}:[\w-]{20,}$", token):
            return {"ok": False, "text": "That doesn’t look like a bot token. It looks like 123456789:AA… and comes from @BotFather."}
        try:
            r = httpx.get(self.api(token, "getMe"), timeout=15).json()
        except Exception as e:
            return {"ok": False, "text": _err(e, "Telegram")}
        if not r.get("ok"):
            return {"ok": False, "text": "Telegram didn’t accept that token. Copy it again from @BotFather."}
        bot = r["result"].get("username")
        E.keys.set("telegram", token)
        E.store.set_setting("telegram", {**E.store.setting("telegram", {}), "bot": bot})
        return {"ok": True, "bot": bot, "text": f"Connected to @{bot}. Now send /start to @{bot} in Telegram."}

    def find_chat(self, E):
        """The chat that last sent /start to your bot. Saved, and alerts turned on."""
        token = E.keys.get("telegram")
        if not token:
            return None
        try:
            ups = httpx.get(self.api(token, "getUpdates"), params={"timeout": 0}, timeout=15).json().get("result", [])
        except Exception:
            return None
        chats = [u["message"]["chat"]["id"] for u in ups if (u.get("message") or {}).get("text", "").startswith("/start")]
        if not chats:
            return None
        E.store.set_setting("telegram", {**E.store.setting("telegram", {}), "chat_id": chats[-1], "enabled": True})
        return chats[-1]

    def send(self, E, text):
        token, chat = E.keys.get("telegram"), E.store.setting("telegram", {}).get("chat_id")
        if not (token and chat):
            raise RuntimeError("Telegram isn’t set up yet")
        r = httpx.post(self.api(token, "sendMessage"), json={"chat_id": chat, "text": text[:4000]}, timeout=15)
        r.raise_for_status()
        return r.json()

    def test(self, E):
        if not E.keys.get("telegram"):
            return {"ok": False, "text": "Paste your bot token first."}
        if not E.store.setting("telegram", {}).get("chat_id") and not self.find_chat(E):
            bot = E.store.setting("telegram", {}).get("bot")
            return {"ok": False, "text": f"Send /start to {'@' + bot if bot else 'your bot'} in Telegram, then test again."}
        try:
            self.send(E, "Inky is connected. Your bots will message you here.")
            return {"ok": True, "text": "Sent you a message on Telegram."}
        except Exception as e:
            return {"ok": False, "text": _err(e, "Telegram")}

    def tools(self):
        return [{"name": "send_message", "description": "Send a Telegram message to you.",
                 "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}]

    def call(self, E, tool, args):
        if tool != "send_message":
            return {"text": f"no tool {tool}", "error": True}
        try:
            self.send(E, str(args.get("text", "")))
            return {"text": "sent", "error": False}
        except Exception as e:
            return {"text": _err(e, "Telegram"), "error": True}


def n8n_workflow(skill, inky_url, cred=None):
    """An n8n workflow that runs one skill every 15 minutes. Inky's token lives in an n8n credential, never in here."""
    run = f"Run {skill['name']} (no AI)"
    return {"name": f"Inky · {skill['name']}", "nodes": [
        {"parameters": {"rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}}, "name": "Every 15 minutes",
         "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0], "id": "t1"},
        {"parameters": {"method": "POST", "url": f"{inky_url}/api/bots/{skill['bot_id']}/run",
                        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
                        "sendBody": True, "specifyBody": "json", "jsonBody": json.dumps({"skill": skill["id"], "wait": True})},
         "credentials": {"httpHeaderAuth": cred or {"name": "Inky token (Header X-Inky-Token)"}},
         "name": run, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [260, 0], "id": "r1"}],
        "connections": {"Every 15 minutes": {"main": [[{"node": run, "type": "main", "index": 0}]]}}, "settings": {}}


class N8n(Provider):
    name, label, logo = "n8n", "n8n", "n8n"
    about = "Send a skill to n8n, and let bots start your n8n workflows."
    fields = [{"key": "url", "label": "Your n8n address", "secret": False, "placeholder": "http://localhost:5678"},
              {"key": "key", "label": "n8n API key (Settings → n8n API)", "secret": True, "placeholder": "n8n_api_…"}]

    def conf(self, E):
        return E.store.setting("n8n", {}).get("url"), E.keys.get("n8n")

    def values(self, E):
        return {"url": E.store.setting("n8n", {}).get("url") or ""}

    def configured(self, E):
        return all(self.conf(E))

    def req(self, method, url, key, path, **kw):
        r = httpx.request(method, url + "/api/v1" + path, headers={"X-N8N-API-KEY": key}, timeout=20, **kw)
        r.raise_for_status()
        return r.json()

    def save(self, E, values):
        url = (values.get("url") or E.store.setting("n8n", {}).get("url") or "").strip().rstrip("/")
        key = (values.get("key") or "").strip() or E.keys.get("n8n")
        if not url.startswith(("http://", "https://")) or not key:
            return {"ok": False, "text": "Put in your n8n address (http://…) and an API key."}
        try:
            wf = self.req("GET", url, key, "/workflows", params={"limit": 100}).get("data", [])
        except Exception as e:
            return {"ok": False, "text": _err(e, "n8n", url)}
        E.keys.set("n8n", key)
        E.store.set_setting("n8n", {**E.store.setting("n8n", {}), "url": url})
        return {"ok": True, "text": f"Connected. {len(wf)} workflow{'' if len(wf) == 1 else 's'} in your n8n."}

    def list_workflows(self, E):
        url, key = self.conf(E)
        return self.req("GET", url, key, "/workflows", params={"limit": 100}).get("data", [])

    def test(self, E):
        if not self.configured(E):
            return {"ok": False, "text": "Put in your n8n address and API key first."}
        try:
            wf = self.list_workflows(E)
            return {"ok": True, "text": f"{len(wf)} workflows: " + ", ".join(f"{w['name']}{' (on)' if w.get('active') else ''}" for w in wf[:10])}
        except Exception as e:
            return {"ok": False, "text": _err(e, "n8n", self.conf(E)[0])}

    def send_skill(self, E, skill, inky_url=None):
        url, key = self.conf(E)
        n = E.store.setting("n8n", {})
        if not n.get("cred_id"):  # one credential holds Inky's token, reused by every workflow we send
            c = self.req("POST", url, key, "/credentials", json={"name": "Inky token", "type": "httpHeaderAuth",
                                                                   "data": {"name": "X-Inky-Token", "value": E.token}})
            n = {**n, "cred_id": c["id"]}
            E.store.set_setting("n8n", n)
        # ponytail: n8n reaches Inky at 127.0.0.1, so n8n must run on this computer (not in Docker or elsewhere)
        wf = n8n_workflow(skill, inky_url or f"http://127.0.0.1:{getattr(E, 'port', 8800)}", {"id": n["cred_id"], "name": "Inky token"})
        return self.req("POST", url, key, "/workflows", json=wf)

    def tools(self):
        return [{"name": "trigger", "description": "Start an n8n workflow through its webhook, with a JSON payload (for example the new results).",
                 "inputSchema": {"type": "object", "properties": {"webhook_url": {"type": "string"}, "payload": {"type": "object"}}, "required": ["webhook_url"]}},
                {"name": "list_workflows", "description": "List your n8n workflows.", "inputSchema": {"type": "object", "properties": {}}}]

    def call(self, E, tool, args):
        url, key = self.conf(E)
        try:
            if tool == "list_workflows":
                return {"text": json.dumps([{"id": w["id"], "name": w["name"], "active": w.get("active")} for w in self.list_workflows(E)]), "error": False}
            if tool == "trigger":
                hook = str(args.get("webhook_url", ""))
                hook = url + hook if hook.startswith("/") else hook
                if not (url and hook.startswith(url + "/")):  # bots only call your own n8n, never another address
                    return {"text": f"That webhook isn’t on your n8n ({url}).", "error": True}
                r = httpx.post(hook, json=args.get("payload") or {}, timeout=60)
                r.raise_for_status()
                return {"text": r.text[:4000] or "started", "error": False}
            return {"text": f"no tool {tool}", "error": True}
        except Exception as e:
            return {"text": _err(e, "n8n", url), "error": True}


class Apify(Provider):
    name, label, logo = "apify", "Apify", "apify"
    about = "Run any Apify Actor and bring its items back as results."
    fields = [{"key": "token", "label": "Apify API token (Settings → API & Integrations)", "secret": True, "placeholder": "apify_api_…"}]

    def base(self):
        return os.environ.get("APIFY_API", "https://api.apify.com") + "/v2"

    def configured(self, E):
        return bool(E.keys.get("apify"))

    def me(self, token):
        r = httpx.get(self.base() + "/users/me", headers={"Authorization": f"Bearer {token}"}, timeout=20)
        r.raise_for_status()
        return r.json().get("data", {})

    def save(self, E, values):
        token = (values.get("token") or "").strip()
        if not token:
            return {"ok": False, "text": "Paste your Apify token first."}
        try:
            me = self.me(token)
        except Exception as e:
            return {"ok": False, "text": _err(e, "Apify")}
        E.keys.set("apify", token)
        return {"ok": True, "text": f"Connected as {me.get('username')}."}

    def test(self, E):
        if not self.configured(E):
            return {"ok": False, "text": "Paste your Apify token first."}
        try:
            me = self.me(E.keys.get("apify"))
            return {"ok": True, "text": f"Signed in as {me.get('username')} ({(me.get('plan') or {}).get('id', 'plan unknown')})."}
        except Exception as e:
            return {"ok": False, "text": _err(e, "Apify")}

    def tools(self):
        return [{"name": "run_actor", "description": "Run an Apify Actor (like apify/web-scraper) with input and return its dataset items.",
                 "inputSchema": {"type": "object", "properties": {"actor": {"type": "string"}, "input": {"type": "object"},
                                                                  "limit": {"type": "integer"}}, "required": ["actor"]}}]

    def call(self, E, tool, args):
        if tool != "run_actor":
            return {"text": f"no tool {tool}", "error": True}
        actor, limit = str(args.get("actor", "")).replace("/", "~"), int(args.get("limit") or 50)
        try:
            r = httpx.post(f"{self.base()}/acts/{actor}/run-sync-get-dataset-items", params={"limit": limit},
                           headers={"Authorization": f"Bearer {E.keys.get('apify')}"}, json=args.get("input") or {}, timeout=310)
            r.raise_for_status()
            return {"text": json.dumps(r.json()[:limit], ensure_ascii=False), "error": False}
        except Exception as e:
            return {"text": _err(e, "Apify"), "error": True}


PROVIDERS = {"telegram": Telegram(), "n8n": N8n(), "apify": Apify()}


class Builtins:
    """What MCPManager needs from the built-in providers: their tools, and calling them."""

    def __init__(self, E):
        self.E = E

    def has(self, name):
        return name in PROVIDERS

    def label(self, name):
        return PROVIDERS[name].label

    def catalog(self):
        return [(n, t) for n, p in PROVIDERS.items() if p.configured(self.E) for t in p.tools()]

    def call(self, name, tool, args):
        return PROVIDERS[name].call(self.E, tool, args)
