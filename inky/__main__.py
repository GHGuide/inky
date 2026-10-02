"""python -m inky [--port 8800] [--home ~/.inky] [--host 127.0.0.1] [--name "This Mac"] [--no-open] [--stop-with-stdin]"""
import argparse
import json
import os
import platform
import _thread
import signal
import threading
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
    ap.add_argument("--or-any-port", action="store_true", help="if the port is taken, use any free one (the desktop app prefers 8800 so links and pairings keep working)")
    ap.add_argument("--stop-with-stdin", action="store_true", help="stop when stdin closes (the desktop app uses this, so a crash never leaves an engine behind)")
    a = ap.parse_args()
    home = Path(a.home).expanduser()
    load_dotenv(home / ".env")  # only Inky's own folder: a .env in whatever folder you started it from isn't Inky's to read
    os.environ["INKY_HOME"] = str(home)
    if getattr(sys, "frozen", False):  # the desktop app: the bots' browser lives in Inky's folder
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(home / "browsers"))
        from inky.connectors import fix_path
        fix_path()  # opened from the Dock, the app can't see claude, codex, ollama or docker without this
    engine = Engine(a.home)
    if a.name:
        engine.store.set_setting("engine_name", a.name)
    engine.start_scheduler()
    try:
        srv = serve(engine, a.host, a.port)  # port 0: any free port (the desktop app reads it from the first line)
    except OSError:
        if not a.or_any_port:
            raise
        srv = serve(engine, a.host, 0)
    url = f"http://{'127.0.0.1' if a.host in ('0.0.0.0', '::', '') else a.host}:{srv.server_port}"  # this computer's browser gets the token
    from inky.transfer import pair_code
    print(f"Inky is running at {url}")
    print(f"Pairing code for other computers: {pair_code(engine.token)}", flush=True)
    write_engine_file(home, url, os.getpid())
    if (engine.store.setting("app", {}) or {}).get("lan"):  # you let your phone open Inky last time
        from inky.server import lan_access
        try:
            lan_access(engine, True)
        except Exception:
            pass
    if a.host in ("0.0.0.0", "::", ""):  # reachable from your network: say so, so the app there finds it
        from inky import __version__
        from inky.connect import start_beacon
        from inky.transfer import engine_id as transfer_id
        start_beacon(lambda: engine.store.setting("engine_name", platform.node()), srv.server_port, __version__, transfer_id(engine))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # finally: below closes the engine and removes engine.json
    if a.stop_with_stdin:
        def watch():
            for _ in sys.stdin:
                pass
            _thread.interrupt_main()  # the app is gone: shut down like Ctrl+C (cleans up engine.json)
        threading.Thread(target=watch, daemon=True).start()
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
    tmp = Path(home) / f"engine.json.{pid}.tmp"  # write then rename, so a reader never sees half a file
    tmp.write_text(json.dumps({"url": url, "pid": pid, "version": __version__}), encoding="utf-8")
    os.replace(tmp, Path(home) / "engine.json")


def remove_engine_file(home):
    try:
        f = Path(home) / "engine.json"
        if json.loads(f.read_text(encoding="utf-8")).get("pid") == os.getpid():
            f.unlink()
    except (OSError, ValueError):
        pass


if __name__ == "__main__":
    main()
