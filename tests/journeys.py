"""End-to-end journeys from docs/vision.md, on real engines, real sites and a real model. Not unit tests: they take
minutes, use the network and a local model. Run them before a release:

    python -m tests.journeys                 # all of them, with gemma3:12b from Ollama
    python -m tests.journeys chat share      # only these
    INKY_JOURNEY_MODEL=qwen3:8b python -m tests.journeys

Each engine gets its own scratch home and port; nothing touches ~/.inky. "Do" journeys only ever send to the local test site."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = os.environ.get("INKY_JOURNEY_MODEL", "gemma3:12b")
SECRETS = ("OPENROUTER_API_KEY", "APIFY_TOKEN", "TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY")


class Engine:
    """A scratch Inky engine in its own process, driven through its HTTP API like the app does."""

    def __init__(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.home = tempfile.mkdtemp(prefix="inky-journey-")
        self.url = f"http://127.0.0.1:{self.port}"
        env = {k: v for k, v in os.environ.items() if k not in SECRETS} | {"INKY_KEYS": "file", "INKY_HEADLESS": "1", "PYTHONPATH": str(ROOT)}
        self.proc = subprocess.Popen([sys.executable, "-m", "inky", "--port", str(self.port), "--home", self.home, "--host", "127.0.0.1", "--no-open"],
                                     env=env, cwd=self.home, stdout=open(os.path.join(self.home, "engine.log"), "w"), stderr=subprocess.STDOUT)
        for _ in range(60):
            try:
                urllib.request.urlopen(self.url + "/api/ping", timeout=1)
                break
            except Exception:
                time.sleep(0.3)
        self.token = Path(self.home, "api_token").read_text().strip()
        self.api("POST", "/api/settings", {"setup_done": True})

    def api(self, method, path, body=None, timeout=300):
        req = urllib.request.Request(self.url + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-Inky-Token": self.token, "Content-Type": "application/json"})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read() or b"{}")
        except urllib.error.HTTPError as e:
            return {"_status": e.code, **json.loads(e.read() or b"{}")}

    def use(self, model=MODEL):
        return self.api("POST", "/api/models/connect", {"provider": "ollama", "model": model})

    def bot(self, bid):
        return self.api("GET", f"/api/bots/{bid}")

    def idle(self, bid, limit=900):
        t0 = time.time()
        while time.time() - t0 < limit:
            b = self.bot(bid)["bot"]
            if b["status"] not in ("working", "learning") and not b.get("run_kind") and not b.get("site_batch"):
                return round(time.time() - t0)
            time.sleep(3)
        return limit

    def close(self):
        self.proc.send_signal(2)
        try:
            self.proc.wait(20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.home, ignore_errors=True)


def learn(E, name, job, goal, url, **extra):
    b = E.api("POST", "/api/bots", {"name": name, "job": job, "goal": goal, "start_url": url, "every_minutes": 0, **extra})["bot"]
    E.api("POST", f"/api/bots/{b['id']}/learn", {})
    secs = E.idle(b["id"])
    d = E.bot(b["id"])
    learned = next((r for r in d["runs"] if r.get("kind") == "learn"), {})
    res = E.api("GET", f"/api/bots/{b['id']}/results").get("results", [])
    return b["id"], {"secs": secs, "ai": learned.get("ai_calls"), "steps": [st.get("text") for s in d["skills"] for st in s["steps"]],
                     "results": len(res), "named": sum(1 for r in res if r.get("title") or r.get("price")),
                     "sample": [{k: str(r.get(k))[:40] for k in ("title", "price")} for r in res[:2]], "needs": [n["title"] for n in d["needs"]]}


# ---------------------------------------------------------------- the journeys

def j_watch_books():
    E = Engine()
    try:
        E.use()
        d = E.api("POST", "/api/bots/draft", {"job": "Every morning, find books under £20 on books.toscrape.com"})["draft"]
        bid, r = learn(E, d["name"], d["job"], d["goal"], d["start_url"], filters=d.get("filters"))
        ok = r["results"] >= 10 and r["named"] == r["results"] and not r["needs"]
        return ok, f"{r['results']} under £20 from 3 pages, {r['ai']} AI calls, {r['secs']} s · steps {r['steps']}"
    finally:
        E.close()


def j_find_sites():
    E = Engine()
    try:
        E.use()
        d = E.api("POST", "/api/bots/draft", {"job": "Find the cheapest wholesale bricks in Moldova"})["draft"]
        s = E.api("POST", "/api/sites", {"job": d["job"], "queries": d.get("search"), "guess": d.get("guess")})
        hosts = [x["host"] for x in s.get("sites", [])]
        made_up = [f["field"] for f in d.get("filters") or [] if f["field"] not in ("country", "location", "price")]
        ok = len(hosts) >= 3 and not made_up and not d.get("start_url")
        return ok, f"{len(hosts)} sites ({', '.join(hosts[:6])}…){' · ' + s['note'] if s.get('note') else ''} · rules {[f.get('text') for f in d.get('filters') or []]}"
    finally:
        E.close()


def j_real_sites():
    E = Engine()
    try:
        E.use()
        out, ok = [], True
        for url in ("https://www.marktplaats.nl/l/fietsen-en-brommers/elektrische-fietsen/", "https://ebikexl.nl/", "https://2dehandsfietsenwinkel.nl/"):
            bid, r = learn(E, "Ebike Test", "Find used e-bikes", "Find used e-bikes for sale", url)
            again = {}
            if r["steps"]:
                E.api("POST", f"/api/bots/{bid}/run", {"wait": True}, timeout=400)
                again = E.bot(bid)["runs"][0]
            good = r["results"] >= 5 and r["named"] >= 0.8 * r["results"] and again.get("status") == "ok"
            ok = ok and good
            out.append(f"{url.split('/')[2]}: {r['results']} results, {r['ai']} AI calls, rerun {again.get('status')} ({again.get('items')})")
        return ok, " · ".join(out)
    finally:
        E.close()


def j_do_and_change():
    from tests import site_server
    site = site_server.start(8766) if not _up("http://127.0.0.1:8766/") else None
    base, sent = "http://127.0.0.1:8766", lambda: json.loads(urllib.request.urlopen("http://127.0.0.1:8766/__sent").read())
    layout = lambda v: urllib.request.urlopen(f"{base}/__layout?v={v}").read()
    E = Engine()
    notes, ok = [], True
    try:
        layout(1)
        E.use()
        b = E.api("POST", "/api/bots", {"name": "Agency Note", "job": "Send the agency the message 'Is it still available?' about listing 1",
                                        "goal": "Type the message 'Is it still available?' and send it", "start_url": base + "/contact?id=1", "every_minutes": 0})["bot"]

        def answer(choice):
            for _ in range(200):
                ns = E.bot(b["id"])["needs"]
                if ns:
                    if choice:
                        E.api("POST", f"/api/bots/{b['id']}/needs/{ns[0]['id']}", {"decision": choice})
                    return True
                if E.bot(b["id"])["bot"]["status"] not in ("working", "learning") and not E.bot(b["id"])["bot"].get("run_kind"):
                    return False
                time.sleep(2)
        n0 = len(sent())
        E.api("POST", f"/api/bots/{b['id']}/learn", {})
        asked = answer("Approve"); E.idle(b["id"])
        learned = len(sent()) - n0 == 1 and asked
        res = [f"learned (asked {asked}, sent {len(sent()) - n0})"]
        for choice, want in (("Deny", 0), ("Always for this step", 1), (None, 1)):
            before = len(sent())
            E.api("POST", f"/api/bots/{b['id']}/run", {})
            a = answer(choice); E.idle(b["id"])
            good = len(sent()) - before == want and (a if choice else not a)
            ok = ok and good
            res.append(f"{choice or 'next run'}: asked {a}, sent {len(sent()) - before}")
        ok = ok and learned
        notes.append("do: " + ", ".join(res))
        f, r = learn(E, "Flat Finder", "Find flats in Bari under 150000 euro", "Search flats in Bari and read the results", base + "/",
                     filters=[{"field": "price", "op": "<=", "value": 150000, "text": "price at most 150000"}])
        layout(2)
        E.api("POST", f"/api/bots/{f}/run", {"wait": True}, timeout=400)
        run = E.bot(f)["runs"][0]
        changed = run.get("status") == "ok" and (run.get("items") or 0) > 0 and not E.bot(f)["needs"]
        ok = ok and changed and r["results"] > 0
        notes.append(f"change: learned {r['results']} results, after the page changed {run.get('status')} with {run.get('items')} items")
        return ok, " · ".join(notes)
    finally:
        layout(1)
        E.close()
        if site:
            site.shutdown()


def j_chat():
    E = Engine()
    try:
        E.use()
        bid = E.api("POST", "/api/library/install", {"url": "bundled:agents/book-bargains.inky"})["id"]
        E.api("POST", f"/api/bots/{bid}/run", {"wait": True}, timeout=300)

        def say(t):
            r = E.api("POST", f"/api/bots/{bid}/chat", {"text": t}, timeout=300)
            b = E.bot(bid)["bot"]
            return r, b
        checks = [("what did you find?", lambda r, b: "60" in (r.get("reply") or "")),
                  ("only keep books under £15", lambda r, b: [f["value"] for f in b["filters"] if f["field"] == "price"] == [15]),
                  ("check every hour", lambda r, b: b["schedule"]["every_minutes"] == 60),
                  ("Should you check every 5 minutes?", lambda r, b: b["schedule"]["every_minutes"] == 60),
                  ("remember I like mystery novels", lambda r, b: any("mystery" in m["text"].lower() for m in b["memory"])),
                  ("forget that I like mystery novels", lambda r, b: not any("mystery" in m["text"].lower() for m in b["memory"])),
                  ("pause", lambda r, b: b.get("held")),
                  ("resume", lambda r, b: not b.get("held")),
                  ("only run when I ask", lambda r, b: b["schedule"]["every_minutes"] == 0),
                  ("run now", lambda r, b: b.get("run_kind") or "run" in " ".join(r.get("done") or []))]
        bad = []
        for t, test in checks:
            r, b = say(t)
            if not test(r, b):
                bad.append(f"“{t}” → {r.get('reply')!r}")
        return not bad, f"{len(checks) - len(bad)}/{len(checks)} did exactly what was asked" + (": " + "; ".join(bad) if bad else "")
    finally:
        E.close()


def j_batch():
    E = Engine()
    try:
        E.use()
        b = E.api("POST", "/api/bots", {"name": "Reader", "job": "find books and quotes", "goal": "Find the books or quotes listed", "start_url": "https://books.toscrape.com/",
                                        "more_sites": ["https://nonexistent-inky-journey.invalid/", "https://quotes.toscrape.com/"], "every_minutes": 0})["bot"]
        E.api("POST", f"/api/bots/{b['id']}/learn", {})
        time.sleep(5)
        E.idle(b["id"], 1200)
        d = E.bot(b["id"])
        msgs = [m["text"] for m in d["messages"]]
        progress = [m for m in msgs if m.startswith("Learning 3 sites")]
        ok = len(progress) == 1 and len(d["skills"]) == 2 and not d["needs"] and not any(m.startswith("Next site") for m in msgs)
        return ok, f"{len(d['skills'])} of 3 learned, {len(progress)} progress message, needs {len(d['needs'])} · {progress[0] if progress else ''}"
    finally:
        E.close()


def j_handled():
    E = Engine()
    try:
        E.use("qwen3:1.7b")
        b = E.api("POST", "/api/bots", {"name": "Lost", "job": "x", "goal": "Find things", "start_url": "https://nonexistent-inky-journey.invalid/"})["bot"]
        E.api("POST", f"/api/bots/{b['id']}/learn", {})
        E.idle(b["id"], 120)
        d, needs = E.bot(b["id"]), E.api("GET", "/api/needs")
        ok = not d["needs"] and needs.get("handled") and "nothing for you to do" in d["messages"][-1]["text"]
        return bool(ok), f"needs {len(d['needs'])}, handled log {len(needs.get('handled') or [])}: {d['messages'][-1]['text'][:90]}"
    finally:
        E.close()


def j_stop():
    import threading
    E = Engine()
    try:
        E.use()
        b = E.api("POST", "/api/bots", {"name": "Stopper", "job": "books", "goal": "Find books under £20", "start_url": "https://books.toscrape.com/catalogue/category/books/travel_2/index.html", "every_minutes": 0})["bot"]
        threading.Thread(target=lambda: E.api("POST", f"/api/bots/{b['id']}/chat", {"text": "Tell me a long story about books and the history of printing"}), daemon=True).start()
        for _ in range(60):
            live = E.api("GET", "/api/models/live")["thinking"]
            if live:
                break
            time.sleep(0.5)
        t0 = time.time()
        E.api("POST", "/api/models/stop", {"bot": b["id"]})
        for _ in range(40):
            if not E.api("GET", "/api/models/live")["thinking"]:
                break
            time.sleep(0.25)
        took = round(time.time() - t0, 1)
        ok = bool(live) and took < 3 and not E.api("GET", "/api/models/live")["thinking"]
        return ok, f"saw {live[0]['model'] if live else 'nothing'} thinking; Stop took {took} s"
    finally:
        E.close()


def j_share():
    A, B = Engine(), Engine()
    try:
        bid = A.api("POST", "/api/library/install", {"url": "bundled:agents/book-bargains.inky"})["id"]
        link = A.api("POST", f"/api/bots/{bid}/share-code", {"meta": {}})["link"]
        prev = B.api("POST", "/api/library/preview", {"url": link})
        nb = B.api("POST", "/api/library/install", {"url": link})["id"]
        run = B.api("POST", f"/api/bots/{nb}/run", {"wait": True}, timeout=300).get("run") or {}
        ok = prev.get("check", {}).get("ok") and run.get("status") == "ok" and (run.get("items") or 0) > 0
        return bool(ok), f"link {len(link)} chars, preview says unverified {prev.get('listing', {}).get('unverified')}, run on the other Inky: {run.get('status')} {run.get('items')} items, {run.get('matched')} pass"
    finally:
        A.close()
        B.close()


def j_new_user():
    """A first-time user on the real screens: 3 setup steps, one job in their words, the bot learns, they see what it found,
    change a rule in chat, and nothing on the way is broken or off-screen."""
    from playwright.sync_api import sync_playwright
    E = Engine()
    E.api("POST", "/api/settings", {"setup_done": False})
    errs, notes = [], []
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            pg = br.new_page(viewport={"width": 1280, "height": 860})
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(E.url + "/")
            pg.wait_for_selector("#wnext", timeout=20000)
            steps = [pg.locator(".wcount").inner_text()]
            pg.click("#wnext")
            pg.wait_for_selector("#localm [data-use], #localm .good", timeout=30000)
            if pg.locator("#localm [data-use]").count() and "In use" not in pg.locator("#localm").inner_text():
                pg.locator("#localm [data-use]").first.click()
                pg.wait_for_timeout(6000)
            steps.append(pg.locator(".wcount").inner_text())
            pg.click("#wnext")
            pg.wait_for_selector("#job", timeout=20000)
            steps.append(pg.locator(".wcount").inner_text())
            pg.fill("#job", "Every morning, find books under £20 on books.toscrape.com")
            pg.click("#start")
            pg.wait_for_selector("#create", timeout=240000)
            pg.click("#create")
            pg.wait_for_function("location.hash.startsWith('#/bot/')", timeout=30000)
            bid = int(pg.evaluate("location.hash").split("/")[2])
            E.idle(bid, 900)
            pg.goto(E.url + "/#/bots")
            pg.wait_for_selector(f"#nav a[data-bot='{bid}']")
            card = pg.locator(".botcard").first.inner_text()
            pg.click(f"#nav a[data-bot='{bid}']")
            pg.wait_for_selector(".rlist .ritem", timeout=20000)
            opened, tabs, found = pg.evaluate("location.hash"), pg.locator(".tabs > a").all_inner_texts(), pg.locator(".ritem").count()
            pg.fill("#say", "only keep books under £15")
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(4000)
            E.api("GET", f"/api/bots/{bid}")
            pg.goto(E.url + f"/#/bot/{bid}/results")
            pg.wait_for_selector(".rlist .ritem, #tb p", timeout=20000)
            pg.wait_for_timeout(1000)
            after = pg.locator(".ritem").count()
            sidebar = pg.locator("#nav .navbottom > a.navlink, #nav .navbottom > details > summary").all_inner_texts()
            pg.set_viewport_size({"width": 390, "height": 844})
            pg.wait_for_timeout(600)
            overflow = pg.evaluate("document.documentElement.scrollWidth > innerWidth")
            br.close()
        ok = (steps == ["Step 1 of 3 · Welcome", "Step 2 of 3 · Model", "Step 3 of 3 · Ready"] and opened.endswith("/results") and found >= 10
              and "found" in card and 0 < after < found and not overflow and not errs and sidebar[-1] == "More")
        notes.append(f"setup {len(steps)} steps · opened on {opened.split('/')[-1]} · tabs {tabs} · {found} found, {after} after “under £15” · card “{card.splitlines()[2] if len(card.splitlines()) > 2 else card}” · phone overflow {overflow} · page errors {len(errs)}")
        return ok, " ".join(notes)
    finally:
        E.close()


def _up(url):
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:
        return False


JOURNEYS = {"newuser": j_new_user, "books": j_watch_books, "find": j_find_sites, "real": j_real_sites, "do": j_do_and_change, "chat": j_chat,
            "batch": j_batch, "handled": j_handled, "stop": j_stop, "share": j_share}

if __name__ == "__main__":
    names = sys.argv[1:] or list(JOURNEYS)
    rows = []
    for n in names:
        t0 = time.time()
        try:
            ok, detail = JOURNEYS[n]()
        except Exception as e:
            ok, detail = False, f"crashed: {type(e).__name__}: {e}"
        rows.append((n, ok, round(time.time() - t0), detail))
        print(f"{'PASS' if ok else 'FAIL'}  {n:8} {rows[-1][2]:>4}s  {detail}", flush=True)
    print(f"\n{sum(1 for r in rows if r[1])}/{len(rows)} journeys passed")
    sys.exit(0 if all(r[1] for r in rows) else 1)
