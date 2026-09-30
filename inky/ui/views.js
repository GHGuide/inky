// Inky views. Each view: show(el, params, query), optional refresh(), onEvent(msg), leave().
const LOOKS = { kinds: ["octopus", "cat", "blob"], colors: [["#E86F51", "Coral"], ["#E9A23B", "Honey"], ["#2BA59B", "Sea"], ["#3B5BDB", "Ocean"], ["#7C6CF2", "Grape"], ["#F07BA8", "Bubblegum"]],
  accs: ["none", "glasses", "beanie", "headphones", "bow"], earned: [[10, "scarf"], [50, "party"], [100, "star"], [500, "crown"]] };
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const OPS = ["<=", "<", ">=", ">", "==", "!=", "contains", "not_contains", "in", "not_in"];

// ================================================================ setup wizard
const STEPS = ["Welcome", "Computers", "Model", "Your screen", "Phone", "Ready"];
const CLOUD = ["openrouter", "anthropic", "openai", "gemini", "groq", "xai", "mistral"];
const KEY_URL = { openrouter: "https://openrouter.ai/settings/keys", anthropic: "https://console.anthropic.com/settings/keys", openai: "https://platform.openai.com/api-keys",
  gemini: "https://aistudio.google.com/apikey", groq: "https://console.groq.com/keys", xai: "https://console.x.ai", mistral: "https://console.mistral.ai/api-keys" };
const KEY_ABOUT = { openrouter: "Hundreds of models, one key", anthropic: "Claude models", openai: "GPT models", gemini: "Free tier in AI Studio",
  groq: "Very fast · free tier", xai: "Grok models", mistral: "Made in Europe" };
VIEWS.setup = {
  bare: true,
  async show(el, [n = "1"]) {
    n = +n; this.el = el; this.n = n;
    let dir = "fwd"; try { dir = sessionStorage.getItem("wizDir") || "fwd"; sessionStorage.removeItem("wizDir"); } catch (e) {}
    const [st, models] = await Promise.all([get("/api/setup"), get("/api/models")]);
    this.st = st; this.label = Object.fromEntries(models.providers.map((p) => [p.name, p.label]));
    const pills = STEPS.map((t, i) => `<li class="${i + 1 < n ? "done" : i + 1 === n ? "on" : ""}"><i>${i + 1 < n ? "✓" : i + 1}</i><span>${t}</span></li>`).join("");
    const nav = (back, next, label = "Continue", skip) => `<div class="wfoot between">
      ${back ? `<a href="#/setup/${back}" class="muted" data-back>Back</a>` : `<span class="mono small muted">open source · MIT · no account needed</span>`}
      <span class="row">${skip ? `<a href="#/setup/${next}" class="muted small">${skip}</a>` : ""}<a class="btn p" href="${typeof next === "number" ? "#/setup/" + next : next}" id="wnext" style="min-height:44px">${label}</a></span></div>`;
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
      <div class="grid2"><div class="opt on"><b style="font-size:17px">This computer</b><span class="small muted">free · private · start here</span>
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
      <div class="col"><div class="between card"><span><b>Allow bots on my screen</b><br><span class="small muted">You still turn it on per bot</span></span><button class="toggle ${S.settings.screen_allowed ? "on" : ""}" id="scr" role="switch" aria-checked="${!!S.settings.screen_allowed}" aria-label="Allow bots on my screen"></button></div>
        <span class="small muted">${st.platform === "Darwin" ? "macOS: a browser window needs no extra permission. Driving other apps needs Screen Recording and Accessibility, which this version doesn’t use." : st.platform === "Windows" ? "Windows: nothing to allow." : "Linux: on Wayland the window is shared through the screen-sharing prompt once; on X11 nothing to allow."}</span></div></div>`;
      foot = nav(3, 5, "Continue", "Skip");
    }
    if (n === 5) {
      const tg = st.telegram || {};
      body = `<h1>Hear from your bots on your phone?</h1><p class="lede">Optional. They can ask you things and send summaries while you’re away.</p>
      <div class="grid2"><div class="opt on"><span class="row">${logo("telegram", 30)}<b style="font-size:17px">Telegram</b></span>
        <span class="small">1. <a href="https://t.me/BotFather" target="_blank" rel="noopener">Open @BotFather ↗</a> and send <span class="mono">/newbot</span>. Any name works.</span>
        <span class="small">2. Paste the token it sends you:</span>
        <div class="row"><input class="f grow" id="tgtoken" type="password" autocomplete="off" placeholder="${st.telegram_key ? "A token is saved. Paste a new one to replace it." : "123456789:AA…"}" aria-label="Telegram bot token"><button class="btn" id="tgsave">Connect</button></div>
        <span class="small" id="tgmsg" role="status">${tg.chat_id ? `✓ Connected${tg.bot ? " through @" + esc(tg.bot) : ""}.` : st.telegram_key ? `✓ Token saved. Send /start to ${tg.bot ? "@" + esc(tg.bot) : "your bot"} to finish.` : ""}</span>
        <span class="small">3. Send <span class="mono">/start</span> to your new bot. Inky finds you and says hello.</span>
        ${tg.chat_id ? `<div class="between"><span class="small">Send my alerts there</span><button class="toggle ${tg.enabled ? "on" : ""}" id="tg" role="switch" aria-checked="${!!tg.enabled}" aria-label="Send my alerts on Telegram"></button></div>` : ""}</div>
      <div class="opt"><b style="font-size:17px">Or the web app</b><span class="small">Open this computer’s address on your phone, on the same Wi-Fi, and sign in with the pairing code <b class="mono">${esc(st.pair_code || S.pair || "")}</b>. It installs like an app.</span></div></div>`;
      foot = nav(4, 6, "Continue", "Skip for now");
    }
    if (n === 6) {
      body = `<h1>You’re set</h1><div class="row" style="justify-content:center">${critter("octopus", "#E86F51", "none", 72)}</div>
      <div class="col list">${[["Computers", "Bots run as browsers on this computer"], ["Model", models.roles.learn ? `${models.roles.learn.model} for learning` : "none yet"],
        ["Your screen", S.settings.screen_allowed ? "Allowed · bots ask each time" : "Off"], ["Phone", (st.telegram || {}).enabled ? "Telegram" : "Off"]].map(([a, b]) =>
        `<div class="between" style="padding:9px 0"><span class="muted">${a}</span><span>${esc(b)}</span></div>`).join("")}</div>
      <div class="composer" style="width:100%"><label class="l" for="job">Make your first bot</label><textarea id="job" rows="2" placeholder="Describe a job in your own words"></textarea>
        <div class="between"><span class="mono small muted">⌘K opens the command bar anywhere</span><button class="btn p" id="start">Start</button></div></div>`;
      foot = nav(5, "#/bots", "Go to your bots");
    }
    el.innerHTML = `<div class="wiz"><header><span class="row">${critter("octopus", "#E86F51", "none", 26)}<b style="font-size:19px">inky</b></span><ol class="wsteps">${pills}</ol><a href="#/bots" id="skipall" class="small muted">Skip setup</a></header>
      <div class="wbody"><div class="wcard"><div class="wstep ${dir}">${body}</div>${foot}</div></div></div>`;
    const finish = async () => { await post("/api/settings", { setup_done: true }); S.setupDone = true; try { if (!localStorage.getItem("inkyTour")) sessionStorage.setItem("inkyTourNext", "1"); } catch (e) {} };
    $("#skipall").onclick = async (e) => { e.preventDefault(); await finish(); location.hash = "#/bots"; };
    if ($("[data-back]")) $("[data-back]").onclick = () => { try { sessionStorage.setItem("wizDir", "back"); } catch (e) {} };
    if ($("#scr")) $("#scr").onclick = async (e) => { const on = !e.target.classList.contains("on"); e.target.classList.toggle("on", on); e.target.setAttribute("aria-checked", on); S.settings = await post("/api/settings", { screen_allowed: on }); };
    if ($("#tg")) $("#tg").onclick = async (e) => { const on = !e.target.classList.contains("on"); e.target.classList.toggle("on", on); e.target.setAttribute("aria-checked", on); await post("/api/settings", { telegram: { enabled: on } }); };
    if (n === 2) bindServerAdder(st.install);
    if (n === 3) { this.showUsing(models.roles.learn); $$("[data-prov]").forEach((b) => (b.onclick = () => this.openKey(b.dataset.prov))); this.renderLocal(); }
    if (n === 5) this.bindTelegram();
    if (n === 6) {
      $("#wnext").onclick = async (e) => { e.preventDefault(); await finish(); location.hash = "#/bots"; };
      $("#start").onclick = async () => { await finish(); location.hash = `#/new?job=${encodeURIComponent($("#job").value)}`; };
    }
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
    const r = await post("/api/models/connect", { provider, model });
    if (!r.ok) { this.say(msgSel, r.reply || "That didn’t work.", false); return false; }
    this.say(msgSel, `✓ Works. Using ${r.model}, answered in ${r.seconds}s.`, true); SOUND.play("chime");
    this.showUsing({ provider, model: r.model });
    return true;
  },
  openKey(p) {
    $$("[data-prov]").forEach((b) => { b.classList.toggle("on", b.dataset.prov === p); b.setAttribute("aria-expanded", b.dataset.prov === p); });
    const kf = $("#keyfield"), has = this.st.keys[p], L = esc(this.label[p]);
    kf.classList.remove("hidden");
    kf.innerHTML = `<div class="row">${providerLogo(p, 28)}<b>Your ${L} key</b></div>
      <span class="small">1. <a href="${KEY_URL[p]}" target="_blank" rel="noopener">Make a key at ${esc(KEY_URL[p].replace("https://", ""))} ↗</a></span>
      <span class="small">2. Paste it here. It stays on this computer and only goes to ${L}.</span>
      <div class="row"><input class="f grow" id="keyin" type="password" autocomplete="off" placeholder="${has ? "A key is saved. Paste a new one to replace it." : "Paste the key"}" aria-label="${L} key"><button class="btn p" id="keysave">Save & test</button></div>
      <div class="between"><span class="small" id="keymsg" role="status"></span>${has ? `<button class="btn s" id="keyuse">Use the saved key</button>` : ""}</div>`;
    $("#keyin").focus();
    const tile = $(`[data-prov="${p}"]`);
    const save = async () => {
      const v = $("#keyin").value.trim(); if (!v) return this.say("#keymsg", "Paste a key first.", false);
      try { await post("/api/keys", { provider: p, key: v }); } catch (e) { return this.say("#keymsg", e.message, false); }
      $("#keyin").value = ""; this.st.keys[p] = "saved"; tile.classList.add("has"); $("[data-sub]", tile).textContent = "✓ key saved";
      await this.connect(p, null, "#keymsg");
    };
    $("#keysave").onclick = save;
    $("#keyin").onkeydown = (e) => { if (e.key === "Enter") save(); };
    if ($("#keyuse")) $("#keyuse").onclick = () => this.connect(p, null, "#keymsg");
  },
  async renderLocal() {
    const box = $("#localm"); if (!box) return;
    const loc = await get("/api/models/local"), o = loc.ollama, pulls = loc.pulls || {};
    const head = (s, t) => `<div class="lrow"><span class="row">${logo(s, 34)}<span><b>${s === "ollama" ? "Ollama" : "LM Studio"}</b><br><span class="small muted">${t}</span></span></span>`;
    let h;
    if (!o.installed && !o.running) h = `${head("ollama", "not installed yet")}<span class="row"><a class="btn" href="https://ollama.com/download" target="_blank" rel="noopener">Install Ollama ↗</a><button class="btn s" data-lrefresh>Check again</button></span></div>
      <span class="small muted">Ollama runs models on this computer for free. Install it, then press Check again.</span>`;
    else if (!o.running) h = `${head("ollama", "installed, not running")}<button class="btn" id="ollstart">Start Ollama</button></div><span class="small" id="lmsg" role="status"></span>`;
    else if (!o.models.length) {
      const pick = loc.catalog.filter((c) => c.fit === "fits well" || c.fit === "tight" || c.fit === "unknown").slice(0, 3);
      h = `${head("ollama", "running · pick a model to download")}</div>${pick.map((c) => {
        const p = pulls[c.name];
        return `<div class="lrow"><span><b class="mono">${esc(c.name)}</b> <span class="small muted">${c.gb} GB${c.badge === "recommended" ? " · recommended" : ""}</span><br><span class="small muted">${esc(c.about)}</span></span>
        <span class="row">${p && p.status !== "success" && !String(p.status).startsWith("failed") ? `<span class="prog" data-prog="${esc(c.name)}"><i style="width:${p.total ? Math.round(100 * p.completed / p.total) : 2}%"></i></span>` : `<button class="btn s" data-pull="${esc(c.name)}">Download</button>`}</span></div>`;
      }).join("") || `<span class="small muted">No model in our list fits this computer’s memory. Use an API key instead.</span>`}<span class="small" id="lmsg" role="status"></span>`;
    } else h = `${head("ollama", "running")}</div>${o.models.map((m) => `<div class="lrow"><b class="mono">${esc(m.name)}</b>${this.using && this.using.provider === "ollama" && this.using.model === m.name ? `<span class="small good">✓ In use</span>` : `<button class="btn s" data-use="${esc(m.name)}">Use this</button>`}</div>`).join("")}<span class="small" id="lmsg" role="status"></span>`;
    if (loc.custom.reachable) h += `${head("lmstudio", "running at " + esc(loc.custom.base))}<button class="btn s" id="uselms">Use LM Studio</button></div>`;
    else if (loc.lmstudio.installed) h += `${head("lmstudio", "installed · start its local server to use it")}<button class="btn s" data-lrefresh>Check again</button></div>`;
    box.innerHTML = h;
    $$("[data-lrefresh]", box).forEach((b) => (b.onclick = () => this.renderLocal()));
    if ($("#ollstart")) $("#ollstart").onclick = async () => {
      $("#ollstart").disabled = true; this.say("#lmsg", "Starting Ollama…");
      const r = await post("/api/models/local/start", {});
      if (r.running) this.renderLocal(); else { $("#ollstart").disabled = false; this.say("#lmsg", "Ollama didn’t start. Open the Ollama app once, then try again.", false); }
    };
    $$("[data-pull]", box).forEach((b) => (b.onclick = async () => { b.disabled = true; b.textContent = "Starting…"; await post("/api/models/pull", { name: b.dataset.pull }); }));
    $$("[data-use]", box).forEach((b) => (b.onclick = async () => { b.disabled = true; if (await this.connect("ollama", b.dataset.use, "#lmsg")) this.renderLocal(); else b.disabled = false; }));
    if ($("#uselms")) $("#uselms").onclick = () => this.connect("custom", null, "#lmsg");
  },
  bindTelegram() {
    const say = (t, ok) => this.say("#tgmsg", t, ok);
    const save = async () => {
      const v = $("#tgtoken").value.trim(); if (!v) return say("Paste the token from @BotFather first.", false);
      say("Checking with Telegram…");
      const r = await post("/api/connectors/telegram/setup", { values: { token: v } });
      if (!r.ok) return say(r.text, false);
      $("#tgtoken").value = "";
      waitForTelegram(r.bot, say);
    };
    const tg = this.st.telegram || {};
    if (this.st.telegram_key && !tg.chat_id && tg.bot) waitForTelegram(tg.bot, say);  // token saved earlier: keep listening for /start
    $("#tgsave").onclick = save;
    $("#tgtoken").onkeydown = (e) => { if (e.key === "Enter") save(); };
  },
  leave() { clearInterval(tgPoll); clearInterval(foundTimer); },
  onEvent(m) {
    if (m.kind === "ssh") return sshLine(m);
    if (m.kind !== "pull" || this.n !== 3) return;
    const bar = $(`[data-prog="${m.name}"] i`);
    if (m.status === "success") { this.connect("ollama", m.name, "#lmsg").then(() => this.renderLocal()); return; }
    if (String(m.status || "").startsWith("failed")) { this.renderLocal().then(() => this.say("#lmsg", `Download stopped: ${m.status.slice(8)}`, false)); return; }
    if (bar) { if (m.total) bar.style.width = Math.round(100 * m.completed / m.total) + "%"; } else this.renderLocal();
  },
};

// ================================================================ your bots
VIEWS.bots = {
  async show(el) {
    this.el = el;
    el.innerHTML = `${mobileBar("Your bots")}<div class="hero">${critter("octopus", "#E86F51", "none", 72)}<h1>What job should a new bot do?</h1>
      <p class="lede" style="margin-top:-6px">Each bot gets its own computer and keeps working while you’re away. It learns a job once, then repeats it with no AI.</p>
      <div class="composer"><label class="vh" for="job">Describe the job</label><textarea id="job" rows="2" placeholder="Describe a job, or @mention a bot"></textarea>
        <div class="between"><span class="mono small muted">⌘K anywhere · @ to talk to a bot</span><button class="btn p" id="go">Start</button></div></div>
      <div class="row wrap" style="justify-content:center">${["Find rental flats abroad under €150k", "Watch 5 webshops for price drops", "Every morning, check new books on books.toscrape.com"].map((t) => `<button class="btn" data-ex="${esc(t)}">${esc(t)}</button>`).join("")}</div></div>
      <div class="page" style="padding-top:12px"><div id="recap"></div><div class="between"><h2>Your bots</h2><span class="row"><span class="seg" id="homeview" role="group" aria-label="Show bots as"><button data-hv="cards">Cards</button><button data-hv="office">Office</button></span><label class="btn s" for="importf">Import a bot file</label><input type="file" id="importf" accept=".inky,.json" class="vh"></span></div><div class="botcards" id="cards"></div></div>`;
    const go = () => {
      const t = $("#job").value.trim();
      const m = t.match(/^@(\S+)\s+(.*)$/);
      const b = m && S.bots.find((x) => x.name.toLowerCase().startsWith(m[1].toLowerCase()));
      if (b) { post(`/api/bots/${b.id}/chat`, { text: m[2] }); location.hash = `#/bot/${b.id}/computer`; } else location.hash = `#/new?job=${encodeURIComponent(t)}`;
    };
    $("#go").onclick = go;
    $("#job").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(); } };
    $$("[data-ex]").forEach((b) => (b.onclick = () => { $("#job").value = b.dataset.ex; $("#job").focus(); }));
    $("#importf").onchange = async (e) => {
      const f = e.target.files[0]; if (!f) return;
      e.target.value = "";
      try { const r = await post("/api/import", JSON.parse(await f.text())); location.hash = `#/bot/${r.bot.id}/computer`; }
      catch (err) { toast(`That isn’t an Inky bot file (${err.message})`); }
    };
    $$("[data-hv]").forEach((x) => (x.onclick = () => { try { localStorage.setItem("inkyHome", x.dataset.hv); } catch (e) {} this.refresh(); }));
    this.refresh();
    this.recap();
    try { if (sessionStorage.getItem("inkyTourNext") && !localStorage.getItem("inkyTour")) { sessionStorage.removeItem("inkyTourNext"); setTimeout(() => tour(0), 600); } } catch (e) {}
    this.timer = setInterval(() => $$("#cards img[data-live]").forEach((i) => (i.src = screenUrl(i.dataset.live))), 2500);
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
    $$("[data-hv]").forEach((x) => x.classList.toggle("on", x.dataset.hv === mode));
    $("#cards").className = mode === "office" ? "" : "botcards";
    if (mode === "office") return this.office();
    $("#cards").innerHTML = S.bots.map((b) => {
      const m = botMeta(b);
      const live = ["working", "learning", "paused"].includes(b.status);
      const mid = b.status === "needs_you" ? `<div class="card" style="padding:12px 14px;gap:4px;border-color:#F3C9BC"><span class="small" style="color:var(--coral-t);font-weight:600">Needs you</span><b>${b.needs} waiting</b></div>`
        : live ? `<div class="thumb"><img data-live="${b.id}" src="${screenUrl(b.id)}" alt="${esc(b.name)}’s computer"><span class="live">LIVE</span></div>`
          : `<div class="thumb idle">${esc(b.remote_id ? "on your server" : b.skills.length ? m.meta : "hasn’t learned yet")}</div>`;
      return `<a class="botcard${m.hot ? " hot" : ""}" href="#/bot/${b.id}/computer"><span class="row">${botCritter(b, 44)}<span class="col" style="gap:2px"><b>${esc(b.name)}</b><span class="small muted">${esc((b.summary || b.job || "").slice(0, 60))}</span></span></span>
        ${mid}<span class="between mono small muted"><span style="color:${m.color}">● ${esc((STATUS[b.status] || [b.status.replace("_", " ")])[0])}</span><span>${b.skills.length} skills</span></span></a>`;
    }).join("") || `<p class="muted">No bots yet. Describe a job above.</p>`;
  },
  office() {  // the same bots, at their desks; the room follows the time of day
    const h = new Date().getHours(), night = S.bots.length && S.bots.every((b) => inQuiet(b.schedule, new Date()));
    const sky = night || h < 6 || h >= 21 ? "night" : h < 8 ? "dawn" : h < 17 ? "day" : "evening";
    $("#cards").innerHTML = `<div class="office ${night ? "dim" : ""}" data-sky="${sky}"><div class="window" aria-hidden="true"><i class="sun"></i><i class="moon"></i><b></b><b></b><b></b></div>
      ${S.bots.map((b) => {
        const live = ["working", "learning", "paused"].includes(b.status) && !b.remote;
        const screen = live ? `<img data-live="${b.id}" src="${screenUrl(b.id)}" alt="${esc(b.name)}’s computer">` : `<span>${esc(botMeta(b).meta.slice(0, 26))}</span>`;
        return `<a class="desk${botMeta(b).hot ? " hot" : ""}" href="#/bot/${b.id}/computer"><div class="top">${botCritter(b, 70)}<div class="mon">${screen}</div></div><div class="table"></div><div class="plate"><b>${esc(b.name)}</b></div></a>`;
      }).join("") || `<p class="muted">No bots yet. Describe a job above.</p>`}</div>`;
  },
  leave() { clearInterval(this.timer); },
};

// ================================================================ new bot
VIEWS.new = {
  async show(el, _, qs) {
    const job = qs.get("job") || "";
    el.innerHTML = `${mobileBar("New bot")}<div class="page narrow"><h1>New bot</h1><p class="lede">Describe the job. It drafts the bot, you check it, then it learns the site once while you watch.</p>
      <div class="composer" style="width:100%"><label class="vh" for="job">Job</label><textarea id="job" rows="3" placeholder="e.g. Every morning, find flats in Bari under €150k on casafacile.it">${esc(job)}</textarea>
      <div class="between"><span class="small muted">Include the site if you know it.</span><button class="btn p" id="draft">Draft the bot</button></div></div><div id="draftbox"></div></div>`;
    const draft = async () => {
      $("#draftbox").innerHTML = `<p class="muted">Thinking…</p>`;
      try { this.render((await post("/api/bots/draft", { job: $("#job").value })).draft); }
      catch (e) { $("#draftbox").innerHTML = `<p class="hot">${esc(e.message)}</p>`; }
    };
    $("#draft").onclick = draft;
    if (job) draft();
  },
  render(d) {
    const look = d.look || { kind: "octopus", color: "#E86F51", acc: "none" };
    $("#draftbox").innerHTML = `<div class="card" style="margin-top:8px"><div class="row">${critter(look.kind, look.color, look.acc, 48)}<div class="grow"><label class="l" for="nm">Your new bot</label><input class="f" id="nm" value="${esc(d.name)}"></div></div>
      ${d.summary ? `<div class="card panel">${esc(d.summary)}</div>` : ""}
      <div class="grid2"><div><label class="l" for="url">Start on this site</label><input class="f" id="url" value="${esc(d.start_url || "")}" placeholder="https://…"></div>
        <div><label class="l" for="every">Check every (minutes, 0 = only when I ask)</label><input class="f" id="every" type="number" min="0" value="${d.every_minutes || 0}"></div></div>
      <div><label class="l" for="goal">What to do there</label><input class="f" id="goal" value="${esc(d.goal || "")}"></div>
      <div><label class="l">Rules for results</label><div id="filters" class="col"></div><button class="btn s" id="addf" style="margin-top:6px">Add a rule</button></div>
      ${(d.questions || []).length ? `<div class="card panel small"><b>It wonders:</b> ${d.questions.map(esc).join(" · ")}</div>` : ""}
      <div class="col"><span class="l">What it may do</span><div class="rule"><b>On its own</b><span>Read, search, take notes</span></div><div class="rule ask"><b>Ask you first</b><span>Send, post, delete, submit forms, sign up</span></div><div class="rule"><b>Never</b><span>Buy or pay · type your passwords</span></div></div>
      <div class="between"><span class="small muted">It learns the site right after you create it.</span><button class="btn p" id="create">Create ${esc(d.name)}</button></div></div>`;
    const filters = [...(d.filters || [])];
    const drawF = () => {
      $("#filters").innerHTML = filters.map((f, i) => `<div class="row"><input class="f" style="width:140px" data-i="${i}" data-k="field" value="${esc(f.field)}"><select class="f" style="width:140px" data-i="${i}" data-k="op">${OPS.map((o) => `<option ${o === f.op ? "selected" : ""}>${o}</option>`).join("")}</select>
        <input class="f" data-i="${i}" data-k="value" value="${esc(Array.isArray(f.value) ? f.value.join(", ") : f.value)}"><button class="iconbtn" data-del="${i}" aria-label="Remove rule">${icon("x", 14)}</button></div>`).join("") || `<span class="small muted">None: it keeps everything it finds.</span>`;
      $$("#filters [data-k]").forEach((x) => (x.onchange = () => { const f = filters[x.dataset.i]; f[x.dataset.k] = x.dataset.k === "value" && /,/.test(x.value) ? x.value.split(",").map((s) => s.trim()) : x.value; }));
      $$("#filters [data-del]").forEach((x) => (x.onclick = () => { filters.splice(+x.dataset.del, 1); drawF(); }));
    };
    drawF();
    $("#addf").onclick = () => { filters.push({ field: "price", op: "<=", value: "" }); drawF(); };
    $("#create").onclick = async () => {
      const body = { ...d, name: $("#nm").value, start_url: $("#url").value.trim() || null, goal: $("#goal").value, every_minutes: +$("#every").value || 0,
        filters: filters.map((f) => ({ ...f, value: isNaN(+f.value) || f.value === "" ? f.value : +f.value, text: `${f.field} ${f.op} ${f.value}` })) };
      const b = (await post("/api/bots", body)).bot;
      if (body.start_url) await post(`/api/bots/${b.id}/learn`, {}).catch((e) => toast(e.message));
      await loadState();
      location.hash = `#/bot/${b.id}/computer?hatch=1`;
    };
  },
};

// ================================================================ a bot
const TABS = [["computer", "Computer"], ["results", "Results"], ["diary", "Diary"], ["skills", "Skills"], ["about", "About you"], ["settings", "Settings"], ["activity", "Activity"], ["call", "Call"]];
VIEWS.bot = {
  async show(el, [id, tab = "computer"], qs) {
    this.id = +id; this.tab = tab; this.el = el;
    this.data = await get(`/api/bots/${this.id}`);
    const b = this.data.bot;
    el.innerHTML = `${mobileBar(b.name)}<div class="botpage"><div class="bothead" id="bh"></div><div class="botbody">
      <section class="chatcol" aria-label="Conversation"><div class="msgs" id="msgs"></div>
        <div class="chatin"><div class="chatbox"><label class="vh" for="say">Message ${esc(b.name)}</label><input id="say" placeholder="Message ${esc(b.name)}… say “slower”, “stop”, or give it a rule" autocomplete="off">
        <div class="between"><span class="mono small muted">⌘K command bar · you can type while it drives</span><span class="row"><a class="iconbtn" href="#/bot/${b.id}/call" aria-label="Call">${icon("mic")}</a><button class="iconbtn" id="send" style="background:var(--ink);color:#fff;border:0" aria-label="Send">${icon("send", 17, 2.2)}</button></span></div></div></div></section>
      <section class="rightcol"><nav class="tabs" aria-label="Bot views">${TABS.map(([k, t]) => `<a href="#/bot/${b.id}/${k}" class="${k === tab ? "on" : ""}">${t}</a>`).join("")}</nav><div class="tabbody" id="tb"></div></section></div></div>`;
    const send = async () => {
      const t = $("#say").value.trim(); if (!t) return;
      $("#say").value = "";
      this.data.messages.push({ role: "you", text: t, ts: Date.now() / 1000 });
      this.typing = true; this.drawMsgs(true);
      try { await post(`/api/bots/${this.id}/chat`, { text: t }); } catch (e) { toast(e.message); }
      this.typing = false; this.refresh();
    };
    $("#send").onclick = send;
    $("#say").onkeydown = (e) => { if (e.key === "Enter") send(); };
    this.drawHead(); this.drawMsgs(); this.drawTab(true);
    if (qs && qs.get("hatch")) { history.replaceState(null, "", `#/bot/${b.id}/${tab}`); hatch(b, (this.data.messages.find((m) => m.intro) || {}).text); }
  },
  async refresh() {
    if (!this.id) return;
    try { this.data = await get(`/api/bots/${this.id}`); } catch (e) { return; }
    this.drawHead(); this.drawMsgs(); this.drawTab(false);
  },
  onEvent(m) { if (m.kind === "move" && m.bot === this.id) toast(m.text || m.step, this.data.bot); },
  leave() { if (this.callEnd) this.callEnd(); this.id = null; },
  drawHead() {
    const b = this.data.bot, m = botMeta(b);
    const running = ["working", "learning", "paused"].includes(b.status);
    $("#bh").innerHTML = `<div class="row" style="min-width:0">${botCritter(b, 30)}<h1>${esc(b.name)}</h1><span class="pill ${m.hot ? "hot" : ""} ${["working", "learning"].includes(b.status) ? "live" : ""}"><i style="background:${m.color}"></i>${esc(m.meta.slice(0, 50))}</span>
      <span class="mono small muted hide-s row" style="gap:5px">${icon(b.remote ? "server" : "monitor", 13)}${esc(b.remote || (b.mode === "screen" ? "your screen" : "its own computer"))}</span></div>
      <div class="row">${running ? `<button class="btn s" id="pz">${b.status === "paused" ? "Resume" : "Pause"}</button>` : `<button class="btn s" id="runnow">Run now</button>`}
      <a class="iconbtn hide-s" href="#/bot/${b.id}/call" aria-label="Call ${esc(b.name)}">${icon("phone", 16, 1.9)}</a><button class="btn s hide-s" data-dl="/api/bots/${b.id}/export" data-name="${esc(b.name)}.inky" title="A file with its skills and settings, without your sign-ins or chat">Share</button></div>`;
    const pz = $("#pz"); if (pz) pz.onclick = () => post(`/api/bots/${b.id}/control`, { cmd: b.status === "paused" ? "resume" : "pause" }).then(refreshSoon);
    const rn = $("#runnow"); if (rn) rn.onclick = () => post(`/api/bots/${b.id}/run`, {}).then(refreshSoon).catch((e) => toast(e.message));
  },
  drawMsgs(force) {
    const box = $("#msgs"); if (!box) return;
    const b = this.data.bot;
    const key = this.data.messages.length + ":" + (this.data.messages.at(-1) || {}).text + ":" + !!this.typing;
    if (!force && key === this.msgKey) return;
    this.msgKey = key;
    let lastDay = "";
    const needIds = new Set(this.data.needs.map((n) => n.id));
    const msgs = [];  // "Checked 11 results…" six times in a row reads as one line with ×6
    for (const m of this.data.messages) {
      const last = msgs.at(-1);
      if (last && m.role === "bot" && last.role === "bot" && m.text === last.text && !m.need && !(m.chips || []).length) last.times = (last.times || 1) + 1;
      else msgs.push({ ...m });
    }
    box.innerHTML = msgs.map((m) => {
      const d = new Date(m.ts * 1000).toDateString();
      const day = d !== lastDay ? `<div class="m sys">${d === new Date().toDateString() ? "Today" : d} ${hhmm(m.ts)}</div>` : "";
      lastDay = d;
      if (m.role === "you") return `${day}<div class="m you"><div class="body">${esc(m.text)}</div></div>`;
      if (m.role === "note") return `${day}<div class="m sys">${esc(m.text)}</div>`;
      if (m.role === "peer") { const sb = S.bots.find((x) => x.id === m.sender_id) || { look: {}, status: "idle" };
        return `${day}<div class="m peer">${botCritter(sb, 26)}<div class="body"><span class="small" style="color:var(--coral-t);font-weight:600">${esc(m.sender)}</span><span>${esc(m.text)}</span></div></div>`; }
      const need = m.need && needIds.has(m.need) ? this.data.needs.find((n) => n.id === m.need) : null;
      const card = need ? `<div class="card hot" style="padding:12px 14px"><span class="small" style="color:var(--coral-t);font-weight:600">Needs you</span><b>${esc(need.title)}</b>${need.body ? `<span class="small muted">${esc(need.body)}</span>` : ""}
        <div class="row wrap">${(need.options || []).map((o, i) => `<button class="btn s ${i === 0 ? "p" : ""}" data-need="${need.id}" data-o="${esc(o)}">${esc(o)}</button>`).join("")}</div></div>` : "";
      const done = (m.done || []).filter(Boolean).map((x) => `<span class="logl">● ${esc(x)}</span>`).join("");
      const chips = (m.chips || []).length ? `<div class="row wrap">${m.chips_used ? `<span class="logl">● done</span>` : m.chips.map((c, i) => `<button class="btn s p" data-chip="${m.id}" data-ci="${i}">${esc(c.label)}</button>`).join("")}</div>` : "";
      return `${day}<div class="m">${botCritter(b, 26)}<div class="body"><span>${esc(m.text)}${m.times ? ` <span class="badge">×${m.times}</span>` : ""}</span>${done}${chips}${card}</div></div>`;
    }).join("") || `<div class="m sys">Say hi, or give it a job.</div>`;
    if (this.typing) box.insertAdjacentHTML("beforeend", `<div class="m">${botCritter(b, 26)}<div class="body typing" aria-label="${esc(b.name)} is typing"><i></i><i></i><i></i></div></div>`);
    $$("[data-need]", box).forEach((x) => (x.onclick = () => answerNeed(+x.dataset.need, x.dataset.o)));
    $$("[data-chip]", box).forEach((x) => (x.onclick = async () => {
      const m = this.data.messages.find((y) => y.id === +x.dataset.chip), c = m && m.chips[+x.dataset.ci];
      if (!c) return;
      try { await post(`/api/bots/${this.id}/apply`, { apply: c.apply, message: m.id }); toast(c.label, b); this.refresh(); } catch (e) { toast(e.message); }
    }));
    box.scrollTop = 1e9;
  },
  drawTab(first) {
    const fn = this["tab_" + this.tab];
    if (fn) fn.call(this, $("#tb"), first);
  },

  // ---- Computer tab: live view, take over, show me once, timeline
  tab_computer(tb, first) {
    const b = this.data.bot;
    const run = b.run_kind;
    const skill = this.data.skills.find((s) => s.id === b.skill_id) || this.data.skills[0];
    if (first || !$("#live")) {
      tb.innerHTML = `<div class="between"><span class="row" id="drv"></span><span class="row">
        <span class="seg" id="speed">${["slow", "normal", "turbo"].map((s) => `<button data-s="${s}" class="${(b.look.speed || "normal") === s ? "on" : ""}">${cap(s)}</button>`).join("")}</span>
        <button class="btn s" id="tk"></button><button class="btn s" id="stop">Stop</button></span></div>
        <div class="row screenrow" style="align-items:flex-start;gap:14px"><div class="grow col" style="gap:8px;min-width:min(420px,100%)">
          <div class="screen" id="scr"><div class="bar"><span>Activities</span><span id="clock"></span><span>${esc(b.name.toLowerCase().replace(/\s+/g, "-"))}</span></div>
          <img id="live" alt="${esc(b.name)}’s computer, live" src="${screenUrl(b.id, "mjpg")}"><span class="over hidden" id="over">You have control · ${esc(b.name)} is waiting</span></div>
          <div class="row wrap hidden" id="typebar"><label class="vh" for="gourl">Open a page</label><input class="f" id="gourl" style="flex:1 1 200px" placeholder="Open a page (address)"><label class="vh" for="typ">Type on its computer</label><input class="f" id="typ" style="flex:1 1 200px" placeholder="Type on its computer, then Enter"><button class="btn s" data-key="Enter">Enter</button><button class="btn s" data-key="Tab">Tab</button><button class="btn s" data-key="Backspace">⌫</button></div>
          <div class="card hot hidden" id="showbar"><b>Show me once</b><span class="small">Click what it should click on its computer. Each click is recorded. <span id="shown"></span></span><div class="row"><button class="btn s p" id="showdone">Done showing</button></div></div>
        </div><aside class="card" style="flex:0 1 250px;min-width:230px" id="side"></aside></div>
        <div class="col" style="gap:8px"><div class="between"><b class="small" id="tlname"></b><span class="mono small muted" id="tlnote"></span></div><div class="steps" id="tl"></div></div>`;
      $$("#speed button").forEach((x) => (x.onclick = () => post(`/api/bots/${b.id}/control`, { cmd: "speed", value: x.dataset.s }).then(refreshSoon)));
      $("#stop").onclick = () => post(`/api/bots/${b.id}/control`, { cmd: "stop" }).then(refreshSoon);
      const img = $("#live");
      img.onclick = (e) => {
        if (!this.data.bot.takeover) return;
        const r = img.getBoundingClientRect();
        post(`/api/bots/${b.id}/input`, { kind: "click", x: Math.round((e.clientX - r.left) / r.width * 1280), y: Math.round((e.clientY - r.top) / r.height * 800) }).then(refreshSoon);
      };
      img.addEventListener("wheel", (e) => { if (this.data.bot.takeover) { e.preventDefault(); post(`/api/bots/${b.id}/input`, { kind: "scroll", y: Math.round(e.deltaY) }); } }, { passive: false });
      $("#typ").onkeydown = (e) => { if (e.key === "Enter") { post(`/api/bots/${b.id}/input`, { kind: "type", text: $("#typ").value }); $("#typ").value = ""; } };
      $("#gourl").onkeydown = (e) => { if (e.key === "Enter" && e.target.value.trim()) { post(`/api/bots/${b.id}/input`, { kind: "goto", text: e.target.value.trim() }).catch((x) => toast(x.message)); } };
      $$("#typebar [data-key]").forEach((x) => (x.onclick = () => post(`/api/bots/${b.id}/input`, { kind: "key", key: x.dataset.key })));
      $("#showdone").onclick = () => post(`/api/bots/${b.id}/show/done`, {}).then(refreshSoon).catch((e) => toast(e.message));
      img.onerror = () => setTimeout(() => (img.src = screenUrl(b.id, "mjpg") + "&r=" + Date.now()), 2000);
    }
    const tk = b.takeover;
    $("#clock").textContent = new Date().toTimeString().slice(0, 5);
    $("#drv").innerHTML = `<span style="width:8px;height:8px;border-radius:50%;background:${tk ? "#111110" : "var(--coral)"};box-shadow:0 0 0 4px rgba(232,111,81,.2)"></span>
      <b>${tk ? "You have control" : run === "learning" || run === "learn" ? `${esc(b.name)} is learning` : run ? `${esc(b.name)} is driving` : `${esc(b.name)}’s computer`}</b>
      <span class="muted">· ${tk ? "click and type on it" : run === "learn" ? "asks the AI once per step" : run ? `replaying a saved skill · ${b.ai_calls} AI calls` : "idle"}</span>`;
    $("#tk").textContent = tk ? "Hand back" : "Take over";
    $("#tk").className = "btn s" + (tk ? " p" : "");
    $("#tk").onclick = () => post(`/api/bots/${b.id}/control`, { cmd: tk ? "handback" : "takeover" }).then(refreshSoon);
    $("#scr").classList.toggle("drive", !!tk);
    $("#over").classList.toggle("hidden", !tk);
    $("#typebar").classList.toggle("hidden", !tk);
    $("#showbar").classList.toggle("hidden", run !== "show");
    $("#shown").textContent = b.shown ? `${b.shown} recorded.` : "";
    $$("#speed button").forEach((x) => x.classList.toggle("on", x.dataset.s === (b.look.speed || "normal")));
    const mem = (b.memory || []).map((m) => `<span class="chip">${esc(m.text)}</span>`).join("") || `<span class="small muted">Nothing yet</span>`;
    const lastRun = this.data.runs[0];
    $("#side").innerHTML = `<div class="head"><b>This run</b><span class="mono small muted">${b.ai_calls} AI calls</span></div>
      <div class="col small" style="gap:6px"><div class="between"><span class="muted">Skill</span><span>${esc(skill ? skill.name : "none yet")}</span></div>
      <div class="between"><span class="muted">Step</span><span class="mono">${b.step_n || "–"}${skill ? " of " + skill.steps.length : ""}</span></div>
      <div class="between"><span class="muted">Last run</span><span>${lastRun ? esc(lastRun.status) + " · " + ago(lastRun.ts) : "–"}</span></div></div>
      <div style="height:1px;background:var(--line)"></div><div class="head"><b>It remembers</b><a class="small" href="#/bot/${b.id}/about">Edit</a></div><div class="row wrap" style="gap:6px">${mem}</div>
      <div style="height:1px;background:var(--line)"></div><div class="col" style="gap:6px">${this.data.events.filter((e) => ["fixed", "repair", "problem", "learned"].includes(e.kind)).slice(0, 3).map((e) => `<span class="logl">${hhmm(e.ts)} · ${esc(e.text)}</span>`).join("") || `<span class="small muted">No fixes yet</span>`}</div>
      <a class="small" href="#/bot/${b.id}/skills" style="margin-top:auto;font-weight:600">See all ${this.data.skills.length} skills</a>`;
    if (skill) {
      $("#tlname").textContent = `${skill.name} · ${skill.steps.length} steps`;
      $("#tlnote").textContent = run === "learn" ? "learning: you can correct any step in the chat" : "replays a saved skill · 0 AI calls";
      const at = run ? b.step_n : 0;
      $("#tl").innerHTML = skill.steps.map((s, i) => `<div class="st ${i + 1 === at ? "cur" : ""}"><span class="n">${i + 1}</span><span class="x" title="${esc(s.text)}">${esc(s.text)}</span><span class="p"><i style="width:${i + 1 < at ? 100 : i + 1 === at ? 55 : 0}%"></i></span></div>`).join("");
    } else {
      $("#tlname").textContent = run === "learn" ? "Learning…" : "No skill yet";
      $("#tlnote").textContent = "";
      const learned = this.data.events.filter((e) => e.kind === "learn").reverse();
      $("#tl").innerHTML = learned.map((e, i) => `<div class="st ${i === learned.length - 1 ? "cur" : ""}"><span class="n">${i + 1}</span><span class="x">${esc(e.text)}</span><span class="p"><i style="width:${i === learned.length - 1 ? 55 : 100}%"></i></span></div>`).join("")
        || `<span class="small muted">Tell it the site and the job, or press Run now.</span>`;
    }
  },

  tab_results(tb) {
    get(`/api/bots/${this.id}/results`).then(({ results }) => {
      const cols = [...new Set(results.flatMap((r) => Object.keys(r)))].filter((k) => !["id", "ts", "run", "skill", "new", "last", "first"].includes(k)).slice(0, 6);
      const f = this.data.bot.filters || [];
      tb.innerHTML = `<div class="between"><b>${results.length} results pass its rules</b><span class="row wrap">${f.map((x) => `<span class="chip">${esc(x.text || `${x.field} ${x.op} ${x.value}`)}</span>`).join("")}</span></div>
        ${results.length ? `<table class="t"><thead><tr><th></th>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${results.map((r) => `<tr><td>${r.new ? '<span class="badge hot">new</span>' : ""}</td>${cols.map((c) => `<td>${c === "link" && r[c] ? `<a href="${esc(r[c])}" target="_blank" rel="noopener">open ↗</a>` : esc(r[c] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table>`
          : `<p class="muted">Nothing yet. Press Run now.</p>`}`;
    });
  },

  tab_skills(tb) {
    const sk = this.data.skills, b = this.data.bot;
    const sel = sk.find((s) => s.id === this.skillSel) || sk[0];
    tb.innerHTML = `<div class="row wrap">${sk.map((s) => `<button class="btn s ${sel && s.id === sel.id ? "p" : ""}" data-sk="${s.id}">${esc(s.name)}</button>`).join("")}<label class="btn s" for="skf">Import a skill</label><input type="file" id="skf" class="vh" accept=".inkyskill,.json"></div>
      ${sel ? `<div class="row" style="align-items:flex-start;gap:14px"><div class="card grow"><div class="head"><h2>${esc(sel.name)}</h2><span class="mono small muted">v${sel.version || 1} · ${esc(sel.site || "")}</span></div>
        <div class="list">${sel.steps.map((s, i) => `<div class="row" style="padding:8px 0;font-size:14px"><span class="mono small muted" style="width:22px">${i + 1}</span><span class="grow">${esc(s.text)}${s.repaired ? ` <span class="badge">fixed ${s.repaired}×</span>` : ""}${s.shown ? ' <span class="badge">shown by you</span>' : ""}${s.approved_always ? ` <span class="badge">always allowed</span> <button class="chip" data-ask="${i}" style="border:0;cursor:pointer">ask again</button>` : ""}</span>
          <span class="mono small muted">${esc(s.action === "extract" ? Object.keys(s.spec.fields || {}).length + " fields" : s.target ? `${s.target.role} “${s.target.name}”` : s.value || "")}</span></div>`).join("")}</div></div>
        <aside class="col" style="width:240px;flex-shrink:0"><div class="card"><b>How it runs</b><div class="grid2" style="gap:8px">${[["runs", this.data.runs.filter((r) => r.skill === sel.name && r.status === "ok").length], ["AI calls per run", 0],
          ["steps", sel.steps.length], ["pages", sel.max_pages || 1]].map(([k, v]) => `<div class="stat" style="background:var(--panel);border:0"><b>${v}</b><span>${k}</span></div>`).join("")}</div></div>
          <div class="card small"><b>If the page changes</b><span>1. It finds the button again by its name. No AI.</span><span>2. If that fails, it asks the model once and only acts when sure.</span><span>3. Otherwise it stops and asks you.</span></div>
          <button class="btn p" id="runsk">Run now</button><button class="btn" data-dl="/api/skills/${sel.id}/export" data-name="${esc(sel.name)}.inkyskill">Download file</button>
          ${S.settings.n8n_connected ? `<button class="btn" id="sendn8n">${logo("n8n", 20)}Send to n8n</button>` : ""}<button class="btn" data-dl="/api/skills/${sel.id}/export?format=n8n" data-name="${esc(sel.name)}.n8n.json">${S.settings.n8n_connected ? "Download for n8n" : "Export to n8n"}</button><button class="btn hot" id="delsk">Delete skill</button></aside></div>` : `<p class="muted">No skills yet.</p>`}
      <div class="card"><b>Learn a new site</b><div class="grid2"><input class="f" id="lurl" placeholder="https://…" value="${esc(b.start_url || "")}"><input class="f" id="lgoal" placeholder="What to do there" value="${esc(b.goal || "")}"></div><div><button class="btn p" id="learn">Learn it once</button></div></div>`;
    $$("[data-sk]").forEach((x) => (x.onclick = () => { this.skillSel = +x.dataset.sk; this.tab_skills(tb); }));
    $$("[data-ask]").forEach((x) => (x.onclick = async () => { const steps = sel.steps.map((s, i) => (i === +x.dataset.ask ? { ...s, approved_always: false } : s)); await patch(`/api/skills/${sel.id}`, { steps }); this.refresh(); }));
    if ($("#runsk")) $("#runsk").onclick = () => post(`/api/bots/${b.id}/run`, { skill: sel.id }).then(() => (location.hash = `#/bot/${b.id}/computer`)).catch((e) => toast(e.message));
    if ($("#sendn8n")) $("#sendn8n").onclick = async () => { $("#sendn8n").disabled = true; const r = await post(`/api/skills/${sel.id}/send-n8n`); toast(r.text); $("#sendn8n").disabled = false; };
    if ($("#delsk")) $("#delsk").onclick = async () => { if (await confirmBox(`Delete “${sel.name}”?`, "Delete", true)) { await del(`/api/skills/${sel.id}`); this.refresh(); } };
    $("#learn").onclick = () => post(`/api/bots/${b.id}/learn`, { url: $("#lurl").value, goal: $("#lgoal").value }).then(() => (location.hash = `#/bot/${b.id}/computer`)).catch((e) => toast(e.message));
    $("#skf").onchange = async (e) => {
      const f = e.target.files[0]; if (!f) return;
      e.target.value = "";
      try { await post(`/api/bots/${b.id}/skills/import`, JSON.parse(await f.text())); this.refresh(); }
      catch (err) { toast(`That isn’t an Inky skill file (${err.message})`); }
    };
  },

  tab_settings(tb) {
    const b = this.data.bot, s = b.schedule || {};
    tb.innerHTML = `<div class="gridfit">
      <div class="card"><b>Schedule</b><span class="seg" id="every">${[[0, "When I ask"], [15, "Every 15 min"], [60, "Hourly"], [1440, "Daily"]].map(([v, t]) => `<button data-v="${v}" class="${(s.every_minutes || 0) === v ? "on" : ""}">${t}</button>`).join("")}</span>
        <div class="between small"><span>Summary at</span><input class="f" type="time" id="sum" aria-label="Summary at" value="${esc(s.summary_at || "")}" style="width:130px;height:36px"></div>
        <div class="between small"><span>Quiet hours</span><span class="row"><input class="f" type="time" id="qf" aria-label="Quiet from" value="${esc(s.quiet_from || "")}" style="width:120px;height:36px"><input class="f" type="time" id="qt" aria-label="Quiet until" value="${esc(s.quiet_to || "")}" style="width:120px;height:36px"></span></div>
        <span class="small muted">Skills replay with no AI, so checking often costs nothing extra.</span></div>
      <div class="card"><b>What it may do</b>${(b.rules || []).map((r, i) => `<div class="rule ${r.kind === "ask" ? "ask" : ""}"><b>${{ own: "On its own", ask: "Ask you first", never: "Never", filter: "Keep only" }[r.kind] || r.kind}</b><span>${esc(r.text)}</span>${r.kind === "filter" || i > 2 ? `<button class="chip" data-rr="${i}" style="border:0;cursor:pointer">remove</button>` : "<span></span>"}</div>`).join("")}
        <input class="f" id="rule" placeholder="Add a rule in your words, e.g. skip ground floor flats"></div>
      <div class="card"><div class="head"><b>It remembers</b><span class="small muted">${(b.memory || []).length} things about you</span></div><a class="btn s" href="#/bot/${b.id}/about" style="align-self:flex-start">About you</a></div>
      <div class="card"><b>Where it works</b><span class="seg" id="mode"><button data-m="own" class="${b.mode !== "screen" ? "on" : ""}">Its own computer</button><button data-m="screen" class="${b.mode === "screen" ? "on" : ""}" ${S.settings.screen_allowed ? "" : "disabled title='Allow bots on your screen in Settings first'"}>A window on your screen</button></span>
        <span class="small muted">${b.mode === "screen" ? "It opens a visible window on your desktop with the coral frame. Move your mouse to pause it, Esc to stop, ⌥C to chat." : "A private browser, streamed here. Your screen stays yours."}</span>
        <a class="btn s" href="#/computers">Move to another computer</a></div>
      <div class="card" style="grid-column:1/-1"><div class="head"><b>Automations · hand results to Claude Code, Codex or any connector</b><a class="small" href="#/connectors">Connectors</a></div>
        ${(b.automations || []).map((a, i) => `<div class="rule"><b>${a.when === "every_run" ? "Every run" : "New results"}</b><span>${esc(a.label || "")} → <span class="mono">${esc(a.server)}.${esc(a.tool)}</span>${a.approved_always ? ' <span class="badge">always allowed</span>' : ""}</span><button class="chip" data-au="${i}" style="border:0;cursor:pointer">remove</button></div>`).join("") || `<span class="small muted">None yet. Or just ask it in the chat, e.g. “when you find new flats, ask Claude Code to add them to flats.md”.</span>`}
        <div class="grid4"><select class="f" id="aw" aria-label="When"><option value="new_results">When there are new results</option><option value="every_run">After every run</option></select><select class="f" id="as" aria-label="Connector"></select><select class="f" id="at" aria-label="Tool"></select><input class="f" id="al" aria-label="Label" placeholder="Label"></div>
        <textarea class="f mono" id="aa" aria-label="Arguments as JSON" rows="2" placeholder='Arguments as JSON, e.g. {"description":"flats","prompt":"Add these to ~/flats.md: {{new_json}}"}'></textarea><div><button class="btn s" id="addauto">Add automation</button></div></div>
      <div class="card" style="grid-column:1/-1"><div class="between"><span><b>Delete ${esc(b.name)}</b><br><span class="small muted">Removes its skills, memory, results and computer. Can’t be undone.</span></span><button class="btn hot" id="delbot">Delete bot…</button></div></div></div>`;
    const save = (p) => patch(`/api/bots/${b.id}`, p).then(refreshSoon);
    $$("#every button").forEach((x) => (x.onclick = () => save({ schedule: { ...s, every_minutes: +x.dataset.v } })));
    $("#sum").onchange = () => save({ schedule: { ...s, summary_at: $("#sum").value || null } });
    $("#qf").onchange = $("#qt").onchange = () => save({ schedule: { ...s, quiet_from: $("#qf").value, quiet_to: $("#qt").value } });
    $("#rule").onkeydown = (e) => { if (e.key === "Enter" && e.target.value.trim()) { post(`/api/bots/${b.id}/chat`, { text: `New rule: ${e.target.value}` }).then(refreshSoon); e.target.value = ""; } };
    $$("[data-rr]").forEach((x) => (x.onclick = () => { const r = b.rules[+x.dataset.rr]; save({ rules: b.rules.filter((_, i) => i !== +x.dataset.rr), filters: (b.filters || []).filter((f) => (f.text || "") !== r.text) }); }));

    $$("#mode button").forEach((x) => (x.onclick = () => save({ mode: x.dataset.m })));
    $$("[data-au]").forEach((x) => (x.onclick = () => save({ automations: b.automations.filter((_, i) => i !== +x.dataset.au) })));
    $("#delbot").onclick = () => goodbye(b);
    get("/api/mcp").then(({ servers }) => {
      const on = servers.filter((x) => x.enabled);
      $("#as").innerHTML = on.map((x) => `<option value="${x.name}">${esc(x.label)}</option>`).join("") || `<option value="">Connect one first</option>`;
      const fillTools = () => { const sv = on.find((x) => x.name === $("#as").value); $("#at").innerHTML = (sv ? sv.tools : []).map((t) => `<option>${esc(t)}</option>`).join(""); };
      $("#as").onchange = fillTools; fillTools();
    });
    $("#addauto").onclick = () => {
      let args = {};
      try { args = JSON.parse($("#aa").value || "{}"); } catch (e) { return toast("Arguments must be JSON"); }
      save({ automations: [...(b.automations || []), { when: $("#aw").value, server: $("#as").value, tool: $("#at").value, args, label: $("#al").value || $("#at").value }] });
    };
  },

  tab_activity(tb) {
    const b = this.data.bot;
    tb.innerHTML = `<div class="card" style="padding:6px 18px"><div class="list">${this.data.events.map((e) => `<div class="ev"><span class="mono small muted">${ago(e.ts)}</span>${botCritter(b, 22)}<span>${esc(e.text)}</span><span class="badge">${esc(e.kind)}</span></div>`).join("") || `<p class="muted">Nothing yet.</p>`}</div></div>
      <div class="card"><b>Runs</b><table class="t"><thead><tr><th>When</th><th>Kind</th><th>Status</th><th>Results</th><th>New</th><th>AI calls</th><th>Seconds</th></tr></thead><tbody>${this.data.runs.map((r) => `<tr><td>${ago(r.ts)}</td><td>${esc(r.kind)}</td><td>${esc(r.status)}</td><td>${r.items ?? ""}</td><td>${r.new ?? ""}</td><td>${r.ai_calls ?? ""}</td><td>${r.seconds ?? ""}</td></tr>`).join("")}</tbody></table></div>`;
  },

  // ---- Call: speak with the bot (browser speech), it keeps working
  tab_diary(tb) {
    const g = this.data.growth, b = this.data.bot, next = g.next;
    const pct = next ? Math.min(100, Math.round((g.runs / next.at) * 100)) : 100;
    const tile = (v, k) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`;
    tb.innerHTML = `<div class="grid4">${tile(g.days, g.days === 1 ? "day on the job" : "days on the job")}${tile(g.streak, "day streak")}${tile(g.hours_saved + " h", "of your time saved")}${tile(g.ai_saved, "AI calls saved")}</div>
      <div class="card"><div class="between"><b>Level ${g.level}</b><span class="small muted">${g.runs} good runs</span></div>
        <div style="height:10px;border-radius:5px;background:var(--panel);overflow:hidden"><div style="height:100%;width:${pct}%;background:var(--coral);border-radius:5px"></div></div>
        <span class="small muted">${next ? `${next.at - g.runs} more runs to unlock the ${esc(next.acc)} ${critter(b.look.kind, b.look.color, next.acc, 22)}` : "Everything unlocked. A true veteran."}</span>
        ${g.unlocked.length ? `<span class="row wrap small">Unlocked: ${g.unlocked.map((a) => `<span class="chip">${critter(b.look.kind, b.look.color, a, 20)} ${esc(a)}</span>`).join("")} <a href="#/look/${b.id}">wear one</a></span>` : ""}</div>
      <div class="col"><b>Diary</b>${(this.data.diary || []).map((d) => `<div class="card"><span class="mono small muted">${esc(d.date)}</span><span>${esc(d.text)}</span></div>`).join("") || `<span class="small muted">${esc(b.name)} writes a short entry each evening, on days something happened.</span>`}</div>`;
  },

  tab_about(tb) {
    const b = this.data.bot, mem = b.memory || [];
    const save = (memory) => patch(`/api/bots/${b.id}`, { memory }).then(() => this.refresh());
    tb.innerHTML = `<div class="card"><div class="head"><b>Things ${esc(b.name)} knows about you</b><span class="small muted">only on this computer</span></div>
      ${mem.map((m, i) => `<div class="row"><input class="f grow" data-mi="${i}" value="${esc(m.text)}" aria-label="Memory ${i + 1}"><button class="btn s" data-fg="${i}">Forget</button></div>`).join("") || `<span class="small muted">Nothing yet. Tell it things in the chat, like “I prefer Libertà”.</span>`}
      <input class="f" id="mem" placeholder="Tell it something to remember"></div>`;
    $$("[data-mi]", tb).forEach((x) => (x.onchange = () => save(mem.map((m, i) => (i === +x.dataset.mi ? { ...m, text: x.value.trim() } : m)).filter((m) => m.text))));
    $$("[data-fg]", tb).forEach((x) => (x.onclick = () => save(mem.filter((_, i) => i !== +x.dataset.fg))));
    $("#mem").onkeydown = (e) => { if (e.key === "Enter" && e.target.value.trim()) { save([...mem, { text: e.target.value.trim(), ts: Date.now() / 1000 }]); e.target.value = ""; } };
  },

  tab_call(tb, first) {
    const b = this.data.bot;
    if (!first && $("#callbox")) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    tb.innerHTML = `<div class="row" style="align-items:stretch;gap:18px;flex:1"><section class="call" id="callbox" aria-label="Call with ${esc(b.name)}">
      <div class="between" style="align-self:stretch"><span class="small" style="color:#C9C5BD">Call with ${esc(b.name)}</span><span class="mono small" id="ctime">0:00</span></div>
      <div class="rings" id="rings"><span style="width:170px;height:170px"></span><span style="width:220px;height:220px"></span><span style="width:260px;height:260px"></span>${botCritter(b, 130)}</div>
      <b style="font-size:26px">${esc(b.name)}</b><span class="small" style="color:#F2957C" id="cstate">${SR ? "allow the microphone to talk…" : "speech isn’t available in this browser: type instead"}</span>
      <div id="trans" style="align-self:stretch;padding:14px 16px;border-radius:16px;background:rgba(255,255,255,.06);display:flex;flex-direction:column;gap:8px;min-height:120px;max-height:260px;overflow:auto;font-size:14px"></div>
      <div class="row" style="align-self:stretch"><label class="vh" for="ctype">Type instead</label><input class="f" id="ctype" placeholder="Type instead…" style="background:rgba(255,255,255,.08);border-color:transparent;color:#fff"></div>
      <div class="row" style="gap:26px;margin-top:auto"><button class="callbtn" id="mute" aria-label="Mute">${icon("micoff", 22)}</button><button class="callbtn on" id="spk" aria-label="Speaker">${icon("speaker", 22)}</button><a class="callbtn end" href="#/bot/${b.id}/computer" aria-label="End call">${icon("phone", 22)}</a></div></section>
      <aside class="col" style="width:320px;flex-shrink:0"><div class="card"><b>${b.step ? "It keeps working" : "Its computer"}</b><div class="thumb" style="height:160px"><img id="callimg" src="${screenUrl(b.id)}" alt=""></div><span class="small muted">${esc(b.step || "idle")}</span></div>
      <div class="card small"><b>Voice</b><span>${b.look.voice === "off" ? "Replies are text only (Make it yours → Voice)." : `Replies are spoken (${esc(b.look.voice || "soft")}). Changes it hears still show up as actions you can see in the chat.`}</span></div></aside></div>`;
    const t0 = Date.now();
    const tick = setInterval(() => { const s = Math.floor((Date.now() - t0) / 1000); if ($("#ctime")) $("#ctime").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; if ($("#callimg")) $("#callimg").src = screenUrl(b.id); }, 1000);
    const line = (who, text) => { const d = document.createElement("div"); d.innerHTML = `<b style="color:${who === "you" ? "#A8A49C" : "#F2957C"}">${who === "you" ? "You" : esc(b.name)}</b> ${esc(text)}`; $("#trans").appendChild(d); $("#trans").scrollTop = 1e9; };
    let speaking = true, muted = false, rec = null, talking = false;
    const hear = () => { if (rec && !muted && !talking && $("#callbox")) try { rec.start(); } catch (e) {} };
    const say = (text) => {
      if (!speaking || b.look.voice === "off" || !window.speechSynthesis) return;
      const u = new SpeechSynthesisUtterance(text);
      u.pitch = b.look.voice === "bright" ? 1.25 : 0.95; u.rate = 1.02;
      talking = true; if (rec) try { rec.abort(); } catch (e) {}  // don't hear its own voice through your speakers
      $("#rings").classList.add("talk");
      u.onend = u.onerror = () => { talking = false; $("#rings") && $("#rings").classList.remove("talk"); hear(); };
      speechSynthesis.speak(u);
    };
    const ask = async (text) => {
      line("you", text);
      $("#cstate").textContent = "thinking…";
      try { const r = await post(`/api/bots/${b.id}/chat`, { text, source: "call" }); line("bot", r.reply); $("#cstate").textContent = "speaking"; say(r.reply); }
      catch (e) { line("bot", e.message); }
      setTimeout(() => $("#cstate") && ($("#cstate").textContent = !rec ? "type to talk" : muted ? "muted" : "listening…"), 800);
    };
    $("#ctype").onkeydown = (e) => { if (e.key === "Enter" && e.target.value.trim()) { ask(e.target.value.trim()); e.target.value = ""; } };
    $("#spk").onclick = (e) => { speaking = !speaking; e.currentTarget.classList.toggle("on", speaking); if (!speaking) speechSynthesis.cancel(); };
    if (SR) {
      rec = new SR(); rec.continuous = true; rec.interimResults = false; rec.lang = navigator.language || "en-US";
      rec.onresult = (e) => { const r = e.results[e.results.length - 1], t = r[0].transcript.trim(); if (r.isFinal && !talking && t) ask(t); };
      rec.onend = hear;
      rec.onstart = () => { if ($("#cstate") && !talking) $("#cstate").textContent = "listening…"; };
      rec.onerror = (e) => {
        if (e.error !== "not-allowed" && e.error !== "service-not-allowed" && e.error !== "audio-capture") return;
        muted = true; if ($("#cstate")) $("#cstate").textContent = e.error === "audio-capture" ? "no microphone found: type instead" : "microphone blocked: type instead";
      };
      try { rec.start(); } catch (e) {}
    }
    $("#mute").onclick = (e) => { muted = !muted; e.currentTarget.classList.toggle("on", muted); $("#cstate").textContent = muted ? "muted" : "listening…"; if (rec) muted ? rec.stop() : rec.start(); };
    line("bot", `Hi, it’s ${b.name}. ${b.step ? `I’m on step ${b.step_n}: ${b.step}.` : "What can I do?"}`);
    this.callEnd = () => { clearInterval(tick); muted = true; if (rec) try { rec.stop(); } catch (e) {} if (window.speechSynthesis) speechSynthesis.cancel(); };
  },
};

// ================================================================ rituals: hatch, goodbye, first-run tour
function hatch(b, intro) {
  const o = document.createElement("div");
  o.className = "ritual";
  o.innerHTML = `<div class="splash">${[0, 1, 2, 3, 4, 5].map((i) => `<i style="--a:${i * 60}deg;--d:${i * 40}ms"></i>`).join("")}</div>
    <div class="hatchling">${botCritter({ ...b, status: "idle", needs: 0 }, 150).replace('data-mood="calm"', 'data-mood="happy"')}</div>
    <div class="card bubble">${esc(intro || `Hi! I'm ${b.name}.`)}</div><span class="small muted">click anywhere to start</span>`;
  document.body.appendChild(o);
  SOUND.play("rise", b);
  setTimeout(() => confetti(), 700);
  const close = () => { o.classList.add("out"); setTimeout(() => o.remove(), 300); };
  o.onclick = close;
  setTimeout(close, 4200);
}

function goodbye(b) {
  const packed = { octopus: "tentacles", cat: "whiskers", blob: "goo" }[(b.look || {}).kind] || "things";
  modal(`<div class="col" style="align-items:center;text-align:center;gap:10px"><div id="byecrit">${botCritter({ ...b, status: "needs_you", needs: 1, need_kind: "decision" }, 110)}</div>
    <h2>${esc(b.name)} packed its ${packed}.</h2><span class="small muted">Delete for good? Its skills, memory and results go too. This can’t be undone.</span>
    <div class="row"><button class="btn" id="byeno">Keep ${esc(b.name)}</button><button class="btn hot" id="byeyes">Delete</button></div></div>`, () => {
    $("#byeno").onclick = closeModal;
    $("#byeyes").onclick = async () => {
      $("#byecrit").classList.add("bye");
      await new Promise((r) => setTimeout(r, calmMotion() ? 0 : 650));
      closeModal(); await del(`/api/bots/${b.id}`); await loadState(); location.hash = "#/bots";
      toast(`Goodbye from ${b.name}`);
    };
  });
}

const TOUR = [
  ["#nav .navbot", "This is your bot. Its critter shows how it’s doing: busy, asleep at night, or waving when it needs you."],
  ["#cards", "Each bot has its own computer. When one is working you can watch it live, take over and hand back."],
  ["#nav .needlink", "When a bot needs a yes, it waits here. Nothing that can’t be undone happens without you."],
  [null, "Press ⌘K (or ⌥Space in the Inky app) to talk to any bot from anywhere. That’s it, have fun!"],
];
function tour(i = 0) {
  $$(".coach").forEach((x) => x.remove());
  if (i >= TOUR.length) { try { localStorage.setItem("inkyTour", "1"); } catch (e) {} return; }
  const [sel, text] = TOUR[i], t = sel && $(sel), r = t && t.getBoundingClientRect();
  const c = document.createElement("div");
  c.className = "coach";
  c.innerHTML = `${r ? `<div class="ring" style="left:${r.left - 6}px;top:${r.top - 6}px;width:${r.width + 12}px;height:${r.height + 12}px"></div>` : ""}
    <div class="card tip" style="${r ? `left:${Math.min(innerWidth - 340, r.right + 16)}px;top:${Math.max(16, Math.min(innerHeight - 180, r.top))}px` : "left:50%;top:40%;transform:translate(-50%,-50%)"}">
      <span class="row">${critter("octopus", "#E86F51", "none", 36, "happy")}<span class="mono small muted">${i + 1} of ${TOUR.length}</span></span><span>${esc(text)}</span>
      <div class="row" style="justify-content:flex-end"><button class="btn s" id="tskip">Skip</button><button class="btn s p" id="tnext">${i === TOUR.length - 1 ? "Done" : "Next"}</button></div></div>`;
  document.body.appendChild(c);
  $("#tnext").onclick = () => tour(i + 1);
  $("#tskip").onclick = () => tour(TOUR.length);
}

async function answerNeed(id, decision) {
  try { await post(`/api/needs/${id}`, { decision }); toast(`You chose “${decision}”`); } catch (e) { toast(e.message); }
  if (decision === "Open its computer" || decision === "Show me once") { const n = await get("/api/needs?status=resolved"); const x = n.needs.find((y) => y.id === id); if (x) location.hash = `#/bot/${x.bot_id}/computer`; }
  refreshSoon(50);
}

// ================================================================ needs you
VIEWS.team = {  // bots talking to each other, morning papers, milestones
  async show(el) { this.el = el; await this.refresh(); },
  async refresh() {
    const { feed } = await get("/api/team?limit=120");
    const by = (id) => S.bots.find((b) => b.id === id) || { look: {}, status: "idle", schedule: {} };
    const line = (f) => {
      const speaker = f.kind === "peer" ? by(f.sender_id) : by(f.bot);
      const who = f.kind === "peer" ? `${esc(f.sender)} → ${esc(f.name)}` : f.kind === "paper" ? `${esc(f.name)} · morning paper` : esc(f.name);
      return `<div class="m">${botCritter(speaker, 30)}<div class="body"><span class="small" style="font-weight:600">${who} <span class="muted" style="font-weight:400">${ago(f.ts)}</span></span><span>${esc(f.text)}</span></div></div>`;
    };
    this.el.innerHTML = `${mobileBar("Team")}<div class="page"><div><h1>Team</h1><p class="lede">Your bots talk to each other here: hand-offs, morning papers and milestones. Anything that can’t be undone still waits for you.</p></div>
      <div class="card"><div class="msgs" style="display:flex;flex-direction:column-reverse;gap:12px">${feed.map(line).join("") || `<span class="small muted">Quiet so far. Tell a bot “ask Flat Checker to …” and they’ll talk here.</span>`}</div></div></div>`;
  },
};

VIEWS.needs = {
  async show(el, _, qs) { this.el = el; this.tab = qs.get("tab") || "decisions"; await this.refresh(); },
  async refresh() {
    const { needs } = await get("/api/needs");
    const dec = needs.filter((n) => n.kind === "decision"), prob = needs.filter((n) => n.kind !== "decision");
    const list = this.tab === "decisions" ? dec : prob;
    const botOf = (n) => S.bots.find((b) => b.id === n.bot_id) || { look: {}, name: n.bot };
    const health = this.tab === "problems" ? (await get("/api/health")).health : [];
    this.el.innerHTML = `${mobileBar("Needs you")}<div class="page"><div><h1>Needs you</h1><p class="lede">Your bots decide small things on their own. They stop here before anything that can’t be undone, and when something breaks.</p></div>
      <span class="seg" style="align-self:flex-start"><a href="#/needs?tab=decisions" class="${this.tab === "decisions" ? "on" : ""}">Decisions · ${dec.length}</a><a href="#/needs?tab=problems" class="${this.tab === "problems" ? "on" : ""}">Problems · ${prob.length}</a></span>
      <div class="row" style="align-items:flex-start;gap:28px"><section class="col grow" style="gap:12px">${list.map((n, i) => { const b = botOf(n); return `<div class="card need ${i === 0 && this.tab === "decisions" ? "hot" : ""}">
        <div class="between"><span class="row small" style="font-weight:600">${botCritter(b, 22)}${esc(b.name)} · ${esc(n.kind.replace("_", " "))}</span><span class="mono small muted">${ago(n.ts)}</span></div>
        <b style="font-size:16.5px">${esc(n.title)}</b>${n.body ? `<span class="small muted" style="line-height:1.5">${esc(n.body)}</span>` : ""}
        <div class="opts">${((n.options || []).length ? n.options : ["Dismiss"]).map((o, j) => `<button class="btn ${j === 0 ? "p" : ""}" data-need="${n.id}" data-o="${esc(o)}">${esc(o)}</button>`).join("")}<a class="btn" href="#/bot/${n.bot_id}/computer">Watch it</a></div></div>`; }).join("") || `<p class="muted">Nothing here. Your bots are fine.</p>`}</section>
      <aside class="col" style="width:330px;flex-shrink:0">${this.tab === "decisions" ? `<div class="card panel"><b>Rules for every bot</b><div class="rule"><b>On its own</b><span>Read, search, take notes</span></div><div class="rule ask"><b>Ask you first</b><span>Send, post, reply, delete, submit forms, sign up, hand work to connectors</span></div><div class="rule"><b>Never</b><span>Buy or pay</span></div><div class="rule"><b>Passwords</b><span>You type them</span></div><span class="small muted">Change a bot’s rules by telling it, or in its Settings.</span></div>`
        : `<div class="card panel small"><b>How bots handle problems</b><span>1. Cheap fixes first: wait, find the button by its name.</span><span>2. Ask the model once, and only act when it’s sure.</span><span>3. Otherwise stop, tell you here and on your phone.</span><span>4. Keep the parts that still work running.</span></div>
        <div class="card"><b>Health</b>${health.map((h) => `<div class="between small"><span>${esc(h.name)}</span><span style="color:${h.ok ? "var(--green-t)" : h.info ? "var(--muted)" : "var(--coral-t)"}">● ${esc(h.detail)}</span></div>`).join("")}</div>`}</aside></div></div>`;
    $$("[data-need]", this.el).forEach((x) => (x.onclick = () => answerNeed(+x.dataset.need, x.dataset.o)));
  },
};

// ================================================================ activity
VIEWS.activity = {
  async show(el) { this.el = el; await this.refresh(); },
  async refresh() {
    const a = await get("/api/activity");
    const w = a.week, botOf = (id) => S.bots.find((b) => b.id === id) || { look: {}, name: "Inky" };
    this.el.innerHTML = `${mobileBar("Activity")}<div class="page" style="background:var(--panel);min-height:100%;max-width:none"><div><h1>Activity</h1><p class="lede">Everything your bots did this week, and what it cost. Learning uses the AI; repeating doesn’t.</p></div>
      <div class="grid5"><div class="stat"><span>Runs</span><b>${w.runs}</b></div><div class="stat hot"><span>AI calls</span><b>${w.ai_calls}</b></div><div class="stat"><span>If it asked the AI every step</span><b>≈ ${w.if_ai_every_step}</b></div>
      <div class="stat"><span>Spent on AI</span><b>$${w.cost.toFixed(2)}</b></div><div class="stat"><span>Asked you</span><b>${w.asked}</b></div></div>
      <div class="card" style="padding:6px 18px"><div class="list">${a.events.map((e) => `<div class="ev"><span class="mono small muted">${ago(e.ts)}</span>${botCritter(botOf(e.bot_id), 24)}<span><b style="font-weight:500">${esc(e.bot || "")}</b> · ${esc(e.text)}</span><span class="badge ${["problem", "denied"].includes(e.kind) ? "hot" : ["fixed", "learned"].includes(e.kind) ? "good" : ""}">${esc(e.kind)}</span></div>`).join("") || `<p class="muted">Nothing yet.</p>`}</div></div>
      <span class="small muted">Every run leaves a log line. Nothing leaves your computers unless you connect something.</span></div>`;
  },
};

// ================================================================ adding a server (Computers and setup share this)
let foundTimer = null, onServerPaired = null;
function serverAdder(install) {
  return `<div class="col" style="gap:16px"><div id="found" class="col" style="gap:8px"></div>
    <div class="col" style="gap:8px"><b>Set it up over SSH</b><span class="small muted">If you can ssh into it with a key, Inky installs itself there and pairs. Nothing to type on the server.</span>
      <div class="row"><input class="f grow mono" id="sshtarget" placeholder="you@your-server" autocomplete="off" spellcheck="false" aria-label="SSH user and host"><button class="btn" id="sshgo">Set up</button></div><div class="col" id="sshprog" style="gap:4px" role="status"></div></div>
    <div class="col" style="gap:8px"><b>Or run this once on the server</b>
      <div class="row"><pre class="code grow" style="margin:0">${esc(install)}</pre><button class="btn s" id="copyinst">Copy</button></div>
      <span class="small muted">It prints a pair link. Paste it here, or the address and code:</span>
      <input class="f mono" id="pairurl" placeholder="inky://pair?…  or  http://192.168.1.20:8800" autocomplete="off" spellcheck="false" aria-label="Pair link or server address">
      <div class="row"><input class="f grow mono" id="paircode" placeholder="Pairing code (not needed with a link)" autocomplete="off" spellcheck="false" aria-label="Pairing code"><button class="btn" id="pairgo">Pair</button></div>
      <span class="small" id="pairmsg" role="status"></span></div></div>`;
}
function sayIn(sel, t, ok) { const m = $(sel); if (m) { m.textContent = t; m.className = "small " + (ok === true ? "good" : ok === false ? "bad" : "muted"); } }
function sshLine(m) {  // SSE "ssh" progress from the engine
  const box = $("#sshprog"); if (!box) return;
  const bad = m.step === "failed", last = box.lastElementChild;
  if (m.step === "installing" && last && last.dataset.step === "installing" && !/^Installing Inky/.test(m.text)) { $("span", last).textContent = m.text; return; }
  box.insertAdjacentHTML("beforeend", `<div class="chk" data-step="${esc(m.step)}"><i class="${bad ? "bad" : "ok"}">${bad ? "!" : m.step === "done" ? "✓" : "·"}</i><span>${esc(m.text || m.step)}</span></div>${bad && m.fix ? `<div class="small" style="padding-left:28px"><b>${esc(m.fix)}</b></div>` : ""}`);
  if (m.step === "done" || bad) $("#sshgo").disabled = false;
  if (m.step === "done") { SOUND.play("chime"); confetti(); if (onServerPaired) onServerPaired(); }
}
function bindServerAdder(install, onPaired) {
  onServerPaired = onPaired;
  $("#copyinst").onclick = async () => { try { await navigator.clipboard.writeText(install); $("#copyinst").textContent = "Copied"; } catch (e) { toast("Select the line and copy it with ⌘C."); } };
  const paired = () => { sayIn("#pairmsg", "✓ Paired. Its bots show up in Computers.", true); SOUND.play("chime"); if (onPaired) onPaired(); };
  const pair = async () => {
    const url = $("#pairurl").value.trim(), code = $("#paircode").value.trim();
    if (!url) return sayIn("#pairmsg", "Paste the pair link, or the address and code.", false);
    if (!url.startsWith("inky://") && !code) return sayIn("#pairmsg", "Put in the code it printed too.", false);
    sayIn("#pairmsg", "Pairing…");
    try { await post("/api/computers", { url, code }); paired(); } catch (e) { sayIn("#pairmsg", e.message, false); }
  };
  $("#pairgo").onclick = pair;
  $("#paircode").onkeydown = (e) => { if (e.key === "Enter") pair(); };
  $("#pairurl").onkeydown = (e) => { if (e.key === "Enter") pair(); };
  const ssh = async () => {
    const t = $("#sshtarget").value.trim(); if (!t) return;
    $("#sshprog").innerHTML = ""; $("#sshgo").disabled = true;
    try { await post("/api/computers/ssh", { target: t }); } catch (e) { sshLine({ step: "failed", text: e.message }); }
  };
  $("#sshgo").onclick = ssh;
  $("#sshtarget").onkeydown = (e) => { if (e.key === "Enter") ssh(); };
  let shown = "";
  const drawFound = async () => {
    const box = $("#found"); if (!box) return clearInterval(foundTimer);
    let found = [];
    try { ({ found } = await get("/api/computers/found")); } catch (e) { return; }
    const key = found.map((f) => f.url).join();
    if (key === shown) return;  // don't wipe a code you're typing
    shown = key;
    box.innerHTML = found.length ? `<b>Found ${found.some((f) => f.via === "tailscale") ? "on your network and tailnet" : "on your network"}</b>` + found.map((f) => `<div class="card lrow" style="padding:10px 12px">${logo(f.via === "tailscale" ? "tailscale" : "linux", 30)}<span class="grow"><b>${esc(f.name)}</b><br><span class="mono small muted">${esc(f.host || f.url)}${f.via === "tailscale" ? " · works away from home" : ""}</span></span><input class="f mono" data-fcode="${esc(f.url)}" placeholder="Its code" style="width:120px" aria-label="Pairing code for ${esc(f.name)}"><button class="btn s" data-fpair="${esc(f.url)}">Pair</button></div>`).join("") : "";
    $$("[data-fpair]", box).forEach((b) => (b.onclick = async () => {
      const code = $(`[data-fcode="${b.dataset.fpair}"]`).value.trim();
      if (!code) return toast("Type the code that server printed when you installed it.");
      try { await post("/api/computers", { url: b.dataset.fpair, code }); shown = ""; paired(); drawFound(); } catch (e) { toast(e.message); }
    }));
  };
  clearInterval(foundTimer); drawFound(); foundTimer = setInterval(drawFound, 5000);
}

// ================================================================ computers
VIEWS.computers = {
  async show(el) { this.el = el; await this.refresh(); },
  onEvent(m) { if (m.kind === "move") this.progress(m); if (m.kind === "ssh") sshLine(m); },
  leave() { clearInterval(foundTimer); },
  progress(m) {
    const box = $("#moveprog"); if (!box) return;
    box.insertAdjacentHTML("beforeend", `<div class="chk"><i class="${m.step === "failed" || m.step === "check_failed" ? "bad" : "ok"}">${m.step === "failed" ? "!" : "✓"}</i><span>${esc(m.text || m.step)}</span></div>`);
    if (m.step === "done" || m.step === "failed") $("#moveclose").classList.remove("hidden");
  },
  async refresh() {
    if ($("#moveprog")) return;
    const [{ computers, pair_code }, { install }] = await Promise.all([get("/api/computers"), get("/api/setup")]);
    this.el.innerHTML = `${mobileBar("Computers")}<div class="page"><div class="between"><div><h1>Computers</h1><p class="lede">Where your bots’ browsers run. Each bot gets its own sandbox, never your screen.</p></div><button class="btn" id="addsrv">Add a server</button></div>
      <div class="grid2">${computers.map((c) => `<div class="card"><div class="row">${logo({ Darwin: "apple", Windows: "windows" }[c.os] || "linux", 40)}<div class="grow"><b style="font-size:18px">${esc(c.name)}</b><div class="mono small muted">${c.kind === "local" ? `this computer${c.docker && c.docker.running ? ` · ${logo("docker", 18)} Docker ${esc(c.docker.version)}` : ""}` : esc(c.url)} · ${c.bots.length} bots</div></div><span class="pill ${c.ok ? "live" : "hot"}"><i style="background:${c.ok ? "var(--green)" : "var(--coral)"}"></i>${c.ok ? (c.kind === "local" ? "awake" : "reachable") : "can’t reach it"}</span></div>
        <div class="grid2">${c.bots.map((b) => `<a class="botcard" style="padding:10px;gap:8px" href="${c.kind === "local" ? `#/bot/${b.id}/computer` : "#/bots"}"><div class="thumb ${["working", "learning"].includes(b.status) ? "" : "idle"}" style="height:90px">${["working", "learning"].includes(b.status) && c.kind === "local" ? `<img src="${screenUrl(b.id)}" alt="">` : esc(b.status.replace("_", " "))}</div><span class="row small">${botCritter(b, 22)}<b class="grow">${esc(b.name)}</b>${c.kind === "local" && b.status !== "moved" && computers.length > 1 ? `<button class="btn s" data-move="${b.id}">Move</button>` : ""}</span></a>`).join("") || `<span class="small muted">No bots here</span>`}</div>
        ${c.kind === "local" ? `<div class="card panel small"><span>This computer’s pairing code: <b class="mono">${esc(pair_code)}</b>. Type it on another Inky to send bots here.</span></div>` : `<button class="btn s hot" data-unpair="${c.id}" style="align-self:flex-start">Unpair</button>`}</div>`).join("")}</div>
      <div class="card panel"><div class="between"><span><b>Your own screen · ${S.settings.screen_allowed ? "allowed" : "off"}</b><br><span class="small muted">Let a bot use a visible browser window on your screen, with the coral frame and ask-first rules. Esc stops it any time.</span></span><a class="btn" href="#/setup/4">${S.settings.screen_allowed ? "Change" : "Allow"}</a></div></div>
      <section class="card" id="adder"><h2>Add a server</h2><span class="small muted">Any Linux server or spare Mac. 2 GB of memory runs about 3 bots, and they keep working while this computer sleeps.</span>${serverAdder(install)}</section></div>`;
    $("#addsrv").onclick = () => { $("#adder").scrollIntoView({ behavior: "smooth", block: "start" }); $("#sshtarget").focus({ preventScroll: true }); };
    bindServerAdder(install, () => setTimeout(() => this.refresh(), 600));
    $$("[data-unpair]").forEach((x) => (x.onclick = async (e) => { e.preventDefault(); await del(`/api/computers/${x.dataset.unpair}`); this.refresh(); }));
    $$("[data-move]").forEach((x) => (x.onclick = (e) => {
      e.preventDefault();
      const b = S.bots.find((y) => y.id === +x.dataset.move), targets = computers.filter((c) => c.kind === "remote" && c.ok);
      modal(`<div class="row">${botCritter(b, 44)}<h2>Move ${esc(b.name)}</h2></div><label class="l" for="mt">To</label><select class="f" id="mt">${targets.map((t) => `<option value="${t.id}">${esc(t.name)}</option>`).join("")}</select>
        <span class="small muted">It pauses between runs, packs its memory, skills and sign-ins, runs one check there, and only then leaves this computer.</span><div class="col" id="mvbox"></div>
        <div class="row" style="justify-content:flex-end"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn p" id="mgo">Move it</button></div>`, () => {
        $("#mgo").onclick = async () => { $("#mvbox").innerHTML = `<div class="col" id="moveprog"></div><button class="btn p hidden" id="moveclose" onclick="closeModal();VIEWS.computers.refresh()">Done</button>`; $("#mgo").disabled = true; await post(`/api/bots/${b.id}/move`, { computer: +$("#mt").value }); };
      });
    }));
  },
};

// ================================================================ models
VIEWS.models = {
  async show(el, [sub]) { this.el = el; this.sub = sub; await this.refresh(); },
  onEvent(m) { if (m.kind === "pull" && this.sub === "local") this.refresh(); },
  async refresh() { return this.sub === "local" ? this.local() : this.main(); },
  async main() {
    const m = await get("/api/models"), loc = await get("/api/models/local");
    const provs = m.providers;
    this.el.innerHTML = `${mobileBar("Models")}<div class="page"><div class="between"><div><h1>Models</h1><p class="lede">Bots only use a model to learn a job or understand you. Repeating a job uses none.</p></div><span class="row"><a class="btn" href="#/models/local">Add a local model</a><a class="btn p" href="#/keys">Add an API key</a></span></div>
      <section class="card"><div class="list">${Object.entries(m.role_labels).map(([r, label]) => { const v = m.roles[r] || {}; return `<div class="row" style="padding:10px 0"><span class="col grow" style="gap:2px"><b>${esc(label)}</b><span class="small muted">${{ learn: "reads the page and plans the steps, once per site", chat: "understands “euro only” and turns it into a rule", repair: "when a button moves and its name isn’t enough", smart: "when you choose “Try a smarter model”" }[r]}</span></span>
        <select class="f" style="width:180px" data-rp="${r}" aria-label="Provider for ${esc(label)}">${provs.map((p) => `<option value="${p.name}" ${v.provider === p.name ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</select>
        <input class="f mono" style="width:240px" data-rm="${r}" value="${esc(v.model || "")}" placeholder="model name" list="ml" aria-label="Model for ${esc(label)}"><button class="btn s" data-save="${r}" aria-label="Save ${esc(label)}">Save</button><button class="btn s" data-test="${r}" aria-label="Test ${esc(label)}">Test</button></div>`; }).join("")}</div>
        <datalist id="ml">${loc.ollama.models.map((x) => `<option value="${esc(x.name)}">`).join("")}<option value="z-ai/glm-5.3"><option value="claude-sonnet-5-5"></datalist><span class="small muted" id="testout"></span></section>
      <div class="grid2"><section class="card"><div class="head"><b>On this computer</b><span class="small muted">free · private · works offline</span></div>
        <div class="between"><span>Ollama</span><span class="small ${loc.ollama.running ? "" : "muted"}">${loc.ollama.running ? `running · ${loc.ollama.models.length} models` : loc.ollama.installed ? "installed, not running (ollama serve)" : "not installed"}</span></div>
        <div class="row wrap">${loc.ollama.models.map((x) => `<span class="chip">${esc(x.name)} · ${(x.size / 2 ** 30).toFixed(1)} GB</span>`).join("")}</div>
        <div class="between"><span>LM Studio</span><span class="small muted">${loc.lmstudio.installed ? "found" : "not found"}</span></div>
        <div class="between"><span>OpenAI-compatible server</span><span class="small muted mono">${esc(loc.custom.base)} · ${loc.custom.reachable ? "reachable" : "not reachable"}</span></div><a class="small" href="#/models/local" style="font-weight:600">Add a local model</a></section>
      <section class="card"><div class="head"><b>With your keys</b><span class="small muted">you pay the provider directly</span></div>${provs.filter((p) => !p.local).map((p) => `<div class="between"><span class="row">${providerLogo(p.name)}${esc(p.label)}</span>${p.key ? `<span class="small" style="color:var(--green-t)">● ${esc(p.key)}${m.errors[p.name] ? ` · error ${m.errors[p.name].status}` : ""}</span>` : `<a class="btn s" href="#/keys?p=${p.name}">Add key</a>`}</div>`).join("")}</section></div>
      <span class="small muted">Local models never leave this computer. Cloud models only see the page text a bot sends while learning, never your passwords or files.</span></div>`;
    $$("[data-save]").forEach((x) => (x.onclick = async () => { const r = x.dataset.save; await post("/api/models/role", { role: r, provider: $(`[data-rp="${r}"]`).value, model: $(`[data-rm="${r}"]`).value }); toast("Saved"); }));
    $$("[data-test]").forEach((x) => (x.onclick = async () => { const r = x.dataset.test; $("#testout").textContent = "Testing…"; const t = await post("/api/models/test", { provider: $(`[data-rp="${r}"]`).value, model: $(`[data-rm="${r}"]`).value }); $("#testout").textContent = t.ok ? `Works · replied “${t.reply}” in ${t.seconds} s` : `Didn’t work: ${t.reply}`; }));
  },
  async local() {
    const loc = await get("/api/models/local"), hw = loc.hardware;
    this.el.innerHTML = `${mobileBar("Local model")}<div class="page"><div class="row small"><a href="#/models" class="muted">Models</a><span class="muted">/</span><b>Add a local model</b></div>
      <div><h1>Add a local model</h1><p class="lede">Runs on this computer. Free, private, and it works offline.</p></div>
      <div class="card panel row">${icon("monitor", 18)}<span><b>${esc(hw.cpu || "This computer")}</b> · ${hw.memory_gb || "?"} GB memory · ${hw.disk_free_gb || "?"} GB free</span><span class="grow"></span><span>${loc.ollama.running ? "Ollama is running ●" : loc.ollama.installed ? "Ollama installed, not running: run “ollama serve”" : "Install Ollama from ollama.com"}</span></div>
      <div class="row" style="align-items:flex-start;gap:18px"><section class="col grow"><b>What fits, next to your running bots</b>${loc.catalog.map((c) => { const p = loc.pulls[c.name]; const pct = p && p.total ? Math.round(p.completed / p.total * 100) : null; return `<div class="card" style="padding:12px 16px"><div class="row"><span class="grow"><span class="row"><b class="mono">${c.name}</b><span class="small muted">${c.gb} GB</span>${c.badge ? `<span class="badge good">${c.badge}</span>` : ""}<span class="badge ${["too big", "not enough disk"].includes(c.fit) ? "hot" : c.fit === "fits well" ? "good" : ""}">${c.fit}</span></span><span class="small muted">${esc(c.about)}</span></span>
        ${c.installed ? `<span class="small" style="color:var(--green-t)">● installed</span>` : `<button class="btn s" data-pull="${c.name}" ${!loc.ollama.running || ["too big", "not enough disk"].includes(c.fit) ? "disabled" : ""}>Download</button>`}</div>${p && !c.installed ? `<div class="small mono muted">${esc(p.status || "")}${pct !== null ? ` · ${pct}%` : ""}</div>` : ""}</div>`; }).join("")}</section>
      <aside class="col" style="width:380px;flex-shrink:0"><div class="card"><b>Another runtime</b><span class="small muted">LM Studio, llama.cpp, vLLM or anything with an OpenAI-compatible address.</span><div class="row"><label class="vh" for="cb">Server address</label><input class="f mono" id="cb" value="${esc(loc.custom.base)}"><button class="btn s" id="cbs">Connect</button></div><span class="small muted">${loc.custom.reachable ? "● reachable" : "not reachable yet"}</span></div>
      <div class="card small"><b>Tip</b><span>Use a local model for chat and a cloud model for learning new sites, in Models.</span></div></aside></div></div>`;
    $$("[data-pull]").forEach((x) => (x.onclick = async () => { if (await confirmBox(`Download ${x.dataset.pull} (${loc.catalog.find((c) => c.name === x.dataset.pull).gb} GB) from ollama.com?`, "Download")) { await post("/api/models/pull", { name: x.dataset.pull }); toast("Downloading…"); } }));
    $("#cbs").onclick = async () => { await post("/api/models/custom", { base: $("#cb").value }); this.refresh(); };
  },
};

// ================================================================ API keys
VIEWS.keys = {
  async show(el, _, qs) { this.el = el; this.sel = qs.get("p") || this.sel || "anthropic"; await this.refresh(); },
  async refresh() {
    const { keys, backend } = await get("/api/keys");
    const cur = keys.find((k) => k.provider === this.sel) || keys[0];
    const where = { keychain: "this Mac’s Keychain", file: "a private file only you can read" }[backend];
    const hint = { openrouter: "openrouter.ai/settings/keys", anthropic: "console.anthropic.com → API keys", openai: "platform.openai.com/api-keys", gemini: "aistudio.google.com/apikey",
      groq: "console.groq.com/keys", xai: "console.x.ai", mistral: "console.mistral.ai/api-keys", custom: "your server’s settings", telegram: "Telegram → @BotFather → /newbot" }[cur.provider];
    this.el.innerHTML = `${mobileBar("API keys")}<div class="page"><div class="row small"><a href="#/models" class="muted">Models</a><span class="muted">/</span><b>API keys</b></div>
      <div><h1>API keys</h1><p class="lede">Paste a key once. It stays in ${where} and only goes to that provider. There is no Inky server.</p></div>
      <div class="row" style="align-items:flex-start;gap:22px"><section class="card panel" style="width:360px;flex-shrink:0;gap:2px;padding:10px">${keys.map((k) => `<a href="#/keys?p=${k.provider}" aria-label="${esc(k.label)}: ${k.source ? esc(k.source) : "not set"}" class="navlink ${k.provider === cur.provider ? "on" : ""}" style="min-height:48px">${providerLogo(k.provider)}<span class="grow">${esc(k.label)}</span><span class="small ${k.source ? "" : "muted"}" style="${k.source ? "color:var(--green-t)" : ""}">${k.source ? "● " + esc(k.source) : "not set"}</span></a>`).join("")}</section>
      <section class="card grow" style="padding:22px 26px;gap:16px"><h2 style="font-size:20px">${cur.source ? "Replace" : "Add"} your ${esc(cur.label)} key</h2>
        <div class="row small"><span class="mono muted">1</span><span>Make a key at <b>${esc(hint)}</b>.</span></div>
        <div class="row" style="align-items:flex-start"><span class="mono small muted">2</span><div class="col grow"><label for="key" class="small">Paste it here</label><div class="row"><input class="f" id="key" type="password" autocomplete="off" placeholder="${cur.source ? "A key is saved. Paste a new one to replace it." : "Paste the key"}"><button class="btn s" id="paste">Paste</button></div><span class="small" id="kstat"></span></div></div>
        ${cur.provider !== "telegram" ? `<div class="row" style="align-items:flex-start"><span class="mono small muted">3</span><div class="col grow"><label for="lim" class="small">Monthly limit (USD)</label><input class="f" id="lim" type="number" min="0" style="width:140px" value="${cur.limit ?? ""}" placeholder="none"></div></div>` : ""}
        <div class="between" style="border-top:1px solid var(--line);padding-top:14px"><span class="small muted row">${icon("lock", 15)}Never shown again. To change it, paste a new one.</span><span class="row">${cur.source === "keychain" || cur.source === "file" ? `<button class="btn hot" id="rm">Remove key</button>` : ""}<button class="btn p" id="save">Save key</button></span></div></section></div></div>`;
    $("#paste").onclick = async () => { try { $("#key").value = await navigator.clipboard.readText(); } catch (e) { toast("Your browser didn’t allow reading the clipboard. Paste with ⌘V."); } };
    $("#save").onclick = async () => {
      const v = $("#key").value.trim(); if (!v) return toast("Paste a key first");
      try {
        await post("/api/keys", { provider: cur.provider, key: v, limit: $("#lim") && $("#lim").value !== "" ? +$("#lim").value : null }); $("#key").value = "";
        if (CLOUD.includes(cur.provider)) {  // find a model this key really has and check it answers
          $("#kstat").textContent = "Saved. Checking which models it has…";
          const r = await post("/api/models/connect", { provider: cur.provider });
          toast(r.ok ? `Saved. Your bots now use ${r.model}.` : `Saved, but the test failed: ${r.reply}`);
        } else toast(`Saved your ${cur.label} key`);
        this.refresh();
      }
      catch (e) { $("#kstat").textContent = e.message; }
    };
    if ($("#rm")) $("#rm").onclick = async () => { if (await confirmBox(`Remove your ${cur.label} key?`, "Remove", true)) { await del(`/api/keys/${cur.provider}`); this.refresh(); } };
  },
};

// ================================================================ connectors
let tgPoll = null;
function waitForTelegram(bot, say) {  // after the token: poll until you send /start, then say hello. say(text, good)
  clearInterval(tgPoll);
  say(`Now open Telegram and send /start to @${bot}. Waiting…`);
  const t0 = Date.now();
  return new Promise((done) => {
    tgPoll = setInterval(async () => {
      if (Date.now() - t0 > 120e3) { clearInterval(tgPoll); say(`Didn’t hear from you yet. Send /start to @${bot}, then press Test.`, false); return done(false); }
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
VIEWS.connectors = {
  async show(el) { this.el = el; this.open = null; await this.refresh(); },
  leave() { clearInterval(tgPoll); },
  state(c) {
    if (c.kind === "builtin") return c.connected ? ["ok", "set up"] : c.name === "telegram" && /\/start/.test(c.detail) ? ["warn", "almost there"] : ["off", "not set up"];
    if (!c.installed) return ["off", "not installed"];
    if (c.connected) return ["ok", `connected · ${c.tools.length} tools`];
    if (c.signed_in === false) return ["warn", "signed out"];
    return ["", "ready to connect"];
  },
  card(c) {
    const [cls, txt] = this.state(c), editing = this.open === c.name || (c.kind === "builtin" && !c.connected && this.open === c.name);
    const btns = c.kind === "builtin"
      ? `${c.connected || c.detail.includes("/start") ? `<button class="btn s" data-test="${c.name}">Test</button>` : ""}<button class="btn s ${c.connected ? "" : "p"}" data-edit="${c.name}">${c.connected ? "Change" : "Set up"}</button>`
      : !c.installed ? (c.fix_url ? `<a class="btn s" href="${esc(c.fix_url)}" target="_blank" rel="noopener">How to install ↗</a>` : "")
      : c.connected ? `<button class="btn s" data-test="${c.name}">Test</button><button class="btn s" data-off="${c.name}">Disconnect</button>` : `<button class="btn s p" data-on="${c.name}">Connect</button>`;
    return `<div class="card conn" data-c="${c.name}"><div class="row">${logo(c.logo, 44)}<div class="grow"><div class="row" style="gap:8px"><b style="font-size:16px">${esc(c.label)}</b><span class="cstate ${cls}">${esc(txt)}</span></div><div class="small muted">${esc(c.about || "")}</div></div>
      <span class="row">${btns}${c.kind === "mcp" && !c.preset ? `<button class="btn s hot" data-rm="${c.name}">Remove</button>` : ""}</span></div>
      ${c.detail && !(c.kind === "builtin" && c.connected && !editing) ? `<div class="small ${cls === "warn" || cls === "off" ? "" : "muted"}">${esc(c.detail)}${c.fix ? ` <b>${esc(c.fix)}</b>` : ""}</div>` : ""}
      ${c.kind === "builtin" && editing ? `<div class="keyfield" data-form="${c.name}">${c.fields.map((f) => `<label class="small" for="f-${c.name}-${f.key}">${esc(f.label)}</label><input class="f ${f.secret ? "" : "mono"}" id="f-${c.name}-${f.key}" data-field="${f.key}" ${f.secret ? `type="password" placeholder="${c.connected ? "Saved. Paste a new one to replace it." : esc(f.placeholder)}"` : `placeholder="${esc(f.placeholder)}"`} autocomplete="off" spellcheck="false">`).join("")}
        <div class="row"><button class="btn p s" data-save="${c.name}">Save & check</button>${c.name === "telegram" ? `<a class="small" href="https://t.me/BotFather" target="_blank" rel="noopener">Open @BotFather ↗</a>` : c.name === "apify" ? `<a class="small" href="https://console.apify.com/settings/integrations" target="_blank" rel="noopener">Get your token ↗</a>` : ""}</div></div>` : ""}
      ${c.tools.length && (c.connected || c.kind === "builtin") ? `<div class="row wrap" style="gap:6px">${c.tools.slice(0, 10).map((t) => `<span class="chip mono">${esc(t)}</span>`).join("")}${c.tools.length > 10 ? `<span class="chip">+${c.tools.length - 10} more</span>` : ""}</div>` : ""}
      ${c.kind === "mcp" && c.connected ? `<details><summary class="small">Try a tool</summary><div class="grid3" style="margin-top:8px"><select class="f" data-tool="${c.name}">${c.tools.map((t) => `<option ${t === ({ "claude-code": "Read", codex: "codex" }[c.name]) ? "selected" : ""}>${esc(t)}</option>`).join("")}</select><input class="f mono" data-args="${c.name}" value='${esc(JSON.stringify(c.name === "claude-code" ? { file_path: "/etc/hosts" } : c.name === "codex" ? { prompt: "Reply with the single word OK. Do not run commands." } : {}))}'><button class="btn s" data-try="${c.name}">Run it</button></div><pre class="code hidden" data-out="${c.name}"></pre></details>` : ""}
      <div class="small" data-res="${c.name}" role="status"></div></div>`;
  },
  async refresh() {
    const { connectors: all, inky } = await get("/api/connectors");
    this.inky = inky;
    const agents = all.filter((c) => c.kind === "mcp" && c.preset), services = all.filter((c) => c.kind === "builtin"), others = all.filter((c) => c.kind === "mcp" && !c.preset);
    this.el.innerHTML = `${mobileBar("Connectors")}<div class="page"><div><h1>Connectors</h1><p class="lede">All optional. Each one shows whether it works, with a real test and a fix when it doesn’t. Handing work to any of them asks you first.</p></div>
      <section class="col"><h2>Agents</h2>${agents.map((c) => this.card(c)).join("")}</section>
      <section class="col"><h2>Services</h2>${services.map((c) => this.card(c)).join("")}</section>
      <section class="col"><h2>Other MCP servers</h2>${others.map((c) => this.card(c)).join("")}
        <div class="card"><b>Add an MCP server</b><div class="row wrap" style="gap:8px">${MCP_PRESETS.map(([n, l, lg]) => `<button class="chip" data-preset="${n}">${logo(lg, 18)}${esc(l)}</button>`).join("")}</div>
        <div class="grid3"><input class="f" id="mn" placeholder="Name, e.g. github" aria-label="Name"><input class="f mono" id="mc" placeholder="Command, e.g. npx -y @modelcontextprotocol/server-github" style="grid-column:span 2" aria-label="Command"></div>
        <input class="f mono" id="me" placeholder="Settings it needs, e.g. GITHUB_PERSONAL_ACCESS_TOKEN=… (one per line, optional)" aria-label="Environment">
        <div><button class="btn s" id="madd">Add and connect</button></div><span class="small" id="mres" role="status"></span></div></section>
      <section class="card"><b>Let Claude Code and Codex use your bots</b><span class="small muted">Inky is an MCP server too. They can list your bots, message them, run their skills and read what they found. Approving Needs-you items stays in this app.</span>
        <div class="row wrap">${agents.map((c) => `<button class="btn" data-addinky="${c.name}" ${c.installed ? "" : "disabled"}>${logo(c.logo, 20)}Add Inky to ${esc(c.label)}</button>`).join("")}</div><span class="small" id="addres" role="status"></span>
        <details><summary class="small">Or do it yourself</summary><label class="l">Claude Code</label><pre class="code">${esc(inky.claude_cli)}</pre><label class="l">Codex (~/.codex/config.toml)</label><pre class="code">${esc(inky.codex_toml)}</pre></details></section></div>`;
    const res = (n, t, ok) => { const r = $(`[data-res="${n}"]`); if (r) { r.textContent = t; r.className = "small " + (ok === true ? "good" : ok === false ? "bad" : "muted"); } };
    $$("[data-on]").forEach((x) => (x.onclick = async () => { x.disabled = true; x.textContent = "Connecting…"; try { await post(`/api/mcp/${x.dataset.on}/connect`); await this.refresh(); SOUND.play("chime"); } catch (e) { res(x.dataset.on, e.message, false); x.disabled = false; x.textContent = "Connect"; } }));
    $$("[data-off]").forEach((x) => (x.onclick = async () => { await post(`/api/mcp/${x.dataset.off}/disconnect`); this.refresh(); }));
    $$("[data-rm]").forEach((x) => (x.onclick = async () => { if (await confirmBox(`Remove ${x.dataset.rm}?`, "Remove", true)) { await del(`/api/mcp/${x.dataset.rm}`); this.refresh(); } }));
    $$("[data-edit]").forEach((x) => (x.onclick = () => { this.open = this.open === x.dataset.edit ? null : x.dataset.edit; this.refresh().then(() => { const f = $(`[data-form="${x.dataset.edit}"] input`); if (f) f.focus(); }); }));
    $$("[data-test]").forEach((x) => (x.onclick = async () => { const n = x.dataset.test; res(n, "Testing…"); const r = await post(`/api/connectors/${n}/test`); res(n, (r.ok ? "✓ " : "") + r.text, r.ok); if (r.ok) SOUND.play("chime"); }));
    $$("[data-save]").forEach((x) => (x.onclick = async () => {
      const n = x.dataset.save, values = {};
      $$(`[data-form="${n}"] [data-field]`).forEach((i) => { if (i.value.trim()) values[i.dataset.field] = i.value.trim(); });
      res(n, "Checking…");
      const r = await post(`/api/connectors/${n}/setup`, { values });
      if (!r.ok) return res(n, r.text, false);
      this.open = null;
      await this.refresh(); res(n, "✓ " + r.text, true); SOUND.play("chime");
      if (n === "telegram") this.waitForStart(r.bot);
    }));
    $$("[data-try]").forEach((x) => (x.onclick = async () => {
      const n = x.dataset.try, out = $(`[data-out="${n}"]`);
      out.classList.remove("hidden"); out.textContent = "Running…";
      try { const r = await post(`/api/mcp/${n}/call`, { tool: $(`[data-tool="${n}"]`).value, args: JSON.parse($(`[data-args="${n}"]`).value || "{}") }); out.textContent = (r.error ? "Error: " : "") + r.text.slice(0, 3000); }
      catch (e) { out.textContent = e.message; }
    }));
    $$("[data-preset]").forEach((x) => (x.onclick = () => { const p = MCP_PRESETS.find((m) => m[0] === x.dataset.preset); $("#mn").value = p[0]; $("#mc").value = p[3]; $("#me").value = p[4]; (p[4] ? $("#me") : $("#mc")).focus(); }));
    $("#madd").onclick = async () => {
      const name = $("#mn").value.trim(), command = $("#mc").value.trim();
      if (!name || !command) return this.say("#mres", "Put in a name and the command that starts it.", false);
      const env = Object.fromEntries($("#me").value.split(/\n|\s+(?=[A-Z_]+=)/).map((l) => l.trim()).filter((l) => l.includes("=")).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1)]));
      try { await post("/api/mcp", { name, command, label: name, env }); } catch (e) { return this.say("#mres", e.message, false); }
      this.say("#mres", "Connecting…");
      const r = await post(`/api/connectors/${name.toLowerCase().replace(/[^a-z0-9-]/g, "-")}/test`);
      await this.refresh(); this.say("#mres", (r.ok ? "✓ " : "") + r.text, r.ok);
    };
    $$("[data-addinky]").forEach((x) => (x.onclick = async () => {
      const n = x.dataset.addinky, cc = n === "claude-code";
      const ok = await confirmBox(cc ? "Add Inky to Claude Code? This runs:" : "Add Inky to Codex? This adds to ~/.codex/config.toml:", "Add it", false, cc ? inky.claude_cli : inky.codex_toml);
      if (!ok) return;
      try { const r = await post(`/api/connectors/${n}/add-inky`); this.say("#addres", (r.ok ? "✓ " : "") + (r.text || "Done."), r.ok); } catch (e) { this.say("#addres", e.message, false); }
    }));
  },
  say(sel, text, good) { const m = $(sel); if (m) { m.textContent = text; m.className = "small " + (good === true ? "good" : good === false ? "bad" : "muted"); } },
  async waitForStart(bot) {
    const say = (t, ok) => { const r = $('[data-res="telegram"]'); if (r) { r.textContent = t; r.className = "small " + (ok === true ? "good" : ok === false ? "bad" : "muted"); } };
    if (await waitForTelegram(bot, say)) { await this.refresh(); say("✓ Found you and sent a hello. Alerts go to Telegram now.", true); }
  },

};

// ================================================================ make it yours
VIEWS.look = {
  async show(el, [id]) {
    this.el = el;
    if (!S.bots.length) { el.innerHTML = `<div class="page"><h1>Make it yours</h1><p class="lede">Make a bot first.</p></div>`; return; }
    this.bot = S.bots.find((b) => b.id === +id) || S.bots.find((b) => b.id === this.botId) || S.bots[0];
    this.botId = this.bot.id;
    this.draft = { ...this.bot.look, name: this.bot.name };
    this.persona = { ...(this.bot.persona || {}) };
    this.render();
  },
  render() {
    const d = this.draft, b = this.bot;
    const frame = d.frame === "bot" ? d.color : "#E86F51";
    const chips = (key, opts) => `<div class="chips">${opts.map(([v, t]) => `<button data-k="${key}" data-v="${v}" class="${String(d[key]) === String(v) ? "on" : ""}">${t}</button>`).join("")}</div>`;
    const sample = { cheerful: `Found one! It passes all your rules. Want me to draft a message?`, calm: `One new result passes your rules. Shall I draft a message?`, direct: `1 new match. Draft message? Yes or no.` }[d.tone || "cheerful"];
    this.el.innerHTML = `${mobileBar("Make it yours")}<div class="page" style="max-width:none"><div class="row" style="align-items:flex-start;gap:36px;flex-wrap:wrap">
      <section class="card panel" style="width:400px;flex-shrink:0;gap:16px;padding:24px"><div class="row">${critter(d.kind, d.color, d.acc, 96)}<div><b style="font-size:28px;letter-spacing:-.03em">${esc(d.name)}</b><div class="small muted">${esc((b.summary || b.job || "").slice(0, 60))}</div></div></div>
        <span class="small muted" style="font-weight:600">While it drives</span>
        <div style="position:relative;height:210px;border-radius:14px;background:#111110;padding:6px"><div style="height:100%;border-radius:9px;background:#ECEAE5;box-shadow:inset 0 0 0 3px ${frame};padding:12px"><div style="height:100%;border-radius:8px;background:#fff;padding:14px;display:flex;flex-direction:column;gap:8px">
          <span style="width:55%;height:8px;border-radius:4px;background:#E8E6E1"></span><span style="width:35%;height:8px;border-radius:4px;background:#E8E6E1"></span>
          <div style="margin-top:auto;margin-bottom:14px;position:relative;align-self:flex-start">${d.labels ? `<span style="position:absolute;left:0;top:-30px;padding:3px 8px;border-radius:7px;background:#111110;color:#fff;font-size:11.5px;white-space:nowrap">4 · Click “Search”</span>` : ""}
          <span style="padding:8px 16px;border-radius:6px;background:#1F6F78;color:#fff;font-size:13px;font-weight:600;outline:2px solid ${frame};outline-offset:3px">Search</span>
          <svg width="22" height="22" viewBox="0 0 24 24" style="position:absolute;right:-13px;bottom:-14px"><path d="M4 3 L20 11 L12.5 13 L9.5 20 Z" fill="${frame}" stroke="#fff" stroke-width="1.5"/></svg>
          ${d.cursor === "name" ? `<span style="position:absolute;left:calc(100% + 12px);top:26px;padding:3px 8px;border-radius:7px;background:${frame};color:#fff;font-size:11.5px;white-space:nowrap">${esc(d.name)}</span>` : d.cursor === "critter" ? `<span style="position:absolute;left:calc(100% + 10px);top:12px">${critter(d.kind, d.color, d.acc, 34)}</span>` : ""}</div></div></div></div>
        <div class="row" style="align-items:flex-start;margin-top:auto">${critter(d.kind, d.color, d.acc, 30)}<div class="card" style="padding:12px 14px;border-radius:16px 16px 16px 4px">${sample}</div></div><span class="mono small muted">voice: ${esc(d.voice || "soft")} · speed ${esc(d.speed || "normal")}</span></section>
      <section class="col grow" style="gap:18px;min-width:320px"><div><h1>Make it yours</h1><p class="lede">Each bot gets its own look, voice and way of showing it’s driving. It shows in the app, on its computer and on your phone.</p></div>
        <div class="row wrap">${S.bots.map((x) => `<button class="btn ${x.id === b.id ? "p" : ""}" data-bot="${x.id}">${botCritter(x, 24)}${esc(x.name)}</button>`).join("")}</div>
        <div class="grid2" style="gap:28px"><div class="col" style="gap:18px">
          <div class="col"><b class="small">Animal</b><div class="row">${LOOKS.kinds.map((k) => `<button class="animal ${d.kind === k ? "on" : ""}" data-k="kind" data-v="${k}">${critter(k, d.color, "none", 44)}${cap(k)}</button>`).join("")}</div></div>
          <div class="col"><b class="small">Color</b><div class="row">${LOOKS.colors.map(([c, n]) => `<button class="swatch ${d.color === c ? "on" : ""}" style="background:${c}" data-k="color" data-v="${c}" aria-label="${n}"></button>`).join("")}</div></div>
          <div class="col"><b class="small">Accessory</b>${chips("acc", LOOKS.accs.map((a) => [a, a === "none" ? "Nothing" : cap(a)]))}
            <div class="chips">${LOOKS.earned.map(([at, a]) => (b.unlocked || []).includes(a) ? `<button data-k="acc" data-v="${a}" class="${d.acc === a ? "on" : ""}">${cap(a === "party" ? "party hat" : a)}</button>` : `<button disabled title="Unlocks at ${at} runs">🔒 ${cap(a === "party" ? "party hat" : a)} · ${at} runs</button>`).join("")}</div></div>
          <div class="col"><label class="small" for="lname"><b>Name</b></label><input class="f" id="lname" value="${esc(d.name)}"></div>
          <div class="col"><b class="small">Voice on calls</b>${chips("voice", [["soft", "Soft"], ["bright", "Bright"], ["off", "Off, text only"]])}</div></div>
        <div class="col" style="gap:18px"><div class="col"><b class="small">How it talks</b>${chips("tone", [["cheerful", "Cheerful"], ["calm", "Calm"], ["direct", "Straight to the point"]])}</div>
          <div class="col"><b class="small">Screen frame</b>${chips("frame", [["coral", "Coral, same for every bot"], ["bot", "This bot’s color"]])}</div>
          <div class="col"><b class="small">Cursor</b>${chips("cursor", [["name", "Arrow with its name"], ["critter", "Its critter follows"], ["plain", "Just an arrow"]])}</div>
          <div class="col"><b class="small">Step labels</b>${chips("labels", [[true, "Show each step"], [false, "Hide steps"]])}</div>
          <div class="col"><b class="small">Default speed</b>${chips("speed", [["slow", "Slow"], ["normal", "Normal"], ["turbo", "Turbo"]])}</div>
          <span class="small muted">A frame always shows while a bot uses a screen, and you can take over at any moment.</span></div></div>
        <div class="card" style="gap:14px"><div class="head"><b>Personality</b><span class="small muted">how it talks, never what it’s allowed to do</span></div>
          <div class="grid2" style="gap:18px"><div class="col">
            <label class="small" for="pc"><b>Chatty ↔ quiet</b></label><input type="range" id="pc" min="0" max="1" step="0.1" value="${1 - (this.persona.chatty ?? 0.5)}" aria-label="Chatty to quiet">
            <label class="small" for="pp"><b>Playful ↔ serious</b></label><input type="range" id="pp" min="0" max="1" step="0.1" value="${1 - (this.persona.playful ?? 0.5)}" aria-label="Playful to serious">
            <div class="col"><b class="small">Emoji</b>${`<div class="chips"><button data-pe="1" class="${this.persona.emoji ? "on" : ""}">Sometimes</button><button data-pe="0" class="${this.persona.emoji ? "" : "on"}">Never</button></div>`}</div></div>
          <div class="col"><label class="small" for="pcat"><b>Catchphrase</b></label><input class="f" id="pcat" maxlength="80" value="${esc(this.persona.catchphrase || "")}">
            <label class="small" for="pq"><b>Quirk</b></label><input class="f" id="pq" maxlength="120" value="${esc(this.persona.quirk || "")}">
            <label class="small" for="pb"><b>In its own words</b></label><input class="f" id="pb" maxlength="160" placeholder="I hunt flats in Bari so you don’t have to." value="${esc(this.persona.bio || "")}"></div></div></div>
        <div class="row"><button class="btn p" id="lsave">Save</button><button class="btn" id="lreset">Reset</button><span class="mono small muted">click to try · nothing saves until you press Save</span></div></section></div></div>`;
    $$("[data-k]", this.el).forEach((x) => (x.onclick = () => { this.draft[x.dataset.k] = x.dataset.v === "true" ? true : x.dataset.v === "false" ? false : x.dataset.v; this.render(); }));
    $$("[data-bot]", this.el).forEach((x) => (x.onclick = () => { location.hash = `#/look/${x.dataset.bot}`; }));
    $("#lname").oninput = (e) => (this.draft.name = e.target.value);
    $("#pc").oninput = (e) => (this.persona.chatty = +(1 - e.target.value).toFixed(1));
    $("#pp").oninput = (e) => (this.persona.playful = +(1 - e.target.value).toFixed(1));
    $$("[data-pe]", this.el).forEach((x) => (x.onclick = () => { this.persona.emoji = x.dataset.pe === "1"; this.render(); }));
    for (const [id, k] of [["pcat", "catchphrase"], ["pq", "quirk"], ["pb", "bio"]]) $("#" + id).oninput = (e) => (this.persona[k] = e.target.value);
    $("#lreset").onclick = () => { this.draft = { ...b.look, name: b.name }; this.persona = { ...(b.persona || {}) }; this.render(); };
    $("#lsave").onclick = async () => { const { name, ...look } = this.draft; await patch(`/api/bots/${b.id}`, { name, look, persona: this.persona }); await loadState(); this.bot = S.bots.find((x) => x.id === b.id); toast("Saved", this.bot); };
  },
};

// ================================================================ settings
VIEWS.settings = {
  async show(el) { this.el = el; await this.refresh(); },
  async refresh() {
    const s = await get("/api/settings");
    const tog = (k, on, label) => `<div class="between"><span>${label}</span><button class="toggle ${on ? "on" : ""}" data-t="${k}" role="switch" aria-checked="${!!on}" aria-label="${label}"></button></div>`;
    const kb = (t, k) => `<div class="between" style="padding:6px 0;border-top:1px solid #F0EEE9"><span>${t}</span><span class="row" style="gap:4px">${k.split(" ").map((x) => `<kbd>${x}</kbd>`).join("")}</span></div>`;
    this.el.innerHTML = `${mobileBar("Settings")}<div class="page"><div><h1>Settings</h1><p class="lede">For the whole app. Each bot has its own settings on its page.</p></div>
      <div class="grid2"><div class="card"><b>Shortcuts</b>${kb("Open the command bar", "⌘ K")}${kb("…or", "⌥ Space")}${kb("Pause all bots", "⌥ P")}${kb("On your screen: stop the bot", "Esc")}${kb("On your screen: chat while it drives", "⌥ C")}${kb("Take over: move your mouse on your screen", "🖱")}
        <span class="small muted" style="margin-top:8px">Anywhere on your computer, in the Inky app:</span><span id="barkey">${kb("Command bar over any app", "⌥ Space")}</span>${kb("Pause all bots", "⌃ ⌥ P")}${kb("Stop everything on my screen", "⌃ ⌥ Esc")}</div>
        <div class="card"><b>Privacy and data</b><div class="between"><span>Never record password fields</span><span class="small muted row">${icon("lock", 13)}always</span></div><div class="between"><span>Bots never type your passwords</span><span class="small muted row">${icon("lock", 13)}always</span></div>
          <span class="small muted">Everything stays on your computers. There is no Inky server. Data folder: <span class="mono">${esc(s.data_folder || "~/.inky")}</span></span></div>
        <div class="card"><b>Notifications</b>${tog("notify_app", s.notify_app !== false, "In this app")}${tog("sounds", s.sounds !== false, "Sounds (each bot has its own)")}${APP ? tog("buddy", s.buddy !== false, "Desktop buddy: a critter peeks in when a bot needs you") + `<div class="between"><span>Open Inky when you log in</span><button class="toggle" id="autost" role="switch" aria-checked="false" aria-label="Open Inky when you log in"></button></div>` : ""}${tog("telegram", s.telegram.enabled, "On Telegram")}<div class="between"><label for="chat">Telegram chat id</label><input class="f" id="chat" style="width:180px;height:36px" value="${esc(s.telegram.chat_id || "")}"></div>
          <div class="between"><span>Bots on your screen</span><button class="toggle ${s.screen_allowed ? "on" : ""}" data-t="screen_allowed" role="switch" aria-checked="${!!s.screen_allowed}" aria-label="Bots on your screen"></button></div></div>
        <div class="card"><b>About</b><div class="between"><span>Inky 0.1.0</span><span class="small muted">open source · MIT</span></div><div class="between"><label for="en">This computer’s name</label><input class="f" id="en" style="width:200px;height:36px" value="${esc(s.engine_name)}"></div><div class="between"><label for="un">What should bots call you?</label><input class="f" id="un" style="width:200px;height:36px" placeholder="your name" value="${esc(s.user_name || "")}"></div>
          <div class="row"><a class="btn s" href="https://github.com/GHGuide/inky" target="_blank" rel="noopener">Read the code ↗</a><a class="btn s" href="#/setup/1">Run setup again</a></div></div></div></div>`;
    $$("[data-t]", this.el).forEach((x) => (x.onclick = async () => {
      const on = !x.classList.contains("on"); x.classList.toggle("on", on); x.setAttribute("aria-checked", on);
      S.settings = await post("/api/settings", x.dataset.t === "telegram" ? { telegram: { enabled: on } } : { [x.dataset.t]: on });
    }));
    $("#chat").onchange = () => post("/api/settings", { telegram: { chat_id: $("#chat").value.trim() } });
    $("#en").onchange = () => post("/api/settings", { engine_name: $("#en").value.trim() }).then(loadState);
    if (APP) invoke("app_info").then((i) => { if (i && $("#barkey")) $("#barkey").innerHTML = i.bar_key === "none" ? kb("Command bar over any app", "taken by another app") : kb("Command bar over any app", i.bar_key.replaceAll("⌃⌥", "⌃ ⌥").replaceAll("⌥Space", "⌥ Space").replace(" or ", " or ")); });
    if ($("#autost")) {
      invoke("autostart", {}).then((on) => { $("#autost").classList.toggle("on", !!on); $("#autost").setAttribute("aria-checked", !!on); });
      $("#autost").onclick = async (e) => { const on = await invoke("autostart", { on: !e.currentTarget.classList.contains("on") }); $("#autost").classList.toggle("on", !!on); $("#autost").setAttribute("aria-checked", !!on); };
    }
    $("#un").onchange = () => post("/api/settings", { user_name: $("#un").value.trim().slice(0, 40) }).then(() => toast(`Bots will call you ${$("#un").value.trim() || "nothing special"}`));
  },
};
