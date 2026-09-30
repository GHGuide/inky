"""Moving bots between engines (this computer ↔ your server). A bundle carries the bot, its skills,
memory, results and browser sign-ins. Pairing: the other engine shows a 6-letter code; typing it here
returns that engine's API token over the local network."""
import time

import httpx

BUNDLE = 1


def pair_code(token):
    return "".join(c for c in token.upper() if c.isalnum())[:6]


def export_bot(engine, bid):
    b = engine.store.get("bots", bid)
    cookies = []
    try:
        cookies = engine.computer(bid).call("storage_state").get("cookies", [])
    except Exception:
        pass
    strip = ("id", "bot_id", "status", "key", "ts")
    clean = lambda r: {k: v for k, v in r.items() if k not in strip}
    return {"bundle": BUNDLE, "exported": time.time(), "bot": clean(b),
            "skills": [clean(s) for s in engine.store.find("skills", bot_id=bid, desc=False)],
            "results": [dict(clean(r), key=r["key"]) for r in engine.store.find("results", bot_id=bid, limit=2000)],
            "messages": [clean(m) for m in engine.store.find("messages", bot_id=bid, limit=200, desc=False)],
            "cookies": cookies}


def import_bot(engine, bundle):
    if bundle.get("bundle") != BUNDLE:
        raise ValueError("not an Inky bot bundle")
    bot = dict(bundle["bot"], computer="local", pending_cookies=bundle.get("cookies") or None, remote=None, remote_id=None)
    bid = engine.store.insert("bots", bot, status="idle")
    for s in bundle.get("skills", []):
        engine.store.insert("skills", s, bot_id=bid, status="ok")
    for r in bundle.get("results", []):
        key = r.pop("key", None)
        engine.store.insert("results", r, bot_id=bid, key=key)
    for m in bundle.get("messages", []):
        engine.store.insert("messages", m, bot_id=bid, status=m.get("role"))
    engine.store.event(bid, "arrived", f"{bot['name']} arrived with {len(bundle.get('skills', []))} skills")
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
    r = httpx.post(url.rstrip("/") + "/api/pair", json={"code": code.strip().upper()}, timeout=15)
    if r.status_code != 200:
        raise ValueError("that code didn’t match")
    info = r.json()
    return info["token"], info.get("name") or url


def move_bot(engine, bid, computer_id, progress=lambda step, **kw: None):
    """Pause → pack → send → start and check there → remove here. Returns the remote bot id."""
    comp = engine.store.get("computers", computer_id)
    remote = Remote(comp["url"], comp["token"])
    b = engine.store.get("bots", bid)
    engine.control(bid, "stop")
    progress("paused", text="Paused between two runs")
    bundle = export_bot(engine, bid)
    size = len(str(bundle))
    progress("packed", text=f"Packed its memory, {len(bundle['skills'])} skills and settings", size=size)
    rid = remote.req("POST", "/api/import", bundle, timeout=120)["bot"]["id"]
    progress("sent", text=f"Sent it to {comp['name']}")
    check = None
    if bundle["skills"]:
        check = remote.req("POST", f"/api/bots/{rid}/run", {"wait": True}, timeout=900).get("run")
        if not check or check.get("status") != "ok":
            progress("check_failed", text="The check run there didn’t pass, so it stays here too", run=check)
            raise RuntimeError("the check run on the server did not pass; nothing was removed here")
    progress("checked", text=f"Checked a run there: {check.get('items', 0) if check else 0} results")
    engine.close_computer(bid)
    engine.store.update("bots", bid, computer=computer_id, remote_id=rid, status="moved")
    engine.store.event(bid, "moved", f"{b['name']} now runs on {comp['name']}")
    progress("done", text=f"{b['name']} now runs on {comp['name']}")
    engine.bus.publish("bots")
    return rid
