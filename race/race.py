"""Race: the compiled program in 8 Chrome windows (no model) next to one click-by-click LLM agent.

    .venv/bin/python race/race.py                  # 60 s: 8 headed windows + 1 agent window (4x2 + agent column, 3x3 on a laptop)
    .venv/bin/python race/race.py --seconds 90 --program teach/tecnocasa.program.json
    .venv/bin/python race/race.py --dry-run        # 2 headless windows for 15 s, agent for 2 steps

Writes data/race.json (or --out) and prints one summary line.
"""
import argparse
import asyncio
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import derive  # noqa: E402  derive.glm(messages) -> (text, cost_usd)

PAGE_GAP = 7.5                      # s between page loads in one window: at most 8 pages a minute
LLM_CAP_S, LLM_CAP_USD = 180, 0.50
CORAL, GREY = "#E86F51", "#6B6862"
DESKTOP_W = 1280                    # every window lays the page out this wide, scaled to fit (see place())
SCALE = {}                          # page -> the scale place() gave it, so the overlay stays readable
MIN_W, MIN_H = 500, 375             # Chrome will not make a window smaller than this
NUMBER_TYPES = {"int", "number"}
# The agent may click around, never contact anyone, log in or accept cookies.
BLOCKED = re.compile(r"contatt|contact|invia|send|chiama|call|telefon|whatsapp|mail|accetta|accept|accedi|login|registr|prenota|mutuo", re.I)

# The frame is drawn from the state Python keeps per page (OVL), fetched over a binding on every new document, so it
# shows on every site the window visits (the homepage during the steps too), not only where it was first set.
OVERLAY = """(() => {
  if (window.top !== window) return;
  const draw = (o) => {
    if (!o || !document.body) return;
    let f = document.getElementById('inky-frame');
    if (!f) {
      const font = document.createElement('link'); font.rel = 'stylesheet';
      font.href = 'https://fonts.googleapis.com/css2?family=Geist:wght@600&display=swap'; document.head.appendChild(font);
      f = document.createElement('div'); f.id = 'inky-frame';
      f.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647;box-sizing:border-box';
      f.innerHTML = '<span style="position:absolute;top:8px;left:8px;padding:5px 12px;border-radius:999px;color:#FFFFFF;font:600 14px/1.3 Geist,-apple-system,system-ui,sans-serif;white-space:nowrap"></span>';
      document.body.appendChild(f);
    }
    f.style.border = (4 / o.k) + 'px solid ' + o.color;
    f.firstChild.style.zoom = 1 / o.k;
    f.firstChild.style.background = o.color;
    f.firstChild.textContent = o.text;
  };
  window.__inkyDraw = draw;
  document.addEventListener('DOMContentLoaded', () => {
    // no Chrome translate bubble over the page: the page says it is not to be translated
    const m = document.createElement('meta'); m.name = 'google'; m.content = 'notranslate'; document.head.appendChild(m);
    window.__inkyState && window.__inkyState().then(draw).catch(() => {});
  });
})();"""
OVL = {}                            # page -> {color, text, k}: what its frame shows

EXTRACT = """(item) => [...document.querySelectorAll(item.selector)].map(el => {
  const o = {};
  for (const [k, f] of Object.entries(item.fields || {})) {
    const e = f.css ? el.querySelector(f.css) : el;
    o[k] = !e ? null : f.attr === 'href' ? e.href : f.attr ? e.getAttribute(f.attr) : e.innerText.trim();
  }
  return o;
})"""

# The site's own page links: the highest page number, and the link with its number turned into {n}.
PAGER = """() => {
  const re = /(pag-|[?&]page=)(\\d+)/;
  const links = [...document.querySelectorAll('a[href]')].map(a => a.href).filter(h => re.test(h));
  return {last: Math.max(1, ...links.map(h => +h.match(re)[2])), url: links.length ? links[0].replace(re, '$1{n}') : null};
}"""

OBSERVE = """() => {
  document.querySelectorAll('a[target]').forEach(a => a.removeAttribute('target'));
  document.querySelectorAll('[data-agent]').forEach(e => e.removeAttribute('data-agent'));
  const els = [...document.querySelectorAll('a[href],button,[role=button],[role=link],[onclick],[id*=close],input[type=submit]')]
    .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !e.closest('#inky-frame'); })
    .slice(0, 120);
  return {
    url: location.href,
    elements: els.map((e, i) => { e.setAttribute('data-agent', i);
      return [i, e.tagName.toLowerCase(), (e.innerText || e.value || e.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ').slice(0, 70), e.href || ''];
    }),
    text: document.body.innerText.replace(/\\n\\s*\\n+/g, '\\n').slice(0, 6000),
  };
}"""


def default_program():
    taught = ROOT / "teach" / "tecnocasa.program.json"
    return taught if taught.exists() else ROOT / "race" / "sample.program.json"


def load_program(path):
    p = json.loads(Path(path).read_text())
    assert p.get("start_url") and (p.get("item") or {}).get("selector"), f"{path}: needs start_url and item.selector"
    return p


def number(s):
    """First number in the string, Italian style: dots are thousands, comma is decimal ("€ 240.000", "1,5")."""
    m = re.search(r"\d[\d.,]*", s or "")  # ponytail: Italian format only; other sites need a per-field format
    if not m:
        return None
    x = float(m.group().rstrip(".,").replace(".", "").replace(",", "."))
    return int(x) if x.is_integer() else x


def typed(rows, fields, base):
    """Raw card strings -> values, same field shape as teach/run_program.py: {css, attr?, type, re?}."""
    out = []
    for r in rows:
        for k, f in fields.items():
            v, t = r.get(k), (f.get("type") or "").lower()
            if v is not None and f.get("re"):
                m = re.search(f["re"], v)
                v = (m.group(1) if m and m.groups() else m.group(0) if m else "").strip()
            r[k] = number(v) if t in NUMBER_TYPES else urljoin(base, v) if t in ("link", "url") and v else v
        if r.get("url") or r.get("title"):
            out.append(r)
    return out


def page_range(last, i, n):
    """Window i of n walks one contiguous slice of pages 1..last."""
    k, r = divmod(last, n)
    start = i * k + min(i, r)
    return list(range(start + 1, start + k + (i < r) + 1))


async def overlay(page, color, text):
    OVL[page] = {"color": color, "text": text, "k": SCALE.get(page, 1)}
    try:
        await page.evaluate("o => window.__inkyDraw && window.__inkyDraw(o)", OVL[page])
    except Exception:
        pass  # page is mid-navigation; the init script draws OVL[page] on load


async def js_click(loc):
    """Click through the DOM, not the mouse: mouse coordinates do not survive the scaled window (see place())."""
    await loc.wait_for(state="attached", timeout=10000)
    await loc.evaluate("e => e.click()")


async def run_steps(page, steps, who):
    """The taught steps replayed with no model, like teach/run_program.py act(). Stops at the first step that fails
    (every later step would only wait and fail too) and returns False; True when every step ran.
    next_page and extract are not replayed: each window jumps to its own pages and reads them with item{}."""
    for s in steps:
        do, v, css = (s.get("do") or "").lower(), s.get("value"), (s.get("target") or {}).get("css")
        try:
            if s.get("optional") and css:  # e.g. the cookie banner, which does not always show
                try:
                    await page.locator(css).first.wait_for(state="visible", timeout=5000)
                except Exception:
                    continue
            if do == "open":
                if v and v != page.url:
                    await page.goto(v, wait_until="domcontentloaded")
            elif do == "click" and css:
                await js_click(page.locator(css).first)
            elif do == "fill" and css:
                await page.locator(css).first.focus(timeout=10000)
                await page.keyboard.type(str(v or ""), delay=60)
                if s.get("type") == "number":
                    await page.keyboard.press("Enter")
            elif do == "select" and css:
                option = page.locator(css).get_by_text(str(v), exact=True).first
                try:
                    await option.wait_for(state="attached", timeout=8000)  # autocomplete suggestions still loading
                except Exception:
                    pass
                if not await option.is_visible():  # a closed dropdown: open it first
                    await js_click(page.locator(css).first)
                await js_click(option)
            else:
                continue
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(600)
        except Exception as e:
            print(f"  {who}: step {s.get('n')} ({s.get('label') or do}) failed: {type(e).__name__}")
            return False
    return True


def squash(x):
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


async def replay(page, program, who, tries=2):
    """Start page + taught steps, started over when a step fails or the results do not show what was typed.
    True when this window reached the right results."""
    item, steps = program["item"], program.get("steps") or []
    typed_in = [squash(s["value"]) for s in steps if s.get("do") == "fill" and s.get("value")]
    for attempt in range(tries):
        await page.goto(program["start_url"], wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("load", timeout=10000)  # the site's own script must be ready before we type
        except Exception:
            pass
        if await run_steps(page, steps, who):
            await cards(page, program)
            # ponytail: "every typed value is in the URL" fits sites that keep filters in the URL (tecnocasa does);
            # a site that does not would compare its first card with the other windows' instead
            if await page.locator(item["selector"]).count() and all(v in squash(page.url) for v in typed_in):
                return True
            print(f"  {who}: steps ended on other results ({page.url[:100]})")
        if attempt + 1 < tries:
            print(f"  {who}: starting the steps over")
    return False


async def cards(page, program):
    """The results are drawn by the page's own script after load: wait for the first card (15 s at most)."""
    try:
        await page.wait_for_selector(program["item"]["selector"], timeout=15000)
    except Exception:
        pass  # an empty page reads as 0 homes


async def compiled_window(page, i, n, program, st):
    """One window: start page, taught steps, then its own slice of result pages. No model anywhere.
    The first window to reach the right results sets the page plan (st["ref"]) for all of them, so the slices line up;
    a window whose steps fail twice still reads its slice, straight from that plan."""
    who = f"window {i + 1}"
    label = lambda note="": overlay(page, CORAL, f"{who} · {st['per_window'][i]} homes{note}")
    where = "steps"
    try:
        await label()
        # program["shortcut"] (a JSON request) is not used here: the race shows the steps replayed in Chrome
        ok = await replay(page, program, who)
        if ok and not st["ref"]:
            pager = await page.evaluate(PAGER)
            st["ref"] = {"first": page.url, "tpl": pager["url"], "last": pager["last"] if pager["url"] else 1}
        if not ok:
            print(f"  {who}: steps failed twice, reading its pages from the plan the other windows found")
            await label(" · waiting")
        while not st["ref"]:
            where = "waiting for a window to reach the results"
            await asyncio.sleep(0.5)
        ref, last_load = st["ref"], time.monotonic()
        mine = page_range(ref["last"], i, n)
        for k, p in enumerate(mine):
            where = f"page {p}"
            url = ref["first"] if p == 1 else ref["tpl"].replace("{n}", str(p))
            if page.url != url:
                if k:  # the first own page follows the steps at once, then one page every PAGE_GAP
                    await asyncio.sleep(max(0.0, last_load + PAGE_GAP - time.monotonic()))
                await page.goto(url, wait_until="domcontentloaded")
                last_load = time.monotonic()
                await cards(page, program)
            rows = typed(await page.evaluate(EXTRACT, program["item"]), program["item"].get("fields") or {}, page.url)
            for r in rows:
                st["seen"].add(r.get("url") or r.get("title"))
            st["per_window"][i] += len(rows)
            st["pages"] += 1
            await label()
        st["done_at"][i] = time.monotonic()
        await label(" · done" if mine else " · no pages left")
    except asyncio.CancelledError:
        print(f"  {who}: still on {where} at the bell")
        await label(" · time")
        raise
    except Exception as e:
        print(f"  {who} stopped: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
        await label(" · stopped")


def on_page(url, obs):
    """The page's own link that the model's listing URL points at (absolute or a tail of it), else None."""
    u = url.strip().rstrip("/")
    if len(urlparse(u).path) < 2:
        return None
    return next((h for _, _, _, h in obs["elements"] if h and h != obs["url"] and h.rstrip("/").endswith(u)), None)


def agent_prompt(goal, obs, history, reported):
    els = "\n".join(json.dumps(e, ensure_ascii=False) for e in obs["elements"])
    return [
        {"role": "system", "content":
            "You are a web-browsing agent controlling one Chrome tab. Each turn you see the page and pick ONE next action. "
            "Rules: close cookie banners with the X (never accept), never fill in forms, never log in, never contact anyone."},
        {"role": "user", "content":
            f"GOAL: {goal}\nLISTINGS YOU REPORTED SO FAR: {reported}\nYOUR LAST ACTIONS: {json.dumps(history[-5:], ensure_ascii=False)}\n"
            f"URL: {obs['url']}\nCLICKABLE ELEMENTS [index, tag, text, href]:\n{els}\nVISIBLE TEXT:\n{obs['text']}\n\n"
            "Answer with one JSON object and nothing else: "
            '{"listings": [{"title", "price_eur", "size_m2", "rooms", "zone", "url"}] for every listing on this page you have not reported yet ([] if none; url copied from the elements list), '
            '"action": "click" | "goto" | "scroll" | "back" | "done", "index": <element index, for click>, "url": <for goto>, "why": <short reason>}'},
    ]


async def llm_agent(page, program, st, deadline, max_steps):
    """A typical click-by-click agent: the model reads the page and picks every action."""
    goal = program.get("goal") or "Find flats for sale in Bari and read as many listings as you can: title, price, size, rooms, neighbourhood, link."
    host = urlparse(program["start_url"]).hostname
    history, fails = [], 0
    page.context.on("page", lambda popup: asyncio.ensure_future(popup.close()))  # no new windows on camera
    status = lambda note: overlay(page, GREY, f"AI agent · {len(st['seen'])} homes · {st['model_calls']} AI calls · ${st['cost_usd']:.3f}{note}")
    try:
        await status("")
        await page.goto(program["start_url"], wait_until="domcontentloaded")
    except Exception as e:
        print(f"  agent could not open start page: {type(e).__name__}", file=sys.stderr)
        return
    while st["model_calls"] < max_steps and time.monotonic() < deadline and st["cost_usd"] < LLM_CAP_USD:
        try:
            await page.wait_for_load_state("load", timeout=8000)
            await page.wait_for_timeout(800)  # let the page's own script draw the results, like any agent waits
            obs = await page.evaluate(OBSERVE)
        except Exception:
            await page.wait_for_timeout(1000)
            continue
        await status(" · thinking")
        try:
            text, cost = await asyncio.to_thread(derive.glm, agent_prompt(goal, obs, history, len(st["seen"])))
        except Exception as e:  # only the type and HTTP status: an httpx header error would print the key
            code = getattr(getattr(e, "response", None), "status_code", "")
            print(f"  agent call failed: {type(e).__name__} {code}".rstrip(), file=sys.stderr)
            fails += 1
            if fails >= 3:
                break
            continue
        st["model_calls"] += 1  # a call counts once the model answered (and billed it)
        st["cost_usd"] += cost or 0
        try:
            reply = json.loads(text[text.find("{"):text.rfind("}") + 1])
            fails = 0
        except ValueError:
            print(f"  AI agent call {st['model_calls']}: no JSON in {text[:200]!r}", file=sys.stderr)
            fails += 1
            if fails >= 3:
                break
            continue
        if time.monotonic() > deadline:
            break  # the answer came in after the bell: its listings do not count
        before = len(st["seen"])
        for l in reply.get("listings") or []:
            # count only a link that is really on the page, stored under that link: not what the model imagines
            real = on_page(str(l.get("url") or "") if isinstance(l, dict) else "", obs)
            if real:
                st["seen"].add(real)
        act, idx = str(reply.get("action") or "").lower(), reply.get("index")
        if act not in ("click", "goto", "scroll", "back", "done"):
            print(f"  AI agent call {st['model_calls']}: no usable action in {text[:200]!r}", file=sys.stderr)
        history.append({"action": act, "index": idx, "url": reply.get("url"), "why": str(reply.get("why") or "")[:100]})
        print(f"  AI agent call {st['model_calls']}: {act} {idx if act == 'click' else reply.get('url') or ''} · +{len(st['seen']) - before} homes · {history[-1]['why']}")
        await status("")
        try:
            if act == "done":
                break
            if act == "click":
                el = next((e for e in obs["elements"] if e[0] == idx), None)
                if el is None or BLOCKED.search(el[2]) or el[3].startswith(("tel:", "mailto:")) or urlparse(el[3]).hostname not in (None, host):
                    history[-1]["result"] = f"not allowed (stay on {host}, no contact, login or cookies) or no such element"
                    continue
                await js_click(page.locator(f'[data-agent="{idx}"]').first)
                await page.wait_for_timeout(1500)
            elif act == "goto":
                if urlparse(str(reply.get("url"))).hostname != host:
                    history[-1]["result"] = f"only {host} is allowed"
                    continue
                await page.goto(reply["url"], wait_until="domcontentloaded")
            elif act == "scroll":
                await page.mouse.wheel(0, 1500)
                await page.wait_for_timeout(500)
            elif act == "back":
                await page.go_back(wait_until="domcontentloaded")
            if urlparse(page.url).hostname != host:  # a script took it off the site: straight back
                history[-1]["result"] = f"left {host}, went back"
                await page.go_back(wait_until="domcontentloaded")
        except Exception as e:
            history[-1]["result"] = f"failed: {type(e).__name__}"
    st["ran_s"] = time.monotonic() - st["t0"]
    await status(" · stopped")


async def place(ctx, page, x, y, w, h):
    """Move the window, then lay the page out DESKTOP_W wide and scale it down to fit.
    The steps were taught on a desktop page; a 270 px window would get the phone layout, where the filters are hidden."""
    cdp = await ctx.new_cdp_session(page)
    try:
        wid = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
        await cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"left": x, "top": y, "width": w, "height": h}})
        await page.wait_for_timeout(300)
    except Exception:
        pass  # headless: position does not matter
    iw, ih = await page.evaluate("[innerWidth, innerHeight]")
    k = min(1.0, iw / DESKTOP_W)
    await cdp.send("Emulation.setDeviceMetricsOverride", {"width": round(iw / k), "height": round(ih / k), "deviceScaleFactor": 0, "mobile": False, "scale": k})
    SCALE[page] = k


def grid(x0, y0, sw, sh, cols, rows, count):
    """count rectangles on a cols x rows grid over the screen. When a cell is below Chrome's minimum window size the
    windows overlap evenly instead: the last row and column still end at the screen's edge."""
    w, h = max(MIN_W, sw // cols), max(MIN_H, sh // rows)
    dx = (sw - w) / (cols - 1) if cols > 1 else 0
    dy = (sh - h) / (rows - 1) if rows > 1 else 0
    return [(x0 + round(i % cols * dx), y0 + round(i // cols * dy), w, h) for i in range(count)]


def layout(x0, y0, sw, sh, n):
    """Window rectangles: n compiled windows, then the agent's."""
    agent_w, cols = max(MIN_W, sw // 5), min(4, n)
    rows = math.ceil(n / cols)
    if (sw - agent_w) // cols >= MIN_W and sh // rows >= MIN_H:  # big screen: the 4x2 grid, the agent in a column on the right
        return grid(x0, y0, sw - agent_w, sh, cols, rows, n) + [(x0 + sw - agent_w, y0, agent_w, sh)]
    cols = math.ceil(math.sqrt(n + 1))  # laptop: one grid of n + 1 windows (3x3), the agent in the last cell
    return grid(x0, y0, sw, sh, cols, math.ceil((n + 1) / cols), n + 1)


async def race(program, n, seconds, headless, llm_seconds, llm_steps):
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=headless, chromium_sandbox=True)
        ctxs, pages = [], []
        for _ in range(n + 1):  # separate contexts: no shared cookies or cache between windows
            ctxs.append(await browser.new_context(no_viewport=True, locale="it-IT"))
            await ctxs[-1].expose_binding("__inkyState", lambda src: OVL.get(src["page"]))
            await ctxs[-1].add_init_script(OVERLAY)
            pages.append(await ctxs[-1].new_page())
        screen = await pages[0].evaluate("[screen.availLeft || 0, screen.availTop || 0, screen.availWidth, screen.availHeight]")
        for c, pg, rect in zip(ctxs, pages, layout(*screen, n)):
            await place(c, pg, *rect)

        t0 = time.monotonic()
        comp = {"per_window": [0] * n, "seen": set(), "pages": 0, "done_at": [None] * n, "ref": None}
        llm = {"seen": set(), "model_calls": 0, "cost_usd": 0.0, "t0": t0, "ran_s": 0.0}
        tasks = [asyncio.create_task(compiled_window(pages[i], i, n, program, comp)) for i in range(n)]
        agent = asyncio.create_task(llm_agent(pages[n], program, llm, t0 + min(llm_seconds, LLM_CAP_S), llm_steps))
        await asyncio.wait(tasks, timeout=seconds)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        comp_s = min(seconds, max(d - t0 for d in comp["done_at"]) if all(comp["done_at"]) else seconds)
        await asyncio.wait([agent], timeout=max(0.0, t0 + llm_seconds - time.monotonic()))
        if not agent.done():  # still thinking at the bell: that answer is waited for (its cost is real) but its listings do not count
            await overlay(pages[n], GREY, f"AI agent · {len(llm['seen'])} homes · {llm['model_calls']} AI calls · time is up")
            await agent
        await asyncio.sleep(0 if headless else 2)  # let the final counters show for the camera
        await browser.close()
    return comp, comp_s, llm


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--program", default=None, help="typed program JSON (default: teach/tecnocasa.program.json, else race/sample.program.json)")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--windows", type=int, default=8)
    ap.add_argument("--out", default=str(ROOT / "data" / "race.json"))
    ap.add_argument("--dry-run", action="store_true", help="2 headless windows for 15 s, agent for 2 steps")
    a = ap.parse_args()
    if a.windows < 1 or a.seconds <= 0:
        ap.error("--windows and --seconds must be at least 1")
    load_dotenv(ROOT / ".env")
    path = Path(a.program) if a.program else default_program()
    try:
        program = load_program(path)
    except (OSError, ValueError, AssertionError) as e:
        ap.error(f"cannot use --program {path}: {e}")
    # dry run: the agent gets its 2 steps however long the model takes (up to the 3 min cap)
    n, seconds, headless, llm_seconds, steps = (2, 15, True, LLM_CAP_S, 2) if a.dry_run else (a.windows, a.seconds, False, a.seconds, 10**6)
    print(f"race: {path} · {n} windows vs 1 AI agent · {seconds:g} s")

    comp, comp_s, llm = asyncio.run(race(program, n, seconds, headless, llm_seconds, steps))
    llm_s = min(llm_seconds, llm["ran_s"]) or seconds
    try:
        prog_ref = str(path.resolve().relative_to(ROOT))
    except ValueError:
        prog_ref = str(path)
    out = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "seconds": seconds,
        "compiled": {"windows": n, "listings": len(comp["seen"]), "per_second": round(len(comp["seen"]) / comp_s, 2),
                     "model_calls": 0, "pages": comp["pages"], "per_window": comp["per_window"], "seconds_used": round(comp_s, 1)},
        "llm": {"listings": len(llm["seen"]), "per_second": round(len(llm["seen"]) / llm_s, 3), "model_calls": llm["model_calls"],
                "cost_usd": round(llm["cost_usd"], 4), "seconds_used": round(llm_s, 1)},
        "program": prog_ref,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    c, l = out["compiled"], out["llm"]
    print(f"{seconds:g} s: program in {n} windows read {c['listings']} listings ({c['per_second']}/s, 0 AI calls) · "
          f"AI agent read {l['listings']} ({l['per_second']}/s, {l['model_calls']} AI calls, ${l['cost_usd']:.3f}) → {a.out}")


if __name__ == "__main__":
    main()
