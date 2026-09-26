"""Turn the scraped listings into rules. GLM-5.3 proposes them, the data tests them, three rounds.

    uv run python derive.py            # uses OpenRouter (GLM-5.3)
    uv run python derive.py --offline  # no LLM: fixed rules, for testing the pipeline

Reads data/raw/*.json and plan.json. Writes data/zones.json, data/costs.json, data/rules.json
and data/research.json (the numbers the Research screen and the video use).
"""
import argparse
import json
import os
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

DATA = Path(os.environ.get("INKY_DATA", "data"))

# Yearly running costs and one-off buying costs as a share of price, and tax on rent.
# Rough, documented estimates for a non-resident private buyer; price_trend comes from Eurostat.
COSTS = {
    "PT": {"buy_costs": 0.08, "upkeep": 0.01, "vacancy": 0.08, "management": 0.09, "rent_tax": 0.25},   # IMT + stamp duty; 25% flat rent tax
    "IT": {"buy_costs": 0.07, "upkeep": 0.012, "vacancy": 0.08, "management": 0.09, "rent_tax": 0.21},  # registro 9% on cadastral value; cedolare secca 21%
    "PL": {"buy_costs": 0.035, "upkeep": 0.008, "vacancy": 0.08, "management": 0.09, "rent_tax": 0.085},  # PCC 2% + notary; ryczałt 8.5%
}
FIELDS = {
    "price_eur": "asking price in euro",
    "size_m2": "floor area",
    "bedrooms": "number of bedrooms",
    "gross_yield": "yearly rent / price, percent",
    "net_yield": "yield after agency, vacancy, upkeep, rent tax and buying costs, percent",
    "price_vs_zone": "price per m² divided by the neighbourhood median (1.0 = average)",
    "zone_rent_listings": "rental listings in the neighbourhood (how easy it is to find tenants)",
    "price_trend": "house prices in that country, change over the last year, percent (Eurostat)",
    "currency": "EUR or PLN",
    "city": "porto, bari or lodz",
}
OPS = ["<=", ">=", "==", "!=", "in", "not_in"]


def node(*args, stdin=None):
    r = subprocess.run(["node", "inky.js", *args], input=stdin, capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def market_facts():
    """PLN per EUR (ECB) and last year's house price change per country (Eurostat)."""
    try:
        ecb = httpx.get("https://data-api.ecb.europa.eu/service/data/EXR/D.PLN.EUR.SP00.A",
                        params={"lastNObservations": 1, "format": "jsondata"}, timeout=20).json()
        pln = list(list(ecb["dataSets"][0]["series"].values())[0]["observations"].values())[0][0]
        es = httpx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hpi_q",
                       params=[("geo", g) for g in COSTS] + [("purchase", "TOTAL"), ("unit", "RCH_A"), ("lastTimePeriod", 1)],
                       timeout=20).json()
        period = list(es["dimension"]["time"]["category"]["index"])[0]
        trend = {g: es["value"][str(i)] for g, i in es["dimension"]["geo"]["category"]["index"].items()}
        return pln, trend, period
    except Exception as e:  # ponytail: offline fallback, the 2026-Q1 values
        print(f"market facts offline ({type(e).__name__}), using 2026-Q1 values")
        return 4.3718, {"PT": 17.8, "IT": 5.2, "PL": 5.9}, "2026-Q1"


def zone_table(listings):
    groups = defaultdict(lambda: {"sale": [], "rent": []})
    for l in listings:
        if l["op"] in ("sale", "rent"):
            groups[(l["city"], l["zone"])][l["op"]].append(l["price_eur"] / l["size_m2"])
    zones = {}
    for (city, zone), g in groups.items():
        if len(g["sale"]) >= 5 and len(g["rent"]) >= 3:
            zones[f"{city}|{zone}"] = {
                "city": city, "zone": zone, "n_sale": len(g["sale"]), "n_rent": len(g["rent"]),
                "sale_m2": round(statistics.median(g["sale"])), "rent_m2": round(statistics.median(g["rent"]), 2),
            }
    return zones


def evaluate(sale, rules, zones, costs):
    scored = node("score", stdin=json.dumps({"listings": sale, "rules": rules, "zones": zones, "costs": costs}))
    known = [s for s in scored if "net_yield" in s]
    seen, matches = set(), []
    for s in sorted((s for s in scored if s["match"]), key=lambda s: -s["net_yield"]):
        key = (s["city"], s["zone"], s["price_eur"], s["size_m2"])  # the same flat listed twice
        if key not in seen:
            seen.add(key)
            matches.append(s)
    removed = {r["id"]: sum(1 for s in known if r["id"] in s["failed"]) for r in rules}
    near = [s for s in known if len(s["failed"]) == 1][:8]
    return scored, known, matches, removed, near


def valid(rules):
    ids = set()
    for r in rules:
        assert r["field"] in FIELDS, f"unknown field {r['field']}"
        assert r["op"] in OPS, f"unknown op {r['op']}"
        assert r["id"] not in ids, f"duplicate id {r['id']}"
        ids.add(r["id"])
        if r["op"] in ("in", "not_in"):
            assert isinstance(r["value"], list), f"{r['id']} needs a list"
    return rules


def glm(messages):
    r = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json={"model": os.environ.get("OPENROUTER_MODEL", "z-ai/glm-5.3"), "messages": messages,
              "response_format": {"type": "json_object"}, "usage": {"include": True}},
        timeout=180,
    )
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"], (d.get("usage") or {}).get("cost", 0)


def propose(history, context, offline):
    """One round of rules. Offline: tighten a fixed rule set so the pipeline can run without a key."""
    if offline:
        y = [4.0, 5.0, 5.5][len(history)]
        return valid([
            {"id": "R1", "field": "price_eur", "op": "<=", "value": context["plan"]["budget_eur"], "why": "Fits the cash budget."},
            {"id": "R2", "field": "bedrooms", "op": "in", "value": [1, 2], "why": "1 or 2 bedrooms rent fastest to locals."},
            {"id": "R3", "field": "net_yield", "op": ">=", "value": y, "why": f"Earns at least {y}% a year after every cost."},
            {"id": "R4", "field": "zone_rent_listings", "op": ">=", "value": 10, "why": "Enough rentals nearby to find tenants."},
            {"id": "R5", "field": "price_trend", "op": ">=", "value": 3, "why": "Prices in the country rose over the last year."},
            {"id": "R6", "field": "price_vs_zone", "op": "<=", "value": 1.1, "why": "Not overpriced for its neighbourhood."},
        ]), 0.0
    messages = [
        {"role": "system", "content": "You are the research step of Inky, an agent that turns a vague goal into typed rules. "
                                      "Answer with one JSON object: {\"rules\": [{\"id\", \"field\", \"op\", \"value\", \"why\"}], \"note\": string}. "
                                      "Number the rules R1, R2, R3 and so on. Use only the listed fields and ops. 'why' is one plain sentence for a non-expert."},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]
    for h in history:
        messages += [{"role": "assistant", "content": json.dumps({"rules": h["rules"]})},
                     {"role": "user", "content": json.dumps(h["feedback"], ensure_ascii=False)}]
    cost = 0.0
    for attempt in range(2):
        text, c = glm(messages)
        cost += c or 0
        try:
            return valid(json.loads(text[text.find("{"):text.rfind("}") + 1])["rules"]), cost
        except (ValueError, KeyError, AssertionError, TypeError) as e:
            messages += [{"role": "assistant", "content": text}, {"role": "user", "content": f"Invalid: {e}. Answer again with valid JSON."}]
    raise RuntimeError("GLM did not return valid rules twice")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()
    load_dotenv()

    pln, trend, period = market_facts()
    costs = {c: {**v, "price_trend": trend[c]} for c, v in COSTS.items()}
    raw = sorted(str(f) for f in (DATA / "raw").glob("*-*-*.json"))
    listings = node("normalize", str(pln), *raw)
    zones = zone_table(listings)
    sale = [l for l in listings if l["op"] == "sale"]
    plan = json.loads(Path("plan.json").read_text())
    print(f"{len(listings)} listings ({len(sale)} for sale), {len(zones)} neighbourhoods with rent data")

    top = sorted(zones.values(), key=lambda z: -z["rent_m2"] * 12 / z["sale_m2"])[:40]
    context = {
        "plan": plan, "fields": FIELDS, "ops": OPS, "costs_by_country": costs,
        "listings_for_sale": len(sale), "neighbourhoods": top,
        "ask": "Propose 5-7 rules that pick the few best flats for this plan. Rules decide what is good enough; Inky ranks the matches by net yield afterwards, so aim for 15-60 matches spread over at least 2 cities and 4 neighbourhoods so the buyer can compare places. Respect the plan: do not add rules the plan leaves open (like currency).",
    }
    history, total_cost = [], 0.0
    for v in range(1, 4):
        rules, cost = propose(history, context, args.offline)
        total_cost += cost
        _, known, matches, removed, near = evaluate(sale, rules, zones, costs)
        zones_passed = sorted({(m["city"], m["zone"]) for m in matches})
        print(f"v{v}: {len(matches)} matches in {len(zones_passed)} neighbourhoods  " + "  ".join(f"{k} -{n}" for k, n in removed.items()))
        history.append({"v": v, "rules": rules, "matches": len(matches), "zones": len(zones_passed), "feedback": {
            "result": f"v{v} passed {len(matches)} of {len(known)} listings with rent data, in {len(zones_passed)} neighbourhoods.",
            "removed_by_rule": removed,
            "matches_by_city": dict(Counter(m["city"] for m in matches)),
            "matches_by_neighbourhood": dict(Counter(f'{m["city"]}: {m["zone"]}' for m in matches).most_common(10)),
            "near_misses": [{k: n[k] for k in ("city", "zone", "price_eur", "bedrooms", "net_yield", "price_vs_zone", "failed")} for n in near],
            "ask": "Revise for the next version: keep rules that work, fix ones that remove too much or too little. Aim for 15-60 matches over at least 2 cities and 4 neighbourhoods. Change one or two thresholds at a time.",
        }})

    final = history[-1]["rules"]
    _, known, matches, _, _ = evaluate(sale, final, zones, costs)
    by_zone = defaultdict(list)
    for m in matches:
        by_zone[(m["city"], m["zone"])].append(m)
    top_zones = sorted(({"city": c, "zone": z, "matches": len(ms), "net_yield": round(statistics.median(m["net_yield"] for m in ms), 2),
                         "price_trend": costs[ms[0]["country"]]["price_trend"], "rent_listings": ms[0]["zone_rent_listings"]}
                        for (c, z), ms in by_zone.items()), key=lambda t: -t["net_yield"])

    for name, obj in [("zones", zones), ("costs", costs), ("rules", {"versions": [{k: h[k] for k in ("v", "rules", "matches", "zones")} for h in history], "final": final})]:
        (DATA / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    (DATA / "research.json").write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "listings_read": len(listings), "for_sale": len(sale), "for_rent": len(listings) - len(sale),
        "neighbourhoods": len(zones), "with_rent_data": len(known), "pln_per_eur": pln, "price_trend_period": period,
        "versions": [{"v": h["v"], "matches": h["matches"], "zones": h["zones"]} for h in history],
        "top_zones": top_zones[:3],
        "by_city": {c: {"matches": sum(1 for m in matches if m["city"] == c),
                        "best_zone": next((t for t in top_zones if t["city"] == c), None)} for c in plan["cities"]}, "matches": [{k: m.get(k) for k in ("title", "city", "zone", "price_eur", "size_m2", "bedrooms", "net_yield", "url")} for m in matches[:200]],
        "llm_cost_usd": round(total_cost, 4), "llm_calls": 0 if args.offline else len(history),
    }, ensure_ascii=False, indent=1))
    print(f"final rules: {len(final)}, {len(matches)} matches. GLM cost ${total_cost:.4f}. Wrote {DATA}/rules.json, {DATA}/research.json")


if __name__ == "__main__":
    main()
