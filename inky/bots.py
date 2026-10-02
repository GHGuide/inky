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
from inky.llm import LLM, ModelStopped, NoModel, plain as llm_plain
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
    """The model proposed something you didn't ask for: not done. offer=True: it's offered as a button instead."""

    def __init__(self, msg="", offer=False):
        super().__init__(msg)
        self.offer = offer


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


FILLER = re.compile(r"^(so|and|ok|okay|well|hey|then|but|um|uh|hmm)\b[,!.\s]*", re.I)
RECAP = re.compile(r"\b(what (did|have) you (do|done|been doing|find|found|get|got)|what you (did|found)|what happened|what'?s new|anything new|"
                   r"how did (it|that|the run|your run) go|any (news|results|luck))\b", re.I)
AFFIRM = re.compile(r"^\s*(yes|yeah|yep|yup|sure|ok(ay)?|please( do)?|do it|go ahead|go for it|i want (that|it)|that'?s (fine|good)|"
                    r"sounds good|let'?s do (it|that)|yes please|please go ahead)\b[\s!.,]*(please|thanks)?[\s!.]*$", re.I)


def is_question(t):
    t = re.sub(r"^[^\w¿¡]+|[^\w?]+$", "", (t or "").strip().lower())  # “📚 any cheap ones? 😍”: emoji around a question
    while FILLER.match(t) and FILLER.sub("", t, 1) != t:
        t = FILLER.sub("", t, 1)
    return t.endswith("?") or bool(re.match(r"^(what|how|did|do|does|when|why|which|who|where|is|are|was|were|can|could|have|has)\b", t))


OFFLINE = re.compile(r"ERR_INTERNET_DISCONNECTED|ERR_NETWORK_CHANGED|ERR_NETWORK_IO_SUSPENDED|ERR_NAME_RESOLUTION_FAILED|isn’t connected to the internet|no internet|this computer is offline", re.I)
SELF_HANDLED = {"error", "fix_failed", "learn_failed", "batch_failed", "blocked"}  # a bot sorts these out itself; Needs you is for what only you can do
ACTIONS = {"add_rule", "remove_rule", "remember", "forget", "learn", "run", "schedule", "pause", "resume", "stop", "speed",
           "delegate", "ask_bot", "add_automation"}
CHANGES = ACTIONS - {"remember", "learn", "ask_bot"}  # those two have their own checks; asking another bot changes nothing
POLITE = re.compile(r"\s*(can|could|would|will) you\b(?!.*\b(better|faster|worth|good idea)\b)|.*\bplease\b", re.I)
REMOVING = re.compile(r"\b(remove|delete|drop|no longer|get rid of|forget|scrap|cancel|undo|take (out|off|away))\b", re.I)
NEGATIVE = re.compile(r"\b(skip|no|not|without|exclude|excluding|ignore|avoid|except|hide|drop|never|don'?t|doesn'?t|isn'?t|aren'?t|non)\b", re.I)
FLIP = {"contains": "not_contains", "in": "not_in", "==": "!="}
PRICE_Q = re.compile(r"\b(cheapest|lowest[- ]price[ds]?|least expensive|best price|most expensive|priciest|dearest|highest[- ]price[ds]?)\b", re.I)
COUNT_Q = re.compile(r"^\s*(so |and |ok,? )?how many\b(?!.*\b(sites?|times|runs?|pages?|rules?|days?|hours?|minutes?|ai calls?|bots?)\b)", re.I)
SCREEN_ASK = re.compile(r"\b(work|run|go|do (it|this|that)|use|switch|move|look)\b.{0,30}\b(on|to|onto|with|using) my (own )?screen\b|\buse my screen\b", re.I)
OWN_ASK = re.compile(r"\b(work|run|go|switch|move|stay)\b.{0,30}\b(on|to) (your|its) own (computer|browser)\b|\boff my screen\b", re.I)


def negated(text, value):
    """“skip senior roles”: the rule says no to its word, whatever the model made of it."""
    low = (text or "").lower()
    for v in value if isinstance(value, list) else [value]:
        i = low.find(str(v).lower())
        if i > 0 and re.search(NEGATIVE.pattern + r"\s+(?:[\w'’-]+\s+){0,2}$", low[:i], re.I):
            return True
    return False


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


def quick_command(text):
    """A plain command, understood without a model: run, pause, resume, stop, a schedule, remember, forget, speed. Or None."""
    t = re.sub(r"[.!]+$", "", FILLER.sub("", (text or "").strip())).strip()
    low = t.lower().removeprefix("please ").strip()
    if not low or "?" in low or len(low) > 120:
        return None
    if re.fullmatch(r"(run|run (it )?now|check( it)? now|search now|go|start|check|run it|do it now|look now)( please)?", low):
        return {"type": "run"}
    if re.fullmatch(r"(pause|pause( it| now| for now)?|hold on|take a break|stop for now)", low):
        return {"type": "pause"}
    if re.fullmatch(r"(resume|resume it|continue|carry on|unpause|start again|keep going)", low):
        return {"type": "resume"}
    if re.fullmatch(r"(stop|stop it|stop now|stop that)", low):
        return {"type": "stop"}
    if re.search(r"\b(only (run|check|look)s? when i ask|only when i (ask|say)|only when asked|don'?t (run|check) on (its|your) own|stop (running|checking) on (its|your) own|no schedule|manually)\b", low):
        return {"type": "schedule", "every_minutes": 0}
    m = re.fullmatch(r"(?:(?:check|run|look|search)(?: it)? )?(every .{1,30}|hourly|daily|weekly|twice a day|each (?:morning|day|hour|week))", low)
    if m and minutes(m.group(1)):
        return {"type": "schedule", "every_minutes": minutes(m.group(1)), **({"at": time_of_day(low)} if time_of_day(low) else {})}
    m = re.fullmatch(r"(?:please )?remember(?: that)? (.{3,200})", t, re.I)
    if m:
        return {"type": "remember", "text": you_form(m.group(1).strip())}
    if re.fullmatch(r"(forget|remove|delete|drop|undo|scrap) (that|this|the|my|the last|your last) (new )?rule", low):
        return {"type": "remove_rule", "last": True}
    m = re.fullmatch(r"(?:please )?forget(?: that| about)? (.{2,200})", t, re.I)
    if m and not re.fullmatch(r"(it|that|this)", m.group(1).strip(), re.I):
        return {"type": "forget", "text": m.group(1).strip()}
    if re.fullmatch(r"(slower|slow down|go slower|slow)", low):
        return {"type": "speed", "value": "slow"}
    if re.fullmatch(r"(faster|speed up|go faster|turbo|fast)", low):
        return {"type": "speed", "value": "turbo"}
    if re.fullmatch(r"(normal speed|normal)", low):
        return {"type": "speed", "value": "normal"}
    return None


HANDOFF = re.compile(r"^(?:please\s+|can you\s+|could you\s+)?(?:ask|have|get|tell|let|use)\s+(codex|claude(?:[\s-]?code)?)\s+(?:to\s+)?(.{3,})$", re.I)


def handoff(text):
    """“Ask Codex to …”, “have Claude Code …”: the agent you named and the job, or None. Never left to the model to pick."""
    m = HANDOFF.match((text or "").strip())
    if not m:
        return None
    return ("codex" if m.group(1).lower() == "codex" else "claude-code"), m.group(2).strip().rstrip("?")


def you_form(t):
    """“I like mystery novels” → “You like mystery novels”: how the bot keeps what you told it."""
    swaps = {"i": "you", "i'm": "you're", "i’m": "you’re", "me": "you", "my": "your", "mine": "yours", "am": "are", "myself": "yourself"}
    out = re.sub(r"\b(i’m|i'm|i|me|my|mine|am|myself)\b", lambda m: swaps[m.group(1).lower()], t, flags=re.I)
    return out[:1].upper() + out[1:]


def command_reply(a, out):
    t = a["type"]
    if t == "schedule":
        m = minutes(a.get("every_minutes"))
        return f"Done: I’ll check every {every_words(m)}{' at ' + str(out).rsplit(' at ', 1)[1] if ' at ' in str(out) else ''}." if m else "Done: I’ll only run when you ask."
    if t == "add_rule":
        return f"Done: from now on I only keep results with {a['text']}."
    if t == "remove_rule":
        return f"Done: I removed the rule “{str(out).removeprefix('removed rule: ')}”."
    return {"run": "Running now.", "pause": "Paused." if out == "paused" else "Paused my schedule: I won’t run until you say resume.",
            "resume": "Carrying on.", "stop": "Stopped.", "remember": f"I’ll remember: {a.get('text')}.",
            "forget": f"Forgotten: {str(out).removeprefix('forgot: ')}.", "speed": f"Speed: {a.get('value')}."}.get(t, "Done.")


def stated(f, job):
    """Did your job text say this limit? Its value (each word of it, or the number) must be in what you wrote."""
    if not isinstance(f, dict) or not f.get("field") or f.get("value") in (None, "", []):
        return False
    vals = f["value"] if isinstance(f["value"], list) else [f["value"]]
    low = job.lower()
    for v in vals:
        if not re.search(r"[^\W_]", str(v)):  # only symbols (“£”, “-”): not a limit anyone states
            return False
        n = skills.parse_num(v)
        if isinstance(v, bool) or str(v).lower() in ("true", "false"):
            return False
        if n is not None:  # a number, or a number written as text: it has to be one you wrote (and 0 is never a limit)
            said = {skills.parse_num(x) for x in re.findall(r"\d[\d.,]*\d|\d", job)}  # “€150.000”, “1,000”, “£15” read like prices
            if n == 0 or n not in said and not re.search(rf"\b{int(n) // 1000}\s*k\b", low):
                return False
        elif not all(w in low for w in re.findall(r"[^\W\d_]{3,}", str(v).lower())):
            return False
    return True


def when_words(ts, future=False):
    """“Today at 12:51”, “Yesterday at 09:00”, “Fri at 12:51” (or “at 12:51” mid-sentence)."""
    d, now = datetime.fromtimestamp(ts), datetime.now()
    days = (d.date() - now.date()).days
    day = "Today" if days == 0 else ("Tomorrow" if days == 1 else "Yesterday" if days == -1 else d.strftime("%a"))
    return f"{day.lower() if future else day} at {d.strftime('%H:%M')}"


def every_words(m):
    """60 → “hour”, 120 → “2 hours”, 5 → “5 minutes”: what follows “every”."""
    n, unit = (m // 1440, "day") if m % 1440 == 0 else (m // 60, "hour") if m % 60 == 0 else (m, "minute")
    return unit if n == 1 else f"{n} {unit}s"


def card_items(rows, n=3):
    """The few results a chat message shows as rows: name, price, link."""
    return [{k: str(v)[:160] for k, v in (("title", r.get("title") or r.get("name") or "Untitled"), ("price", r.get("price")), ("link", r.get("link") or r.get("url"))) if v}
            for r in rows[:n]]


def nres(n, word="result"):
    return f"{n} {word}{'' if n == 1 else 's'}"


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


def time_of_day(text):
    """The time of day a daily check runs, if you said one: “every evening” 18:00, “each day at 9” 09:00. Else None."""
    t = str(text or "").lower()
    m = re.search(r"\bat (\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b", t)
    if m:
        h = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0) if m.group(3) else int(m.group(1))
        if h < 24 and int(m.group(2) or 0) < 60:
            return f"{h:02d}:{int(m.group(2) or 0):02d}"
    return "18:00" if re.search(r"evening|night", t) else "12:00" if re.search(r"noon|lunch|midday", t) else "07:30" if "morning" in t else None


def due_at(s, last):
    """When the next scheduled check is due: an interval after the last one; daily and weekly checks run at their time of
    day (s["at"]), so a Run now in between never moves tomorrow's check."""
    m = minutes((s or {}).get("every_minutes"))
    base = (last or 0) + m * 60
    if not last or m < 1440 or not re.fullmatch(r"\d{2}:\d{2}", str(s.get("at") or "")):
        return base
    h, mi = map(int, s["at"].split(":"))
    early = base - 18 * 3600  # the slot nearest a full period after the last check
    t = datetime.fromtimestamp(early).replace(hour=h, minute=mi, second=0, microsecond=0)
    return t.timestamp() if t.timestamp() > early else t.timestamp() + 86400


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

KNOWN_SITES = {"hacker news": "https://news.ycombinator.com/"}  # sites people name by a name that isn't in their address

DRAFT_SYSTEM = """You turn a job description into a bot. Reply with ONE JSON object:
{"name": "<2 words, e.g. Flat Hunter>", "summary": "<one sentence of what it will do>", "goal": "<what to search and read on the site>",
 "start_url": "<the site to start on, full URL, or null if unknown>", "every_minutes": <a number of minutes: 1440 for daily or every morning, 60 for hourly, 0 for only when asked>, "summary_at": "<HH:MM or null>",
 "filters": [{"field": "<price|size|title|text>", "op": "<|<=|>|>=|==|contains|not_contains|in|not_in", "value": <number|string|list>, "text": "<the rule in words>"}],
 "search": ["<2-3 web searches that find websites for this job; one in the local language if the job names a place>"],
 "ask_first": ["<things it must ask before>"], "questions": ["<at most 2 short questions if something important is missing>"],
 "persona": {"chatty": <0-1>, "playful": <0-1>, "emoji": <true|false>, "catchphrase": "<short, fits the job>", "quirk": "<one line>", "bio": "<one line, first person>"}}
Filters: only limits the user actually stated (a price, a size, a place, a word). Never invent one. A word the user said the results must mention (a place, "remote", a topic like "AI") is {"field": "text", "op": "contains", "value": "<that word>"}; prices and currencies are never a text rule.
start_url: when the job names a site, by its address or its well-known name, use that site. No question about which website: Inky searches for sites itself."""

CHAT_SYSTEM = """You are {name}, an Inky bot with its own computer (a browser). Your job: {job}.
Talk {tone}. Keep replies to one or two short sentences, in the language the user writes in. Answer only what was asked: don't add
your status, schedule, counts or small talk about yourself unless asked. You can take actions. Reply with ONE JSON object:
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
        self.site = ""  # the site it's on now, in plain words: shown next to the bot's name


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

    def _remember_always(self, step):
        sid = getattr(self.run, "skill_id", None) if self.run else None
        sk = self.e.store.get("skills", sid) if sid else None
        if not sk:
            return
        same = lambda st: st.get("action") == step.get("action") and st.get("text") == step.get("text") and \
            (st.get("target") or {}).get("name") == (step.get("target") or {}).get("name")
        steps = [dict(st, approved_always=True) if same(st) else st for st in sk.get("steps") or []]
        if steps != sk.get("steps"):
            self.e.store.update("skills", sid, steps=steps)

    def gate(self, step, el, page):
        verdict, why = classify(step["action"], el, page)
        name = self.bot["name"]
        said = f"{step.get('text') or ''} {(el or {}).get('name') or ''}"
        pg = page or {}
        where = f"{said} {pg.get('title') or ''} {' '.join(pg.get('heads') or [])} {urlparse(pg.get('url') or '').path.replace('/', ' ')}"
        # “never contact the agency”: for a step that can't be undone, the page it's on counts too, not only its button's words
        never = rule_hit(self.bot.get("rules", []), "never", said) or (verdict in ("irreversible", "pay") and rule_hit(self.bot.get("rules", []), "never", where))
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
                                   ["Open its computer", "Skip this run"])
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
        job = f"{self.bot.get('job') or ''} {self.bot.get('goal') or ''}"
        if not skills.DOING.search(job):  # a finding job: sending anything wasn't asked for (a page may have tried to steer it)
            body += " Its job is only to find things, so this isn’t part of it: Deny unless you meant it."
        typed = next((r["text"] for r in preview if r.get("text")), None)
        if typed:
            body += f" Message: “{typed[:280]}”"
        what = step["text"][:1].lower() + step["text"][1:] if step["text"][1:2].islower() else step["text"]
        decision = self.e.ask(self.bot_id, "decision", f"{name} wants to {what}", body,
                              ["Approve", "Always for this step", "Deny"], run=self.run, step=step.get("text"))
        if decision not in ("Approve", "Always for this step"):  # only a clear yes goes ahead
            raise skills.NeedsHelp("denied", f"Stopped before it could {what}", "You said no, so nothing was sent.", [])
        if getattr(self.run, "paused", None) is not None:
            self.check()  # paused or stopped while it waited for you: that holds, even after a yes
        if decision == "Always for this step":
            step["approved_always"] = True
            self._remember_always(step)  # saved now: a later step failing must never make it ask you again


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
        self.llm.on_live = lambda: self.bus.publish("thinking")  # the app shows which model is thinking, for which bot
        self.mcp = MCPManager(self.store, str(self.home))
        self.mcp.builtin = connectors.Builtins(self)
        self.computers, self.runs, self.waits = {}, {}, {}
        for r in self.store.find("runs", status="running", limit=1000):  # a restart ended them: say so instead of "running" forever
            self.store.update("runs", r["id"], status="stopped", note="Inky restarted")
            b = self.store.get("bots", r["bot_id"])
            if b and r.get("kind") == "learn" and r.get("url") and not any(x.get("url") == r["url"] for x in b.get("retries") or []):
                self.store.update("bots", b["id"], retries=list(b.get("retries") or []) + [  # it was learning: it learns that site again, soon
                    {"key": f"site:{skills.site_of(urlparse(r['url']).hostname or '')}", "at": time.time() + 300, "sid": None, "url": r["url"], "goal": r.get("goal") or b.get("goal"), "do": "learn"}])
        for n in self.store.find("needs", status="open", limit=500):  # problems the bot handles itself now: closed, and tried again soon
            if n.get("kind") in SELF_HANDLED and not n.get("asked"):
                self.store.update("needs", n["id"], status="resolved", decision="Handled by the bot")
                b = self.store.get("bots", n["bot_id"])
                if b:
                    urls = n.get("urls") or [n.get("url") or (self.store.get("skills", n["skill_id"]) or {}).get("start_url") if n.get("skill_id") else n.get("url")]
                    rs = list(b.get("retries") or [])
                    for i, u in enumerate(u for u in urls if u):
                        rs.append({"key": f"need:{n['id']}:{i}", "at": time.time() + 60 * (len(rs) + 1), "sid": n.get("skill_id"), "url": u, "goal": n.get("goal") or b.get("goal"),
                                   "do": "learn" if n.get("kind") == "fix_failed" or not n.get("skill_id") else "run"})
                    self.store.update("bots", b["id"], retries=rs)
        self.hops = {}  # (from bot, to bot) -> times, so two bots can't talk in circles
        self.lock = threading.RLock()
        self._sched = None
        self._tg_lock = threading.Lock()

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
        if sched.get("every_minutes") and sk and b.get("status") != "moved" and not b.get("held"):
            nxt = max(time.time(), due_at(sched, b.get("last_run")))  # never ran: due now
            end = sched.get("quiet_to")
            if end and quiet(datetime.fromtimestamp(nxt).strftime("%H:%M"), sched.get("quiet_from"), end):
                h, m = map(int, end.split(":"))  # quiet hours: the first run after they end
                t = datetime.fromtimestamp(nxt).replace(hour=h, minute=m, second=0)
                nxt = t.timestamp() if t.timestamp() > nxt else t.timestamp() + 86400
        return {**{k: b.get(k) for k in ("id", "name", "job", "summary", "goal", "start_url", "rules", "filters", "memory", "home",
                                         "schedule", "automations", "mode", "computer", "last_run", "created", "allowed_domains", "library")},
                "look": {**DEFAULT_LOOK, **(b.get("look") or {})},  # older bots get every part of a look
                "persona": persona_mod.normalize(b.get("persona"), (b.get("look") or {}).get("kind", "octopus")),
                "status": status, "step": run.step if live else "", "step_n": run.n if live else 0, "site": getattr(run, "site", "") if live else "",
                "skills": [s["name"] for s in sk], "needs": len(needs), "next_run": nxt, "held": bool(b.get("held")), "retries": len(b.get("retries") or []), "sites_to_go": len(b.get("site_queue") or []) + (1 if b.get("site_batch") else 0),
                **(self._found(b["id"]) if b.get("status") != "moved" else {"found": 0, "fresh": 0, "top": []}),  # what it finds now lives on its server
                "need_kind": ("decision" if needs[0].get("kind") == "decision" else "problem") if needs else None,
                "unlocked": growth.unlocked(len(growth.ok_runs(self.store.find("runs", bot_id=b["id"], status="ok", limit=600)))),
                "ai_calls": run.ai_calls if run else 0, "takeover": bool(run and run.takeover),
                "run_kind": run.kind if run and run.thread and run.thread.is_alive() else None,
                "skill_id": run.skill_id if run else None, "shown": len(getattr(run, "show", None) or []) if run else 0,
                "remote_id": b.get("remote_id"),
                "offline": b.get("status") == "moved" and str(b.get("computer") or "").isdigit() and int(b["computer"]) in getattr(self, "offline", {})}

    def kept(self, bid, limit=2000, b=None):
        """What it found that passes your rules as they are now: they may have changed since its last run."""
        b = b or self.store.get("bots", bid)
        hidden = ("id", "bot_id", "status", "key", "ts", "passed", "new", "run", "skill")
        return [r for r in self.store.find("results", bot_id=bid, limit=limit)
                if skills.apply_filters([{k: v for k, v in r.items() if k not in hidden}], b.get("filters"))]

    def _found(self, bid):
        """What it found, in a line: how many pass its rules, how many are new, the newest two."""
        rows = self.kept(bid, 400)
        top = [{"title": str(r.get("title") or r.get("name") or "")[:80], "price": str(r.get("price") or "")[:24]} for r in rows if r.get("title") or r.get("name")][:2]
        return {"found": len(rows), "fresh": sum(1 for r in rows if r.get("new")), "top": top}

    def bots(self):
        return [self.bot_view(b) for b in self.store.find("bots", desc=False)]

    def draft_bot(self, job):
        try:
            d, _ = self.llm.ask_json("chat", DRAFT_SYSTEM, job)
        except (NoModel, httpx.HTTPError, ValueError):
            url = re.search(r"https?://\S+|\b[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}(?:/\S*)?", job, re.I)
            filler = {"every", "morning", "daily", "check", "find", "keep", "watch", "look", "with", "that", "this", "from", "your", "want",
                      "please", "could", "would", "eye", "new", "cheap", "each", "week", "hour", "hourly", "night", "evening", "tell", "when"}
            words = [w for w in re.findall(r"[A-Za-z]+", job) if len(w) > 3 and w.lower() not in filler][:2]
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
        typed = re.search(r"https?://[^\s,]+|\b(?:localhost|\d{1,3}(?:\.\d{1,3}){3}|[\w-]+(?:\.[\w-]+)*\.[a-z]{2,})(?::\d+)?(?:/[^\s,]*)?", job, re.I)
        raw = typed.group(0).rstrip(".,);") if typed else ""
        typed = skills.web_address(raw, "") if raw else None
        host = lambda u: (urlparse(u or "").hostname or "").removeprefix("www.")
        if typed and not (re.match(r"https?://|localhost\b|\d", raw, re.I) or host(typed) == host(skills.web_address(d.get("start_url") or "", ""))):
            typed = None  # “Node.js” is a word, not an address, unless the model read it as that site too
        known = next((u for n, u in KNOWN_SITES.items() if re.search(rf"\b{n}\b", job, re.I)), None)
        if typed:  # the address you wrote, as you wrote it (http for your own machines), over the model's version of it
            d["start_url"] = typed
        elif known:  # you named it, just not by its address
            d["start_url"] = known
        elif d.get("start_url"):  # a site you didn't name is the model's guess: one suggestion among the ones found, not where it starts
            site = skills.site_of(urlparse(skills.web_address(d["start_url"], "")).hostname)
            if site and site not in job.lower() and site not in re.sub(r"[\s-]", "", job.lower()):  # “Stack Overflow” names stackoverflow.com
                d["guess"], d["start_url"] = skills.web_address(d["start_url"], ""), None
        d["questions"] = [q for q in d.get("questions") or [] if isinstance(q, str) and not re.search(r"\b(website|web site|which site|what site|url)\b", q, re.I)][:2]
        said = lambda f: {**f, "value": [v for v in f["value"] if stated({**f, "value": v}, job)]} if isinstance(f.get("value"), list) else f
        d["filters"] = [f for f in (said(f) for f in d.get("filters") or [] if isinstance(f, dict)) if stated(f, job)]  # a rule you never said (“wholesale is true”) isn't yours
        d["search"] = [q for q in d.get("search") or [] if isinstance(q, str) and q.strip()][:3] or [d.get("goal") or job]
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
                            "quiet_from": "23:00", "quiet_to": "07:00",
                            **({"at": time_of_day(f"{d.get('job') or ''} {d.get('summary') or ''}") or "07:30"}  # just before the paper
                               if minutes(d.get("every_minutes")) >= 1440 else {})},
               "mode": "own", "computer": "local", "created": time.time(),
               "site_queue": [u for u in (skills.web_address(x, "") for x in d.get("more_sites") or []) if u][:60],  # learned one after another
               "persona": persona_mod.normalize(d.get("persona"), look.get("kind", "octopus"))}
        if bot["site_queue"] and bot.get("start_url"):  # several sites: one progress message while it learns them
            bot["site_batch"] = {"total": 1 + len(bot["site_queue"]), "done": [], "msg": None}
        bid = self.store.insert("bots", bot, status="idle")
        self.drop_profile(bid)  # a new bot never inherits sign-ins left by an old one with this id
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
        if patch.get("mode") == "screen" and not self.screen_allowed():
            raise ValueError("Bots may not use your screen yet. Turn on “Allow bots on my screen” in Settings first.")
        if "look" in patch:
            patch["look"] = {**b.get("look", {}), **patch["look"]}
        if "schedule" in patch:
            patch["schedule"] = {**(b.get("schedule") or {}), **(patch["schedule"] or {})}
            if minutes(patch["schedule"].get("every_minutes")) >= 1440 and not patch["schedule"].get("at"):
                patch["schedule"]["at"] = "07:30"
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
        self.drop_profile(bid)  # its browser and sign-ins go too
        for t in ("skills", "runs", "results", "messages", "events", "needs", "diary"):
            self.store.delete(t, bot_id=bid)
        self.store.delete("bots", bid)
        self.bus.publish("bots")

    def drop_profile(self, bid):
        import shutil
        shutil.rmtree(self.home / "profiles" / f"bot-{bid}", ignore_errors=True)

    # ---------------------------------------------------------- computers
    def computer(self, bid):
        with self.lock:
            c = self.computers.get(bid)
            if c and c.alive:
                return c
            b = self.store.get("bots", bid)
            headful = b.get("mode") == "screen" and self.screen_allowed() and not os.environ.get("INKY_HEADLESS")  # INKY_HEADLESS: tests, servers
            c = Computer(bid, self.home / "profiles" / f"bot-{bid}", look=b.get("look"), headful=headful,
                         on_frame=None, on_control=self._on_control)
            self.computers[bid] = c
            if b.get("pending_cookies"):
                c.call("add_cookies", b["pending_cookies"])
                self.store.update("bots", bid, pending_cookies=None)
            self.apply_overlay(bid)
            return c

    def screen_allowed(self):
        """You allowed bots on your screen (Settings). Off until you say so; turning it off keeps every bot off it."""
        return bool(self.store.setting("app", {}).get("screen_allowed"))

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
        self.notify(bid, f"{title}\n{body}", need=nid)
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
        if h.kind in SELF_HANDLED and not meta.pop("ask", False):  # the bot deals with it; you only hear about it
            return self.handle(bid, h, **meta)
        if h.kind in SELF_HANDLED:
            meta["asked"] = True  # it asked on purpose (tried three times, or you were showing it): never closed on its own
        roles = self.llm.roles()
        opts = [o for o in h.options if not (o == "Try a smarter model" and roles.get("smart") == roles.get("repair"))]  # same model: no point
        if not (meta.get("skill_id") or h.meta.get("skill_id")):  # nothing to replay up to: showing it once can't record anything
            opts = [o for o in opts if o != "Show me once"] or ["Try again"]
        same = next((n for n in self.store.find("needs", bot_id=bid, status="open") if n.get("kind") == h.kind and n.get("title") == h.title
                     and n.get("skill_id") == (meta.get("skill_id") or h.meta.get("skill_id"))), None)
        if same:  # the same problem again (a scheduled rerun): one card, one notification
            self.store.update("needs", same["id"], body=h.body, options=opts, seen=time.time())
            self.bus.publish("needs", bot=bid)
            return same["id"]
        nid = self.store.insert("needs", {"kind": h.kind, "title": h.title, "body": h.body, "options": opts, **h.meta, **meta},
                                bot_id=bid, status="open")
        self.store.message(bid, "bot", f"{h.title}. {h.body}", need=nid)
        self.store.event(bid, "problem", h.title, need=nid)
        self.bus.publish("needs", bot=bid)
        self.notify(bid, f"{h.title}\n{h.body}", need=nid)
        return nid

    def handle(self, bid, h, **meta):
        """A problem the bot sorts out itself: it tries again later (learning the site again when a step broke), and only after
        the third time in a row does it ask you, once. A rule or a site fence that stopped it is just said."""
        b = self.store.get("bots", bid)
        if h.kind == "blocked":
            self.store.message(bid, "bot", f"{h.title}. {h.body}")
            self.store.event(bid, "handled", h.title)
            self.bus.publish("messages", bot=bid)
            return None
        sid = meta.get("skill_id") or h.meta.get("skill_id")
        sk = self.store.get("skills", sid) if sid else None
        urls = [u for u in (meta.get("urls") or h.meta.get("urls") or [meta.get("url") or h.meta.get("url") or (sk or {}).get("start_url")]) if u]
        host = lambda u: (urlparse(u).netloc or u).removeprefix("www.")
        fails, retries, later = dict(b.get("fails") or {}), list(b.get("retries") or []), []
        offline = bool(OFFLINE.search(f"{h.title} {h.body} {meta.get('error') or ''}"))
        for u in urls or [None]:
            key = f"skill:{sid}" if sid else f"site:{skills.site_of(urlparse(u or '').hostname or '')}"
            n = fails.get(key, 0) + (0 if offline else 1)  # this computer was offline: not the site's fault, so it doesn't count
            fails[key] = n
            if n >= 3:  # it keeps failing: now it's worth your time, once
                fails[key] = 0
                self.store.update("bots", bid, fails=fails)
                opts = ["Show me once", "Learn it again", "Remove this site"] if sid else ["Show me once", "Try again", "Skip this site"]
                return self.problem(bid, skills.NeedsHelp(h.kind, f"{host(u or '') or 'A site'} hasn’t worked {n} times in a row",
                                                          f"{h.body} I tried again each time on my own.", opts),
                                    ask=True, **{k: v for k, v in {**h.meta, **meta, "url": u, "skill_id": sid}.items() if k != "urls"})
            if not any(r.get("key") == key for r in retries):
                at = time.time() + (600 if offline else 1800 if n <= 1 else 7200)  # offline: in 10 minutes; else in half an hour, then two hours
                retries.append({"key": key, "at": at, "sid": sid, "url": u, "goal": meta.get("goal") or b.get("goal"),
                                "do": "learn" if (h.kind == "fix_failed" and sk) or not sid else "run"})
                later.append(at)
        self.store.update("bots", bid, fails=fails, retries=retries)
        later += [r["at"] for r in retries if r.get("at") and any(r.get("key") == f"skill:{sid}" or (r.get("url") in urls) for _ in [0])]  # already planned
        when = f"at {datetime.fromtimestamp(min(later)).strftime('%H:%M')}" if later else "soon"
        what = ", ".join(host(u) for u in urls[:3]) + (f" and {len(urls) - 3} more" if len(urls) > 3 else "") if urls else "it"
        why = plain_error(h.body) if h.body and len(h.body) < 160 else ""
        text = f"{h.title} ({what}){': ' + why.rstrip('.') if why else ''}. I’ll try again on my own {when}; nothing for you to do."
        self.store.message(bid, "bot", text, handled=True, kind="status")
        self.store.event(bid, "handled", text)
        self.bus.publish("messages", bot=bid)
        return None

    def retry_now(self, bid=None):
        """What the bots planned to try again later: now. The first starts at once, the rest follow one after another."""
        n = 0
        for b in [self.store.get("bots", bid)] if bid else self.store.find("bots"):
            if b and b.get("retries"):
                self.store.update("bots", b["id"], retries=[dict(r, at=0) for r in b["retries"]])
                n += len(b["retries"])
        threading.Thread(target=self.tick, daemon=True).start()
        return n

    def _worked(self, bid, key):
        b = self.store.get("bots", bid) or {}
        if key in (b.get("fails") or {}):
            self.store.update("bots", bid, fails={k: v for k, v in b["fails"].items() if k != key})

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
        if decision == "Learn it again":
            sk = self.store.get("skills", n.get("skill_id")) if n.get("skill_id") else None
            u = n.get("url") or (sk or {}).get("start_url")
            if u:
                self.learn(bid, n.get("goal") or (self.store.get("bots", bid) or {}).get("goal"), u, replace=n.get("skill_id"))
            return
        if decision == "Remove this site":
            if n.get("skill_id"):
                self.store.delete("skills", n["skill_id"])
                self.store.message(bid, "bot", "Done: I won’t check that site any more.")
                self.bus.publish("messages", bot=bid)
            return
        if decision == "Skip this site":
            return
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
        elif decision == "Try them again" and n.get("urls"):
            urls = [u for u in n["urls"] if u]
            self.store.update("bots", bid, site_queue=urls, site_batch={"total": len(urls), "done": [], "msg": None})
            threading.Thread(target=self._learn_next, args=(bid, n.get("goal") or (self.store.get("bots", bid) or {}).get("goal")), daemon=True).start()
        elif decision in ("Show me once",):
            self.start_show(bid, n)
        elif decision in ("Open its computer",):
            self.store.update("bots", bid, resume_after_handback=n.get("skill_id") or True)  # carry on with that skill, not all of them
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
        correcting = bool(run and run.kind == "learn" and run.thread and run.thread.is_alive())
        if correcting:  # while it learns, what you say steers the learner
            run.fixes.append(text)
        if not sender and not correcting:
            last = next((m for m in self.store.find("messages", bot_id=bid, limit=6) if m["role"] == "bot"), None)
            if last and last.get("offers") and not last.get("chips_used") and AFFIRM.match(text):  # “yes” to the button it offered
                return self._say(bid, self.take_offer(bid, last["id"], 0, said_yes=True))
            if RECAP.search(text):  # “what did you do?”: the facts, not a guess from the model
                said, items = self.recap(bid)
                return self._say(bid, said, **({"items": items} if items else {}))
            fact = self.facts(bid, text)
            if fact:  # “what's the cheapest?”, “how many did you find?”: from what it found, never a guess
                said, items = fact if isinstance(fact, tuple) else (fact, [])
                return self._say(bid, said, **({"items": items} if items else {}))
            if (SCREEN_ASK.search(text) or OWN_ASK.search(text)) and (not is_question(text) or POLITE.match(text)):
                return self._say(bid, self._switch_screen(bid, bool(SCREEN_ASK.search(text))))
            h = handoff(text)
            if h:  # you named the agent: it goes to that one, with what this bot found
                return self._handoff(bid, *h)
            cmd = quick_command(text)
            f = None if cmd or text.lower().startswith("new rule:") else limit_filter(re.sub(r"[.!]+$", "", FILLER.sub("", text.strip())))
            if f:  # “only keep books under £15”: a limit is as plain as a command
                seen = self.store.find("results", bot_id=bid, limit=1)
                if seen and f["field"] not in seen[0]:
                    f = {**f, "field": "price"} if "price" in seen[0] else None
                elif not seen and f["field"] not in ("price", "size", "rooms", "year", "km", "rating", "floor", "area", "weight"):
                    f = {**f, "field": "price"}  # “books under 15”: the thing itself isn't a field, its price is
            if f:
                word = {"<": "under", "<=": "at most", ">": "over", ">=": "at least"}[f["op"]]
                val = int(f["value"]) if float(f["value"]).is_integer() else f["value"]
                cur = (re.search(r"[£€$]", text) or [""])[0]  # “under £15” stays in pounds
                cmd = {"type": "add_rule", "text": f"{f['field']} {word} {cur}{val}", "kind": "filter", "filter": f}
            if cmd:  # plain commands never depend on how good the model is
                try:
                    out = self.apply_action(bid, cmd)
                except Guard as g:
                    return self._say(bid, "Nothing is running right now." if cmd["type"] == "stop" else
                                     "I already remember that." if "already remembered" in str(g) else "Nothing to change.")
                except Exception as e:
                    return self._say(bid, f"I couldn’t: {e}")
                r = self._say(bid, command_reply(cmd, out))
                return {**r, "actions": [cmd], "done": [out]}
        results = [r for r in self.store.find("results", bot_id=bid, limit=10) if r.get("passed") is not False][:3]
        fields = sorted({k for r in results for k in r if k not in ("id", "bot_id", "status", "key", "ts", "run", "skill", "new")})
        sk = self.store.find("skills", bot_id=bid)
        hist = [m for m in reversed(self.store.find("messages", bot_id=bid, limit=12))]
        saved = len(self.kept(bid, b=b))  # under your rules as they are now
        status = self.bot_view(b)["status"] + (f" · {run.step}" if run and run.step else "") + \
            ("" if saved else ". You have NO results yet: never say you found anything." + ("" if sk else " You haven’t learned a site yet."))
        last = next((r for r in self.store.find("runs", bot_id=bid, limit=5) if r.get("kind") == "replay" and r.get("status") == "ok"), None)
        if last:
            status += (f". Last run {datetime.fromtimestamp(last['ts']).strftime('%a %H:%M')}: {last.get('items', 0)} results, "
                       f"{last.get('matched', 0)} pass the rules, {last.get('new', 0)} new, {nres(last.get('ai_calls', 0), 'AI call')}. "
                       f"Results that pass your rules now: {saved}")
        sys = CHAT_SYSTEM.format(name=b["name"], job=b.get("job", ""), tone=b.get("look", {}).get("tone", "cheerful"),
                                 fields=", ".join(fields) or "none yet", rules="; ".join(r["text"] for r in b.get("rules", [])),
                                 memory="; ".join(m["text"] for m in b.get("memory", [])) or "nothing yet",
                                 skills="; ".join(f"{s['name']} ({len(s['steps'])} steps)" for s in sk) or "none yet",
                                 status=status, tools="\n".join(self.mcp.catalog()) or "none",
                                 others="; ".join(f"{o['name']} ({(o.get('job') or '')[:70]}; {o['status'].replace('_', ' ')})" for o in self.bots() if o["id"] != bid and o["status"] != "moved") or "none")
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
            if d is None and t.strip() and not re.search(r'^\s*(```|\{)|"reply"\s*:', t):  # plain words, no JSON at all: that's its reply
                d = {"reply": t.strip()[:4000], "actions": []}
            if d is None:  # broken JSON: say so once and ask again
                t2, _ = self.llm.chat("chat", msgs + [{"role": "assistant", "content": t},
                                                      {"role": "user", "content": "That wasn’t valid JSON. Send the same answer as ONE valid JSON object."}],
                                      bot_id=bid, max_tokens=900)
                d = try_json(t2)
            if d is None:
                d = {"reply": t.strip()[:800] if not t.lstrip().startswith("{") else "Sorry, I got muddled. Could you say that again?", "actions": []}
        except NoModel as e:
            d = {"reply": str(e), "actions": []}
        except ModelStopped:
            d = {"reply": "Stopped.", "actions": []}
        except Exception as e:
            from inky.llm import PROVIDERS
            prov = (self.llm.roles().get("chat") or {}).get("provider")
            why = llm_plain(e, PROVIDERS.get(prov, {}).get("label", "my model"))
            d = {"reply": f"{why[:1].upper()}{why[1:]} Check Models.", "actions": []}
        done, held, failed, offers = [], False, False, []
        new_rule = not sender and text.lower().startswith("new rule:")
        pre = self.store.get("bots", bid)  # the rules before the model touched them
        for a in d.get("actions") or []:
            for k in ("text", "goal", "label"):  # the model sometimes copies the /no_think switch into what it saves
                if isinstance(a.get(k), str):
                    a[k] = re.sub(r"\s*/no_think\b", "", a[k]).strip()
            if new_rule and a.get("type") != "add_rule":  # Settings' rule box only ever adds a rule
                continue
            try:
                done.append(self.apply_action(bid, a, said=text))
            except Guard as g:
                held = True
                if g.offer and not sender and a.get("type") not in ("delegate", "ask_bot"):
                    offers.append(a)
            except Exception as e:
                failed = True
                done.append(f"Couldn’t do that: {e}")
        if new_rule:
            rule = text.split(":", 1)[1].strip()
            kind = "never" if re.match(r"^(never|don.?t|do not)\b", rule, re.I) else "ask" if re.search(r"\b(ask|before|first|check with)\b", rule, re.I) else "own"
            bb = self.store.get("bots", bid)
            f = limit_filter(rule)
            seen = self.store.find("results", bot_id=bid, limit=1)
            if f and seen and f["field"] not in seen[0]:  # “books under 10”: the number is a price when results have one
                f = {**f, "field": "price"} if "price" in seen[0] else None
            added = any(str(x).startswith("rule:") for x in done)
            if f:  # “price under 15” is a limit on results, whatever the model made of it: the exact limit replaces its version
                kind, bb = "filter", pre
                same = lambda x: x.get("field") == f["field"] and x.get("op") == f["op"] and skills.parse_num(x.get("value")) == f["value"]
                have = any(same(x) for x in bb.get("filters", []))
                self.store.update("bots", bid, rules=bb.get("rules", []) + ([] if have else [{"kind": "filter", "text": rule}]),
                                  filters=bb.get("filters", []) + ([] if have else [{**f, "text": rule}]))
                done = [x for x in done if not str(x).startswith("rule:")] + [f"already a rule: {rule}" if have else f"rule: {rule}"]
            elif rule and not added:  # a small model returned no action: add it anyway
                self.store.update("bots", bid, rules=bb.get("rules", []) + [{"kind": kind, "text": rule}])
                done.append(f"rule: {rule}")
            elif rule and kind in ("never", "ask"):  # it said Never / Ask first: that's the kind, whatever the model picked
                rules = bb.get("rules", [])
                if rules and rules[-1].get("kind") != kind:
                    self.store.update("bots", bid, rules=rules[:-1] + [{**rules[-1], "kind": kind}],
                                      filters=[f for f in bb.get("filters", []) if f.get("text") != rules[-1].get("text")])
        reply = re.sub(r"\s*/no_think\b", "", d.get("reply") or "").strip() or "OK."
        did = [x for x in done if not str(x).startswith(("Couldn’t", "already a rule"))]
        chips, kept = [], []
        for a in offers:  # what it wanted to do but you didn't ask for: one tap away, never done on its own
            a = self._offerable(bid, a, text)
            if a and not any(x["type"] == a["type"] for x in kept):
                kept.append(a)
                chips.append({"label": self._offer_label(a), "offer": len(kept) - 1})
        promise = re.search(r"\b(I'?ll|I will|I’ll|I've|I’ve|I have|let me|done|handled|consider it|updated|changed|set|added|removed|scheduled)\b", reply, re.I)
        if failed and not did and not sender and not correcting and promise:
            reply = "That didn’t work, so nothing changed."
        elif held and not did and not chips and not sender and not correcting and promise:  # it talked about doing something that didn't happen
            reply = "I haven’t changed anything."
        elif chips:
            reply = f"{reply} Want me to?" if promise and not reply.rstrip().endswith("?") else reply
        self.store.message(bid, "bot", reply, actions=[a.get("type") for a in d.get("actions") or []], done=done, team=bool(sender), to_peer=bool(sender),
                           **({"chips": chips, "offers": kept} if chips else {}))
        self.bus.publish("messages", bot=bid)
        return {"reply": reply, "actions": d.get("actions") or [], "done": done}

    def apply_action(self, bid, a, said=None):
        """An action the model proposed. said: the message it answers, so it only does what was asked."""
        b = self.store.get("bots", bid)
        t = a.get("type")
        if t not in ACTIONS:
            raise Guard(f"unknown action {t}")
        if said is not None and t in CHANGES and is_question(said) and not POLITE.match(said):
            raise Guard("a question isn't a request", offer=True)  # “Should you run every 5 minutes?” changes nothing
        if t == "add_rule":
            kind = "filter" if a.get("filter") else (a.get("kind") if a.get("kind") in ("own", "ask", "never") else "own")
            if not (a.get("text") or "").strip():
                raise ValueError("the rule has no words")
            rules, filters = b.get("rules", []), b.get("filters", [])
            f = a.get("filter")
            if f and f.get("op") in FLIP and negated(a["text"], f.get("value")):  # a small model reads “skip senior” as “contains senior”
                f = {**f, "op": FLIP[f["op"]]}
            if f and f.get("op") in ("<", "<=", ">", ">="):  # “only under £15” replaces “under £20”: one limit per field and direction
                way = f["op"][0]
                old = [x for x in filters if x.get("field") == f.get("field") and str(x.get("op", ""))[:1] == way]
                gone = {x.get("text") for x in old}
                filters = [x for x in filters if x not in old]
                rules = [r for r in rules if not (r["kind"] == "filter" and r["text"] in gone)]
            rules = rules + [{"kind": kind, "text": a["text"].strip()}]
            filters = filters + ([{**f, "text": a["text"]}] if f else [])
            self.store.update("bots", bid, rules=rules, filters=filters)
            return f"rule: {a['text']}"
        if t == "remove_rule":
            if said is not None and (said.lower().startswith("new rule:") or not REMOVING.search(said)):
                raise Guard("you didn’t ask me to remove a rule", offer=True)
            rules = b.get("rules", [])
            mine = [j for j, r in enumerate(rules) if r.get("text") not in DEFAULT_RULE_TEXTS]
            i = (mine[-1] if mine else None) if a.get("last") else best_match(a.get("text"), rules, key=lambda r: r["text"])  # “forget that rule”: the newest of yours
            if i is None:
                raise ValueError("you have no rules of your own yet" if a.get("last") else f"no rule like “{a.get('text')}”")
            gone = rules[i]["text"]
            self.store.update("bots", bid, rules=rules[:i] + rules[i + 1:], filters=[f for f in b.get("filters", []) if f.get("text", "") != gone])
            return f"removed rule: {gone}"
        if t == "remember":
            if said is not None and is_question(said) and not re.search(r"\bremember\b", said, re.I):
                raise Guard("a question isn't something to remember", offer=True)
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
                raise Guard("you didn’t ask me to learn a site", offer=True)  # a question is never a reason to go learning
            if b.get("allowed_domains") and url and skills.site_of(urlparse(url).hostname) not in {skills.site_of(d) for d in b["allowed_domains"]}:
                raise ValueError(f"I only work on {', '.join(b['allowed_domains'])}")
            self.learn(bid, a.get("goal") or b.get("goal"), url)
            return f"learning {urlparse(url).hostname or url}"
        if t == "run":
            self.run(bid)
            return "started a run"
        if t == "schedule":
            s = {**b.get("schedule", {}), **{k: a[k] or None for k in ("summary_at", "quiet_from", "quiet_to") if a.get(k) is not None}}
            if a.get("every_minutes") is not None:
                s["every_minutes"] = minutes(a["every_minutes"])  # 0 = only when you ask
            if minutes(s.get("every_minutes")) >= 1440:  # daily and weekly checks run at a time of day
                s["at"] = (a.get("at") if re.fullmatch(r"\d{2}:\d{2}", str(a.get("at") or "")) else None) or time_of_day(said) or s.get("at") or "07:30"
            self.store.update("bots", bid, schedule=s)
            m = minutes(s.get("every_minutes"))
            return (f"I’ll check every {every_words(m)}" + (f" at {s['at']}" if m >= 1440 else "")) if m else "I’ll only run when you ask"
        if t in ("pause", "resume", "stop"):
            running = self.busy(bid)
            if t == "stop" and not running:
                raise Guard("nothing to stop")
            self.control(bid, t)
            return {"pause": "paused" if running else "paused its schedule", "resume": "resumed", "stop": "stopped"}[t]
        if t == "speed":
            v = a.get("value") if a.get("value") in ("slow", "normal", "turbo") else "turbo" if a.get("value") == "fast" else "normal"
            self.update_bot(bid, {"look": {"speed": v}})
            return f"speed: {v}"
        if t == "delegate":
            srv = a.get("server")
            if not (self.mcp.known(srv) or self.mcp.builtin and self.mcp.builtin.has(srv)):
                other = next((o for o in self.store.find("bots") if o["id"] != bid and o["name"].lower() == str(srv or "").lower()), None)
                if other:  # the model handed a job to another bot as if it were a connector: that's asking the bot
                    args = a.get("args") or {}
                    return self.apply_action(bid, {"type": "ask_bot", "bot": other["name"], "text": args.get("prompt") or args.get("description") or a.get("label") or ""})
                raise ValueError(f"there’s no connector called {srv}")
            threading.Thread(target=self.delegate, args=(bid, a), daemon=True).start()
            return f"handing to {srv}"
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

    def _handoff(self, bid, server, task):
        b = self.store.get("bots", bid)
        srv = next((x for x in self.mcp.servers() if x["name"] == server), None)
        who = self.mcp.label(server)
        if not srv or not srv["installed"]:
            return self._say(bid, f"{who} isn’t installed on this computer. Connectors shows how to get it.")
        if server == "claude-code" and connectors.signed_in("claude-code", timeout=15) is False:
            alt = " Codex can take it now: say “ask Codex to …”." if any(x["name"] == "codex" and x["installed"] for x in self.mcp.servers()) else ""
            return self._say(bid, f"Claude Code isn’t signed in on this computer, so it can’t take a whole job. Open a terminal, run claude "
                                  f"and sign in, then ask again.{alt}")
        if not srv["connected"]:
            try:
                self.mcp.connect(server)
            except Exception as e:
                return self._say(bid, f"I couldn’t reach {who}: {plain_error(e)}. Connectors → {who} → Connect.")
        kept = self.kept(bid, b=b)  # your rules as they are now
        found = [{k: r.get(k) for k in ("title", "price", "link") if r.get(k)} for r in kept][:20]
        prompt = (f"{task}\n\nContext: you're helping {b['name']}, an Inky bot whose job is: {b.get('job') or b.get('goal')}."
                  + (f" What it has found so far (JSON):\n{json.dumps(found, ensure_ascii=False)}" if found else " It hasn't found anything yet."))
        label = f"Ask {who}: {skills.short(task, 60)}"
        a = ({"server": "codex", "tool": "codex", "args": {"prompt": prompt, "sandbox": "read-only"}, "label": label} if server == "codex" else
             {"server": "claude-code", "tool": "Agent", "args": {"description": skills.short(task, 40), "prompt": prompt, "subagent_type": "general-purpose"}, "label": label})
        threading.Thread(target=self.delegate, args=(bid, a), daemon=True).start()  # it asks you first
        r = self._say(bid, f"I’ll hand that to {who} as soon as you say yes. Its answer comes back here.")
        return {**r, "actions": [{"type": "delegate", **a}], "done": [f"handing to {server}"]}

    def _said_stopped(self, bid):
        """A run that ends because you stopped it says so once: not again after the chat already said “Stopped.”"""
        last = next((m for m in self.store.find("messages", bot_id=bid, limit=3) if m["role"] == "bot"), None)
        if not (last and last["text"].startswith("Stopped") and time.time() - last["ts"] < 30):
            self.store.message(bid, "bot", "Stopped.", kind="status")

    def _say(self, bid, text, **meta):
        self.store.message(bid, "bot", text, **meta)
        self.bus.publish("messages", bot=bid)
        return {"reply": text, "actions": [], "done": []}

    def _offerable(self, bid, a, said=""):
        """An action worth offering as a button, or None: it must change something, and match what you said.
        “Learn the site again” on a bot that already knows it means: run it."""
        b = self.store.get("bots", bid)
        if a.get("type") == "speed":
            v = a.get("value") if a.get("value") in ("slow", "normal", "turbo") else None
            v = v or ("turbo" if re.search(r"\b(fast|faster|quick|quicker|turbo|speed up)\b", said, re.I) else
                      "slow" if re.search(r"\b(slow|slower|careful)\b", said, re.I) else None)
            return {**a, "value": v} if v and v != (b.get("look") or {}).get("speed", "normal") else None
        if a.get("type") == "schedule":
            m = minutes(a.get("every_minutes")) if a.get("every_minutes") is not None else None
            return a if m is not None and m != minutes((b.get("schedule") or {}).get("every_minutes")) else None
        if a.get("type") == "learn":
            url = skills.web_address(a.get("url") or b.get("start_url"), "")
            site = url and skills.site_of(urlparse(url).hostname)
            if not url:
                return None
            if any(skills.site_of(urlparse(sk.get("start_url") or "").hostname or "") == site for sk in self.store.find("skills", bot_id=bid)):
                return {"type": "run"}
            return {**a, "url": url}
        if a.get("type") == "remember" and not (a.get("text") or "").strip():
            return None
        return a

    def _offer_label(self, a):
        t, txt = a["type"], skills.short(str(a.get("text") or ""), 40)
        if t == "schedule":
            m = minutes(a.get("every_minutes"))
            return f"Yes, check every {every_words(m)}" if m else "Yes, only run when I ask"
        return {"run": "Yes, run it now", "pause": "Yes, pause it", "resume": "Yes, resume it", "stop": "Yes, stop it",
                "speed": f"Yes, go {a.get('value') or 'normal'}", "remember": f"Yes, remember “{txt}”", "forget": f"Yes, forget “{txt}”",
                "add_rule": f"Yes, add “{txt}”", "remove_rule": f"Yes, remove “{txt}”", "add_automation": "Yes, add that automation",
                "learn": f"Yes, learn {urlparse(a.get('url') or '').hostname or 'that site'}"}.get(t, "Yes, do it")

    def take_offer(self, bid, msg_id, i, said_yes=False):
        """You tapped (or said yes to) what the bot offered. Only what that very message offered, once."""
        m = self.store.get("messages", int(msg_id))
        if not m or m.get("bot_id") != bid or not m.get("offers") or m.get("chips_used"):
            raise ValueError("That was already done, or it’s gone.")
        offers = m["offers"]
        if not 0 <= int(i) < len(offers):
            raise ValueError("That isn’t one of its offers.")
        a, label = offers[int(i)], next((c["label"] for c in m.get("chips") or [] if c.get("offer") == int(i)), "it")
        self.store.update("messages", m["id"], chips_used=True)
        try:
            out = self.apply_action(bid, a)  # you asked for it: no question guard
        except Exception as e:
            return f"I couldn’t: {e}."
        self.bus.publish("messages", bot=bid)
        return {"run": "Running now.", "learning": "Learning it now."}.get(out, f"Done: {label.removeprefix('Yes, ')}.") if said_yes else out

    def facts(self, bid, text):
        """The cheapest, the dearest or how many: answered from the results it kept (as Found shows them), or None."""
        price, count = PRICE_Q.search(text or ""), COUNT_Q.search(text or "")
        if not (price or count):
            return None
        b = self.store.get("bots", bid)
        rows = self.kept(bid, b=b)
        if not rows:
            return "I haven’t found anything yet." + ("" if self.store.find("skills", bot_id=bid) else " I haven’t learned my site yet." if b.get("start_url")
                                                     else " Tell me a site and I’ll learn it.")
        rules = " that pass your rules" if b.get("filters") else ""
        if count:
            fresh = sum(1 for r in rows if r.get("new"))
            last = next((r for r in self.store.find("runs", bot_id=bid, limit=10) if r.get("kind") == "replay" and r.get("status") == "ok"), None)
            read = f" My last check read {nres(last['items'])}." if last and last.get("items") and last["items"] != len(rows) else ""
            return f"I’ve found {nres(len(rows), 'thing')}{rules}" + (f", {fresh} new." if fresh else ".") + read
        priced = [(skills.parse_num(r.get("price")), r) for r in rows]
        priced = [(p, r) for p, r in priced if p is not None]
        if not priced:
            return f"None of the {nres(len(rows), 'thing')} I found shows a price."
        top = re.search(r"most|priciest|dearest|highest", price.group(0), re.I)
        p, r = (max if top else min)(priced, key=lambda x: x[0])
        name = r.get("title") or r.get("name") or "One"
        return f"The {'most expensive' if top else 'cheapest'} of the {nres(len(priced), 'thing')}{rules} is “{name}” at {r.get('price')}.", card_items([r])

    def _switch_screen(self, bid, screen):
        """“Work on my screen from now on”: done in code, so it's never claimed and not done."""
        b = self.store.get("bots", bid)
        if (b.get("mode") == "screen") == screen:
            return "I already work on your screen." if screen else "I already work on my own computer."
        try:
            self.update_bot(bid, {"mode": "screen" if screen else "own"})
        except ValueError:
            return "I can’t use your screen yet: bots aren’t allowed on it. Turn on “Allow bots on my screen” in Settings, then ask me again."
        return "Done: from now on I work in a window on your screen." if screen else "Done: from now on I work on my own computer, out of your way."

    def recap(self, bid):
        """What it did, from its own records, in two short sentences: the last check and what's next. -> (text, newest results)."""
        b = self.store.get("bots", bid)
        v = self.bot_view(b)
        runs = [r for r in self.store.find("runs", bot_id=bid, limit=20) if r.get("status") != "running"]
        busy = self.busy(bid)
        if not runs:
            return "I haven’t run yet. " + ("I’m working on it right now." if busy else "Press Run now and I’ll start." if v["skills"] or b.get("start_url")
                                            else "Tell me a site and what to look for, and I’ll learn it."), []
        r, when, items = runs[0], when_words(runs[0]["ts"]), []
        sites = len(v["skills"])
        rules = " that pass your rules" if b.get("filters") else ""
        last = {}  # the latest check of each site: with several sites, the last run alone is only one of them
        for x in runs:
            if x.get("kind") == "replay" and x.get("status") == "ok" and x.get("items") is not None:
                last.setdefault(x.get("skill"), x)
        site = lambda k: str(k or "a site").removeprefix("Check ").removeprefix("www.")
        if r.get("kind") == "learn":
            s = f"{when} I learned {(urlparse(r.get('url') or b.get('start_url') or '').netloc or 'the site').removeprefix('www.')}" + \
                ("." if r.get("status") == "ok" else f", but it stopped: {plain_error(r.get('note') or r.get('status')).rstrip('.')}.")
        elif r.get("status") == "ok":
            ai = sum(x.get("ai_calls") or 0 for x in last.values()) if sites > 1 else r.get("ai_calls") or 0
            checked = f"{len(last)} sites ({', '.join(site(k) for k in last)})" if sites > 1 and len(last) > 1 else f"“{site(r.get('skill') or 'my check')}”"
            s = (f"{when} I checked {checked}: {v['found']} found{rules}, {v['fresh']} new." if r.get("items") or v["found"]
                 else f"{when} I ran {checked}.") + (f" I used AI {'once' if ai == 1 else f'{ai} times'} to fix a step." if ai else "")
            items = card_items([x for x in self.kept(bid, 200, b=b) if x.get("new")])  # shown as rows under the message
        else:
            s = f"{when} my run {'stopped' if r.get('status') == 'stopped' else 'needed you' if r.get('status') == 'needs_you' else 'failed'}" + \
                (f": {plain_error(r['note']).rstrip('.')}." if r.get("note") else ".")
        if busy:
            s += " I’m checking again right now."
        elif b.get("held"):
            s += " My schedule is paused."
        elif v.get("next_run"):
            s += f" Next check {when_words(v['next_run'], future=True)}."
        if v.get("needs"):
            s += f" {nres(v['needs'], 'thing')} {'needs' if v['needs'] == 1 else 'need'} you."
        return s, items
        r, when = runs[0], when_words(runs[0]["ts"])
        sites = len(v["skills"])
        lead = (f"So far I’ve found {v['found']} {'that pass your rules' if b.get('filters') else 'things'}"
                + (f" on {sites} sites" if sites > 1 else "") + (f", {v['fresh']} new. " if v["fresh"] else ". ")) if sites > 1 or (v["found"] and v["found"] != r.get("matched")) else ""  # one site: its last run says it
        last = {}  # the latest check of each site: with several sites, the last run alone is only one of them
        for x in runs:
            if x.get("kind") == "replay" and x.get("status") == "ok" and x.get("items") is not None:
                last.setdefault(x.get("skill"), x)
        if sites > 1 and len(last) > 1 and r.get("kind") == "replay":
            ai = sum(x.get("ai_calls") or 0 for x in last.values())
            s = lead + f"{when}, I checked {len(last)} sites: " + ", ".join(
                f"{str(k or 'a site').removeprefix('Check ').removeprefix('www.')} {x.get('matched') or 0} of {x.get('items') or 0}" for k, x in last.items()) + \
                (f", with {ai} AI call{'s' if ai != 1 else ''} to fix a step." if ai else ", no AI needed.")
        elif r.get("kind") == "learn":
            s = f"{when}, I learned {(urlparse(r.get('url') or b.get('start_url') or '').netloc or 'the site').removeprefix('www.')}" + ("." if r.get("status") == "ok" else f", but it stopped: {r.get('note') or r.get('status')}.")
        elif r.get("status") == "ok":
            pages = f" over {r['pages']} pages" if (r.get("pages") or 0) > 1 else ""
            reads = r.get("items") is not None and r.get("matched") is not None
            ai = r.get("ai_calls") or 0
            passed = "passed your rules then" if lead else "pass your rules"  # your rules changed since: that count was under the old ones
            s = (f"{when}, I ran “{r.get('skill') or 'my check'}”: read {nres(r.get('items') or 0)}{pages}, {r.get('matched') or 0} {passed}, "
                 f"{r.get('new') or 0} new" if reads else f"{when}, I ran “{r.get('skill') or 'my check'}”") + \
                (f", with {ai} AI call{'s' if ai != 1 else ''} to fix a step." if ai else ", no AI needed.")
            items = card_items([x for x in self.kept(bid, 200, b=b) if x.get("new")])  # shown as rows under the message
        else:
            s = f"{when}, my run {'stopped' if r.get('status') == 'stopped' else 'needed you' if r.get('status') == 'needs_you' else 'failed'}" + \
                (f": {plain_error(r['note']).rstrip('.')}." if r.get("note") else ".")
        if not s.startswith(lead):
            s = lead + s
        if busy:
            s += " I’m working again right now."
        elif b.get("held"):
            s += " My schedule is paused."
        elif v.get("next_run"):
            s += f" Next run {when_words(v['next_run'], future=True)}."
        if v.get("needs"):
            s += f" {v['needs']} thing{'s' if v['needs'] != 1 else ''} need{'s' if v['needs'] == 1 else ''} you in Needs you."
        return s

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
            if r["error"] and a["server"] == "claude-code" and re.search(r"Agent type .* not found|not (logged|signed) in|login", out, re.I):
                out = "it isn’t signed in on this computer, so it can’t take a whole job. Open a terminal, run claude and sign in."
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
            raise RuntimeError("It’s already working. Wait for it to finish, or press Stop.")
        self.runs[bid] = run
        run.thread = threading.Thread(target=target, daemon=True, name=f"run-{bid}")
        run.thread.start()
        self.bus.publish("bots")
        return run

    def learn(self, bid, goal, url, replace=None):
        url = skills.web_address(url, "")
        if not url:
            raise ValueError("It needs a web address to start on, like https://example.com")
        run = Run("learn")
        run.replace = replace  # learning a site again: its new skill takes the broken one's place
        return self._start(bid, run, lambda: self._learn(bid, goal, url, run))

    def _learn(self, bid, goal, url, run):
        run.run_id = self.store.insert("runs", {"kind": "learn", "goal": goal, "url": url}, bot_id=bid, status="running")
        run.site = (urlparse(url).netloc or url).removeprefix("www.")
        b = self.store.get("bots", bid)
        batch = bool(b.get("site_batch"))  # one of several sites you picked: one progress message, one summary at the end
        if batch:
            self._batch_say(bid, now=url)
        else:
            self.store.message(bid, "bot", f"Learning {(urlparse(url).netloc or url).removeprefix('www.')}. Watch if you like, and tell me if I pick something wrong.", kind="status")
            self.bus.publish("messages", bot=bid)
        try:
            skill = skills.learn(Ctx(self, bid, run), goal, url)
            sid = self.store.insert("skills", skill, bot_id=bid, status="ok")
            host = lambda u: (urlparse(u or "").hostname or "").removeprefix("www.")  # the same site, not just the same domain (books. vs quotes.)
            same = run.replace or next((x["id"] for x in self.store.find("skills", bot_id=bid) if x["id"] != sid and host(x.get("start_url")) == host(url)), None)  # learning a site again: its new skill replaces the old one
            if same:
                self.store.delete("skills", same)
                self._worked(bid, f"skill:{same}")
            self._worked(bid, f"site:{skills.site_of(urlparse(url).hostname or '')}")
            self.store.event(bid, "learned", f"Learned {skill['name']}: {nres(len(skill['steps']), 'step')}, {nres(run.ai_calls, 'AI call')}")
            self._finish(run, "ok", learned=sid)
            reads = any(st["action"] == "extract" for st in skill["steps"])
            if not batch:
                self.store.message(bid, "bot", f"Learned {run.site} with {nres(run.ai_calls, 'AI call')}. From now on I check it with none.", kind="status")
                self.bus.publish("messages", bot=bid)
            if reads:  # an action (like sending) already happened while learning: never twice
                run2 = Run("replay", sid)
                self.runs[bid] = run2
                run2.thread = threading.current_thread()
                self._replay(bid, sid, run2, "silent" if batch else "first run after learning")
                chk = next((r for r in self.store.find("runs", bot_id=bid, limit=3) if r.get("kind") == "replay"), {})
                if chk.get("status") == "ok" and not chk.get("items"):  # checked right after learning and found nothing: it didn't hold up
                    self.store.delete("skills", sid)
                    site = (urlparse(url).netloc or url).removeprefix("www.")
                    raise skills.NeedsHelp("learn_failed", f"What it learned on {site} didn’t hold up",
                                           "Checking it again right after learning found nothing, so I didn’t keep it.", ["Try again", "Show me once"])
            if batch:
                last = next((r for r in self.store.find("runs", bot_id=bid, limit=3) if r.get("kind") == "replay"), {}) if reads else {}
                self._batch_record(bid, url, True, f"{last.get('matched', 0)} of {nres(last.get('items', 0))} pass your rules" if reads else "learned")
        except skills.NeedsHelp as h:
            if batch and h.kind != "denied":  # noted in the batch; one card at the end covers every site that failed
                self._finish(run, "failed", note=h.title)
                self._batch_record(bid, url, False, h.title)
            else:
                self.problem(bid, h, url=url, goal=goal)
                self._finish(run, "stopped" if h.kind == "denied" else "needs_you", note=h.title)
        except (skills.Stopped, ModelStopped):
            self._finish(run, "stopped")
            self.store.update("bots", bid, site_queue=[])  # you stopped it: the other sites wait for you
            if batch:
                self._batch_record(bid, url, False, "stopped")
            self.store.message(bid, "bot", "Stopped. Nothing was learned this time." if not batch else "Stopped. The sites still to go were dropped.", kind="status")
            self.bus.publish("messages", bot=bid)
        except NoModel as e:
            self.problem(bid, skills.NeedsHelp("no_model", "No model to learn with", str(e), ["Open Models"]))
            self._finish(run, "failed", note=str(e))
            self.store.update("bots", bid, site_queue=[], site_batch=None)
            batch = False
        except Exception as e:
            if batch:
                self._finish(run, "failed", note=str(e)[:300])
                self._batch_record(bid, url, False, plain_error(e))
            else:
                self.problem(bid, skills.NeedsHelp("error", "Learning stopped", plain_error(e), ["Try again", "Show me once"]), url=url, goal=goal)
                self._finish(run, "failed", note=str(e)[:300])
        finally:
            self.store.update("bots", bid, last_run=time.time())
            self.apply_overlay(bid, target=None, step="")
            self.bus.publish("bots")
            if (self.store.get("bots", bid) or {}).get("site_queue"):
                threading.Thread(target=self._learn_next, args=(bid, goal), daemon=True).start()
            elif batch:
                self._batch_end(bid)

    # one progress message for several sites, then one summary
    def _batch_say(self, bid, now=None):
        b = self.store.get("bots", bid)
        bt = b.get("site_batch")
        if not bt:
            return
        host = lambda u: (urlparse(u).netloc or u).removeprefix("www.")
        parts = [("✓ " if d["ok"] else "✗ ") + host(d["url"]) for d in bt["done"]] + ([f"now {host(now)}"] if now else [])
        left = bt["total"] - len(bt["done"]) - (1 if now else 0)
        text = f"Learning {bt['total']} sites, one at a time: " + " · ".join(parts) + (f" · {left} to go" if left > 0 else "") + "."
        if bt.get("msg") and self.store.get("messages", bt["msg"]):
            self.store.update("messages", bt["msg"], text=text)
        else:
            bt["msg"] = self.store.message(bid, "bot", text, batch=True, kind="status")
            self.store.update("bots", bid, site_batch=bt)
        self.bus.publish("messages", bot=bid)

    def _batch_record(self, bid, url, ok, note):
        b = self.store.get("bots", bid)
        bt = b.get("site_batch")
        if bt:
            bt["done"] = bt["done"] + [{"url": url, "ok": ok, "note": note}]
            self.store.update("bots", bid, site_batch=bt)
            self._batch_say(bid)

    def _batch_end(self, bid):
        b = self.store.get("bots", bid)
        bt = b.get("site_batch")
        if not bt:
            return
        self.store.update("bots", bid, site_batch=None)
        host = lambda u: (urlparse(u).netloc or u).removeprefix("www.")
        ok, bad = [d for d in bt["done"] if d["ok"]], [d for d in bt["done"] if not d["ok"] and d["note"] != "stopped"]
        fresh = sum(1 for r in self.store.find("results", bot_id=bid, limit=5000) if r.get("passed") is not False)
        text = (f"Learned {len(ok)} of {bt['total']} sites" + (f": {', '.join(host(d['url']) for d in ok)}" if ok else "") + "."
                + (f" From now on every run checks {'them all' if len(ok) > 1 else 'it'} with no AI." if ok else "")
                + (f" {nres(fresh)} pass your rules so far: see Results." if fresh else ""))
        self.store.message(bid, "bot", text)
        self.bus.publish("messages", bot=bid)
        if ok:
            self.notify(bid, text)
        if bad:  # one card for every site that didn't work
            why = "; ".join(f"{host(d['url'])}: {d['note']}" for d in bad[:6]) + ("; …" if len(bad) > 6 else "")
            self.problem(bid, skills.NeedsHelp("batch_failed", f"Couldn’t learn {len(bad)} of {bt['total']} sites", why, ["Try them again", "Skip them"]),
                         urls=[d["url"] for d in bad], goal=b.get("goal"))

    def _learn_next(self, bid, goal):
        """The next site you picked when you made it, once this run is over."""
        for _ in range(1200):  # up to 10 minutes for the first run after learning to finish
            if not self.busy(bid):
                break
            time.sleep(0.5)
        b = self.store.get("bots", bid)
        if not b or not b.get("site_queue") or self.busy(bid):
            return
        url, rest = b["site_queue"][0], b["site_queue"][1:]
        self.store.update("bots", bid, site_queue=rest)
        if not b.get("site_batch"):
            self.store.message(bid, "bot", f"Next site: {urlparse(url).netloc.removeprefix('www.')}." + (f" {len(rest)} more after this." if rest else ""), kind="status")
        try:
            self.learn(bid, goal, url)
        except Exception as e:
            if b.get("site_batch"):
                self._batch_record(bid, url, False, str(e))
                if not rest:
                    self._batch_end(bid)
            else:
                self.store.message(bid, "bot", f"I couldn’t start on {urlparse(url).netloc}: {e}")
        self.bus.publish("messages", bot=bid)

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
        run.site = (urlparse(skill.get("start_url") or "").netloc or "").removeprefix("www.")
        self.bus.publish("bots")
        try:
            was = [st.get("text") for st in skill["steps"]]  # a repair relabels its step; a failure names the step as it was
            out = skills.replay(Ctx(self, bid, run), skill, repair_role=repair_role)
            reads = any(st["action"] == "extract" for st in skill["steps"])
            found_before = any(r.get("skill") == skill["name"] and r.get("items") for r in self.store.find("runs", bot_id=bid, status="ok", limit=30))
            if out["repairs"] and reads and not out["items"] and found_before:  # the fix led nowhere: keep the old step, ask instead
                r = out["repairs"][0]
                raise skills.NeedsHelp("fix_failed", f"Couldn’t fix step {r['step']} ({was[r['step'] - 1]})",
                                       f"I tried “{r['to']}” instead, but then found nothing, so I kept the old step.",
                                       ["Show me once", "Try a smarter model", "Skip this run"], step=r["step"] - 1)
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
            self._worked(bid, f"skill:{sid}")
            self.store.event(bid, "replay", f"{nres(len(out['items']))}, {len(kept)} pass your rules, {len(new)} new" if reads
                             else f"Done in {len(skill['steps'])} steps", ai=run.ai_calls)
            fixed = f" I used AI {'once' if run.ai_calls == 1 else f'{run.ai_calls} times'} to fix a step." if run.ai_calls else ""  # only worth saying when it happened
            if new and reason != "silent":
                top = "; ".join(f"{x.get('title') or x.get('name') or 'untitled'} {x.get('price') or ''}".strip() for x in new[:3])
                self.store.message(bid, "bot", f"{len(new)} new: {top}.{fixed}", kind="results", items=card_items(new), count=len(new), checked=len(out["items"]))
                self.notify(bid, f"{len(new)} new: {top}")
            elif not reads:
                self.store.message(bid, "bot", f"Done: {skill['name'].removeprefix('Check ')}.{fixed}", kind="status")
            elif reason not in ("schedule", "silent"):
                self.store.message(bid, "bot", f"Nothing new" + (f" ({len(kept)} found{' under your rules' if b.get('filters') else ''})." if kept else ".") + fixed, kind="status")
            if not new and reason != "silent":
                self.maybe_suggest(bid, missed)
            skipped = skills.unchecked(out["items"], b.get("filters"))
            if skipped and b.get("warned_unchecked") != skipped:
                self.store.update("bots", bid, warned_unchecked=skipped)
                self.store.message(bid, "bot", f"I can’t check “{'”, “'.join(skipped)}”: this site’s results don’t show it. "
                                               f"Tell me another way to check, or remove that rule in Settings.")
            self.check_level(bid)  # after this run's own messages
            for auto in b.get("automations", []):
                if auto.get("when") == "every_run" or (auto.get("when") == "new_results" and new):
                    self.delegate(bid, auto, context=new, run=run)
        except skills.NeedsHelp as h:
            self.problem(bid, h, skill_id=sid)
            self._finish(run, "stopped" if h.kind == "denied" else "needs_you", note=h.title)
        except skills.CheckedUpTo as c:
            self._finish(run, "ok", note=f"Checked up to “{c}”, which asks you first")
        except (skills.Stopped, ModelStopped):
            self._finish(run, "stopped")
            self._said_stopped(bid)
        except NoModel as e:
            self.problem(bid, skills.NeedsHelp("no_model", "A step needs a fix, but there’s no model", str(e), ["Open Models"]), skill_id=sid)
            self._finish(run, "failed", note=str(e))
        except Exception as e:
            if run.stop:  # you pressed Stop while a step was waiting on the page
                self._finish(run, "stopped")
                self._said_stopped(bid)
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
        elif cmd == "pause":  # nothing running: pausing holds its schedule until you resume it
            self.store.update("bots", bid, held=True)
        elif cmd in ("resume", "handback"):
            if run:
                run.paused.clear()
                run.takeover = False
            if cmd == "resume" and b.get("held"):
                self.store.update("bots", bid, held=False)
            if cmd == "handback":
                self.store.event(bid, "handback", "You handed back")
                open_takeover = [n for n in self.store.find("needs", bot_id=bid, status="open") if n.get("kind") in ("robot", "sign_in")]
                for n in open_takeover:
                    self.store.update("needs", n["id"], status="resolved", decision="Handed back")
                resume = open_takeover or b.get("resume_after_handback")
                r = b.get("resume_after_handback")
                sid = r if type(r) is int else next((n.get("skill_id") for n in open_takeover if n.get("skill_id")), None)
                self.store.update("bots", bid, resume_after_handback=False)
                if resume and not alive:
                    self.store.message(bid, "bot", "Thanks, carrying on from here.")
                    try:
                        self.run(bid, sid, reason="after you took over")
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
        said = {"pause": "Paused" if alive else "Paused its schedule", "resume": "Resumed" if alive or not b.get("held") else "Its schedule is back on", "stop": "Stopped", "takeover": "You took over its computer",
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
            if run.show:
                self._finish(run, "ok")
            else:
                self._finish(run, "stopped", note="You didn’t click anything")
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
                self.problem(bid, skills.NeedsHelp(need["kind"], need["title"], need["body"], need.get("options")), ask=True,
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
    def notify(self, bid, text, need=None):
        self.bus.publish("notify", bot=bid, text=text)
        if self._telegram_on():
            name = (self.store.get("bots", bid) or {}).get("name", "Inky") if bid else "Inky"
            try:
                connectors.PROVIDERS["telegram"].send(self, f"{name}: {text}", need=self.store.get("needs", need) if need else None)
            except Exception:
                pass

    def _telegram_on(self):
        return bool(self.store.setting("telegram", {}).get("enabled") and connectors.PROVIDERS["telegram"].configured(self))

    def _poll_telegram(self):
        if not self._tg_lock.acquire(blocking=False):  # the last check is still going
            return
        try:
            connectors.PROVIDERS["telegram"].poll(self)
        except Exception:
            pass
        finally:
            self._tg_lock.release()

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
        if self._telegram_on():  # answers you tapped on your phone
            threading.Thread(target=self._poll_telegram, daemon=True).start()
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
            due = [r for r in b.get("retries") or [] if r.get("at", 0) <= now]
            if due and not b.get("held") and not self.busy(b["id"]) and not quiet(hm, s.get("quiet_from"), s.get("quiet_to")):
                r = due[0]
                self.store.update("bots", b["id"], retries=[x for x in b["retries"] if x is not r and x != r])
                try:
                    if r.get("do") == "run" and r.get("sid") and self.store.get("skills", r["sid"]):
                        self.run(b["id"], r["sid"], reason="trying again")
                    elif r.get("url"):
                        self.learn(b["id"], r.get("goal") or b.get("goal"), r["url"], replace=r.get("sid"))
                except Exception:
                    pass
                continue
            if not s.get("every_minutes") or b.get("held") or self.busy(b["id"]) or not self.store.find("skills", bot_id=b["id"], limit=1):
                continue
            if quiet(hm, s.get("quiet_from"), s.get("quiet_to")):
                continue
            if now >= due_at(s, b.get("last_run")):
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
        every = self.store.find("bots", desc=False)
        pick = lambda bots: next((b for b in bots if b["name"].lower() == low), None) or next((b for b in bots if b["name"].lower().startswith(low) and low), None)
        t = pick([b for b in every if b.get("status") != "moved"])
        if not t:
            away = pick([b for b in every if b.get("status") == "moved"])
            if away:
                c = self.store.get("computers", int(away["computer"])) if str(away.get("computer")).isdigit() else None
                raise ValueError(f"{away['name']} runs on {c['name'] if c else 'another computer'} now, so it can’t be asked from here")
            raise ValueError(f"there’s no bot called {name}")
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
                if m["role"] == "bot" and (m.get("to_peer") or m.get("team") and "done" in m):  # its answer to a bot shows once, as the copy that reached the asker
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
