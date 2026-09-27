// Inky compositor: window.setup(timeline) builds the stage once, window.renderAt(t) poses every layer for time t.
// Pure function of t: no CSS animation, no timers. render.py compiles the timeline (paths, sizes, clip frames, captions).
'use strict';
const W = 1920, H = 1080;
const EASE = {
  linear: x => x,
  cubic: x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2,
  quint: x => x < .5 ? 16 * x ** 5 : 1 - Math.pow(-2 * x + 2, 5) / 2,
  outCubic: x => 1 - Math.pow(1 - x, 3),
  outQuint: x => 1 - Math.pow(1 - x, 5),
};
const c01 = x => Math.max(0, Math.min(1, x));
const lerp = (a, b, p) => a + (b - a) * p;
const ramp = (t, a, b, ease = 'cubic') => b <= a ? (t >= a ? 1 : 0) : EASE[ease](c01((t - a) / (b - a)));
const fade = (t, s, e, fin, fout = fin) => Math.min(ramp(t, s, s + fin), 1 - ramp(t, e - fout, e));
const el = (tag, cls, parent, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; if (parent) parent.appendChild(n); return n; };
const esc = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

let TL, stage, shots = [], overlays = [], capEl, capText = null;

// camera keys {t, zoom, cx, cy, ease}: missing fields carry over; eased between keys, held outside them
function camAt(keys, lt) {
  const ks = [];
  let cur = { zoom: 1, cx: .5, cy: .5 };
  for (const k of keys || []) { cur = { ...cur, ...k }; ks.push(cur); }
  if (!ks.length) return { zoom: 1, cx: .5, cy: .5 };
  if (lt <= ks[0].t) return ks[0];
  for (let i = 1; i < ks.length; i++) if (lt < ks[i].t) {
    const a = ks[i - 1], b = ks[i], p = EASE[b.ease || 'quint'](c01((lt - a.t) / (b.t - a.t)));
    return { zoom: lerp(a.zoom, b.zoom, p), cx: lerp(a.cx, b.cx, p), cy: lerp(a.cy, b.cy, p) };
  }
  return ks[ks.length - 1];
}

// piecewise-linear local time -> source time; [[local, source], ...]
function srcTime(map, lt) {
  if (lt <= map[0][0]) return map[0][1];
  for (let i = 1; i < map.length; i++) if (lt < map[i][0]) {
    const [a, as] = map[i - 1], [b, bs] = map[i];
    return as + (bs - as) * (lt - a) / (b - a);
  }
  const [a, as] = map[map.length - 1], [pb, pbs] = map.length > 1 ? map[map.length - 2] : [a - 1, as - 1];
  return as + (lt - a) * ((as - pbs) / (a - pb) || 1);
}

function frameRect(s) {
  const pad = s.bleed ? 0 : (s.pad ?? 48), pb = s.padBottom ?? pad, bw = W - 2 * pad, bh = H - pad - pb, a = (s.w || 16) / (s.h || 9);
  if (s.type === 'phone') {
    const sh = s.phoneHeight || 940, sw = Math.max(380, Math.min(560, sh * a));
    return { x: (W - sw) / 2, y: (H - sh) / 2, w: sw, h: sh, pad, pb };
  }
  if (s.fit === 'width') { const h = bw / a; return { x: pad, y: pad, w: bw, h, pad, pb }; }
  let w = a > bw / bh ? bw : bh * a, h = w / a;
  if (s.maxScale && w > s.w * s.maxScale) { w = s.w * s.maxScale; h = w / a; }   // no upscaling of small crops
  return { x: (W - w) / 2, y: pad + (bh - h) / 2, w, h, pad, pb };
}

// world -> screen for a shot at local time lt: screen = world * z + (tx, ty)
function camXform(s, lt) {
  const f = s.rect, k = camAt(s.camera, lt), z = k.zoom * (s.zoomBase || 1);
  const fx = f.x + k.cx * f.w, fy = f.y + k.cy * f.h;
  if (s.type === 'phone') return { z, tx: fx * (1 - z), ty: fy * (1 - z) };   // zoom about the focus point
  const axis = (p, lo0, hi0, half) => { const lo = lo0 + half / z, hi = hi0 - half / z; return lo > hi ? (lo + hi) / 2 : Math.max(lo, Math.min(hi, p)); };
  const vx = axis(fx, f.x - f.pad, f.x + f.w + f.pad, W / 2), vy = axis(fy, f.y - f.pad, f.y + f.h + f.pb, H / 2);
  return { z, tx: W / 2 - vx * z, ty: H / 2 - vy * z };
}

// a point in a shot's content space -> stage px. space: 'page' (px of page [pw,ph]), 'src' (px of the asset), 'norm' (0..1)
function mapPt(s, lt, x, y, space, page) {
  const f = s.rect, X = camXform(s, lt);
  let u = x, v = y;
  if (space === 'page') { u = x / page[0]; v = y / page[1]; } else if (space === 'src') { u = x / s.w; v = y / s.h; }
  return { x: (f.x + u * f.w) * X.z + X.tx, y: (f.y + v * f.h) * X.z + X.ty, z: X.z };
}

function placeholder(parent, s) {
  el('div', 'placeholder', parent, `<b>${esc(s.src || s.id)}</b><span>${esc(s.note || 'asset missing: placeholder')}</span>`);
}

function buildShot(s, i) {
  s.node = el('div', 'shot ' + (s.type === 'card' ? 'card' + (s.theme === 'light' ? ' light' : '') : s.type === 'phone' ? 'phone' : 'screen'), stage);
  s.node.style.zIndex = i + 1;
  if (s.bg) s.node.style.background = s.bg;
  if (s.type === 'card') {
    s.inner = el('div', 'cardin', s.node);
    if (s.logoSvg) { s.logo = el('div', 'logo', s.inner, s.logoSvg); s.eyes = [...s.logo.querySelectorAll('ellipse[fill="#111110"], circle[fill="#fff"]')]; }
    s.word = el('h1', '', s.inner, esc(s.text)); if (s.sub) el('p', '', s.node, esc(s.sub)); return;
  }
  if (s.type === 'endcard') {
    s.node.className = 'shot card light endcard';
    s.inner = el('div', 'endin', s.node);
    const L = el('div', 'endl', s.inner), R = el('div', 'endr', s.inner);
    el('div', 'endhead', L, `<div class="logo">${s.logoSvg || ''}</div><b>Inky</b>`);
    el('h2', '', L, esc(s.title));
    el('p', 'endsub', L, esc(s.sub));
    const chipRow = el('div', 'endchips', L);
    s.chips = s.recap.map(c => el('span', 'endchip', chipRow, esc(c)));
    el('p', 'endtot', L, esc(s.totals));
    el('p', 'endtot2', L, esc(s.totals2));
    el('div', 'endqr', R, s.qrSvg || '');
    el('p', 'endtry', R, `Try it: <b>${esc(s.url)}</b>`);
    el('p', 'endfoot', L, esc(s.foot));
    return;
  }
  s.world = el('div', 'world', s.node);
  s.rect = frameRect(s);
  const r = s.rect, box = el('div', s.type === 'phone' ? 'handset' : 'frame' + (s.bleed ? ' bleed' : ''), s.world);
  if (s.type === 'phone') {
    Object.assign(box.style, { left: r.x - 14 + 'px', top: r.y - 14 + 'px', width: r.w + 28 + 'px', height: r.h + 28 + 'px' });
    const scr = el('div', 'pscreen', box);
    if (s.missing) placeholder(scr, s); else s.img = el('img', '', scr);
  } else {
    Object.assign(box.style, { left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px' });
    if (s.missing) placeholder(box, s); else s.img = el('img', '', box);
  }
  if (s.img && s.crop) {
    const [cx, cy] = s.crop, k = r.w / s.w;
    Object.assign(s.img.style, { width: s.nw * k + 'px', height: s.nh * k + 'px', left: -cx * k + 'px', top: -cy * k + 'px', objectFit: 'fill' });
  }
  if (s.img && !s.frames) s.img.src = s.url;
}

function buildOverlay(o) {
  if (o.type === 'caption') return;
  if (o.type === 'lower_third') o.node = el('div', 'ov lower', stage, `${o.title ? `<small><i class="dot"></i>${esc(o.title)}</small>` : ''}<div>${esc(o.text)}</div>`);
  else if (o.type === 'stamp') o.node = el('div', 'ov stamp' + (o.big ? ' big' : ''), stage, `<i class="dot"></i>${esc(o.text)}`);
  else if (o.type === 'counter') {
    o.node = el('div', 'ov counter', stage);
    const row = el('div', 'row', o.node);
    o.nums = o.items.map(it => { const d = el('div', 'item', row); const b = el('b', '', d); el('span', '', d, esc(it.label)); return b; });
    if (o.title) el('small', '', o.node, esc(o.title));
  } else if (o.type === 'highlight') {
    o.node = el('div', 'ov hl' + (o.box === false ? ' nobox' : ''), stage);
    if (o.label) o.lab = el('div', 'hl-label', stage, esc(o.label));
  } else if (o.type === 'cursor') {
    o.rip = el('div', 'ov ripple', stage);
    o.node = el('div', 'ov cursor', stage, '<svg viewBox="0 0 28 28" width="40" height="40"><path d="M3 2 L3 22.5 L8.2 17.6 L12 26 L15.6 24.4 L11.9 16.3 L19 16.3 Z" fill="#141413" stroke="#FFFFFF" stroke-width="1.8" stroke-linejoin="round"/></svg>');
    o.node.style.filter = 'drop-shadow(0 2px 3px rgba(0,0,0,.25))';
    if (o.touch) { o.node.innerHTML = ''; Object.assign(o.node.style, { width: '44px', height: '44px', borderRadius: '50%', background: 'rgba(255,255,255,.42)', border: '2px solid rgba(255,255,255,.8)', filter: 'none' }); }
  }
  else if (o.type === 'scoreboard') {
    o.node = el('div', 'ov score', stage);
    o.rows.forEach(r => { r.node = el('div', 'srow', o.node, `<span>${esc(r.label)}</span><b></b>`); r.val = r.node.querySelector('b'); });
    if (o.note) { o.noteNode = el('div', 'snote', o.node, `<i class="lock"></i>${esc(o.note.text)}`); }
  } else if (o.type === 'chapters') {
    o.node = el('div', 'ov chapters', stage);
    o.chips = o.items.map(c => el('span', 'chap', o.node, esc(c.label)));
  } else if (o.type === 'compare') {
    o.node = el('div', 'ov compare', stage, o.tiles.map((t, i) => `<div class="tile ${i ? 'them' : 'us'}"><small>${esc(t.title)}</small>${t.rows.map(r => `<div class="trow"><b>${esc(r[0])}</b><span>${esc(r[1])}</span></div>`).join('')}</div>`).join(''));
    o.tileNodes = [...o.node.querySelectorAll('.tile')];
    if (o.scrim) { o.scrimNode = el('div', 'ov scrim', stage); o.scrimNode.style.zIndex = 999; }
  } else if (o.type === 'timesaved') {
    o.node = el('div', 'ov saved', stage, `<div class="sv a"><span>By hand</span>${esc(o.hand)} <em>estimate</em></div><div class="sv b"><span>Inky</span>${esc(o.inky)}</div>`);
    o.parts = [...o.node.querySelectorAll('.sv')];
  } else if (o.type === 'badges') {
    o.node = el('div', 'ov badges', stage, o.items.map(b => `<span><i class="dot"></i>${esc(b)}</span>`).join(''));
    o.parts = [...o.node.querySelectorAll('span')];
  }
  if (o.node) o.node.style.zIndex = 1000 + (o.z || 0);
  if (o.lab) o.lab.style.zIndex = 1001 + (o.z || 0);
}

window.setup = async function (tl) {
  TL = tl; stage = document.getElementById('stage');
  if (tl.scale && tl.scale !== 1) stage.style.transform = `scale(${tl.scale})`;
  shots = tl.shots; overlays = tl.overlays || [];
  shots.forEach(buildShot);
  // an outgoing shot holds under the incoming one until the incoming transition is done
  shots.forEach((s, i) => {
    s.hold = s.end;
    const n = shots[i + 1];
    if (n && n.start <= s.end + 1e-3 && (n.transition || {}).type !== 'cut') s.hold = Math.max(s.end, n.start + (n.transition?.dur ?? .35));
  });
  const shotById = Object.fromEntries(shots.map(s => [s.id, s]));
  overlays.forEach(o => { o.shotRef = o.shot ? shotById[o.shot] : null; buildOverlay(o); });
  capEl = el('div', 'caption', stage); capEl.style.zIndex = 2000;
  await document.fonts.ready;
  await Promise.all(['400 20px Geist', '500 20px Geist', '600 20px Geist', '400 20px "Geist Mono"', '500 20px "Geist Mono"'].map(f => document.fonts.load(f, 'Łódź €')));
  await Promise.all(shots.filter(s => s.img && !s.frames).map(s => s.img.decode().catch(() => { })));
  return { shots: shots.length, overlays: overlays.length };
};

function poseShot(s, t) {
  const lt = t - s.start;
  const tr = s.transition || { type: 'fade', dur: .35 };
  const p = tr.type === 'cut' ? 1 : ramp(t, s.start, s.start + (tr.dur ?? .35), 'cubic');
  s.node.style.display = (s.type === 'card' || s.type === 'endcard') ? 'flex' : 'block';
  s.node.style.opacity = tr.type === 'slide' ? 1 : p;
  s.node.style.transform = tr.type === 'slide' ? `translateX(${(1 - p) * W}px)` : tr.type === 'scale' ? `scale(${lerp(.965, 1, p)})` : '';
  if (tr.type === 'scale') s.node.style.transformOrigin = '50% 50%';
  s.inP = p;
  if (s.inner && s.type === 'card') {
    const q = ramp(lt, 0.05, 0.7, 'outCubic'), w = ramp(lt, 0.35, 1.05, 'outCubic');
    s.inner.style.transform = `scale(${lerp(1, 1.025, c01(lt / Math.max(1, s.end - s.start)))})`;
    if (s.logo) { s.logo.style.opacity = q; s.logo.style.transform = `scale(${lerp(0.94, 1, q)})`; }
    s.word.style.opacity = w; s.word.style.transform = `translateX(${(1 - w) * -28}px)`;
    const b = lt > 1.25 && lt < 1.47 ? Math.sin((lt - 1.25) / 0.22 * Math.PI) : 0;   // one soft blink
    (s.eyes || []).forEach(e => { e.style.transformBox = 'fill-box'; e.style.transformOrigin = '50% 50%'; e.style.transform = `scaleY(${1 - 0.9 * b})`; });
  }
  if (s.inner && s.type === 'endcard') {
    s.inner.style.transform = `scale(${lerp(1, 1.03, c01(lt / Math.max(1, s.end - s.start)))})`;
    s.inner.style.opacity = ramp(lt, 0, 0.5, 'outCubic');
    s.chips.forEach((c, i) => { const q = ramp(lt, 0.5 + i * 0.12, 0.85 + i * 0.12, 'outCubic'); c.style.opacity = q; c.style.transform = `translateY(${(1 - q) * 8}px)`; });
  }
  if (s.world) { const X = camXform(s, lt); s.world.style.transform = `translate(${X.tx}px,${X.ty}px) scale(${X.z})`; }
  if (s.frames && s.img) {
    const st = srcTime(s.map, lt), n = Math.max(1, Math.min(s.frames.count, Math.floor(st * s.frames.fps + 1e-4) + 1));
    const url = s.frames.base + String(n).padStart(5, '0') + '.jpg';
    if (s.cur !== url) { s.img.src = url; s.cur = url; }
  }
}

function place(node, x, y, opacity, extra = '') {
  node.style.display = opacity > 0.001 ? (/\b(stamp|compare|saved|badges|chapters)\b/.test(node.className) ? 'flex' : 'block') : 'none';
  node.style.opacity = opacity;
  node.style.transform = `translate(${x}px,${y}px) ${extra}`;
}

function poseOverlay(o, t) {
  const on = t >= o.start && t < o.end;
  const hide = () => { if (o.node) o.node.style.display = 'none'; if (o.lab) o.lab.style.display = 'none'; if (o.rip) o.rip.style.display = 'none'; o.vis = 0; };
  if (o.type === 'caption' || !on) return hide();
  const fi = o.fade ?? .35, a = fade(t, o.start, o.end, fi), s = o.shotRef, lt = s ? t - s.start : 0;
  o.vis = a;
  if (o.type === 'lower_third' || o.type === 'counter') {
    const pos = o.pos || {};
    o.node.style.left = pos.right != null ? 'auto' : (pos.x ?? 88) + 'px'; o.node.style.right = pos.right != null ? pos.right + 'px' : 'auto';
    o.node.style.bottom = (pos.bottom ?? 64) + 'px';
    place(o.node, 0, (1 - a) * 18, a);
    if (o.type === 'counter') o.items.forEach((it, i) => {
      const p = ramp(t, o.start + .25 + i * .12, o.start + .25 + i * .12 + (o.count ?? 1.3), o.countEase || 'outQuint');
      o.nums[i].textContent = (it.prefix || '') + lerp(it.from ?? 0, it.value, p).toFixed(it.decimals || 0);
    });
  } else if (o.type === 'stamp') {
    const pos = o.pos || { x: 88, y: 76 };
    place(o.node, pos.x, pos.y + (1 - a) * -10, a);
  } else if (o.type === 'highlight') {
    const [x, y, w, h] = o.rect, sp = o.space || 'norm', pg = o.page || [W, H];
    const p0 = s ? mapPt(s, lt, x, y, sp, pg) : { x, y }, p1 = s ? mapPt(s, lt, x + w, y + h, sp, pg) : { x: x + w, y: y + h };
    const m = o.margin ?? 8;
    Object.assign(o.node.style, { width: p1.x - p0.x + 2 * m + 'px', height: p1.y - p0.y + 2 * m + 'px' });
    place(o.node, p0.x - m, p0.y - m, a * (s ? s.inP : 1));
    if (o.lab) {
      const below = o.labelPos !== 'above';
      place(o.lab, p0.x - m, below ? p1.y + m + 12 : p0.y - m - 56, a * (s ? s.inP : 1));
    }
  } else if (o.type === 'cursor') poseCursor(o, t, lt, s, a);
  else if (o.type === 'scoreboard') poseScore(o, t, a);
  else if (o.type === 'chapters') {
    place(o.node, 0, (1 - a) * -8, a);
    o.node.style.left = '50%'; o.node.style.transform += ' translateX(-50%)';
    o.chips.forEach((c, i) => {
      const it = o.items[i], cur = t >= it.from && t < it.to, done = t >= it.to || (it.lit != null && t >= it.lit && !cur);
      c.className = 'chap' + (cur ? ' cur' : done ? ' done' : '');
    });
  } else if (o.type === 'compare') {
    const pos = o.pos || {};
    o.node.style.left = '50%'; o.node.style.bottom = (pos.bottom ?? 150) + 'px';
    place(o.node, 0, (1 - a) * 18, a, 'translateX(-50%)');
    o.tileNodes.forEach((n, i) => { const q = ramp(t, o.start + i * 0.45, o.start + i * 0.45 + 0.4, 'outCubic'); n.style.opacity = q; n.style.transform = `translateY(${(1 - q) * 10}px)`; });
    if (o.scrimNode) place(o.scrimNode, 0, 0, a * o.scrim);
  } else if (o.type === 'timesaved' || o.type === 'badges') {
    const pos = o.pos || { x: 88, y: 110 };
    if (pos.bottom != null) { o.node.style.top = 'auto'; o.node.style.bottom = pos.bottom + 'px'; place(o.node, pos.x, (1 - a) * 12, a); }
    else place(o.node, pos.x, pos.y + (1 - a) * -8, a);
    o.parts.forEach((n, i) => { const q = ramp(t, o.start + i * (o.stagger ?? 0.8), o.start + i * (o.stagger ?? 0.8) + 0.35, 'outCubic'); n.style.opacity = q; n.style.transform = `translateY(${(1 - q) * 8}px)`; });
  }
}

// rows of [t, value] steps; each change counts up over `dur` (eased), rows appear at their first step
function poseScore(o, t, a) {
  place(o.node, 0, (1 - a) * -8, a);
  o.node.style.left = 'auto'; o.node.style.right = (o.pos?.right ?? 40) + 'px'; o.node.style.top = (o.pos?.top ?? 22) + 'px';
  o.rows.forEach(r => {
    const first = r.steps[0][0];
    r.node.style.display = t >= first - 0.01 ? 'flex' : 'none';
    let v = r.steps[0][1], pulse = 0;
    for (let i = 1; i < r.steps.length; i++) {
      const [ts, tv] = r.steps[i], d = r.dur ?? 1.1;
      if (t >= ts) { v = lerp(r.steps[i - 1][1], tv, ramp(t, ts, ts + d, 'outCubic')); pulse = Math.max(pulse, 1 - c01((t - ts) / 1.4)); }
    }
    const txt = (r.prefix || '') + v.toLocaleString('en-US', { minimumFractionDigits: r.decimals || 0, maximumFractionDigits: r.decimals || 0 });
    if (r.val.textContent !== txt) r.val.textContent = txt;
    r.node.style.color = pulse > 0 ? `rgba(194,80,47,${0.35 + 0.65 * pulse})` : '';
    r.node.style.opacity = ramp(t, first - 0.01, first + 0.4);
  });
  if (o.noteNode) {
    const n = o.note, on = t >= n.from;
    o.noteNode.style.display = on ? 'flex' : 'none';
    o.noteNode.style.opacity = ramp(t, n.from, n.from + 0.4);
    const pl = (n.pulse || []).reduce((m, p) => Math.max(m, t >= p && t < p + 1.2 ? Math.sin((t - p) / 1.2 * Math.PI) : 0), 0);
    o.noteNode.style.background = `rgba(232,111,81,${0.08 + 0.22 * pl})`;
  }
}

function poseCursor(o, t, lt, s, a) {
  const pts = o.points; if (!pts || !pts.length) return;
  const sp = o.space || 'page', pg = o.page || [W, H];
  let x = pts[0].x, y = pts[0].y;
  for (let i = 1; i < pts.length; i++) {
    const p0 = pts[i - 1], p1 = pts[i];
    if (lt >= p1.t) { x = p1.x; y = p1.y; continue; }
    const md = Math.min(p1.move ?? o.move ?? .75, p1.t - p0.t);
    const p = ramp(lt, p1.t - md, p1.t, 'cubic');
    x = lerp(p0.x, p1.x, p); y = lerp(p0.y, p1.y, p); break;
  }
  const q = s ? mapPt(s, lt, x, y, sp, pg) : { x, y, z: 1 };
  // Screen Studio "hide when idle": shown from just before each move until `idle` s after the point
  const idle = o.idle ?? 1.6;
  let act = 0;
  pts.forEach((p, i) => {
    const a0 = p.t - Math.min(p.move ?? o.move ?? .75, i ? p.t - pts[i - 1].t : 1) - .25;
    act = Math.max(act, fade(lt, a0, p.t + idle, .25));
  });
  const vis = a * (s ? s.inP : 1) * act;
  let press = 1, rip = null;
  for (const p of pts) if (p.click) {
    const d = lt - p.t;
    if (d >= -.08 && d < .12) press = .86;
    if (d >= 0 && d < .5) rip = d / .5;
  }
  const sc = (o.size ?? 1.0) * Math.min(1.5, Math.max(1, q.z ** .5));
  if (o.touch) place(o.node, q.x - 22, q.y - 22, vis, `scale(${press})`);
  else place(o.node, q.x - 4 * sc, q.y - 3 * sc, vis, `scale(${sc * press})`);
  if (rip != null) {
    const r = lerp(10, 34, EASE.outCubic(rip)) * sc;
    Object.assign(o.rip.style, { width: 2 * r + 'px', height: 2 * r + 'px' });
    place(o.rip, q.x - r, q.y - r, vis * (1 - rip));
  } else o.rip.style.display = 'none';
}

function hiCaption(text) {
  let h = esc(text);
  const keys = (TL.caption_keys || []).slice().sort((a, b) => b.length - a.length);
  // key phrases (whole words) and standalone numbers (not the 8 in n8n) turn coral
  const phrases = keys.map(k => '\\b' + k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b');
  const rx = new RegExp('(' + phrases.concat(['(?<![\\w])[€$~]?\\d(?:[\\d,.]*\\d)?(?![\\w])']).join('|') + ')', 'gi');
  return h.replace(rx, m => `<span class="kw">${m}</span>`);
}

function poseCaption(t) {
  const c = (TL.captions || []).find(c => t >= c.start && t < c.end);
  if (!c) { capEl.style.display = 'none'; return; }
  if (capText !== c.text) { capEl.innerHTML = hiCaption(c.text); capText = c.text; }
  let lift = 0;
  for (const o of overlays) if (o.vis > 0 && o.node && (o.lift ?? (o.type === 'lower_third' || o.type === 'counter')))
    lift = Math.max(lift, (o.node.offsetHeight + 24 + ((o.pos || {}).bottom ?? 64) - 60) * EASE.cubic(o.vis));
  const top = (TL.caption_top || []).some(w => t >= w[0] && t < w[1]);
  const left = (TL.caption_left || []).some(w => t >= w[0] && t < w[1]);
  capEl.style.left = left ? '56px' : '50%';
  capEl.style.transform = left ? 'none' : 'translateX(-50%)';
  capEl.style.textAlign = left ? 'left' : 'center';
  capEl.style.display = 'block';
  capEl.style.opacity = fade(t, c.start, c.end, .15);
  capEl.style.bottom = top ? 'auto' : 60 + lift + 'px';
  capEl.style.top = top ? '92px' : 'auto';
}

window.renderAt = async function (t) {
  for (const s of shots) {
    if (t >= s.start && t < s.hold) poseShot(s, t);
    else { s.node.style.display = 'none'; s.inP = 0; }
  }
  // slide: push the outgoing shot out while the incoming one comes in
  shots.forEach((s, i) => {
    if (i && (s.transition || {}).type === 'slide' && t >= s.start && t < s.start + (s.transition.dur ?? .35)) {
      const prev = shots[i - 1]; prev.node.style.transform = `translateX(${-s.inP * W}px)`;
    }
  });
  overlays.forEach(o => poseOverlay(o, t));
  poseCaption(t);
  const imgs = shots.filter(s => s.img && s.node.style.display !== 'none').map(s => s.img);
  await Promise.all(imgs.map(i => i.decode().catch(() => { })));
  return imgs.length;
};
