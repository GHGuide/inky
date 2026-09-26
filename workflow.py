"""Inky writes its own n8n workflows through the n8n API.

    uv run python workflow.py            # create or update both workflows, activate the main one
    uv run python workflow.py --dry-run  # only write data/n8n-main.json and data/n8n-repair.json

Main:   every 15 min -> 4 Apify actors -> merge -> score (inky.js + derived rules) ->
        Telegram approval -> Gmail draft (never sent). Plus an 08:00 digest.
Repair: on error -> GLM-5.3 rewrites the one broken Apify input -> saves it via the n8n node ->
        tells you on Telegram -> runs the main workflow again. At most one fix per hour.
IDs of what it created are kept in data/n8n.json so a second run updates instead of duplicating.
"""
import argparse
import json
import os
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

DATA = Path(os.environ.get("INKY_DATA", "data"))
APIFY_NODE = "@apify/n8n-nodes-apify.apify"
MODEL = "z-ai/glm-5.3"

# Overnight scrape: newest sale listings only, 40 per source per run, $0.50 cap per node.
SOURCES = [
    ("idealista · Porto", "idealista|porto", "igolaizola~idealista-scraper",
     {"country": "pt", "location": "Porto", "operation": "sale", "propertyType": "homes", "sortBy": "mostRecent", "maxItems": 40}),
    ("idealista · Bari", "idealista|bari", "igolaizola~idealista-scraper",
     {"country": "it", "location": "Bari", "operation": "sale", "propertyType": "homes", "sortBy": "mostRecent", "maxItems": 40}),
    ("immobiliare · Bari", "immobiliare|bari", "memo23~immobiliare-scraper",
     {"startUrls": ["https://www.immobiliare.it/vendita-case/bari/"], "sortBy": "mostRecent", "includeAgencyDetails": False, "maxItems": 40}),
    ("otodom · Łódź", "otodom|lodz", "trev0n~otodom-scraper",
     {"searchType": "sprzedaz", "propertyType": "mieszkanie", "location": "lodzkie/lodz/lodz/lodz", "maxItems": 40}),
]
SCORE = "Score · rules"
SETTINGS_KEYS = ["saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
                 "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone", "executionOrder"]


def node(name, type_, version, params, pos, creds=None, **extra):
    n = {"id": str(uuid.uuid4()), "name": name, "type": type_, "typeVersion": version,
         "position": list(pos), "parameters": params, **extra}
    if creds:
        n["credentials"] = creds
    return n


def link(conns, a, b, index=0):
    conns.setdefault(a, {"main": [[]]})["main"][0].append({"node": b, "type": "main", "index": index})


def score_code(rules, zones, costs, pln):
    program = Path("inky.js").read_text().split("// ---- end of compiled program")[0]
    steps = {key: name for name, key, _, _ in SOURCES}
    return f"""{program}
// Compiled by Inky from the research run. No model runs here.
const RULES = {json.dumps(rules, ensure_ascii=False)};
const ZONES = {json.dumps(zones, ensure_ascii=False)};
const COSTS = {json.dumps(costs)};
const PLN_PER_EUR = {pln};
const STEPS = {json.dumps(steps, ensure_ascii=False)};
const LETTER = {{
  PT: (u) => `Olá! O apartamento ainda está disponível? Gostaria de marcar uma visita.\\n\\n${{u}}`,
  IT: (u) => `Buongiorno, l'appartamento è ancora disponibile? Vorrei fissare una visita.\\n\\n${{u}}`,
  PL: (u) => `Dzień dobry, czy mieszkanie jest nadal dostępne? Chciałbym umówić się na oglądanie.\\n\\n${{u}}`,
}};

const state = $getWorkflowStaticData('global');
state.seen = state.seen || {{}};
state.stats = state.stats || {{ runs: 0, checked: 0, fresh: 0, matches: 0, since: new Date().toISOString() }};

const listings = $input.all().map((it) => normalize(it.json, PLN_PER_EUR, {{ op: 'sale' }})).filter(Boolean);
const empty = Object.keys(STEPS).filter((k) => !listings.some((l) => `${{l.source}}|${{l.city}}` === k));
if (empty.length) throw new Error(`Step ${{STEPS[empty[0]]}} returned 0 homes`);

const matches = [];
for (const l of listings) {{
  state.stats.checked++;
  const key = `${{l.source}}:${{l.id}}`;
  if (state.seen[key]) continue;
  state.seen[key] = Date.now();
  state.stats.fresh++;
  const s = score(l, RULES, ZONES, COSTS);
  if (s.match) matches.push(s);
}}
state.stats.runs++;
state.stats.matches += matches.length;

// At most 3 questions per run, best first.
return matches.sort((a, b) => b.net_yield - a.net_yield).slice(0, 3).map((s) => ({{ json: {{
  ...s,
  telegram_text: `New match · ${{s.city}} · ${{s.zone}}\\n${{s.title || ''}}\\n€${{s.price_eur.toLocaleString('en')}} · ${{s.size_m2}} m² · ${{s.bedrooms}} bed\\n` +
    `${{s.net_yield}}% a year after costs (${{s.gross_yield}}% before)\\nPassed ${{s.passed.join(' ')}}\\n${{s.url}}\\n\\nSave a Gmail draft to the agent? Nothing is sent.`,
  email_subject: `${{s.title || 'Apartment'}} · ${{s.zone}}`,
  email_body: LETTER[s.country](s.url),
}} }}));
"""


def apify_step(name, actor, body, creds, pos, mode):
    """The official Apify node when it is installed in n8n, otherwise n8n's HTTP node on Apify's API."""
    text = json.dumps(body, ensure_ascii=False, indent=2)
    if mode == "node":
        return node(name, APIFY_NODE, 1, {
            "authentication": "apifyApi", "resource": "Actors", "operation": "Run actor and get dataset",
            "actorId": {"__rl": True, "value": actor, "mode": "id"}, "customBody": text, "maxTotalChargeUsd": 0.5,
        }, pos, {"apifyApi": creds["apify"]})
    return node(name, "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendQuery": True, "queryParameters": {"parameters": [{"name": "maxTotalChargeUsd", "value": "0.5"}, {"name": "timeout", "value": "280"}]},
        "sendBody": True, "specifyBody": "json", "jsonBody": text, "options": {"timeout": 300000},
    }, pos, {"httpHeaderAuth": creds["apify"]})


def main_workflow(rules, zones, costs, pln, creds, chat_id, repair_id=None, mode="node"):
    nodes, conns = [], {}
    add = lambda n: nodes.append(n) or n["name"]
    every = add(node("Every 15 min", "n8n-nodes-base.scheduleTrigger", 1.2,
                     {"rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}}, (0, 200)))
    again = add(node("Run again after a fix", "n8n-nodes-base.executeWorkflowTrigger", 1.1,
                     {"inputSource": "passthrough"}, (0, 420)))
    merge = add(node("Merge", "n8n-nodes-base.merge", 3, {"numberInputs": len(SOURCES)}, (560, 300)))
    for i, (name, _, actor, body) in enumerate(SOURCES):
        add(apify_step(name, actor, body, creds, (280, 60 + i * 160), mode))
        link(conns, every, name)
        link(conns, again, name)
        link(conns, name, merge, i)
    score = add(node(SCORE, "n8n-nodes-base.code", 2, {"jsCode": score_code(rules, zones, costs, pln)}, (800, 300)))
    link(conns, merge, score)
    ask = add(node("Ask me on Telegram", "n8n-nodes-base.telegram", 1.2, {
        "operation": "sendAndWait", "chatId": chat_id, "message": "={{ $json.telegram_text }}",
        "responseType": "approval",
        "approvalOptions": {"values": {"approvalType": "double", "approveLabel": "Save as draft", "disapproveLabel": "Skip"}},
        "options": {},
    }, (1040, 300), {"telegramApi": creds["telegram"]}, webhookId=str(uuid.uuid4())))
    link(conns, score, ask)
    keep = add(node("Keep approved", "n8n-nodes-base.code", 2, {"jsCode": (
        f"return $input.all().flatMap((it, i) => it.json.data?.approved "
        f"? [{{ json: $('{SCORE}').itemMatching(i).json }}] : []);")}, (1280, 300)))
    link(conns, ask, keep)
    gmail_creds = {"gmailOAuth2": creds["gmail"]} if creds.get("gmail") else None
    draft = add(node("Gmail draft to the agent", "n8n-nodes-base.gmail", 2.1, {
        "resource": "draft", "operation": "create", "subject": "={{ $json.email_subject }}",
        "emailType": "text", "message": "={{ $json.email_body }}", "options": {},
    }, (1520, 300), gmail_creds, **({} if gmail_creds else {"disabled": True})))  # paused until a Gmail credential exists
    link(conns, keep, draft)
    morning = add(node("Every day 08:00", "n8n-nodes-base.scheduleTrigger", 1.2,
                       {"rule": {"interval": [{"field": "cronExpression", "expression": "0 8 * * *"}]}}, (0, 760)))
    digest = add(node("Digest", "n8n-nodes-base.code", 2, {"jsCode": (
        "const s = $getWorkflowStaticData('global').stats || { runs: 0, checked: 0, matches: 0 };\n"
        "return [{ json: { text: `Good morning. While you slept:\\n${s.matches} homes match your plan\\n"
        "${s.runs} runs · ${s.checked.toLocaleString('en')} listings checked` } }];")}, (280, 760)))
    send = add(node("Send the digest", "n8n-nodes-base.telegram", 1.2, {
        "chatId": chat_id, "text": "={{ $json.text }}", "additionalFields": {},
    }, (560, 760), {"telegramApi": creds["telegram"]}))
    link(conns, morning, digest)
    link(conns, digest, send)
    settings = {"executionOrder": "v1", "timezone": "Europe/Amsterdam", "saveManualExecutions": True}
    if repair_id:
        settings["errorWorkflow"] = repair_id
    return {"name": "Inky · Buy-to-let abroad", "nodes": nodes, "connections": conns, "settings": settings}


def repair_workflow(main_id, creds, chat_id, schemas):
    nodes, conns = [], {}
    add = lambda n: nodes.append(n) or n["name"]
    tg = {"telegramApi": creds["telegram"]}
    n8n = {"n8nApi": creds["n8n"]}
    on_error = add(node("On error", "n8n-nodes-base.errorTrigger", 1, {}, (0, 300)))
    broke = add(node("Tell me it broke", "n8n-nodes-base.telegram", 1.2, {
        "chatId": chat_id, "additionalFields": {},
        "text": "={{ 'Inky hit an error in ' + $json.workflow.name + ': ' + ($json.execution.error?.message || '?') + '. Trying to fix one step.' }}",
    }, (260, 120), tg))
    read = add(node("Read the error", "n8n-nodes-base.code", 2, {"jsCode": """
const e = $json.execution || {};
const msg = e.error?.message || '';
const m = msg.match(/Step (.+) returned 0 homes/);
const state = $getWorkflowStaticData('global');
state.fixes = (state.fixes || []).filter((t) => Date.now() - t < 3600e3);
if (state.fixes.length) return [];  // safety limit: one fix per hour, then a human decides
return [{ json: { workflowId: $json.workflow.id, step: m ? m[1] : e.lastNodeExecuted, error: msg } }];
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
return [{{ json: {{ wf, step: err.step, key, before: step.parameters[key], body: {{
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
const state = $getWorkflowStaticData('global');
state.fixes = [...(state.fixes || []), Date.now()];
return [{{ json: {{ workflowId: wf.id, step: pick.step, change: answer.change || 'input updated',
  workflow: {{ name: wf.name, nodes: wf.nodes, connections: wf.connections, settings }} }} }}];
"""}, (1220, 400)))
    save = add(node("Save the fix", "n8n-nodes-base.n8n", 1, {
        "resource": "workflow", "operation": "update",
        "workflowId": {"__rl": True, "value": "={{ $json.workflowId }}", "mode": "id"},
        "workflowObject": "={{ JSON.stringify($json.workflow) }}",
    }, (1460, 400), n8n))
    told = add(node("Tell me it's fixed", "n8n-nodes-base.telegram", 1.2, {
        "chatId": chat_id, "additionalFields": {},
        "text": "={{ 'Fixed ' + $('Patch the step').first().json.step + ': ' + $('Patch the step').first().json.change + '. Running it again now.' }}",
    }, (1700, 400), tg))
    rerun = add(node("Run it again", "n8n-nodes-base.executeWorkflow", 1.2, {
        "source": "database", "workflowId": {"__rl": True, "value": main_id, "mode": "id"},
        "options": {"waitForSubWorkflow": False},
    }, (1940, 400)))
    for a, b in [(on_error, broke), (on_error, read), (read, get), (get, pick), (pick, fix), (fix, patch), (patch, save), (save, told), (told, rerun)]:
        link(conns, a, b)
    return {"name": "Inky · repair one step", "nodes": nodes, "connections": conns,
            "settings": {"executionOrder": "v1", "timezone": "Europe/Amsterdam"}}


def actor_schemas():
    """Input field names per actor, from the public Apify API, so GLM repairs with real field names."""
    out = {}
    for _, _, actor, _ in SOURCES:
        if actor in out:
            continue
        try:
            a = httpx.get(f"https://api.apify.com/v2/acts/{actor}", timeout=20).json()["data"]
            b = httpx.get(f"https://api.apify.com/v2/actor-builds/{a['taggedBuilds']['latest']['buildId']}", timeout=20).json()["data"]
            props = b["actorDefinition"]["input"]["properties"]
            out[actor] = {k: {"type": v.get("type"), **({"enum": v["enum"][:12]} if v.get("enum") else {})} for k, v in props.items()}
        except Exception as e:
            print(f"schema for {actor} unavailable ({type(e).__name__})")
    return out


class N8n:
    def __init__(self):
        self.base = os.environ["N8N_BASE_URL"].rstrip("/")
        self.http = httpx.Client(base_url=f"{self.base}/api/v1", headers={"X-N8N-API-KEY": os.environ["N8N_API_KEY"]}, timeout=60)

    def call(self, method, path, **kw):
        r = self.http.request(method, path, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"n8n {method} {path}: {r.status_code} {r.text[:400]}")
        return r.json() if r.content else {}

    def has_type(self, type_):
        return self.http.get(f"/credentials/schema/{type_}").status_code == 200

    def credential(self, state, role, type_, name, data):
        if role in state["credentials"]:
            return state["credentials"][role]
        try:
            c = self.call("POST", "/credentials", json={"name": name, "type": type_, "data": data})
        except RuntimeError:
            print(json.dumps(self.call("GET", f"/credentials/schema/{type_}"))[:600])
            raise
        state["credentials"][role] = {"id": c["id"], "name": c["name"], "type": type_}
        return state["credentials"][role]

    def upsert(self, state, key, wf):
        if state.get(key):
            self.call("PUT", f"/workflows/{state[key]}", json=wf)
        else:
            state[key] = self.call("POST", "/workflows", json=wf)["id"]
        return state[key]


def chat_id():
    if os.environ.get("TELEGRAM_CHAT_ID"):
        return os.environ["TELEGRAM_CHAT_ID"]
    t = os.environ["TELEGRAM_BOT_TOKEN"]
    updates = httpx.get(f"https://api.telegram.org/bot{t}/getUpdates", timeout=20).json().get("result", [])
    ids = [u["message"]["chat"]["id"] for u in updates if "message" in u]
    if not ids:
        raise SystemExit("No Telegram chat yet: send /start to your bot, then run again.")
    return str(ids[-1])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-activate", action="store_true", help="create or update, but do not switch on")
    args = p.parse_args()
    load_dotenv()

    rules = json.loads((DATA / "rules.json").read_text())["final"]
    zones = json.loads((DATA / "zones.json").read_text())
    costs = json.loads((DATA / "costs.json").read_text())
    pln = json.loads((DATA / "research.json").read_text())["pln_per_eur"]
    schemas = actor_schemas()

    if args.dry_run:
        fake = {r: {"id": "0", "name": r} for r in ("apify", "telegram", "n8n", "openrouter", "gmail")}
        (DATA / "n8n-main.json").write_text(json.dumps(main_workflow(rules, zones, costs, pln, fake, "0", "REPAIR_ID"), ensure_ascii=False, indent=1))
        (DATA / "n8n-repair.json").write_text(json.dumps(repair_workflow("MAIN_ID", fake, "0", schemas), ensure_ascii=False, indent=1))
        print(f"wrote {DATA}/n8n-main.json and {DATA}/n8n-repair.json")
        return

    state_file = Path("data/n8n.json")  # one record of what exists in n8n, whatever the input folder
    state = json.loads(state_file.read_text()) if state_file.exists() else {"credentials": {}}
    api, chat = N8n(), chat_id()
    mode = "node" if api.has_type("apifyApi") else "http"
    if mode == "http":
        print("Apify node not installed in n8n: using n8n's HTTP node on the Apify API. Install @apify/n8n-nodes-apify and run again to switch.")
    token = os.environ["APIFY_TOKEN"]
    creds = {
        "apify": api.credential(state, f"apify-{mode}", *(("apifyApi", "Inky · Apify", {"apiKey": token}) if mode == "node"
                                                         else ("httpHeaderAuth", "Inky · Apify token", {"name": "Authorization", "value": f"Bearer {token}"}))),
        "telegram": api.credential(state, "telegram", "telegramApi", "Inky · Telegram", {"accessToken": os.environ["TELEGRAM_BOT_TOKEN"]}),
        "n8n": api.credential(state, "n8n", "n8nApi", "Inky · n8n API", {"apiKey": os.environ["N8N_API_KEY"], "baseUrl": f"{api.base}/api/v1"}),
        "openrouter": api.credential(state, "openrouter", "httpHeaderAuth", "Inky · OpenRouter", {"name": "Authorization", "value": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}),
    }
    if os.environ.get("N8N_GMAIL_CREDENTIAL_ID"):
        creds["gmail"] = {"id": os.environ["N8N_GMAIL_CREDENTIAL_ID"], "name": "Gmail"}
    state_file.write_text(json.dumps(state, indent=1))

    main_id = api.upsert(state, "main", main_workflow(rules, zones, costs, pln, creds, chat, state.get("repair"), mode))
    repair_id = api.upsert(state, "repair", repair_workflow(main_id, creds, chat, schemas))
    api.upsert(state, "main", main_workflow(rules, zones, costs, pln, creds, chat, repair_id, mode))
    state_file.write_text(json.dumps(state, indent=1))
    print(f"main:   {api.base}/workflow/{main_id}\nrepair: {api.base}/workflow/{repair_id}")
    if args.no_activate:
        return
    try:
        api.call("POST", f"/workflows/{main_id}/activate")
    except RuntimeError as e:
        hint = ""
        raise SystemExit(f"Created, but could not activate: {e}.{hint}")
    print("active: runs every 15 minutes, digest at 08:00")
    if not creds.get("gmail"):
        print("Gmail drafts are paused: set N8N_GMAIL_CREDENTIAL_ID in .env (see .env.example) and run again.")


if __name__ == "__main__":
    main()
