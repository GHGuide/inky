"""Inky app server: the front-end in app/static plus a small JSON API. Stdlib only, besides the repo's own modules.

    .venv/bin/python app/serve.py [port]     # from the repo root, default http://127.0.0.1:8765

GET  /api/state        research, rules, plan, n8n links, race, program (null where a file is missing)
GET  /api/executions   recent runs of the main and repair n8n workflows, newest first (cached 20 s)
GET  /api/run_detail   items per step of the latest runs, and the latest repair's story (cached 60 s)
POST /api/interview    {messages}             -> the next 2-3 questions, or the finished plan (GLM-5.3)
POST /api/command      {text, dry_run?}       -> one rule edit on rules.json 'final', then pushed to n8n
POST /api/share        {to, text?}            -> plain-language description and a link; nothing is sent
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

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
if os.environ.get("N8N_BASE_URL"):  # also accept a pasted browser URL like https://x.app.n8n.cloud/home/workflows
    _u = os.environ["N8N_BASE_URL"].strip()
    _u = urlsplit(_u if "://" in _u else f"https://{_u}")
    os.environ["N8N_BASE_URL"] = f"{_u.scheme}://{_u.netloc}"
NUMERIC = set(derive.FIELDS) - {"currency", "city"}


class Bad(Exception):
    """The request is wrong (400), as opposed to GLM or n8n failing (502)."""


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):  # missing, or half-written by derive right now
        return None


def plan():
    return json.loads((ROOT / "plan.json").read_text())


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
    return {"research": read_json(DATA / "research.json"), "rules": read_json(DATA / "rules.json"), "plan": plan(),
            "n8n": n8n_links(), "race": read_json(DATA / "race.json"), "program": read_json(ROOT / "teach" / "tecnocasa.program.json")}


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
                err = first_json(rep, "Read the error")
                out["repair"] = {**summarize(rep), **first_json(rep, "Patch the step"), "error": err.get("error"),
                                 "failed": {"id": str(failed["id"]), "startedAt": failed.get("startedAt")} if failed else None,
                                 "again": {"id": str(again["id"]), "status": again.get("status"), "startedAt": again.get("startedAt"),
                                           "stoppedAt": again.get("stoppedAt")} if again else None}
                out["repair"].pop("workflow", None)  # the patched workflow itself is not needed on screen
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


# ---- HTTP ----

POSTS = {"/api/interview": interview, "/api/command": command, "/api/share": share}


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

    def do_GET(self):
        if self.foreign():
            return
        path = self.path.split("?")[0]
        if path == "/api/state":
            return self.reply(state())
        if path == "/api/executions":
            return self.reply(executions())
        if path == "/api/run_detail":
            return self.reply(run_detail())
        if path.startswith("/api/"):
            return self.reply({"error": "not found"}, 404)
        super().do_GET()

    def do_POST(self):
        route = POSTS.get(self.path.split("?")[0])
        if self.foreign():
            return
        if not route:
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
            result = route(body)
        except Bad as e:
            return self.reply({"error": str(e)}, 400)
        except Exception as e:
            print(f"{self.path}: {type(e).__name__}: {e}", file=sys.stderr)
            return self.reply({"error": f"{type(e).__name__}: {e}"}, 502)
        self.reply(result)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Inky on http://127.0.0.1:{port}  (data: {DATA})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
