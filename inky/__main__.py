"""python -m inky [--port 8800] [--home ~/.inky] [--host 127.0.0.1] [--name "This Mac"] [--no-open]"""
import argparse
import os
import signal
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
    a = ap.parse_args()
    load_dotenv(Path.cwd() / ".env")
    os.environ["INKY_HOME"] = str(Path(a.home).expanduser())
    engine = Engine(a.home)
    if a.name:
        engine.store.set_setting("engine_name", a.name)
    engine.start_scheduler()
    srv = serve(engine, a.host, a.port)
    url = f"http://{'127.0.0.1' if a.host in ('0.0.0.0', '::', '') else a.host}:{a.port}"  # this computer's browser gets the token
    from inky.transfer import pair_code
    print(f"Inky is running at {url}")
    print(f"Pairing code for other computers: {pair_code(engine.token)}", flush=True)
    signal.signal(signal.SIGTERM, lambda *_: (engine.close(), sys.exit(0)))
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.close()


if __name__ == "__main__":
    main()
