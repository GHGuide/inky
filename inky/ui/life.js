// Life for critters: moods from what a bot is doing, blinking that never syncs, eyes that follow you.
// Works in the page (globals + LIFE.start()) and in Node for tests (module.exports).
(function (root) {
  const MIN = 60e3;

  function inQuiet(s, date) {
    const a = s && s.quiet_from, b = s && s.quiet_to;
    if (!a || !b) return false;
    const hm = String(date.getHours()).padStart(2, "0") + ":" + String(date.getMinutes()).padStart(2, "0");
    return a < b ? a <= hm && hm < b : hm >= a || hm < b;
  }

  function moodOf(bot, recent, now = Date.now()) {
    if (bot.status === "needs_you" || bot.needs > 0) return bot.need_kind === "decision" ? "waving" : "worried";
    if (bot.status === "working") return "focused";
    if (bot.status === "learning") return "curious";
    if (inQuiet(bot.schedule, new Date(now))) return "asleep";
    const r = (recent || {})[bot.id] || {};
    if (r.fixed && now - r.fixed < 2 * MIN) return "dizzy";
    if (r.results && now - r.results < 2 * MIN) return "happy";
    if (r.learned && now - r.learned < 5 * MIN) return "proud";
    return "calm";
  }

  function blinkDelay(seed, n) {
    return 3000 + (((seed * 9301 + n * 49297 + 7) % 233280) / 233280) * 4000;
  }

  // Idle life: every few seconds a critter does something small. Which thing, and when, is fixed per critter
  // (seeded), so two critters side by side never move in step.
  const BEATS = {
    calm: ["look", "look", "sway", "blink2", "stretch", "yawn", "none"],
    asleep: ["none", "none", "sway"],
    focused: ["look", "blink2", "sway", "none"],
    curious: ["look", "look", "blink2", "sway", "stretch"],
    happy: ["look", "sway", "stretch", "blink2"],
    proud: ["look", "stretch", "sway", "none"],
    worried: ["look", "look", "blink2", "none"],
    waving: ["none", "look"],
    dizzy: ["none", "blink2"],
  };
  const LASTS = { look: 1500, sway: 1700, yawn: 1900, stretch: 950, blink2: 460 };
  function rnd(seed, n, salt) {
    let h = (Math.imul(seed | 0, 0x9e3779b1) ^ Math.imul(n + 1, 0x85ebca6b) ^ Math.imul(salt, 0xc2b2ae35)) >>> 0;
    h = Math.imul(h ^ (h >>> 16), 0x7feb352d); h = Math.imul(h ^ (h >>> 15), 0x846ca68b);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }
  function nextBehaviour(seed, n, mood = "calm") {
    const list = BEATS[mood] || BEATS.calm;
    return { name: list[Math.floor(rnd(seed, n, 1) * list.length)], at: 2500 + rnd(seed, n, 2) * 6500 };
  }
  const REACT = { hover: 600, click: 460, results: 1300, learned: 1300, needs: 560 };

  const LIFE = {
    react(el, kind) {  // a short one-off reaction: wiggle, squish, dance, jump
      if (!el || !REACT[kind] || (root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches)) return;
      el.classList.remove("r-" + kind); void el.getBoundingClientRect(); el.classList.add("r-" + kind);
      clearTimeout(el["_r" + kind]); el["_r" + kind] = setTimeout(() => el.classList.remove("r-" + kind), REACT[kind]);
    },
    started: false,
    start() {
      if (this.started || typeof document === "undefined") return;
      this.started = true;
      const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
      setInterval(() => {  // one loop for all critters, so re-rendered ones just pick up a new schedule
        if (document.hidden || calm()) return;
        const t = Date.now();
        document.querySelectorAll("svg.critter").forEach((el) => {
          const seed = +el.dataset.seed || 1;
          if (!el._next) { el._n = 0; el._next = t + blinkDelay(seed, 0); el._bn = 0; el._bnext = t + nextBehaviour(seed, 0).at; return; }
          if (t >= el._next) {
            el.classList.add("blink");
            setTimeout(() => el.classList.remove("blink"), 140);
            el._next = t + blinkDelay(seed, ++el._n);
          }
          const mood = el.dataset.mood || "calm";
          if (mood === "waving" && t - (el._jump || 0) > 8000) { el._jump = t; LIFE.react(el, "needs"); }
          if (t < el._bnext) return;
          const b = nextBehaviour(seed, el._bn++, mood);
          el._bnext = t + b.at;
          if (b.name === "none") return;
          if (b.name === "look") el.style.setProperty("--lx", (rnd(seed, el._bn, 3) < 0.5 ? -3 : 3) + "px");
          el.classList.add("b-" + b.name);
          setTimeout(() => el.classList.remove("b-" + b.name), LASTS[b.name]);
        });
      }, 200);
      let pending = false, px = 0, py = 0;
      addEventListener("pointermove", (e) => {
        px = e.clientX; py = e.clientY;
        if (pending || calm()) return;
        pending = true;
        requestAnimationFrame(() => {
          pending = false;
          document.querySelectorAll("svg.critter").forEach((el) => {
            const r = el.getBoundingClientRect();
            if (r.width <= 40 || r.bottom < 0 || r.top > innerHeight) return;
            const dx = px - (r.left + r.width / 2), dy = py - (r.top + r.height * 0.45), d = Math.hypot(dx, dy) || 1;
            const k = Math.min(1, d / 300) * 3;  // at most 3 viewBox units
            const p = el.querySelector(".pupil");
            if (p) p.style.transform = `translate(${((dx / d) * k).toFixed(2)}px, ${((dy / d) * k).toFixed(2)}px)`;
          });
        });
      }, { passive: true });
      let over = null;  // hovering a big critter makes it wiggle; pressing it squishes it
      addEventListener("pointerover", (e) => {
        const c = e.target.closest && e.target.closest("svg.critter");
        if (c === over) return;
        over = c;
        if (c && c.getBoundingClientRect().width > 30) LIFE.react(c, "hover");
      }, { passive: true });
      addEventListener("pointerdown", (e) => { const c = e.target.closest && e.target.closest("svg.critter"); if (c) LIFE.react(c, "click"); }, { passive: true });
    },
    forBot(id, kind) { if (typeof document !== "undefined") document.querySelectorAll(`svg.critter[data-bot="${id}"]`).forEach((el) => LIFE.react(el, kind)); },
  };

  const api = { moodOf, inQuiet, blinkDelay, nextBehaviour, LIFE };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else Object.assign(root, api);
})(typeof window !== "undefined" ? window : globalThis);
