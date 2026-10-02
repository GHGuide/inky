"""A bot's computer: one thread owning one Playwright browser (Playwright's sync API is single-threaded).
Other threads talk to it through call(). Headless = the bot's own computer, streamed to the app.
Headful = "your screen": a visible window on your desktop, with the coral frame and pill."""
import base64
import re
import concurrent.futures
import queue
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

OVERLAY = (Path(__file__).parent / "overlay.js").read_text(encoding="utf-8")
SELF_PORTS = set()  # the engine's own port: its page carries the key to everything, so a bot's browser never opens it


def is_inky(url):
    """This computer's own Inky (any loopback name on the engine's port)."""
    import ipaddress
    u = urlsplit(str(url or ""))
    host = (u.hostname or "").rstrip(".").lower()
    try:
        port = u.port or (443 if u.scheme == "https" else 80)
    except ValueError:
        return False
    try:
        local = host == "localhost" or host.endswith(".localhost") or ipaddress.ip_address(host).is_loopback or host in ("0.0.0.0", "::")
    except ValueError:
        local = False
    return local and port in SELF_PORTS


def safe_url(url):
    """Bots open web pages and nothing else: not files on this computer, and not Inky itself."""
    u = urlsplit(str(url or "").strip())
    if u.scheme.lower() not in ("http", "https") or not u.hostname:
        raise ValueError(f"Bots only open web addresses (http or https), not “{str(url)[:80]}”.")
    if is_inky(url):
        raise ValueError("That address is Inky itself. Bots never open it.")
    return url
SPEED = {"slow": 0.9, "normal": 0.35, "turbo": 0.0}

INDEX_JS = r"""() => {
  const sel = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],[role=tab],[role=checkbox],[role=menuitem],[onclick],[contenteditable=true]';
  const out = [];
  document.querySelectorAll('[data-inky-idx]').forEach(e => e.removeAttribute('data-inky-idx'));
  const cssPath = (el) => {
    if (el.id && /^[A-Za-z][\w-]*$/.test(el.id)) return '#' + el.id;
    const parts = [];
    while (el && el.nodeType === 1 && el !== document.body && parts.length < 6) {
      let p = el.tagName.toLowerCase();
      if (el.classList.length) p += '.' + [...el.classList].slice(0, 2).map(c => CSS.escape(c)).join('.');
      const sib = el.parentElement ? [...el.parentElement.children].filter(c => c.tagName === el.tagName) : [];
      if (sib.length > 1) p += `:nth-of-type(${sib.indexOf(el) + 1})`;
      parts.unshift(p); el = el.parentElement;
    }
    return parts.join(' > ');
  };
  const labelOf = (el) => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return l.innerText.trim(); }
    const wrap = el.closest('label'); if (wrap) return wrap.innerText.trim();
    return '';
  };
  const roleOf = (el) => {
    const r = el.getAttribute('role'); if (r) return r;
    const t = el.tagName.toLowerCase(), ty = (el.getAttribute('type') || '').toLowerCase();
    if (t === 'a') return 'link';
    if (t === 'button' || t === 'summary' || (t === 'input' && ['submit','button','reset','image'].includes(ty))) return 'button';
    if (t === 'select') return 'combobox';
    if (t === 'textarea') return 'textbox';
    if (t === 'input') return ty === 'checkbox' ? 'checkbox' : ty === 'radio' ? 'radio' : ty === 'password' ? 'password' : 'textbox';
    return 'generic';
  };
  const formOf = (el) => {  // what pressing it would send: a POST form, a sign-in (it has a password box)
    const f = el.form || el.closest('form'); if (!f) return null;
    const ty = (el.getAttribute('type') || '').toLowerCase();
    // one form around the whole page (ASP.NET): only the controls beside this one count, not a newsletter or sign-in box elsewhere
    let near = f;
    if (f.querySelector('input[name=__VIEWSTATE], main, header, nav, footer'))
      for (let g = el.parentElement; g && g !== f; g = g.parentElement)
        if ([...g.querySelectorAll('input:not([type=hidden]), textarea, select, button')].some((x) => x !== el)) { near = g; break; }
    return { post: (f.getAttribute('method') || 'get').toLowerCase() === 'post', password: !!near.querySelector('input[type=password]'),
             personal: !!near.querySelector('textarea, input[type=email], input[type=tel]'),  // a message, an email, a phone number
             submits: el.tagName === 'BUTTON' ? (ty || 'submit') === 'submit' : el.tagName === 'INPUT' && ['submit', 'image'].includes(ty) };
  };
  let i = 0;
  for (const el of document.querySelectorAll(sel)) {
    if (el.closest('inky-overlay')) continue;
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || cs.visibility === 'hidden' || cs.display === 'none' || el.type === 'hidden') continue;
    if (el.checkVisibility && !el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true, contentVisibilityAuto: true})) continue;
    const text = (el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    const name = (labelOf(el) || text || el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('alt') || el.getAttribute('name') || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    el.setAttribute('data-inky-idx', i);
    out.push({ i, tag: el.tagName.toLowerCase(), role: roleOf(el), name, text, type: (el.getAttribute('type') || '').toLowerCase(),
      id: el.id || '', attr_name: el.getAttribute('name') || '', placeholder: el.getAttribute('placeholder') || '',
      href: el.getAttribute('href') || '', css: cssPath(el), value: el.tagName === 'SELECT' ? [...el.options].map(o => o.text).join('|') : '',
      x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
      inview: r.bottom > 0 && r.top < innerHeight, form: formOf(el) });
    i++;
  }
  const heads = [...document.querySelectorAll('h1,h2,h3')].slice(0, 8).map(h => h.innerText.trim()).filter(Boolean);
  const robot = !!document.querySelector('.g-recaptcha,.h-captcha,iframe[src*="captcha"],iframe[title*="CAPTCHA" i],#challenge-form') ||
                /are you a robot|not a robot|sei un robot|verify you are human/i.test(document.body ? document.body.innerText.slice(0, 3000) : '');
  const pw = [...document.querySelectorAll('input[type=password]')].some(e => e.getBoundingClientRect().width > 1);
  return { url: location.href, title: document.title, heads, pw, text: (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').slice(0, 1500), elements: out, robot };
}"""

EXTRACT_JS = r"""(spec) => {
  const items = [...document.querySelectorAll(spec.item)].slice(0, spec.limit || 200);
  return items.map(it => {
    const row = {};
    for (const [k, v] of Object.entries(spec.fields || {})) {
      const [css, attr] = v.split('@');
      const el = css ? it.querySelector(css) : it;
      row[k] = el ? (attr === 'value' ? (el.value || '') : attr ? (el.getAttribute(attr) || '') : el.innerText.trim().replace(/\s+/g, ' ')) : null;
      if (k === 'text' && row[k]) row[k] = row[k].slice(0, 400);
      if ((attr === 'href' || attr === 'src') && row[k]) { try { row[k] = new URL(row[k], location.href).href; } catch (e) {} }
    }
    if ('link' in row && !row.link) {  // a result built a little differently: its own first link
      const a = it.matches('a[href]') ? it : it.querySelector('a[href]');
      if (a) { try { row.link = new URL(a.getAttribute('href'), location.href).href; } catch (e) {} }
    }
    return row;
  });
}"""

LISTS_JS = r"""() => {
  // The lists of results on this page, found from their shape (many siblings alike, each with a link),
  // each with a ready selector spec, so a model only has to pick one.
  const skip = (el) => el.closest('inky-overlay,nav,header,footer,[role=navigation],[role=banner],[role=contentinfo]');
  const cls = (el) => [...el.classList].filter((c) => !/^(active|selected|current|odd|even|first|last|hover|focus|open|show|is-|js-)|\d{3,}/.test(c)).slice(0, 2);
  const sig = (el) => el.tagName.toLowerCase() + cls(el).map((c) => '.' + CSS.escape(c)).join('');
  const CUR = /([$€£¥₽₴]|\b(lei|mdl|eur|usd|ron|zł|pln|kr|chf|rub|uah)\b)\s*\d|\d[\d.,\s]*\s*([$€£¥₽₴]|\b(lei|mdl|eur|usd|ron|zł|pln|kr|chf|rub|uah)\b)/i;
  // a price shops print without the sign: "1.450,00", "1.450,-", "1,450.00" (cents may sit in their own element: "1.450,\n00")
  const BARE = /^\d{1,3}(?:\.\d{3})*,(?:\d{2}|-{1,2}|—)$|^\d{1,3}(?:,\d{3})*\.\d{2}$/;
  const PRICE = { test: (t) => CUR.test(t) || String(t).split('\n').some((l, i, a) => { const x = l.replace(/\s+/g, ''), y = x + (a[i + 1] || '').replace(/\s+/g, '');
    return x.length < 14 && (BARE.test(x) || (/[.,]$/.test(x) && BARE.test(y))); }) };
  const path = (el) => {  // a selector for this element that's short and still points at it
    const parts = [];
    for (let n = el; n && n !== document.body && parts.length < 6; n = n.parentElement) {
      if (n.id && !/\d{3,}/.test(n.id)) { parts.unshift('#' + CSS.escape(n.id)); break; }
      parts.unshift(sig(n));
    }
    return parts.join(' > ');
  };
  const step = (n, k) => n.tagName.toLowerCase() + cls(n).slice(0, k).map((c) => '.' + CSS.escape(c)).join('');
  const relK = (item, el, k) => { const parts = []; for (let n = el; n && n !== item; n = n.parentElement) parts.unshift(step(n, k)); return parts.join(' > '); };
  let peers = [];  // the other results, so a selector is picked that works for most of them, not just the first
  const rel = (item, el) => {  // a selector inside one result: the most specific one that still finds this field in most results
    const cands = [relK(item, el, 2), relK(item, el, 1), step(el, 1), relK(item, el, 0), step(el, 0)].filter((c, i, a) => c && a.indexOf(c) === i && item.querySelector(c) === el);
    if (!cands.length) return el.tagName.toLowerCase();
    const cover = (c) => peers.filter((it) => { try { return it.querySelector(c); } catch (e) { return false; } }).length;
    let best = cands[0], most = cover(best);
    for (const c of cands.slice(1)) { const n = cover(c); if (n > most) { best = c; most = n; } }
    return best;
  };
  const groups = [];
  for (const parent of document.querySelectorAll('body *')) {
    if (parent.children.length < 3 || skip(parent)) continue;
    const by = {};
    for (const k of parent.children) (by[sig(k)] = by[sig(k)] || []).push(k);
    for (const [s, els] of Object.entries(by)) {
      if (els.length < 3) continue;
      const shown = els.filter((e) => { const r = e.getBoundingClientRect(); return r.width > 20 && r.height > 8; });
      const linked = shown.filter((e) => e.matches('a[href]') || e.querySelector('a[href]'));
      const text = shown.reduce((n, e) => n + Math.min((e.innerText || '').trim().length, 300), 0) / Math.max(1, shown.length);
      if (shown.length < 3 || linked.length < shown.length * 0.6 || text < 12) continue;
      const priced = shown.filter((e) => PRICE.test(e.innerText || '')).length / shown.length;
      const imaged = shown.filter((e) => e.querySelector('img')).length / shown.length;
      groups.push({ parent, s, els: shown, score: shown.length * Math.log(5 + text) * (1 + priced * 2) * (1 + imaged * 0.5), priced, text });
    }
  }
  groups.sort((a, b) => b.score - a.score);
  const out = [];
  const GENERIC = /^(dettagli|details?|more|more (info|details)|read more|learn more|view|view (details|more|offer|listing)|see (more|details)|scopri( di più)?|vedi|leggi( tutto)?|mehr|mehr erfahren|details ansehen|plus|en savoir plus|voir( plus)?|ver( más)?|más información|bekijk|meer info|info|open|apri|zobacz|więcej|→|›|»)$/i;
  for (const g of groups.slice(0, 12)) {
    const item = path(g.parent) + ' > ' + g.s;
    if (document.querySelectorAll(item).length < 3 || out.some((o) => o.item === item)) continue;
    const first = g.els[0], fields = {};
    peers = g.els.slice(0, 15);
    const links = [...first.querySelectorAll('a[href]')].concat(first.matches('a[href]') ? [first] : []);
    const head = first.querySelector('h1,h2,h3,h4,h5,h6,[class*=title],[class*=name]');
    // the result's own link goes somewhere different in every result; "more jobs in Worldwide" or a category link repeats
    const differs = (l) => { if (l === first) return peers.length; const c = rel(first, l);
      return new Set(peers.map((it) => { try { const x = it.querySelector(c); return x && x.getAttribute('href'); } catch (e) { return null; } }).filter(Boolean)).size; };
    const ranked = links.map((l, i) => ({ l, i, u: differs(l), h: head && (head.contains(l) || l.contains(head)) ? 1 : 0, t: (l.innerText || '').trim() ? 1 : 0 }))
      .sort((x, y) => y.u - x.u || y.h - x.h || y.t - x.t || x.i - y.i);
    const a = ranked.length ? ranked[0].l : null;
    const atext = a ? (a.innerText || '').trim() : '', ttl = a ? (a.getAttribute('title') || '').trim() : '';
    const sole = head && a && (a.contains(head) || (head.contains(a) && head.querySelectorAll('a[href]').length === 1));
    if (ttl && atext && ttl.toLowerCase().startsWith(atext.replace(/(\.\.\.|…)$/, '').trim().toLowerCase().slice(0, 12)))
      fields.title = (a === first ? '' : rel(first, a)) + '@title';  // a cut-off name whose full name is in its title
    else if (sole) fields.title = rel(first, head);
    else if (a && a !== first && atext.length >= 3 && !(head && GENERIC.test(atext))) fields.title = rel(first, a);  // “Dettagli” names nothing: its heading does
    else if (head) fields.title = rel(first, head);
    else if (a) fields.title = a === first ? '' : rel(first, a);
    if (a) fields.link = (a === first ? '' : rel(first, a)) + '@href';
    // the price: not a discount badge ("€424 korting", "-20%"), not a struck-out old price; the sale/current one when there are two
    const OFF = /korting|discount|rabatt|réduction|sconto|descuento|reducere|bespaar|save|you save|\boff\b|%|was\b|before|vorher|avant|prima/i;
    const OLDW = 'old|was|compare|regular|strike|before|original|list-?price';  // whole words in class names: a random "kOLdPq" isn't one
    const OLD = (e) => { const c = String(e.className || '') + ' ' + String((e.parentElement || {}).className || '');
      return e.closest('del,s,strike') || new RegExp(`(^|[-_\\s])(${OLDW})([-_\\s]|$)`, 'i').test(c) || new RegExp(`(^|[-_\\s])(${OLDW})[A-Z]`).test(c); };
    const priceIn = (it) => {
      const leaves = [...it.querySelectorAll('*')].filter((e) => !e.children.length || [...e.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim()));
      // a price split over a few tiny elements ("1.450," and "00") counts as one
      const small = [...it.querySelectorAll('*')].filter((e) => e.children.length && e.children.length <= 3 && (e.innerText || '').trim().length < 20 && [...e.children].every((c) => !c.children.length));
      const prices = [...leaves, ...small].filter((e) => { const t = (e.innerText || '').trim(); return PRICE.test(t) && t.length < 40 && !OFF.test(t) && !OLD(e); });
      return prices.find((e) => /sale|current|final|now|special|actual|nieuw|new/i.test(String(e.className || '') + ' ' + (e.innerText || ''))) || prices[0]
        || leaves.find((e) => PRICE.test((e.innerText || '').trim()) && (e.innerText || '').trim().length < 40);
    };
    const withPrice = [first, ...peers].find((it) => priceIn(it));  // the first result can be an ad with no price ("Bieden")
    if (withPrice) fields.price = rel(withPrice, priceIn(withPrice));
    if (fields.title !== '') fields.text = '';  // everything the result shows (place, company, tags), for rules like “remote”
    const img = first.querySelector('img');
    if (img) fields.image = rel(first, img) + '@src';
    out.push({ item, fields, count: document.querySelectorAll(item).length, priced: g.priced > 0.5 });
    if (out.length >= 5) break;
  }
  return out;
}"""

SAMPLE_JS = r"""() => {
  // A compact outline of the main content, for the model to pick an item selector from.
  const root = document.querySelector('main') || document.body;
  const lines = [];
  const walk = (el, depth) => {
    if (lines.length > 220 || depth > 9 || el.closest('inky-overlay,nav,header,footer,aside,[role=navigation]')) return;
    const cls = el.classList.length ? '.' + [...el.classList].slice(0, 3).join('.') : '';
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').slice(0, 60);
    lines.push('  '.repeat(depth) + el.tagName.toLowerCase() + cls + (own ? ' "' + own + '"' : '') + (el.getAttribute('href') ? ' href' : ''));
    for (const c of el.children) walk(c, depth + 1);
  };
  walk(root, 0);
  return lines.join('\n');
}"""


class Computer:
    def __init__(self, bot_id, profile_dir, look=None, headful=False, on_frame=None, on_control=None):
        self.bot_id, self.profile_dir = bot_id, str(profile_dir)
        self.look = look or {}
        self.headful = headful
        self.on_frame, self.on_control = on_frame, on_control
        self.q = queue.Queue()
        self.frame = None
        self.frame_cond = threading.Condition()
        self.chat_focused = False
        self.alive = False
        self.started = threading.Event()
        self.error = None
        self.overlay_state = {}
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"computer-{bot_id}")
        self.thread.start()
        self.started.wait(40)
        if self.error:
            raise RuntimeError(self.error)

    # ---- thread
    def _run(self):
        try:
            self.pw = sync_playwright().start()
            args = ["--disable-blink-features=AutomationControlled", "--disable-features=Translate,TranslateUI",
                    "--no-first-run", "--no-default-browser-check", "--hide-crash-restore-bubble",
                    "--disable-session-crashed-bubble"]
            self.ctx = self.pw.chromium.launch_persistent_context(
                self.profile_dir, headless=not self.headful, viewport={"width": 1280, "height": 800}, args=args,
                locale="en-US")
            self.ctx.add_init_script(OVERLAY)
            self.ctx.expose_binding("inkyControl", lambda source, msg: self._control(msg))
            self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
            self.page.on("load", lambda _: self._reapply())
            self._start_screencast()
            self.alive = True
        except Exception as e:  # browser missing, profile locked…
            self.error = f"could not start its browser: {e}"
            self.started.set()
            return
        self.started.set()
        while self.alive:
            try:
                fn, a, kw, fut = self.q.get(timeout=0.05)
            except queue.Empty:
                try:
                    self.page.wait_for_timeout(40)  # pumps Playwright events (screencast, bindings)
                except Exception:
                    time.sleep(0.05)
                continue
            if fn is None:
                break
            try:
                fut.set_result(fn(*a, **kw))
            except Exception as e:
                fut.set_exception(e)
        try:
            self.ctx.close()
            self.pw.stop()
        except Exception:
            pass

    def call(self, _fn, *a, timeout=90, **kw):
        if not self.alive:
            raise RuntimeError("its computer is off")
        fut = concurrent.futures.Future()
        self.q.put((getattr(self, "_" + _fn), a, kw, fut))
        return fut.result(timeout=timeout)

    def close(self):
        if self.alive:
            self.alive = False
            self.q.put((None, (), {}, None))
            self.thread.join(10)

    # ---- screencast
    def _start_screencast(self):
        self.cdp = self.ctx.new_cdp_session(self.page)

        def on_frame(ev):
            data = base64.b64decode(ev["data"])
            with self.frame_cond:
                self.frame = data
                self.frame_cond.notify_all()
            try:
                self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
            except Exception:
                pass
            if self.on_frame:
                self.on_frame(self.bot_id)

        self.cdp.on("Page.screencastFrame", on_frame)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 70, "maxWidth": 1280, "maxHeight": 800})
        self.frame = self.page.screenshot(type="jpeg", quality=70)

    def wait_frame(self, last, timeout=2.0):
        with self.frame_cond:
            if self.frame is last:
                self.frame_cond.wait(timeout)
            return self.frame

    # ---- overlay
    def _control(self, msg):
        if msg.get("type") == "chat_focus":
            self.chat_focused = bool(msg.get("focused"))
            return
        if self.on_control:
            threading.Thread(target=self.on_control, args=(self.bot_id, msg), daemon=True).start()

    def _reapply(self):
        try:
            self.page.evaluate("s => window.__inky && window.__inky.set(s)", self.overlay_state)
        except Exception:
            pass

    def _overlay(self, **patch):
        self.overlay_state.update(patch)
        self._reapply()
        return True

    def _say(self, text):
        self.overlay_state.setdefault("chat", []).append({"role": "bot", "text": text})
        try:
            return self.page.evaluate("t => window.__inky && window.__inky.say(t)", text)
        except Exception:
            return None

    # ---- actions
    def _go(self, page, url):
        """Every navigation a bot makes: only web pages, never Inky itself, even when a site redirects there."""
        page.goto(safe_url(url), wait_until="domcontentloaded", timeout=45000)
        if is_inky(page.url) or page.url.startswith("file:"):
            page.goto("about:blank")
            raise ValueError("That site sent the bot to this computer's own Inky, so it stopped.")

    def _open(self, url):
        self._go(self.page, url)
        self._settle()
        return self._elements()

    def _elements(self):
        return self.page.evaluate(INDEX_JS)

    def _sample(self):
        return self.page.evaluate(SAMPLE_JS)

    def _lists(self):
        """The lists of results on the page, each with a selector spec and its first rows."""
        out = []
        for c in self.page.evaluate(LISTS_JS) or []:
            rows = self.page.evaluate(EXTRACT_JS, {"item": c["item"], "fields": c["fields"], "limit": 200})
            rows = [r for r in rows if any(v for v in r.values())]
            if len(rows) >= 3:
                out.append({**c, "count": len(rows), "rows": rows[:3]})
        return out

    def _settle(self):
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        self.page.wait_for_timeout(250)

    def _point_at(self, el, step_text):
        if not el:
            return
        speed = SPEED.get(self.look.get("speed", "normal"), 0.35)
        cx, cy = el["x"] + el["w"] * 0.6, el["y"] + el["h"] * 0.7
        try:  # the overlay is decoration: a page that blocks it must never stop the step
            self.page.evaluate("([x,y,t,s]) => window.__inky && window.__inky.point(x,y,t,s)",
                               [cx, cy, {k: el[k] for k in ("x", "y", "w", "h")}, step_text])
        except Exception:
            pass
        if speed:
            self.page.wait_for_timeout(int(speed * 1000))

    def _act(self, action, index=None, value=None, step_text="", el=None):
        """Run one step on element `index` (from the latest elements() call)."""
        page = self.page
        loc = page.locator(f'[data-inky-idx="{index}"]').first if index is not None else None
        if loc is not None:
            try:
                loc.scroll_into_view_if_needed(timeout=3000)
                bb = loc.bounding_box()
                if bb:
                    el = dict(el or {}, x=bb["x"], y=bb["y"], w=bb["width"], h=bb["height"])
            except Exception:
                pass
        self._point_at(el, step_text)
        while self.headful and self.chat_focused and action in ("fill", "press", "type"):
            page.wait_for_timeout(200)  # never type while you're typing in the chat
        page.evaluate("window.__inkySynthetic = true")
        try:
            if action == "click":
                loc.click(timeout=10000)
            elif action == "fill":
                loc.fill(str(value or ""), timeout=10000)
            elif action == "select":
                try:
                    loc.select_option(label=str(value), timeout=5000)
                except Exception:
                    loc.select_option(str(value), timeout=5000)
            elif action == "press":
                (loc.press(value or "Enter") if loc is not None else page.keyboard.press(value or "Enter"))
            elif action == "goto":
                self._go(page, value)
            elif action == "wait":
                page.wait_for_timeout(int(float(value or 1) * 1000))
            else:
                raise ValueError(f"unknown action {action}")
            self._settle()
        finally:
            try:
                page.wait_for_timeout(150)
                page.evaluate("window.__inkySynthetic = false")
            except Exception:
                pass
        return {"url": page.url}

    def _extract(self, spec):
        return self.page.evaluate(EXTRACT_JS, spec)

    def _screenshot(self):
        return self.page.screenshot(type="jpeg", quality=70)

    def _url(self):
        return self.page.url

    def _storage_state(self):
        return self.ctx.storage_state()

    def _add_cookies(self, cookies):
        if cookies:
            self.ctx.add_cookies(cookies)
        return True

    # ---- you drive (take over on the bot's own computer)
    def _user(self, kind, x=0, y=0, text="", key=""):
        """Input from the app's live view. Returns the element under a click so "show me once" can record it."""
        page = self.page
        info = None
        if kind == "click":
            info = page.evaluate("""([x,y]) => { const el = document.elementFromPoint(x,y); if (!el) return null;
              const t = el.closest('a,button,input,select,textarea,summary,[role=button],[onclick]') || el;
              t.setAttribute('data-inky-picked','1'); return {tag: t.tagName.toLowerCase(), text: (t.innerText||t.value||'').trim().slice(0,80)} }""", [x, y])
            page.mouse.click(x, y)
            self._settle()
        elif kind == "type":
            page.keyboard.type(text)
        elif kind == "key":
            page.keyboard.press(key)
        elif kind == "scroll":
            page.mouse.wheel(0, y)
        elif kind == "goto":
            local = re.match(r"^(localhost|127\.|10\.|192\.168\.|\d+\.\d+\.\d+\.\d+)", text)  # your own machines rarely have https
            self._go(page, text if "://" in text else ("http://" if local else "https://") + text)
        return info
