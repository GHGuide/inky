// Inky app shell: API, live events, router, sidebar, command bar, toasts.
// This computer's browser gets the token in the page; other devices sign in once with the pairing code.
let TOKEN = document.querySelector('meta[name="inky-token"]').content;
if (!TOKEN || TOKEN.startsWith("__")) { try { TOKEN = localStorage.getItem("inkyToken") || ""; } catch (e) { TOKEN = ""; } }
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = { bots: [], needs: 0, settings: {}, route: "", view: null, pair: "" };

async function api(method, path, body) {
  const r = await fetch(path, { method, headers: { "X-Inky-Token": TOKEN, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}
async function download(path, name) {  // header auth, so the token never sits in a link you could copy
  const r = await fetch(path, { headers: { "X-Inky-Token": TOKEN } });
  if (!r.ok) return toast(`Couldn’t download (${r.status})`);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([await r.text()], { type: "application/json" }));
  a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
const get = (p) => api("GET", p), post = (p, b = {}) => api("POST", p, b), patch = (p, b) => api("PATCH", p, b), del = (p) => api("DELETE", p);
const screenUrl = (id, kind = "jpg") => `/api/bots/${id}/screen.${kind}?t=${encodeURIComponent(TOKEN)}${kind === "jpg" ? "&_=" + Date.now() : ""}`;

const ICON = {
  plus: "M12 5v14 M5 12h14", activity: "M3 12h4l3 7 4-14 3 7h4", monitor: "M5 4h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z M8 20h8 M12 16v4",
  models: "M9 3h6 M9 21h6 M3 9v6 M21 9v6 M6 6h12v12H6z M10 10h4v4h-4z", plug: "M9 7V3 M15 7V3 M6 7h12v4a6 6 0 0 1-12 0z M12 17v4",
  spark: "M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z", gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  mic: "M9 3h6v11H9z M5 11a7 7 0 0 0 14 0 M12 18v3", send: "M12 19V5 M6 11l6-6 6 6", phone: "M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z",
  server: "M4 3h16v7H4z M4 14h16v7H4z M8 6.5h.01 M8 17.5h.01", lock: "M6 11h12v10H6z M8 11V7a4 4 0 0 1 8 0v4", menu: "M4 6h16 M4 12h16 M4 18h16",
  store: "M3 9l1.5-5h15L21 9 M3 9h18v11H3z M9 20v-6h6v6", check: "M5 12l5 5 9-10", x: "M6 6l12 12 M18 6L6 18", keys: "M3 6h18v12H3z M7 10h.01 M11 10h.01 M15 10h.01 M7 14h10",
  speaker: "M11 5L6 9H2v6h4l5 4z M15.5 8.5a5 5 0 0 1 0 7 M19 5a10 10 0 0 1 0 14", micoff: "M9 9v2a3 3 0 0 0 5.1 2.1 M15 9.3V6a3 3 0 0 0-5.9-.8 M5 11a7 7 0 0 0 11.9 5 M12 18v3 M3 3l18 18",
};
const icon = (n, s = 17, w = 2) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ICON[n]}"/></svg>`;
const STATUS = { working: ["working", "#2F9E5B"], learning: ["learning", "#E86F51"], paused: ["paused", "#8E8A83"], needs_you: ["needs you", "#E86F51"],
  idle: ["idle", "#C9C5BD"], moved: ["on another computer", "#3B5BDB"] };
function botMeta(b) {
  const [t, c] = STATUS[b.status] || [b.status, "#C9C5BD"];
  let meta = t;
  if (b.status === "working" || b.status === "learning") meta = b.step ? `${t} · ${b.step}` : t;
  else if (b.status === "idle" && b.next_run) {
    const d = new Date(b.next_run * 1000), today = new Date().toDateString() === d.toDateString();
    meta = `next run ${today ? "" : d.toLocaleDateString(undefined, { weekday: "short" }) + " "}${d.toTimeString().slice(0, 5)}`;
  }
  else if (b.status === "idle" && !b.skills.length) meta = "hasn’t learned yet";
  return { meta, color: c, hot: b.status === "needs_you" };
}
const ago = (ts) => { const s = Date.now() / 1000 - ts; return s < 60 ? "now" : s < 3600 ? `${Math.floor(s / 60)} min` : s < 86400 ? new Date(ts * 1000).toTimeString().slice(0, 5) : new Date(ts * 1000).toLocaleDateString(undefined, { weekday: "short" }); };
const hhmm = (ts) => new Date(ts * 1000).toTimeString().slice(0, 5);

function toast(text, b) {
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = `${b ? botCritter(b, 30) : critter("octopus", "#E86F51", "none", 30)}<div><b>${esc(b ? b.name : "Inky")}</b><br>${esc(text)}</div>`;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 6000);
}

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
  if (m.kind === "results" && m.new > 0) { r.results = Date.now(); SOUND.play("plip", bot); }
  if (m.kind === "event" && m.ev === "learned") { r.learned = Date.now(); SOUND.play("rise", bot); }
  if (m.kind === "event" && m.ev === "fixed") r.fixed = Date.now();
  if (m.kind === "event" && m.ev === "replay" && /pass your rules|^Done in/.test(m.text || "")) SOUND.play("chime", bot);
  if (m.kind === "needs") knockFor = bot;  // loadState knocks if the count went up
}
let moodKey = "";
setInterval(() => {  // moods fade back to calm without any event
  const k = S.bots.map((b) => moodOf(b, RECENT)).join();
  if (k === moodKey) return;
  moodKey = k; renderNav(); if (S.view && S.view.refresh && !BAR) S.view.refresh();
}, 30e3);

// ---------------------------------------------------------------- live events
let refreshTimer = null;
function refreshSoon(ms = 250) {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(async () => { await loadState(); if (S.view && S.view.refresh) S.view.refresh(); }, ms);
}
function listen() {
  const es = new EventSource(`/api/events?t=${encodeURIComponent(TOKEN)}`);
  es.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.kind === "notify" && S.settings.notify_app !== false) toast(m.text, S.bots.find((b) => b.id === m.bot));
    feel(m);
    if (S.view && S.view.onEvent) S.view.onEvent(m);
    refreshSoon(m.kind === "run" ? 400 : 150);
  };
  es.onerror = () => { es.close(); setTimeout(listen, 2000); };
}

async function loadState() {
  const st = await get("/api/state");
  if (knockFor && S.settings && st.needs > S.needs) SOUND.play("knock", knockFor);
  knockFor = null;
  Object.assign(S, { bots: st.bots, needs: st.needs, settings: st.settings, pair: st.pair_code, today: st.today, engine: st.engine, setupDone: st.setup_done });
  renderNav();
}

// ---------------------------------------------------------------- sidebar
function renderNav() {
  const r = location.hash;
  const on = (h) => (r.startsWith(h) ? " on" : "");
  $("#nav").innerHTML = `
    <a class="brand" href="#/bots">${critter("octopus", "#E86F51", "none", 26)}<b>inky</b><span class="os">open source</span></a>
    <a class="newbot" href="#/new">${icon("plus", 16, 2.2)}New bot</a>
    <div class="navlabel">Bots</div>
    ${S.bots.map((b) => { const m = botMeta(b); return `<a class="navbot${on("#/bot/" + b.id + "/")}" href="#/bot/${b.id}/computer" data-bot="${b.id}">
      <span class="av">${botCritter(b, 26)}<i style="background:${m.color}"></i></span>
      <span class="t"><span>${esc(b.name)}</span><small class="${m.hot ? "hot" : ""}">${esc(m.meta)}</small></span></a>`; }).join("") || `<span class="small muted" style="padding:4px 10px">No bots yet</span>`}
    <div class="navbottom">
      <a class="navlink needlink${on("#/needs")}" href="#/needs"><i></i>${S.needs} need you</a>
      <a class="navlink${on("#/activity")}" href="#/activity">${icon("activity")}Activity</a>
      <a class="navlink${on("#/computers")}" href="#/computers">${icon("monitor")}Computers</a>
      <a class="navlink${r.startsWith("#/models") || r.startsWith("#/keys") ? " on" : ""}" href="#/models">${icon("models")}Models</a>
      <a class="navlink${on("#/connectors")}" href="#/connectors">${icon("plug")}Connectors</a>
      <a class="navlink${on("#/look")}" href="#/look">${icon("spark")}Make it yours</a>
      <a class="navlink${on("#/settings")}" href="#/settings">${icon("gear")}Settings</a>
      <a class="navfoot" href="#/connectors">${icon("plug", 14)}<span>Claude Code · Codex · MCP</span></a>
    </div>`;
  $("#nav").classList.remove("open");
}

// ---------------------------------------------------------------- router
const VIEWS = {};
function mobileBar(title) {
  return `<div class="mobilebar"><button class="iconbtn" onclick="document.getElementById('nav').classList.add('open')" aria-label="Menu">${icon("menu")}</button><b>${esc(title || "Inky")}</b>
  <span class="grow"></span><a class="btn s" href="#/needs">${S.needs} need you</a></div>`;
}
async function route() {
  const h = location.hash || "#/bots";
  if (!S.setupDone && !h.startsWith("#/setup") && !sessionStorage.getItem("skipSetup")) { location.hash = "#/setup/1"; return; }
  const [, name, ...rest] = h.split(/[/?]/);
  const qs = new URLSearchParams(h.split("?")[1] || "");
  if (S.view && S.view.leave) S.view.leave();
  const v = VIEWS[name] || VIEWS.bots, prev = S.view;
  S.view = v;
  $("#app").classList.toggle("bare", !!v.bare);
  $("#nav").style.display = v.bare ? "none" : "";
  renderNav();
  const el = $("#view").cloneNode(false);  // fresh node per route: a slow render of the last view lands on a detached one
  const swap = async () => {
    $("#view").replaceWith(el);
    try {
      await v.show(el, rest.filter(Boolean), qs);
    } catch (e) {
      el.innerHTML = `<div class="page"><h1>Something went wrong</h1><p class="lede">${esc(e.message)}</p></div>`;
    }
  };
  if (document.startViewTransition && !calmMotion() && !(prev === v && v === VIEWS.bot)) await document.startViewTransition(swap).updateCallbackDone;
  else await swap();
}
window.addEventListener("hashchange", () => {
  if (!BAR) return route();
  if (location.hash !== "#/bar") { native({ type: "open", hash: location.hash }); history.replaceState(null, "", "?bar=1#/bar"); }
});
document.addEventListener("click", (e) => { const b = e.target.closest("[data-dl]"); if (b) { e.preventDefault(); download(b.dataset.dl, b.dataset.name); } });

// ---------------------------------------------------------------- command bar (⌘K, Ctrl+K, Alt+Space)
const CMD = { open: false, sel: 0, items: [] };
function cmdItems(q) {
  let text = q, target = null;
  if (q.startsWith("@")) {  // "@Flat Checker check now" (full name) or "@flat check now" (start of its first word)
    const rest = q.slice(1), low = rest.toLowerCase();
    target = S.bots.find((b) => low === b.name.toLowerCase() || low.startsWith(b.name.toLowerCase() + " "));
    if (target) text = rest.slice(target.name.length).trim();
    else {
      const [w, ...more] = rest.split(" ");
      target = (w && S.bots.find((b) => b.name.toLowerCase().startsWith(w.toLowerCase()))) || null;
      if (target) text = more.join(" ").trim();
    }
  }
  const items = [];
  const bots = target ? [target] : S.bots;
  bots.forEach((b) => items.push({ sec: "SEND TO", label: esc(b.name), lead: botCritter(b, 26), k: botMeta(b).meta,
    run: async () => { if (text.trim()) { await post(`/api/bots/${b.id}/chat`, { text, source: "command bar" }); toast("Sent", b); } location.hash = `#/bot/${b.id}/computer`; } }));
  const act = (label, k, d, run) => items.push({ sec: "OR", label, k, lead: `<span style="width:26px;height:26px;border-radius:8px;background:rgba(255,255,255,.08);display:flex;align-items:center;justify-content:center">${icon(d, 15)}</span>`, run });
  act(text ? `Make a new bot: “${esc(text.slice(0, 60))}”` : "Make a new bot", "⌘ ↵", "plus", () => (location.hash = `#/new?job=${encodeURIComponent(text)}`));
  act("Open Needs you", `${S.needs}`, "check", () => (location.hash = "#/needs"));
  act("Pause all bots", BAR ? "⌃ ⌥ P" : "⌥ P", "activity", () => pauseAll());
  act('<span style="color:#F2957C">Stop everything on my screen</span>', BAR ? "⌃ ⌥ Esc" : "Esc", "x", () => stopScreens());
  act("Models and keys", "", "models", () => (location.hash = "#/models"));
  act("Connectors · Claude Code, Codex", "", "plug", () => (location.hash = "#/connectors"));
  return items;
}
async function pauseAll() { for (const b of S.bots) if (["working", "learning"].includes(b.status)) await post(`/api/bots/${b.id}/control`, { cmd: "pause" }); toast("Paused all bots"); refreshSoon(); }
async function stopScreens() { for (const b of S.bots) if (b.mode === "screen") await post(`/api/bots/${b.id}/control`, { cmd: "stop" }); toast("Stopped every bot on your screen"); refreshSoon(); }
function renderCmd() {
  const q = $("#cmdq") ? $("#cmdq").value : "";
  CMD.items = cmdItems(q);
  CMD.sel = Math.min(CMD.sel, CMD.items.length - 1);
  let sec = "";
  $("#cmdlist").innerHTML = CMD.items.map((it, i) => {
    const head = it.sec !== sec ? `<div class="sec">${(sec = it.sec)}</div>` : "";
    return `${head}<div class="it${i === CMD.sel ? " on" : ""}" data-i="${i}">${it.lead}<span>${it.label}</span><span class="k">${esc(it.k || "")}</span></div>`;
  }).join("");
  $$("#cmdlist .it").forEach((el) => el.addEventListener("click", () => { CMD.sel = +el.dataset.i; runCmd(); }));
}
function openCmd(prefill = "") {
  CMD.open = true;
  const c = $("#cmd");
  c.classList.remove("hidden");
  c.innerHTML = `<div class="cmdbox"><div class="in"><b>›</b><label class="vh" for="cmdq">Ask a bot or describe a job</label><input id="cmdq" placeholder="Ask a bot (@name) or describe a new job…" autocomplete="off" value="${esc(prefill)}"><span class="mono small" style="color:#8E8A83">⌥ Space</span></div>
    <div id="cmdlist" style="border-top:1px solid rgba(255,255,255,.08);padding-bottom:8px"></div>
    <div class="foot"><span>↵ send · ⌘ ↵ new bot · ↑↓ choose</span><span>esc close</span></div></div>`;
  c.onclick = (e) => { if (e.target === c) closeCmd(); };
  const inp = $("#cmdq");
  inp.addEventListener("input", () => { CMD.sel = 0; renderCmd(); });
  inp.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { CMD.sel = (CMD.sel + 1) % CMD.items.length; renderCmd(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { CMD.sel = (CMD.sel - 1 + CMD.items.length) % CMD.items.length; renderCmd(); e.preventDefault(); }
    else if (e.key === "Enter") { if (e.metaKey || e.ctrlKey) CMD.sel = CMD.items.findIndex((x) => x.sec === "OR"); runCmd(); e.preventDefault(); }
    else if (e.key === "Escape") closeCmd();
  });
  renderCmd();
  inp.focus();
  requestAnimationFrame(() => inp.focus());
}
// Bar mode (?bar=1): the macOS menu bar app shows just the command bar in a floating panel.
const BAR = new URLSearchParams(location.search).has("bar");
const native = (m) => { try { window.webkit.messageHandlers.inky.postMessage(m); } catch (e) {} };
function closeCmd() { CMD.open = false; $("#cmd").classList.add("hidden"); if (BAR) native({ type: "hide" }); }
async function runCmd() { const it = CMD.items[CMD.sel]; closeCmd(); if (it) try { await it.run(); } catch (e) { toast(e.message); } }
document.addEventListener("keydown", (e) => {
  const inField = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.code === "Space" && e.altKey)) { e.preventDefault(); CMD.open ? closeCmd() : openCmd(); }
  else if (e.code === "KeyP" && e.altKey && !inField) { e.preventDefault(); pauseAll(); }
  else if (e.key === "Escape" && CMD.open) closeCmd();
  else if (e.key === "Escape" && !$("#modal").classList.contains("hidden")) closeModal();
});

function modal(html, onmount) {
  const m = $("#modal");
  m.classList.remove("hidden");
  m.innerHTML = `<div class="box">${html}</div>`;
  m.onclick = (e) => { if (e.target === m) closeModal(); };
  if (onmount) onmount(m);
}
function confirmBox(text, ok = "OK", danger = false) {
  return new Promise((res) => {
    modal(`<h2>${esc(text)}</h2><div class="row" style="justify-content:flex-end"><button class="btn" id="cno">Cancel</button><button class="btn ${danger ? "hot" : "p"}" id="cyes">${esc(ok)}</button></div>`, () => {
      $("#cno").onclick = () => { closeModal(); res(false); };
      $("#cyes").onclick = () => { closeModal(); res(true); };
    });
  });
}
function closeModal() { $("#modal").classList.add("hidden"); $("#modal").innerHTML = ""; }

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
  try { await loadState(); } catch (e) {
    if (String(e.message).includes("401") || String(e.message).includes("token")) { try { localStorage.removeItem("inkyToken"); } catch (err) {} return signIn(); }
    throw e;
  }
  listen();
  if (!BAR) return route();
  document.body.classList.add("bar");
  window.inkyBarOpen = async () => { await loadState(); CMD.sel = 0; openCmd(); return true; };
  openCmd();
});
