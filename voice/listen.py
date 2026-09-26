"""Talk to Inky: record, transcribe on this Mac with whisper.cpp, send the text to the Inky app.

  python voice/listen.py --flag /tmp/inky-voice.flag   record while that file exists (init.lua does this)
  python voice/listen.py --seconds 4                   record for 4 s
  python voice/listen.py --text "only places with the euro"   skip recording
  add --dry-run to ask the app what would change without applying it

stdout: one JSON line, {"heard": ..., **response of POST /api/command} or {"heard": ..., "error": ...}.
"""
import argparse
import array
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

MODELS = Path(__file__).resolve().parent / "models"
MODEL, VAD = MODELS / "ggml-base.bin", MODELS / "ggml-silero-v5.1.2.bin"
MAX_SECONDS = 30
# Hints for whisper's spelling. On noise whisper can echo it back, so heard_nothing() drops an echo.
PROMPT = "Porto, Bari, Łódź, euro, zloty, net yield, flat."
SEARCH = os.environ.get("PATH", "") + ":/opt/homebrew/bin:/usr/local/bin"  # Hammerspoon's PATH has no Homebrew


def tool(name):
    path = shutil.which(name, path=SEARCH)
    if not path:
        raise RuntimeError(f"{name} not found: brew install {'whisper-cpp' if 'whisper' in name else name}")
    return path


def record(wav, flag=None, seconds=None, source=("-f", "avfoundation", "-i", "none:default")):
    """ffmpeg to 16 kHz mono wav. Stops when `flag` disappears, after `seconds`, or at MAX_SECONDS.
    `source` is the ffmpeg input: the default mic, or a file in check.py."""
    cmd = [tool("ffmpeg"), "-loglevel", "error", "-y", *source,
           "-ar", "16000", "-ac", "1", "-t", str(min(seconds or MAX_SECONDS, MAX_SECONDS)), wav]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    while flag and p.poll() is None and os.path.exists(flag):
        time.sleep(0.05)
    try:
        _, err = p.communicate(b"q" if flag else None, timeout=MAX_SECONDS + 5)  # "q" = finish the wav cleanly
    except subprocess.TimeoutExpired:
        p.kill()
        raise RuntimeError("ffmpeg did not stop")
    if not os.path.exists(wav) or os.path.getsize(wav) < 1000:
        raise RuntimeError("Too short. Hold ⌥ Space while you speak. " + err.decode(errors="replace").strip()[-200:])
    with wave.open(wav) as w:
        samples = array.array("h", w.readframes(w.getnframes()))
    if max(map(abs, samples), default=0) < 10:  # macOS gives pure zeros when the mic is not allowed
        raise RuntimeError("The mic gave only silence. Allow Microphone for Hammerspoon in System Settings.")


def transcribe(wav, lang="en"):
    # --vad: Silero finds the speech first, so room noise gives "" instead of "Thank you." or the PROMPT.
    out = subprocess.run([tool("whisper-cli"), "-m", str(MODEL), "-f", wav, "-l", lang, "-nt", "-np",
                          "--vad", "-vm", str(VAD), "--prompt", PROMPT], capture_output=True, text=True, timeout=120)
    if out.returncode:
        raise RuntimeError("whisper.cpp failed: " + out.stderr.strip()[-200:])
    return " ".join(re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", out.stdout).split())  # drops [BLANK_AUDIO], (music)


def heard_nothing(text):
    """Empty, or only words from PROMPT: whisper echoing its hints, not a command. Never send it live."""
    words = set(re.findall(r"\w+", text.lower()))
    return not words or words <= set(re.findall(r"\w+", PROMPT.lower()))


def post(text, url, dry_run=False):
    body = {"text": text} | ({"dry_run": True} if dry_run else {})
    req = urllib.request.Request(url.rstrip("/") + "/api/command", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never route localhost via a proxy
    try:
        with opener.open(req, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return {"error": json.load(e).get("error") or f"HTTP {e.code}"}
        except ValueError:
            return {"error": f"Inky app answered HTTP {e.code}"}
    except urllib.error.URLError:
        return {"error": f"Inky app is not running at {url}"}


def main():
    ap = argparse.ArgumentParser(description="Hold-to-talk for Inky.")
    how = ap.add_mutually_exclusive_group(required=True)
    how.add_argument("--flag", help="record while this file exists")
    how.add_argument("--seconds", type=float, help="record for N seconds")
    how.add_argument("--text", help="skip recording and send this text")
    ap.add_argument("--dry-run", action="store_true", help='adds "dry_run": true to the POST')
    ap.add_argument("--url", default=os.environ.get("INKY_URL", "http://127.0.0.1:8765"))
    ap.add_argument("--lang", default="en", help="whisper language, or auto")
    ap.add_argument("--mic", default="none:default", help="ffmpeg avfoundation input, e.g. none:2")
    a = ap.parse_args()

    out = {"heard": a.text}
    try:
        if a.text is None:
            with tempfile.TemporaryDirectory() as d:
                wav = os.path.join(d, "voice.wav")
                record(wav, a.flag, a.seconds, ("-f", "avfoundation", "-i", a.mic))
                out["heard"] = transcribe(wav, a.lang)
        if heard_nothing(out["heard"]):
            raise RuntimeError("Didn't catch that. Hold ⌥ Space while you speak.")
        print("heard:", out["heard"], file=sys.stderr)
        out |= post(out["heard"], a.url, a.dry_run)
    except Exception as e:
        out["error"] = str(e)
    if "error" not in out:
        print(f"inky: {out.get('change')} ({out.get('matches_before')} -> {out.get('matches_after')} matches)",
              file=sys.stderr)
    print(json.dumps(out, ensure_ascii=False))
    return 1 if "error" in out else 0


if __name__ == "__main__":
    sys.exit(main())
