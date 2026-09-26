"""Inky app server: the front-end in app/static plus a small JSON API. Stdlib only, besides the repo's own modules.

    .venv/bin/python app/serve.py [port]     # from the repo root, default http://127.0.0.1:8765
    .venv/bin/python app/serve.py --demo     # the committed snapshot in data-demo/, no keys, never calls n8n, Apify or GLM

GET  /api/state        research, rules, plan, n8n links, race, program (null where a file is missing)
GET  /api/executions   recent runs of the main and repair n8n workflows, newest first (cached 20 s)
GET  /api/run_detail   items per step of the latest runs, and the latest repair's story with before/after (cached 60 s)
GET  /api/summary      ?since=<iso>, default the last 24 h: runs, listings, matches, fixes, Apify cost (cached 60 s)
GET  /api/end          the totals for the end card
POST /api/interview    {messages}             -> the next 2-3 questions, or the finished plan (GLM-5.3)
POST /api/command      {text, dry_run?}       -> one rule edit on rules.json 'final', then pushed to n8n
POST /api/share        {to, text?}            -> plain-language description and a link; nothing is sent
POST /api/plan         {plan}                 -> checks and saves plan.json (previous one in <data>/plan.backup.json)
POST /api/best_now     {n?}                   -> the top n matches to the n8n best-now webhook (Telegram), 503 until it exists
POST /api/research/run {plan?, offline?}      -> Server-Sent Events while derive.run works: step, version, done | error
POST /api/build/run    {staging?}             -> Server-Sent Events of workflow.deploy(); INKY_SAFE=1 forces staging
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)  # derive and workflow use paths relative to the repo root (inky.js, data/)
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
import derive  # noqa: E402
import workflow  # noqa: E402

STATIC = ROOT / "app" / "static"
DATA = Path(os.environ.get("INKY_DATA", "data"))
N8N_STATE = ROOT / "data" / "n8n.json"  # workflow.main() always writes here, whatever INKY_DATA is
PLAN = ROOT / "plan.json"
DEMO, DEMO_DIR = False, ROOT / "data-demo"  # --demo sets DEMO and points DATA and PLAN at DEMO_DIR
DEMO_LINKS = {"base": "https://your-n8n.example", "main_url": "https://your-n8n.example/workflow/MAIN",
              "repair_url": "https://your-n8n.example/workflow/REPAIR", "demo": True}
REPO = "github.com/GHGuide/inky"
CITIES = ("porto", "bari", "lodz")
if os.environ.get("N8N_BASE_URL"):  # also accept a pasted browser URL like https://x.app.n8n.cloud/home/workflows
    _u = os.environ["N8N_BASE_URL"].strip()
    _u = urlsplit(_u if "://" in _u else f"https://{_u}")
    os.environ["N8N_BASE_URL"] = f"{_u.scheme}://{_u.netloc}"
NUMERIC = set(derive.FIELDS) - {"currency", "city"}


class Bad(Exception):
    """The request is wrong (400), as opposed to GLM or n8n failing (502)."""


class Unavailable(Exception):
    """Something this needs is not set up yet (503), like the best-now webhook before the next deploy."""


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):  # missing, or half-written by derive right now
        return None


def as_json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def when(text):
    """ISO time -> aware datetime; a time without a zone is UTC."""
    t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def plan():
    return json.loads(PLAN.read_text())


def ask(messages, check):
    """derive.glm, parse the JSON object, check() it; one retry with the error, like derive.propose."""
    for _ in range(2):
        text, cost = derive.glm(messages)
        print(f"GLM call ${cost or 0:.4f}", file=sys.stderr)
        try:
            return check(json.loads(text[text.find("{"):text.rfind("}") + 1]))
        except (ValueError, KeyError, TypeError, AttributeError, AssertionError) as e:
            error = f"{type(e).__name__}: {e}"
            messages = messages + [{"role": "assistant", "content": text},
                                   {"role": "user", "content": f"Invalid: {error}. Answer again with one valid JSON object."}]
    raise RuntimeError(f"GLM gave an invalid answer twice ({error})")


# ---- state and executions ----

def n8n_links():
    s, base = read_json(N8N_STATE), os.environ.get("N8N_BASE_URL")
    if not s or not s.get("main") or not base:
        return None
    return {"base": base, "main_url": f"{base}/workflow/{s['main']}",
            "repair_url": f"{base}/workflow/{s['repair']}" if s.get("repair") else None}


def state():
    program = DATA / "program.json" if DEMO else ROOT / "teach" / "tecnocasa.program.json"
    return {"research": read_json(DATA / "research.json"), "rules": read_json(DATA / "rules.json"), "plan": plan(),
            "n8n": DEMO_LINKS if DEMO else n8n_links(), "race": read_json(DATA / "race.json"), "program": read_json(program)}


_runs = {"at": 0.0, "data": []}


def executions():
    if time.time() - _runs["at"] < 20:
        return _runs["data"]
    s, out = read_json(N8N_STATE) or {}, []
    if s.get("main") and os.environ.get("N8N_BASE_URL") and os.environ.get("N8N_API_KEY"):
        try:
            api = workflow.N8n()
            for key in ("main", "repair"):
                if s.get(key):
                    for e in api.call("GET", "/executions", params={"workflowId": s[key], "limit": 40}).get("data", []):
                        out.append({"id": str(e["id"]), "status": e.get("status") or ("success" if e.get("finished") else "unknown"),
                                    "startedAt": e.get("startedAt"), "stoppedAt": e.get("stoppedAt"), "mode": e.get("mode"), "workflow": key})
        except Exception as e:  # the screen shows "no runs yet" rather than an error
            print(f"n8n executions: {type(e).__name__}: {e}", file=sys.stderr)
    out.sort(key=lambda e: e["startedAt"] or "", reverse=True)
    _runs.update(at=time.time(), data=out)
    return out


_detail = {"at": 0.0, "data": None}


def summarize(e):
    """One n8n execution -> items, time and error per node (not the items themselves)."""
    rd = ((e.get("data") or {}).get("resultData")) or {}
    nodes = {}
    for name, runs in (rd.get("runData") or {}).items():
        r = runs[-1]
        nodes[name] = {"items": sum(len(o or []) for o in ((r.get("data") or {}).get("main") or [])),
                       "ms": r.get("executionTime"), "error": (r.get("error") or {}).get("message")}
    return {"id": str(e["id"]), "status": e.get("status"), "mode": e.get("mode"),
            "startedAt": e.get("startedAt"), "stoppedAt": e.get("stoppedAt"), "nodes": nodes}


def first_json(e, node):
    try:
        return e["data"]["resultData"]["runData"][node][-1]["data"]["main"][0][0]["json"]
    except (KeyError, IndexError, TypeError):
        return {}


def run_detail():
    """What the last runs did, per step: the latest run, the latest good run, and the latest repair with its story."""
    if time.time() - _detail["at"] < 60:
        return _detail["data"]
    s, out = read_json(N8N_STATE) or {}, {"main": None, "ok": None, "repair": None}
    if s.get("main") and os.environ.get("N8N_BASE_URL") and os.environ.get("N8N_API_KEY"):
        try:
            api = workflow.N8n()
            full = lambda i: api.call("GET", f"/executions/{i}", params={"includeData": "true"})
            runs = api.call("GET", "/executions", params={"workflowId": s["main"], "limit": 40}).get("data", [])
            if runs:
                out["main"] = summarize(full(runs[0]["id"]))
                ok = next((e for e in runs if e.get("status") == "success"), None)
                out["ok"] = out["main"] if ok and ok["id"] == runs[0]["id"] else summarize(full(ok["id"])) if ok else None
            reps = api.call("GET", "/executions", params={"workflowId": s["repair"], "limit": 1}).get("data", []) if s.get("repair") else []
            if reps:
                rep = full(reps[0]["id"])
                t0 = rep.get("startedAt") or ""
                failed = next((e for e in runs if (e.get("stoppedAt") or "") <= t0 and e.get("status") == "error"), None)
                again = next((e for e in reversed(runs) if (e.get("startedAt") or "") > t0), None)
                err, pick, patch = (first_json(rep, n) for n in ("Read the error", "Pick the broken step", "Patch the step"))
                fixed = next((n for n in (patch.get("workflow") or {}).get("nodes", []) if n.get("name") == patch.get("step")), {})
                out["repair"] = {**summarize(rep), **{k: patch[k] for k in ("workflowId", "step", "change") if k in patch},
                                 "error": err.get("error"),  # before/after: the broken step's actor input, not the whole workflow
                                 "before": as_json(pick.get("before")), "after": as_json((fixed.get("parameters") or {}).get(pick.get("key"))),
                                 "failed": {"id": str(failed["id"]), "startedAt": failed.get("startedAt")} if failed else None,
                                 "again": {"id": str(again["id"]), "status": again.get("status"), "startedAt": again.get("startedAt"),
                                           "stoppedAt": again.get("stoppedAt")} if again else None}
        except Exception as e:
            print(f"n8n run detail: {type(e).__name__}: {e}", file=sys.stderr)
    _detail.update(at=time.time(), data=out)
    return out


# ---- interview ----

INTERVIEW = """You are Inky. A person describes a goal vaguely; you interview them until the goal is a precise plan a program can run on its own.
Each round ask 2 or 3 short questions, only about what is still unclear, each with a one-line reason why it matters. Plain words, no jargon.
Stop as soon as these are clear: budget, cities, home type, tenants, who manages it, and the worst case to avoid.
Inky can read flats for sale and for rent in three cities: porto, bari, lodz (use these lowercase keys in plan.cities).
Answer with ONE JSON object, either
{"done": false, "understood": [{"k": "<short label>", "v": "<what you understood so far>"}], "questions": [{"id": "q1", "text": "<question>", "why": "<why it matters>"}]}
or, when the plan is clear,
{"done": true, "plan": <object with exactly the keys of the example plan>, "summary": "<one sentence>", "results_format": ["<what each result will show>", ...]}
Example of a finished plan: """


def interview(body):
    msgs = body.get("messages")
    if not isinstance(msgs, list) or not 1 <= len(msgs) <= 20:
        raise Bad("messages: a list of 1-20 {role, content}")
    convo = []
    for m in msgs:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant") or not m.get("content"):
            raise Bad("each message needs role 'user' or 'assistant' and content")
        c = m["content"]
        convo.append({"role": m["role"], "content": c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)})
    if convo[-1]["role"] != "user":
        raise Bad("the last message must be the user's")
    example = plan()
    asked = sum(m["role"] == "assistant" for m in convo)
    last = asked >= 5
    system = INTERVIEW + json.dumps(example, ensure_ascii=False)
    if last:
        system += "\nYou have asked 5 rounds. Answer now with done: true, filling any gap with the example's value."

    def check(d):
        if d.get("done"):
            p = d["plan"]
            missing = sorted(set(example) - set(p))
            assert not missing, f"plan is missing {missing}"
            assert isinstance(p["budget_eur"], (int, float)), "budget_eur must be a number"
            assert isinstance(p["cities"], list) and p["cities"], "cities must be a non-empty list"
            assert isinstance(d["summary"], str) and d["summary"], "summary must be a sentence"
            assert isinstance(d["results_format"], list) and d["results_format"], "results_format must be a list"
            p = {k: p[k] for k in example}
            never = p["never"] if isinstance(p["never"], list) else [p["never"]]
            p["never"] = list(dict.fromkeys([*never, *example["never"]]))  # the safety limits are not negotiable
            return {"done": True, "plan": p, "summary": d["summary"], "results_format": [str(x) for x in d["results_format"]]}
        assert not last, "that was round 5: done must be true now"
        qs = d["questions"]
        assert isinstance(qs, list) and qs, "questions must be a non-empty list"
        for q in qs:
            assert all(isinstance(q.get(k), (str, int)) and str(q[k]).strip() for k in ("id", "text", "why")), "each question needs id, text and why"
        und = d.get("understood") or []
        assert isinstance(und, list) and all(isinstance(u, dict) and "k" in u and "v" in u for u in und), "understood must be [{k, v}]"
        return {"done": False, "round": asked + 1, "understood": [{"k": str(u["k"]), "v": str(u["v"])} for u in und],
                "questions": [{k: str(q[k]) for k in ("id", "text", "why")} for q in qs[:3]]}

    return ask([{"role": "system", "content": system}, *convo], check)


# ---- command: one rule edit ----

COMMAND = """You edit the rules of Inky, a program that picks flats to buy and rent out. The user asks for one change in plain words.
The user message is JSON: the current rules, the allowed fields and ops, the plan, and the request.
Turn the request into ONE edit of the rule list. Do not repeat the input. Answer with one JSON object:
{"change": "<one plain sentence: what you changed>", "rule": {"id", "field", "op", "value", "why"} or null, "removed": "<rule id>" or null}
To change an existing rule, reuse its id and give the whole new rule. To add a rule, use the next free id. To drop a rule, set removed to its id and rule to null.
Use only the listed fields and ops. Numbers are plain numbers (180000, not "180k"); prices are in euro. currency is "EUR" or "PLN"; city is "porto", "bari" or "lodz".
'why' is one plain sentence for a non-expert. If the change cannot be expressed with these fields, set rule and removed to null and say why in change."""


def edit(rules, rule, removed):
    new = [r for r in rules if r["id"] != removed]
    at = next((i for i, r in enumerate(new) if rule and r["id"] == rule["id"]), None)
    if rule and at is None:
        new.append(rule)
    elif rule:
        new[at] = rule
    return new


_sale = {}


def sale_listings():
    raw, research = sorted((DATA / "raw").glob("*-*-*.json")), read_json(DATA / "research.json")
    if not raw or not research:
        return None
    key = tuple((str(f), f.stat().st_mtime) for f in raw)
    if key not in _sale:  # ponytail: normalizes every raw file again after any scrape write; fine for one user
        _sale.clear()
        _sale[key] = [l for l in derive.node("normalize", str(research["pln_per_eur"]), *map(str, raw)) if l["op"] == "sale"]
    return _sale[key]


def count_matches(rules):
    """Matches for these rules on the current listings, the same way derive.evaluate does it; None without data."""
    try:
        sale, zones, costs = sale_listings(), read_json(DATA / "zones.json"), read_json(DATA / "costs.json")
        if not (sale and zones and costs):
            return None
        return len(derive.evaluate(sale, rules, zones, costs)[2])
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError) as e:
        print(f"re-score failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def push_rules(rules):
    """Rebuild the main n8n workflow with new rules, keeping its credentials, Telegram chat, Apify mode and node ids."""
    s = json.loads(N8N_STATE.read_text())
    zones, costs, research = (json.loads((DATA / f).read_text()) for f in ("zones.json", "costs.json", "research.json"))
    api = workflow.N8n()
    cur = api.call("GET", f"/workflows/{s['main']}")
    live = {n["name"]: n for n in cur["nodes"]}
    mode = "node" if any(n["type"] == workflow.APIFY_NODE for n in live.values()) else "http"
    chat = live["Ask me on Telegram"]["parameters"]["chatId"]
    creds = {"apify": s["credentials"][f"apify-{mode}"], "telegram": s["credentials"]["telegram"]}
    gmail = live.get("Gmail draft to the agent", {}).get("credentials", {}).get("gmailOAuth2")
    if os.environ.get("N8N_GMAIL_CREDENTIAL_ID"):
        gmail = {"id": os.environ["N8N_GMAIL_CREDENTIAL_ID"], "name": "Gmail"}
    if gmail:
        creds["gmail"] = gmail
    wf = workflow.main_workflow(rules, zones, costs, research["pln_per_eur"], creds, chat, s.get("repair"), mode)
    for n in wf["nodes"]:  # same ids and webhook ids, so Telegram questions still open keep working
        if n["name"] in live:
            n["id"] = live[n["name"]]["id"]
            if "webhookId" in live[n["name"]]:
                n["webhookId"] = live[n["name"]]["webhookId"]
    api.call("PUT", f"/workflows/{s['main']}", json=wf)
    if cur.get("active"):  # n8n cloud keeps a published version: republish so the new rules run, not only the draft
        api.call("POST", f"/workflows/{s['main']}/activate")


def command(body):
    text, dry = body.get("text"), bool(body.get("dry_run"))
    if not isinstance(text, str) or not text.strip() or len(text) > 500:
        raise Bad("text: the change in plain words, up to 500 characters")
    doc = read_json(DATA / "rules.json")
    out = {"change": "No rules yet: the research step has not finished.", "rule": None, "removed": None,
           "applied": False, "matches_before": None, "matches_after": None}
    if dry:
        out["dry_run"] = True
    if not doc or not doc.get("final"):
        return out
    final = doc["final"]
    ids = [r["id"] for r in final]

    def check(d):
        assert "rules" not in d and "request" not in d, "answer with {change, rule, removed}, do not repeat the input"
        assert isinstance(d.get("change"), str) and d["change"], "change must be one sentence"
        assert d["change"].strip(" .").lower() != text.strip(" .").lower(), "change must say what you changed, not repeat the request"
        rule, removed = d.get("rule"), d.get("removed")
        assert removed is None or removed in ids, f"removed must be null or one of {ids}"
        assert not (rule and removed and rule.get("id") != removed), "one edit only: change a rule by reusing its id"
        if rule is not None:
            rule = {k: rule[k] for k in ("id", "field", "op", "value", "why")}
            vals = rule["value"] if isinstance(rule["value"], list) else [rule["value"]]
            if rule["field"] in NUMERIC:
                assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals), f"{rule['field']} needs numbers"
        new = derive.valid(edit(final, rule, removed))
        return d["change"], rule, removed, new

    change, rule, removed, new = ask([{"role": "system", "content": COMMAND}, {"role": "user", "content": json.dumps(
        {"rules": final, "fields": derive.FIELDS, "ops": derive.OPS, "plan": plan(), "request": text}, ensure_ascii=False)}], check)
    before = count_matches(final)
    out.update(change=change, rule=rule, removed=removed, matches_before=before,
               matches_after=count_matches(new) if (rule or removed) else before)
    if dry:
        return out
    if rule or removed:
        (DATA / "rules.backup.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        (DATA / "rules.json").write_text(json.dumps({**doc, "final": new}, ensure_ascii=False, indent=1))
        out["applied"] = True
        if N8N_STATE.exists() and DATA.resolve() != N8N_STATE.parent.resolve():
            out["n8n_error"] = f"not pushed: n8n runs the rules from data/, this server reads {DATA}"
        elif N8N_STATE.exists():
            try:
                push_rules(new)
            except Exception as e:  # the rule is saved locally either way
                out["n8n_error"] = f"{type(e).__name__}: {e}"
    return out


# ---- share ----

def amounts(text):
    """Every number in the text, reading 200,000 / 200.000 / 200 000 as 200000 and 200k as 200000."""
    text = re.sub(r"(?<=\d)[ ,.'](?=\d{3}\b)", "", text)
    return {float(n) * (1000 if k else 1) for n, k in re.findall(r"(\d+(?:\.\d+)?)\s*([kK]?)\b", text)}


SHARE = """You write the description shown when someone shares their Inky agent with another person.
2 to 4 short sentences in plain words for a non-expert, speaking to the person who receives it ("Tell it your budget...").
Say what it reads and how often, what it looks for, that it asks on Telegram before doing anything, and that it never makes an offer, pays, signs or sends a message without approval.
Leave out the sender's personal data: no amounts of money, no results, no names, no chat details.
Answer with one JSON object: {"name": "<2 to 4 word name of the agent>", "description": "<the description>"}"""


def share(body):
    to, note = body.get("to"), body.get("text") or ""
    if not isinstance(to, str) or not to.strip() or len(to) > 60 or not isinstance(note, str) or len(note) > 500:
        raise Bad("to: a name up to 60 characters; text: optional, up to 500")
    p, rules = plan(), (read_json(DATA / "rules.json") or {}).get("final") or []

    budget = {float(p["budget_eur"])} | {float(r["value"]) for r in rules if r["field"] == "price_eur" and isinstance(r["value"], (int, float))}

    def check(d):
        assert isinstance(d["description"], str) and 40 <= len(d["description"]) <= 1200, "description: 2-4 sentences"
        assert not amounts(d["description"]) & budget, "leave out the budget amount"
        assert isinstance(d["name"], str) and d["name"].strip(), "name: 2-4 words"
        return d["name"].strip(), d["description"].strip()

    name, description = ask([{"role": "system", "content": SHARE}, {"role": "user", "content": json.dumps(
        {"plan": {k: v for k, v in p.items() if k != "budget_eur"}, "for": to, "their_note": note,
         "rules": [{"field": "price_eur", "op": r["op"], "value": "their own budget", "why": "Fits their budget."} if r["field"] == "price_eur"
                   else {k: r[k] for k in ("field", "op", "value", "why")} for r in rules],
         "runs": "every 15 minutes, plus a Telegram digest at 08:00", "reads": [name for name, *_ in workflow.SOURCES]},
        ensure_ascii=False)}], check)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32] or "agent"
    slug += "-" + hashlib.sha1(json.dumps([p, rules, to], sort_keys=True).encode()).hexdigest()[:4]
    ruleset = (f"The rules {rules[0]['id']} to {rules[-1]['id']}" if len(rules) > 1 else "The rules, once research finishes" if not rules
               else f"The rule {rules[0]['id']}") + ", with the budget left for them to set"
    return {"name": name, "description": description, "link": f"inky.app/a/{slug}",
            "gets": ["This description and the plan questions", f"The n8n workflow and {len(workflow.SOURCES)} Apify actors",
                     ruleset, "What it may do alone, and never"],
            "keeps": ["Your answers and budget", "Your results and matches", "Your messages and Telegram"]}


# ---- plan, research and build ----

def check_plan(p):
    example = plan()
    if not isinstance(p, dict) or set(p) != set(example):
        extra = f"; missing {sorted(set(example) - set(p))}, unknown {sorted(set(p) - set(example))}" if isinstance(p, dict) else ""
        raise Bad(f"plan: an object with exactly the keys of plan.json{extra}")
    if not isinstance(p["budget_eur"], (int, float)) or isinstance(p["budget_eur"], bool) or p["budget_eur"] <= 0:
        raise Bad("plan.budget_eur: a number of euro")
    if not isinstance(p["cities"], list) or not p["cities"] or not set(p["cities"]) <= set(CITIES):
        raise Bad(f"plan.cities: a non-empty list of {', '.join(CITIES)}")
    never = p["never"] if isinstance(p["never"], list) else [p["never"]]
    return {**p, "never": list(dict.fromkeys([*map(str, never), *example["never"]]))}  # the safety limits stay


def save_plan(body):
    p = check_plan(body.get("plan"))
    if not DEMO:  # the demo snapshot is committed: shown, never written
        DATA.mkdir(parents=True, exist_ok=True)
        shutil.copy(PLAN, DATA / "plan.backup.json")
        PLAN.write_text(json.dumps(p, ensure_ascii=False, indent=2) + "\n")
    return {"ok": True, "plan": p, **({"demo": True} if DEMO else {})}


def research_run(body):
    """C1: GLM-5.3 derives the rules from the plan on the cached listings (no scraping), streaming each step."""
    p = check_plan(body["plan"]) if body.get("plan") is not None else None

    def job(send):
        if p:
            save_plan({"plan": p})
            send({"type": "step", "text": "Saved your plan", "sub": f"{', '.join({'lodz': 'Łódź'}.get(c, c.title()) for c in p['cities'])} · up to €{p['budget_eur']:,.0f}"})
        research, rules = derive.run(send, offline=bool(body.get("offline")), data_dir=DATA, plan=plan())
        _sale.clear()  # a new exchange rate re-prices the Łódź listings
        return {"research": research, "rules": rules}
    return "research", job


def as_step(e, sub=None):
    """workflow.deploy reports progress(text) or progress(text, sub); a dict passes through as a step."""
    e = e if isinstance(e, dict) else {"text": str(e), **({"sub": str(sub)} if sub else {})}
    return {**e, "type": "step"} if e.get("type") in (None, "done", "error") else e


def build_run(body):
    """C2: workflow.deploy() writes and publishes the n8n workflows; its progress becomes steps."""
    deploy = getattr(workflow, "deploy", None)
    if not callable(deploy):
        raise Unavailable("workflow.deploy() is not in this version of workflow.py yet")
    staging = bool(body.get("staging")) or os.environ.get("INKY_SAFE") == "1"
    if not staging and DATA.resolve() != N8N_STATE.parent.resolve():  # workflow.deploy builds from $INKY_DATA
        raise Unavailable(f"not deployed live: this server reads {DATA}, the live workflow runs the rules from {N8N_STATE.parent}")

    def job(send):
        send({"type": "step", "text": f"Building the {'staging' if staging else 'live'} n8n workflows"})
        result = deploy(lambda *a: send(as_step(*a)), staging=staging)
        _runs["at"] = _detail["at"] = 0
        links = {**({} if staging else n8n_links() or {}), **(result if isinstance(result, dict) else {})}
        return {"main_url": links.get("main_url"), "repair_url": links.get("repair_url"), "staging": staging,
                **{k: links[k] for k in ("mode", "active", "gmail") if k in links}}  # never best_url: the webhook path is its only lock
    return "build", job


def best_now(body):
    """B1: the top n matches of the current rules go to the n8n webhook, which asks on Telegram."""
    n = body.get("n", 3)
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 10:
        raise Bad("n: 1-10 homes")
    url_of = getattr(workflow, "best_now_url", None)
    try:
        url = url_of() if callable(url_of) else None
    except Exception as e:
        raise Unavailable(f"the best-now webhook is not deployed yet ({type(e).__name__}: {e})")
    if not url:
        raise Unavailable("the best-now webhook is not deployed yet: build the workflow first")
    if os.environ.get("INKY_SAFE") == "1" and urlsplit(url).hostname not in ("127.0.0.1", "localhost"):
        raise Unavailable("INKY_SAFE=1: homes only go to a local test webhook, never to Telegram")
    final = (read_json(DATA / "rules.json") or {}).get("final")
    sale, zones, costs = sale_listings(), read_json(DATA / "zones.json"), read_json(DATA / "costs.json")
    if not (final and sale and zones and costs):
        raise Unavailable("no rules or listings yet: the research step has not finished")
    matches = derive.evaluate(sale, final, zones, costs)[2][:n]
    r = httpx.post(url, json={"matches": matches}, timeout=60)
    if r.status_code >= 400:  # the webhook URL itself stays out of the error
        raise RuntimeError(f"the n8n webhook answered {r.status_code}")
    return {"sent": len(matches), "matches": matches}


# ---- summary (B3, B4) and the end card (A8) ----

_summary, _summary_lock = {}, threading.Lock()
SINCE_START = "2000-01-01T00:00:00Z"  # the end card counts everything


def all_executions(api, wid):
    out, cursor = [], None
    while True:
        r = api.call("GET", "/executions", params={"workflowId": wid, "limit": 250, **({"cursor": cursor} if cursor else {})})
        out += r.get("data", [])
        cursor = r.get("nextCursor")
        if not cursor:
            return out


def run_numbers(e):
    """One execution with its data -> what run-cache.json keeps: items per source step, matches, the fix, and short hashes
    of the listings read (for 'new'). Source steps are the ones wired into a Merge node, so a new source counts too."""
    rd = (((e.get("data") or {}).get("resultData")) or {}).get("runData") or {}
    wd = e.get("workflowData") or {}
    merges = {n["name"] for n in wd.get("nodes", []) if n.get("type") == "n8n-nodes-base.merge"}
    srcs = [a for a, c in (wd.get("connections") or {}).items() if any(t.get("node") in merges for o in c.get("main", []) for t in (o or []))]
    items = lambda name: [i.get("json") or {} for o in (((rd[name][-1].get("data") or {}).get("main")) or []) for i in (o or [])]
    sources = {s: len(items(s)) for s in srcs if s in rd}
    keys = sorted({hashlib.sha1(f"{s}:{j.get('propertyCode') or j.get('id') or j.get('propertyUrl') or j.get('url')}".encode()).hexdigest()[:10]
                   for s in sources for j in items(s)})
    patch = first_json(e, "Patch the step")
    return {"sources": sources, "scored": workflow.SCORE in rd, "matches": len(items(workflow.SCORE)) if workflow.SCORE in rd else 0,
            "keys": keys, "fixed": "Save the fix" in rd and not rd["Save the fix"][-1].get("error"),
            "step": patch.get("step"), "change": patch.get("change")}


def apify_runs(since):
    """Apify runs started since `since`, newest first: [(start, usd)]."""
    out, offset = [], 0
    while True:
        r = httpx.get("https://api.apify.com/v2/actor-runs", params={"desc": 1, "limit": 1000, "offset": offset},
                      headers={"Authorization": f"Bearer {os.environ['APIFY_TOKEN']}"}, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"Apify runs list: {r.status_code}")
        d = r.json()["data"]
        for i in d["items"]:
            if when(i["startedAt"]) < since:
                return out
            out.append((when(i["startedAt"]), i.get("usageTotalUsd") or 0))
        offset += len(d["items"])
        if not d["items"] or offset >= d["total"]:
            return out


def summary(since=None):
    try:
        t0 = when(since) if since else datetime.now(timezone.utc) - timedelta(hours=24)
    except (ValueError, AttributeError):
        raise Bad("since: an ISO time like 2026-09-26T20:00:00Z")
    with _summary_lock:  # one fetch at a time; the first one reads every run once (about 4 MB each), then run-cache.json has it
        hit = _summary.get(since)
        if hit and time.time() - hit[0] < 60:
            return hit[1]
        s, research, errors = read_json(N8N_STATE) or {}, read_json(DATA / "research.json") or {}, []
        cache_file = N8N_STATE.with_name("run-cache.json")
        cache, main, reps, saved = read_json(cache_file) or {}, [], [], None
        if s.get("main") and os.environ.get("N8N_BASE_URL") and os.environ.get("N8N_API_KEY"):
            try:
                api = workflow.N8n()
                # the workflow's own counters, the ones its 08:00 digest reports (they count only listings Inky could read)
                saved = ((api.call("GET", f"/workflows/{s['main']}").get("staticData") or {}).get("global") or {}).get("stats")
                main = all_executions(api, s["main"])
                reps = all_executions(api, s["repair"]) if s.get("repair") else []
                todo = [e for e in main + reps if str(e["id"]) not in cache and e.get("status") not in (None, "new", "running", "unknown")]
                with ThreadPoolExecutor(4) as pool:
                    for e, full in zip(todo, pool.map(lambda e: api.call("GET", f"/executions/{e['id']}", params={"includeData": "true"}), todo)):
                        cache[str(e["id"])] = run_numbers(full)
                if todo:
                    cache_file.write_text(json.dumps(cache))
            except Exception as e:
                errors.append(f"n8n: {type(e).__name__}: {e}")
        apify = []
        if os.environ.get("APIFY_TOKEN"):
            try:
                apify = apify_runs(t0)
            except Exception as e:
                errors.append(f"Apify: {type(e).__name__}: {e}")
        seen, rows, checked = set(), [], 0
        for e in sorted(main, key=lambda e: e.get("startedAt") or ""):
            c = cache.get(str(e["id"]))
            if not c or not c["sources"]:  # the 08:00 digest, a best-now send, or still running
                continue
            fresh = [k for k in c["keys"] if k not in seen] if c["scored"] else []
            seen.update(fresh)  # like n8n: a listing is only marked seen when the Score step ran
            start = when(e["startedAt"])
            if start < t0:
                continue
            stop = when(e["stoppedAt"]) if e.get("stoppedAt") else None
            listings = sum(c["sources"].values())
            checked += listings if c["scored"] else 0
            rows.append({"id": str(e["id"]), "startedAt": e["startedAt"], "status": e.get("status"), "mode": e.get("mode"),
                         "listings": listings, "new": len(fresh), "matches": c["matches"],
                         "secs": round((stop - start).total_seconds(), 1) if stop else None, "sources": c["sources"],
                         # the Apify runs this n8n run started: they begin within its time window
                         "apify_usd": round(sum(u for at, u in apify if start <= at <= (stop or start + timedelta(minutes=10)) + timedelta(seconds=30)), 4)})
        fixes = [{"id": str(e["id"]), "startedAt": e["startedAt"], "step": cache[str(e["id"])]["step"], "change": cache[str(e["id"])]["change"]}
                 for e in reps if str(e["id"]) in cache and cache[str(e["id"])]["fixed"] and when(e["startedAt"]) >= t0]
        in_runs = sum(r["apify_usd"] for r in rows)
        out = {"since": t0.isoformat(timespec="seconds"), "runs": len(rows),
               "ok": sum(r["status"] in ("success", "waiting") for r in rows), "failed": sum(r["status"] in ("error", "crashed") for r in rows),
               "waiting": sum(r["status"] == "waiting" for r in rows), "repairs": len(fixes), "fixes": fixes,
               "listings_checked": checked, "new_listings": sum(r["new"] for r in rows), "matches": sum(r["matches"] for r in rows),
               "apify_usd": round(sum(u for _, u in apify), 2), "apify_usd_runs": round(in_runs, 2),
               "apify_usd_per_run": round(in_runs / len(rows), 3) if rows else None,
               "ai_calls": 0, "glm_usd_research": research.get("llm_cost_usd"), "n8n_stats": saved, "per_run": rows[::-1], "errors": errors}
        _summary[since] = (time.time(), out)
        return out


def end():
    """Totals since the start. Listings and matches: the workflow's own counters when n8n answers, so the end card and the
    Telegram digest say the same; else counted from the run data (raw items, a few more than Inky could read)."""
    s, r = summary(SINCE_START), read_json(DATA / "research.json") or {}
    n = s.get("n8n_stats") or {}
    return {"listings_read": r.get("listings_read"), "runs": s["runs"], "listings_checked": n.get("checked", s["listings_checked"]),
            "new_listings": n.get("fresh", s["new_listings"]), "matches": n.get("matches", s["matches"]), "research_matches": len(r.get("matches") or []),
            "fixes": s["repairs"], "apify_usd_total": s["apify_usd"], "apify_usd_per_run": s["apify_usd_per_run"],
            "glm_usd_research": r.get("llm_cost_usd"), "ai_calls_per_run": 0, "repo": REPO}


# ---- demo mode (K4): the committed snapshot in data-demo/, made by app/make_demo.py ----

def demo_file(name):
    d = read_json(DATA / name)
    if d is None:
        raise Unavailable(f"the demo snapshot has no {name}: run app/make_demo.py")
    return d


def demo_interview(body):
    replies = demo_file("replies/interview.json")  # recorded rounds of a real interview, in order
    asked = sum(isinstance(m, dict) and m.get("role") == "assistant" for m in body.get("messages") or [])
    return replies[min(asked, len(replies) - 1)]


def demo_best_now(body):
    n = body.get("n", 3) if isinstance(body.get("n", 3), int) else 3
    return {"sent": 0, "matches": demo_file("research.json")["matches"][:n], "demo": True, "note": "demo mode: nothing is sent"}


DEMO_PACE = 1.0  # seconds per replayed step; the self-check sets 0


def replay(name):
    events = demo_file(f"replies/{name}.json")

    def job(send):
        for e in events[:-1]:
            time.sleep(DEMO_PACE * (0.5 if e.get("type") == "step" else 0.2))
            send(e)
        return {k: v for k, v in events[-1].items() if k != "type"}
    return job


# ---- HTTP ----

GETS = {"/api/state": lambda q: state(), "/api/executions": lambda q: executions(), "/api/run_detail": lambda q: run_detail(),
        "/api/summary": lambda q: summary((q.get("since") or [None])[0]), "/api/end": lambda q: end()}
POSTS = {"/api/interview": interview, "/api/command": command, "/api/share": share, "/api/plan": save_plan, "/api/best_now": best_now}
STREAMS = {"/api/research/run": research_run, "/api/build/run": build_run}
DEMO_GETS = {**GETS, "/api/executions": lambda q: demo_file("executions.json"), "/api/run_detail": lambda q: demo_file("run_detail.json"),
             "/api/summary": lambda q: demo_file("summary.json"), "/api/end": lambda q: demo_file("end.json")}
DEMO_POSTS = {"/api/interview": demo_interview, "/api/command": lambda b: demo_file("replies/command.json"),
              "/api/share": lambda b: demo_file("replies/share.json"), "/api/plan": save_plan, "/api/best_now": demo_best_now}
DEMO_STREAMS = {"/api/research/run": lambda b: ("research", replay("research_run")), "/api/build/run": lambda b: ("build", replay("build_run"))}
JOBS = {"research": threading.Lock(), "build": threading.Lock()}  # one research run and one build at a time


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def reply(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def foreign(self):
        """Refuse other hosts (DNS rebinding) and cross-site POSTs; a browser cannot send JSON cross-site without a preflight."""
        host, origin = self.headers.get("Host") or "", self.headers.get("Origin")
        if urlsplit(f"//{host}").hostname not in ("127.0.0.1", "localhost") or (origin and urlsplit(origin).netloc != host):
            self.reply({"error": "only for this computer"}, 403)
            return True
        return False

    def stream(self, job):
        """Server-Sent Events: job(send) calls send(event) per step and returns the done event. A closed tab does not stop the job."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        gone = False

        def send(e):
            nonlocal gone
            if not gone:
                try:
                    self.wfile.write(f"data: {json.dumps(e, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()
                except OSError:
                    gone = True
        try:
            send({"type": "done", **job(send)})
        except Exception as e:
            print(f"{self.path}: {type(e).__name__}: {e}", file=sys.stderr)
            send({"type": "error", "text": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        if self.foreign():
            return
        path, _, query = self.path.partition("?")
        route = (DEMO_GETS if DEMO else GETS).get(path)
        if route:
            try:
                return self.reply(route(parse_qs(query)))
            except Bad as e:
                return self.reply({"error": str(e)}, 400)
            except Unavailable as e:
                return self.reply({"error": str(e)}, 503)
        if path.startswith("/api/"):
            return self.reply({"error": "not found"}, 404)
        super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        route, streamed = (DEMO_POSTS if DEMO else POSTS).get(path), (DEMO_STREAMS if DEMO else STREAMS).get(path)
        if self.foreign():
            return
        if not (route or streamed):
            return self.reply({"error": "not found"}, 404)
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            return self.reply({"error": "send Content-Type: application/json"}, 415)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if 0 <= n <= 1_000_000 else None
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return self.reply({"error": "send one JSON object, up to 1 MB"}, 400)
        try:
            if streamed:
                kind, job = streamed(body)
                if not JOBS[kind].acquire(blocking=False):
                    return self.reply({"error": f"a {kind} run is already going"}, 409)
                try:
                    return self.stream(job)
                finally:
                    JOBS[kind].release()
            result = route(body)
        except Bad as e:
            return self.reply({"error": str(e)}, 400)
        except Unavailable as e:
            return self.reply({"error": str(e)}, 503)
        except Exception as e:
            print(f"{self.path}: {type(e).__name__}: {e}", file=sys.stderr)
            return self.reply({"error": f"{type(e).__name__}: {e}"}, 502)
        self.reply(result)


if __name__ == "__main__":
    if "--demo" in sys.argv:
        DEMO, DATA, PLAN = True, DEMO_DIR, DEMO_DIR / "plan.json"
    port = int(next((a for a in sys.argv[1:] if a.isdigit()), 8765))
    print(f"Inky on http://127.0.0.1:{port}  (data: {DATA}{', demo mode: no keys, nothing leaves this computer' if DEMO else ''})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
