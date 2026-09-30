"""API keys. macOS: login Keychain via `security -i`, fed on stdin so a key never appears in argv.
Elsewhere (or INKY_KEYS=file): a 0600 JSON file in INKY_HOME. Environment variables are a read-only fallback."""
import json
import os
import platform
import subprocess
from pathlib import Path

ENV = {"openrouter": "OPENROUTER_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
       "gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "xai": "XAI_API_KEY", "mistral": "MISTRAL_API_KEY",
       "telegram": "TELEGRAM_BOT_TOKEN", "custom": "INKY_CUSTOM_API_KEY", "apify": "APIFY_TOKEN", "n8n": "N8N_API_KEY"}


def load_dotenv(path):
    """Minimal .env reader (KEY=value lines). Values never leave this process."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Keys:
    def __init__(self, home, backend=None, service="inky"):
        self.service = service
        self.backend = backend or os.environ.get("INKY_KEYS") or ("keychain" if platform.system() == "Darwin" else "file")
        self.file = Path(home) / "keys.json"

    # ---- file backend
    def _read_file(self):
        return json.loads(self.file.read_text(encoding="utf-8")) if self.file.exists() else {}

    def _write_file(self, d):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.touch(mode=0o600, exist_ok=True)
        os.chmod(self.file, 0o600)
        self.file.write_text(json.dumps(d), encoding="utf-8")

    # ---- keychain backend
    def _security(self, script):
        return subprocess.run(["security", "-i"], input=script, capture_output=True, text=True, timeout=15)

    def set(self, provider, value):
        value = (value or "").strip()
        if not value or any(c in value for c in '"\n\r\\'):
            raise ValueError("key is empty or has characters a key never has")
        if self.backend == "keychain":
            r = self._security(f'add-generic-password -U -s "{self.service}" -a "{provider}" -w "{value}"\n')
            if r.returncode != 0:
                raise RuntimeError("keychain refused the key")
        else:
            d = self._read_file()
            d[provider] = value
            self._write_file(d)

    def stored(self, provider):
        if self.backend == "keychain":
            r = subprocess.run(["security", "find-generic-password", "-s", self.service, "-a", provider, "-w"],
                               capture_output=True, text=True, timeout=15)
            return r.stdout.strip() if r.returncode == 0 else None
        return self._read_file().get(provider)

    def get(self, provider):
        return self.stored(provider) or os.environ.get(ENV.get(provider, "")) or None

    def delete(self, provider):
        if self.backend == "keychain":
            subprocess.run(["security", "delete-generic-password", "-s", self.service, "-a", provider],
                           capture_output=True, timeout=15)
        else:
            d = self._read_file()
            d.pop(provider, None)
            self._write_file(d)

    def source(self, provider):
        if self.stored(provider):
            return "keychain" if self.backend == "keychain" else "file"
        return "environment" if os.environ.get(ENV.get(provider, "")) else None
