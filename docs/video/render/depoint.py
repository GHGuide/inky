"""Retouch the macOS mouse pointer out of screen captures.

  python3 docs/video/render/depoint.py data/film/assets/web/n8n-*.png     # -> data/film/assets/web/clean/<name>.png

Finds the white arrow (solid white body, tip at the top-left, straight left edge, dark outline) and fills it
with the best-matching nearby patch of background. Prints what it patched; files with no pointer are copied as-is.
"""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi


def read(p):
    st = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                             "stream=width,height", "-of", "json", str(p)]))["streams"][0]
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(p), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    return np.frombuffer(raw, np.uint8).reshape(st["height"], st["width"], 3).copy()


def write(p, a):
    h, w = a.shape[:2]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-i", "-", str(p)],
                   input=a.tobytes(), check=True)


def pointers(a):
    """Bounding slices of arrow-shaped white blobs with a dark rim."""
    lab, _ = ndi.label(a.min(2) >= 228)
    found = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if not (28 <= h <= 64 and 16 <= w <= 46): continue
        m = lab[sl] == i
        if not (0.28 <= m.mean() <= 0.7): continue
        if np.nonzero(m[0])[0].min() > 5: continue                       # tip at the top-left
        firsts = np.array([np.nonzero(r)[0][0] if r.any() else 99 for r in m[: int(h * 0.65)]])
        if (firsts > 4).mean() > 0.15: continue                            # straight left edge
        widths = m[: int(h * 0.55)].sum(1)
        if np.corrcoef(np.arange(len(widths)), widths)[0, 1] < 0.8: continue  # widens downwards
        y0, x0 = max(sl[0].start - 7, 0), max(sl[1].start - 7, 0)
        box = a[y0:sl[0].stop + 7, x0:sl[1].stop + 7].astype(int)
        mm = np.zeros(box.shape[:2], bool); mm[sl[0].start - y0:sl[0].stop - y0, sl[1].start - x0:sl[1].stop - x0] = m
        rim = ndi.binary_dilation(mm, iterations=6) & ~ndi.binary_dilation(mm, iterations=3)
        if np.median(box[rim].max(1)) > 200: continue                      # rim must not be white
        rr = box[ndi.binary_dilation(mm, iterations=4) & ~mm]
        if np.median(rr[:, 0] - rr[:, 2]) < 20: continue                    # this capture's pointer has a warm (coral) outline
        found.append((sl, m))
    return found


def patch(a, sl, m, grow=28, max_diff=6):
    """Cover the pointer and its glow with the nearby patch whose surroundings match best; skip it if nothing matches."""
    H, W = a.shape[:2]
    mask = np.zeros((H, W), bool); mask[sl] = m
    mask = ndi.binary_dilation(mask, iterations=grow)
    ring = ndi.binary_dilation(mask, iterations=8) & ~mask
    ys, xs = np.nonzero(mask); ry, rx = np.nonzero(ring)
    h, w = int(np.ptp(ys)) + 1, int(np.ptp(xs)) + 1
    ref = a[ry, rx].astype(np.int16)
    best = None
    for dy in range(-3 * h, 3 * h + 1, 4):
        for dx in range(-3 * w, 3 * w + 1, 4):
            if abs(dy) < h and abs(dx) < w: continue                           # source must not overlap the pointer
            if ry.min() + dy < 0 or rx.min() + dx < 0 or ry.max() + dy >= H or rx.max() + dx >= W: continue
            cost = np.abs(ref - a[ry + dy, rx + dx]).mean()
            if best is None or cost < best[0]: best = (cost, dy, dx)
    if best is None or best[0] > max_diff: return None                         # busy background: leave it
    _, dy, dx = best
    a[ys, xs] = a[ys + dy, xs + dx]
    return (int(xs.min()), int(ys.min()), w, h, round(float(best[0]), 1))


def _selfcheck():
    a = np.full((200, 200, 3), 40, np.uint8)
    for y in range(48): a[56 + y, 55:55 + y * 2 // 3 + 10] = (200, 90, 70)  # a crude arrow: coral glow...
    for y in range(40): a[61 + y, 61:61 + y * 2 // 3 + 2] = 255          # ...around a white body
    assert len(pointers(a)) == 1


if __name__ == "__main__":
    _selfcheck()
    for f in map(Path, sys.argv[1:]):
        a = read(f)
        found = pointers(a)
        boxes = [patch(a, sl, m) for sl, m in found]   # None = left in place (nothing similar nearby)
        out = f.parent / "clean" / f.name
        out.parent.mkdir(exist_ok=True)
        write(out, a)
        print(f"{f.name}: {len(boxes)} pointer(s) {boxes}")
