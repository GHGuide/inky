// Inky critters: octopus, cat, blob, plus accessories. Same drawings as the design canvas, split into
// named parts (.body .limbs .eyes .pupil) so life.js and app.css can make them breathe, blink and show moods.
(() => {
  const star = (cx, cy, r) => {
    let d = "";
    for (let i = 0; i < 10; i++) {
      const a = -Math.PI / 2 + (i * Math.PI) / 5, rr = i % 2 ? r * 0.45 : r;
      d += `${i ? "L" : "M"}${(cx + rr * Math.cos(a)).toFixed(1)} ${(cy + rr * Math.sin(a)).toFixed(1)} `;
    }
    return d + "Z";
  };
  const twinkle = (x, y) => `M${x} ${y - 6} L${x + 1.6} ${y - 1.6} L${x + 6} ${y} L${x + 1.6} ${y + 1.6} L${x} ${y + 6} L${x - 1.6} ${y + 1.6} L${x - 6} ${y} L${x - 1.6} ${y - 1.6} Z`;
  const spiral = (cx, cy) => {
    let d = "";
    for (let i = 0; i <= 36; i++) { const t = (i / 36) * 3.2 * Math.PI, r = 0.6 + t * 0.62; d += `${i ? "L" : "M"}${(cx + r * Math.cos(t)).toFixed(1)} ${(cy + r * Math.sin(t)).toFixed(1)} `; }
    return d;
  };
  const eyes = (y) => `<g class="eyes"><g class="gaze"><g class="pupil"><ellipse cx="46" cy="${y}" rx="5.5" ry="7.5" fill="#1D1A17"/><ellipse cx="74" cy="${y}" rx="5.5" ry="7.5" fill="#1D1A17"/><circle cx="48" cy="${y - 3}" r="2" fill="#FFFFFF"/><circle cx="76" cy="${y - 3}" r="2" fill="#FFFFFF"/></g></g></g>`;
  const moods = (y) => `<g class="brows" fill="none" stroke="#1D1A17" stroke-width="3" stroke-linecap="round"><path d="M37 ${y - 13} L52 ${y - 17}"/><path d="M83 ${y - 13} L68 ${y - 17}"/></g>
    <g class="spiral" fill="none" stroke="#1D1A17" stroke-width="2.2" stroke-linecap="round"><path d="${spiral(46, y)}"/><path d="${spiral(74, y)}"/></g>
    <path class="sweat" d="M97 28 Q102 38 97 42 Q92 38 97 28 Z" fill="#8FD0F6" stroke="#1D1A17" stroke-width="1.5"/>
    <g class="zzz" fill="#8E8A83" font-family="Geist,-apple-system,sans-serif" font-weight="700"><text x="88" y="28" font-size="17">z</text><text x="101" y="14" font-size="12">z</text></g>
    <g class="sparkle" fill="#F5C542"><path d="${twinkle(14, 22)}"/><path d="${twinkle(106, 24)}"/><path d="${twinkle(104, 92)}"/></g>
    <path class="star" d="${star(60, 90, 9)}" fill="#F5C542" stroke="#1D1A17" stroke-width="2" stroke-linejoin="round"/>`;
  const BODY = {
    octopus: () => `<g class="limbs" fill="none" stroke="C" stroke-width="11" stroke-linecap="round"><g class="limb" style="--i:0"><path d="M34 76 C 28 92, 16 98, 20 110"/></g><g class="limb" style="--i:1"><path d="M47 80 C 45 96, 38 104, 42 114"/></g><g class="limb" style="--i:2"><path d="M60 82 C 62 98, 56 106, 60 114"/></g><g class="limb" style="--i:3"><path d="M73 80 C 75 96, 82 104, 78 114"/></g><g class="limb" style="--i:4"><path d="M86 76 C 92 92, 104 98, 100 110"/></g></g>
      <g class="body"><ellipse cx="60" cy="52" rx="38" ry="36" fill="C"/><ellipse cx="46" cy="30" rx="11" ry="6" fill="#FFFFFF" opacity="0.35"/><ellipse cx="35" cy="66" rx="6" ry="3.5" fill="#F7A99A"/><ellipse cx="85" cy="66" rx="6" ry="3.5" fill="#F7A99A"/><path class="mouth" d="M54 66 Q60 72 66 66" fill="none" stroke="#1D1A17" stroke-width="3" stroke-linecap="round"/><ellipse class="yawn" cx="60" cy="69" rx="4.5" ry="5.5" fill="#1D1A17"/>${eyes(54)}</g>${moods(54)}`,
    cat: () => `<path class="tail" d="M90 98 Q114 94 110 70 Q108 60 100 62" fill="none" stroke="C" stroke-width="8" stroke-linecap="round"/><g class="limbs"><g class="limb" style="--i:0"><ellipse cx="46" cy="106" rx="9" ry="7" fill="C"/></g><g class="limb" style="--i:1"><ellipse cx="74" cy="106" rx="9" ry="7" fill="C"/></g></g>
      <g class="body"><path d="M24 46 L30 10 L54 30 Z" fill="C"/><path d="M96 46 L90 10 L66 30 Z" fill="C"/><path d="M32 36 L34 20 L45 29 Z" fill="#F7A99A"/><path d="M88 36 L86 20 L75 29 Z" fill="#F7A99A"/><ellipse cx="60" cy="62" rx="40" ry="38" fill="C"/><ellipse cx="46" cy="38" rx="10" ry="5" fill="#FFFFFF" opacity="0.3"/><ellipse cx="34" cy="69" rx="6" ry="3.5" fill="#F7A99A"/><ellipse cx="86" cy="69" rx="6" ry="3.5" fill="#F7A99A"/><path d="M57 66 L63 66 L60 70 Z" fill="#F7A99A"/><path class="mouth" d="M53 73 Q56.5 77 60 73 Q63.5 77 67 73" fill="none" stroke="#1D1A17" stroke-width="2.5" stroke-linecap="round"/><ellipse class="yawn" cx="60" cy="76" rx="4.5" ry="5.5" fill="#1D1A17"/><g stroke="#1D1A17" stroke-width="2" stroke-linecap="round" opacity="0.45"><path d="M18 64 L34 66"/><path d="M18 73 L34 71"/><path d="M102 64 L86 66"/><path d="M102 73 L86 71"/></g>${eyes(55)}</g>${moods(55)}`,
    blob: () => `<g class="body"><path d="M22 58 Q22 16 60 16 Q98 16 98 58 L98 102 Q91 94 83 102 Q75 110 67 102 Q60 95 53 102 Q45 110 37 102 Q29 94 22 102 Z" fill="C"/><ellipse cx="44" cy="32" rx="11" ry="6" fill="#FFFFFF" opacity="0.35"/><ellipse cx="35" cy="67" rx="6" ry="3.5" fill="#F7A99A"/><ellipse cx="85" cy="67" rx="6" ry="3.5" fill="#F7A99A"/><path class="mouth" d="M53 66 Q60 74 67 66" fill="none" stroke="#1D1A17" stroke-width="3" stroke-linecap="round"/><ellipse class="yawn" cx="60" cy="70" rx="4.5" ry="5.5" fill="#1D1A17"/>${eyes(54)}</g>${moods(54)}`,
  };
  const EXTRA = {
    glasses: `<g fill="#FFFFFF" fill-opacity="0.25" stroke="#1D1A17" stroke-width="3.5"><circle cx="46" cy="54" r="12"/><circle cx="74" cy="54" r="12"/></g><path d="M58 53 Q60 50 62 53" fill="none" stroke="#1D1A17" stroke-width="3.5"/>`,
    beanie: `<path d="M24 34 Q24 4 60 4 Q96 4 96 34 Z" fill="#3B5BDB"/><rect x="20" y="28" width="80" height="12" rx="6" fill="#2A45B0"/><circle cx="60" cy="5" r="7" fill="#F3ECE1"/>`,
    headphones: `<path d="M20 56 Q20 10 60 10 Q100 10 100 56" fill="none" stroke="#1D1A17" stroke-width="6" stroke-linecap="round"/><rect x="11" y="46" width="17" height="27" rx="7" fill="#1D1A17"/><rect x="92" y="46" width="17" height="27" rx="7" fill="#1D1A17"/><rect x="15" y="51" width="9" height="17" rx="4.5" fill="#F2957C"/><rect x="96" y="51" width="9" height="17" rx="4.5" fill="#F2957C"/>`,
    bow: `<g transform="translate(88 24) rotate(18)"><path d="M0 0 L-15 -10 L-15 10 Z" fill="#F07BA8"/><path d="M0 0 L15 -10 L15 10 Z" fill="#F07BA8"/><circle cx="0" cy="0" r="5" fill="#D9558A"/></g>`,
    // unlocked by runs (growth levels)
    scarf: `<path d="M26 82 Q60 98 94 82 L94 91 Q60 107 26 91 Z" fill="#3B5BDB" stroke="#1D1A17" stroke-width="2"/><path d="M76 93 L86 114 L75 115 L68 96 Z" fill="#2A45B0" stroke="#1D1A17" stroke-width="2"/><path d="M34 88 L34 94 M48 92 L48 98 M62 94 L62 100" stroke="#F3ECE1" stroke-width="2.5" stroke-linecap="round"/>`,
    party: `<g transform="translate(66 2) rotate(14)"><path d="M0 2 L15 34 L-15 34 Z" fill="#7C6CF2" stroke="#1D1A17" stroke-width="2" stroke-linejoin="round"/><path d="M-9 22 L9 22 M-5 13 L5 13" stroke="#F5C542" stroke-width="3" stroke-linecap="round"/><circle cx="0" cy="2" r="5" fill="#F5C542"/></g>`,
    star: `<path d="M84 72 L79 86 L88 82 L97 86 L92 72 Z" fill="#3B5BDB"/><circle cx="88" cy="92" r="9" fill="#F5C542" stroke="#1D1A17" stroke-width="2"/><path d="${star(88, 92, 5)}" fill="#E0A21B"/>`,
    crown: `<path d="M32 24 L40 4 L51 18 L60 0 L69 18 L80 4 L88 24 Z" fill="#F5C542" stroke="#1D1A17" stroke-width="2.5" stroke-linejoin="round"/><circle cx="60" cy="16" r="3.5" fill="#E86F51"/><circle cx="44" cy="18" r="2.5" fill="#3B5BDB"/><circle cx="76" cy="18" r="2.5" fill="#3B5BDB"/>`,
  };
  let n = 0;
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  window.critter = function (kind = "octopus", color = "#E86F51", acc = "none", size = 40, mood = "calm") {
    // a shared bot's look is data from someone else: only a real colour, kind and accessory ever reach the markup
    if (!/^#[0-9a-f]{3,8}$/i.test(String(color))) color = "#E86F51";
    if (!own(BODY, kind)) kind = "octopus";
    const body = BODY[kind]().replace(/"C"/g, `"${color}"`);
    return `<svg class="critter" data-kind="${kind}" data-mood="${/^\w+$/.test(mood) ? mood : "calm"}" data-seed="${++n}" width="${+size || 40}" height="${+size || 40}" viewBox="0 0 120 120" aria-hidden="true">${body}${own(EXTRA, acc) ? EXTRA[acc] : ""}</svg>`;
  };
  window.botCritter = (b, size) => {
    const l = b.look || {};
    const mood = window.moodOf ? window.moodOf(b, window.RECENT || {}) : "calm";
    return critter(l.kind, l.color, l.acc, size, mood).replace("<svg ", `<svg data-bot="${b.id}" `);
  };
})();
