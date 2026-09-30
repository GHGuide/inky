"""Codex as an MCP server. Codex CLI 0.159 has no `mcp-server`, so this wraps `codex exec --json`.
Tools: codex(prompt, cwd, sandbox) and codex_reply(session_id, prompt). Read-only sandbox unless asked."""
import json
import os
import shutil
import subprocess

from inky.mcp import serve_stdio

SCHEMA_RUN = {"type": "object", "required": ["prompt"], "properties": {
    "prompt": {"type": "string", "description": "What Codex should do"},
    "cwd": {"type": "string", "description": "Working directory (default: home)"},
    "sandbox": {"type": "string", "enum": ["read-only", "workspace-write"], "description": "Default read-only"}}}
SCHEMA_REPLY = {"type": "object", "required": ["session_id", "prompt"], "properties": {
    "session_id": {"type": "string"}, "prompt": {"type": "string"}}}


def _exec(args, timeout=900):
    if not shutil.which("codex"):
        raise RuntimeError("the Codex CLI is not installed")
    p = subprocess.run([shutil.which("codex"), "exec", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout,
                       stdin=subprocess.DEVNULL)
    session, last, errors = None, None, []
    for line in p.stdout.splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        t = ev.get("type", "")
        session = session or ev.get("thread_id") or ev.get("session_id") or (ev.get("msg") or {}).get("session_id")
        item = ev.get("item") or {}
        if item.get("type") in ("agent_message", "assistant_message") and item.get("text"):
            last = item["text"]
        elif (ev.get("msg") or {}).get("type") == "agent_message":
            last = ev["msg"].get("message")
        if "error" in t:
            errors.append(ev.get("message") or json.dumps(ev)[:300])
    if p.returncode != 0 and not last:
        raise RuntimeError((errors and errors[-1]) or p.stderr.strip()[-500:] or f"codex exited {p.returncode}")
    return json.dumps({"session_id": session, "reply": last or "", "errors": errors[-3:]})


def run(a):
    cwd = os.path.expanduser(a.get("cwd") or "~")
    sandbox = a.get("sandbox") if a.get("sandbox") in ("read-only", "workspace-write") else "read-only"
    return _exec(["--json", "--skip-git-repo-check", "-s", sandbox, "-C", cwd, a["prompt"]])


def reply(a):
    return _exec(["resume", a["session_id"], "--json", "--skip-git-repo-check", a["prompt"]])


def main():
    serve_stdio("inky-codex", "0.1", {
        "codex": ("Run a Codex agent on a task and return its final reply and session id.", SCHEMA_RUN, run),
        "codex_reply": ("Continue a Codex session with another message.", SCHEMA_REPLY, reply),
    })


if __name__ == "__main__":
    main()
