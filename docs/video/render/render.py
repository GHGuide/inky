"""Frame-exact video compositor: timeline.json -> compose.html (headless Chrome) -> ffmpeg -> mp4 with the voice-over.

  .venv/bin/python docs/video/render/render.py                      # full 1920x1080 render -> data/film/out/inky-video.mp4
  .venv/bin/python docs/video/render/render.py --scale 0.5          # fast preview -> inky-video-preview.mp4
  .venv/bin/python docs/video/render/render.py --from 40 --to 56    # one beat -> inky-video-40-56.mp4
  .venv/bin/python docs/video/render/render.py --still 33.5         # one PNG -> data/film/out/stills/still-33.50.png

Assets are read from data/film/assets/ (missing ones render as a labelled placeholder). Video clips are
pre-extracted once to 30 fps JPEG sequences under data/film/cache/; the page swaps img src per frame.
"""
import argparse, asyncio, glob, hashlib, json, re, subprocess, sys, threading, time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CACHE = ROOT / "data/film/cache"
OUT = ROOT / "data/film/out"


def probe(p):
    j = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                            "stream=width,height:format=duration", "-of", "json", str(p)]))
    st = j["streams"][0]
    return st["width"], st["height"], float(j["format"].get("duration") or 0)


def extract(p, fps, vf=""):
    """Clip -> JPEG sequence at `fps` (after an optional ffmpeg filter, e.g. a crop), cached by path, size, mtime and filter."""
    key = hashlib.sha1(f"{p.resolve()}|{p.stat().st_size}|{p.stat().st_mtime}|{fps}|{vf}".encode()).hexdigest()[:10]
    d = CACHE / f"{p.stem}-{key}"
    if not (d / ".done").exists():
        d.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-vf", f"fps={fps},{vf + ',' if vf else ''}scale='min(1920,iw)':-2",
                        "-q:v", "2", str(d / "%05d.jpg")], check=True)
        (d / ".done").write_text("ok")
    return d, len(list(d.glob("*.jpg")))


def url(p):
    return "/" + Path(p).resolve().relative_to(ROOT).as_posix()


def inv_map(m, s):
    """source time -> local time through a piecewise-linear [[local, source], ...] map."""
    if len(m) == 1: return m[0][0] + s - m[0][1]
    for (a, as_), (b, bs) in zip(m, m[1:]):
        if as_ <= s <= bs and bs > as_: return a + (s - as_) * (b - a) / (bs - as_)
    (a, as_), (b, bs) = (m[0], m[1]) if s < m[0][1] else (m[-2], m[-1])
    return a + (s - as_) * (b - a) / ((bs - as_) or 1)


def seg_rate(m, s):
    """playback rate of the map segment holding source time s (huge inside a jump cut)."""
    for (a, as_), (b, bs) in zip(m, m[1:]):
        if as_ <= s <= bs: return (bs - as_) / max(b - a, 1e-6)
    return 1


def manifest_events(man, name):
    """Events for one clip, from whichever shape the recorder wrote: {clips: {name: {events}}}, {name: {events}},
    {name: [...]}, or a flat list/`events` with a `clip` field. Each event: t|time|at (s), x, y (page px), type."""
    stem = Path(name).stem
    for cand in ((man.get("clips") or {}) if isinstance(man, dict) else {}, man if isinstance(man, dict) else {}):
        for k in (name, stem):
            v = cand.get(k)
            if isinstance(v, dict) and "events" in v: return v["events"], v
            if isinstance(v, list): return v, {}
    flat = man if isinstance(man, list) else (man.get("events") or []) if isinstance(man, dict) else []
    evs = [e for e in flat if isinstance(e, dict) and Path(str(e.get("clip", e.get("file", "")))).stem == stem]
    return evs, {}


def parse_srt(p):
    ts = lambda s: sum(float(x) * m for x, m in zip(s.replace(",", ".").split(":"), (3600, 60, 1)))
    caps = []
    for block in re.split(r"\n\s*\n", Path(p).read_text().strip()):
        lines = block.strip().splitlines()
        a, b = lines[1].split(" --> ")
        caps.append({"start": ts(a), "end": ts(b), "text": "\n".join(lines[2:4])})
    return caps


def compile_timeline(tl, fps):
    assets = ROOT / tl.get("assets", "data/film/assets")
    shots, overlays = [], list(tl.get("overlays", []))
    for s in tl["shots"]:
        s = dict(s)
        s.setdefault("id", f"s{len(shots)}")
        src = s.get("src")
        if s["type"] == "still" and src and (isinstance(src, list) or "*" in src):   # stills sharing the shot's time
            files = [f for g in ([src] if isinstance(src, str) else src) for f in sorted(glob.glob(str(assets / g)))]
            if not files: s["src"] = src if isinstance(src, str) else src[0]
            if files:
                w = s.get("weights") or [1] * len(files)
                w = (w + [1] * len(files))[:len(files)]
                t, span = s["start"], s["end"] - s["start"]
                for i, f in enumerate(files):
                    d = span * w[i] / sum(w)
                    sub = {**s, "id": f"{s['id']}-{i}", "src": str(Path(f).relative_to(assets)), "start": t, "end": t + d}
                    if i: sub["transition"] = s.get("seq_transition", {"type": "fade", "dur": .25})
                    shots.append(sub); t += d
                continue
        shots.append(s)
    missing = []
    for s in shots:
        if s["type"] in ("card", "endcard"):   # inline SVGs so the page can animate them (logo blink)
            for k in ("logo", "qr"):
                if s.get(k): s[k + "Svg"] = (ROOT / s[k]).read_text()
            continue
        p = assets / s["src"]
        alt = s.pop("alt", None)   # stand-in asset (with its own camera) while the named one is missing
        if not p.exists() and alt and (assets / alt["src"]).exists():
            s.update(alt); p = assets / s["src"]; print("stand-in:", s["src"], "for", s["id"])
        if not p.exists():
            s["missing"] = True; missing.append(s["src"])
            s.setdefault("w", 1920 if s["type"] != "phone" else 1179); s.setdefault("h", 1080 if s["type"] != "phone" else 2556)
            continue
        try:
            s["w"], s["h"], dur = probe(p)
            if p.suffix.lower() in (".mp4", ".mov", ".webm"):
                d, n = extract(p, fps, s.get("vf", ""))
                s["w"], s["h"] = probe(next(d.glob("*.jpg")))[:2]
        except (subprocess.CalledProcessError, KeyError, IndexError):   # still being written, or broken
            print("unreadable, placeholder:", s["src"])
            s["missing"] = True; missing.append(s["src"]); s.setdefault("w", 1920); s.setdefault("h", 1080)
            continue
        if p.suffix.lower() in (".mp4", ".mov", ".webm"):
            s["frames"] = {"base": url(d) + "/", "count": n, "fps": fps}
            s["srcdur"] = dur
            s["map"] = s.get("map") or [[0, s.get("in", 0)], [1, s.get("in", 0) + s.get("rate", 1)]]
        else:
            s["url"] = url(p)
            if s.get("crop"):   # show only [x, y, w, h] of the image
                s["nw"], s["nh"] = s["w"], s["h"]; s["w"], s["h"] = s["crop"][2], s["crop"][3]
    # cursors from the recorder's manifest (page coords at 1920x1080, source-clip time)
    man_p = assets / tl.get("manifest", "app/manifest.json")
    man = json.loads(man_p.read_text()) if man_p.exists() else None
    for s in shots:
        cur = s.pop("cursor", None)
        if not cur or s.get("missing"): continue
        cur = cur if isinstance(cur, dict) else {}
        pts = cur.get("points")
        if pts is None and man is not None:
            evs, meta = manifest_events(man, s["src"])
            m = s.get("map") or [[0, 0], [1, 1]]
            pts = []
            pw, ph = meta.get("width", 1920), meta.get("height", 1080)
            for e in evs:
                kind = str(e.get("type") or e.get("kind") or e.get("action") or "click").lower()
                if e.get("x") is None or kind in ("scroll", "wait", "key", "note") or e["y"] > ph or e["x"] > pw: continue
                st = float(e.get("t", e.get("time", e.get("at", 0))))
                if seg_rate(m, st) > 6: continue          # inside a cut (model wait): drop it
                pt = {"t": round(inv_map(m, st), 3), "x": e["x"], "y": e["y"], "click": "click" in kind}
                if e.get("t_start") is not None:          # the overlay moves at human speed even when the clip is sped up
                    pt["move"] = max(0.45, round(pt["t"] - inv_map(m, float(e["t_start"])), 3))
                pts.append(pt)
            pts = [p for p in pts if 0 <= p["t"] <= s["end"] - s["start"]]
            cur.setdefault("page", meta.get("page") or meta.get("viewport") or man.get("page") or man.get("viewport") or [1920, 1080])
            if isinstance(cur["page"], dict): cur["page"] = [cur["page"].get("width", 1920), cur["page"].get("height", 1080)]
        if pts:
            overlays.append({"type": "cursor", "shot": s["id"], "start": s["start"], "end": s["end"], "fade": .2,
                             "space": "page", **cur, "points": sorted(pts, key=lambda p: p["t"])})
    caps = []
    c = tl.get("captions")
    if c:
        caps = parse_srt(ROOT / c["srt"])
        for cap, (a, b) in zip(caps, c.get("times", [])):
            cap["start"], cap["end"] = a, b
    return {"shots": shots, "overlays": overlays, "captions": caps, "caption_keys": tl.get("caption_keys", []), "caption_top": tl.get("caption_top", []), "caption_left": tl.get("caption_left", []),
            "duration": tl["duration"]}, missing


def sfx_events(tl):
    """Sound cues from the compiled timeline: click on cursor clicks, whoosh on beat changes, pop when a card or chip
    appears, ping when a Telegram message appears. Cues closer than 0.15 s keep the stronger one."""
    shots = {s["id"]: s for s in tl["shots"]}
    ev = []
    for o in tl["overlays"]:
        if o["type"] == "cursor":
            base = shots[o["shot"]]["start"] if o.get("shot") else 0
            ev += [(round(base + p["t"], 3), "click", -10) for p in o["points"] if p.get("click") and o["start"] <= base + p["t"] < o["end"]]
        elif o["type"] == "chapters" and o["start"] > 5:
            ev += [(it["from"], "whoosh", -6) for it in o["items"][1:]]
        elif o["type"] in ("compare", "timesaved", "badges", "lower_third", "counter") or (o["type"] == "stamp" and o.get("big")):
            ev.append((o["start"], "pop", -12 if o["start"] < 11 else -9))
        elif o["type"] == "scoreboard":
            ev.append((o["start"], "pop", -12))
    ev += [(s["start"], "whoosh", -6) for s in tl["shots"] if s["type"] == "endcard"]
    ev += [(s["start"], "ping", -8) for s in tl["shots"] if str(s.get("src", "")).startswith("tg/")]
    rank = {"ping": 3, "whoosh": 2, "pop": 1, "click": 0}
    out = []
    for t, k, g in sorted(ev, key=lambda e: (e[0], -rank[e[1]])):
        if out and t - out[-1]["t"] < 0.15:
            if rank[k] > rank[out[-1]["sfx"]]: out[-1] = {"t": t, "sfx": k, "gain_db": g}
            continue
        out.append({"t": t, "sfx": k, "gain_db": g})
    return out


def serve():
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    h = partial(Quiet, directory=str(ROOT))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


def _selfcheck():
    m = [[0, 1.3], [0.9, 2.8], [4.6, 9.66]]
    assert abs(inv_map(m, 2.8) - 0.9) < 1e-9 and abs(inv_map(m, 9.66 + 1) - (4.6 + 3.7 / 6.86)) < 1e-6 and abs(inv_map(m, 0.3) + 0.6) < 1e-6


async def main():
    _selfcheck()
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", default=str(HERE / "timeline.json"))
    ap.add_argument("--from", dest="t0", type=float, default=0)
    ap.add_argument("--to", dest="t1", type=float)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--scale", type=float, default=1)
    ap.add_argument("--still", type=float, action="append", help="write PNG frame(s) at these seconds and stop")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out")
    ap.add_argument("--no-mix", action="store_true", help="bare voice-over instead of the music + sfx mix")
    ap.add_argument("--small", action="store_true", help="also write a small copy (crf 25, capped bitrate) next to the output")
    a = ap.parse_args()
    tl_raw = json.loads(Path(a.timeline).read_text())
    t_start = time.time()
    tl, missing = compile_timeline(tl_raw, a.fps)
    tl["scale"] = a.scale
    for m in sorted(set(missing)): print("placeholder:", m)
    t1 = a.t1 if a.t1 is not None else tl["duration"]
    vw, vh = round(1920 * a.scale), round(1080 * a.scale)
    port = serve()
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        br = await pw.chromium.launch(channel="chrome", headless=True, args=["--force-color-profile=srgb", "--hide-scrollbars"])
        ctx = await br.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=1)
        n = 1 if a.still else max(1, a.workers)
        pages = []
        for _ in range(n):
            pg = await ctx.new_page()
            pg.on("pageerror", lambda e: print("page error:", e, file=sys.stderr))
            await pg.goto(f"http://127.0.0.1:{port}/docs/video/render/compose.html")
            await pg.evaluate("tl => setup(tl)", tl)
            pages.append(pg)
        if a.still:
            (OUT / "stills").mkdir(exist_ok=True)
            for t in a.still:
                await pages[0].evaluate("t => renderAt(t)", t)
                p = OUT / "stills" / f"still-{t:06.2f}.png"
                await pages[0].screenshot(path=str(p))
                print(p)
            await br.close(); return
        out = Path(a.out) if a.out else OUT / ("inky-video" + ("-preview" if a.scale != 1 else "")
                                               + (f"-{a.t0:g}-{t1:g}" if a.t0 or a.t1 is not None else "") + ".mp4")
        audio = ROOT / tl_raw["audio"] if tl_raw.get("audio") else None
        mx = tl_raw.get("mix")
        if mx and not a.no_mix and (HERE / "mix.py").exists():       # voice + ducked music + sfx -> one track
            evp, mixp = OUT / "sfx-events.json", OUT / "mix.wav"
            evp.write_text(json.dumps(sfx_events(tl), indent=1))
            subprocess.run(["python3", str(HERE / "mix.py"), "--voice", str(audio), "--music", str(ROOT / mx["music"]),
                            "--events", str(evp), "--out", str(mixp), *mx.get("args", [])], check=True, cwd=ROOT)
            audio = mixp
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(a.fps), "-c:v", "mjpeg", "-i", "-"]
        if audio: cmd += ["-ss", f"{a.t0:.3f}", "-t", f"{t1 - a.t0:.3f}", "-i", str(audio), "-map", "0:v", "-map", "1:a"]
        cmd += ["-vf", "scale=in_range=pc:out_range=tv,format=yuv420p", "-c:v", "libx264", "-crf", "17",
                "-preset", "medium" if a.scale == 1 else "veryfast", "-pix_fmt", "yuv420p", "-color_range", "tv", "-r", str(a.fps)]
        if audio: cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd += ["-movflags", "+faststart", str(out)]
        ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        frames = list(range(round(a.t0 * a.fps), round(t1 * a.fps)))

        async def shoot(pg, i):
            await pg.evaluate("t => renderAt(t)", i / a.fps)
            return await pg.screenshot(type="jpeg", quality=95)

        last = time.time()
        for k in range(0, len(frames), n):
            batch = frames[k:k + n]
            for img in await asyncio.gather(*(shoot(pages[j], i) for j, i in enumerate(batch))):
                ff.stdin.write(img)
            if time.time() - last > 10:
                last = time.time(); print(f"  {batch[-1] / a.fps:6.1f} s of {t1:.0f}", flush=True)
        ff.stdin.close(); ff.wait()
        await br.close()
    print(f"{out}  ({len(frames)} frames, {time.time() - t_start:.0f} s)")
    if a.small:
        small = out.with_name(out.stem + "-small.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out), "-c:v", "libx264", "-crf", "25", "-maxrate", "1.6M", "-bufsize", "3.2M",
                        "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(small)], check=True)
        print(small, f"{small.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    asyncio.run(main())
