// Tiny sounds, synthesized (no files). Each bot has its own voice: a pitch from its color, a timbre from its kind.
(function (root) {
  function voiceOf(bot) {
    const l = (bot && bot.look) || {};
    let h = 0x811c9dc5;  // FNV-1a
    for (const ch of String(l.color || "#E86F51") + (l.kind || "")) h = Math.imul(h ^ ch.charCodeAt(0), 0x01000193) >>> 0;
    return { base: 330 + (h % 551), wave: l.kind === "cat" ? "triangle" : "sine" };
  }

  const NOTES = {  // [multiplier of the voice's base, start offset s, length s]
    plip: [[2, 0, 0.09]],
    knock: [[0.5, 0, 0.06], [0.5, 0.14, 0.06]],
    chime: [[1, 0, 0.18], [1.5, 0.16, 0.24]],
    rise: [[1, 0, 0.12], [1.25, 0.11, 0.12], [1.5, 0.22, 0.2]],
  };

  let ctx = null;
  const SOUND = {
    allowed(bot) {
      const st = typeof S !== "undefined" ? S : root.S || {};  // app.js's top-level S isn't on window
      if ((st.settings || {}).sounds === false) return false;
      return !(root.inQuiet && bot && root.inQuiet(bot.schedule, new Date()));
    },
    play(name, bot) {
      if (!NOTES[name] || !SOUND.allowed(bot)) return;
      try {
        ctx = ctx || new (root.AudioContext || root.webkitAudioContext)();
        if (ctx.state === "suspended") ctx.resume();
        const v = voiceOf(bot), t0 = ctx.currentTime + 0.01;
        for (const [mul, at, len] of NOTES[name]) {
          const o = ctx.createOscillator(), g = ctx.createGain();
          o.type = v.wave;
          o.frequency.value = v.base * mul;
          g.gain.setValueAtTime(0.0001, t0 + at);
          g.gain.exponentialRampToValueAtTime(0.08, t0 + at + 0.012);
          g.gain.exponentialRampToValueAtTime(0.0001, t0 + at + len);
          o.connect(g).connect(ctx.destination);
          o.start(t0 + at);
          o.stop(t0 + at + len + 0.05);
        }
      } catch (e) { /* no audio here: stay quiet */ }
    },
  };

  const api = { voiceOf, SOUND };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else Object.assign(root, api);
})(typeof window !== "undefined" ? window : globalThis);
