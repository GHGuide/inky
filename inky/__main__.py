"""python -m inky [--port 8800] [--home ~/.inky] [--host 127.0.0.1] [--name "This Mac"] [--no-open] [--bar]"""
import argparse
import json
import os
import signal
import subprocess
import sys
import webbrowser
from pathlib import Path

from inky.bots import Engine
from inky.keys import load_dotenv
from inky.server import serve


def main():
    ap = argparse.ArgumentParser(prog="inky")
    ap.add_argument("--port", type=int, default=int(os.environ.get("INKY_PORT", 8800)))
    ap.add_argument("--host", default=os.environ.get("INKY_HOST", "127.0.0.1"))
    ap.add_argument("--home", default=os.environ.get("INKY_HOME", "~/.inky"))
    ap.add_argument("--name", default=None, help="what this engine is called in Computers")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--bar", action="store_true", help="macOS: also start the menu bar app (build it once with native/mac/build.sh)")
    a = ap.parse_args()
    load_dotenv(Path.cwd() / ".env")
    home = Path(a.home).expanduser()
    os.environ["INKY_HOME"] = str(home)
    if getattr(sys, "frozen", False):  # the desktop app: the bots' browser lives in Inky's folder
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(home / "browsers"))
    engine = Engine(a.home)
    if a.name:
        engine.store.set_setting("engine_name", a.name)
    engine.start_scheduler()
    srv = serve(engine, a.host, a.port)  # port 0: any free port (the desktop app reads it from the first line)
    url = f"http://{'127.0.0.1' if a.host in ('0.0.0.0', '::', '') else a.host}:{srv.server_port}"  # this computer's browser gets the token
    from inky.transfer import pair_code
    print(f"Inky is running at {url}")
    print(f"Pairing code for other computers: {pair_code(engine.token)}", flush=True)
    write_engine_file(home, url, os.getpid())
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # finally: below closes the engine and removes engine.json
    if a.bar and sys.platform == "darwin":
        bar = Path(__file__).resolve().parent.parent / "native" / "mac" / "build" / "InkyBar.app"
        if bar.exists():
            subprocess.Popen(["open", str(bar), "--args", "--url", url])
        else:
            print("Build the menu bar app first: native/mac/build.sh")
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        remove_engine_file(home)
        engine.close()


def write_engine_file(home, url, pid):
    """engine.json tells the desktop app an engine already runs on this data folder, so it attaches instead of starting a second."""
    from inky import __version__
    (Path(home) / "engine.json").write_text(json.dumps({"url": url, "pid": pid, "version": __version__}), encoding="utf-8")


def remove_engine_file(home):
    try:
        f = Path(home) / "engine.json"
        if json.loads(f.read_text(encoding="utf-8")).get("pid") == os.getpid():
            f.unlink()
    except (OSError, ValueError):
        pass


if __name__ == "__main__":
    main()
