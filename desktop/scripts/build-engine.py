"""Builds the engine binary the Tauri app runs as a sidecar: desktop/src-tauri/binaries/inky-engine-<target triple>.
Run from the repo root: python desktop/scripts/build-engine.py"""
import os
import subprocess
import sys

triple = next(l.split(": ", 1)[1] for l in subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True).stdout.splitlines()
              if l.startswith("host: "))
sep, A = os.pathsep, os.path.abspath  # absolute paths: PyInstaller reads some relative to --specpath
cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--name", f"inky-engine-{triple}",
       "--collect-all", "playwright", "--add-data", f"{A('inky/ui')}{sep}inky/ui", "--add-data", f"{A('inky/overlay.js')}{sep}inky", "--add-data", f"{A('library')}{sep}library",
       "--exclude-module", "tkinter", "--paths", A("."), "--distpath", A("desktop/src-tauri/binaries"),
       "--workpath", A("build/pyi"), "--specpath", A("build/pyi"), A("desktop/scripts/engine-entry.py")]
print(" ".join(cmd))
subprocess.run(cmd, check=True)
print("built", f"desktop/src-tauri/binaries/inky-engine-{triple}")
