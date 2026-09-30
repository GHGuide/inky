"""HTTP API + static UI. Every /api call needs the X-Inky-Token header (or ?t= for images and SSE),
so other websites open in your browser can't drive your bots."""
import json
import os
import re
import threading
import time
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from inky import health, transfer
from inky.llm import PROVIDERS, ROLES, fits
from inky.mcp import PRESETS

UI = Path(__file__).parent / "ui"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
         ".png": "image/png", ".json": "application/json", ".webmanifest": "application/manifest+json"}
ROUTES = []


def route(method, pattern):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn))
        return fn
    return deco


class HTTPError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status = status


def bot_or_404(E, bid):
    b = E.store.get("bots", int(bid))
    if not b:
        raise HTTPError(404, "no such bot")
    return b


# ------------------------------------------------------------------ bots
@route("GET", "/api/ping")
def ping(E, h, q, body):
    return {"ok": True, "name": E.store.setting("engine_name", os.uname().nodename), "time": time.time()}


PAIR_TRIES = []


@route("POST", "/api/pair")
def pair_route(E, h, q, body):
    now = time.time()
    PAIR_TRIES[:] = [t for t in PAIR_TRIES if now - t < 60]
    if len(PAIR_TRIES) >= 5:
        raise HTTPError(429, "too many tries, wait a minute")
    PAIR_TRIES.append(now)
    if (body.get("code") or "").upper() != transfer.pair_code(E.token):
        raise HTTPError(403, "wrong code")
    return {"token": E.token, "name": E.store.setting("engine_name", os.uname().nodename)}


@route("GET", "/api/state")
def state(E, h, q, body):
    usage = E.store.setting("usage", {})
    today = usage.get(datetime.now().strftime("%Y-%m-%d"), {"calls": 0, "tokens": 0, "cost": 0})
    return {"bots": E.bots(), "needs": len(E.store.find("needs", status="open")), "setup_done": E.store.setting("setup_done", False),
            "settings": settings_view(E), "today": today, "pair_code": transfer.pair_code(E.token),
            "engine": E.store.setting("engine_name", os.uname().nodename)}


@route("GET", "/api/bots")
def bots(E, h, q, body):
    return {"bots": E.bots()}


@route("POST", "/api/bots/draft")
def draft(E, h, q, body):
    return {"draft": E.draft_bot(body.get("job", ""))}


@route("POST", "/api/bots")
def create(E, h, q, body):
    return {"bot": E.create_bot(body)}


@route("GET", r"/api/bots/(\d+)")
def bot(E, h, q, body, bid):
    b = bot_or_404(E, bid)
    bid = int(bid)
    return {"bot": E.bot_view(b), "skills": E.store.find("skills", bot_id=bid, desc=False),
            "messages": list(reversed(E.store.find("messages", bot_id=bid, limit=120))),
            "runs": E.store.find("runs", bot_id=bid, limit=30),
            "events": [e for e in E.store.find("events", bot_id=bid, limit=120) if e.get("kind") != "ai"][:60],
            "needs": E.store.find("needs", bot_id=bid, status="open")}


@route("PATCH", r"/api/bots/(\d+)")
def patch_bot(E, h, q, body, bid):
    bot_or_404(E, bid)
    return {"bot": E.update_bot(int(bid), body)}


@route("DELETE", r"/api/bots/(\d+)")
def delete_bot(E, h, q, body, bid):
    bot_or_404(E, bid)
    E.delete_bot(int(bid))
    return {"ok": True}


@route("POST", r"/api/bots/(\d+)/chat")
def chat(E, h, q, body, bid):
    bot_or_404(E, bid)
    return E.chat(int(bid), body.get("text", ""), source=body.get("source", "app"))


@route("POST", r"/api/bots/(\d+)/learn")
def learn(E, h, q, body, bid):
    b = bot_or_404(E, bid)
    E.learn(int(bid), body.get("goal") or b.get("goal"), body.get("url") or b.get("start_url"))
    return {"ok": True}


@route("POST", r"/api/bots/(\d+)/run")
def run(E, h, q, body, bid):
    bot_or_404(E, bid)
    r = E.run(int(bid), body.get("skill"), wait=bool(body.get("wait")), reason=body.get("reason", "manual"))
    return {"run": r} if isinstance(r, dict) else {"ok": True}


@route("POST", r"/api/bots/(\d+)/control")
def control(E, h, q, body, bid):
    bot_or_404(E, bid)
    return {"bot": E.control(int(bid), body.get("cmd"), value=body.get("value"), reason=body.get("reason"))}


@route("POST", r"/api/bots/(\d+)/input")
def user_input(E, h, q, body, bid):
    bot_or_404(E, bid)
    kind = body.pop("kind")
    return {"result": E.user_input(int(bid), kind, **{k: body[k] for k in ("x", "y", "text", "key") if k in body})}


@route("POST", r"/api/bots/(\d+)/show/done")
def show_done(E, h, q, body, bid):
    return {"shown": E.finish_show(int(bid))}


@route("GET", r"/api/bots/(\d+)/results")
def results(E, h, q, body, bid):
    bot_or_404(E, bid)
    rows = E.store.find("results", bot_id=int(bid), limit=int(q.get("limit", 300)))
    return {"results": [{k: v for k, v in r.items() if k not in ("bot_id", "status", "key")} for r in rows]}


@route("GET", r"/api/bots/(\d+)/export")
def export(E, h, q, body, bid):
    bot_or_404(E, bid)
    return transfer.export_bot(E, int(bid))


@route("POST", "/api/import")
def import_(E, h, q, body):
    bid = transfer.import_bot(E, body)
    return {"bot": E.bot_view(E.store.get("bots", bid))}


@route("POST", r"/api/bots/(\d+)/move")
def move(E, h, q, body, bid):
    bot_or_404(E, bid)

    def go():
        try:
            transfer.move_bot(E, int(bid), int(body["computer"]),
                              progress=lambda step, **kw: E.bus.publish("move", bot=int(bid), step=step, **kw))
        except Exception as e:
            E.bus.publish("move", bot=int(bid), step="failed", text=str(e))
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True}


# ------------------------------------------------------------------ skills
@route("GET", r"/api/skills/(\d+)")
def skill(E, h, q, body, sid):
    return {"skill": E.store.get("skills", int(sid))}


@route("PATCH", r"/api/skills/(\d+)")
def patch_skill(E, h, q, body, sid):
    return {"skill": E.store.update("skills", int(sid), **{k: v for k, v in body.items() if k in ("name", "steps", "max_pages", "start_url")})}


@route("DELETE", r"/api/skills/(\d+)")
def delete_skill(E, h, q, body, sid):
    E.store.delete("skills", int(sid))
    return {"ok": True}


@route("GET", r"/api/skills/(\d+)/export")
def export_skill(E, h, q, body, sid):
    s = E.store.get("skills", int(sid))
    if q.get("format") == "n8n":
        port = h.server.server_port
        return {"name": f"Inky · {s['name']}", "nodes": [
            {"parameters": {"rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}}, "name": "Every 15 minutes",
             "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0], "id": "t1"},
            {"parameters": {"method": "POST", "url": f"http://127.0.0.1:{port}/api/bots/{s['bot_id']}/run",
                            "sendHeaders": True, "headerParameters": {"parameters": [{"name": "X-Inky-Token", "value": "={{$env.INKY_TOKEN}}"}]},
                            "sendBody": True, "specifyBody": "json", "jsonBody": json.dumps({"skill": s["id"], "wait": True})},
             "name": f"Run {s['name']} (no AI)", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [260, 0], "id": "r1"}],
                "connections": {"Every 15 minutes": {"main": [[{"node": f"Run {s['name']} (no AI)", "type": "main", "index": 0}]]}},
                "settings": {}}
    return {"inky_skill": 1, **{k: s[k] for k in ("name", "site", "goal", "start_url", "steps", "version", "max_pages") if k in s}}


@route("POST", r"/api/bots/(\d+)/skills/import")
def import_skill(E, h, q, body, bid):
    if body.get("inky_skill") != 1:
        raise HTTPError(400, "not an Inky skill file")
    s = {k: body[k] for k in ("name", "site", "goal", "start_url", "steps", "version", "max_pages") if k in body}
    sid = E.store.insert("skills", s, bot_id=int(bid), status="ok")
    return {"skill": E.store.get("skills", sid)}


# ------------------------------------------------------------------ needs, activity
@route("GET", "/api/needs")
def needs(E, h, q, body):
    names = {b["id"]: b["name"] for b in E.store.find("bots")}
    rows = E.store.find("needs", status=q.get("status", "open"), limit=100)
    return {"needs": [dict(n, bot=names.get(n["bot_id"])) for n in rows]}


@route("POST", r"/api/needs/(\d+)")
def answer(E, h, q, body, nid):
    return {"need": E.resolve(int(nid), body.get("decision"))}


@route("GET", "/api/activity")
def activity(E, h, q, body):
    names = {b["id"]: b["name"] for b in E.store.find("bots")}
    ev = [dict(e, bot=names.get(e["bot_id"])) for e in E.store.find("events", limit=400) if e.get("kind") != "ai"][:150]
    runs = [dict(r, bot=names.get(r["bot_id"])) for r in E.store.find("runs", limit=300)]
    week = time.time() - 7 * 86400
    wk = [r for r in runs if r["ts"] > week]
    steps_if_ai = sum((r.get("pages") or 1) * 10 for r in wk if r.get("kind") == "replay")
    usage = E.store.setting("usage", {})
    return {"events": ev, "runs": runs[:100], "usage": usage,
            "week": {"runs": len(wk), "ai_calls": sum(r.get("ai_calls") or 0 for r in wk), "cost": round(sum(r.get("cost") or 0 for r in wk), 4),
                     "asked": len([n for n in E.store.find("needs", limit=500) if n["ts"] > week]),
                     "if_ai_every_step": steps_if_ai, "results": sum(r.get("items") or 0 for r in wk)}}


# ------------------------------------------------------------------ models and keys
@route("GET", "/api/models")
def models(E, h, q, body):
    return {"roles": E.llm.roles(), "role_labels": ROLES, "providers": E.llm.providers(),
            "usage": E.store.setting("usage", {}), "errors": E.store.setting("provider_errors", {})}


@route("POST", "/api/models/role")
def set_role(E, h, q, body):
    if body.get("provider") not in PROVIDERS or body.get("role") not in ROLES:
        raise HTTPError(400, "unknown provider or role")
    E.llm.set_role(body["role"], body["provider"], body.get("model", "").strip())
    return {"roles": E.llm.roles()}


@route("GET", "/api/models/local")
def local(E, h, q, body):
    st = E.llm.local_status()
    mem = st["hardware"].get("memory_gb")
    running = sum(1 for c in E.computers.values() if c.alive)
    catalog = [("qwen3:8b", 5.2, "Fast. Good at learning sites and understanding you.", "recommended"),
               ("qwen3:30b-a3b", 18.6, "Smarter on hard sites, still quick on Apple silicon.", ""),
               ("gemma3:12b", 8.1, "Good all-round model.", ""),
               ("qwen2.5vl:7b", 6.0, "Reads screenshots. Only needed for apps with nothing readable.", "vision"),
               ("llama3.2:3b", 2.0, "Tiny and quick, for chat only.", ""),
               ("llama3.3:70b", 43.0, "Very capable, very large.", "")]
    have = {m["name"] for m in st["ollama"]["models"]}
    disk = st["hardware"].get("disk_free_gb")
    fit = lambda gb: "not enough disk" if disk is not None and gb + 1 > disk else fits(gb * 2**30, mem, running)
    st["catalog"] = [{"name": n, "gb": gb, "about": a, "badge": b, "installed": n in have or any(x.startswith(n + ":") for x in have),
                      "fit": fit(gb)} for n, gb, a, b in catalog]
    st["pulls"] = E.store.setting("pulls", {})
    return st


@route("POST", "/api/models/pull")
def pull(E, h, q, body):
    name = body["name"]

    def go():
        def prog(p):
            pulls = E.store.setting("pulls", {})
            pulls[name] = {"status": p.get("status"), "completed": p.get("completed"), "total": p.get("total")}
            E.store.set_setting("pulls", pulls)
            E.bus.publish("pull", name=name, **pulls[name])
        try:
            E.llm.pull(name, prog)
        except Exception as e:
            E.bus.publish("pull", name=name, status=f"failed: {e}")
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True}


@route("POST", "/api/models/test")
def test_model(E, h, q, body):
    try:
        return E.llm.test(body["provider"], body["model"])
    except Exception as e:
        return {"ok": False, "reply": str(e)[:200]}


@route("POST", "/api/models/custom")
def custom(E, h, q, body):
    E.store.set_setting("custom_provider", {"base": body["base"].strip()})
    return {"ok": True}


@route("GET", "/api/keys")
def keys(E, h, q, body):
    spend = E.store.setting("key_limits", {})
    return {"keys": [{"provider": p["name"], "label": p["label"], "source": p["key"], "limit": spend.get(p["name"])}
                     for p in E.llm.providers() if not p["local"] or p["name"] == "custom"] +
                    [{"provider": "telegram", "label": "Telegram bot", "source": E.keys.source("telegram")}],
            "backend": E.keys.backend}


@route("POST", "/api/keys")
def set_key(E, h, q, body):
    prov = body.get("provider")
    if prov not in PROVIDERS and prov != "telegram":
        raise HTTPError(400, "unknown provider")
    E.keys.set(prov, body.get("key", ""))
    if body.get("limit") is not None:
        lim = E.store.setting("key_limits", {})
        lim[prov] = body["limit"]
        E.store.set_setting("key_limits", lim)
    return {"ok": True, "source": E.keys.source(prov)}


@route("DELETE", r"/api/keys/(\w+)")
def del_key(E, h, q, body, prov):
    E.keys.delete(prov)
    return {"ok": True, "source": E.keys.source(prov)}


# ------------------------------------------------------------------ connectors (MCP)
@route("GET", "/api/mcp")
def mcp(E, h, q, body):
    return {"servers": E.mcp.servers()}


@route("POST", "/api/mcp")
def mcp_save(E, h, q, body):
    name = re.sub(r"[^a-z0-9-]", "-", (body.get("name") or "").lower()).strip("-")
    if not name:
        raise HTTPError(400, "a name is needed")
    cmd = body.get("command")
    if isinstance(cmd, str):
        cmd = cmd.split()
    E.mcp.save(name, command=cmd, enabled=body.get("enabled", True), label=body.get("label"), env=body.get("env"))
    return {"servers": E.mcp.servers()}


@route("POST", r"/api/mcp/([\w-]+)/connect")
def mcp_connect(E, h, q, body, name):
    E.mcp.save(name, enabled=True)
    tools = E.mcp.tools(name)
    return {"tools": [{"name": t["name"], "description": (t.get("description") or "")[:300],
                       "params": list((t.get("inputSchema") or {}).get("properties", {}).keys())} for t in tools],
            "server": E.mcp.clients[name].server_info}


@route("POST", r"/api/mcp/([\w-]+)/disconnect")
def mcp_disconnect(E, h, q, body, name):
    E.mcp.disconnect(name)
    E.mcp.save(name, enabled=False)
    return {"ok": True}


@route("POST", r"/api/mcp/([\w-]+)/call")
def mcp_call(E, h, q, body, name):
    r = E.mcp.call(name, body["tool"], body.get("args") or {}, timeout=int(body.get("timeout", 600)))
    return {"text": r["text"][:20000], "error": r["error"]}


@route("DELETE", r"/api/mcp/([\w-]+)")
def mcp_remove(E, h, q, body, name):
    if name in PRESETS:
        raise HTTPError(400, "built-in connectors can only be turned off")
    E.mcp.remove(name)
    return {"ok": True}


@route("GET", "/api/mcp/inky-config")
def inky_config(E, h, q, body):
    py = os.sys.executable
    env = {"INKY_HOME": str(E.home), "INKY_URL": f"http://127.0.0.1:{h.server.server_port}",
           "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    return {"claude": {"mcpServers": {"inky": {"command": py, "args": ["-m", "inky.mcp_server"], "env": env}}},
            "claude_cli": f"claude mcp add inky -e INKY_HOME={env['INKY_HOME']} -e INKY_URL={env['INKY_URL']} -e PYTHONPATH={env['PYTHONPATH']} -- {py} -m inky.mcp_server",
            "codex_toml": f'[mcp_servers.inky]\ncommand = "{py}"\nargs = ["-m", "inky.mcp_server"]\nenv = {{ INKY_HOME = "{env["INKY_HOME"]}", INKY_URL = "{env["INKY_URL"]}", PYTHONPATH = "{env["PYTHONPATH"]}" }}'}


# ------------------------------------------------------------------ computers, settings, health
@route("GET", "/api/computers")
def computers(E, h, q, body):
    bots_ = E.bots()
    local = {"id": "local", "name": E.store.setting("engine_name", os.uname().nodename), "kind": "local", "ok": True,
             "bots": [b for b in bots_ if (b.get("computer") or "local") == "local"], "docker": health.docker()}
    out = [local]
    for c in E.store.find("computers", desc=False):
        try:
            info = transfer.Remote(c["url"], c["token"]).req("GET", "/api/bots", timeout=4)
            ok, rbots = True, info["bots"]
        except Exception:
            ok, rbots = False, []
        out.append({"id": c["id"], "name": c["name"], "url": c["url"], "kind": "remote", "ok": ok, "bots": rbots})
    return {"computers": out, "pair_code": transfer.pair_code(E.token)}


@route("POST", "/api/computers")
def add_computer(E, h, q, body):
    token, name = transfer.pair(body["url"], body["code"])
    cid = E.store.insert("computers", {"name": body.get("name") or name, "url": body["url"].rstrip("/"), "token": token})
    return {"id": cid}


@route("DELETE", r"/api/computers/(\d+)")
def del_computer(E, h, q, body, cid):
    E.store.delete("computers", int(cid))
    return {"ok": True}


def settings_view(E):
    d = {"setup_done": False, "engine_name": os.uname().nodename, "notify_app": True, "screen_allowed": False}
    d.update(E.store.setting("app", {}))
    d["data_folder"] = str(E.home)
    d["telegram"] = E.store.setting("telegram", {"enabled": False})
    return d


@route("GET", "/api/settings")
def settings(E, h, q, body):
    return settings_view(E)


@route("POST", "/api/settings")
def save_settings(E, h, q, body):
    app = E.store.setting("app", {})
    tg = body.pop("telegram", None)
    app.update(body)
    E.store.set_setting("app", app)
    if "setup_done" in body:
        E.store.set_setting("setup_done", bool(body["setup_done"]))
    if "engine_name" in body:
        E.store.set_setting("engine_name", body["engine_name"])
    if tg is not None:
        E.store.set_setting("telegram", {**E.store.setting("telegram", {}), **tg})
    return settings_view(E)


@route("GET", "/api/health")
def health_(E, h, q, body):
    return {"health": health.check(E)}


@route("GET", "/api/setup")
def setup(E, h, q, body):
    import platform
    import shutil
    st = E.llm.local_status()
    return {"platform": platform.system(), "docker": health.docker(), "ollama": st["ollama"], "hardware": st["hardware"],
            "keys": {p["name"]: p["key"] for p in E.llm.providers() if not p["local"]}, "roles": E.llm.roles(),
            "claude": bool(shutil.which("claude")), "codex": bool(shutil.which("codex")),
            "telegram": E.store.setting("telegram", {"enabled": False}), "pair_code": transfer.pair_code(E.token)}


@route("POST", "/api/telegram/test")
def telegram_test(E, h, q, body):
    tg = E.store.setting("telegram", {})
    token = E.keys.get("telegram")
    if not token:
        raise HTTPError(400, "paste the bot token first")
    r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15).json()
    return {"ok": r.get("ok", False), "bot": (r.get("result") or {}).get("username"), "chat_id": tg.get("chat_id")}


# ------------------------------------------------------------------ handler
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    engine = None

    def log_message(self, *a):
        pass

    def _send(self, status, data, ctype="application/json", extra=None):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _authed(self, q):
        return self.headers.get("X-Inky-Token") == self.engine.token or q.get("t") == self.engine.token

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PATCH(self):
        self._handle("PATCH")

    def do_DELETE(self):
        self._handle("DELETE")

    def _handle(self, method):
        E = self.engine
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        path = u.path
        if not path.startswith("/api/"):
            return self._static(path)
        if path not in ("/api/ping", "/api/pair") and not self._authed(q):
            return self._send(401, {"error": "missing token"})
        m = re.match(r"^/api/bots/(\d+)/screen\.(mjpg|jpg)$", path)
        if m:
            return self._screen(int(m.group(1)), m.group(2))
        if path == "/api/events":
            return self._sse()
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad JSON"})
        proxied = self._proxy(method, path, body)
        if proxied is not None:
            return
        for meth, rx, fn in ROUTES:
            mm = rx.match(path)
            if meth == method and mm:
                try:
                    return self._send(200, fn(E, self, q, body, *mm.groups()))
                except HTTPError as e:
                    return self._send(e.status, {"error": str(e)})
                except (KeyError, ValueError, RuntimeError) as e:
                    return self._send(400, {"error": str(e)})
                except Exception as e:
                    traceback.print_exc()
                    return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        return self._send(404, {"error": "not found"})

    def _proxy(self, method, path, body):
        """Bots that moved to another engine: forward their calls there."""
        m = re.match(r"^/api/bots/(\d+)(/.*)?$", path)
        if not m or path.endswith("/move"):
            return None
        b = self.engine.store.get("bots", int(m.group(1)))
        if not b or not b.get("remote_id") or (b.get("computer") or "local") == "local":
            return None
        c = self.engine.store.get("computers", int(b["computer"]))
        if not c:
            return None
        rpath = f"/api/bots/{b['remote_id']}{m.group(2) or ''}"
        try:
            r = httpx.request(method, c["url"] + rpath, json=body if method != "GET" else None,
                              headers={"X-Inky-Token": c["token"]}, timeout=300)
            data = r.json()
            if isinstance(data, dict) and isinstance(data.get("bot"), dict):
                data["bot"].update(id=b["id"], computer=b["computer"], remote=c["name"])
            self._send(r.status_code, data)
        except Exception as e:
            self._send(502, {"error": f"can’t reach {c['name']}: {e}"})
        return True

    def _static(self, path):
        if path in ("/", "/index.html"):
            html = (UI / "index.html").read_text().replace("__INKY_TOKEN__", self.engine.token)
            return self._send(200, html.encode(), TYPES[".html"])
        f = (UI / path.lstrip("/")).resolve()
        if UI.resolve() not in f.parents or not f.is_file():
            return self._send(404, b"not found", "text/plain")
        return self._send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))

    def _screen(self, bid, kind):
        E = self.engine
        b = E.store.get("bots", bid)
        if b and b.get("remote_id") and (b.get("computer") or "local") != "local":
            c = E.store.get("computers", int(b["computer"]))
            r = httpx.get(f"{c['url']}/api/bots/{b['remote_id']}/screen.jpg", headers={"X-Inky-Token": c["token"]}, timeout=20)
            return self._send(r.status_code, r.content, "image/jpeg")
        comp = E.computers.get(bid)
        if not (comp and comp.alive):
            if b and b.get("mode") == "screen":  # never open a window on your screen just to show it here
                return self._send(204, b"", "image/jpeg")
            try:
                comp = E.computer(bid)
            except Exception as e:
                return self._send(503, {"error": str(e)})
        if kind == "jpg":
            return self._send(200, comp.frame or b"", "image/jpeg")
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        last = None
        try:
            end = time.time() + 3600
            while time.time() < end and comp.alive:
                frame = comp.wait_frame(last, 2.0)
                if frame is None:
                    continue
                if frame is last:
                    frame = comp.frame  # resend so proxies and players keep the connection
                last = frame
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def _sse(self):
        E = self.engine
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        q = E.bus.subscribe()
        try:
            self.wfile.write(b": hello\n\n")
            self.wfile.flush()
            while True:
                try:
                    msg = q.get(timeout=15)
                    self.wfile.write(f"data: {json.dumps(msg, ensure_ascii=False, default=str)}\n\n".encode())
                except Exception:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            E.bus.unsubscribe(q)
        self.close_connection = True


def serve(engine, host="127.0.0.1", port=8800):
    srv = ThreadingHTTPServer((host, port), type("EngineHandler", (Handler,), {"engine": engine}))
    srv.daemon_threads = True
    return srv
