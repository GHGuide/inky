// App motion: calm and quick. Things arrive with a short stagger, numbers count up, buttons give under your finger.
// Everything is off when the system asks for reduced motion.
(function (root) {
  const calm = () => root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const EASE = "cubic-bezier(.2,.8,.2,1)";
  const PICK = "[data-enter],.card,.botcard,.desk,.m,.rule,.stat,.ptile,.opt,.navlink.sub";
  const MOTION = {
    calm,
    enter(el) {  // stagger what's on screen now; later re-renders don't replay it
      if (!el || calm() || !el.animate) return;
      const h = root.innerHeight;
      [...el.querySelectorAll(PICK)].filter((x) => !x.closest(".critter") && x.getBoundingClientRect().top < h).slice(0, 24).forEach((x, i) =>
        x.animate([{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }], { duration: 320, delay: i * 30, easing: EASE, fill: "backwards" }));
      el.querySelectorAll(".stat b").forEach((b) => MOTION.count(b));
    },
    count(el, to) {  // "1,240" or "3.5 h" count up from 0, keeping the words around the number
      const m = String(el.textContent).match(/^(\D*)([\d,]*\.?\d+)(.*)$/);
      if (!m || calm()) return;
      const end = to ?? parseFloat(m[2].replace(/,/g, "")), dec = (m[2].split(".")[1] || "").length, comma = m[2].includes(",");
      if (!(end > 0)) return;
      const fmt = (v) => m[1] + (comma ? Math.round(v).toLocaleString("en-US") : v.toFixed(dec)) + m[3];
      const t0 = performance.now();
      const step = (t) => {
        const k = Math.min(1, (t - t0) / 600), e = 1 - Math.pow(1 - k, 3);
        el.textContent = fmt(end * e);
        if (k < 1) requestAnimationFrame(step);
      };
      el.textContent = fmt(0); requestAnimationFrame(step);
    },
  };
  root.MOTION = MOTION;
})(typeof window !== "undefined" ? window : globalThis);
