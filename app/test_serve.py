"""Offline check of app/serve.py: every endpoint, with data and without. GLM and n8n are faked, nothing leaves the machine.

    .venv/bin/python app/test_serve.py
"""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
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
os.environ.update(INKY_DATA=str(FULL), N8N_BASE_URL="https://example.app.n8n.cloud/home/workflows/", N8N_API_KEY="fake", OPENROUTER_API_KEY="fake")
os.environ.pop("N8N_GMAIL_CREDENTIAL_ID", None)
sys.path.insert(0, str(HERE))
import serve  # noqa: E402

serve.STATIC = STATIC
serve.N8N_STATE = FULL / "n8n.json"  # never the repo's real data/n8n.json
glm_calls, n8n_calls = [], []
BAD_ONCE = {"interview": True, "echo": True, "leak": True}


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
    raise AssertionError(f"unexpected GLM prompt: {system[:60]}")


class FakeN8n:
    base = "https://example.app.n8n.cloud"

    def call(self, method, path, **kw):
        n8n_calls.append((method, path, kw))
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

# ---- another data folder than the one n8n was built from: links stay, push is skipped out loud ----
serve.N8N_STATE = TMP / "n8n.json"
shutil.copy(FULL / "n8n.json", serve.N8N_STATE)
puts = sum(c[0] == "PUT" for c in n8n_calls)
assert http("/api/state")[1]["n8n"]["main_url"].endswith("/workflow/M1")
code, r = http("/api/command", {"text": "max 150k"})
assert code == 200 and r["applied"] is True and r["n8n_error"].startswith("not pushed"), r
assert sum(c[0] == "PUT" for c in n8n_calls) == puts

# ---- without data (the scrape has not finished) ----
serve.DATA, serve.N8N_STATE = EMPTY, EMPTY / "n8n.json"
serve._runs["at"] = 0
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

srv.shutdown()
shutil.rmtree(TMP)
print(f"ok: all endpoints, with and without data ({len(glm_calls)} fake GLM calls, {len(n8n_calls)} fake n8n calls)")
