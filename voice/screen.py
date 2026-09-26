"""'Inky has the screen': while this flag file exists, voice/init.lua (Hammerspoon) draws a coral frame round the display.

    with has_screen("learning tecnocasa.it"): ...    # teach/learn.py and race/race.py, headed runs only

Without Hammerspoon the file does nothing. If a run is killed hard (kill -9), remove it: rm "$TMPDIR/inky-screen.flag".
"""
import os
from contextlib import contextmanager
from pathlib import Path

FLAG = Path(os.environ.get("TMPDIR") or "/tmp/") / "inky-screen.flag"  # init.lua reads the same $TMPDIR path


@contextmanager
def has_screen(text):
    FLAG.write_text(text)
    try:
        yield
    finally:
        FLAG.unlink(missing_ok=True)
