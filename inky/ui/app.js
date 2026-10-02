// Inky app shell: API, live events, router, sidebar, command bar, toasts.
// This computer's browser gets the token in the page; other devices sign in once with the pairing code.
let TOKEN = document.querySelector('meta[name="inky-token"]').content;
if (!TOKEN || TOKEN.startsWith("__")) { try { TOKEN = localStorage.getItem("inkyToken") || ""; } catch (e) { TOKEN = ""; } }
const $ = (s, el = document) => el.querySelector(s);
const MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = { bots: [], needs: 0, settings: {}, route: "", view: null, pair: "" };

const OFFLINE = "Can’t reach Inky. Is it still running?";
async function api(method, path, body) {
  const r = await fetch(path, { method, headers: { "X-Inky-Token": TOKEN, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body) }).catch(() => { throw new Error(OFFLINE); });  // "Failed to fetch" says nothing
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(data.error || `HTTP ${r.status}`), { status: r.status, data });
  return data;
}
async function download(path, name) {  // header auth, so the token never sits in a link you could copy
  const r = await fetch(path, { headers: { "X-Inky-Token": TOKEN } }).catch(() => null);
  if (!r) return toast(OFFLINE);
  if (!r.ok) return toast(`Couldn’t download (${r.status})`);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([await r.text()], { type: "application/json" }));
  a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
const get = (p) => api("GET", p), post = (p, b = {}) => api("POST", p, b), patch = (p, b) => api("PATCH", p, b), del = (p) => api("DELETE", p);
const screenUrl = (id, kind = "jpg") => `/api/bots/${id}/screen.${kind}?t=${encodeURIComponent(TOKEN)}${kind === "jpg" ? "&_=" + Date.now() : ""}`;

const ICON = {
  link: "M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7 M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7",
  plus: "M12 5v14 M5 12h14", activity: "M3 12h4l3 7 4-14 3 7h4", monitor: "M5 4h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z M8 20h8 M12 16v4",
  models: "M9 3h6 M9 21h6 M3 9v6 M21 9v6 M6 6h12v12H6z M10 10h4v4h-4z", plug: "M9 7V3 M15 7V3 M6 7h12v4a6 6 0 0 1-12 0z M12 17v4",
  spark: "M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z", gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  mic: "M9 3h6v11H9z M5 11a7 7 0 0 0 14 0 M12 18v3", send: "M12 19V5 M6 11l6-6 6 6", phone: "M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z",
  server: "M4 3h16v7H4z M4 14h16v7H4z M8 6.5h.01 M8 17.5h.01", lock: "M6 11h12v10H6z M8 11V7a4 4 0 0 1 8 0v4", menu: "M4 6h16 M4 12h16 M4 18h16",
  store: "M3 9l1.5-5h15L21 9 M3 9h18v11H3z M9 20v-6h6v6", check: "M5 12l5 5 9-10", x: "M6 6l12 12 M18 6L6 18", keys: "M3 6h18v12H3z M7 10h.01 M11 10h.01 M15 10h.01 M7 14h10",
  users: "M16 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1 M9.5 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7 M21 19v-1a4 4 0 0 0-3-3.8 M15.5 4.2a3.5 3.5 0 0 1 0 6.6",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z M20 20l-4-4",
  mouse: "M12 3a6 6 0 0 1 6 6v6a6 6 0 0 1-12 0V9a6 6 0 0 1 6-6z M12 7v4",
  speaker: "M11 5L6 9H2v6h4l5 4z M15.5 8.5a5 5 0 0 1 0 7 M19 5a10 10 0 0 1 0 14", micoff: "M9 9v2a3 3 0 0 0 5.1 2.1 M15 9.3V6a3 3 0 0 0-5.9-.8 M5 11a7 7 0 0 0 11.9 5 M12 18v3 M3 3l18 18",
};
// Real brand marks (inky/ui/logos, sources in SOURCES.md). One-colour marks are tinted with the brand colour
// through a CSS mask; multi-colour ones (colour: null) are shown as they are.
const LOGOS = {
  claude: ["Claude Code", "#D97757"], anthropic: ["Anthropic", "#191919"], openai: ["OpenAI", "#111110"],
  codex: ["Codex", "#111110", "openai"], openrouter: ["OpenRouter", "#6467F2"], googlegemini: ["Google Gemini", "#8E75B2"],
  groq: ["Groq", null], xai: ["xAI", "#111110"], mistral: ["Mistral AI", "#FA520F"], ollama: ["Ollama", "#111110"],
  lmstudio: ["LM Studio", "#111110"], mcp: ["MCP", "#111110"], n8n: ["n8n", "#EA4B71"], apify: ["Apify", null],
  telegram: ["Telegram", "#26A5E4"], github: ["GitHub", "#181717"], docker: ["Docker", "#2496ED"], linux: ["Linux", "#111110"],
  tailscale: ["Tailscale", "#242424"], apple: ["Apple", "#111110"], windows: ["Windows", "#0078D4"],
};
const PROVIDER_LOGO = { openrouter: "openrouter", anthropic: "anthropic", openai: "openai", gemini: "googlegemini", groq: "groq",
  xai: "xai", mistral: "mistral", ollama: "ollama", custom: "server", telegram: "telegram", apify: "apify", n8n: "n8n", lmstudio: "lmstudio" };
function logo(slug, size = 34) {
  if (slug === "server") return `<span class="logo" role="img" aria-label="Your own server" style="width:${size}px;height:${size}px">${icon("server", Math.round(size * 0.5))}</span>`;
  const L = LOGOS[slug];
  if (!L) return `<span class="logo lm" style="width:${size}px;height:${size}px">${esc(String(slug || "?")[0].toUpperCase())}</span>`;
  const [name, color, file = slug] = L, m = Math.round(size * 0.6), url = `/logos/${file}.svg`;
  const mark = color ? `<i style="width:${m}px;height:${m}px;background:${color};-webkit-mask:url(${url}) center/contain no-repeat;mask:url(${url}) center/contain no-repeat"></i>`
    : `<img src="${url}" alt="" width="${m}" height="${m}">`;
  return `<span class="logo" role="img" aria-label="${esc(name)}" style="width:${size}px;height:${size}px">${mark}</span>`;
}
const providerLogo = (name, size) => logo(PROVIDER_LOGO[name] || name, size);

const icon = (n, s = 17, w = 2) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ICON[n]}"/></svg>`;
const STATUS = { working: ["working", "#2F9E5B"], learning: ["learning", "#E86F51"], paused: ["paused", "#8E8A83"], needs_you: ["needs you", "#E86F51"],
  idle: ["idle", "#C9C5BD"], moved: ["on another computer", "#3B5BDB"], takeover: ["you have control", "#B5482A"], showing: ["showing it once", "#B5482A"] };
function botMeta(b) {
  const [t, c] = STATUS[b.status] || [b.status, "#C9C5BD"];
  let meta = t;
  if (b.status === "working" || b.status === "learning") meta = b.site ? `${b.status === "learning" ? "learning" : "checking"} ${b.site}${b.sites_to_go > 1 ? ` · ${b.sites_to_go - 1} more after` : ""}` : t;  // the site, not the model's step: "Click to reveal" reads like an order
  else if (b.status === "idle" && b.held) meta = "paused · runs when you ask";
  else if (b.status === "idle" && b.next_run) {
    const d = new Date(b.next_run * 1000), days = Math.round((new Date(d.toDateString()) - new Date(new Date().toDateString())) / 864e5);
    meta = `next run ${days === 0 ? "today" : days === 1 ? "tomorrow" : d.toLocaleDateString(undefined, { weekday: "long" })} at ${d.toTimeString().slice(0, 5)}`;
  }
  else if (b.status === "idle" && !b.skills.length) meta = "hasn’t learned yet";
  else if (b.status === "moved") meta = b.needs ? `needs you · on ${b.remote || "another computer"}` : `on ${b.remote || "another computer"}`;
  return { meta, color: b.status === "moved" && b.needs ? STATUS.needs_you[1] : c, hot: b.status === "needs_you" || (b.status === "moved" && b.needs > 0) };
}
const ago = (ts) => { const s = Date.now() / 1000 - ts; return s < 60 ? "now" : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? new Date(ts * 1000).toTimeString().slice(0, 5) : new Date(ts * 1000).toLocaleDateString(undefined, { weekday: "short" }); };
const hhmm = (ts) => new Date(ts * 1000).toTimeString().slice(0, 5);

function toast(text, b) {
  text = text || "Something went wrong.";  // an error without a message still says something
  const box = $("#toasts"), key = `${b ? b.id : 0}|${text}`;
  if ([...box.children].some((t) => t.dataset.key === key && !t.classList.contains("out"))) return;  // the same message once
  const el = document.createElement("div");
  el.className = "toast"; el.dataset.key = key;
  el.innerHTML = `${b ? botCritter(b, 30) : critter("octopus", "#E86F51", "none", 30)}<div><b>${esc(b ? b.name : "Inky")}</b><br>${esc(text)}</div><button class="tx" aria-label="Dismiss">${icon("x", 14)}</button>`;
  const bye = () => { if (el.classList.contains("out")) return; el.classList.add("out"); setTimeout(() => el.remove(), 260); };
  $(".tx", el).onclick = bye;
  el.onclick = (e) => { if (!getSelection().toString()) bye(); };  // selecting its text doesn't close it
  let left = 6000, t0 = Date.now(), timer = setTimeout(bye, left);
  const hold = () => { clearTimeout(timer); left -= Date.now() - t0; };
  const go = () => { t0 = Date.now(); timer = setTimeout(bye, Math.max(left, 1500)); };
  el.onmouseenter = hold; el.onmouseleave = go; el.onfocusin = hold; el.onfocusout = go;  // reading it pauses the clock
  box.appendChild(el);
  while (box.children.length > 3) box.firstChild.remove();  // a burst of events never buries the page
}
const needsText = () => (S.needs ? `${S.needs} need${S.needs === 1 ? "s" : ""} you` : "Nothing needs you");

const calmMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
function confetti(x = innerWidth / 2, y = innerHeight / 3) {  // a small burst for milestones
  if (calmMotion()) return;
  const c = document.createElement("canvas"), g = c.getContext("2d"), dpr = devicePixelRatio || 1;
  c.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:200";
  c.width = innerWidth * dpr; c.height = innerHeight * dpr; g.scale(dpr, dpr);
  document.body.appendChild(c);
  const colors = ["#E86F51", "#E9A23B", "#2BA59B", "#7C6CF2", "#3B5BDB", "#F07BA8"];
  const ps = Array.from({ length: 40 }, (_, i) => ({ x, y, vx: Math.cos(i * 2.4) * (3 + (i % 5)), vy: -4 - (i % 7), r: 3 + (i % 3), c: colors[i % colors.length], a: i }));
  const t0 = performance.now();
  (function frame(t) {
    const k = (t - t0) / 1400;
    g.clearRect(0, 0, innerWidth, innerHeight);
    for (const p of ps) {
      p.x += p.vx; p.y += p.vy; p.vy += 0.25; p.a += 0.2;
      g.save(); g.globalAlpha = Math.max(0, 1 - k); g.translate(p.x, p.y); g.rotate(p.a); g.fillStyle = p.c; g.fillRect(-p.r, -p.r / 2, p.r * 2, p.r); g.restore();
    }
    if (k < 1) requestAnimationFrame(frame); else c.remove();
  })(t0);
}

// ---------------------------------------------------------------- life: what just happened drives each critter's mood
const RECENT = (window.RECENT = {});
let knockFor = null;
function feel(m) {
  if (!m.bot) return;
  const r = (RECENT[m.bot] = RECENT[m.bot] || {}), bot = S.bots.find((b) => b.id === m.bot);
  if (m.kind === "results" && m.new > 0) { r.results = Date.now(); SOUND.play("plip", bot); LIFE.forBot(m.bot, "results"); if (bot) appNotify(bot, bot.name, `${m.new} new`, `#/bot/${bot.id}/results`); }
  if (m.kind === "event" && m.ev === "learned") { r.learned = Date.now(); SOUND.play("rise", bot); LIFE.forBot(m.bot, "learned"); }
  if (m.kind === "event" && m.ev === "fixed") r.fixed = Date.now();
  if (m.kind === "event" && m.ev === "replay" && /pass your rules|^Done in/.test(m.text || "")) SOUND.play("chime", bot);
  if (m.kind === "needs") knockFor = bot;  // loadState knocks if the count went up
  if (m.kind === "level") { r.learned = Date.now(); SOUND.play("rise", bot); confetti(); toast(`Unlocked the ${m.acc}!`, bot); }
}
let moodKey = "";
setInterval(() => {  // moods fade back to calm without any event
  const k = S.bots.map((b) => moodOf(b, RECENT)).join();
  if (k === moodKey) return;
  moodKey = k; renderNav(); if (canRefresh()) S.view.refresh();
}, 30e3);
function canRefresh() {  // never redraw a page under your hands: form pages opt out (live:false), and nothing redraws while you type
  const v = S.view;
  if (!v || !v.refresh || v.live === false || BAR || BUDDY) return false;
  if (v.live === true) return true;  // the page keeps its own inputs across a redraw
  const a = document.activeElement;
  return !(a && a.closest && a.closest("#view") && /INPUT|TEXTAREA|SELECT/.test(a.tagName));
}

// ---------------------------------------------------------------- away time, for "While you were away"
const seenKey = "inkyLastSeen";
const markSeen = () => { try { localStorage.setItem(seenKey, String(Date.now() / 1000)); } catch (e) {} };
function awaySince() {  // when the app was last seen, if that was 2+ hours ago (read once per page load)
  if (awaySince.v === undefined) { let t = 0; try { t = +localStorage.getItem(seenKey) || 0; } catch (e) {} awaySince.v = t && Date.now() / 1000 - t > 7200 ? t : 0; }
  return awaySince.v;
}
const clearAway = () => { awaySince.v = 0; markSeen(); };
awaySince();
setInterval(() => { if (!document.hidden) markSeen(); }, 60e3);
addEventListener("visibilitychange", () => { if (document.hidden) markSeen(); else if (Date.now() / 1000 - (+localStorage.getItem(seenKey) || 0) > 7200) { awaySince.v = undefined; awaySince(); } });
addEventListener("pagehide", markSeen);

// ---------------------------------------------------------------- live events
let refreshTimer = null;
function refreshSoon(ms = 250) {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(async () => { await loadState(); if (S.view && S.view.drawLive && S.view.data) S.view.drawLive(); if (canRefresh()) S.view.refresh(); }, ms);
}
setInterval(() => $$("[data-since]").forEach((x) => (x.textContent = `${Math.max(0, Math.round(Date.now() / 1000 - +x.dataset.since))} s`)), 1000);  // how long a model has been thinking
document.addEventListener("click", async (e) => {  // the sidebar's Stop: cut off what the models are doing now
  if (!e.target.closest("#stopmodel")) return;
  const r = await post("/api/models/stop", {}).catch((err) => ({ error: err.message }));
  toast(r.error || (r.stopped ? "Stopped the model. The runs it was thinking for stopped too." : "Nothing was thinking."));
  refreshSoon();
});
function listen() {
  const es = new EventSource(`/api/events?t=${encodeURIComponent(TOKEN)}`);
  es.onmessage = (e) => {
    const m = JSON.parse(e.data);
    // the open bot page already shows its own news
    if (m.kind === "notify" && S.settings.notify_app !== false && !location.hash.startsWith(`#/bot/${m.bot}/`)) toast(m.text, S.bots.find((b) => b.id === m.bot));
    feel(m);
    if (S.view && S.view.onEvent) S.view.onEvent(m);
    refreshSoon(m.kind === "run" ? 400 : 150);
  };
  es.onerror = () => { es.close(); setTimeout(listen, 2000); };
}

async function loadState() {
  const st = await get("/api/state");
  if (knockFor && S.settings && st.needs > S.needs) { SOUND.play("knock", knockFor); appNotify(knockFor, `${knockFor.name} needs you`, "Open Inky to decide.", "#/needs"); }
  knockFor = null;
  Object.assign(S, { bots: st.bots, needs: st.needs, settings: st.settings, pair: st.pair_code, today: st.today, engine: st.engine, setupDone: st.setup_done, engineId: st.engine_id || S.engineId, thinking: st.thinking || [] });
  renderNav();
  if (APP && !BAR && !BUDDY) invoke("tray", { needs: S.needs, bots: S.bots.map((b) => ({ id: b.id, name: b.name, status: b.status })), buddy: S.settings.buddy !== false });
  if (BUDDY) drawBuddy();
}

// the app tells you about new things when its window isn't in front (and never in quiet hours)
function appNotify(bot, title, body, hash) {
  if (!APP || BAR || BUDDY || (document.hasFocus() && !document.hidden) || S.settings.notify_app === false) return;
  if (bot && inQuiet(bot.schedule, new Date())) return;
  invoke("notify", { title, body, hash });
}

// "Send me a test": alerts reach you before you rely on them (in the app: the system notification; in a browser: the browser's)
async function testNotify() {
  const title = "Inky", body = "This is how your bots will tell you about new things.";
  if (APP) { invoke("notify", { title, body, hash: "#/bots" }); return toast("Sent. If nothing showed up, allow notifications for Inky in your system settings."); }
  if (!("Notification" in window)) return toast("This browser can't show notifications. Use the Inky app, or Telegram in More → Phone.");
  const ok = Notification.permission === "granted" || (await Notification.requestPermission()) === "granted";
  if (!ok) return toast("Notifications are blocked for this page. Allow them in the browser's site settings.");
  new Notification(title, { body });
}

// double-clicking an .inky bot file (or .inkyskill) in Finder/Explorer
async function importFile(text) {
  let d;
  try { d = JSON.parse(text); } catch (e) { return toast("That file isn’t a bot file (it isn’t valid JSON)."); }
  try {
    if (d.inky_skill) {
      const id = location.hash.match(/#\/bot\/(\d+)/);
      if (!id) return toast("Open a bot first, then open the file again.");
      await post(`/api/bots/${id[1]}/skills/import`, d); toast("Added"); return refreshSoon();
    }
    const r = await post("/api/import", d);
    await loadState(); location.hash = `#/bot/${r.bot.id}/computer?hatch=1`;
  } catch (e) { toast(e.message); }
}

// buddy mode (?buddy=1): a critter that peeks in from the screen edge when a bot needs you, and says what about.
// Its bubble opens Needs you; × (or right-click → Hide) hides it until something new needs you; right-click → Turn off stops it.
async function drawBuddy() {
  const b = S.bots.find((x) => x.status === "needs_you" || x.needs > 0);
  if (!b) { $("#view").innerHTML = ""; return; }
  const needs = (await get("/api/needs").catch(() => ({ needs: [] }))).needs || [];
  const n = needs.find((x) => x.bot_id === b.id) || needs[0];
  const more = Math.max(0, (S.needs || needs.length) - 1);
  $("#view").innerHTML = `<div class="buddywrap">
      <div class="bubble" id="bbub"><button class="bx" id="bhide" aria-label="Hide until something new needs you" title="Hide until something new needs you">×</button>
        <b>${esc(b.name)} needs you</b><span>${esc(clip((n && n.title) || "Open Inky to see what it is.", 90))}</span>${more ? `<span class="muted">and ${more} more</span>` : ""}
        <button class="bopen" id="bopen">${n && n.kind === "decision" ? "Decide" : "Open"}</button></div>
      <div class="bmenu hidden" id="bmenu" role="menu"><button role="menuitem" data-b="open">Open Inky</button><button role="menuitem" data-b="hide">Hide until something new</button><button role="menuitem" data-b="off">Turn off the buddy</button></div>
      <button class="buddy" id="bcrit" title="${esc(b.name)} needs you. Right-click for options." aria-label="${esc(b.name)} needs you">${botCritter(b, 92)}</button></div>`;
  const open = () => invoke("open_needs"), hide = () => invoke("buddy_snooze");
  const off = async () => { await post("/api/settings", { buddy: false }).catch(() => {}); hide(); };
  $("#bopen").onclick = open; $("#bcrit").onclick = open; $("#bhide").onclick = hide;
  const menu = $("#bmenu");
  document.oncontextmenu = (e) => { e.preventDefault(); menu.classList.toggle("hidden"); $("#bbub").classList.toggle("hidden", !menu.classList.contains("hidden")); };
  $$("[data-b]", menu).forEach((x) => (x.onclick = () => ({ open, hide, off })[x.dataset.b]()));
  document.onkeydown = (e) => { if (e.key === "Escape") { menu.classList.add("hidden"); $("#bbub").classList.remove("hidden"); } };
}

// ---------------------------------------------------------------- sidebar
const MORE = ["#/library", "#/models", "#/keys", "#/activity", "#/team", "#/computers", "#/connectors", "#/look", "#/settings"];  // everything past the basics, folded away
function renderNav() {
  const r = location.hash;
  const on = (h) => (r.startsWith(h) ? " on" : ""), nav = $("#nav");
  const html = `<button class="iconbtn navclose" aria-label="Close menu">${icon("x")}</button>
    <a class="brand" href="#/bots">${critter("octopus", "#E86F51", "none", 26)}<b>inky</b><span class="os">open source</span></a>
    <a class="newbot" href="#/new">${icon("plus", 16, 2.2)}New bot</a>
    <div class="navlabel">Bots</div>
    <div class="navbots">${S.bots.map((b) => { const m = botMeta(b); return `<a class="navbot${on("#/bot/" + b.id + "/")}" href="#/bot/${b.id}/${b.skills.length ? "results" : "computer"}" data-bot="${b.id}">
      <span class="av">${botCritter(b, 26)}<i class="${["working", "learning"].includes(b.status) ? "live" : ""}" style="background:${m.color}"></i></span>
      <span class="t"><span title="${esc(b.name)}">${esc(b.name)}</span><small class="${m.hot ? "hot" : ""}">${esc(m.meta)}</small></span></a>`; }).join("") || `<span class="small muted" style="padding:4px 10px">No bots yet</span>`}</div>
    <div class="navbottom">
      ${(S.thinking || []).length ? `<div class="thinking" role="status"><span class="livedot" aria-hidden="true"></span><span class="t small"><b class="mono">${esc(S.thinking[0].model)}</b> is thinking${S.thinking[0].name ? ` for ${esc(S.thinking[0].name)}` : ""} · <span data-since="${S.thinking[0].since}">${Math.round(Date.now() / 1000 - S.thinking[0].since)} s</span>${S.thinking.length > 1 ? ` · ${S.thinking.length - 1} more` : ""}</span><button class="iconbtn" id="stopmodel" aria-label="Stop the model" title="Stop the model">${icon("x", 14)}</button></div>` : ""}
      <a class="navlink needlink${S.needs ? "" : " calm"}${on("#/needs")}" href="#/needs"><i></i>${needsText()}</a>
      <details class="navmore"${MORE.some((h) => r.startsWith(h)) ? " open" : ""}><summary class="navlink">${icon("menu")}More</summary>
        <a class="navlink${on("#/library")}" href="#/library">${icon("store")}Library: ready-made bots</a>
        <a class="navlink${r.startsWith("#/models") || r.startsWith("#/keys") ? " on" : ""}" href="#/models">${icon("models")}Models and keys</a>
        <a class="navlink${on("#/activity")}" href="#/activity">${icon("activity")}Activity</a>
        <a class="navlink${on("#/team")}" href="#/team">${icon("users")}Team</a>
        <a class="navlink${on("#/computers")}" href="#/computers">${icon("monitor")}Computers</a>
        <a class="navlink${on("#/connectors")}" href="#/connectors">${icon("plug")}Connectors</a>
        <a class="navlink${on("#/look")}" href="#/look">${icon("spark")}Make it yours</a>
        <a class="navlink${on("#/settings")}" href="#/settings">${icon("gear")}Settings</a></details>
    </div>`;
  if (html === nav._html) return;  // live events re-render a lot: an unchanged sidebar keeps its focus and scroll
  const f = nav.contains(document.activeElement) && document.activeElement.getAttribute("href"), top = $(".navbots") ? $(".navbots").scrollTop : 0;
  nav.innerHTML = nav._html = html;
  $(".navbots").scrollTop = top;
  $$("a.on", nav).forEach((a) => a.setAttribute("aria-current", "page"));
  if (f && $(`a[href="${f}"]`, nav)) $(`a[href="${f}"]`, nav).focus();
}
function openNav() {  // phones: the sidebar slides over the page
  $("#nav").classList.add("open"); $("#app").classList.add("navopen");
  $$("[aria-controls=nav]").forEach((b) => b.setAttribute("aria-expanded", "true"));
  $(".navclose").focus();
}
function closeNav() {
  if (!$("#nav").classList.contains("open")) return;
  const back = $("#nav").contains(document.activeElement);
  $("#nav").classList.remove("open"); $("#app").classList.remove("navopen");
  $$("[aria-controls=nav]").forEach((b) => b.setAttribute("aria-expanded", "false"));
  if (back && $(".mobilebar [aria-controls=nav]")) $(".mobilebar [aria-controls=nav]").focus();
}

// ---------------------------------------------------------------- router
const VIEWS = Object.create(null);  // so #/constructor isn't a page
const homeLink = `<a class="btn p" href="#/bots" style="align-self:flex-start">Go to your bots</a>`;
const NOTFOUND = { show(el) { el.innerHTML = `${mobileBar("Not found")}<div class="page narrow"><h1>Page not found</h1><p class="lede">There’s no page at ${esc(location.hash)}.</p>${homeLink}</div>`; } };
function mobileBar(title) {
  return `<div class="mobilebar"><button class="iconbtn" data-act="openNav" aria-label="Menu" aria-controls="nav" aria-expanded="false">${icon("menu")}</button><b>${esc(title || "Inky")}</b>
  <span class="grow"></span><button class="iconbtn" data-act="openCmd" aria-label="Ask a bot or describe a job">${icon("search")}</button><a class="btn s${S.needs ? " hot" : ""}" href="#/needs">${needsText()}</a></div>`;
}
let routedHash = null;
const viewDirty = () => !!(S.view && typeof S.view.dirty === "function" && !S.view.leaving && S.view.dirty());
async function route() {
  const h = location.hash || "#/bots";
  if (routedHash && h !== routedHash && viewDirty()) {  // unsaved changes (back, forward, a typed address): ask before leaving
    const back = routedHash;
    history.replaceState(null, "", back);  // stay put while you decide (no redraw, nothing lost)
    if (!(await confirmBox(S.view.leaveText ? S.view.leaveText() : "Leave without saving your changes?", "Leave", true))) return;
    S.view.leaving = true;  // you chose to leave (its show() resets this)
    history.replaceState(null, "", h);
  }
  routedHash = h;
  if (!S.setupDone && !h.startsWith("#/setup") && !sessionStorage.getItem("skipSetup")) { location.hash = "#/setup/1"; return; }
  const [, name, ...rest] = h.split(/[/?]/);
  const qs = new URLSearchParams(h.split("?")[1] || "");
  if (CMD.open && !BAR) closeCmd();  // a new page never sits under an old command bar
  if (S.view && S.view.leave) S.view.leave();
  const v = name ? VIEWS[name] || NOTFOUND : VIEWS.bots, prev = S.view;
  S.view = v;
  $("#app").classList.toggle("bare", !!v.bare);
  $("#nav").style.display = v.bare ? "none" : "";
  closeNav(); renderNav();
  const cur = $("#nav .navbot.on"); if (cur) cur.scrollIntoView({ block: "nearest" });  // the bot you opened is in view in the list
  const el = $("#view").cloneNode(false);  // fresh node per route: a slow render of the last view lands on a detached one
  let shown;
  const swap = () => {
    $("#view").replaceWith(el);
    shown = (async () => {
      try {
        await v.show(el, rest.filter(Boolean), qs);
        MOTION.enter(el);
      } catch (e) {
        el.innerHTML = `${mobileBar("Inky")}<div class="page"><h1>Something went wrong</h1><p class="lede">${esc((e && e.message) || "Something went wrong.")}</p>${homeLink}</div>`;
      }
      if (document.activeElement === document.body && el.isConnected) el.focus({ preventScroll: true });  // keyboard users land in the page (#view has tabindex=-1)
      const h = el.isConnected && $("h1", el);  // the window and tab say where you are
      document.title = v !== VIEWS.bots && h && h.textContent.trim() ? `${h.textContent.trim().slice(0, 60)} · Inky` : "Inky";
    })();
    return Promise.race([shown, new Promise((r) => setTimeout(r, 300))]);  // a slow page never freezes the screen mid-transition
  };
  if (document.startViewTransition && !calmMotion() && !(prev === v && v === VIEWS.bot)) {
    const t = document.startViewTransition(swap);
    t.ready.catch(() => {}); t.finished.catch(() => {});  // skipped or cut short: the page still shows, just without the slide
    await t.updateCallbackDone.catch(() => {});
  } else swap();
  await shown;
}
document.addEventListener("click", async (e) => {  // a link away from unsaved changes asks first, before the address changes
  const a = e.target.closest && e.target.closest('a[href^="#/"]');
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || a.getAttribute("href") === location.hash || !viewDirty()) return;
  e.preventDefault();
  const v = S.view, href = a.getAttribute("href");
  if (!(await confirmBox(v.leaveText ? v.leaveText() : "Leave without saving your changes?", "Leave", true)) || S.view !== v) return;
  v.leaving = true;  // you chose to leave (its show() resets this)
  location.hash = href;
}, true);
addEventListener("beforeunload", (e) => { if (viewDirty()) { e.preventDefault(); e.returnValue = ""; } });
window.addEventListener("hashchange", () => {
  if (!BAR) return route();
  if (location.hash !== "#/bar") { native({ type: "open", hash: location.hash }); history.replaceState(null, "", "?bar=1#/bar"); }
});
document.addEventListener("click", (e) => {
  if (e.target.closest(".skip")) { e.preventDefault(); $("#view").focus(); }  // not a real #view link: the hash is the router's
  if (e.target.id === "app" || e.target.closest("#nav a, .navclose")) closeNav();  // #app itself is only hit on the phone menu's backdrop
  const b = e.target.closest("[data-dl]"); if (b) { e.preventDefault(); download(b.dataset.dl, b.dataset.name); }
  const a = e.target.closest("a[target=_blank]");  // in the app, outside links open in your own browser
  if (a && APP && /^https?:/.test(a.href)) { e.preventDefault(); invoke("open_url", { url: a.href }); }
});

// ---------------------------------------------------------------- command bar (⌘K, Ctrl+K, Alt+Space)
const CMD = { open: false, sel: 0, items: [] };
function mention(q) {  // "@Flat Hunter check now" (full name, longest first) or "@flat check now" → {bot, text, named}
  q = String(q || "").trim();
  if (!q.startsWith("@")) return { bot: null, text: q, named: null };
  const rest = q.slice(1), low = rest.toLowerCase();
  const full = [...S.bots].sort((a, b) => b.name.length - a.name.length)
    .find((b) => low === b.name.toLowerCase() || low.startsWith(b.name.toLowerCase() + " "));
  if (full) return { bot: full, text: rest.slice(full.name.length).trim(), named: full.name };
  const [w, ...more] = rest.split(/\s+/);
  const byWord = w ? S.bots.filter((b) => b.name.toLowerCase().split(/\s+/)[0].startsWith(w.toLowerCase())) : [];
  return { bot: byWord.length === 1 ? byWord[0] : null, text: more.join(" ").trim(), named: w || "", ambiguous: byWord.length > 1, matches: byWord };
}
const TOUCH = matchMedia("(hover: none) and (pointer: coarse)").matches;  // phones: no keyboard, so no key hints
function cmdItems(q) {
  q = q.trim();
  const m = mention(q), at = q.startsWith("@"), text = at ? (m.named ? m.text : "") : q, items = [], kb = (k) => (TOUCH ? "" : k);
  const lead = (d) => `<span style="width:26px;height:26px;border-radius:8px;background:rgba(255,255,255,.08);display:flex;align-items:center;justify-content:center">${icon(d, 15)}</span>`;
  // open the page first and send without waiting for the reply, so a later click still wins
  const send = (sec) => (b) => items.push({ sec, label: esc(b.name), lead: botCritter(b, 26), k: botMeta(b).meta,
    run: () => { location.hash = `#/bot/${b.id}/computer`; if (text) post(`/api/bots/${b.id}/chat`, { text, source: "command bar" }).catch((e) => toast(e.message, b)); } });
  if (at) {  // an @name picks the bot; nothing is ever sent to a bot you didn't name
    if (m.bot) send("SEND TO")(m.bot);
    else if (m.ambiguous || !m.named) (m.ambiguous ? m.matches : S.bots).forEach(send("SEND TO"));
    else items.push({ sec: "SEND TO", label: `No bot called “${esc(m.named)}”`, lead: lead("x"), k: "", noop: true });
  }
  const act = (label, k, d, run, make) => items.push({ sec: at ? "OR" : "ACTIONS", label, k, lead: lead(d), run, make });
  if (/^inky:\/\//i.test(text)) return [{ sec: "LINK", label: "Open this Inky link", k: "↵", lead: lead("link"), run: () => handleLink(text) }];  // a pasted share or pair link
  act(text ? `Make a new bot: “${esc(text.slice(0, 60))}”` : "Make a new bot", kb(MAC ? "⌘ ↵" : "Ctrl ↵"), "plus", () => (location.hash = `#/new?job=${encodeURIComponent(text)}`), true);
  act("Open Needs you", `${S.needs}`, "check", () => (location.hash = "#/needs"));
  act("Pause all bots", kb(BAR ? "⌃ ⌥ P" : "⌥ P"), "activity", () => pauseAll());
  act('<span style="color:#F2957C">Stop everything on my screen</span>', APP ? "⌃ ⌥ Esc" : "", "x", () => stopScreens());
  act("Models and keys", "", "models", () => (location.hash = "#/models"));
  act("Connectors · Claude Code, Codex", "", "plug", () => (location.hash = "#/connectors"));
  act("Library · agents other people made", "", "store", () => (location.hash = "#/library"));
  if (!at) S.bots.forEach(send(text ? "OR SEND TO" : "BOTS"));  // below the actions: a bot gets your text only when you pick it
  if (text && !at) {  // “open needs”, “models”: the page you named comes first, before making a bot of it
    const words = text.toLowerCase().split(/\s+/).filter((w) => w.length > 1);
    const hit = (it) => it.sec === "ACTIONS" && !it.make && words.length && words.every((w) => it.label.replace(/<[^>]+>/g, "").toLowerCase().includes(w));
    const hits = items.filter(hit);
    if (hits.length) return [...hits.map((it) => ({ ...it, sec: "GO TO" })), ...items.filter((it) => !hit(it))];
  }
  return items;
}
async function pauseAll() {
  const busy = S.bots.filter((b) => ["working", "learning"].includes(b.status));
  for (const b of busy) await post(`/api/bots/${b.id}/control`, { cmd: "pause" });
  toast(busy.length ? `Paused ${busy.length === 1 ? busy[0].name : `${busy.length} bots`}` : "Nothing was running"); refreshSoon();
}
async function stopScreens() {
  const on = S.bots.filter((b) => b.mode === "screen" && ["working", "learning", "paused"].includes(b.status));
  for (const b of on) await post(`/api/bots/${b.id}/control`, { cmd: "stop" });
  toast(on.length ? "Stopped every bot on your screen" : "No bot was on your screen"); refreshSoon();
}
const shortcut = (what = "the command bar") => TOUCH ? `tap the search button for ${what}` : `${MAC ? "⌘K" : "Ctrl+K"} opens ${what}`;  // hints that fit this device
function renderCmd() {
  const q = $("#cmdq") ? $("#cmdq").value : "";
  CMD.items = cmdItems(q);
  CMD.sel = Math.min(CMD.sel, CMD.items.length - 1);
  let sec = "";
  $("#cmdlist").innerHTML = CMD.items.map((it, i) => {
    const head = it.sec !== sec ? `<div class="sec">${(sec = it.sec)}</div>` : "";
    return `${head}<div class="it${i === CMD.sel ? " on" : ""}" id="cmdi${i}" data-i="${i}" role="option" aria-selected="${i === CMD.sel}">${it.lead}<span>${it.label}</span><span class="k">${esc(it.k || "")}</span></div>`;
  }).join("");
  $$("#cmdlist .it").forEach((el) => {
    el.addEventListener("click", () => { CMD.sel = +el.dataset.i; runCmd(); });
    el.addEventListener("mousemove", () => { if (CMD.sel !== +el.dataset.i) pickCmd(+el.dataset.i); });
  });
  pickCmd(CMD.sel);
  const on = $("#cmdlist .it.on"); if (on) on.scrollIntoView({ block: "nearest" });
}
function pickCmd(i) {  // the mouse moves the selection without redrawing (and scrolling) the list under it
  CMD.sel = i;
  $$("#cmdlist .it").forEach((x) => { x.classList.toggle("on", +x.dataset.i === i); x.setAttribute("aria-selected", +x.dataset.i === i); });
  if ($("#cmdq")) $("#cmdq").setAttribute("aria-activedescendant", `cmdi${i}`);
}
let cmdReturn = null;
function openCmd(prefill = "") {
  if (!CMD.open) cmdReturn = document.activeElement;
  CMD.open = true;
  CMD.sel = 0;  // reopening always starts at the top
  const c = $("#cmd");
  c.classList.remove("hidden");
  c.innerHTML = `<div class="cmdbox"><div class="in"><b>›</b><label class="vh" for="cmdq">Ask a bot or describe a job</label><input id="cmdq" placeholder="Ask a bot (@name) or describe a new job…" autocomplete="off" value="${esc(prefill)}" role="combobox" aria-controls="cmdlist" aria-expanded="true">${TOUCH ? `<button class="iconbtn cmdx" aria-label="Close">${icon("x", 15)}</button>` : `<span class="mono small" style="color:var(--faint)">${MAC ? (BAR ? "⌥ Space" : "⌘ K") : BAR ? "Alt Space" : "Ctrl K"}</span>`}</div>
    <div id="cmdlist" role="listbox" aria-label="Suggestions"></div>
    ${TOUCH ? "" : `<div class="foot"><span>↵ choose · ${MAC ? "⌘" : "Ctrl"} ↵ new bot · ↑↓ move</span><span>esc close</span></div>`}</div>`;
  c.onclick = (e) => { if (e.target === c || e.target.closest(".cmdx")) closeCmd(); };
  const inp = $("#cmdq");
  inp.addEventListener("input", () => { CMD.sel = 0; renderCmd(); });
  inp.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { CMD.sel = (CMD.sel + 1) % CMD.items.length; renderCmd(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { CMD.sel = (CMD.sel - 1 + CMD.items.length) % CMD.items.length; renderCmd(); e.preventDefault(); }
    else if (e.key === "Enter") { if (e.metaKey || e.ctrlKey) CMD.sel = CMD.items.findIndex((x) => x.make); runCmd(); e.preventDefault(); }
    else if (e.key === "Escape") { e.stopPropagation(); closeCmd(); }
    else if (e.key === "Tab") { CMD.sel = (CMD.sel + (e.shiftKey ? CMD.items.length - 1 : 1)) % CMD.items.length; renderCmd(); e.preventDefault(); }
  });
  renderCmd();
  inp.focus();
  requestAnimationFrame(() => inp.focus());
}
// Bar mode (?bar=1): the macOS menu bar app shows just the command bar in a floating panel.
const BAR = new URLSearchParams(location.search).has("bar"), BUDDY = new URLSearchParams(location.search).has("buddy");
const APP = !!(window.__TAURI__ && window.__TAURI__.core);  // inside the Inky desktop app
const invoke = (cmd, args) => (APP ? window.__TAURI__.core.invoke(cmd, args).catch((e) => { console.warn("inky app:", cmd, e); return null; }) : Promise.resolve(null));
const native = (m) => (APP ? invoke("bar", { msg: m }) : null);
const openOut = (url) => (APP ? invoke("open_url", { url }) : window.open(url, "_blank", "noopener"));  // your own browser
function closeCmd() {
  CMD.open = false; $("#cmd").classList.add("hidden");
  if (BAR) native({ type: "hide" });
  else if (cmdReturn && document.contains(cmdReturn) && cmdReturn.focus) cmdReturn.focus();
  cmdReturn = null;
}
async function runCmd() { const it = CMD.items[CMD.sel]; if (!it || it.noop) return; closeCmd(); try { await it.run(); } catch (e) { toast(e.message); } }
document.addEventListener("keydown", (e) => {
  const inField = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName), navOpen = $("#nav").classList.contains("open");
  if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.code === "Space" && e.altKey)) { e.preventDefault(); CMD.open ? closeCmd() : openCmd(); }
  else if (e.code === "KeyP" && e.altKey && !inField) { e.preventDefault(); pauseAll(); }
  else if (e.key === "Escape" && CMD.open) closeCmd();
  else if (e.key === "Tab" && CMD.open) { if (document.activeElement !== $("#cmdq")) trapTab($("#cmd"), e); }  // in the input, Tab moves the selection
  else if (e.key === "Escape" && !$("#modal").classList.contains("hidden")) closeModal();
  else if (e.key === "Tab" && !$("#modal").classList.contains("hidden")) trapTab($("#modal"), e);
  else if (e.key === "Escape" && navOpen) closeNav();
  else if (e.key === "Tab" && navOpen) trapTab($("#nav"), e);
});

let modalReturn = null;
function modal(html, onmount, onclose) {  // onclose: runs however it closes (a button, Esc, a click outside)
  const m = $("#modal");
  if (m.classList.contains("hidden")) modalReturn = document.activeElement;
  m.classList.remove("hidden");
  m.innerHTML = `<div class="box">${html}</div>`;
  const h = $("h2", m);
  if (h) { h.id = "modalh"; m.setAttribute("aria-labelledby", "modalh"); } else m.removeAttribute("aria-labelledby");
  m._onclose = onclose;
  m.onclick = (e) => { if (e.target === m) closeModal(); };
  if (onmount) onmount(m);
  const first = m.querySelector("input:not([type=hidden]):not([readonly]),textarea,select") || m.querySelector("button,a[href]");
  if (first) requestAnimationFrame(() => first.focus());
}
function trapTab(root, e) {  // Tab stays inside a dialog
  const f = [...root.querySelectorAll("button:not([disabled]),a[href],input:not([disabled]),textarea,select,summary,[tabindex]:not([tabindex='-1'])")].filter((x) => x.offsetParent);
  if (!f.length) return;
  const i = f.indexOf(document.activeElement);
  if (e.shiftKey && i <= 0) { f[f.length - 1].focus(); e.preventDefault(); }
  else if (!e.shiftKey && (i === -1 || i === f.length - 1)) { f[0].focus(); e.preventDefault(); }
}
function confirmBox(text, ok = "OK", danger = false, detail = "") {  // detail: the exact change, shown as code
  return new Promise((res) => {
    modal(`<h2>${esc(text)}</h2>${detail ? `<pre class="code" style="max-height:40vh;overflow:auto">${esc(detail)}</pre>` : ""}<div class="row" style="justify-content:flex-end"><button class="btn" id="cno">Cancel</button><button class="btn ${danger ? "hot" : "p"}" id="cyes">${esc(ok)}</button></div>`, () => {
      $("#cno").onclick = () => closeModal();
      $("#cyes").onclick = () => { res(true); closeModal(); };
    }, () => res(false));
  });
}
window.handleLink = async (link) => {  // inky:// links the desktop app hands over (from install.sh, a browser, a friend)
  let u; try { u = new URL(link); } catch (e) { return toast("Inky can’t open that link."); }
  if (u.host === "pair") {  // same checks as the engine (connect.parse_pair_link), before asking you anything
    let host = ""; try { const t = new URL(u.searchParams.get("url")); if (/^https?:$/.test(t.protocol)) host = t.host; } catch (e) {}
    if (!host || !/^[a-z0-9]{4,12}$/i.test((u.searchParams.get("code") || "").trim())) return toast("That pair link is incomplete.");
    if (!(await confirmBox(`Pair with the Inky at ${host}?`, "Pair"))) return;
    try { const r = await post("/api/computers", { url: link }); SOUND.play("chime"); toast(`Paired with ${r.name || host}. Its bots show up in Computers.`); location.hash = "#/computers"; }
    catch (e) { toast(e.message); }
    return;
  }
  if (u.host === "install") return u.searchParams.get("url") ? getAgent(u.searchParams.get("url")) : toast("That install link is incomplete.");
  if (u.host === "agent") return u.searchParams.get("d") ? getAgent(link) : toast("That share link is incomplete.");  // the agent is inside the link
  toast("Inky can’t open that link.");
};
document.addEventListener("click", (e) => {  // buttons drawn as HTML say what they do in data-act (no inline handlers: the page's security policy forbids them)
  const b = e.target.closest("[data-act]");
  const act = b && { openNav, openCmd: () => openCmd(), closeModal }[b.dataset.act];
  if (act) { e.preventDefault(); act(); }
});

function closeModal() {
  const m = $("#modal");
  if (m.classList.contains("hidden")) return;
  m.classList.add("hidden"); m.innerHTML = "";
  const cb = m._onclose; m._onclose = null;
  if (cb) cb();
  if (modalReturn && modalReturn.focus && document.contains(modalReturn)) modalReturn.focus();
  if (modalReturn && document.activeElement !== modalReturn) {  // it was in a menu that closed: its menu button, else the page
    const menu = modalReturn.closest && modalReturn.closest("details");
    const to = menu && $("summary", menu);
    if (to && document.contains(to)) to.focus(); else if (!document.activeElement || document.activeElement === document.body) $("#view") && $("#view").focus();
  }
  modalReturn = null;
}

function getBrowser() {  // first launch of the app: the bots' browser downloads once (~170 MB)
  $("#app").classList.add("bare"); $("#nav").style.display = "none";
  $("#view").innerHTML = `<div class="page" style="max-width:520px;margin:14vh auto;text-align:center;align-items:center">${critter("octopus", "#E86F51", "none", 110, "curious")}
    <h1>Getting your bots a browser…</h1><p class="lede">Each bot uses its own private browser. It downloads once, about 250 MB.</p>
    <div class="mono small muted" id="blog" style="min-height:20px">Starting…</div><button class="btn hidden" id="bretry">Try again</button></div>`;
  const go = () => { $("#bretry").classList.add("hidden"); post("/api/setup/browser").catch((e) => { $("#blog").textContent = e.message; $("#bretry").classList.remove("hidden"); }); };
  S.view = { onEvent(m) {
    if (m.kind !== "browser") return;
    $("#blog").textContent = m.line;
    if (m.done && m.ok) setTimeout(() => location.reload(), 600);
    else if (m.done) $("#bretry").classList.remove("hidden");
  } };
  $("#bretry").onclick = go;
  go();
}

function signIn(why) {
  $("#app").classList.add("bare"); $("#nav").style.display = "none";
  $("#view").innerHTML = `<div class="page" style="max-width:420px;margin:12vh auto"><h1>Sign in to this Inky</h1>
    <p class="lede">${esc(why || "Type the 6-letter pairing code shown on the computer running Inky (Computers page, or printed when it starts).")}</p>
    <form id="pairf" class="col"><label class="l" for="pc">Pairing code</label><input class="f mono" id="pc" maxlength="6" autocomplete="one-time-code" autofocus>
    <button class="btn p">Sign in</button></form></div>`;
  $("#pairf").onsubmit = async (e) => {
    e.preventDefault();
    const r = await fetch("/api/pair", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: $("#pc").value.trim() }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) return signIn(d.error === "wrong code" ? "That code didn’t match. Try again." : d.error);
    try { localStorage.setItem("inkyToken", d.token); } catch (err) {}
    location.reload();
  };
}

window.addEventListener("load", async () => {
  LIFE.start();
  if (!TOKEN) return signIn();
  get("/api/ping").then((p) => { S.engineId = p.id; }).catch(() => {});  // this engine's id: which bots on a server moved there from here
  try { await loadState(); } catch (e) {
    if (String(e.message).includes("401") || String(e.message).includes("token")) { try { localStorage.removeItem("inkyToken"); } catch (err) {} return signIn(); }
    throw e;
  }
  listen();
  if (!BAR && !BUDDY && !(await get("/api/setup/browser").catch(() => ({ ready: true }))).ready) return getBrowser();
  if (BUDDY) { document.body.classList.add("buddymode"); window.inkyBuddy = () => loadState(); return drawBuddy(); }
  if (!BAR) return route();
  document.body.classList.add("bar");
  window.inkyBarOpen = async () => { await loadState(); CMD.sel = 0; openCmd(); return true; };
  openCmd();
});
