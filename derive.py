"""Turn the scraped listings into rules. GLM-5.3 proposes them, the data tests them, three rounds.

    uv run python derive.py            # uses OpenRouter (GLM-5.3)
    uv run python derive.py --offline  # no LLM: fixed rules, for testing the pipeline
    uv run python derive.py --rescore  # no LLM: re-evaluate the saved final rules, rewrite research.json only (same "at")

The same work is callable from Python: derive.run(progress, offline=False, data_dir=None, rescore=False, plan=None).

Reads data/raw/*.json and plan.json. Writes data/zones.json, data/costs.json, data/rules.json
and data/research.json (the numbers the Research screen and the video use), keeping the previous
version of each as <name>.bak.json.
"""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
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


ONLY_RULES = 'Do not repeat the input. Answer with one JSON object {"rules": [...], "note": "..."} and nothing else.\n'


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
        {"role": "user", "content": ONLY_RULES + "The plan and the data:\n" + json.dumps(context, ensure_ascii=False)},
    ]
    for h in history:
        messages += [{"role": "assistant", "content": json.dumps({"rules": h["rules"]})},
                     {"role": "user", "content": ONLY_RULES + f"What v{h['v']} let through:\n" + json.dumps(h["feedback"], ensure_ascii=False)}]
    cost = 0.0
    for attempt in range(3):  # seen live: GLM-5.3 now and then echoes the input or answers {"error": ...}
        text, c = glm(messages)
        cost += c or 0
        try:
            return valid(json.loads(text[text.find("{"):text.rfind("}") + 1])["rules"]), cost
        except (ValueError, KeyError, AssertionError, TypeError) as e:
            error = f"{type(e).__name__}: {e}"
            print(f"GLM answer {attempt + 1} invalid ({error}): {text[:300]!r}", file=sys.stderr)
            messages += [{"role": "assistant", "content": text[:500]},
                         {"role": "user", "content": f"That was not valid ({error}). " + ONLY_RULES}]
    raise RuntimeError(f"GLM did not return valid rules in 3 tries ({error})")


ZONE_KEYS = ("rent_m2", "sale_m2", "n_rent")
MATCH_KEYS = ("title", "city", "zone", "country", "source", "currency", "price_eur", "size_m2", "bedrooms", "rent_month",
              "gross_yield", "net_yield", "zone_rent_listings", "price_vs_zone", "price_trend", "url")


def rule_text(r):
    return f"{r['id']} {r['field']} {r['op']} {r['value']}"


def verdict(matches, known, rules):
    """What to change next, from the data, so GLM does not overshoot (seen live: 664 homes, then 0)."""
    n = len(matches)
    if n > 60:
        # the highest 'yields' are wrecks, garages and typos far below the neighbourhood price: aim the tip at the rest (seen live: 13%)
        sane = sorted((m["net_yield"] for m in matches if m["price_vs_zone"] >= 0.7), reverse=True)
        floor = any(r["field"] == "price_vs_zone" and r["op"] == ">=" for r in rules)
        tip = f"about {sane[59]}% leaves 60, {sane[14]}% leaves 15" if len(sane) > 60 else "raise it a little"
        return (f"Far too many ({n}). Raise the net_yield floor: {tip}."
                + ("" if floor else " Also add price_vs_zone >= 0.7: far below the neighbourhood price means a wreck or a typo, and those top the yields.")
                + " Keep the other rules.")
    if n < 15:
        near = Counter(s["failed"][0] for s in known if len(s["failed"]) == 1)
        if not near:
            return f"Too few ({n}). Loosen the rule that removes the most."
        rid, k = near.most_common(1)[0]
        return f"Too few ({n}). {k:,} listings fail only {rule_text(next(r for r in rules if r['id'] == rid))}: loosen that one a little."
    return "In range: change little, if anything."


def best_by_city(known, rules, cities, matches):
    """Per city: the best net yield among flats that fit only the budget and bedroom rules, and why nothing passes if nothing does.
    Also kept: the price-vs-neighbourhood rules and a floor of half the neighbourhood's price per m², else the "best" is a wreck,
    a garage or a typo (a €1,121 flat at 852%)."""
    basic = {r["id"] for r in rules if r["field"] in ("price_eur", "bedrooms", "price_vs_zone")}
    out = {}
    for city in cities:
        pool = [s for s in known if s["city"] == city and s["price_vs_zone"] >= 0.5 and not basic & set(s["failed"])]
        passed = [m for m in matches if m["city"] == city]
        n = len(passed)
        if not pool:
            out[city] = {"candidates": 0, "matches": n, "reason": None if n else "No flat in budget with the right bedrooms has rent data nearby."}
            continue
        best = max(passed or pool, key=lambda s: s["net_yield"])  # a city with matches shows its best passing home
        reason = None
        if not n:
            fails = Counter(f for s in pool for f in s["failed"] if f not in basic)
            rid, blocked = fails.most_common(1)[0]
            r = next(r for r in rules if r["id"] == rid)
            reason = (f"Of {len(pool):,} flats in budget with the right bedrooms, {blocked:,} fail {rule_text(r)}. "
                      f"The best earns {best['net_yield']}% a year after costs, in {best['zone']}.")
        out[city] = {"candidates": len(pool), "matches": n, **{k: best.get(k) for k in MATCH_KEYS}, "failed": best.get("failed", []), "reason": reason}
    return out


# E6: per site, the raw field with the date a listing went up, and a field that says when the scrape saw it.
# idealista gives neither for homes for sale (firstActivationDate shows up on some rentals only).
DATED = {"otodom": ("dateCreated", "scrapedAt"), "immobiliare": ("creationDate", "lastModified")}


def stamp(v):
    """ISO text or unix seconds -> aware datetime."""
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, timezone.utc)
    t = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def speed(raw, cities):
    """How fresh the homes for sale are, per city, from the dates in the raw items: no scrape, no model.
    A listing's age runs from its date to the newest 'seen' time in the same file, so it never runs past the scrape."""
    out = {}
    for city in cities:
        files = {Path(f).stem.split("-", 2)[2]: Path(f) for f in raw if Path(f).name.startswith(f"{city}-sale-")}
        ages, used, read_at = [], [], None
        for source, f in sorted(files.items()):
            if source not in DATED:
                continue
            made, seen = DATED[source]
            items = {str(i.get("id")): i for i in json.loads(f.read_text())}.values()  # the same listing twice counts once
            ref = max((stamp(i[seen]) for i in items if i.get(seen)), default=None)
            got = [(ref - stamp(i[made])).total_seconds() / 86400 for i in items if ref and i.get(made)]
            if got:
                ages, used, read_at = ages + got, used + [source], max(read_at or ref, ref)
        if not ages:
            out[city] = {"listings": 0, "reason": f"{' and '.join(sorted(files)) or 'no site'} {'give' if len(files) > 1 else 'gives'} no listing dates for homes for sale"}
            continue
        out[city] = {"sources": used, "listings": len(ages), "median_age_days": round(statistics.median(ages), 1),
                     "under_7_days_pct": round(100 * sum(a < 7 for a in ages) / len(ages), 1), "new_24h": sum(a < 1 for a in ages),
                     "read_at": read_at.isoformat(timespec="seconds")}
    return {"by_city": out, "note": "Age: from the date the site gives a listing to when Inky read it. "
                                    "Counted on the homes for sale Inky read, not on every listing in the city."}


def run(progress=None, offline=False, data_dir=None, rescore=False, plan=None):
    """The research step. progress(event) gets {"type": "step", "text", "sub"?} and {"type": "version", "v", "matches", "zones", "rules"}.
    rescore=True: no GLM and no new market facts, re-test the saved versions and rewrite research.json only (rules.json stays).
    plan: the plan object, else plan.json. Returns (research, rules_doc), both as written."""
    data, emit = Path(data_dir or DATA), progress or (lambda e: None)
    step = lambda text, sub=None: emit({"type": "step", "text": text, **({"sub": sub} if sub else {})})
    plan = plan or json.loads(Path("plan.json").read_text())
    raw = sorted(str(f) for f in (data / "raw").glob("*-*-*.json"))
    if not raw:
        raise RuntimeError(f"no listings in {data / 'raw'}: run the scrape (research.py) first")
    if rescore:
        old, doc = (json.loads((data / f).read_text()) for f in ("research.json", "rules.json"))
        pln, period, costs = old["pln_per_eur"], old["price_trend_period"], json.loads((data / "costs.json").read_text())
    else:
        pln, trend, period = market_facts()
        costs = {c: {**v, "price_trend": trend[c]} for c, v in COSTS.items()}
        step(f"Checked the exchange rate (ECB) and house prices (Eurostat {period})",
             f"1 EUR = {pln:.2f} PLN · prices " + ", ".join(f"{c} {t:+.1f}%" for c, t in trend.items()))
    listings = node("normalize", str(pln), *raw)
    zones = json.loads((data / "zones.json").read_text()) if rescore else zone_table(listings)
    sale = [l for l in listings if l["op"] == "sale"]
    step(f"Read {len(listings):,} listings", f"{len(sale):,} for sale, {len(listings) - len(sale):,} for rent")
    step(f"Matched rent to {len(zones)} neighbourhoods", "median rent and price per m², where there are 3+ rentals and 5+ sales")

    def report(v, rules):
        """Test one version on the listings and tell the caller what it let through."""
        _, known, matches, removed, near = evaluate(sale, rules, zones, costs)
        zones_passed = sorted({(m["city"], m["zone"]) for m in matches})
        worst = max(removed, key=removed.get) if removed else None
        step(f"{len(matches)} homes in {len(zones_passed)} neighbourhoods pass",
             f"{len(rules)} rules" + (f" · {rule_text(next(r for r in rules if r['id'] == worst))} removes {removed[worst]:,}" if worst else ""))
        emit({"type": "version", "v": v, "matches": len(matches), "zones": len(zones_passed), "rules": rules, "removed": removed})
        return known, matches, removed, near, zones_passed

    if rescore:
        history, total_cost, calls = doc["versions"], old.get("llm_cost_usd", 0), old.get("llm_calls", 0)
        for h in history:
            step(f"Rules v{h['v']}, as GLM-5.3 proposed them", "saved answer, no new GLM call")
            report(h["v"], h["rules"])
    else:
        top = sorted(zones.values(), key=lambda z: -z["rent_m2"] * 12 / z["sale_m2"])[:40]
        context = {
            "plan": plan, "fields": FIELDS, "ops": OPS, "costs_by_country": costs,
            "listings_for_sale": len(sale), "neighbourhoods": top,
            "ask": "Propose 5-7 rules that pick the few best flats for this plan. Rules decide what is good enough; Inky ranks the matches by net yield afterwards, so aim for 15-60 matches spread over at least 2 cities and 4 neighbourhoods so the buyer can compare places. Respect the plan: do not add rules the plan leaves open (like currency).",
        }
        history, total_cost = [], 0.0
        for v in range(1, 4):
            step(f"Took the offline rules v{v}" if offline else f"Asked GLM-5.3 for rules v{v}",
                 "from your plan and the neighbourhood table" if v == 1 else f"with what v{v - 1} let through")
            rules, cost = propose(history, context, offline)
            total_cost += cost
            known, matches, removed, near, zones_passed = report(v, rules)
            cities = len({m["city"] for m in matches})
            history.append({"v": v, "rules": rules, "matches": len(matches), "zones": len(zones_passed), "cities": cities, "feedback": {
                "result": f"v{v} passed {len(matches)} of {len(known)} listings with rent data, in {len(zones_passed)} neighbourhoods.",
                "verdict": verdict(matches, known, rules) + (" Only one city passes: the buyer wants to compare at least 2." if cities < 2 else ""),
                "removed_by_rule": removed,
                "matches_by_city": dict(Counter(m["city"] for m in matches)),
                "matches_by_neighbourhood": dict(Counter(f'{m["city"]}: {m["zone"]}' for m in matches).most_common(10)),
                "near_misses": [{k: n[k] for k in ("city", "zone", "price_eur", "bedrooms", "net_yield", "price_vs_zone", "failed")} for n in near],
                "ask": "Revise for the next version: keep rules that work, fix ones that remove too much or too little. Aim for 15-60 matches over at least 2 cities and 4 neighbourhoods. Change one or two thresholds at a time.",
            }})
        calls = 0 if offline else len(history)
        # ponytail: naive fit score; GLM sometimes loosens instead of tightening, so the last version is not always the best
        fit = lambda h: max(15 / h["matches"], h["matches"] / 60, 1) * (2 if h["cities"] < 2 else 1) * (1.5 if h["zones"] < 4 else 1) if h["matches"] else 1e9
        best = min(reversed(history), key=fit)  # 1 = 15-60 homes in 2+ cities and 4+ neighbourhoods; 0 homes is the worst
        if best is not history[-1]:
            step(f"Kept rules v{best['v']}", f"closest to 15-60 homes over 2+ cities: {best['matches']} homes in {best['zones']} neighbourhoods")
        doc = {"versions": [{k: h[k] for k in ("v", "rules", "matches", "zones")} for h in history], "final": best["rules"], "final_v": best["v"]}

    final = doc["final"]
    _, known, matches, _, _ = evaluate(sale, final, zones, costs)
    by_zone = defaultdict(list)
    for m in matches:
        by_zone[(m["city"], m["zone"])].append(m)
    top_zones = sorted(({"city": c, "zone": z, "matches": len(ms), "net_yield": round(statistics.median(m["net_yield"] for m in ms), 2),
                         "price_trend": costs[ms[0]["country"]]["price_trend"], "rent_listings": ms[0]["zone_rent_listings"]}
                        for (c, z), ms in by_zone.items()), key=lambda t: -t["net_yield"])
    research = {
        "at": old["at"] if rescore else datetime.now(timezone.utc).isoformat(timespec="seconds"),  # rescore changes no research
        "listings_read": len(listings), "for_sale": len(sale), "for_rent": len(listings) - len(sale),
        "neighbourhoods": len(zones), "with_rent_data": len(known), "pln_per_eur": pln, "price_trend_period": period,
        "versions": [{"v": h["v"], "matches": h["matches"], "zones": h["zones"]} for h in history], "final_v": doc.get("final_v", history[-1]["v"]),
        "top_zones": top_zones[:3],
        "by_city": {c: {"matches": sum(1 for m in matches if m["city"] == c),
                        "best_zone": next((t for t in top_zones if t["city"] == c), None)} for c in plan["cities"]},
        "best_by_city": best_by_city(known, final, plan["cities"], matches),
        "speed": speed(raw, plan["cities"]),
        "costs": costs,
        "matches": [{**{k: m.get(k) for k in MATCH_KEYS}, **{k: zones[f"{m['city']}|{m['zone']}"][k] for k in ZONE_KEYS}} for m in matches[:200]],
        "llm_cost_usd": round(total_cost, 4), "llm_calls": calls,
    }
    out = [("research", research)] if rescore else [("zones", zones), ("costs", costs), ("rules", doc), ("research", research)]
    for name, obj in out:
        f = data / f"{name}.json"
        if f.exists():  # one version back, so a bad run never loses the rules the live demo uses
            shutil.copy(f, data / f"{name}.bak.json")
        f.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    step("Saved the rules and the results", f"{len(final)} rules, {len(matches)} matches · GLM cost ${total_cost:.2f}")
    return research, doc


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--offline", action="store_true")
    p.add_argument("--rescore", action="store_true", help="no GLM: re-evaluate data/rules.json 'final' and rewrite research.json")
    args = p.parse_args()
    load_dotenv()
    research, doc = run(lambda e: print(e["text"] + (f"  ({e['sub']})" if e.get("sub") else "")) if e["type"] == "step" else None,
                        offline=args.offline, rescore=args.rescore)
    print(f"final rules: {len(doc['final'])}, {research['versions'][-1]['matches']} matches. GLM cost ${research['llm_cost_usd']:.4f}. "
          f"Wrote {'' if args.rescore else f'{DATA}/rules.json, '}{DATA}/research.json")


if __name__ == "__main__":
    main()
