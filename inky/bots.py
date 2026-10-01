"""The bot runtime: creating bots, chatting, learning, running, approvals, problems, take over, scheduling."""
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path

import httpx

from inky import connectors, skills
from inky.bus import Bus
from inky.computer import Computer
from inky.keys import Keys
from inky.llm import LLM, NoModel, plain as llm_plain
from inky.mcp import MCPManager
from inky.safety import classify
from inky.store import Store
from inky import persona as persona_mod
from inky import growth, insights
from inky.insights import quiet

LOOKS = [("octopus", "#E9A23B", "glasses"), ("cat", "#7C6CF2", "none"), ("blob", "#2BA59B", "headphones"),
         ("octopus", "#3B5BDB", "beanie"), ("cat", "#F07BA8", "bow"), ("blob", "#E86F51", "none")]
DEFAULT_LOOK = {"tone": "cheerful", "voice": "soft", "frame": "coral", "cursor": "name", "labels": True, "speed": "normal",
                "kind": "octopus", "color": "#E86F51", "acc": "none"}
DEFAULT_RULES = [{"kind": "own", "text": "Read, search, take notes"},
                 {"kind": "ask", "text": "Send, post, reply, delete, submit forms, sign up"},
                 {"kind": "never", "text": "Buy or pay"}]
CORAL = "#E86F51"


def close_match(target, text):
    """For forget / remove rule: the thing meant ("I prefer paperbacks" ≈ "User prefers paperbacks"), never a few letters."""
    return match_score(target, text) >= 0.6


def match_score(target, text):
    a, b = (target or "").strip().lower(), (text or "").strip().lower()
    if len(a) < 3:
        return 0
    if a == b or (a in b and len(a) >= 0.4 * len(b)) or (b in a and len(b) >= 0.4 * len(a)):
        return 1
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0
    return sum(any(_same_word(x, y) for y in wb) for x in wa) / len(wa)


def best_match(target, items, key=lambda x: x):
    """The single closest item (score ≥ 0.6), or None."""
    scored = sorted(((match_score(target, key(i)), n) for n, i in enumerate(items)), reverse=True)
    return scored[0][1] if scored and scored[0][0] >= 0.6 else None


class Guard(ValueError):
    """The model proposed something you didn't ask for: dropped quietly."""


RULE_STOP = {"before", "first", "always", "never", "ask", "asks", "with", "that", "this", "from", "what", "when", "your", "them",
             "they", "have", "about", "into", "only", "anything", "something", "things", "without", "permission", "please",
             "don't", "dont", "must", "should", "make", "sure", "just", "click", "clicks", "open", "opens", "press", "type",
             "read", "page", "pages", "site", "sites", "button", "buttons", "link", "links", "any", "every", "time", "times"}


SHORT_STOP = {"the", "and", "for", "you", "any", "all", "not", "but", "can", "its", "it's", "our", "out", "one", "get", "let", "use", "who", "how", "why", "too", "off", "via", "per", "ask", "me"}


def _same_word(a, b):  # contact/contacting, book/booking/books
    if min(len(a), len(b)) < 4:
        return a == b or (len(a) == 3 and b in (a + "s", a + "es")) or (len(b) == 3 and a in (b + "s", b + "es"))  # ad/ads
    return a[:5] == b[:5] or a.startswith(b) or b.startswith(a)


def _words(t):
    return [w for w in re.findall(r"[^\W\d_]{3,}", (t or "").lower()) if w not in RULE_STOP and w not in SHORT_STOP]
DEFAULT_RULE_TEXTS = {r["text"] for r in DEFAULT_RULES}


def rule_hit(rules, kind, text):
    """Your own Ask first / Never rules, matched by their key words against what a step does
    ("Ask before contacting agencies" matches "Click Contact agency"). The built-in defaults are handled by safety.classify."""
    said = _words(text)
    for r in rules or []:
        if r.get("kind") != kind or r.get("text") in DEFAULT_RULE_TEXTS:
            continue
        if any(_same_word(w, x) for w in _words(r.get("text")) for x in said):
            return r
    return None


def is_question(t):
    t = (t or "").strip().lower()
    return t.endswith("?") or bool(re.match(r"^(what|how|did|do|does|when|why|which|who|where|is|are|was|were|can|could|have|has)\b", t))


ACTIONS = {"add_rule", "remove_rule", "remember", "forget", "learn", "run", "schedule", "pause", "resume", "stop", "speed",
           "delegate", "ask_bot", "add_automation"}
CHANGES = ACTIONS - {"remember", "learn", "ask_bot"}  # those two have their own checks; asking another bot changes nothing
POLITE = re.compile(r"\s*(can|could|would|will) you\b(?!.*\b(better|faster|worth|good idea)\b)|.*\bplease\b", re.I)
REMOVING = re.compile(r"\b(remove|delete|drop|no longer|get rid of|forget|scrap|cancel|undo|take (out|off|away))\b", re.I)
LIMIT = re.compile(r"^\s*(?:only (?:keep |show )?(?:\w+ )?)?(\w+)\s+(under|below|less than|at most|over|above|more than|at least|<=|<|>=|>)"
                   r"\s*[£€$]?\s*(\d+(?:[.,]\d+)?)\s*[£€$]?\s*$", re.I)


def limit_filter(text):
    """“price under 15” → a filter on results, or None."""
    m = LIMIT.match(text or "")
    if not m:
        return None
    op = {"under": "<", "below": "<", "less than": "<", "<": "<", "at most": "<=", "<=": "<=",
          "over": ">", "above": ">", "more than": ">", ">": ">", "at least": ">=", ">=": ">="}[m.group(2).lower()]
    return {"field": m.group(1).lower(), "op": op, "value": float(m.group(3).replace(",", "."))}


def every_words(m):
    """60 → “hour”, 120 → “2 hours”, 5 → “5 minutes”: what follows “every”."""
    n, unit = (m // 1440, "day") if m % 1440 == 0 else (m // 60, "hour") if m % 60 == 0 else (m, "minute")
    return unit if n == 1 else f"{n} {unit}s"


def nres(n):
    return f"{n} result{'' if n == 1 else 's'}"


def plain_error(e):
    """What went wrong, in words: browser and network errors are long and technical."""
    t = str(e)
    if "Locator." in t and ("Timeout" in t or "timeout" in t):
        return "Couldn’t click it: the button moved, or something covered it. Show it once, or try again."
    if "Timeout" in type(e).__name__ or "Timeout " in t or "timed out" in t:
        return "The page took too long to answer. The site may be slow or down right now; try again in a bit."
    m = re.search(r"net::ERR_(\w+)", t)
    if m:
        why = {"NAME_NOT_RESOLVED": "that address doesn’t exist", "CONNECTION_REFUSED": "nothing answered there",
               "INTERNET_DISCONNECTED": "this computer is offline", "ADDRESS_UNREACHABLE": "that address can’t be reached"}
        return f"Couldn’t open the site: {why.get(m.group(1), m.group(1).replace('_', ' ').lower())}."
    if "has been closed" in t:
        return "Its browser closed while it was working. Try again."
    if "invalid URL" in t:
        return "It tried to open something that isn’t a web address."
    if "did not return JSON" in t:
        return "The model’s answers didn’t make sense. Try again, show it once, or pick a smarter model in Models."
    return f"Something went wrong ({type(e).__name__}): {t.splitlines()[0][:200] if t else 'no details'}"


def minutes(v):
    """How often, in whole minutes (0 = only when you ask). Words a model might write are understood too:
    "every 2 hours" 120, "6h" 360, "twice a day" 720, "every morning" 1440, "every 3 days" 4320."""
    if isinstance(v, str):
        t = v.lower().strip()
        if t.startswith("-"):
            return 0
        m = re.search(r"(\d+(?:\.\d+)?)\s*(m|min|mins|minutes?|h|hrs?|hours?|d|days?|w|weeks?)\b", t)
        if m:
            unit = {"m": 1, "h": 60, "d": 1440, "w": 10080}[m.group(2)[0]]
            return max(0, min(int(float(m.group(1)) * unit), 525600))
        if "twice" in t and "day" in t:
            return 720
        if re.search(r"morning|daily|day|night|evening|monday|tuesday|wednesday|thursday|friday|saturday|sunday", t):
            return 10080 if re.search(r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|week", t) else 1440
        if "hour" in t:
            return 60
        if "week" in t:
            return 10080
        v = re.sub(r"[^\d.]", "", t) or 0
    try:
        return max(0, min(int(float(v)), 525600))
    except (TypeError, ValueError):
        return 0

DRAFT_SYSTEM = """You turn a job description into a bot. Reply with ONE JSON object:
{"name": "<2 words, e.g. Flat Hunter>", "summary": "<one sentence of what it will do>", "goal": "<what to search and read on the site>",
 "start_url": "<the site to start on, full URL, or null if unknown>", "every_minutes": <a number of minutes: 1440 for daily or every morning, 60 for hourly, 0 for only when asked>, "summary_at": "<HH:MM or null>",
 "filters": [{"field": "<price|size|title|…>", "op": "<|<=|>|>=|==|contains|not_contains|in|not_in", "value": <number|string|list>, "text": "<the rule in words>"}],
 "ask_first": ["<things it must ask before>"], "questions": ["<at most 2 short questions if something important is missing>"],
 "persona": {"chatty": <0-1>, "playful": <0-1>, "emoji": <true|false>, "catchphrase": "<short, fits the job>", "quirk": "<one line>", "bio": "<one line, first person>"}}"""

CHAT_SYSTEM = """You are {name}, an Inky bot with its own computer (a browser). Your job: {job}.
Talk {tone}. Keep replies short (1–3 sentences). You can take actions. Reply with ONE JSON object:
{{"reply": "<what you say>", "actions": [<zero or more actions>]}}
Actions:
{{"type":"add_rule","text":"<rule in words>","kind":"own|ask|never","filter":{{"field":..,"op":..,"value":..}} or null}}   (op: < <= > >= == != contains not_contains in not_in; kind ask = ask the user first, never = never do it)
{{"type":"remove_rule","text":"<rule to drop>"}}
{{"type":"remember","text":"<fact about the user>"}}   {{"type":"forget","text":"<fact>"}}
{{"type":"learn","goal":"<what to do on the site>","url":"<start URL>"}}   (learn a new site/search once)
{{"type":"run"}}  (check now)   {{"type":"schedule","every_minutes":<n>}}  (add "summary_at":"HH:MM", "quiet_from"/"quiet_to":"HH:MM" only if the user asks; "" turns one off)
{{"type":"pause"}} {{"type":"resume"}} {{"type":"stop"}} {{"type":"speed","value":"slow|normal|turbo"}}
{{"type":"delegate","server":"<connector>","tool":"<tool>","args":{{...}},"label":"<what you hand over>"}}   (hand a job to Claude Code, Codex or another connector now)
{{"type":"add_automation","when":"new_results|every_run","server":..,"tool":..,"args":{{...}},"label":".."}}   (use {{{{new_json}}}}, {{{{count}}}}, {{{{bot}}}} in args)
{{"type":"ask_bot","bot":"<other bot's name>","text":"<what you need or want to tell it>"}}   (talk to another bot; anything irreversible still needs the user's yes)
Only take actions the user's LATEST message asks for; talking about earlier ones is not a reason to repeat them.
Only use tools that are listed. Result fields you have seen: {fields}.
YOUR RULES: {rules}
WHAT YOU REMEMBER: {memory}
YOUR SKILLS: {skills}
STATUS: {status}
OTHER BOTS (your team): {others}
CONNECTED TOOLS:
{tools}"""


class Run:
    def __init__(self, kind, skill_id=None):
        self.kind, self.skill_id = kind, skill_id
        self.paused = threading.Event()
        self.stop = False
        self.takeover = False
        self.fixes = []
        self.step = ""
        self.n = 0
        self.ai_calls = 0
        self.tokens = 0
        self.cost = 0.0
        self.started = time.time()
        self.thread = None
        self.need = None
        self.run_id = None


class Ctx:
    """What skills.learn/replay see: the bot's computer, the model, and the safety gate."""

    def __init__(self, engine, bot_id, run):
        self.e, self.bot_id, self.run = engine, bot_id, run
        self.computer = engine.computer(bot_id)
        self.llm = engine.llm
        self.bot = engine.store.get("bots", bot_id)

    def emit(self, kind, text, step=None, **meta):
        self.run.step, self.run.n = text, step or self.run.n
        self.e.store.event(self.bot_id, kind, text, step=step, run=self.run.run_id, **meta)
        self.e.bus.publish("run", bot=self.bot_id, ev=kind, text=text, step=step, ai=self.run.ai_calls)
        self.e.overlay_step(self.bot_id, text)

    def check(self):
        while self.run.paused.is_set() and not self.run.stop:
            time.sleep(0.2)
        if self.run.stop:
            raise skills.Stopped()

    def corrections(self):
        out, self.run.fixes = self.run.fixes, []
        return out

    def gate(self, step, el, page):
        verdict, why = classify(step["action"], el, page)
        name = self.bot["name"]
        said = f"{step.get('text') or ''} {(el or {}).get('name') or ''}"
        never = rule_hit(self.bot.get("rules", []), "never", said)
        if never and step["action"] != "goto":
            raise skills.NeedsHelp("blocked", f"{name} stopped before “{step.get('text')}”", f"Your rule says: {never['text']}.", ["OK"])
        ask = rule_hit(self.bot.get("rules", []), "ask", said)
        if verdict == "ok" and ask and step["action"] in ("click", "press", "fill", "select"):
            verdict, why = "irreversible", f"Your rule says: {ask['text']}"
        if verdict == "ok":
            return
        if verdict in ("irreversible", "pay", "password") and getattr(self.run, "check", False):  # a check never asks or acts: it stops here
            raise skills.CheckedUpTo(step.get("text") or "a step")
        if verdict == "robot":
            raise skills.NeedsHelp("robot", "The site shows a robot check", "Bots don’t solve these. Solve it once on its computer, then press Hand back.",
                                   ["Open its computer", "Skip"])
        if verdict == "password":
            raise skills.NeedsHelp("sign_in", f"{name} needs you to sign in",
                                   "Bots never see or type your passwords. Sign in yourself on its computer and it keeps the session.",
                                   ["Open its computer", "Later"])
        if verdict == "pay" and not any(r["kind"] == "own" and "pay" in r["text"].lower() for r in self.bot.get("rules", [])):
            raise skills.NeedsHelp("blocked", f"{name} stopped before paying", f"{why}. Your rules say it never buys or pays.", ["OK"])
        if step.get("approved_always"):
            return
        preview = self.computer.call("extract", {"item": "form", "fields": {"text": "textarea@value"}}) if el else []
        body = f"{why}. On {page.get('url', '')}."
        typed = next((r["text"] for r in preview if r.get("text")), None)
        if typed:
            body += f" Message: “{typed[:280]}”"
        what = step["text"][:1].lower() + step["text"][1:] if step["text"][1:2].islower() else step["text"]
        decision = self.e.ask(self.bot_id, "decision", f"{name} wants to {what}", body,
                              ["Approve", "Always for this step", "Deny"], run=self.run, step=step.get("text"))
        if decision not in ("Approve", "Always for this step"):  # only a clear yes goes ahead
            raise skills.NeedsHelp("denied", f"Stopped before it could {what}", "You said no, so nothing was sent.", [])
        if decision == "Always for this step":
            step["approved_always"] = True


class Engine:
    def __init__(self, home):
        self.home = Path(home).expanduser()
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "profiles").mkdir(exist_ok=True)
        tok = self.home / "api_token"
        if not tok.exists():
            tok.write_text(secrets.token_urlsafe(24))
            tok.chmod(0o600)
        self.token = tok.read_text().strip()
        self.store = Store(str(self.home / "inky.db"))
        self.bus = Bus()
        self.store.on_event = lambda bid, kind, text: self.bus.publish("event", bot=bid, ev=kind, text=text)
        self.keys = Keys(self.home)
        self.llm = LLM(self.store, self.keys, on_usage=self._usage)
        self.mcp = MCPManager(self.store, str(self.home))
        self.mcp.builtin = connectors.Builtins(self)
        self.computers, self.runs, self.waits = {}, {}, {}
        for r in self.store.find("runs", status="running", limit=1000):  # a restart ended them: say so instead of "running" forever
            self.store.update("runs", r["id"], status="stopped", note="Inky restarted")
        self.hops = {}  # (from bot, to bot) -> times, so two bots can't talk in circles
        self.lock = threading.RLock()
        self._sched = None

    # ---------------------------------------------------------- bots
    def bot_view(self, b):
        run = self.runs.get(b["id"])
        sk = self.store.find("skills", bot_id=b["id"])
        needs = self.store.find("needs", bot_id=b["id"], status="open")
        status = b.get("status") or "idle"
        live = bool(run and run.thread and run.thread.is_alive())
        if live and run.need:  # it's waiting on your yes
            status = "needs_you"
        elif live and run.kind == "show":
            status = "showing"
        elif live and run.takeover:
            status = "takeover"
        elif live:
            status = "paused" if run.paused.is_set() else ("learning" if run.kind == "learn" else "working")
        elif run and run.takeover:  # you have its computer between runs
            status = "takeover"
        elif needs:
            status = "needs_you"
        sched = b.get("schedule") or {}
        nxt = None
        if sched.get("every_minutes") and sk and b.get("status") != "moved":
            nxt = max(time.time(), (b.get("last_run") or 0) + sched["every_minutes"] * 60)  # never ran: due now
            end = sched.get("quiet_to")
            if end and quiet(datetime.fromtimestamp(nxt).strftime("%H:%M"), sched.get("quiet_from"), end):
                h, m = map(int, end.split(":"))  # quiet hours: the first run after they end
                t = datetime.fromtimestamp(nxt).replace(hour=h, minute=m, second=0)
                nxt = t.timestamp() if t.timestamp() > nxt else t.timestamp() + 86400
        return {**{k: b.get(k) for k in ("id", "name", "job", "summary", "goal", "start_url", "rules", "filters", "memory",
                                         "schedule", "automations", "mode", "computer", "last_run", "created", "allowed_domains", "library")},
                "look": {**DEFAULT_LOOK, **(b.get("look") or {})},  # older bots get every part of a look
                "persona": persona_mod.normalize(b.get("persona"), (b.get("look") or {}).get("kind", "octopus")),
                "status": status, "step": run.step if live else "", "step_n": run.n if live else 0,
                "skills": [s["name"] for s in sk], "needs": len(needs), "next_run": nxt,
                "need_kind": ("decision" if needs[0].get("kind") == "decision" else "problem") if needs else None,
                "unlocked": growth.unlocked(len(growth.ok_runs(self.store.find("runs", bot_id=b["id"], status="ok", limit=600)))),
                "ai_calls": run.ai_calls if run else 0, "takeover": bool(run and run.takeover),
                "run_kind": run.kind if run and run.thread and run.thread.is_alive() else None,
                "skill_id": run.skill_id if run else None, "shown": len(getattr(run, "show", None) or []) if run else 0,
                "remote_id": b.get("remote_id")}

    def bots(self):
        return [self.bot_view(b) for b in self.store.find("bots", desc=False)]

    def draft_bot(self, job):
        try:
            d, _ = self.llm.ask_json("chat", DRAFT_SYSTEM, job)
        except (NoModel, httpx.HTTPError, ValueError):
            url = re.search(r"https?://\S+|\b[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}(?:/\S*)?", job, re.I)
            words = [w for w in re.findall(r"[A-Za-z]+", job) if len(w) > 3][:2]
            d = {"name": " ".join(w.title() for w in words) or "New Bot", "summary": job[:140], "goal": job,
                 "start_url": url and url.group(0).rstrip(".,)"), "every_minutes": 0, "filters": [], "questions": [],
                 "notice": "I couldn’t reach my model, so this is a rough draft from your words. Check Models."}
        n = len(self.store.find("bots"))
        kind, color, acc = LOOKS[n % len(LOOKS)]
        d.setdefault("look", {"kind": kind, "color": color, "acc": acc})
        d["job"] = job
        d["every_minutes"] = minutes(d.get("every_minutes"))
        if d.get("start_url") and not skills.web_address(d["start_url"], ""):
            d["start_url"] = None
        return d

    def create_bot(self, d):
        if d.get("start_url"):
            d = {**d, "start_url": skills.web_address(d["start_url"], "") or None}
        rules = list(DEFAULT_RULES) + [{"kind": "ask", "text": t} for t in d.get("ask_first") or []]
        rules += [{"kind": "filter", "text": f.get("text") or f"{f['field']} {f['op']} {f['value']}"} for f in d.get("filters") or []]
        look = {**DEFAULT_LOOK, **(d.get("look") or {})}
        bot = {"name": (d.get("name") or "New Bot").strip()[:40], "job": d.get("job") or d.get("summary") or "",
               "summary": d.get("summary") or "", "goal": d.get("goal") or d.get("job") or "", "start_url": d.get("start_url"),
               "look": look, "rules": rules, "filters": d.get("filters") or [], "memory": [], "automations": [],
               "schedule": {"every_minutes": minutes(d.get("every_minutes")), "summary_at": d.get("summary_at") or "08:00",  # the morning paper
                            "quiet_from": "23:00", "quiet_to": "07:00"},
               "mode": "own", "computer": "local", "created": time.time(),
               "persona": persona_mod.normalize(d.get("persona"), look.get("kind", "octopus"))}
        bid = self.store.insert("bots", bot, status="idle")
        self.store.event(bid, "created", f"Created {bot['name']}")
        p = bot["persona"]  # it hatches and says hello in its own words
        dot = lambda x: x if not x or x[-1] in ".!?…" else x + "."  # each part is its own sentence
        self.store.message(bid, "bot", " ".join(dot(x.strip()) for x in (f"Hi! I'm {bot['name']}.", p.get("bio") or bot["summary"]) if x and x.strip()), intro=True)
        self.bus.publish("bots")
        return self.bot_view(self.store.get("bots", bid))

    def update_bot(self, bid, patch):
        b = self.store.get("bots", bid)
        allowed = {"name", "job", "summary", "goal", "start_url", "look", "rules", "filters", "memory", "schedule", "automations", "mode", "computer", "persona"}
        patch = {k: v for k, v in patch.items() if k in allowed}
        if "look" in patch:
            patch["look"] = {**b.get("look", {}), **patch["look"]}
        if "schedule" in patch:
            patch["schedule"] = {**(b.get("schedule") or {}), **(patch["schedule"] or {})}
            patch["schedule"]["every_minutes"] = minutes(patch["schedule"].get("every_minutes"))
        if patch.get("start_url"):
            patch["start_url"] = skills.web_address(patch["start_url"], "") or b.get("start_url")
        if "name" in patch:
            patch["name"] = (str(patch["name"]).strip() or b["name"])[:40]
        if "persona" in patch:
            kind = (patch.get("look") or b.get("look") or {}).get("kind", "octopus")
            patch["persona"] = persona_mod.normalize({**(b.get("persona") or {}), **patch["persona"]}, kind)
        self.store.update("bots", bid, **patch)
        every = (patch.get("schedule") or {}).get("every_minutes")
        if "schedule" in patch and every != (b.get("schedule") or {}).get("every_minutes"):
            when = {0: "only when you ask", 15: "every 15 minutes", 60: "every hour", 1440: "once a day"}.get(every or 0, f"every {every} minutes")
            self.store.message(bid, "note", f"You changed the schedule: {when}.")  # so the bot knows it was on purpose
            self.bus.publish("messages", bot=bid)
        if "mode" in patch and patch["mode"] != b.get("mode"):
            self.close_computer(bid)
        if "look" in patch and bid in self.computers:
            self.computers[bid].look = patch["look"]
            self.apply_overlay(bid)
        self.bus.publish("bots")
        return self.bot_view(self.store.get("bots", bid))

    def delete_bot(self, bid):
        self.control(bid, "stop")
        run = self.runs.pop(bid, None)
        if run and run.thread:
            run.thread.join(15)  # let it finish writing before its rows go
        self.close_computer(bid)
        for t in ("skills", "runs", "results", "messages", "events", "needs", "diary"):
            self.store.delete(t, bot_id=bid)
        self.store.delete("bots", bid)
        self.bus.publish("bots")

    # ---------------------------------------------------------- computers
    def computer(self, bid):
        with self.lock:
            c = self.computers.get(bid)
            if c and c.alive:
                return c
            b = self.store.get("bots", bid)
            headful = b.get("mode") == "screen" and not os.environ.get("INKY_HEADLESS")  # INKY_HEADLESS: tests, servers
            c = Computer(bid, self.home / "profiles" / f"bot-{bid}", look=b.get("look"), headful=headful,
                         on_frame=None, on_control=self._on_control)
            self.computers[bid] = c
            if b.get("pending_cookies"):
                c.call("add_cookies", b["pending_cookies"])
                self.store.update("bots", bid, pending_cookies=None)
            self.apply_overlay(bid)
            return c

    def close_computer(self, bid):
        c = self.computers.pop(bid, None)
        if c:
            c.close()

    def apply_overlay(self, bid, **extra):
        c = self.computers.get(bid)
        if not c:
            return
        b = self.store.get("bots", bid)
        look = b.get("look", {})
        frame = CORAL if look.get("frame", "coral") == "coral" else look.get("color", CORAL)
        run = self.runs.get(bid)
        state = {"frame": frame, "cursor": look.get("cursor", "name"), "labels": look.get("labels", True), "name": b["name"],
                 "mode": "screen" if b.get("mode") == "screen" else "own", "paused": bool(run and run.paused.is_set()),
                 "pill": {"title": f"{b['name']} is using your screen", "sub": run.step if run else "ready"}}
        state.update(extra)
        try:
            c.call("overlay", **state, timeout=10)
        except Exception:
            pass

    def overlay_step(self, bid, text):
        b = self.store.get("bots", bid)
        self.apply_overlay(bid, step=text, pill={"title": f"{b['name']} is using your screen", "sub": text})

    def _on_control(self, bid, msg):
        t = msg.get("type")
        if t == "chat":
            reply = self.chat(bid, msg.get("text", ""), source="overlay")["reply"]
            try:
                self.computers[bid].call("say", reply, timeout=10)
            except Exception:
                pass
        elif t == "user_input":
            run = self.runs.get(bid)
            if run and run.thread and run.thread.is_alive() and not run.paused.is_set():
                self.control(bid, "takeover", reason="You moved the mouse, so I paused.")
        elif t in ("pause", "stop", "takeover", "resume", "handback"):
            run = self.runs.get(bid)
            if t == "pause" and run and run.paused.is_set():
                t = "resume"
            self.control(bid, t)

    # ---------------------------------------------------------- usage
    def _usage(self, bid, u):
        run = self.runs.get(bid) if bid else None
        if run:
            run.ai_calls += 1
            run.tokens += (u.get("in") or 0) + (u.get("out") or 0)
            run.cost += u.get("cost") or 0
        day = datetime.now().strftime("%Y-%m-%d")
        log = self.store.setting("usage", {})
        d = log.setdefault(day, {"calls": 0, "tokens": 0, "cost": 0.0, "local": 0})
        d["calls"] += 1
        d["tokens"] += (u.get("in") or 0) + (u.get("out") or 0)
        d["cost"] += u.get("cost") or 0
        d["local"] += 1 if u.get("local") else 0
        self.store.set_setting("usage", dict(list(log.items())[-60:]))
        self.store.event(bid, "ai", f"{u['role']} · {u['model']}", tokens=(u.get("in") or 0) + (u.get("out") or 0),
                         cost=u.get("cost"), seconds=u.get("seconds"), local=u.get("local"))

    # ---------------------------------------------------------- needs you
    def ask(self, bid, kind, title, body, options, run=None, **meta):
        """Open a Needs-you item and block until it is answered (or the run stops)."""
        nid = self.store.insert("needs", {"kind": kind, "title": title, "body": body, "options": options, **meta}, bot_id=bid, status="open")
        ev = threading.Event()
        self.waits[nid] = ev
        if run:
            run.need = nid
        self.store.message(bid, "bot", title, need=nid)
        self.bus.publish("needs", bot=bid)
        self.notify(bid, f"{title}\n{body}")
        while not ev.wait(0.5):
            if run and run.stop:
                self.store.update("needs", nid, status="resolved", decision="stopped")
                raise skills.Stopped()
        if run:
            run.need = None
        return self.store.get("needs", nid).get("decision")

    def problem(self, bid, h, **meta):
        if h.kind == "denied":  # you already decided: just say so, nothing to answer
            self.store.message(bid, "bot", f"{h.title}. {h.body}")
            self.store.event(bid, "denied", h.title)
            self.bus.publish("messages", bot=bid)
            return None
        roles = self.llm.roles()
        opts = [o for o in h.options if not (o == "Try a smarter model" and roles.get("smart") == roles.get("repair"))]  # same model: no point
        if not (meta.get("skill_id") or h.meta.get("skill_id")):  # nothing to replay up to: showing it once can't record anything
            opts = [o for o in opts if o != "Show me once"] or ["Try again"]
        nid = self.store.insert("needs", {"kind": h.kind, "title": h.title, "body": h.body, "options": opts, **h.meta, **meta},
                                bot_id=bid, status="open")
        self.store.message(bid, "bot", f"{h.title}. {h.body}", need=nid)
        self.store.event(bid, "problem", h.title, need=nid)
        self.bus.publish("needs", bot=bid)
        self.notify(bid, f"{h.title}\n{h.body}")
        return nid

    def resolve(self, nid, decision, bot_id=None):
        n = self.store.get("needs", nid)
        if not n or (bot_id is not None and n["bot_id"] != bot_id):
            raise KeyError(nid)
        if n.get("status") != "open":
            raise ValueError("That was already answered.")
        if n.get("options") and decision not in n["options"]:
            raise ValueError(f"“{decision}” isn’t one of the answers.")
        self.store.update("needs", nid, status="resolved", decision=decision)
        self.store.event(n["bot_id"], "answered", f"You chose “{decision}”: {n['title']}", need=nid, decision=decision)
        ev = self.waits.pop(nid, None)
        if ev:
            ev.set()
        else:
            for r in self.store.find("runs", bot_id=n["bot_id"], status="needs_you", limit=5):  # the run that stopped for this
                self.store.update("runs", r["id"], status="stopped", note=f"You answered: {decision}")
            self._follow_up(n, decision)
        self.bus.publish("needs", bot=n["bot_id"])
        return self.store.get("needs", nid)

    def _follow_up(self, n, decision):
        """Answers to Problems (the run already ended)."""
        bid = n["bot_id"]
        if decision in ("Try a smarter model", "Try again"):
            smart = decision == "Try a smarter model"
            try:
                if n.get("skill_id"):
                    self.run(bid, n["skill_id"], repair_role="smart" if smart else "repair", reason="you asked me to try again")
                elif n.get("url"):  # learning never finished: learn again
                    self.learn(bid, n.get("goal") or (self.store.get("bots", bid) or {}).get("goal"), n["url"])
                else:
                    self.run(bid, reason="you asked me to try again")
            except (RuntimeError, ValueError) as e:
                self.store.message(bid, "bot", f"I couldn’t try again: {e}.")
                self.bus.publish("messages", bot=bid)
        elif decision in ("Show me once",):
            self.start_show(bid, n)
        elif decision in ("Open its computer",):
            self.store.update("bots", bid, resume_after_handback=True)
            self.control(bid, "takeover", reason="You have its computer. Press Hand back when you’re done, and I’ll carry on.")

    # ---------------------------------------------------------- chat
    def chat(self, bid, text, source="app", sender=None):
        """sender=(bot id, name) when another bot is talking, not you."""
        b = self.store.get("bots", bid)
        if sender:
            self.store.message(bid, "peer", text, source=source, sender=sender[1], sender_id=sender[0], team=True)
        else:
            self.store.message(bid, "you", text, source=source)
        self.bus.publish("messages", bot=bid)
        run = self.runs.get(bid)
        if run and run.kind == "learn" and run.thread and run.thread.is_alive():
            run.fixes.append(text)
        results = [r for r in self.store.find("results", bot_id=bid, limit=10) if r.get("passed") is not False][:3]
        fields = sorted({k for r in results for k in r if k not in ("id", "bot_id", "status", "key", "ts", "run", "skill", "new")})
        sk = self.store.find("skills", bot_id=bid)
        hist = [m for m in reversed(self.store.find("messages", bot_id=bid, limit=12))]
        saved = sum(1 for r in self.store.find("results", bot_id=bid, limit=2000) if r.get("passed") is not False)
        status = self.bot_view(b)["status"] + (f" · {run.step}" if run and run.step else "") + \
            ("" if saved else ". You have NO results yet: never say you found anything." + ("" if sk else " You haven’t learned a site yet."))
        last = next((r for r in self.store.find("runs", bot_id=bid, limit=5) if r.get("kind") == "replay" and r.get("status") == "ok"), None)
        if last:
            status += (f". Last run {datetime.fromtimestamp(last['ts']).strftime('%a %H:%M')}: {last.get('items', 0)} results, "
                       f"{last.get('matched', 0)} pass the rules, {last.get('new', 0)} new, {last.get('ai_calls', 0)} AI calls. "
                       f"Results saved so far: {sum(1 for r in self.store.find('results', bot_id=bid, limit=2000) if r.get('passed') is not False)}")
        sys = CHAT_SYSTEM.format(name=b["name"], job=b.get("job", ""), tone=b.get("look", {}).get("tone", "cheerful"),
                                 fields=", ".join(fields) or "none yet", rules="; ".join(r["text"] for r in b.get("rules", [])),
                                 memory="; ".join(m["text"] for m in b.get("memory", [])) or "nothing yet",
                                 skills="; ".join(f"{s['name']} ({len(s['steps'])} steps)" for s in sk) or "none yet",
                                 status=status, tools="\n".join(self.mcp.catalog()) or "none",
                                 others="; ".join(f"{o['name']} ({(o.get('job') or '')[:70]}; {o['status'].replace('_', ' ')})" for o in self.bots() if o["id"] != bid) or "none")
        def worth_remembering(e):  # run summaries, not every step
            if e.get("kind") == "replay":
                return "pass your rules" in e.get("text", "") or e.get("text", "").startswith("Done in")
            return e.get("kind") in ("learned", "fixed", "problem", "level")
        notable = [e for e in reversed(self.store.find("events", bot_id=bid, limit=200))
                   if e["ts"] > time.time() - 3 * 86400 and worth_remembering(e)]
        sys += "\n" + persona_mod.prompt_lines(b, self.store.setting("app", {}).get("user_name", ""), datetime.now(), notable)
        msgs = [{"role": "system", "content": sys}] + [
            {"role": "assistant", "content": m["text"]} if m["role"] == "bot" else
            {"role": "user", "content": f"[settings note] {m['text']}" if m["role"] == "note" else
             f"(from {m.get('sender')}, another bot) {m['text']}" if m["role"] == "peer" else m["text"]} for m in hist[:-1]] + [
            {"role": "user", "content": f"(from {sender[1]}, another bot) {text}" if sender else text}]
        try:
            t, _ = self.llm.chat("chat", msgs, bot_id=bid, max_tokens=900)
            if not t.strip():  # a reasoning model can spend its whole budget thinking: ask once more
                t, _ = self.llm.chat("chat", msgs + [{"role": "user", "content": "Reply now with the JSON object only."}], bot_id=bid, max_tokens=900)
            d = try_json(t)
            if d is None:  # invalid JSON: say so once and ask again
                t2, _ = self.llm.chat("chat", msgs + [{"role": "assistant", "content": t},
                                                      {"role": "user", "content": "That wasn’t valid JSON. Send the same answer as ONE valid JSON object."}],
                                      bot_id=bid, max_tokens=900)
                d = try_json(t2)
            if d is None:
                d = {"reply": t.strip()[:800] if not t.lstrip().startswith("{") else "Sorry, I got muddled. Could you say that again?", "actions": []}
        except NoModel as e:
            d = {"reply": str(e), "actions": []}
        except Exception as e:
            why = llm_plain(e, "my model")
            d = {"reply": f"{why[:1].upper()}{why[1:]} Check Models.", "actions": []}
        done, held = [], False
        new_rule = not sender and text.lower().startswith("new rule:")
        for a in d.get("actions") or []:
            for k in ("text", "goal", "label"):  # the model sometimes copies the /no_think switch into what it saves
                if isinstance(a.get(k), str):
                    a[k] = re.sub(r"\s*/no_think\b", "", a[k]).strip()
            if new_rule and a.get("type") != "add_rule":  # Settings' rule box only ever adds a rule
                continue
            try:
                done.append(self.apply_action(bid, a, said=text))
            except Guard:
                held = True
            except Exception as e:
                done.append(f"Couldn’t do that: {e}")
        if new_rule:
            rule = text.split(":", 1)[1].strip()
            kind = "never" if re.match(r"^(never|don.?t|do not)\b", rule, re.I) else "ask" if re.search(r"\b(ask|before|first|check with)\b", rule, re.I) else "own"
            bb = self.store.get("bots", bid)
            f = limit_filter(rule)
            seen = self.store.find("results", bot_id=bid, limit=1)
            if f and seen and f["field"] not in seen[0]:  # “books under 10”: the number is a price when results have one
                f = {**f, "field": "price"} if "price" in seen[0] else None
            if f and not any(x.get("field") == f["field"] and x.get("value") == f["value"] for x in bb.get("filters", [])):
                kind = "filter"  # “price under 15” is a limit on results, whatever the model made of it
                if any(str(x).startswith("rule:") for x in done):  # replace the plain rule the model added
                    bb = {**bb, "rules": bb["rules"][:-1]}
                self.store.update("bots", bid, rules=bb.get("rules", []) + [{"kind": "filter", "text": rule}],
                                  filters=bb.get("filters", []) + [{**f, "text": rule}])
                done = [x for x in done if not str(x).startswith("rule:")] + [f"rule: {rule}"]
            elif rule and not any(str(x).startswith("rule:") for x in done):  # a small model returned no action: add it anyway
                self.store.update("bots", bid, rules=bb.get("rules", []) + [{"kind": kind, "text": rule}])
                done.append(f"rule: {rule}")
            elif rule and kind in ("never", "ask"):  # it said Never / Ask first: that's the kind, whatever the model picked
                rules = bb.get("rules", [])
                if rules and rules[-1].get("kind") != kind:
                    self.store.update("bots", bid, rules=rules[:-1] + [{**rules[-1], "kind": kind}],
                                      filters=[f for f in bb.get("filters", []) if f.get("text") != rules[-1].get("text")])
        reply = re.sub(r"\s*/no_think\b", "", d.get("reply") or "").strip() or "OK."
        if held and not done:  # it talked about doing something you didn't ask for: say nothing changed
            reply += " (I haven’t changed anything. Ask me straight out if you want that.)"
        self.store.message(bid, "bot", reply, actions=[a.get("type") for a in d.get("actions") or []], done=done, team=bool(sender))
        self.bus.publish("messages", bot=bid)
        return {"reply": reply, "actions": d.get("actions") or [], "done": done}

    def apply_action(self, bid, a, said=None):
        """An action the model proposed. said: the message it answers, so it only does what was asked."""
        b = self.store.get("bots", bid)
        t = a.get("type")
        if t not in ACTIONS:
            raise Guard(f"unknown action {t}")
        if said is not None and t in CHANGES and is_question(said) and not POLITE.match(said):
            raise Guard("a question isn't a request")  # “Should you run every 5 minutes?” changes nothing
        if t == "add_rule":
            kind = "filter" if a.get("filter") else (a.get("kind") if a.get("kind") in ("own", "ask", "never") else "own")
            if not (a.get("text") or "").strip():
                raise ValueError("the rule has no words")
            rules = b.get("rules", []) + [{"kind": kind, "text": a["text"].strip()}]
            filters = b.get("filters", []) + ([{**a["filter"], "text": a["text"]}] if a.get("filter") else [])
            self.store.update("bots", bid, rules=rules, filters=filters)
            return f"rule: {a['text']}"
        if t == "remove_rule":
            if said is not None and (said.lower().startswith("new rule:") or not REMOVING.search(said)):
                raise Guard("you didn’t ask me to remove a rule")
            rules = b.get("rules", [])
            i = best_match(a.get("text"), rules, key=lambda r: r["text"])
            if i is None:
                raise ValueError(f"no rule like “{a.get('text')}”")
            gone = rules[i]["text"]
            self.store.update("bots", bid, rules=rules[:i] + rules[i + 1:], filters=[f for f in b.get("filters", []) if f.get("text", "") != gone])
            return f"removed rule: {gone}"
        if t == "remember":
            if said is not None and is_question(said) and not re.search(r"\bremember\b", said, re.I):
                raise Guard("a question isn't something to remember")
            if best_match(a.get("text"), b.get("memory", []), key=lambda m: m["text"]) is not None:
                raise Guard("already remembered")
            self.store.update("bots", bid, memory=b.get("memory", []) + [{"text": a["text"], "ts": time.time()}])
            return f"remembered: {a['text']}"
        if t == "forget":
            mem = b.get("memory", [])
            i = best_match(a.get("text"), mem, key=lambda m: m["text"])
            if i is None:
                raise ValueError(f"nothing remembered like “{a.get('text')}”")
            self.store.update("bots", bid, memory=mem[:i] + mem[i + 1:])
            return f"forgot: {mem[i]['text']}"
        if t == "learn":
            url = skills.web_address(a.get("url") or b.get("start_url"), "")
            if said is not None and (is_question(said) or not re.search(r"\b(learn|teach|check|watch|look at|search|go to|try)\b", said, re.I)
                                     or not (re.search(r"https?://|\b[\w-]+\.[a-z]{2,}\b", said, re.I) or re.search(r"\b(new|another|this) (site|website|page)\b", said, re.I))):
                raise Guard("you didn’t ask me to learn a site")  # a question is never a reason to go learning
            if b.get("allowed_domains") and url and skills.site_of(urlparse(url).hostname) not in {skills.site_of(d) for d in b["allowed_domains"]}:
                raise ValueError(f"I only work on {', '.join(b['allowed_domains'])}")
            self.learn(bid, a.get("goal") or b.get("goal"), url)
            return f"learning {urlparse(url).hostname or url}"
        if t == "run":
            self.run(bid)
            return "started a run"
        if t == "schedule":
            s = {**b.get("schedule", {}), **{k: a[k] or None for k in ("every_minutes", "summary_at", "quiet_from", "quiet_to") if a.get(k) is not None}}
            self.store.update("bots", bid, schedule=s)
            m = minutes(s.get("every_minutes"))
            return f"schedule: every {every_words(m)}" if m else "schedule: only when you say"
        if t in ("pause", "resume", "stop"):
            self.control(bid, t)
            return {"pause": "paused", "resume": "resumed", "stop": "stopped"}[t]
        if t == "speed":
            v = a.get("value") if a.get("value") in ("slow", "normal", "turbo") else "turbo" if a.get("value") == "fast" else "normal"
            self.update_bot(bid, {"look": {"speed": v}})
            return f"speed: {v}"
        if t == "delegate":
            threading.Thread(target=self.delegate, args=(bid, a), daemon=True).start()
            return f"handing to {a.get('server')}"
        if t == "ask_bot":
            target = self.find_bot(a.get("bot"), bid)  # fail now if it's unknown or itself
            threading.Thread(target=self._ask_quietly, args=(bid, target["name"], a.get("text") or ""), daemon=True).start()
            return f"asked {target['name']}"
        if t == "add_automation":
            auto = {k: a.get(k) for k in ("when", "server", "tool", "args", "label")}
            if not (auto["server"] and auto["tool"]) or not (self.mcp.known(auto["server"]) or self.mcp.builtin and self.mcp.builtin.has(auto["server"])):
                raise ValueError("an automation needs a connector and one of its tools")
            auto["when"] = auto["when"] if auto["when"] in ("new_results", "every_run") else "new_results"
            self.store.update("bots", bid, automations=b.get("automations", []) + [auto])
            return f"automation: {a.get('label')}"
        raise Guard(f"unknown action {t}")

    # ---------------------------------------------------------- MCP delegation
    def delegate(self, bid, a, context=None, run=None):
        b = self.store.get("bots", bid)
        label = a.get("label") or f"{a.get('server')}.{a.get('tool')}"
        who = self.mcp.label(a.get("server"))
        args = fill_template(a.get("args") or {}, {"bot": b["name"], "count": len(context or []),
                                                   "new_json": json.dumps(context or [], ensure_ascii=False)[:6000]})
        if not a.get("approved_always"):
            decision = self.ask(bid, "decision", f"{b['name']} wants to hand a job to {who}",
                                f"{label}. Tool {a.get('tool')} with {json.dumps(args, ensure_ascii=False)[:400]}",
                                ["Approve", "Always for this automation", "Deny"], run=run, delegate=label)
            if decision not in ("Approve", "Always for this automation"):
                self.store.message(bid, "bot", f"OK, I didn’t hand “{label}” over.")
                return None
            if decision == "Always for this automation":
                autos = b.get("automations", [])
                for x in autos:
                    if all(x.get(k) == a.get(k) for k in ("label", "server", "tool")):
                        x["approved_always"] = True
                self.store.update("bots", bid, automations=autos)
        self.store.event(bid, "delegate", f"Handed to {who}: {label}")
        try:
            r = self.mcp.call(a["server"], a["tool"], args)
            if r["error"] and a["tool"] == "Write" and "not been read" in r["text"] and args.get("file_path"):
                self.mcp.call(a["server"], "Read", {"file_path": args["file_path"]})  # Claude Code only overwrites files it has read
                r = self.mcp.call(a["server"], a["tool"], args)
            out = (r["text"] or "").strip()
            if a.get("as_results") and not r["error"]:  # e.g. an Apify Actor's items become this bot's results
                try:
                    items = [x for x in json.loads(out) if isinstance(x, dict)]
                except (ValueError, TypeError):
                    items = []
                n = self.add_results(bid, items, label)
                out = f"{len(items)} items, {n} new."
            try:  # Codex (and others) answer in JSON: show the reply itself
                j = json.loads(out)
                if isinstance(j, dict):  # a tool result without a reply (e.g. Write) just says it's done
                    out = j.get("reply") or j.get("result") or f"done ({label})"
            except (ValueError, TypeError):
                pass
            self.store.message(bid, "bot", f"{who}: {out[:1500]}" if not r["error"] else f"{who} had a problem: {out[:600]}",
                               delegate=label)
            self.store.event(bid, "delegate", f"{who} finished: {label}", error=r["error"])
            return r
        except Exception as e:
            self.store.message(bid, "bot", f"Couldn’t reach {who}: {e}")
            return None
        finally:
            self.bus.publish("messages", bot=bid)

    def add_results(self, bid, items, source):
        """Results from outside a skill run (a connector): the same rules and new/seen tracking. Returns how many are new."""
        b = self.store.get("bots", bid)
        kept = skills.apply_filters(items, b.get("filters"))
        new = 0
        for it in kept:
            k = skills.item_key(it)
            prev = self.store.find("results", bot_id=bid, key=k, limit=1)
            self.store.upsert_key("results", bid, k, {**it, "skill": source, "run": "connector", "new": not prev, "passed": True})
            new += not prev
        self.bus.publish("results", bot=bid, new=new)
        return new

    # ---------------------------------------------------------- runs
    def busy(self, bid):
        r = self.runs.get(bid)
        return bool(r and r.thread and r.thread.is_alive())

    def _start(self, bid, run, target):
        if self.busy(bid):
            raise RuntimeError("it’s already working")
        self.runs[bid] = run
        run.thread = threading.Thread(target=target, daemon=True, name=f"run-{bid}")
        run.thread.start()
        self.bus.publish("bots")
        return run

    def learn(self, bid, goal, url):
        url = skills.web_address(url, "")
        if not url:
            raise ValueError("It needs a web address to start on, like https://example.com")
        run = Run("learn")
        return self._start(bid, run, lambda: self._learn(bid, goal, url, run))

    def _learn(self, bid, goal, url, run):
        run.run_id = self.store.insert("runs", {"kind": "learn", "goal": goal, "url": url}, bot_id=bid, status="running")
        b = self.store.get("bots", bid)
        self.store.message(bid, "bot", f"Learning {urlparse(url).netloc or url} now, once. Watch if you like, and tell me if I pick something wrong.")
        self.bus.publish("messages", bot=bid)
        try:
            skill = skills.learn(Ctx(self, bid, run), goal, url)
            sid = self.store.insert("skills", skill, bot_id=bid, status="ok")
            self.store.event(bid, "learned", f"Learned {skill['name']}: {len(skill['steps'])} steps, {run.ai_calls} AI calls")
            self._finish(run, "ok", learned=sid)
            reads = any(st["action"] == "extract" for st in skill["steps"])
            self.store.message(bid, "bot", f"Learned “{skill['name']}” in {len(skill['steps'])} steps with {run.ai_calls} AI calls. "
                                           f"From now on it repeats with none." + (" Checking it once now." if reads else " Done for now."))
            self.bus.publish("messages", bot=bid)
            if not reads:  # an action (like sending) already happened while learning: don't do it twice
                return
            run2 = Run("replay", sid)
            self.runs[bid] = run2
            run2.thread = threading.current_thread()
            self._replay(bid, sid, run2, "first run after learning")
        except skills.NeedsHelp as h:
            self.problem(bid, h, url=url, goal=goal)
            self._finish(run, "stopped" if h.kind == "denied" else "needs_you", note=h.title)
        except skills.Stopped:
            self._finish(run, "stopped")
        except NoModel as e:
            self.problem(bid, skills.NeedsHelp("no_model", "No model to learn with", str(e), ["Open Models"]))
            self._finish(run, "failed", note=str(e))
        except Exception as e:
            self.problem(bid, skills.NeedsHelp("error", "Learning stopped", plain_error(e), ["Try again", "Show me once"]), url=url, goal=goal)
            self._finish(run, "failed", note=str(e)[:300])
        finally:
            self.store.update("bots", bid, last_run=time.time())
            self.apply_overlay(bid, target=None, step="")
            self.bus.publish("bots")

    def run(self, bid, skill_id=None, repair_role="repair", reason="manual", wait=False, check=False, timeout=900):
        sk = [s for s in self.store.find("skills", bot_id=bid, desc=False) if skill_id in (None, s["id"], s["name"])]
        if not sk:
            b = self.store.get("bots", bid)
            if b.get("start_url"):
                return self.learn(bid, b.get("goal"), b.get("start_url"))
            raise ValueError("Tell it a site first: Skills → Learn a new site.")
        run = Run("replay", sk[0]["id"])
        run.check = check

        def go():
            for s in sk:
                if run.stop:
                    break
                run.skill_id = s["id"]
                self._replay(bid, s["id"], run, reason, repair_role)
            self.bus.publish("bots")
        self._start(bid, run, go)
        if wait:
            run.thread.join(timeout)
            if run.thread.is_alive():  # too long: stop it rather than leave it running behind a timed-out caller
                run.stop = True
            return self.store.find("runs", bot_id=bid, limit=1)[0]
        return run

    def _replay(self, bid, sid, run, reason, repair_role="repair"):
        skill = self.store.get("skills", sid)
        run.run_id = self.store.insert("runs", {"kind": "replay", "skill": skill["name"], "reason": reason}, bot_id=bid, status="running")
        self.bus.publish("bots")
        try:
            out = skills.replay(Ctx(self, bid, run), skill, repair_role=repair_role)
            if out["repairs"]:
                self.store.update("skills", sid, steps=skill["steps"], version=skill.get("version", 1) + 1)
                for r in out["repairs"]:
                    self.store.event(bid, "fixed", f"Step {r['step']} changed: “{r['from']}” is now “{r['to']}”", confidence=r["confidence"])
            elif any(s.get("approved_always") for s in skill["steps"]):
                self.store.update("skills", sid, steps=skill["steps"])
            b = self.store.get("bots", bid)
            kept = skills.apply_filters(out["items"], b.get("filters"))
            new, kept_ids = [], {id(x) for x in kept}
            for it in kept:  # new = never seen, or used to miss a rule and now passes
                k = skills.item_key(it)
                prev = self.store.find("results", bot_id=bid, key=k, limit=1)
                fresh = not prev or prev[0].get("passed") is False
                self.store.upsert_key("results", bid, k, {**it, "skill": skill["name"], "run": run.run_id, "new": fresh, "passed": True})
                if not prev or prev[0].get("passed") is False:
                    new.append(it)
            missed = [it for it in out["items"] if id(it) not in kept_ids]
            for it in missed:  # kept, hidden, so near-misses can become suggestions
                self.store.upsert_key("results", bid, skills.item_key(it), {**it, "skill": skill["name"], "run": run.run_id, "new": False, "passed": False})
            self.bus.publish("results", bot=bid, new=len(new))
            for r in self.store.find("results", bot_id=bid, limit=1000):
                if r.get("new") and r.get("run") != run.run_id:
                    self.store.update("results", r["id"], new=False)
            self._finish(run, "ok", items=len(out["items"]), matched=len(kept), new=len(new), pages=out["pages"], steps=len(skill["steps"]))
            reads = any(st["action"] == "extract" for st in skill["steps"])
            self.store.event(bid, "replay", f"{nres(len(out['items']))}, {len(kept)} pass your rules, {len(new)} new" if reads
                             else f"Done in {len(skill['steps'])} steps", ai=run.ai_calls)
            if new and reason != "silent":
                top = "; ".join(f"{x.get('title') or x.get('name') or 'untitled'} {x.get('price') or ''}".strip() for x in new[:3])
                self.store.message(bid, "bot", f"{len(new)} new {'match' if len(new) == 1 else 'matches'} from {nres(len(out['items']))}: {top}")
                self.notify(bid, f"{len(new)} new: {top}")
            elif not reads:
                self.store.message(bid, "bot", f"Done: “{skill['name']}”, {len(skill['steps'])} steps, {run.ai_calls} AI calls.")
            elif reason != "schedule":
                ai = "no AI" if not run.ai_calls else f"{run.ai_calls} AI call{'s' if run.ai_calls > 1 else ''} to fix a step"
                self.store.message(bid, "bot", f"Checked {nres(len(out['items']))} with {ai}. {len(kept)} pass{'es' if len(kept) == 1 else ''} your rules, none new.")
            if not new and reason != "silent":
                self.maybe_suggest(bid, missed)
            skipped = skills.unchecked(out["items"], b.get("filters"))
            if skipped and b.get("warned_unchecked") != skipped:
                self.store.update("bots", bid, warned_unchecked=skipped)
                self.store.message(bid, "bot", f"I couldn’t check {'; '.join(skipped)}: this site’s results don’t show that. "
                                               f"Its search already narrows it, or tell me another way to check.")
            self.check_level(bid)  # after this run's own messages
            for auto in b.get("automations", []):
                if auto.get("when") == "every_run" or (auto.get("when") == "new_results" and new):
                    self.delegate(bid, auto, context=new, run=run)
        except skills.NeedsHelp as h:
            self.problem(bid, h, skill_id=sid)
            self._finish(run, "stopped" if h.kind == "denied" else "needs_you", note=h.title)
        except skills.CheckedUpTo as c:
            self._finish(run, "ok", note=f"Checked up to “{c}”, which asks you first")
        except skills.Stopped:
            self._finish(run, "stopped")
            self.store.message(bid, "bot", "Stopped.")
        except NoModel as e:
            self.problem(bid, skills.NeedsHelp("no_model", "A step needs a fix, but there’s no model", str(e), ["Open Models"]), skill_id=sid)
            self._finish(run, "failed", note=str(e))
        except Exception as e:
            if run.stop:  # you pressed Stop while a step was waiting on the page
                self._finish(run, "stopped")
                self.store.message(bid, "bot", "Stopped.")
                return
            self.problem(bid, skills.NeedsHelp("error", f"“{skill['name']}” stopped", plain_error(e), ["Try again"]), skill_id=sid)
            self._finish(run, "failed", note=str(e)[:300])
        finally:
            self.store.update("bots", bid, last_run=time.time())
            self.apply_overlay(bid, target=None, step="")
            self.bus.publish("messages", bot=bid)
            self.bus.publish("bots")
            self._close_screen_later(bid)

    def _close_screen_later(self, bid, delay=4):
        """A window on your screen goes away when its run is done (unless you took over)."""
        def go():
            time.sleep(delay)
            b = self.store.get("bots", bid)
            run = self.runs.get(bid)
            if b and b.get("mode") == "screen" and not self.busy(bid) and not (run and run.takeover):
                self.close_computer(bid)
        threading.Thread(target=go, daemon=True).start()

    def _finish(self, run, status, **data):
        self.store.update("runs", run.run_id, status=status, ended=time.time(), seconds=round(time.time() - run.started, 1),
                          ai_calls=run.ai_calls, tokens=run.tokens, cost=round(run.cost, 5), **data)

    # ---------------------------------------------------------- control, take over, show me once
    def control(self, bid, cmd, reason=None, **kw):
        run = self.runs.get(bid)
        alive = bool(run and run.thread and run.thread.is_alive())
        b = self.store.get("bots", bid)
        if cmd == "pause" and alive:
            run.paused.set()
        elif cmd in ("resume", "handback"):
            if run:
                run.paused.clear()
                run.takeover = False
            if cmd == "handback":
                self.store.event(bid, "handback", "You handed back")
                open_takeover = [n for n in self.store.find("needs", bot_id=bid, status="open") if n.get("kind") in ("robot", "sign_in")]
                for n in open_takeover:
                    self.store.update("needs", n["id"], status="resolved", decision="Handed back")
                resume = open_takeover or b.get("resume_after_handback")
                self.store.update("bots", bid, resume_after_handback=False)
                if resume and not alive:
                    self.store.message(bid, "bot", "Thanks, carrying on from here.")
                    try:
                        self.run(bid, reason="after you took over")
                    except Exception as e:
                        self.store.message(bid, "bot", f"I couldn’t carry on: {e}")
        elif cmd == "stop" and run:
            run.stop = True
            run.paused.clear()
        elif cmd == "takeover":
            if alive:
                run.paused.set()
                run.takeover = True
            else:
                self.runs[bid] = run = run or Run("idle")
                run.takeover = True
            self.computer(bid)
            if reason:
                self.store.message(bid, "bot", reason)
        elif cmd == "speed":
            self.update_bot(bid, {"look": {"speed": kw.get("value", "normal")}})
        elif cmd == "mode":
            self.update_bot(bid, {"mode": kw.get("value", "own")})
        said = {"pause": "Paused", "resume": "Resumed", "stop": "Stopped", "takeover": "You took over its computer",
                "handback": "You handed its computer back", "speed": f"Speed: {kw.get('value', 'normal')}",
                "mode": "Now works in a window on your screen" if kw.get("value") == "screen" else "Now works on its own computer"}.get(cmd, cmd)
        self.store.event(bid, "control", f"{said} · {reason}" if reason and cmd in ("stop", "pause") and len(reason) < 80 else said)
        paused = bool(run and run.paused.is_set())
        self.apply_overlay(bid, paused=paused, pausedText="Paused · you have the screen" if run and run.takeover else "Paused")
        self.bus.publish("bots")
        return self.bot_view(self.store.get("bots", bid))

    def user_input(self, bid, kind, **kw):
        c = self.computer(bid)
        run = self.runs.get(bid)
        if kind == "click" and run and getattr(run, "show", None) is not None:
            page = c.call("elements")
            x, y = kw.get("x", 0), kw.get("y", 0)
            hits = [e for e in page["elements"] if e["x"] <= x <= e["x"] + e["w"] and e["y"] <= y <= e["y"] + e["h"]]
            if hits:
                el = min(hits, key=lambda e: e["w"] * e["h"])
                run.show.append({"action": "click", "target": skills.descriptor(el), "text": f"Click “{el['name']}”",
                                 "value": None, "shown": True})
                self.store.event(bid, "shown", f"You clicked “{el['name']}”")
        return c.call("user", kind, **kw)

    def start_show(self, bid, need):
        """Replay up to the failed step, then let you click the right thing(s)."""
        sid, at = need.get("skill_id"), need.get("step")
        skill = self.store.get("skills", sid)
        run = Run("show", sid)
        run.show = []
        run.takeover = True

        def go():
            run.run_id = self.store.insert("runs", {"kind": "show", "skill": skill["name"]}, bot_id=bid, status="running")
            partial = dict(skill, steps=skill["steps"][:at])
            try:
                skills.replay(Ctx(self, bid, run), partial)
            except Exception:
                pass
            run.paused.set()
            self.store.message(bid, "bot", "Your turn: click what I should click on my computer, then press Done showing.")
            self.bus.publish("messages", bot=bid)
            while run.paused.is_set() and not run.stop:
                time.sleep(0.2)
            self._finish(run, "ok")
        self._start(bid, run, go)
        return run

    def finish_show(self, bid):
        run = self.runs.get(bid)
        if not run or getattr(run, "show", None) is None:
            raise ValueError("not in show mode")
        shown = run.show
        need = next((n for n in self.store.find("needs", bot_id=bid) if n.get("kind") == "fix_failed"), None)
        run.paused.clear()
        run.thread.join(10)
        if not shown:
            run.takeover = False
            self.store.message(bid, "bot", "You didn’t click anything, so the step is unchanged. Press Show me once again when you’re ready.")
            if need:  # a fresh card: the old one stays answered
                self.problem(bid, skills.NeedsHelp(need["kind"], need["title"], need["body"], need.get("options")),
                             **{k: need[k] for k in ("skill_id", "step", "guess", "confidence", "url") if k in need})
            self.bus.publish("messages", bot=bid)
            self.bus.publish("needs", bot=bid)
        if shown and need:
            skill = self.store.get("skills", need["skill_id"])
            at = need["step"]
            failed = skill["steps"][at]
            # your last click is the new target of the failed step (keeping what it typed); earlier clicks come before it
            name = (shown[-1]["target"] or {}).get("name") or ""
            last = {**failed, "target": shown[-1]["target"], "shown": True,
                    "text": f"{failed['action'].capitalize()} “{name}”" if name and failed.get("action") in ("click", "press") else failed["text"]}
            steps = skill["steps"][:at] + shown[:-1] + [last] + skill["steps"][at + 1:]
            self.store.update("skills", skill["id"], steps=steps, version=skill.get("version", 1) + 1)
            self.store.update("needs", need["id"], status="resolved", decision="Shown")
            self.store.message(bid, "bot", f"Thanks. I replaced step {at + 1} with what you showed me ({len(shown)} click{'s' if len(shown) > 1 else ''}). Running it again.")
            self.bus.publish("needs", bot=bid)
            self.runs.pop(bid, None)
            self.run(bid, skill["id"], reason="after you showed me")
        return len(shown)

    # ---------------------------------------------------------- notify, schedule
    def notify(self, bid, text):
        self.bus.publish("notify", bot=bid, text=text)
        if self.store.setting("telegram", {}).get("enabled") and connectors.PROVIDERS["telegram"].configured(self):
            name = (self.store.get("bots", bid) or {}).get("name", "Inky") if bid else "Inky"
            try:
                connectors.PROVIDERS["telegram"].send(self, f"{name}: {text}")
            except Exception:
                pass

    def start_scheduler(self):
        if self._sched:
            return
        for srv in self.mcp.servers():  # reconnect the connectors you turned on
            if srv["enabled"] and srv["installed"]:
                threading.Thread(target=lambda n=srv["name"]: self._try_connect(n), daemon=True).start()
        self._sched = threading.Thread(target=self._tick_loop, daemon=True, name="scheduler")
        self._sched.start()

    def _try_connect(self, name):
        try:
            self.mcp.connect(name)
        except Exception:
            pass

    def _tick_loop(self):
        while True:
            try:
                self.tick()
            except Exception:
                pass
            time.sleep(10)

    def tick(self, now=None):
        now = now or time.time()
        hm = datetime.fromtimestamp(now).strftime("%H:%M")
        today = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
        for b in self.store.find("bots"):
            s = b.get("schedule") or {}
            if b.get("status") == "moved":
                continue  # its server runs it now
            # daily rituals first: they happen whether or not the bot is on a schedule
            if s.get("summary_at") == hm and b.get("summary_day") != today:
                self.post_paper(b["id"], now)
            if s.get("quiet_from") == hm and b.get("night_day") != today:
                self.store.update("bots", b["id"], night_day=today)
                threading.Thread(target=self.evening, args=(b["id"], now), daemon=True).start()
            if not s.get("every_minutes") or self.busy(b["id"]) or not self.store.find("skills", bot_id=b["id"], limit=1):
                continue
            if quiet(hm, s.get("quiet_from"), s.get("quiet_to")):
                continue
            if now - (b.get("last_run") or 0) >= s["every_minutes"] * 60:
                try:
                    self.run(b["id"], reason="schedule")
                except Exception:
                    pass

    def evening(self, bid, now):
        """Quiet hours begin: a one-line good night (only if it worked today), then the diary."""
        text = self.good_night(bid, now)
        if text:
            self.store.message(bid, "bot", text, unprompted=True, team=True)
            self.bus.publish("messages", bot=bid)
        self.write_diary(bid, now)

    def good_night(self, bid, now):
        start = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0).timestamp()
        runs = [r for r in growth.ok_runs(self.store.find("runs", bot_id=bid, limit=500)) if r["ts"] >= start]
        if not runs:
            return None
        new = sum(r.get("new") or 0 for r in runs)
        return f"Good night! Today I did {len(runs)} run{'s' if len(runs) > 1 else ''} and found {new} new. Back at it in the morning."

    # ---------------------------------------------------------- team life: bots talking to each other
    def find_bot(self, name, from_bid=None):
        low = str(name or "").strip().lower()
        bots = [b for b in self.store.find("bots", desc=False) if b.get("status") != "moved"]
        t = next((b for b in bots if b["name"].lower() == low), None) or next((b for b in bots if b["name"].lower().startswith(low) and low), None)
        if not t:
            raise ValueError(f"there's no bot called {name}")
        if t["id"] == from_bid:
            raise ValueError("a bot can't ask itself")
        return t

    def ask_bot(self, from_bid, to_name, text):
        """One bot talks to another. At most 3 times an hour per pair; the other bot's own rules and gates apply."""
        src = self.store.get("bots", from_bid)
        dst = self.find_bot(to_name, from_bid)
        now = time.time()
        key = (from_bid, dst["id"])
        recent = [t for t in self.hops.get(key, []) if now - t < 3600]
        if len(recent) >= 3:
            raise ValueError(f"{src['name']} and {dst['name']} have talked enough this hour")
        self.hops[key] = recent + [now]
        self.store.event(from_bid, "team", f"Asked {dst['name']}: {text[:120]}")
        return self.chat(dst["id"], text, source=f"bot:{from_bid}", sender=(from_bid, src["name"]))["reply"]

    def _ask_quietly(self, from_bid, to_name, text):
        try:
            reply = self.ask_bot(from_bid, to_name, text)
            if reply:  # the answer comes back to the bot (and you) that asked
                self.store.message(from_bid, "peer", reply, sender=to_name, sender_id=self.find_bot(to_name, from_bid)["id"], team=True, reply_to=text[:120])
                self.bus.publish("messages", bot=from_bid)
        except Exception as e:
            self.store.message(from_bid, "bot", f"I couldn't reach {to_name}: {e}")
            self.bus.publish("messages", bot=from_bid)

    def team_feed(self, limit=100):
        bots = {b["id"]: b for b in self.store.find("bots")}
        feed = []
        for bid, b in bots.items():
            for m in self.store.find("messages", bot_id=bid, limit=200):
                if m["role"] == "bot" and m.get("team"):  # its answer to a bot shows once, as the copy that reached the asker
                    continue
                if m["role"] == "peer":
                    kind = "peer"
                elif m.get("paper"):
                    kind = "paper"
                elif m.get("team"):
                    kind = "reply" if m["role"] == "bot" else "note"
                else:
                    continue
                feed.append({"ts": m["ts"], "bot": bid, "name": b["name"], "look": b.get("look"), "kind": kind,
                             "text": m["text"], "sender": m.get("sender"), "sender_id": m.get("sender_id"),
                             "reply_to": m.get("reply_to"), "role": m["role"]})
        feed.sort(key=lambda f: -f["ts"])
        return feed[:limit]

    # ---------------------------------------------------------- growth
    def check_level(self, bid):
        n = len(growth.ok_runs(self.store.find("runs", bot_id=bid, limit=5000)))
        acc = growth.level_up(n - 1, n)
        if not acc:
            return None
        self.store.event(bid, "level", f"Reached {n} runs: unlocked the {acc}")
        self.store.message(bid, "bot", f"🎉 {n} runs on the job! I unlocked the {acc}. You can put it on me in Make it yours.", team=True)
        self.bus.publish("level", bot=bid, acc=acc, runs=n)
        self.bus.publish("messages", bot=bid)
        return acc

    def growth_view(self, bid):
        b = self.store.get("bots", bid)
        return growth.stats(b, self.store.find("runs", bot_id=bid, limit=5000), self.store.find("skills", bot_id=bid), time.time())

    def write_diary(self, bid, now=None):
        """One entry a day, in the bot's own words: a template, polished once by the model when one is set."""
        now = now or time.time()
        day = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
        if self.store.find("diary", bot_id=bid, key=day, limit=1):
            return None
        start = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0).timestamp()
        b = self.store.get("bots", bid)
        runs = [r for r in self.store.find("runs", bot_id=bid, limit=500) if r["ts"] >= start]
        events = [e for e in self.store.find("events", bot_id=bid, limit=500) if e["ts"] >= start]
        if not growth.ok_runs(runs) and not any(e.get("kind") in ("fixed", "problem", "level") for e in events):
            return None  # nothing happened: no entry
        text = growth.diary_entry(b, events, runs)
        try:
            p = persona_mod.prompt_lines(b, self.store.setting("app", {}).get("user_name", ""), datetime.fromtimestamp(now), [])
            t, _ = self.llm.chat("chat", [{"role": "system", "content": f"You are {b['name']}, a bot. {p}"},
                                          {"role": "user", "content": f"Rewrite this diary entry in your own voice. Keep every fact, add none, at most 4 sentences, plain text:\n{text}"}],
                                 bot_id=bid, max_tokens=400)
            t = re.sub(r"<think>.*?(</think>|$)", "", t or "", flags=re.S).strip()
            if 20 < len(t) < 900 and not t.startswith("{"):
                text = t
        except Exception:
            pass  # no model, or it failed: the template is fine
        self.store.insert("diary", {"text": text, "date": day}, bot_id=bid, key=day)
        return text

    # ---------------------------------------------------------- insights: what a bot notices
    def post_paper(self, bid, now=None):
        """The morning paper: what happened, a trend, one suggestion. It's the bot's one unprompted note today."""
        now = now or time.time()
        b = self.store.get("bots", bid)
        paper = insights.morning_paper(self.store, b, now)
        self.store.message(bid, "bot", paper["text"], chips=paper["chips"], unprompted=True, paper=True, team=True)
        self.store.update("bots", bid, summary_day=datetime.fromtimestamp(now).strftime("%Y-%m-%d"))
        self.bus.publish("messages", bot=bid)
        self.notify(bid, paper["text"])
        return paper

    def maybe_suggest(self, bid, missed):
        b = self.store.get("bots", bid)
        if not missed or not insights.may_post(self.store, b, time.time()):
            return None
        nm = insights.near_misses(missed, b.get("filters"))
        if not nm:
            return None
        text, chips = insights.suggestion(b, nm)
        self.store.message(bid, "bot", text + " Want me to widen it?", chips=chips, unprompted=True)
        self.bus.publish("messages", bot=bid)
        return chips

    def apply_chip(self, bid, apply, msg_id=None):
        """A tap on a suggestion. Only reversible settings: filters, schedule or look."""
        if not isinstance(apply, dict) or len(apply) != 1 or not set(apply) <= {"filters", "schedule", "look"}:
            raise ValueError("a suggestion can only change filters, schedule or look")
        b = self.store.get("bots", bid)
        patch = dict(apply)
        if "filters" in apply:  # keep the rule texts in step with the filters
            texts = {f.get("text") for f in b.get("filters") or []}
            rules = [r for r in b.get("rules", []) if not (r["kind"] == "filter" and r["text"] in texts)]
            have = {r["text"] for r in rules}
            patch["rules"] = rules + [{"kind": "filter", "text": t} for t in dict.fromkeys(f.get("text") or f"{f['field']} {f['op']} {f['value']}" for f in apply["filters"]) if t not in have]
        view = self.update_bot(bid, patch)
        if msg_id:
            self.store.update("messages", int(msg_id), chips_used=True)
        self.store.message(bid, "note", "You tapped: " + ("rules updated" if "filters" in apply else "settings updated") + ".")
        self.bus.publish("messages", bot=bid)
        return view

    def close(self):
        for bid in list(self.runs):
            self.control(bid, "stop")
        for bid in list(self.computers):
            self.close_computer(bid)
        self.mcp.close()


def fill_template(obj, vars):
    if isinstance(obj, str):
        return re.sub(r"\{\{(\w+)\}\}", lambda m: str(vars.get(m.group(1), m.group(0))), obj)
    if isinstance(obj, dict):
        return {k: fill_template(v, vars) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fill_template(v, vars) for v in obj]
    return obj


def try_json(text):
    from inky.llm import parse_json
    try:
        d = parse_json(text)
        return d if isinstance(d, dict) else None
    except Exception:
        return None
