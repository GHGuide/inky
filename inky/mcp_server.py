"""Inky as an MCP server, so Claude Code, Codex or any MCP client can use your bots.
Talks to the running engine's local API. Approving Needs-you items is deliberately not a tool.
Claude Code, one run:  claude -p "..." --mcp-config '{"mcpServers":{"inky":{"command":"<python>","args":["-m","inky.mcp_server"]}}}'
Codex, one run:        codex exec -c 'mcp_servers.inky.command="<python>"' -c 'mcp_servers.inky.args=["-m","inky.mcp_server"]' "..."

Answers are short JSON an agent can read at a glance: names, counts, prices, links, what's new. Every call returns well
within an MCP client's usual 60-second tool limit; a longer check keeps going in Inky and says how to pick it up."""
import json
import os
import time
from datetime import datetime
from pathlib import Path

import httpx

from inky.mcp import serve_stdio

HOME = Path(os.environ.get("INKY_HOME", "~/.inky")).expanduser()
URL = os.environ.get("INKY_URL", "http://127.0.0.1:8800")
WAIT = 45  # seconds a call waits for a check or a draft before handing back (clients give up at about 60)
INSTRUCTIONS = ("Inky runs bots that watch websites for the user: each bot learned its sites once with AI and now repeats "
                "the check on a schedule with no AI. Start with list_bots. bot_results shows what a bot found; run_bot checks "
                "again now; message_bot talks to a bot in plain words (\"only keep under €500\", \"check every hour\", "
                "\"pause\"). Bots ask before anything irreversible, and only the user can answer that, in the Inky app: "
                "list_needs shows what's waiting, but you can't approve it.")


class Gone(Exception):
    """Something the agent should read as a plain sentence, not a traceback."""


def engine_url():
    """The running engine's address from engine.json (the desktop app may pick a new port each start), else INKY_URL."""
    try:
        return json.loads((HOME / "engine.json").read_text(encoding="utf-8"))["url"]
    except (OSError, ValueError, KeyError):
        return URL


def api(method, path, body=None, timeout=60):
    token = (HOME / "api_token").read_text().strip() if (HOME / "api_token").exists() else ""
    url = engine_url()
    try:
        r = httpx.request(method, url + path, json=body, timeout=timeout, headers={"X-Inky-Token": token})
    except httpx.ConnectError:
        raise Gone(f"Inky isn't running on this computer (nothing answers at {url}). Open the Inky app, or run "
                   "`python -m inky`, then try again.")
    except httpx.TimeoutException:
        raise Gone("Inky took too long to answer. It's still working; try again in a minute.")
    if r.status_code == 401:
        raise Gone(f"Inky refused the call: the token in {HOME / 'api_token'} doesn't match the running Inky. "
                   "Point INKY_HOME at the folder of the Inky that's running.")
    if r.status_code >= 400:
        try:
            msg = r.json().get("error")
        except ValueError:
            msg = None
        raise Gone(msg or f"Inky answered {r.status_code} for {path}.")
    return r.json()


def when(ts):
    return datetime.fromtimestamp(ts).strftime("%a %d %b %H:%M") if ts else None


def find_bot(ref):
    """A bot by id or name, the loose way people say it: "books", "the ebike bot", "python jobs"."""
    bots = api("GET", "/api/bots")["bots"]
    ref = str(ref).strip().lower()
    exact = next((b for b in bots if str(b["id"]) == ref or b["name"].lower() == ref), None)
    if exact:
        return exact
    flat = lambda t: t.replace("-", "").replace("_", "")
    stem = lambda w: w[:-1] if len(w) > 3 and w.endswith("s") else w
    words = [stem(flat(w)) for w in ref.split() if w not in ("the", "my", "a", "bot", "bots", "one")]
    fits = lambda name: bool(words) and all(any(flat(n).startswith(w) or w.startswith(stem(flat(n))) for n in name.lower().split()) for w in words)
    hits = [b for b in bots if flat(ref) in flat(b["name"].lower())] or [b for b in bots if fits(b["name"])]
    if not hits:
        import difflib
        close = difflib.get_close_matches(ref, [x["name"].lower() for x in bots], n=1, cutoff=0.6)
        hits = [x for x in bots if close and x["name"].lower() == close[0]]
    if len(hits) > 1:
        raise Gone(f"More than one bot fits “{ref}”: {', '.join(b['name'] for b in hits)}. Say which, or use its id.")
    if not hits:
        raise Gone(f"No bot called “{ref}”. Your bots: {', '.join(x['name'] for x in bots) or 'none yet'}.")
    return hits[0]


def every(minutes):
    m = int(minutes or 0)
    return "only when asked" if not m else "every hour" if m == 60 else "every day" if m == 1440 else \
        f"every {m // 60} hours" if m % 60 == 0 else f"every {m} minutes"


def item(r):
    """What a person would want from one result: its name, price, link, whether it's new, and other short fields it has."""
    skip = {"id", "ts", "run", "skill", "bot_id", "key", "status", "passed", "text", "image", "last", "first"}
    out = {k: v for k, v in r.items() if k not in skip and v not in (None, "") and len(str(v)) < 200}
    out["new"] = bool(r.get("new"))
    return out


def summary(b):
    return {"id": b["id"], "name": b["name"], "job": b.get("job") or b.get("summary"), "status": b.get("status"),
            "found": b.get("found", 0), "new": b.get("fresh", 0), "sites": len(b.get("skills") or []),
            "checks": every((b.get("schedule") or {}).get("every_minutes")), "next_check": when(b.get("next_run")),
            "waiting_for_you": b.get("needs", 0), **({"runs_on": b["remote"]} if b.get("remote") else {})}


def list_bots(a):
    return json.dumps([summary(b) for b in api("GET", "/api/bots")["bots"]], ensure_ascii=False)


def get_bot(a):
    d = api("GET", f"/api/bots/{find_bot(a['bot'])['id']}")
    b = d["bot"]
    runs = [{"when": when(r.get("ts")), "what": "learned a site" if r.get("kind") == "learn" else "checked",
             "site": r.get("skill") or r.get("url"), "outcome": r.get("status"), "results": r.get("items"),
             "passed_rules": r.get("matched"), "new": r.get("new"), "ai_calls": r.get("ai_calls"), "note": r.get("note")}
            for r in d.get("runs", [])[:5]]
    msgs = [{"from": m.get("role"), "text": m.get("text", "")[:300]} for m in d.get("messages", [])[-6:]]
    return json.dumps({**summary(b), "rules": [f.get("text") or f"{f.get('field')} {f.get('op')} {f.get('value')}" for f in b.get("filters") or []],
                       "remembers": [m.get("text") for m in b.get("memory") or []],
                       "sites": [{"name": s["name"], "starts_at": s.get("start_url"), "steps": len(s.get("steps") or [])} for s in d.get("skills", [])],
                       "recent_runs": runs, "recent_chat": msgs,
                       "waiting_for_you": [{"question": n.get("title"), "options": n.get("options")} for n in d.get("needs", [])]},
                      ensure_ascii=False)


def message_bot(a):
    b = find_bot(a["bot"])
    r = api("POST", f"/api/bots/{b['id']}/chat", {"text": a["text"], "source": "mcp"}, timeout=WAIT + 10)
    done = r.get("done") or []
    return r["reply"] + (f"\n(It did: {'; '.join(done)})" if done else "")


def run_bot(a):
    b = find_bot(a["bot"])
    before = {r["id"] for r in api("GET", f"/api/bots/{b['id']}")["runs"]}
    api("POST", f"/api/bots/{b['id']}/run", {"skill": a.get("site") or a.get("skill")})
    t0 = time.time()
    while time.time() - t0 < WAIT:
        time.sleep(1.5)
        d = api("GET", f"/api/bots/{b['id']}")
        if not d["bot"].get("run_kind"):
            break
    else:
        return f"{b['name']} is still checking (it can take a few minutes on several sites). Ask bot_results in a minute."
    runs = [r for r in d["runs"] if r["id"] not in before]
    if not runs:
        return f"{b['name']} didn't start a check. {d['bot'].get('status') == 'needs_you' and 'It is waiting for you in the Inky app.' or ''}".strip()
    lines = []
    for r in runs:
        if r.get("status") == "ok" and r.get("items") is not None:
            lines.append(f"{r.get('skill') or 'its site'}: {r['items']} results, {r.get('matched', 0)} pass the rules, "
                         f"{r.get('new', 0)} new, {r.get('ai_calls') or 0} AI calls")
        else:
            lines.append(f"{r.get('skill') or r.get('url') or 'its site'}: {r.get('status')}" + (f" ({r['note']})" if r.get("note") else ""))
    fresh = [item(x) for x in api("GET", f"/api/bots/{b['id']}/results")["results"] if x.get("new")][:5]
    return json.dumps({"checked": lines, "newest": fresh, "waiting_for_you": d["bot"].get("needs", 0)}, ensure_ascii=False)


def bot_results(a):
    b = find_bot(a["bot"])
    rows = api("GET", f"/api/bots/{b['id']}/results")["results"]
    if a.get("only_new"):
        rows = [r for r in rows if r.get("new")]
    return json.dumps([item(r) for r in rows[: max(1, min(int(a.get("limit") or 50), 200))]], ensure_ascii=False)


def list_needs(a):
    needs = api("GET", "/api/needs")["needs"]
    rows = [{"bot": n.get("bot") or n.get("bot_id"), "question": n.get("title"), "details": (n.get("body") or "")[:300],
             "options": n.get("options"), "since": when(n.get("ts"))} for n in needs]
    return json.dumps({"waiting": rows, "note": "Only the user can answer these, in the Inky app."} if rows else {"waiting": []}, ensure_ascii=False)


def create_bot(a):
    job = api("POST", "/api/bots/from-job", {"job": a["job"], "site": a.get("site")})
    t0 = time.time()
    while job["status"] in ("drafting", "finding sites") and time.time() - t0 < WAIT:
        time.sleep(2)
        job = api("GET", f"/api/bots/from-job/{job['id']}")
    if job["status"] == "failed":
        return f"Inky couldn't make that bot: {job.get('error')}"
    if job["status"] in ("drafting", "finding sites"):
        return (f"Inky is still {job['status']} for this job (its model is slow right now). It carries on by itself; the bot shows up "
                f"in list_bots in a minute or two. (Check on it with create_bot_status, id {job['id']}.)")
    return made(job)


def made(job):
    if job["status"] == "needs a site":
        return (f"Created {job['name']}, but it needs a site to look at: none was named and none was found. Tell it one with message_bot, "
                f"e.g. “learn https://example.com”.")
    if job["status"] in ("drafting", "finding sites"):
        return f"Still {job['status']}. Try again in a minute."
    if job["status"] == "failed":
        return f"Inky couldn't make that bot: {job.get('error')}"
    sites = job.get("sites") or []
    return (f"Created {job['name']}. It's learning {len(sites)} site{'s' if len(sites) != 1 else ''} now ({', '.join(sites)}), which takes a "
            f"minute or two, then it checks {every(job.get('every_minutes'))} with no AI. Rules: {'; '.join(job.get('rules') or []) or 'none'}. "
            f"Use get_bot or bot_results on it later.")


def create_bot_status(a):
    return made(api("GET", f"/api/bots/from-job/{a['id']}"))


BOT = {"type": "string", "description": "The bot's name (or part of it) or id, as list_bots shows"}
TOOLS = {
    "list_bots": ("Your Inky bots: what each watches, how much it found and how much is new, when it checks next, and whether it's waiting for you. Start here.",
                  {"type": "object", "properties": {}}, list_bots, {"title": "List bots", "readOnlyHint": True, "openWorldHint": False}),
    "get_bot": ("One bot in detail: its job, rules, sites, what it remembers, its last runs and chat, and anything it's waiting for you on.",
                {"type": "object", "required": ["bot"], "properties": {"bot": BOT}}, get_bot, {"title": "Get a bot", "readOnlyHint": True, "openWorldHint": False}),
    "bot_results": ("What a bot has found: name, price, link and whether it's new, plus other fields the site shows. Your rules are already applied.",
                    {"type": "object", "required": ["bot"], "properties": {"bot": BOT, "only_new": {"type": "boolean", "description": "Only things that are new since the last check"},
                                                                         "limit": {"type": "integer", "description": "At most this many (default 50, max 200)"}}},
                    bot_results, {"title": "Bot results", "readOnlyHint": True, "openWorldHint": False}),
    "run_bot": ("Check a bot's sites again now (it repeats what it learned, with no AI) and say what's new. Takes seconds; very long checks carry on in Inky.",
                {"type": "object", "required": ["bot"], "properties": {"bot": BOT, "site": {"type": "string", "description": "Only this site (its name as get_bot lists it); default all"}}},
                run_bot, {"title": "Check now", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}),
    "message_bot": ("Talk to a bot in plain words and get its reply. It can change its rules (\"only keep under €500\"), schedule (\"every hour\"), pause, resume, "
                    "remember things, learn a new site or check now. Anything irreversible still needs the user's yes in the app.",
                    {"type": "object", "required": ["bot", "text"], "properties": {"bot": BOT, "text": {"type": "string", "description": "What you'd type in the bot's chat"}}},
                    message_bot, {"title": "Message a bot", "readOnlyHint": False, "destructiveHint": False, "openWorldHint": True}),
    "create_bot": ("Make a new bot from a job in plain words (\"tell me when Sony WH-1000XM5 drops below €250\"). Inky drafts it, finds sites if none is named, "
                   "and starts learning them; it's ready a minute or two later.",
                   {"type": "object", "required": ["job"], "properties": {"job": {"type": "string", "description": "The job, as the user would say it"},
                                                                        "site": {"type": "string", "description": "Optional: the site to start on (a full address)"}}},
                   create_bot, {"title": "Create a bot", "readOnlyHint": False, "destructiveHint": False, "openWorldHint": True}),
    "create_bot_status": ("How a bot that create_bot is still making is getting on (drafting, finding sites, learning).",
                          {"type": "object", "required": ["id"], "properties": {"id": {"type": "string", "description": "The id create_bot gave"}}},
                          create_bot_status, {"title": "Bot being made", "readOnlyHint": True, "openWorldHint": False}),
    "list_needs": ("What your bots are waiting for you on (a yes before sending, a sign-in only you can do). Read only: the user answers in the Inky app.",
                   {"type": "object", "properties": {}}, list_needs, {"title": "Needs you", "readOnlyHint": True, "openWorldHint": False}),
}
ALIASES = {"run_skill": "run_bot"}  # its name in 0.1.0


def main():
    from inky import __version__
    serve_stdio("inky", __version__, TOOLS, instructions=INSTRUCTIONS, aliases=ALIASES, errors=(Gone,))


if __name__ == "__main__":
    main()
