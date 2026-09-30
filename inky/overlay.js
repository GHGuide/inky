// Inky overlay: coral frame, named cursor, step label, target outline, control pill and chat.
// Injected into every page a bot drives. Lives in a closed shadow root so the page can't style it
// and so typing in the chat never reaches the page.
(() => {
  if (window.__inky) return;
  const S = { frame: "#E86F51", cursor: "name", labels: true, name: "Bot", mode: "own", step: "", pill: null,
              paused: false, chat: [], chatOpen: false, visible: true, x: -100, y: -100, target: null, critter: "" };
  let root, host, els = {};
  const call = (msg) => { try { window.inkyControl && window.inkyControl(msg); } catch (e) {} };

  function build() {
    if (host && document.documentElement.contains(host)) return;
    host = document.createElement("inky-overlay");
    host.style.cssText = "position:fixed;inset:0;z-index:2147483647;pointer-events:none;display:block";
    root = host.attachShadow({ mode: "closed" });
    root.innerHTML = `<style>
      *{box-sizing:border-box;font-family:Geist,-apple-system,system-ui,sans-serif}
      .frame{position:fixed;inset:0;border:3px solid var(--c);box-shadow:inset 0 0 28px color-mix(in srgb,var(--c) 35%,transparent);transition:border-color .3s}
      .tag{position:fixed;left:50%;top:0;transform:translateX(-50%);padding:4px 12px;border-radius:0 0 10px 10px;background:var(--c);color:#fff;font-size:12.5px;font-weight:500;white-space:nowrap}
      .cursor{position:fixed;left:0;top:0;transition:transform .45s cubic-bezier(.2,.8,.2,1);will-change:transform}
      .cursor .name{position:absolute;left:20px;top:20px;padding:3px 8px;border-radius:7px;background:var(--c);color:#fff;font-size:11.5px;font-weight:500;white-space:nowrap}
      .cursor .crit{position:absolute;left:18px;top:14px;width:30px;height:30px}
      .box{position:fixed;border:2px solid var(--c);border-radius:6px;transition:all .35s;pointer-events:none}
      .label{position:fixed;padding:3px 8px;border-radius:7px;background:#111110;color:#fff;font-size:11.5px;white-space:nowrap;transition:all .35s}
      .pill{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);display:flex;align-items:center;gap:10px;padding:8px 10px 8px 14px;border-radius:999px;background:#111110;color:#fff;box-shadow:0 14px 40px rgba(17,17,16,.3);white-space:nowrap;pointer-events:auto}
      .pill .t{display:flex;flex-direction:column;padding-right:8px}.pill b{font-size:13.5px}.pill small{font-size:12px;color:#A8A49C}
      .pill .sep{width:1px;height:28px;background:#3A3936}
      .pill button{height:36px;padding:0 14px;border-radius:999px;border:0;background:#2B2A28;color:#fff;font-size:13px;cursor:pointer}
      .pill button.hot{background:var(--c)} .pill button.on{background:#fff;color:#111110}
      .pill kbd{font-family:ui-monospace,monospace;font-size:11px;opacity:.7;margin-left:6px}
      .dot{width:8px;height:8px;border-radius:50%;background:var(--c);box-shadow:0 0 0 4px color-mix(in srgb,var(--c) 25%,transparent)}
      .chat{position:fixed;right:18px;top:18px;width:360px;height:min(560px,calc(100vh - 120px));border-radius:18px;background:#fff;color:#111110;box-shadow:0 20px 50px rgba(17,17,16,.26);display:flex;flex-direction:column;pointer-events:auto;overflow:hidden}
      .chat header{height:48px;display:flex;align-items:center;justify-content:space-between;padding:0 14px;border-bottom:1px solid #E8E6E1;font-weight:600;font-size:14px}
      .chat header span{font-weight:400;font-size:12.5px;color:#C2502F}
      .msgs{flex:1;overflow:auto;padding:14px;display:flex;flex-direction:column;gap:10px;font-size:14px;line-height:1.45}
      .m{max-width:85%;padding:9px 12px;border-radius:16px}.m.you{align-self:flex-end;background:#F2F1ED;border-radius:16px 16px 4px 16px}.m.bot{align-self:flex-start;border:1px solid #E8E6E1;border-radius:4px 16px 16px 16px}
      .in{padding:10px;border-top:1px solid #E8E6E1}.in form{display:flex;gap:8px}.in input{flex:1;height:38px;border:1.5px solid #111110;border-radius:12px;padding:0 12px;font-size:14px;outline:none}
      .in button{height:38px;padding:0 14px;border:0;border-radius:12px;background:#111110;color:#fff;cursor:pointer}
      .in small{display:block;margin-top:6px;font-family:ui-monospace,monospace;font-size:10.5px;color:#6B6862}
      .hidden{display:none!important}
      .paused .frame{border-style:dashed}
    </style>
    <div class="wrap">
      <div class="frame"></div><div class="tag hidden"></div>
      <div class="box hidden"></div><div class="label hidden"></div>
      <div class="cursor"><svg width="24" height="24" viewBox="0 0 24 24"><path d="M4 3 L20 11 L12.5 13 L9.5 20 Z" fill="var(--c)" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg><span class="name"></span><span class="crit"></span></div>
      <div class="pill hidden"><span class="dot"></span><span class="t"><b></b><small></small></span><span class="sep"></span>
        <button data-a="chat">Chat<kbd>⌥C</kbd></button><button data-a="pause">Pause</button><button data-a="takeover">Take over</button><button data-a="stop" class="hot">Stop<kbd>Esc</kbd></button></div>
      <div class="chat hidden"><header>${"<b></b>"}<span>still driving</span></header><div class="msgs"></div>
        <div class="in"><form><input placeholder="Message the bot…" autocomplete="off"><button>Send</button></form><small>Your typing goes here, never into the page</small></div></div>
    </div>`;
    const q = (s) => root.querySelector(s);
    els = { wrap: q(".wrap"), frame: q(".frame"), tag: q(".tag"), box: q(".box"), label: q(".label"), cursor: q(".cursor"),
            cname: q(".cursor .name"), crit: q(".cursor .crit"), pill: q(".pill"), pt: q(".pill b"), ps: q(".pill small"),
            chat: q(".chat"), chatName: q(".chat header b"), msgs: q(".msgs"), form: q(".in form"), input: q(".in input") };
    root.querySelectorAll(".pill button").forEach((b) => b.addEventListener("click", (e) => {
      e.stopPropagation();
      const a = b.dataset.a;
      if (a === "chat") { S.chatOpen = !S.chatOpen; render(); if (S.chatOpen) setTimeout(() => els.input.focus(), 30); return; }
      call({ type: a });
    }));
    els.form.addEventListener("submit", (e) => {
      e.preventDefault(); e.stopPropagation();
      const t = els.input.value.trim(); if (!t) return;
      els.input.value = ""; S.chat.push({ role: "you", text: t }); render(); call({ type: "chat", text: t });
    });
    // keep chat typing out of the page
    for (const ev of ["keydown", "keyup", "keypress", "input", "beforeinput"]) host.addEventListener(ev, (e) => e.stopPropagation());
    els.input.addEventListener("focus", () => call({ type: "chat_focus", focused: true }));
    els.input.addEventListener("blur", () => call({ type: "chat_focus", focused: false }));
    (document.body || document.documentElement).appendChild(host);
  }

  function render() {
    build();
    host.style.display = S.visible ? "block" : "none";
    els.wrap.style.setProperty("--c", S.frame);
    els.wrap.classList.toggle("paused", !!S.paused);
    els.tag.classList.toggle("hidden", !S.paused);
    els.tag.textContent = S.paused ? (S.pausedText || "Paused · you have the screen") : "";
    els.cname.textContent = S.name;
    els.cname.classList.toggle("hidden", S.cursor !== "name");
    els.crit.innerHTML = S.cursor === "critter" ? S.critter : "";
    els.cursor.style.transform = `translate(${S.x}px, ${S.y}px)`;
    const t = S.target;
    els.box.classList.toggle("hidden", !t);
    els.label.classList.toggle("hidden", !t || !S.labels || !S.step);
    if (t) {
      Object.assign(els.box.style, { left: t.x - 4 + "px", top: t.y - 4 + "px", width: t.w + 8 + "px", height: t.h + 8 + "px" });
      els.label.textContent = S.step;
      const above = t.y > 34;
      Object.assign(els.label.style, { left: Math.max(4, t.x - 4) + "px", top: (above ? t.y - 32 : t.y + t.h + 10) + "px" });
    }
    const showPill = S.mode === "screen" && S.pill;
    els.pill.classList.toggle("hidden", !showPill);
    if (showPill) { els.pt.textContent = S.pill.title || ""; els.ps.textContent = S.pill.sub || ""; }
    root.querySelector('[data-a="pause"]').textContent = S.paused ? "Resume" : "Pause";
    root.querySelector('[data-a="chat"]').classList.toggle("on", S.chatOpen);
    els.chat.classList.toggle("hidden", !(S.mode === "screen" && S.chatOpen));
    els.chatName.textContent = S.name;
    els.msgs.innerHTML = "";
    for (const m of S.chat.slice(-30)) {
      const d = document.createElement("div"); d.className = "m " + (m.role === "you" ? "you" : "bot"); d.textContent = m.text; els.msgs.appendChild(d);
    }
    els.msgs.scrollTop = 1e9;
  }

  // Real people vs the bot: the engine sets __inkySynthetic around its own input.
  const human = (kind) => (e) => {
    if (!e.isTrusted || window.__inkySynthetic || S.mode !== "screen") return;
    if (kind === "key" && ["Alt", "Meta", "Shift", "Control", "CapsLock"].includes(e.key)) return;
    if (kind === "key" && e.key === "Escape") { call({ type: "stop" }); return; }  // Esc always stops, even from the chat
    if (host && e.composedPath && e.composedPath().includes(host)) return;
    if (kind === "key" && e.altKey && (e.key === "c" || e.key === "ç" || e.code === "KeyC")) {
      S.chatOpen = !S.chatOpen; render(); e.preventDefault(); e.stopPropagation();
      if (S.chatOpen) els.input.focus(); else els.input.blur();
      return;
    }
    call({ type: "user_input", kind });
  };
  window.addEventListener("mousedown", human("mouse"), true);
  window.addEventListener("keydown", human("key"), true);
  let lastMove = 0;
  window.addEventListener("mousemove", (e) => { const t = Date.now(); if (t - lastMove > 400) { lastMove = t; human("mouse")(e); } }, true);

  window.__inky = {
    set(patch) { Object.assign(S, patch || {}); render(); return true; },
    point(x, y, target, step) { S.x = x; S.y = y; S.target = target || null; if (step !== undefined) S.step = step; render(); },
    say(text) { S.chat.push({ role: "bot", text }); render(); },
    state() { return JSON.parse(JSON.stringify({ ...S, critter: "" })); },
    chatFocused() { return !!(root && root.activeElement && root.activeElement.tagName === "INPUT"); },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", render); else render();
})();
