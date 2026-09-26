// The program Inky learned on tecnocasa.it (program.json, copied from teach/tecnocasa.program.json
// by teach/publish.py), as an Apify actor. No model and no browser: the shortcut learn.py found,
// one JSON request per page, typed with the recorded fields. Same rules as teach/run_program.py.
import { readFileSync } from 'node:fs';
import { Actor } from 'apify';

const program = JSON.parse(readFileSync(new URL('./program.json', import.meta.url), 'utf8'));
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36';

function dig(o, path) {
  for (const k of path ? path.split('.') : []) o = o && typeof o === 'object' ? o[k] : undefined;
  return o;
}

// One raw value -> its typed value. int: first number, dots are thousands (Italian '€ 175.000').
function typed(raw, f, base) {
  if (raw == null) return null;
  raw = String(raw).trim();
  if (f.re) {
    const m = raw.match(new RegExp(f.re));
    raw = (m ? m[1] ?? m[0] : '').trim();
  }
  if (f.type === 'int') {
    const m = raw.match(/\d[\d.]*/);
    return m ? parseInt(m[0].replace(/\./g, ''), 10) : null;
  }
  if (f.type === 'link') return raw ? new URL(raw, base).href : null;
  return raw || null;
}

async function get(url, params) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== ''));
  const r = await fetch(`${url}?${q}`, { headers: { 'User-Agent': UA, Accept: 'application/json' } });
  if (!r.ok) throw new Error(`${r.status} from ${url}`);
  return r.json();
}

// Other cities: the site's own autocomplete gives the city id and province (the search needs both).
async function cityParams(city) {
  const r = await get(new URL('/api/geo/autocomplete', program.start_url).href, { search: city, section: 'estate' });
  const c = (r.precise || []).find((x) => x.type === 'city');
  if (!c) throw new Error(`tecnocasa.it does not know the city "${city}"`);
  return { city: String(c.id), province: c.province_id, region: null, placeholder: null };
}

await Actor.init();
const { maxItems = 100, maxPrice = 200000, city = program.city } = (await Actor.getInput()) || {};
const sc = program.shortcut;
if (!sc) throw new Error('This program has no JSON shortcut; run teach/run_program.py --browser instead.');
const cityKey = String(city).trim().toLowerCase();
const params = { ...sc.params };
if (sc.inputs?.max_price) params[sc.inputs.max_price] = maxPrice ? String(maxPrice) : null;
if (cityKey !== program.city) Object.assign(params, await cityParams(city));

const seen = new Set();
for (let page = 1; seen.size < maxItems; page++) {
  const body = await get(sc.url, { ...params, [sc.page_param]: page });
  const items = dig(body, sc.items_path) || [];
  const rows = [];
  for (const x of items) {
    const row = { source: 'tecnocasa', city: cityKey, op: 'sale' };
    for (const [k, f] of Object.entries(program.item.fields)) row[k] = typed(dig(x, f.json), f, program.start_url);
    if (row.url && !seen.has(row.url) && seen.size < maxItems) {
      seen.add(row.url);
      rows.push(row);
    }
  }
  await Actor.pushData(rows);
  const last = dig(body, sc.pages_path);
  console.log(`page ${page}: ${rows.length} listings (${seen.size} total)`);
  if (!rows.length || (Number.isInteger(last) && page >= last)) break; // past the last page the site returns other listings
}
await Actor.exit();
