// Inky's compiled program: turn raw Apify items into one listing shape, then score them against
// the rules GLM derived. The same file runs locally (node inky.js normalize ...) and inside the
// n8n Code node, so the rules the judges see in n8n are exactly the ones that were tested here.

const CITY = { porto: 'PT', bari: 'IT', lodz: 'PL' };

function cityKey(name) {
  return String(name || '')
    .replace(/[Łł]/g, 'l')
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .toLowerCase().trim();
}

// otodom does not return districts for Łódź, only coordinates.
// ponytail: rough districts by distance and direction from the centre; use real boundaries if zones matter more.
function lodzDistrict(lat, lon) {
  const dy = (lat - 51.7687) * 111, dx = (lon - 19.457) * 68.7;  // km
  if (Math.hypot(dx, dy) < 2) return 'Śródmieście';
  const a = Math.atan2(dy, dx) * 180 / Math.PI;  // 0 = east, 90 = north
  return a >= 45 && a < 135 ? 'Bałuty' : a >= -45 && a < 45 ? 'Widzew' : a >= -135 && a < -45 ? 'Górna' : 'Polesie';
}

function num(v) {
  const n = typeof v === 'number' ? v : parseFloat(String(v ?? '').replace(/[^\d.]/g, ''));
  return Number.isFinite(n) ? n : null;
}

// One raw Apify item -> { id, source, city, country, op, price_eur, size_m2, bedrooms, zone, url, ... }.
// `hint` fills what an actor does not say itself (otodom items do not carry sale/rent).
function normalize(item, plnPerEur, hint = {}) {
  let l;
  if (item.propertyCode !== undefined) {
    // In Portugal idealista's "municipality" is the parish (Campanhã, Bonfim...) and the city is the province.
    const inCity = CITY[cityKey(item.municipality)];
    const rooms = num(item.rooms);
    l = {
      source: 'idealista', id: String(item.propertyCode), op: item.operation,
      city: inCity ? item.municipality : item.province,
      zone: inCity ? item.neighborhood || item.district || item.municipality : item.municipality,
      price: num(item.price), currency: 'EUR', size_m2: num(item.size),
      // idealista.it counts all rooms (locali), idealista.pt counts bedrooms (T2 = 2)
      bedrooms: rooms == null ? null : item.country === 'it' ? Math.max(rooms - 1, 0) : rooms,
      url: item.url, title: item.suggestedTexts?.title || item.address,
      lat: item.latitude, lon: item.longitude,
    };
  } else if (item.topology || item.geography) {
    const rooms = num(item.topology?.rooms);
    const contract = item.contract?.name || item.analytics?.contract || '';
    l = {
      source: 'immobiliare', id: String(item.id),
      op: /rent|affitto/i.test(contract) ? 'rent' : 'sale',
      city: item.geography?.municipality?.name,
      zone: item.geography?.macrozone?.name || item.geography?.microzone?.name || item.geography?.municipality?.name,
      price: num(item.price?.raw), currency: item.price?.currency || 'EUR',
      size_m2: num(item.topology?.surface?.size),
      bedrooms: num(item.analytics?.numBedrooms) ?? (rooms == null ? null : Math.max(rooms - 1, 0)),
      url: item.url || `https://www.immobiliare.it/annunci/${item.id}/`, title: item.title,
      lat: item.geography?.geolocation?.latitude, lon: item.geography?.geolocation?.longitude,
    };
  } else if (item.propertyUrl !== undefined) {
    const rooms = num(item.rooms);
    l = {
      source: 'otodom', id: String(item.id || item.propertyUrl), op: hint.op || 'sale',
      city: item.city,
      zone: item.district || item.subdistrict || (item.latitude ? lodzDistrict(item.latitude, item.longitude) : item.city),
      price: num(item.price), currency: item.priceCurrency || 'PLN', size_m2: num(item.area),
      bedrooms: rooms == null ? null : Math.max(rooms - 1, 0),
      url: item.propertyUrl, title: item.title, lat: item.latitude, lon: item.longitude,
    };
  } else if (item.source === 'tecnocasa') {
    // Items of the program Inky learned (teach/run_program.py, the inky-tecnocasa-homes actor): already typed.
    // Tecnocasa counts all rooms (locali), like immobiliare.it.
    const rooms = num(item.rooms);
    l = {
      source: 'tecnocasa', id: (String(item.url).match(/(\d+)\.html/) || [])[1] || String(item.url),
      op: item.op || hint.op || 'sale', city: item.city, zone: item.zone || item.city,
      price: num(item.price), currency: 'EUR', size_m2: num(item.size_m2),
      bedrooms: rooms == null ? null : Math.max(rooms - 1, 0),
      url: item.url, title: item.title,
    };
  } else {
    return null;
  }
  l.city = cityKey(l.city || hint.city);
  l.country = CITY[l.city] || null;
  l.op = l.op || hint.op;
  l.price_eur = l.price == null ? null : l.currency === 'PLN' ? Math.round(l.price / plnPerEur) : l.price;
  if (!l.country || !l.price_eur || !l.size_m2 || l.size_m2 < 15) return null;
  return l;
}

const OPS = {
  '<=': (a, b) => a <= b, '>=': (a, b) => a >= b, '==': (a, b) => a === b, '!=': (a, b) => a !== b,
  in: (a, b) => b.includes(a), not_in: (a, b) => !b.includes(a),
};

// Yield after costs for one sale listing, using the rent per m² of its neighbourhood.
function economics(l, zones, costs) {
  const z = zones[`${l.city}|${l.zone}`];
  const c = costs[l.country];
  if (!z || !c || !z.rent_m2) return null;
  const rentMonth = z.rent_m2 * l.size_m2;
  const collected = rentMonth * 12 * (1 - c.vacancy);
  const net = collected * (1 - c.management) - l.price_eur * c.upkeep - collected * c.rent_tax;
  return {
    rent_month: Math.round(rentMonth),
    gross_yield: +((rentMonth * 12) / l.price_eur * 100).toFixed(2),
    net_yield: +(net / (l.price_eur * (1 + c.buy_costs)) * 100).toFixed(2),
    price_vs_zone: +((l.price_eur / l.size_m2) / z.sale_m2).toFixed(2),
    zone_rent_listings: z.n_rent,
    price_trend: c.price_trend,
    currency: l.currency,
  };
}

function score(l, rules, zones, costs) {
  const e = economics(l, zones, costs);
  if (!e) return { ...l, match: false, passed: [], failed: ['no rent data for this area'] };
  const f = { ...l, ...e };
  const passed = [], failed = [];
  for (const r of rules) (OPS[r.op] && OPS[r.op](f[r.field], r.value) ? passed : failed).push(r.id);
  return { ...f, match: failed.length === 0, passed, failed };
}

// ---- end of compiled program (workflow.py copies everything above this line into n8n) ----

if (typeof module !== 'undefined') module.exports = { normalize, score, economics, cityKey };

// CLI, used by derive.py so Python and n8n share one implementation:
//   node inky.js normalize <plnPerEur> <raw.json>...   raw files named <city>-<sale|rent>-<source>.json
//   node inky.js score < {listings, rules, zones, costs}
if (typeof module !== 'undefined' && require.main === module) {
  const [cmd, pln, ...files] = process.argv.slice(2);
  const fs = require('fs'), path = require('path');
  if (cmd === 'score') {
    const { listings, rules, zones, costs } = JSON.parse(fs.readFileSync(0, 'utf8'));
    process.stdout.write(JSON.stringify(listings.map((l) => score(l, rules, zones, costs))));
    return;
  }
  if (cmd !== 'normalize') throw new Error('usage: node inky.js normalize <plnPerEur> <raw.json>... | score');
  const out = [];
  for (const file of files) {
    const [city, op] = path.basename(file, '.json').split('-');
    for (const item of JSON.parse(fs.readFileSync(file, 'utf8'))) {
      const l = normalize(item, +pln, { city, op });
      if (l) out.push(l);
    }
  }
  process.stdout.write(JSON.stringify(out));
}
