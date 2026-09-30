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

  const LIFE = {
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
          if (!el._next) { el._n = 0; el._next = t + blinkDelay(seed, 0); return; }
          if (t < el._next) return;
          el.classList.add("blink");
          setTimeout(() => el.classList.remove("blink"), 140);
          el._next = t + blinkDelay(seed, ++el._n);
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
    },
  };

  const api = { moodOf, inQuiet, blinkDelay, LIFE };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else Object.assign(root, api);
})(typeof window !== "undefined" ? window : globalThis);
