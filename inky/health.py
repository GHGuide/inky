"""Health: what works and what doesn't, with the fix for each."""
import os
import shutil
import subprocess
import time

import httpx

from inky.llm import PROVIDERS, ROLES


def docker():
    if not shutil.which("docker"):
        return {"installed": False, "running": False}
    try:
        r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True, timeout=6)
        return {"installed": True, "running": r.returncode == 0, "version": r.stdout.strip()}
    except Exception:
        return {"installed": True, "running": False}


def check(engine):
    rows = []
    roles = engine.llm.roles()
    errs = engine.store.setting("provider_errors", {})
    for role, label in ROLES.items():
        r = roles.get(role)
        if not r:
            rows.append({"name": label, "ok": False, "detail": "no model set", "fix": "#/models"})
            continue
        p = PROVIDERS[r["provider"]]
        ok, detail = True, f"{r['model']} · {p['label']}"
        if not p.get("local") and not engine.keys.get(r["provider"]):
            ok, detail = False, f"no key for {p['label']}"
        e = errs.get(r["provider"])
        if e and time.time() - e["at"] < 3600:
            ok = False
            detail = {401: "the key was refused", 402: "out of credit or monthly limit reached", 429: "rate limited"}.get(e["status"], f"error {e['status']}")
        rows.append({"name": label, "ok": ok, "detail": detail, "fix": "#/keys" if not ok else None})
    local = engine.llm.local_status()
    rows.append({"name": "Ollama", "ok": local["ollama"]["running"],
                 "detail": (f"{len(local['ollama']['models'])} models" if local["ollama"]["running"] else
                            "installed, not running" if local["ollama"]["installed"] else "not installed"), "fix": "#/models/local", "info": True})
    d = docker()
    rows.append({"name": "Docker", "ok": d["running"], "detail": d.get("version") or ("stopped" if d["installed"] else "not installed"),
                 "info": True, "fix": None})
    for c in engine.store.find("computers"):
        try:
            ok = httpx.get(c["url"].rstrip("/") + "/api/ping", timeout=3).status_code == 200
        except Exception:
            ok = False
        rows.append({"name": c["name"], "ok": ok, "detail": "reachable" if ok else "can’t reach it", "fix": "#/computers"})
    for s in engine.mcp.servers():
        if s["enabled"]:
            rows.append({"name": s["label"], "ok": s["installed"], "detail": ("connected" if s["connected"] else "ready") if s["installed"] else "not installed",
                         "fix": "#/connectors"})
    tg = engine.store.setting("telegram", {})
    if tg.get("enabled"):
        rows.append({"name": "Telegram", "ok": bool(engine.keys.get("telegram")), "detail": "ready" if engine.keys.get("telegram") else "no bot token", "fix": "#/connectors"})
    return rows


_browser = {"ready": False}


def browser_ready():
    """Is the bots' browser (Chromium) installed? The desktop app downloads it on first launch."""
    if _browser["ready"]:
        return True
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            _browser["ready"] = os.path.exists(p.chromium.executable_path)
    except Exception:
        return False
    return _browser["ready"]


def install_browser(on_line):
    """Runs Playwright's own installer for Chromium, line by line. True when it worked."""
    from playwright._impl._driver import compute_driver_executable, get_driver_env
    node, cli = compute_driver_executable()
    p = subprocess.Popen([node, cli, "install", "chromium"], env=get_driver_env(), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    for line in p.stdout:
        if line.strip():
            on_line(line.strip()[:200])
    ok = p.wait() == 0
    _browser["ready"] = False  # look again next time
    return ok
