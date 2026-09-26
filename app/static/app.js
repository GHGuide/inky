'use strict';
// Inky front-end: hash routes, plain template strings, data from /api/*. Every number on screen comes from the API.

// ---------- tiny helpers ----------
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const raw = (s) => ({ __raw: String(s) });
const show = (v) => (v == null || v === false ? '' : Array.isArray(v) ? v.map(show).join('') : v.__raw != null ? v.__raw : esc(v));
const h = (s, ...v) => raw(s.reduce((o, x, i) => o + x + (i < v.length ? show(v[i]) : ''), ''));
const has = (n) => n != null && n !== '' && !Number.isNaN(Number(n));
const num = (n) => (has(n) ? Number(n).toLocaleString('en') : '–');
const eur = (n) => (has(n) ? '€' + Math.round(n).toLocaleString('en') : '–');
const pct = (n) => (has(n) ? Number(n).toFixed(1) + '%' : '–');
const safeUrl = (u) => (typeof u === 'string' && /^https?:\/\//i.test(u) ? u : '');
const CITY = { porto: 'Porto', bari: 'Bari', lodz: 'Łódź' };
const city = (c) => CITY[c] || (c ? String(c)[0].toUpperCase() + String(c).slice(1) : '');
const money = (c) => (c === 'lodz' ? 'złoty' : 'euro');
const clock = (iso) => (iso ? new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '–');
const day = (iso) => (iso ? new Date(iso).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }) : '');
const short = (s, n = 44) => { const t = String(s).replace(/^https?:\/\/(www\.)?/i, ''); return t.length > n ? t.slice(0, n - 1) + '…' : t; };
const pick = (o, ...keys) => { for (const k of keys) if (o && o[k] != null) return o[k]; return undefined; };
const CORAL = '#E86F51';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// ?rec=1: recording mode (1440-wide design scaled to the window, slower motion). ?replay=1: replay the last interview (?replay=4 = 4× faster).
const Q = new URLSearchParams(location.search);
const REC = Q.has('rec'), REPLAY = Q.has('replay') ? Math.max(0.1, Number(Q.get('replay')) || 1) : 0;
const SLOW = REC ? 1.3 : 1;

// ---------- icons and critters (copied from Nav.dc.html / Critter.dc.html) ----------
const P = {
  plus: 'M12 5v14 M5 12h14', market: 'M3 9l1.5-5h15L21 9 M3 9h18v11H3z M9 20v-6h6v6',
  clock: 'M21 12a9 9 0 1 1-18 0a9 9 0 1 1 18 0 M12 7v5l3 2', mic: 'M9 6a3 3 0 0 1 6 0v5a3 3 0 0 1-6 0z M5 11a7 7 0 0 0 14 0 M12 18v3',
  send: 'M12 19V5 M6 11l6-6 6 6', merge: 'M6 4v5a3 3 0 0 0 3 3h6a3 3 0 0 1 3 3v5 M6 20v-4 M18 4v4',
  mail: 'M4 6h16v12H4z M4 7l8 6 8-6', search: 'M18 11a7 7 0 1 1-14 0a7 7 0 1 1 14 0 M20 20l-4-4',
  check: 'M4 12l5 5L20 6', lock: 'M5 11h14v10H5z M8 11V8a4 4 0 0 1 8 0v3',
};
const icon = (d, size = 16, w = 2, color = 'currentColor') => raw(`<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${d}"/></svg>`);
const APIFY = raw('<svg width="15" height="15" viewBox="0 0 32 32" fill="none" aria-label="Apify"><path d="M18.3512 0H31.5152C31.7829 0 32 0.217074 32 0.484848V20.6025C32 21.0844 31.3733 21.2712 31.1094 20.868L17.9455 0.750323C17.7345 0.427859 17.9659 0 18.3512 0Z" fill="#246DFF"/><path d="M13.6488 0H0.484848C0.217074 0 0 0.217074 0 0.484848V20.6025C0 21.0844 0.626717 21.2712 0.890559 20.868L14.0545 0.750323C14.2655 0.427859 14.0341 0 13.6488 0Z" fill="#20A34E"/><path d="M15.7745 16.1069L0.820235 31.1736C0.51656 31.4796 0.733277 32 1.16436 32H30.848C31.2773 32 31.4948 31.4832 31.1947 31.1762L16.4653 16.1095C16.2761 15.916 15.9651 15.9148 15.7745 16.1069Z" fill="#F86606"/></svg>');
const N8N = raw('<svg width="16" height="16" viewBox="0 0 24 24" aria-label="n8n"><path fill="#EA4B71" d="M21.4737 5.6842c-1.1772 0-2.1663.8051-2.4468 1.8947h-2.8955c-1.235 0-2.289.893-2.492 2.111l-.1038.623a1.263 1.263 0 0 1-1.246 1.0555H11.289c-.2805-1.0896-1.2696-1.8947-2.4468-1.8947s-2.1663.8051-2.4467 1.8947H4.973c-.2805-1.0896-1.2696-1.8947-2.4468-1.8947C1.1311 9.4737 0 10.6047 0 12s1.131 2.5263 2.5263 2.5263c1.1772 0 2.1663-.8051 2.4468-1.8947h1.4223c.2804 1.0896 1.2696 1.8947 2.4467 1.8947 1.1772 0 2.1663-.8051 2.4468-1.8947h1.0008a1.263 1.263 0 0 1 1.2459 1.0555l.1038.623c.203 1.218 1.257 2.111 2.492 2.111h.3692c.2804 1.0895 1.2696 1.8947 2.4468 1.8947 1.3952 0 2.5263-1.131 2.5263-2.5263s-1.131-2.5263-2.5263-2.5263c-1.1772 0-2.1664.805-2.4468 1.8947h-.3692a1.263 1.263 0 0 1-1.246-1.0555l-.1037-.623A2.52 2.52 0 0 0 13.9607 12a2.52 2.52 0 0 0 .821-1.4794l.1038-.623a1.263 1.263 0 0 1 1.2459-1.0555h2.8955c.2805 1.0896 1.2696 1.8947 2.4468 1.8947 1.3952 0 2.5263-1.131 2.5263-2.5263s-1.131-2.5263-2.5263-2.5263"/></svg>');
const TG = raw('<svg width="15" height="15" viewBox="0 0 24 24" aria-label="Telegram"><path fill="#26A5E4" d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>');
const LOGO = raw('<svg class="critter" width="26" height="26" viewBox="0 0 120 120" aria-hidden="true"><g fill="none" stroke="#E86F51" stroke-width="11" stroke-linecap="round"><path d="M34 76 C 28 92, 16 98, 20 110"/><path d="M47 80 C 45 96, 38 104, 42 114"/><path d="M60 82 C 62 98, 56 106, 60 114"/><path d="M73 80 C 75 96, 82 104, 78 114"/><path d="M86 76 C 92 92, 104 98, 100 110"/></g><ellipse cx="60" cy="52" rx="38" ry="36" fill="#E86F51"/><g class="eyes"><ellipse cx="46" cy="54" rx="5.5" ry="7.5" fill="#111110"/><ellipse cx="74" cy="54" rx="5.5" ry="7.5" fill="#111110"/><circle cx="48" cy="51" r="2" fill="#FFFFFF"/><circle cx="76" cy="51" r="2" fill="#FFFFFF"/></g><path d="M54 66 Q60 72 66 66" fill="none" stroke="#111110" stroke-width="3" stroke-linecap="round"/></svg>');
const FACE = '<g class="eyes"><ellipse cx="46" cy="54" rx="5.5" ry="7.5" fill="#1D1A17"/><ellipse cx="74" cy="54" rx="5.5" ry="7.5" fill="#1D1A17"/><circle cx="48" cy="51" r="2" fill="#FFFFFF"/><circle cx="76" cy="51" r="2" fill="#FFFFFF"/></g>';
const BODY = {
  octopus: (c) => `<g fill="none" stroke="${c}" stroke-width="11" stroke-linecap="round"><path d="M34 76 C 28 92, 16 98, 20 110"/><path d="M47 80 C 45 96, 38 104, 42 114"/><path d="M60 82 C 62 98, 56 106, 60 114"/><path d="M73 80 C 75 96, 82 104, 78 114"/><path d="M86 76 C 92 92, 104 98, 100 110"/></g><ellipse cx="60" cy="52" rx="38" ry="36" fill="${c}"/><ellipse cx="46" cy="30" rx="11" ry="6" fill="#FFFFFF" opacity="0.35"/>${FACE}<ellipse cx="35" cy="66" rx="6" ry="3.5" fill="#F7A99A"/><ellipse cx="85" cy="66" rx="6" ry="3.5" fill="#F7A99A"/><path d="M54 66 Q60 72 66 66" fill="none" stroke="#1D1A17" stroke-width="3" stroke-linecap="round"/>`,
  cat: (c) => `<path d="M24 46 L30 10 L54 30 Z" fill="${c}"/><path d="M96 46 L90 10 L66 30 Z" fill="${c}"/><path d="M32 36 L34 20 L45 29 Z" fill="#F7A99A"/><path d="M88 36 L86 20 L75 29 Z" fill="#F7A99A"/><ellipse cx="46" cy="106" rx="9" ry="7" fill="${c}"/><ellipse cx="74" cy="106" rx="9" ry="7" fill="${c}"/><ellipse cx="60" cy="62" rx="40" ry="38" fill="${c}"/><ellipse cx="46" cy="38" rx="10" ry="5" fill="#FFFFFF" opacity="0.3"/><g class="eyes"><ellipse cx="46" cy="55" rx="5.5" ry="7.5" fill="#1D1A17"/><ellipse cx="74" cy="55" rx="5.5" ry="7.5" fill="#1D1A17"/><circle cx="48" cy="52" r="2" fill="#FFFFFF"/><circle cx="76" cy="52" r="2" fill="#FFFFFF"/></g><ellipse cx="34" cy="69" rx="6" ry="3.5" fill="#F7A99A"/><ellipse cx="86" cy="69" rx="6" ry="3.5" fill="#F7A99A"/><path d="M57 66 L63 66 L60 70 Z" fill="#F7A99A"/><path d="M53 73 Q56.5 77 60 73 Q63.5 77 67 73" fill="none" stroke="#1D1A17" stroke-width="2.5" stroke-linecap="round"/><g stroke="#1D1A17" stroke-width="2" stroke-linecap="round" opacity="0.45"><path d="M18 64 L34 66"/><path d="M18 73 L34 71"/><path d="M102 64 L86 66"/><path d="M102 73 L86 71"/></g>`,
  blob: (c) => `<path d="M22 58 Q22 16 60 16 Q98 16 98 58 L98 102 Q91 94 83 102 Q75 110 67 102 Q60 95 53 102 Q45 110 37 102 Q29 94 22 102 Z" fill="${c}"/><ellipse cx="44" cy="32" rx="11" ry="6" fill="#FFFFFF" opacity="0.35"/>${FACE}<ellipse cx="35" cy="67" rx="6" ry="3.5" fill="#F7A99A"/><ellipse cx="85" cy="67" rx="6" ry="3.5" fill="#F7A99A"/><path d="M53 66 Q60 74 67 66" fill="none" stroke="#1D1A17" stroke-width="3" stroke-linecap="round"/>`,
};
const ACC = {
  glasses: '<g fill="#FFFFFF" fill-opacity="0.25" stroke="#1D1A17" stroke-width="3.5"><circle cx="46" cy="54" r="12"/><circle cx="74" cy="54" r="12"/></g><path d="M58 53 Q60 50 62 53" fill="none" stroke="#1D1A17" stroke-width="3.5"/>',
  beanie: '<path d="M24 34 Q24 4 60 4 Q96 4 96 34 Z" fill="#3B5BDB"/><rect x="20" y="28" width="80" height="12" rx="6" fill="#2A45B0"/><circle cx="60" cy="5" r="7" fill="#F3ECE1"/>',
  headphones: '<path d="M20 56 Q20 10 60 10 Q100 10 100 56" fill="none" stroke="#1D1A17" stroke-width="6" stroke-linecap="round"/><rect x="11" y="46" width="17" height="27" rx="7" fill="#1D1A17"/><rect x="92" y="46" width="17" height="27" rx="7" fill="#1D1A17"/><rect x="15" y="51" width="9" height="17" rx="4.5" fill="#F2957C"/><rect x="96" y="51" width="9" height="17" rx="4.5" fill="#F2957C"/>',
  bow: '<g transform="translate(88 24) rotate(18)"><path d="M0 0 L-15 -10 L-15 10 Z" fill="#F07BA8"/><path d="M0 0 L15 -10 L15 10 Z" fill="#F07BA8"/><circle cx="0" cy="0" r="5" fill="#D9558A"/></g>',
};
const critter = (size, kind = 'octopus', color = CORAL, acc = 'none') =>
  raw(`<svg class="critter" width="${size}" height="${size}" viewBox="0 0 120 120" aria-hidden="true">${BODY[kind](color)}${ACC[acc] || ''}</svg>`);

// ---------- state ----------
const S = { state: {}, runs: [], detail: null, summary: null, end: null, loaded: false, log: [], busy: false, v: null, shared: null, shareBusy: false, shareErr: '',
  job: null, f: { city: '', min: 0 }, why: new Set(), seenBase: null };
const box = (area) => ({ get(k) { try { return JSON.parse(area().getItem(k)); } catch { return null; } }, set(k, v) { try { area().setItem(k, JSON.stringify(v)); } catch { /* private mode */ } } });
const store = box(() => sessionStorage), keep = box(() => localStorage);
const freshIv = (prompt = '') => ({ prompt, messages: [], rounds: [], done: null, busy: false, error: '' });
let iv = { ...freshIv(), ...store.get('inky.iv'), busy: false };
const saveIv = () => { store.set('inky.iv', iv); if (iv.done) keep.set('inky.iv.last', iv); };  // the last finished interview, for ?replay=1 in a new tab
const current = () => { const r = iv.rounds[iv.rounds.length - 1]; return r && !r.answers ? r : null; };

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => null);
  if (!r.ok) throw Object.assign(new Error((data && data.error) || `${r.status} ${r.statusText}`), { status: r.status });
  return data;
}
// POST that answers with Server-Sent Events: calls on(event) for every `data: {json}` block, in order.
async function sse(path, body, on) {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  if (!r.ok) { const d = await r.json().catch(() => null); throw Object.assign(new Error((d && d.error) || `${r.status} ${r.statusText}`), { status: r.status }); }
  if (!/event-stream/.test(r.headers.get('Content-Type') || '')) return on({ type: 'done', ...(await r.json().catch(() => ({}))) });
  const rd = r.body.getReader(), dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await rd.read();
    buf += dec.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buf.split(/\r?\n\r?\n/);
    buf = done ? '' : blocks.pop();
    for (const b of blocks) {
      const data = b.split(/\r?\n/).filter((l) => l.startsWith('data:')).map((l) => l.slice(5).trim()).join('\n');
      let ev = null;
      try { ev = data && JSON.parse(data); } catch { /* not JSON: skip */ }
      if (ev && typeof ev === 'object') await on(ev);
    }
    if (done) return;
  }
}
const since = () => new Date(Date.now() - 24 * 3600e3).toISOString();
const usd = (x) => '$' + Number(x).toFixed(2);
const usdRun = (sm) => (has(sm.apify_usd_per_run) ? `${usd(sm.apify_usd_per_run)} a run on Apify` : has(sm.apify_usd) ? `${usd(sm.apify_usd)} on Apify` : '');
const okSummary = (x) => (x && typeof x === 'object' && has(x.runs) ? x : null);  // null: not on this server yet (404), or no n8n
async function refresh() {
  // The summary reads every n8n run once (slow the first time, then cached), so it never holds up the rest of the screen.
  const sum = api('/api/summary?since=' + encodeURIComponent(since())).then(okSummary, () => null);
  const [st, runs, detail] = await Promise.all([api('/api/state').catch(() => null), api('/api/executions').catch(() => null), api('/api/run_detail').catch(() => null)]);
  S.state = st && typeof st === 'object' ? st : {};
  S.runs = Array.isArray(runs) ? runs : [];
  S.detail = detail && typeof detail === 'object' ? detail : null;
  S.loaded = true;
  const quick = await Promise.race([sum, sleep(1200).then(() => undefined)]);
  if (quick !== undefined) { S.summary = quick; return; }
  sum.then((x) => {  // arrived late: show it where it is used
    if (JSON.stringify(x) === JSON.stringify(S.summary)) return;
    S.summary = x;
    if (['workflow', 'activity', 'end'].includes(route()) && !S.busy && !jobOn() && !dirty()) render();
  });
}

// ---------- toasts ----------
function toast(text, bad) {
  let t = document.getElementById('toasts');
  if (!t) { t = document.createElement('div'); t.id = 'toasts'; t.setAttribute('role', 'status'); t.setAttribute('aria-live', 'polite'); document.body.append(t); }
  const el = document.createElement('div');
  el.className = 'toast' + (bad ? ' bad' : '');
  el.textContent = text;
  t.append(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 400); }, 3600 * SLOW);
}
const research = () => S.state.research || null;
const finalRules = () => (S.state.rules && S.state.rules.final) || [];
const versions = () => (S.state.rules && S.state.rules.versions) || (research() && research().versions) || [];
const n8n = () => S.state.n8n || {};
const built = () => !!safeUrl(n8n().main_url);
// ponytail: /api/state has no n8n "active" flag, so running = a scheduled run started in the last 30 min (it runs every 15).
const live = () => built() && S.runs.some((e) => e.workflow !== 'repair' && (e.status === 'running' || (e.mode === 'trigger' && Date.now() - new Date(e.startedAt) < 30 * 60e3)));
const count = (n, key, delay = 0) => (has(n) ? h`<span data-count="${Number(n)}" ${raw(key ? `data-key="${esc(key)}"` : '')} data-delay="${delay}">${num(n)}</span>` : '–');
const plural = (n, one, many = one + 's') => `${num(n)} ${Number(n) === 1 ? one : many}`;

// How many homes pass the current rules: a command result for exactly these rules, else the research version that had them.
const rulesKey = (rules) => JSON.stringify(rules || []);
function matchTotal() {
  const fin = finalRules(), vs = versions(), last = vs[vs.length - 1];
  if (!fin.length) return last ? last.matches : null;
  const known = (store.get('inky.counts') || {})[rulesKey(fin)];
  const v = [...vs].reverse().find((x) => x.rules && rulesKey(x.rules) === rulesKey(fin));
  return has(known) ? known : v ? v.matches : !S.state.rules && last ? last.matches : null;
}
// derive saves only the first 15 matches; after a command the ones that fail a new rule are hidden (fields a saved home carries).
const TEST = { '<=': (a, b) => a <= b, '>=': (a, b) => a >= b, '==': (a, b) => a === b, '!=': (a, b) => a !== b, in: (a, b) => [].concat(b).includes(a), not_in: (a, b) => ![].concat(b).includes(a) };
const HOME_FIELD = { price_eur: (m) => m.price_eur, size_m2: (m) => m.size_m2, bedrooms: (m) => m.bedrooms, net_yield: (m) => m.net_yield, city: (m) => m.city,
  currency: (m) => (m.city ? (m.city === 'lodz' ? 'PLN' : 'EUR') : null), price_m2: (m) => (m.price_eur && m.size_m2 ? m.price_eur / m.size_m2 : null) };
const passes = (m) => finalRules().every((r) => { const x = (HOME_FIELD[r.field] || ((h) => h[r.field]))(m); return x == null || !TEST[r.op] || TEST[r.op](x, r.value); });

// ---------- rule text ----------
const FIELD = {
  price_eur: ['Price', eur], bedrooms: ['Bedrooms', String], net_yield: ['Yield after costs', (v) => v + '%'],
  zone_rent_listings: ['Rentals nearby', String], price_trend: ['Price trend', (v) => v + '% a year'],
  price_vs_zone: ['Price vs neighbourhood', (v) => v + '×'], size_m2: ['Size', (v) => v + ' m²'],
  price_m2: ['Price per m²', eur], currency: ['Currency', String], city: ['City', city],
};
const OPS = { '<=': '≤', '>=': '≥', '<': '<', '>': '>', '==': 'is', '=': 'is', '!=': 'is not', in: 'is', not_in: 'is not', nin: 'is not' };
function ruleText(r) {
  if (!r || typeof r !== 'object') return String(r ?? '');
  const [label, f] = FIELD[r.field] || [String(r.field ?? '').replace(/_/g, ' '), String];
  const val = Array.isArray(r.value) ? r.value.map(f).join(' or ') : f(r.value);
  return `${label} ${OPS[r.op] || r.op || ''} ${val}`.replace(/\s+/g, ' ').trim();
}
function versionRules(vs, i) {
  const cur = vs[i].rules || [], prev = i ? vs[i - 1].rules || [] : null;
  const same = (a, b) => JSON.stringify([a.op, a.value]) === JSON.stringify([b.op, b.value]);
  const out = cur.map((r) => {
    const p = prev && prev.find((x) => x.id === r.id);
    const m = !prev ? '✓' : !p ? '+' : same(p, r) ? '✓' : '~';
    return { m, id: r.id, t: ruleText(r), why: m === '~' ? `${r.why || ''} Was: ${ruleText(p)}.` : r.why };
  });
  if (prev) prev.filter((p) => !cur.some((r) => r.id === p.id)).forEach((p) => out.push({ m: '−', id: p.id, t: ruleText(p), why: 'Dropped: it made no difference.' }));
  return out;
}

// ---------- shared pieces ----------
const me = (t) => h`<div class="me">${t}</div>`;
const inky = (body, acc) => h`<div class="inky">${critter(26, 'octopus', CORAL, acc)}<div class="inky-body">${body}</div></div>`;
const logLines = (items) => h`<div class="log">${items.filter(Boolean).map(([a, b]) => h`<div><div><span class="b">●</span> ${a}</div>${b ? h`<div class="sub">└ ${b}</div>` : ''}</div>`)}</div>`;
const empty = (text = 'Runs after the first build', sub) => h`<div class="empty">${critter(40)}<span>${text}</span>${sub ? h`<span class="note">${sub}</span>` : ''}</div>`;
const typing = () => h`<span class="typing" aria-label="Inky is thinking"><i></i><i></i><i></i></span>`;
const pill = (text, dot, hot) => h`<span class="pill ${hot ? 'hot' : ''}">${dot ? h`<span class="dot ${dot}"></span>` : ''}${text}</span>`;
function livePill() {
  const main = S.runs.find((e) => e.workflow !== 'repair');
  if (live()) return pill('Running · every 15 min', 'green');
  if (!built()) return pill('Not built yet', 'grey');
  return pill(main ? `Built in n8n · last run ${day(main.startedAt)} ${clock(main.startedAt)}` : 'Built in n8n · no runs yet', 'grey');
}
const ext = (url, label, cls = 'btn') => (safeUrl(url) ? h`<a class="${cls}" href="${url}" target="_blank" rel="noopener">${label} ↗</a>` : '');

function nav(active) {
  const need = S.runs.filter((r) => r.status === 'waiting').length;
  const cur = (on) => raw(on ? 'aria-current="page"' : '');
  const taskHref = research() ? '#results' : iv.done ? '#confirm' : '#task';
  return h`<nav class="nav" aria-label="Inky">
    <a class="brand" href="#home">${LOGO}<span>inky</span></a>
    <a class="newtask" href="#home">${icon(P.plus, 16, 2.2)}New task</a>
    <div class="navlabel">Tasks</div>
    <a class="navitem" href="${taskHref}" ${cur(active === 'task')}><span class="dot ${live() ? 'green' : ''}"></span><span>Buy-to-let abroad</span><span class="meta">${live() ? 'live' : built() ? 'built' : 'new'}</span></a>
    <div class="navfoot">
      ${need ? h`<a class="navitem need" href="#activity"><span class="dot coral"></span>${need} need you</a>` : ''}
      <a class="navitem" href="#activity" ${cur(active === 'activity')}>${icon(P.clock, 17)}Activity</a>
      <a class="navitem" href="#market" ${cur(active === 'market')}>${icon(P.market, 17)}Marketplace</a>
      <a class="connected" href="#workflow">${APIFY}${N8N}${TG}<span>${built() ? 'connected' : 'not connected yet'}</span></a>
    </div></nav>`;
}
function header(status, acc = 'none', shareOn = false) {
  return h`<header class="hdr"><div class="hdr-l">${critter(30, 'octopus', CORAL, acc)}<h1>Buy-to-let abroad</h1>${status}</div>
    <div class="row">${shareOn ? h`<span class="btn dark" aria-current="page">Share</span>` : h`<a class="btn" href="#share">Share</a>`}</div></header>`;
}
const TABS = [['Plan', 'task'], ['Research', 'research'], ['Screen', 'screen'], ['Results', 'results'], ['Workflow', 'workflow']];
const TAB_OF = { task: 'task', confirm: 'task', research: 'research', screen: 'screen', fast: 'screen', results: 'results', activity: 'results', workflow: 'workflow' };
function tabs(k) {
  return h`<nav class="tabs" aria-label="Task views">${TABS.map(([label, r]) => h`<a class="tab" href="${r === 'task' && iv.done ? '#confirm' : '#' + r}" ${raw(TAB_OF[k] === r ? 'aria-current="page"' : '')}>${label}</a>`)}</nav>`;
}
function composer(ph, act) {
  return h`<form class="composer" data-act="${act}"><div class="cbox">
    <label class="sr" for="msg">Message Inky</label>
    <input id="msg" name="text" type="text" autocomplete="off" placeholder="${ph}">
    <div class="cbar"><span class="hint">enter to send</span><div class="row" style="gap:6px">
      <button type="button" class="ibtn" data-act="mic" aria-label="Talk">${icon(P.mic, 17)}</button>
      <button type="submit" class="ibtn dark" aria-label="Send">${icon(P.send, 17, 2.2)}</button></div></div></div></form>`;
}
const skeleton = () => h`<div class="skel" style="height:44px;width:40%"></div><div class="skel" style="height:120px"></div><div class="skel" style="height:220px"></div><div class="skel" style="height:90px"></div>`;
function page(k, o) {
  if (!S.loaded && !(k === 'task' || (k === 'confirm' && iv.done))) o = { ...o, status: pill('Loading'), thread: inky(typing()), panel: o.bare ? h`<div class="body">${skeleton()}</div>` : skeleton() };  // first load: shimmer, not a flash of empty states
  const panel = o.bare ? o.panel : h`${tabs(k)}<div class="body">${o.panel}</div>`;
  return h`<div class="shell">${nav(o.nav || 'task')}<div class="col">${header(o.status, o.acc, o.share)}<div class="split">
    <section class="thread" aria-label="Conversation"><div class="msgs" role="log" aria-live="polite">${o.thread}${k === 'task' ? '' : commandLog()}</div>${composer(o.placeholder || 'Change a rule…', k === 'task' ? 'free' : 'command')}</section>
    <section class="panel" aria-label="${o.label || k}">${panel}</section></div></div></div>`;
}

// ---------- commands: the message box on every task screen ----------
function reply(r) {
  const removed = [].concat(r.removed || []).map((x) => (typeof x === 'object' ? x.id || ruleText(x) : x));
  return h`<p>${r.change || 'Done.'}</p>${logLines([
    r.rule && [`${r.rule.id ? r.rule.id + ': ' : ''}${ruleText(r.rule)}`, r.rule.why],
    removed.length && ['Removed ' + removed.join(', ')],
    has(r.matches_before) && has(r.matches_after) && [`${num(r.matches_before)} → ${plural(r.matches_after, 'home matches', 'homes match')}`, r.applied ? (r.n8n_error ? 'saved, n8n not updated yet' : 'saved to the n8n workflow') : 'nothing changed'],
    !has(r.matches_before) && r.applied && ['Saved the rule', r.n8n_error ? 'n8n not updated yet' : 'and updated the n8n workflow'],
  ])}`;
}
const isFresh = (t) => Date.now() - (t || 0) < 1500;
const commandLog = () => S.log.map((x) => h`<div class="${isFresh(x.t) ? 'fresh' : ''}" style="display:flex;flex-direction:column;gap:16px">${me(x.me)}</div>${x.res ? h`<div class="${isFresh(x.done) ? 'fresh' : ''}">${inky(reply(x.res))}</div>`
  : x.say ? h`<div class="${isFresh(x.done) ? 'fresh' : ''}">${inky(x.say)}</div>` : x.err ? inky(h`<p class="hot">That did not work: ${x.err}</p>`) : inky(typing())}`);
// "Send me the best ones now": the top homes go to Telegram with buttons (the n8n webhook), so there is a real approval to tap.
const BEST = /\b(send|give|text|message)\b.*\bbest\b/i;
async function bestNow(text = 'Send me the best 3 now.') {
  if (S.busy) return;
  const entry = { me: text, t: Date.now() };
  S.log.push(entry); S.busy = true; render();
  try {
    const r = await api('/api/best_now', { n: 3 }), ms = Array.isArray(r.matches) ? r.matches : [];
    const n = has(r.sent) ? Number(r.sent) : ms.length;
    entry.say = h`<p>Sent ${plural(n, 'home')} to your Telegram. Tap one there and I save a Gmail draft to the agent. Nothing is sent without you.</p>
      ${ms.length ? logLines(ms.slice(0, 3).map((m) => [m.title || 'A flat', [m.zone, city(m.city), has(m.net_yield) && pct(m.net_yield) + ' after costs'].filter(Boolean).join(' · ')])) : ''}`;
    toast(`Sent ${plural(n, 'home')} to your Telegram ✓`);
  } catch (e) {
    entry.err = e.status === 404 ? 'this server can’t send to Telegram yet.' : e.message;
    toast(e.status === 404 ? 'Sending isn’t on this server yet' : `Not sent: ${e.message}`, true);
  }
  entry.done = Date.now(); S.busy = false; render();
}

// ---------- live jobs: research and the n8n build stream their steps into the chat, one line at a time ----------
const jobOn = (kind) => !!S.job && S.job.state === 'run' && (!kind || S.job.kind === kind);
const jobMax = (j) => Math.max(1, ...j.lines.filter((l) => l.v).map((l) => Number(l.v.matches) || 0));
function jobLine(l, max, fresh) {
  if (l.v) return h`<div class="jv ${fresh ? 'fresh' : ''}"><span>v${l.v.v ?? ''}</span><div class="track"><div class="${fresh ? 'grow' : ''}" style="width:${Math.max(2, Math.round((100 * (Number(l.v.matches) || 0)) / max))}%"></div></div><span>${plural(l.v.matches ?? 0, 'home')}${has(l.v.zones) ? ' · ' + plural(l.v.zones, 'area') : ''}</span></div>`;
  return h`<div class="${fresh ? 'fresh' : ''}"><div><span class="b ${l.bad ? 'hot' : l.ok ? 'ok' : ''}">●</span> ${l.text || ''}</div>${l.sub ? h`<div class="sub">└ ${l.sub}</div>` : ''}</div>`;
}
function jobView(kind) {
  const j = S.job;
  if (!j || j.kind !== kind) return '';
  const max = jobMax(j);
  return h`<div class="inky job ${j.state === 'run' ? 'live' : ''}">${critter(26, 'octopus', CORAL, j.acc)}<div class="inky-body">
    <div class="log" id="job-lines">${j.lines.map((l) => { const f = !l.shown; l.shown = true; return jobLine(l, max, f); })}</div>
    ${j.state === 'run' ? typing() : ''}
    ${j.state === 'err' ? h`<p class="hot">That did not work: ${j.err}</p><div class="row"><button type="button" class="btn" data-act="${kind}">Try again</button></div>` : ''}
    ${j.links ? h`<div class="row">${ext(j.links.main, 'Open in n8n', 'btn dark')}${ext(j.links.repair, 'Open repair', 'btn')}</div>` : ''}</div></div>`;
}
// Lines come in bursts; show them one by one, like a terminal. Append to the DOM so the typing dots keep going.
async function jobPush(j, line) {
  const wait = j.last + (calm.matches ? 60 : 420 * SLOW) - Date.now();
  if (wait > 0) await sleep(wait);
  j.last = line.t = Date.now();
  const grew = line.v && (Number(line.v.matches) || 0) > jobMax(j);
  j.lines.push(line);
  const lines = document.getElementById('job-lines');
  if (S.job !== j || !lines) return;  // on another screen: the line is kept and shows when you come back
  if (grew) return render();  // a longer bar: redraw so every bar keeps the same scale
  lines.insertAdjacentHTML('beforeend', jobLine(line, jobMax(j), true).__raw);
  line.shown = true;  // a later full render shows it without rising in again
  const m = $('.msgs');
  if (m) m.scrollTop = m.scrollHeight;
  slowDown();
}
const stepEvents = (j) => async (ev) => {
  if (ev.type === 'step') await jobPush(j, { text: ev.text, sub: ev.sub });
  else if (ev.type === 'version') await jobPush(j, { v: ev });
  else if (ev.type === 'error') throw new Error(ev.text || 'it stopped.');
  else if (ev.type === 'done') j.fin = ev;
};
async function runResearch() {
  if (jobOn()) return;
  const plan = (iv.done && iv.done.plan) || S.state.plan || null;
  const j = S.job = { kind: 'research', acc: 'glasses', lines: [], state: 'run', last: 0 };
  render();
  const go = async () => { j.state = 'done'; render(); await sleep(1100 * SLOW); if (route() === 'confirm') location.hash = '#research'; };
  try {
    // research/run saves the plan itself (plan.json, the old one as plan.backup.json). /api/plan only when streaming research isn't there.
    try { await sse('/api/research/run', plan ? { plan } : {}, stepEvents(j)); }
    catch (e) {
      if (e.status === 404 && plan) await api('/api/plan', { plan }).then(() => jobPush(j, { text: 'Saved your plan', sub: 'plan.json, the old one kept as a backup' }), () => {});
      throw e;
    }
    if (!j.fin) throw new Error('the research stopped before it finished.');
    await refresh();
    if (j.fin.research && typeof j.fin.research === 'object') S.state.research = j.fin.research;
    if (j.fin.rules && typeof j.fin.rules === 'object') S.state.rules = j.fin.rules;
    store.set('inky.counts', {});  // new research, new counts
    S.v = null;
    const lv = versions()[versions().length - 1];
    await jobPush(j, { text: 'Research done', sub: lv ? `version ${lv.v} keeps ${plural(lv.matches, 'home')} in ${plural(lv.zones, 'neighbourhood')}` : 'saved', ok: true });
    toast('Research done ✓');
    await go();
  } catch (e) {
    if (e.status === 404) { await jobPush(j, { text: 'Live research isn’t on this server yet', sub: 'here is the last research instead' }); return go(); }
    j.state = 'err'; j.err = e.message; render();
  }
}
async function runBuild() {
  if (jobOn()) return;
  const j = S.job = { kind: 'build', acc: 'none', lines: [], state: 'run', last: 0 };
  render();
  const go = async () => { j.state = 'done'; render(); await sleep(2200 * SLOW); if (route() === 'research') location.hash = '#workflow'; };
  try {
    await sse('/api/build/run', Q.has('staging') ? { staging: true } : {}, stepEvents(j));
    if (!j.fin) throw new Error('the build stopped before it finished.');
    j.links = { main: j.fin.main_url, repair: j.fin.repair_url };
    await jobPush(j, { text: 'Published in your n8n', sub: 'it runs every 15 minutes from now, without me', ok: true });
    await refresh();
    toast('Saved to n8n ✓');
    await go();
  } catch (e) {
    if (e.status === 404 && built()) {
      j.links = { main: n8n().main_url, repair: n8n().repair_url };
      await jobPush(j, { text: 'The workflow is already in your n8n', sub: 'live building isn’t on this server yet', ok: true });
      return go();
    }
    j.state = 'err'; j.err = e.status === 404 ? 'building isn’t on this server yet.' : e.message; render();
  }
}
async function sendCommand(text) {
  const entry = { me: text, t: Date.now() };
  S.log.push(entry); S.busy = true; render();
  const before = rulesKey(finalRules());
  try {
    const r = entry.res = await api('/api/command', { text });
    await refresh();
    if (has(r.matches_before) && has(r.matches_after)) {  // remember both counts so every screen shows the same number
      const after = rulesKey(finalRules()), c = store.get('inky.counts') || {};
      c[before] = r.matches_before;
      if (after !== before) c[after] = r.matches_after;
      store.set('inky.counts', c);
    }
  } catch (e) { entry.err = e.message; }
  entry.done = Date.now();
  S.busy = false; render();
}

// ---------- interview ----------
function startInterview() {
  if (REPLAY) return replayInterview();
  if (iv.busy || iv.done || !iv.prompt || iv.messages.length) return;
  iv.messages = [{ role: 'user', content: iv.prompt }];
  askInterview();
}
async function askInterview() {
  iv.busy = true; iv.error = ''; render();
  try {
    const r = await api('/api/interview', { messages: iv.messages });
    if (r.done) iv.done = r;
    else iv.rounds.push({ round: r.round ?? iv.rounds.length + 1, questions: r.questions || [], understood: r.understood || [], answers: null });
  } catch (e) { iv.error = e.message; }
  iv.busy = false; saveIv();
  if (iv.done && location.hash !== '#confirm') location.hash = '#confirm'; else render();
}
function submitRound(content, answers) {
  const cur = current();
  if (!cur || iv.busy || REPLAY) return;  // a replay never calls the interview API
  cur.answers = answers;
  iv.messages.push({ role: 'assistant', content: JSON.stringify({ round: cur.round, understood: cur.understood, questions: cur.questions }) }, { role: 'user', content });
  askInterview();
}

// ---------- routes ----------
const SUGGEST = [
  ['Buy-to-let abroad, up to €200k', 'I want to buy a flat abroad, up to €200,000 in cash, that I can rent out for as much as possible, where prices will probably go up.'],
  ['A student flat in Łódź', 'Find me a small flat in Łódź near the universities that I can rent to students, under €100,000.'],
  ['Only euro countries', 'I want a rental flat in Porto or Bari, priced in euro, under €150,000, that pays for itself.'],
];
function home() {
  const text = 'I want to buy a place abroad that I can rent out for as much as possible, where prices will probably go up. I’m Dutch, so it has to be easy for me to buy there.';
  const agent = (name, blurb, kind, color, acc) => h`<a class="agent" href="#market">${critter(44, kind, color, acc)}<span>${name}<small>${blurb}</small></span></a>`;
  return h`<div class="shell">${nav('home')}<main class="home"><div class="home-in">
    ${critter(84)}
    <h1>What should Inky do for you?</h1>
    <p class="lead">Say it in your own words. Inky asks a few questions, learns the job once, then does it on its own.</p>
    <form class="prompt" data-act="start">
      <label class="sr" for="home-prompt">Describe the task</label>
      <textarea id="home-prompt" name="prompt" rows="3">${iv.prompt || text}</textarea>
      <div class="cbar"><span class="hint">click the mic to talk</span><div class="row">
        <button type="button" class="ibtn" data-act="mic" aria-label="Talk">${icon(P.mic, 18)}</button>
        <button type="submit" class="btn dark big">Start</button></div></div>
    </form>
    <div class="row" style="justify-content:center">
      ${SUGGEST.map(([t, full]) => h`<button type="button" class="suggest" data-act="fill" data-text="${full}">${t}</button>`)}
    </div>
    <div style="width:100%;margin-top:36px;display:flex;flex-direction:column;gap:12px">
      <div class="between"><h2 style="margin:0;font-size:16px;font-weight:600">Or start from someone else’s agent <span class="tag preview">Preview</span></h2><a href="#market" class="muted" style="font-size:14px">Marketplace</a></div>
      <div class="agents stagger">${agent('Yield Hunter', 'Homes abroad that rent well', 'octopus', '#E9A23B', 'glasses')}${agent('Price Watch', 'Competitor prices, hourly', 'blob', '#2BA59B', 'headphones')}${agent('Invoice Chaser', 'Friendly payment reminders', 'cat', '#7C6CF2')}</div>
    </div>
  </div></main></div>`;
}

let lastPct = 0;
function progress(p) {  // grows from the last value it showed
  const from = p ? Math.min(1, lastPct / p) : 0; lastPct = p;
  return h`<div class="grow" style="width:${p}%;--from:${from}"></div>`;
}
function task() {
  const cur = current();
  // every round's understood list, merged by label: a later round updates an item, never drops it
  const understood = Object.values(Object.fromEntries(iv.rounds.flatMap((r) => r.understood || []).map((u) => [String(u.k).toLowerCase(), u])));
  const asking = cur ? cur.questions : [];
  const total = understood.length + asking.length;
  const done = iv.rounds.filter((r) => r.answers);
  const thread = !iv.prompt
    ? inky(h`<p>Tell me what you want me to do, in your own words.</p><div class="row"><a class="btn dark" href="#home">New task</a></div>`)
    : h`${me(iv.prompt)}
      ${inky(h`<p>Good goal. I’ll ask in a few short rounds so I really understand it. Skip anything and I’ll pick a sensible default.</p>
        ${iv.rounds.length ? h`<div class="chips">${iv.rounds.map((r) => h`<span class="${r.answers ? '' : 'now'}">${r.answers ? '✓ Round ' + r.round : r.round + ' · now'}</span>`)}</div>` : ''}`)}
      ${done.length ? h`<div class="done-rounds">${done.map((r) => h`<details><summary><b>✓ Round ${r.round}</b> <span class="muted">· ${r.answers.map((a) => a.a).join(' · ')}</span></summary><dl>${r.answers.map((a) => h`<dt>${a.q}</dt><dd>${a.a}</dd>`)}</dl></details>`)}</div>` : ''}
      ${cur ? h`<form class="round fresh" data-act="round"><span class="label">ROUND ${cur.round}</span>
        ${cur.questions.map((q, i) => h`<div class="q fresh" style="animation-delay:${120 + i * 110}ms"><b>${q.text}</b>${q.why ? h`<span class="why">${q.why}</span>` : ''}<div class="ans"><input name="a${i}" autocomplete="off" placeholder="Your answer" aria-label="${q.text}"><button type="button" class="decide" data-act="decide">You decide</button></div></div>`)}
        <div class="row"><button type="submit" class="btn dark" ${raw(iv.busy ? 'disabled' : '')}>Next</button><button type="button" class="linkbtn" data-act="skip">Skip the rest, use defaults</button></div>
        ${skipPicks() ? h`<span class="note">Skip picks: ${skipPicks()}</span>` : ''}</form>` : ''}
      ${iv.busy ? inky(typing()) : ''}
      ${iv.error ? inky(h`<p class="hot">That did not work: ${iv.error}</p><div class="row"><button type="button" class="btn" data-act="retry">Try again</button></div>`) : ''}`;
  const rows = h`${understood.map((u) => h`<div class="kv"><span>${u.k}</span><span>${u.v}</span><span class="tag">✓</span></div>`)}
    ${asking.map((q) => h`<div class="kv wide"><span class="hot">${q.text}</span><span class="tag ask">asking</span></div>`)}`;
  const panel = h`<div class="card big">
      <div class="between"><h2 class="h2">What I understood so far</h2>${total ? h`<span class="muted" style="font-size:14px"><b style="color:var(--ink)">${understood.length} of ${total}</b> clear</span>` : ''}</div>
      <div class="bar">${progress(total ? Math.round((100 * understood.length) / total) : 0)}</div>
      ${total ? h`<div>${rows}</div>` : h`<p class="note" style="margin:0">Nothing yet. What I understand shows up here after the first round.</p>`}
    </div>
    <div class="row" style="align-items:stretch;gap:14px;flex-wrap:nowrap">
      <div class="card" style="flex:1;display:flex;flex-direction:column;gap:4px;border-radius:14px;padding:14px 16px"><span style="font-size:14px;font-weight:600">Why so many questions?</span><span class="note" style="font-size:13.5px">Each answer changes which homes count as a good deal. I only ask what changes the result.</span></div>
      <div style="display:flex;flex-direction:column;gap:8px;justify-content:center;align-items:flex-end">
        <button type="button" class="btn big" disabled>Start research${asking.length ? ` · ${asking.length} left` : ''}</button>
        ${cur ? h`<button type="button" class="linkbtn" data-act="skip">Skip the rest, use defaults</button>` : ''}
      </div></div>`;
  const status = REPLAY ? pill(`Replay${cur ? ' · round ' + cur.round : ''} · saved interview`, 'coral', true) : pill(cur ? `Planning · round ${cur.round}` : iv.busy ? 'Planning' : 'New task');
  return page('task', { status, thread, panel, label: 'What Inky understood', placeholder: 'Or answer in your own words…' });
}
// What "Skip" fills in: the server fills every gap from the example plan (plan.json), so show that plan's values.
const skipPicks = () => { const p = S.state.plan; return p && typeof p === 'object' ? ['budget_eur', 'cash', 'cities', 'home', 'managed_by'].filter((k) => p[k] != null && p[k] !== '').map((k) => planValue(k, p[k])).join(' · ') : ''; };

// ?replay=1: play the last saved interview again at a readable pace, for a clean take. Nothing is sent to the API.
let replayed = false;  // plays once per page load
async function replayInterview() {
  const R = [store.get('inky.iv'), keep.get('inky.iv.last')].find((x) => x && x.prompt && Array.isArray(x.rounds) && x.rounds.length);
  if (replayed || !R) return;
  replayed = true;
  const t = (ms) => sleep((ms * SLOW) / REPLAY), here = () => route() === 'task';
  const type = async (el, text) => { for (let i = 1; i <= text.length && el.isConnected; i++) { el.value = text.slice(0, i); await t(32); } };
  iv = { ...freshIv(R.prompt), messages: [{ role: 'user', content: R.prompt }], busy: true };
  render(); await t(1400);
  for (const r of R.rounds) {
    if (!here()) break;
    iv.busy = false; iv.rounds.push({ ...r, answers: null }); render(); await t(2200);
    const ans = r.answers || [], qs = r.questions || [];
    if (ans.length === qs.length && ans.every((a, i) => a.q === qs[i].text)) {
      for (const [i, a] of ans.entries()) { const el = $(`form.round input[name=a${i}]`); if (el) await (a.a === 'You decide' ? (el.value = a.a, t(500)) : type(el, a.a)); await t(350); }
    } else if (ans[0] && ans[0].q === 'In my own words' && $('#msg')) await type($('#msg'), ans[0].a);
    await t(700);
    iv.rounds[iv.rounds.length - 1].answers = ans; iv.busy = true; render(); await t(1500);
  }
  iv = { ...R, busy: false };
  if (here() && R.done) location.hash = '#confirm'; else render();
}

const LABEL = { question: 'Question', budget_eur: 'Budget', cash: 'Paying', keep_years: 'Keep it', where: 'Where', cities: 'Cities', home: 'Home', tenants: 'Tenants', managed_by: 'Managed by', worst_case: 'Worst case', never: 'Never', currency: 'Currency' };
const label = (k) => LABEL[k] || (k[0].toUpperCase() + k.slice(1)).replace(/_/g, ' ');
function planValue(k, v) {
  if (k === 'budget_eur') return 'Up to ' + eur(v);
  if (k === 'cash') return v ? 'Cash' : 'With a mortgage';
  if (k === 'keep_years') return `${v}+ years`;
  if (k === 'cities') return [].concat(v).map(city).join(', ');
  if (Array.isArray(v)) return v.join(', ');
  if (v && typeof v === 'object') return Object.entries(v).map(([a, b]) => `${a}: ${b}`).join(' · ');
  return String(v ?? '');
}
function confirm() {
  const d = iv.done || {}, plan = d.plan || S.state.plan;
  const answers = iv.rounds.reduce((n, r) => n + (r.answers ? r.answers.length : 0), 0);
  const fmt = Array.isArray(d.results_format) ? d.results_format : [];
  const never = (plan && [].concat(plan.never || []).join(', ')) || 'make an offer, pay, sign, log in as you';
  const thread = !plan ? inky(h`<p>No plan yet. Tell me what you want first.</p><div class="row"><a class="btn dark" href="#home">New task</a></div>`)
    : h`${iv.rounds.length ? h`<a class="stamp" href="#task">↑ ${iv.rounds.length} ${iv.rounds.length === 1 ? 'round' : 'rounds'} · ${answers} ${answers === 1 ? 'answer' : 'answers'}</a>` : ''}
      ${inky(h`<p>That’s everything. Here’s what I understood${d.summary ? ', in one sentence' : ''}:</p>
        <div class="quote">${d.summary || plan.question || ''}</div>
        ${fmt.length ? h`<p>And here’s how I’ll show you what I find:</p><ul>${fmt.map((x) => h`<li>${x}</li>`)}</ul>` : ''}
        <p style="font-weight:600">Did I get it right?</p>
        <div class="row"><button type="button" class="btn dark big" data-act="research" ${raw(jobOn() ? 'disabled' : '')}>${jobOn('research') ? 'Researching…' : 'Yes, start research'}</button><a class="btn big" href="#task">Change something</a></div>`)}
      ${jobView('research')}`;
  const rows = plan ? Object.entries(plan).filter(([k]) => k !== 'never' && k !== 'question') : [];
  const panel = !plan ? empty('No plan yet', 'Start a new task and answer a few questions.') : h`<div class="row" style="align-items:stretch;gap:16px;flex-wrap:nowrap;flex:1">
    <div class="card big" style="flex:1;min-width:0">
      <div class="between"><h2 class="h2">Your plan</h2><span class="muted" style="font-size:14px"><b style="color:var(--ink)">${rows.length} of ${rows.length}</b> clear</span></div>
      <div class="bar"><div class="grow" style="width:100%"></div></div>
      <div class="stagger">${rows.map(([k, v]) => h`<div class="kv" style="grid-template-columns:110px 1fr"><span>${label(k)}</span><span>${planValue(k, v)}</span></div>`)}</div>
      <div style="margin-top:auto;padding-top:12px;border-top:1px solid var(--line);display:flex;flex-direction:column;gap:6px">
        <span class="h3">What I may do</span>
        <div class="may"><b>On my own</b><span>Read listings, run every 15 min, fix one broken step</span></div>
        <div class="may ask"><b>Ask you first</b><span>Save a Gmail draft to an agent</span></div>
        <div class="may"><b>Never</b><span>${never[0].toUpperCase() + never.slice(1)}</span></div>
      </div>
    </div>
    <div style="width:300px;flex-shrink:0;display:flex;flex-direction:column;gap:10px">
      <span class="h3">How your results will look</span>
      <div class="card" style="padding:0;overflow:hidden;border-radius:18px">
        <div class="between" style="padding:10px 14px;background:var(--chip);font-size:12.5px;color:var(--grey)"><span>Telegram</span><span>one message per match</span></div>
        <div style="height:100px;background:var(--well);display:flex;align-items:center;justify-content:center"><svg width="64" height="50" viewBox="0 0 90 70" fill="none" stroke="#C9C5BD" stroke-width="2.5" stroke-linejoin="round" aria-hidden="true"><path d="M8 34 L45 8 L82 34"/><path d="M16 28 V64 H74 V28"/><path d="M38 64 V44 H52 V64"/></svg></div>
        <div style="padding:12px 14px;display:flex;flex-direction:column;gap:8px">
          <div class="between"><span style="font-size:15px;font-weight:600">[home], [city]</span><span style="font-size:14px;font-weight:600">€[price]</span></div>
          ${['Yield after costs', 'Price trend', 'Size and rooms', 'Neighbourhood', 'Link to the listing'].map((f) => h`<div class="between" style="font-size:13.5px;padding-top:6px;border-top:1px solid var(--row)"><span class="muted">${f}</span><span>[…]</span></div>`)}
          <div class="row" style="flex-wrap:nowrap;margin-top:4px"><span class="btn dark" style="flex:1;justify-content:center;font-weight:400">Save as draft</span><span class="btn">Skip</span></div>
        </div>
      </div>
      <span class="note">This is the format. Real homes fill it in after the research.</span>
    </div></div>`;
  const status = jobOn('research') ? pill('Researching', 'coral', true) : pill(plan ? `Plan ready · ${REPLAY ? 'replay' : 'check it'}` : 'No plan yet', REPLAY && 'coral', REPLAY);
  return page('confirm', { status, thread, panel, label: 'Your plan', placeholder: 'e.g. “actually, 2 bedrooms only”' });
}

function researchView() {
  const r = research(), vs = versions();
  if (S.v == null || !vs[S.v]) S.v = vs.length ? vs.length - 1 : null;  // the newest version, once the data is there
  const v = vs[S.v], lastV = vs[vs.length - 1];
  const thread = h`<a class="stamp" href="#confirm">↑ Your plan</a>${me('Start the research.')}${inky(!r
    ? h`<p>The research runs after the first build: I read the listings with Apify, match rents to prices and test the rules on real homes.</p>`
    : h`<p>Done. Here’s what I read.</p>${logLines([
      ['Read listings with Apify', `${num(r.listings_read)} homes: ${num(r.for_sale)} for sale, ${num(r.for_rent)} for rent`],
      ['Matched rents to prices, street by street', `${plural(r.neighbourhoods, 'neighbourhood')} scored, ${plural(r.with_rent_data, 'home')} with rent data`],
      lastV && [`Tested ${plural(vs.length, 'version')} of the rules`, `version ${lastV.v} keeps ${plural(lastV.zones, 'neighbourhood')}, ${plural(lastV.matches, 'home')}`],
      has(r.llm_calls) && ['Asked GLM-5.3 to propose rules', `${num(r.llm_calls)} AI calls · $${Number(r.llm_cost_usd || 0).toFixed(2)}`],
    ])}
    ${lastV ? h`<p>Click the versions on the right to see how the rules got sharper. Shall I watch ${lastV.zones === 1 ? 'this neighbourhood' : `these ${plural(lastV.zones, 'neighbourhood')}`} every 15 minutes?</p>` : ''}
    <div class="row"><button type="button" class="btn dark" data-act="build" ${raw(jobOn() ? 'disabled' : '')}>${jobOn('build') ? 'Building…' : 'Yes, watch them'}</button><button type="button" class="btn" data-act="focus">Change a rule</button></div>
    <p class="note">Research, not financial advice. Check with a local notary before you buy.</p>`, 'glasses')}${jobView('build')}`;
  if (!r) return page('research', { status: pill('No research yet'), acc: 'glasses', thread, panel: empty(), placeholder: 'Ask why a rule is there…' });
  const max = Math.max(1, ...vs.map((x) => x.matches || 0));
  const vr = v ? versionRules(vs, S.v) : [];
  const mark = { '✓': 'var(--ink)', '+': 'var(--coral-ink)', '~': 'var(--coral-ink)', '−': 'var(--grey)' };
  const changed = vr.filter((x) => x.m !== '✓');
  const prev = S.v > 0 ? vs[S.v - 1] : null;
  const steps = [[r.listings_read, 'listings read'], [r.for_sale, 'for sale'], [r.with_rent_data, 'with rent data'], [r.neighbourhoods, 'neighbourhoods scored']].filter(([n]) => has(n));
  const zones = r.top_zones || [];
  const panel = h`
    <div class="between"><h2 class="h2">How Inky found the rules</h2><span class="mono small">${has(r.llm_calls) ? num(r.llm_calls) + ' AI calls' : ''}${r.at ? ' · ' + day(r.at) + ' ' + clock(r.at) : ''}</span></div>
    <div class="card steps">${steps.map(([n, label]) => h`<div class="row" style="gap:14px;flex-wrap:nowrap"><div style="display:flex;flex-direction:column;gap:2px"><span class="n">${count(n)}</span><span class="small">${label}</span></div><span class="arrow" aria-hidden="true">→</span></div>`)}
      ${v ? h`<div style="display:flex;flex-direction:column;gap:2px"><span class="n hot">${count(v.zones, 'zones')}</span><span class="small">${v.zones === 1 ? 'neighbourhood passes' : 'neighbourhoods pass'} v${v.v}</span></div>` : ''}</div>
    ${vs.length ? h`<div class="row" style="align-items:stretch;gap:14px;flex-wrap:nowrap">
      <div class="card" style="flex:1;min-width:0;display:flex;flex-direction:column;gap:6px">
        <div class="between"><span class="h3">Homes that pass each version</span><span class="mono small">tested on ${num(r.for_sale)} homes for sale</span></div>
        <div style="margin-top:8px">${vs.map((x, i) => h`<div class="vbar ${i === S.v ? 'on' : ''}"><span class="mono">v${x.v}</span><div class="track"><div class="grow" style="width:${Math.max(2, Math.round((100 * (x.matches || 0)) / max))}%;--delay:${200 + i * 160}ms"></div></div><span class="mono" style="font-size:12.5px">${plural(x.matches, 'home')} · ${plural(x.zones, 'area')}</span></div>`)}</div>
        <p style="margin:0;padding-top:12px;font-size:13.5px;line-height:1.5;border-top:1px solid var(--row)">${!prev ? `v${v.v} is your plan turned into ${plural(vr.length, 'rule')}: ${plural(v.matches, 'home')} in ${plural(v.zones, 'neighbourhood')} ${v.matches === 1 ? 'passes' : 'pass'}.`
          : changed.length ? `v${v.v} changed ${changed.map((x) => x.id).join(', ')}. ${num(prev.matches)} → ${plural(v.matches, 'home')}, ${num(prev.zones)} → ${plural(v.zones, 'neighbourhood')}.` : `v${v.v} kept the rules of v${prev.v}.`}</p>
      </div>
      <div class="card" style="width:318px;flex-shrink:0;display:flex;flex-direction:column;gap:12px">
        <div class="vpick" role="group" aria-label="Rule version">${vs.map((x, i) => h`<button type="button" data-act="version" data-v="${i}" aria-pressed="${String(i === S.v)}">v${x.v}</button>`)}</div>
        <div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:15px;font-weight:600">${S.v === 0 ? 'From your plan' : `After testing v${prev.v}`}</span><span class="mono small">v${v.v} · ${plural(vr.length, 'rule')}</span></div>
        <div class="play" style="display:flex;flex-direction:column;gap:10px">${vr.map((x) => h`<div class="rule"><span class="m" style="color:${mark[x.m]}">${x.m}</span><span class="t"><span>${x.id ? x.id + ' · ' : ''}${x.t}</span>${x.why ? h`<small>${x.why}</small>` : ''}</span></div>`)}</div>
        <div class="between" style="margin-top:auto;padding-top:12px;border-top:1px solid var(--line)"><span class="muted" style="font-size:13.5px">Neighbourhoods that pass</span><span style="font-size:26px;font-weight:600;letter-spacing:-0.02em" class="${S.v === vs.length - 1 ? 'hot' : ''}">${num(v.zones)}</span></div>
      </div></div>` : empty('No rule versions yet')}
    ${zones.length ? h`<div class="card" style="padding:0"><table class="tbl">
      <thead><tr><th>${zones.length === 1 ? 'Top neighbourhood' : `Top ${zones.length} neighbourhoods`}</th><th>Yield after costs</th><th>Price trend</th><th>Rentals nearby</th><th>Matches</th><th style="text-align:right"><a class="muted" href="#results">${has(matchTotal()) ? `All ${plural(matchTotal(), 'home')}` : 'All homes'} →</a></th></tr></thead>
      <tbody>${zones.map((z) => h`<tr><td><b>${city(z.city)} · ${z.zone}</b></td><td class="num">${pct(z.net_yield)}</td><td class="num">${trend(z.price_trend)}</td><td>${num(z.rent_listings)}</td><td>${num(z.matches)}</td><td style="text-align:right" class="${money(z.city) === 'złoty' ? 'hot' : 'muted'}">${money(z.city)}</td></tr>`)}</tbody>
    </table></div>` : ''}
    ${bestPerCity(r)}
    <span class="note">${honest(r)}</span>`;
  return page('research', { status: jobOn('build') ? pill('Building in n8n', 'coral', true) : pill('Research done', 'coral', true), acc: 'glasses', thread, panel, placeholder: 'Ask why a rule is there…' });
}
const trend = (t) => (has(t) ? (t >= 0 ? '+' : '') + t + '%/yr' : '–');
const COUNTRY = { porto: 'PT', bari: 'IT', lodz: 'PL' }, NATION = { PT: 'Portugal', IT: 'Italy', PL: 'Poland' };
const costsOf = (m) => { const c = research() && research().costs; return (c && c[m.country || COUNTRY[m.city]]) || null; };
const honest = (r) => `Yields are estimates from asking prices and asking rents. Price trend is per country (Eurostat${r && r.price_trend_period ? ' ' + r.price_trend_period : ''}), not per street. Łódź districts are approximate.`;
// Best per city, even where nothing passes: "Porto: prices +17.8% a year, but the best yield after costs is only 3.1%".
function bestPerCity(r) {
  const b = r.best_by_city || {}, bc = r.by_city || {};
  const cities = [...new Set([...Object.keys(b), ...Object.keys(bc)])];
  if (!cities.length) return '';
  return h`<div class="card" style="display:flex;flex-direction:column;gap:12px"><div class="between"><span class="h3">Best per city</span><span class="mono small">estimates</span></div>
    <div class="cities">${cities.map((c) => {
      const x = b[c] || {}, y = bc[c] || {}, z = y.best_zone || {}, cc = costsOf({ city: c });
      const yv = pick(x, 'net_yield') ?? z.net_yield, zone = x.zone || z.zone, t = cc && has(cc.price_trend) ? cc.price_trend : z.price_trend;
      const n = pick(x, 'matches') ?? y.matches, fails = [].concat(x.failed || []);
      const passText = has(n) ? (Number(n) ? `${plural(n, 'home')} ${Number(n) === 1 ? 'passes' : 'pass'} the rules.` : 'No home passes the rules.') : '';
      // nothing passes: say it plainly (E3); the server's longer reason stays in the tooltip
      const why = has(n) && !Number(n) && has(yv) ? `${has(t) ? `Prices ${t >= 0 ? '+' : ''}${t}% a year, but t` : 'T'}he best yield after costs is only ${pct(yv)}. No home passes.`
        : x.reason || [fails.length && `This one misses ${fails.join(', ')}.`, passText].filter(Boolean).join(' ');
      return h`<div class="city ${has(n) && !Number(n) ? 'none' : ''}" title="${x.reason || ''}"><div class="between"><b>${city(c)}</b><span class="mono small">${has(t) ? `prices ${trend(t)}` : ''}</span></div>
        <span class="city-n">${has(yv) ? pct(yv) : '–'}</span><span class="small">best yield after costs${zone ? ' · ' + zone : ''}</span>${why ? h`<span class="note">${why}</span>` : ''}</div>`;
    })}</div></div>`;
}

// Program: teach/learn.py writes {site, start_url, learned_at, llm_calls, llm_cost_usd, shortcut, steps: [{n, do, label, target: {css}}], item: {selector, fields: {name: {css, attr, type}}}}
const programSteps = (p) => (Array.isArray(p && p.steps) ? p.steps.filter((s) => s && typeof s === 'object') : []);
const stepName = (s) => String(pick(s, 'do', 'op', 'action', 'type') ?? 'step');
const stepDetail = (s) => String(pick(s, 'label') ?? pick(s.target || {}, 'css', 'name') ?? pick(s, 'selector', 'url', 'value') ?? '');
const programFields = (p) => Object.entries((p && p.item && p.item.fields) || {}).map(([k, f]) => ({ name: k, sel: f && typeof f === 'object' ? [f.css, f.attr && '@' + f.attr].filter(Boolean).join(' ') : String(f) }));
// Race: race/race.py writes {at, seconds, compiled: {windows, listings, per_second, model_calls, pages, per_window: [n], seconds_used}, llm: {listings, per_second, model_calls, cost_usd, seconds_used}}
function raceData() {
  const r = S.state.race;
  if (!r || typeof r !== 'object') return null;
  const c = r.compiled || {}, a = r.llm || null;
  const per = Array.isArray(c.per_window) ? c.per_window : [];
  return { at: r.at, secs: r.seconds, used: c.seconds_used, nWin: has(c.windows) ? Number(c.windows) : per.length, per, listings: c.listings,
    perSec: c.per_second, pages: c.pages, calls: c.model_calls, agent: a && { listings: a.listings, perSec: a.per_second, calls: a.model_calls, cost: a.cost_usd, used: a.seconds_used } };
}
function screenToggle(on) {
  return h`<div class="seg white"><a href="#screen" ${raw(on === 'slow' ? 'aria-current="page"' : '')}>Slow</a><a href="#fast" ${raw(on === 'turbo' ? 'aria-current="page"' : '')}>Turbo</a></div>`;
}
function screen() {
  const p = S.state.program && typeof S.state.program === 'object' ? S.state.program : null;
  const steps = programSteps(p), fields = programFields(p), race = raceData();
  const site = (p && p.site) || '', url = (p && p.start_url) || '', sc = p && p.shortcut;
  const thread = h`<a class="stamp" href="#research">↑ Research and rules</a>${me('Yes, watch them.')}${inky(!p
    ? h`<p>This screen shows the program I learned for a site with no Apify actor. It fills in once I’ve learned one.</p>`
    : h`<p>Here’s the program I learned for ${site || 'this site'}. It runs with no AI: the same steps every time.</p>
      ${logLines([...steps.slice(0, 7).map((s) => [stepName(s), short(stepDetail(s))]), fields.length && [`Reads ${num(fields.length)} fields from every listing`, fields.map((f) => f.name).join(', ')], sc && ['Found a shortcut', `${sc.method || 'GET'} ${short(sc.url || '', 36)}`]])}
      ${steps.length > 7 ? h`<p class="note">and ${steps.length - 7} more steps on the right.</p>` : ''}`)}`;
  const panel = !p ? h`<div class="between" style="align-items:center"><span class="h3">Inky is driving</span>${screenToggle('slow')}</div>${empty()}` : h`
    <div class="between" style="align-items:center"><span class="h3" style="display:flex;align-items:center;gap:8px"><span class="dot coral" style="width:8px;height:8px"></span>The program <span class="muted" style="font-weight:400">· ${site}</span></span>${screenToggle('slow')}</div>
    <div class="row" style="align-items:stretch;gap:14px;flex-wrap:nowrap;flex:1;min-height:420px">
      <div class="frame"><div class="frame-in"><div class="win">
        <div class="urlbar"><div class="lights" aria-hidden="true"><span></span><span></span><span></span></div><div class="url">${url || site}</div></div>
        <div style="flex:1;min-height:0;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:14px">
          ${fields.length ? h`<span class="h3">What the program reads from each listing</span><div class="fields run">${fields.map((f, i) => h`<div class="field" style="--i:${i}" title="${f.sel}"><span>${f.name}</span><span>${f.sel || ' '}</span></div>`)}</div>` : ''}
          ${steps.length ? h`<span class="h3">Steps</span><ol class="steplist run">${steps.map((s, i) => h`<li style="--i:${i}"><span>${stepName(s)}</span><span class="d" title="${stepDetail(s)}">${stepDetail(s)}</span></li>`)}</ol>` : ''}
          ${sc ? h`<div class="note" style="padding:10px 12px;border-radius:10px;background:var(--panel)"><b style="color:var(--ink)">Shortcut:</b> the site has a JSON API, so the clicks became one request. <span class="mono" style="font-size:11.5px;overflow-wrap:anywhere">${sc.method || 'GET'} ${short(sc.url || '', 80)}</span></div>` : ''}
        </div></div></div></div>
      <div class="card" style="width:262px;flex-shrink:0;display:flex;flex-direction:column;gap:12px">
        <div style="display:flex;flex-direction:column;gap:2px"><span class="h3">The program</span>${has(p.llm_calls) ? h`<span class="mono small">learned in ${num(p.llm_calls)} AI ${p.llm_calls === 1 ? 'call' : 'calls'}${has(p.llm_cost_usd) ? ` · $${Number(p.llm_cost_usd).toFixed(3)}` : ''}</span>` : ''}</div>
        <div style="display:flex;flex-direction:column;gap:7px;font-size:13.5px">
          ${[['Site', site], ['City', p.city ? city(p.city) : ''], ['Steps', steps.length ? num(steps.length) : ''], ['Fields', fields.length ? num(fields.length) : ''], ['Learned', p.learned_at ? `${day(p.learned_at)} ${clock(p.learned_at)}` : '']].filter(([, x]) => x).map(([k, x]) => h`<div style="display:grid;grid-template-columns:62px 1fr;gap:8px"><span class="muted">${k}</span><span class="mono" style="font-size:13px;overflow-wrap:anywhere">${x}</span></div>`)}
        </div>
        ${finalRules().length ? h`<div style="height:1px;background:var(--line)"></div><span style="font-size:13px;font-weight:600">Then every home is scored on</span><div class="row" style="gap:5px">${finalRules().map((r) => h`<span class="chip" title="${ruleText(r)}">✓ ${r.id}</span>`)}</div>` : ''}
        <span style="margin-top:auto;font-size:13.5px;font-weight:600" class="hot">A match? Inky drafts a message, you send it.</span>
      </div>
    </div>
    ${race && race.nWin ? h`<div class="between"><a href="#fast" style="font-size:13.5px;font-weight:600">All ${num(race.nWin)} windows in Turbo</a><span class="mono small">${[has(race.listings) && num(race.listings) + ' listings', has(race.used) && num(race.used) + ' s', has(race.calls) && num(race.calls) + ' AI calls'].filter(Boolean).join(' · ')}</span></div>` : ''}`;
  return page('screen', { status: livePill(), thread, panel, placeholder: 'Say “slower”, “stop”, or change a rule…' });
}

// The race replays at the real pace, squeezed: 60 real seconds take 3.6 s on screen.
const pace = (used, secs) => (has(used) ? Math.max(0.6, Math.min(4, (3.6 * used) / (has(secs) ? secs : 60))) : 1.2);
function fast() {
  const r = raceData(), a = r && r.agent;
  const calls = (n) => (has(n) ? ` · ${num(n)} AI ${Number(n) === 1 ? 'call' : 'calls'}` : '');
  // "all 96 Bari flats under €200k in 19.7 s": "all" only when a window ran out of pages, so the program really reached the end
  const prog = S.state.program || {}, maxPrice = programSteps(prog).map((x) => /price/i.test(x.label || '') && Number(x.value)).find((x) => x > 0);
  const per = r ? r.per.map(Number) : [], emptyW = per.filter((n) => !n).length, ranOut = per.length > 1 && Math.min(...per) < Math.max(...per);
  const what = r && has(r.listings) ? `${ranOut ? 'all ' : ''}${num(r.listings)} ${prog.city ? city(prog.city) + ' ' : ''}flats${maxPrice ? ` under €${maxPrice >= 1000 ? Math.round(maxPrice / 1000) + 'k' : num(maxPrice)}` : ''}` : '';
  const thread = h`<a class="stamp" href="#screen">↑ The program, slowly</a>${me('Show me all of them at full speed.')}${inky(!r
    ? h`<p>Turbo runs the same program in many windows at once, with no AI. The numbers show up after the first race.</p>`
    : h`<p>${what ? `Inky’s program read ${what}${has(r.used) ? ` in ${num(r.used)} s` : ''}, in ${plural(r.nWin, 'window')} at once. ` : `Here ${r.nWin === 1 ? 'is the window' : `are all ${num(r.nWin)} windows`}. `}It’s the same program in each one, with no AI.</p>
      ${emptyW ? h`<p class="note">${emptyW === 1 ? 'One window found nothing' : `${num(emptyW)} windows found nothing`}: the others had already read every page.</p>` : ''}
      ${logLines([has(r.listings) && [`Checked ${num(r.listings)} listings${has(r.pages) ? ` on ${num(r.pages)} pages` : ''}`, [has(r.perSec) && `${num(r.perSec)} per second`, has(r.calls) && `${num(r.calls)} AI calls`].filter(Boolean).join(' · ')],
        a && has(a.listings) && [`An AI clicking agent read ${num(a.listings)}${has(a.used) ? ` in ${num(a.used)} s` : ''}`, [has(a.calls) && `${num(a.calls)} AI calls`, has(a.cost) && `$${Number(a.cost).toFixed(2)}`].filter(Boolean).join(' · ')]])}
      ${a ? h`<p class="note">A clicking agent asks the AI before every click. Inky’s program doesn’t need to.</p>` : ''}`, 'headphones')}`;
  const stat = (k, v, hot) => (v ? h`<div class="stat"><span>${k}</span><span class="mono ${hot ? 'hot' : ''}" style="font-weight:400">${v}</span></div>` : '');
  const maxW = r ? Math.max(1, ...r.per.map(Number).filter((x) => !Number.isNaN(x))) : 1;
  const panel = !r ? h`<div class="between" style="align-items:center"><span class="h3">Turbo</span>${screenToggle('turbo')}</div>${empty()}` : h`
    <div class="between" style="align-items:center"><span class="h3">Turbo <span class="muted" style="font-weight:400">· ${num(r.nWin)} windows at once</span></span>${screenToggle('turbo')}</div>
    ${a && has(a.listings) && has(r.listings) ? h`<div class="card" style="display:flex;flex-direction:column;gap:12px">
      <div class="between"><span class="h3">Same task, ${has(r.secs) ? `same ${num(r.secs)} seconds` : 'same time'}</span><span class="mono small">listings read</span></div>
      <div class="race"><span style="font-weight:500">Inky</span><div class="track"><div style="width:100%;background:var(--coral);--dur:${pace(r.used, r.secs)}s"></div></div><span class="mono" style="font-size:13px;text-align:right">${count(r.listings)}${calls(r.calls)}</span>
        <span class="muted">Clicking agent</span><div class="track"><div style="width:${Math.max(1, Math.min(100, (100 * a.listings) / Math.max(1, r.listings)))}%;background:var(--faint);--dur:${pace(a.used, r.secs)}s"></div></div><span class="mono muted" style="font-size:13px;text-align:right">${count(a.listings)}${calls(a.calls)}</span></div>
    </div>` : ''}
    ${r.per.length ? h`<div class="arms">${r.per.map((n, i) => h`<div class="arm ${Number(n) ? '' : 'idle'}" style="--i:${i}"><div class="arm-h"><span>Window ${i + 1}</span><span class="mono muted" style="font-size:11px;font-weight:400">${Number(n) ? `✓ ${num(n)}` : 'empty'}</span></div>
      <div class="arm-b"><div class="bar"><div class="grow" style="width:${Math.round((100 * (Number(n) || 0)) / maxW)}%;background:var(--coral);--delay:${300 + i * 70}ms"></div></div><span class="muted" style="font-size:11.5px">${Number(n) ? `${num(n)} listings · no AI` : 'no pages left to read'}</span></div></div>`)}</div>` : ''}
    <div class="stats">${stat('Inky’s time', has(r.used) ? num(r.used) + ' s' : '')}${stat('Listings', has(r.listings) ? num(r.listings) : '')}${stat('Per second', has(r.perSec) ? num(r.perSec) : '')}${stat('AI calls', has(r.calls) ? num(r.calls) : '')}${stat('Agent’s AI cost', a && has(a.cost) ? '$' + Number(a.cost).toFixed(2) : '', true)}</div>
    ${r.at ? h`<span class="note">Raced ${day(r.at)} ${clock(r.at)}.</span>` : ''}`;
  return page('fast', { status: livePill(), acc: 'headphones', thread, panel, placeholder: 'Say “slow down”, or change a rule…' });
}

// "Why 6.8%?": the same sum inky.js does in n8n, written out. Needs the rent estimate and the country's costs from research.json.
function breakdown(m) {
  const c = costsOf(m), size = Number(m.size_m2), price = Number(m.price_eur);
  if (!c || !(size > 0) || !(price > 0)) return null;
  const perM2 = has(m.rent_m2) ? Number(m.rent_m2) : has(m.rent_month) ? m.rent_month / size : null;
  if (!has(perM2)) return null;
  const month = perM2 * size, year = month * 12, vac = year * c.vacancy, got = year - vac;
  const agency = got * c.management, tax = got * c.rent_tax, upkeep = price * c.upkeep, net = got - agency - tax - upkeep, paid = price * (1 + c.buy_costs);
  return { c, perM2, month, year, vac, agency, tax, upkeep, net, paid, pct: (100 * net) / paid, n: pick(m, 'n_rent', 'zone_rent_listings'), nation: NATION[m.country || COUNTRY[m.city]] || '' };
}
const share100 = (x) => `${+(x * 100).toFixed(1)}%`;
function whyRow(m, b) {
  const line = (k, v, cls = '') => h`<div class="${cls}"><span>${k}</span><span class="mono">${v}</span></div>`;
  const minus = (x) => '−' + eur(x);
  return h`<tr class="why-row"><td colspan="6"><div class="whybox">
    <div class="between"><span class="h3">Why ${pct(b.pct)}?</span><span class="tag">estimate</span></div>
    <p class="note" style="margin:0">Rent about <b style="color:var(--ink)">${eur(b.month)} a month</b>: ${has(b.n) ? `${plural(b.n, 'rental')} nearby ask` : 'rentals nearby ask'} about €${b.perM2.toFixed(2)} per m², times ${Math.round(Number(m.size_m2))} m².</p>
    <div class="sum">
      ${line('Rent for a year', eur(b.year))}
      ${line(`Empty months, ${share100(b.c.vacancy)}`, minus(b.vac))}
      ${line(`Agency, ${share100(b.c.management)} of the rent`, minus(b.agency))}
      ${line(`Rent tax${b.nation ? ' in ' + b.nation : ''}, ${share100(b.c.rent_tax)}`, minus(b.tax))}
      ${line(`Upkeep, ${share100(b.c.upkeep)} of the price a year`, minus(b.upkeep))}
      ${line('Left each year', eur(b.net), 'tot')}
      ${line(`Price ${eur(m.price_eur)} + buying costs ${share100(b.c.buy_costs)}`, eur(b.paid))}
      ${line('Yield after costs', pct(b.pct), 'tot hot')}
    </div>
    <span class="note">${has(b.c.price_trend) ? `The price trend, ${b.c.price_trend >= 0 ? '+' : ''}${b.c.price_trend}% a year, is for all of ${b.nation || 'the country'} (Eurostat${research().price_trend_period ? ' ' + research().price_trend_period : ''}), not this street. ` : ''}Rent and costs are estimates, not quotes.${m.city === 'lodz' ? ' Łódź districts are approximate.' : ''}</span>
  </div></td></tr>`;
}
const seenUrls = () => { if (!S.seenBase) { S.seenBase = keep.get('inky.seen') || []; } return S.seenBase; };
const chip = (act, v, on, text) => h`<button type="button" class="fchip" data-act="${act}" data-v="${v}" aria-pressed="${String(on)}">${text}</button>`;
function results() {
  const r = research(), saved = (r && r.matches) || [], passing = saved.filter(passes), last = [...S.log].reverse().find((x) => x.res);
  const total = matchTotal(), hidden = saved.length - passing.length;
  // what's new since you last looked: the homes whose link wasn't on screen the last time (per browser)
  const base = seenUrls(), urls = saved.map((m) => m.url).filter(Boolean);
  if (urls.some((u) => !base.includes(u))) keep.set('inky.seen', [...new Set([...base, ...urls])].slice(-2000));
  const isNew = (m) => base.length > 0 && m.url && !base.includes(m.url);
  const ms = passing.filter((m) => (!S.f.city || m.city === S.f.city) && (!S.f.min || (m.net_yield || 0) >= S.f.min)).sort((a, b) => (b.net_yield || 0) - (a.net_yield || 0));
  const cities = [...new Set(passing.map((m) => m.city).filter(Boolean))];
  const fresh = passing.filter(isNew).length;
  const headline = has(total) ? plural(total, 'home matches', 'homes match') : plural(passing.length, 'saved home passes', 'saved homes pass');
  const bigHeadline = has(total) ? h`${count(total, 'matches')} ${Number(total) === 1 ? 'home matches' : 'homes match'}` : headline;
  const best = passing.reduce((b, m) => (!b || (m.net_yield || 0) > (b.net_yield || 0) ? m : b), null);
  const top = r && r.top_zones && r.top_zones[0];
  const cur = finalRules().find((x) => x.field === 'currency');
  const idea = cur && cur.op === '==' && cur.value === 'EUR' ? 'Also allow homes priced in złoty' : 'Only places with the euro';
  const thread = h`${r && r.at ? h`<span class="stamp">${day(r.at)} ${clock(r.at)}</span>` : ''}${inky(!r
    ? h`<p>Your results show up here after the first build.</p>`
    : h`<p>I checked ${num(r.listings_read)} listings.</p>${logLines([
      [headline, best && `best: ${best.title || 'a flat'} in ${best.zone}, ${pct(best.net_yield)} after costs`],
      top && [r.top_zones.length === 1 ? 'Top neighbourhood' : `${num(r.top_zones.length)} top neighbourhoods`, `${r.top_zones.length === 1 ? '' : 'first: '}${top.zone}, ${city(top.city)}`],
    ])}<div class="row"><button type="button" class="btn dark" data-act="best" ${raw(S.busy ? 'disabled' : '')}>${TG}Send me the best 3 now</button><button type="button" class="btn" data-act="fill" data-text="${idea}">${idea}</button></div>`)}`;
  const panel = h`<div class="seg"><span aria-current="page">Homes</span><a href="#activity">Activity</a></div>
    ${!r ? empty() : h`
      <div class="between" style="align-items:center"><h2 class="h2">${bigHeadline}</h2>${finalRules().length ? h`<span class="mono small">rules ${finalRules()[0].id}–${finalRules()[finalRules().length - 1].id}</span>` : ''}</div>
      <span class="mono small" style="margin-top:-8px">from ${num(r.listings_read)} listings${r.at ? ' · research ' + day(r.at) + ' ' + clock(r.at) : ''}${ms.length && has(total) && ms.length < total ? ` · showing ${num(ms.length)}` : ''}</span>
      ${last ? h`<div class="card" style="border-color:var(--coral);background:var(--blush);padding:12px 16px;display:flex;justify-content:space-between;gap:12px;align-items:baseline"><span style="font-size:14px"><b class="hot">Last change</b> · ${last.res.change}</span>${has(last.res.matches_before) && has(last.res.matches_after) ? h`<span class="mono" style="font-size:13px;white-space:nowrap">${num(last.res.matches_before)} → ${plural(last.res.matches_after, 'home')}</span>` : ''}</div>` : ''}
      ${passing.length > 1 ? h`<div class="filters" role="group" aria-label="Filter homes">
        ${chip('fcity', '', S.f.city === '', `All ${num(passing.length)}`)}${cities.map((c) => chip('fcity', c, S.f.city === c, `${city(c)} · ${num(passing.filter((m) => m.city === c).length)}`))}
        <span class="fsep" aria-hidden="true"></span>${[0, 5, 6, 7].map((y) => chip('fmin', y, S.f.min === y, y ? `${y}%+` : 'Any yield'))}
        ${fresh ? h`<span class="newnote"><span class="newtag">new</span> ${plural(fresh, 'home')} since you last looked</span>` : ''}</div>` : ''}
      ${ms.length ? h`<div class="card" style="padding:0;overflow:hidden"><table class="tbl">
        <thead><tr><th>Home</th><th>Where</th><th>Price</th><th>Size</th><th>After costs</th><th></th></tr></thead>
        <tbody>${ms.map((m, i) => { const b = breakdown(m), key = m.url || m.title + m.price_eur, open = b && S.why.has(key);
          return h`<tr class="${i === 0 ? 'best' : ''}"><td><div class="clip" title="${m.title || ''}">${m.title || 'Flat'}</div><div class="sub">${i === 0 ? h`<span class="besttag">best now</span>` : ''}${isNew(m) ? h`<span class="newtag">new</span>` : ''}${has(m.bedrooms) ? plural(m.bedrooms, 'bedroom') : ''}</div></td>
          <td>${m.zone || ''}<div class="sub">${city(m.city)}</div></td><td class="num">${eur(m.price_eur)}</td><td class="num">${has(m.size_m2) ? Math.round(m.size_m2) + ' m²' : '–'}</td>
          <td class="num">${b ? h`<button type="button" class="whybtn" data-act="why" data-k="${key}" aria-expanded="${String(!!open)}" aria-label="Why ${pct(m.net_yield)}?">${pct(m.net_yield)}<small>why?</small></button>` : pct(m.net_yield)}</td>
          <td style="text-align:right">${safeUrl(m.url) ? h`<a href="${m.url}" target="_blank" rel="noopener" class="muted" aria-label="Open listing">↗</a>` : ''}</td></tr>${open ? whyRow(m, b) : ''}`; })}</tbody>
      </table></div>` : passing.length ? empty('No home fits these filters', 'Pick another city or a lower yield.') : saved.length ? empty('None of the saved homes pass the new rules', 'The next research run lists the homes that do.') : empty('No homes match these rules', 'Change a rule in the message box.')}
      ${hidden > 0 ? h`<span class="note">The rules changed after the research, so ${plural(hidden, 'saved home')} that no longer ${hidden === 1 ? 'passes is' : 'pass are'} hidden.</span>` : ''}
      <span class="note">Research, not financial advice. Check with a local notary before you buy.</span>`}`;
  return page('results', { status: livePill(), thread, panel, placeholder: 'Change a rule in your own words…' });
}

const SOURCES = [['idealista · Porto', 'igolaizola~idealista-scraper'], ['idealista · Bari', 'igolaizola~idealista-scraper'], ['immobiliare · Bari', 'memo23~immobiliare-scraper'], ['otodom · Łódź', 'trev0n~otodom-scraper'], ['tecnocasa · Bari', 'cavernous_stew~inky-tecnocasa-homes']];
const secsBetween = (a, b) => (a && b ? (new Date(b) - new Date(a)) / 1000 : null);
const secsText = (x) => (has(x) ? (x < 10 ? x.toFixed(1) : Math.round(x)) + ' s' : '');
// seconds from the start of an execution to the end of one of its steps (steps run one after another)
const upTo = (r, name) => { let t = 0; for (const [n, x] of Object.entries((r && r.nodes) || {})) { t += (x.ms || 0) / 1000; if (n === name) break; } return t; };
const bigIcon = (svg, n = 22) => raw(svg.__raw.replace(/width="1[56]" height="1[56]"/, `width="${n}" height="${n}"`));
// The repair's audit trail: the broken step's settings before and after the fix, only the changed keys highlighted.
const parsed = (x) => { if (typeof x === 'string') { try { return JSON.parse(x); } catch { /* plain text */ } } return x; };
function flat(o, p = '', out = {}) {
  if (o && typeof o === 'object' && !Array.isArray(o) && Object.keys(o).length) for (const [k, v] of Object.entries(o)) flat(v, p ? `${p}.${k}` : k, out);
  else out[p || 'value'] = typeof o === 'string' ? o : JSON.stringify(o);
  return out;
}
function diffView(before, after) {
  if (before == null && after == null) return '';
  const a = flat(parsed(before)), b = flat(parsed(after)), keys = [...new Set([...Object.keys(a), ...Object.keys(b)])];
  const changed = keys.filter((k) => a[k] !== b[k]), same = keys.filter((k) => a[k] === b[k]);
  if (!changed.length) return '';
  const val = (v) => (String(v).length > 70 ? String(v).slice(0, 69) + '…' : String(v)), ctx = same.slice(0, 3);
  return h`<div class="diff" aria-label="What the fix changed">
    ${ctx.map((k) => h`<div class="same"><i> </i>${k}: ${val(a[k])}</div>`)}
    ${changed.map((k) => h`${k in a ? h`<div class="del"><i>−</i>${k}: ${val(a[k])}</div>` : ''}${k in b ? h`<div class="add"><i>+</i>${k}: ${val(b[k])}</div>` : ''}`)}
    ${same.length > ctx.length ? h`<div class="same more">${plural(same.length - ctx.length, 'other setting')} unchanged</div>` : ''}</div>`;
}

// The workflow screen answers three questions in plain words: what happens every 15 minutes, what happens when
// something breaks, and how the recent runs went. Every number is from the real n8n executions (/api/run_detail).
function workflow() {
  const nn = n8n(), main = safeUrl(nn.main_url), repair = safeUrl(nn.repair_url);
  const runs = S.runs.filter((e) => e.workflow !== 'repair');
  const failed = runs.filter((e) => /error|crash|fail/.test(e.status || '')).length;
  const d = S.detail || {}, ok = d.ok, rep = d.repair;
  const node = (r, n) => (r && r.nodes && r.nodes[n]) || null;
  const items = (r, n) => (node(r, n) ? node(r, n).items : null);
  const read = ok ? SOURCES.reduce((a, [n]) => a + (items(ok, n) || 0), 0) : null;
  // sites, not steps: idealista feeds two cities
  const sites = new Set((ok ? SOURCES.filter(([n]) => node(ok, n)) : SOURCES).map(([n]) => n.split(' · ')[0])).size;
  const score = node(ok, 'Score · rules');
  const matched = score ? score.items : null;
  const asked = items(ok, 'Ask me on Telegram') ?? (matched === 0 ? 0 : null);
  const drafted = items(ok, 'Gmail draft to the agent') ?? (matched === 0 || asked === 0 ? 0 : null);
  const took = ok ? secsBetween(ok.startedAt, ok.stoppedAt) : null;
  const trig = runs.find((e) => e.mode === 'trigger');
  const rules = finalRules(), ruleIds = rules.length ? `${rules[0].id}–${rules[rules.length - 1].id}` : 'your rules';

  const thread = h`${me('How does this actually run?')}${inky(h`<p>Without me. I turned your plan into a workflow in your own n8n. Every 15 minutes it reads the newest listings with Apify, scores them on ${ruleIds} with no AI, and asks you on Telegram when a home fits.</p>
    ${main ? h`${logLines([
      ok && [`Last run: ${plural(read, 'listing')} read`, `${plural(matched, 'match', 'matches')}${has(took) ? `, took ${secsText(took)}` : ''}`],
      [`${plural(runs.length, 'run')} so far`, failed ? `${num(failed)} failed${rep ? ` · ${num((S.summary && S.summary.repairs) || 1)} fixed by the repair workflow` : ', check Activity'}` : 'none failed'],
      rep && ['Fixed one broken step on its own', rep.change],
    ])}
      <div class="row">${ext(main, 'Open in n8n', 'btn dark')}<a class="btn" href="#activity">All runs</a></div>` : h`<p class="note">It gets built after the research. Nothing is running yet.</p>`}`)}
    ${me('What if a site changes?')}${inky(h`<p>A second workflow watches for errors. It asks GLM-5.3 to rewrite only the broken step, saves it, and runs again. At most once an hour, and it tells you both times.</p>`)}`;

  if (!main) return page('workflow', { status: livePill(), thread, panel: empty(), placeholder: 'Ask what a step does, or change a rule…' });

  const stage = (i, ic, title, n, unit, sub, hot, extra) => h`<div class="stage ${hot ? 'hot' : ''}" style="--i:${i}">
    <div class="stage-ic">${ic}</div><span class="stage-t">${title}</span>
    <span class="stage-n">${has(n) ? h`<b>${count(n, 'st' + i, 300 + i * 380)}</b>` : h`<b>–</b>`}<span>${unit}</span></span>
    ${extra ? h`<span class="stage-x">${extra}</span>` : ''}<span class="stage-s">${sub}</span></div>`;
  // Totals for the last 24 h (/api/summary) next to the last run, so a quiet run doesn't read as a dead "0 · 0 · 0".
  const sm = S.summary, day24 = (n, one, many) => `${Number(n) === 1 ? one : many} in 24 h`;
  const lastMatch = sm && Array.isArray(sm.per_run) ? sm.per_run.filter((x) => Number(x.matches) > 0).sort((a, b) => new Date(b.startedAt) - new Date(a.startedAt))[0] : null;
  const lastRun = (n) => (has(n) ? `last run ${num(n)}` : '');
  const pipe = (i) => h`<div class="pipe" style="--i:${i}" aria-hidden="true"><i></i><i></i><i></i></div>`;
  const flow = h`<div class="flow">
    ${sm ? stage(0, bigIcon(APIFY), `Read ${num(sites)} sites`, sm.listings_checked, day24(sm.listings_checked, 'listing checked', 'listings checked'), 'idealista, immobiliare, otodom and Tecnocasa, through Apify', false,
        [lastRun(read), has(sm.new_listings) && `${num(sm.new_listings)} new`].filter(Boolean).join(' · '))
      : stage(0, bigIcon(APIFY), `Read ${num(sites)} sites`, read, 'new listings', 'idealista, immobiliare, otodom and Tecnocasa, through Apify')}${pipe(0)}
    ${sm ? stage(1, '{ }', 'Score them, no AI', sm.matches, day24(sm.matches, 'match', 'matches'), `rules ${ruleIds} · 0 AI calls`, false,
        [lastRun(matched), lastMatch && `last match ${day(lastMatch.startedAt)} ${clock(lastMatch.startedAt)}`].filter(Boolean).join(' · '))
      : stage(1, '{ }', 'Score them, no AI', matched, matched === 1 ? 'match' : 'matches', `rules ${ruleIds}${score && has(score.ms) ? ` · ${secsText(score.ms / 1000)}` : ''} · 0 AI calls`)}${pipe(1)}
    ${sm ? stage(2, bigIcon(TG), 'Ask you', sm.matches, day24(sm.matches, 'question', 'questions'), 'on Telegram, one per match, then it waits for your tap', !!Number(sm.matches), lastRun(asked))
      : stage(2, bigIcon(TG), 'Ask you', asked, asked === 1 ? 'question' : 'questions', 'on Telegram, then it waits for your tap', !!asked)}${pipe(2)}
    ${has(drafted) || !sm ? stage(3, icon(P.mail, 20, 1.8), 'Save a draft', drafted, drafted === 1 ? 'Gmail draft' : 'Gmail drafts', 'to the agent, never sent: you press send')
      : stage(3, icon(P.mail, 20, 1.8), 'Save a draft', S.runs.filter((e) => e.status === 'waiting').length, 'waiting for your tap', 'to the agent, never sent: you press send')}</div>`;

  const repairAt = rep && (rep.failed ? rep.failed.startedAt : rep.startedAt);
  const fixSecs = rep ? secsBetween(rep.startedAt, rep.stoppedAt) : null;
  const again = rep && rep.again;
  const incident = rep ? h`<div class="incident fixed">
      <div class="between" style="align-items:center"><span class="h3">${day(repairAt)}, ${clock(repairAt)} · a step broke</span><span class="badge">${icon(P.check, 13, 3)}fixed in ${secsText(fixSecs)}</span></div>
      <div class="tl">
        <div class="tl-s" style="--i:0"><span class="t">${clock(repairAt)}</span><span><b>${rep.step || 'A step'} failed</b>${rep.error || 'The step returned an error.'}</span></div>
        <div class="tl-s" style="--i:1"><span class="t">+${secsText(upTo(rep, 'GLM-5.3 fixes one step'))}</span><span><b>GLM-5.3 rewrote that one step</b>${rep.change ? h`<code>${rep.change}</code>` : ''}${diffView(rep.before, rep.after)}</span></div>
        <div class="tl-s" style="--i:2"><span class="t">+${secsText(fixSecs)}</span><span><b>Saved and published the fix</b>in your n8n, and told you on Telegram</span></div>
        ${again ? h`<div class="tl-s ok" style="--i:3"><span class="t">${clock(again.startedAt)}</span><span><b>Ran again${again.status === 'success' ? ' and worked' : ''}</b>${again.status === 'success' ? `every site read${has(secsBetween(again.startedAt, again.stoppedAt)) ? `, took ${secsText(secsBetween(again.startedAt, again.stoppedAt))}` : ''}` : again.status || 'running'}</span></div>` : ''}
      </div>
      <div class="between" style="align-items:center"><span class="note">It only touches the broken step, at most once an hour. Anything else, it asks you.</span>${ext(repair, 'Open repair', 'hot nowrap')}</div>
    </div>`
    : h`<div class="incident"><span class="h3">Nothing has broken yet</span><span class="note">If a site changes and a step fails, the repair workflow asks GLM-5.3 to rewrite only that step, publishes the fix and runs again. At most once an hour.</span>${ext(repair, 'Open the repair workflow', 'hot')}</div>`;

  const beats = [...S.runs].reverse().slice(-40);
  const beatCls = (e) => { const [tag] = runTag(e.status); return e.workflow === 'repair' ? 'fix' : tag === 'failed' ? 'bad' : tag === 'needs you' ? 'wait' : tag === 'ok' ? 'ok' : 'run'; };
  const heartbeat = beats.length ? h`<div class="beats" role="img" aria-label="${num(runs.length)} runs, ${num(failed)} failed">${beats.map((e, i) => h`<span class="beat ${beatCls(e)}" style="--i:${i}" title="${day(e.startedAt)} ${clock(e.startedAt)} · ${e.workflow === 'repair' ? 'repair' : (MODE[e.mode] || 'run').toLowerCase()} · ${runTag(e.status)[0]}"></span>`)}</div>
    <div class="legend"><span><i style="background:var(--green)"></i>worked</span><span><i style="background:var(--coral)"></i>failed</span><span><i style="background:var(--coral-ink)"></i>repair</span><span><i style="background:#E9A23B"></i>waiting for you</span></div>` : empty('No runs yet', 'Each run shows up here.');

  const panel = h`<div class="wf-hero">
      <div class="wf-hero-l">${critter(54)}<div><h2 class="h2" style="font-size:21px">Inky runs this on its own</h2><p>In your n8n, every 15 minutes. It built the workflow itself through the n8n API.</p></div></div>
      <div class="wf-hero-r">${trig ? h`<span class="next"><span class="dot green"></span>Next run in <b data-countdown="${trig.startedAt}">–</b></span>` : ''}<div class="row">${ext(main, 'Open in n8n', 'btn dark')}</div></div>
    </div>
    <div class="sec"><h3>Every 15 minutes</h3>${ok ? h`<span class="mono small">last full run ${day(ok.startedAt)} ${clock(ok.startedAt)}${has(took) ? ` · took ${secsText(took)}` : ''}</span>` : ''}</div>
    ${flow}
    ${sm ? h`<span class="mono small">Last 24 h: ${[plural(sm.runs, 'run'), has(sm.failed) && `${num(sm.failed)} failed`, has(sm.repairs) && plural(sm.repairs, 'repair'), usdRun(sm), has(sm.ai_calls) && plural(sm.ai_calls, 'AI call')].filter(Boolean).join(' · ')}</span>` : ''}
    <div class="sec"><h3>When something breaks</h3></div>
    ${incident}
    <div class="sec"><h3>Recent runs</h3><a class="mono small" href="#activity">${plural(runs.length, 'run')} · ${num(failed)} failed →</a></div>
    ${heartbeat}`;
  return page('workflow', { status: livePill(), thread, panel, placeholder: 'Ask what a step does, or change a rule…' });
}

const MODE = { trigger: 'Scheduled run', manual: 'Run by hand', retry: 'Retry', webhook: 'Webhook run', integrated: 'Run again after a fix', error: 'Repair run', internal: 'Internal run', cli: 'Run from the command line' };
function runTag(s) {
  if (s === 'success') return ['ok', false];
  if (s === 'waiting') return ['needs you', true];
  if (/error|crash|fail/.test(s || '')) return ['failed', true];
  if (s === 'running' || s === 'new') return ['running', false];
  return [s || 'unknown', false];
}
function activity() {
  const nn = n8n(), runs = S.runs, main = safeUrl(nn.main_url), sm = S.summary;
  const tally = (f) => runs.filter(f).length;
  const secs = runs.map((e) => (e.startedAt && e.stoppedAt ? (new Date(e.stoppedAt) - new Date(e.startedAt)) / 1000 : null)).filter((x) => x != null);
  const thread = h`${me('What have you done so far?')}${inky(h`<p>${runs.length ? 'Every run is on the right. Open one to see what each site gave. Each run is also in n8n and Apify, so you can check me.' : 'No runs yet. Every run shows up here once the workflow is live.'}</p>
    ${sm ? logLines([[`Last 24 h: ${plural(sm.runs, 'run')}, ${plural(sm.listings_checked, 'listing')} checked`, [has(sm.new_listings) && `${num(sm.new_listings)} new`, `${plural(sm.matches, 'match', 'matches')}`, has(sm.ai_calls) && plural(sm.ai_calls, 'AI call')].filter(Boolean).join(' · ')],
      has(sm.apify_usd) && [`${usd(sm.apify_usd)} on Apify in 24 h`, has(sm.apify_usd_runs) ? `${usd(sm.apify_usd_runs)} of it by these runs${has(sm.apify_usd_per_run) ? `, about ${usd(sm.apify_usd_per_run)} a run` : ''}; the rest was research` : '']]) : ''}
    <div class="row">${ext(main && main + '/executions', 'n8n runs')}<a class="btn" href="https://console.apify.com/actors/runs" target="_blank" rel="noopener">Apify runs ↗</a></div>`)}`;
  const link = (e) => { const base = safeUrl(e.workflow === 'repair' ? nn.repair_url : nn.main_url); return base ? `${base}/executions/${encodeURIComponent(e.id)}` : ''; };
  const per = new Map((sm && Array.isArray(sm.per_run) ? sm.per_run : []).map((x) => [String(x.id), x]));
  const stats = sm ? [['Runs · 24 h', sm.runs], ['Checked', sm.listings_checked], ['Matches', sm.matches, true], ['Repairs', sm.repairs], ['AI calls', sm.ai_calls], has(sm.apify_usd_per_run) ? ['Apify a run', usd(sm.apify_usd_per_run)] : ['Apify cost', has(sm.apify_usd) ? usd(sm.apify_usd) : null]]
    : [['Runs', runs.length], ['Succeeded', tally((e) => e.status === 'success')], ['Failed', tally((e) => /error|crash|fail/.test(e.status || ''))], ['Need you', tally((e) => e.status === 'waiting'), true], ['Repairs', tally((e) => e.workflow === 'repair')]];
  const row = (e) => {
    const [tag, hot] = runTag(e.status), d = secsBetween(e.startedAt, e.stoppedAt), url = link(e), x = per.get(String(e.id));
    const head = h`<span class="tt">${clock(e.startedAt)}</span><span class="ti">${e.workflow === 'repair' ? 'Repair workflow' : MODE[e.mode] || 'Run'} · #${e.id}<small>${day(e.startedAt)}${has(d) ? ` · took ${secsText(d)}` : ''}${x && has(x.listings) ? ` · ${plural(x.listings, 'listing')}` : ''}${x && Number(x.matches) ? ` · ${plural(x.matches, 'match', 'matches')}` : ''}</small></span><span class="etag ${hot ? 'hot' : ''}">${tag}</span>`;
    if (!x) return h`<a class="event" ${raw(url ? `href="${esc(url)}" target="_blank" rel="noopener"` : '')}>${head}</a>`;
    const src = Object.entries(x.sources || {});
    return h`<details class="runrow"><summary class="event">${head}</summary><div class="run-d">
      ${src.length ? h`<div class="srcs">${src.map(([name, n]) => h`<div><span>${name}</span><span class="mono">${num(n)}</span></div>`)}</div>` : ''}
      <div class="row" style="justify-content:space-between"><span class="mono small">${[has(x.listings) && plural(x.listings, 'listing'), has(x.new) && `${num(x.new)} new`, has(x.matches) && plural(x.matches, 'match', 'matches'),
        has(x.secs) && secsText(Number(x.secs)), has(x.apify_usd) && `$${Number(x.apify_usd).toFixed(2)} Apify`, '0 AI calls'].filter(Boolean).join(' · ')}</span>${url ? h`<a class="small" href="${url}" target="_blank" rel="noopener">Open in n8n ↗</a>` : ''}</div>
    </div></details>`;
  };
  const panel = h`<div class="between" style="align-items:center"><div class="seg"><a href="#results">Homes</a><span aria-current="page">Activity</span></div>
      ${runs.length ? h`<span class="mono small">${day(runs[runs.length - 1].startedAt)} ${clock(runs[runs.length - 1].startedAt)} → ${day(runs[0].startedAt)} ${clock(runs[0].startedAt)}</span>` : ''}</div>
    ${!runs.length ? (main ? empty('No runs yet', 'The workflow is built in n8n. Its runs show up here.') : empty()) : h`
      <div class="stats">${stats.filter(([, v]) => v != null).map(([k, v, hot]) => h`<div class="stat"><span>${k}</span><span class="${hot && Number(v) ? 'hot' : ''}">${typeof v === 'string' ? v : count(v, 'act-' + k)}</span></div>`)}</div>
      <div class="card stagger" style="padding:6px 18px">${runs.map(row)}</div>
      <span class="note">${secs.length ? `Average run: ${(secs.reduce((a, b) => a + b, 0) / secs.length).toFixed(1)} s. ` : ''}Every run is an n8n execution you can open.</span>`}`;
  return page('activity', { nav: 'activity', status: livePill(), thread, panel, placeholder: 'Ask about any run, or change a rule…' });
}

function share() {
  const s = S.shared;
  const thread = h`${me('Can I share this with someone?')}${inky(h`<p>Yes. There’s no code to send. I write down what this agent does, in plain words. They change it the same way: by describing it.</p>
    ${s ? h`${logLines([['Wrote the description', `for ${s.to}`], ['Left your data out', (s.keeps || []).join(', ').toLowerCase()], ['Made a link', 'runs in their own n8n and Apify']])}
      <div class="row"><button type="button" class="btn dark" data-act="copy" data-text="${s.link || ''}">Copy link for ${s.to}</button><a class="btn" href="#market">Post to marketplace</a></div>` : ''}
    ${S.shareErr ? h`<p class="hot">That did not work: ${S.shareErr}</p>` : ''}`)}`;
  const check = icon(P.check, 13, 3, '#2F9E5B'), lock = icon(P.lock, 13, 2.4, '#6B6862');
  const panel = h`<div class="tabs" style="justify-content:space-between"><span style="font-size:15px;font-weight:600">Share this agent</span>
      <div class="seg" style="font-size:13.5px"><span aria-current="true">A person</span><a href="#market">Marketplace</a></div></div>
    <div class="body"><div class="row" style="align-items:stretch;gap:14px;flex-wrap:nowrap;flex:1">
      <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:14px">
        <div class="card big" style="border-radius:18px">
          <div class="row" style="gap:12px">${critter(44)}<div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:18px;font-weight:600">${(s && s.name) || 'Buy-to-let abroad'}</span><span class="small">by you · made by describing it</span></div></div>
          ${!s ? h`<form data-act="share" style="display:flex;flex-direction:column;gap:10px">
              <label for="share-to" class="h3" style="font-size:13.5px">Who is it for?</label>
              <div class="row" style="flex-wrap:nowrap"><input id="share-to" name="to" maxlength="60" autocomplete="off" placeholder="e.g. Sanne" style="flex:1;min-height:40px;padding:0 14px;border-radius:999px;border:1px solid var(--edge);font-size:15px;outline:none">
              <button type="submit" class="btn dark" ${raw(S.shareBusy ? 'disabled' : '')}>${S.shareBusy ? 'Writing…' : 'Write the description'}</button></div>
              <span class="note">Inky writes what the agent does, leaves your data out and makes a link. Nothing is sent to anyone.</span></form>`
            : h`<div style="display:flex;flex-direction:column;gap:6px"><label for="share-desc" class="small" style="font-weight:600">What it does, in plain words · written by Inky, edit anything</label>
              <textarea id="share-desc" class="share-desc" rows="6">${s.description || ''}</textarea></div>
              <div class="grid2" style="gap:16px">
                <div style="display:flex;flex-direction:column;gap:6px;font-size:14px"><span style="font-size:13.5px;font-weight:600">${s.to} gets</span>${(s.gets || []).map((g) => h`<span class="row" style="gap:8px;flex-wrap:nowrap;align-items:baseline">${check}${g}</span>`)}</div>
                <div style="display:flex;flex-direction:column;gap:6px;font-size:14px"><span style="font-size:13.5px;font-weight:600">Stays with you</span>${(s.keeps || []).map((k) => h`<span class="row" style="gap:8px;flex-wrap:nowrap;align-items:baseline;color:#3F3C37">${lock}${k}</span>`)}</div>
              </div>`}
        </div>
        ${s ? h`<div class="card" style="border-radius:18px;padding:14px 16px;display:flex;align-items:center;gap:10px">
          <span class="mono" style="flex:1;min-width:0;height:40px;padding:0 14px;border-radius:999px;background:var(--panel);font-size:13.5px;display:flex;align-items:center;color:#3F3C37;overflow:hidden;white-space:nowrap">${s.link || ''}</span>
          <button type="button" class="btn" data-act="copy" data-text="${s.link || ''}">Copy link</button></div>` : ''}
      </div>
      <div class="card" style="width:290px;flex-shrink:0;border-radius:18px;display:flex;flex-direction:column;gap:12px">
        <span class="h3">${s ? s.to : 'They'} change${s ? 's' : ''} it by describing it</span>
        <p class="note" style="margin:0;font-size:14px;color:var(--ink)">They say what’s different, like another country or budget. Inky rewrites the plan and the rules. The rest stays the same.</p>
        <span style="margin-top:auto;padding-top:10px;border-top:1px solid var(--line)" class="note">Runs in their own n8n and Apify. You never see their results; they never see yours.</span>
      </div></div></div>`;
  return page('share', { status: livePill(), share: true, bare: true, thread, panel, label: 'Share this agent', placeholder: 'Change a rule…' });
}

function market() {
  // Static sample agents: the marketplace is a design mock for the demo.
  const cats = ['All', 'Shared with me', 'From Team Inky', 'Property', 'Buying & selling', 'Shops', 'Money & admin'];
  const add = ['Add', 'dark'], manage = ['Manage', ''];
  const shared = [
    ['Shared with you', 'only you can see these', [['Flat Finder Spain', 'from Sanne', 'octopus', '#2BA59B', 'bow', 'private link', 'Your agent, changed to Spain and €150,000. Sanne shared it back.', add, '#market'], ['Renovation Check', 'from Daan', 'cat', '#3B5BDB', 'glasses', 'private link', 'Compares renovation quotes in Porto with local prices. Read-only.', add, '#market']]],
    ['You shared', 'your data never goes with it', [['Buy-to-let abroad', 'by you', 'octopus', '#E86F51', 'none', '1 person', 'With Sanne. She runs it in her own n8n and Apify.', manage, '#share'], ['Webshop prices', 'by you', 'blob', '#E9A23B', 'none', 'team · 3', 'With your team. Everyone gets their own results.', manage, '#share']]],
  ];
  const featured = [['Yield Hunter', 'Mila', 'M', 'octopus', '#E9A23B', 'glasses'], ['Rent Radar', 'Team Inky', 'TI', 'octopus', '#E86F51', 'beanie'], ['Invoice Chaser', 'Jonas', 'J', 'cat', '#7C6CF2', 'none'], ['Price Watch', 'Priya', 'P', 'blob', '#2BA59B', 'headphones']];
  const property = [['Yield Hunter', 'Mila', 'octopus', '#E9A23B', 'glasses', 'Finds homes abroad that rent well and are rising in price. Never makes an offer.'], ['Rent Radar', 'Team Inky', 'octopus', '#E86F51', 'beanie', 'New rentals in your city minutes after they go live. Never pays or signs.'], ['Mortgage Rate Watch', 'Sem', 'blob', '#3B5BDB', 'none', 'Checks 12 banks every morning and tells you when your rate can drop.'], ['Viewing Booker', 'Noor', 'cat', '#F07BA8', 'bow', 'Finds viewing slots that fit your calendar. Asks before booking any.']];
  return h`<div class="shell">${nav('market')}<main class="market">
    <div class="between" style="align-items:flex-end"><h1>Marketplace <span class="tag preview big">Preview</span></h1><a class="btn dark" href="#share">Share an agent</a></div>
    <p class="note" style="margin:-8px 0 0;font-size:14px">A preview of where shared agents will live. The agents below are samples.</p>
    <div class="row">${cats.map((c, i) => h`<button type="button" class="cat" aria-pressed="${String(i === 0)}">${c}</button>`)}</div>
    <div class="search"><label class="sr" for="store-search">Search agents</label>${icon(P.search, 17, 2, '#6B6862')}<input id="store-search" type="search" placeholder="Search by creator or agent name"></div>
    <section class="shared" aria-label="Shared agents">${shared.map(([title, note, rows]) => h`<div style="display:flex;flex-direction:column">
      <div class="between" style="padding-bottom:4px"><h2 style="margin:0;font-size:16px;font-weight:600">${title}</h2><span class="small" style="font-size:13px">${note}</span></div>
      ${rows.map(([name, by, kind, color, acc, who, blurb, [action, cls], href]) => h`<div class="mrow">${critter(40, kind, color, acc)}<div class="who"><span><b>${name}</b> <span class="muted">${by}</span></span><small>${blurb}</small></div>
        <span class="pill" style="background:#fff;border:1px solid var(--line);font-size:12px;padding:3px 9px">${who}</span><a class="btn ${cls}" style="min-height:34px" href="${href}">${action}</a></div>`)}</div>`)}</section>
    <h2 style="margin:4px 0 0;font-size:16px;font-weight:600">Featured</h2>
    <div class="featured stagger">${featured.map(([name, by, ini, kind, color, acc]) => h`<a class="feat" href="#market"><div class="av">${critter(80, kind, color, acc)}<span class="ini">${ini}</span></div><span style="font-size:15px;font-weight:600">${name}</span><span class="small" style="font-size:13px">by ${by}</span></a>`)}</div>
    <div class="between" style="padding:10px 0 0"><h2 style="margin:0;font-size:16px;font-weight:600">Property</h2><a class="muted" href="#market" style="font-size:14px">View all</a></div>
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:40px">${property.map(([name, by, kind, color, acc, blurb]) => h`<div class="mrow">${critter(40, kind, color, acc)}<div class="who"><span><b>${name}</b> <span class="muted">by ${by}</span></span><small>${blurb}</small></div><a class="btn" style="min-height:34px;background:var(--chip);border-color:var(--chip);font-weight:500" href="#market">Add</a></div>`)}</div>
  </main></div>`;
}

// The end card (EndCard.dc.html) as a screen, so the last shot is recorded live with last night's real totals (/api/end).
// Press F for full screen.
function end() {
  const e = S.end || {}, sm = S.summary || {};
  const checked = pick(e, 'listings_checked') ?? sm.listings_checked, found = pick(e, 'matches') ?? sm.matches, fixes = pick(e, 'fixes') ?? sm.repairs, runs = pick(e, 'runs') ?? sm.runs;
  const repo = String(e.repo || 'github.com/GHGuide/inky').replace(/^https?:\/\//, '').replace(/\/$/, '');
  const facts = [has(checked) && h`${count(checked, '', 400)} listings checked${has(runs) ? ` in ${plural(runs, 'run')}` : ''}`, has(found) && h`<span class="hot">${count(found, '', 600)} ${Number(found) === 1 ? 'home' : 'homes'} found</span>`,
    has(fixes) && `${num(fixes)} ${Number(fixes) === 1 ? 'time' : 'times'} I stepped in`].filter(Boolean);
  const cost = [has(e.apify_usd_per_run) ? `$${Number(e.apify_usd_per_run).toFixed(2)} a run on Apify` : has(e.apify_usd_total) && `$${Number(e.apify_usd_total).toFixed(2)} on Apify`,
    has(e.ai_calls_per_run) && `${num(e.ai_calls_per_run)} AI calls a run`].filter(Boolean);
  const brand = (svg, name, n) => h`<span class="with">${bigIcon(svg, n)}${name}</span>`;
  return h`<main class="endcard"><div class="end-main">
      <div class="end-logo">${critter(112)}<span>Inky</span></div>
      <h1>Tell it once.</h1>
      <p>Describe a task in plain words. Inky learns it once, then runs it on its own with Apify and n8n, and only asks you when it must.</p>
      ${facts.length ? h`<span class="end-facts">Last night: ${facts.map((f, i) => h`${i ? ' · ' : ''}${f}`)}</span>` : ''}
      ${cost.length ? h`<span class="end-facts dim">${cost.join(' · ')}</span>` : ''}
    </div>
    <div class="end-foot">
      <div class="row" style="gap:18px;flex-wrap:nowrap"><span class="qr"><img src="qr-repo.svg" alt="QR code: ${repo}" data-fallback></span>
        <div style="display:flex;flex-direction:column;gap:4px"><span style="font-size:18px;font-weight:600">Open source · MIT · open models</span><a class="mono end-repo" href="https://${repo}" target="_blank" rel="noopener">${repo}</a></div></div>
      <div class="row end-with"><span class="small" style="font-size:15px">Built with</span>${brand(APIFY, 'Apify', 24)}${brand(N8N, 'n8n', 26)}${brand(TG, 'Telegram', 24)}</div>
    </div></main>`;
}

// ---------- router ----------
const ROUTES = { home, task, confirm, research: researchView, screen, fast, results, workflow, activity, share, market, end };
const TITLES = { home: 'New task', task: 'Plan', confirm: 'Your plan', research: 'Research', screen: 'Screen', fast: 'Turbo', results: 'Results', workflow: 'Workflow', activity: 'Activity', share: 'Share', market: 'Marketplace', end: 'Tell it once' };
const route = () => { const k = location.hash.slice(1); return ROUTES[k] ? k : 'home'; };
let shown = null;
function render() {
  const k = route(), enter = k !== shown;
  shown = k;
  const app = $('#app');
  const focus = document.activeElement && document.activeElement.id, typed = !enter && $('#msg') ? $('#msg').value : '';  // keep a half-typed message
  app.innerHTML = ROUTES[k]().__raw;
  document.title = 'Inky · ' + TITLES[k];
  if (typed && $('#msg')) $('#msg').value = typed;
  if (focus && !enter && document.getElementById(focus)) document.getElementById(focus).focus();
  for (const img of app.querySelectorAll('img[data-fallback]')) img.addEventListener('error', () => img.replaceWith(Object.assign(document.createElement('span'), { className: 'qr-none', textContent: 'QR' })));
  const m = $('.msgs');
  if (m) m.scrollTop = m.scrollHeight;
  fit();
  motion(app, enter);
  if (k === 'task') startInterview();
  if (k === 'end' && !S.endAsked) { S.endAsked = true; api('/api/end').then((d) => { if (d && typeof d === 'object') { S.end = d; if (route() === 'end') { shown = null; render(); } } }, () => {}); }
}

// ---------- motion ----------
// A new screen: cards and messages rise in one after another. Numbers count up the first time they show, and
// again whenever they change (a rule edit moves "46 homes" to the new count). Everything is off for reduced motion.
const calm = matchMedia('(prefers-reduced-motion: reduce)');
const seen = new Map();
function motion(app, enter) {
  clearTimeout(motion.t);
  app.classList.toggle('enter', enter && !calm.matches);
  if (enter) motion.t = setTimeout(() => app.classList.remove('enter'), 2200 * SLOW);
  for (const list of app.querySelectorAll('.body, .msgs, .home-in, .market, .stagger, .play, tbody, .log, .end-main'))
    [...list.children].forEach((c, i) => c.style.setProperty('--i', Math.min(i, 16)));
  for (const el of app.querySelectorAll('[data-count]')) countUp(el, enter);
  tickCountdown();
  slowDown();
}
// ?rec=1: every CSS animation and transition plays 1.3× slower, delays included.
function slowDown() { if (REC && document.getAnimations) for (const a of document.getAnimations()) if (a.playbackRate === 1) a.playbackRate = 1 / SLOW; }
function countUp(el, enter) {
  const to = Number(el.dataset.count), key = el.dataset.key;
  const from = key && seen.has(key) ? seen.get(key) : enter ? 0 : to;
  if (key) seen.set(key, to);
  if (calm.matches || from === to || !Number.isFinite(to)) return;
  const dec = Number.isInteger(to) ? 0 : 1, delay = Number(el.dataset.delay || 0) * SLOW, dur = (900 + Math.min(600, Math.abs(to - from) / 40)) * SLOW;
  const t0 = performance.now() + delay;
  el.textContent = from.toLocaleString('en', { maximumFractionDigits: dec });
  const step = (t) => {
    if (!el.isConnected) return;
    const p = Math.min(1, Math.max(0, (t - t0) / dur)), e = 1 - Math.pow(1 - p, 3);
    el.textContent = (from + (to - from) * e).toLocaleString('en', { minimumFractionDigits: p < 1 ? dec : 0, maximumFractionDigits: dec });
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
// "Next run in 7:12": the schedule is every 15 minutes from the last scheduled run.
function tickCountdown() {
  for (const el of document.querySelectorAll('[data-countdown]')) {
    let next = new Date(el.dataset.countdown).getTime() + 15 * 60e3;
    while (next < Date.now() - 60e3) next += 15 * 60e3;
    const left = Math.max(0, Math.round((next - Date.now()) / 1000));
    el.textContent = left ? `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}` : 'now';
  }
}
setInterval(tickCountdown, 1000);
// The n8n picture is drawn 680 wide; zoom it down when the panel is narrower (laptop screens).
function fit() { for (const c of document.querySelectorAll('.wfc')) c.style.zoom = Math.min(1, c.parentElement.clientWidth / 680); }
window.addEventListener('resize', fit);
// ?rec=1: the 1440-wide design fills a 1920×1080 recording (CSS zoom; app.css divides 100vh by --z so it still fits).
function recZoom() { document.documentElement.style.setProperty('--z', String(Math.max(0.5, innerWidth / 1440))); }
if (REC) { document.documentElement.classList.add('rec'); recZoom(); window.addEventListener('resize', recZoom); }

// ---------- actions ----------
function mic(btn) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const input = btn.closest('form').querySelector('input[type=text], textarea');
  if (!SR) { input.placeholder = 'Voice input needs Chrome'; return; }
  const rec = new SR();
  rec.lang = 'en-US'; rec.interimResults = true;
  btn.classList.add('rec');
  rec.onresult = (e) => { input.value = [...e.results].map((x) => x[0].transcript).join(''); };
  rec.onend = rec.onerror = () => btn.classList.remove('rec');
  rec.start();
}
const ACT = {
  start(f) { const t = f.elements.prompt.value.trim(); if (!t) return; iv = freshIv(t); saveIv(); location.hash = '#task'; },
  fill(el) { const i = $('#home-prompt') || $('#msg'); i.value = el.dataset.text; i.focus(); },
  focus() { $('#msg').focus(); },
  command(f) { const t = f.elements.text.value.trim(); if (!t || S.busy) return; f.elements.text.value = ''; if (BEST.test(t)) bestNow(t); else sendCommand(t); },
  free(f) {
    const t = f.elements.text.value.trim();
    if (!t || iv.busy || REPLAY) return;
    f.elements.text.value = '';
    if (current()) return submitRound(t, [{ q: 'In my own words', a: t }]);
    if (!iv.prompt) iv.prompt = t;
    iv.done = null; iv.messages.push({ role: 'user', content: t }); askInterview();
  },
  round(f) {
    const cur = current();
    if (!cur) return;
    const answers = cur.questions.map((q, i) => ({ q: q.text, a: (f.elements['a' + i]?.value || '').trim() || 'You decide' }));
    submitRound(answers.map((x) => `${x.q}\n→ ${x.a}`).join('\n\n'), answers);
  },
  decide(el) { el.parentElement.querySelector('input').value = 'You decide'; },
  skip() { submitRound('Skip the rest of the questions and use sensible defaults.', [{ q: 'The rest', a: 'Use defaults' }]); },
  retry() { if (!iv.busy) askInterview(); },
  version(el) { S.v = Number(el.dataset.v); render(); },
  research() { runResearch(); },
  build() { runBuild(); },
  best() { bestNow(); },
  why(el) { const k = el.dataset.k; if (S.why.has(k)) S.why.delete(k); else S.why.add(k); render(); },
  fcity(el) { S.f.city = el.dataset.v; render(); },
  fmin(el) { S.f.min = Number(el.dataset.v) || 0; render(); },
  async share(f) {
    const to = f.elements.to.value.trim();
    if (!to || S.shareBusy) return;
    S.shareBusy = true; S.shareErr = ''; render();
    try { S.shared = { to, ...(await api('/api/share', { to })) }; } catch (e) { S.shareErr = e.message; }
    S.shareBusy = false; render();
  },
  copy(el) { navigator.clipboard?.writeText(el.dataset.text).then(() => { el.textContent = 'Copied'; }, () => {}); },
  mic,
};
document.addEventListener('keydown', (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey || e.defaultPrevented) return;
  const inField = e.target.closest && e.target.closest('input, textarea, select, [contenteditable]');
  if (inField) { if (e.key === 'Escape') e.target.blur(); return; }
  const k = route();
  if (e.key === '/' && $('#msg')) { e.preventDefault(); $('#msg').focus(); }
  else if (/^[1-5]$/.test(e.key) && TAB_OF[k]) { const r = TABS[Number(e.key) - 1][1]; location.hash = r === 'task' && iv.done ? '#confirm' : '#' + r; }
  else if ((e.key === 'f' || e.key === 'F') && k === 'end') { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen?.().catch(() => {}); }
});
document.addEventListener('input', (e) => { if (e.target.id === 'share-desc' && S.shared) S.shared.description = e.target.value; });
document.addEventListener('submit', (e) => { e.preventDefault(); const a = ACT[e.target.dataset.act]; if (a) a(e.target); });
document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el || el.tagName === 'FORM') return;
  const a = ACT[el.dataset.act];
  if (a) { e.preventDefault(); a(el); }
});
// Page changes cross-fade and the tab pill slides to the new tab (View Transitions, where the browser has them).
window.addEventListener('hashchange', () => { if (document.startViewTransition && !calm.matches) document.startViewTransition(render).ready.catch(() => {}); else render(); });  // a skipped transition is fine

// Poll so research, runs and links appear while the build finishes; never re-render over anything typed and not sent yet.
let last = '';
const dirty = () => [...document.querySelectorAll('#app input, #app textarea')].some((el) => el.value !== el.defaultValue);
async function tick() {
  const first = !S.loaded;
  await refresh();
  if (first) shown = null;  // the skeleton gave way to data: play the entry motion now
  const now = JSON.stringify([S.state, S.runs, S.summary]);
  if (now !== last && !S.busy && !jobOn() && (first || (!iv.busy && !dirty()))) { last = now; render(); }
}
render();
tick();
setInterval(tick, 20000);
