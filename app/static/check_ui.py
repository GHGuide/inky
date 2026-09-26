"""UI self-check: serve app/static with a stub API, open every route in headless Chrome (1440x900),
fail on any console error, uncaught exception or broken layout, and save a screenshot per route to /tmp/inky-ui/.

    .venv/bin/python app/static/check_ui.py        # from the repo root

Passes: full fixtures (data-offline/ + the shapes below), every state field null (the empty states), full
fixtures at 1280x720 with a workflow that has no runs yet and reduced motion, full fixtures at 1920x1080, and ?rec=1 at 1920x1080.
The empty and 1280 passes answer 404 for the newer endpoints (summary, end, plan, research/run, build/run,
best_now), so the quiet fallbacks are tested too. Walks a 2-round interview, the live research and build
streams, "send me the best 3", a command, "Why 6.8%?", the filters, the new-since-last-time markers, a
share and the interview replay through the stub. Layout: no card squashed by its flex column, nothing wider
than its panel.
"""
import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = Path("/tmp/inky-ui")
LAYOUT = """() => {
  const bad = [], name = (el) => el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(' ')[0] : '');
  for (const el of document.querySelectorAll('.body > *, .msgs > *'))
    if (el.scrollHeight > el.clientHeight + 2) bad.push(`${name(el)} squashed to ${el.clientHeight}px of ${el.scrollHeight}px`);
  for (const el of document.querySelectorAll('.body, .msgs, .home, .market, .canvas'))
    if (el.scrollWidth > el.clientWidth + 1) bad.push(`${name(el)} is ${el.scrollWidth}px wide in ${el.clientWidth}px`);
  if (document.documentElement.scrollWidth > innerWidth) bad.push('the page scrolls sideways');
  return bad;
}"""
ROUTES = ["home", "task", "confirm", "research", "screen", "fast", "results", "workflow", "activity", "share", "market", "end"]
NEW_API = ("/api/summary", "/api/end", "/api/plan", "/api/research/run", "/api/build/run", "/api/best_now")

research = json.loads((ROOT / "data-offline" / "research.json").read_text())
ZONES = json.loads((ROOT / "data-offline" / "zones.json").read_text())
COSTS = json.loads((ROOT / "data-offline" / "costs.json").read_text())
COUNTRY = {"porto": "PT", "bari": "IT", "lodz": "PL"}


def economics(m):
    """The fields serve.py adds to every match (same sum as inky.js), so "Why 6.8%?" has something to explain."""
    z, c = ZONES[f"{m['city']}|{m['zone']}"], COSTS[COUNTRY[m["city"]]]
    month = z["rent_m2"] * m["size_m2"]
    got = month * 12 * (1 - c["vacancy"])
    net = got * (1 - c["management"]) - m["price_eur"] * c["upkeep"] - got * c["rent_tax"]
    return {**m, "country": COUNTRY[m["city"]], "rent_m2": z["rent_m2"], "sale_m2": z["sale_m2"], "n_rent": z["n_rent"], "zone_rent_listings": z["n_rent"],
            "rent_month": round(month), "gross_yield": round(month * 12 / m["price_eur"] * 100, 2), "net_yield": round(net / (m["price_eur"] * (1 + c["buy_costs"])) * 100, 2),
            "price_vs_zone": round(m["price_eur"] / m["size_m2"] / z["sale_m2"], 2), "price_trend": c["price_trend"]}


BARI = [{"title": "Bilocale Libertà", "city": "bari", "zone": "Libertà", "price_eur": 60000, "size_m2": 60, "bedrooms": 1, "url": "https://www.idealista.it/immobile/bari-1/"},
        {"title": "Trilocale Libertà", "city": "bari", "zone": "Libertà", "price_eur": 62000, "size_m2": 58, "bedrooms": 2, "url": "https://www.idealista.it/immobile/bari-2/"}]
research["matches"] = [economics(m) for m in research["matches"] + BARI]
assert all(m["net_yield"] >= 5.5 for m in research["matches"][-2:]), "the Bari fixtures must pass R3"
research["costs"] = COSTS
research["best_by_city"] = {  # the shape serve.py writes: the best home per city, why it fails, and a reason when nothing passes
    "porto": {"matches": 0, "net_yield": 3.1, "zone": "Bonfim", "title": "T1 Bonfim", "failed": ["R3"], "reason": "Of 30 flats in budget, 30 fail R3 net_yield >= 5.5."},
    "bari": {"matches": 2, "net_yield": 7.7, "zone": "Carbonara", "title": "Rustico", "failed": ["R4"], "reason": None},
    "lodz": {"matches": 15, "net_yield": 8.3, "zone": "Śródmieście", "title": "Mieszkanie Śródmieście", "failed": [], "reason": None}}
N8N = "https://example.app.n8n.cloud"
FULL = {
    "research": research,
    "rules": json.loads((ROOT / "data-offline" / "rules.json").read_text()),
    "plan": json.loads((ROOT / "plan.json").read_text()),
    "n8n": {"base": N8N, "main_url": f"{N8N}/workflow/MAIN1", "repair_url": f"{N8N}/workflow/REPAIR1"},
    # race and program in the shapes race/race.py and teach/learn.py write
    "race": {"at": "2026-09-26T19:35:06+00:00", "seconds": 60, "program": "race/sample.program.json",
             "compiled": {"windows": 8, "listings": 174, "per_second": 12.98, "model_calls": 0, "pages": 12,
                          "per_window": [30, 24, 18, 24, 18, 24, 18, 18], "seconds_used": 13.4},
             "llm": {"listings": 30, "per_second": 0.5, "model_calls": 4, "cost_usd": 0.1258, "seconds_used": 60}},
    "program": {"site": "tecnocasa.it", "city": "bari", "learned_at": "2026-09-26T19:20:00+00:00",
                "start_url": "https://www.tecnocasa.it/annunci/appartamenti/puglia/bari/bari.html", "llm_calls": 1, "llm_cost_usd": 0.0041,
                "shortcut": {"method": "GET", "url": "https://www.tecnocasa.it/api/search?city=bari&page=1"},
                "steps": [{"n": 1, "do": "click", "label": "Close the cookie banner (refuses non-essential cookies)", "target": {"css": "#cookie-banner #close"}, "value": None, "type": "dismiss"},
                          {"n": 2, "do": "fill", "label": "Type the maximum price", "target": {"css": "#price-max"}, "value": "200000", "type": "filter"},
                          {"n": 3, "do": "extract", "label": "Read the listing cards", "target": {"css": ".estate-card"}, "value": None, "type": "extract"},
                          {"n": 4, "do": "next_page", "label": "Go to the next page", "target": {"css": "a.next"}, "value": None, "type": "paginate"}],
                "item": {"selector": ".estate-card", "fields": {"title": {"css": ".estate-card-title", "type": "text"}, "price": {"css": ".estate-card-current-price", "type": "number"},
                                                               "size_m2": {"css": ".estate-card-surface span", "type": "number"}, "url": {"css": "a", "attr": "href", "type": "url"}}}},
}
EMPTY = {k: None for k in FULL}
NOW = datetime.now(timezone.utc)
RUNS = [{"id": str(100 - i), "status": s, "startedAt": (NOW - timedelta(minutes=5 + 15 * i)).isoformat(),
         "stoppedAt": (NOW - timedelta(minutes=5 + 15 * i, seconds=-(i + 2))).isoformat(), "mode": m, "workflow": w}
        for i, (s, m, w) in enumerate([("waiting", "trigger", "main"), ("success", "trigger", "main"), ("success", "integrated", "main"),
                                       ("success", "error", "repair"), ("error", "trigger", "main"), ("success", "manual", "main")])]
ROUND = {"done": False, "round": 1, "understood": [{"k": "Budget", "v": "€200,000, cash"}, {"k": "Goal", "v": "Highest rent after costs"}],
         "questions": [{"id": "q1", "text": "Who looks after the tenants?", "why": "An agency costs about 9% of the rent."},
                       {"id": "q2", "text": "How much work are you OK with?", "why": "Older flats cost less but need work."}]}
ROUND2 = {"done": False, "round": 2, "understood": [{"k": "budget", "v": "€200,000 in cash"}, {"k": "Managed by", "v": "A local agency"}],
          "questions": [{"id": "q3", "text": "Which cities?", "why": "Inky reads Porto, Bari and Łódź."}]}
DONE = {"done": True, "plan": FULL["plan"], "summary": "A 1-2 bedroom flat in Porto, Bari or Łódź, up to €200,000 in cash, that earns the most after costs.",
        "results_format": ["Yield after costs", "Price trend", "Link to the listing"]}
COMMAND = {"change": "Only homes priced in euro now count.", "rule": {"id": "R7", "field": "currency", "op": "==", "value": "EUR", "why": "You asked for euro only."},
           "removed": None, "applied": True, "matches_before": 36, "matches_after": 21}
SHARE = {"name": "Flat Finder", "description": "Tell it your budget and where you can buy. It reads the big portals every 15 minutes and asks you on Telegram before it does anything.",
         "link": "inky.app/a/flat-finder-1a2b", "gets": ["This description and the plan questions", "The n8n workflow and 4 Apify actors"],
         "keeps": ["Your answers and budget", "Your results and matches"]}


SETTLE = 2600  # ms: the longest entry animation (workflow timeline) is about 2.3 s
_ok_nodes = {n: {"items": 40, "ms": 8000, "error": None} for n in ("idealista · Porto", "idealista · Bari", "immobiliare · Bari", "otodom · Łódź")}
DETAIL = {
    "main": None,
    "ok": {"id": "8", "status": "success", "mode": "trigger", "startedAt": "2026-09-26T21:31:35Z", "stoppedAt": "2026-09-26T21:33:31Z",
           "nodes": {**_ok_nodes, "Merge": {"items": 160, "ms": 5, "error": None}, "Score · rules": {"items": 1, "ms": 1729, "error": None},
                     "Ask me on Telegram": {"items": 1, "ms": 200, "error": None}}},
    "repair": {"id": "7", "status": "success", "mode": "error", "startedAt": "2026-09-26T21:31:28Z", "stoppedAt": "2026-09-26T21:31:35Z",
               "nodes": {"On error": {"items": 1, "ms": 1, "error": None}, "GLM-5.3 fixes one step": {"items": 1, "ms": 4242, "error": None}},
               "step": "otodom · Łódź", "change": "Changed searchType from 'sale' to 'sprzedaz'.", "error": "Bad request",
               "failed": {"id": "6", "startedAt": "2026-09-26T21:30:41Z"}, "again": {"id": "8", "status": "success", "startedAt": "2026-09-26T21:31:35Z", "stoppedAt": "2026-09-26T21:33:31Z"}},
}
DETAIL["main"] = DETAIL["ok"]
DETAIL["repair"]["before"] = json.dumps({"actor": "trev0n~otodom-scraper", "input": {"searchType": "sale", "city": "lodz", "maxItems": 40, "sort": "newest"}})
DETAIL["repair"]["after"] = {"actor": "trev0n~otodom-scraper", "input": {"searchType": "sprzedaz", "city": "lodz", "maxItems": 40, "sort": "newest"}}
SOURCE_ITEMS = {n: 40 for n in _ok_nodes}
SUMMARY = {"since": (NOW - timedelta(hours=24)).isoformat(), "runs": 96, "ok": 92, "failed": 4, "repairs": 1, "listings_checked": 4210, "new_listings": 312, "matches": 3,
           "apify_usd": 1.92, "ai_calls": 0, "glm_usd_research": 0.14,
           "per_run": [{"id": r["id"], "startedAt": r["startedAt"], "status": r["status"], "mode": r["mode"], "listings": 160, "new": 12, "matches": 1 if i == 1 else 0, "secs": 116, "apify_usd": 0.02,
                        "sources": SOURCE_ITEMS} for i, r in enumerate(RUNS) if r["workflow"] == "main"]}
END = {"listings_read": 48312, "runs": 96, "listings_checked": 4210, "matches": 3, "fixes": 1, "apify_usd_total": 1.92, "apify_usd_per_run": 0.02, "ai_calls_per_run": 0, "repo": "https://github.com/GHGuide/inky"}
RESEARCH_RUN = [{"type": "step", "text": "Saved your plan", "sub": "porto, bari, lodz · up to €200,000"},
                {"type": "step", "text": "Read listings with Apify", "sub": "1,312 homes: 820 for sale, 492 for rent"},
                {"type": "step", "text": "Matched rents to prices, street by street", "sub": "9 neighbourhoods scored"},
                {"type": "version", "v": 1, "matches": 77, "zones": 5, "rules": []},
                {"type": "step", "text": "GLM-5.3 looked at what passed", "sub": "too many homes far from any rental: added R4"},
                {"type": "version", "v": 2, "matches": 53, "zones": 4, "rules": []},
                {"type": "version", "v": 3, "matches": 36, "zones": 4, "rules": []}]
BUILD_RUN = [{"type": "step", "text": "Checked the credentials", "sub": "Apify, Telegram and Gmail, in your n8n"},
             {"type": "step", "text": "Wrote the workflow", "sub": "12 steps: 4 sites, score, ask you, draft"},
             {"type": "step", "text": "Wrote the repair workflow", "sub": "on any error: GLM-5.3 rewrites the broken step"}]


class Stub(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def log_message(self, *a):
        pass

    def reply(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def stream(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        for ev in events:
            self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.05)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in NEW_API and not self.server.new_api:
            return self.send_error(404)
        if path == "/api/state":
            time.sleep(self.server.delay)
            return self.reply(self.server.state)
        if path == "/api/executions":
            return self.reply(self.server.runs if self.server.state["n8n"] else [])
        if path == "/api/run_detail":
            return self.reply(DETAIL if self.server.state["n8n"] and self.server.runs else {"main": None, "ok": None, "repair": None})
        if path == "/api/summary":
            return self.reply(SUMMARY if self.server.runs else {**SUMMARY, **{k: 0 for k in SUMMARY if k not in ("since", "per_run")}, "per_run": []})
        if path == "/api/end":
            return self.reply(END)
        super().do_GET()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        self.server.calls[self.path] = self.server.calls.get(self.path, 0) + 1
        if self.path in NEW_API and not self.server.new_api:
            return self.send_error(404)
        if self.path == "/api/plan":
            assert isinstance(body.get("plan"), dict), body
            return self.reply({"ok": True, "plan": body["plan"]})
        if self.path == "/api/research/run":
            return self.stream([*RESEARCH_RUN, {"type": "done", "research": research, "rules": FULL["rules"]}])
        if self.path == "/api/build/run":
            return self.stream([*BUILD_RUN, {"type": "done", "main_url": FULL["n8n"]["main_url"], "repair_url": FULL["n8n"]["repair_url"]}])
        if self.path == "/api/best_now":
            return self.reply({"sent": 3, "matches": research["matches"][:3]})
        if self.path == "/api/interview":
            msgs = body["messages"]
            assert msgs and msgs[-1]["role"] == "user", msgs
            return self.reply([ROUND, ROUND2, DONE][min(2, sum(m["role"] == "assistant" for m in msgs))])
        if self.path == "/api/command":  # like serve.py: the rule is saved to rules.json 'final'
            st = self.server.state
            if st["rules"]:
                self.server.state = {**st, "rules": {**st["rules"], "final": st["rules"]["final"] + [COMMAND["rule"]]}}
            return self.reply(COMMAND)
        if self.path == "/api/share":
            return self.reply(SHARE)
        self.send_error(404)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    srv.calls, srv.delay, srv.new_api = {}, 0, True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    errors, shots = [], 0
    qr_missing = not (HERE / "qr-repo.svg").exists()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        passes = (("", FULL, (1440, 900), RUNS, True, ""), ("empty-", EMPTY, (1440, 900), [], False, ""), ("1280-", FULL, (1280, 720), [], False, ""),
                  ("1920-", FULL, (1920, 1080), RUNS, True, ""), ("rec-", FULL, (1920, 1080), RUNS, True, "?rec=1"))
        for label, state, size, runs, new_api, query in passes:
            srv.state, srv.runs, srv.new_api, srv.calls = state, runs, new_api, {}
            ctx = browser.new_context(viewport={"width": size[0], "height": size[1]}, reduced_motion="reduce" if label == "1280-" else "no-preference")
            page = ctx.new_page()
            where = {"route": "load"}

            def console(m, label=label):
                url = (m.location or {}).get("url", "")
                quiet_404 = "Failed to load resource" in m.text and (("/api/" in url and not srv.new_api) or (qr_missing and url.endswith("qr-repo.svg")))
                if m.type == "error" and "fonts.g" not in url and not quiet_404:
                    errors.append(f"{label}{where['route']}: console: {m.text} {url}")
            page.on("console", console)
            page.on("pageerror", lambda e, label=label: errors.append(f"{label}{where['route']}: exception: {e}"))

            def go(route, q=query):
                where["route"] = route
                page.goto(base + q + "#" + route)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(SETTLE)  # let the entry animations finish: moving cards count as overflow

            def shot(route):
                nonlocal shots
                page.screenshot(path=str(OUT / f"{label}{route}.png"))
                shots += 1

            def expect(ok, what):
                if not ok:
                    errors.append(f"{label}{where['route']}: expected {what}")

            def layout():  # the bugs a DOM count misses: squashed cards, content cut off or wider than the panel
                for bad in page.evaluate(LAYOUT):
                    errors.append(f"{label}{where['route']}: layout: {bad}")

            def header():
                return page.inner_text(".hdr") if page.locator(".hdr").count() else ""

            def rows():
                return page.locator(".tbl tbody tr:not(.why-row)")

            if label in ("1920-", "rec-"):  # F11 and A4: every route at 1920x1080, laid out like the 1440 design
                if label == "1920-":
                    srv.delay = 1.5  # F6: the first paint is a shimmer, not an empty state
                    where["route"] = "skeleton"
                    page.goto(base + "#results")
                    page.wait_for_timeout(400)
                    expect(page.locator(".skel").count() >= 3, "skeletons while /api/state loads")
                    shot("skeleton")
                    srv.delay = 0
                for route in ROUTES:
                    go(route)
                    layout()
                    if label == "rec-":
                        expect(page.evaluate("document.documentElement.classList.contains('rec')"), "the rec class")
                        expect(page.evaluate("document.documentElement.scrollHeight <= innerHeight + 1 && document.documentElement.scrollWidth <= innerWidth"), "a page that fits 1920x1080 without scrolling")
                    shot(route)
                ctx.close()
                continue

            for route in ROUTES:
                go(route)
                if not label and route == "home":
                    shot(route)
                    page.click("form.prompt button[type=submit]")  # Start -> #task -> round 1 from the stub
                    page.wait_for_selector("form.round")
                    where["route"] = "task"
                    expect(page.locator(".kv").count() == 4, "2 understood + 2 asking rows")
                    expect("Skip picks: Up to €200,000" in page.inner_text("form.round"), "the defaults Skip picks")
                    layout()
                    shot("task")
                    page.fill("input[name=a0]", "A local agency")
                    page.click("form.round button[type=submit]")  # -> round 2
                    page.wait_for_selector("text=ROUND 2")
                    where["route"] = "task-round2"
                    expect(page.locator(".done-rounds summary").first.bounding_box()["height"] > 20, "round 1 collapsed into a visible row")
                    expect(page.locator(".kv").count() == 4, "3 understood (budget merged across rounds) + 1 asking row")
                    expect("3 of 4" in page.inner_text(".panel"), "the understood count to grow, not drop")
                    layout()
                    shot("task-round2")
                    page.click("form.round [data-act=skip]")  # stub answers done -> #confirm
                    page.wait_for_url("**#confirm")
                    page.wait_for_timeout(SETTLE)
                    where["route"] = "confirm"
                    expect("Did I get it right?" in page.inner_text("body"), "the plan summary")
                    shot("confirm")
                    # C1: the research streams into the chat, then the app moves to #research; a second click does nothing
                    page.click("[data-act=research]")
                    page.click("[data-act=research]", force=True, no_wait_after=True)
                    page.wait_for_selector("#job-lines .jv >> nth=1", timeout=15000)
                    where["route"] = "confirm-research"
                    expect(page.locator("[data-act=research]").is_disabled(), "the button disabled while it runs")
                    layout()
                    shot("confirm-research")
                    page.wait_for_url("**#research", timeout=20000)
                    expect(srv.calls.get("/api/research/run") == 1 and not srv.calls.get("/api/plan"), f"one research run, which saves the plan itself, got {srv.calls}")
                    continue
                if not label and route in ("task", "confirm"):
                    continue  # already shot during the interview
                text = page.inner_text("body")
                layout()
                if label == "1280-":
                    if route in ("results", "workflow"):
                        expect("Running" not in header() and "no runs yet" in header(), "'no runs yet', not 'Running', without runs")
                    if route == "activity":
                        expect("No runs yet" in text, "'No runs yet' for a built workflow without runs")
                    if route == "research":  # build/run is a 404 here: it says the workflow is already built and moves on
                        page.click("[data-act=build]")
                        page.wait_for_url("**#workflow", timeout=15000)
                        expect(srv.calls.get("/api/build/run") == 1, "one build call")
                    if route == "results":
                        page.click("[data-act=best]")
                        page.wait_for_selector(".toast.bad", timeout=5000)
                        expect("isn’t on this server" in page.inner_text("#toasts"), "a quiet toast for a missing /api/best_now")
                    if route == "end":
                        expect("Tell it once." in text and "Last night" not in text, "the end card without numbers when /api/end is missing")
                elif label:
                    if route in ("research", "screen", "fast", "results", "workflow", "activity"):
                        expect(page.locator(".empty").count() >= 1, "an empty state")
                elif route == "research":
                    expect(f"{research['listings_read']:,}" in text, "listings read from the fixture")
                    cities_text = page.inner_text(".cities")
                    expect(page.locator(".city").count() == 3 and "Prices +17.8% a year, but the best yield after costs is only 3.1%" in cities_text and "misses R4" in cities_text,
                           f"best per city, with why nothing passes in Porto: {cities_text!r}")
                    page.click("button[data-v='0']")
                    expect("From your plan" in page.inner_text("body"), "v1 selected")
                    shot(route)
                    # C2: the build streams into the chat with the links, then #workflow
                    page.click("[data-act=build]")
                    page.wait_for_selector("#job-lines > div >> nth=2", timeout=15000)
                    where["route"] = "research-build"
                    layout()
                    shot("research-build")
                    page.wait_for_selector(".job a[href$='/workflow/MAIN1']", timeout=15000)
                    page.wait_for_url("**#workflow", timeout=15000)
                    expect(srv.calls.get("/api/build/run") == 1, f"one build call, got {srv.calls}")
                    expect("Saved to n8n" in page.inner_text("#toasts"), "the 'Saved to n8n' toast")
                    continue
                elif route == "results":
                    total = FULL["rules"]["versions"][-1]["matches"]
                    expect(rows().count() == len(research["matches"]), "one row per saved match")
                    expect(f"{total} homes match" in page.inner_text(".panel h2"), f"the same total as the last research version ({total})")
                    expect("Running" in header(), "'Running' while scheduled runs come in")
                    expect(page.locator(".tbl .newtag").count() == 0 and "best now" in rows().first.inner_text(), "no 'new' marks on a first visit, the best home on top")
                    shot(route)
                    # F2: two homes the browser hasn't seen yet are marked new
                    page.evaluate("u => localStorage.setItem('inky.seen', JSON.stringify(u))", [m["url"] for m in research["matches"][2:]])
                    page.reload()
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(SETTLE)
                    expect(page.locator(".tbl .newtag").count() == 2, "2 homes marked new since the last look")
                    # E1: Why 6.8%? adds up to the same number as the row
                    first = page.locator(".whybtn").first
                    shown_pct = first.inner_text().split("why")[0].strip()
                    first.click()
                    page.wait_for_timeout(500)
                    where["route"] = "results-why"
                    expect(page.locator(".why-row").count() == 1 and shown_pct in page.inner_text(".why-row .tot.hot"), f"the breakdown to end at {shown_pct}")
                    expect("estimate" in page.inner_text(".why-row") and "Eurostat" in page.inner_text(".why-row"), "estimate labels")
                    layout()
                    shot("results-why")
                    first.click()
                    # F2: city filter
                    page.click(".fchip[data-v='bari']")
                    cities = page.locator(".tbl tbody tr:not(.why-row) td:nth-child(2) .sub").all_inner_texts()
                    expect(cities and all(c == "Bari" for c in cities), f"only Bari homes, got {cities}")
                    page.click(".fchip[data-act=fcity][data-v='']")
                    # B1: the button and the phrase both send the best 3, not a rule edit
                    page.click("[data-act=best]")
                    page.wait_for_selector(".toast:has-text('Sent 3 homes to your Telegram')")
                    page.wait_for_timeout(500)  # the reply and the toast rise in
                    where["route"] = "results-best"
                    layout()
                    shot("results-best")
                    page.fill("#msg", "send me the best ones")
                    page.press("#msg", "Enter")
                    page.wait_for_function("document.querySelectorAll('.toast').length >= 2")
                    expect(srv.calls.get("/api/best_now") == 2 and not srv.calls.get("/api/command"), f"2 best_now calls and no command, got {srv.calls}")
                    page.fill("#msg", "Only places with the euro")
                    page.press("#msg", "Enter")
                    page.wait_for_selector("text=36 → 21 homes match")
                    page.wait_for_timeout(SETTLE)  # the headline counts from 36 down to 21
                    where["route"] = route = "results-command"
                    expect("21 homes match" in page.inner_text(".panel h2"), "the headline to follow the command")
                    euro = sum(m["city"] != "lodz" for m in research["matches"])
                    expect(rows().count() == euro, f"only the {euro} saved homes in euro")
                    layout()
                elif route == "workflow":
                    expect(page.locator(f"a[href='{N8N}/workflow/MAIN1']").count() >= 1, "a link to the main workflow")
                    flow = page.inner_text(".flow")
                    expect(page.locator(".stage").count() == 4 and "160" in flow and "4,210" in flow, "4 stages with 24 h totals (4,210) and the last run's 160")
                    expect("fixed in 7.0 s" in text and "sprzedaz" in text, "the repair story: fixed in 7 s, GLM's change")
                    expect(page.locator(".diff .del").count() == 1 and page.locator(".diff .add").count() == 1, "one changed key in the repair diff")
                elif route == "activity":
                    expect(page.locator(".event").count() == len(RUNS), "one row per execution")
                    expect("4,210" in page.inner_text(".stats"), "24 h totals from /api/summary")
                    page.click("details.runrow summary >> nth=0")
                    expect(page.locator("details.runrow[open] .srcs > div").count() == len(SOURCE_ITEMS), "listings per site in an opened run")
                    shot("activity-open")
                elif route == "share":
                    page.fill("#share-to", "Sanne")
                    page.click("form[data-act=share] button[type=submit]")
                    page.wait_for_selector(f"text={SHARE['link']}")
                elif route == "screen":
                    expect(page.locator(".steplist li").count() == len(FULL["program"]["steps"]), "one row per program step")
                elif route == "fast":
                    expect(page.locator(".arm").count() == len(FULL["race"]["compiled"]["per_window"]), "one card per window")
                    expect("all 174 Bari flats under €200k in 13.4 s" in text, "the race in one sentence")
                    page.keyboard.press("/")  # F13: "/" focuses the chat, Esc leaves it, 1-5 switch tabs
                    expect(page.evaluate("document.activeElement.id") == "msg", "'/' to focus the message box")
                    page.keyboard.press("Escape")
                    shot(route)
                    page.keyboard.press("4")
                    page.wait_for_url("**#results")
                    continue
                elif route == "end":
                    expect("Tell it once." in text and "4,210 listings checked in 96 runs" in text and "3 homes found" in text, "last night's totals from /api/end")
                    expect(page.locator(".qr img, .qr-none").count() == 1, "the QR code or its placeholder")
                elif route == "market":
                    expect("Preview" in text, "the Preview label on sample agents")
                shot(route)
            if not label:  # A5: replay the interview saved in this tab, then land on the plan
                where["route"] = "replay"
                srv.calls = {}
                page.goto(base + "?replay=5#task")
                page.wait_for_selector("form.round", timeout=10000)
                expect("Replay" in header(), "a 'Replay' header pill")
                page.wait_for_timeout(700)
                shot("task-replay")
                page.wait_for_url("**#confirm", timeout=30000)
                expect(not srv.calls.get("/api/interview"), "no interview calls during a replay")
            ctx.close()
        browser.close()
    srv.shutdown()
    if errors:
        print("FAIL\n" + "\n".join(errors))
        sys.exit(1)
    print(f"OK: {len(ROUTES)} routes x {len(passes)} passes, {shots} screenshots in {OUT}")


if __name__ == "__main__":
    main()
