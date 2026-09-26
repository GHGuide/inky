"""Offline check of app/serve.py: every endpoint, with data and without, and demo mode. GLM, n8n, Apify and the best-now
webhook are faked (the webhook is a local stub server), nothing leaves the machine.

    .venv/bin/python app/test_serve.py
"""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="inky-serve-"))
FULL, EMPTY, STATIC = TMP / "full", TMP / "empty", TMP / "static"
shutil.copytree(HERE.parent / "data-offline", FULL, ignore=shutil.ignore_patterns("n8n-*.json"))
EMPTY.mkdir()
STATIC.mkdir()
(STATIC / "index.html").write_text("<title>Inky</title>")
(FULL / "n8n.json").write_text(json.dumps({"credentials": {"apify-http": {"id": "A", "name": "Apify"}, "telegram": {"id": "T", "name": "Telegram"}},
                                           "main": "M1", "repair": "R9"}))

# Set before import: serve and derive read these once, and load_dotenv never overrides them. Fake keys, so a missed patch fails loudly.
os.environ.update(INKY_DATA=str(FULL), N8N_BASE_URL="https://example.app.n8n.cloud/home/workflows/", N8N_API_KEY="fake", OPENROUTER_API_KEY="fake",
                  APIFY_TOKEN="fake")
for k in ("N8N_GMAIL_CREDENTIAL_ID", "INKY_SAFE"):
    os.environ.pop(k, None)
sys.path.insert(0, str(HERE))
import serve  # noqa: E402

serve.STATIC = STATIC
serve.N8N_STATE = FULL / "n8n.json"  # never the repo's real data/n8n.json
serve.PLAN = TMP / "plan.json"  # never the repo's plan.json
shutil.copy(HERE.parent / "plan.json", serve.PLAN)
serve.derive.market_facts = lambda: (4.3718, {"PT": 17.8, "IT": 5.2, "PL": 5.9}, "2026-Q1")  # no ECB or Eurostat call
glm_calls, n8n_calls = [], []
BAD_ONCE = {"interview": True, "echo": True, "leak": True, "research": True}


def fake_glm(messages):
    system, last = messages[0]["content"], messages[-1]["content"]
    glm_calls.append(system[:20])
    if system.startswith("You are Inky. A person"):
        if BAD_ONCE.pop("interview", False):
            return "sorry, no json here", 0.0  # exercises the one retry
        if "You have asked 5 rounds" in system:
            p = serve.plan()
            return json.dumps({"done": True, "plan": {**p, "budget_eur": 150000, "never": ["pay"]}, "summary": "Flats in Łódź.",
                               "results_format": ["city", "net yield", "link"], "extra": 1}), 0.001
        return json.dumps({"done": False, "understood": [{"k": "Goal", "v": "rent out a flat abroad"}],
                           "questions": [{"id": "q1", "text": "What is your budget?", "why": "It decides which cities fit."},
                                         {"id": "q2", "text": "Who will manage it?", "why": "Agency fees cut the yield."}]}), 0.001
    if system.startswith("You edit the rules"):
        last = json.loads(messages[1]["content"])["request"]
        if "euro" in last and BAD_ONCE.pop("echo", False):
            return json.dumps({"change": "Only places with the euro.", "rule": None, "removed": None}), 0.0  # the echo seen live
        if "euro" in last:
            return json.dumps({"change": "Only homes priced in euro.", "rule": {"id": "R7", "field": "currency", "op": "==", "value": "EUR",
                                                                                "why": "No exchange-rate risk."}, "removed": None}), 0.001
        if "banana" in last:
            return json.dumps({"change": "x", "rule": {"id": "R1", "field": "banana", "op": "<=", "value": 1, "why": "x"}, "removed": None}), 0.0
        return json.dumps({"change": "Budget lowered to €150,000.", "rule": {"id": "R1", "field": "price_eur", "op": "<=", "value": 150000,
                                                                              "why": "Fits the new budget."}, "removed": None}), 0.001
    if system.startswith("You write the description"):
        assert "200000" not in messages[1]["content"], "the budget never reaches GLM"
        if BAD_ONCE.pop("leak", False):
            return json.dumps({"name": "x", "description": "Tell it your budget of €200,000 and it reads the portals every 15 minutes."}), 0.0
        return json.dumps({"name": "Buy-to-let abroad", "description": "Tell it your budget and where you can buy. It reads the big portals every "
                                                                        "15 minutes and asks you on Telegram. It never pays or signs."}), 0.001
    if system.startswith("You are the research step"):
        if BAD_ONCE.pop("research", False):
            return "no rules today", 0.0  # derive.propose retries once
        if "BROKEN" in messages[1]["content"]:
            return "still no rules", 0.0  # twice invalid: the run ends with an error event
        v = sum(m["role"] == "assistant" for m in messages)  # earlier versions in the history
        return json.dumps({"rules": [{"id": "R1", "field": "price_eur", "op": "<=", "value": 200000, "why": "Budget."},
                                     {"id": "R2", "field": "net_yield", "op": ">=", "why": "Yield.",
                                      "value": ([5.5, 4.0, 4.0] if "LOOSEN" in messages[1]["content"] else [4.0, 5.0, 5.5])[min(v, 2)]}],
                           "note": "ok"}), 0.002
    raise AssertionError(f"unexpected GLM prompt: {system[:60]}")


class FakeN8n:
    base = "https://example.app.n8n.cloud"
    execs, full = None, {}  # the summary and run-detail checks put richer runs here

    def call(self, method, path, **kw):
        n8n_calls.append((method, path, kw))
        if path == "/executions" and FakeN8n.execs:
            return {"data": FakeN8n.execs[kw["params"]["workflowId"]]}
        if path.startswith("/executions/"):
            return FakeN8n.full[path.split("/")[-1]]
        if path == "/executions":
            wid = kw["params"]["workflowId"]
            return {"data": [{"id": 7 if wid == "M1" else 8, "status": "error" if wid == "M1" else "success", "mode": "trigger",
                              "startedAt": "2026-09-26T10:0%d:00Z" % (1 if wid == "M1" else 2), "stoppedAt": "2026-09-26T10:05:00Z"}]}
        if method == "GET":
            d = serve.DATA
            FakeN8n.live = getattr(FakeN8n, "live", None) or {"active": True, **serve.workflow.main_workflow(json.loads((d / "rules.json").read_text())["final"], json.loads((d / "zones.json").read_text()),
                                                json.loads((d / "costs.json").read_text()), 4.37, {"apify": {"id": "A"}, "telegram": {"id": "T"}},
                                                "42", "R9", "http")}
            return FakeN8n.live
        return {}


serve.derive.glm = fake_glm
serve.workflow.N8n = FakeN8n
srv = serve.ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}"


def http(path, body=None, headers=None):
    req = urllib.request.Request(URL + path, data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw, code = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, code = e.read(), e.code
    return code, (json.loads(raw) if raw.startswith((b"{", b"[")) else raw.decode())


def sse(path, body, first=None):
    """POST, then read Server-Sent Events as they come; first(event) runs on the first one, while the job is still going."""
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        assert r.headers["Content-Type"].startswith("text/event-stream"), r.headers["Content-Type"]
        events = []
        for line in r:
            if line.startswith(b"data: "):
                events.append(json.loads(line[6:]))
                if first and len(events) == 1:
                    first(events[0])
            else:
                assert line == b"\n", line
    assert events and events[-1]["type"] in ("done", "error") and all(e["type"] not in ("done", "error") for e in events[:-1]), events
    return events


# ---- with data ----
code, page = http("/")
assert code == 200 and "<title>Inky</title>" in page, (code, page)
assert http("/api/nope")[0] == 404 and http("/api/nope", {})[0] == 404

code, s = http("/api/state")
assert code == 200 and set(s) == {"research", "rules", "plan", "n8n", "race", "program"}, s.keys()
assert s["research"]["for_sale"] == 480 and s["rules"]["final"] and s["plan"]["budget_eur"] == 200000
assert s["n8n"] == {"base": "https://example.app.n8n.cloud", "main_url": "https://example.app.n8n.cloud/workflow/M1",
                    "repair_url": "https://example.app.n8n.cloud/workflow/R9"}, s["n8n"]
assert s["race"] is None and s["program"] == serve.read_json(serve.ROOT / "teach" / "tecnocasa.program.json")

code, runs = http("/api/executions")
assert code == 200 and [(r["id"], r["workflow"], r["status"]) for r in runs] == [("8", "repair", "success"), ("7", "main", "error")], runs
assert set(runs[0]) == {"id", "status", "startedAt", "stoppedAt", "mode", "workflow"}
before = len(n8n_calls)
assert http("/api/executions")[1] == runs and len(n8n_calls) == before, "cached for 20 s"

code, r = http("/api/interview", {"messages": [{"role": "user", "content": "I want to earn from a flat abroad"}]})
assert code == 200 and r["done"] is False and r["round"] == 1 and 2 <= len(r["questions"]) <= 3, r
assert all(set(q) == {"id", "text", "why"} for q in r["questions"]) and r["understood"][0] == {"k": "Goal", "v": "rent out a flat abroad"}
assert sum(c.startswith("You are Inky") for c in glm_calls) == 2, "invalid first answer is retried once"
five = [m for _ in range(5) for m in ({"role": "user", "content": "..."}, {"role": "assistant", "content": {"done": False}})]
code, r = http("/api/interview", {"messages": five + [{"role": "user", "content": "use the defaults"}]})
assert code == 200 and r["done"] is True and set(r["plan"]) == set(serve.plan()) and r["plan"]["budget_eur"] == 150000, r
assert r["plan"]["never"][0] == "pay" and "make an offer" in r["plan"]["never"] and r["summary"] and r["results_format"]
assert http("/api/interview", {"messages": [{"role": "assistant", "content": "hi"}]})[0] == 400
assert http("/api/interview", {"messages": "hi"})[0] == 400
req = urllib.request.Request(URL + "/api/interview", data=b"not json", method="POST", headers={"Content-Type": "application/json"})
try:
    urllib.request.urlopen(req)
    raise AssertionError("bad JSON body accepted")
except urllib.error.HTTPError as e:
    assert e.code == 400

# other websites and hosts are refused, before any GLM call
calls = len(glm_calls)
assert http("/api/command", {"text": "max 1k"}, {"Content-Type": "text/plain"})[0] == 415
assert http("/api/command", {"text": "max 1k"}, {"Origin": "https://evil.example"})[0] == 403
assert http("/api/state", headers={"Host": "evil.example"})[0] == 403
assert http("/api/share", {"to": "Sanne"}, {"Origin": URL})[0] == 200 and len(glm_calls) > calls  # same origin works
with socket.create_connection(srv.server_address, timeout=5) as c:  # a negative length must not hang the handler
    c.sendall(b"POST /api/share HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: -1\r\n\r\n{}")
    assert c.recv(100).startswith(b"HTTP/1.0 400"), "negative Content-Length"
BAD_ONCE["leak"] = True

rules_before = (FULL / "rules.json").read_text()
code, r = http("/api/command", {"text": "max 150k", "dry_run": True})
assert code == 200 and r["applied"] is False and r["dry_run"] is True and r["rule"]["value"] == 150000, r
assert isinstance(r["matches_before"], int) and isinstance(r["matches_after"], int) and r["matches_after"] <= r["matches_before"], r
assert (FULL / "rules.json").read_text() == rules_before and not (FULL / "rules.backup.json").exists()
assert not any(m == "PUT" for m, _, _ in n8n_calls), "dry run never pushes"

code, r = http("/api/command", {"text": "only places with the euro"})
assert code == 200 and r["applied"] is True and r["rule"]["id"] == "R7" and r["removed"] is None and "n8n_error" not in r, r
assert r["change"] == "Only homes priced in euro." and "echo" not in BAD_ONCE, "an echo of the request is retried, not accepted"
assert r["matches_after"] < r["matches_before"], r  # Łódź is in złoty, so its matches drop out
assert json.loads((FULL / "rules.backup.json").read_text()) == json.loads(rules_before)
final = json.loads((FULL / "rules.json").read_text())["final"]
assert final[-1]["id"] == "R7" and len(final) == len(json.loads(rules_before)["final"]) + 1
live = {n["name"]: n for n in FakeN8n.live["nodes"]}
(method, path, kw), = [c for c in n8n_calls if c[0] == "PUT"]
assert path == "/workflows/M1", path
assert n8n_calls[-1][:2] == ("POST", "/workflows/M1/activate"), "an active workflow is republished after the PUT"
put = {n["name"]: n for n in kw["json"]["nodes"]}
assert '"value": "EUR"' in put["Score · rules"]["parameters"]["jsCode"], "new rule is in the n8n Code node"
assert put["Ask me on Telegram"]["parameters"]["chatId"] == "42" and put["Every 15 min"]["type"] == "n8n-nodes-base.scheduleTrigger"
assert kw["json"]["settings"]["errorWorkflow"] == "R9" and "httpHeaderAuth" in put["idealista · Porto"]["credentials"]
assert all(n["id"] == live[k]["id"] for k, n in put.items()), "node ids kept"
assert put["Ask me on Telegram"]["webhookId"] == live["Ask me on Telegram"]["webhookId"], "open Telegram questions keep working"
assert http("/api/command", {"text": "banana rule"})[0] == 502, "invalid rule twice -> 502"
assert http("/api/command", {"text": ""})[0] == 400

code, r = http("/api/share", {"to": "Sanne", "text": "Same but in Spain"})
assert code == 200 and r["link"].startswith("inky.app/a/buy-to-let-abroad-") and len(r["link"]) == len("inky.app/a/buy-to-let-abroad-") + 4, r
assert "leak" not in BAD_ONCE and "200" not in r["description"], "a description with the budget is retried"
assert r["gets"][2] == "The rules R1 to R7, with the budget left for them to set" and len(r["gets"]) == 4 and len(r["keeps"]) == 3, r
assert serve.amounts("€200,000 or 200.000 or 200 000 or 200k, every 15 minutes") == {200000.0, 15.0}
assert http("/api/share", {})[0] == 400

# ---- plan (C3) ----
p0 = serve.plan()
code, r = http("/api/plan", {"plan": {**p0, "budget_eur": 180000, "never": ["pay"]}})
assert code == 200 and r["ok"] is True and r["plan"]["budget_eur"] == 180000, r
assert r["plan"]["never"][0] == "pay" and set(p0["never"]) <= set(r["plan"]["never"]), "the safety limits stay"
assert json.loads(serve.PLAN.read_text()) == r["plan"] and json.loads((FULL / "plan.backup.json").read_text()) == p0
assert http("/api/plan", {"plan": {"budget_eur": 1}})[0] == 400, "missing keys"
assert http("/api/plan", {"plan": {**p0, "extra": 1}})[0] == 400, "unknown key"
assert http("/api/plan", {"plan": {**p0, "cities": ["paris"]}})[0] == 400
assert http("/api/plan", {"plan": {**p0, "budget_eur": "lots"}})[0] == 400
assert http("/api/plan", {})[0] == 400
serve.PLAN.write_text(json.dumps(p0))

# ---- marketplace (I2): the example bundle and the ones share/export.py --out wrote into <data>/shared/ ----
CARD = {"id", "title", "description", "author", "cities", "rules", "sources", "created_at", "example"}
merge = lambda *srcs: {"nodes": [{"name": n, "type": "n8n-nodes-base.httpRequest"} for n in srcs] + [{"name": "Merge", "type": "n8n-nodes-base.merge"},
                                                                                                   {"name": "Score", "type": "n8n-nodes-base.code"}],
                       "connections": {**{n: {"main": [[{"node": "Merge", "type": "main", "index": 0}]]} for n in srcs},
                                       "Merge": {"main": [[{"node": "Score", "type": "main", "index": 0}]]}}, "name": "Inky · Flats in Bari"}
for name, files in {"sanne": {"inky-main.json": merge("idealista · Bari", "immobiliare · Bari"), "plan.json": {**p0, "cities": ["bari"]},
                              "rules.json": {"final": [{"id": "R1"}, {"id": "R2"}]},
                              "bundle.json": {"title": "Flats in Bari", "description": "Two-bed flats near the sea.\nSecond line.", "author": "Sanne",
                                              "created_at": "2026-09-27T09:00:00+00:00"}},
                    "older": {"inky-main.json": merge("otodom · Łódź"), "plan.json": {**p0, "cities": ["lodz"]}, "rules.json": {"final": []},
                              "bundle.json": {"created_at": "2026-09-26T09:00:00+00:00", "author": " "}},
                    "not-a-bundle": {"README.md": "hi"}, "broken": {"inky-main.json": "{not json", "plan.json": {}}}.items():
    (FULL / "shared" / name).mkdir(parents=True)
    for f, doc in files.items():
        (FULL / "shared" / name / f).write_text(doc if isinstance(doc, str) else json.dumps(doc))
(FULL / "shared" / "stray.json").write_text("{}")
code, r = http("/api/bundles")
assert code == 200 and set(r) == {"bundles"} and all(set(b) == CARD for b in r["bundles"]), r
ex, sanne, older = r["bundles"]
assert ex["id"] == "example" and ex["example"] is True and ex["title"] == "Buy-to-let abroad" and ex["cities"] == ["porto", "bari", "lodz"], ex
assert ex["rules"] == 7 and ex["sources"] > 0 and ex["description"].startswith("Where can") and serve.when(ex["created_at"]), ex
assert sanne == {"id": "sanne", "title": "Flats in Bari", "description": "Two-bed flats near the sea.", "author": "Sanne", "cities": ["bari"],
                 "rules": 2, "sources": 2, "created_at": "2026-09-27T09:00:00+00:00", "example": False}, sanne
assert (older["id"], older["title"], older["author"], older["rules"], older["sources"]) == ("older", "Flats in Bari", None, 0, 1), older
assert older["description"] == p0["question"], "no description in bundle.json: the plan's question"
text = json.dumps(r)
assert not any(s in text for s in ("INKY_", "n8n.cloud", "webhook", "credential", "budget")), "a card shows no placeholders, hosts or secrets"

# ---- research run (C1): Server-Sent Events, on its own copy of the data ----
RES = TMP / "res"
shutil.copytree(HERE.parent / "data-offline", RES, ignore=shutil.ignore_patterns("n8n-*.json"))
# E6: listing dates on two sources (ISO and unix seconds), 0-119 days old; idealista (Porto) has none, like the real data
for f, made, seen, as_time in [("lodz-sale-otodom", "dateCreated", "scrapedAt", lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")),
                               ("bari-sale-immobiliare", "creationDate", "lastModified", lambda t: int(t.timestamp()))]:
    items, t0 = json.loads((RES / "raw" / f"{f}.json").read_text()), serve.when("2026-09-26T20:00:00Z")
    for i, item in enumerate(items):
        item.update({made: as_time(t0 - serve.timedelta(days=i)), seen: as_time(t0 - serve.timedelta(days=i % 3))})
    (RES / "raw" / f"{f}.json").write_text(json.dumps(items))
serve.DATA = RES
rules_before = json.loads((RES / "rules.json").read_text())
ev = sse("/api/research/run", {})
steps, versions, done = [e for e in ev if e["type"] == "step"], [e for e in ev if e["type"] == "version"], ev[-1]
assert done["type"] == "done", done
assert steps[1] == {"type": "step", "text": "Read 720 listings", "sub": "480 for sale, 240 for rent"}, steps[1]
assert [s["text"] for s in steps if s["text"].startswith("Asked")] == ["Asked GLM-5.3 for rules v1", "Asked GLM-5.3 for rules v2", "Asked GLM-5.3 for rules v3"]
assert any(s["text"].endswith("neighbourhoods pass") for s in steps)
assert [v["v"] for v in versions] == [1, 2, 3] and versions[0]["matches"] >= versions[-1]["matches"] > 0, versions
assert versions[-1]["rules"][1]["value"] == 5.5 and isinstance(versions[0]["zones"], int)
res, rules = done["research"], done["rules"]
assert rules["final"] == versions[-1]["rules"] and json.loads((RES / "rules.json").read_text()) == rules
assert json.loads((RES / "rules.bak.json").read_text()) == rules_before, "the previous rules are kept"
assert res == json.loads((RES / "research.json").read_text()) and res["llm_calls"] == 3 and res["llm_cost_usd"] == 0.006
m = res["matches"][0]
assert {"rent_month", "gross_yield", "net_yield", "zone_rent_listings", "price_vs_zone", "price_trend", "country", "rent_m2", "sale_m2", "n_rent"} <= set(m), m
assert set(res["costs"]) == {"PT", "IT", "PL"} and set(res["best_by_city"]) == set(serve.plan()["cities"])
sp = res["speed"]["by_city"]
assert sp["porto"] == {"listings": 0, "reason": "idealista gives no listing dates for homes for sale"}, sp
assert sp["lodz"] == {"sources": ["otodom"], "listings": 120, "median_age_days": 59.5, "under_7_days_pct": 5.8, "new_24h": 1,
                      "read_at": "2026-09-26T20:00:00+00:00"}, sp["lodz"]
assert sp["bari"] == {**sp["lodz"], "sources": ["immobiliare"]}, sp["bari"]
assert all(b["reason"] is None for b in res["best_by_city"].values() if b["matches"]), res["best_by_city"]
assert "research" not in BAD_ONCE, "an invalid GLM answer is retried once"

code, r = http("/api/research/run", {"plan": {"budget_eur": 1}})
assert code == 400, "a bad plan is refused before anything runs"
ev = sse("/api/research/run", {"plan": {**p0, "budget_eur": 150000}, "offline": True})
assert ev[0] == {"type": "step", "text": "Saved your plan", "sub": "Porto, Bari, Łódź · up to €150,000"}, ev[0]
assert ev[-1]["type"] == "done" and ev[-1]["rules"]["final"][0]["value"] == 150000, "the offline rules use the saved plan's budget"
assert ev[-1]["research"]["llm_calls"] == 0 and json.loads(serve.PLAN.read_text())["budget_eur"] == 150000
assert any(e["type"] == "step" and e["text"] == "Took the offline rules v2" for e in ev)
serve.PLAN.write_text(json.dumps({**p0, "question": "LOOSEN"}))  # GLM loosens after v1: 53 -> 141 -> 141 homes
ev = sse("/api/research/run", {})
assert ev[-1]["rules"]["final_v"] == 1 and ev[-1]["rules"]["final"] == ev[-1]["rules"]["versions"][0]["rules"], ev[-1]["rules"]
assert ev[-1]["research"]["final_v"] == 1 and {"type": "step", "text": "Kept rules v1", "sub": "closest to 15-60 homes over 2+ cities: 53 homes in 4 neighbourhoods"} in ev
serve.PLAN.write_text(json.dumps({**p0, "question": "BROKEN"}))
ev = sse("/api/research/run", {})
assert ev[-1]["type"] == "error" and "GLM did not return valid rules in 3 tries" in ev[-1]["text"], ev[-1]
serve.PLAN.write_text(json.dumps(p0))
serve.JOBS["research"].acquire()
assert http("/api/research/run", {})[0] == 409, "one research run at a time"
serve.JOBS["research"].release()
serve.DATA = FULL

# ---- build run (C2) ----
real_deploy = getattr(serve.workflow, "deploy", None)
if real_deploy:
    del serve.workflow.deploy
code, r = http("/api/build/run", {})
assert code == 503 and "workflow.deploy" in r["error"], r
deploys, gate = [], threading.Event()


def fake_deploy(progress, staging=False):
    deploys.append(staging)
    progress("Credentials ready", "Apify · Telegram")
    gate.wait(5)  # the test only opens this once it has the first events: proof they stream
    progress({"text": "Published", "sub": "main and repair", "url": "https://example.app.n8n.cloud/workflow/S1"})
    progress({"type": "done", "text": "not the end"})
    return {"main_url": "https://example.app.n8n.cloud/workflow/S1", "repair_url": "https://example.app.n8n.cloud/workflow/S2",
            "best_url": "https://example.app.n8n.cloud/webhook/SECRET", "gmail": False, "main": "S1"}


serve.workflow.deploy = fake_deploy
t = time.time()
ev = sse("/api/build/run", {"staging": True}, first=lambda e: gate.set())
assert time.time() - t < 4, "events stream as they happen, not at the end"
assert [e["text"] for e in ev[:-1]] == ["Building the staging n8n workflows", "Credentials ready", "Published", "not the end"], ev
assert all(e["type"] == "step" for e in ev[:-1]) and ev[2]["url"].endswith("/S1") and ev[1]["sub"] == "Apify · Telegram"
assert ev[-1] == {"type": "done", "main_url": "https://example.app.n8n.cloud/workflow/S1", "repair_url": "https://example.app.n8n.cloud/workflow/S2",
                  "staging": True, "gmail": False}, "the webhook URL (its secret path) never reaches the page"
os.environ["INKY_SAFE"] = "1"
ev = sse("/api/build/run", {"staging": False})
assert deploys == [True, True] and ev[-1]["staging"] is True, "INKY_SAFE=1 forces staging"
del os.environ["INKY_SAFE"]
serve.workflow.deploy = lambda progress, staging=False: deploys.append(staging) or None
ev = sse("/api/build/run", {})
assert deploys[-1] is False and ev[-1]["main_url"] == "https://example.app.n8n.cloud/workflow/M1", "live by default, links from n8n.json"


def broken_deploy(progress, staging=False):
    progress("Credentials ready")
    raise RuntimeError("n8n PUT /workflows: 400")


serve.workflow.deploy = broken_deploy
ev = sse("/api/build/run", {})
assert ev[-1] == {"type": "error", "text": "RuntimeError: n8n PUT /workflows: 400"}, ev[-1]
serve.JOBS["build"].acquire()
assert http("/api/build/run", {})[0] == 409
serve.JOBS["build"].release()
del serve.workflow.deploy
if real_deploy:
    serve.workflow.deploy = real_deploy

# ---- best now (B1): a local stub server stands in for the n8n webhook ----
hooked = []


class Hook(serve.SimpleHTTPRequestHandler):
    def do_POST(self):
        hooked.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(Hook.code)
        self.end_headers()

    def log_message(self, *a):
        pass


Hook.code = 200
hook = serve.ThreadingHTTPServer(("127.0.0.1", 0), Hook)
threading.Thread(target=hook.serve_forever, daemon=True).start()
real_url = getattr(serve.workflow, "best_now_url", None)
if real_url:
    del serve.workflow.best_now_url
code, r = http("/api/best_now", {})
assert code == 503 and "not deployed" in r["error"], r
serve.workflow.best_now_url = lambda: None
assert http("/api/best_now", {})[0] == 503
serve.workflow.best_now_url = lambda: f"http://127.0.0.1:{hook.server_address[1]}/webhook/best-now"
code, r = http("/api/best_now", {})
assert code == 200 and r["sent"] == 3 and len(r["matches"]) == 3, r
assert hooked == [{"matches": r["matches"]}], "the webhook gets exactly the homes the app shows"
final = json.loads((FULL / "rules.json").read_text())["final"]
assert all(m["match"] and set(m["passed"]) == {x["id"] for x in final} for m in r["matches"])
assert [m["net_yield"] for m in r["matches"]] == sorted((m["net_yield"] for m in r["matches"]), reverse=True)
assert http("/api/best_now", {"n": 1})[1]["sent"] == 1 and http("/api/best_now", {"n": 0})[0] == 400
Hook.code = 500
assert http("/api/best_now", {})[0] == 502
os.environ["INKY_SAFE"] = "1"
serve.workflow.best_now_url = lambda: "https://example.app.n8n.cloud/webhook/best-now"
calls = len(hooked)
code, r = http("/api/best_now", {})
assert code == 503 and "INKY_SAFE" in r["error"] and len(hooked) == calls, r
del os.environ["INKY_SAFE"]
del serve.workflow.best_now_url
if real_url:
    serve.workflow.best_now_url = real_url
hook.shutdown()


# ---- summary (B3, B4), end card (A8) and run detail with before/after (C5) ----
def execution(i, status, start, stop, sources, score=None, mode="trigger", failed=None):
    names = list(sources) + ([failed] if failed else [])
    nodes = [{"name": n, "type": "n8n-nodes-base.httpRequest"} for n in names] + [{"name": "Merge", "type": "n8n-nodes-base.merge"}]
    rd = {n: [{"executionTime": 9, "data": {"main": [[{"json": {"propertyCode": f"{n}-{k}"}} for k in ids]]}}] for n, ids in sources.items()}
    if failed:
        rd[failed] = [{"executionTime": 3, "error": {"message": "Bad request - please check your parameters"}}]
    if score is not None:
        rd["Score · rules"] = [{"executionTime": 5, "data": {"main": [[{"json": {"net_yield": 7}} for _ in range(score)]]}}]
    row = {"id": str(i), "status": status, "mode": mode, "startedAt": start, "stoppedAt": stop, "workflowId": "M1"}
    FakeN8n.full[str(i)] = {**row, "workflowData": {"nodes": nodes, "connections": {n: {"main": [[{"node": "Merge", "type": "main", "index": 0}]]} for n in names}},
                            "data": {"resultData": {"runData": rd}}}
    return row


D = "2026-09-26T"
main_runs = [  # newest first, like n8n
    {"id": "5", "status": "running", "mode": "trigger", "startedAt": D + "22:00:00Z", "stoppedAt": None},
    execution(4, "success", D + "21:40:00Z", D + "21:40:01Z", {}),  # the 08:00 digest: no source step ran
    execution(3, "success", D + "21:00:00Z", D + "21:01:00Z", {"A": range(12), "B": range(5)}, score=0, mode="integrated"),
    execution(2, "error", D + "20:45:00Z", D + "20:46:00Z", {"A": range(10)}, failed="B"),
    execution(1, "waiting", D + "20:30:00Z", None, {"A": range(10), "B": range(5)}, score=1),
]
FakeN8n.full["9"] = {"id": "9", "status": "success", "mode": "error", "startedAt": D + "20:50:00Z", "stoppedAt": D + "20:51:00Z", "workflowData": {},
                     "data": {"resultData": {"runData": {
                         "Read the error": [{"data": {"main": [[{"json": {"step": "B", "error": "Bad request - please check your parameters"}}]]}}],
                         "Pick the broken step": [{"data": {"main": [[{"json": {"step": "B", "key": "jsonBody", "before": '{"searchType": "sale"}',
                                                                                "wf": {"nodes": ["big"]}, "body": {"messages": ["big"]}}}]]}}],
                         "Patch the step": [{"data": {"main": [[{"json": {"workflowId": "M1", "step": "B", "change": "searchType is sprzedaz",
                                                                          "workflow": {"nodes": [{"name": "B", "parameters": {"jsonBody": '{"searchType": "sprzedaz"}'}}]}}}]]}}],
                         "Save the fix": [{"data": {"main": [[{"json": {}}]]}}]}}}}
FakeN8n.full["5"] = {**main_runs[0], "data": {"resultData": {"runData": {}}}}
FakeN8n.execs = {"M1": main_runs, "R9": [{k: FakeN8n.full["9"][k] for k in ("id", "status", "mode", "startedAt", "stoppedAt")}]}
APIFY = [(serve.when(D + t), usd) for t, usd in [("21:00:20Z", 0.05), ("20:45:10Z", 0.04), ("20:30:05Z", 0.1), ("19:00:00Z", 5.0)]]
serve.apify_runs = lambda since: [a for a in APIFY if a[0] >= since]

code, r = http("/api/run_detail")
rep = r["repair"]
assert code == 200 and rep["step"] == "B" and rep["change"] == "searchType is sprzedaz" and rep["error"].startswith("Bad request"), rep
assert rep["before"] == {"searchType": "sale"} and rep["after"] == {"searchType": "sprzedaz"}, rep
assert "workflow" not in rep and "wf" not in json.dumps(rep) and rep["failed"]["id"] == "2" and rep["again"]["id"] == "3", rep
assert r["main"]["id"] == "5" and r["ok"]["id"] == "4", r

fetched = lambda: sum(1 for m, p, _ in n8n_calls if p.startswith("/executions/"))
before = fetched()
code, s = http("/api/summary?since=2026-09-26T00:00:00Z")
assert code == 200, s
assert (s["runs"], s["ok"], s["failed"], s["waiting"], s["repairs"]) == (3, 2, 1, 1, 1), s
assert (s["listings_checked"], s["new_listings"], s["matches"]) == (32, 17, 1), s
assert (s["apify_usd"], s["apify_usd_runs"], s["apify_usd_per_run"], s["ai_calls"]) == (5.19, 0.19, 0.063, 0), s
assert s["glm_usd_research"] == serve.read_json(FULL / "research.json")["llm_cost_usd"] and s["errors"] == []
assert [x["id"] for x in s["per_run"]] == ["3", "2", "1"] and s["fixes"] == [{"id": "9", "startedAt": D + "20:50:00Z", "step": "B", "change": "searchType is sprzedaz"}]
assert s["per_run"][0] == {"id": "3", "startedAt": D + "21:00:00Z", "status": "success", "mode": "integrated", "listings": 17, "new": 2, "matches": 0,
                           "secs": 60.0, "sources": {"A": 12, "B": 5}, "apify_usd": 0.05}, s["per_run"][0]
assert s["per_run"][1]["sources"] == {"A": 10, "B": 0} and s["per_run"][1]["new"] == 0 and s["per_run"][2]["secs"] is None
assert fetched() - before == 5, "every finished run fetched once, the running one not"
cache = json.loads((FULL / "run-cache.json").read_text())
assert set(cache) == {"1", "2", "3", "4", "9"} and "5" not in cache
n = len(n8n_calls)
assert http("/api/summary?since=2026-09-26T00:00:00Z")[1] == s and len(n8n_calls) == n, "cached 60 s"
code, s2 = http("/api/summary?since=2026-09-26T20:40:00%2B00:00")
assert code == 200 and s2["runs"] == 2 and s2["new_listings"] == 2 and s2["apify_usd"] == 0.09 and fetched() - before == 5, s2
code, s3 = http("/api/summary")
ago = (serve.datetime.now(serve.timezone.utc) - serve.when(s3["since"])).total_seconds()
assert code == 200 and abs(ago - 86400) < 120, "default: the last 24 h"
assert http("/api/summary?since=yesterday")[0] == 400
assert s["n8n_stats"] is None, "no saved counters in this fake workflow yet"
FakeN8n.live["staticData"] = {"global": {"stats": {"runs": 2, "checked": 30, "fresh": 16, "matches": 1, "since": D + "20:30:00Z"}}}
code, e = http("/api/end")
assert code == 200 and e == {"listings_read": 720, "runs": 3, "listings_checked": 30, "new_listings": 16, "matches": 1,
                             "research_matches": len(serve.read_json(FULL / "research.json")["matches"]), "fixes": 1, "apify_usd_total": 5.19,
                             "apify_usd_per_run": 0.063, "glm_usd_research": serve.read_json(FULL / "research.json")["llm_cost_usd"],
                             "ai_calls_per_run": 0, "repo": "github.com/GHGuide/inky"}, e
FakeN8n.execs, serve._runs["at"], serve._detail["at"] = None, 0, 0

# ---- another data folder than the one n8n was built from: links stay, push is skipped out loud ----
serve.N8N_STATE = TMP / "n8n.json"
shutil.copy(FULL / "n8n.json", serve.N8N_STATE)
puts = sum(c[0] == "PUT" for c in n8n_calls)
assert http("/api/state")[1]["n8n"]["main_url"].endswith("/workflow/M1")
code, r = http("/api/command", {"text": "max 150k"})
assert code == 200 and r["applied"] is True and r["n8n_error"].startswith("not pushed"), r
assert sum(c[0] == "PUT" for c in n8n_calls) == puts
serve.workflow.deploy = lambda progress, staging=False: {"main_url": "S"}
code, r = http("/api/build/run", {})
assert code == 503 and r["error"].startswith("not deployed live"), r
assert sse("/api/build/run", {"staging": True})[-1] == {"type": "done", "main_url": "S", "repair_url": None, "staging": True}
del serve.workflow.deploy
if real_deploy:
    serve.workflow.deploy = real_deploy

# ---- without data (the scrape has not finished) ----
serve.DATA, serve.N8N_STATE = EMPTY, EMPTY / "n8n.json"
serve._runs["at"] = 0
serve._summary.clear()
code, s = http("/api/state")
assert code == 200 and s["research"] is None and s["rules"] is None and s["n8n"] is None and s["plan"]["cities"], s
assert http("/api/executions") == (200, [])
calls = len(glm_calls)
code, r = http("/api/command", {"text": "max 150k"})
assert code == 200 and r["applied"] is False and r["rule"] is None and r["matches_before"] is None and "No rules yet" in r["change"], r
assert http("/api/command", {"text": "max 150k", "dry_run": True})[1]["dry_run"] is True
assert len(glm_calls) == calls, "no GLM spend without rules"
code, r = http("/api/share", {"to": "Sanne"})
assert code == 200 and r["gets"][2].startswith("The rules, once research finishes"), r
code, s = http("/api/summary")
assert code == 200 and s["runs"] == 0 and s["per_run"] == [] and s["errors"] == [], s
assert http("/api/end")[1]["listings_read"] is None
assert http("/api/best_now", {})[0] == 503
ev = sse("/api/research/run", {})
assert ev == [{"type": "error", "text": f"RuntimeError: no listings in {EMPTY / 'raw'}: run the scrape (research.py) first"}], ev

# ---- demo mode (K4): the committed snapshot in data-demo/; nothing may call GLM, n8n, Apify or a webhook ----
from dotenv import dotenv_values  # noqa: E402

demo = serve.DEMO_DIR
assert (demo / "research.json").exists(), "data-demo/ is missing: run app/make_demo.py"
size = sum(f.stat().st_size for f in demo.rglob("*") if f.is_file())
assert size < 2e6, f"data-demo/ is {size / 1e6:.1f} MB"
text = "".join(f.read_text() for f in demo.rglob("*.json"))
for k, v in dotenv_values(HERE.parent / ".env").items():
    assert k == "OPENROUTER_MODEL" or not v or len(v) < 8 or v not in text, f"{k} is in data-demo/"
assert "app.n8n.cloud" not in text


def boom(*a, **kw):
    raise AssertionError("demo mode called out")


serve.DEMO, serve.DATA, serve.PLAN, serve.DEMO_PACE = True, demo, demo / "plan.json", 0
serve.derive.glm = FakeN8n.call = serve.httpx.post = serve.httpx.get = serve.apify_runs = boom
plan_text = serve.PLAN.read_text()
code, s = http("/api/state")
assert code == 200 and s["n8n"]["demo"] is True and 0 < len(s["research"]["matches"]) <= 60 and s["rules"]["final"] and s["program"], s.keys()
assert set(s["research"]["speed"]["by_city"]) == set(s["plan"]["cities"]), "E6 speed is in the demo research"
code, r = http("/api/bundles")
assert code == 200 and [b["id"] for b in r["bundles"]] == ["example"], r
for path in ("/api/executions", "/api/run_detail", "/api/summary", "/api/end"):
    code, r = http(path)
    assert code == 200 and r, (path, r)
assert http("/api/end")[1]["ai_calls_per_run"] == 0 and "per_run" in http("/api/summary")[1]
code, r = http("/api/interview", {"messages": [{"role": "user", "content": "I want rent from a flat abroad"}]})
assert code == 200 and r["done"] is False and r["questions"], r
code, r = http("/api/interview", {"messages": [{"role": "user", "content": "x"}, {"role": "assistant", "content": r}, {"role": "user", "content": "y"}]})
assert code == 200 and "done" in r, r
code, r = http("/api/command", {"text": "only homes under 150k"})
assert code == 200 and r["demo"] is True and r["applied"] is False and r["change"], r
assert http("/api/share", {"to": "Sanne"})[1]["link"].startswith("inky.app/a/")
code, r = http("/api/plan", {"plan": {**json.loads(plan_text), "budget_eur": 1000}})
assert code == 200 and r["demo"] is True and serve.PLAN.read_text() == plan_text, "the snapshot is never written"
code, r = http("/api/best_now", {})
assert code == 200 and r["sent"] == 0 and len(r["matches"]) == 3, r
ev = sse("/api/research/run", {})
assert ev[-1]["type"] == "done" and ev[-1]["research"]["matches"] and any(e["type"] == "version" for e in ev), ev[-1]
if (demo / "replies" / "build_run.json").exists():
    assert sse("/api/build/run", {})[-1]["type"] == "done"
else:
    print("note: data-demo/replies/build_run.json not recorded yet (app/make_demo.py --record-build)")

srv.shutdown()
shutil.rmtree(TMP)
print(f"ok: all endpoints, with and without data, and demo mode ({len(glm_calls)} fake GLM calls, {len(n8n_calls)} fake n8n calls)")
