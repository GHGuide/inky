"""UI self-check: serve app/static with a stub API, open every route in headless Chrome (1440x900),
fail on any console error, uncaught exception or broken layout, and save a screenshot per route to /tmp/inky-ui/.

    .venv/bin/python app/static/check_ui.py        # from the repo root

Three passes: full fixtures (data-offline/ + the shapes below), every state field null (the empty states),
and full fixtures at 1280x720 with a workflow that has no runs yet. Walks a 2-round interview, one command
and one share through the stub. Layout: no card squashed by its flex column, nothing wider than its panel.
"""
import json
import sys
import threading
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
ROUTES = ["home", "task", "confirm", "research", "screen", "fast", "results", "workflow", "activity", "share", "market"]

research = json.loads((ROOT / "data-offline" / "research.json").read_text())
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

    def do_GET(self):
        if self.path == "/api/state":
            return self.reply(self.server.state)
        if self.path == "/api/executions":
            return self.reply(self.server.runs if self.server.state["n8n"] else [])
        super().do_GET()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
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
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    errors, shots = [], 0
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for label, state, size, runs in (("", FULL, (1440, 900), RUNS), ("empty-", EMPTY, (1440, 900), []), ("1280-", FULL, (1280, 720), [])):
            srv.state, srv.runs = state, runs
            ctx = browser.new_context(viewport={"width": size[0], "height": size[1]})
            page = ctx.new_page()
            where = {"route": "load"}
            page.on("console", lambda m: m.type == "error" and "fonts.g" not in (m.location or {}).get("url", "")
                    and errors.append(f"{label}{where['route']}: console: {m.text}"))
            page.on("pageerror", lambda e: errors.append(f"{label}{where['route']}: exception: {e}"))

            def go(route):
                where["route"] = route
                page.goto(base + "#" + route)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(200)

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

            for route in ROUTES:
                go(route)
                if not label and route == "home":
                    shot(route)
                    page.click("form.prompt button[type=submit]")  # Start -> #task -> round 1 from the stub
                    page.wait_for_selector("form.round")
                    where["route"] = "task"
                    expect(page.locator(".kv").count() == 4, "2 understood + 2 asking rows")
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
                    page.wait_for_timeout(200)
                    where["route"] = "confirm"
                    expect("Did I get it right?" in page.inner_text("body"), "the plan summary")
                    shot("confirm")
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
                elif label:
                    if route in ("research", "screen", "fast", "results", "workflow", "activity"):
                        expect(page.locator(".empty").count() >= 1, "an empty state")
                elif route == "research":
                    expect(f"{research['listings_read']:,}" in text, "listings read from the fixture")
                    page.click("button[data-v='0']")
                    expect("From your plan" in page.inner_text("body"), "v1 selected")
                elif route == "results":
                    total = FULL["rules"]["versions"][-1]["matches"]
                    expect(page.locator(".tbl tbody tr").count() == len(research["matches"]), "one row per saved match")
                    expect(f"{total} homes match" in page.inner_text(".panel h2"), f"the same total as the last research version ({total})")
                    expect("Running" in header(), "'Running' while scheduled runs come in")
                    shot(route)
                    page.fill("#msg", "Only places with the euro")
                    page.press("#msg", "Enter")
                    page.wait_for_selector("text=36 → 21 homes match")
                    where["route"] = route = "results-command"
                    expect("21 homes match" in page.inner_text(".panel h2"), "the headline to follow the command")
                    euro = sum(m["city"] != "lodz" for m in research["matches"])
                    expect(page.locator(".tbl tbody tr").count() == euro, f"only the {euro} saved homes in euro")
                    layout()
                elif route == "workflow":
                    expect(page.locator(f"a[href='{N8N}/workflow/MAIN1']").count() >= 1, "a link to the main workflow")
                elif route == "activity":
                    expect(page.locator(".event").count() == len(RUNS), "one row per execution")
                elif route == "share":
                    page.fill("#share-to", "Sanne")
                    page.click("form[data-act=share] button[type=submit]")
                    page.wait_for_selector(f"text={SHARE['link']}")
                elif route == "screen":
                    expect(page.locator(".steplist li").count() == len(FULL["program"]["steps"]), "one row per program step")
                elif route == "fast":
                    expect(page.locator(".arm").count() == len(FULL["race"]["compiled"]["per_window"]), "one card per window")
                shot(route)
            ctx.close()
        browser.close()
    srv.shutdown()
    if errors:
        print("FAIL\n" + "\n".join(errors))
        sys.exit(1)
    print(f"OK: {len(ROUTES)} routes x 3 passes, {shots} screenshots in {OUT}")


if __name__ == "__main__":
    main()
