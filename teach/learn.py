"""Inky learns tecnocasa.it once and writes it down as a typed program.

    .venv/bin/python teach/learn.py              # visible Chrome, 1280x800 (for the video)
    .venv/bin/python teach/learn.py --headless

Uses the site like a person: search Bari, for sale, flats, max price 200000, read the cards, next page.
Every step is recorded as a typed step and marked on the page with a coral border and a chip.
Network traffic is watched: if the cards come from a JSON endpoint, that endpoint is the shortcut.
GLM-5.3 is called once, at the end, to name and type the card fields and label the steps.
Writes teach/tecnocasa.program.json (run it with teach/run_program.py).
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import derive  # noqa: E402  derive.glm: the one GLM-5.3 call
from run_program import act, dig, typed  # noqa: E402  the same executor replays the program

PROGRAM = HERE / "tecnocasa.program.json"
START = "https://www.tecnocasa.it/"
CARD = ".estate-card"

# What a person does on the site. The selectors are what they click; Inky records each as a typed step.
DEMO = [
    ("open", None, START, "link"),
    ("click", ".cookie-banner #close", None, None, "optional"),  # close the banner = only technical cookies
    ("click", ".contract-buttons .btn:nth-child(1)", None, None),  # Vendita
    ("fill", "#geo-autocomplete input", "Bari", "text"),
    ("select", ".geo-autocomplete-results", "Bari (tutto il comune)", "text"),
    ("select", ".filter-type", "Appartamenti", "text"),
    ("click", ".filter-price .toggleFilters", None, None),
    ("fill", ".filter-price .col-6:nth-child(2) input.form-control", "200000", "number"),
    ("extract", CARD, None, "loop"),
    ("next_page", "ul.pagination li:has(a.active) + li a", None, "link"),
]
WANT = {  # field -> (what it is, the type the program needs)
    "title": ("listing title", "text"), "price": ("asking price in euro", "int"), "size_m2": ("floor area in m²", "int"),
    "rooms": ("number of rooms", "int"), "zone": ("the neighbourhood name only, not the street", "text"),
    "url": ("link to the listing page", "link"),
}

# Coral border around the element and a chip with the step, drawn above the page (pointer-events: none).
MARK = """([css, text, option]) => {
  document.querySelectorAll('.inky-mark').forEach(e => e.remove());
  if (!document.getElementById('inky-font')) document.head.insertAdjacentHTML('beforeend',
    '<link id="inky-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@600&display=swap">');
  const add = (style) => { const d = document.createElement('div'); d.className = 'inky-mark';
    d.style.cssText = 'position:absolute;z-index:2147483647;pointer-events:none;box-sizing:border-box;' + style;
    document.body.appendChild(d); return d; };
  let el = css && [...document.querySelectorAll(css)].find(e => e.getClientRects().length);
  const opt = el && option && [...el.querySelectorAll('*')].find(e => e.textContent.trim() === option && e.getClientRects().length);
  if (opt) el = opt;
  const r = el ? el.getBoundingClientRect() : null, x = scrollX, y = scrollY;
  if (r) add(`left:${r.left + x - 4}px;top:${r.top + y - 4}px;width:${r.width + 8}px;height:${r.height + 8}px;` +
             'border:2px solid #E86F51;border-radius:8px');
  const chip = add('padding:4px 9px;border-radius:8px;background:#E86F51;color:#111110;white-space:nowrap;' +
    "font:600 12px/1.4 'Geist Mono',ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.2px");
  chip.textContent = text;
  if (r && r.top > 30) { chip.style.left = (r.left + x - 4) + 'px'; chip.style.top = (r.top + y - 30) + 'px'; }
  else if (r) { chip.style.left = (r.left + x - 4) + 'px'; chip.style.top = (r.bottom + y + 8) + 'px'; }
  else { chip.style.position = 'fixed'; chip.style.left = '16px'; chip.style.top = '16px'; }
}"""

# Role and accessible name of the element, for the program's target.
TARGET = """css => { const el = [...document.querySelectorAll(css)].find(e => e.getClientRects().length) || document.querySelector(css);
  if (!el) return {css, role: null, name: null};
  const role = el.getAttribute('role') || {A: 'link', BUTTON: 'button', INPUT: 'textbox', SELECT: 'combobox', LI: 'option'}[el.tagName] || null;
  const name = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.innerText.replace(/\\s+/g, ' ').trim().slice(0, 60) || null;
  return {css, role, name}; }"""

# Every element in the first 3 cards that carries text or a link, with a css relative to the card.
CANDIDATES = """sel => {
  const out = {};
  for (const card of [...document.querySelectorAll(sel)].slice(0, 8)) {
    for (const el of card.querySelectorAll('*')) {
      const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').replace(/\\s+/g, ' ').trim();
      const href = el.tagName === 'A' ? el.getAttribute('href') : null;
      if (!own && !href) continue;
      let a = el; while (a !== card && !a.classList.length) a = a.parentElement;
      let css = el.tagName.toLowerCase();
      if (a !== card) {  // the rarest class of the nearest element with a class
        const cls = [...a.classList].sort((p, q) => card.getElementsByClassName(p).length - card.getElementsByClassName(q).length)[0];
        const same = a.textContent.replace(/\\s+/g, ' ').trim() === own;  // the classed box holds just this text
        css = '.' + CSS.escape(cls) + (a === el || same ? '' : ' ' + css);
      }
      if (!href && card.querySelectorAll(css).length !== 1) continue;
      (out[css] ||= {css, attr: href ? 'href' : null, samples: []}).samples.push(href || own);
    }
  }
  return Object.values(out);
}"""


def flat(d, pre=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flat(v, f"{pre}{k}."))
        elif not isinstance(v, list):
            out[pre + k] = v
    return out


def find_items(obj, hrefs, path=""):
    """Dotted path to the first list of objects that holds one of the card links."""
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        if any(v in hrefs for x in obj for v in flat(x).values()):
            return path
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = find_items(v, hrefs, f"{path}.{k}" if path else k)
            if p is not None:
                return p
    return None


def find_key(obj, names, path=""):
    # ponytail: known spellings of "last page"; add more when a site uses another
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if k in names and isinstance(v, int):
                return p
            p = find_key(v, names, p)
            if p:
                return p
    return None


def shortcut(seen, hrefs, typed_values):
    """The JSON request behind the cards, from the page-2 load, and one item of it. Clicks become 1 request."""
    hits = [(req, body, find_items(body, hrefs)) for req, body in seen]
    hits = [h for h in hits if h[2] is not None]
    if not hits:
        return None, None
    req, body, items_path = hits[-1]
    u = urlsplit(req["url"])
    params = dict(parse_qsl(u.query)) if req["method"] == "GET" else json.loads(req["post"] or "{}")
    pages = [k for k, v in params.items() if str(v) == "2"]  # we just went to page 2
    page_param = next((k for k in pages if "pag" in k.lower()), pages[0] if pages else None)
    if not page_param:
        return None, None
    params.pop(page_param)
    return [flat(x) for x in dig(body, items_path)], {
        "kind": "json_api", "method": req["method"], "url": f"{u.scheme}://{u.netloc}{u.path}", "params": params,
        "page_param": page_param, "items_path": items_path,
        "pages_path": find_key(body, {"total_pages", "totalPages", "last_page", "lastPage", "page_count", "pageCount"}),
        # which param holds what the person typed, so the actor can change it
        "inputs": {name: k for name, value in typed_values.items() for k, v in params.items() if str(v) == value},
    }


def parses(values, g):
    """Share of the values that are there which the field turns into a typed value."""
    vals = [v for v in values if v not in (None, "")]
    return sum(typed(v, g, START) is not None for v in vals) / max(len(vals), 1)


def check_fields(fields, cands, items):
    """GLM's answer must hold on every card and JSON item we saw (a zone may be missing from an address)."""
    by_css = {c["css"]: c for c in cands}
    out = {}
    for k in WANT:
        f = fields.get(k) or {}
        c = by_css.get(f.get("css"))
        assert c, f"{k}: css {f.get('css')!r} is not one of the card elements"
        assert f.get("type") == WANT[k][1], f"{k}: type must be {WANT[k][1]}"
        if f.get("re"):
            re.compile(f["re"])
        g = {"css": c["css"], "attr": c["attr"], "json": f.get("json"), "type": f["type"], "re": f.get("re") or None}
        g = {key: v for key, v in g.items() if v is not None}
        need = 0.5 if k == "zone" else 1
        bad = [v for v in c["samples"] if v and typed(v, g, START) is None]
        assert parses(c["samples"], g) >= need, f"{k}: css {g['css']} gives nothing for {bad[:3]}"
        if items:
            assert g.get("json") in items[0], f"{k}: json key {g.get('json')!r} is not in the JSON item"
            vals = [x.get(g["json"]) for x in items]
            bad = [v for v in vals if v and typed(v, g, START) is None]
            assert parses(vals, g) >= need, f"{k}: json {g['json']} gives nothing for {bad[:3]}"
        out[k] = g
    return out


def name_fields(steps, cands, items):
    """The one GLM-5.3 call: label the steps, name and type the fields. One retry if the answer does not check out."""
    ask = (
        "A person used tecnocasa.it (Italian real estate site). Recorded steps:\n"
        + json.dumps([{k: s[k] for k in ("n", "do", "value")} | {"target": (s["target"] or {}).get("name")} for s in steps], ensure_ascii=False)
        + "\n\nElements inside one listing card: css relative to the card, samples from 8 cards:\n"
        + json.dumps(cands, ensure_ascii=False)
        + ("\n\nThe same listing in the site's JSON API (dotted keys):\n" + json.dumps(items[0], ensure_ascii=False) if items else "")
        + "\n\nReturn JSON: {\"labels\": {\"<n>\": \"<plain English label, 2 to 5 words, no emoji>\"}, "
        '"fields": {"<name>": {"css": "<one css from the card list>", "json": "<one JSON key, or null if no JSON>", '
        '"type": "text|int|link", "re": "<regex with one capture group taken from the raw text before typing, or null>"}}}\n'
        f"Fields (name: [meaning, type]): {json.dumps(WANT, ensure_ascii=False)}. "
        "int = the first number in the text, dots are thousands separators."
    )
    msgs = [{"role": "system", "content": "You turn a recorded browser session into a typed program. Reply with one JSON object only."},
            {"role": "user", "content": ask}]
    cost, calls = 0.0, 0
    for _ in range(2):
        text, c = derive.glm(msgs)
        cost, calls = cost + (c or 0), calls + 1
        try:
            ans = json.loads(text)
            labels = ans["labels"]
            assert all(labels.get(s["n"]) for s in steps), "a label per step n is missing"
            return {n: str(v)[:60] for n, v in labels.items()}, check_fields(ans["fields"], cands, items), calls, cost
        except (AssertionError, KeyError, TypeError, ValueError, re.error) as e:
            err = str(e)
            msgs += [{"role": "assistant", "content": text}, {"role": "user", "content": f"That does not check out: {err}. Fix it."}]
    sys.exit(f"GLM-5.3 could not name the fields: {err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    load_dotenv(HERE.parent / ".env")
    pause = 600 if args.headless else 1600

    seen, steps, hrefs = [], [], set()

    def on_response(r):
        if r.request.resource_type in ("xhr", "fetch") and "json" in (r.headers.get("content-type") or ""):
            try:
                seen.append(({"method": r.request.method, "url": r.url, "post": r.request.post_data}, r.json()))
            except Exception:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=args.headless)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.on("response", on_response)
        for i, (do, css, value, kind, *optional) in enumerate(DEMO, 1):
            s = {"n": f"{i:02d}", "do": do, "label": "", "target": None, "value": value, "type": kind}
            if optional:
                s["optional"] = True
            if do == "open":
                act(page, s, pause)
            else:
                try:
                    page.wait_for_selector(css, state="attached", timeout=6000 if optional else 20000)
                except Exception:
                    if not optional:
                        raise
                    steps.append(s | {"target": {"css": css, "role": None, "name": None}})
                    continue
                s["target"] = page.evaluate(TARGET, css)
                if do == "select":  # the thing chosen is the option, not the list around it
                    s["target"] |= {"role": "option", "name": value}
            chip = f"{s['n']}  {do}" + (f"  {value}" if value and do != "open" else f"  {page.url}" if do == "open" else "")
            if do == "extract":
                cards = page.eval_on_selector_all(css, "cs => cs.map(c => c.querySelector('a') && c.querySelector('a').href)")
                hrefs.update(h for h in cards if h)
                cands = page.evaluate(CANDIDATES, css)
                chip += f"  {len(cards)} cards"
                s["target"]["name"] = f"{len(cards)} listing cards"
            if do == "select":  # autocomplete options still loading: wait, so the chip lands on the one chosen
                option = page.locator(css).get_by_text(value, exact=True).first
                if not option.count():
                    option.wait_for(state="visible", timeout=15000)
            try:
                page.evaluate(MARK, [css, chip, value if do == "select" else None])
            except Exception:
                pass  # the page is navigating; the chip is only for the video
            page.wait_for_timeout(pause)
            if do not in ("open", "extract"):
                act(page, s, pause)
            if do == "next_page":
                page.wait_for_timeout(2500)
                hrefs.update(h for h in page.eval_on_selector_all(CARD, "cs => cs.map(c => c.querySelector('a') && c.querySelector('a').href)") if h)
            steps.append(s)

        items, sc = shortcut(seen, hrefs, {"max_price": "200000"})
        if sc:
            clicks = sum(s["do"] in ("click", "fill", "select", "next_page") for s in steps)
            page.evaluate(MARK, [None, f"shortcut  {sc['method']} {urlsplit(sc['url']).path}  {clicks} steps became 1 request", None])
        else:
            page.evaluate(MARK, [None, "no JSON shortcut: the program replays the clicks", None])
        page.wait_for_timeout(pause * 2)
        browser.close()

    labels, fields, calls, cost = name_fields(steps, cands, items)
    for s in steps:
        s["label"] = labels[s["n"]]
    program = {
        "site": "tecnocasa.it", "city": "bari", "learned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "start_url": START, "llm_calls": calls, "llm_cost_usd": round(cost, 5), "shortcut": sc, "steps": steps,
        "item": {"selector": CARD, "fields": fields},
    }
    PROGRAM.write_text(json.dumps(program, ensure_ascii=False, indent=1))
    print(f"{len(steps)} steps, {len(fields)} fields, shortcut: {sc['url'] if sc else 'none'}, "
          f"{calls} GLM call(s) ${cost:.4f} -> {PROGRAM}")


if __name__ == "__main__":
    main()
