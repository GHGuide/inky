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


# What to pick when you paste a key: first pattern that matches wins; within a pattern the newest,
# undated, non-preview model wins. ponytail: name patterns rot as providers ship models; the "" fallback keeps it working.
PICK = {
    "anthropic": ["sonnet", "haiku", "opus"],
    "openai": ["gpt-5-mini", "gpt-4.1-mini", "gpt-4o-mini", "gpt-5", "gpt-4.1", "gpt-4o"],
    "gemini": ["flash", "pro"],
    "groq": ["gpt-oss-120b", "llama-3.3-70b", "qwen3", "llama"],
    "xai": ["grok-4-fast", "grok-4", "grok-3-mini", "grok"],
    "mistral": ["mistral-medium", "mistral-small", "mistral-large", "mistral"],
}
NOT_CHAT = re.compile(r"embed|whisper|tts|audio|image|dall-e|moderation|realtime|transcribe|search|guard|rerank|ocr|"
                      r"computer-use|codex|sora|babbage|davinci|instruct|aqa|imagen|veo|learnlm", re.I)
NOISE = re.compile(r"lite|preview|exp|nano|thinking|deep-research", re.I)
LOCAL_PREFS = ("qwen3", "llama3", "gemma3", "mistral", "phi")


class NoModel(RuntimeError):
    pass


def plain(e, label="The provider"):
    """A model call's error in words."""
    if isinstance(e, NoModel):
        return str(e)
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code in (400, 401, 403):
            body = e.response.text.lower()
            if code == 400 and "model" in body and "key" not in body:
                return f"{label} doesn’t have that model."
            return "That key was refused. Check you copied all of it."
        if code == 404:
            return f"{label} doesn’t have that model."
        if code == 429:
            return f"{label} says too many requests, or the account is out of credit."
        if code >= 500:
            return f"{label} had a problem answering ({code}). If it’s a local model, it may not be a chat model."
        return f"{label} answered {code}."
    if isinstance(e, httpx.ConnectError):
        return f"Couldn’t reach {label}. Is it running?"
    if isinstance(e, httpx.TimeoutException):
        return f"{label} took too long to answer."
    return str(e)[:200]


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
        d = self.store.setting("default_model") or {}
        if d.get("provider") in PROVIDERS and (PROVIDERS[d["provider"]].get("local") or self.keys.get(d["provider"])):
            return {r: {"provider": d["provider"], "model": d["model"]} for r in ROLES}
        local = sorted((m["name"] for m in self.local_models()),
                       key=lambda n: next((i for i, f in enumerate(LOCAL_PREFS) if n.startswith(f)), 99))
        if local:  # free and private; a key only takes over once you connect it (Models, API keys or setup)
            return {r: {"provider": "ollama", "model": local[0]} for r in ROLES}
        if self.keys.get("openrouter"):
            m = os.environ.get("OPENROUTER_MODEL") or "z-ai/glm-4.6"
            roles = {r: {"provider": "openrouter", "model": m} for r in ROLES}
        return roles

    def remember_default(self, provider, model):
        """Connecting a model makes it the one every role uses (you can still pick per role in Models)."""
        self.store.set_setting("default_model", {"provider": provider, "model": model})
        self.store.set_setting("roles", {r: {"provider": provider, "model": model} for r in ROLES})

    def over_limit(self, provider):
        lim = (self.store.setting("key_limits", {}) or {}).get(provider)
        spent = self.spent(provider)
        return lim is not None and spent >= float(lim), spent, lim

    def spent(self, provider):
        return float(((self.store.setting("spend", {}) or {}).get(time.strftime("%Y-%m")) or {}).get(provider, 0.0))

    def list_models(self, provider):
        """Ask a provider which models it has (every provider here serves GET /models)."""
        p, key = PROVIDERS[provider], self.keys.get(provider)
        base = self.store.setting("custom_provider", {}).get("base", p["base"]) if provider == "custom" else p["base"]
        if p.get("kind") == "anthropic":
            headers, params = {"x-api-key": key or "", "anthropic-version": "2023-06-01"}, {"limit": 100}
        else:
            headers, params = ({"Authorization": f"Bearer {key}"} if key else {}), None
        r = httpx.get(base.rstrip("/") + "/models", headers=headers, params=params, timeout=15)
        self._record(provider, r)
        r.raise_for_status()
        return [m["id"].removeprefix("models/") for m in r.json().get("data", []) if m.get("id")]

    def pick_model(self, provider):
        """A good everyday model for this provider, chosen from what it actually offers."""
        if provider == "openrouter":  # hundreds of models; this one is cheap and good at tools
            return os.environ.get("OPENROUTER_MODEL") or "z-ai/glm-4.6"
        if provider == "ollama":
            local = [m["name"] for m in self.local_models()]
            return sorted(local, key=lambda n: next((i for i, f in enumerate(LOCAL_PREFS) if n.startswith(f)), 99))[0] if local else None
        ids = [i for i in self.list_models(provider) if not NOT_CHAT.search(i)]
        prefs = PICK.get(provider, []) + [""]

        def score(t):
            i, m = t
            rank = next(n for n, pat in enumerate(prefs) if pat in m)
            v = re.search(r"(?<!\d)(\d{1,2})(?:[.-](\d{1,2}))?(?!\d)", m)  # 4.5 in gemini-2.5 or claude-sonnet-4-5
            ver = float(f"{v.group(1)}.{v.group(2) or 0}") if v else 0
            return (rank, bool(NOISE.search(m)), bool(re.search(r"\d{4}", m)), -ver, len(m), i)
        return min(enumerate(ids), key=score)[1] if ids else None

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
        over, spent, lim = self.over_limit(provider)
        if over:
            raise NoModel(f"{p['label']} reached your monthly limit (${spent:.2f} of ${float(lim):.2f}). Raise it in API keys.")
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
            if "qwen3" in model.lower() and messages and messages[-1]["role"] == "user":
                messages = messages[:-1] + [{**messages[-1], "content": messages[-1]["content"] + " /no_think"}]  # skip thinking
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
            text = re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.S).strip()
            u = j.get("usage") or {}
            usage = {"in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0), "cost": u.get("cost")}
        usage.update(provider=provider, model=model, role=role, seconds=round(time.time() - t0, 2),
                     local=bool(p.get("local")))
        if usage.get("cost"):  # only OpenRouter reports what a call cost; that is what monthly limits count
            spend = self.store.setting("spend", {}) or {}
            month = spend.setdefault(time.strftime("%Y-%m"), {})
            month[provider] = month.get(provider, 0.0) + float(usage["cost"])
            self.store.set_setting("spend", dict(list(spend.items())[-13:]))
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

    def start_ollama(self, wait=8):
        """Start Ollama if it is installed but not running. True once it answers."""
        up = lambda: self.local_status()["ollama"]["running"]
        if up():
            return True
        if platform.system() == "Darwin" and os.path.exists("/Applications/Ollama.app"):
            subprocess.Popen(["open", "-g", "-a", "Ollama"])
        elif shutil.which("ollama"):
            kw = {"creationflags": 0x08000000} if os.name == "nt" else {"start_new_session": True}  # CREATE_NO_WINDOW
            subprocess.Popen([shutil.which("ollama"), "serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, **kw)
        else:
            return False
        for _ in range(wait * 2):
            time.sleep(0.5)
            if up():
                return True
        return False

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
        elif platform.system() == "Windows":
            import ctypes

            class Mem(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("pt", ctypes.c_ulonglong), ("pa", ctypes.c_ulonglong),
                            ("vt", ctypes.c_ulonglong), ("va", ctypes.c_ulonglong), ("ve", ctypes.c_ulonglong)]
            m = Mem(length=ctypes.sizeof(Mem))
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            info["memory_gb"] = round(m.total / 2**30)
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
