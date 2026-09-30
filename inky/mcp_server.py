"""Inky as an MCP server, so Claude Code, Codex or any MCP client can use your bots.
Talks to the running engine's local API. Approving Needs-you items is deliberately not a tool.
Claude Code, one run:  claude -p "..." --mcp-config '{"mcpServers":{"inky":{"command":"<python>","args":["-m","inky.mcp_server"]}}}'
Codex, one run:        codex exec -c 'mcp_servers.inky.command="<python>"' -c 'mcp_servers.inky.args=["-m","inky.mcp_server"]' "..." """
import json
import os
from pathlib import Path

import httpx

from inky.mcp import serve_stdio

HOME = Path(os.environ.get("INKY_HOME", "~/.inky")).expanduser()
URL = os.environ.get("INKY_URL", "http://127.0.0.1:8800")


def engine_url():
    """The running engine's address from engine.json (the desktop app may pick a new port each start), else INKY_URL."""
    try:
        return json.loads((HOME / "engine.json").read_text(encoding="utf-8"))["url"]
    except (OSError, ValueError, KeyError):
        return URL


def api(method, path, body=None, timeout=300):
    token = (HOME / "api_token").read_text().strip() if (HOME / "api_token").exists() else ""
    r = httpx.request(method, engine_url() + path, json=body, timeout=timeout, headers={"X-Inky-Token": token})
    r.raise_for_status()
    return r.json()


def find_bot(ref):
    bots = api("GET", "/api/bots")["bots"]
    ref = str(ref).strip().lower()
    b = next((b for b in bots if str(b["id"]) == ref or b["name"].lower() == ref), None) or \
        next((b for b in bots if ref in b["name"].lower()), None)
    if not b:
        raise ValueError(f"no bot called {ref}; bots: {', '.join(x['name'] for x in bots)}")
    return b


def list_bots(a):
    where = {str(c["id"]): c["name"] for c in api("GET", "/api/computers")["computers"]}
    return json.dumps([{**{k: b.get(k) for k in ("id", "name", "job", "status", "step", "skills", "next_run")},
                        "runs_on": where.get(str(b.get("computer") or "local"), "this computer")}
                       for b in api("GET", "/api/bots")["bots"]], ensure_ascii=False)


def get_bot(a):
    b = find_bot(a["bot"])
    return json.dumps(api("GET", f"/api/bots/{b['id']}"), ensure_ascii=False)[:20000]


def message_bot(a):
    b = find_bot(a["bot"])
    return api("POST", f"/api/bots/{b['id']}/chat", {"text": a["text"], "source": "mcp"})["reply"]


def run_skill(a):
    b = find_bot(a["bot"])
    return json.dumps(api("POST", f"/api/bots/{b['id']}/run", {"skill": a.get("skill"), "wait": True}), ensure_ascii=False)


def bot_results(a):
    b = find_bot(a["bot"])
    rows = api("GET", f"/api/bots/{b['id']}/results")["results"]
    if a.get("only_new"):
        rows = [r for r in rows if r.get("new")]
    return json.dumps(rows[: int(a.get("limit", 50))], ensure_ascii=False)


def list_needs(a):
    return json.dumps(api("GET", "/api/needs")["needs"], ensure_ascii=False)


def create_bot(a):
    draft = api("POST", "/api/bots/draft", {"job": a["job"]})["draft"]
    return json.dumps(api("POST", "/api/bots", draft)["bot"], ensure_ascii=False)


BOT = {"type": "string", "description": "Bot name or id"}
TOOLS = {
    "list_bots": ("List your Inky bots with their status.", {"type": "object", "properties": {}}, list_bots, {"readOnlyHint": True, "title": "List bots"}),
    "get_bot": ("One bot: job, rules, memory, skills, recent messages.", {"type": "object", "required": ["bot"], "properties": {"bot": BOT}}, get_bot, {"readOnlyHint": True, "title": "Get a bot"}),
    "message_bot": ("Send a bot a chat message and get its reply (it may add rules, learn or run).",
                    {"type": "object", "required": ["bot", "text"], "properties": {"bot": BOT, "text": {"type": "string"}}}, message_bot),
    "run_skill": ("Run a bot's learned skill now (replays with no AI) and return what it found.",
                  {"type": "object", "required": ["bot"], "properties": {"bot": BOT, "skill": {"type": "string", "description": "Skill name or id; default all"}}}, run_skill),
    "bot_results": ("What a bot has found (listings, prices…).",
                    {"type": "object", "required": ["bot"], "properties": {"bot": BOT, "only_new": {"type": "boolean"}, "limit": {"type": "integer"}}}, bot_results, {"readOnlyHint": True, "title": "Bot results"}),
    "list_needs": ("What your bots are waiting for you on (read only; approve in the Inky app).", {"type": "object", "properties": {}}, list_needs, {"readOnlyHint": True, "title": "Needs you"}),
    "create_bot": ("Create a new bot from a job description.", {"type": "object", "required": ["job"], "properties": {"job": {"type": "string"}}}, create_bot),
}

def main():
    serve_stdio("inky", "0.1", TOOLS)


if __name__ == "__main__":
    main()
