"""HTTP API + static UI. Every /api call needs the X-Inky-Token header (or ?t= for images and SSE),
so other websites open in your browser can't drive your bots."""
import hmac
import itertools
import json
import os
import platform
import re
import sys
import threading
import time
import traceback
from datetime import datetime
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from inky import connect, connectors, health, insights, library, transfer
from inky import skills as skills_mod
from inky.llm import PROVIDERS, ROLES, fits, plain as llm_plain
from inky.mcp import PRESETS

UI = Path(__file__).parent / "ui"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
         ".png": "image/png", ".json": "application/json", ".webmanifest": "application/manifest+json", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8"}
class Server(ThreadingHTTPServer):
    """HTTPServer looks up this computer's full name when it starts (getfqdn: a multicast-DNS lookup). macOS holds that
    lookup for about 30 s the first time a new app touches the local network, so a first launch sat on "Waking up your
    bots". Nothing here uses that name."""

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = str(self.server_address[0]), self.server_address[1]

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return  # a page closed or a client went quiet: not worth a traceback in the log
        super().handle_error(request, client_address)


# The app's page loads only its own scripts and fonts. Pictures of what bots found come from the sites themselves (img-src),
# and the desktop app talks to its shell over ipc:.
MAX_BODY = 16_000_000  # a move with its sign-ins, chat and history fits; a shared bot file is far smaller
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https: http:; font-src 'self'; "
       "connect-src 'self' ipc: http://ipc.localhost; media-src 'self' blob: data:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
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
    return {"ok": True, "name": E.store.setting("engine_name", platform.node()), "time": time.time(), "os": platform.system(),
            "id": transfer.engine_id(E)}


PAIR_TRIES = []


@route("POST", "/api/pair")
def pair_route(E, h, q, body):
    """Wrong codes are limited per address (5 a minute) and overall (60 a minute), so one device can't lock out the rest."""
    now, ip = time.time(), h.client_address[0] if h else "?"
    PAIR_TRIES[:] = [(t, a) for t, a in PAIR_TRIES if now - t < 60]
    if sum(1 for _, a in PAIR_TRIES if a == ip) >= 5 or len(PAIR_TRIES) >= 60:
        raise HTTPError(429, "too many tries, wait a minute")
    if (body.get("code") or "").upper() != transfer.pair_code(E.token):
        PAIR_TRIES.append((now, ip))
        raise HTTPError(403, "wrong code")
    return {"token": E.token, "name": E.store.setting("engine_name", platform.node())}


@route("GET", "/api/state")
def state(E, h, q, body):
    usage = E.store.setting("usage", {})
    today = usage.get(datetime.now().strftime("%Y-%m-%d"), {"calls": 0, "tokens": 0, "cost": 0})
    return {"bots": bots_here(E), "needs": len(E.store.find("needs", status="open")) + len(REMOTE_NEEDS["rows"]), "setup_done": E.store.setting("setup_done", False),
            "settings": settings_view(E), "today": today, "pair_code": transfer.pair_code(E.token),
            "engine": E.store.setting("engine_name", platform.node()), "engine_id": transfer.engine_id(E), "thinking": thinking(E)}


@route("GET", "/api/bots")
def bots(E, h, q, body):
    return {"bots": bots_here(E)}


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
            "needs": E.store.find("needs", bot_id=bid, status="open"),
            "growth": E.growth_view(bid), "diary": E.store.find("diary", bot_id=bid, limit=30)}


@route("PATCH", r"/api/bots/(\d+)")
def patch_bot(E, h, q, body, bid):
    bot_or_404(E, bid)
    return {"bot": E.update_bot(int(bid), body)}


@route("DELETE", r"/api/bots/(\d+)")
def delete_bot(E, h, q, body, bid):
    b = bot_or_404(E, bid)
    c = E.store.get("computers", int(b["computer"])) if b.get("remote_id") and str(b.get("computer") or "local") != "local" else None
    if c and q.get("here") != "1":  # it lives on another computer: delete it there too (directly, never through another forward)
        try:
            r = httpx.delete(f"{c['url']}/api/bots/{b['remote_id']}", headers=fwd_headers(E, c, b), timeout=transfer.connect_timeout(30))
            ok = r.status_code < 300 or r.status_code == 404  # 404: it's already gone there (or that id is someone else's now)
        except httpx.HTTPError:
            ok = False
        if not ok:
            raise HTTPError(409, f"{c['name']} isn’t answering, so {b['name']} is still there. Try again when it’s on, or remove it only here.")
    E.delete_bot(int(bid))
    forget_remote_needs(bid)
    return {"ok": True}


@route("POST", r"/api/bots/(\d+)/bring-back")
def bring_back(E, h, q, body, bid):
    bot_or_404(E, bid)

    def go():
        try:
            transfer.bring_back(E, int(bid), progress=lambda step, **kw: E.bus.publish("move", bot=int(bid), step=step, **kw))
            forget_remote_needs(bid)
        except httpx.HTTPStatusError as e:
            b = E.store.get("bots", int(bid)) or {}
            E.bus.publish("move", bot=int(bid), step="failed", text=f"{b.get('name', 'It')} is no longer there. Remove it here from its page." if e.response.status_code in (404, 410) else f"The other computer answered {e.response.status_code}.")
        except httpx.RequestError:
            b = E.store.get("bots", int(bid)) or {}
            c = E.store.get("computers", int(b["computer"])) if str(b.get("computer", "")).isdigit() else None
            E.bus.publish("move", bot=int(bid), step="failed", text=f"{c['name'] if c else 'The other computer'} isn’t answering. It can only pack up while it’s on.")
        except Exception as e:
            E.bus.publish("move", bot=int(bid), step="failed", text=str(e)[:200])
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True}


@route("POST", r"/api/bots/(\d+)/chat")
def chat(E, h, q, body, bid):
    bot_or_404(E, bid)
    return E.chat(int(bid), body.get("text", ""), source=body.get("source", "app"))


@route("POST", "/api/retry")
def retry_now(E, h, q, body):
    """Try now what the bots would try again later on their own."""
    return {"started": E.retry_now(body.get("bot"))}


@route("POST", r"/api/bots/(\d+)/learn")
def learn(E, h, q, body, bid):
    b = bot_or_404(E, bid)
    E.learn(int(bid), body.get("goal") or b.get("goal"), body.get("url") or b.get("start_url"))
    return {"ok": True}


@route("POST", r"/api/bots/(\d+)/run")
def run(E, h, q, body, bid):
    bot_or_404(E, bid)
    r = E.run(int(bid), body.get("skill"), wait=bool(body.get("wait")), reason=body.get("reason", "manual"),
              check=bool(body.get("check")), timeout=min(int(body.get("timeout") or 900), 900))
    return {"run": r} if isinstance(r, dict) else {"ok": True}


@route("POST", r"/api/bots/(\d+)/control")
def control(E, h, q, body, bid):
    bot_or_404(E, bid)
    return {"bot": E.control(int(bid), body.get("cmd"), value=body.get("value"), reason=body.get("reason"))}


@route("POST", r"/api/bots/(\d+)/input")
def user_input(E, h, q, body, bid):
    bot_or_404(E, bid)
    kind = body.pop("kind")
    if kind == "goto" and not skills_mod.web_address(body.get("text"), ""):
        raise HTTPError(400, "That isn’t a web address. It looks like example.com or 192.168.1.20:8800.")
    try:
        return {"result": E.user_input(int(bid), kind, **{k: body[k] for k in ("x", "y", "text", "key") if k in body})}
    except Exception as e:
        from inky.bots import plain_error
        raise HTTPError(400, plain_error(e))


@route("POST", r"/api/bots/(\d+)/show/done")
def show_done(E, h, q, body, bid):
    return {"shown": E.finish_show(int(bid))}


@route("GET", r"/api/bots/(\d+)/results")
def results(E, h, q, body, bid):
    bot_or_404(E, bid)
    b = bot_or_404(E, bid)
    rows = E.store.find("results", bot_id=int(bid), limit=int(q.get("limit", 300)))
    hidden = ("id", "bot_id", "status", "key", "ts", "passed", "new", "run", "skill")
    passes = lambda r: skills_mod.apply_filters([{k: v for k, v in r.items() if k not in hidden}], b.get("filters"))
    if not q.get("all"):  # your rules as they are now (they may have changed since the run); near-misses stay for suggestions
        rows = [r for r in rows if passes(r)]
    return {"results": [{k: v for k, v in r.items() if k not in ("bot_id", "status", "key", "passed")} for r in rows],
            "unchecked": skills_mod.unchecked(rows, b.get("filters"))}


@route("POST", r"/api/bots/(\d+)/apply")
def apply_chip(E, h, q, body, bid):
    bot_or_404(E, bid)
    if "offer" in body:  # a button the bot offered in chat: what that very message offered, once
        text = E.take_offer(int(bid), body.get("message"), body.get("offer"))
        E._say(int(bid), text if isinstance(text, str) and text[:1].isupper() else f"Done: {text}.")
        return {"bot": E.bot_view(E.store.get("bots", int(bid)))}
    return {"bot": E.apply_chip(int(bid), body.get("apply"), body.get("message"))}


@route("GET", "/api/setup/browser")
def browser_status(E, h, q, body):
    return {"ready": health.browser_ready()}


@route("POST", "/api/setup/browser")
def browser_install(E, h, q, body):
    def go():
        try:
            ok = health.install_browser(lambda line: E.bus.publish("browser", line=line, done=False))
        except Exception as e:
            E.bus.publish("browser", line=str(e), done=True, ok=False)
            return
        E.bus.publish("browser", line="Done." if ok else "It didn’t work.", done=True, ok=ok and health.browser_ready())
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True}


@route("GET", "/api/team")
def team(E, h, q, body):
    return {"feed": E.team_feed(int(q.get("limit", 100)))}


@route("GET", "/api/recap")
def recap(E, h, q, body):
    return {"recap": insights.recap(E.store, float(q.get("since") or 0))}


@route("GET", r"/api/bots/(\d+)/export")
def export(E, h, q, body, bid):
    bot_or_404(E, bid)
    return transfer.export_bot(E, int(bid), private=q.get("private") == "1")  # private: a move between your own computers


@route("POST", "/api/import")
def import_(E, h, q, body):
    """?move=1: a move from one of your paired computers (keeps its sign-ins and chat). Anything else is a file someone
    gave you: the same checks, fence and fresh start as a shared agent."""
    try:
        bid = transfer.import_bot(E, body, move=True) if q.get("move") else library.install(E, body, file=True)
    except ValueError as e:
        raise HTTPError(400, str(e))
    return {"bot": E.bot_view(E.store.get("bots", bid))}


@route("POST", r"/api/bots/(\d+)/move")
def move(E, h, q, body, bid):
    bot_or_404(E, bid)
    c = E.store.get("computers", int(body.get("computer") or 0)) if str(body.get("computer") or "").isdigit() else None
    if not c:
        raise HTTPError(400, "Pick a paired computer to move it to.")

    def go():
        try:
            transfer.move_bot(E, int(bid), int(body["computer"]),
                              progress=lambda step, **kw: E.bus.publish("move", bot=int(bid), step=step, **kw))
        except Exception as e:
            why = "Nothing changed: it’s still here, and nothing was left there." if str(e) == "check_failed" else \
                (f"{c['name']} isn’t answering. Try again when it’s on." if isinstance(e, httpx.RequestError) else str(e)[:200])
            E.bus.publish("move", bot=int(bid), step="failed", text=why)
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True}


# ------------------------------------------------------------------ skills
# a bot's skills through the bot, so a moved bot's skills are changed on its own computer
def _own_skill(E, bid, sid):
    s = E.store.get("skills", int(sid))
    if not s or s.get("bot_id") != int(bid):
        raise HTTPError(404, "That site is gone: it was forgotten.")
    return s


@route("GET", r"/api/bots/(\d+)/skills/(\d+)")
def bot_skill(E, h, q, body, bid, sid):
    return {"skill": _own_skill(E, bid, sid)}


@route("PATCH", r"/api/bots/(\d+)/skills/(\d+)")
def bot_patch_skill(E, h, q, body, bid, sid):
    _own_skill(E, bid, sid)
    return patch_skill(E, h, q, body, sid)


@route("DELETE", r"/api/bots/(\d+)/skills/(\d+)")
def bot_delete_skill(E, h, q, body, bid, sid):
    _own_skill(E, bid, sid)
    return delete_skill(E, h, q, body, sid)


@route("GET", r"/api/bots/(\d+)/skills/(\d+)/export")
def bot_export_skill(E, h, q, body, bid, sid):
    _own_skill(E, bid, sid)
    return export_skill(E, h, q, body, sid)


@route("GET", r"/api/skills/(\d+)")
def skill(E, h, q, body, sid):
    return {"skill": E.store.get("skills", int(sid))}


def bad_goto(steps, start):
    """Every “go to” in a site file is a web address: never a file on this computer or anything that isn't http(s)."""
    bad = next((st.get("value") for st in steps if st.get("action") == "goto" and not skills_mod.web_address(st.get("value"), start or "")), None)
    if bad is not None:
        raise HTTPError(400, f"A step opens “{str(bad)[:60]}”, which isn’t a web address.")


@route("PATCH", r"/api/skills/(\d+)")
def patch_skill(E, h, q, body, sid):
    was = E.store.get("skills", int(sid))
    if not was:
        raise HTTPError(404, "That site is gone: it was forgotten.")
    patch = {k: v for k, v in body.items() if k in ("name", "steps", "max_pages", "start_url")}
    if "steps" in patch:
        ok = {"click", "fill", "select", "press", "goto", "extract", "wait"}
        if not isinstance(patch["steps"], list) or not patch["steps"] or not all(isinstance(st, dict) and st.get("action") in ok for st in patch["steps"]):
            raise HTTPError(400, "It needs at least one step.")
        bad_goto(patch["steps"], patch.get("start_url") or was.get("start_url"))
        if patch["steps"] != was.get("steps"):  # removing a step or "ask again" is a new version, like Show me once
            patch["version"] = (was.get("version") or 1) + 1
    if "name" in patch:
        patch["name"] = str(patch["name"]).strip()[:60] or "Skill"
    if "start_url" in patch and not skills_mod.web_address(patch["start_url"], ""):
        raise HTTPError(400, "That isn’t a web address.")
    if "max_pages" in patch:
        patch["max_pages"] = max(1, min(int(patch["max_pages"] or 1), 20))
    return {"skill": E.store.update("skills", int(sid), **patch)}


@route("DELETE", r"/api/skills/(\d+)")
def delete_skill(E, h, q, body, sid):
    E.store.delete("skills", int(sid))
    return {"ok": True}


@route("GET", r"/api/skills/(\d+)/export")
def export_skill(E, h, q, body, sid):
    s = E.store.get("skills", int(sid))
    if q.get("format") == "n8n":
        return connectors.n8n_workflow(s, f"http://127.0.0.1:{h.server.server_port}")
    return {"inky_skill": 1, **{k: s[k] for k in ("name", "site", "goal", "start_url", "steps", "version", "max_pages") if k in s}}


@route("POST", r"/api/bots/(\d+)/skills/import")
def import_skill(E, h, q, body, bid):
    bot_or_404(E, bid)
    if not isinstance(body, dict) or body.get("inky_skill") != 1:
        raise HTTPError(400, "That isn’t an Inky file." + (" It’s a bot file: import it on Your bots." if isinstance(body, dict) and body.get("bundle") else ""))
    steps = body.get("steps")
    ok = {"click", "fill", "select", "press", "goto", "extract", "wait"}
    if not isinstance(steps, list) or not steps or not all(isinstance(st, dict) and st.get("action") in ok for st in steps):
        raise HTTPError(400, "That file has no steps Inky can run.")
    if not skills_mod.web_address(body.get("start_url"), ""):
        raise HTTPError(400, "That file has no web address to start on.")
    bad_goto(steps, body.get("start_url"))
    s = {k: body[k] for k in ("name", "site", "goal", "start_url", "version", "max_pages") if k in body}
    s["name"] = (str(s.get("name") or "Imported skill").strip() or "Imported skill")[:60]
    if "max_pages" in s:  # a file can't make it read a billion pages
        s["max_pages"] = max(1, min(int(s["max_pages"]) if str(s["max_pages"]).isdigit() else 3, 20))
    s["steps"] = [{k: v for k, v in st.items() if k != "approved_always"} for st in steps]  # someone else's yes isn't yours: it asks again
    sid = E.store.insert("skills", s, bot_id=int(bid), status="ok")
    E.bus.publish("bots")  # the sidebar stops saying it hasn't learned yet
    return {"skill": E.store.get("skills", sid)}


# ------------------------------------------------------------------ needs, activity
REMOTE_NEEDS = {"at": 0, "rows": []}


def bots_here(E):
    """Your bots; one that moved says where it runs and how many of its questions wait for you there."""
    names = {c["id"]: c["name"] for c in E.store.find("computers")}
    rows = E.bots()
    for b in rows:
        if b["status"] == "moved":
            b["remote"] = names.get(int(b["computer"])) if str(b.get("computer")).isdigit() else None
            b["needs"] = sum(1 for n in REMOTE_NEEDS["rows"] if n.get("bot_id") == b["id"])
            b["need_kind"] = next((("decision" if n.get("kind") == "decision" else "problem") for n in REMOTE_NEEDS["rows"] if n.get("bot_id") == b["id"]), None)
    return rows


def forget_remote_needs(bid):
    REMOTE_NEEDS["rows"] = [n for n in REMOTE_NEEDS["rows"] if n.get("bot_id") != int(bid)]


def fwd_headers(E, c, b):
    """Headers for a call to a moved bot's computer: its token, forwarded once, and which bot this really is."""
    return {"X-Inky-Token": c["token"], "X-Inky-Forwarded": "1", "X-Inky-Home": transfer.home_of(E, b)}


def remote_needs(E, retry_down=False):
    """Open questions from your bots that moved to another computer: one request per server, in parallel, every 15 s at most.
    A server that didn't answer is skipped for a minute (its questions can't be answered anyway); the watcher keeps trying it."""
    if time.time() - REMOTE_NEEDS["at"] < 15:
        return REMOTE_NEEDS["rows"]
    down = REMOTE_NEEDS.setdefault("down", {})
    moved = {}
    for b in E.store.find("bots"):
        if b.get("status") == "moved" and b.get("remote_id") and str(b.get("computer")).isdigit():
            moved.setdefault(int(b["computer"]), []).append(b)

    def ask(cid):
        c = E.store.get("computers", cid)
        if not c or (not retry_down and time.time() - down.get(cid, 0) < 60):
            return []
        try:
            got = transfer.Remote(c["url"], c["token"]).req("GET", f"/api/needs?home={transfer.engine_id(E)}", timeout=4)["needs"]
            down.pop(cid, None)
        except httpx.HTTPError:
            down[cid] = time.time()
            return []
        except Exception:
            return []
        mine = {(b["remote_id"], transfer.home_of(E, b)): b for b in moved[cid]}
        return [dict(n, bot_id=mine[k]["id"], bot=mine[k]["name"], remote=c["name"]) for n in got
                if (k := (n.get("bot_id"), n.get("home"))) in mine]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max(1, min(8, len(moved)))) as ex:
        rows = [n for got in ex.map(ask, moved) for n in got] if moved else []
    before = len(REMOTE_NEEDS["rows"])
    REMOTE_NEEDS.update(at=time.time(), rows=rows)
    if len(rows) != before:  # the badge and Needs you follow along without opening the page
        E.bus.publish("needs")
    return rows


def watch_remote_needs(E):
    def loop():
        while True:
            time.sleep(15)
            try:
                REMOTE_NEEDS["at"] = 0  # with no moved bots this asks no one and clears the list (the badge stays right)
                remote_needs(E, retry_down=True)
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True, name="remote-needs").start()


@route("GET", "/api/needs")
def needs(E, h, q, body):
    bots = {b["id"]: b for b in E.store.find("bots")}
    rows = [dict(n, bot=(bots.get(n["bot_id"]) or {}).get("name")) for n in E.store.find("needs", status=q.get("status", "open"), limit=100)]
    if q.get("home"):  # another computer asking about the bots it sent here: only those, by who they are, never forwarded on
        return {"needs": [dict(n, home=transfer.home_of(E, bots[n["bot_id"]])) for n in rows
                          if n["bot_id"] in bots and (bots[n["bot_id"]].get("home") or {}).get("engine") == q["home"]]}
    if q.get("status", "open") == "open":
        rows = sorted(rows + remote_needs(E), key=lambda n: n.get("ts") or 0, reverse=True)  # newest first, wherever the bot runs
    handled = [dict(e, bot=(bots.get(e["bot_id"]) or {}).get("name")) for e in E.store.find("events", status="handled", limit=30)
               if e.get("ts", 0) > time.time() - 3 * 86400 and e["bot_id"] in bots]  # what bots sorted out themselves lately
    return {"needs": rows, "handled": handled[:15]}


@route("POST", r"/api/bots/(\d+)/needs/(\d+)")
def answer_for_bot(E, h, q, body, bid, nid):
    """Answering from a bot's page: forwarded with the bot when it moved, and only ever that bot's question."""
    try:
        return {"need": E.resolve(int(nid), body.get("decision"), bot_id=int(bid))}
    except KeyError:
        raise HTTPError(404, "That question is gone.")
    except ValueError as e:
        raise HTTPError(409, str(e))


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
                     "asked": len([n for n in E.store.find("needs", limit=500) if n["ts"] > week and n.get("kind") == "decision"]),
                     "if_ai_every_step": steps_if_ai, "results": sum(r.get("items") or 0 for r in wk)}}


# ------------------------------------------------------------------ models and keys
@route("GET", "/api/models")
def models(E, h, q, body):
    return {"roles": E.llm.roles(), "role_labels": ROLES, "providers": E.llm.providers(),
            "usage": E.store.setting("usage", {}), "errors": E.store.setting("provider_errors", {})}


def thinking(E):
    """Model calls in progress: which model, for which bot, for how long."""
    names = {b["id"]: b["name"] for b in E.store.find("bots")}
    return [dict(c, bot=c.get("bot_id"), name=names.get(c.get("bot_id"))) for c in E.llm.live_calls()]


@route("GET", "/api/models/live")
def models_live(E, h, q, body):
    return {"thinking": thinking(E), "loaded": E.llm.loaded()}


@route("POST", "/api/models/stop")
def models_stop(E, h, q, body):
    """Stop the model: its calls are cut off, and the runs they were for stop too."""
    bid = body.get("bot")
    bots = {c.get("bot_id") for c in E.llm.live_calls() if bid is None or c.get("bot_id") == bid} - {None}
    for b in bots:
        try:
            E.control(int(b), "stop")
        except Exception:
            pass
    return {"stopped": E.llm.stop(int(bid) if bid is not None else None)}


@route("POST", "/api/models/unload")
def models_unload(E, h, q, body):
    try:
        E.llm.unload(str(body.get("name") or ""))
    except httpx.HTTPError:
        raise HTTPError(502, "Ollama didn’t answer. Is it running?")
    return {"loaded": E.llm.loaded()}


@route("GET", "/api/models/choices")
def model_choices(E, h, q, body):
    """Every model you can use right now, for the one picker: what's on this computer, then each provider you have a key for."""
    from inky.llm import NOT_CHAT, fits
    st = E.llm.local_status()
    mem = st["hardware"].get("memory_gb")
    rows = []
    if st["ollama"]["running"]:
        for m in sorted(st["ollama"]["models"], key=lambda m: -(m.get("size") or 0)):
            if NOT_CHAT.search(m["name"]):
                continue
            gb, fit = round((m.get("size") or 0) / 1e9, 1), fits(m.get("size") or 0, mem)
            rows.append({"provider": "ollama", "model": m["name"], "group": "On this computer", "small": gb < 3,
                         "label": f"{m['name']} · {gb} GB" + (" · too big for this computer’s memory" if fit == "too big" else "")})
    if st["custom"]["reachable"]:
        rows.append({"provider": "custom", "model": None, "group": "On this computer", "label": f"Your own server · {st['custom']['base']}"})
    for p in E.llm.providers():
        if not p["local"] and p["key"]:
            rows.append({"provider": p["name"], "model": None, "group": "With your keys", "label": f"{p['label']} · Inky picks its best model"})
    roles = E.llm.roles()
    same = {(v.get("provider"), v.get("model")) for v in roles.values() if v}
    using = dict(zip(("provider", "model"), next(iter(same)))) if len(same) == 1 else None
    return {"choices": rows, "using": using, "mixed": len(same) > 1, "recommended": E.llm.pick_model("ollama") if st["ollama"]["running"] else None}


@route("POST", "/api/models/role")
def set_role(E, h, q, body):
    prov, model = body.get("provider"), (body.get("model") or "").strip()
    if prov not in PROVIDERS or body.get("role") not in ROLES:
        raise HTTPError(400, "unknown provider or role")
    if not model:
        raise HTTPError(400, "Pick or type a model name first.")
    E.llm.set_role(body["role"], prov, model)
    warn = None if PROVIDERS[prov].get("local") or E.keys.get(prov) else f"There’s no {PROVIDERS[prov]['label']} key yet, so this role won’t work until you add one in API keys."
    if prov == "ollama":
        have = {m["name"] for m in E.llm.local_status()["ollama"]["models"]}
        if have and model not in have and f"{model}:latest" not in have:
            warn = f"Ollama doesn’t have “{model}”. Saved anyway: download it in Models → On this computer, or pick one it has ({', '.join(sorted(have)[:4])})."
    return {"roles": E.llm.roles(), "warning": warn}


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
    fit = lambda gb: "not enough disk" if disk is not None and gb + 1 > disk else fits(gb * 1e9, mem, running)  # catalog sizes are decimal GB
    st["catalog"] = [{"name": n, "gb": gb, "about": a, "badge": b, "installed": n in have or any(x.startswith(n + ":") for x in have),
                      "fit": fit(gb)} for n, gb, a, b in catalog]
    st["pulls"] = E.store.setting("pulls", {})
    return st


@route("POST", "/api/models/pull")
def pull(E, h, q, body):
    name = body["name"]

    last = {"t": 0, "status": None}

    def save(st):
        pulls = E.store.setting("pulls", {}) or {}
        pulls[name] = st
        E.store.set_setting("pulls", pulls)
        E.bus.publish("pull", name=name, **st)

    def go():
        def prog(p):  # Ollama sends many lines a second: pass on a change of step, or twice a second
            st = {"status": p.get("status"), "completed": p.get("completed"), "total": p.get("total")}
            if st["status"] != last["status"] or time.time() - last["t"] > 0.5 or st["status"] == "success":
                last.update(t=time.time(), status=st["status"])
                save(st)
        try:
            E.llm.pull(name, prog)
        except Exception as e:
            save({"status": f"failed: {llm_plain(e, 'Ollama')}"})
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True}


@route("POST", "/api/models/test")
def test_model(E, h, q, body):
    prov = body.get("provider")
    if prov not in PROVIDERS or not (body.get("model") or "").strip():
        return {"ok": False, "reply": "Pick a provider and a model first."}
    try:
        return E.llm.test(prov, body["model"].strip())
    except Exception as e:
        msg = llm_plain(e, PROVIDERS[prov]["label"])
        if PROVIDERS[prov].get("local") and msg.startswith("That key was refused"):  # a local server refusing isn't about a key you pasted
            msg = f"{PROVIDERS[prov]['label']} refused the request. If it needs a key, add it in API keys."
        return {"ok": False, "reply": msg}


@route("POST", "/api/models/connect")
def connect_model(E, h, q, body):
    """After a key is pasted: pick a model the provider really has, test it, and use it everywhere."""
    prov = body.get("provider")
    if prov not in PROVIDERS:
        raise HTTPError(400, "unknown provider")
    label = PROVIDERS[prov]["label"]
    try:
        model = body.get("model") or E.llm.pick_model(prov)
        if not model:
            return {"ok": False, "reply": "No models found. Download one first." if prov == "ollama" else "This key has no chat models."}
        res = E.llm.test(prov, model)
    except Exception as e:
        msg = llm_plain(e, label)
        if PROVIDERS[prov].get("local") and isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500:
            msg = f"{model} didn’t answer ({label} error {e.response.status_code}). It may not be a chat model, or it needs a newer {label}. Pick another one."
        if msg.startswith("That key was refused") and E.keys.stored(prov):  # a refused key is not kept, nor its warning
            E.keys.delete(prov)
            errs = E.store.setting("provider_errors", {}) or {}
            if errs.pop(prov, None) is not None:
                E.store.set_setting("provider_errors", errs)
            msg += " It wasn’t saved."
        return {"ok": False, "reply": msg}
    if not res["ok"]:
        return {**res, "model": model, "reply": f"{model} answered, but not as expected: “{res['reply']}”"}
    E.llm.remember_default(prov, model)
    return {**res, "model": model}


@route("POST", "/api/models/local/start")
def start_local(E, h, q, body):
    return {"running": E.llm.start_ollama()}


@route("POST", "/api/models/custom")
def custom(E, h, q, body):
    base = (body.get("base") or "").strip().rstrip("/")
    if base and "://" not in base:
        base = "http://" + base
    if not re.match(r"^https?://[^\s/]+(/\S*)?$", base):
        raise HTTPError(400, "That isn’t a server address. It looks like http://127.0.0.1:1234/v1")
    E.store.set_setting("custom_provider", {"base": base})
    return {"ok": True, "base": base, "reachable": E.llm.local_status()["custom"]["reachable"]}


@route("GET", "/api/keys")
def keys(E, h, q, body):
    lims, errs = E.store.setting("key_limits", {}) or {}, E.store.setting("provider_errors", {}) or {}
    rows = [{"provider": p["name"], "label": p["label"], "source": p["key"], "limit": lims.get(p["name"]),
             "spent": round(E.llm.spent(p["name"]), 2), "error": (errs.get(p["name"]) or {}).get("status")}
            for p in E.llm.providers() if not p["local"]]
    custom = next(p for p in E.llm.providers() if p["name"] == "custom")
    return {"keys": rows + [{"provider": "custom", "label": "Your own server", "source": custom["key"]},
                            {"provider": "telegram", "label": "Telegram bot", "source": E.keys.source("telegram")}],
            "backend": E.keys.backend}


@route("POST", "/api/keys")
def set_key(E, h, q, body):
    prov, key = body.get("provider"), (body.get("key") or "").strip()
    if prov not in PROVIDERS and prov != "telegram":
        raise HTTPError(400, "unknown provider")
    if "limit" in body:  # a monthly limit can be set, changed or cleared on its own
        lim = body["limit"]
        lims = E.store.setting("key_limits", {}) or {}
        if lim in (None, ""):
            lims.pop(prov, None)
        else:
            try:
                lim = float(lim)
            except (TypeError, ValueError):
                raise HTTPError(400, "The limit must be a number of dollars.")
            if lim < 0:
                raise HTTPError(400, "The limit can’t be below zero.")
            lims[prov] = lim
        E.store.set_setting("key_limits", lims)
    if not key:
        if "limit" in body:
            return {"ok": True, "source": E.keys.source(prov)}
        raise HTTPError(400, "Paste the token from @BotFather first." if prov == "telegram" else "Paste a key first.")
    if prov == "telegram":  # same check as Connectors: Telegram must know the token
        r = connectors.PROVIDERS["telegram"].save(E, {"token": key})
        if not r["ok"]:
            raise HTTPError(400, r["text"])
    else:
        try:
            E.keys.set(prov, key)
        except (ValueError, RuntimeError) as e:
            raise HTTPError(400, str(e)[:1].upper() + str(e)[1:] + ".")
        errs = E.store.setting("provider_errors", {}) or {}
        if errs.pop(prov, None):
            E.store.set_setting("provider_errors", errs)
    return {"ok": True, "source": E.keys.source(prov)}


@route("DELETE", r"/api/keys/(\w+)")
def del_key(E, h, q, body, prov):
    E.keys.delete(prov)
    if prov in connectors.PROVIDERS:  # its service is off too (Telegram alerts can't stay on without a token)
        E.store.set_setting(prov, {**(E.store.setting(prov, {}) or {}), "enabled": False} if prov == "telegram" else {})
    for name in ("provider_errors", "key_limits"):  # nothing stale left behind
        d = E.store.setting(name, {}) or {}
        if d.pop(prov, None) is not None:
            E.store.set_setting(name, d)
    return {"ok": True, "source": E.keys.source(prov)}


# ------------------------------------------------------------------ connectors (MCP)
@route("GET", "/api/mcp")
def mcp(E, h, q, body):
    return {"servers": E.mcp.servers()}


@route("POST", "/api/mcp")
def mcp_save(E, h, q, body):
    import shlex
    name = re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", (body.get("name") or "").lower())).strip("-")[:40]
    if not name:
        raise HTTPError(400, "Give it a name, like github.")
    if name in PRESETS or name in connectors.PROVIDERS or name == "inky":
        raise HTTPError(400, f"“{name}” is already a built-in connector. Pick another name.")
    if E.mcp.known(name) and not body.get("replace"):
        raise HTTPError(409, f"There’s already a server called “{name}”. Remove it first, or pick another name.")
    cmd = body.get("command")
    if isinstance(cmd, str):
        try:
            cmd = shlex.split(cmd)
        except ValueError:
            raise HTTPError(400, "The command has an unclosed quote.")
    if not cmd:
        raise HTTPError(400, "Put in the command that starts it, like npx -y @modelcontextprotocol/server-github.")
    E.mcp.save(name, command=cmd, enabled=body.get("enabled", True), label=(body.get("label") or "").strip() or name, env=body.get("env"))
    return {"name": name, "servers": E.mcp.servers()}


@route("POST", r"/api/mcp/([\w-]+)/connect")
def mcp_connect(E, h, q, body, name):
    if not E.mcp.known(name):
        raise HTTPError(404, f"There’s no connector called {name}.")
    E.mcp.save(name, enabled=True)
    tools = E.mcp.tools(name)
    return {"tools": [{"name": t["name"], "description": (t.get("description") or "")[:300],
                       "params": list((t.get("inputSchema") or {}).get("properties", {}).keys()),
                       "required": (t.get("inputSchema") or {}).get("required", []),
                       "types": {k: v.get("type") for k, v in (t.get("inputSchema") or {}).get("properties", {}).items() if isinstance(v, dict)}}
                      for t in tools],
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
    if name in PRESETS:  # a built-in goes back to how it came
        E.mcp.remove(name)
        return {"ok": True, "reset": True}
    E.mcp.remove(name)
    return {"ok": True}


@route("DELETE", r"/api/connectors/(telegram|n8n|apify)")
def connector_forget(E, h, q, body, name):
    """Disconnect a built-in service: its key and settings are removed from this computer."""
    E.keys.delete(name)
    E.store.set_setting(name, {"enabled": False} if name == "telegram" else {})
    return {"ok": True}


def inky_mcp(E):
    """How Claude Code or Codex start Inky's own MCP server. It finds the running engine through engine.json."""
    from inky.mcp import launcher
    py, *args = launcher("inky.mcp_server", "mcp-server")
    env = {"INKY_HOME": str(E.home)}
    if not getattr(sys, "frozen", False):  # running from source: `python -m inky.mcp_server` needs the repo on the path
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    return py, args, env


@route("GET", "/api/mcp/inky-config")
def inky_config(E, h, q, body):
    py, args, env = inky_mcp(E)
    return {"claude": {"mcpServers": {"inky": {"command": py, "args": args, "env": env}}},
            "claude_argv": ["claude", "mcp", "add", "--scope", "user", "inky", *[x for k, v in env.items() for x in ("-e", f"{k}={v}")], "--", py, *args],
            "claude_cli": f"claude mcp add --scope user inky {' '.join(f'-e {k}={v}' for k, v in env.items())} -- {py} {' '.join(args)}",
            "codex_toml": f'[mcp_servers.inky]\ncommand = {json.dumps(py)}\nargs = {json.dumps(args)}\nenv = {{ {", ".join(f"{k} = {json.dumps(v)}" for k, v in env.items())} }}\n'}


# ------------------------------------------------------------------ the agent library
@route("GET", "/api/library")
def library_index(E, h, q, body):
    return library.index()


@route("POST", "/api/library/preview")
def library_preview(E, h, q, body):
    """What an agent would do here, before it's installed: its sites, what it may do that can't be undone, its skills."""
    file = isinstance(body.get("bundle"), dict)  # a bot file you opened: previewed as it would arrive, without what it may carry
    try:
        b = library.as_shared(body["bundle"]) if file else library.fetch(body.get("url", ""))
        listing = library.listing_for(b, None if file else body.get("url", "").strip())
    except Exception as e:
        raise HTTPError(400, str(e) if isinstance(e, ValueError) else "That link doesn’t point to an Inky agent.")
    have = [] if file else [x["id"] for x in E.store.find("bots") if (x.get("library") or {}).get("slug") == listing.get("slug")]
    return {"listing": listing, "check": library.check(b), "have": have,
            "skills": [{"name": s.get("name"), "steps": len(s.get("steps") or [])} for s in b.get("skills") or []]}


@route("POST", "/api/library/install")
def library_install(E, h, q, body):
    url = body.get("url", "")
    try:
        bid = library.install(E, body["bundle"], file=True) if isinstance(body.get("bundle"), dict) else library.install(E, library.fetch(url), source=url)
    except Exception as e:
        raise HTTPError(400, str(e) if isinstance(e, ValueError) else "That agent couldn’t be installed.")
    return {"id": bid}


@route("POST", r"/api/bots/(\d+)/publish/preview")
def publish_preview(E, h, q, body, bid):
    b, c, text = library.prepare(E, int(bid), body.get("meta") or {})
    import shutil
    gh = bool(shutil.which("gh")) and library._gh("auth", "status").returncode == 0
    return {"text": text, "check": c, "listing": b["listing"], "gh": gh}


@route("POST", r"/api/bots/(\d+)/publish")
def publish(E, h, q, body, bid):
    public(body)
    return library.publish(E, int(bid), body.get("meta") or {})


def public(body):
    """Posting in public happens only after you said yes on screen: a script or an agent calling the API can't do it by accident."""
    if body.get("confirm") is not True:
        raise HTTPError(400, "Posting in public needs your yes in the app.")


@route("POST", r"/api/bots/(\d+)/share-code")
def share_code(E, h, q, body, bid):
    bot_or_404(E, bid)
    return library.share_code(E, int(bid), body.get("meta") or {})


@route("POST", "/api/sites")
def find_sites(E, h, q, body):
    """Websites for a job (a DuckDuckGo search per query), so you can pick instead of hunting for them."""
    from inky import sites
    qs = [x for x in body.get("queries") or [] if isinstance(x, str)] or [str(body.get("job") or "")]
    web, note = [], ""
    try:
        web = sites.suggest(qs, guess=body.get("guess"), pages=3 if body.get("more") else 1)
    except RuntimeError as e:  # the search engine is busy or unreachable: the model's suggestions still help
        note = str(e)
    ai = []
    if len(web) < 15 and E.llm.roles().get("chat"):
        model = E.llm.roles()["chat"].get("model") or "the model"
        ai = sites.from_model(E.llm, str(body.get("job") or " ".join(qs)), have={r["site"] for r in web}, label=model)
    if not web and not ai:
        raise HTTPError(502, note or "No sites found. Try other words, or type an address.")
    said = str(body.get("job") or "").lower()
    rows = web + ai
    for r in rows:  # a site your job names (“on Amazon” → amazon.de): it starts there
        name = (r.get("site") or "").split(".")[0]
        r["named"] = bool(len(name) > 2 and re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", said))
    rows.sort(key=lambda r: not r["named"])
    return {"sites": rows, "searched": qs, "note": note, "more": bool(body.get("more"))}


MAKING, MADE = {}, itertools.count(1)  # bots being made from a sentence in the background (for MCP clients, which can't wait a minute for a draft)


@route("POST", "/api/bots/from-job")
def from_job(E, h, q, body):
    """Make a bot the way the New bot screen does (draft, find sites unless one is named, create, learn), in the background.
    Returns at once with an id to ask about: a draft with a local model can take longer than an MCP client waits."""
    job = str(body.get("job") or "").strip()
    if not job:
        raise HTTPError(400, "Describe the job first.")
    jid = str(next(MADE))
    MAKING[jid] = {"status": "drafting", "job": job}

    def go():
        try:
            d = E.draft_bot(job)
            start, more = body.get("site") or d.get("start_url"), []
            if not start:
                MAKING[jid]["status"] = "finding sites"
                try:
                    found = find_sites(E, None, {}, {"job": d["job"], "queries": d.get("search"), "guess": d.get("guess")})["sites"]
                except Exception:
                    found = []
                pick = [x["url"] for x in found if x.get("named")] or [x["url"] for x in found][:3]
                start, more = (pick[0], pick[1:]) if pick else (None, [])
            filters = [{**f, "text": f.get("text") or f"{f['field']} {f['op']} {f['value']}"} for f in d.get("filters") or []]
            b = E.create_bot({**d, "start_url": start, "more_sites": more, "filters": filters})
            if start:
                E.learn(b["id"], b.get("goal") or d.get("goal"), start)
            MAKING[jid].update(status="learning" if start else "needs a site", bot=b["id"], name=b["name"], sites=[x for x in [start, *more] if x],
                               rules=[f["text"] for f in filters], every_minutes=(b.get("schedule") or {}).get("every_minutes"))
        except Exception as e:
            from inky.bots import plain_error
            MAKING[jid].update(status="failed", error=plain_error(e))
    threading.Thread(target=go, daemon=True, name="from-job").start()
    return {"id": jid, **MAKING[jid]}


@route("GET", r"/api/bots/from-job/(\d+)")
def from_job_status(E, h, q, body, jid):
    if jid not in MAKING:
        raise HTTPError(404, "No bot is being made with that id.")
    return {"id": jid, **MAKING[jid]}


@route("POST", r"/api/bots/(\d+)/share-link")
def share_link(E, h, q, body, bid):
    public(body)  # it makes a public Gist with your GitHub account
    return library.share_link(E, int(bid), body.get("meta") or {})


# ------------------------------------------------------------------ connectors (status, setup, test)
@route("GET", "/api/connectors")
def connectors_list(E, h, q, body):
    return {"connectors": connectors.status(E), "inky": inky_config(E, h, q, body)}


@route("POST", r"/api/connectors/([\w-]+)/test")
def connector_test(E, h, q, body, name):
    return connectors.test(E, name)


@route("POST", r"/api/connectors/(telegram|n8n|apify)/setup")
def connector_setup(E, h, q, body, name):
    return connectors.PROVIDERS[name].save(E, body.get("values") or {})


@route("POST", "/api/connectors/telegram/find-chat")
def telegram_find_chat(E, h, q, body):
    chat = connectors.PROVIDERS["telegram"].find_chat(E)
    return {"chat_id": chat, "bot": E.store.setting("telegram", {}).get("bot")}


@route("POST", "/api/connectors/claude-code/add-inky")
def claude_add_inky(E, h, q, body):
    """Changes Claude Code's own settings, so the UI shows the exact command first and only calls this on your click."""
    import shutil
    import subprocess
    argv = inky_config(E, h, q, body)["claude_argv"]
    exe = shutil.which("claude")
    if not exe:
        raise HTTPError(400, "Claude Code isn’t installed")
    subprocess.run([exe, "mcp", "remove", "--scope", "user", "inky"], capture_output=True, timeout=20)  # replace an older entry
    r = subprocess.run([exe, *argv[1:]], capture_output=True, text=True, timeout=30)
    return {"ok": r.returncode == 0, "text": (r.stdout or r.stderr).strip()[:400]}


@route("POST", "/api/connectors/codex/add-inky")
def codex_add_inky(E, h, q, body):
    """Adds [mcp_servers.inky] to ~/.codex/config.toml if it isn't there. Only on your click; returns what it wrote."""
    cfg = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser() / "config.toml"
    have = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    if re.search(r"^\[mcp_servers\.inky\]", have, re.M):
        return {"ok": True, "wrote": "", "text": "Codex already has Inky."}
    block = inky_config(E, h, q, body)["codex_toml"]
    cfg.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg, "a", encoding="utf-8") as f:
        f.write(("\n" if have and not have.endswith("\n") else "") + "\n" + block)
    return {"ok": True, "wrote": block, "text": f"Added to {cfg}."}


@route("POST", r"/api/bots/(\d+)/skills/(\d+)/send-n8n")
def bot_send_n8n(E, h, q, body, bid, sid):
    _own_skill(E, bid, sid)
    return send_n8n(E, h, q, body, sid)


@route("POST", r"/api/skills/(\d+)/send-n8n")
def send_n8n(E, h, q, body, sid):
    s = E.store.get("skills", int(sid))
    try:
        wf = connectors.PROVIDERS["n8n"].send_skill(E, s, f"http://127.0.0.1:{h.server.server_port}")
    except Exception as e:
        return {"ok": False, "text": connectors._err(e, "n8n")}
    return {"ok": True, "id": wf.get("id"), "text": f"Sent. It’s in n8n as “{wf.get('name')}”, turned off until you switch it on."}


# ------------------------------------------------------------------ computers, settings, health
@route("GET", "/api/computers")
def computers(E, h, q, body):
    bots_ = E.bots()
    local = {"id": "local", "name": E.store.setting("engine_name", platform.node()), "kind": "local", "ok": True, "os": platform.system(),
             "bots": [b for b in bots_ if (b.get("computer") or "local") == "local"], "docker": health.docker()}
    def remote(c):
        r = transfer.Remote(c["url"], c["token"])
        try:
            ok, rbots = True, [x for x in r.req("GET", "/api/bots", timeout=4)["bots"] if x.get("status") != "moved"]
            if not c.get("os"):  # remember what it runs, for its logo
                c["os"] = r.req("GET", "/api/ping", timeout=4).get("os") or "Linux"
                E.store.update("computers", c["id"], os=c["os"])
        except Exception:
            ok, rbots = False, []
        return {"id": c["id"], "name": c["name"], "url": c["url"], "kind": "remote", "ok": ok, "bots": rbots, "os": c.get("os")}
    from concurrent.futures import ThreadPoolExecutor
    comps = E.store.find("computers", desc=False)
    with ThreadPoolExecutor(max(1, min(8, len(comps)))) as ex:  # all servers at once, not one after another
        out = [local] + list(ex.map(remote, comps))
    return {"computers": out, "pair_code": transfer.pair_code(E.token)}


@route("POST", "/api/computers")
def add_computer(E, h, q, body):
    url, code = (body.get("url") or "").strip(), (body.get("code") or "").strip()
    try:
        if url.startswith("inky://"):
            url, code = connect.parse_pair_link(url)
        if not url or re.search(r"\s", url):
            raise ValueError("That isn’t an address. It looks like 192.168.1.20:8800 or a pair link.")
        if re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I) and not url.lower().startswith(("http://", "https://")):
            raise ValueError("Use an http:// address, like 192.168.1.20:8800.")
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        u = urlparse(url)
        host = f"[{u.hostname}]" if u.hostname and ":" in u.hostname else u.hostname
        url = f"{u.scheme}://{host}:{u.port or 8800}" if host else url  # just the server, not a page on it
        cid = connect.pair_and_save(E, url, code)
    except ValueError as e:
        raise HTTPError(400, str(e))
    except httpx.RequestError:
        raise HTTPError(400, f"Couldn’t reach {url}. Is Inky running there, and is the port open?")
    if body.get("name"):
        E.store.update("computers", cid, name=body["name"])
    return {"id": cid, "name": (E.store.get("computers", cid) or {}).get("name")}


@route("POST", "/api/computers/link")
def pair_link(E, h, q, body):
    return add_computer(E, h, q, {"url": body.get("link", "")})


@route("GET", "/api/computers/found")
def computers_found(E, h, q, body):
    return {"found": connect.found(E)}


@route("POST", "/api/computers/ssh")
def computers_ssh(E, h, q, body):
    target = (body.get("target") or "").strip()
    try:
        connect.split_target(target)
    except ValueError as e:
        raise HTTPError(400, str(e))

    def go():
        say = lambda step, **kw: E.bus.publish("ssh", step=step, **kw)
        try:
            connect.ssh_setup(E, target, say)
        except connect.SetupError as e:
            say("failed", text=str(e), fix=e.fix)
        except Exception as e:
            say("failed", text=str(e)[:300])
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True}


@route("DELETE", r"/api/computers/(\d+)")
def del_computer(E, h, q, body, cid):
    for b in E.store.find("bots"):  # their placeholders here point at that server: they'd act on whatever has that id there later
        if b.get("status") == "moved" and str(b.get("computer")) == str(cid):
            E.delete_bot(b["id"])
    E.store.delete("computers", int(cid))
    REMOTE_NEEDS.update(at=0, rows=[])
    return {"ok": True}


def settings_view(E):
    d = {"setup_done": False, "engine_name": platform.node(), "notify_app": True, "screen_allowed": False, "sounds": True, "user_name": ""}
    d.update(E.store.setting("app", {}))
    d["data_folder"] = str(E.home)
    d["telegram"] = E.store.setting("telegram", {"enabled": False})
    d["n8n_connected"] = connectors.PROVIDERS["n8n"].configured(E)
    d["web_url"] = lan_url(E)
    d["engine_name"] = E.store.setting("engine_name") or platform.node()  # the stored, trimmed name (not what was typed)
    from inky import __version__
    d["version"] = __version__
    return d


@route("GET", "/api/settings")
def settings(E, h, q, body):
    return settings_view(E)


@route("POST", "/api/settings")
def save_settings(E, h, q, body):
    if "lan" in body:
        lan_access(E, bool(body.pop("lan")))
    app = E.store.setting("app", {})
    if "user_name" in body:
        body["user_name"] = str(body["user_name"]).strip()[:40]
    tg = body.pop("telegram", None)
    if tg and "chat_id" in tg and tg["chat_id"] not in (None, "") and not re.match(r"^-?\d{3,20}$", str(tg["chat_id"]).strip()):
        raise HTTPError(400, "A Telegram chat id is a number, like 123456789 (Connectors finds it for you when you send /start).")
    if tg and tg.get("enabled") and not E.keys.get("telegram"):
        raise HTTPError(400, "Set up Telegram in Connectors first: paste your bot’s token and send it /start.")
    app.update(body)
    E.store.set_setting("app", app)
    if "setup_done" in body:
        E.store.set_setting("setup_done", bool(body["setup_done"]))
    if "engine_name" in body:
        E.store.set_setting("engine_name", (str(body["engine_name"]).strip() or platform.node())[:40])
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
            "telegram": E.store.setting("telegram", {"enabled": False}), "telegram_key": E.keys.source("telegram"),
            "pair_code": transfer.pair_code(E.token), "install": f"curl -fsSL {connect.INSTALL_URL} | sh", "web_url": lan_url(E)}


@route("POST", "/api/telegram/test")
def telegram_test(E, h, q, body):
    token = E.keys.get("telegram")
    if not token:
        raise HTTPError(400, "paste the bot token first")
    r = httpx.get(connectors.PROVIDERS["telegram"].api(token, "getMe"), timeout=15).json()
    if r.get("ok"):
        E.store.set_setting("telegram", {**E.store.setting("telegram", {}), "bot": r["result"].get("username")})
    return {"ok": r.get("ok", False), "bot": (r.get("result") or {}).get("username"), "chat_id": E.store.setting("telegram", {}).get("chat_id")}


# ------------------------------------------------------------------ handler
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    engine = None
    timeout = 60  # a client that stops sending mid-request never holds a thread

    def log_message(self, *a):
        pass

    def _send(self, status, data, ctype="application/json", extra=None):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if ctype.startswith("text/html"):  # the app's page: its own scripts only, never inside another site's frame
            self.send_header("Content-Security-Policy", CSP)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _authed(self, q):
        t = self.headers.get("X-Inky-Token") or q.get("t") or ""
        return hmac.compare_digest(t.encode(), self.engine.token.encode())

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
        mh = re.match(r"^/api/bots/(\d+)", path)
        if mh and self.headers.get("X-Inky-Home"):  # another computer asking for its moved bot: never a bot that only shares its id
            hb = E.store.get("bots", int(mh.group(1)))
            if not hb or not hb.get("home") or transfer.home_of(E, hb) != self.headers["X-Inky-Home"]:
                return self._send(410 if method != "DELETE" else 404, {"error": "That bot isn’t here any more.", "gone": True})
        m = re.match(r"^/api/bots/(\d+)/screen\.(mjpg|jpg)$", path)
        if m:
            return self._screen(int(m.group(1)), m.group(2))
        if path == "/api/events":
            return self._sse()
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0 or n > (MAX_BODY if self._authed(q) else 4096):  # before the token is checked, only a pairing code fits
            self.close_connection = True
            return self._send(413 if n > 0 else 400, {"error": "That request is too big." if n > 0 else "bad Content-Length"})
        try:
            raw = self.rfile.read(n) if n else b""
        except (TimeoutError, ConnectionError):
            self.close_connection = True
            return
        try:
            body = json.loads(raw or b"{}")
        except (ValueError, RecursionError):  # not JSON, not UTF-8, or nested too deep
            return self._send(400, {"error": "bad JSON"})
        if not isinstance(body, dict):
            return self._send(400, {"error": "Send a JSON object."})
        proxied = self._proxy(method, path, body, u.query)
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

    def _proxy(self, method, path, body, query=""):
        """Bots that moved to another engine: forward their calls there."""
        m = re.match(r"^/api/bots/(\d+)(/.*)?$", path)
        if not m or path.endswith(("/move", "/bring-back")) or method == "DELETE" or self.headers.get("X-Inky-Forwarded"):
            return None  # deleting is never forwarded, and nothing is forwarded twice
        b = self.engine.store.get("bots", int(m.group(1)))
        if not b or not b.get("remote_id") or (b.get("computer") or "local") == "local":
            return None
        c = self.engine.store.get("computers", int(b["computer"]))
        if not c:
            return None
        rpath = f"/api/bots/{b['remote_id']}{m.group(2) or ''}" + (f"?{query}" if query else "")
        try:
            r = httpx.request(method, c["url"] + rpath, json=body if method != "GET" else None, headers=fwd_headers(self.engine, c, b),
                              timeout=transfer.connect_timeout(120 if method != "GET" else 20))
            data = r.json()
            if r.status_code == 410 or (r.status_code == 404 and not m.group(2)):  # the bot itself is gone there
                return self._send(410, {"error": f"{b['name']} is no longer on {c['name']}.", "gone": True}) or True
            if isinstance(data, dict) and isinstance(data.get("bot"), dict):
                rb = data["bot"]
                if (rb.get("name"), rb.get("look")) != (b.get("name"), b.get("look")):  # renamed or restyled there: the sidebar follows
                    self.engine.store.update("bots", b["id"], name=rb.get("name") or b["name"], look=rb.get("look") or b.get("look"))
                    self.engine.bus.publish("bots")
                rb.update(id=b["id"], computer=b["computer"], remote=c["name"])
            if method == "POST" and re.search(r"/needs/\d+$", path) and r.status_code in (200, 201, 404, 409):
                REMOTE_NEEDS["at"] = 0  # answered (or already answered there): the list follows at once
            self._send(r.status_code, data)
        except Exception:
            self._send(502, {"error": f"{c['name']} isn’t answering. It may be asleep or offline.", "offline": True})
        return True

    def _local(self):
        """A browser on this computer. The Host check stops DNS-rebinding pages from reading the token."""
        host = (self.headers.get("Host") or "").lower()
        host = host[1:host.index("]")] if host.startswith("[") else host.split(":")[0]
        return self.client_address[0] in ("127.0.0.1", "::1") and host in ("127.0.0.1", "localhost", "::1")

    def _static(self, path):
        if path in ("/", "/index.html"):  # other devices sign in with the pairing code instead
            html = (UI / "index.html").read_text(encoding="utf-8").replace("__INKY_TOKEN__", self.engine.token if self._local() else "")
            return self._send(200, html.encode(), TYPES[".html"])
        f = (UI / path.lstrip("/")).resolve()
        if UI.resolve() not in f.parents or not f.is_file():
            return self._send(404, b"not found", "text/plain")
        return self._send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))

    def _screen(self, bid, kind):
        E = self.engine
        b = E.store.get("bots", bid)
        if b and b.get("remote_id") and (b.get("computer") or "local") != "local":
            c = E.store.get("computers", int(b["computer"])) if str(b["computer"]).isdigit() else None
            if not c:  # its computer was unpaired
                return self._send(204, b"", "image/jpeg")
            url, hd = f"{c['url']}/api/bots/{b['remote_id']}/screen.{kind}", fwd_headers(E, c, b)
            if kind == "jpg":
                try:
                    r = httpx.get(url, headers=hd, timeout=transfer.connect_timeout(20))
                except httpx.HTTPError:
                    return self._send(204, b"", "image/jpeg")
                return self._send(r.status_code, r.content, "image/jpeg")
            started = False
            try:  # the live view streams through, frame by frame
                with httpx.stream("GET", url, headers=hd, timeout=httpx.Timeout(None, connect=3)) as r:
                    if r.status_code != 200:
                        return self._send(204, b"", "image/jpeg")
                    self.send_response(200)
                    self.send_header("Content-Type", r.headers.get("content-type") or "multipart/x-mixed-replace; boundary=frame")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    started = True
                    for chunk in r.iter_raw():
                        self.wfile.write(chunk)
                        self.wfile.flush()
            except httpx.HTTPError:
                if not started:
                    return self._send(204, b"", "image/jpeg")
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True
            return
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
    srv = Server((host, port), type("EngineHandler", (Handler,), {"engine": engine}))
    srv.daemon_threads = True
    engine.port = srv.server_port  # connectors that call back into Inky (n8n) need it
    from inky import computer
    computer.SELF_PORTS.add(srv.server_port)  # bots' browsers never open this engine's own page
    engine.host = host
    if not getattr(engine, "watching_needs", False):
        engine.watching_needs = True
        watch_remote_needs(engine)
    return srv


def lan_access(E, on):
    """Let phones and other computers on your Wi-Fi open Inky (they sign in with the pairing code). The engine
    keeps its own address; this adds a second one on your network, and tells the network it's there."""
    from inky import __version__
    srv = getattr(E, "lan_srv", None)
    if on and not srv and getattr(E, "host", "") not in ("0.0.0.0", "::", ""):
        for port in ((E.port or 8800) + 1, 0):
            try:  # no address reuse: on macOS it would let us share a port another program listens on
                cls = type("LanServer", (Server,), {"allow_reuse_address": False})
                srv = cls(("0.0.0.0", port), type("EngineHandler", (Handler,), {"engine": E}))
                break
            except OSError:
                srv = None
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True, name="lan").start()
        E.lan_srv = srv
        E.lan_beacon = connect.start_beacon(lambda: E.store.setting("engine_name", platform.node()), srv.server_port, __version__, transfer.engine_id(E))
    elif not on and srv:
        E.lan_beacon.set()
        srv.shutdown()
        srv.server_close()
        E.lan_srv = None
    app = E.store.setting("app", {}) or {}
    E.store.set_setting("app", {**app, "lan": bool(on)})
    return lan_url(E)


def lan_url(E):
    if getattr(E, "lan_srv", None):
        port = E.lan_srv.server_port
    elif getattr(E, "host", "") in ("0.0.0.0", "::", ""):
        port = E.port
    else:
        return None
    ip = connect.lan_ip()
    return f"http://{ip}:{port}" if ip else None
