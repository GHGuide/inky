"""The bot runtime: creating bots, chatting, learning, running, approvals, problems, take over, scheduling."""
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx

from inky import skills
from inky.bus import Bus
from inky.computer import Computer
from inky.keys import Keys
from inky.llm import LLM, NoModel
from inky.mcp import MCPManager
from inky.safety import classify
from inky.store import Store
from inky import persona as persona_mod
from inky import insights
from inky.insights import quiet

LOOKS = [("octopus", "#E9A23B", "glasses"), ("cat", "#7C6CF2", "none"), ("blob", "#2BA59B", "headphones"),
         ("octopus", "#3B5BDB", "beanie"), ("cat", "#F07BA8", "bow"), ("blob", "#E86F51", "none")]
DEFAULT_LOOK = {"tone": "cheerful", "voice": "soft", "frame": "coral", "cursor": "name", "labels": True, "speed": "normal"}
DEFAULT_RULES = [{"kind": "own", "text": "Read, search, take notes"},
                 {"kind": "ask", "text": "Send, post, reply, delete, submit forms, sign up"},
                 {"kind": "never", "text": "Buy or pay"}]
CORAL = "#E86F51"

DRAFT_SYSTEM = """You turn a job description into a bot. Reply with ONE JSON object:
{"name": "<2 words, e.g. Flat Hunter>", "summary": "<one sentence of what it will do>", "goal": "<what to search and read on the site>",
 "start_url": "<the site to start on, full URL, or null if unknown>", "every_minutes": <how often to check: 1440 daily or "every morning", 60 hourly, 0 only when asked>, "summary_at": "<HH:MM or null>",
 "filters": [{"field": "<price|size|title|…>", "op": "<|<=|>|>=|==|contains|not_contains|in|not_in", "value": <number|string|list>, "text": "<the rule in words>"}],
 "ask_first": ["<things it must ask before>"], "questions": ["<at most 2 short questions if something important is missing>"],
 "persona": {"chatty": <0-1>, "playful": <0-1>, "emoji": <true|false>, "catchphrase": "<short, fits the job>", "quirk": "<one line>", "bio": "<one line, first person>"}}"""

CHAT_SYSTEM = """You are {name}, an Inky bot with its own computer (a browser). Your job: {job}.
Talk {tone}. Keep replies short (1–3 sentences). You can take actions. Reply with ONE JSON object:
{{"reply": "<what you say>", "actions": [<zero or more actions>]}}
Actions:
{{"type":"add_rule","text":"<rule in words>","filter":{{"field":..,"op":..,"value":..}} or null}}   (op: < <= > >= == != contains not_contains in not_in)
{{"type":"remove_rule","text":"<rule to drop>"}}
{{"type":"remember","text":"<fact about the user>"}}   {{"type":"forget","text":"<fact>"}}
{{"type":"learn","goal":"<what to do on the site>","url":"<start URL>"}}   (learn a new site/search once)
{{"type":"run"}}  (check now)   {{"type":"schedule","every_minutes":<n>}}  (add "summary_at":"HH:MM", "quiet_from"/"quiet_to":"HH:MM" only if the user asks; "" turns one off)
{{"type":"pause"}} {{"type":"resume"}} {{"type":"stop"}} {{"type":"speed","value":"slow|normal|turbo"}}
{{"type":"delegate","server":"<connector>","tool":"<tool>","args":{{...}},"label":"<what you hand over>"}}   (hand a job to Claude Code, Codex or another connector now)
{{"type":"add_automation","when":"new_results|every_run","server":..,"tool":..,"args":{{...}},"label":".."}}   (use {{{{new_json}}}}, {{{{count}}}}, {{{{bot}}}} in args)
Only take actions the user's LATEST message asks for; talking about earlier ones is not a reason to repeat them.
Only use tools that are listed. Result fields you have seen: {fields}.
YOUR RULES: {rules}
WHAT YOU REMEMBER: {memory}
YOUR SKILLS: {skills}
STATUS: {status}
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
        if verdict == "ok":
            return
        name = self.bot["name"]
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
        decision = self.e.ask(self.bot_id, "decision", f"{name} wants to {step['text'].lower()}", body,
                              ["Approve", "Always for this step", "Deny"], run=self.run, step=step.get("text"))
        if decision == "Deny":
            raise skills.NeedsHelp("denied", f"Stopped before “{step['text']}”", "You said no, so nothing was sent.", [])
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
        self.computers, self.runs, self.waits = {}, {}, {}
        self.lock = threading.RLock()
        self._sched = None

    # ---------------------------------------------------------- bots
    def bot_view(self, b):
        run = self.runs.get(b["id"])
        sk = self.store.find("skills", bot_id=b["id"])
        needs = self.store.find("needs", bot_id=b["id"], status="open")
        status = b.get("status") or "idle"
        live = bool(run and run.thread and run.thread.is_alive())
        if live:
            status = "paused" if run.paused.is_set() else ("learning" if run.kind == "learn" else "working")
        elif needs:
            status = "needs_you"
        sched = b.get("schedule") or {}
        nxt = None
        if sched.get("every_minutes") and sk:
            nxt = (b.get("last_run") or time.time()) + sched["every_minutes"] * 60
        return {**{k: b.get(k) for k in ("id", "name", "job", "summary", "goal", "start_url", "look", "rules", "filters", "memory",
                                         "schedule", "automations", "mode", "computer", "last_run", "created")},
                "persona": persona_mod.normalize(b.get("persona"), (b.get("look") or {}).get("kind", "octopus")),
                "status": status, "step": run.step if live else "", "step_n": run.n if live else 0,
                "skills": [s["name"] for s in sk], "needs": len(needs), "next_run": nxt,
                "need_kind": ("decision" if needs[0].get("kind") == "decision" else "problem") if needs else None,
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
            url = re.search(r"https?://\S+", job)
            words = [w for w in re.findall(r"[A-Za-z]+", job) if len(w) > 3][:2]
            d = {"name": " ".join(w.title() for w in words) or "New Bot", "summary": job[:140], "goal": job,
                 "start_url": url and url.group(0).rstrip(".,)"), "every_minutes": 0, "filters": [],
                 "questions": ["I couldn’t reach my model, so this is a rough draft from your words. Check Models."]}
        n = len(self.store.find("bots"))
        kind, color, acc = LOOKS[n % len(LOOKS)]
        d.setdefault("look", {"kind": kind, "color": color, "acc": acc})
        d["job"] = job
        return d

    def create_bot(self, d):
        rules = list(DEFAULT_RULES) + [{"kind": "ask", "text": t} for t in d.get("ask_first") or []]
        rules += [{"kind": "filter", "text": f.get("text") or f"{f['field']} {f['op']} {f['value']}"} for f in d.get("filters") or []]
        look = {**DEFAULT_LOOK, **(d.get("look") or {})}
        bot = {"name": (d.get("name") or "New Bot").strip()[:40], "job": d.get("job") or d.get("summary") or "",
               "summary": d.get("summary") or "", "goal": d.get("goal") or d.get("job") or "", "start_url": d.get("start_url"),
               "look": look, "rules": rules, "filters": d.get("filters") or [], "memory": [], "automations": [],
               "schedule": {"every_minutes": int(d.get("every_minutes") or 0), "summary_at": d.get("summary_at"),
                            "quiet_from": "23:00", "quiet_to": "07:00"},
               "mode": "own", "computer": "local", "created": time.time(),
               "persona": persona_mod.normalize(d.get("persona"), look.get("kind", "octopus"))}
        bid = self.store.insert("bots", bot, status="idle")
        self.store.event(bid, "created", f"Created {bot['name']}")
        self.bus.publish("bots")
        return self.bot_view(self.store.get("bots", bid))

    def update_bot(self, bid, patch):
        b = self.store.get("bots", bid)
        allowed = {"name", "job", "summary", "goal", "start_url", "look", "rules", "filters", "memory", "schedule", "automations", "mode", "computer", "persona"}
        patch = {k: v for k, v in patch.items() if k in allowed}
        if "look" in patch:
            patch["look"] = {**b.get("look", {}), **patch["look"]}
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
        for t in ("skills", "runs", "results", "messages", "events", "needs"):
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
        nid = self.store.insert("needs", {"kind": h.kind, "title": h.title, "body": h.body, "options": h.options, **h.meta, **meta},
                                bot_id=bid, status="open")
        self.store.message(bid, "bot", f"{h.title}. {h.body}", need=nid)
        self.store.event(bid, "problem", h.title, need=nid)
        self.bus.publish("needs", bot=bid)
        self.notify(bid, f"{h.title}\n{h.body}")
        return nid

    def resolve(self, nid, decision):
        n = self.store.get("needs", nid)
        if not n:
            raise KeyError(nid)
        self.store.update("needs", nid, status="resolved", decision=decision)
        self.store.event(n["bot_id"], "answered", f"You chose “{decision}”: {n['title']}")
        ev = self.waits.pop(nid, None)
        if ev:
            ev.set()
        else:
            self._follow_up(n, decision)
        self.bus.publish("needs", bot=n["bot_id"])
        return self.store.get("needs", nid)

    def _follow_up(self, n, decision):
        """Answers to Problems (the run already ended)."""
        bid = n["bot_id"]
        if decision in ("Try a smarter model",):
            self.run(bid, n.get("skill_id"), repair_role="smart", reason="retry with a smarter model")
        elif decision in ("Show me once",):
            self.start_show(bid, n)
        elif decision in ("Open its computer",):
            self.store.update("bots", bid, resume_after_handback=True)
            self.control(bid, "takeover", reason="You have its computer. Press Hand back when you’re done, and I’ll carry on.")

    # ---------------------------------------------------------- chat
    def chat(self, bid, text, source="app"):
        b = self.store.get("bots", bid)
        self.store.message(bid, "you", text, source=source)
        self.bus.publish("messages", bot=bid)
        run = self.runs.get(bid)
        if run and run.kind == "learn" and run.thread and run.thread.is_alive():
            run.fixes.append(text)
        results = [r for r in self.store.find("results", bot_id=bid, limit=10) if r.get("passed") is not False][:3]
        fields = sorted({k for r in results for k in r if k not in ("id", "bot_id", "status", "key", "ts", "run", "skill", "new")})
        sk = self.store.find("skills", bot_id=bid)
        hist = [m for m in reversed(self.store.find("messages", bot_id=bid, limit=12))]
        status = self.bot_view(b)["status"] + (f" · {run.step}" if run and run.step else "")
        last = next((r for r in self.store.find("runs", bot_id=bid, limit=5) if r.get("kind") == "replay" and r.get("status") == "ok"), None)
        if last:
            status += (f". Last run {datetime.fromtimestamp(last['ts']).strftime('%a %H:%M')}: {last.get('items', 0)} results, "
                       f"{last.get('matched', 0)} pass the rules, {last.get('new', 0)} new, {last.get('ai_calls', 0)} AI calls. "
                       f"Results saved so far: {sum(1 for r in self.store.find('results', bot_id=bid, limit=2000) if r.get('passed') is not False)}")
        sys = CHAT_SYSTEM.format(name=b["name"], job=b.get("job", ""), tone=b.get("look", {}).get("tone", "cheerful"),
                                 fields=", ".join(fields) or "none yet", rules="; ".join(r["text"] for r in b.get("rules", [])),
                                 memory="; ".join(m["text"] for m in b.get("memory", [])) or "nothing yet",
                                 skills="; ".join(f"{s['name']} ({len(s['steps'])} steps)" for s in sk) or "none yet",
                                 status=status, tools="\n".join(self.mcp.catalog()) or "none")
        def worth_remembering(e):  # run summaries, not every step
            if e.get("kind") == "replay":
                return "pass your rules" in e.get("text", "") or e.get("text", "").startswith("Done in")
            return e.get("kind") in ("learned", "fixed", "problem", "level")
        notable = [e for e in reversed(self.store.find("events", bot_id=bid, limit=200))
                   if e["ts"] > time.time() - 3 * 86400 and worth_remembering(e)]
        sys += "\n" + persona_mod.prompt_lines(b, self.store.setting("app", {}).get("user_name", ""), datetime.now(), notable)
        msgs = [{"role": "system", "content": sys}] + [
            {"role": "assistant", "content": m["text"]} if m["role"] == "bot" else
            {"role": "user", "content": f"[settings note] {m['text']}" if m["role"] == "note" else m["text"]} for m in hist[:-1]] + [
            {"role": "user", "content": text}]
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
            d = {"reply": f"I couldn’t reach my model ({type(e).__name__}). Check Models.", "actions": []}
        done = []
        for a in d.get("actions") or []:
            try:
                done.append(self.apply_action(bid, a))
            except Exception as e:
                done.append(f"couldn’t {a.get('type')}: {e}")
        reply = d.get("reply") or "OK."
        self.store.message(bid, "bot", reply, actions=[a.get("type") for a in d.get("actions") or []], done=done)
        self.bus.publish("messages", bot=bid)
        return {"reply": reply, "actions": d.get("actions") or [], "done": done}

    def apply_action(self, bid, a):
        b = self.store.get("bots", bid)
        t = a.get("type")
        if t == "add_rule":
            rules = b.get("rules", []) + [{"kind": "filter" if a.get("filter") else "own", "text": a["text"]}]
            filters = b.get("filters", []) + ([{**a["filter"], "text": a["text"]}] if a.get("filter") else [])
            self.store.update("bots", bid, rules=rules, filters=filters)
            return f"rule: {a['text']}"
        if t == "remove_rule":
            low = a["text"].lower()
            self.store.update("bots", bid, rules=[r for r in b.get("rules", []) if low not in r["text"].lower()],
                              filters=[f for f in b.get("filters", []) if low not in f.get("text", "").lower()])
            return f"removed: {a['text']}"
        if t == "remember":
            self.store.update("bots", bid, memory=b.get("memory", []) + [{"text": a["text"], "ts": time.time()}])
            return f"remembered: {a['text']}"
        if t == "forget":
            low = a["text"].lower()
            self.store.update("bots", bid, memory=[m for m in b.get("memory", []) if low not in m["text"].lower()])
            return f"forgot: {a['text']}"
        if t == "learn":
            self.learn(bid, a.get("goal") or b.get("goal"), a.get("url") or b.get("start_url"))
            return "learning"
        if t == "run":
            self.run(bid)
            return "running"
        if t == "schedule":
            s = {**b.get("schedule", {}), **{k: a[k] or None for k in ("every_minutes", "summary_at", "quiet_from", "quiet_to") if a.get(k) is not None}}
            self.store.update("bots", bid, schedule=s)
            return "schedule"
        if t in ("pause", "resume", "stop"):
            self.control(bid, t)
            return t
        if t == "speed":
            self.update_bot(bid, {"look": {"speed": a.get("value", "normal")}})
            return "speed"
        if t == "delegate":
            threading.Thread(target=self.delegate, args=(bid, a), daemon=True).start()
            return f"handing to {a.get('server')}"
        if t == "add_automation":
            auto = {k: a.get(k) for k in ("when", "server", "tool", "args", "label")}
            self.store.update("bots", bid, automations=b.get("automations", []) + [auto])
            return f"automation: {a.get('label')}"
        raise ValueError(f"unknown action {t}")

    # ---------------------------------------------------------- MCP delegation
    def delegate(self, bid, a, context=None, run=None):
        b = self.store.get("bots", bid)
        label = a.get("label") or f"{a.get('server')}.{a.get('tool')}"
        who = next((x["label"] for x in self.mcp.servers() if x["name"] == a.get("server")), a.get("server"))
        args = fill_template(a.get("args") or {}, {"bot": b["name"], "count": len(context or []),
                                                   "new_json": json.dumps(context or [], ensure_ascii=False)[:6000]})
        if not a.get("approved_always"):
            decision = self.ask(bid, "decision", f"{b['name']} wants to hand a job to {who}",
                                f"{label}. Tool {a.get('tool')} with {json.dumps(args, ensure_ascii=False)[:400]}",
                                ["Approve", "Always for this automation", "Deny"], run=run, delegate=label)
            if decision == "Deny":
                self.store.message(bid, "bot", f"OK, I didn’t hand “{label}” over.")
                return None
            if decision == "Always for this automation":
                autos = b.get("automations", [])
                for x in autos:
                    if x.get("label") == a.get("label"):
                        x["approved_always"] = True
                self.store.update("bots", bid, automations=autos)
        self.store.event(bid, "delegate", f"Handed to {who}: {label}")
        try:
            r = self.mcp.call(a["server"], a["tool"], args)
            if r["error"] and a["tool"] == "Write" and "not been read" in r["text"] and args.get("file_path"):
                self.mcp.call(a["server"], "Read", {"file_path": args["file_path"]})  # Claude Code only overwrites files it has read
                r = self.mcp.call(a["server"], a["tool"], args)
            out = (r["text"] or "").strip()
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
        if not url:
            raise ValueError("it needs a site to start on")
        run = Run("learn")
        return self._start(bid, run, lambda: self._learn(bid, goal, url, run))

    def _learn(self, bid, goal, url, run):
        run.run_id = self.store.insert("runs", {"kind": "learn", "goal": goal, "url": url}, bot_id=bid, status="running")
        b = self.store.get("bots", bid)
        self.store.message(bid, "bot", f"Learning {url.split('/')[2]} now, once. Watch if you like, and tell me if I pick something wrong.")
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
            self._finish(run, "needs_you", note=h.title)
        except skills.Stopped:
            self._finish(run, "stopped")
        except NoModel as e:
            self.problem(bid, skills.NeedsHelp("no_model", "No model to learn with", str(e), ["Open Models"]))
            self._finish(run, "failed", note=str(e))
        except Exception as e:
            self.problem(bid, skills.NeedsHelp("error", "Learning stopped", f"{type(e).__name__}: {str(e)[:300]}", ["Try again"]))
            self._finish(run, "failed", note=str(e)[:300])
        finally:
            self.store.update("bots", bid, last_run=time.time())
            self.apply_overlay(bid, target=None, step="")
            self.bus.publish("bots")

    def run(self, bid, skill_id=None, repair_role="repair", reason="manual", wait=False):
        sk = [s for s in self.store.find("skills", bot_id=bid, desc=False) if skill_id in (None, s["id"], s["name"])]
        if not sk:
            b = self.store.get("bots", bid)
            if b.get("start_url"):
                return self.learn(bid, b.get("goal"), b.get("start_url"))
            raise ValueError("it hasn’t learned a skill yet")
        run = Run("replay", sk[0]["id"])

        def go():
            for s in sk:
                if run.stop:
                    break
                run.skill_id = s["id"]
                self._replay(bid, s["id"], run, reason, repair_role)
            self.bus.publish("bots")
        self._start(bid, run, go)
        if wait:
            run.thread.join(900)
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
                self.store.upsert_key("results", bid, k, {**it, "skill": skill["name"], "run": run.run_id, "new": True, "passed": True})
                if not prev or prev[0].get("passed") is False:
                    new.append(it)
            missed = [it for it in out["items"] if id(it) not in kept_ids]
            for it in missed:  # kept, hidden, so near-misses can become suggestions
                self.store.upsert_key("results", bid, skills.item_key(it), {**it, "skill": skill["name"], "run": run.run_id, "new": False, "passed": False})
            self.bus.publish("results", bot=bid, new=len(new))
            for r in self.store.find("results", bot_id=bid, limit=1000):
                if r.get("new") and r.get("run") != run.run_id:
                    self.store.update("results", r["id"], new=False)
            self._finish(run, "ok", items=len(out["items"]), matched=len(kept), new=len(new), pages=out["pages"])
            reads = any(st["action"] == "extract" for st in skill["steps"])
            self.store.event(bid, "replay", f"{len(out['items'])} results, {len(kept)} pass your rules, {len(new)} new" if reads
                             else f"Done in {len(skill['steps'])} steps", ai=run.ai_calls)
            if new and reason != "silent":
                top = "; ".join(f"{x.get('title', '')} {x.get('price', '') or ''}".strip() for x in new[:3])
                self.store.message(bid, "bot", f"{len(new)} new {'match' if len(new) == 1 else 'matches'} from {len(out['items'])} results: {top}")
                self.notify(bid, f"{len(new)} new: {top}")
            elif not reads:
                self.store.message(bid, "bot", f"Done: “{skill['name']}”, {len(skill['steps'])} steps, {run.ai_calls} AI calls.")
            elif reason != "schedule":
                ai = "no AI" if not run.ai_calls else f"{run.ai_calls} AI call{'s' if run.ai_calls > 1 else ''} to fix a step"
                self.store.message(bid, "bot", f"Checked {len(out['items'])} results with {ai}. {len(kept)} pass your rules, none new.")
            if not new and reason != "silent":
                self.maybe_suggest(bid, missed)
            skipped = skills.unchecked(out["items"], b.get("filters"))
            if skipped and b.get("warned_unchecked") != skipped:
                self.store.update("bots", bid, warned_unchecked=skipped)
                self.store.message(bid, "bot", f"I couldn’t check {'; '.join(skipped)}: this site’s results don’t show that. "
                                               f"Its search already narrows it, or tell me another way to check.")
            for auto in b.get("automations", []):
                if auto.get("when") == "every_run" or (auto.get("when") == "new_results" and new):
                    self.delegate(bid, auto, context=new, run=run)
        except skills.NeedsHelp as h:
            self.problem(bid, h, skill_id=sid)
            self._finish(run, "needs_you", note=h.title)
        except skills.Stopped:
            self._finish(run, "stopped")
            self.store.message(bid, "bot", "Stopped.")
        except NoModel as e:
            self.problem(bid, skills.NeedsHelp("no_model", "A step needs a fix, but there’s no model", str(e), ["Open Models"]), skill_id=sid)
            self._finish(run, "failed", note=str(e))
        except Exception as e:
            self.problem(bid, skills.NeedsHelp("error", f"“{skill['name']}” stopped", f"{type(e).__name__}: {str(e)[:300]}", ["Try again"]), skill_id=sid)
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
        self.store.event(bid, "control", cmd)
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
        if shown and need:
            skill = self.store.get("skills", need["skill_id"])
            at = need["step"]
            failed = skill["steps"][at]
            # your last click is the new target of the failed step (keeping what it typed); earlier clicks come before it
            last = {**failed, "target": shown[-1]["target"], "shown": True}
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
        tg = self.store.setting("telegram", {})
        if tg.get("enabled") and tg.get("chat_id"):
            token = self.keys.get("telegram")
            if token:
                name = (self.store.get("bots", bid) or {}).get("name", "Inky") if bid else "Inky"
                try:
                    httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                               json={"chat_id": tg["chat_id"], "text": f"{name}: {text}"[:4000]}, timeout=15)
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
        for b in self.store.find("bots"):
            s = b.get("schedule") or {}
            if b.get("status") == "moved":
                continue  # its server runs it now
            if not s.get("every_minutes") or self.busy(b["id"]) or not self.store.find("skills", bot_id=b["id"], limit=1):
                continue
            if quiet(hm, s.get("quiet_from"), s.get("quiet_to")):
                continue
            if now - (b.get("last_run") or 0) >= s["every_minutes"] * 60:
                try:
                    self.run(b["id"], reason="schedule")
                except Exception:
                    pass
            if s.get("summary_at") == hm and b.get("summary_day") != datetime.fromtimestamp(now).strftime("%Y-%m-%d"):
                self.post_paper(b["id"], now)

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
