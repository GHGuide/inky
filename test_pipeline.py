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
const { code, input, json, refs, statics } = JSON.parse(fs.readFileSync(0, 'utf8'));
const staticData = statics || {};
const $ = (name) => ({ first: () => ({ json: refs[name][0] }), itemMatching: (i) => ({ json: refs[name][i] }) });
const fn = new Function('$input', '$json', '$', '$getWorkflowStaticData', code);
try {
  const out = fn({ all: () => input.map((j) => ({ json: j })) }, json, $, () => staticData);
  process.stdout.write(JSON.stringify({ out: out.map((o) => o.json), statics: staticData }));
} catch (e) {
  process.stdout.write(JSON.stringify({ error: e.message, statics: staticData }));
}
"""


def run_code(code, input=(), json_=None, refs=None, statics=None):
    r = subprocess.run(["node", "-e", HARNESS], input=json.dumps({"code": code, "input": list(input), "json": json_ or {}, "refs": refs or {}, "statics": statics}),
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def main():
    if "--fixtures-only" in sys.argv:
        fixtures(Path(os.environ.get("INKY_DATA", "data")) / "raw")
        return
    tmp = Path(tempfile.mkdtemp())
    env = {**os.environ, "INKY_DATA": str(tmp)}
    fixtures(tmp / "raw")
    for script in (["derive.py", "--offline"], ["workflow.py", "--dry-run"]):
        subprocess.run([sys.executable, *script], cwd=HERE, env=env, check=True)

    research = json.loads((tmp / "research.json").read_text())
    assert research["listings_read"] == 720, research["listings_read"]
    assert [v["matches"] for v in research["versions"]][0] >= research["versions"][-1]["matches"] > 0, research["versions"]

    main_wf = json.loads((tmp / "n8n-main.json").read_text())
    repair = json.loads((tmp / "n8n-repair.json").read_text())
    for wf in (main_wf, repair):
        names = [n["name"] for n in wf["nodes"]]
        assert len(names) == len(set(names)), "duplicate node names"
        for src, out in wf["connections"].items():
            assert src in names and all(c["node"] in names for c in out["main"][0]), src
    nodes = {n["name"]: n for n in main_wf["nodes"] + repair["nodes"]}

    # The Score node: first run finds matches, the same items again find nothing new, a missing source throws.
    sale = [i for f in sorted((tmp / "raw").glob("*-sale-*.json")) for i in json.loads(f.read_text())]
    score = nodes["Score · rules"]["parameters"]["jsCode"]
    r1 = run_code(score, sale)
    assert "error" not in r1, r1.get("error")
    assert 1 <= len(r1["out"]) <= 3 and all(m["match"] for m in r1["out"]), len(r1["out"])
    assert "Gmail draft" in r1["out"][0]["telegram_text"] and r1["out"][0]["email_body"], r1["out"][0]["telegram_text"]
    r2 = run_code(score, sale, statics=r1["statics"])
    assert r2["out"] == [], "dedupe failed"
    r3 = run_code(score, [i for i in sale if "propertyUrl" not in i])
    assert r3.get("error") == "Step otodom · Łódź returned 0 homes", r3

    # Only approved matches become Gmail drafts.
    keep = run_code(nodes["Keep approved"]["parameters"]["jsCode"], [{"data": {"approved": True}}, {"data": {"approved": False}}],
                    refs={"Score · rules": r1["out"][:2]})
    assert len(keep["out"]) == 1

    # Repair: read the error, pick the broken Apify step, apply GLM's corrected input.
    err = {"execution": {"error": {"message": r3["error"]}, "lastNodeExecuted": "Score · rules"}, "workflow": {"id": "W1", "name": "Inky"}}
    read = run_code(nodes["Read the error"]["parameters"]["jsCode"], json_=err)
    assert read["out"] == [{"workflowId": "W1", "step": "otodom · Łódź", "error": r3["error"]}], read
    limited = run_code(nodes["Read the error"]["parameters"]["jsCode"], json_=err, statics=read["statics"] | {"fixes": [9e15]})
    assert limited["out"] == [], "safety limit"
    wf = {"id": "W1", **main_wf}
    pick = run_code(nodes["Pick the broken step"]["parameters"]["jsCode"], json_=wf, refs={"Read the error": read["out"]})
    assert pick["out"][0]["body"]["model"] and "otodom" in pick["out"][0]["body"]["messages"][1]["content"], pick
    glm = {"choices": [{"message": {"content": json.dumps({"input": {"searchType": "sprzedaz", "location": "lodzkie/lodz/lodz/lodz", "maxItems": 40}, "change": "restored the location"})}}]}
    patch = run_code(nodes["Patch the step"]["parameters"]["jsCode"], json_=glm, refs={"Pick the broken step": pick["out"]})
    fixed = next(n for n in patch["out"][0]["workflow"]["nodes"] if n["name"] == "otodom · Łódź")
    assert json.loads(fixed["parameters"]["customBody"])["location"] == "lodzkie/lodz/lodz/lodz"
    assert set(patch["out"][0]["workflow"]) == {"name", "nodes", "connections", "settings"}

    print(f"ok: {research['listings_read']} fixture listings, rules v1-v3 "
          f"{' -> '.join(str(v['matches']) for v in research['versions'])} matches, n8n Code nodes run, repair patches the right step")


if __name__ == "__main__":
    main()
