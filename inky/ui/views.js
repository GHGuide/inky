// Inky views. Each view: show(el, params, query), optional refresh(), onEvent(msg), leave().
const LOOKS = { kinds: ["octopus", "cat", "blob"], colors: [["#E86F51", "Coral"], ["#E9A23B", "Honey"], ["#2BA59B", "Sea"], ["#3B5BDB", "Ocean"], ["#7C6CF2", "Grape"], ["#F07BA8", "Bubblegum"]],
  accs: ["none", "glasses", "beanie", "headphones", "bow"], earned: [[10, "scarf"], [50, "party"], [100, "star"], [500, "crown"]] };
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const OPS = ["<=", "<", ">=", ">", "==", "!=", "contains", "not_contains", "in", "not_in"];
const EVERY = [[0, "Only when I ask"], [60, "Every hour"], [360, "Every 6 hours"], [1440, "Every day"], [10080, "Every week"]];
const everyOf = (d) => { const m = +d.every_minutes || 0; return EVERY.reduce((a, [v]) => (Math.abs(v - m) < Math.abs(a - m) ? v : a), 0); };  // nearest choice
const OP_WORDS = { "<=": "at most", "<": "under", ">=": "at least", ">": "over", "==": "is", "!=": "isn’t", contains: "contains", not_contains: "doesn’t contain", in: "is one of", not_in: "isn’t one of" };

// ================================================================ setup wizard
const STEPS = ["Welcome", "Computers", "Model", "Your screen", "Phone", "Ready"];
const CLOUD = ["openrouter", "anthropic", "openai", "gemini", "groq", "xai", "mistral"];
const KEY_URL = { openrouter: "https://openrouter.ai/settings/keys", anthropic: "https://console.anthropic.com/settings/keys", openai: "https://platform.openai.com/api-keys",
  gemini: "https://aistudio.google.com/apikey", groq: "https://console.groq.com/keys", xai: "https://console.x.ai", mistral: "https://console.mistral.ai/api-keys" };
const KEY_ABOUT = { openrouter: "Hundreds of models, one key", anthropic: "Claude models", openai: "GPT models", gemini: "Free tier in AI Studio",
  groq: "Very fast · free tier", xai: "Grok models", mistral: "Made in Europe" };
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const NOT_CHAT = /embed|rerank|bge-|minilm|clip|whisper/i;  // local models that can't chat (embeddings and the like)
const enterSends = (el, go) => (el.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); go(); } });
function busyBtn(b, on, label) {  // a button that shows it's working and can't be pressed twice
  if (!b) return;
  if (on) { if (!b.disabled) b.dataset.label = b.textContent; b.disabled = true; b.innerHTML = `<span class="spin" aria-hidden="true"></span>${esc(label)}`; }
  else { b.disabled = false; b.textContent = b.dataset.label || b.textContent; }
}
VIEWS.setup = {
  bare: true,
  async show(el, [n = "1"]) {
    n = Math.min(STEPS.length, Math.max(1, parseInt(n, 10) || 1)); this.el = el; this.n = n;
    if (location.hash.split("?")[0] !== `#/setup/${n}`) history.replaceState(null, "", `#/setup/${n}`);
    let dir = "fwd"; try { dir = sessionStorage.getItem("wizDir") || "fwd"; sessionStorage.removeItem("wizDir"); } catch (e) {}
    const [st, models, comps] = await Promise.all([get("/api/setup"), get("/api/models"), n === 6 ? get("/api/computers").catch(() => ({ computers: [] })) : null]);
    this.st = st; this.label = Object.fromEntries(models.providers.map((p) => [p.name, p.label]));
    const pills = STEPS.map((t, i) => `<li class="${i + 1 < n ? "done" : i + 1 === n ? "on" : ""}"${i + 1 === n ? ' aria-current="step"' : ""}><i>${i + 1 < n ? "✓" : i + 1}</i><span>${t}</span></li>`).join("");
    const nav = (back, next, label = "Continue") => `<div class="wfoot between">
      ${back ? `<a href="#/setup/${back}" class="muted" data-back>Back</a>` : `<span class="mono small muted">open source · MIT · no account needed</span>`}
      <a class="btn p" href="${typeof next === "number" ? "#/setup/" + next : next}" id="wnext" style="min-height:44px">${label}</a></div>`;
    const ok = (b) => `<i class="${b ? "ok" : "bad"}">${b ? "✓" : "!"}</i>`;
    let body = "", foot = "";
    if (n === 1) {
      body = `<h1>Bots that work on their own computers</h1><p class="lede">Inky is open source and runs on your computer. Setup takes about 3 minutes, and only the first 3 steps are needed.</p>
      <div class="row" style="justify-content:center;align-items:flex-end;gap:18px">${critter("octopus", "#E9A23B", "glasses", 60)}${critter("octopus", "#E86F51", "none", 104)}${critter("cat", "#7C6CF2", "none", 60)}${critter("blob", "#2BA59B", "headphones", 60)}</div>
      <div class="grid3">${[["monitor", "Each bot has its own computer", "A browser of its own, on this computer or your server. Your screen stays yours."],
        ["activity", "Learns once, then repeats for free", "It uses a model to learn a job. After that, no AI, so it can run all day."],
        ["lock", "Asks before it can’t undo", "Sending, buying, deleting or signing up always waits for your yes."]].map(([i, t, x]) =>
        `<div class="card panel"><span class="iconbtn" style="border-radius:10px">${icon(i)}</span><b>${t}</b><span class="small muted">${x}</span></div>`).join("")}</div>`;
      foot = nav(0, 2, "Get started");
    }
    if (n === 2) {
      body = `<h1>Where should your bots’ computers run?</h1><p class="lede">Each bot gets its own browser in a sandbox. It never sees your screen unless you allow that later.</p>
      <div class="grid2"><div class="opt"><b style="font-size:17px">This computer</b><span class="small muted">free · private · start here</span>
        <div class="chk">${ok(true)}<span>Bots run as isolated browsers here<br><span class="small muted">no install needed</span></span></div>
        <div class="chk">${ok(true)}<span>${st.hardware.memory_gb || "?"} GB memory · ${esc(st.hardware.cpu || "")}<br><span class="small muted">room for about ${Math.max(1, Math.floor((st.hardware.memory_gb || 8) / 3))} bots</span></span></div></div>
      <div class="opt"><span class="row">${logo("linux", 30)}<b style="font-size:17px">A server too</b></span><span class="small muted">optional · always on · any Linux server or spare Mac</span>
        <span class="small">Your bots keep working while this computer sleeps. You can also add one later in Computers.</span></div></div>
      ${serverAdder(st.install)}`;
      foot = nav(1, 3);
    }
    if (n === 3) {
      body = `<h1>Which model should think for them?</h1><p class="lede">Only to learn a job or understand you. Repeating a job needs no model at all.</p>
      <div class="usingm" id="usingm" role="status"></div>
      <h3 class="wsec">With your API key<span class="small muted">smarter on hard sites · usually cents a week</span></h3>
      <div class="ptiles">${CLOUD.map((p) => `<button class="ptile ${st.keys[p] ? "has" : ""}" data-prov="${p}" aria-expanded="false">${providerLogo(p, 36)}<span><b>${esc(this.label[p])}</b><span class="small muted" data-sub>${st.keys[p] ? "✓ key saved" : KEY_ABOUT[p]}</span></span></button>`).join("")}</div>
      <div class="keyfield hidden" id="keyfield"></div>
      <h3 class="wsec">Or on this computer<span class="small muted">free · private · works offline</span></h3>
      <div class="card panel" id="localm"><span class="small muted">Looking for Ollama and LM Studio…</span></div>`;
      foot = nav(2, 4);
    }
    if (n === 4) {
      body = `<h1>Let bots use your own screen too?</h1><p class="lede">Optional. A bot can drive a visible browser window on your desktop, inside a coral frame, and ask every time.</p>
      <div class="grid2"><div class="card panel"><b>How it looks</b><span class="small">A coral frame shows while a bot drives. Its cursor carries its name, each step gets a label, and a pill has Chat, Pause, Take over and Stop.</span>
        <span class="small">Move your mouse and it pauses. <b>Esc</b> stops it. <b>⌥C</b> opens a chat: your typing goes to the bot, never into the page.</span></div>
      <div class="col"><div class="card"><div class="between"><span><b>Allow bots on my screen</b><br><span class="small muted">You still turn it on per bot</span></span><button class="toggle ${S.settings.screen_allowed ? "on" : ""}" id="scr" role="switch" aria-checked="${!!S.settings.screen_allowed}" aria-label="Allow bots on my screen"></button></div></div>
        <span class="small muted">${st.platform === "Darwin" ? "macOS: a browser window needs no extra permission. Driving other apps needs Screen Recording and Accessibility, which this version doesn’t use." : st.platform === "Windows" ? "Windows: nothing to allow." : "Linux: on Wayland the window is shared through the screen-sharing prompt once; on X11 nothing to allow."}</span></div></div>`;
      foot = nav(3, 5);
    }
    if (n === 5) {
      const tg = st.telegram || {};
      body = `<h1>Hear from your bots on your phone?</h1><p class="lede">Optional. They can ask you things and send summaries while you’re away.</p>
      <div class="grid2"><div class="opt"><span class="row">${logo("telegram", 30)}<b style="font-size:17px">Telegram</b></span>
        <span class="small">1. <a href="https://t.me/BotFather" target="_blank" rel="noopener">Open @BotFather ↗</a> and send <span class="mono">/newbot</span>. Any name works.</span>
        <span class="small">2. Paste the token it sends you:</span>
        <div class="row keyrow"><input class="f grow" id="tgtoken" type="password" autocomplete="off" placeholder="${st.telegram_key ? "Saved · paste a new token to replace" : "123456789:AA…"}" aria-label="Telegram bot token"><button class="btn" id="tgsave">Connect</button></div>
        <span class="small" id="tgmsg" role="status">${tg.chat_id ? `✓ Connected${tg.bot ? " through @" + esc(tg.bot) : ""}.` : st.telegram_key ? `✓ Token saved. Send /start to ${tg.bot ? "@" + esc(tg.bot) : "your bot"} to finish.` : ""}</span>
        <button class="btn s hidden" id="tgagain" style="align-self:flex-start">Check again</button>
        <span class="small">3. Send <span class="mono">/start</span> to your new bot. Inky finds you and says hello.</span>
        ${tg.chat_id ? `<div class="between"><span class="small">Send my alerts there</span><button class="toggle ${tg.enabled ? "on" : ""}" id="tg" role="switch" aria-checked="${!!tg.enabled}" aria-label="Send my alerts on Telegram"></button></div>` : ""}</div>
      <div class="opt"><b style="font-size:17px">Or the web app</b>
        <div class="between"><span class="small">Let my phone open Inky (on this Wi‑Fi)</span><button class="toggle ${st.web_url ? "on" : ""}" id="lan" role="switch" aria-checked="${!!st.web_url}" aria-label="Let my phone open Inky on this Wi‑Fi"></button></div>
        <span class="small" id="lanmsg" role="status">${this.lanText(st.web_url)}</span></div></div>`;
      foot = nav(4, 6);
    }
    if (n === 6) {
      const servers = (comps ? comps.computers : []).filter((c) => c.kind === "remote");
      body = `<h1>You’re set</h1><div class="row" style="justify-content:center">${critter("octopus", "#E86F51", "none", 72)}</div>
      <div class="col list">${[["Computers", servers.length ? `This computer and ${plural(servers.length, "server")}` : "Bots run as browsers on this computer"], ["Model", models.roles.learn ? `${models.roles.learn.model} for learning` : "none yet"],
        ["Your screen", S.settings.screen_allowed ? "Allowed · bots ask each time" : "Off"], ["Phone", [(st.telegram || {}).enabled && "Telegram", st.web_url && "web app on this Wi‑Fi"].filter(Boolean).join(" · ") || "Off"]].map(([a, b]) =>
        `<div class="between" style="padding:9px 0"><span class="muted">${a}</span><span>${esc(b)}</span></div>`).join("")}</div>
      <div class="composer" style="width:100%"><label class="l" for="job">Make your first bot</label><textarea id="job" rows="2" placeholder="Describe a job in your own words"></textarea>
        <div class="between"><span class="mono small muted">${esc(shortcut())}</span><button class="btn p" id="start">Start</button></div></div>`;
      foot = nav(5, "#/bots", "Go to your bots");
    }
    el.innerHTML = `<div class="wiz"><header><span class="row">${critter("octopus", "#E86F51", "none", 26)}<b class="wmark">inky</b></span><ol class="wsteps">${pills}</ol><span class="wcount small">Step ${n} of ${STEPS.length} · ${STEPS[n - 1]}</span><a href="#/bots" id="skipall" class="small muted"${n === 6 ? ' style="visibility:hidden"' : ""}>Skip setup</a></header>
      <div class="wbody"><div class="wcard"><div class="wstep ${dir}">${body}</div>${foot}</div></div></div>`;
    const finish = async () => { await post("/api/settings", { setup_done: true }); S.setupDone = true; try { if (!localStorage.getItem("inkyTour")) sessionStorage.setItem("inkyTourNext", "1"); } catch (e) {} };
    $("#skipall").onclick = async (e) => { e.preventDefault(); await finish(); location.hash = "#/bots"; };
    if ($("[data-back]")) $("[data-back]").onclick = () => { try { sessionStorage.setItem("wizDir", "back"); } catch (e) {} };
    const flip = async (t, body) => {  // a switch shows its new state at once, and goes back if the engine says no
      const on = !t.classList.contains("on"), set = (v) => { t.classList.toggle("on", v); t.setAttribute("aria-checked", v); };
      set(on);
      try { return await post("/api/settings", body(on)); } catch (e) { set(!on); toast(e.message); return null; }
    };
    if ($("#scr")) $("#scr").onclick = async (e) => { const s = await flip(e.currentTarget, (on) => ({ screen_allowed: on })); if (s) S.settings = s; };
    if ($("#tg")) $("#tg").onclick = (e) => flip(e.currentTarget, (on) => ({ telegram: { enabled: on } }));
    if ($("#lan")) $("#lan").onclick = async (e) => {
      const t = e.currentTarget; t.disabled = true;
      const s = await flip(t, (on) => ({ lan: on }));
      t.disabled = false;
      if (!s) return;
      S.settings = s;
      const on = t.classList.contains("on");
      if (!on && s.web_url) { t.classList.add("on"); t.setAttribute("aria-checked", true); }  // this Inky was started open to the network
      $("#lanmsg").innerHTML = on && !s.web_url ? "Inky couldn’t find this computer’s Wi‑Fi address. Check it’s on Wi‑Fi, then switch this off and on again." : this.lanText(s.web_url);
    };
    if (n === 2) bindServerAdder(st.install);
    if (n === 3) { this.showUsing(models.roles.learn); $$("[data-prov]").forEach((b) => (b.onclick = () => this.openKey(b.dataset.prov))); this.renderLocal(); }
    if (n === 5) this.bindTelegram();
    if (n === 6) {
      $("#wnext").onclick = async (e) => { e.preventDefault(); await finish(); location.hash = "#/bots"; };
      const start = async () => {
        const job = $("#job").value.trim();
        if (!job) { toast("Describe the job first"); return $("#job").focus(); }
        await finish(); location.hash = `#/new?job=${encodeURIComponent(job)}`;
      };
      $("#start").onclick = start;
      enterSends($("#job"), start);
    }
  },
  lanText(url) {
    const code = `<b class="mono">${esc(this.st.pair_code || S.pair || "")}</b>`;
    return url ? `On your phone, on the same Wi‑Fi, open <b class="mono">${esc(url)}</b> and sign in with the pairing code ${code}. It installs like an app.`
      : "Off: only this computer can open Inky. Switch it on to get an address your phone can open on this Wi‑Fi, with a pairing code to sign in.";
  },
  say(sel, text, good) { const m = $(sel); if (m) { m.textContent = text; m.className = "small " + (good === true ? "good" : good === false ? "bad" : "muted"); } },
  showUsing(r) {
    this.using = r; const u = $("#usingm"); if (!u) return;
    u.classList.toggle("ok", !!r);
    u.innerHTML = r ? `${icon("check", 16)}<span>Using <b class="mono">${esc(r.model)}</b> from ${esc(this.label[r.provider] || r.provider)}</span>`
      : `<span class="muted">No model yet. Pick one below, or skip and add one later in Models.</span>`;
  },
  async connect(provider, model, msgSel) {
    this.say(msgSel, provider === "ollama" || provider === "custom" ? "Checking the model…" : "Checking which models your key has…");
    let r;
    try { r = await post("/api/models/connect", { provider, model }); } catch (e) { r = { ok: false, reply: e.message }; }
    if (!r.ok) { this.say(msgSel, r.reply || "That didn’t work.", false); return false; }
    this.say(msgSel, `✓ Works. Using ${r.model}, answered in ${r.seconds}s.`, true); SOUND.play("chime");
    this.showUsing({ provider, model: r.model });
    return true;
  },
  openKey(p) {
    const kf = $("#keyfield");
    if (this.openProv === p && !kf.classList.contains("hidden")) {  // a second click closes it again
      kf.classList.add("hidden"); this.openProv = null;
      $$("[data-prov]").forEach((b) => { b.classList.remove("on"); b.setAttribute("aria-expanded", "false"); });
      return;
    }
    this.openProv = p;
    $$("[data-prov]").forEach((b) => { b.classList.toggle("on", b.dataset.prov === p); b.setAttribute("aria-expanded", b.dataset.prov === p); });
    const has = this.st.keys[p], L = esc(this.label[p]);
    kf.classList.remove("hidden");
    kf.innerHTML = `<div class="row">${providerLogo(p, 28)}<b>Your ${L} key</b></div>
      <span class="small">1. <a href="${KEY_URL[p]}" target="_blank" rel="noopener">Make a key at ${esc(KEY_URL[p].replace("https://", ""))} ↗</a></span>
      <span class="small">2. Paste it here. It stays on this computer and only goes to ${L}.</span>
      <div class="row keyrow"><input class="f grow" id="keyin" type="password" autocomplete="off" placeholder="${has ? "Saved · paste a new key to replace" : "Paste the key"}" aria-label="${L} key"><button class="btn p" id="keysave">Save & test</button></div>
      <div class="between"><span class="small" id="keymsg" role="status"></span>${has ? `<button class="btn s" id="keyuse">Use the saved key</button>` : ""}</div>`;
    $("#keyin").focus();
    const tile = $(`[data-prov="${p}"]`);
    const busy = (on) => { busyBtn($("#keysave"), on, "Checking…"); if ($("#keyuse")) $("#keyuse").disabled = on; $("#keyin").disabled = on; };
    const sync = async () => {  // the tile says what the engine really kept (a refused key is deleted there)
      let kept = this.st.keys[p];
      try { kept = ((await get("/api/keys")).keys.find((k) => k.provider === p) || {}).source; } catch (e) {}
      this.st.keys[p] = kept || null;
      tile.classList.toggle("has", !!kept); $("[data-sub]", tile).textContent = kept ? "✓ key saved" : KEY_ABOUT[p];
      if (!kept && $("#keyuse")) { $("#keyuse").remove(); $("#keyin").placeholder = "Paste the key"; }
    };
    const check = async (v) => {
      busy(true);
      try {
        if (v) { await post("/api/keys", { provider: p, key: v }); $("#keyin").value = ""; }
        await this.connect(p, null, "#keymsg");
      } catch (e) { this.say("#keymsg", e.message, false); }
      await sync(); busy(false);
      const m = $("#keymsg"); if (m) m.scrollIntoView({ block: "nearest" });  // never under the sticky footer
      if ($("#keyin")) $("#keyin").focus({ preventScroll: true });
    };
    const save = () => { const v = $("#keyin").value.trim(); if (!v) return this.say("#keymsg", "Paste a key first.", false); check(v); };
    $("#keysave").onclick = save;
    $("#keyin").onkeydown = (e) => { if (e.key === "Enter" && !$("#keysave").disabled) save(); };
    if ($("#keyuse")) $("#keyuse").onclick = () => check(null);
  },
  async renderLocal() {
    const box = $("#localm"); if (!box) return;
    let loc;
    let ch = { choices: [] };
    try { [loc, ch] = await Promise.all([get("/api/models/local"), get("/api/models/choices").catch(() => ({ choices: [] }))]); } catch (e) { box.innerHTML = `<span class="small bad">${esc(e.message)}</span><button class="btn s" data-lrefresh>Check again</button>`; $("[data-lrefresh]", box).onclick = () => this.renderLocal(); return; }
    if (!box.isConnected) return;
    const o = loc.ollama, pulls = loc.pulls || {}, chat = o.models.filter((m) => !NOT_CHAT.test(m.name));
    const head = (s, t, name) => `<div class="lrow"><span class="row">${logo(s, 34)}<span><b>${name || (s === "ollama" ? "Ollama" : "LM Studio")}</b><br><span class="small muted">${t}</span></span></span>`;
    let h;
    if (!o.installed && !o.running) h = `${head("ollama", "not installed yet")}<span class="row"><a class="btn" href="https://ollama.com/download" target="_blank" rel="noopener">Install Ollama ↗</a><button class="btn s" data-lrefresh>Check again</button></span></div>
      <span class="small muted">Ollama runs models on this computer for free. Install it, then press Check again.</span>`;
    else if (!o.running) h = `${head("ollama", "installed, not running")}<button class="btn" id="ollstart">Start Ollama</button></div><span class="small" id="lmsg" role="status"></span>`;
    else if (!chat.length) {
      const pick = loc.catalog.filter((c) => c.fit === "fits well" || c.fit === "tight" || c.fit === "unknown").slice(0, 3);
      h = `${head("ollama", o.models.length ? "running · its models can’t chat, pick one to download" : "running · pick a model to download")}</div>${pick.map((c) => {
        const p = pulls[c.name], pct = p && p.total ? Math.round(100 * p.completed / p.total) : 0;
        return `<div class="lrow"><span><b class="mono">${esc(c.name)}</b> <span class="small muted">${c.gb} GB${c.badge === "recommended" ? " · recommended" : ""}</span><br><span class="small muted">${esc(c.about)}</span></span>
        <span class="row">${p && p.status !== "success" && !String(p.status).startsWith("failed") ? `<span class="prog" data-prog="${esc(c.name)}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="Downloading ${esc(c.name)}"><i style="width:${Math.max(2, pct)}%"></i></span><span class="small mono" data-pct="${esc(c.name)}">${pct}%</span>` : `<button class="btn s" data-pull="${esc(c.name)}" data-gb="${c.gb}">Download</button>`}</span></div>`;
      }).join("") || `<span class="small muted">No model in our list fits this computer’s memory. Use an API key instead.</span>`}<span class="small" id="lmsg" role="status"></span>`;
    } else {  // best results first: the biggest that fits on top, the recommended one marked, tiny ones say what they're good for
      const rows = ch.choices.filter((c) => c.provider === "ollama");
      const list = rows.length ? rows : chat.map((m) => ({ model: m.name, label: m.name }));
      const better = !rows.some((c) => !c.small) && loc.catalog.find((c) => c.badge === "recommended" && !c.installed && ["fits well", "tight", "unknown"].includes(c.fit));
      const pb = better && pulls[better.name], pct = pb && pb.total ? Math.round(100 * pb.completed / pb.total) : 0;
      h = `${head("ollama", "running")}</div>
        ${better ? `<div class="lrow"><span><b>Your models are small.</b> <span class="small muted">They chat, but learn sites poorly. ${esc(better.name)} (${better.gb} GB) learns much better.</span></span>
          <span class="row">${pb && pb.status !== "success" && !String(pb.status).startsWith("failed") ? `<span class="prog" data-prog="${esc(better.name)}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="Downloading ${esc(better.name)}"><i style="width:${Math.max(2, pct)}%"></i></span><span class="small mono" data-pct="${esc(better.name)}">${pct}%</span>` : `<button class="btn s p" data-pull="${esc(better.name)}" data-gb="${better.gb}">Download it</button>`}</span></div>` : ""}
        ${list.map((c) => `<div class="lrow"><span><b class="mono">${esc(c.model)}</b> <span class="small muted">${esc(c.label.replace(c.model, "").replace(/^ · /, ""))}${ch.recommended === c.model ? " · recommended" : ""}${c.small ? " · small: learns sites poorly" : ""}</span></span>${this.using && this.using.provider === "ollama" && this.using.model === c.model ? `<span class="small good">✓ In use</span>` : `<button class="btn s${ch.recommended === c.model ? " p" : ""}" data-use="${esc(c.model)}">Use this</button>`}</div>`).join("")}<span class="small" id="lmsg" role="status"></span>`;
    }
    if (loc.custom.reachable) h += loc.lmstudio.installed ? `${head("lmstudio", "running at " + esc(loc.custom.base))}<button class="btn s" id="uselms">Use LM Studio</button></div>`
      : `${head("server", "running at " + esc(loc.custom.base), "Your own server")}<button class="btn s" id="uselms">Use it</button></div>`;
    else if (loc.lmstudio.installed) h += `${head("lmstudio", "installed · start its local server to use it")}<button class="btn s" data-lrefresh>Check again</button></div>`;
    box.innerHTML = h;
    $$("[data-lrefresh]", box).forEach((b) => (b.onclick = () => this.renderLocal()));
    if ($("#ollstart")) $("#ollstart").onclick = async () => {
      busyBtn($("#ollstart"), true, "Starting…"); this.say("#lmsg", "Starting Ollama…");
      const r = await post("/api/models/local/start", {}).catch((e) => ({ running: false, error: e.message }));
      if (r.running) this.renderLocal(); else { busyBtn($("#ollstart"), false); this.say("#lmsg", r.error || "Ollama didn’t start. Open the Ollama app once, then try again.", false); }
    };
    $$("[data-pull]", box).forEach((b) => (b.onclick = async () => {
      if (!(await confirmBox(`Download ${b.dataset.pull} (${b.dataset.gb} GB) from ollama.com?`, "Download"))) return;
      busyBtn(b, true, "Starting…");
      try { await post("/api/models/pull", { name: b.dataset.pull }); } catch (e) { busyBtn(b, false); this.say("#lmsg", e.message, false); }
    }));
    $$("[data-use]", box).forEach((b) => (b.onclick = async () => { busyBtn(b, true, "Checking…"); if (await this.connect("ollama", b.dataset.use, "#lmsg")) this.renderLocal(); else busyBtn(b, false); }));
    if ($("#uselms")) $("#uselms").onclick = async () => { busyBtn($("#uselms"), true, "Checking…"); await this.connect("custom", null, "#lmsg"); busyBtn($("#uselms"), false); };
  },
  bindTelegram() {
    const say = (t, ok) => this.say("#tgmsg", t, ok), again = $("#tgagain");
    const wait = async (bot) => {  // waitForTelegram gives up after 2 minutes; then you can look again from here
      again.classList.add("hidden");
      const t0 = Date.now(), ok = await waitForTelegram(bot, say, "press Check again");
      if (ok !== false || !again.isConnected) return;
      if (Date.now() - t0 >= 119e3) say(`Didn’t hear from you yet. Send /start to @${bot}, then press Check again.`, false);
      again.classList.remove("hidden"); again.onclick = () => wait(bot);
    };
    const save = async () => {
      const v = $("#tgtoken").value.trim(); if (!v) return say("Paste the token from @BotFather first.", false);
      say("Checking with Telegram…"); busyBtn($("#tgsave"), true, "Checking…");
      let r;
      try { r = await post("/api/connectors/telegram/setup", { values: { token: v } }); } catch (e) { r = { ok: false, text: e.message }; }
      busyBtn($("#tgsave"), false);
      if (!r.ok) return say(r.text, false);
      $("#tgtoken").value = "";
      wait(r.bot);
    };
    const tg = this.st.telegram || {};
    if (this.st.telegram_key && !tg.chat_id && tg.bot) wait(tg.bot);  // token saved earlier: keep listening for /start
    $("#tgsave").onclick = save;
    $("#tgtoken").onkeydown = (e) => { if (e.key === "Enter" && !$("#tgsave").disabled) save(); };
  },
  leave() { clearInterval(tgPoll); clearInterval(foundTimer); },
  onEvent(m) {
    if (m.kind === "ssh") return sshLine(m);
    if (m.kind !== "pull" || this.n !== 3) return;
    const bar = $(`[data-prog="${CSS.escape(m.name)}"]`);
    if (m.status === "success") { this.connect("ollama", m.name, "#lmsg").then(() => this.renderLocal()); return; }
    if (String(m.status || "").startsWith("failed")) { this.renderLocal().then(() => this.say("#lmsg", `Download stopped: ${m.status.slice(8)}`, false)); return; }
    if (!bar) return this.renderLocal();
    if (!m.total) return;
    const pct = Math.round(100 * m.completed / m.total);
    $("i", bar).style.width = Math.max(2, pct) + "%"; bar.setAttribute("aria-valuenow", pct);
    const t = $(`[data-pct="${CSS.escape(m.name)}"]`); if (t) t.textContent = pct + "%";
  },
};

// ================================================================ your bots
VIEWS.bots = {
  async show(el) {
    this.el = el;
    el.innerHTML = `${mobileBar("Your bots")}<div class="hero">${critter("octopus", "#E86F51", "none", 72)}<h1>What job should a new bot do?</h1>
      <p class="lede" style="margin-top:-6px">Each bot gets its own computer and keeps working while you’re away. It learns a job once, then repeats it with no AI.</p>
      <div class="composer"><label class="vh" for="job">Describe the job</label><textarea id="job" rows="2" placeholder="Describe a job, or @mention a bot"></textarea>
        <div class="between"><span class="mono small muted">${esc(shortcut())} · @ to talk to a bot</span><button class="btn p" id="go">Start</button></div></div>
      <div class="row wrap" style="justify-content:center">${["Find rental flats abroad under €150k", "Watch 5 webshops for price drops", "Every morning, check new books on books.toscrape.com"].map((t) => `<button class="btn" data-ex="${esc(t)}">${esc(t)}</button>`).join("")}</div></div>
      <div class="page" style="padding-top:12px"><div id="betterm"></div><div id="recap"></div><div class="between"><h2>Your bots</h2><span class="row"><span class="seg" id="homeview" role="group" aria-label="Show bots as"><button data-hv="cards" aria-pressed="false">Cards</button><button data-hv="office" aria-pressed="false">Office</button></span><label class="btn s" for="importf">Import a bot file</label><input type="file" id="importf" accept=".inky,.json" class="vh"></span></div><div class="botcards" id="cards"></div></div>`;
    const go = () => {
      const t = $("#job").value.trim();
      if (!t) { toast("Describe the job first"); return $("#job").focus(); }
      if (/^inky:\/\//i.test(t)) { $("#job").value = ""; return handleLink(t); }  // a share or pair link someone sent you
      if (!t.startsWith("@")) { location.hash = `#/new?job=${encodeURIComponent(t)}`; return; }
      const m = mention(t);  // an @-message is always for a bot, never a new bot's job
      if (m.ambiguous) {
        const names = S.bots.filter((b) => b.name.toLowerCase().split(/\s+/)[0].startsWith(m.named.toLowerCase())).map((b) => b.name);
        return toast(`More than one bot is called ${m.named}: ${names.join(", ")}. Type the full name.`);
      }
      if (!m.bot) return toast(m.named ? `No bot called ${m.named}` : "Type a bot’s name after @");
      if (m.text) post(`/api/bots/${m.bot.id}/chat`, { text: m.text }).catch((e) => toast(e.message, m.bot));
      location.hash = `#/bot/${m.bot.id}/computer`;
    };
    $("#go").onclick = go;
    enterSends($("#job"), go);
    $$("[data-ex]").forEach((b) => (b.onclick = () => { $("#job").value = b.dataset.ex; $("#job").focus(); }));
    $("#importf").onchange = async (e) => {
      const f = e.target.files[0]; if (!f) return;
      e.target.value = "";
      let d;
      try { d = JSON.parse(await f.text()); } catch (err) { return toast("That file isn’t a bot file (it isn’t valid JSON)."); }
      toast(`Importing ${f.name}…`);
      try { const r = await post("/api/import", d); await loadState(); toast(`${r.bot.name} moved in`, r.bot); location.hash = `#/bot/${r.bot.id}/computer`; }
      catch (err) { toast(err.message); }
    };
    $$("[data-hv]").forEach((x) => (x.onclick = () => { try { localStorage.setItem("inkyHome", x.dataset.hv); } catch (e) {} this.refresh(); }));
    this.refresh();
    this.recap();
    this.better();
    try { if (sessionStorage.getItem("inkyTourNext") && !localStorage.getItem("inkyTour")) { sessionStorage.removeItem("inkyTourNext"); setTimeout(() => tour(0), 600); } } catch (e) {}
    this.timer = setInterval(() => $$("#cards img[data-live]").forEach((i) => (i.src = screenUrl(i.dataset.live))), 2500);
  },
  async better() {  // best results first: a small model learns sites poorly, so a bigger one you already have is offered once
    try { if (localStorage.getItem("inkyBetterNo")) return; } catch (e) {}
    const ch = await get("/api/models/choices").catch(() => null);
    const u = ch && ch.using, cur = u && ch.choices.find((c) => c.provider === u.provider && c.model === u.model);
    const rec = ch && ch.recommended && ch.choices.find((c) => c.provider === "ollama" && c.model === ch.recommended);
    if (!cur || !cur.small || !rec || rec.small || !$("#betterm")) return;
    $("#betterm").innerHTML = `<div class="card panel" style="margin-bottom:18px"><div class="between"><span><b>Your bots use ${esc(u.model)}, a small model.</b> <span class="small muted">It chats fine but learns sites poorly. ${esc(rec.model)} is on this computer and learns much better.</span></span>
      <span class="row"><button class="btn s p" id="betteryes">Use ${esc(rec.model)}</button><button class="btn s" id="betterno">Not now</button></span></div><span class="small" id="bettermsg" role="status"></span></div>`;
    $("#betterno").onclick = () => { try { localStorage.setItem("inkyBetterNo", "1"); } catch (e) {} $("#betterm").innerHTML = ""; };
    $("#betteryes").onclick = async () => {
      const b = $("#betteryes"); busyBtn(b, true, "Checking…");
      const r = await post("/api/models/connect", { provider: "ollama", model: rec.model }).catch((e) => ({ ok: false, reply: e.message }));
      if (r.ok) { $("#betterm").innerHTML = ""; toast(`All your bots use ${r.model} now`); } else { busyBtn(b, false); formSay("#bettermsg", r.reply || "It didn’t answer.", false); }
    };
  },
  async recap() {  // "While you were away", when the app was closed or hidden for 2+ hours
    const since = awaySince();
    if (!since) return;
    const { recap } = await get(`/api/recap?since=${since}`);
    const rows = recap.filter((r) => r.runs || r.needs || r.new);
    if (!rows.length || !$("#recap")) return;
    const away = Math.round((Date.now() / 1000 - since) / 3600);
    $("#recap").innerHTML = `<div class="card panel" style="margin-bottom:18px"><div class="between"><b>While you were away · ${away} h</b><button class="btn s" id="recapx">Dismiss</button></div>
      ${rows.map((r) => { const b = S.bots.find((x) => x.id === r.bot) || { look: {}, id: r.bot, status: "idle", schedule: {} };
        return `<a class="row" style="text-decoration:none;color:inherit" href="#/bot/${r.bot}/computer">${botCritter(b, 30)}<span><b>${esc(r.name)}</b> <span class="small muted">${[r.runs && `${r.runs} run${r.runs > 1 ? "s" : ""}`, r.new && `${r.new} new`, r.fixed && `fixed ${r.fixed} step${r.fixed > 1 ? "s" : ""}`, r.needs && `${r.needs} waiting for you`].filter(Boolean).join(" · ")}</span></span></a>`; }).join("")}</div>`;
    $("#recapx").onclick = () => { $("#recap").innerHTML = ""; clearAway(); };
  },
  refresh() {
    if (!$("#cards")) return;
    let mode = "cards"; try { mode = localStorage.getItem("inkyHome") || "cards"; } catch (e) {}
    $$("[data-hv]").forEach((x) => { x.classList.toggle("on", x.dataset.hv === mode); x.setAttribute("aria-pressed", x.dataset.hv === mode); });
    $("#cards").className = mode === "office" ? "" : "botcards";
    if (mode === "office") return this.office();
    $("#cards").innerHTML = S.bots.map((b) => {
      const m = botMeta(b);
      const live = ["working", "learning", "paused", "takeover", "showing"].includes(b.status);
      const said = b.status === "moved" ? m.meta : (STATUS[b.status] || [b.status.replace("_", " ")])[0];  // the line under it says this already
      const mid = b.status === "needs_you" || (b.status === "moved" && b.needs) ? `<div class="card" style="padding:12px 14px;gap:4px;border-color:#F3C9BC"><span class="small" style="color:var(--coral-t);font-weight:600">Needs you</span><b>${b.needs} waiting</b></div>`
        : live ? `<div class="thumb"><img data-live="${b.id}" src="${screenUrl(b.id)}" alt="${esc(b.name)}’s computer"><span class="live">LIVE</span></div>`
          : `<div class="thumb idle">${esc(b.remote_id ? `runs on ${b.remote || "your server"}` : !b.skills.length ? "hasn’t learned yet" : m.meta !== said ? m.meta : b.status === "idle" ? "runs when you ask" : "")}</div>`;
      return `<a class="botcard${m.hot ? " hot" : ""}" href="#/bot/${b.id}/computer"><span class="row">${botCritter(b, 44)}<span class="col" style="gap:2px"><b>${esc(b.name)}</b><span class="small muted">${esc(clip(b.summary || b.job || "", 70))}</span></span></span>
        ${mid}<span class="between mono small muted"><span style="color:${m.color}">${m.hot ? "" : `● ${esc(said)}`}</span><span>${b.status === "moved" ? "" : plural(b.skills.length, "skill")}</span></span></a>`;
    }).join("") || `<p class="muted">No bots yet. Describe a job above.</p>`;
  },
  office() {  // the same bots, at their desks; the room follows the time of day
    const h = new Date().getHours(), night = S.bots.length && S.bots.every((b) => inQuiet(b.schedule, new Date()));
    const sky = night || h < 6 || h >= 21 ? "night" : h < 8 ? "dawn" : h < 17 ? "day" : "evening";
    $("#cards").innerHTML = `<div class="office ${night ? "dim" : ""}" data-sky="${sky}"><div class="window" aria-hidden="true"><i class="sun"></i><i class="moon"></i><b></b><b></b><b></b></div>
      ${S.bots.map((b) => {
        const live = ["working", "learning", "paused", "takeover", "showing"].includes(b.status) && !b.remote;
        const screen = live ? `<img data-live="${b.id}" src="${screenUrl(b.id)}" alt="${esc(b.name)}’s computer">` : `<span>${esc(clip(botMeta(b).meta, 26))}</span>`;
        return `<a class="desk${botMeta(b).hot ? " hot" : ""}" href="#/bot/${b.id}/computer"><div class="top">${botCritter(b, 70)}<div class="mon">${screen}</div></div><div class="table"></div><div class="plate"><b>${esc(b.name)}</b></div></a>`;
      }).join("") || `<p class="muted">No bots yet. Describe a job above.</p>`}</div>`;
  },
  leave() { clearInterval(this.timer); },
};

// ================================================================ new bot
function siteUrl(v) {  // "books.toscrape.com" → "https://books.toscrape.com/"; "" → null; not an address → false
  v = String(v || "").trim();
  if (!v) return null;
  if (/\s/.test(v)) return false;  // "books .toscrape.com" isn't an address
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(v)) v = (/^(localhost|127\.|\d+\.\d+\.\d+\.\d+)/i.test(v) ? "http://" : "https://") + v;
  try {
    const u = new URL(v);
    return /^https?:$/.test(u.protocol) && /^(localhost|[^.\s]+(\.[^.\s]+)+)$/i.test(u.hostname) ? u.href : false;
  } catch (e) { return false; }
}
VIEWS.new = {
  async show(el, _, qs) {
    const job = qs.get("job") || "";
    this.el = el; this.req = (this.req || 0) + 1; this.edited = new Set(); this.filters = null; this.leaving = false; this.job0 = job.trim();
    this.picked = new Set(); this.found = null; this.siteQuery = ""; this.searched = null; this.allSites = false; this.gotMore = false; this.every = 0;  // "edited", not "dirty": the router calls a page's dirty() before leaving it
    el.innerHTML = `${mobileBar("New bot")}<div class="page narrow"><h1>New bot</h1><p class="lede">Describe the job. It drafts the bot, you check it, then it learns the site once while you watch.</p>
      <div class="composer" style="width:100%"><label class="vh" for="job">Job</label><textarea id="job" rows="3" placeholder="e.g. Every morning, find flats in Bari under €150k on casafacile.it">${esc(job)}</textarea>
      <div class="between"><span class="small muted">Include the site if you know it.</span><button class="btn p" id="draft">Draft the bot</button></div></div><div id="draftbox"></div></div>`;
    $("#draft", el).onclick = () => this.draft();
    enterSends($("#job", el), () => this.draft());
    if (job) this.draft();
  },
  leave() { this.req++; },  // a draft that comes back after you left is dropped
  dirty() {  // you typed a job or changed the draft, and haven't made the bot yet
    const job = $("#job", this.el);
    return !!job && (job.value.trim() !== this.job0 || this.edited.size > 0);
  },
  leaveText() { return "Leave without making this bot? Your draft will be lost."; },
  async draft() {
    const el = this.el, job = $("#job", el).value.trim(), box = $("#draftbox", el), btn = $("#draft", el);
    if (btn.disabled) return;  // a second Enter while it's thinking
    if (!job) { toast("Describe the job first"); return $("#job", el).focus(); }
    const my = ++this.req, redraft = !!$("#create", box);
    busyBtn(btn, true, "Thinking…");
    if (redraft) { busyBtn($("#create", box), true, "Redrafting…"); box.setAttribute("aria-busy", "true"); } else box.innerHTML = `<p class="muted">Thinking…</p>`;
    let d, err;
    try { d = (await post("/api/bots/draft", { job })).draft; } catch (e) { err = e; }
    if (my !== this.req || !el.isConnected) return;
    busyBtn(btn, false); box.removeAttribute("aria-busy");
    if (err) {
      toast(err.message);
      if (redraft) busyBtn($("#create", box), false); else box.innerHTML = `<p class="bad" style="background:none">${esc(err.message)}</p>`;
      return;
    }
    const had = box.contains(document.activeElement) || document.activeElement === document.body;
    this.render(d);
    if (had && redraft) { const to = $("#draftbox [id^=qa]", el) || $("#create", el); if (to) to.focus(); }  // an answered question: focus stays in the draft
  },
  kept() {  // what you changed in the draft survives a redraft
    const box = $("#draftbox", this.el), k = {};
    for (const [id, key] of [["nm", "name"], ["url", "start_url"], ["goal", "goal"]]) if (this.edited.has(id) && $("#" + id, box)) k[key] = $("#" + id, box).value;
    if (this.edited.has("every")) k.every_minutes = this.every;
    if (this.edited.has("filters") && this.filters) k.filters = this.filters;
    return k;
  },
  async sites(d, box) {  // websites for the job, found for you: tick the ones it should check
    const sb = $("#sitebox", box), url = $("#url", box), my = this.req;
    this.picked = this.picked || new Set();
    const query = (this.siteQuery = this.siteQuery || (d.search || [])[0] || d.goal || d.job || "");
    this.searched = this.searched || d.search || [query];
    const draw = (rows, note) => {
      const show = rows.slice(0, this.allSites ? rows.length : 12);
      const web = rows.filter((r) => !r.source && !r.guess).length;
      sb.innerHTML = `<div class="between"><b class="small">Sites for this job</b><span class="small muted">${rows.length ? [web && `${web} found on the web (DuckDuckGo)`, rows.length - web && `${rows.length - web} suggested by its model, each checked to exist`].filter(Boolean).join(" · ") : ""}</span></div>
        ${rows.length ? `<span class="small muted clip1">Searched for: ${this.searched.map(esc).join(" · ")}</span>` : ""}
        ${note ? `<span class="small ${/Couldn’t/.test(note) ? "bad" : "muted"}" style="background:none">${esc(note)}</span>` : ""}
        <div class="sites" role="group" aria-label="Sites for this job">${show.map((r) => `<label class="siterow${this.picked.has(r.url) ? " on" : ""}"><input type="checkbox" data-site="${esc(r.url)}" ${this.picked.has(r.url) ? "checked" : ""}>
          <span class="col grow" style="gap:1px;min-width:0"><b class="mono small">${esc(r.host)}${r.guess ? ` <span class="badge">its guess</span>` : ""}${r.source ? ` <span class="badge">${esc(r.source)}</span>` : ""}</b>${r.title ? `<span class="small clip1">${esc(r.title)}</span>` : ""}${r.snippet ? `<span class="small muted clip1">${esc(r.snippet)}</span>` : ""}</span>
          <a class="small" href="${esc(r.url)}" data-out="${esc(r.url)}" aria-label="Open ${esc(r.host)}">open ↗</a></label>`).join("")}</div>
        <div class="row wrap">${rows.length > show.length ? `<button class="btn s" id="sitemore" type="button">Show all ${rows.length}</button>` : !this.gotMore && rows.length ? `<button class="btn s" id="sitefetch" type="button">Find more sites</button>` : ""}
          ${rows.length > 1 ? (rows.every((r) => this.picked.has(r.url)) ? `<button class="btn s" id="sitenone" type="button">Untick all</button>` : `<button class="btn s p" id="siteall" type="button">Check all ${rows.length} sites</button>`) : ""}</div>
        <form class="row" id="sitesearch"><label class="vh" for="siteq">Search for sites</label><input class="f grow" id="siteq" value="${esc(this.siteQuery)}" placeholder="Search for sites"><button class="btn s" id="sitego">Search</button></form>
        <span class="small muted">${this.picked.size > 1 ? `It learns ${esc(new URL([...this.picked][0]).hostname)} first, then the other ${this.picked.size - 1}, one after another (a few minutes each). After that, every run checks them all, with no AI.` : "Tick one or more. The first one is where it starts."}</span>`;
      $$("[data-site]", sb).forEach((x) => (x.onchange = () => {
        x.checked ? this.picked.add(x.dataset.site) : this.picked.delete(x.dataset.site);
        this.edited.add("sites");
        const first = [...this.picked][0];
        url.value = first ? first : ""; url.setCustomValidity(""); this.edited.add("url");
        draw(rows); const again = $(`[data-site="${CSS.escape(x.dataset.site)}"]`, sb); if (again) again.focus();
      }));
      $$("[data-out]", sb).forEach((a) => (a.onclick = (e) => { e.preventDefault(); e.stopPropagation(); openOut(a.dataset.out); }));
      if ($("#sitemore", sb)) $("#sitemore", sb).onclick = () => { this.allSites = true; draw(rows); };
      if ($("#sitefetch", sb)) $("#sitefetch", sb).onclick = () => { this.gotMore = true; this.allSites = true; find(this.searched, true); };
      const setAll = (on) => { rows.forEach((r) => (on ? this.picked.add(r.url) : this.picked.delete(r.url))); this.edited.add("sites"); this.edited.add("url");
        url.value = on ? rows[0].url : ""; url.setCustomValidity(""); this.allSites = this.allSites || on; draw(rows); const f = $("#siteall, #sitenone", sb); if (f) f.focus(); };
      if ($("#siteall", sb)) $("#siteall", sb).onclick = () => setAll(true);
      if ($("#sitenone", sb)) $("#sitenone", sb).onclick = () => setAll(false);
      $("#sitesearch", sb).onsubmit = (e) => { e.preventDefault(); this.siteQuery = $("#siteq", sb).value.trim(); if (this.siteQuery) { this.searched = [this.siteQuery]; this.allSites = false; find([this.siteQuery]); } };
    };
    const find = async (queries, more = false) => {
      sb.innerHTML = `<span class="small muted">${more ? "Looking further…" : "Looking for sites for this job…"} It searches the web and asks its model, which can take half a minute.</span>`;
      try {
        const r = await post("/api/sites", { queries, guess: d.guess || null, job: d.job || $("#job", this.el).value, more });
        if (my !== this.req || !sb.isConnected) return;
        const keep = new Map((more ? this.found || [] : []).map((x) => [x.site || x.host, x]));
        r.sites.forEach((x) => { if (!keep.has(x.site || x.host)) keep.set(x.site || x.host, x); });
        this.found = [...keep.values()];
        draw(this.found, r.note || (this.found.length ? "" : "No sites found. Try other words, or type an address above."));
      } catch (e) { if (sb.isConnected) draw(this.found || [], e.message); }
    };
    if (this.found) return draw(this.found);
    if (d.start_url && !d.guess && !this.edited.has("sites")) {  // you named the site: no need to search, but you can
      sb.innerHTML = `<div class="between"><span class="small">It starts on the site you named.</span><button class="btn s" type="button" id="sitefind">Find more sites like it</button></div>`;
      $("#sitefind", sb).onclick = () => { this.picked.add(siteUrl(url.value) || d.start_url); find(d.search && d.search.length ? d.search : [query]); };
      return;
    }
    find(d.search && d.search.length ? d.search : [query]);
  },
  render(draft) {
    const d = { ...draft, ...this.kept() }, box = $("#draftbox", this.el), dirty = this.edited;
    const look = d.look || { kind: "octopus", color: "#E86F51", acc: "none" };
    const label = () => `Create ${$("#nm", box).value.trim() || "the bot"}`;
    const notice = d.notice ? `<p class="small muted" role="status" style="margin:8px 0 0">${/\bModels\b/.test(d.notice) ? esc(d.notice).replace(/\bModels\b/, '<a href="#/models">Models</a>') : `${esc(d.notice)} <a href="#/models">Models</a>`}</p>` : "";
    box.innerHTML = `${notice}<div class="card" style="margin-top:8px"><div class="row">${critter(look.kind, look.color, look.acc, 48)}<div class="grow"><label class="l" for="nm">Your new bot</label><input class="f" id="nm" value="${esc(d.name)}" maxlength="40"></div></div>
      ${d.summary ? `<div class="card panel">${esc(d.summary)}</div>` : ""}
      <div class="col" style="gap:8px"><label class="l" for="url">Where it looks</label><input class="f" id="url" value="${esc(d.start_url || "")}" placeholder="a site’s address, or pick some below" inputmode="url" autocomplete="off" spellcheck="false">
        <div class="card panel sitebox" id="sitebox"></div></div>
      <div><label class="l" for="goal">What to do there</label><input class="f" id="goal" value="${esc(d.goal || "")}"></div>
      <div class="col" style="gap:6px"><span class="l" id="everyl">How often</span><span class="seg wrap" id="every" role="group" aria-labelledby="everyl">${EVERY.map(([v, t]) => `<button type="button" data-v="${v}" aria-pressed="${+v === everyOf(d)}" class="${+v === everyOf(d) ? "on" : ""}">${t}</button>`).join("")}</span></div>
      <div><span class="l">Only keep results where…</span><div id="filters" class="col"></div><button class="btn s" id="addf" style="margin-top:6px">Add a rule</button></div>
      ${(d.questions || []).length ? `<div class="card panel small wonders"><b>It wonders:</b>${d.questions.map((q, i) => `<div class="col" style="gap:6px"><label for="qa${i}">${esc(q)}</label>
        <div class="row"><input class="f grow" id="qa${i}" data-q="${esc(q)}" placeholder="Your answer" autocomplete="off"><button class="btn s" data-qa="${i}">Answer</button></div></div>`).join("")}
        <span class="muted">Your answer goes into the job, and it drafts again. What you changed above stays.</span></div>` : ""}
      <div class="col"><span class="l">What it may do</span><div class="rule"><b>On its own</b><span>Read, search, take notes</span></div><div class="rule ask"><b>Ask you first</b><span>Send, post, delete, submit forms, sign up</span></div><div class="rule"><b>Never</b><span>Buy or pay · type your passwords</span></div></div>
      <div class="between"><span class="small muted">It learns the site right after you create it.</span><button class="btn p" id="create"></button></div></div>`;
    $("#create", box).textContent = label();
    ["nm", "url", "goal"].forEach((id) => $("#" + id, box).addEventListener("input", () => { dirty.add(id); $("#" + id, box).setCustomValidity(""); }));
    let every = everyOf(d);
    $$("#every button", box).forEach((x) => (x.onclick = () => { every = +x.dataset.v; this.every = every; dirty.add("every");
      $$("#every button", box).forEach((y) => { y.classList.toggle("on", y === x); y.setAttribute("aria-pressed", y === x); }); }));
    this.sites(d, box);
    $("#nm", box).addEventListener("input", () => { if (!$("#create", box).disabled) $("#create", box).textContent = label(); });
    const filters = (this.filters = (d.filters || []).map((f) => ({ ...f })));
    const drawF = () => {
      $("#filters", box).innerHTML = filters.map((f, i) => `<div class="frow"><input class="f" data-i="${i}" data-k="field" value="${esc(f.field)}" aria-label="Field" placeholder="price"><select class="f" data-i="${i}" data-k="op" aria-label="Test">${OPS.map((o) => `<option value="${esc(o)}"${o === f.op ? " selected" : ""}>${OP_WORDS[o]}</option>`).join("")}</select>
        <input class="f" data-i="${i}" data-k="value" value="${esc(Array.isArray(f.value) ? f.value.join(", ") : f.value)}" aria-label="Value"><button class="iconbtn" data-del="${i}" aria-label="Remove rule">${icon("x", 14)}</button></div>`).join("") || `<span class="small muted">Nothing yet: it keeps everything it finds. Add one like “price at most 20”.</span>`;
      $$("#filters [data-k]", box).forEach((x) => (x.oninput = () => { dirty.add("filters"); const f = filters[x.dataset.i]; f[x.dataset.k] = x.dataset.k === "value" && /,/.test(x.value) ? x.value.split(",").map((s) => s.trim()) : x.value; }));
      $$("#filters [data-del]", box).forEach((x) => (x.onclick = () => { dirty.add("filters"); filters.splice(+x.dataset.del, 1); drawF(); }));
    };
    drawF();
    $("#addf", box).onclick = () => { dirty.add("filters"); filters.push({ field: "price", op: "<=", value: "" }); drawF(); };
    $$("[data-qa]", box).forEach((b) => {
      const inp = $(`#qa${b.dataset.qa}`, box);
      const answer = () => {
        const a = inp.value.trim(); if (!a) return inp.focus();
        const job = $("#job", this.el);
        job.value = `${job.value.trim()}\n${inp.dataset.q} ${a}`;
        this.draft();
      };
      b.onclick = answer;
      enterSends(inp, answer);
    });
    $("#create", box).onclick = async () => {
      const url = $("#url", box), start = siteUrl(url.value);
      url.setCustomValidity(start === false ? "That isn’t a web address. It looks like example.com or https://…" : "");
      if (!url.reportValidity()) return;
      if (start) url.value = start;
      const more = [...(this.picked || [])].filter((u) => u !== start);  // the other sites you ticked: learned one after another
      const body = { ...d, name: $("#nm", box).value.trim() || d.name, start_url: start, goal: $("#goal", box).value, every_minutes: every, more_sites: more,
        filters: filters.map((f) => ({ ...f, value: isNaN(+f.value) || f.value === "" ? f.value : +f.value, text: `${f.field} ${OP_WORDS[f.op] || f.op} ${f.value}` })) };
      const btn = $("#create", box);
      busyBtn(btn, true, "Creating…");
      let b;
      try { b = (await post("/api/bots", body)).bot; } catch (e) { busyBtn(btn, false); btn.textContent = label(); return toast(e.message); }
      if (body.start_url) await post(`/api/bots/${b.id}/learn`, {}).catch((e) => toast(e.message));
      await loadState();
      this.leaving = true;  // it's made: nothing to lose
      location.hash = `#/bot/${b.id}/computer?hatch=1`;
    };
  },
};

// ================================================================ a bot
const TABS = [["chat", "Chat"], ["computer", "Computer"], ["results", "Results"], ["diary", "Diary"], ["skills", "Skills"], ["about", "About you"], ["settings", "Settings"], ["activity", "Activity"], ["call", "Call"]];  // Chat is a tab on phones only
const nWord = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const onPhone = () => matchMedia("(max-width:760px)").matches;
const RUN_WORDS = { ok: "done", failed: "didn’t finish", stopped: "stopped", needs_you: "waiting for you", running: "running now" };
const RUN_KINDS = { replay: "Run", learn: "Learning", show: "Show me once" };
const EVENT_WORDS = { control: "you", handback: "handed back", answered: "you answered", denied: "not allowed", shown: "shown by you", replay: "ran", learn: "learning",  // the same words as Activity
  learned: "learned", repair: "trying a fix", fixed: "fixed a step", problem: "problem", delegate: "handed off", moved: "moved", arrived: "arrived", created: "new bot", level: "milestone", team: "team" };
const CONTROL_WORDS = { pause: "You paused it", resume: "You let it carry on", stop: "You stopped it", takeover: "You took over its computer", handback: "You handed back",
  speed: "You changed its speed", mode: "You changed where it works", "You handed its computer back": "You handed back" };
const ruleText = (f) => f.text || `${f.field} ${f.op} ${f.value}`;
const RULE_KINDS = { own: "On its own", ask: "Ask you first", never: "Never", filter: "Keep only" };
const BUILT_IN_RULES = new Set(["Read, search, take notes", "Send, post, reply, delete, submit forms, sign up", "Buy or pay"]);  // bots.DEFAULT_RULES: every bot has them, they can't be removed
const ruleBody = (r) => {  // "Never contact agencies" under a Never badge reads "contact agencies"
  const k = RULE_KINDS[r.kind] || "", t = String(r.text || "");
  const rest = k && t.toLowerCase().startsWith(k.toLowerCase() + " ") ? t.slice(k.length + 1).trim() : t;
  return rest.charAt(0).toUpperCase() + rest.slice(1);
};
const homeOf = (b) => (b.home && b.home.engine ? `${b.home.engine}:${b.home.bot}` : `${S.engineId}:${b.id}`);  // who a bot really is, across computers
const sameBot = (mine, rb) => !!(rb.home && rb.home.engine) && homeOf(mine) === `${rb.home.engine}:${rb.home.bot}`;  // never by id alone: a reset server reuses ids
const offName = (m) => (String(m || "").match(/^(.+?) isn’t answering\. It may be/) || String(m || "").match(/can’t reach (.+?):/) || [])[1];  // a moved bot's server is off
const one = (t) => String(t ?? "").replace(/\b1 results\b/g, "1 result");  // older engines and saved skills say "Read 1 results"
const idleBot = (b) => !b.run_kind && !b.takeover && !["takeover", "showing"].includes(b.status);  // nothing running and nobody at its computer
ICON.speakeroff = "M11 5L6 9H2v6h4l5 4z M23 9l-6 6 M17 9l6 6";  // the Call tab's speaker, turned off
const DRAFTS = {};  // what you were typing to each bot, kept when you go to another page and back
// ponytail: a copy of skills.parse_num()/keep(), so Results follow your rules the moment you change them; drop it if the results route re-checks rules itself
function numOf(v) {
  if (typeof v === "number") return v;
  const m = String(v ?? "").match(/-?\d[\d.,\s]*/);
  if (!m) return null;
  let t = m[0].replace(/\s/g, "").replace(/[.,]+$/, "");
  if (/^-?\d{1,3}([.,]\d{3})+$/.test(t)) t = t.replace(/[.,]/g, "");
  else if (t.includes(",") && t.includes(".")) t = t.lastIndexOf(",") > t.lastIndexOf(".") ? t.replace(/\./g, "").replace(",", ".") : t.replace(/,/g, "");
  else t = t.replace(/,/g, ".");
  const n = Number(t);
  return Number.isNaN(n) ? null : n;
}
function rowPasses(it, f) {
  if (!(f.field in it)) return true;  // the site doesn't show it: can't judge (Results says so)
  const { op } = f, want = f.value, v = it[f.field], low = (s) => String(s ?? "").trim().toLowerCase().replace(/\s+/g, " ");
  if (["<", "<=", ">", ">="].includes(op)) {
    const a = numOf(v), b = numOf(want);
    return a !== null && b !== null && { "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b }[op];
  }
  if ((op === "==" || op === "!=") && numOf(v) !== null && numOf(want) !== null) return (numOf(v) === numOf(want)) === (op === "==");
  const s = low(v);
  if (op === "==") return s === low(want);
  if (op === "!=") return s !== low(want);
  if (op === "contains") return s.includes(low(want));
  if (op === "not_contains") return !s.includes(low(want));
  if (op === "in" || op === "not_in") {
    const ws = typeof want === "string" ? want.split(/[,;]/) : want || [];
    const hit = ws.some((w) => low(w) && s.includes(low(w)));
    return op === "in" ? hit : !hit;
  }
  return true;
}
// a tab you're typing in (or picked something in) isn't redrawn under you
const tabBusy = (el) => [...el.querySelectorAll("input,textarea,select")].some((x) => x === document.activeElement || x.dataset.touched
  || ((x.tagName === "TEXTAREA" || x.type === "text") && x.value !== x.defaultValue));
const follow = (x, v) => { if (x && x !== document.activeElement && x.value === x.defaultValue) x.value = x.defaultValue = v; };  // a field you aren't editing shows the bot as it is now
function keepFocus(box, draw) {  // redraw part of a tab; the focus goes back to the same control (by id or data-*), or the one now in its place
  const a = document.activeElement, inside = a && a !== document.body && box.contains(a);
  const sel = inside && (a.id ? `#${CSS.escape(a.id)}` : [...a.attributes].filter((x) => x.name.startsWith("data-")).map((x) => `[${x.name}="${CSS.escape(x.value)}"]`).join(""));
  draw();
  if (!inside || box.contains(a)) return;
  const f = sel && $(a.tagName.toLowerCase() + sel, box);
  if (f && !f.disabled) f.focus();
}
document.addEventListener("click", (e) => $$("details.more[open]").forEach((d) => { if (!d.contains(e.target)) d.open = false; }));

VIEWS.bot = {
  live: true,  // redraws keep what you type: the chat box is never redrawn, and a tab only when you aren't busy in it
  async show(el, [id, tab = "computer"], qs) {
    const asked = tab;
    if (tab === "chat" && !onPhone()) tab = "computer";
    if (!TABS.some(([k]) => k === tab)) tab = "computer";
    this.id = +id; this.tab = tab; this.el = el; this.data = null; this.msgKey = this.headKey = this.tabSeen = this.chatTop = this.named = null; this.bringing = false;
    if (!/^\d+$/.test(id)) return this.missing(el, new Error("no such bot"));  // #/bot/abc
    const known = S.bots.find((x) => x.id === +id);
    if (known && (known.remote || known.status === "moved"))  // its server can take a few seconds: say so instead of a blank page
      el.innerHTML = `${mobileBar(known.name)}<div class="page narrow"><p class="lede row" role="status"><span class="spin" aria-hidden="true"></span>Asking ${esc(known.remote || "its server")}…</p></div>`;
    let data;
    try { data = await get(`/api/bots/${this.id}`); } catch (e) { return this.missing(el, e); }
    if (this.id !== +id || !el.isConnected) return;  // you went elsewhere meanwhile
    this.data = data;
    const b = data.bot;
    if (asked !== tab) history.replaceState(null, "", `#/bot/${b.id}/${tab}`);
    const hint = matchMedia("(pointer:coarse)").matches ? "" : `<span class="kbdhint"><span class="mono">${MAC ? "⌘K" : "Ctrl K"}</span> command bar · </span>`;
    el.innerHTML = `<a class="skipchat" href="#/bot/${b.id}/chat">Skip to chat</a>${mobileBar(b.name)}<div class="botpage t-${tab}"><div class="bothead" id="bh"></div><div class="botbody">
      <section class="rightcol"><nav class="tabs" aria-label="Bot views">${TABS.map(([k, t]) => `<a href="#/bot/${b.id}/${k}" data-t="${k}" class="${k === tab ? "on" : ""}${k === "chat" ? " only-s" : ""}"${k === tab ? ' aria-current="page"' : ""}>${t}</a>`).join("")}</nav><div class="tabbody" id="tb"></div></section>
      <section class="chatcol" aria-label="Conversation"><div class="msgs" id="msgs" role="log" aria-live="polite" aria-label="Messages with ${esc(b.name)}"></div>
        <div class="chatlive hidden" id="chatlive" role="status"></div>
        <div class="chatin"><div class="chatbox"><label class="vh" for="say">Message ${esc(b.name)}</label><input id="say" placeholder="Message ${esc(b.name)}…" autocomplete="off">
        <div class="between"><span class="small muted">${hint}say “slower”, “stop”, or give it a rule</span><span class="row"><a class="iconbtn" href="#/bot/${b.id}/call" aria-label="Call">${icon("mic")}</a><button class="iconbtn" id="send" style="background:var(--ink);color:#fff;border:0" aria-label="Send">${icon("send", 17, 2.2)}</button></span></div></div></div></section></div></div>`;
    $(".skipchat", el).onclick = (e) => { e.preventDefault(); if (onPhone()) this.go("chat"); $("#say").focus(); };  // before the tabs' own click: on a computer, chat isn't a tab
    const nav = $(".tabs", el), fade = () => { nav.classList.toggle("fr", nav.scrollLeft + nav.clientWidth < nav.scrollWidth - 4); nav.classList.toggle("fl", nav.scrollLeft > 4); };
    nav.onscroll = fade;
    new ResizeObserver(fade).observe(nav);
    const on = $("a.on", nav); if (on) on.scrollIntoView({ block: "nearest", inline: "center" });
    const send = async () => {
      const t = $("#say").value.trim(), id = this.id, mine = { role: "you", text: t, ts: Date.now() / 1000 }; if (!t) return;
      $("#say").value = "";
      this.data.messages.push(mine);
      this.typing = true; this.drawMsgs(true);
      try { await post(`/api/bots/${id}/chat`, { text: t }); }
      catch (e) {  // it didn't go: your words go back in the box, to send again
        const off = offName(e.message);
        toast(off ? `${off} isn’t answering, so your message didn’t reach ${this.data ? this.data.bot.name : "the bot"}. It’s back in the box.` : e.message);
        if (id !== this.id || !this.data) { if (!DRAFTS[id]) DRAFTS[id] = t; return; }
        this.data.messages = this.data.messages.filter((m) => m !== mine);
        this.typing = false; this.drawMsgs(true);
        const say = $("#say"); if (say && !say.value.trim()) { say.value = t; say.focus(); }
      }
      this.typing = false; this.refresh();
    };
    $("#send").onclick = send;
    $("#say").onkeydown = (e) => { if (e.key === "Enter" && !e.isComposing) send(); };
    $("#say").value = DRAFTS[b.id] || "";
    $("#tb").addEventListener("change", (e) => { if (e.target.tagName === "SELECT") e.target.dataset.touched = "1"; });
    el.addEventListener("click", (e) => {  // this bot's tabs switch in place: the chat, what you typed in it and where you scrolled stay
      const a = e.target.closest && e.target.closest("a[href]");
      const m = a && !e.defaultPrevented && !e.button && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey && a.getAttribute("href").match(/^#\/bot\/(\d+)\/(\w+)$/);
      if (!m || +m[1] !== this.id) return;
      e.preventDefault();
      const d = a.closest("details"); if (d) d.open = false;
      this.go(m[2]);
    });
    this.drawHead(); this.drawMsgs(true); this.drawTab(true);
    if (qs && qs.get("hatch")) { history.replaceState(null, "", `#/bot/${b.id}/${tab}`); hatch(b, (this.data.messages.find((m) => m.intro) || {}).text); }
  },
  go(tab) {  // another tab of this bot, without leaving the page
    if (tab === "chat" && !onPhone()) tab = "computer";
    if (!TABS.some(([k]) => k === tab)) tab = "computer";
    const page = $(".botpage", this.el), box = $("#msgs");
    if (!page || tab === this.tab) return;
    if (this.tab === "call" && this.callEnd) { this.callEnd(); this.callEnd = null; }
    if (this.tab === "chat" && box) this.chatTop = box.scrollHeight - box.scrollTop - box.clientHeight < 40 ? null : box.scrollTop;  // a hidden box forgets its scroll
    this.tab = tab; this.tabSeen = null;
    history.replaceState(null, "", `#/bot/${this.id}/${tab}`);
    page.className = page.className.replace(/\bt-\w+/, "t-" + tab);
    $$(".tabs a[data-t]", this.el).forEach((a) => { const on = a.dataset.t === tab; a.classList.toggle("on", on); if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    const on = $(".tabs a.on", this.el); if (on) on.scrollIntoView({ block: "nearest", inline: "center" });
    if (tab === "chat" && box) box.scrollTop = this.chatTop ?? 1e9;
    $("#tb").innerHTML = ""; $("#tb").scrollTop = 0;  // never the last tab's content under this tab's name, even for a moment
    this.drawTab(true);
  },
  missing(el, e) {  // no such bot, it lives on a computer that isn't answering, or it's gone from there
    const known = S.bots.find((x) => x.id === this.id), msg = String(e.message || "");
    const gone = msg.match(/ is no longer on (.+?)\.?$/);
    const away = !gone && !!known && (known.status === "moved" || !!offName(msg));
    if (!gone && !away && !msg.includes("no such bot")) throw e;  // anything else: the router's error page
    const where = offName(msg) || known && known.remote || "another computer";
    this.data = null;  // nothing here to refresh
    el.innerHTML = `${mobileBar(known ? known.name : "Inky")}<div class="page narrow">${known ? botCritter({ ...known, status: "idle", needs: 0 }, 90) : critter("octopus", "#E86F51", "none", 90, "worried")}
      ${gone ? `<h1 style="overflow-wrap:anywhere">It’s no longer on ${esc(gone[1])}</h1><p class="lede">${esc(known ? known.name : "This bot")} was deleted there, or that computer was reset. Only this computer still lists it.</p>
        <div class="row wrap"><button class="btn p" id="rmhere">Remove it here</button><a class="btn" href="#/bots">Your bots</a></div>`
      : away ? `<h1 style="overflow-wrap:anywhere">${esc(known.name)} is on ${esc(where)}</h1><p class="lede">That computer isn’t answering right now. It may be asleep, switched off or offline.</p>
        <div class="row wrap"><button class="btn p" id="retry">Try again</button><button class="btn bringback">Bring back to this computer</button><button class="btn hot" id="rmhere">Remove it here</button></div><span class="small muted" id="mvline" role="status"></span>`
      : `<h1>This bot doesn’t exist anymore</h1><p class="lede">It may have been deleted, here or on another computer.</p><div><a class="btn p" href="#/bots">Your bots</a></div>`}</div>`;
    if (away) { $("#retry", el).onclick = () => route(); $(".bringback", el).onclick = () => this.bringBack(); }
    if (gone || away) $("#rmhere", el).onclick = async (ev) => {
      const btn = ev.currentTarget, name = known ? known.name : "this bot";
      if (away && !(await confirmBox(`Remove ${name} from this computer only? The copy on ${where} stays.`, "Remove it here", true))) return;
      busyBtn(btn, true, "Removing…");
      try { await del(`/api/bots/${this.id}?here=1`); } catch (err) { busyBtn(btn, false); return toast(err.message); }
      await loadState().catch(() => {});
      toast(`Removed ${name} from this computer.`);
      location.hash = "#/bots";
    };
  },
  oops(e) {  // an action that didn't go through
    const b = this.data && this.data.bot;
    if (b && b.remote && /can’t reach|isn’t answering/.test(e.message || "")) try { return this.missing(this.el, e); } catch (x) {}  // its server is off: say so, with Try again and Bring back
    toast(e.message);
  },
  bringBack() {
    $$(".bringback").forEach((x) => (x.disabled = true));
    this.bringing = true;
    const l = $("#mvline"); if (l) l.textContent = "Asking it to pack up…";
    post(`/api/bots/${this.id}/bring-back`).catch((e) => { toast(e.message); $$(".bringback").forEach((x) => (x.disabled = false)); });
  },
  async refresh(force) {
    if (!this.id || !this.data) return;
    const id = this.id;
    let d; try { d = await get(`/api/bots/${id}`); } catch (e) { if (id === this.id && this.data && / is no longer on /.test(e.message)) this.missing(this.el, e); return; }
    if (id !== this.id || !this.data) return;  // you went to another bot meanwhile
    this.data = d;
    this.drawHead(); this.drawMsgs(); this.drawTab(false, force);
  },
  edit(fn) {  // one change at a time, each made to the bot as it is now, so nothing added meanwhile is lost
    const id = this.id;
    const go = async () => { const d = await get(`/api/bots/${id}`); if (id === this.id) return fn(d); };
    this.queue = (this.queue || Promise.resolve()).then(go, go);
    return this.queue.catch((e) => this.oops(e));
  },
  onEvent(m) {
    if (m.kind !== "move" || m.bot !== this.id) return;
    const l = $("#mvline"), back = this.bringing || !!(this.data ? this.data.bot.remote : (S.bots.find((b) => b.id === m.bot) || {}).status === "moved");
    const down = /Errno|refused|timed? ?out|unreachable|connect/i.test(m.text || "");  // it packs up over there, so that computer has to be on
    const text = m.step !== "failed" ? m.text || m.step
      : back ? (down || !m.text ? "Couldn’t bring it back: its computer isn’t answering. It can only pack up while that computer is on." : `Couldn’t bring it back: ${m.text}`)
      : `Couldn’t move it: ${m.text || "the other computer isn’t answering."}`;
    if (l) l.textContent = text; else toast(text, this.data ? this.data.bot : S.bots.find((b) => b.id === m.bot));
    if (m.step === "failed") { this.bringing = false; $$(".bringback").forEach((x) => (x.disabled = false)); }
    if (m.step === "done") loadState().then(route);
  },
  leave() {
    if (this.callEnd) this.callEnd();
    const s = $("#say"); if (s && this.id) DRAFTS[this.id] = s.value;
    this.callEnd = null; this.id = null;
  },
  drawHead() {
    const b = this.data.bot, m = botMeta(b), tk = b.takeover, show = b.run_kind === "show";
    if (this.named !== b.name) {  // renamed: the chat box, its label and the bar above say the new name
      this.named = b.name;
      const say = $("#say"), mb = $(".mobilebar b", this.el);
      if (say) { say.placeholder = `Message ${b.name}…`; $('label[for="say"]').textContent = `Message ${b.name}`; $("#msgs").setAttribute("aria-label", `Messages with ${b.name}`); }
      if (mb) mb.textContent = b.name;
    }
    this.drawLive();
    const meta = tk ? (show ? "showing it once" : "you have control") : m.meta;
    const key = JSON.stringify([b.name, meta, m.hot, b.status, b.run_kind, tk, b.library, b.allowed_domains, b.remote, b.mode, b.look, moodOf(b, RECENT)]);
    $$('.tabs a[data-t="chat"]').forEach((a) => a.classList.toggle("dot", this.data.needs.length > 0));
    if (key === this.headKey) return;
    this.headKey = key;
    const open = !!$("#bh details.more[open]");
    const lib = b.library ? `<span class="badge hide-s" title="From the library${b.library.author ? " · by " + esc(b.library.author) : ""}. It only visits ${esc((b.allowed_domains || []).join(", "))}.">library · ${esc((b.allowed_domains || []).join(", "))}</span>` : "";
    // while you have its computer, Hand back (Computer tab) is the way on: Resume or Run now would take it from you
    $("#bh").innerHTML = `<div class="row" style="min-width:0">${botCritter(b, 30)}<h1>${esc(b.name)}</h1><span class="pill ${m.hot ? "hot" : ""} ${["working", "learning", "takeover", "showing"].includes(b.status) ? "live" : ""}" title="${esc(meta)}"><i style="background:${tk ? "var(--ink)" : m.color}"></i><span>${esc(meta)}</span></span>${lib}
      <span class="mono small muted hide-s row where" style="gap:5px">${icon(b.remote ? "server" : "monitor", 13)}<span>${esc(b.remote || (b.mode === "screen" ? "your screen" : "its own computer"))}</span></span></div>
      <div class="row" style="flex-shrink:0">${show || tk ? "" : b.run_kind ? `<button class="btn s" id="pz">${b.status === "paused" ? "Resume" : "Pause"}</button>` : `${b.held ? `<button class="btn s" id="pz" title="Its schedule is paused">Resume schedule</button>` : ""}<button class="btn s" id="runnow">Run now</button>`}
      ${b.remote ? `<button class="btn s hide-s bringback" title="Move ${esc(b.name)}, its memory and skills back to this computer">Bring back</button>` : ""}
      <a class="iconbtn hide-s" href="#/bot/${b.id}/call" aria-label="Call ${esc(b.name)}">${icon("phone", 16, 1.9)}</a><button class="btn s hide-s sharebot" title="Download it, make a link, or post it to the library">Share</button>
      <details class="more"${open ? " open" : ""}><summary class="iconbtn" aria-label="More">⋯</summary><div class="card menu">
        <a href="#/bot/${b.id}/call">${icon("phone", 16, 1.9)} Call ${esc(b.name)}</a><button class="sharebot">Share</button>${b.remote ? `<button class="bringback">Bring back to this computer</button>` : ""}</div></details></div>`;
    const pz = $("#pz"); if (pz) pz.onclick = () => post(`/api/bots/${b.id}/control`, { cmd: b.status === "paused" || (b.held && !b.run_kind) ? "resume" : "pause" }).then(refreshSoon).catch((e) => this.oops(e));
    const rn = $("#runnow"); if (rn) rn.onclick = () => post(`/api/bots/${b.id}/run`, {}).then(refreshSoon).catch((e) => this.oops(e));
    $$("#bh .sharebot").forEach((x) => (x.onclick = () => { const d = $("#bh details.more"); if (d) d.open = false; shareBot(b); }));
    $$("#bh .bringback").forEach((x) => (x.onclick = () => this.bringBack()));
    const more = $("#bh details.more");
    more.onkeydown = (e) => { if (e.key === "Escape" && more.open) { e.preventDefault(); e.stopPropagation(); more.open = false; $("summary", more).focus(); } };
  },
  drawLive() {  // in the chat, while it works: what it's doing, the AI it used, which model is thinking right now, and Stop
    const box = $("#chatlive"); if (!box || !this.data) return;
    const b = { ...this.data.bot, ...(S.bots.find((x) => x.id === this.data.bot.id) || {}) };  // the newest step, even while you type
    const t = (S.thinking || []).find((x) => x.bot === b.id), run = b.run_kind;
    if (!run && !t) { box.classList.add("hidden"); box.innerHTML = ""; this.liveKey = ""; return; }
    let site = ""; try { site = new URL(b.start_url).hostname.replace(/^www\./, ""); } catch (e) {}
    const what = run === "learn" ? `Learning ${site || "a site"}` : run === "show" ? "Watching you show it" : run ? "Working" : "Thinking";
    const key = JSON.stringify([what, b.step, b.ai_calls, b.status, t && t.model]);
    if (key === this.liveKey) return;
    this.liveKey = key;
    box.classList.remove("hidden");
    box.innerHTML = `<span class="livedot" aria-hidden="true"></span><span class="grow small"><b>${esc(what)}</b>${b.step ? ` · ${esc(b.step)}` : ""}${run ? ` · ${plural(b.ai_calls || 0, "AI call")}` : ""}
        ${t ? `<br><span class="muted"><b class="mono">${esc(t.model)}</b> is thinking · <span data-since="${t.since}">${Math.round(Date.now() / 1000 - t.since)} s</span></span>` : run === "replay" ? `<br><span class="muted">no AI needed</span>` : ""}</span>
      ${run && run !== "show" ? `<button class="btn s" id="livepause">${b.status === "paused" ? "Resume" : "Pause"}</button>` : ""}<button class="btn s hot" id="livestop">Stop</button>`;
    const lp = $("#livepause"); if (lp) lp.onclick = () => post(`/api/bots/${b.id}/control`, { cmd: b.status === "paused" ? "resume" : "pause" }).then(refreshSoon).catch((e) => this.oops(e));
    $("#livestop").onclick = async () => {
      busyBtn($("#livestop"), true, "Stopping…");
      await post(`/api/models/stop`, { bot: b.id }).catch(() => {});
      await post(`/api/bots/${b.id}/control`, { cmd: "stop" }).catch(() => {});
      refreshSoon();
    };
  },
  drawMsgs(force) {
    const box = $("#msgs"); if (!box) return;
    const b = this.data.bot, open = this.data.needs || [];
    const key = JSON.stringify([this.data.messages.map((m) => m.id + (m.chips_used ? "u" : "")).join(), (this.data.messages.at(-1) || {}).text, !!this.typing,
      open.map((n) => n.id), Object.keys(CHOSEN).filter((k) => k.startsWith(this.id + ":"))]);
    if (!force && key === this.msgKey) return;
    this.msgKey = key;
    // what you chose on an answered card: this session's click, else the "You chose …" event right after it
    const answers = this.data.events.filter((e) => e.kind === "answered").map((e) => ({ ...e, m: e.text.match(/^You chose “(.*?)”: ([\s\S]*)$/) })).filter((e) => e.m);
    const choiceFor = (m, next) => CHOSEN[`${this.id}:${m.need}`] || (answers.find((a) => (a.need ? a.need === m.need
      : (m.text === a.m[2] || m.text.startsWith(a.m[2] + ". ")) && a.ts >= m.ts && (!next || a.ts < next.ts))) || { m: [] }).m[1];
    let lastDay = "";
    const msgs = [];  // "Checked 11 results…" six times in a row reads as one line with ×6
    for (const m of this.data.messages) {
      const last = msgs.at(-1);
      if (last && m.role === "bot" && last.role === "bot" && m.text === last.text && !m.need && !(m.chips || []).length) last.times = (last.times || 1) + 1;
      else msgs.push({ ...m });
    }
    const atEnd = box.scrollHeight - box.scrollTop - box.clientHeight < 40;  // you scrolled up to read: stay there
    box.innerHTML = msgs.map((m, idx) => {
      const d = new Date(m.ts * 1000).toDateString();
      const day = d !== lastDay ? `<div class="m sys">${d === new Date().toDateString() ? "Today" : d} ${hhmm(m.ts)}</div>` : "";
      lastDay = d;
      if (m.role === "you") return `${day}<div class="m you"><div class="body">${esc(m.text)}</div></div>`;
      if (m.role === "note") return `${day}<div class="m sys">${esc(m.text)}</div>`;
      if (m.role === "peer") { const sb = S.bots.find((x) => x.id === m.sender_id) || { look: {}, status: "idle" };
        return `${day}<div class="m peer">${botCritter(sb, 26)}<div class="body"><span class="small" style="color:var(--coral-t);font-weight:600">${esc(m.sender)}</span><span>${esc(m.text)}</span></div></div>`; }
      const need = m.need ? open.find((n) => n.id === m.need) : null;
      const picked = m.need && choiceFor(m, msgs.slice(idx + 1).find((x) => x.text === m.text));
      const card = need ? `<div class="card hot needcard" style="padding:12px 14px"><span class="small" style="color:var(--coral-t);font-weight:600">Needs you</span><b>${esc(need.title)}</b>${need.body ? `<span class="small muted">${esc(need.body)}</span>` : ""}
        <div class="row wrap">${(need.options || []).map((o, i) => `<button class="btn s ${i === 0 ? "p" : ""}${picked === o ? " chosen" : ""}" data-need="${need.id}" data-bot="${this.id}" data-o="${esc(o)}"${picked ? " disabled" : ""}>${esc(o)}</button>`).join("")}</div>
        ${picked ? `<span class="small muted">You chose “${esc(picked)}”…</span>` : ""}</div>`
        : picked ? `<span class="logl">● You chose “${esc(picked)}”</span>` : "";
      const done = (m.done || []).filter(Boolean).map((x) => `<span class="logl">● ${esc(one(x))}</span>`).join("");
      const chips = (m.chips || []).length ? `<div class="row wrap">${m.chips_used ? `<span class="logl">● done</span>` : m.chips.map((c, i) => `<button class="btn s p" data-chip="${m.id}" data-ci="${i}">${esc(c.label)}</button>`).join("")}</div>` : "";
      const said = need ? "" : `<span>${esc(one(m.text))}${m.times ? ` <span class="badge">×${m.times}</span>` : ""}</span>`;  // an open question's card says it already
      return `${day}<div class="m">${botCritter(b, 26)}<div class="body">${said}${done}${chips}${card}</div></div>`;
    }).join("") || `<div class="m sys">Say hi, or give it a job.</div>`;
    if (this.typing) box.insertAdjacentHTML("beforeend", `<div class="m">${botCritter(b, 26)}<div class="body typing" aria-label="${esc(b.name)} is typing"><i></i><i></i><i></i></div></div>`);
    $$("[data-need]", box).forEach((x) => (x.onclick = () => answerNeed(+x.dataset.bot, +x.dataset.need, x.dataset.o)));
    $$("[data-chip]", box).forEach((x) => (x.onclick = async () => {
      const m = this.data.messages.find((y) => y.id === +x.dataset.chip), c = m && m.chips[+x.dataset.ci];
      if (!c) return;
      x.disabled = true;
      const body = c.offer != null ? { offer: c.offer, message: m.id } : { apply: c.apply, message: m.id };  // an offer is something it wanted to do: you said yes
      try { await post(`/api/bots/${this.id}/apply`, body); if (c.offer == null) toast(c.label, b); this.refresh(true); } catch (e) { x.disabled = false; toast(e.message); this.refresh(true); }
    }));
    if (force || atEnd) box.scrollTop = 1e9;
  },
  tabKey() {  // what each tab shows: it's only redrawn when that changed
    const d = this.data, b = d.bot;
    return JSON.stringify(this.tab === "settings" ? [b.name, b.schedule, b.rules, b.mode, b.automations, b.remote, (b.memory || []).length, S.settings.screen_allowed]
      : this.tab === "about" ? b.memory
      : this.tab === "results" ? [b.filters, d.runs[0]]
      : this.tab === "skills" ? [d.skills, d.runs, b.start_url, b.goal, S.settings.n8n_connected]
      : this.tab === "activity" ? [d.events, d.runs]
      : this.tab === "diary" ? [d.growth, d.diary, b.look]
      : [b, d.skills, d.runs[0], d.events.slice(0, 12), hhmm(Date.now() / 1000)]);
  },
  drawTab(first, force) {  // force: after your own change; what you typed elsewhere in the tab stays
    const tb = $("#tb"), fn = this["tab_" + this.tab], live = this["live_" + this.tab];
    if (!tb || !fn) return;
    const key = this.tabKey(), own = ["computer", "call"].includes(this.tab) || !!live;  // these update in place and keep their own inputs
    if (!first && !force && (key === this.tabSeen || (!own && tabBusy(tb)))) return;
    this.tabSeen = key;
    if (!first && live && $(`[data-tab="${this.tab}"]`, tb)) return keepFocus(tb, () => live.call(this, tb));  // only what isn't yours to type in
    const a = document.activeElement, fid = a && tb.contains(a) && a.id;
    const keep = force ? $$("input[id],textarea[id]", tb).filter((x) => x.value !== x.defaultValue).map((x) => [x.id, x.value]) : [];
    fn.call(this, tb, first);
    keep.forEach(([id, v]) => { const x = document.getElementById(id); if (x) x.value = v; });
    const f = fid && document.getElementById(fid); if (f && !f.disabled) f.focus();
  },
  aiPerRun(skill) {  // from its finished runs, not a promise
    const rs = this.data.runs.filter((r) => r.kind === "replay" && r.skill === skill.name && r.status === "ok");
    return rs.length ? Math.round((rs.reduce((a, r) => a + (r.ai_calls || 0), 0) / rs.length) * 10) / 10 : 0;
  },

  // ---- Computer tab: live view, take over, show me once, timeline
  tab_computer(tb, first) {
    const b = this.data.bot, run = b.run_kind, tk = b.takeover, show = run === "show", paused = b.status === "paused";
    const sk = this.data.skills, r0 = this.data.runs.find((r) => r.learned || r.skill);  // the skill it runs now, else the one it last learned or ran
    const skill = sk.find((s) => s.id === b.skill_id) || (r0 && sk.find((s) => s.id === r0.learned || s.name === r0.skill)) || sk.at(-1);
    if (first || !$("#live")) {
      tb.innerHTML = `<div class="between wrap"><span class="row" id="drv"></span><span class="row wrap">
        <span class="seg" id="speed" role="group" aria-label="Speed">${["slow", "normal", "turbo"].map((s) => `<button data-s="${s}">${cap(s)}</button>`).join("")}</span>
        <button class="btn s" id="tk"></button><button class="btn s" id="stop">Stop</button></span></div>
        <div class="row screenrow" style="align-items:flex-start;gap:14px"><div class="grow col" style="gap:8px;min-width:min(420px,100%)">
          <div class="screen" id="scr"><div class="bar"><span>Activities</span><span id="clock"></span><span>${esc(b.name.toLowerCase().replace(/\s+/g, "-"))}</span></div>
          <img id="live" alt="${esc(b.name)}’s computer, live"><div class="idle hidden" id="idle">${botCritter(b, 64)}<b>Not running right now</b><span class="small" id="idlehow"></span></div>
          <span class="over hidden" id="over">You have control · ${esc(b.name)} is waiting</span></div>
          <div class="col hidden" id="typebar" style="gap:8px">
            <div class="row wrap"><label class="vh" for="gourl">Go to an address</label><input class="f" id="gourl" style="flex:1 1 200px" placeholder="Go to an address, like example.com"><button class="btn s" id="gobtn">Go</button></div>
            <div class="row wrap"><label class="vh" for="typ">Type text into the page</label><input class="f" id="typ" style="flex:1 1 200px" placeholder="Type text into the page"><button class="btn s" id="typbtn">Type it</button>
              <span class="small muted">Press a key:</span><button class="btn s" data-key="Enter">Enter</button><button class="btn s" data-key="Tab">Tab</button><button class="btn s" data-key="Backspace" aria-label="Backspace">⌫</button></div></div>
          <div class="card hot hidden" id="showbar"><b>Show me once</b><span class="small">Click what it should click on its computer. Each click is recorded. <span id="shown"></span></span><div class="row"><button class="btn s p" id="showdone">Done showing</button></div></div>
        </div><aside class="card sidecard" id="side"></aside></div>
        <div class="col" style="gap:8px"><div class="between wrap"><b class="small" id="tlname"></b><span class="mono small muted" id="tlnote"></span></div><div class="steps" id="tl"></div></div>`;
      $$("#speed button").forEach((x) => (x.onclick = () => post(`/api/bots/${b.id}/control`, { cmd: "speed", value: x.dataset.s }).then(refreshSoon).catch((e) => this.oops(e))));
      $("#stop").onclick = () => post(`/api/bots/${b.id}/control`, { cmd: "stop" }).then(refreshSoon).catch((e) => this.oops(e));
      const img = $("#live");
      img.onclick = (e) => {
        if (!this.data.bot.takeover) return;
        const r = img.getBoundingClientRect();
        post(`/api/bots/${b.id}/input`, { kind: "click", x: Math.round((e.clientX - r.left) / r.width * 1280), y: Math.round((e.clientY - r.top) / r.height * 800) }).then(refreshSoon);
      };
      img.addEventListener("wheel", (e) => { if (this.data.bot.takeover) { e.preventDefault(); post(`/api/bots/${b.id}/input`, { kind: "scroll", y: Math.round(e.deltaY) }); } }, { passive: false });
      const typeIt = () => { const t = $("#typ").value; if (t) post(`/api/bots/${b.id}/input`, { kind: "type", text: t }).catch((x) => toast(x.message)); $("#typ").value = ""; };
      const goIt = () => { const u = $("#gourl").value.trim(); if (u) post(`/api/bots/${b.id}/input`, { kind: "goto", text: u }).catch((x) => toast(x.message)); };
      $("#typ").onkeydown = (e) => { if (e.key === "Enter" && !e.isComposing) typeIt(); };
      $("#gourl").onkeydown = (e) => { if (e.key === "Enter" && !e.isComposing) goIt(); };
      $("#typbtn").onclick = typeIt; $("#gobtn").onclick = goIt;
      $$("#typebar [data-key]").forEach((x) => (x.onclick = () => post(`/api/bots/${b.id}/input`, { kind: "key", key: x.dataset.key })));
      $("#showdone").onclick = () => post(`/api/bots/${b.id}/show/done`, {}).then(refreshSoon).catch((e) => this.oops(e));
      img.onerror = () => setTimeout(() => { if (img.getAttribute("src")) img.src = screenUrl(b.id, "mjpg") + "&r=" + Date.now(); }, 2000);
    }
    const idle = idleBot(b), img = $("#live");  // an idle bot's computer is a blank page: show that it's resting, and don't start its browser for nothing
    if (idle) img.removeAttribute("src");
    else if (!img.getAttribute("src")) img.src = screenUrl(b.id, "mjpg");
    img.classList.toggle("hidden", idle); $("#idle").classList.toggle("hidden", !idle);
    const site = b.start_url || sk.length;  // Run now learns its site, or replays a skill; with neither it can only ask for a site
    $("#idlehow").innerHTML = site ? "Press Run now, or Take over to use its computer yourself." : `Tell it a site in the chat, or in <a href="#/bot/${b.id}/skills">Skills</a> → Learn a new site.`;
    $("#clock").textContent = new Date().toTimeString().slice(0, 5);
    const name = esc(b.name), calls = nWord(b.ai_calls, "AI call");
    const [what, how, dot] = tk ? (show ? ["Show it once", "click what it should click", "var(--ink)"] : ["You have control", "click and type on it", "var(--ink)"])
      : paused ? [`${name} is paused`, "press Resume to carry on", "var(--faint)"]
      : run && b.status === "needs_you" ? [`${name} is waiting for you`, "answer in the chat", "var(--coral)"]
      : run === "learn" ? [`${name} is learning`, `asks the AI once per step · ${calls}`, "var(--coral)"]
      : run ? [`${name} is driving`, `replaying a saved skill · ${calls}`, "var(--coral)"]
      : [`${name}’s computer`, "not running", "var(--line2)"];
    $("#drv").innerHTML = `<span class="dot" style="background:${dot}"></span><b>${what}</b><span class="muted">· ${how}</span>`;
    const tkb = $("#tk");
    tkb.textContent = tk ? "Hand back" : "Take over";
    tkb.className = "btn s" + (tk ? " p" : "") + (show ? " hidden" : "");  // while showing, Done showing is the way out
    tkb.onclick = () => post(`/api/bots/${b.id}/control`, { cmd: tk ? "handback" : "takeover" }).then(refreshSoon).catch((e) => this.oops(e));
    $("#stop").disabled = !run;
    $("#scr").classList.toggle("drive", !!tk);
    $("#over").classList.toggle("hidden", !tk || show);
    $("#typebar").classList.toggle("hidden", !tk || show);  // showing it once records clicks only, not typing
    $("#showbar").classList.toggle("hidden", !show);
    $("#shown").textContent = b.shown ? `${b.shown} recorded.` : "";
    $$("#speed button").forEach((x) => { const on = x.dataset.s === (b.look.speed || "normal"); x.classList.toggle("on", on); x.setAttribute("aria-pressed", on); });
    const mem = (b.memory || []).map((m) => `<span class="chip">${esc(m.text)}</span>`).join("") || `<span class="small muted">Nothing yet</span>`;
    const n = sk.length, done = this.data.runs.find((r) => r.status !== "running"), row = (k, v) => `<div class="between"><span class="muted">${k}</span><span>${v}</span></div>`;
    const went = (r) => (r ? esc(RUN_WORDS[r.status] || r.status) + " · " + ago(r.ts) : "–");
    $("#side").innerHTML = (run ? `<div class="head"><b>This run</b><span class="mono small muted">${calls}</span></div>
      <div class="col small" style="gap:6px">${row("Skill", run === "learn" ? "learning a new one" : esc(skill ? skill.name : "none yet"))}
      ${row("Step", `<span class="mono">${b.step_n || "–"}${skill && run !== "learn" ? " of " + skill.steps.length : ""}</span>`)}${row("Last run", went(done))}</div>`
      : `<div class="head"><b>Last run</b><span class="mono small muted">${done ? nWord(done.ai_calls || 0, "AI call") : ""}</span></div>
      <div class="col small" style="gap:6px">${row("Skill", done && done.kind === "learn" ? esc((sk.find((s) => s.id === done.learned) || { name: "learning a new one" }).name) : esc((done && done.skill) || (skill ? skill.name : "none yet")))}
      ${row("How it went", went(done))}${done && done.items != null ? row("Results", done.items) : ""}</div>`) + `
      <div style="height:1px;background:var(--line)"></div><div class="head"><b>It remembers</b><a class="small" href="#/bot/${b.id}/about">Edit</a></div><div class="row wrap" style="gap:6px">${mem}</div>
      <div style="height:1px;background:var(--line)"></div><div class="col" style="gap:6px">${this.data.events.filter((e) => ["fixed", "repair", "problem", "learned"].includes(e.kind)).slice(0, 3).map((e) => `<span class="logl">${hhmm(e.ts)} · ${esc(one(e.text))}</span>`).join("") || `<span class="small muted">No fixes yet</span>`}</div>
      ${n ? `<a class="small" href="#/bot/${b.id}/skills" style="margin-top:auto;font-weight:600">${n === 1 ? "See its skill" : `See all ${n} skills`}</a>` : ""}`;
    if (skill && run !== "learn") {
      const avg = this.aiPerRun(skill);
      $("#tlname").textContent = `${skill.name} · ${nWord(skill.steps.length, "step")}`;
      $("#tlnote").textContent = `${run ? "replaying now" : "replays a saved skill"} · ${nWord(avg, "AI call")} per run`;
      const at = run ? b.step_n : 0;
      $("#tl").innerHTML = skill.steps.map((s, i) => `<div class="st ${i + 1 === at ? "cur" : ""}"><span class="n">${i + 1}</span><span class="x" title="${esc(one(s.text))}">${esc(one(s.text))}</span><span class="p"><i style="width:${i + 1 < at ? 100 : i + 1 === at ? 55 : 0}%"></i></span></div>`).join("");
    } else {  // learning: only this learning run's steps, not earlier tries
      const lr = this.data.runs.find((r) => r.kind === "learn");
      const learned = lr ? this.data.events.filter((e) => e.kind === "learn" && (e.run ? e.run === lr.id : e.ts >= lr.ts - 1)).reverse() : [];
      $("#tlname").textContent = run === "learn" ? "Learning…" : "No skill yet";
      $("#tlnote").textContent = run === "learn" ? "you can correct any step in the chat" : "";
      $("#tl").innerHTML = learned.map((e, i) => `<div class="st ${i === learned.length - 1 && run === "learn" ? "cur" : ""}"><span class="n">${i + 1}</span><span class="x" title="${esc(one(e.text))}">${esc(one(e.text))}</span><span class="p"><i style="width:${i === learned.length - 1 && run === "learn" ? 55 : 100}%"></i></span></div>`).join("")
        || `<span class="small muted">${b.start_url ? "Press Run now and it learns the site while you watch." : `Tell it a site and the job in the chat, or in <a href="#/bot/${b.id}/skills">Skills</a> → Learn a new site.`}</span>`;
    }
  },

  tab_results(tb) {
    const b = this.data.bot, runs = this.data.runs, seq = (this.resultsSeq = (this.resultsSeq || 0) + 1);
    get(`/api/bots/${this.id}/results?all=1&limit=1000`).then(({ results: all }) => {
      if (seq !== this.resultsSeq || this.tab !== "results" || !tb.isConnected) return;  // you went to another tab, or a newer draw is coming
      const f = (b.filters || []).filter((x) => x && x.field);
      const fields = new Set(all.flatMap((r) => Object.keys(r)));
      const skip = all.length ? f.filter((x) => !fields.has(x.field)) : [];  // rules this site's results can't be checked against
      const checked = f.filter((x) => !skip.includes(x));
      const rows = all.filter((r) => checked.every((x) => rowPasses(r, x)));  // your rules as they are now, also right after you change them
      const keys = [...new Set(rows.flatMap((r) => Object.keys(r)))].filter((k) => !["id", "ts", "run", "skill", "new", "last", "first"].includes(k));
      const lead = matchMedia("(max-width:640px)").matches && keys.includes("link") && (keys.find((k) => /title|name/i.test(k)) || keys.find((k) => k !== "link"));  // phones: the title is the link
      const cols = [...keys.filter((k) => k !== "link").slice(0, 5), ...keys.filter((k) => k === "link" && !lead)];  // the link goes last
      const price = keys.find((k) => /price/i.test(k)), cost = (r) => numOf(r[price]) ?? Infinity;
      rows.sort((x, y) => (price ? cost(x) - cost(y) || 0 : (y.ts || 0) - (x.ts || 0) || (y.id || 0) - (x.id || 0)));  // cheapest first, else newest first
      const last = runs.find((r) => r.kind === "replay" && r.status !== "running" && r.items != null);
      const rules = checked.length ? ` its ${checked.length === 1 ? "rule" : "rules"}` : "";
      const head = rows.length ? (checked.length ? `${nWord(rows.length, "result")} ${rows.length === 1 ? "passes" : "pass"}${rules}` : nWord(rows.length, "result"))
        : last && last.items ? `None of the last ${nWord(last.items, "result")} ${last.items === 1 ? "passes" : "pass"}${rules}` : last ? "The last run found nothing to read" : "No results yet";
      tb.innerHTML = `<div class="between wrap"><b>${head}</b><span class="row wrap">${checked.map((x) => `<span class="chip">${esc(ruleText(x))}</span>`).join("")}</span></div>
        ${skip.length ? `<div class="card panel small" style="gap:4px"><b>Couldn’t check</b>${skip.map((x) => `<span>${esc(ruleText(x))} (this site doesn’t show ${esc(x.field)})</span>`).join("")}<span class="muted">Its search may already narrow it, or tell it another way to check in the chat.</span></div>` : ""}
        ${rows.length ? `<div class="tscroll"><table class="t"><thead><tr><th><span class="vh">New</span></th>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr><td>${r.new ? '<span class="badge hot">new</span>' : ""}</td>${cols.map((c) => `<td${c === "link" || String(r[c] ?? "").length <= 24 ? ' class="nw"' : ""}>${c === "link" && r[c] ? `<a href="${esc(r[c])}" target="_blank" rel="noopener">open ↗</a>` : c === lead && r.link ? `<a href="${esc(r.link)}" target="_blank" rel="noopener">${esc(r[c] ?? "open")} ↗</a>` : esc(r[c] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
          : `<p class="muted">${last && last.items ? "Loosen a rule in Settings, or wait for the next run." : "Press Run now to check."}</p>`}`;
    }).catch((e) => { if (seq === this.resultsSeq && this.tab === "results") tb.innerHTML = `<p class="muted">Couldn’t load its results: ${esc(e.message)}</p>`; });
  },

  tab_skills(tb) {  // the skills redraw in place (live_skills); the Learn a new site box keeps what you typed
    const b = this.data.bot;
    tb.innerHTML = `<div class="row wrap" data-tab="skills"><span id="sklist" style="display:contents"></span><label class="btn s" for="skf">Import a skill</label><input type="file" id="skf" class="vh" accept=".inkyskill,.json"></div>
      <div id="skmain" style="display:contents"></div>
      <div class="card"><b>Learn a new site</b><div class="grid2"><label class="vh" for="lurl">Web address</label><input class="f" id="lurl" placeholder="https://…" value="${esc(b.start_url || "")}"><label class="vh" for="lgoal">What to do there</label><input class="f" id="lgoal" placeholder="What to do there" value="${esc(b.goal || "")}"></div><div class="row wrap"><button class="btn p" id="learn">Learn it once</button><span class="small" id="lmsg" role="status"></span></div></div>`;
    const learn = () => post(`/api/bots/${this.id}/learn`, { url: $("#lurl").value, goal: $("#lgoal").value }).then(() => this.go("computer"))
      .catch((e) => { if (this.data.bot.remote && /can’t reach|isn’t answering/.test(e.message || "")) return this.oops(e);  // the error sits by the field
        const m = $("#lmsg"); if (!m) return toast(e.message); m.className = "small bad"; m.style.background = "none"; m.textContent = e.message; $("#lurl").setAttribute("aria-invalid", "true"); $("#lurl").focus(); });
    $("#learn").onclick = learn; enterSends($("#lurl"), learn); enterSends($("#lgoal"), learn);
    $("#skf").onchange = async (e) => {
      const f = e.target.files[0]; if (!f) return;
      e.target.value = "";
      let d; try { d = JSON.parse(await f.text()); } catch (err) { return toast("That file isn’t valid JSON, so it can’t be a skill file."); }
      try { const r = await post(`/api/bots/${this.id}/skills/import`, d); this.skillSel = r.skill.id; toast(`Added the skill “${r.skill.name}”`, this.data.bot); this.refresh(true); }
      catch (err) { toast(err.message); }  // the engine says what's wrong with it
    };
    this.live_skills(tb);
  },
  live_skills(tb) {
    const sk = this.data.skills, b = this.data.bot;
    const sel = sk.find((s) => s.id === this.skillSel) || sk[0];
    const typed = (s) => s.value && ["fill", "select", "press"].includes(s.action) ? `<span class="typed">${s.action === "fill" ? "types" : s.action === "select" ? "picks" : "presses"} “${esc(s.value)}”</span>` : "";
    follow($("#lurl"), b.start_url || ""); follow($("#lgoal"), b.goal || "");
    $("#sklist").innerHTML = sk.map((s) => `<button class="btn s ${sel && s.id === sel.id ? "p" : ""}" data-sk="${s.id}" aria-pressed="${!!sel && s.id === sel.id}">${esc(s.name)}</button>`).join("");
    $("#skmain").innerHTML = sel ? `<div class="row skrow" style="align-items:flex-start;gap:14px"><div class="card"><div class="head"><h2>${esc(sel.name)}</h2><span class="mono small muted">v${sel.version || 1} · ${esc(sel.site || "")}</span></div>
        <div class="list">${sel.steps.map((s, i) => `<div class="row" style="padding:8px 0;font-size:14px;align-items:flex-start"><span class="mono small muted" style="width:22px;flex-shrink:0">${i + 1}</span><span class="grow">${esc(one(s.text))}${s.repaired ? ` <span class="badge">fixed ${s.repaired}×</span>` : ""}${s.shown ? ' <span class="badge">shown by you</span>' : ""}${s.approved_always ? ` <span class="badge">always allowed</span> <button class="chip" data-ask="${i}" style="border:0;cursor:pointer" aria-label="Ask again before step ${i + 1}, “${esc(s.text)}”">ask again</button>` : ""}${typed(s)}</span>
          <span class="mono small muted steptarget">${esc(s.action === "extract" ? nWord(Object.keys((s.spec || {}).fields || {}).length, "field") : s.target ? `${s.target.role} “${s.target.name}”` : s.value || "")}</span>${sel.steps.length > 1 ? `<button class="chip" data-rm="${i}" style="border:0;cursor:pointer" aria-label="Remove step ${i + 1}, “${esc(s.text)}”">remove</button>` : ""}</div>`).join("")}</div></div>
        <aside class="col skside"><div class="card"><b>How it runs</b><div class="grid2" style="gap:8px">${[["good runs", this.data.runs.filter((r) => r.skill === sel.name && r.status === "ok").length], ["AI calls per run", this.aiPerRun(sel)],
          ["steps", sel.steps.length], ["pages", sel.max_pages || 1]].map(([k, v]) => `<div class="stat" style="background:var(--panel);border:0"><b>${v}</b><span>${k}</span></div>`).join("")}</div></div>
          <div class="card small"><b>If the page changes</b><span>1. It finds the button again by its name. No AI.</span><span>2. If that fails, it asks the model once and only acts when sure.</span><span>3. Otherwise it stops and asks you.</span></div>
          <button class="btn p" id="runsk">Run now</button><button class="btn" data-dl="/api/bots/${b.id}/skills/${sel.id}/export" data-name="${esc(sel.name)}.inkyskill">Download file</button>
          ${S.settings.n8n_connected ? `<button class="btn" id="sendn8n">${logo("n8n", 20)}Send to n8n</button>` : ""}<button class="btn" data-dl="/api/bots/${b.id}/skills/${sel.id}/export?format=n8n" data-name="${esc(sel.name)}.n8n.json">${S.settings.n8n_connected ? "Download for n8n" : "Export to n8n"}</button><button class="btn hot" id="delsk">Delete skill</button></aside></div>` : `<p class="muted">No skills yet.</p>`;
    // a step is found again by what it does, in the skill as it is now: never by its place in what this page drew
    const stepEdit = (i, change) => this.edit(async (d) => {
      const was = sel.steps[i], now = (d.skills || []).find((s) => s.id === sel.id);
      const j = now ? now.steps.findIndex((s) => s.action === was.action && s.text === was.text) : -1;
      if (j < 0) { toast("That step changed meanwhile, so nothing was changed."); return this.refresh(true); }
      await patch(`/api/bots/${b.id}/skills/${sel.id}`, { steps: change(now.steps, j) });
      return this.refresh(true);
    });
    $$("[data-sk]", tb).forEach((x) => (x.onclick = () => { this.skillSel = +x.dataset.sk; keepFocus(tb, () => this.live_skills(tb)); }));
    $$("[data-ask]", tb).forEach((x) => (x.onclick = () => stepEdit(+x.dataset.ask, (st, j) => st.map((s, k) => (k === j ? { ...s, approved_always: false } : s)))));
    $$("[data-rm]", tb).forEach((x) => (x.onclick = async () => {
      const i = +x.dataset.rm;
      if (await confirmBox(`Remove step ${i + 1}, “${sel.steps[i].text}”? It won’t do it on its next runs.`, "Remove step", true)) stepEdit(i, (st, j) => st.filter((_, k) => k !== j));
    }));
    if ($("#runsk")) $("#runsk").onclick = () => post(`/api/bots/${b.id}/run`, { skill: sel.id }).then(() => this.go("computer")).catch((e) => this.oops(e));
    if ($("#sendn8n")) $("#sendn8n").onclick = async () => { $("#sendn8n").disabled = true; try { toast((await post(`/api/bots/${b.id}/skills/${sel.id}/send-n8n`)).text); } catch (e) { toast(e.message); } if ($("#sendn8n")) $("#sendn8n").disabled = false; };
    if ($("#delsk")) $("#delsk").onclick = async () => { if (await confirmBox(`Delete “${sel.name}”?`, "Delete", true)) { await del(`/api/bots/${b.id}/skills/${sel.id}`).catch((e) => toast(e.message)); this.refresh(true); } };
  },

  save(p) {  // change the bot, then show it as it is now
    return patch(`/api/bots/${this.id}`, p).then(() => { loadState().catch(() => {}); return this.refresh(true); });
  },
  tab_settings(tb) {  // drawn once per visit: live_settings keeps the rest current and never touches what you're typing
    const b = this.data.bot, s = b.schedule || {};
    tb.innerHTML = `<div class="gridfit" data-tab="settings">
      <div class="card"><b>Name and look</b><div class="row wrap"><label class="vh" for="bname">Name</label><input class="f" id="bname" value="${esc(b.name)}" maxlength="40" style="flex:1 1 160px"><a class="btn s" href="#/look/${b.id}">Change its look</a></div></div>
      <div class="card"><b>Schedule</b><span class="seg" id="every" role="group" aria-label="How often">${[[0, "When I ask"], [15, "Every 15 min"], [60, "Hourly"], [1440, "Daily"]].map(([v, t]) => `<button data-v="${v}">${t}</button>`).join("")}</span>
        <div class="between small"><label for="sum">Summary at</label><input class="f" type="time" id="sum" value="${esc(s.summary_at || "")}" style="width:130px;height:36px"></div>
        <div class="between small"><span>Quiet hours</span><span class="row" style="gap:6px"><input class="f" type="time" id="qf" aria-label="Quiet from" value="${esc(s.quiet_from || "")}" style="width:120px;height:36px"><span class="muted">to</span><input class="f" type="time" id="qt" aria-label="Quiet until" value="${esc(s.quiet_to || "")}" style="width:120px;height:36px"></span></div>
        <span class="small muted">Skills replay with no AI, so checking often costs nothing extra.</span></div>
      <div class="card"><b>What it may do</b><div id="rules" style="display:contents"></div>
        <label class="vh" for="rule">Add a rule</label><input class="f" id="rule" placeholder="Add a rule in your words, e.g. skip ground floor flats"><span class="small muted" id="rulenote" role="status"></span></div>
      <div class="card"><div class="head"><b>It remembers</b><span class="small muted" id="memn"></span></div><a class="btn s" href="#/bot/${b.id}/about" style="align-self:flex-start">About you</a></div>
      <div class="card" id="where"></div>
      <div class="card" style="grid-column:1/-1"><div class="head"><b>Automations · hand results to Claude Code, Codex or any connector</b><a class="small" href="#/connectors">Connectors</a></div>
        <div id="autos" style="display:contents"></div>
        <div class="autoform"><select class="f" id="aw" aria-label="When"><option value="new_results">When there are new results</option><option value="every_run">After every run</option></select><select class="f" id="as" aria-label="Connector"><option value="">Loading connectors…</option></select><select class="f" id="at" aria-label="Tool" disabled></select><input class="f" id="al" aria-label="Label" placeholder="Label"></div>
        <textarea class="f mono" id="aa" aria-label="Arguments as JSON" rows="2" placeholder='Arguments as JSON, e.g. {"description":"flats","prompt":"Add these to ~/flats.md: {{new_json}}"}'></textarea><div class="row wrap"><button class="btn s" id="addauto" disabled>Add automation</button><span class="small muted" id="autonote"></span></div></div>
      <div class="card" style="grid-column:1/-1"><div class="between"><span id="delwhat"></span><button class="btn hot" id="delbot">Delete bot…</button></div></div></div>`;
    const save = (p) => this.save(p).catch((e) => this.oops(e));
    const pick = (x) => $$("button", x.parentElement).forEach((y) => { y.classList.toggle("on", y === x); y.setAttribute("aria-pressed", y === x); });  // shows at once
    $("#bname").onchange = (e) => {
      const x = e.target, v = x.value.trim(), name = this.data.bot.name;
      if (!v || v === name) { x.value = x.defaultValue = name; return; }  // emptied: it keeps its name, and the field says so
      x.defaultValue = x.value; save({ name: v });
    };
    $("#bname").onkeydown = (e) => { if (e.key === "Enter" && !e.isComposing) { e.target.blur(); e.target.focus(); } };  // saves, and you stay in the field
    // only what you changed is sent: the engine keeps the rest of the schedule as it is now
    $$("#every button").forEach((x) => (x.onclick = () => { pick(x); save({ schedule: { every_minutes: +x.dataset.v } }); }));
    $("#sum").onchange = (e) => { e.target.defaultValue = e.target.value; save({ schedule: { summary_at: e.target.value || null } }); };
    $("#qf").onchange = $("#qt").onchange = () => { ["#qf", "#qt"].forEach((q) => ($(q).defaultValue = $(q).value)); save({ schedule: { quiet_from: $("#qf").value, quiet_to: $("#qt").value } }); };
    $("#rule").onkeydown = async (e) => {
      const x = e.target, text = x.value.trim(), note = $("#rulenote"), had = (this.data.bot.rules || []).length;
      if (e.key !== "Enter" || e.isComposing || !text || x.disabled) return;
      x.disabled = true; note.textContent = `Adding “${text}”… ${this.data.bot.name} is reading it.`;
      let r;
      try { r = await post(`/api/bots/${this.id}/chat`, { text: `New rule: ${text}` }); }
      catch (err) { x.disabled = false; note.textContent = err.message; x.focus(); return; }
      await this.refresh(true);
      x.disabled = false;
      const said = (r.done || []).map(String).find((d) => d.startsWith("rule:"));
      if (said || (this.data && (this.data.bot.rules || []).length > had)) { x.value = x.defaultValue = ""; note.textContent = said ? `Added “${said.slice(5).trim()}”.` : "Added."; }
      else note.textContent = "Didn’t add it as a rule — try “Ask first before …”, “Never …” or a limit like “price under 20”.";  // your words stay, to change
      if (x.isConnected) x.focus();
    };
    $("#delbot").onclick = () => goodbye(this.data.bot);
    const ready = () => { $("#addauto").disabled = !($("#as").value && $("#at").value); };
    get("/api/mcp").then(({ servers }) => {
      if (!tb.contains($("#as"))) return;
      const on = servers.filter((x) => x.enabled);
      $("#as").innerHTML = on.length ? `<option value="">Pick a connector</option>${on.map((x) => `<option value="${esc(x.name)}">${esc(x.label)}</option>`).join("")}` : `<option value="">No connectors yet</option>`;
      $("#as").disabled = !on.length;
      $("#autonote").innerHTML = on.length ? "" : `Connect one in <a href="#/connectors">Connectors</a> first.`;
      const fillTools = () => {
        const sv = on.find((x) => x.name === $("#as").value);
        $("#at").innerHTML = sv ? (sv.tools || []).map((t) => `<option>${esc(t)}</option>`).join("") : `<option value="">Pick a connector first</option>`;
        $("#at").disabled = !sv; ready();
      };
      $("#as").onchange = fillTools; $("#at").onchange = ready; fillTools();
    }).catch(() => { if (tb.contains($("#as"))) $("#as").innerHTML = `<option value="">Couldn’t load connectors</option>`; });
    $("#addauto").onclick = () => {
      let args = {};
      try { args = JSON.parse($("#aa").value || "{}"); } catch (e) { return toast("The arguments aren’t valid JSON. They look like {\"prompt\": \"…\"}."); }
      if (!$("#as").value || !$("#at").value) return;
      const a = { when: $("#aw").value, server: $("#as").value, tool: $("#at").value, args, label: $("#al").value.trim() || $("#at").value };
      ["#aw", "#as", "#at", "#al", "#aa"].forEach((q) => { const x = $(q); delete x.dataset.touched; if (x.tagName !== "SELECT") x.value = x.defaultValue = ""; });
      this.edit((d) => this.save({ automations: [...(d.bot.automations || []), a] }));
    };
    this.live_settings(tb);
  },
  live_settings(tb) {
    const b = this.data.bot, s = b.schedule || {}, rules = b.rules || [], autos = b.automations || [];
    const put = (sel, html) => { const el = $(sel, tb); if (!el || el._html === html) return false; el.innerHTML = el._html = html; return true; };  // true: redrawn, bind it again
    const seg = (on) => `class="${on ? "on" : ""}" aria-pressed="${!!on}"`;
    follow($("#bname"), b.name); follow($("#sum"), s.summary_at || ""); follow($("#qf"), s.quiet_from || ""); follow($("#qt"), s.quiet_to || "");
    $$("#every button", tb).forEach((x) => { const on = +x.dataset.v === (s.every_minutes || 0); x.classList.toggle("on", on); x.setAttribute("aria-pressed", on); });
    $("#memn").textContent = `${nWord((b.memory || []).length, "thing")} about you`;
    put("#delwhat", `<b>Delete ${esc(b.name)}</b><br><span class="small muted">Removes its skills, memory, results and computer${b.remote ? `, here and on ${esc(b.remote)}` : ""}. Can’t be undone.</span>`);
    if (put("#rules", rules.map((r, i) => `<div class="rule ${r.kind === "ask" ? "ask" : ""}"><span class="badge">${esc(RULE_KINDS[r.kind] || r.kind)}</span><span>${esc(ruleBody(r))}</span>${r.kind === "filter" || !BUILT_IN_RULES.has(r.text) ? `<button class="chip" data-rr="${i}" aria-label="Remove the rule “${esc(r.text)}”">remove</button>` : "<span></span>"}</div>`).join("")))
      $$("[data-rr]", tb).forEach((x) => (x.onclick = async () => {  // found again by what it says, in the bot as it is now
        const r = rules[+x.dataset.rr];
        await this.edit((d) => {
          const rs = d.bot.rules || [], i = rs.findIndex((y) => y.kind === r.kind && y.text === r.text);
          if (i < 0) return this.refresh(true);  // already gone
          return this.save({ rules: rs.filter((_, j) => j !== i), filters: (d.bot.filters || []).filter((f) => (f.text || "") !== r.text) });
        });
        if (document.activeElement === document.body && $("#rule")) $("#rule").focus();  // the last one went: back to adding
      }));
    if (put("#where", `<b>Where it works</b>${b.remote ? `<span class="small">It runs on <b>${esc(b.remote)}</b> now.</span><button class="btn s bringback" style="align-self:flex-start"${this.bringing ? " disabled" : ""}>Bring back to this computer</button>`
      : `<span class="seg" id="mode" role="group" aria-label="Where it works"><button data-m="own" ${seg(b.mode !== "screen")}>Its own computer</button><button data-m="screen" ${seg(b.mode === "screen")} ${S.settings.screen_allowed ? "" : "disabled"}>A window on your screen</button></span>
        ${S.settings.screen_allowed ? "" : `<span class="small muted">A window on your screen is off until you allow bots on your screen in <a href="#/settings">Settings</a>.</span>`}
        <span class="small muted">${b.mode === "screen" ? "It opens a visible window on your desktop with the coral frame. Move your mouse to pause it, Esc to stop, ⌥C to chat." : "A private browser, streamed here. Your screen stays yours."}</span>
        <a class="btn s" href="#/computers" style="align-self:flex-start">Move to another computer</a>`}`)) {
      $$("#mode button", tb).forEach((x) => (x.onclick = () => { $$("#mode button", tb).forEach((y) => { y.classList.toggle("on", y === x); y.setAttribute("aria-pressed", y === x); }); this.save({ mode: x.dataset.m }).catch((e) => toast(e.message)); }));
      $$(".bringback", tb).forEach((x) => (x.onclick = () => this.bringBack()));
    }
    const name = (a) => esc(a.label || a.tool);
    if (put("#autos", autos.map((a, i) => `<div class="rule"><b>${a.when === "every_run" ? "Every run" : "New results"}</b><span>${esc(a.label || "")} → <span class="mono">${esc(a.server)}.${esc(a.tool)}</span>${a.approved_always ? ` <span class="badge">always allowed</span> <button class="chip" data-aa="${i}" aria-label="Ask again before “${name(a)}”">ask again</button>` : ""}</span><button class="chip" data-au="${i}" aria-label="Remove the automation “${name(a)}”">remove</button></div>`).join("")
      || `<span class="small muted">None yet. Or just ask it in the chat, e.g. “when you find new flats, ask Claude Code to add them to flats.md”.</span>`)) {
      const change = (i, fn) => this.edit((d) => {  // found again by label and tool, in the bot as it is now
        const list = d.bot.automations || [], a = autos[i], j = list.findIndex((y) => y.label === a.label && y.server === a.server && y.tool === a.tool);
        return j < 0 ? this.refresh(true) : this.save({ automations: fn(list, j) });
      });
      $$("[data-au]", tb).forEach((x) => (x.onclick = () => change(+x.dataset.au, (l, j) => l.filter((_, k) => k !== j))));
      $$("[data-aa]", tb).forEach((x) => (x.onclick = () => change(+x.dataset.aa, (l, j) => l.map((a, k) => (k === j ? { ...a, approved_always: false } : a)))));
    }
  },

  tab_activity(tb) {
    const b = this.data.bot, evs = [], you = (e) => ["control", "handback"].includes(e.kind);
    const said = (e) => one(e.kind === "control" ? CONTROL_WORDS[e.text] || e.text : e.text);
    for (const e of this.data.events) {  // the same line many times in a row reads as one, with ×N
      const l = evs.at(-1);
      if (l && l.kind === e.kind && l.text === e.text) l.times = (l.times || 1) + 1;
      else if (l && l.kind !== e.kind && you(l) && you(e) && said(l) === said(e) && Math.abs(l.ts - e.ts) < 5) continue;  // one hand back, logged twice
      else evs.push({ ...e });
    }
    tb.innerHTML = `<div class="card" style="padding:6px 18px"><div class="list">${evs.map((e) => `<div class="ev"><span class="mono small muted">${ago(e.ts)}</span>${botCritter(b, 22)}<span>${esc(said(e))}${e.times ? ` <span class="badge">×${e.times}</span>` : ""}</span><span class="badge">${esc(EVENT_WORDS[e.kind] || String(e.kind).replace(/_/g, " "))}</span></div>`).join("") || `<p class="muted">Nothing yet.</p>`}</div></div>
      <div class="card"><b>Runs</b>${this.data.runs.length ? `<div class="tscroll"><table class="t"><thead><tr><th>When</th><th>What</th><th>How it went</th><th>Results</th><th>New</th><th>AI calls</th><th>Seconds</th></tr></thead><tbody>${this.data.runs.map((r) => `<tr><td>${ago(r.ts)}</td><td>${esc(RUN_KINDS[r.kind] || r.kind)}</td><td>${esc(RUN_WORDS[r.status] || r.status)}</td><td>${r.items ?? ""}</td><td>${r.new ?? ""}</td><td>${r.ai_calls ?? ""}</td><td>${r.seconds ?? ""}</td></tr>`).join("")}</tbody></table></div>`
        : `<span class="small muted">No runs yet. Press Run now, and each run shows up here.</span>`}</div>`;
  },

  tab_diary(tb) {
    const g = this.data.growth, b = this.data.bot, next = g.next;
    const pct = next ? Math.min(100, Math.round((g.runs / next.at) * 100)) : 100;
    const tile = (v, k) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`;
    tb.innerHTML = `<div class="grid4">${tile(g.days, g.days === 1 ? "day on the job" : "days on the job")}${tile(g.streak, "day streak")}${tile(g.hours_saved + " h", "of your time saved")}${tile(g.ai_saved, g.ai_saved === 1 ? "AI call saved" : "AI calls saved")}</div>
      <div class="card"><div class="between"><b>Level ${g.level}</b><span class="small muted">${nWord(g.runs, "good run")}</span></div>
        <div style="height:10px;border-radius:5px;background:var(--panel);overflow:hidden"><div style="height:100%;width:${pct}%;background:var(--coral);border-radius:5px"></div></div>
        <span class="small muted">${next ? `${nWord(next.at - g.runs, "more run")} to unlock the ${esc(next.acc)} ${critter(b.look.kind, b.look.color, next.acc, 22)}` : "Everything unlocked. A true veteran."}</span>
        ${g.unlocked.length ? `<span class="row wrap small">Unlocked: ${g.unlocked.map((a) => `<span class="chip">${critter(b.look.kind, b.look.color, a, 20)} ${esc(a)}</span>`).join("")} <a href="#/look/${b.id}">wear one</a></span>` : ""}</div>
      <div class="col"><b>Diary</b>${(this.data.diary || []).map((d) => `<div class="card"><span class="mono small muted">${esc(d.date)}</span><span>${esc(d.text)}</span></div>`).join("") || `<span class="small muted">${esc(b.name)} writes a short entry each evening, on days something happened.</span>`}</div>`;
  },

  tab_about(tb) {
    const b = this.data.bot, mem = b.memory || [];
    // each change is made to its memory as it is now, found by what it says: never by its place in this list
    const change = (text, fn) => this.edit((d) => {
      const list = d.bot.memory || [], i = list.findIndex((m) => m.text === text);
      return text !== null && i < 0 ? this.refresh(true) : this.save({ memory: fn(list, i) });
    });
    tb.innerHTML = `<div class="card"><div class="head"><b>Things ${esc(b.name)} knows about you</b><span class="small muted">${b.remote ? `only on ${esc(b.remote)}, where it lives` : "only on this computer"}</span></div>
      ${mem.map((m, i) => `<div class="row"><input class="f grow" id="mi${i}" data-mi="${i}" value="${esc(m.text)}" aria-label="Memory ${i + 1}"><button class="btn s" id="fg${i}" data-fg="${i}" aria-label="Forget “${esc(m.text)}”">Forget</button></div>`).join("") || `<span class="small muted">Nothing yet. Tell it things in the chat, like “I prefer Libertà”.</span>`}
      <label class="vh" for="mem">Tell it something to remember</label><input class="f" id="mem" placeholder="Tell it something to remember, then press Enter"></div>`;
    $$("[data-mi]", tb).forEach((x) => (x.onchange = () => {
      const was = mem[+x.dataset.mi].text, t = x.value.trim();
      x.defaultValue = x.value;
      change(was, (list, i) => (t ? list.map((m, j) => (j === i ? { ...m, text: t } : m)) : list.filter((_, j) => j !== i)));
    }));
    $$("[data-fg]", tb).forEach((x) => (x.onclick = async () => {
      const i = +x.dataset.fg;
      await change(mem[i].text, (list, j) => list.filter((_, k) => k !== j));
      const next = $("#fg" + i) || $("#mem");  // the next Forget, else back to adding
      if (next) next.focus();
    }));
    $("#mem").onkeydown = (e) => {  // the box keeps focus, so you can add the next one
      const t = e.target.value.trim();
      if (e.key === "Enter" && !e.isComposing && t) { e.target.value = ""; change(null, (list) => [...list, { text: t, ts: Date.now() / 1000 }]); }
    };
  },

  // ---- Call: speak with the bot (browser speech), it keeps working
  tab_call(tb, first) {
    const b = this.data.bot;
    if (!first && $("#callbox")) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const canMic = !!(SR && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    tb.innerHTML = `<div class="row callrow"><section class="call" id="callbox" aria-label="Call with ${esc(b.name)}">
      <div class="between" style="align-self:stretch"><span class="small" style="color:#C9C5BD">Call with ${esc(b.name)}</span><span class="mono small" id="ctime">0:00</span></div>
      <div class="rings" id="rings"><span style="width:65%;height:65%"></span><span style="width:85%;height:85%"></span><span style="width:100%;height:100%"></span>${botCritter({ ...b, schedule: null }, 130)}</div>
      <b style="font-size:26px">${esc(b.name)}</b><span class="small" style="color:#F2957C;text-align:center" id="cstate" role="status">${canMic ? "Allow the microphone to talk…" : "Speech isn’t available in this browser. Type instead."}</span>
      <div id="trans" style="align-self:stretch;padding:14px 16px;border-radius:16px;background:rgba(255,255,255,.06);display:flex;flex-direction:column;gap:8px;min-height:120px;max-height:260px;overflow:auto;font-size:14px"></div>
      <div class="row" style="align-self:stretch"><label class="vh" for="ctype">Type instead</label><input class="f" id="ctype" placeholder="Type instead…" style="background:rgba(255,255,255,.08);border-color:transparent;color:#fff"></div>
      <div class="row callctl" style="gap:22px;margin-top:auto"><span class="col"><button class="callbtn" id="mute" aria-label="Mute" aria-pressed="false" aria-describedby="mutecap" disabled>${icon("mic", 22)}</button><span class="callcap" id="mutecap">${canMic ? "Mic off" : "No mic"}</span></span>
        <span class="col"><button class="callbtn" id="spk" aria-label="Speaker" aria-pressed="true" aria-describedby="spkcap">${icon("speaker", 22)}</button><span class="callcap" id="spkcap">Speaker on</span></span>
        <span class="col"><a class="callbtn end" href="#/bot/${b.id}/computer" aria-label="End call">${icon("phone", 22)}</a><span class="callcap" aria-hidden="true">End</span></span></div></section>
      <aside class="col callside"><div class="card"><b id="cside"></b><div class="thumb" id="cthumb" style="height:160px"><img id="callimg" alt=""><span id="callidle">${botCritter({ ...b, schedule: null }, 72)}</span></div><span class="small muted" id="cstep"></span></div>
      <div class="card small"><b>Voice</b><span>${b.look.voice === "off" ? "Replies are text only (Make it yours → Voice)." : `Replies are spoken (${esc(b.look.voice || "soft")}). Changes it hears still show up as actions you can see in the chat.`}</span></div></aside></div>`;
    const t0 = Date.now();
    const side = () => {  // its screen only while it works: asking an idle bot for one starts its browser for nothing
      const lb = (this.data && this.data.bot) || b, live = !idleBot(lb), img = $("#callimg");
      if (!img) return;
      $("#cthumb").classList.toggle("idle", !live); img.classList.toggle("hidden", !live); $("#callidle").classList.toggle("hidden", live);
      if (live) img.src = screenUrl(b.id); else img.removeAttribute("src");
      $("#cside").textContent = lb.step ? "It keeps working" : "Its computer";
      $("#cstep").textContent = lb.step || "not running right now";
    };
    side();
    const tick = setInterval(() => { const s = Math.floor((Date.now() - t0) / 1000); if ($("#ctime")) $("#ctime").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; side(); }, 1000);
    const line = (who, text) => { const d = document.createElement("div"); d.innerHTML = `<b style="color:${who === "you" ? "#A8A49C" : "#F2957C"}">${who === "you" ? "You" : esc(b.name)}</b> ${esc(text)}`; $("#trans").appendChild(d); $("#trans").scrollTop = 1e9; };
    let speaking = true, muted = false, rec = null, talking = false, micOk = false, asking = canMic;
    const state = (t) => { if ($("#cstate")) $("#cstate").textContent = t; };
    const calm = () => state(asking ? "Allow the microphone to talk…" : !micOk ? "Type to talk." : muted ? "Muted." : "Listening…");
    const hear = () => { if (rec && micOk && !muted && !talking && $("#callbox")) try { rec.start(); } catch (e) {} };
    const noMic = (why) => {  // every way the microphone can fail ends here: say why, and typing works
      asking = false; micOk = false;
      if (rec) try { rec.abort(); } catch (e) {}
      rec = null;
      if (!$("#callbox")) return;
      $("#mute").disabled = true; $("#mutecap").textContent = "No mic";
      state(`${why}. Type instead.`);
      $("#ctype").focus({ preventScroll: true });
    };
    const hushed = () => { if (!talking) return; talking = false; if ($("#rings")) $("#rings").classList.remove("talk"); calm(); hear(); };  // it stopped speaking, or you turned the speaker off
    const say = (text) => {
      if (!speaking || b.look.voice === "off" || !window.speechSynthesis) return false;
      const u = new SpeechSynthesisUtterance(text);
      u.pitch = b.look.voice === "bright" ? 1.25 : 0.95; u.rate = 1.02;
      talking = true; if (rec) try { rec.abort(); } catch (e) {}  // don't hear its own voice through your speakers
      $("#rings").classList.add("talk");
      u.onend = u.onerror = hushed;
      setTimeout(hushed, 3000 + text.length * 90);  // some browsers never say it's done
      speechSynthesis.speak(u);
      return true;
    };
    const ask = async (text) => {
      line("you", text);
      state("Thinking…");
      try { const r = await post(`/api/bots/${b.id}/chat`, { text, source: "call" }); line("bot", r.reply); if (say(r.reply)) state("Speaking…"); else calm(); }
      catch (e) { line("bot", e.message); calm(); }
    };
    $("#ctype").onkeydown = (e) => { if (e.key === "Enter" && !e.isComposing && e.target.value.trim()) { ask(e.target.value.trim()); e.target.value = ""; } };
    $("#spk").onclick = (e) => {
      speaking = !speaking;
      const x = e.currentTarget;
      x.setAttribute("aria-pressed", speaking); x.innerHTML = icon(speaking ? "speaker" : "speakeroff", 22); $("#spkcap").textContent = speaking ? "Speaker on" : "Speaker off";
      if (!speaking) { if (window.speechSynthesis) speechSynthesis.cancel(); hushed(); }
    };
    $("#mute").onclick = (e) => {
      if (!micOk) return;
      muted = !muted;
      const x = e.currentTarget;
      x.setAttribute("aria-pressed", muted); x.innerHTML = icon(muted ? "micoff" : "mic", 22); $("#mutecap").textContent = muted ? "Muted" : "Mic on";
      if (muted) { if (rec) try { rec.stop(); } catch (err) {} } else hear();
      calm();
    };
    const MIC = { NotAllowedError: "The microphone is blocked for this page", NotFoundError: "No microphone found", NotReadableError: "Another app is using the microphone",
      SecurityError: "This page isn’t allowed to use the microphone", NotSupportedError: "This browser can’t use a microphone here", AbortError: "The microphone stopped", OverconstrainedError: "No microphone found" };
    let settled = !canMic;
    const timer = canMic && setTimeout(() => { if (!settled) { settled = true; noMic("The microphone didn’t answer"); } }, 8000);
    if (canMic) navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      stream.getTracks().forEach((t) => t.stop());  // only asking: speech recognition opens its own
      if (settled || !$("#callbox")) return;
      settled = true; clearTimeout(timer); asking = false; micOk = true;
      rec = new SR(); rec.continuous = true; rec.interimResults = false; rec.lang = navigator.language || "en-US";
      rec.onresult = (e) => { const r = e.results[e.results.length - 1], t = r[0].transcript.trim(); if (r.isFinal && !talking && t) ask(t); };
      rec.onend = hear;
      rec.onstart = () => { if (!talking) calm(); };
      rec.onerror = (e) => {
        const why = { "not-allowed": "The microphone is blocked for this page", "service-not-allowed": "Speech recognition is turned off in this browser", "audio-capture": "No microphone found",
          network: "Speech recognition can’t reach its service", "language-not-supported": "Speech recognition doesn’t know this language" }[e.error];
        if (why) noMic(why);  // "no-speech" and "aborted" just start listening again
      };
      $("#mute").disabled = false; $("#mutecap").textContent = "Mic on";
      calm(); hear();
    }).catch((e) => { if (settled) return; settled = true; clearTimeout(timer); noMic(MIC[e && e.name] || "The microphone didn’t start"); });
    line("bot", `Hi, it’s ${b.name}. ${b.step ? `I’m on step ${b.step_n}: ${b.step}.` : "What can I do?"}`);
    this.callEnd = () => { clearInterval(tick); clearTimeout(timer); settled = true; muted = true; if (rec) try { rec.abort(); } catch (e) {} if (window.speechSynthesis) speechSynthesis.cancel(); };
  },
};

// ================================================================ rituals: hatch, goodbye, first-run tour
function hatch(b, intro) {
  const o = document.createElement("div"), l = b.look || {};
  o.className = "ritual"; o.tabIndex = -1; o.setAttribute("role", "dialog"); o.setAttribute("aria-label", `${b.name} hatched`);
  o.innerHTML = `<div class="splash">${[0, 1, 2, 3, 4, 5].map((i) => `<i style="--a:${i * 60}deg;--d:${i * 40}ms"></i>`).join("")}</div>
    <div class="hatchling">${critter(l.kind, l.color, l.acc, 150, "happy")}</div>
    <div class="card bubble">${esc(intro || `Hi! I'm ${b.name}.`)}</div><span class="small muted">${TOUCH ? "Tap to start" : "Click or press Enter to start"}</span>`;  // a newborn is happy, even at night
  document.body.appendChild(o);
  o.focus();
  SOUND.play("rise", b);
  setTimeout(() => confetti(), 700);
  const key = (e) => { if (!CMD.open && ["Escape", "Enter", " "].includes(e.key) && !e.isComposing) { e.preventDefault(); e.stopPropagation(); close(); } };
  const close = () => {
    if (o.classList.contains("out")) return;
    clearTimeout(timer); removeEventListener("keydown", key, true);
    o.classList.add("out"); setTimeout(() => o.remove(), 300);
    if (!CMD.open) { const v = $("#view"); if (v) { v.tabIndex = -1; v.focus({ preventScroll: true }); } }
  };
  addEventListener("keydown", key, true);
  o.onclick = close;
  const timer = setTimeout(close, 4200);
}

function goodbye(b) {  // b.remote: it lives on another computer, and is deleted there too (or, if that one isn't answering, only here)
  const packed = { octopus: "tentacles", cat: "whiskers", blob: "goo" }[(b.look || {}).kind] || "tentacles", far = b.remote;
  modal(`<div class="col" style="align-items:center;text-align:center;gap:10px"><div id="byecrit">${botCritter({ ...b, status: "needs_you", needs: 1, need_kind: "decision" }, 110)}</div>
    <h2 style="overflow-wrap:anywhere">${esc(b.name)} packed its ${packed}.</h2><span class="small muted">Delete for good? Its skills, memory and results go too${far ? `, here and on ${esc(far)}` : ""}. This can’t be undone.</span>
    <span class="small bad hidden" id="byeerr" role="alert" style="background:none"></span>
    <div class="row wrap" style="justify-content:center"><button class="btn" id="byeno">Keep ${esc(b.name)}</button><button class="btn hot" id="byeyes">Delete</button><button class="btn hot hidden" id="byehere">Remove only here</button></div></div>`, () => {
    $("#byeno").onclick = closeModal;
    const go = async (here) => {
      const btn = $(here ? "#byehere" : "#byeyes");
      busyBtn(btn, true, here ? "Removing…" : "Deleting…");
      try { await del(`/api/bots/${b.id}${here ? "?here=1" : ""}`); }
      catch (e) {  // e.g. its computer isn't answering: say so, and offer to remove it only here
        if (!btn.isConnected) return toast(e.message, b);
        busyBtn(btn, false);
        $("#byeerr").textContent = e.message; $("#byeerr").classList.remove("hidden");
        if (far) { $("#byehere").classList.remove("hidden"); $("#byehere").focus(); }
        return;
      }
      if ($("#byecrit")) { $("#byecrit").classList.add("bye"); await new Promise((r) => setTimeout(r, calmMotion() ? 0 : 650)); }
      closeModal(); await loadState().catch(() => {}); location.hash = "#/bots";
      toast(`Goodbye from ${b.name}`);
    };
    $("#byeyes").onclick = () => go(false);
    $("#byehere").onclick = () => go(true);
  });
}

const TOUR = [
  ["#nav .navbot", "This is your bot. Its critter shows how it’s doing: busy, asleep at night, or waving when it needs you."],
  ["#cards", "Each bot has its own computer. When one is working you can watch it live, take over and hand back."],
  ["#nav .needlink", "When a bot needs a yes, it waits here. Nothing that can’t be undone happens without you."],
  [null, () => `${TOUCH ? "Tap the search button" : `Press ${MAC ? "⌘K" : "Ctrl+K"}${APP ? ` (or ${MAC ? "⌥Space" : "Alt+Space"} from any app)` : ""}`} to talk to any bot. That’s it, have fun!`],
];
const tourBox = (sel) => { const t = sel && $(sel), r = t && t.getBoundingClientRect(); return r && r.width && r.height && r.bottom > 0 && r.top < innerHeight ? r : null; };
function tourKey(e) {
  if (CMD.open) return;
  if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); tour(TOUR.length); }
  else if (e.key === "Tab" && $(".coach .tip")) trapTab($(".coach .tip"), e);
}
function tour(i = 0) {
  $$(".coach").forEach((x) => x.remove());
  removeEventListener("keydown", tourKey, true);
  if (i === 0 && !S.bots.length) { try { sessionStorage.setItem("inkyTourNext", "1"); } catch (e) {} return; }  // it starts once your first bot exists
  if (i >= TOUR.length) { try { localStorage.setItem("inkyTour", "1"); } catch (e) {} return; }
  const [sel, said] = TOUR[i], text = typeof said === "function" ? said() : said;
  const tgt = sel && $(sel);
  if (tgt && tgt.offsetParent) tgt.scrollIntoView({ block: "center" });  // point at it where you can see it
  const r = tourBox(sel);
  if (sel && !r) return tour(i + 1);  // nothing to point at here (the sidebar is hidden on a phone)
  const shown = TOUR.filter(([s]) => !s || tourBox(s)), n = shown.indexOf(TOUR[i]) + 1;
  const w = Math.min(320, innerWidth - 32);
  let pos = "left:50%;top:40%;transform:translate(-50%,-50%)", ring = "";
  if (r) {
    const top = Math.max(4, r.top - 6), bottom = Math.min(innerHeight - 4, r.bottom + 6), left = Math.max(4, r.left - 6), right = Math.min(innerWidth - 4, r.right + 6);
    ring = `<div class="ring" style="left:${left}px;top:${top}px;width:${right - left}px;height:${bottom - top}px"></div>`;
    let x = r.right + 16, y = Math.max(16, Math.min(innerHeight - 200, r.top));
    if (x + w > innerWidth - 16) { x = Math.max(16, Math.min(innerWidth - w - 16, r.left)); y = Math.max(16, Math.min(innerHeight - 200, bottom + 12)); }  // no room beside it: below
    pos = `left:${x}px;top:${y}px`;
  }
  const c = document.createElement("div");
  c.className = "coach";
  c.innerHTML = `${ring}<div class="card tip" role="dialog" aria-label="Tour, step ${n} of ${shown.length}" style="width:${w}px;${pos}">
      <span class="row">${critter("octopus", "#E86F51", "none", 36, "happy")}<span class="mono small muted">${n} of ${shown.length}</span></span><span>${esc(text)}</span>
      <div class="row" style="justify-content:flex-end"><button class="btn s" id="tskip">Skip</button><button class="btn s p" id="tnext">${i === TOUR.length - 1 ? "Done" : "Next"}</button></div></div>`;
  document.body.appendChild(c);
  addEventListener("keydown", tourKey, true);
  $("#tnext").onclick = () => tour(i + 1);
  $("#tskip").onclick = () => tour(TOUR.length);
  $("#tnext").focus();
}

const CHOSEN = {};  // "bot:need" → your answer: its buttons stop working at once, and the card says what you chose
async function answerNeed(bid, id, decision) {  // always through the bot, so a moved bot's question is answered on its own computer
  const k = `${bid}:${id}`, btns = $$(`[data-need="${id}"][data-bot="${bid}"]`);
  if (CHOSEN[k]) return false;  // a second click doesn't answer again
  CHOSEN[k] = decision;
  btns.forEach((x) => { x.disabled = true; x.classList.toggle("chosen", x.dataset.o === decision); });
  try { await post(`/api/bots/${bid}/needs/${id}`, { decision }); toast(`You chose “${decision}”`, S.bots.find((b) => b.id === bid)); }
  catch (e) { delete CHOSEN[k]; btns.forEach((x) => { x.disabled = false; x.classList.remove("chosen"); }); toast(e.message); refreshSoon(50); return false; }
  if (decision === "Open its computer" || decision === "Show me once") {
    if (S.view === VIEWS.bot && VIEWS.bot.id === bid && VIEWS.bot.data) VIEWS.bot.go("computer");  // already on its page: the chat stays as it is
    else location.hash = `#/bot/${bid}/computer`;
  }
  else if (decision === "Open Models") location.hash = "#/models";
  refreshSoon(50);
  return true;
}

// ================================================================ team
VIEWS.team = {  // bots talking to each other, morning papers, milestones
  async show(el) { this.el = el; await this.refresh(); },
  async refresh() {
    const { feed } = await get("/api/team?limit=120");
    const by = (id) => S.bots.find((b) => b.id === id);
    const nameOf = (id, was) => (by(id) || {}).name || was || "a bot";  // its name now, even if it was renamed since
    const line = (f) => {
      const speaker = (f.kind === "peer" ? by(f.sender_id) : by(f.bot)) || { look: f.look || {}, status: "idle", schedule: {} };
      const who = f.kind === "peer" ? `${esc(nameOf(f.sender_id, f.sender))} → ${esc(nameOf(f.bot, f.name))}` : f.kind === "paper" ? `${esc(nameOf(f.bot, f.name))} · morning paper` : esc(nameOf(f.bot, f.name));
      const re = f.reply_to ? `<span class="small muted">replying to “${esc(f.reply_to)}”</span>` : "";
      return `<div class="m">${botCritter(speaker, 30)}<div class="body"><span class="small" style="font-weight:600">${who} <span class="muted" style="font-weight:400;white-space:nowrap" title="${esc(new Date(f.ts * 1000).toLocaleString())}">${ago(f.ts)}</span></span>${re}<span>${esc(f.text)}</span></div></div>`;
    };
    this.el.innerHTML = `${mobileBar("Team")}<div class="page"><div><h1>Team</h1><p class="lede">Your bots talk to each other here: hand-offs, morning papers and milestones. Anything that can’t be undone still waits for you.</p></div>
      <div class="card"><div class="msgs" style="display:flex;flex-direction:column-reverse;gap:12px">${feed.map(line).join("") || `<span class="small muted">Quiet so far. ${S.bots.length > 1 ? `Tell ${esc(S.bots[0].name)} “ask ${esc(S.bots[1].name)} to …”` : "Make two bots and tell one to ask the other"}, and they’ll talk here.</span>`}</div></div></div>`;
  },
};

// ================================================================ needs you
const NEED_KIND = { decision: "wants your yes", error: "stopped", robot: "robot check", sign_in: "needs you to sign in", blocked: "blocked",
  denied: "not allowed", fix_failed: "couldn’t fix a step", learn_failed: "couldn’t learn the site", no_model: "needs a model" };
const needKind = (k) => NEED_KIND[k] || String(k || "").replace(/_/g, " ");
const GONE = new Set();  // "bot:need" answered somewhere else (a 409): its card goes now, not when a moved bot's server is next asked
VIEWS.needs = {
  async show(el, _, qs) {
    const t = qs.get("tab");
    this.el = el; this.tab = ["decisions", "problems"].includes(t) ? t : null; this.health = null; await this.refresh();
    if (this.tabFocus) { this.tabFocus = false; const t = $(".seg .on", el); if (t) t.focus(); }  // switching tabs keeps your place
  },
  async refresh() {
    const key = (n) => `${n.bot_id}:${n.id}`;
    const needs = (await get("/api/needs")).needs.filter((n) => !GONE.has(key(n)));
    const dec = needs.filter((n) => n.kind === "decision"), prob = needs.filter((n) => n.kind !== "decision");
    if (!this.tab) this.tab = !dec.length && prob.length ? "problems" : "decisions";  // once per visit: it doesn't switch under you
    const list = this.tab === "decisions" ? dec : prob;
    const botOf = (n) => S.bots.find((b) => b.id === n.bot_id) || { look: {}, name: n.bot };
    if (this.tab === "problems" && !this.health) this.health = (await get("/api/health")).health;  // once per visit, or on Check again
    const health = this.health || [];
    const empty = !S.bots.length ? `<p class="muted">Nothing here yet: you have no bots. <a href="#/bots">Make your first one</a>, and when it needs a yes or gets stuck, it waits here.</p>`
      : `<p class="muted">${this.tab === "decisions" ? "Nothing to decide. Your bots are fine." : "No problems. Your bots are fine."}</p>`;
    const tab = (t, label, n) => `<a href="#/needs?tab=${t}" data-tab="${t}" class="${this.tab === t ? "on" : ""}"${this.tab === t ? ' aria-current="page"' : ""}>${label} · ${n}</a>`;
    const card = (n, i) => {
      const b = botOf(n), picked = CHOSEN[key(n)], opts = (n.options || []).length ? n.options : ["Dismiss"];
      return `<div class="card need ${i === 0 && this.tab === "decisions" && !picked ? "hot" : ""}">
        <div class="between"><span class="row small" style="font-weight:600;min-width:0">${botCritter(b, 22)}<span class="nwho">${esc(b.name)}${n.remote ? `<span class="muted" style="font-weight:400"> on ${esc(n.remote)}</span>` : ""} · ${esc(needKind(n.kind))}</span></span><span class="mono small muted">${ago(n.ts)}</span></div>
        <b style="font-size:16.5px">${esc(n.title)}</b>${n.body ? `<span class="small muted" style="line-height:1.5">${esc(n.body)}</span>` : ""}
        <div class="opts">${opts.map((o, j) => `<button class="btn ${j === 0 && !picked ? "p" : ""}${picked === o ? " chosen" : ""}" data-need="${n.id}" data-bot="${n.bot_id}" data-o="${esc(o)}"${picked ? " disabled" : ""}>${esc(o)}</button>`).join("")}<a class="btn" href="#/bot/${n.bot_id}/computer">Watch it</a></div>
        ${picked ? `<span class="small muted" role="status">You chose “${esc(picked)}”.</span>` : ""}</div>`;
    };
    redraw(this.el, () => (this.el.innerHTML = `${mobileBar("Needs you")}<div class="page"><div><h1>Needs you</h1><p class="lede">Your bots decide small things on their own. They stop here before anything that can’t be undone, and when something breaks.</p></div>
      <span class="seg" style="align-self:flex-start">${tab("decisions", "Decisions", dec.length)}${tab("problems", "Problems", prob.length)}</span>
      <div class="row needrow"><section class="col grow" style="gap:12px">${list.map(card).join("") || empty}</section>
      <aside class="col needside">${this.tab === "decisions" ? `<div class="card panel"><b>Rules for every bot</b><div class="rule"><b>On its own</b><span>Read, search, take notes</span></div><div class="rule ask"><b>Ask you first</b><span>Send, post, reply, delete, submit forms, sign up, hand work to connectors</span></div><div class="rule"><b>Never</b><span>Buy or pay</span></div><div class="rule"><b>Passwords</b><span>You type them</span></div><span class="small muted">Change a bot’s rules by telling it, or in its Settings.</span></div>`
        : `<div class="card panel small"><b>How bots handle problems</b><span>1. Cheap fixes first: wait, find the button by its name.</span><span>2. Ask the model once, and only act when it’s sure.</span><span>3. Otherwise stop, tell you here and on your phone.</span><span>4. Keep the parts that still work running.</span></div>
        <div class="card"><div class="between"><b>Health</b><button class="btn s" id="hagain">Check again</button></div>${health.map((h) => `<div class="between small" style="align-items:flex-start;gap:12px"><span style="flex-shrink:0">${esc(h.name)}</span><span style="display:flex;gap:5px;text-align:right;color:${h.ok ? "var(--green-t)" : h.info ? "var(--muted)" : "var(--coral-t)"}"><i aria-hidden="true" style="font-style:normal;flex-shrink:0">●</i><span>${esc(h.detail)}</span></span></div>`).join("")}</div>`}</aside></div></div>`));
    $$("[data-tab]", this.el).forEach((a) => (a.onclick = () => (this.tabFocus = true)));
    if ($("#hagain", this.el)) $("#hagain", this.el).onclick = async () => {
      busyBtn($("#hagain", this.el), true, "Checking…"); this.health = null;
      try { await this.refresh(); } catch (e) { toast(e.message); busyBtn($("#hagain", this.el), false); }
      if ($("#hagain", this.el)) $("#hagain", this.el).focus();
    };
    $$("[data-need]", this.el).forEach((x) => (x.onclick = async () => {
      const bid = +x.dataset.bot, nid = +x.dataset.need, k = `${bid}:${nid}`, btns = $$("button", x.closest(".need")), b = botOf(needs.find((y) => y.id === nid && y.bot_id === bid) || { bot_id: bid });
      btns.forEach((y) => (y.disabled = true));  // one answer per question, even on a double click
      if (await answerNeed(bid, nid, x.dataset.o)) {
        const who = b.name || "the bot", as = S.bots.find((y) => y.id === bid);
        if (x.dataset.o === "Always for this step") toast(`It won’t ask for that step again. To take it back, open ${who} → Skills and press “ask again”.`, as);
        if (x.dataset.o === "Always for this automation") toast(`It won’t ask for that hand-off again. To take it back, open ${who} → Settings and remove the automation.`, as);
        await this.refresh();
        const tab = $(".seg .on", this.el);  // its buttons are off now: back to the tab, never onto another question's Yes
        if (tab && (!document.activeElement || document.activeElement === document.body)) tab.focus();
        return;
      }
      if (CHOSEN[k]) return;  // already answered from this window
      let open = true;  // didn't go through: is the question still open where the bot is? (answered elsewhere = a 409)
      try { open = (await get(`/api/bots/${bid}`)).needs.some((n) => n.id === nid); } catch (e) {}
      if (open) return btns.forEach((y) => (y.disabled = false));
      GONE.add(k); this.refresh();
    }));
  },
};

// ================================================================ activity
const EV_KIND = { learned: ["learned", "good"], fixed: ["fixed a step", "good"], problem: ["problem", "hot"], denied: ["not allowed", "hot"], replay: ["ran"], created: ["new bot"],
  control: ["you"], delegate: ["handed off"], answered: ["you answered"], team: ["team"], shown: ["shown by you"], handback: ["handed back"], level: ["milestone", "good"],
  moved: ["moved"], arrived: ["arrived"], learn: ["learning"], repair: ["trying a fix"] };
VIEWS.activity = {
  async show(el) { this.el = el; await this.refresh(); },
  async refresh() {
    const a = await get("/api/activity");
    const w = a.week, botOf = (id) => S.bots.find((b) => b.id === id), away = S.bots.filter((b) => b.remote || b.status === "moved").length;
    const row = (e) => {
      const b = botOf(e.bot_id), [label, tone = ""] = EV_KIND[e.kind] || [String(e.kind || "").replace(/_/g, " ")];
      const inner = `<span class="mono small muted">${ago(e.ts)}</span>${botCritter(b || { look: {}, name: "Inky" }, 24)}<span><b style="font-weight:500">${esc((b && b.name) || e.bot || "")}</b> · ${esc(e.text)}</span><span class="badge ${tone}">${esc(label)}</span>`;
      return b ? `<a class="ev" href="#/bot/${b.id}/activity">${inner}</a>` : `<div class="ev">${inner}</div>`;
    };
    this.el.innerHTML = `${mobileBar("Activity")}<div class="page" style="background:var(--panel);min-height:100%;max-width:none"><div><h1>Activity</h1><p class="lede">Everything your bots did this week, and what it cost. Learning uses the AI; repeating doesn’t.</p></div>
      <div class="grid5 stats5"><div class="stat"><span>Runs</span><b>${w.runs}</b></div><div class="stat"><span>AI calls</span><b>${w.ai_calls}</b></div><div class="stat"><span>If it asked the AI every step</span><b>≈ ${w.if_ai_every_step}</b></div>
      <div class="stat"><span>Spent on AI</span><b>$${w.cost.toFixed(2)}</b></div><div class="stat"><span>Asked you</span><b>${w.asked}</b></div></div>
      ${away ? `<p class="small muted" style="margin:0">${away === 1 ? "1 of your bots runs on another computer; its runs show on that computer." : `${away} of your bots run on other computers; their runs show on those computers.`}</p>` : ""}
      <div class="card" style="padding:6px 18px"><div class="list">${a.events.map(row).join("") || `<p class="muted">Nothing yet.</p>`}</div></div>
      <span class="small muted">Every run leaves a log line. Nothing leaves your computers unless you connect something.</span></div>`;
  },
};

// ================================================================ the agent library
async function getAgent(url) {  // a permission preview, then install (from the Library tab or an inky://install link)
  let p;
  try { p = await post("/api/library/preview", { url }); } catch (e) { return toast(e.message); }
  const L = p.listing, c = p.check, look = L.look || {}, have = p.have || [];
  modal(`<div class="row">${critter(look.kind, look.color, look.acc, 64, "happy")}<div><h2>${esc(L.title)}</h2><span class="small muted">${L.author ? `by ${esc(L.author)} · ` : ""}${plural(p.skills.length, "skill")}</span>${L.unverified ? `<span class="small" style="display:block;color:var(--coral-t)">Not from the library: nobody reviewed it. Read what it may do below.</span>` : ""}</div></div>
    <p class="small">${esc(L.summary || "")}</p>
    ${have.length ? `<div class="chk"><i class="ok">✓</i><span><b>You have it</b> · <a href="#/bot/${have[0]}/computer" id="gethave">Open</a><br><span class="small muted">Getting it again makes ${have.length > 1 ? "another" : "a second"} copy with its own computer.</span></span></div>` : ""}
    ${c.ok ? `<div class="col" style="gap:8px">
      <div class="chk"><i class="ok">✓</i><span><b>Only visits</b> ${esc(c.domains.join(", ") || "no sites")}<br><span class="small muted">If a step leads anywhere else, it stops.</span></span></div>
      <div class="chk"><i class="${c.irreversible.length ? "bad" : "ok"}">${c.irreversible.length ? "!" : "✓"}</i><span><b>${c.irreversible.length ? "May do, and asks you first each time:" : "Nothing it can’t undo"}</b>${c.irreversible.length ? `<br><span class="small">${c.irreversible.map(esc).join("<br>")}</span>` : ""}</span></div>
      <div class="chk"><i class="ok">✓</i><span><b>Brings no one’s data</b><br><span class="small muted">No sign-ins, memory, results or chat. It starts fresh, in its own browser.</span></span></div></div>`
      : `<div class="chk"><i class="bad">!</i><span><b>This file didn’t pass Inky’s checks</b><br><span class="small">${c.problems.map(esc).join("<br>")}</span></span></div>`}
    <span class="small bad hidden" id="getmsg" role="status" style="background:none"></span>
    <div class="row" style="justify-content:flex-end"><button class="btn" onclick="closeModal()">Cancel</button>${c.ok ? `<button class="btn p" id="getit">${have.length ? `Get ${have.length > 1 ? "another" : "a second"} copy` : `Get ${esc(L.title)}`}</button>` : ""}</div>`, () => {
    if ($("#gethave")) $("#gethave").onclick = () => closeModal();
    if (!$("#getit")) return;
    $("#getit").onclick = async () => {
      const b = $("#getit");
      if (have.length && !b.dataset.sure) {  // asked once more: two copies of the same agent is rarely what you want
        b.dataset.sure = "1"; b.textContent = `Yes, make ${have.length > 1 ? "another" : "a second"} ${L.title}`;
        $("#getmsg").textContent = `You’ll have ${have.length + 1} copies. Each runs on its own.`; $("#getmsg").className = "small"; return;
      }
      busyBtn(b, true, "Getting…");
      try { const r = await post("/api/library/install", { url }); closeModal(); await loadState(); location.hash = `#/bot/${r.id}/computer?hatch=1`; }
      catch (e) { busyBtn(b, false); $("#getmsg").textContent = `${e.message} Nothing was installed; you can try again.`; $("#getmsg").className = "small bad"; }
    };
  });
}
VIEWS.library = {
  async show(el, _, qs) {
    this.el = el; this.q = qs.get("q") || ""; this.tag = qs.get("tag") || ""; this.data = await get("/api/library");
    el.innerHTML = `${mobileBar("Library")}<div class="page"><div><h1>Library</h1><p class="lede">Agents other people made and shared. Get one and it moves in with its skills, ready to run. Anyone can post one, and every file is checked before it’s listed.</p></div>
      <div class="row wrap"><input class="f grow" id="lq" type="search" placeholder="Search agents, sites, tags, authors" value="${esc(this.q)}" aria-label="Search the library" style="min-width:220px"><span class="row wrap" id="ltags" style="gap:6px"></span></div>
      ${this.data.error && !this.data.agents.length ? `<div class="card panel small">${esc(this.data.error)}</div>` : ""}
      <div class="grid3" id="lgrid" aria-live="polite"></div>
      <form class="card row wrap" id="lshare" style="padding:12px 16px"><label class="l" for="lsl" style="margin:0">Got a share link?</label><input class="f mono grow" id="lsl" placeholder="inky://agent?d=…" autocomplete="off" spellcheck="false" style="min-width:220px"><button class="btn s">Open it</button></form>
      <div class="card panel small"><span><b>Post your own.</b> Open one of your bots → <b>Share</b> → <b>Post to the library</b>. Inky checks it and shows you exactly what becomes public first. <a href="https://github.com/GHGuide/inky/tree/main/library" target="_blank" rel="noopener">How the library works ↗</a></span></div></div>`;
    $("#lq", el).oninput = (e) => { this.q = e.target.value; this.draw(); };
    $("#lshare", el).onsubmit = (e) => {  // the same preview and checks as the Library's own agents
      e.preventDefault(); const v = $("#lsl", el).value.trim();
      if (!v) return $("#lsl", el).focus();
      /^inky:\/\//i.test(v) ? handleLink(v) : /^https:\/\//i.test(v) ? getAgent(v) : toast("That isn’t a share link. It starts with inky://");
    };
    this.draw();
  },
  draw() {  // only the tags and results redraw, so the search box keeps your typing
    const el = this.el, { agents } = this.data, q = this.q.trim().toLowerCase();
    const p = new URLSearchParams(); if (this.q) p.set("q", this.q); if (this.tag) p.set("tag", this.tag);
    history.replaceState(null, "", `#/library${p.toString() ? "?" + p : ""}`);  // a reload keeps your search
    const tags = [...new Set(agents.flatMap((a) => a.tags || []))].sort();
    const shown = agents.filter((a) => (!this.tag || (a.tags || []).includes(this.tag)) && (!q || `${a.title} ${a.summary} ${(a.sites || []).join(" ")} ${(a.tags || []).join(" ")} ${a.author}`.toLowerCase().includes(q)));
    $("#ltags", el).innerHTML = `<button class="chip ${this.tag ? "" : "hot"}" data-tag="" aria-pressed="${!this.tag}">All</button>${tags.map((t) => `<button class="chip ${t === this.tag ? "hot" : ""}" data-tag="${esc(t)}" aria-pressed="${t === this.tag}">${esc(t)}</button>`).join("")}`;
    $("#lgrid", el).innerHTML = shown.map((a) => {
      const look = a.look || {}, mine = S.bots.find((b) => (b.library || {}).slug === a.slug);
      return `<div class="card">
        <div class="row">${critter(look.kind, look.color, look.acc, 52)}<div class="grow"><b style="font-size:16px">${esc(a.title)}</b><div class="small muted">${a.author ? `${logo("github", 14)} ${esc(a.author)}` : "anonymous"}</div></div></div>
        <span class="small">${esc(a.summary || "")}</span>
        <span class="small muted">Visits ${esc((a.sites || []).join(", ") || "no sites")}</span>
        <span class="small ${a.may && a.may.length ? "" : "muted"}">${a.may && a.may.length ? `May: ${esc(a.may.join(", "))} (asks you)` : "Nothing it can’t undo"}</span>
        <div class="between"><span class="row wrap" style="gap:6px">${a.reviewed ? `<span class="badge good">Reviewed</span>` : ""}${a.starter ? `<span class="badge">Starter</span>` : ""}${mine ? `<a class="small" href="#/bot/${mine.id}/computer" style="font-weight:600">You have it · Open</a>` : ""}</span><button class="btn s ${mine ? "" : "p"}" data-get="${esc(a.url)}">${mine ? "Get again" : "Get"}</button></div></div>`;
    }).join("") || `<p class="muted">No agents match${this.q ? ` “${esc(this.q)}”` : ""}${this.tag ? ` in ${esc(this.tag)}` : ""}.</p>`;
    $$("[data-tag]", el).forEach((b) => (b.onclick = () => { this.tag = b.dataset.tag; this.draw(); $(`[data-tag="${CSS.escape(this.tag)}"]`, el).focus(); }));  // redrawn: the chip you pressed keeps the focus
    $$("[data-get]", el).forEach((b) => (b.onclick = () => getAgent(b.dataset.get)));
  },
};
function shareBot(b) {  // Share: download the file, make a link anyone can open, or post it to the library
  modal(`<div class="row">${botCritter(b, 44)}<h2>Share ${esc(b.name)}</h2></div><span class="small muted">What you share is its skills, rules, look and personality. Never your sign-ins, memory, results or chat.</span>
    <label class="l" for="shsum">One line about what it does</label><input class="f" id="shsum" value="${esc(b.summary || b.goal || "")}">
    <label class="l" for="shtags">Tags (optional, comma separated)</label><input class="f" id="shtags" placeholder="shopping, flats">
    <div class="col" style="gap:8px"><button class="btn p" id="shcode">${icon("link", 16)}Copy a share link</button>
      <span class="small muted" style="margin-top:-2px">No account needed. Anyone with Inky opens it, or pastes it into their Library, sees what it does, and gets it with one tap.</span>
      <button class="btn" data-dl="/api/bots/${b.id}/export" data-name="${esc(b.name)}.inky">Download the file</button>
      <button class="btn" id="shpost">${logo("github", 18)}Post to the public library</button>
      <details><summary class="small muted">More: a GitHub link</summary><button class="btn s" id="shlink" style="margin-top:8px">${logo("github", 16)}Make a GitHub share link</button></details></div>
    <div class="col" id="shout" style="gap:8px" role="status"></div><div class="row" style="justify-content:flex-end"><button class="btn" id="shclose">Close</button></div>`, () => {
    $("#shclose").onclick = closeModal;
    const meta = () => ({ summary: $("#shsum").value.trim(), tags: $("#shtags").value.split(",").map((t) => t.trim()).filter(Boolean) });
    const out = (html) => ($("#shout").innerHTML = html);
    const next = "Nothing was made public. Try again in a moment, or use Download the file and share it yourself.";
    const failed = (msg) => out(`<span class="small bad" style="background:none">${esc(msg)}</span><span class="small">${next}</span>`);
    const review = async (btn) => {  // exactly what becomes public, and the checker's verdict, before anything leaves
      busyBtn(btn, true, "Checking…");
      let p;
      try { p = await post(`/api/bots/${b.id}/publish/preview`, { meta: meta() }); } catch (e) { failed(e.message); return null; } finally { busyBtn(btn, false); }
      if (!p.check.ok) { out(`<div class="chk"><i class="bad">!</i><span><b>Not shareable yet</b><br><span class="small">${p.check.problems.map(esc).join("<br>")}</span><br><span class="small muted">Fix these on the bot (tell it, or use its Settings and Skills), then press this again. Nothing was made public.</span></span></div>`); return null; }
      return p;
    };
    const confirmPublic = (p, go, label) => {
      out(`<span class="small"><b>This becomes public.</b> Visits ${esc(p.check.domains.join(", ") || "no sites")}. ${p.check.irreversible.length ? "May do (asks first): " + esc(p.check.irreversible.join("; ")) : "Nothing it can’t undo."}</span>
        <details><summary class="small">See the whole file (${Math.round(p.text.length / 1024 * 10) / 10} KB)</summary><pre class="code" style="max-height:30vh;overflow:auto">${esc(p.text)}</pre></details>
        <div class="row" style="justify-content:flex-end"><button class="btn p" id="shgo">${esc(label)}</button></div>`);
      $("#shgo").onclick = async () => { busyBtn($("#shgo"), true, "Working…"); try { await go(); } catch (e) { failed(e.message); } };
    };
    $("#shpost").onclick = async () => {
      const p = await review($("#shpost")); if (!p) return;
      confirmPublic(p, async () => {
        const r = await post(`/api/bots/${b.id}/publish`, { meta: meta() });
        if (r.mode === "pr") out(`<span class="small good">✓ Pull request opened. Once someone reviews and merges it, everyone’s Library shows it.</span><a class="btn s" href="${esc(r.url)}" target="_blank" rel="noopener">Open the pull request ↗</a>`);
        else if (r.mode === "web") { out(`<span class="small">${r.note ? esc(r.note) + " " : ""}GitHub opens with the file filled in. Click <b>Propose new file</b>, then <b>Create pull request</b>.</span><a class="btn s" href="${esc(r.url)}" target="_blank" rel="noopener">Open GitHub ↗</a>`); openOut(r.url); }
        else if (r.mode === "manual") out(`<span class="small">This agent is too big for GitHub’s link. Download the file, then upload it on GitHub’s page.</span><div class="row"><button class="btn s" data-dl="/api/bots/${b.id}/export" data-name="${esc(r.filename)}">Download</button><a class="btn s" href="${esc(r.url)}" target="_blank" rel="noopener">Upload on GitHub ↗</a></div>`);
        else failed((r.problems || []).join(" ") || r.text || "Couldn’t post it.");
      }, p.gh ? "Open a pull request" : "Continue on GitHub");
    };
    $("#shcode").onclick = async () => {  // the whole (checked) agent inside the link: nothing is uploaded anywhere
      const btn = $("#shcode");
      busyBtn(btn, true, "Checking…");
      let r;
      try { r = await post(`/api/bots/${b.id}/share-code`, { meta: meta() }); } catch (e) { busyBtn(btn, false); return failed(e.message); }
      busyBtn(btn, false);
      if (r.mode === "blocked") return out(`<div class="chk"><i class="bad">!</i><span><b>Not shareable yet</b><br><span class="small">${r.problems.map(esc).join("<br>")}</span></span></div>`);
      if (r.mode !== "link") return failed(r.text || "Couldn’t make the link.");
      out(`<span class="small good">✓ Link ready. It carries ${esc(b.name)}${/s$/i.test(b.name) ? "’" : "’s"} skills, rules and look, never your sign-ins, memory or results. Visits ${esc(r.check.domains.join(", ") || "no sites")}.</span>
        <div class="row"><input class="f mono grow" id="shl" value="${esc(r.link)}" readonly aria-label="Share link"><button class="btn s" id="shcopy">Copy</button></div>
        <span class="small muted">Send it in any chat or email. If it doesn’t open Inky when clicked, they paste it into Library → “Got a share link?”.</span>`);
      $("#shcopy").onclick = () => copyText(r.link, $("#shcopy"), $("#shl"));
      copyText(r.link, $("#shcopy"), $("#shl"));
    };
    $("#shlink").onclick = async () => {
      const p = await review($("#shlink")); if (!p) return;
      if (!p.gh) return out(`<span class="small">Share links need GitHub’s <b>gh</b> tool, signed in: run <span class="mono">gh auth login</span> once, then press Make a share link again. You can still send the file.</span>`);
      confirmPublic(p, async () => {
        const r = await post(`/api/bots/${b.id}/share-link`, { meta: meta() });
        if (r.mode !== "gist") return failed(r.text || (r.problems || []).join(" ") || "Couldn’t make the link.");
        out(`<span class="small good">✓ Anyone with Inky can open this link to get ${esc(b.name)}:</span><div class="row"><input class="f mono grow" id="shl" value="${esc(r.link)}" readonly aria-label="Share link"><button class="btn s" id="shcopy">Copy</button></div>`);
        $("#shcopy").onclick = () => copyText(r.link, $("#shcopy"), $("#shl"));
      }, "Make it public");
    };
  });
}
async function copyText(text, btn, field) {  // Copy → Copied → Copy; field: the input or block that shows the text
  try { await navigator.clipboard.writeText(text); }
  catch (e) {  // the browser said no: the text is selected for you, ready to copy
    if (field && field.select) { field.focus(); field.select(); } else if (field) getSelection().selectAllChildren(field);
    return toast(`${field ? "It’s selected" : "Select it"}: press ${MAC ? "⌘C" : "Ctrl+C"} to copy.`);
  }
  btn.textContent = "Copied"; clearTimeout(btn._t); btn._t = setTimeout(() => (btn.textContent = "Copy"), 2000);
}

// ================================================================ adding a server (Computers and setup share this)
let foundTimer = null, onServerPaired = null;
const OS_LOGO = { Darwin: "apple", Windows: "windows", Linux: "linux" };  // unknown: a plain server, never a guess
function serverAdder(install) {
  return `<div class="col" style="gap:16px"><div id="found" class="col" style="gap:8px"></div>
    <div class="col" style="gap:8px"><b>Set it up over SSH</b><span class="small muted">If you can ssh into it with a key, Inky installs itself there and pairs. Nothing to type on the server.</span>
      <div class="row keyrow"><input class="f grow mono" id="sshtarget" placeholder="you@your-server" autocomplete="off" spellcheck="false" aria-label="SSH user and host"><button class="btn" id="sshgo">Set up</button></div><div class="col" id="sshprog" style="gap:4px" role="status"></div></div>
    <div class="col" style="gap:8px"><b>Or run this once on the server</b>
      <div class="row"><pre class="code grow" id="instcmd" style="margin:0">${esc(install)}</pre><button class="btn s" id="copyinst">Copy</button></div>
      <span class="small muted">It prints a pair link. Paste it here, or the address and code:</span>
      <input class="f mono" id="pairurl" placeholder="inky://pair?…  or  192.168.1.20:8800" autocomplete="off" spellcheck="false" aria-label="Pair link or server address">
      <div class="row keyrow"><input class="f grow mono" id="paircode" placeholder="Pairing code (not needed with a link)" autocomplete="off" spellcheck="false" aria-label="Pairing code"><button class="btn" id="pairgo">Pair</button></div>
      <span class="small" id="pairmsg" role="status"></span></div></div>`;
}
function sayIn(sel, t, ok, root = document) { const m = typeof sel === "string" ? $(sel, root) : sel; if (m) { m.textContent = t; m.className = "small " + (ok === true ? "good" : ok === false ? "bad" : "muted"); if (ok === false) m.style.background = "none"; } }
function sshLine(m) {  // SSE "ssh" progress from the engine
  const box = $("#sshprog"); if (!box) return;
  const bad = m.step === "failed", last = box.lastElementChild;
  if (m.step === "installing" && last && last.dataset.step === "installing" && !/^Installing Inky/.test(m.text)) { $("span", last).textContent = m.text; return; }
  box.insertAdjacentHTML("beforeend", `<div class="chk" data-step="${esc(m.step)}"><i class="${bad ? "bad" : "ok"}">${bad ? "!" : m.step === "done" ? "✓" : "·"}</i><span>${esc(m.text || m.step)}</span></div>${bad && m.fix ? `<div class="small" style="padding-left:28px"><b>${esc(m.fix)}</b></div>` : ""}`);
  if (m.step === "done" || bad) {
    const lost = !document.activeElement || document.activeElement === document.body || document.activeElement === $("#sshgo");
    busyBtn($("#sshgo"), false);
    if (bad && lost && $("#sshtarget")) $("#sshtarget").focus();  // the button was off while it worked: back to the address, to fix it
  }
  if (m.step === "done") { SOUND.play("chime"); confetti(); if (onServerPaired) onServerPaired(); }
}
const NOT_ADDRESS = "That isn’t an address. It looks like 192.168.1.20:8800 or a pair link.";
function bindServerAdder(install, onPaired) {
  onServerPaired = onPaired;
  $("#copyinst").onclick = () => copyText(install, $("#copyinst"), $("#instcmd"));
  const pair = async () => {
    const url = $("#pairurl").value.trim(), code = $("#paircode").value.trim(), btn = $("#pairgo");
    if (btn.disabled) return;
    if (!url) return sayIn("#pairmsg", "Paste the pair link, or the address and code.", false);
    if (/\s/.test(url)) return sayIn("#pairmsg", NOT_ADDRESS, false);
    if (!url.startsWith("inky://") && !code) return sayIn("#pairmsg", "Put in the code it printed too.", false);
    busyBtn(btn, true, "Pairing…"); sayIn("#pairmsg", "Pairing… if the server doesn’t answer, this takes up to 15 seconds.");
    try {
      const r = await post("/api/computers", { url, code });
      sayIn("#pairmsg", `✓ Paired with ${r.name || "it"}. Its bots show up in Computers.`, true); SOUND.play("chime");
      $("#pairurl").value = ""; $("#paircode").value = "";
      if (onPaired) onPaired();
    } catch (e) { sayIn("#pairmsg", e.message, false); }
    const lost = !document.activeElement || document.activeElement === document.body;
    busyBtn(btn, false);
    if (lost && document.contains(btn)) btn.focus();
  };
  $("#pairgo").onclick = pair;
  $("#paircode").onkeydown = (e) => { if (e.key === "Enter") pair(); };
  $("#pairurl").onkeydown = (e) => { if (e.key === "Enter") pair(); };
  const ssh = async () => {
    const t = $("#sshtarget").value.trim(), box = $("#sshprog");
    if ($("#sshgo").disabled) return;
    if (!t) { box.innerHTML = `<span class="small bad" style="background:none">Type the user and server first, like you@your-server.</span>`; return $("#sshtarget").focus(); }
    if (/\s/.test(t)) { box.innerHTML = `<span class="small bad" style="background:none">That has a space in it. It looks like you@your-server, or you@192.168.1.20.</span>`; return $("#sshtarget").focus(); }
    box.innerHTML = ""; busyBtn($("#sshgo"), true, "Setting up…");
    try { await post("/api/computers/ssh", { target: t }); } catch (e) { sshLine({ step: "failed", text: e.message }); }
  };
  $("#sshgo").onclick = ssh;
  $("#sshtarget").onkeydown = (e) => { if (e.key === "Enter") ssh(); };
  let shown = "";
  const done = new Map();  // servers you just paired from this list: they leave it, so their ✓ stays here
  const t0 = Date.now();
  const drawFound = async () => {
    const box = $("#found"); if (!box) return clearInterval(foundTimer);
    if ($("[data-fpair]:disabled", box)) return;  // one is pairing right now
    let found = [];
    try { ({ found } = await get("/api/computers/found")); } catch (e) { return; }
    const key = (found.map((f) => f.url).join() || (Date.now() - t0 > 15e3 ? "quiet" : "")) + "|" + [...done.keys()].join();
    if (key === shown) return;  // don't wipe a code you're typing
    shown = key;
    if (!found.length && !done.size && Date.now() - t0 > 15e3 && APP && /Mac/.test(navigator.platform)) {  // macOS keeps apps off the local network until you allow it
      box.innerHTML = `<span class="small muted">Nothing found on your network yet. If macOS asked whether Inky may find devices on your local network, allow it (System Settings → Privacy & Security → Local Network).</span>`;
      return;
    }
    const rows = found.filter((f) => !done.has(f.url));
    box.innerHTML = (rows.length || done.size ? `<b>Found ${found.some((f) => f.via === "tailscale") ? "on your network and tailnet" : "on your network"}</b>` : "")
      + [...done].map(([u, n]) => `<div class="card" data-done="${esc(u)}" tabindex="-1" style="padding:10px 12px"><span class="small good">✓ Paired with ${esc(n)}. Its bots show up in Computers.</span></div>`).join("")
      + rows.map((f) => `<div class="card" data-frow style="padding:10px 12px;gap:6px"><div class="lrow frow2">${logo(OS_LOGO[f.os] || (f.via === "tailscale" ? "tailscale" : "server"), 30)}<span class="grow"><b>${esc(f.name)}</b><br><span class="mono small muted">${esc(f.host || f.url)}${f.via === "tailscale" ? " · works away from home" : ""}</span></span><input class="f mono" data-fcode placeholder="Its code" style="width:120px" aria-label="Pairing code for ${esc(f.name)}"><button class="btn s" data-fpair="${esc(f.url)}" data-fname="${esc(f.name)}">Pair</button></div><span class="small" data-fmsg role="status"></span></div>`).join("");
    $$("[data-fpair]", box).forEach((b) => {
      const row = b.closest("[data-frow]"), inp = $("[data-fcode]", row), msg = $("[data-fmsg]", row);
      const go = async () => {
        const code = inp.value.trim();
        if (!code) { sayIn(msg, "Type the code that server printed when you installed it.", false); return inp.focus(); }
        busyBtn(b, true, "Pairing…"); sayIn(msg, "Pairing…");
        try { await post("/api/computers", { url: b.dataset.fpair, code }); } catch (e) { busyBtn(b, false); sayIn(msg, e.message, false); return inp.focus(); }
        SOUND.play("chime"); done.set(b.dataset.fpair, b.dataset.fname); busyBtn(b, false); shown = "";
        const i = $$("[data-frow]", box).indexOf(row);
        if (onPaired) onPaired();
        await drawFound();  // its row leaves the list: the focus goes to the next one, or to its ✓
        const a = document.activeElement, next = $$("[data-fcode]", box)[i] || $(`[data-done="${CSS.escape(b.dataset.fpair)}"]`, box);
        if (next && (!a || a === document.body || !a.isConnected)) next.focus();
      };
      b.onclick = go;
      inp.onkeydown = (e) => { if (e.key === "Enter") go(); };
    });
  };
  clearInterval(foundTimer); drawFound(); foundTimer = setInterval(drawFound, 5000);
}

// ================================================================ computers
VIEWS.computers = {
  live: false,  // the app never redraws this page: the cards redraw themselves, so the server adder keeps what you typed
  async show(el) {
    this.el = el;
    const { install } = await get("/api/setup");
    el.innerHTML = `${mobileBar("Computers")}<div class="page"><div class="between"><div><h1>Computers</h1><p class="lede">Where your bots’ browsers run. Each bot gets its own sandbox, never your screen.</p></div><button class="btn" id="addsrv">Add a server</button></div>
      <div class="grid2 clist" id="clist"><span class="small muted">Looking at your computers…</span></div>
      <div class="card panel"><div class="between"><span><b>Your own screen</b><br><span class="small muted">Let a bot use a visible browser window on your screen, with the coral frame and ask-first rules. You still turn it on per bot, and Esc stops it any time.</span></span><button class="toggle ${S.settings.screen_allowed ? "on" : ""}" id="scrok" role="switch" aria-checked="${!!S.settings.screen_allowed}" aria-label="Allow bots on my screen"></button></div></div>
      <section class="card" id="adder"><h2>Add a server</h2><span class="small muted">Any Linux server or spare Mac. 2 GB of memory runs about 3 bots, and they keep working while this computer sleeps.</span>${serverAdder(install)}</section></div>`;
    $("#addsrv", el).onclick = () => { $("#adder", el).scrollIntoView({ behavior: calmMotion() ? "auto" : "smooth", block: "start" }); $("#sshtarget", el).focus({ preventScroll: true }); };
    $("#scrok", el).onclick = async (e) => {
      const t = e.currentTarget, on = !t.classList.contains("on"), set = (v) => { t.classList.toggle("on", v); t.setAttribute("aria-checked", v); };
      set(on);
      try { S.settings = await post("/api/settings", { screen_allowed: on }); toast(on ? "Bots may use your screen now. Turn it on per bot in its Settings." : "Bots stay off your screen."); }
      catch (err) { set(!on); toast(err.message); }
    };
    bindServerAdder(install, () => this.cardsSoon(300));
    clearInterval(this.poll);
    this.poll = setInterval(() => {  // servers come and go: check again, but never under a dialog or your typing
      const a = document.activeElement;
      if (!document.hidden && $("#modal").classList.contains("hidden") && !(a && /INPUT|TEXTAREA|SELECT/.test(a.tagName))) this.cards();
    }, 15e3);
    await this.cards();
  },
  onEvent(m) {
    if (m.kind === "ssh") sshLine(m);
    if (m.kind === "move") { this.progress(m); if (["done", "failed"].includes(m.step)) this.cardsSoon(); }
    if (m.kind === "bots") this.cardsSoon();
  },
  cardsSoon(ms = 600) { clearTimeout(this.t); this.t = setTimeout(() => this.cards(), ms); },
  leave() { clearInterval(foundTimer); clearInterval(this.poll); clearTimeout(this.t); this.moving = null; },
  progress(m) {
    if (this.moving && m.bot !== this.moving) return;
    const box = $("#moveprog"); if (!box) return;
    const bad = m.step === "failed" || m.step === "check_failed", last = box.lastElementChild;
    if (m.step === "failed" && last && last.dataset.step === "check_failed")  // one line: why the check didn't pass, and that nothing changed
      $("span", last).textContent = `${$("span", last).textContent.replace(/,? so it stays here\.?$/, ".")} ${m.text || ""}`.trim();
    else box.insertAdjacentHTML("beforeend", `<div class="chk" data-step="${esc(m.step)}"><i class="${bad ? "bad" : "ok"}">${bad ? "!" : "✓"}</i><span>${esc(m.text || m.step)}</span></div>`);
    if ((m.step === "done" || m.step === "failed") && this.waiting) this.waiting(m.step);
  },
  ended(step, again) {  // a move or bring back finished: no more spinner or Cancel, one button
    this.waiting = null;
    $$("#mgo,#mcancel").forEach((x) => x.classList.add("hidden"));
    if ($("#mt") && step !== "done") $("#mt").disabled = false;
    const c = $("#moveclose"); if (!c) return;
    const id = this.moving, gone = step !== "done" && id && /no longer there/.test(($("#moveprog") || {}).textContent || "");
    c.textContent = step === "done" ? "Done" : gone ? "Remove it here" : "Try again"; c.classList.remove("hidden"); c.focus();
    c.onclick = step === "done" ? closeModal : gone ? async () => {  // it's gone over there: trying again can't help
      try { await del(`/api/bots/${id}?here=1`); toast("Removed it from this computer."); closeModal(); await loadState(); } catch (e) { toast(e.message); }
    } : again;  // closing redraws the cards
  },
  starting(go) {  // (again) a move or bring back is on its way; closing the window doesn't stop it
    $("#moveprog").innerHTML = ""; $("#moveclose").classList.add("hidden");
    $("#mcancel").textContent = "Close"; $("#mcancel").classList.remove("hidden");
    this.waiting = (step) => this.ended(step, () => this.starting(go));
    go();
    if (!document.activeElement || document.activeElement === document.body) $("#mcancel").focus();  // the pressed button is off or gone now
  },
  async cards() {
    const box = $("#clist", this.el); if (!box) return;
    let computers, pair_code;
    try { ({ computers, pair_code } = await get("/api/computers")); } catch (e) { box.innerHTML = `<span class="small bad" style="background:none">${esc(e.message)}</span>`; return; }
    if (!box.isConnected) return;
    this.computers = computers;
    const reach = computers.filter((c) => c.kind === "remote" && c.ok);
    const mineOf = (c, rb) => S.bots.find((b) => b.status === "moved" && String(b.computer) === String(c.id) && sameBot(b, rb));  // it moved there from here
    const movedTo = (c) => S.bots.filter((b) => b.status === "moved" && String(b.computer) === String(c.id));
    const running = (b) => ["working", "learning", "paused", "takeover", "showing"].includes(b.status);
    const botCard = (c, b, away) => {  // away: your bot on a server that isn't answering, greyed, as this computer last knew it
      const mine = c.kind === "local" || away ? b : mineOf(c, b), name = (mine || b).name;
      const act = away ? "" : c.kind === "local" ? (reach.length && b.status !== "moved" ? `<button class="btn s" data-move="${b.id}" aria-label="Move ${esc(name)}">Move</button>` : "")
        : mine ? `<button class="btn s" data-back="${mine.id}" aria-label="Bring ${esc(name)} back">Bring back</button>` : "";
      const live = running(b) && c.kind === "local";
      const body = `<div class="thumb ${live ? "" : "idle"}" style="height:90px">${live ? `<img src="${screenUrl(b.id)}" alt="">` : esc(away ? "can’t see it now" : (STATUS[b.status] || [String(b.status).replace(/_/g, " ")])[0])}</div>
        <span class="row small">${botCritter(mine || b, 22)}<b class="grow cname" title="${esc(name)}">${esc(name)}</b></span>`;
      return `<div class="botcard cbot${mine ? "" : " nolink"}${away ? " away" : ""}">${mine ? `<a class="cblink" data-open="${mine.id}" href="#/bot/${mine.id}/computer" aria-label="${esc(name)}, open its computer">${body}</a>` : body}${act}</div>`;
    };
    redraw(box, () => (box.innerHTML = computers.map((c) => {
      const away = c.kind === "remote" && !c.ok ? movedTo(c) : [];
      const count = (c.ok ? ` · ${plural(c.bots.length, "bot")}` : away.length ? ` · ${plural(away.length, "bot")} of yours` : "").replace(/ (?=bots?)/, "\u00a0");  // "3 bots" never splits
      const where = c.kind === "local" ? `this computer${c.docker && c.docker.running ? ` · ${logo("docker", 18)} Docker ${esc(c.docker.version)}` : ""}` : esc(c.url);
      return `<div class="card" data-comp="${esc(c.id)}" tabindex="-1"><div class="row">${logo(OS_LOGO[c.os] || "server", 40)}<div class="grow"><b class="cname" style="font-size:18px">${esc(c.name)}</b><div class="mono small muted cname">${where}${count}</div></div><span class="pill ${c.ok ? "live" : "hot"}"><i style="background:${c.ok ? "var(--green)" : "var(--coral)"}"></i>${c.ok ? (c.kind === "local" ? "awake" : "reachable") : "can’t reach it"}</span></div>
        <div class="grid2">${c.bots.map((b) => botCard(c, b)).join("") + away.map((b) => botCard(c, b, true)).join("") || `<span class="small muted">${c.ok ? "No bots here" : "It isn’t answering, so Inky can’t see its bots."}</span>`}</div>
        ${c.kind === "local" ? `<div class="card panel small"><span>This computer’s pairing code: <b class="mono">${esc(pair_code)}</b>. Type it on another Inky to send bots here.</span></div>` : `<button class="btn s hot" data-unpair="${c.id}" style="align-self:flex-start">Unpair</button>`}</div>`;
    }).join("")));  // a redraw (every "bots" event) keeps the focus on the same card's button or link
    const back = this.focusBot && ($(`[data-move="${this.focusBot}"],[data-back="${this.focusBot}"],[data-open="${this.focusBot}"]`, box)
      || $(`[data-comp="${CSS.escape(String(this.focusComp))}"]`, box) || $("#addsrv", this.el));  // a bot that went home is gone from here: its computer
    if (back && (!document.activeElement || document.activeElement === document.body)) back.focus();  // after its dialog: back to that bot
    this.focusBot = this.focusComp = null;
    $$("[data-unpair]", box).forEach((x) => (x.onclick = () => this.unpair(computers.find((c) => String(c.id) === x.dataset.unpair))));
    $$("[data-back]", box).forEach((x) => (x.onclick = () => this.bringBack(S.bots.find((b) => b.id === +x.dataset.back))));
    $$("[data-move]", box).forEach((x) => (x.onclick = () => {
      const b = S.bots.find((y) => y.id === +x.dataset.move), targets = (this.computers || []).filter((c) => c.kind === "remote" && c.ok);
      modal(`<div class="row">${botCritter(b, 44)}<h2 class="cname">Move ${esc(b.name)}</h2></div><label class="l" for="mt">To</label><select class="f" id="mt">${targets.map((t) => `<option value="${t.id}">${esc(t.name)}</option>`).join("")}</select>
        <span class="small muted">${targets.length ? "It pauses between runs, packs its memory, skills and sign-ins, runs one check there, and only then leaves this computer." : "No paired server answers right now. Pair one below, or check it’s on."}</span><div class="col" id="moveprog" role="status"></div>
        <div class="row" style="justify-content:flex-end"><button class="btn" id="mcancel">Cancel</button><button class="btn p" id="mgo" ${targets.length ? "" : "disabled"}>Move it</button><button class="btn p hidden" id="moveclose">Done</button></div>`, () => {
        $("#mcancel").onclick = closeModal;
        $("#mgo").onclick = () => this.starting(async () => {
          this.moving = b.id; this.moveTo = $("#mt").value; $("#mt").disabled = true;
          $("#mgo").classList.remove("hidden"); busyBtn($("#mgo"), true, "Moving…");
          try { await post(`/api/bots/${b.id}/move`, { computer: +$("#mt").value }); } catch (err) { this.progress({ bot: b.id, step: "failed", text: err.message }); }
        });
      }, () => { this.moving = null; this.waiting = null; this.focusBot = b.id; this.focusComp = this.moveTo; this.cardsSoon(50); });
    }));
  },
  bringBack(b) {  // one bot that moved away comes home, with progress
    modal(`<div class="row">${botCritter(b, 44)}<h2 class="cname">Bring ${esc(b.name)} back</h2></div><span class="small muted">It stops there, packs its memory, skills and sign-ins, and moves back to this computer.</span>
      <div class="col" id="moveprog" role="status"></div><div class="row" style="justify-content:flex-end"><button class="btn" id="mcancel">Close</button><button class="btn p hidden" id="moveclose">Done</button></div>`, () => {
      $("#mcancel").onclick = closeModal;
      this.starting(() => { this.moving = b.id; post(`/api/bots/${b.id}/bring-back`, {}).catch((e) => this.progress({ bot: b.id, step: "failed", text: e.message })); });
    }, () => { this.moving = null; this.waiting = null; this.focusBot = b.id; this.focusComp = "local"; this.cardsSoon(50); });
  },
  unpair(c) {  // asks first, and offers to bring your bots home before the link to them goes
    const mine = S.bots.filter((b) => b.status === "moved" && String(b.computer) === String(c.id)), them = (one, many) => (mine.length === 1 ? one : many);
    const others = c.bots.filter((rb) => !mine.some((b) => sameBot(b, rb))), one = others.length === 1;
    const there = !c.ok ? `${esc(c.name)} isn’t answering, so Inky can’t see its bots.`
      : others.length ? `${plural(others.length, "bot")} ${one ? "lives" : "live"} there: <b>${others.map((rb) => esc(rb.name)).join(", ")}</b>. ${one ? "It keeps" : "They keep"} running there, but this computer can’t see or reach ${one ? "it" : "them"} any more.`
      : mine.length ? "" : "No bots live there. You can pair it again any time with its code.";
    modal(`<h2 class="cname">Unpair ${esc(c.name)}?</h2>
      <span class="small">${there}</span>
      ${mine.length ? `<span class="small"><b>${mine.map((b) => esc(b.name)).join(", ")}</b> moved there from here. Unpairing forgets ${them("it", "them")} here; ${them("it keeps", "they keep")} running there. Bring ${them("it", "them")} back first to keep ${them("it", "them")} on this computer.${c.ok ? "" : ` <b id="ubackwhy">That works once ${esc(c.name)} answers.</b>`}</span>` : ""}
      <div class="col" id="moveprog" role="status"></div><span class="small" id="umsg" role="status"></span>
      <div class="row wrap" style="justify-content:flex-end"><button class="btn" id="uno">Cancel</button>${mine.length ? `<button class="btn p" id="uback" ${c.ok ? "" : 'disabled aria-describedby="ubackwhy"'}>Bring ${them("it", "them")} back, then unpair</button>` : ""}<button class="btn hot" id="uyes">Unpair</button></div>`, () => {
      const unpair = async () => {
        busyBtn($("#uyes"), true, "Unpairing…");
        try { await del(`/api/computers/${c.id}`); closeModal(); toast(`Unpaired ${c.name}`); await loadState(); await this.cards(); if (document.activeElement === document.body && $("#addsrv")) $("#addsrv").focus(); } catch (e) { busyBtn($("#uyes"), false); sayIn("#umsg", e.message, false); $("#uyes").focus(); }
      };
      $("#uno").onclick = closeModal;
      $("#uyes").onclick = unpair;
      if ($("#uback")) $("#uback").onclick = async () => {
        busyBtn($("#uback"), true, "Bringing back…"); $("#uyes").disabled = true; $("#moveprog").innerHTML = ""; $("#umsg").textContent = "";
        for (const b of mine) {
          this.moving = b.id;
          const step = await new Promise((res) => { this.waiting = res; post(`/api/bots/${b.id}/bring-back`, {}).catch((e) => this.progress({ bot: b.id, step: "failed", text: e.message })); });
          this.waiting = null;
          if (step !== "done") {  // stop at the first that couldn't come back: nothing was unpaired
            this.moving = null; busyBtn($("#uback"), false); $("#uyes").disabled = false;
            sayIn("#umsg", `Nothing was unpaired. Try again when ${c.name} is on, or unpair now: ${them("it keeps", "they keep")} running there.`);
            return $("#uback").focus();
          }
        }
        this.moving = null; await loadState(); unpair();
      };
    }, () => { this.moving = null; this.waiting = null; });
  },
};

// ================================================================ form pages: models, keys, connectors, make it yours, settings
// They are live:false, so a live event never redraws them under your hands. They redraw after their own actions
// (through redraw, which keeps what you typed) and update single elements for the events they care about.
function formSay(where, text, ok) {  // a status line: ok true = good, false = bad, "warn" = amber, else muted
  const m = typeof where === "string" ? $(where) : where;
  if (m) { m.textContent = text; m.className = "small " + (ok === true ? "good" : ok === false ? "bad" : ok === "warn" ? "warn" : "muted"); }
}
function busy(b, on) {  // a button that is working can't be pressed twice, and gets the focus back afterwards
  if (!b) return;
  const had = document.activeElement === b;
  b.disabled = on;
  if (!on && (had || document.activeElement === document.body) && document.contains(b)) b.focus();
}
function redraw(el, render) {  // draw a form page again, keeping what you typed or picked, open sections and the focus
  const key = (x) => x.id || [...x.attributes].filter((a) => a.name.startsWith("data-")).map((a) => `${a.name}=${a.value}`).join("&");
  const changed = (i) => i.tagName === "SELECT" ? !(i.selectedOptions[0] && i.selectedOptions[0].defaultSelected) : i.value !== i.defaultValue;
  const vals = $$("input,textarea,select", el).filter((i) => i.type !== "checkbox" && changed(i)).map((i) => [key(i), i.value]);
  const open = $$("details[open]", el).map(key), a = document.activeElement, focus = a && el.contains(a) ? key(a) : "";
  render();
  const find = (k) => k && $$("input,textarea,select,details,button,a", el).find((x) => key(x) === k);
  vals.forEach(([k, v]) => { const i = find(k); if (i && i.tagName !== "BUTTON" && i.tagName !== "A" && i.tagName !== "DETAILS") i.value = v; });
  open.forEach((k) => { const d = find(k); if (d && d.tagName === "DETAILS") d.open = true; });
  const f = find(focus); if (f) f.focus();
}
const GB = (bytes) => (bytes / 1e9).toFixed(1);  // decimal GB, like ollama.com, `ollama list` and the local catalog
const KEY_SOURCE = { keychain: "saved in your Keychain", file: "saved on this computer", env: "from your environment (.env)", environment: "from your environment (.env)" };
const keyErr = (status) => ([401, 403].includes(+status) ? `refused (${status})` : `error ${status}`);

// ================================================================ models
const ROLE_NAMES = { learn: "learning a site", chat: "talking with you", repair: "fixing a step", smart: "smarter model", test: "a test" };
const PROVIDER_NAMES = { ollama: "Ollama", custom: "Your own server", openrouter: "OpenRouter", anthropic: "Anthropic", openai: "OpenAI", gemini: "Google Gemini", groq: "Groq", xai: "xAI", mistral: "Mistral" };
const provLabel = (p) => (p.name === "custom" ? "Your own server" : p.label);
const ROLE_ABOUT = { learn: "reads the page and plans the steps, once per site", chat: "understands “euro only” and turns it into a rule",
  repair: "when a button moves and its name isn’t enough", smart: "when you choose “Try a smarter model”" };
VIEWS.models = {
  live: false,
  async show(el, [sub]) { this.el = el; this.sub = sub; await this.refresh(); },
  onEvent(m) {
    if (m.kind === "pull" && this.sub === "local") this.pulled(m);
    if (m.kind === "thinking" && !this.sub) {  // only the "Right now" card follows along; the forms hold still
      clearTimeout(this.liveT);
      this.liveT = setTimeout(async () => {
        const lv = await get("/api/models/live").catch(() => null); if (!lv || !this.el.isConnected) return;
        const html = this.liveCard(lv), cur = $(".mlive", this.el);
        if (cur) cur.outerHTML = html || "";
        else if (html) { const pk = $(".mpick", this.el); if (pk) pk.insertAdjacentHTML("afterend", html); }
        this.bindLive();
      }, 300);
    }
  },
  async refresh() {
    if (this.sub === "local") { const loc = await get("/api/models/local"); return redraw(this.el, () => this.local(loc)); }
    const [md, loc, ch, lv] = await Promise.all([get("/api/models"), get("/api/models/local"), get("/api/models/choices"), get("/api/models/live").catch(() => ({ thinking: [], loaded: [] }))]);
    redraw(this.el, () => this.main(md, loc, ch, lv));
  },
  liveCard(lv) {  // what the models are doing right now, and what's in memory
    if (!lv.thinking.length && !lv.loaded.length) return "";
    return `<section class="card mlive"><div class="between"><b>Right now</b><button class="btn s" id="mlrefresh" type="button">Check again</button></div>
      ${lv.thinking.map((t) => `<div class="between"><span class="row"><span class="livedot" aria-hidden="true"></span><span><b class="mono">${esc(t.model)}</b> is thinking${t.name ? ` for <a href="#/bot/${t.bot}/chat">${esc(t.name)}</a>` : ""} <span class="small muted">· ${esc(ROLE_NAMES[t.role] || t.role)} · <span data-since="${t.since}">${t.seconds} s</span></span></span></span><button class="btn s hot" data-mstop="${t.bot == null ? "" : t.bot}">Stop</button></div>`).join("")
        || `<span class="small muted">No model is thinking right now.</span>`}
      ${lv.loaded.length ? `<div class="col" style="gap:6px"><span class="small muted">In memory on this computer (Ollama keeps a model loaded for a few minutes after use)</span>${lv.loaded.map((m) => `<div class="between"><span><b class="mono">${esc(m.name)}</b> <span class="small muted">· ${m.gb} GB</span></span><button class="btn s" data-unload="${esc(m.name)}">Unload</button></div>`).join("")}</div>` : ""}</section>`;
  },
  bindLive() {
    $$("[data-mstop]", this.el).forEach((b) => (b.onclick = async () => {
      busy(b, true); await post("/api/models/stop", b.dataset.mstop ? { bot: +b.dataset.mstop } : {}).catch((e) => toast(e.message));
      toast("Stopped. The run it was thinking for stopped too."); this.refresh();
    }));
    $$("[data-unload]", this.el).forEach((b) => (b.onclick = async () => {
      busy(b, true);
      try { await post("/api/models/unload", { name: b.dataset.unload }); toast(`Unloaded ${b.dataset.unload}: its memory is free again`); } catch (e) { toast(e.message); }
      this.refresh();
    }));
    if ($("#mlrefresh", this.el)) $("#mlrefresh", this.el).onclick = () => this.refresh();
  },
  picker(ch) {  // the one choice most people need: which model every bot uses
    const val = (c) => `${c.provider}|${c.model || ""}`, u = ch.using;
    const cur = u ? ch.choices.find((c) => c.provider === u.provider && (!c.model || c.model === u.model)) : null;
    const extra = u && !cur ? [{ provider: u.provider, model: u.model, group: "Using now", label: `${u.model} · ${(PROVIDER_NAMES[u.provider] || u.provider)}` }] : [];
    const all = [...extra, ...ch.choices], groups = [...new Set(all.map((c) => c.group))];
    const options = groups.map((g) => `<optgroup label="${esc(g)}">${all.filter((c) => c.group === g).map((c) => `<option value="${esc(val(c))}" ${c === cur || extra.includes(c) ? "selected" : ""}>${esc(c.label)}${ch.recommended && c.model === ch.recommended ? " · recommended" : ""}</option>`).join("")}</optgroup>`).join("");
    const now = u ? `Your bots use <b>${esc(u.model)}</b>${u.provider === "ollama" ? " on this computer" : ` from ${esc(PROVIDER_NAMES[u.provider] || u.provider)}`}.` : ch.mixed ? "Your bots use different models for different jobs (below)." : "No model yet.";
    return `<section class="card mpick"><div class="col" style="gap:2px"><b style="font-size:17px">The model your bots use</b><span class="small muted">One model for everything. Pick it, press Use it, and Inky checks it works.</span></div>
      ${all.length ? `<div class="row wrap"><label class="vh" for="mpick">Model</label><select class="f grow" id="mpick" style="min-width:240px">${options}</select><button class="btn p" id="muse">Use it</button></div>`
        : `<span>There’s no model to pick yet. Start or install Ollama on this computer, or add an API key.</span>`}
      <span class="small" id="mpickmsg" role="status">${now}</span><span class="small warn hidden" id="msmall">Small models chat fine but learn new sites poorly. For learning, pick a bigger one or add an API key.</span></section>`;
  },
  bindPicker(ch) {
    const sel = $("#mpick", this.el); if (!sel) return;
    const pick = () => { const [p, m] = sel.value.split("|"); return { provider: p, model: m || null, c: ch.choices.find((c) => c.provider === p && (c.model || "") === m) }; };
    const small = () => $("#msmall", this.el).classList.toggle("hidden", !(pick().c && pick().c.small));
    sel.onchange = small; small();
    $("#muse", this.el).onclick = async () => {
      const b = $("#muse", this.el), { provider, model } = pick();
      busy(b, true); formSay("#mpickmsg", "Checking it works…");
      try {
        const r = await post("/api/models/connect", { provider, model });
        if (!r.ok) { formSay("#mpickmsg", r.reply || "It didn’t answer.", false); return busy(b, false); }
        toast(`All your bots use ${r.model} now`);
        await this.refresh();
        formSay("#mpickmsg", `✓ Works: it answered in ${r.seconds} s. All your bots use ${r.model} now.`, true);
      } catch (e) { formSay("#mpickmsg", e.message, false); busy(b, false); }
    };
  },
  main(md, loc, ch, lv = { thinking: [], loaded: [] }) {
    const provs = md.providers, o = loc.ollama, local = o.models.map((x) => x.name);
    const suggest = (p) => (p === "ollama" ? local : [...new Set(Object.values(md.roles).filter((v) => v.provider === p && v.model).map((v) => v.model))]);
    const opts = (p) => suggest(p).map((x) => `<option value="${esc(x)}">`).join("");
    this.el.innerHTML = `${mobileBar("Models")}<div class="page"><div class="between"><div><h1>Models</h1><p class="lede">Bots only use a model to learn a job or understand you. Repeating a job uses none.</p></div><span class="row"><a class="btn" href="#/models/local">Add a local model</a><a class="btn p" href="#/keys">Add an API key</a></span></div>
      ${this.picker(ch)}
      ${this.liveCard(lv)}
      <details class="card mjobs" data-keep="mjobs"${ch.mixed ? " open" : ""}><summary><b>Different models for different jobs</b> <span class="small muted">optional, for when one model isn’t enough</span></summary><div class="list">${Object.entries(md.role_labels).map(([r, label]) => { const v = md.roles[r] || {}; return `<div class="mrole"><div class="row mrow"><span class="col mlabel" style="gap:2px"><b>${esc(label)}</b><span class="small muted">${ROLE_ABOUT[r] || ""}</span></span>
        <select class="f mprov" data-rp="${r}" aria-label="Provider for ${esc(label)}">${provs.map((p) => `<option value="${p.name}" ${v.provider === p.name ? "selected" : ""}>${esc(provLabel(p))}</option>`).join("")}</select>
        <input class="f mono mmodel" data-rm="${r}" value="${esc(v.model || "")}" placeholder="model name" list="ml-${r}" aria-label="Model for ${esc(label)}" autocomplete="off" spellcheck="false"><datalist id="ml-${r}">${opts(v.provider)}</datalist>
        <span class="row" style="gap:6px"><button class="btn s" data-save="${r}" aria-label="Save ${esc(label)}">Save</button><button class="btn s" data-test="${r}" aria-label="Test ${esc(label)}">Test</button></span></div>
        <span class="small" data-out="${r}" role="status"></span></div>`; }).join("")}</div></details>
      <div class="grid2"><section class="card"><div class="head"><b>On this computer</b><span class="small muted">free · private · works offline</span></div>
        <div class="between"><span>Ollama</span>${o.running ? `<span class="small good">● running · ${o.models.length} model${o.models.length === 1 ? "" : "s"}</span>` : o.installed ? `<span class="row" style="gap:8px"><span class="small muted">installed, not running</span><button class="btn s" data-ostart>Start Ollama</button></span>` : `<a class="small" href="https://ollama.com/download" target="_blank" rel="noopener">Install Ollama ↗</a>`}</div>
        ${o.models.length ? `<div class="row wrap">${o.models.map((x) => `<span class="chip">${esc(x.name)} · ${GB(x.size)} GB</span>`).join("")}</div>` : ""}
        <div class="between"><span>LM Studio</span><span class="small muted">${loc.lmstudio.installed ? "found" : "not found"}</span></div>
        <div class="between"><span>Your own server</span><span class="small mono addr ${loc.custom.reachable ? "good" : "muted"}">${esc(loc.custom.base)} · ${loc.custom.reachable ? "reachable" : "not reachable"}</span></div><a class="small" href="#/models/local" style="font-weight:600">Add a local model</a></section>
      <section class="card"><div class="head"><b>With your keys</b><span class="small muted">you pay the provider directly</span></div>${provs.filter((p) => !p.local).map((p) => { const e = md.errors[p.name]; return `<div class="between"><span class="row">${providerLogo(p.name)}${esc(p.label)}</span>${p.key ? `<a class="small ${e ? "warn" : "good"}" href="#/keys?p=${p.name}">● ${esc(KEY_SOURCE[p.key] || p.key)}${e ? ` · ${keyErr(e.status)}` : ""}</a>` : `<a class="btn s" href="#/keys?p=${p.name}">Add key</a>`}</div>`; }).join("")}</section></div>
      <span class="small muted">Local models never leave this computer. Cloud models only see the page text a bot sends while learning, never your passwords or files.</span></div>`;
    const row = (r) => ({ p: $(`[data-rp="${r}"]`, this.el), m: $(`[data-rm="${r}"]`, this.el), out: $(`[data-out="${r}"]`, this.el), label: md.role_labels[r] });
    $$("[data-rp]", this.el).forEach((s) => (s.onchange = () => {  // suggestions follow the provider; a model from another provider is cleared
      const r = s.dataset.rp, list = suggest(s.value), i = row(r).m;
      $(`#ml-${r}`, this.el).innerHTML = opts(s.value);
      const saved = (md.roles[r] || {}).provider === s.value ? md.roles[r].model : null;  // back to its own provider: its own model again
      if (saved) i.value = saved;
      else if (!list.includes(i.value)) i.value = list[0] || "";
      i.placeholder = list.length ? "model name" : "type the model name";
    }));
    $$("[data-save]", this.el).forEach((b) => (b.onclick = async () => {
      const r = b.dataset.save, x = row(r), model = x.m.value.trim();
      if (!model) { formSay(x.out, "Pick or type a model name first.", false); return x.m.focus(); }
      busy(b, true); formSay(x.out, "Saving…");
      try {
        const res = await post("/api/models/role", { role: r, provider: x.p.value, model });
        if (res.roles) md.roles = res.roles;  // switching provider back and the suggestions follow what's saved now
        formSay(x.out, res.warning || `✓ Saved. ${x.label} uses ${model}.`, res.warning ? "warn" : true);
        if (!res.warning) toast(`Saved: ${x.label} uses ${model}`);
      } catch (e) { formSay(x.out, e.message, false); }
      busy(b, false);
    }));
    $$("[data-rm]", this.el).forEach((i) => enterSends(i, () => $(`[data-save="${i.dataset.rm}"]`, this.el).click()));  // Enter saves, like Save
    $$("[data-test]", this.el).forEach((b) => (b.onclick = async () => {
      const r = b.dataset.test, x = row(r);
      busy(b, true); formSay(x.out, "Testing…");
      try {
        const t = await post("/api/models/test", { provider: x.p.value, model: x.m.value.trim() });
        formSay(x.out, t.ok ? `✓ Works. Replied “${t.reply}” in ${t.seconds} s.` : t.seconds != null ? `It answered, but not with OK: “${t.reply}”` : t.reply, !!t.ok);
      } catch (e) { formSay(x.out, e.message, false); }
      busy(b, false);
    }));
    this.bindPicker(ch);
    this.bindLive();
    this.bindStart();
  },
  bindStart() {
    $$("[data-ostart]", this.el).forEach((b) => (b.onclick = async () => {
      busy(b, true); b.textContent = "Starting…";
      const r = await post("/api/models/local/start").catch(() => ({}));
      if (r.running) { toast("Ollama is running"); return this.refresh(); }
      b.textContent = "Start Ollama"; busy(b, false);
      toast("Ollama didn’t start. Open the Ollama app once, then try again.");
    }));
  },
  pullCard(c) {
    const p = this.loc.pulls[c.name], big = ["too big", "not enough disk"].includes(c.fit);
    const pct = p && p.total ? Math.round(p.completed / p.total * 100) : null, failed = p && String(p.status).startsWith("failed");
    return `<div class="card" style="padding:12px 16px" data-pc="${esc(c.name)}"><div class="row"><span class="grow"><span class="row wrap"><b class="mono">${esc(c.name)}</b><span class="small muted">${c.gb} GB</span>${c.badge ? `<span class="badge good">${esc(c.badge)}</span>` : ""}<span class="badge ${big ? "hot" : c.fit === "fits well" ? "good" : ""}">${esc(c.fit)}</span></span><span class="small muted">${esc(c.about)}</span></span>
      ${c.installed ? `<span class="small good">● installed</span>` : `<button class="btn s" data-pull="${esc(c.name)}" ${!this.loc.ollama.running || big ? "disabled" : ""}>Download</button>`}</div>
      ${p && !c.installed ? `<div class="small mono ${failed ? "bad" : "muted"}" role="status">${esc(p.status || "")}${pct !== null && !failed ? ` · ${pct}%` : ""}</div>` : ""}</div>`;
  },
  local(loc) {
    this.loc = loc; loc.pulls = loc.pulls || {};
    const hw = loc.hardware, o = loc.ollama;
    const ostate = o.running ? `<span>Ollama is running <span class="okdot">●</span></span>`
      : o.installed ? `<span class="row" style="gap:8px"><span>Ollama is installed, not running</span><button class="btn s" data-ostart>Start Ollama</button></span>`
      : `<a href="https://ollama.com/download" target="_blank" rel="noopener">Install Ollama from ollama.com ↗</a>`;
    this.el.innerHTML = `${mobileBar("Local model")}<div class="page"><div class="row small"><a href="#/models" class="muted">Models</a><span class="muted">/</span><b>Add a local model</b></div>
      <div><h1>Add a local model</h1><p class="lede">Runs on this computer. Free, private, and it works offline.</p></div>
      <div class="card panel hw">${icon("monitor", 18)}<span><b>${esc(hw.cpu || "This computer")}</b> · ${hw.memory_gb || "?"} GB memory · ${hw.disk_free_gb || "?"} GB free</span><span class="grow"></span>${ostate}</div>
      <div class="row lmwrap"><section class="col lmlist"><b>What fits, next to your running bots</b>${loc.catalog.map((c) => this.pullCard(c)).join("")}</section>
      <aside class="col lmside"><form class="card" id="cbf" novalidate><b>Your own server</b><span class="small muted">LM Studio, llama.cpp, vLLM or anything with an OpenAI-compatible address.</span>
        <div class="row"><label class="vh" for="cb">Server address</label><input class="f mono" id="cb" value="${esc(loc.custom.base)}" placeholder="http://127.0.0.1:1234/v1" autocomplete="off" spellcheck="false"><button class="btn s" id="cbs">Connect</button></div>
        <span class="small ${loc.custom.reachable ? "good" : "muted"}" id="cbmsg" role="status">${loc.custom.reachable ? "● reachable" : "not reachable yet"}</span></form>
      <div class="card small"><b>Tip</b><span>Use a local model for chat and a cloud model for learning new sites, in Models.</span></div></aside></div></div>`;
    this.el.onclick = async (e) => {  // on the page, not the button: a download's card is redrawn as it goes
      const b = e.target.closest("[data-pull]"); if (!b || b.disabled) return;
      const c = this.loc.catalog.find((x) => x.name === b.dataset.pull);
      if (!(await confirmBox(`Download ${c.name} (${c.gb} GB) from ollama.com?`, "Download"))) return;
      try { await post("/api/models/pull", { name: c.name }); toast(`Downloading ${c.name}…`); } catch (err) { toast(err.message); }
    };
    $("#cbf").onsubmit = async (e) => {
      e.preventDefault();
      const b = $("#cbs"), i = $("#cb");
      busy(b, true); formSay("#cbmsg", "Checking the server…");
      try {
        const r = await post("/api/models/custom", { base: i.value });
        i.value = r.base; loc.custom = { base: r.base, reachable: r.reachable };
        formSay("#cbmsg", r.reachable ? `Saved ${r.base} · reachable ✓` : `Saved ${r.base} · not reachable yet. Is the server running?`, r.reachable ? true : "warn");
      } catch (err) { formSay("#cbmsg", err.message, false); }
      busy(b, false);
    };
    this.bindStart();
  },
  pulled(m) {  // a download's progress redraws only its own card
    const c = this.loc && this.loc.catalog.find((x) => x.name === m.name), card = c && $(`[data-pc="${CSS.escape(m.name)}"]`, this.el);
    if (!card) return;
    this.loc.pulls[m.name] = m;
    if (m.status === "success") { c.installed = true; toast(`${m.name} is ready. Pick it in Models.`); }
    card.outerHTML = this.pullCard(c);
  },
};

// ================================================================ API keys
const LIMIT_URL = { anthropic: "https://console.anthropic.com/settings/limits", openai: "https://platform.openai.com/settings/organization/limits",
  gemini: "https://console.cloud.google.com/billing/budgets", openrouter: "https://openrouter.ai/settings/credits" };
const spentLine = (k) => `Spent $${(+k.spent || 0).toFixed(2)}${k.limit != null ? ` of $${(+k.limit).toFixed(2)}` : ""} this month.${k.limit != null ? " Bots stop using OpenRouter at the limit." : " No limit."}`;
VIEWS.keys = {
  live: false,
  async show(el, _, qs) { this.el = el; this.sel = qs.get("p") || this.sel || "anthropic"; this.msg = null; await this.refresh(); },
  async refresh() { const d = await get("/api/keys"); redraw(this.el, () => this.render(d)); },
  render({ keys, backend }) {
    const cur = keys.find((k) => k.provider === this.sel) || keys[0], P = cur.provider, L = esc(cur.label), what = P === "telegram" ? "token" : "key";
    const yours = P === "custom" ? "your own server’s" : `your ${cur.label}`;  // "your own server’s key", never "your Your own server key"
    const where = { keychain: "this Mac’s Keychain", file: "a private file only you can read" }[backend] || "this computer";
    const src = (k) => (k.source ? `<span class="small ${k.error ? "warn" : "good"}">● ${esc(KEY_SOURCE[k.source] || k.source)}${k.error ? ` · ${keyErr(k.error)}` : ""}</span>` : `<span class="small muted">not set</span>`);
    const step1 = CLOUD.includes(P) ? `Make a key at <a href="${KEY_URL[P]}" target="_blank" rel="noopener">${esc(KEY_URL[P].replace("https://", ""))} ↗</a>.`
      : P === "telegram" ? `In Telegram, open <a href="https://t.me/BotFather" target="_blank" rel="noopener">@BotFather ↗</a>, send /newbot and copy the token it sends you.`
      : "Only if your server needs a key. You find it in your server’s settings.";
    const limit = P === "openrouter" ? `<form class="row" id="limf" style="align-items:flex-start" novalidate><span class="mono small muted">3</span><div class="col grow"><label for="lim" class="small">Monthly limit in dollars (optional)</label>
        <div class="row wrap"><input class="f" id="lim" type="number" min="0" step="any" inputmode="decimal" style="width:140px" value="${cur.limit ?? ""}" placeholder="no limit"><button class="btn s" id="limsave">Save limit</button></div>
        <span class="small muted" id="lspent">${spentLine(cur)}</span><span class="small" id="lstat" role="status"></span></div></form>`
      : CLOUD.includes(P) ? `<div class="row small"><span class="mono muted">3</span><span>Set a spending limit in <a href="${LIMIT_URL[P] || new URL(KEY_URL[P]).origin}" target="_blank" rel="noopener">${L}’s console ↗</a>. Inky can’t see what ${L} charges.</span></div>` : "";
    const msg = this.msg && this.msg.P === this.sel ? this.msg : {};
    this.el.innerHTML = `${mobileBar("API keys")}<div class="page"><div class="row small"><a href="#/models" class="muted">Models</a><span class="muted">/</span><b>API keys</b></div>
      <div><h1>API keys</h1><p class="lede">Paste a key once. It stays in ${where} and only goes to that provider. There is no Inky server.</p></div>
      <div class="row kwrap"><nav class="card panel klist" aria-label="Providers">${keys.map((k) => `<a href="#/keys?p=${k.provider}" data-kp="${k.provider}" class="navlink ${k.provider === P ? "on" : ""}" ${k.provider === P ? 'aria-current="page"' : ""}>${providerLogo(k.provider)}<span class="grow col" style="gap:1px">${esc(k.label)}${src(k)}</span></a>`).join("")}</nav>
      <section class="card grow kform" id="kform"><h2 style="font-size:20px">${cur.source ? "Replace" : "Add"} ${esc(yours)} ${what}</h2>
        ${cur.error && !msg.text ? `<div class="small warn">${[401, 403].includes(+cur.error) ? `${L} refused this key last time (${cur.error}). Paste a new one.` : `${L} answered with an error last time (${cur.error}).`}</div>` : ""}
        <div class="row small"><span class="mono muted">1</span><span>${step1}</span></div>
        <form class="row" id="kf" style="align-items:flex-start" novalidate><span class="mono small muted">2</span><div class="col grow"><label for="key" class="small">Paste it here</label><div class="row pasterow"><input class="f" id="key" type="password" autocomplete="off" spellcheck="false" placeholder="${cur.source ? `A ${what} is saved. Paste a new one to replace it.` : `Paste the ${what}`}"><button type="button" class="btn s" id="paste">Paste</button></div>
          <span class="small ${msg.ok === true ? "good" : msg.ok === false ? "bad" : msg.ok === "warn" ? "warn" : "muted"}" id="kstat" role="status">${esc(msg.text || "")}${msg.link ? ` <a href="#/connectors">Open Connectors</a>` : ""}</span></div></form>
        ${limit}
        <div class="between" style="border-top:1px solid var(--line);padding-top:14px"><span class="small muted row">${icon("lock", 15)}Never shown again. To change it, paste a new one.</span><span class="row">${cur.source === "keychain" || cur.source === "file" ? `<button class="btn hot" id="rm">Remove ${what}</button>` : ""}<button class="btn p" id="save" form="kf">Save ${what}</button></span></div></section></div></div>`;
    $$("[data-kp]", this.el).forEach((a) => (a.onclick = () => (this.jump = true)));
    $("#paste").onclick = async () => {
      try { $("#key").value = await navigator.clipboard.readText(); $("#key").focus(); }
      catch (e) { formSay("#kstat", `Your browser didn’t allow reading the clipboard. Click the field and press ${MAC ? "⌘V" : "Ctrl+V"}.`); }
    };
    $("#kf").onsubmit = async (e) => {
      e.preventDefault();
      const b = $("#save"), say = (text, ok, link) => { this.msg = { text, ok, link, P }; if (this.sel === P) formSay("#kstat", text, ok); };
      busy(b, true); say("Checking…");
      try {
        await post("/api/keys", { provider: P, key: $("#key").value.trim() });  // the engine checks it (an empty one, a Telegram token)
        $("#key").value = "";
        if (CLOUD.includes(P)) {  // find a model this key really has and check it answers
          say("Saved. Checking which models it has…");
          const r = await post("/api/models/connect", { provider: P });
          say(r.ok ? `✓ Works. Your bots now use ${r.model}.` : r.reply, !!r.ok);
        } else if (P === "telegram") {
          await loadState();
          const bot = (S.settings.telegram || {}).bot;
          say(`✓ Saved. Now send /start to ${bot ? "@" + bot : "your bot"} in Telegram, then press Test in Connectors.`, true, true);
        } else say(`✓ Saved ${yours} key.`, true);
        await this.refresh();
        if (this.sel === P && $("#key")) $("#key").focus();
      } catch (err) { say(err.message, false); busy(b, false); if ($("#key")) $("#key").focus(); }
    };
    if ($("#limf")) $("#limf").onsubmit = async (e) => {
      e.preventDefault();
      const i = $("#lim"), b = $("#limsave"), raw = i.value.trim();
      if (i.validity.badInput) return formSay("#lstat", "Type a number of dollars, like 5, or leave it empty for no limit.", false);
      busy(b, true);
      try {
        await post("/api/keys", { provider: P, limit: raw === "" ? null : +raw });
        cur.limit = raw === "" ? null : +raw;
        $("#lspent").textContent = spentLine(cur);
        formSay("#lstat", raw === "" ? "✓ Saved. No limit now." : `✓ Saved. The limit is $${(+raw).toFixed(2)} a month.`, true);
      } catch (err) { formSay("#lstat", err.message, false); }
      busy(b, false);
    };
    if ($("#rm")) $("#rm").onclick = async () => {
      if (!(await confirmBox(`Remove ${yours} ${what}?`, "Remove", true))) return;
      try { await del(`/api/keys/${P}`); toast(`Removed ${yours} ${what}${P === "telegram" ? ". Telegram alerts are off now." : ""}`); this.msg = null; if (P === "telegram") await loadState(); await this.refresh(); if ($("#key")) $("#key").focus(); }
      catch (err) { formSay("#kstat", err.message, false); }
    };
    if (this.jump) {  // on a phone or a narrow window the form is below the list: choosing a provider goes to it
      this.jump = false;
      if (matchMedia("(max-width:1100px)").matches) requestAnimationFrame(() => $("#kform", this.el).scrollIntoView({ block: "start", behavior: calmMotion() ? "auto" : "smooth" }));
    }
  },
};

// ================================================================ connectors
let tgPoll = null;
function waitForTelegram(bot, say, retryWord = "press Test") {  // after the token: poll until you send /start, then say hello. say(text, good); false after 2 min
  clearInterval(tgPoll);
  say(`Now open Telegram and send /start to @${bot}. Waiting…`);
  const t0 = Date.now();
  return new Promise((done) => {
    tgPoll = setInterval(async () => {
      if (Date.now() - t0 > 120e3) { clearInterval(tgPoll); say(`Didn’t hear from you yet. Send /start to @${bot}, then ${retryWord}.`, false); return done(false); }
      const { chat_id } = await post("/api/connectors/telegram/find-chat");
      if (!chat_id) return;
      clearInterval(tgPoll);
      const t = await post("/api/connectors/telegram/test");
      say(t.ok ? "✓ Found you and sent a hello. Alerts go to Telegram now." : t.text, t.ok);
      if (t.ok) { SOUND.play("chime"); confetti(); }
      done(t.ok);
    }, 2000);
  });
}
const MCP_PRESETS = [["github", "GitHub", "github", "npx -y @modelcontextprotocol/server-github", "GITHUB_PERSONAL_ACCESS_TOKEN="],
  ["filesystem", "Files", "mcp", "npx -y @modelcontextprotocol/server-filesystem ~/Documents", ""], ["fetch", "Fetch", "mcp", "uvx mcp-server-fetch", ""]];
// ponytail: how the built-in agents start by default; the engine could send `overridden` instead of the UI knowing this
const PRESET_CMD = { "claude-code": /^claude mcp serve$/, codex: /(inky\.codex_mcp|codex-mcp)$/ };
const TRY_EXAMPLE = { "claude-code.Read": { file_path: "/etc/hosts" } };
const withCode = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>");  // `codex exec` in a description reads as code
const pretty = (t) => { try { return JSON.stringify(JSON.parse(t), null, 2); } catch (e) { return t; } };
VIEWS.connectors = {
  live: false,
  async show(el) {
    this.el = el; this.open = new Set(); this.params = {};
    el.innerHTML = `${mobileBar("Connectors")}<div class="page"><div><h1>Connectors</h1><p class="lede">All optional. Each one shows whether it works, with a real test and a fix when it doesn’t. Handing work to any of them asks you first.</p></div>
      <div class="row" role="status"><span class="typing"><i></i><i></i><i></i></span><span class="muted">Checking your tools…</span></div></div>`;
    await this.refresh();
  },
  leave() { clearInterval(tgPoll); },
  async refresh() { const d = await get("/api/connectors"); redraw(this.el, () => this.render(d)); },
  res(n, t, ok) { formSay($(`[data-res="${n}"]`, this.el), t, ok); },
  state(c) {
    if (c.kind === "builtin") return c.connected ? ["ok", "set up"] : c.name === "telegram" && /\/start/.test(c.detail) ? ["warn", "almost there"] : ["off", "not set up"];
    if (!c.installed) return ["off", "not installed"];
    if (c.connected) return ["ok", `connected · ${c.tools.length} tools`];
    if (c.signed_in === false) return ["warn", "signed out"];
    if (c.error) return ["warn", "didn’t connect"];
    return ["", "ready to connect"];
  },
  card(c) {
    const [cls, txt] = this.state(c), B = c.kind === "builtin", setUp = B && (c.connected || /\/start/.test(c.detail));
    const btns = B
      ? `${setUp ? `<button class="btn s" data-test="${c.name}">Test</button>` : ""}<button class="btn s ${setUp ? "" : "p"}" data-edit="${c.name}" aria-expanded="${this.open.has(c.name)}">${setUp ? "Change" : "Set up"}</button>${setUp ? `<button class="btn s hot" data-forget="${c.name}">Disconnect</button>` : ""}`
      : !c.installed ? (c.fix_url ? `<a class="btn s" href="${esc(c.fix_url)}" target="_blank" rel="noopener">How to install ↗</a>` : "")
      : c.connected ? `<button class="btn s" data-test="${c.name}">Test</button><button class="btn s" data-off="${c.name}">Disconnect</button>` : `<button class="btn s p" data-on="${c.name}">Connect</button>`;
    const extra = c.kind === "mcp" && !c.preset ? `<button class="btn s hot" data-rm="${c.name}">Remove</button>`
      : c.overridden || (c.overridden === undefined && PRESET_CMD[c.name] && !PRESET_CMD[c.name].test((c.command || []).join(" "))) ? `<button class="btn s" data-reset="${c.name}">Reset</button>` : "";
    const detail = ["Not set up yet.", "Connected."].includes(c.detail) ? "" : c.detail;  // the badge already says so
    const saved = B ? (c.fields || []).filter((f) => !f.secret && (c.values || {})[f.key]).map((f) => `${esc(f.label)}: <span class="mono">${esc(c.values[f.key])}</span>`).join(" · ") : "";
    return `<div class="card conn" data-c="${c.name}"><div class="row crow">${logo(c.logo, 44)}<div class="grow"><div class="row wrap" style="gap:8px"><b style="font-size:16px">${esc(c.label)}</b><span class="cstate ${cls}">${esc(txt)}</span></div><div class="small muted">${withCode(c.about || "")}</div></div>
      <span class="row cbtns">${btns}${extra}</span></div>
      ${detail ? `<div class="small ${cls === "warn" || cls === "off" ? "" : "muted"}">${withCode(detail)}${c.fix ? ` <b>${withCode(c.fix)}</b>` : ""}</div>` : ""}
      ${saved ? `<div class="small muted">${saved}</div>` : ""}
      ${B ? this.form(c, setUp) : ""}
      ${c.tools.length && c.connected ? `<div class="row wrap" style="gap:6px">${c.tools.slice(0, 10).map((t) => `<span class="chip mono">${esc(t)}</span>`).join("")}${c.tools.length > 10 ? `<span class="chip">+${c.tools.length - 10} more</span>` : ""}</div>` : ""}
      ${c.kind === "mcp" && c.connected ? this.tryTool(c) : ""}
      <div class="small" data-res="${c.name}" role="status"></div></div>`;
  },
  form(c, setUp) {  // always in the page, hidden until you open it, so another form's typing is never lost
    const help = { telegram: ["https://t.me/BotFather", "Open @BotFather ↗"], apify: ["https://console.apify.com/settings/integrations", "Get your token ↗"] }[c.name];
    return `<form class="keyfield ${this.open.has(c.name) ? "" : "hidden"}" data-form="${c.name}" novalidate>${c.fields.map((f) => `<label class="small" for="f-${c.name}-${f.key}">${esc(f.label)}</label><input class="f ${f.secret ? "" : "mono"}" id="f-${c.name}-${f.key}" data-field="${f.key}" ${f.secret ? `type="password" placeholder="${setUp ? "Saved. Paste a new one to replace it." : esc(f.placeholder)}"` : `value="${esc((c.values || {})[f.key] || "")}" placeholder="${esc(f.placeholder)}"`} autocomplete="off" spellcheck="false">`).join("")}
      <div class="row wrap"><button class="btn p s" data-setup="${c.name}">Save & check</button><button type="button" class="btn s" data-cancel="${c.name}">Cancel</button>${help ? `<a class="small" href="${help[0]}" target="_blank" rel="noopener">${help[1]}</a>` : ""}</div></form>`;
  },
  tryTool(c) {
    const n = c.name, def = n === "claude-code" && c.tools.includes("Read") ? "Read" : "";  // never a default that spends anything (Codex)
    return `<details data-keep="try-${n}"><summary class="small">Try a tool</summary><form class="trytool" data-tryf="${n}" novalidate>
      <div class="col" style="gap:4px"><label class="small" for="tool-${n}">Tool</label><select class="f" id="tool-${n}" data-tool="${n}">${def ? "" : `<option value="" selected disabled>Pick a tool…</option>`}${c.tools.map((t) => `<option ${t === def ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div>
      <div class="col" style="gap:4px"><label class="small" for="args-${n}">Arguments (JSON)</label><textarea class="f mono" id="args-${n}" rows="${def ? 3 : 1}" spellcheck="false">${esc(JSON.stringify(TRY_EXAMPLE[`${n}.${def}`] || {}, null, 2))}</textarea></div>
      <div><button class="btn s" data-try="${n}">Run it</button></div></form><pre class="code tryout hidden" data-out="${n}" role="status"></pre></details>`;
  },
  toolParams(n) {  // each tool's parameters, for the arguments skeleton (Connect on a connected server only lists its tools)
    const blank = { string: "", number: 0, integer: 0, boolean: false, array: [], object: {} };  // required fields only, typed
    return (this.params[n] = this.params[n] || post(`/api/mcp/${n}/connect`).then((r) => Object.fromEntries(r.tools.map((t) => [t.name,
      Object.fromEntries((t.required && t.required.length ? t.required : t.params).map((p) => [p, blank[(t.types || {})[p]] ?? ""]))])))
      .catch(() => { delete this.params[n]; return {}; }));
  },
  render({ connectors: all, inky }) {
    this.inky = inky;
    const agents = all.filter((c) => c.kind === "mcp" && c.preset), services = all.filter((c) => c.kind === "builtin"), others = all.filter((c) => c.kind === "mcp" && !c.preset);
    const label = (n) => (all.find((c) => c.name === n) || {}).label || n;
    this.el.innerHTML = `${mobileBar("Connectors")}<div class="page"><div><h1>Connectors</h1><p class="lede">All optional. Each one shows whether it works, with a real test and a fix when it doesn’t. Handing work to any of them asks you first.</p></div>
      <section class="col"><h2>Agents</h2>${agents.map((c) => this.card(c)).join("")}</section>
      <section class="col"><h2>Services</h2>${services.map((c) => this.card(c)).join("")}</section>
      <section class="col"><h2>Other MCP servers</h2>${others.map((c) => this.card(c)).join("")}
        <form class="card" id="maddf" novalidate><b>Add an MCP server</b><div class="row wrap" style="gap:8px">${MCP_PRESETS.map(([n, l, lg]) => `<button type="button" class="chip" data-preset="${n}">${logo(lg, 18)}${esc(l)}</button>`).join("")}</div>
        <div class="mcpgrid"><div class="col" style="gap:4px"><label class="small" for="mn">Name</label><input class="f" id="mn" placeholder="e.g. github" autocomplete="off" spellcheck="false"></div>
          <div class="col" style="gap:4px"><label class="small" for="mc">Command that starts it</label><input class="f mono" id="mc" placeholder="npx -y @modelcontextprotocol/server-github" autocomplete="off" spellcheck="false"></div></div>
        <div class="col" style="gap:4px"><label class="small" for="me">Settings it needs (optional, one per line)</label><textarea class="f mono" id="me" rows="2" placeholder="GITHUB_PERSONAL_ACCESS_TOKEN=…" autocomplete="off" spellcheck="false"></textarea></div>
        <div><button class="btn s" id="madd">Add and connect</button></div><span class="small" id="mres" role="status"></span></form></section>
      <section class="card"><b>Let Claude Code and Codex use your bots</b><span class="small muted">Inky is an MCP server too. They can list your bots, message them, run their skills and read what they found. Approving Needs-you items stays in this app.</span>
        <div class="row wrap">${agents.map((c) => `<button class="btn" data-addinky="${c.name}" ${c.installed ? "" : "disabled"}>${logo(c.logo, 20)}Add Inky to ${esc(c.label)}</button>`).join("")}</div><span class="small" id="addres" role="status"></span>
        <details data-keep="diy"><summary class="small">Or do it yourself</summary><div class="between"><label class="l">Claude Code</label><button type="button" class="btn s" data-copy="claude_cli">Copy</button></div><pre class="code">${esc(inky.claude_cli)}</pre>
          <div class="between"><label class="l">Codex (~/.codex/config.toml)</label><button type="button" class="btn s" data-copy="codex_toml">Copy</button></div><pre class="code">${esc(inky.codex_toml)}</pre></details></section></div>`;
    const on = (sel, fn) => $$(sel, this.el).forEach((x) => (x.onclick = () => fn(x)));
    on("[data-on]", async (x) => {
      const n = x.dataset.on; busy(x, true); x.textContent = "Connecting…";
      try { await post(`/api/mcp/${n}/connect`); await this.refresh(); this.res(n, "✓ Connected.", true); SOUND.play("chime"); const t = $(`[data-test="${n}"]`, this.el); if (t) t.focus(); }
      catch (e) { x.textContent = "Connect"; busy(x, false); this.res(n, e.message, false); }
    });
    on("[data-off]", async (x) => {
      const n = x.dataset.off; busy(x, true);
      try { await post(`/api/mcp/${n}/disconnect`); await this.refresh(); const b = $(`[data-on="${n}"]`, this.el); if (b) b.focus(); } catch (e) { busy(x, false); this.res(n, e.message, false); }
    });
    on("[data-rm]", async (x) => {
      const n = x.dataset.rm;
      if (!(await confirmBox(`Remove ${label(n)}?`, "Remove", true))) return;
      try { await del(`/api/mcp/${n}`); toast(`Removed ${label(n)}`); await this.refresh(); $("#mn", this.el).focus(); } catch (e) { this.res(n, e.message, false); }
    });
    on("[data-reset]", async (x) => {
      const n = x.dataset.reset;
      if (!(await confirmBox(`Reset ${label(n)} to how it came with Inky?`, "Reset", true))) return;
      try { await del(`/api/mcp/${n}`); await this.refresh(); this.res(n, `${label(n)} is back to how it came.`); const f = $(`[data-on="${n}"],[data-test="${n}"]`, this.el); if (f) f.focus(); } catch (e) { this.res(n, e.message, false); }
    });
    on("[data-test]", async (x) => {
      const n = x.dataset.test; busy(x, true); this.res(n, "Testing…");
      try { const r = await post(`/api/connectors/${n}/test`); this.res(n, (r.ok ? "✓ " : "") + r.text, r.ok); if (r.ok) SOUND.play("chime"); } catch (e) { this.res(n, e.message, false); }
      busy(x, false);
    });
    on("[data-edit]", (x) => {  // opens or closes in place: what you typed stays
      const n = x.dataset.edit, f = $(`[data-form="${n}"]`, this.el), open = f.classList.contains("hidden");
      f.classList.toggle("hidden", !open); x.setAttribute("aria-expanded", open);
      if (open) { this.open.add(n); $("input", f).focus(); } else this.open.delete(n);
    });
    on("[data-cancel]", (x) => {
      const n = x.dataset.cancel, f = $(`[data-form="${n}"]`, this.el);
      f.reset(); f.classList.add("hidden"); this.open.delete(n); this.res(n, "");
      const e = $(`[data-edit="${n}"]`, this.el); e.setAttribute("aria-expanded", false); e.focus();
    });
    $$("[data-form]", this.el).forEach((f) => (f.onsubmit = async (ev) => {
      ev.preventDefault();
      const n = f.dataset.form, b = $("[data-setup]", f), values = Object.fromEntries($$("[data-field]", f).map((i) => [i.dataset.field, i.value.trim()]));
      busy(b, true); this.res(n, "Checking…");
      let r; try { r = await post(`/api/connectors/${n}/setup`, { values }); } catch (e) { r = { ok: false, text: e.message }; }
      if (!r.ok) { busy(b, false); return this.res(n, r.text, false); }  // the engine says what's missing or wrong
      $$("[data-field]", f).forEach((i) => (i.value = "")); this.open.delete(n);
      await this.refresh(); this.res(n, "✓ " + r.text, true); SOUND.play("chime");
      const ft = $(`[data-test="${n}"]`, this.el); if (ft) ft.focus();  // focus stays where you were working
      if (n === "telegram") this.waitForStart(r.bot);
    }));
    on("[data-forget]", async (x) => {
      const n = x.dataset.forget;
      const what = { telegram: "Its token is removed from this computer and alerts stop.", n8n: "Its address and API key are removed from this computer.", apify: "Its token is removed from this computer." }[n];
      if (!(await confirmBox(`Disconnect ${label(n)}? ${what}`, "Disconnect", true))) return;
      try { await del(`/api/connectors/${n}`); if (n === "telegram") clearInterval(tgPoll); this.open.delete(n); await this.refresh(); this.res(n, `Disconnected ${label(n)}.`); const fe = $(`[data-edit="${n}"]`, this.el); if (fe) fe.focus(); }
      catch (e) { this.res(n, e.message, false); }
    });
    $$("details[data-keep^='try-']", this.el).forEach((d) => (d.ontoggle = () => { if (d.open) this.toolParams(d.dataset.keep.slice(4)); }));
    $$("[data-tool]", this.el).forEach((s) => (s.onchange = async () => {  // the arguments follow the tool
      const n = s.dataset.tool, tool = s.value, ps = (await this.toolParams(n))[tool] || {}, a = $(`#args-${n}`, this.el);
      if (a && s.value === tool) { a.value = JSON.stringify(TRY_EXAMPLE[`${n}.${tool}`] || ps, null, 2); a.rows = Math.min(8, a.value.split("\n").length); }
    }));
    $$("[data-tryf]", this.el).forEach((f) => (f.onsubmit = async (ev) => {
      ev.preventDefault();
      const n = f.dataset.tryf, tool = $(`#tool-${n}`, this.el).value, out = $(`[data-out="${n}"]`, this.el), b = $(`[data-try="${n}"]`, this.el);
      const show = (t, bad) => { out.classList.remove("hidden"); out.classList.toggle("bad", !!bad); out.textContent = t; };
      if (!tool) return show("Pick a tool first.", true);
      let args;
      try { args = JSON.parse($(`#args-${n}`, this.el).value.trim() || "{}"); if (!args || typeof args !== "object" || Array.isArray(args)) throw new Error("not an object"); }
      catch (e) { return show("Arguments must be JSON, like {\"name\": \"value\"}.", true); }
      const SAFE = /^(Read|Glob|Grep|LS|WebSearch|WebFetch|TaskOutput|ListMcpResources|ReadMcpResource)$/;  // look, never change
      const no = () => { out.textContent = ""; out.classList.add("hidden"); };  // cancelled: no output from the tool before it
      if (n === "codex" && !(await confirmBox(`Run ${tool} in Codex now? It uses your ChatGPT plan’s Codex quota.`, "Run it"))) return no();
      if (n !== "codex" && !SAFE.test(tool) && !(await confirmBox(`Run ${tool} in ${label(n)} now? It can change files or run commands on this computer.`, "Run it", true))) return no();
      busy(b, true); show("Running…");
      try { const r = await post(`/api/mcp/${n}/call`, { tool, args }); show(r.error && !/^error\b/i.test(r.text || "") ? `Error: ${r.text || "the tool didn’t say why."}` : pretty(r.text || ""), r.error); }  // never "Error: Error: …"
      catch (e) { show(e.message, true); }
      busy(b, false);
    }));
    on("[data-preset]", (x) => { const p = MCP_PRESETS.find((m) => m[0] === x.dataset.preset); $("#mn").value = p[0]; $("#mc").value = p[3]; $("#me").value = p[4]; (p[4] ? $("#me") : $("#mc")).focus(); });
    $("#maddf").onsubmit = async (ev) => {
      ev.preventDefault();
      const b = $("#madd"), given = $("#mn").value.trim(), command = $("#mc").value.trim();
      const env = Object.fromEntries($("#me").value.split(/\n|\s+(?=[A-Z_][A-Z0-9_]*=)/).map((l) => l.trim()).filter((l) => l.includes("=")).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1)]));
      busy(b, true); formSay("#mres", "Adding…");
      try {
        const { name } = await post("/api/mcp", { name: given, command, label: given, env });  // the engine checks the name and command, and says why
        formSay("#mres", "Connecting…");
        const r = await post(`/api/connectors/${name}/test`);
        $("#mn").value = $("#mc").value = $("#me").value = "";
        await this.refresh();
        if (r.ok) this.res(name, "✓ " + r.text, true);  // a failed try shows on the card as “Last try: …”
        formSay("#mres", r.ok ? `✓ Added ${given}.` : `Added ${given}, but it didn’t connect yet. Its card says why.`, r.ok ? true : "warn");
        const card = $(`[data-c="${CSS.escape(name)}"]`, this.el); if (card) card.scrollIntoView({ block: "nearest" });
      } catch (e) { formSay("#mres", e.message, false); busy(b, false); if (e.status === 409) $("#mn").select(); }  // a name that's taken: fix it right there
    };
    on("[data-addinky]", async (x) => {
      const n = x.dataset.addinky, cc = n === "claude-code";
      const ok = await confirmBox(cc ? "Add Inky to Claude Code? This runs:" : "Add Inky to Codex? This adds to ~/.codex/config.toml:", "Add it", false, cc ? inky.claude_cli : inky.codex_toml);
      if (!ok) return;
      try { const r = await post(`/api/connectors/${n}/add-inky`); formSay("#addres", (r.ok ? "✓ " : "") + (r.text || "Done."), r.ok); } catch (e) { formSay("#addres", e.message, false); }
    });
    on("[data-copy]", async (x) => {
      try { await navigator.clipboard.writeText(inky[x.dataset.copy]); x.textContent = "Copied ✓"; setTimeout(() => (x.textContent = "Copy"), 2000); }
      catch (e) { toast(`Couldn’t copy. Select the text and press ${MAC ? "⌘C" : "Ctrl+C"}.`); }
    });
  },
  async waitForStart(bot) {
    const say = (t, ok) => this.res("telegram", t, ok);
    if (await waitForTelegram(bot, say)) { await this.refresh(); say("✓ Found you and sent a hello. Alerts go to Telegram now.", true); }
  },
};

// ================================================================ make it yours
const clip = (s, n) => {  // at most n characters, cut at a word, with …
  s = String(s || "").trim();
  if (s.length <= n) return s;
  const c = s.slice(0, n + 1), i = c.lastIndexOf(" ");
  return (i > n / 2 ? c.slice(0, i) : s.slice(0, n)).replace(/[\s,.;:!?–—-]+$/, "") + "…";
};
VIEWS.look = {
  live: false,
  leaveText() { return `Discard your changes to ${this.bot ? this.bot.name : "this bot"}?`; },
  async show(el, [id]) {
    this.el = el; this.leaving = false;
    const none = (text, link) => { el.innerHTML = `${mobileBar("Make it yours")}<div class="page"><div><h1>Make it yours</h1><p class="lede">${text}</p></div><div>${link}</div></div>`; };
    if (!S.bots.length) return none("Each bot gets its own look, voice and personality. Make your first bot, then come back here.", `<a class="btn p" href="#/new">${icon("plus", 16, 2.2)}Make a bot</a>`);
    const b = id !== undefined ? S.bots.find((x) => String(x.id) === id) : S.bots.find((x) => x.id === this.botId) || S.bots[0];
    if (!b) return none(`There’s no bot ${esc(id)}. It may have been deleted.`, `<a class="btn" href="#/look">Pick one of your bots</a>`);
    this.load(b);
    this.render();
  },
  load(b) { this.bot = b; this.botId = b.id; this.draft = { ...b.look, name: b.name }; this.persona = { ...(b.persona || {}) }; this.saved = this.snap(); },
  snap() { return JSON.stringify([this.draft, this.persona]); },
  dirty() { return this.snap() !== this.saved; },
  preview() {
    const d = this.draft, b = this.bot, frame = d.frame === "bot" ? d.color : "#E86F51";
    const sample = { cheerful: `Found one! It passes all your rules. Want me to draft a message?`, calm: `One new result passes your rules. Shall I draft a message?`, direct: `1 new match. Draft message? Yes or no.` }[d.tone || "cheerful"];
    return `<div class="row lphead">${critter(d.kind, d.color, d.acc, 96)}<div class="grow"><b class="lpname">${esc(d.name)}</b><div class="small muted">${esc(clip(b.summary || b.job, 60))}</div></div></div>
        <span class="small muted" style="font-weight:600">While it drives</span>
        <div class="ldrive"><div style="height:100%;border-radius:9px;background:#ECEAE5;box-shadow:inset 0 0 0 3px ${frame};padding:12px"><div style="height:100%;border-radius:8px;background:#fff;padding:14px;display:flex;flex-direction:column;gap:8px">
          <span style="width:55%;height:8px;border-radius:4px;background:#E8E6E1"></span><span style="width:35%;height:8px;border-radius:4px;background:#E8E6E1"></span>
          <div style="margin-top:auto;margin-bottom:14px;position:relative;align-self:flex-start">${d.labels ? `<span style="position:absolute;left:0;top:-30px;padding:3px 8px;border-radius:7px;background:#111110;color:#fff;font-size:11.5px;white-space:nowrap">4 · Click “Search”</span>` : ""}
          <span style="padding:8px 16px;border-radius:6px;background:#1F6F78;color:#fff;font-size:13px;font-weight:600;outline:2px solid ${frame};outline-offset:3px">Search</span>
          <svg width="22" height="22" viewBox="0 0 24 24" style="position:absolute;right:-13px;bottom:-14px" aria-hidden="true"><path d="M4 3 L20 11 L12.5 13 L9.5 20 Z" fill="${frame}" stroke="#fff" stroke-width="1.5"/></svg>
          ${d.cursor === "name" ? `<span style="position:absolute;left:calc(100% + 12px);top:26px;padding:3px 8px;border-radius:7px;background:color-mix(in srgb,${frame} 70%,#111110);color:#fff;font-size:11.5px;font-weight:600;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(d.name)}</span>` : d.cursor === "critter" ? `<span style="position:absolute;left:calc(100% + 10px);top:12px">${critter(d.kind, d.color, d.acc, 34)}</span>` : ""}</div></div></div></div>
        <div class="row" style="align-items:flex-start;margin-top:auto">${critter(d.kind, d.color, d.acc, 30)}<div class="card" style="padding:12px 14px;border-radius:16px 16px 16px 4px">${sample}</div></div><span class="mono small muted">voice: ${esc(d.voice || "soft")} · speed ${esc(d.speed || "normal")}</span>`;
  },
  render() {
    const d = this.draft, b = this.bot, p = this.persona;
    const on = (k, v) => String(d[k]) === String(v);
    const chips = (key, label, opts) => `<div class="col"><b class="small">${label}</b><div class="chips" role="group" aria-label="${label}">${opts.map(([v, t]) => `<button type="button" data-k="${key}" data-v="${v}" class="${on(key, v) ? "on" : ""}" aria-pressed="${on(key, v)}">${t}</button>`).join("")}</div></div>`;
    this.el.innerHTML = `${mobileBar("Make it yours")}<div class="page" style="max-width:none"><div class="lookwrap">
      <section class="card panel lookprev" id="lprev" aria-label="Preview">${this.preview()}</section>
      <section class="col lookctl"><div><h1>Make it yours</h1><p class="lede">Each bot gets its own look, voice and way of showing it’s driving. It shows in the app, on its computer and on your phone.</p></div>
        <div class="row wrap" role="group" aria-label="Bot">${S.bots.map((x) => `<button class="btn ${x.id === b.id ? "p" : ""}" data-bot="${x.id}" aria-pressed="${x.id === b.id}">${botCritter(x, 24)}${esc(x.name)}</button>`).join("")}</div>
        <div class="grid2" style="gap:28px"><div class="col" style="gap:18px">
          <div class="col"><b class="small">Animal</b><div class="row wrap" role="group" aria-label="Animal">${LOOKS.kinds.map((k) => `<button type="button" class="animal ${on("kind", k) ? "on" : ""}" data-k="kind" data-v="${k}" aria-pressed="${on("kind", k)}">${critter(k, d.color, "none", 44)}${cap(k)}</button>`).join("")}</div></div>
          <div class="col"><b class="small">Color</b><div class="row wrap" role="group" aria-label="Color">${LOOKS.colors.map(([c, n]) => `<button type="button" class="swatch ${on("color", c) ? "on" : ""}" style="background:${c}" data-k="color" data-v="${c}" aria-label="${n}" aria-pressed="${on("color", c)}"></button>`).join("")}</div></div>
          <div class="col"><b class="small">Accessory</b><div class="chips" role="group" aria-label="Accessory">${LOOKS.accs.map((a) => `<button type="button" data-k="acc" data-v="${a}" class="${on("acc", a) ? "on" : ""}" aria-pressed="${on("acc", a)}">${a === "none" ? "Nothing" : cap(a)}</button>`).join("")}</div>
            <div class="chips">${LOOKS.earned.map(([at, a]) => (b.unlocked || []).includes(a) ? `<button type="button" data-k="acc" data-v="${a}" class="${on("acc", a) ? "on" : ""}" aria-pressed="${on("acc", a)}">${cap(a === "party" ? "party hat" : a)}</button>` : `<button type="button" disabled title="Unlocks at ${at} runs">🔒 ${cap(a === "party" ? "party hat" : a)} · ${at} runs</button>`).join("")}</div></div>
          <div class="col"><label class="small" for="lname"><b>Name</b></label><input class="f" id="lname" maxlength="40" value="${esc(d.name)}"></div>
          ${chips("voice", "Voice on calls", [["soft", "Soft"], ["bright", "Bright"], ["off", "Off, text only"]])}</div>
        <div class="col" style="gap:18px">${chips("tone", "How it talks", [["cheerful", "Cheerful"], ["calm", "Calm"], ["direct", "Straight to the point"]])}
          ${chips("frame", "Screen frame", [["coral", "Coral, same for every bot"], ["bot", "This bot’s color"]])}
          ${chips("cursor", "Cursor", [["name", "Arrow with its name"], ["critter", "Its critter follows"], ["plain", "Just an arrow"]])}
          ${chips("labels", "Step labels", [[true, "Show each step"], [false, "Hide steps"]])}
          ${chips("speed", "Default speed", [["slow", "Slow"], ["normal", "Normal"], ["turbo", "Turbo"]])}
          <span class="small muted">A frame always shows while a bot uses a screen, and you can take over at any moment.</span></div></div>
        <div class="card" style="gap:14px"><div class="head"><b>Personality</b><span class="small muted">how it talks, never what it’s allowed to do</span></div>
          <div class="grid2" style="gap:18px"><div class="col">
            <label class="small" for="pc"><b>Chatty ↔ quiet</b></label><input type="range" id="pc" min="0" max="1" step="0.1" value="${1 - (p.chatty ?? 0.5)}">
            <label class="small" for="pp"><b>Playful ↔ serious</b></label><input type="range" id="pp" min="0" max="1" step="0.1" value="${1 - (p.playful ?? 0.5)}">
            <div class="col"><b class="small">Emoji</b><div class="chips" role="group" aria-label="Emoji"><button type="button" data-pe="1" class="${p.emoji ? "on" : ""}" aria-pressed="${!!p.emoji}">Sometimes</button><button type="button" data-pe="0" class="${p.emoji ? "" : "on"}" aria-pressed="${!p.emoji}">Never</button></div></div></div>
          <div class="col"><label class="small" for="pcat"><b>Catchphrase</b></label><input class="f" id="pcat" maxlength="80" value="${esc(p.catchphrase || "")}">
            <label class="small" for="pq"><b>Quirk</b></label><input class="f" id="pq" maxlength="120" value="${esc(p.quirk || "")}">
            <label class="small" for="pb"><b>In its own words</b></label><input class="f" id="pb" maxlength="160" placeholder="I hunt flats in Bari so you don’t have to." value="${esc(p.bio || "")}"></div></div></div>
        <div class="row wrap"><button class="btn p" id="lsave">Save</button><button class="btn" id="lreset">Reset</button><span class="mono small muted" id="lhint" role="status"></span></div></section></div></div>`;
    this.hint();
    $$("[data-k]", this.el).forEach((x) => (x.onclick = () => { const v = x.dataset.v; this.draft[x.dataset.k] = v === "true" ? true : v === "false" ? false : v; this.paint(); }));
    $$("[data-pe]", this.el).forEach((x) => (x.onclick = () => { this.persona.emoji = x.dataset.pe === "1"; this.paint(); }));
    $("#lname").oninput = (e) => { this.draft.name = e.target.value; this.paint(); };
    $("#pc").oninput = (e) => { this.persona.chatty = +(1 - e.target.value).toFixed(1); this.hint(); };
    $("#pp").oninput = (e) => { this.persona.playful = +(1 - e.target.value).toFixed(1); this.hint(); };
    for (const [id, k] of [["pcat", "catchphrase"], ["pq", "quirk"], ["pb", "bio"]]) $("#" + id).oninput = (e) => { this.persona[k] = e.target.value; this.hint(); };
    $$("button[data-bot]", this.el).forEach((x) => (x.onclick = async () => {
      if (+x.dataset.bot === this.bot.id) return;
      location.hash = `#/look/${x.dataset.bot}`;  // the router asks first if there are unsaved changes
    }));
    $("#lreset").onclick = () => { this.load(this.bot); this.render(); $("#lreset", this.el).focus(); };
    $("#lsave").onclick = async () => {
      const { name, ...look } = this.draft, btn = $("#lsave");
      if (!String(name || "").trim()) { toast("Give it a name first."); return $("#lname").focus(); }
      busy(btn, true);
      try {
        await patch(`/api/bots/${this.bot.id}`, { name: name.trim(), look, persona: this.persona });
        await loadState();
        const nb = S.bots.find((x) => x.id === this.bot.id);
        if (nb) this.load(nb);
        this.render(); $("#lsave", this.el).focus();
        toast("Saved", nb || this.bot);
      } catch (e) { toast(e.message); busy(btn, false); }
    };
  },
  paint() {  // the preview and the pressed buttons change in place, so the focus stays on what you pressed
    const d = this.draft;
    $("#lprev", this.el).innerHTML = this.preview();
    $$("[data-k]", this.el).forEach((x) => { const on = String(d[x.dataset.k]) === x.dataset.v; x.classList.toggle("on", on); x.setAttribute("aria-pressed", on); });
    $$("[data-pe]", this.el).forEach((x) => { const on = (x.dataset.pe === "1") === !!this.persona.emoji; x.classList.toggle("on", on); x.setAttribute("aria-pressed", on); });
    $$(".animal", this.el).forEach((x) => { x.firstElementChild.outerHTML = critter(x.dataset.v, d.color, "none", 44); });
    this.hint();
  },
  hint() { const h = $("#lhint", this.el); if (h) h.textContent = this.dirty() ? "not saved yet · press Save to keep it" : "click to try · nothing saves until you press Save"; },
};

// ================================================================ settings
VIEWS.settings = {
  live: false,
  async show(el) { this.el = el; await this.refresh(); },
  async refresh() {
    const s = await get("/api/settings");
    const tog = (k, on, label) => `<div class="between tgl"><span>${label}</span><button class="toggle ${on ? "on" : ""}" data-t="${k}" role="switch" aria-checked="${!!on}" aria-label="${label}"></button></div>`;
    const kb = (t, k) => `<div class="between" style="padding:6px 0;border-top:1px solid #F0EEE9"><span>${t}</span><span class="row" style="gap:4px">${k.split(" ").map((x) => `<kbd>${x === "mouse" ? `${icon("mouse", 14)}<span class="vh">mouse</span>` : x}</kbd>`).join("")}</span></div>`;
    const field = (id, label, value, extra = "") => `<div class="between fld"><label for="${id}">${label}</label><span class="row sfw"><span class="small good" data-saved="${id}" aria-live="polite"></span><input class="f sf" id="${id}" value="${esc(value)}" ${extra}></span></div>`;
    const lan = (st) => (!st.lan ? "Only this computer can open Inky." : st.web_url ? `On your phone, open <b class="mono">${esc(st.web_url)}</b> and sign in with the pairing code <b class="mono">${esc(S.pair || "")}</b>.` : "On, but this computer isn’t on a Wi‑Fi network right now.");
    this.el.innerHTML = `${mobileBar("Settings")}<div class="page"><div><h1>Settings</h1><p class="lede">For the whole app. Each bot has its own settings on its page.</p></div>
      <div class="grid2 sets"><div class="card shortcuts"><b>Shortcuts</b>${kb("Open the command bar", MAC ? "⌘ K" : "Ctrl K")}${APP ? kb("…from any app", MAC ? "⌥ Space" : "Alt Space") : ""}${kb("Pause all bots", MAC ? "⌥ P" : "Alt P")}${kb("On your screen: stop the bot", "Esc")}${kb("On your screen: chat while it drives", MAC ? "⌥ C" : "Alt C")}${kb("Take over: move your mouse on your screen", "mouse")}
        <span class="small muted" style="margin-top:8px">Anywhere on your computer, in the Inky app:</span><span id="barkey">${kb("Command bar over any app", "⌥ Space")}</span>${kb("Pause all bots", "⌃ ⌥ P")}${kb("Stop everything on my screen", "⌃ ⌥ Esc")}</div>
        <div class="card"><b>Privacy and data</b><div class="between"><span>Never record password fields</span><span class="small muted row">${icon("lock", 13)}always</span></div><div class="between"><span>Bots never type your passwords</span><span class="small muted row">${icon("lock", 13)}always</span></div>
          ${tog("lan", s.lan, "Let my phone open Inky (on this Wi‑Fi)")}<span class="small muted" id="lanline" role="status">${lan(s)}</span>
          <span class="small muted">Everything stays on your computers. There is no Inky server. Data folder: <span class="mono">${esc(s.data_folder || "~/.inky")}</span></span></div>
        <div class="card"><b>Notifications</b>${tog("notify_app", s.notify_app !== false, "In this app")}${tog("sounds", s.sounds !== false, "Sounds (each bot has its own)")}${APP ? tog("buddy", s.buddy !== false, "Desktop buddy: a critter peeks in when a bot needs you") + `<div class="between"><span>Open Inky when you log in</span><button class="toggle" id="autost" role="switch" aria-checked="false" aria-label="Open Inky when you log in"></button></div>` : ""}${tog("telegram", s.telegram.enabled, "On Telegram")}${field("chat", "Telegram chat id", s.telegram.chat_id || "", 'inputmode="numeric"')}
          <div class="between"><span>Bots on your screen</span><button class="toggle ${s.screen_allowed ? "on" : ""}" data-t="screen_allowed" role="switch" aria-checked="${!!s.screen_allowed}" aria-label="Bots on your screen"></button></div></div>
        <div class="card"><b>About</b><div class="between"><span>Inky 0.1.0</span><span class="small muted">open source · MIT</span></div>${field("en", "This computer’s name", String(s.engine_name || "").trim() || S.engine || "", 'maxlength="40"')}${field("un", "What should bots call you?", s.user_name || "", 'maxlength="40" placeholder="your name"')}
          <div class="row wrap"><a class="btn s" href="https://github.com/GHGuide/inky" target="_blank" rel="noopener">Read the code ↗</a><a class="btn s" href="#/setup/1">Run setup again</a></div></div></div></div>`;
    $$("[data-t]", this.el).forEach((x) => (x.onclick = async () => {  // shows the new state at once, and goes back if the engine says no
      if (x.dataset.busy) return;
      const k = x.dataset.t, on = !x.classList.contains("on"), set = (v) => { x.classList.toggle("on", v); x.setAttribute("aria-checked", v); };
      set(on); x.dataset.busy = "1";
      try {
        S.settings = await post("/api/settings", k === "telegram" ? { telegram: { enabled: on } } : { [k]: on });
        if (k === "lan") $("#lanline", this.el).innerHTML = lan(S.settings);
      } catch (e) { set(!on); toast(e.message); }
      delete x.dataset.busy;
    }));
    const saveField = (id, body, after) => {
      const i = $("#" + id, this.el), m = $(`[data-saved="${id}"]`, this.el);
      const say = (t, ok) => { clearTimeout(m._t); m.textContent = t; m.className = `small ${ok ? "good" : "bad"}`; ok ? i.removeAttribute("aria-invalid") : i.setAttribute("aria-invalid", "true"); };
      i.onchange = async () => {
        try {
          S.settings = await post("/api/settings", body(i.value.trim()));
          if (after) await after(S.settings, i);
          say("Saved", true); m._t = setTimeout(() => (m.textContent = ""), 2500);
        } catch (e) { say(e.message, false); }  // the engine's reason, next to what you typed, to fix it there
      };
    };
    saveField("chat", (v) => ({ telegram: { chat_id: v } }));
    saveField("en", (v) => ({ engine_name: v }), (r, i) => loadState().then(() => { i.value = String(r.engine_name || "").trim() || S.engine || i.value.trim(); }));  // blank: the computer’s own name
    saveField("un", (v) => ({ user_name: v }), (r, i) => { i.value = r.user_name || ""; toast(r.user_name ? `Bots will call you ${r.user_name}` : "Bots won’t use a name"); });
    if (APP) invoke("app_info").then((i) => { if (i && $("#barkey")) $("#barkey").innerHTML = i.bar_key === "none" ? kb("Command bar over any app", "taken by another app") : kb("Command bar over any app", i.bar_key.replaceAll("⌃⌥", "⌃ ⌥").replaceAll("⌥Space", "⌥ Space").replace(" or ", " or ")); });
    if ($("#autost")) {
      invoke("autostart", {}).then((on) => { $("#autost").classList.toggle("on", !!on); $("#autost").setAttribute("aria-checked", !!on); });
      $("#autost").onclick = async (e) => { const on = await invoke("autostart", { on: !e.currentTarget.classList.contains("on") }); $("#autost").classList.toggle("on", !!on); $("#autost").setAttribute("aria-checked", !!on); };
    }
  },
};
