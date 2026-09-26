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
const LOGO = raw('<svg width="26" height="26" viewBox="0 0 120 120" aria-hidden="true"><g fill="none" stroke="#E86F51" stroke-width="11" stroke-linecap="round"><path d="M34 76 C 28 92, 16 98, 20 110"/><path d="M47 80 C 45 96, 38 104, 42 114"/><path d="M60 82 C 62 98, 56 106, 60 114"/><path d="M73 80 C 75 96, 82 104, 78 114"/><path d="M86 76 C 92 92, 104 98, 100 110"/></g><ellipse cx="60" cy="52" rx="38" ry="36" fill="#E86F51"/><ellipse cx="46" cy="54" rx="5.5" ry="7.5" fill="#111110"/><ellipse cx="74" cy="54" rx="5.5" ry="7.5" fill="#111110"/><circle cx="48" cy="51" r="2" fill="#FFFFFF"/><circle cx="76" cy="51" r="2" fill="#FFFFFF"/><path d="M54 66 Q60 72 66 66" fill="none" stroke="#111110" stroke-width="3" stroke-linecap="round"/></svg>');
const FACE = '<ellipse cx="46" cy="54" rx="5.5" ry="7.5" fill="#1D1A17"/><ellipse cx="74" cy="54" rx="5.5" ry="7.5" fill="#1D1A17"/><circle cx="48" cy="51" r="2" fill="#FFFFFF"/><circle cx="76" cy="51" r="2" fill="#FFFFFF"/>';
const BODY = {
  octopus: (c) => `<g fill="none" stroke="${c}" stroke-width="11" stroke-linecap="round"><path d="M34 76 C 28 92, 16 98, 20 110"/><path d="M47 80 C 45 96, 38 104, 42 114"/><path d="M60 82 C 62 98, 56 106, 60 114"/><path d="M73 80 C 75 96, 82 104, 78 114"/><path d="M86 76 C 92 92, 104 98, 100 110"/></g><ellipse cx="60" cy="52" rx="38" ry="36" fill="${c}"/><ellipse cx="46" cy="30" rx="11" ry="6" fill="#FFFFFF" opacity="0.35"/>${FACE}<ellipse cx="35" cy="66" rx="6" ry="3.5" fill="#F7A99A"/><ellipse cx="85" cy="66" rx="6" ry="3.5" fill="#F7A99A"/><path d="M54 66 Q60 72 66 66" fill="none" stroke="#1D1A17" stroke-width="3" stroke-linecap="round"/>`,
  cat: (c) => `<path d="M24 46 L30 10 L54 30 Z" fill="${c}"/><path d="M96 46 L90 10 L66 30 Z" fill="${c}"/><path d="M32 36 L34 20 L45 29 Z" fill="#F7A99A"/><path d="M88 36 L86 20 L75 29 Z" fill="#F7A99A"/><ellipse cx="46" cy="106" rx="9" ry="7" fill="${c}"/><ellipse cx="74" cy="106" rx="9" ry="7" fill="${c}"/><ellipse cx="60" cy="62" rx="40" ry="38" fill="${c}"/><ellipse cx="46" cy="38" rx="10" ry="5" fill="#FFFFFF" opacity="0.3"/><ellipse cx="46" cy="55" rx="5.5" ry="7.5" fill="#1D1A17"/><ellipse cx="74" cy="55" rx="5.5" ry="7.5" fill="#1D1A17"/><circle cx="48" cy="52" r="2" fill="#FFFFFF"/><circle cx="76" cy="52" r="2" fill="#FFFFFF"/><ellipse cx="34" cy="69" rx="6" ry="3.5" fill="#F7A99A"/><ellipse cx="86" cy="69" rx="6" ry="3.5" fill="#F7A99A"/><path d="M57 66 L63 66 L60 70 Z" fill="#F7A99A"/><path d="M53 73 Q56.5 77 60 73 Q63.5 77 67 73" fill="none" stroke="#1D1A17" stroke-width="2.5" stroke-linecap="round"/><g stroke="#1D1A17" stroke-width="2" stroke-linecap="round" opacity="0.45"><path d="M18 64 L34 66"/><path d="M18 73 L34 71"/><path d="M102 64 L86 66"/><path d="M102 73 L86 71"/></g>`,
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
const S = { state: {}, runs: [], log: [], busy: false, v: null, shared: null, shareBusy: false, shareErr: '' };
const store = { get(k) { try { return JSON.parse(sessionStorage.getItem(k)); } catch { return null; } }, set(k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } } };
const freshIv = (prompt = '') => ({ prompt, messages: [], rounds: [], done: null, busy: false, error: '' });
let iv = { ...freshIv(), ...store.get('inky.iv'), busy: false };
const saveIv = () => store.set('inky.iv', iv);
const current = () => { const r = iv.rounds[iv.rounds.length - 1]; return r && !r.answers ? r : null; };

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new Error((data && data.error) || `${r.status} ${r.statusText}`);
  return data;
}
async function refresh() {
  const [st, runs] = await Promise.all([api('/api/state').catch(() => null), api('/api/executions').catch(() => null)]);
  S.state = st && typeof st === 'object' ? st : {};
  S.runs = Array.isArray(runs) ? runs : [];
}
const research = () => S.state.research || null;
const finalRules = () => (S.state.rules && S.state.rules.final) || [];
const versions = () => (S.state.rules && S.state.rules.versions) || (research() && research().versions) || [];
const n8n = () => S.state.n8n || {};
const built = () => !!safeUrl(n8n().main_url);
// ponytail: /api/state has no n8n "active" flag, so running = a scheduled run started in the last 30 min (it runs every 15).
const live = () => built() && S.runs.some((e) => e.workflow !== 'repair' && (e.status === 'running' || (e.mode === 'trigger' && Date.now() - new Date(e.startedAt) < 30 * 60e3)));
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
const passes = (m) => finalRules().every((r) => { const get = HOME_FIELD[r.field], x = get && get(m); return x == null || !TEST[r.op] || TEST[r.op](x, r.value); });

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
function page(k, o) {
  const panel = o.bare ? o.panel : h`${tabs(k)}<div class="body">${o.panel}</div>`;
  return h`<div class="shell">${nav(o.nav || 'task')}<div class="col">${header(o.status, o.acc, o.share)}<div class="split">
    <section class="thread" aria-label="Conversation"><div class="msgs">${o.thread}${k === 'task' ? '' : commandLog()}</div>${composer(o.placeholder || 'Change a rule…', k === 'task' ? 'free' : 'command')}</section>
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
const commandLog = () => S.log.map((x) => h`${me(x.me)}${x.res ? inky(reply(x.res)) : x.err ? inky(h`<p class="hot">That did not work: ${x.err}</p>`) : inky(h`<p class="muted">Working on it…</p>`)}`);
async function sendCommand(text) {
  const entry = { me: text };
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
  S.busy = false; render();
}

// ---------- interview ----------
function startInterview() {
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
  if (!cur || iv.busy) return;
  cur.answers = answers;
  iv.messages.push({ role: 'assistant', content: JSON.stringify({ round: cur.round, understood: cur.understood, questions: cur.questions }) }, { role: 'user', content });
  askInterview();
}

// ---------- routes ----------
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
      ${['Find a rental property abroad', 'Watch webshops for price drops', 'Chase unpaid invoices'].map((t) => h`<button type="button" class="suggest" data-act="fill" data-text="${t}">${t}</button>`)}
    </div>
    <div style="width:100%;margin-top:36px;display:flex;flex-direction:column;gap:12px">
      <div class="between"><h2 style="margin:0;font-size:16px;font-weight:600">Or start from someone else’s agent</h2><a href="#market" class="muted" style="font-size:14px">Marketplace</a></div>
      <div class="agents">${agent('Yield Hunter', 'Homes abroad that rent well', 'octopus', '#E9A23B', 'glasses')}${agent('Price Watch', 'Competitor prices, hourly', 'blob', '#2BA59B', 'headphones')}${agent('Invoice Chaser', 'Friendly payment reminders', 'cat', '#7C6CF2')}</div>
    </div>
  </div></main></div>`;
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
      ${cur ? h`<form class="round" data-act="round"><span class="label">ROUND ${cur.round}</span>
        ${cur.questions.map((q, i) => h`<div class="q"><b>${q.text}</b>${q.why ? h`<span class="why">${q.why}</span>` : ''}<div class="ans"><input name="a${i}" autocomplete="off" placeholder="Your answer" aria-label="${q.text}"><button type="button" class="decide" data-act="decide">You decide</button></div></div>`)}
        <div class="row"><button type="submit" class="btn dark" ${raw(iv.busy ? 'disabled' : '')}>Next</button><button type="button" class="linkbtn" data-act="skip">Skip the rest, use defaults</button></div></form>` : ''}
      ${iv.busy ? inky(h`<p class="muted">Thinking…</p>`) : ''}
      ${iv.error ? inky(h`<p class="hot">That did not work: ${iv.error}</p><div class="row"><button type="button" class="btn" data-act="retry">Try again</button></div>`) : ''}`;
  const rows = h`${understood.map((u) => h`<div class="kv"><span>${u.k}</span><span>${u.v}</span><span class="tag">✓</span></div>`)}
    ${asking.map((q) => h`<div class="kv wide"><span class="hot">${q.text}</span><span class="tag ask">asking</span></div>`)}`;
  const panel = h`<div class="card big">
      <div class="between"><h2 class="h2">What I understood so far</h2>${total ? h`<span class="muted" style="font-size:14px"><b style="color:var(--ink)">${understood.length} of ${total}</b> clear</span>` : ''}</div>
      <div class="bar"><div style="width:${total ? Math.round((100 * understood.length) / total) : 0}%"></div></div>
      ${total ? h`<div>${rows}</div>` : h`<p class="note" style="margin:0">Nothing yet. What I understand shows up here after the first round.</p>`}
    </div>
    <div class="row" style="align-items:stretch;gap:14px;flex-wrap:nowrap">
      <div class="card" style="flex:1;display:flex;flex-direction:column;gap:4px;border-radius:14px;padding:14px 16px"><span style="font-size:14px;font-weight:600">Why so many questions?</span><span class="note" style="font-size:13.5px">Each answer changes which homes count as a good deal. I only ask what changes the result.</span></div>
      <div style="display:flex;flex-direction:column;gap:8px;justify-content:center;align-items:flex-end">
        <button type="button" class="btn big" disabled>Start research${asking.length ? ` · ${asking.length} left` : ''}</button>
        ${cur ? h`<button type="button" class="linkbtn" data-act="skip">Skip the rest, use defaults</button>` : ''}
      </div></div>`;
  return page('task', { status: pill(cur ? `Planning · round ${cur.round}` : iv.busy ? 'Planning' : 'New task'), thread, panel, label: 'What Inky understood', placeholder: 'Or answer in your own words…' });
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
        <div class="row"><a class="btn dark big" href="#research">Yes, start research</a><a class="btn big" href="#task">Change something</a></div>`)}`;
  const rows = plan ? Object.entries(plan).filter(([k]) => k !== 'never' && k !== 'question') : [];
  const panel = !plan ? empty('No plan yet', 'Start a new task and answer a few questions.') : h`<div class="row" style="align-items:stretch;gap:16px;flex-wrap:nowrap;flex:1">
    <div class="card big" style="flex:1;min-width:0">
      <div class="between"><h2 class="h2">Your plan</h2><span class="muted" style="font-size:14px"><b style="color:var(--ink)">${rows.length} of ${rows.length}</b> clear</span></div>
      <div class="bar"><div style="width:100%"></div></div>
      <div>${rows.map(([k, v]) => h`<div class="kv" style="grid-template-columns:110px 1fr"><span>${label(k)}</span><span>${planValue(k, v)}</span></div>`)}</div>
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
  return page('confirm', { status: pill(plan ? 'Plan ready · check it' : 'No plan yet'), thread, panel, label: 'Your plan', placeholder: 'e.g. “actually, 2 bedrooms only”' });
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
    <div class="row"><a class="btn dark" href="#screen">Yes, watch them</a><button type="button" class="btn" data-act="focus">Change a rule</button></div>
    <p class="note">Research, not financial advice. Check with a local notary before you buy.</p>`, 'glasses')}`;
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
    <div class="card steps">${steps.map(([n, label]) => h`<div class="row" style="gap:14px;flex-wrap:nowrap"><div style="display:flex;flex-direction:column;gap:2px"><span class="n">${num(n)}</span><span class="small">${label}</span></div><span class="arrow" aria-hidden="true">→</span></div>`)}
      ${v ? h`<div style="display:flex;flex-direction:column;gap:2px"><span class="n hot">${num(v.zones)}</span><span class="small">${v.zones === 1 ? 'neighbourhood passes' : 'neighbourhoods pass'} v${v.v}</span></div>` : ''}</div>
    ${vs.length ? h`<div class="row" style="align-items:stretch;gap:14px;flex-wrap:nowrap">
      <div class="card" style="flex:1;min-width:0;display:flex;flex-direction:column;gap:6px">
        <div class="between"><span class="h3">Homes that pass each version</span><span class="mono small">tested on ${num(r.for_sale)} homes for sale</span></div>
        <div style="margin-top:8px">${vs.map((x, i) => h`<div class="vbar ${i === S.v ? 'on' : ''}"><span class="mono">v${x.v}</span><div class="track"><div style="width:${Math.max(2, Math.round((100 * (x.matches || 0)) / max))}%"></div></div><span class="mono" style="font-size:12.5px">${plural(x.matches, 'home')} · ${plural(x.zones, 'area')}</span></div>`)}</div>
        <p style="margin:0;padding-top:12px;font-size:13.5px;line-height:1.5;border-top:1px solid var(--row)">${!prev ? `v${v.v} is your plan turned into ${plural(vr.length, 'rule')}: ${plural(v.matches, 'home')} in ${plural(v.zones, 'neighbourhood')} ${v.matches === 1 ? 'passes' : 'pass'}.`
          : changed.length ? `v${v.v} changed ${changed.map((x) => x.id).join(', ')}. ${num(prev.matches)} → ${plural(v.matches, 'home')}, ${num(prev.zones)} → ${plural(v.zones, 'neighbourhood')}.` : `v${v.v} kept the rules of v${prev.v}.`}</p>
      </div>
      <div class="card" style="width:318px;flex-shrink:0;display:flex;flex-direction:column;gap:12px">
        <div class="vpick" role="group" aria-label="Rule version">${vs.map((x, i) => h`<button type="button" data-act="version" data-v="${i}" aria-pressed="${String(i === S.v)}">v${x.v}</button>`)}</div>
        <div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:15px;font-weight:600">${S.v === 0 ? 'From your plan' : `After testing v${prev.v}`}</span><span class="mono small">v${v.v} · ${plural(vr.length, 'rule')}</span></div>
        <div style="display:flex;flex-direction:column;gap:10px">${vr.map((x) => h`<div class="rule"><span class="m" style="color:${mark[x.m]}">${x.m}</span><span class="t"><span>${x.id ? x.id + ' · ' : ''}${x.t}</span>${x.why ? h`<small>${x.why}</small>` : ''}</span></div>`)}</div>
        <div class="between" style="margin-top:auto;padding-top:12px;border-top:1px solid var(--line)"><span class="muted" style="font-size:13.5px">Neighbourhoods that pass</span><span style="font-size:26px;font-weight:600;letter-spacing:-0.02em" class="${S.v === vs.length - 1 ? 'hot' : ''}">${num(v.zones)}</span></div>
      </div></div>` : empty('No rule versions yet')}
    ${zones.length ? h`<div class="card" style="padding:0"><table class="tbl">
      <thead><tr><th>${zones.length === 1 ? 'Top neighbourhood' : `Top ${zones.length} neighbourhoods`}</th><th>Yield after costs</th><th>Price trend</th><th>Rentals nearby</th><th>Matches</th><th style="text-align:right"><a class="muted" href="#results">${has(matchTotal()) ? `All ${plural(matchTotal(), 'home')}` : 'All homes'} →</a></th></tr></thead>
      <tbody>${zones.map((z) => h`<tr><td><b>${city(z.city)} · ${z.zone}</b></td><td class="num">${pct(z.net_yield)}</td><td class="num">${has(z.price_trend) ? (z.price_trend >= 0 ? '+' : '') + z.price_trend + '%/yr' : '–'}</td><td>${num(z.rent_listings)}</td><td>${num(z.matches)}</td><td style="text-align:right" class="${money(z.city) === 'złoty' ? 'hot' : 'muted'}">${money(z.city)}</td></tr>`)}</tbody>
    </table></div>` : ''}`;
  return page('research', { status: pill('Research done', 'coral', true), acc: 'glasses', thread, panel, placeholder: 'Ask why a rule is there…' });
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
          ${fields.length ? h`<span class="h3">What the program reads from each listing</span><div class="fields">${fields.map((f) => h`<div class="field" title="${f.sel}"><span>${f.name}</span><span>${f.sel || ' '}</span></div>`)}</div>` : ''}
          ${steps.length ? h`<span class="h3">Steps</span><ol class="steplist">${steps.map((s) => h`<li><span>${stepName(s)}</span><span class="d" title="${stepDetail(s)}">${stepDetail(s)}</span></li>`)}</ol>` : ''}
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

function fast() {
  const r = raceData(), a = r && r.agent;
  const calls = (n) => (has(n) ? ` · ${num(n)} AI ${Number(n) === 1 ? 'call' : 'calls'}` : '');
  const thread = h`<a class="stamp" href="#screen">↑ The program, slowly</a>${me('Show me all of them at full speed.')}${inky(!r
    ? h`<p>Turbo runs the same program in many windows at once, with no AI. The numbers show up after the first race.</p>`
    : h`<p>Here ${r.nWin === 1 ? 'is the window' : `are all ${num(r.nWin)} windows`}. It’s the same program in each one, with no AI.${has(r.used) ? ` It read everything in ${num(r.used)} seconds.` : ''}</p>
      ${logLines([has(r.listings) && [`Checked ${num(r.listings)} listings${has(r.pages) ? ` on ${num(r.pages)} pages` : ''}`, [has(r.perSec) && `${num(r.perSec)} per second`, has(r.calls) && `${num(r.calls)} AI calls`].filter(Boolean).join(' · ')],
        a && has(a.listings) && [`An AI clicking agent read ${num(a.listings)}${has(a.used) ? ` in ${num(a.used)} s` : ''}`, [has(a.calls) && `${num(a.calls)} AI calls`, has(a.cost) && `$${Number(a.cost).toFixed(2)}`].filter(Boolean).join(' · ')]])}
      ${a ? h`<p class="note">A clicking agent asks the AI before every click. Inky’s program doesn’t need to.</p>` : ''}`, 'headphones')}`;
  const stat = (k, v, hot) => (v ? h`<div class="stat"><span>${k}</span><span class="mono ${hot ? 'hot' : ''}" style="font-weight:400">${v}</span></div>` : '');
  const maxW = r ? Math.max(1, ...r.per.map(Number).filter((x) => !Number.isNaN(x))) : 1;
  const panel = !r ? h`<div class="between" style="align-items:center"><span class="h3">Turbo</span>${screenToggle('turbo')}</div>${empty()}` : h`
    <div class="between" style="align-items:center"><span class="h3">Turbo <span class="muted" style="font-weight:400">· ${num(r.nWin)} windows at once</span></span>${screenToggle('turbo')}</div>
    ${a && has(a.listings) && has(r.listings) ? h`<div class="card" style="display:flex;flex-direction:column;gap:12px">
      <div class="between"><span class="h3">Same task, ${has(r.secs) ? `same ${num(r.secs)} seconds` : 'same time'}</span><span class="mono small">listings read</span></div>
      <div class="race"><span style="font-weight:500">Inky</span><div class="track"><div style="width:100%;background:var(--coral)"></div></div><span class="mono" style="font-size:13px;text-align:right">${num(r.listings)}${calls(r.calls)}</span>
        <span class="muted">Clicking agent</span><div class="track"><div style="width:${Math.max(1, Math.min(100, (100 * a.listings) / Math.max(1, r.listings)))}%;background:var(--faint)"></div></div><span class="mono muted" style="font-size:13px;text-align:right">${num(a.listings)}${calls(a.calls)}</span></div>
    </div>` : ''}
    ${r.per.length ? h`<div class="arms">${r.per.map((n, i) => h`<div class="arm"><div class="arm-h"><span>Window ${i + 1}</span><span class="mono muted" style="font-size:11px;font-weight:400">✓ ${num(n)}</span></div>
      <div class="arm-b"><div class="bar"><div style="width:${Math.round((100 * (Number(n) || 0)) / maxW)}%;background:var(--coral)"></div></div><span class="muted" style="font-size:11.5px">${num(n)} listings · no AI</span></div></div>`)}</div>` : ''}
    <div class="stats">${stat('Inky’s time', has(r.used) ? num(r.used) + ' s' : '')}${stat('Listings', has(r.listings) ? num(r.listings) : '')}${stat('Per second', has(r.perSec) ? num(r.perSec) : '')}${stat('AI calls', has(r.calls) ? num(r.calls) : '')}${stat('Agent’s AI cost', a && has(a.cost) ? '$' + Number(a.cost).toFixed(2) : '', true)}</div>
    ${r.at ? h`<span class="note">Raced ${day(r.at)} ${clock(r.at)}.</span>` : ''}`;
  return page('fast', { status: livePill(), acc: 'headphones', thread, panel, placeholder: 'Say “slow down”, or change a rule…' });
}

function results() {
  const r = research(), saved = (r && r.matches) || [], ms = saved.filter(passes), last = [...S.log].reverse().find((x) => x.res);
  const total = matchTotal(), hidden = saved.length - ms.length;
  const headline = has(total) ? plural(total, 'home matches', 'homes match') : plural(ms.length, 'saved home passes', 'saved homes pass');
  const best = ms.reduce((b, m) => (!b || (m.net_yield || 0) > (b.net_yield || 0) ? m : b), null);
  const top = r && r.top_zones && r.top_zones[0];
  const cur = finalRules().find((x) => x.field === 'currency');
  const idea = cur && cur.op === '==' && cur.value === 'EUR' ? 'Also allow homes priced in złoty' : 'Only places with the euro';
  const thread = h`${r && r.at ? h`<span class="stamp">${day(r.at)} ${clock(r.at)}</span>` : ''}${inky(!r
    ? h`<p>Your results show up here after the first build.</p>`
    : h`<p>I checked ${num(r.listings_read)} listings.</p>${logLines([
      [headline, best && `best: ${best.title || 'a flat'} in ${best.zone}, ${pct(best.net_yield)} after costs`],
      top && [r.top_zones.length === 1 ? 'Top neighbourhood' : `${num(r.top_zones.length)} top neighbourhoods`, `${r.top_zones.length === 1 ? '' : 'first: '}${top.zone}, ${city(top.city)}`],
    ])}<div class="row"><button type="button" class="btn" data-act="fill" data-text="${idea}">${idea}</button></div>`)}`;
  const panel = h`<div class="seg"><span aria-current="page">Homes</span><a href="#activity">Activity</a></div>
    ${!r ? empty() : h`
      <div class="between" style="align-items:center"><h2 class="h2">${headline}</h2>${finalRules().length ? h`<span class="mono small">rules ${finalRules()[0].id}–${finalRules()[finalRules().length - 1].id}</span>` : ''}</div>
      <span class="mono small" style="margin-top:-8px">from ${num(r.listings_read)} listings${r.at ? ' · research ' + day(r.at) + ' ' + clock(r.at) : ''}${ms.length && has(total) && ms.length < total ? ` · showing ${num(ms.length)}` : ''}</span>
      ${last ? h`<div class="card" style="border-color:var(--coral);background:var(--blush);padding:12px 16px;display:flex;justify-content:space-between;gap:12px;align-items:baseline"><span style="font-size:14px"><b class="hot">Last change</b> · ${last.res.change}</span>${has(last.res.matches_before) && has(last.res.matches_after) ? h`<span class="mono" style="font-size:13px;white-space:nowrap">${num(last.res.matches_before)} → ${plural(last.res.matches_after, 'home')}</span>` : ''}</div>` : ''}
      ${ms.length ? h`<div class="card" style="padding:0;overflow:hidden"><table class="tbl">
        <thead><tr><th>Home</th><th>Where</th><th>Price</th><th>Size</th><th>After costs</th><th></th></tr></thead>
        <tbody>${ms.map((m) => h`<tr><td><div class="clip" title="${m.title || ''}">${m.title || 'Flat'}</div><div class="sub">${has(m.bedrooms) ? plural(m.bedrooms, 'bedroom') : ''}</div></td>
          <td>${m.zone || ''}<div class="sub">${city(m.city)}</div></td><td class="num">${eur(m.price_eur)}</td><td class="num">${has(m.size_m2) ? Math.round(m.size_m2) + ' m²' : '–'}</td><td class="num">${pct(m.net_yield)}</td>
          <td style="text-align:right">${safeUrl(m.url) ? h`<a href="${m.url}" target="_blank" rel="noopener" class="muted" aria-label="Open listing">↗</a>` : ''}</td></tr>`)}</tbody>
      </table></div>` : saved.length ? empty('None of the saved homes pass the new rules', 'The next research run lists the homes that do.') : empty('No homes match these rules', 'Change a rule in the message box.')}
      ${hidden > 0 ? h`<span class="note">The rules changed after the research, so ${plural(hidden, 'saved home')} that no longer ${hidden === 1 ? 'passes is' : 'pass are'} hidden.</span>` : ''}
      <span class="note">Research, not financial advice. Check with a local notary before you buy.</span>`}`;
  return page('results', { status: livePill(), thread, panel, placeholder: 'Change a rule in your own words…' });
}

const SOURCES = [['idealista · Porto', 'igolaizola~idealista-scraper'], ['idealista · Bari', 'igolaizola~idealista-scraper'], ['immobiliare · Bari', 'memo23~immobiliare-scraper'], ['otodom · Łódź', 'trev0n~otodom-scraper']];
function wfNode(x, y, inner, label, hot, cls = '') {
  return h`<div class="wfn ${cls}" style="left:${x - 45}px;top:${y - 26}px"><div class="wfbox ${hot ? 'hot' : ''}">${inner}</div><span>${label}</span></div>`;
}
function workflow() {
  const nn = n8n(), main = safeUrl(nn.main_url), repair = safeUrl(nn.repair_url);
  const runs = S.runs.filter((e) => e.workflow !== 'repair');
  const failed = runs.filter((e) => /error|crash|fail/.test(e.status || '')).length;
  const fixes = S.runs.filter((e) => e.workflow === 'repair');
  const rules = finalRules();
  const thread = h`${me('How does this actually run?')}${inky(h`<p>As one n8n workflow in your own account. Apify brings the listings in, n8n decides what to do and asks you. I only come back when something breaks.</p>
    ${main ? h`${logLines([['Built the workflow', 'created through the n8n API'], [`Uses ${SOURCES.length} Apify steps`, 'idealista, immobiliare, otodom'], ['Every run is an n8n execution', `${num(runs.length)} so far, ${num(failed)} failed`], repair && ['Built a repair workflow', 'fixes one broken step, then runs again']])}
      <div class="row">${ext(main, 'Open in n8n', 'btn dark')}${ext(repair, 'Repair workflow')}</div>` : h`<p class="note">It gets built after the research. Nothing is running yet.</p>`}`)}
    ${me('Can other people use it?')}${inky(h`<p>Yes. They get the same workflow, set up in their own n8n and Apify. Never your results, budget or messages.</p><div class="row"><a class="btn" href="#share">Share it</a></div>`)}`;
  const ys = [44, 112, 180, 248];
  const edges = ys.map((y) => `<path d="M66 145 C 90 145, 90 ${y}, 114 ${y}"/><path d="M166 ${y} C 190 ${y}, 190 145, 214 145"/>`).join('') + '<path d="M266 145 L 310 145"/><path d="M458 145 L 502 145"/><path d="M554 145 L 598 145"/>';
  const panel = !main ? empty() : h`
    <div class="between" style="align-items:center"><div class="row" style="gap:10px">${N8N}<h2 class="h2" style="font-size:20px">Your n8n workflow</h2>
      <span class="pill hot" style="font-size:12.5px;font-weight:500">Built by Inky via the n8n API</span>
      ${runs[0] ? h`<span class="pill" style="font-size:12.5px;background:#fff;border:1px solid var(--line)">last run ${clock(runs[0].startedAt)}</span>` : ''}</div>
      ${ext(main, 'Open in n8n', '')}</div>
    <div class="card" style="border-radius:18px;padding:14px 16px;display:flex;flex-direction:column;gap:10px">
      <div class="canvas"><div class="wfc">
        <svg width="680" height="302" viewBox="0 0 680 302" aria-hidden="true"><g fill="none" stroke="#B9B5AD" stroke-width="1.6">${raw(edges)}</g><g fill="none" stroke="#E86F51" stroke-width="1.8"><path d="M362 145 L 406 145"/></g></svg>
        ${wfNode(40, 145, icon(P.clock, 24, 1.8), 'Every 15 min')}
        ${SOURCES.map(([name], i) => wfNode(140, ys[i], raw(APIFY.__raw.replace(/width="15" height="15"/, 'width="24" height="24"')), name, false, 'src'))}
        ${wfNode(240, 145, icon(P.merge, 24, 1.8), 'Merge')}
        ${wfNode(336, 145, '{ }', rules.length ? `Score, ${rules[0].id}–${rules[rules.length - 1].id}` : 'Score on the rules')}
        ${wfNode(432, 145, raw(TG.__raw.replace(/width="15" height="15"/, 'width="24" height="24"')), 'Ask you on Telegram', true)}
        ${wfNode(528, 145, '{ }', 'Keep approved')}
        ${wfNode(624, 145, icon(P.mail, 24, 1.8), 'Gmail draft, never sent')}
      </div></div>
      <div class="onerror"><span class="mono hot" style="font-size:11px;white-space:nowrap">ON ERROR</span>
        ${['Error trigger', 'GLM-5.3 fixes 1 step', 'Save the fix', 'Run it again'].map((s, i) => h`${i ? h`<span aria-hidden="true" style="color:var(--coral)">→</span>` : ''}<span class="s">${s}</span>`)}
        <span style="margin-left:auto;white-space:nowrap">${fixes.length ? h`<span class="hot">used ${clock(fixes[0].startedAt)}</span> · ` : ''}${ext(repair, 'Open', 'hot')}</span></div>
    </div>
    <div class="row" style="align-items:stretch;gap:14px;flex-wrap:nowrap">
      <div class="card" style="flex:1;flex-basis:0;min-width:0;display:flex;flex-direction:column;gap:9px;padding:14px 16px">
        <span class="h3">n8n makes the decisions</span>
        ${[['Ask', 'A home passes every rule? Ask you on Telegram and wait for your tap.'], ['Draft', 'You tap “Save as draft”? Write a Gmail draft to the agent. Never sent.'], ['Error', 'A step fails? The repair workflow fixes that one step and runs again, at most once an hour.'], ['08:00', 'Every morning, a short digest on Telegram.']].map(([k, t]) => h`<div class="decide-row"><span class="k">${k}</span><span>${t}</span></div>`)}
        <span class="mono small" style="margin-top:auto">${runs.length ? `${num(runs.length)} executions · ${num(failed)} failed` : 'No runs yet'}</span>
      </div>
      <div class="card" style="flex:1;flex-basis:0;min-width:0;display:flex;flex-direction:column;gap:8px;padding:14px 16px">
        <div class="row" style="flex-wrap:nowrap">${APIFY}<span class="h3">Apify brings the data</span><a href="https://console.apify.com/actors/runs" target="_blank" rel="noopener" style="margin-left:auto;font-size:12.5px">Console ↗</a></div>
        ${SOURCES.map(([name, actor]) => h`<div class="between" style="font-size:13px"><span>${name}</span><span class="mono muted" style="font-size:11.5px">${actor}</span></div>`)}
        <span class="note" style="margin-top:auto;font-size:12px">Each step runs a Store actor and returns the newest listings.</span>
      </div></div>`;
  return page('workflow', { status: livePill(), thread, panel, placeholder: 'Ask what a node does, or change a rule…' });
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
  const nn = n8n(), runs = S.runs, main = safeUrl(nn.main_url);
  const count = (f) => runs.filter(f).length;
  const secs = runs.map((e) => (e.startedAt && e.stoppedAt ? (new Date(e.stoppedAt) - new Date(e.startedAt)) / 1000 : null)).filter((x) => x != null);
  const thread = h`${me('What have you done so far?')}${inky(h`<p>${runs.length ? 'Every run is on the right. Each one is also in n8n and Apify, so you can check me.' : 'No runs yet. Every run shows up here once the workflow is live.'}</p>
    <div class="row">${ext(main && main + '/executions', 'n8n runs')}<a class="btn" href="https://console.apify.com/actors/runs" target="_blank" rel="noopener">Apify runs ↗</a></div>`)}`;
  const link = (e) => { const base = safeUrl(e.workflow === 'repair' ? nn.repair_url : nn.main_url); return base ? `${base}/executions/${encodeURIComponent(e.id)}` : ''; };
  const panel = h`<div class="between" style="align-items:center"><div class="seg"><a href="#results">Homes</a><span aria-current="page">Activity</span></div>
      ${runs.length ? h`<span class="mono small">${day(runs[runs.length - 1].startedAt)} ${clock(runs[runs.length - 1].startedAt)} → ${day(runs[0].startedAt)} ${clock(runs[0].startedAt)}</span>` : ''}</div>
    ${!runs.length ? (main ? empty('No runs yet', 'The workflow is built in n8n. Its runs show up here.') : empty()) : h`
      <div class="stats">${[['Runs', runs.length], ['Succeeded', count((e) => e.status === 'success')], ['Failed', count((e) => /error|crash|fail/.test(e.status || ''))], ['Need you', count((e) => e.status === 'waiting'), true], ['Repairs', count((e) => e.workflow === 'repair')]]
        .map(([k, v, hot]) => h`<div class="stat"><span>${k}</span><span class="${hot && v ? 'hot' : ''}">${num(v)}</span></div>`)}</div>
      <div class="card" style="padding:6px 18px">${runs.map((e) => { const [tag, hot] = runTag(e.status); const d = e.startedAt && e.stoppedAt ? (new Date(e.stoppedAt) - new Date(e.startedAt)) / 1000 : null; const url = link(e);
        return h`<a class="event" ${raw(url ? `href="${esc(url)}" target="_blank" rel="noopener"` : '')}><span class="tt">${clock(e.startedAt)}</span><span class="ti">${e.workflow === 'repair' ? 'Repair workflow' : MODE[e.mode] || 'Run'} · #${e.id}<small>${day(e.startedAt)}${has(d) ? ` · took ${d < 10 ? d.toFixed(1) : Math.round(d)} s` : ''}</small></span><span class="etag ${hot ? 'hot' : ''}">${tag}</span></a>`; })}</div>
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
    <div class="between" style="align-items:flex-end"><h1>Marketplace</h1><a class="btn dark" href="#share">Share an agent</a></div>
    <div class="row">${cats.map((c, i) => h`<button type="button" class="cat" aria-pressed="${String(i === 0)}">${c}</button>`)}</div>
    <div class="search"><label class="sr" for="store-search">Search agents</label>${icon(P.search, 17, 2, '#6B6862')}<input id="store-search" type="search" placeholder="Search by creator or agent name"></div>
    <section class="shared" aria-label="Shared agents">${shared.map(([title, note, rows]) => h`<div style="display:flex;flex-direction:column">
      <div class="between" style="padding-bottom:4px"><h2 style="margin:0;font-size:16px;font-weight:600">${title}</h2><span class="small" style="font-size:13px">${note}</span></div>
      ${rows.map(([name, by, kind, color, acc, who, blurb, [action, cls], href]) => h`<div class="mrow">${critter(40, kind, color, acc)}<div class="who"><span><b>${name}</b> <span class="muted">${by}</span></span><small>${blurb}</small></div>
        <span class="pill" style="background:#fff;border:1px solid var(--line);font-size:12px;padding:3px 9px">${who}</span><a class="btn ${cls}" style="min-height:34px" href="${href}">${action}</a></div>`)}</div>`)}</section>
    <h2 style="margin:4px 0 0;font-size:16px;font-weight:600">Featured</h2>
    <div class="featured">${featured.map(([name, by, ini, kind, color, acc]) => h`<a class="feat" href="#market"><div class="av">${critter(80, kind, color, acc)}<span class="ini">${ini}</span></div><span style="font-size:15px;font-weight:600">${name}</span><span class="small" style="font-size:13px">by ${by}</span></a>`)}</div>
    <div class="between" style="padding:10px 0 0"><h2 style="margin:0;font-size:16px;font-weight:600">Property</h2><a class="muted" href="#market" style="font-size:14px">View all</a></div>
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:40px">${property.map(([name, by, kind, color, acc, blurb]) => h`<div class="mrow">${critter(40, kind, color, acc)}<div class="who"><span><b>${name}</b> <span class="muted">by ${by}</span></span><small>${blurb}</small></div><a class="btn" style="min-height:34px;background:var(--chip);border-color:var(--chip);font-weight:500" href="#market">Add</a></div>`)}</div>
  </main></div>`;
}

// ---------- router ----------
const ROUTES = { home, task, confirm, research: researchView, screen, fast, results, workflow, activity, share, market };
const TITLES = { home: 'New task', task: 'Plan', confirm: 'Your plan', research: 'Research', screen: 'Screen', fast: 'Turbo', results: 'Results', workflow: 'Workflow', activity: 'Activity', share: 'Share', market: 'Marketplace' };
const route = () => { const k = location.hash.slice(1); return ROUTES[k] ? k : 'home'; };
function render() {
  const k = route();
  $('#app').innerHTML = ROUTES[k]().__raw;
  document.title = 'Inky · ' + TITLES[k];
  const m = $('.msgs');
  if (m) m.scrollTop = m.scrollHeight;
  fit();
  if (k === 'task') startInterview();
}
// The n8n picture is drawn 680 wide; zoom it down when the panel is narrower (laptop screens).
function fit() { for (const c of document.querySelectorAll('.wfc')) c.style.zoom = Math.min(1, c.parentElement.clientWidth / 680); }
window.addEventListener('resize', fit);

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
  command(f) { const t = f.elements.text.value.trim(); if (t && !S.busy) sendCommand(t); },
  free(f) {
    const t = f.elements.text.value.trim();
    if (!t || iv.busy) return;
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
document.addEventListener('input', (e) => { if (e.target.id === 'share-desc' && S.shared) S.shared.description = e.target.value; });
document.addEventListener('submit', (e) => { e.preventDefault(); const a = ACT[e.target.dataset.act]; if (a) a(e.target); });
document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el || el.tagName === 'FORM') return;
  const a = ACT[el.dataset.act];
  if (a) { e.preventDefault(); a(el); }
});
window.addEventListener('hashchange', render);

// Poll so research, runs and links appear while the build finishes; never re-render over anything typed and not sent yet.
let last = '';
const dirty = () => [...document.querySelectorAll('#app input, #app textarea')].some((el) => el.value !== el.defaultValue);
async function tick() {
  await refresh();
  const now = JSON.stringify([S.state, S.runs]);
  if (now !== last && !S.busy && !iv.busy && !dirty()) { last = now; render(); }
}
render();
tick();
setInterval(tick, 20000);
