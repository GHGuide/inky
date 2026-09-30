"""A bot's computer: one thread owning one Playwright browser (Playwright's sync API is single-threaded).
Other threads talk to it through call(). Headless = the bot's own computer, streamed to the app.
Headful = "your screen": a visible window on your desktop, with the coral frame and pill."""
import base64
import concurrent.futures
import queue
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OVERLAY = (Path(__file__).parent / "overlay.js").read_text()
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
      inview: r.bottom > 0 && r.top < innerHeight });
    i++;
  }
  const heads = [...document.querySelectorAll('h1,h2,h3')].slice(0, 8).map(h => h.innerText.trim()).filter(Boolean);
  const robot = !!document.querySelector('.g-recaptcha,.h-captcha,iframe[src*="captcha"],iframe[title*="CAPTCHA" i],#challenge-form') ||
                /are you a robot|not a robot|sei un robot|verify you are human/i.test(document.body ? document.body.innerText.slice(0, 3000) : '');
  return { url: location.href, title: document.title, heads, text: (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').slice(0, 1500), elements: out, robot };
}"""

EXTRACT_JS = r"""(spec) => {
  const items = [...document.querySelectorAll(spec.item)].slice(0, spec.limit || 200);
  return items.map(it => {
    const row = {};
    for (const [k, v] of Object.entries(spec.fields || {})) {
      const [css, attr] = v.split('@');
      const el = css ? it.querySelector(css) : it;
      row[k] = el ? (attr === 'value' ? (el.value || '') : attr ? (el.getAttribute(attr) || '') : el.innerText.trim().replace(/\s+/g, ' ')) : null;
      if (attr === 'href' && row[k]) { try { row[k] = new URL(row[k], location.href).href; } catch (e) {} }
    }
    return row;
  });
}"""

SAMPLE_JS = r"""() => {
  // A compact outline of the main content, for the model to pick an item selector from.
  const root = document.querySelector('main') || document.body;
  const lines = [];
  const walk = (el, depth) => {
    if (lines.length > 140 || depth > 7 || el.closest('inky-overlay')) return;
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
            args = ["--disable-blink-features=AutomationControlled"]
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
        return self.page.evaluate("t => window.__inky && window.__inky.say(t)", text)

    # ---- actions
    def _open(self, url):
        self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        self._settle()
        return self._elements()

    def _elements(self):
        return self.page.evaluate(INDEX_JS)

    def _sample(self):
        return self.page.evaluate(SAMPLE_JS)

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
        self.page.evaluate("([x,y,t,s]) => window.__inky && window.__inky.point(x,y,t,s)",
                           [cx, cy, {k: el[k] for k in ("x", "y", "w", "h")}, step_text])
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
                page.goto(value, wait_until="domcontentloaded", timeout=45000)
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
        return info
