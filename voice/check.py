"""Self-check for Inky voice. Run: .venv/bin/python voice/check.py   (no mic, no network, no keys)

say -> 16 kHz wav -> whisper.cpp says "euro"; the hold-to-talk flag stops a recording cleanly;
pure silence is caught; noise gives no words; a prompt echo is never POSTed; listen.py --text POSTs
the right body to a stub /api/command; init.lua parses and its pill states are right under a mock hs.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import listen  # noqa: E402

LINE = "only places with the euro"
REPLY = {"change": "Got it: euro only. I'll skip the Łódź flats.", "rule": {"id": "currency", "field": "currency",
         "op": "eq", "value": "EUR"}, "removed": 4, "applied": False, "matches_before": 12, "matches_after": 8}

tmp = Path(tempfile.mkdtemp())
aiff, wav = str(tmp / "say.aiff"), str(tmp / "say.wav")
subprocess.run(["say", "-o", aiff, LINE], check=True)
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", aiff, "-ar", "16000", "-ac", "1", wav], check=True)
text = listen.transcribe(wav)
assert "euro" in text.lower(), text
print("ok  whisper.cpp:", text)

# Hold-to-talk: record a looping file in real time while the flag exists, then drop the flag.
flag, held = tmp / "held.flag", str(tmp / "held.wav")
flag.touch()
threading.Timer(3.0, flag.unlink).start()
t0 = time.time()
listen.record(held, flag=str(flag), source=("-re", "-stream_loop", "-1", "-i", aiff))
took = time.time() - t0
assert 2.5 < took < 6, took
assert "euro" in listen.transcribe(held).lower()
print(f"ok  flag released after 3 s, recording stopped at {took:.1f} s and transcribes")

try:
    listen.record(str(tmp / "mute.wav"), seconds=1, source=("-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono"))
    raise AssertionError("silence not caught")
except RuntimeError as e:
    assert "silence" in str(e), e
print("ok  a mic that gives only zeros is reported")

# Room noise, no speech. Without VAD these gave the PROMPT back ("Bari, Łódź, euro, ...") or "Thank you.".
for c, a, d in [("pink", 0.02, 5), ("pink", 0.03, 2), ("white", 0.001, 5), ("brown", 0.001, 2), ("brown", 0.02, 2)]:
    noise = str(tmp / f"{c}.wav")
    listen.record(noise, seconds=d, source=("-f", "lavfi", "-i", f"anoisesrc=r=16000:a={a}:c={c}:d={d}:seed=7"))
    heard = listen.transcribe(noise)
    assert listen.heard_nothing(heard), (c, a, d, heard)
print("ok  5 noise-only recordings give no command")

got = []


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        got.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
        body = json.dumps(REPLY).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}"


def run(*args):
    p = subprocess.run([sys.executable, str(HERE / "listen.py"), "--text", LINE, *args],
                       capture_output=True, text=True, timeout=60)
    return p.returncode, json.loads(p.stdout.strip().splitlines()[-1])


code, out = run("--dry-run", "--url", url)
assert code == 0 and got[-1] == ("/api/command", {"text": LINE, "dry_run": True}), got
assert out == {"heard": LINE, **REPLY}, out
code, out = run("--url", url)
assert code == 0 and got[-1] == ("/api/command", {"text": LINE}), got
print("ok  POST /api/command body, with and without --dry-run:", out["change"])
sent = len(got)
p = subprocess.run([sys.executable, str(HERE / "listen.py"), "--text", listen.PROMPT, "--url", url],
                   capture_output=True, text=True, timeout=60)
assert p.returncode == 1 and len(got) == sent and "catch" in json.loads(p.stdout)["error"], (p.stdout, got)
print("ok  whisper echoing its prompt is not sent")
server.shutdown()
server.server_close()

code, out = run("--url", url)  # server gone
assert code == 1 and "not running" in out["error"], out
print("ok  app down ->", out["error"])

# init.lua under a fake Hammerspoon: key events in, pill titles out.
MOCK = r"""
local pill, timers, task, tap = nil, {}, nil, nil
local function obj(t) return setmetatable(t, { __index = function() return function() end end }) end
hs = {
  fs = { attributes = function(p) return io.open(p) and {} end },
  fnutils = { contains = function(t, v) for _, x in ipairs(t) do if x == v then return true end end end },
  styledtext = { fontNames = function() return {} end, new = function(s) return { s = s } end,
    defaultFonts = { boldSystem = { name = "B" }, system = { name = "R" } } },
  image = { imageFromPath = function(p) return io.open(p) and { p = p } end },
  screen = { mainScreen = function() return { frame = function() return { x = 0, y = 0, w = 1440, h = 900 } end } end },
  drawing = { getTextDrawingSize = function(t) return { w = 7 * #t.s, h = 17 } end },
  canvas = { windowLevels = { overlay = 1 }, new = function()
    local c = obj({ els = {} })
    function c:appendElements(...) self.els = { ... } end
    function c:delete() if pill == self then pill = nil end end
    function c:show() pill = self end
    return setmetatable(c, { __index = function(t, k) return rawget(t, "els")[k] or function() end end }) end },
  timer = { doEvery = function() return obj({}) end, doAfter = function(s)
    local t = obj({ s = s }); t.stop = function() timers[t] = nil end; timers[t] = true; return t end },
  task = { new = function(py, cb, args)
    task = obj({ cb = cb, args = args, running = false })
    function task:start() self.running = true end
    function task:isRunning() return self.running end
    return task end },
  json = { decode = function(s) return load("return " .. s)() end },
  keycodes = { map = { space = 49 } },
  eventtap = { event = { types = { keyDown = 10, keyUp = 11 } }, new = function(_, fn)
    tap = obj({ fn = fn }); function tap:isEnabled() return true end; return tap end },
}
dofile(arg[1])
local function key(down, alt, code)
  return tap.fn({ getKeyCode = function() return code or 49 end, getFlags = function() return { alt = alt } end,
    getType = function() return down and 10 or 11 end })
end
local function title() return pill and pill.els[3].text.s end
local function finish(lua) task.running = false; task.cb(0, lua .. "\n", "") end
local function pending() local n = 0 for t in pairs(timers) do n = n + t.s end return n end
local flag = os.getenv("TMPDIR") .. "inky-voice.flag"
local OK = '{heard = "only places with the euro", change = "Euro only", matches_before = 12, matches_after = 8}'

assert(key(true, true) and title() == "Listening…" and io.open(flag) and task.args[2] == "--flag")
assert(pill.els[2].image.p, "the pill shows the octopus png")
assert(key(true, true) and title() == "Listening…", "key repeat")
assert(key(false, true) and title() == "Thinking…" and not io.open(flag))
finish(OK)
assert(title() == "Euro only" and pending() == 4, title())

assert(key(true, true)); finish('{error = "no mic"}')           -- listen.py is done before the key-up
assert(key(false, true) and title() == "Inky didn't get that", title())

assert(key(true, true) and key(false, true) and title() == "Thinking…")
assert(key(true, true) and title() == "Still thinking…", "busy press gives feedback")
assert(key(true, true) and key(false, true), "its repeat and key-up are swallowed")
finish(OK); assert(title() == "Euro only")
assert(not key(true, false) and not key(false, false), "plain Space passes through")
assert(not key(true, true, 0), "⌥ A passes through")
print("mock ok")
"""
lua, luac = shutil.which("lua"), shutil.which("luac")
if lua and luac:
    subprocess.run([luac, "-p", str(HERE / "init.lua")], check=True)
    (tmp / "mock.lua").write_text(MOCK)
    p = subprocess.run([lua, str(tmp / "mock.lua"), str(HERE / "init.lua")], capture_output=True, text=True,
                       env={**os.environ, "TMPDIR": str(tmp) + "/"}, timeout=30)
    assert p.returncode == 0 and "mock ok" in p.stdout, p.stdout + p.stderr
    print("ok  init.lua: Listening → Thinking → change; done-before-release and busy press show the right pill")
else:
    print("skip lua not installed (brew install lua)")

shutil.rmtree(tmp)
print("all checks passed")
