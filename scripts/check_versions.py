"""The app's version is written in five places; they must agree (CI fails otherwise). Prints the version."""
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
found = {
    "pyproject.toml": tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"],
    "inky/__init__.py": re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "inky/__init__.py").read_text()).group(1),
    "desktop/src-tauri/tauri.conf.json": json.loads((ROOT / "desktop/src-tauri/tauri.conf.json").read_text())["version"],
    "desktop/src-tauri/Cargo.toml": tomllib.loads((ROOT / "desktop/src-tauri/Cargo.toml").read_text())["package"]["version"],
    "desktop/package.json": json.loads((ROOT / "desktop/package.json").read_text())["version"],
}
if len(set(found.values())) != 1:
    sys.exit("Versions differ: " + ", ".join(f"{k} {v}" for k, v in found.items()))
tag = sys.argv[1].removeprefix("v") if len(sys.argv) > 1 else None
if tag and tag != next(iter(found.values())):
    sys.exit(f"The tag says {tag} but the app says {next(iter(found.values()))}")
print(next(iter(found.values())))
