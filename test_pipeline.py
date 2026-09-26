"""Offline check of the whole pipeline: fixtures -> derive -> n8n workflows -> run the n8n Code nodes.

    uv run python test_pipeline.py                  # full check in a temp folder, no keys, no spend
    uv run python test_pipeline.py --fixtures-only  # just write fixture raw files into $INKY_DATA/raw

The fixtures copy the item shapes of the three Apify actors (from their READMEs). The n8n Code
nodes run in Node with the same globals n8n gives them ($input, $, $json, static data).
"""
import json
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
# city: zone -> (sale per m², rent per m² per month), in local currency
ZONES = {
    "porto": {"Campanhã": (2800, 15.5), "Bonfim": (3600, 16), "Foz do Douro": (6000, 18)},
    "bari": {"Libertà": (1600, 9.8), "Murat": (3200, 12), "Poggiofranco": (2400, 9)},
    "lodz": {"Śródmieście": (9000, 62), "Bałuty": (7000, 48), "Widzew": (7500, 50)},
}


def idealista(rng, city, op, zone, i, m2, per):
    return {"propertyCode": f"{city}{op}{zone}{i}", "operation": op, "municipality": city.title(), "neighborhood": zone,
            "price": round(m2 * per), "size": m2, "rooms": rng.choice([1, 2, 2, 3]),
            "url": f"https://www.idealista.pt/imovel/{i}/", "suggestedTexts": {"title": f"T2 em {zone}"}}


def immobiliare(rng, city, op, zone, i, m2, per):
    return {"id": hash((city, op, zone, i)) % 10**9, "title": f"Bilocale {zone}", "contract": {"name": "Sale" if op == "sale" else "Rent"},
            "geography": {"municipality": {"name": "Bari"}, "macrozone": {"name": zone}},
            "price": {"raw": round(m2 * per), "currency": "EUR"}, "topology": {"surface": {"size": m2}, "rooms": str(rng.choice([2, 3, 4]))}}


def otodom(rng, city, op, zone, i, m2, per):
    return {"id": f"{op}{zone}{i}", "title": f"Mieszkanie {zone}", "price": round(m2 * per), "priceCurrency": "PLN",
            "area": m2, "rooms": rng.choice([2, 3, 3, 4]), "city": "Łódź", "district": zone,
            "propertyUrl": f"https://www.otodom.pl/pl/oferta/{op}-{i}"}


def fixtures(raw: Path):
    rng = random.Random(7)
    raw.mkdir(parents=True, exist_ok=True)
    jobs = {"porto": [("idealista", idealista)], "bari": [("idealista", idealista), ("immobiliare", immobiliare)], "lodz": [("otodom", otodom)]}
    for city, makers in jobs.items():
        for source, make in makers:
            for op in ("sale", "rent"):
                items = []
                for zone, (sale, rent) in ZONES[city].items():
                    for i in range(40 if op == "sale" else 20):
                        m2 = rng.randint(35, 95)
                        per = (sale if op == "sale" else rent) * rng.uniform(0.7, 1.3)
                        items.append(make(rng, city, op, zone, i, m2, per))
                (raw / f"{city}-{op}-{source}.json").write_text(json.dumps(items, ensure_ascii=False))


HARNESS = r"""
const fs = require('fs');
const { code, input, json, refs, statics, now } = JSON.parse(fs.readFileSync(0, 'utf8'));
if (now) {  // a fixed clock, for quiet hours and the daily cap
  const Real = Date;
  globalThis.Date = class extends Real {
    constructor(...a) { super(...(a.length ? a : [now])); }
    static now() { return new Real(now).getTime(); }
  };
}
const staticData = statics || {};
const $ = (name) => ({ first: () => ({ json: refs[name][0] }), itemMatching: (i) => ({ json: refs[name][i] }), isExecuted: name in refs });
const fn = new Function('$input', '$json', '$', '$getWorkflowStaticData', code);
try {
  const all = () => input.map((j) => ({ json: j }));
  const out = fn({ all, first: () => all()[0] }, json, $, () => staticData);
  process.stdout.write(JSON.stringify({ out: out.map((o) => o.json), statics: staticData }));
} catch (e) {
  process.stdout.write(JSON.stringify({ error: e.message, statics: staticData }));
}
"""
NOON = "2026-09-27T10:00:00Z"  # 12:00 in Amsterdam


def run_code(code, input=(), json_=None, refs=None, statics=None, now=NOON):
    r = subprocess.run(["node", "-e", HARNESS], input=json.dumps({"code": code, "input": list(input), "json": json_ or {}, "refs": refs or {}, "statics": statics, "now": now}),
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def tecnocasa(rng):
    """Items of Inky's own actor (teach/actor): already typed, Tecnocasa's own quarter names."""
    return [{"source": "tecnocasa", "city": "bari", "op": "sale", "title": "Bilocale in vendita", "price": rng.randint(60, 180) * 1000,
             "size_m2": rng.randint(40, 90), "rooms": 2, "zone": zone, "url": f"https://www.tecnocasa.it/vendita/appartamenti/bari/bari/{7000 + i}.html"}
            for i, zone in enumerate(["Quartiere Murat Antico", "Libertà", "Parco Due Giugno"] * 4)]


def check_connections(wf):
    names = [n["name"] for n in wf["nodes"]]
    assert len(names) == len(set(names)), "duplicate node names"
    for src, out in wf["connections"].items():
        assert src in names and all(c["node"] in names for branch in out["main"] for c in branch), src


def test_score(nodes, sale, tmp):
    score = nodes["Score · rules"]["parameters"]["jsCode"]
    # First run finds matches, the same items again find nothing new, a missing source throws.
    r1 = run_code(score, sale)
    assert "error" not in r1, r1.get("error")
    assert 1 <= len(r1["out"]) <= 3 and all(m["match"] for m in r1["out"]), len(r1["out"])
    assert "Gmail draft" in r1["out"][0]["telegram_text"] and r1["out"][0]["email_body"], r1["out"][0]["telegram_text"]
    assert r1["statics"]["stats"]["runs"] == 1 and r1["statics"]["night"]["runs"] == 1
    r2 = run_code(score, sale, statics=r1["statics"])  # nothing new: only the matches that did not fit in 3 questions
    assert r2["statics"]["stats"]["fresh"] == r1["statics"]["stats"]["fresh"], "dedupe failed"
    assert [m["url"] for m in r2["out"]] == [m["url"] for m in r1["statics"]["held"][:3]], "held matches"
    r3 = run_code(score, [i for i in sale if "propertyUrl" not in i])
    assert r3.get("error") == "Step otodom · Łódź returned 0 homes", r3

    # Tecnocasa quarters join the rent data by name: "Quartiere Murat Antico" -> Murat.
    table = json.loads(score.split("const ZONE_NEAR = ", 1)[1].split(";\n", 1)[0])
    assert table["bari"]["murat"] == "Murat", table

    # Schema drift: otodom items that no longer read (price and area renamed) -> the step is named for the repair.
    drift = [({**{k: v for k, v in i.items() if k not in ("price", "area")}, "cena": i["price"]} if "propertyUrl" in i else i) for i in sale]
    r4 = run_code(score, drift)
    assert r4.get("error") == "Step otodom · Łódź returned items Inky can't read", r4

    # The same flat on two sites counts once (city, price, size).
    twin = next(i for i in sale if "propertyCode" in i and i["municipality"] == "Bari")
    other = {"id": 999999, "title": "Same flat", "contract": {"name": "Sale"}, "geography": {"municipality": {"name": "Bari"}, "macrozone": {"name": twin["neighborhood"]}},
             "price": {"raw": twin["price"], "currency": "EUR"}, "topology": {"surface": {"size": twin["size"]}, "rooms": "3"}, "url": "https://www.immobiliare.it/annunci/999999/"}
    one = run_code(score, sale)["statics"]["stats"]["fresh"]
    two = run_code(score, sale + [other])["statics"]["stats"]["fresh"]
    assert one == two, (one, two)

    # Quiet hours: at 01:00 matches are held, the 07:15 run asks them (best first, 3 at most, the rest wait).
    night = run_code(score, sale, now="2026-09-26T23:00:00Z")
    assert night["out"] == [] and night["statics"]["held"], "quiet hours"
    held = len(night["statics"]["held"])
    morning = run_code(score, sale, statics=night["statics"], now="2026-09-27T05:15:00Z")
    assert len(morning["out"]) == min(3, held) and len(morning["statics"]["held"]) == max(0, held - 3), (held, len(morning["out"]))
    assert morning["out"][0]["net_yield"] >= morning["out"][-1]["net_yield"]
    assert (" 1 of " in morning["out"][0]["telegram_text"]) == (len(morning["out"]) > 1)
    return r1, r3


def test_main_nodes(nodes, r1):
    # The daily cap: runs are counted per Amsterdam day; over the cap, Apify is not called.
    cap = nodes["Under the daily cap"]["parameters"]["jsCode"]
    c1 = run_code(cap)
    assert c1["out"][0]["run"] == 1 and c1["statics"]["day"]["runs"] == 1, c1
    full = run_code(cap, statics={"day": {"date": "2026-09-27", "runs": 120, "skipped": 0}})
    assert full["out"] == [] and full["statics"]["day"]["skipped"] == 1, full
    fixed = run_code(cap, refs={"Run again after a fix": [{}]}, statics=r1["statics"])
    assert fixed["statics"]["night"]["fixes"] == 1

    # The digest: counters since the last digest, the best home when nothing matched, then the counters restart.
    digest = nodes["Digest"]["parameters"]["jsCode"]
    d1 = run_code(digest, statics=r1["statics"])
    text = d1["out"][0]["text"]
    assert text.startswith("Good morning. While you slept: 1 run · ") and "0 fixes" in text and "Best home" not in text, text
    assert d1["statics"]["night"]["runs"] == 0
    d2 = run_code(digest, statics=d1["statics"])
    assert "Best home right now: " in d2["out"][0]["text"], d2
    old = {"stats": {"runs": 30, "checked": 4000, "fresh": 200, "matches": 0, "since": "x"}, "seen": {}}
    d3 = run_code(digest, statics=old)  # a workflow saved before the digest counters existed: counts from the start
    assert "30 runs · 4,000 listings checked · 200 new · 0 matches" in d3["out"][0]["text"], d3

    # Send me the best now: the app's top homes get the same question, best first, at most 3; bad rows are dropped.
    homes = [{"title": f"Flat {i}", "city": "bari", "zone": "Murat", "price_eur": 90000 + i, "size_m2": 50, "bedrooms": 1,
              "net_yield": 6 + i / 10, "url": f"https://www.idealista.it/immobile/{i}/", "country": "IT"} for i in range(4)]
    homes.append({**homes[0], "url": "javascript:alert(1)"})
    homes.append({**homes[0], "country": None, "net_yield": 9, "title": "No_country *star*"})
    b = run_code(nodes["Best so far"]["parameters"]["jsCode"], [{"body": {"matches": homes}}])
    assert len(b["out"]) == 3 and [h["net_yield"] for h in b["out"]] == [9, 6.3, 6.2], b
    assert b["out"][0]["telegram_text"].startswith("Best so far 1 of 3 · bari · Murat\nNo\\_country \\*star\\*"), b["out"][0]["telegram_text"]
    assert b["out"][0]["email_body"].startswith("Hello") and b["out"][1]["email_body"].startswith("Buongiorno")
    assert run_code(nodes["Best so far"]["parameters"]["jsCode"], [{"body": {}}])["out"] == []

    # Your answer next to the home it was about; no answer (24 h) or Telegram switched off counts as no.
    keep = run_code(nodes["Keep approved"]["parameters"]["jsCode"], [{"data": {"approved": True}}, {"telegram_text": "x"}],
                    refs={"One home at a time": r1["out"][:1] + b["out"][:1]})
    assert [k["approved"] for k in keep["out"]] == [True, False] and keep["out"][0]["email_subject"] == r1["out"][0]["email_subject"], keep


def test_wiring(main_wf):
    c = main_wf["connections"]
    to = lambda a, out=0: [x["node"] for x in c[a]["main"][out]]
    assert to("Every 15 min") == to("Run again after a fix") == ["Under the daily cap"]
    assert len(to("Under the daily cap")) == 5 and to("Merge") == ["Score · rules"]
    assert to("Score · rules") == to("Best so far") == ["One home at a time"] and to("Send me the best now") == ["Best so far"]
    assert c["One home at a time"]["main"][0] == [] and to("One home at a time", 1) == ["Ask me on Telegram"]
    assert to("Ask me on Telegram") == ["Keep approved"] and to("Keep approved") == ["Approved?"]
    assert to("Approved?") == ["Gmail draft to the agent"] and to("Approved?", 1) == to("Gmail draft to the agent") == ["One home at a time"]
    n = {x["name"]: x for x in main_wf["nodes"]}
    assert n["Ask me on Telegram"]["parameters"]["options"]["limitWaitTime"]["values"] == {"limitType": "afterTimeInterval", "resumeAmount": 24, "resumeUnit": "hours"}
    assert n["Send me the best now"]["parameters"]["path"] == "BEST_PATH" and n["Send me the best now"]["webhookId"]
    body = lambda s: json.loads(n[s]["parameters"].get("customBody") or n[s]["parameters"]["jsonBody"])
    assert all(body(s)["maxItems"] == 60 for s in ("idealista · Porto", "idealista · Bari", "immobiliare · Bari", "otodom · Łódź", "tecnocasa · Bari"))
    assert "tecnocasa-homes" in n["tecnocasa · Bari"]["parameters"]["actorId"]["value"] and body("tecnocasa · Bari")["city"] == "Bari"
    o = n["otodom · Łódź"]["parameters"]  # the Apify node (the HTTP node's query is checked in test_deploy)
    assert (o["memory"], o["timeout"], o["maxTotalChargeUsd"]) == (512, 240, 0.3), o
    notes = [x for x in main_wf["nodes"] if x["type"] == "n8n-nodes-base.stickyNote"]
    assert len(notes) >= 4 and notes[0]["parameters"]["content"].startswith("## 1 · Read")
    # Sticky notes do not overlap each other.
    box = lambda x: (x["position"][0], x["position"][1], x["position"][0] + x["parameters"]["width"], x["position"][1] + x["parameters"]["height"])
    for i, a in enumerate(notes):
        for b in notes[i + 1:]:
            A, B = box(a), box(b)
            assert A[2] <= B[0] or B[2] <= A[0] or A[3] <= B[1] or B[3] <= A[1], (a["name"], b["name"])


def test_repair(nodes, main_wf, repair, r3):
    # Repair: read the error, pick the broken Apify step, apply GLM's corrected input.
    err = {"execution": {"error": {"message": r3["error"]}, "lastNodeExecuted": "Score · rules"}, "workflow": {"id": "W1", "name": "Inky"}}
    read = run_code(nodes["Read the error"]["parameters"]["jsCode"], json_=err)
    assert read["out"] == [{"workflowId": "W1", "name": "Inky", "step": "otodom · Łódź", "error": r3["error"]}], read
    again = run_code(nodes["Read the error"]["parameters"]["jsCode"], json_=err, statics=read["statics"])
    assert again["out"] == [], "one message and one fix attempt per hour, whatever the outcome"
    assert repair["connections"]["On error"]["main"][0] == [{"node": "Read the error", "type": "main", "index": 0}]
    drift = {**err, "execution": {"error": {"message": "Step idealista · Porto returned items Inky can't read"}}}
    assert run_code(nodes["Read the error"]["parameters"]["jsCode"], json_=drift)["out"][0]["step"] == "idealista · Porto"
    limited = run_code(nodes["Read the error"]["parameters"]["jsCode"], json_=err, statics=read["statics"] | {"fixes": [9e15]})
    assert limited["out"] == [], "safety limit"
    wf = {"id": "W1", **main_wf}
    pick = run_code(nodes["Pick the broken step"]["parameters"]["jsCode"], json_=wf, refs={"Read the error": read["out"]})
    assert pick["out"][0]["body"]["model"] and "otodom" in pick["out"][0]["body"]["messages"][1]["content"], pick
    glm = {"choices": [{"message": {"content": json.dumps({"input": {"searchType": "sprzedaz", "location": "lodzkie/lodz/lodz/lodz", "maxItems": 40}, "change": "restored the location"})}}]}
    patch = run_code(nodes["Patch the step"]["parameters"]["jsCode"], json_=glm, refs={"Pick the broken step": pick["out"]})
    fixed = next(n for n in patch["out"][0]["workflow"]["nodes"] if n["name"] == "otodom · Łódź")
    assert json.loads(fixed["parameters"]["jsonBody"] if "jsonBody" in fixed["parameters"] else fixed["parameters"]["customBody"])["location"] == "lodzkie/lodz/lodz/lodz"
    assert set(patch["out"][0]["workflow"]) == {"name", "nodes", "connections", "settings"}


def test_zone_near(tmp):
    """A place without rent data gets the rent neighbourhood whose listings sit nearest."""
    import workflow
    raw = tmp / "near"
    raw.mkdir()
    at = lambda name, lat, lon, n: [{"propertyCode": f"{name}{i}", "municipality": "Bari", "neighborhood": name, "latitude": lat, "longitude": lon} for i in range(n)]
    (raw / "bari-sale-idealista.json").write_text(json.dumps(at("Alto", 41.10, 16.80, 3) + at("Basso", 41.20, 16.90, 3) + at("Chiesa Russa", 41.11, 16.81, 4)))
    zones = {"bari|Alto": {"city": "bari", "zone": "Alto", "rent_m2": 10}, "bari|Basso": {"city": "bari", "zone": "Basso", "rent_m2": 12}}
    assert workflow.zone_near(zones, raw) == {"bari": {"alto": "Alto", "basso": "Basso", "chiesa russa": "Alto"}}


def test_deploy(tmp, main_wf_dry):
    """deploy() against a fake n8n: ids, webhook ids and saved state survive an update; staging never touches the live record."""
    import workflow

    class Fake(workflow.N8n):
        store, calls, drop_static, n = {}, [], False, 0

        def __init__(self):
            self.base = "https://fake.n8n.cloud"

        def new_id(self, p):
            Fake.n += 1
            return f"{p}{Fake.n}"

        def get(self, wid):
            return json.loads(json.dumps(Fake.store[wid])) if wid in Fake.store else None

        def has_type(self, t):
            return False

        def call(self, method, path, **kw):
            Fake.calls.append((method, path, kw.get("json")))
            body, parts = kw.get("json"), path.strip("/").split("/")
            if path == "/credentials":
                return {"id": self.new_id("C"), "name": body["name"]}
            if path == "/workflows":
                wid = self.new_id("W")
                Fake.store[wid] = {**body, "id": wid, "staticData": None, "tags": []}
                return {"id": wid}
            if path == "/tags":
                return {"data": [{"id": "T1", "name": "inky"}]} if method == "GET" else {"id": "T1", "name": body["name"]}
            wf = Fake.store[parts[1]]
            if len(parts) == 3 and parts[2] == "tags":
                if method == "PUT":
                    wf["tags"] = body
                return wf["tags"]
            if len(parts) == 3 and parts[2] == "activate":
                wf["active"] = True
                return {}
            if method == "PUT":
                static = body.get("staticData", None if Fake.drop_static else wf["staticData"])
                Fake.store[parts[1]] = {**wf, **body, "staticData": static}
                return {}
            raise AssertionError(path)

    real = (workflow.N8n, workflow.STATE_DIR, workflow.DATA, workflow.actor_schemas, dict(os.environ))
    workflow.N8n, workflow.STATE_DIR, workflow.DATA, workflow.actor_schemas = Fake, tmp / "state", tmp, lambda: {}
    (tmp / "state").mkdir()
    os.environ.update({k: "fake" for k in ("N8N_BASE_URL", "N8N_API_KEY", "APIFY_TOKEN", "TELEGRAM_BOT_TOKEN", "OPENROUTER_API_KEY")})
    os.environ.update({"TELEGRAM_CHAT_ID": "42", "N8N_GMAIL_CREDENTIAL_ID": "G1"})
    try:
        said = []
        first = workflow.deploy(lambda text, sub=None: said.append((text, sub)))
        live = json.loads((tmp / "state" / "n8n.json").read_text())
        assert first["main"] == live["main"] and first["best_url"] == f"https://fake.n8n.cloud/webhook/{live['best_path']}"
        assert Fake.store[live["main"]]["settings"]["errorWorkflow"] == live["repair"] and Fake.store[live["main"]]["active"]
        assert Fake.store[live["repair"]]["active"] and Fake.store[live["main"]]["tags"] == [{"id": "T1"}]
        assert [t for t, _ in said][-2:] == ["Published the main workflow", "Published the repair workflow"], said
        assert all(len(t) <= 40 and (s is None or len(s) <= 90) for t, s in said), said
        http = next(n for n in Fake.store[live["main"]]["nodes"] if n["name"] == "otodom · Łódź")["parameters"]
        q = {p["name"]: p["value"] for p in http["queryParameters"]["parameters"]}
        assert q == {"maxTotalChargeUsd": "0.3", "timeout": "240", "memory": "512"} and json.loads(http["jsonBody"])["maxItems"] == 60, q

        # The live workflow has been running: saved state, and a Telegram question waiting on the Ask node.
        m = Fake.store[live["main"]]
        m["staticData"] = {"global": {"seen": {"idealista:1": 1}}}
        before = {n["name"]: (n["id"], n.get("webhookId")) for n in m["nodes"]}
        Fake.calls.clear()
        workflow.deploy(lambda *a: None)
        m = Fake.store[live["main"]]
        after = {n["name"]: (n["id"], n.get("webhookId")) for n in m["nodes"]}
        assert after == before and m["staticData"] == {"global": {"seen": {"idealista:1": 1}}}
        assert not any(b and "staticData" in b for _, _, b in Fake.calls), "static data is left to n8n"
        assert not any(p == "/credentials" for _, p, _ in Fake.calls) and json.loads((tmp / "state" / "n8n.json").read_text())["best_path"] == live["best_path"]

        # An n8n that dropped static data on update: deploy puts it back.
        Fake.drop_static = True
        workflow.deploy(lambda *a: None)
        assert Fake.store[live["main"]]["staticData"] == {"global": {"seen": {"idealista:1": 1}}}
        Fake.drop_static = False

        # Staging: its own record and workflows, the live credentials, nothing that messages or runs on a clock.
        record = (tmp / "state" / "n8n.json").read_bytes()
        st = workflow.deploy(lambda *a: None, staging=True)
        assert (tmp / "state" / "n8n.json").read_bytes() == record and st["main"] not in (live["main"], live["repair"])
        staged = json.loads((tmp / "state" / "n8n-staging.json").read_text())
        assert staged["credentials"] == live["credentials"] and staged["best_path"] != live["best_path"]
        sm, sr = Fake.store[st["main"]], Fake.store[st["repair"]]
        assert sm["name"] == "Inky · staging main" and sr["name"] == "Inky · staging repair" and sm["settings"]["errorWorkflow"] == st["repair"]
        off = {n["name"] for n in sm["nodes"] + sr["nodes"] if n.get("disabled")}
        assert off == {"Every 15 min", "Every day 08:00", "Ask me on Telegram", "Gmail draft to the agent", "Send the digest",
                       "Tell me it broke", "Tell me it's fixed", "Run it again"}, off
        assert next(n for n in sr["nodes"] if n["name"] == "Run it again")["parameters"]["workflowId"]["value"] == st["main"]
    finally:
        workflow.N8n, workflow.STATE_DIR, workflow.DATA, workflow.actor_schemas = real[:4]
        os.environ.clear()
        os.environ.update(real[4])


def test_share(tmp):
    """share/export.py leaves only placeholders and refuses to write secrets; share/import.py fills the placeholders."""
    import importlib.util
    import workflow

    def load(rel):
        spec = importlib.util.spec_from_file_location(rel.replace("/", "_")[:-3], HERE / rel)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    export, imp = load("share/export.py"), load("share/import.py")
    real = (workflow.DATA, workflow.STATE_DIR, workflow.actor_schemas, os.environ.get("APIFY_TOKEN"))
    workflow.DATA, workflow.STATE_DIR, workflow.actor_schemas = tmp, tmp / "state", lambda: {}
    try:
        rules, main_wf, repair_wf = export.build()
        text = json.dumps([main_wf, repair_wf], ensure_ascii=False)
        assert all(p in text for p in ("INKY_APIFY_CREDENTIAL", "INKY_TELEGRAM_CHAT_ID", "INKY_BEST_PATH", "INKY_MAIN_WORKFLOW_ID"))
        os.environ["APIFY_TOKEN"] = "apify_api_notreal123"
        assert export.leaks(text) == [] and export.leaks(text + "apify_api_notreal123") == ["apif…"]
        values = {p: "X1" for p in ("INKY_APIFY_CREDENTIAL", "INKY_TELEGRAM_CREDENTIAL", "INKY_N8N_CREDENTIAL", "INKY_OPENROUTER_CREDENTIAL",
                                    "INKY_GMAIL_CREDENTIAL", "INKY_TELEGRAM_CHAT_ID", "INKY_BEST_PATH", "INKY_MAIN_WORKFLOW_ID")}
        filled = json.dumps([imp.fill(main_wf, values), imp.fill(repair_wf, values)])
        assert "INKY_" not in filled.replace("INKY_REPAIR_WORKFLOW_ID", ""), "a placeholder is left"
        bundle = tmp / "bundle"
        bundle.mkdir()
        (bundle / "inky-main.json").write_text(json.dumps(main_wf))
        (bundle / "inky-repair.json").write_text(json.dumps(repair_wf))
        env = {k: "x" for k in imp.NEEDED}
        assert imp.install(bundle, env, dry_run=True, say=lambda *a: None) == {}
    finally:
        workflow.DATA, workflow.STATE_DIR, workflow.actor_schemas = real[:3]
        os.environ.pop("APIFY_TOKEN", None) if real[3] is None else os.environ.update(APIFY_TOKEN=real[3])


def main():
    if "--fixtures-only" in sys.argv:
        fixtures(Path(os.environ.get("INKY_DATA", "data")) / "raw")
        return
    tmp = Path(tempfile.mkdtemp())
    env = {**os.environ, "INKY_DATA": str(tmp)}
    fixtures(tmp / "raw")
    for script in (["derive.py", "--offline"], ["workflow.py", "--dry-run"], ["workflow.py", "--dry-run", "--staging"]):
        subprocess.run([sys.executable, *script], cwd=HERE, env=env, check=True, stdout=subprocess.DEVNULL)

    research = json.loads((tmp / "research.json").read_text())
    assert research["listings_read"] == 720, research["listings_read"]
    assert [v["matches"] for v in research["versions"]][0] >= research["versions"][-1]["matches"] > 0, research["versions"]

    main_wf = json.loads((tmp / "n8n-main.json").read_text())
    repair = json.loads((tmp / "n8n-repair.json").read_text())
    for wf in (main_wf, repair, json.loads((tmp / "n8n-staging-main.json").read_text())):
        check_connections(wf)
    nodes = {n["name"]: n for n in main_wf["nodes"] + repair["nodes"]}

    sale = [i for f in sorted((tmp / "raw").glob("*-sale-*.json")) for i in json.loads(f.read_text())] + tecnocasa(random.Random(3))
    r1, r3 = test_score(nodes, sale, tmp)
    test_main_nodes(nodes, r1)
    test_wiring(main_wf)
    test_repair(nodes, main_wf, repair, r3)
    test_zone_near(tmp)
    test_deploy(tmp, main_wf)
    test_share(tmp)

    print(f"ok: {research['listings_read']} fixture listings, rules v1-v3 "
          f"{' -> '.join(str(v['matches']) for v in research['versions'])} matches, n8n Code nodes run (score, quiet hours, drift, "
          f"daily cap, digest, best now), repair patches the right step, deploy keeps ids and saved state, staging stays quiet, share bundle has no secrets")


if __name__ == "__main__":
    main()
