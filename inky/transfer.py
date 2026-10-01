"""Moving bots between engines (this computer ↔ your server). A bundle carries the bot, its skills,
memory, results and browser sign-ins. Pairing: the other engine shows a 6-letter code; typing it here
returns that engine's API token over the local network."""
import time

import httpx

BUNDLE = 1


def pair_code(token):
    return "".join(c for c in token.upper() if c.isalnum())[:6]


def engine_id(engine):
    """A stable id for an engine that reveals nothing about its token."""
    import hashlib
    return hashlib.sha256(("inky-engine:" + engine.token).encode()).hexdigest()[:16]


def export_bot(engine, bid, private=False):
    """private=True (moving to your own server) carries sign-ins and chat; a shared file never does."""
    b = engine.store.get("bots", bid)
    cookies = []
    if private:
        try:
            cookies = engine.computer(bid).call("storage_state").get("cookies", [])
        except Exception:
            pass
    strip = ("id", "bot_id", "status", "key", "ts")
    clean = lambda r: {k: v for k, v in r.items() if k not in strip}
    # a shared file is a bot's skills, rules, look and personality; not what it knows about you or found for you
    bot = clean(b) if private else {**{k: v for k, v in clean(b).items() if k not in ("pending_cookies", "remote_id", "computer", "home")}, "memory": []}
    if private:  # remember where it came from, so going back home reuses its old place instead of making a copy
        bot.setdefault("home", {"engine": engine_id(engine), "bot": bid})
    else:  # a shared file never carries your approvals: whoever gets it is asked again
        bot["automations"] = [{k: v for k, v in a.items() if k != "approved_always"} for a in bot.get("automations") or []]
    sks = [clean(s) for s in engine.store.find("skills", bot_id=bid, desc=False)]
    if not private:
        sks = [dict(s, steps=[{k: v for k, v in st.items() if k != "approved_always"} for st in s.get("steps") or []]) for s in sks]
    return {"bundle": BUNDLE, "exported": time.time(), "bot": bot,
            "skills": sks,
            "results": [dict(clean(r), key=r["key"]) for r in engine.store.find("results", bot_id=bid, limit=2000)] if private else [],
            "messages": [clean(m) for m in engine.store.find("messages", bot_id=bid, limit=200, desc=False)] if private else [],
            # a move keeps its history: runs (its level and streak come from them) and recent events
            "runs": [dict(clean(r), status=r.get("status")) for r in engine.store.find("runs", bot_id=bid, limit=600, desc=False)] if private else [],
            "events": [dict(clean(e), kind=e.get("kind")) for e in engine.store.find("events", bot_id=bid, limit=300, desc=False)] if private else [],
            "cookies": cookies}


def import_bot(engine, bundle):
    if not isinstance(bundle, dict) or bundle.get("bundle") != BUNDLE or not isinstance(bundle.get("bot"), dict):
        if isinstance(bundle, dict) and bundle.get("inky_skill"):
            raise ValueError("That’s a skill file. Open a bot, then Skills → Import, to add it there.")
        raise ValueError("That isn’t an Inky bot file.")
    if not isinstance(bundle.get("skills", []), list):
        raise ValueError("That bot file is damaged (its skills aren’t a list).")
    names = {b["name"] for b in engine.store.find("bots")}
    name = (str(bundle["bot"].get("name") or "Imported bot").strip() or "Imported bot")[:40]
    base, n = name, 2
    while name in names:  # importing the same file twice gives "Name 2", not two identical bots
        name, n = f"{base[:36]} {n}", n + 1
    home = bundle["bot"].get("home") or {}
    old = engine.store.get("bots", home.get("bot")) if home.get("engine") == engine_id(engine) and home.get("bot") else None
    moving = bool(bundle.get("cookies") or bundle.get("messages") or home)  # a move carries its sign-ins and chat
    if old and old.get("status") == "moved":  # it's coming home: take its old place back
        name = old["name"]
    bot = dict(bundle["bot"], name=name, computer="local", pending_cookies=bundle.get("cookies") or None, remote=None, remote_id=None)
    if old and old.get("status") == "moved":
        bid = old["id"]
        for tb in ("skills", "results", "messages", "needs", "runs", "events"):
            engine.store.delete(tb, bot_id=bid)
        bot.pop("home", None)
        engine.store.update("bots", bid, **bot)
        engine.store.update("bots", bid, status="idle")
    else:
        bid = engine.store.insert("bots", bot, status="idle")
    for s in bundle.get("skills", []):
        s = dict(s)
        if not moving:  # someone else's approvals don't count here: it asks you again
            s["steps"] = [{k: v for k, v in st.items() if k != "approved_always"} for st in s.get("steps") or []]
        engine.store.insert("skills", s, bot_id=bid, status="ok")
    for r in bundle.get("results", []):
        key = r.pop("key", None)
        engine.store.insert("results", r, bot_id=bid, key=key)
    for m in bundle.get("messages", []):
        engine.store.insert("messages", m, bot_id=bid, status=m.get("role"))
    for r in bundle.get("runs", []) if moving else []:
        r = dict(r); st = r.pop("status", None) or "ok"
        engine.store.insert("runs", r, bot_id=bid, status="stopped" if st == "running" else st)
    for e in bundle.get("events", []) if moving else []:
        engine.store.insert("events", dict(e), bot_id=bid, status=e.get("kind"))
    n = len(bundle.get("skills", []))
    engine.store.event(bid, "arrived", f"{bot['name']} arrived with {n} skill{'' if n == 1 else 's'}")
    if not bundle.get("messages"):  # a shared bot says hello when it moves in
        n = len(bundle.get("skills", []))
        engine.store.message(bid, "bot", f"Hi! I'm {bot['name']}. I just moved in" + (f" and brought {n} skill{'s' if n != 1 else ''}, so I can start right away." if n else "."), intro=True)
    engine.bus.publish("bots")
    return bid


class Remote:
    def __init__(self, url, token):
        self.url, self.token = url.rstrip("/"), token

    def req(self, method, path, body=None, timeout=60):
        r = httpx.request(method, self.url + path, json=body, headers={"X-Inky-Token": self.token}, timeout=timeout)
        r.raise_for_status()
        return r.json()


def pair(url, code):
    url = url.rstrip("/")
    try:  # is it an Inky at all?
        ping = httpx.get(url + "/api/ping", timeout=8).json()
        assert ping.get("ok")
    except (ValueError, AssertionError, AttributeError):
        raise ValueError(f"{url} answered, but it isn’t an Inky.")
    r = httpx.post(url + "/api/pair", json={"code": (code or "").strip().upper()}, timeout=15)
    if r.status_code == 429:
        raise ValueError("Too many tries. Wait a minute, then type the code again.")
    if r.status_code != 200:
        raise ValueError("That code didn’t match. It’s the 6 letters and numbers that server shows.")
    info = r.json()
    return info["token"], info.get("name") or url


def move_bot(engine, bid, computer_id, progress=lambda step, **kw: None):
    """Pause → pack → send → start and check there → remove here. Returns the remote bot id."""
    comp = engine.store.get("computers", computer_id)
    remote = Remote(comp["url"], comp["token"])
    b = engine.store.get("bots", bid)
    engine.control(bid, "stop")
    progress("paused", text="Paused between two runs")
    bundle = export_bot(engine, bid, private=True)
    size = len(str(bundle))
    n = len(bundle["skills"])
    progress("packed", text=f"Packed its memory, {n} skill{'' if n == 1 else 's'} and settings", size=size)
    rid = remote.req("POST", "/api/import", bundle, timeout=120)["bot"]["id"]
    progress("sent", text=f"Sent it to {comp['name']}")
    check = None
    try:
        if bundle["skills"]:  # a check never asks and never acts: it stops at the first step that would ask you
            check = remote.req("POST", f"/api/bots/{rid}/run", {"wait": True, "check": True, "timeout": 240, "reason": "check after moving"}, timeout=260).get("run")
            if not check or check.get("status") != "ok":
                why = (check or {}).get("note") or "it didn’t finish"
                progress("check_failed", text=f"The check run there didn’t pass ({why}), so it stays here", run=check)
                raise RuntimeError("check_failed")
    except Exception:
        try:  # never leave a second copy on the server
            remote.req("DELETE", f"/api/bots/{rid}", timeout=30)
        except Exception:
            pass
        raise
    if check:
        n = check.get("items", 0)
        progress("checked", text=f"Checked a run there: {n} result{'' if n == 1 else 's'}" + (f" ({check['note']})" if check.get("note") else ""))
    engine.close_computer(bid)
    home = b.get("home") or {}
    if home.get("engine") and home.get("engine") == remote.req("GET", "/api/ping", timeout=10).get("id"):
        engine.delete_bot(bid)  # it went back home: nothing needs to stay behind here
        progress("done", text=f"{b['name']} is back on {comp['name']}")
        return rid
    engine.store.update("bots", bid, computer=computer_id, remote_id=rid, status="moved")
    engine.store.event(bid, "moved", f"{b['name']} now runs on {comp['name']}")
    progress("done", text=f"{b['name']} now runs on {comp['name']}")
    engine.bus.publish("bots")
    return rid


def bring_back(engine, bid, progress=lambda step, **kw: None):
    """A bot that moved to another computer comes back here, with its memory, skills and sign-ins."""
    b = engine.store.get("bots", bid)
    comp = engine.store.get("computers", int(b["computer"])) if b and b.get("remote_id") else None
    if not comp:
        raise RuntimeError("it isn’t on another computer")
    remote = Remote(comp["url"], comp["token"])
    remote.req("POST", f"/api/bots/{b['remote_id']}/control", {"cmd": "stop"}, timeout=30)
    progress("paused", text=f"Paused it on {comp['name']}")
    bundle = remote.req("GET", f"/api/bots/{b['remote_id']}/export?private=1", timeout=120)
    n = len(bundle.get("skills", []))
    progress("packed", text=f"Packed its memory and {n} skill{'' if n == 1 else 's'} there")
    bundle["bot"]["home"] = {"engine": engine_id(engine), "bot": bid}
    import_bot(engine, bundle)
    remote.req("DELETE", f"/api/bots/{b['remote_id']}", timeout=60)
    progress("done", text=f"{b['name']} is back on this computer")
    engine.bus.publish("bots")
    return bid
