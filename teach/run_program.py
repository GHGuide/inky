"""Run the program Inky learned on tecnocasa.it, with no model.

    .venv/bin/python teach/run_program.py --pages 3                     # the shortcut: one JSON request per page
    .venv/bin/python teach/run_program.py --pages 2 --browser --headed  # replay the recorded clicks in Chrome

Reads teach/tecnocasa.program.json, writes teach/out.json (one item per listing, the shape
inky.js normalize() takes) and prints listings per second.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx

HERE = Path(__file__).parent
PROGRAM = HERE / "tecnocasa.program.json"
OUT = HERE / "out.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

# Raw strings of every field in every card, in the page. Same as the actor's Playwright-free twin.
READ_CARDS = """(cards, fields) => cards.map(c => Object.fromEntries(Object.entries(fields).map(([k, f]) => {
  const el = c.querySelector(f.css);
  return [k, !el ? null : f.attr ? el.getAttribute(f.attr) : el.textContent.replace(/\\s+/g, ' ').trim()];
})))"""


def dig(obj, path):
    for k in path.split(".") if path else []:
        obj = obj.get(k) if isinstance(obj, dict) else None
    return obj


def typed(raw, f, base):
    """One raw string -> its typed value. int: first number, dots are thousands (Italian '€ 175.000')."""
    if raw is None:
        return None
    raw = str(raw).strip()
    if f.get("re"):
        m = re.search(f["re"], raw)
        raw = (m.group(1) if m and m.groups() else m.group(0) if m else "").strip()
    if f["type"] == "int":
        m = re.search(r"\d[\d.]*", raw)
        return int(m.group().replace(".", "")) if m else None
    if f["type"] == "link":
        return urljoin(base, raw) if raw else None
    return raw or None


def listing(raw, prog):
    fields = prog["item"]["fields"]
    row = {"source": prog["site"].split(".")[0], "city": prog["city"], "op": "sale"}
    row.update({k: typed(raw.get(k), f, prog["start_url"]) for k, f in fields.items()})
    return row


def act(page, s, pause=1200):
    """Do one recorded step in the page. learn.py uses this too, so what was learned is what replays."""
    from playwright.sync_api import TimeoutError

    css = (s.get("target") or {}).get("css")
    if s.get("optional"):  # e.g. the cookie banner, which does not always show
        try:
            page.locator(css).first.wait_for(state="visible", timeout=6000)
        except TimeoutError:
            return
    if s["do"] == "open":
        page.goto(s["value"], wait_until="domcontentloaded")
    elif s["do"] in ("click", "next_page"):
        page.locator(css).first.click()
    elif s["do"] == "fill":
        page.locator(css).first.focus()
        page.keyboard.type(str(s["value"]), delay=90)
        if s["type"] == "number":
            page.keyboard.press("Enter")
    elif s["do"] == "select":
        option = page.locator(css).get_by_text(s["value"], exact=True).first
        if option.count() and not option.is_visible():  # a closed dropdown: open it first
            page.locator(css).first.click()
        option.click()  # waits for options that are still loading (autocomplete)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(pause)


def via_shortcut(prog, pages):
    sc, fields = prog["shortcut"], prog["item"]["fields"]
    rows = []
    with httpx.Client(headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30) as http:
        for n in range(1, pages + 1):
            params = {**sc["params"], sc["page_param"]: n}
            r = http.request(sc["method"], sc["url"], **({"params": params} if sc["method"] == "GET" else {"json": params}))
            r.raise_for_status()
            got = dig(r.json(), sc["items_path"]) or []
            rows += [{k: dig(x, f.get("json")) for k, f in fields.items()} for x in got]
            last = dig(r.json(), sc.get("pages_path"))
            if not got or (isinstance(last, int) and n >= last):  # past the last page the site returns other listings
                break
    return rows


def via_browser(prog, pages, headed):
    from playwright.sync_api import sync_playwright

    sel, fields = prog["item"]["selector"], prog["item"]["fields"]
    nxt = next(s for s in prog["steps"] if s["do"] == "next_page")
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=not headed)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        for s in prog["steps"]:
            if s["do"] not in ("extract", "next_page"):
                act(page, s, 1200 if headed else 600)
        def settled(before=None):
            """The list is swapped in place by XHR: wait until it differs from `before` and stops changing."""
            page.wait_for_selector(sel, timeout=20000)
            last = None
            for _ in range(40):
                now = page.eval_on_selector_all(sel, READ_CARDS, fields)
                if now == last and now != before:
                    return now
                last = now
                page.wait_for_timeout(700)
            return now

        got = None
        for n in range(pages):
            got = settled(got)
            rows += got
            if n + 1 == pages or not page.locator(nxt["target"]["css"]).count():
                break
            act(page, nxt, 300)
        browser.close()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--headed", action="store_true", help="show Chrome (browser replay only)")
    ap.add_argument("--browser", action="store_true", help="replay the clicks even if a shortcut was learned")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    if not PROGRAM.exists():
        sys.exit(f"No program yet: run teach/learn.py first (it writes {PROGRAM.name}).")
    prog = json.loads(PROGRAM.read_text())

    t = time.time()
    use_shortcut = prog.get("shortcut") and not args.browser
    raw = via_shortcut(prog, args.pages) if use_shortcut else via_browser(prog, args.pages, args.headed)
    secs = time.time() - t
    seen, items = set(), []
    for r in raw:
        row = listing(r, prog)
        if row["url"] not in seen:
            seen.add(row["url"])
            items.append(row)
    args.out.write_text(json.dumps(items, ensure_ascii=False, indent=1))
    mode = "shortcut, 1 request per page" if use_shortcut else "browser replay"
    print(f"{len(items)} listings in {secs:.1f}s = {len(items) / max(secs, 0.001):.1f} listings/s ({mode}) -> {args.out}")


if __name__ == "__main__":
    main()
