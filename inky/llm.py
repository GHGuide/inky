"""Model router. Roles (learn, chat, repair, smart) map to a provider + model.
Every provider is OpenAI-compatible except Anthropic, which gets a tiny adapter."""
import json
import os
import platform
import re
import shutil
import subprocess
import time

import httpx

PROVIDERS = {
    "ollama": {"label": "Ollama", "base": "http://127.0.0.1:11434/v1", "local": True},
    "custom": {"label": "OpenAI-compatible server", "base": "http://127.0.0.1:1234/v1", "local": True},
    "openrouter": {"label": "OpenRouter", "base": "https://openrouter.ai/api/v1"},
    "anthropic": {"label": "Anthropic", "base": "https://api.anthropic.com/v1", "kind": "anthropic"},
    "openai": {"label": "OpenAI", "base": "https://api.openai.com/v1"},
    "gemini": {"label": "Google Gemini", "base": "https://generativelanguage.googleapis.com/v1beta/openai"},
    "groq": {"label": "Groq", "base": "https://api.groq.com/openai/v1"},
    "xai": {"label": "xAI", "base": "https://api.x.ai/v1"},
    "mistral": {"label": "Mistral", "base": "https://api.mistral.ai/v1"},
}
ROLES = {
    "learn": "Learning a new site",
    "chat": "Talking with you",
    "repair": "Fixing a broken step",
    "smart": "Smarter model, when you ask for it",
}


class NoModel(RuntimeError):
    pass


def parse_json(text):
    """Pull the first JSON object out of a model reply (handles ```json fences and chatter)."""
    if text is None:
        raise ValueError("empty reply")
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, flags=re.S)
    if m:
        t = m.group(1)
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object in reply")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(t[start:], start):
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            elif ch != "\\":
                esc = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(t[start:i + 1])
    raise ValueError("unbalanced JSON in reply")


class LLM:
    def __init__(self, store, keys, on_usage=None):
        self.store, self.keys, self.on_usage = store, keys, on_usage

    # ---- config
    def providers(self):
        custom = self.store.setting("custom_provider", {})
        out = []
        for name, p in PROVIDERS.items():
            base = custom.get("base", p["base"]) if name == "custom" else p["base"]
            out.append(dict(name=name, label=p["label"], base=base, local=p.get("local", False),
                            key=self.keys.source(name) if not p.get("local") or name == "custom" else None))
        return out

    def default_roles(self):
        roles = {}
        if self.keys.get("openrouter"):
            m = os.environ.get("OPENROUTER_MODEL") or "z-ai/glm-4.6"
            roles = {r: {"provider": "openrouter", "model": m} for r in ROLES}
        local = [m["name"] for m in self.local_models()]
        if local:
            roles["chat"] = {"provider": "ollama", "model": local[0]}
            roles.setdefault("learn", {"provider": "ollama", "model": local[0]})
            roles.setdefault("repair", {"provider": "ollama", "model": local[0]})
            roles.setdefault("smart", {"provider": "ollama", "model": local[0]})
        return roles

    def roles(self):
        saved = self.store.setting("roles") or {}
        roles = self.default_roles()
        roles.update({k: v for k, v in saved.items() if v and v.get("provider")})
        return roles

    def set_role(self, role, provider, model):
        saved = self.store.setting("roles") or {}
        saved[role] = {"provider": provider, "model": model}
        self.store.set_setting("roles", saved)

    # ---- calls
    def chat(self, role, messages, bot_id=None, max_tokens=1200, temperature=0.2, timeout=120):
        r = self.roles().get(role)
        if not r:
            raise NoModel(f"No model is set for “{ROLES.get(role, role)}”. Add one in Models.")
        return self.complete(r["provider"], r["model"], messages, bot_id=bot_id, role=role,
                             max_tokens=max_tokens, temperature=temperature, timeout=timeout)

    def complete(self, provider, model, messages, bot_id=None, role="test", max_tokens=1200, temperature=0.2, timeout=120):
        p = dict(PROVIDERS[provider])
        if provider == "custom":
            p["base"] = self.store.setting("custom_provider", {}).get("base", p["base"])
        key = self.keys.get(provider)
        if not p.get("local") and not key:
            raise NoModel(f"No key for {p['label']}. Paste one in API keys.")
        t0 = time.time()
        if p.get("kind") == "anthropic":
            system = "\n".join(m["content"] for m in messages if m["role"] == "system")
            body = {"model": model, "max_tokens": max_tokens, "temperature": temperature, "system": system,
                    "messages": [m for m in messages if m["role"] != "system"]}
            res = httpx.post(p["base"] + "/messages", json=body, timeout=timeout,
                             headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
            self._record(provider, res)
            res.raise_for_status()
            j = res.json()
            text = "".join(c.get("text", "") for c in j.get("content", []))
            usage = {"in": j.get("usage", {}).get("input_tokens", 0), "out": j.get("usage", {}).get("output_tokens", 0)}
        else:
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
            if provider == "openrouter":
                body["usage"] = {"include": True}
                body["max_tokens"] = max(max_tokens, 6000)  # reasoning models think before they answer
                body["reasoning"] = {"effort": self.store.setting("reasoning_effort", "low")}
            res = httpx.post(p["base"].rstrip("/") + "/chat/completions", json=body, headers=headers, timeout=timeout)
            self._record(provider, res)
            res.raise_for_status()
            j = res.json()
            text = j["choices"][0]["message"].get("content") or ""
            u = j.get("usage") or {}
            usage = {"in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0), "cost": u.get("cost")}
        usage.update(provider=provider, model=model, role=role, seconds=round(time.time() - t0, 2),
                     local=bool(p.get("local")))
        if self.on_usage:
            self.on_usage(bot_id, usage)
        return text, usage

    def _record(self, provider, res):
        errs = self.store.setting("provider_errors", {})
        if res.status_code >= 400:
            errs[provider] = {"status": res.status_code, "at": time.time(), "text": res.text[:200]}
        else:
            errs.pop(provider, None)
        self.store.set_setting("provider_errors", errs)

    def ask_json(self, role, system, user, bot_id=None, retries=1, **kw):
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last = None
        for _ in range(retries + 1):
            text, usage = self.chat(role, msgs, bot_id=bot_id, **kw)
            try:
                return parse_json(text), usage
            except (ValueError, json.JSONDecodeError) as e:
                last = e
                msgs += [{"role": "assistant", "content": text},
                         {"role": "user", "content": "Reply with one JSON object only."}]
        raise ValueError(f"model did not return JSON: {last}")

    def test(self, provider, model):
        text, usage = self.complete(provider, model, [{"role": "user", "content": "Reply with the single word OK."}],
                                    max_tokens=400, timeout=90)
        return {"ok": "ok" in text.lower(), "reply": text.strip()[:80], "seconds": usage["seconds"]}

    # ---- local runtimes
    def local_models(self):
        try:
            r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=1.5)
            return [{"name": m["name"], "size": m.get("size", 0)} for m in r.json().get("models", [])]
        except Exception:
            return []

    def local_status(self):
        ollama_bin = shutil.which("ollama")
        running = False
        try:
            running = httpx.get("http://127.0.0.1:11434/api/version", timeout=1.5).status_code == 200
        except Exception:
            pass
        custom = self.store.setting("custom_provider", {}).get("base", PROVIDERS["custom"]["base"])
        custom_ok = False
        try:
            custom_ok = httpx.get(custom.rstrip("/") + "/models", timeout=1.5).status_code == 200
        except Exception:
            pass
        lmstudio = any(os.path.exists(p) for p in ("/Applications/LM Studio.app", os.path.expanduser("~/.lmstudio")))
        return {"ollama": {"installed": bool(ollama_bin), "running": running, "models": self.local_models()},
                "lmstudio": {"installed": lmstudio}, "custom": {"base": custom, "reachable": custom_ok},
                "hardware": hardware()}

    def pull(self, name, on_progress=None):
        """Download a local model through Ollama's API (streams progress)."""
        with httpx.stream("POST", "http://127.0.0.1:11434/api/pull", json={"name": name}, timeout=None) as r:
            for line in r.iter_lines():
                if line and on_progress:
                    on_progress(json.loads(line))


def hardware():
    info = {"cpu": platform.processor() or platform.machine(), "memory_gb": None, "disk_free_gb": None}
    try:
        if platform.system() == "Darwin":
            info["cpu"] = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
            info["memory_gb"] = round(int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 2**30)
        elif hasattr(os, "sysconf"):
            info["memory_gb"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30)
        info["disk_free_gb"] = round(shutil.disk_usage(os.path.expanduser("~")).free / 2**30)
    except Exception:
        pass
    return info


def fits(size_bytes, memory_gb, bots_running=0):
    """Rough fit: a model needs its size plus ~2 GB headroom, and each bot browser ~0.7 GB."""
    if not memory_gb:
        return "unknown"
    need = size_bytes / 2**30 + 2 + 0.7 * bots_running
    return "fits well" if need < memory_gb * 0.6 else ("tight" if need < memory_gb * 0.85 else "too big")
