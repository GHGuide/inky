"""Inky writes its own n8n workflows through the n8n API.

    .venv/bin/python workflow.py                # create or update both workflows and publish them (live)
    .venv/bin/python workflow.py --staging      # the same as "Inky · staging main/repair": Telegram, Gmail, schedules off
    .venv/bin/python workflow.py --no-activate  # create or update, but do not publish
    .venv/bin/python workflow.py --dry-run      # only write data/n8n-main.json and data/n8n-repair.json

Main:   every 15 min -> daily cap -> 5 Apify actors -> merge -> score (inky.js + derived rules; 23:00-07:00 matches
        wait for the morning) -> one home at a time: Telegram approval -> Gmail draft (never sent).
        A webhook "Send me the best now" feeds the same questions. Plus an 08:00 digest, which also lists up to 3
        "almost" homes (new, missing exactly one rule by a little; never asked about, never drafted).
Repair: on error -> GLM-5.3 rewrites the one broken Apify input -> checks it against the actor's input schema on
        Apify -> saves it via the n8n node -> publishes it -> tells you on Telegram -> runs the main workflow again.
        A fix that fails the check is not published; you get told what GLM proposed and why. At most one fix per hour.
IDs of what it created are kept in data/n8n.json (staging: data/n8n-staging.json), so a second run updates instead
of duplicating. An update keeps the node ids, webhook ids and saved state (seen listings, counters) of the workflow.
"""
import argparse
import json
import math
import os
import re
import secrets
import unicodedata
import uuid
from collections import defaultdict
from pathlib import Path

import httpx
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("INKY_DATA", HERE / "data"))
STATE_DIR = HERE / "data"  # one record of what exists in n8n, whatever the input folder
APIFY_NODE = "@apify/n8n-nodes-apify.apify"
MODEL = "z-ai/glm-5.3"
MAX_ITEMS = 60          # newest listings per source per run
MAX_RUNS_A_DAY = 120    # 96 scheduled runs a day, plus room for re-runs after a fix
QUIET = (23, 7)         # Europe/Amsterdam: matches found in these hours wait for the morning
TECNOCASA = "cavernous_stew~inky-tecnocasa-homes"  # Inky's own actor (teach/actor)

# (step, source|city, actor, input, site in the items' URLs, (memory MB, timeout s, max $ a run)).
# The four portal actors bill per listing, not per memory, so the per-run $ caps are the real cost guard.
SOURCES = [
    ("idealista · Porto", "idealista|porto", "igolaizola~idealista-scraper",
     {"country": "pt", "location": "Porto", "operation": "sale", "propertyType": "homes", "sortBy": "mostRecent", "maxItems": MAX_ITEMS},
     "idealista.pt", (128, 120, 0.1)),
    ("idealista · Bari", "idealista|bari", "igolaizola~idealista-scraper",
     {"country": "it", "location": "Bari", "operation": "sale", "propertyType": "homes", "sortBy": "mostRecent", "maxItems": MAX_ITEMS},
     "idealista.it", (128, 120, 0.1)),
    ("immobiliare · Bari", "immobiliare|bari", "memo23~immobiliare-scraper",
     {"startUrls": ["https://www.immobiliare.it/vendita-case/bari/"], "sortBy": "mostRecent", "includeAgencyDetails": False, "maxItems": MAX_ITEMS},
     "immobiliare.it", (512, 180, 0.15)),
    ("otodom · Łódź", "otodom|lodz", "trev0n~otodom-scraper",
     {"searchType": "sprzedaz", "propertyType": "mieszkanie", "location": "lodzkie/lodz/lodz/lodz", "maxItems": MAX_ITEMS},
     "otodom.pl", (512, 240, 0.3)),
    ("tecnocasa · Bari", "tecnocasa|bari", TECNOCASA,
     {"city": "Bari", "maxPrice": 200000, "maxItems": MAX_ITEMS},
     "tecnocasa.it", (128, 60, 0.05)),
]
SCORE = "Score · rules"
LOOP = "One home at a time"
QUIET_TYPES = {"n8n-nodes-base.telegram", "n8n-nodes-base.gmail", "n8n-nodes-base.scheduleTrigger"}
SETTINGS_KEYS = ["saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
                 "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone", "executionOrder"]


def node(name, type_, version, params, pos, creds=None, **extra):
    n = {"id": str(uuid.uuid4()), "name": name, "type": type_, "typeVersion": version,
         "position": list(pos), "parameters": params, **extra}
    if creds:
        n["credentials"] = creds
    return n


def if_true(name, expr, pos):
    """n8n's IF node: output 0 when expr is true, output 1 otherwise."""
    return node(name, "n8n-nodes-base.if", 2.2, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                       "conditions": [{"id": str(uuid.uuid4()), "leftValue": expr, "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                       "combinator": "and"},
        "options": {},
    }, pos)


def note(name, text, pos, width, height, color=7):
    return node(name, "n8n-nodes-base.stickyNote", 1, {"content": text, "width": width, "height": height, "color": color}, pos)


def link(conns, a, b, index=0, out=0):
    outs = conns.setdefault(a, {"main": [[]]})["main"]
    while len(outs) <= out:
        outs.append([])
    outs[out].append({"node": b, "type": "main", "index": index})


# ---- JavaScript shared by the Code nodes (plain strings: no Python formatting inside) ----

COMMON_JS = r"""
// Saved between runs in n8n's static data: seen listings, counters, homes held for the morning.
function inkyState() {
  const s = $getWorkflowStaticData('global');
  s.seen = s.seen || {};
  s.flats = s.flats || {};
  s.held = s.held || [];
  s.almost = s.almost || [];
  s.stats = s.stats || { runs: 0, checked: 0, fresh: 0, matches: 0, since: new Date().toISOString() };
  // Counters since the last digest. The first time, they start from everything so far.
  s.night = s.night || { runs: s.stats.runs, checked: s.stats.checked, fresh: s.stats.fresh, matches: s.stats.matches, fixes: 0, since: s.stats.since };
  return s;
}
const hourNow = () => +new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Amsterdam', hour: '2-digit', hourCycle: 'h23' }).format(new Date());
const dayNow = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Amsterdam' }).format(new Date());
// Telegram reads messages as Markdown: a * or _ in a listing title must not break the message.
const md = (t) => String(t ?? '').replace(/[_*`\[]/g, '\\$&');
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
"""

TEXTS_JS = r"""
const LETTER = {
  PT: (u) => `Olá! O apartamento ainda está disponível? Gostaria de marcar uma visita.\n\n${u}`,
  IT: (u) => `Buongiorno, l'appartamento è ancora disponibile? Vorrei fissare una visita.\n\n${u}`,
  PL: (u) => `Dzień dobry, czy mieszkanie jest nadal dostępne? Chciałbym umówić się na oglądanie.\n\n${u}`,
  EN: (u) => `Hello, is the apartment still available? I would like to arrange a viewing.\n\n${u}`,
};
// The Telegram question and the Gmail draft for one home.
function texts(s, label, i, n) {
  return {
    telegram_text: `${label}${n > 1 ? ` ${i + 1} of ${n}` : ''} · ${md(s.city)} · ${md(s.zone)}\n${md(s.title)}\n` +
      `€${Math.round(s.price_eur).toLocaleString('en')} · ${s.size_m2 ?? '?'} m² · ${s.bedrooms ?? '?'} bed\n` +
      `${s.net_yield}% a year after costs${s.gross_yield != null ? ` (${s.gross_yield}% before)` : ''}\n` +
      (s.passed && s.passed.length ? `Passed ${s.passed.join(' ')}\n` : '') +
      `${md(s.url)}\n\nSave a Gmail draft to the agent? Nothing is sent.`,
    email_subject: `${s.title || 'Apartment'} · ${s.zone}`,
    email_body: (LETTER[s.country] || LETTER.EN)(s.url),
  };
}
"""

SCORE_JS = r"""
const state = inkyState();
// "Almost": a new home that misses exactly one rule, by a little. Never asked about, only listed in the 08:00 digest.
// "A little" depends on the field: percentages (yields, the price trend) 0.3 points, about the error of a rent
// estimate from a neighbourhood median; the price against the neighbourhood 0.05; money and counts 5% of the
// threshold (EUR 185,000 -> up to 194,250, about what a seller gives in a negotiation). A list rule (city, bedrooms)
// has no "a little", so a miss there never counts.
const ALMOST = { net_yield: 0.3, gross_yield: 0.3, price_trend: 0.3, price_vs_zone: 0.05 };
function almost(s) {
  const r = s.failed.length === 1 && RULES.find((x) => x.id === s.failed[0]);
  const v = r && s[r.field];
  if (!r || !['<=', '>='].includes(r.op) || typeof v !== 'number') return null;
  const by = +Math.abs(v - r.value).toFixed(2);
  if (by > (ALMOST[r.field] ?? Math.abs(r.value) * 0.05)) return null;
  const unit = r.field === 'price_eur' ? `€${by.toLocaleString('en')}` : /yield|trend/.test(r.field) ? `${by} points` : by;
  return { title: s.title, city: s.city, zone: s.zone, price_eur: s.price_eur, net_yield: s.net_yield, url: s.url,
    rule: r.id, by, miss: `misses ${r.id} (${r.field} ${r.op} ${r.value}) by ${unit}` };
}
const siteOf = (item) => { const t = JSON.stringify(item); return Object.keys(SITES).find((k) => t.includes(SITES[k])); };
const read = {};  // per step: [items, items Inky could read]
const listings = [];
for (const { json: item } of $input.all()) {
  const l = normalize(item, PLN_PER_EUR, { op: 'sale', near: ZONE_NEAR });
  const k = l ? `${l.source}|${l.city}` : siteOf(item);
  if (k) {
    read[k] = read[k] || [0, 0];
    read[k][0]++;
    if (l) read[k][1]++;
  }
  if (l) listings.push(l);
}
// A site that changed its format: most of its items no longer read. The repair workflow takes it from here.
for (const [k, [n, ok]] of Object.entries(read)) {
  if (STEPS[k] && n >= 4 && ok * 2 < n) throw new Error(`Step ${STEPS[k]} returned items Inky can't read`);
}
const empty = Object.keys(STEPS).filter((k) => !(read[k] && read[k][1]));
if (empty.length) throw new Error(`Step ${STEPS[empty[0]]} returned 0 homes`);

const now = Date.now();
const found = [], near = [];
for (const l of listings) {
  state.stats.checked++;
  state.night.checked++;
  const key = `${l.source}:${l.id}`;
  if (state.seen[key]) continue;
  state.seen[key] = now;
  // The same flat on two sites counts once: same city, price and size.
  const flat = `${l.city}|${l.price_eur}|${Math.round(l.size_m2)}`;
  if (state.flats[flat]) continue;
  state.flats[flat] = now;
  state.stats.fresh++;
  state.night.fresh++;
  const s = score(l, RULES, ZONES, COSTS);
  const a = s.match ? null : almost(s);
  if (s.match) found.push(s);
  if (a) near.push(a);
}
// Only new homes get here, so a near miss is listed once. The digest shows the best 3 since the last one.
state.almost = [...state.almost, ...near].sort((a, b) => b.net_yield - a.net_yield).slice(0, 3);
state.stats.runs++;
state.night.runs++;
state.stats.matches += found.length;
state.night.matches += found.length;
for (const s of found) {
  if (!state.best || s.net_yield > state.best.net_yield) state.best = { title: s.title, city: s.city, zone: s.zone, net_yield: s.net_yield, url: s.url };
}

// Quiet hours: hold what was found, the first run after 07:00 asks.
const h = hourNow();
if (h >= QUIET[0] || h < QUIET[1]) {
  state.held.push(...found);
  return [];
}
// At most 3 questions per run, best first; the rest wait for the next run.
const all = [...state.held, ...found].sort((a, b) => b.net_yield - a.net_yield);
state.held = all.slice(3);
const ask = all.slice(0, 3);
return ask.map((s, i) => ({ json: { ...s, ...texts(s, 'New match', i, ask.length) } }));
"""

CAP_JS = r"""
// At most MAX_RUNS runs a day, so Apify spend has a ceiling. Over it, this run stops here and Apify is not called.
const state = inkyState();
const day = dayNow();
if (!state.day || state.day.date !== day) state.day = { date: day, runs: 0, skipped: 0 };
if ($('Run again after a fix').isExecuted) state.night.fixes++;
if (state.day.runs >= MAX_RUNS) {
  state.day.skipped++;
  return [];
}
state.day.runs++;
return [{ json: { day, run: state.day.runs, cap: MAX_RUNS } }];
"""

DIGEST_JS = r"""
const s = inkyState();
const n = s.night;
const lines = [`Good morning. While you slept: ${plural(n.runs, 'run', 'runs')} · ${n.checked.toLocaleString('en')} listings checked · ` +
  `${n.fresh} new · ${plural(n.matches, 'match', 'matches')} · ${plural(n.fixes, 'fix', 'fixes')}`];
for (const m of s.held.slice(0, 3)) lines.push(`Waiting for you: ${md(m.title)} · ${md(m.zone)} · ${m.net_yield}% after costs`);
for (const a of s.almost) lines.push(`Almost: ${md(a.miss)} · ${md(a.title)} · ${md(a.zone)} · ${a.net_yield}% after costs\n${md(a.url)}`);
const best = [s.best, BEST].filter(Boolean).sort((a, b) => b.net_yield - a.net_yield)[0];
if (!n.matches && best) lines.push(`Best home right now: ${md(best.title)}, ${md(best.zone)}, ${best.net_yield}% after costs\n${md(best.url)}`);
s.night = { runs: 0, checked: 0, fresh: 0, matches: 0, fixes: 0, since: new Date().toISOString() };
s.almost = [];
return [{ json: { text: lines.join('\n') } }];
"""

BEST_JS = r"""
// The app sends the best homes it knows: POST {"matches": [{title, city, zone, price_eur, size_m2, bedrooms, net_yield, url, country}]}.
// They get the same question as a new match, best first, at most 3.
const body = $input.first().json.body || {};
const num = (v) => (v === null || v === undefined || v === '' || !Number.isFinite(+v) ? null : +v);
const text = (v, n) => String(v ?? '').slice(0, n);
const homes = (Array.isArray(body.matches) ? body.matches : [])
  .filter((m) => m && typeof m.url === 'string' && /^https:\/\//.test(m.url) && num(m.price_eur))
  .map((m) => ({ title: text(m.title, 160), city: text(m.city, 40), zone: text(m.zone, 80), country: text(m.country, 2).toUpperCase(),
    price_eur: num(m.price_eur), size_m2: num(m.size_m2), bedrooms: num(m.bedrooms), net_yield: num(m.net_yield),
    gross_yield: num(m.gross_yield), url: text(m.url, 500) }))
  .sort((a, b) => (b.net_yield ?? 0) - (a.net_yield ?? 0))
  .slice(0, 3);
return homes.map((s, i) => ({ json: { ...s, ...texts(s, 'Best so far', i, homes.length) } }));
"""

CHECK_JS = r"""
// GLM's input against the actor's own input schema (its default build, read from Apify just now), before anything
// is saved: a required field missing (with no default), a value outside the allowed list, a wrong type, or a field
// the actor doesn't have that the fix added. Anything wrong, or no schema to check against: not published.
const patch = $('Patch the step').first().json;
const build = $json.data || {};
let schema = build.actorDefinition?.input;
try { schema = schema || JSON.parse(build.inputSchema); } catch (e) {}
const props = schema?.properties || {};
const input = patch.input;
const TYPES = { string: (v) => typeof v === 'string', integer: Number.isInteger, number: Number.isFinite, boolean: (v) => typeof v === 'boolean',
  array: Array.isArray, object: (v) => v !== null && typeof v === 'object' && !Array.isArray(v) };
const problems = [];
if (!schema) problems.push(`Apify gave no input schema for ${patch.actor}${$json.error ? ` (${$json.error.message || $json.error})` : ''}`);
for (const k of schema?.required || []) if (input[k] == null && !('default' in (props[k] || {}))) problems.push(`${k} is required`);
for (const [k, v] of Object.entries(input)) {
  const p = props[k];
  if (!p) {
    if (schema && !(k in patch.before)) problems.push(`${k} is not an input field of ${patch.actor}`);
  } else if (v === null) {
    if (!p.nullable) problems.push(`${k} can't be empty`);
  } else if (TYPES[p.type] && !TYPES[p.type](v)) {
    problems.push(`${k} must be of type ${p.type}, not ${JSON.stringify(v)}`);
  } else if (p.enum && !p.enum.includes(v)) {
    problems.push(`${k} can't be ${JSON.stringify(v)}, only ${p.enum.join(', ')}`);
  } else if (Array.isArray(v) && p.items?.enum && v.some((x) => !p.items.enum.includes(x))) {
    problems.push(`${k} may only hold ${p.items.enum.join(', ')}`);
  }
}
const esc = (t) => String(t).replace(/[_*`\[]/g, '\\$&');
const proposed = JSON.stringify(input);
return [{ json: { ...patch, ok: !problems.length, problems, text: problems.length ? esc(`Inky did not publish the fix for ${patch.step}: ` +
  `${problems.join('; ')}. GLM proposed (${patch.change}): ${proposed.length > 600 ? proposed.slice(0, 600) + '…' : proposed}. ` +
  'The step is unchanged; at most one fix an hour, so a human decides.') : null } }];
"""

KEEP_JS = f"""
// Your answer, next to the home it was about (the loop holds one home at a time, from either branch).
// No answer within 24 hours, or Telegram switched off, counts as "no".
return $input.all().map((it, i) => ({{ json: {{ ...$('{LOOP}').itemMatching(i).json, approved: it.json.data?.approved === true }} }}));
"""


def js_const(name, value):
    return f"const {name} = {json.dumps(value, ensure_ascii=False)};\n"


def score_code(rules, zones, costs, pln, near=None):
    program = (HERE / "inky.js").read_text().split("// ---- end of compiled program")[0]
    return (program + "\n// Compiled by Inky from the research run. No model runs here.\n"
            + js_const("RULES", rules) + js_const("ZONES", zones) + js_const("COSTS", costs) + js_const("PLN_PER_EUR", pln)
            + js_const("STEPS", {key: name for name, key, *_ in SOURCES}) + js_const("SITES", {key: site for _, key, _, _, site, _ in SOURCES})
            + js_const("ZONE_NEAR", near or {}) + js_const("QUIET", list(QUIET)) + COMMON_JS + TEXTS_JS + SCORE_JS)


def apify_step(name, actor, body, creds, pos, mode, limits):
    """The official Apify node when it is installed in n8n, otherwise n8n's HTTP node on Apify's API."""
    memory, timeout, usd = limits
    text = json.dumps(body, ensure_ascii=False, indent=2)
    if mode == "node":
        return node(name, APIFY_NODE, 1, {
            "authentication": "apifyApi", "resource": "Actors", "operation": "Run actor and get dataset",
            "actorId": {"__rl": True, "value": actor, "mode": "id"}, "customBody": text,
            "memory": memory, "timeout": timeout, "maxTotalChargeUsd": usd,
        }, pos, {"apifyApi": creds["apify"]})
    return node(name, "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendQuery": True, "queryParameters": {"parameters": [
            {"name": "maxTotalChargeUsd", "value": str(usd)}, {"name": "timeout", "value": str(timeout)}, {"name": "memory", "value": str(memory)}]},
        "sendBody": True, "specifyBody": "json", "jsonBody": text, "options": {"timeout": 300000},
    }, pos, {"httpHeaderAuth": creds["apify"]})


def main_workflow(rules, zones, costs, pln, creds, chat_id, repair_id=None, mode="node", best_path=None, near=None, best=None):
    """The main workflow. best_path, near and best default to what data/ holds (see deploy)."""
    if best_path is None:
        best_path = load_state().get("best_path") or secrets.token_hex(16)
    if near is None:
        near = zone_near(zones)
    if best is None:
        best = best_home()
    budget = next((r["value"] for r in rules if r.get("field") == "price_eur" and r.get("op") == "<="), None)
    nodes, conns = [], {}
    add = lambda n: nodes.append(n) or n["name"]
    every = add(node("Every 15 min", "n8n-nodes-base.scheduleTrigger", 1.2,
                     {"rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}}, (0, 260)))
    again = add(node("Run again after a fix", "n8n-nodes-base.executeWorkflowTrigger", 1.1,
                     {"inputSource": "passthrough"}, (0, 460)))
    cap = add(node("Under the daily cap", "n8n-nodes-base.code", 2,
                   {"jsCode": js_const("MAX_RUNS", MAX_RUNS_A_DAY) + COMMON_JS + CAP_JS}, (220, 360)))
    link(conns, every, cap)
    link(conns, again, cap)
    merge = add(node("Merge", "n8n-nodes-base.merge", 3, {"numberInputs": len(SOURCES)}, (680, 360)))
    for i, (name, _, actor, body, _, limits) in enumerate(SOURCES):
        if actor == TECNOCASA and budget:
            body = {**body, "maxPrice": budget}
        add(apify_step(name, actor, body, creds, (440, 80 + i * 140), mode, limits))
        link(conns, cap, name)
        link(conns, name, merge, i)
    score = add(node(SCORE, "n8n-nodes-base.code", 2, {"jsCode": score_code(rules, zones, costs, pln, near)}, (900, 360)))
    link(conns, merge, score)
    webhook = add(node("Send me the best now", "n8n-nodes-base.webhook", 2,
                       {"httpMethod": "POST", "path": best_path, "responseMode": "onReceived", "options": {}},
                       (680, 760), webhookId=str(uuid.uuid4())))
    best_so_far = add(node("Best so far", "n8n-nodes-base.code", 2, {"jsCode": COMMON_JS + TEXTS_JS + BEST_JS}, (900, 760)))
    link(conns, webhook, best_so_far)
    loop = add(node(LOOP, "n8n-nodes-base.splitInBatches", 3, {"batchSize": 1, "options": {}}, (1140, 360)))
    link(conns, score, loop)
    link(conns, best_so_far, loop)
    ask = add(node("Ask me on Telegram", "n8n-nodes-base.telegram", 1.2, {
        "operation": "sendAndWait", "chatId": chat_id, "message": "={{ $json.telegram_text }}",
        "responseType": "approval",
        "approvalOptions": {"values": {"approvalType": "double", "approveLabel": "Save as draft", "disapproveLabel": "Skip"}},
        "options": {"limitWaitTime": {"values": {"limitType": "afterTimeInterval", "resumeAmount": 24, "resumeUnit": "hours"}},
                    "appendAttribution": False},
    }, (1360, 360), {"telegramApi": creds["telegram"]}, webhookId=str(uuid.uuid4())))
    link(conns, loop, ask, out=1)  # output 0 is "done", output 1 is the next home
    keep = add(node("Keep approved", "n8n-nodes-base.code", 2, {"jsCode": KEEP_JS}, (1580, 360)))
    link(conns, ask, keep)
    approved = add(if_true("Approved?", "={{ $json.approved }}", (1800, 360)))
    link(conns, keep, approved)
    gmail_creds = {"gmailOAuth2": creds["gmail"]} if creds.get("gmail") else None
    draft = add(node("Gmail draft to the agent", "n8n-nodes-base.gmail", 2.1, {
        "resource": "draft", "operation": "create", "subject": "={{ $json.email_subject }}",
        "emailType": "text", "message": "={{ $json.email_body }}", "options": {},
    }, (2040, 260), gmail_creds, **({} if gmail_creds else {"disabled": True})))  # paused until a Gmail credential exists
    link(conns, approved, draft)
    link(conns, draft, loop)
    link(conns, approved, loop, out=1)
    morning = add(node("Every day 08:00", "n8n-nodes-base.scheduleTrigger", 1.2,
                       {"rule": {"interval": [{"field": "cronExpression", "expression": "0 8 * * *"}]}}, (0, 1040)))
    digest = add(node("Digest", "n8n-nodes-base.code", 2, {"jsCode": js_const("BEST", best) + COMMON_JS + DIGEST_JS}, (220, 1040)))
    send = add(node("Send the digest", "n8n-nodes-base.telegram", 1.2, {
        "chatId": chat_id, "text": "={{ $json.text }}", "additionalFields": {"appendAttribution": False},
    }, (440, 1040), {"telegramApi": creds["telegram"]}))
    link(conns, morning, digest)
    link(conns, digest, send)
    sites = len(SOURCES)
    nodes += [
        note("Note · Read", f"## 1 · Read\n{sites} sites through Apify, every 15 minutes: up to {MAX_ITEMS} homes for sale on each, newest first where the site allows. "
             f"At most {MAX_RUNS_A_DAY} runs a day.", (-60, -120), 640, 900, 5),
        note("Note · Score", "## 2 · Score\nInky's compiled rules, no AI. Only new homes; the same flat on two sites counts once. "
             "23:00-07:00 matches wait for the morning.", (640, 160), 400, 360, 6),
        note("Note · Ask", "## 3 · Ask\nTelegram, one home at a time. It waits for your tap, at most 24 hours.", (1100, 160), 860, 360, 4),
        note("Note · Draft", "## 4 · Draft\nGmail, never sent. You read it and send it yourself.", (2000, 100), 260, 380, 3),
        note("Note · Best now", "## Send me the best now\nThe Inky app posts its top 3 homes here. They get the same question.", (640, 600), 400, 320, 4),
        note("Note · Digest", "## Every morning\n08:00 on Telegram: what happened while you slept.", (-60, 880), 640, 320, 7),
    ]
    settings = {"executionOrder": "v1", "timezone": "Europe/Amsterdam", "saveManualExecutions": True}
    if repair_id:
        settings["errorWorkflow"] = repair_id
    return {"name": "Inky · Buy-to-let abroad", "nodes": nodes, "connections": conns, "settings": settings}


def repair_workflow(main_id, creds, chat_id, schemas):
    nodes, conns = [], {}
    add = lambda n: nodes.append(n) or n["name"]
    tg = {"telegramApi": creds["telegram"]}
    n8n = {"n8nApi": creds["n8n"]}
    on_error = add(node("On error", "n8n-nodes-base.errorTrigger", 1, {}, (0, 400)))
    broke = add(node("Tell me it broke", "n8n-nodes-base.telegram", 1.2, {
        "chatId": chat_id, "additionalFields": {"appendAttribution": False},
        "text": r"={{ 'Inky hit an error in ' + $json.name + ': ' + ($json.error || '?').replace(/[_*\x60\[]/g, '\\$&') + '. Trying to fix one step.' }}",
    }, (500, 160), tg))
    read = add(node("Read the error", "n8n-nodes-base.code", 2, {"jsCode": """
const e = $json.execution || {};
const msg = e.error?.message || '';
// "returned 0 homes": an empty result. "returned items Inky can't read": the site changed its format.
const m = msg.match(/Step (.+?) returned (?:0 homes|items Inky can't read)/);
const state = $getWorkflowStaticData('global');
state.fixes = (state.fixes || []).filter((t) => Date.now() - t < 3600e3);
if (state.fixes.length) return [];  // safety limit: one message and one fix per hour, then a human decides
state.fixes.push(Date.now());
return [{ json: { workflowId: $json.workflow.id, name: $json.workflow.name, step: m ? m[1] : e.lastNodeExecuted, error: msg } }];
"""}, (260, 400)))
    get = add(node("Get the workflow", "n8n-nodes-base.n8n", 1, {
        "resource": "workflow", "operation": "get",
        "workflowId": {"__rl": True, "value": "={{ $json.workflowId }}", "mode": "id"},
    }, (500, 400), n8n))
    pick = add(node("Pick the broken step", "n8n-nodes-base.code", 2, {"jsCode": f"""
const SCHEMAS = {json.dumps(schemas, ensure_ascii=False)};
const err = $('Read the error').first().json;
const wf = $json;
const step = wf.nodes.find((n) => n.name === err.step);
const key = step && ['customBody', 'jsonBody'].find((k) => typeof step.parameters?.[k] === 'string');
if (!key) throw new Error(`Cannot repair step ${{err.step}}`);
const actor = step.parameters.actorId?.value || (step.parameters.url || '').split('/acts/')[1]?.split('/')[0];
return [{{ json: {{ wf, step: err.step, key, actor, before: step.parameters[key], body: {{
  model: '{MODEL}',
  response_format: {{ type: 'json_object' }},
  messages: [
    {{ role: 'system', content: 'You repair one step of a scraping workflow. The step runs an Apify actor with a JSON input. ' +
      'It failed. Return JSON {{"input": <the corrected actor input>, "change": "<one short sentence>"}}. Change as little as possible.' }},
    {{ role: 'user', content: JSON.stringify({{ step: err.step, actor, error: err.error, input: JSON.parse(step.parameters[key]), input_fields: SCHEMAS[actor] || {{}} }}) }},
  ],
}} }} }}];
"""}, (740, 400)))
    fix = add(node("GLM-5.3 fixes one step", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": "https://openrouter.ai/api/v1/chat/completions",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.body) }}", "options": {},
    }, (980, 400), {"httpHeaderAuth": creds["openrouter"]}))
    patch = add(node("Patch the step", "n8n-nodes-base.code", 2, {"jsCode": f"""
const pick = $('Pick the broken step').first().json;
const text = $json.choices[0].message.content;
const answer = JSON.parse(text.slice(text.indexOf('{{'), text.lastIndexOf('}}') + 1));
if (!answer.input || typeof answer.input !== 'object') throw new Error('GLM returned no input');
const wf = pick.wf;
const step = wf.nodes.find((n) => n.name === pick.step);
step.parameters[pick.key] = JSON.stringify(answer.input, null, 2);
const keep = {json.dumps(SETTINGS_KEYS)};
const settings = Object.fromEntries(Object.entries(wf.settings || {{}}).filter(([k]) => keep.includes(k)));
return [{{ json: {{ workflowId: wf.id, step: pick.step, change: answer.change || 'input updated', actor: pick.actor,
  input: answer.input, before: JSON.parse(pick.before), workflow: {{ name: wf.name, nodes: wf.nodes, connections: wf.connections, settings }} }} }}];
"""}, (1220, 400)))
    # The actor's input schema, from its default build (the one a run uses), with the Apify credential the steps use.
    apify = creds["apify"]
    auth = ({"authentication": "predefinedCredentialType", "nodeCredentialType": "apifyApi"}, {"apifyApi": apify}) \
        if apify.get("type") == "apifyApi" else ({"authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth"}, {"httpHeaderAuth": apify})
    fields = add(node("Read the actor's input schema", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "GET", "url": "=https://api.apify.com/v2/acts/{{ $json.actor }}/builds/default", **auth[0], "options": {},
    }, (1460, 400), auth[1], onError="continueRegularOutput"))  # no schema: the check below rejects the fix
    check = add(node("Check the fix", "n8n-nodes-base.code", 2, {"jsCode": CHECK_JS}, (1700, 400)))
    valid = add(if_true("Fix checks out?", "={{ $json.ok }}", (1940, 400)))
    rejected = add(node("Tell me the fix was rejected", "n8n-nodes-base.telegram", 1.2, {
        "chatId": chat_id, "text": "={{ $json.text }}", "additionalFields": {"appendAttribution": False},
    }, (2180, 160), tg))
    save = add(node("Save the fix", "n8n-nodes-base.n8n", 1, {
        "resource": "workflow", "operation": "update",
        "workflowId": {"__rl": True, "value": "={{ $json.workflowId }}", "mode": "id"},
        "workflowObject": "={{ JSON.stringify($json.workflow) }}",
    }, (2180, 400), n8n))
    publish = add(node("Publish the fix", "n8n-nodes-base.n8n", 1, {
        "resource": "workflow", "operation": "activate",
        "workflowId": {"__rl": True, "value": "={{ $('Patch the step').first().json.workflowId }}", "mode": "id"},
    }, (2420, 400), n8n))
    told = add(node("Tell me it's fixed", "n8n-nodes-base.telegram", 1.2, {
        "chatId": chat_id, "additionalFields": {"appendAttribution": False},
        "text": r"={{ ('Fixed ' + $('Patch the step').first().json.step + ': ' + $('Patch the step').first().json.change).replace(/[_*\x60\[]/g, '\\$&') + '. Running it again now.' }}",
    }, (2660, 400), tg))
    rerun = add(node("Run it again", "n8n-nodes-base.executeWorkflow", 1.2, {
        "source": "database", "workflowId": {"__rl": True, "value": main_id, "mode": "id"},
        "options": {"waitForSubWorkflow": False},
    }, (2900, 400)))
    for a, b in [(on_error, read), (read, broke), (read, get), (get, pick), (pick, fix), (fix, patch), (patch, fields), (fields, check),
                 (check, valid), (valid, save), (save, publish), (publish, told), (told, rerun)]:
        link(conns, a, b)
    link(conns, valid, rejected, out=1)
    nodes.append(note("Note · Repair", "## Repair\nFixes one broken step, at most once an hour. GLM-5.3 rewrites only that step's Apify input; "
                      "the fix is checked against the actor's input schema on Apify, then saved and published, you get told on Telegram, "
                      "and the run starts again. A fix that fails the check is not published: you get told what GLM proposed and why.",
                      (-60, -20), 3200, 580, 2))
    return {"name": "Inky · repair one step", "nodes": nodes, "connections": conns,
            "settings": {"executionOrder": "v1", "timezone": "Europe/Amsterdam"}}


def stage(wf, name):
    """A staging copy: its own name, and nothing in it can message you, write a draft, run on a clock or start other runs."""
    wf["name"] = name
    for n in wf["nodes"]:
        if n["type"] in QUIET_TYPES or n["name"] == "Run it again":
            n["disabled"] = True
    wf["nodes"].append(note("Note · Staging", "## Staging copy\nTelegram, Gmail, the schedules and re-runs are switched off.", (0, -320), 520, 160, 3))
    return wf


def place(s):
    """The same key as cityKey() in inky.js, with single spaces."""
    s = str(s or "").replace("Ł", "l").replace("ł", "l")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not "̀" <= c <= "ͯ")
    return " ".join(s.lower().split())


def zone_near(zones, raw=None, cities=None):
    """{city: {place name: nearest neighbourhood with rent data}}, from where geolocated sale listings say each place is.

    Tecnocasa names quarters the rent data does not have ("Carrassi Chiesa Russa", "Madonnella"). idealista and
    immobiliare listings carry coordinates plus their neighbourhood, district, macro- and microzone names, so each
    name gets a centroid; every name then maps to the rent neighbourhood whose centroid is nearest.
    """
    raw = Path(raw or DATA / "raw")
    cities = cities or {key.split("|")[1] for _, key, actor, *_ in SOURCES if actor == TECNOCASA}
    exact, parts = defaultdict(list), defaultdict(list)
    for f in sorted(raw.glob("*-sale-*.json")):
        city = f.name.split("-")[0]
        if city not in cities:
            continue
        for it in json.loads(f.read_text()):
            if "propertyCode" in it:
                lat, lon, names = it.get("latitude"), it.get("longitude"), [it.get("neighborhood"), it.get("district")]
            elif isinstance(it.get("geography"), dict):
                g = it["geography"]
                loc = g.get("geolocation") or {}
                lat, lon, names = loc.get("latitude"), loc.get("longitude"), [(g.get(k) or {}).get("name") for k in ("macrozone", "microzone")]
            else:
                continue
            if lat is None or lon is None:
                continue
            for name in filter(None, names):
                exact[(city, place(name))].append((lat, lon))
                for p in re.split(r"\s*[,\-–/]\s*", name):
                    if place(p):
                        parts[(city, place(p))].append((lat, lon))
    mean = lambda pts: (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    centre = {k: mean(v) for k, v in parts.items() if len(v) >= 3}
    centre.update({k: mean(v) for k, v in exact.items() if len(v) >= 3})  # a name's own listings beat its parts
    out = {}
    for city in cities:
        rent = {z["zone"]: centre.get((city, place(z["zone"]))) for z in zones.values() if z.get("city") == city and z.get("rent_m2")}
        table = {place(z): z for z in rent}
        targets = [(z, c) for z, c in rent.items() if c]
        for (c, k), (lat, lon) in centre.items():
            if c != city or k in table or not targets:
                continue
            dist = lambda t: math.hypot((t[1][0] - lat) * 111, (t[1][1] - lon) * 111 * math.cos(math.radians(lat)))
            table[k] = min(targets, key=dist)[0]
        if table:
            out[city] = dict(sorted(table.items()))
    return out


def best_home(research=None):
    """The best match of the research run, for the digest on a night with nothing new."""
    if research is None:
        f = DATA / "research.json"
        research = json.loads(f.read_text()) if f.exists() else {}
    m = (research.get("matches") or [None])[0]
    return {k: m.get(k) for k in ("title", "city", "zone", "net_yield", "url")} if m else None


def actor_schemas():
    """Input field names per actor, from the Apify API, so GLM repairs with real field names."""
    out = {}
    headers = {"Authorization": f"Bearer {os.environ['APIFY_TOKEN']}"} if os.environ.get("APIFY_TOKEN") else {}
    for _, _, actor, *_ in SOURCES:
        if actor in out:
            continue
        try:
            a = httpx.get(f"https://api.apify.com/v2/acts/{actor}", headers=headers, timeout=20).json()["data"]
            b = httpx.get(f"https://api.apify.com/v2/actor-builds/{a['taggedBuilds']['latest']['buildId']}", headers=headers, timeout=20).json()["data"]
            props = b["actorDefinition"]["input"]["properties"]
            out[actor] = {k: {"type": v.get("type"), **({"enum": v["enum"][:12]} if v.get("enum") else {})} for k, v in props.items()}
        except Exception:  # GLM then repairs without the field list
            pass
    return out


class N8n:
    def __init__(self, base=None, key=None):
        self.base = (base or os.environ["N8N_BASE_URL"]).rstrip("/")
        self.http = httpx.Client(base_url=f"{self.base}/api/v1", headers={"X-N8N-API-KEY": key or os.environ["N8N_API_KEY"]}, timeout=60)

    def call(self, method, path, **kw):
        r = self.http.request(method, path, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"n8n {method} {path}: {r.status_code} {r.text[:400]}")
        return r.json() if r.content else {}

    def has_type(self, type_):
        return self.http.get(f"/credentials/schema/{type_}").status_code == 200

    def get(self, wid):
        """The workflow, or None when it no longer exists in n8n."""
        if not wid:
            return None
        r = self.http.get(f"/workflows/{wid}")
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise RuntimeError(f"n8n GET /workflows/{wid}: {r.status_code} {r.text[:400]}")
        return r.json()

    def credential(self, state, role, type_, name, data):
        if role in state["credentials"]:
            return state["credentials"][role]
        c = self.call("POST", "/credentials", json={"name": name, "type": type_, "data": data})
        state["credentials"][role] = {"id": c["id"], "name": c["name"], "type": type_}
        return state["credentials"][role]

    def upsert(self, state, key, wf):
        """Create, or update in place keeping node ids, webhook ids (open Telegram questions) and static data."""
        cur = self.get(state.get(key))
        if not cur:
            state[key] = self.call("POST", "/workflows", json=wf)["id"]
            return state[key]
        keep_ids(wf, cur)
        self.call("PUT", f"/workflows/{state[key]}", json=wf)
        # n8n keeps the saved state when an update leaves staticData out. Check, and put it back if it did not.
        saved = cur.get("staticData")
        if saved and not (self.get(state[key]) or {}).get("staticData"):
            self.call("PUT", f"/workflows/{state[key]}", json={**wf, "staticData": saved})
        return state[key]

    def tag(self, wid, name="inky"):
        tags = self.call("GET", "/tags", params={"limit": 100}).get("data", [])
        t = next((t for t in tags if t["name"] == name), None) or self.call("POST", "/tags", json={"name": name})
        have = [{"id": x["id"]} for x in self.call("GET", f"/workflows/{wid}/tags")]
        if {"id": t["id"]} not in have:
            self.call("PUT", f"/workflows/{wid}/tags", json=have + [{"id": t["id"]}])


def keep_ids(wf, cur):
    """Same node ids and webhook ids as the workflow in n8n, matched by node name."""
    live = {n["name"]: n for n in cur.get("nodes", [])}
    for n in wf["nodes"]:
        if n["name"] in live:
            n["id"] = live[n["name"]]["id"]
            if live[n["name"]].get("webhookId"):
                n["webhookId"] = live[n["name"]]["webhookId"]


def state_file(staging=False):
    return STATE_DIR / ("n8n-staging.json" if staging else "n8n.json")


def load_state(staging=False):
    f = state_file(staging)
    state = json.loads(f.read_text()) if f.exists() else {}
    state.setdefault("credentials", {})
    if staging:  # staging uses the live credentials (read only) and keeps everything else to itself
        live = json.loads(state_file().read_text()) if state_file().exists() else {}
        state["credentials"] = {**live.get("credentials", {}), **state["credentials"]}
    return state


def save_state(state, staging=False):
    state_file(staging).write_text(json.dumps(state, indent=1))


def best_now_url(staging=False):
    """The production URL of the "Send me the best now" webhook, or None before the first deploy."""
    load_dotenv(HERE / ".env")
    path = load_state(staging).get("best_path")
    base = os.environ.get("N8N_BASE_URL", "").rstrip("/")
    return f"{base}/webhook/{path}" if path and base else None


def chat_id(cur=None):
    if os.environ.get("TELEGRAM_CHAT_ID"):
        return os.environ["TELEGRAM_CHAT_ID"]
    ask = next((n for n in (cur or {}).get("nodes", []) if n["name"] == "Ask me on Telegram"), None)
    if ask and ask["parameters"].get("chatId"):
        return ask["parameters"]["chatId"]
    t = os.environ["TELEGRAM_BOT_TOKEN"]
    updates = httpx.get(f"https://api.telegram.org/bot{t}/getUpdates", timeout=20).json().get("result", [])
    ids = [u["message"]["chat"]["id"] for u in updates if "message" in u]
    if not ids:
        raise RuntimeError("No Telegram chat yet: send /start to your bot, then run again.")
    return str(ids[-1])


def inputs():
    rules = json.loads((DATA / "rules.json").read_text())["final"]
    zones = json.loads((DATA / "zones.json").read_text())
    costs = json.loads((DATA / "costs.json").read_text())
    research = json.loads((DATA / "research.json").read_text())
    return rules, zones, costs, research


def deploy(progress=print, staging=False, activate=True) -> dict:
    """Credentials, both workflows (updated in place), error-workflow link, tags, publish. Reports each step."""
    say = lambda text, sub=None: progress(text, sub) if sub else progress(text)
    load_dotenv(HERE / ".env")
    rules, zones, costs, research = inputs()
    say("Read the research", f"{len(rules)} rules · {sum(1 for z in zones.values() if z.get('rent_m2'))} neighbourhoods with rent data")
    schemas = actor_schemas()
    say("Read the Apify input fields", f"{len(schemas)} of {len({s[2] for s in SOURCES})} actors")
    state = load_state(staging)
    api = N8n()
    cur = api.get(state.get("main"))
    ref = cur or (api.get(load_state().get("main")) if staging else None)  # staging reads the live chat and Gmail (read only)
    chat = chat_id(ref)
    mode = "node" if api.has_type("apifyApi") else "http"
    say("Connected to n8n", api.base + (" · Apify node" if mode == "node" else " · Apify through the HTTP node (Apify node not installed)"))
    token = os.environ["APIFY_TOKEN"]
    creds = {
        "apify": api.credential(state, f"apify-{mode}", *(("apifyApi", "Inky · Apify", {"apiKey": token}) if mode == "node"
                                                         else ("httpHeaderAuth", "Inky · Apify token", {"name": "Authorization", "value": f"Bearer {token}"}))),
        "telegram": api.credential(state, "telegram", "telegramApi", "Inky · Telegram", {"accessToken": os.environ["TELEGRAM_BOT_TOKEN"]}),
        "n8n": api.credential(state, "n8n", "n8nApi", "Inky · n8n API", {"apiKey": os.environ["N8N_API_KEY"], "baseUrl": f"{api.base}/api/v1"}),
        "openrouter": api.credential(state, "openrouter", "httpHeaderAuth", "Inky · OpenRouter", {"name": "Authorization", "value": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}),
    }
    gmail = next((n.get("credentials", {}).get("gmailOAuth2") for n in (ref or {}).get("nodes", []) if n["name"] == "Gmail draft to the agent"), None)
    if os.environ.get("N8N_GMAIL_CREDENTIAL_ID"):
        gmail = {"id": os.environ["N8N_GMAIL_CREDENTIAL_ID"], "name": "Gmail"}
    if gmail:
        creds["gmail"] = gmail
    state.setdefault("best_path", secrets.token_hex(16))  # the secret part of the "Send me the best now" URL, made once
    save_state(state, staging)
    say("Credentials ready", "Apify · Telegram · n8n · OpenRouter" + (" · Gmail" if gmail else " (Gmail drafts paused: set N8N_GMAIL_CREDENTIAL_ID)"))

    near = zone_near(zones)
    build_main = lambda repair_id: main_workflow(rules, zones, costs, research["pln_per_eur"], creds, chat, repair_id, mode,
                                                 best_path=state["best_path"], near=near, best=best_home(research))
    staged = lambda wf, name: stage(wf, name) if staging else wf
    repair_before = state.get("repair")
    main_wf = staged(build_main(repair_before), "Inky · staging main")
    api.upsert(state, "main", main_wf)
    save_state(state, staging)
    say("Updated the main workflow" if cur else "Created the main workflow",
        f"{steps(main_wf)} steps · {len(SOURCES)} Apify sources" + (" · seen listings and counters kept" if cur else ""))
    repair_wf = staged(repair_workflow(state["main"], creds, chat, schemas), "Inky · staging repair")
    api.upsert(state, "repair", repair_wf)
    save_state(state, staging)
    say("Saved the repair workflow", f"{steps(repair_wf)} steps · fixes one broken step, at most once an hour")
    if state["repair"] != repair_before:  # a new repair workflow: point the main one at it
        main_wf = staged(build_main(state["repair"]), "Inky · staging main")
        api.upsert(state, "main", main_wf)
        say("Linked the repair to the main workflow")
    for key in ("main", "repair"):
        api.tag(state[key])
    say("Tagged both workflows", "inky")
    if activate:
        try:
            api.call("POST", f"/workflows/{state['main']}/activate")
        except RuntimeError as e:
            raise RuntimeError(f"Saved, but n8n would not publish the main workflow: {e}") from e
        say("Published the main workflow", "webhook only: Telegram, Gmail, schedules off" if staging else "every 15 minutes, digest at 08:00")
        api.call("POST", f"/workflows/{state['repair']}/activate")  # n8n only runs a published error workflow
        say("Published the repair workflow", "runs when a step fails")
    return {"staging": staging, "main": state["main"], "repair": state["repair"], "mode": mode, "active": activate, "gmail": bool(gmail),
            "main_url": f"{api.base}/workflow/{state['main']}", "repair_url": f"{api.base}/workflow/{state['repair']}",
            "best_url": f"{api.base}/webhook/{state['best_path']}"}


def steps(wf):
    return sum(1 for n in wf["nodes"] if n["type"] != "n8n-nodes-base.stickyNote")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="only write the workflow JSON into the data folder")
    p.add_argument("--no-activate", action="store_true", help="create or update, but do not publish")
    p.add_argument("--staging", action="store_true", help='"Inky · staging main/repair": Telegram, Gmail and schedules off')
    args = p.parse_args()
    load_dotenv(HERE / ".env")
    if args.dry_run:
        rules, zones, costs, research = inputs()
        fake = {r: {"id": "0", "name": r} for r in ("apify", "telegram", "n8n", "openrouter", "gmail")}
        main_wf = main_workflow(rules, zones, costs, research["pln_per_eur"], fake, "0", "REPAIR_ID", best_path="BEST_PATH", best=best_home(research))
        repair_wf = repair_workflow("MAIN_ID", fake, "0", actor_schemas())
        prefix = "n8n-staging" if args.staging else "n8n"
        if args.staging:
            stage(main_wf, "Inky · staging main")
            stage(repair_wf, "Inky · staging repair")
        (DATA / f"{prefix}-main.json").write_text(json.dumps(main_wf, ensure_ascii=False, indent=1))
        (DATA / f"{prefix}-repair.json").write_text(json.dumps(repair_wf, ensure_ascii=False, indent=1))
        print(f"wrote {DATA}/{prefix}-main.json and {DATA}/{prefix}-repair.json")
        return
    try:
        out = deploy(staging=args.staging, activate=not args.no_activate)
    except RuntimeError as e:
        raise SystemExit(str(e))
    print(f"main:   {out['main_url']}\nrepair: {out['repair_url']}\n"
          f"best now: POST {{\"matches\": [...]}} to the webhook in {state_file(args.staging).name} (best_path)")


if __name__ == "__main__":
    main()
