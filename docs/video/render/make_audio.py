#!/usr/bin/env python3
"""Synthesize the Inky film's music bed and UI SFX locally (numpy + scipy, no samples, no downloads).

  python3 docs/video/render/make_audio.py [--out data/film/audio]

Writes music.wav (119 s, 48 kHz stereo, peak -1 dBFS), beats.json (bar/beat grid + cues) and
sfx/{click,whoosh,ping,pop}.wav, then prints objective checks (peak, RMS, DC, largest sample jump).
"""
import argparse
import json
import os

import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
DUR = 119.0
N = int(SR * DUR)
BAR = 2.6                  # 92.3 BPM: bar lines land exactly on the 11.2 s and 97.0 s cues
BEAT = BAR / 4
SW = 0.08 * BEAT           # 8th-note swing
T0 = 0.8                   # first bar line
DEMO, FINALE, LAST, FADE = 11.2, 97.0, 115.2, 116.0
NBARS = int(round((LAST - T0) / BAR)) + 1   # bars 0..44, bar 44 (115.2) is the final chord
# Fmaj7 - Am7 - Dm7 - Cmaj7 as (bass midi, voicing midi)
CHORDS = [(41, [53, 57, 60, 64]), (45, [55, 57, 60, 64]), (38, [53, 57, 60, 62]), (36, [52, 55, 59, 62])]
rng = np.random.default_rng(7)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def filt(x, kind, fc, order=2, zero_phase=False):
    sos = signal.butter(order, fc, kind, fs=SR, output='sos')
    return signal.sosfiltfilt(sos, x, axis=-1) if zero_phase else signal.sosfilt(sos, x, axis=-1)


def tt(dur):
    return np.arange(int(dur * SR)) / SR


def fades(x, a, r):
    """Raised-cosine attack/release (seconds) so every event starts and ends at zero."""
    n = x.shape[-1]
    e = np.ones(n)
    na, nr = min(n, max(1, int(a * SR))), min(n, max(1, int(r * SR)))
    e[:na] *= 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, na))
    e[n - nr:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, nr))
    return x * e


def add(buf, t, x, pan=0.0):
    """Mix mono x (equal-power pan -1..1) or stereo x into stereo buf at time t."""
    if x.ndim == 1:
        a = (pan + 1) * np.pi / 4
        x = np.stack([x * np.cos(a), x * np.sin(a)])
    i = int(round(t * SR))
    m = min(x.shape[1], buf.shape[1] - i)
    if m > 0:
        buf[:, i:i + m] += x[:, :m]


def noise(dur):
    return rng.standard_normal(int(dur * SR))


# ---------------------------------------------------------------- instruments
def epiano(f, vel, dur):
    t = tt(dur)
    idx = 0.3 + 1.3 * vel * np.exp(-t * 5)                        # FM "bark" on the attack only
    x = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * t))
    x += 0.05 * vel * np.sin(2 * np.pi * f * 7 * t) * np.exp(-t * 60)   # tine
    return fades(x * np.exp(-t * (0.9 + f / 900)) * vel, 0.005, 0.25)


def pad(f, dur, att, rel, amp):
    t = tt(dur)
    out = np.zeros((2, len(t)))
    for c, det in enumerate((-0.0035, 0.0035)):                   # +-6 cents, one per side
        ph = rng.uniform(0, 2 * np.pi)
        out[c] = sum(np.sin(2 * np.pi * k * f * (1 + det) * t + k * ph) * 0.5 ** (k - 1) / k for k in range(1, 5))
    return fades(out * amp, att, rel)


def bass(f, vel, dur):
    t = tt(dur)
    x = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) + 0.1 * np.sin(6 * np.pi * f * t)
    return fades(np.tanh(1.4 * x) * vel * (0.55 + 0.45 * np.exp(-t * 3)), 0.01, 0.08)


def kick(vel):
    t = tt(0.4)
    f = 46 + 64 * np.exp(-t * 28)
    return fades(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 10) * vel, 0.002, 0.05)


def rim(vel):
    t = tt(0.25)
    x = 0.6 * filt(noise(0.25), 'band', [1200, 5000]) * np.exp(-t * 30) + 0.4 * np.sin(2 * np.pi * 185 * t) * np.exp(-t * 28)
    return fades(x * vel, 0.002, 0.03)


def hat(vel):
    t = tt(0.12)
    return fades(filt(noise(0.12), 'high', 7000) * np.exp(-t * 70) * vel, 0.001, 0.02)


def shaker(vel):
    t = tt(0.1)
    return fades(filt(noise(0.1), 'band', [3500, 9000]) * np.exp(-t * 50) * vel, 0.012, 0.02)


def riser(dur):
    t = tt(dur)
    n, w = noise(dur), (t / dur) ** 2
    return fades((filt(n, 'low', 1200) * (1 - w) + filt(n, 'low', 5000) * w) * w, 0.05, 0.06)


# ---------------------------------------------------------------- arrangement
def music():
    tonal = np.zeros((2, N))
    low = np.zeros((2, N))
    drums = np.zeros((2, N))
    rims = np.zeros((2, N))
    for b in range(NBARS):
        t = T0 + b * BAR
        root, voicing = CHORDS[b % 4]
        intro, finale, last = t < DEMO, t >= FINALE, b == NBARS - 1

        # pad: bar 0 swells in from t=0; chords crossfade over bar lines
        start = 0.0 if b == 0 else t - 0.15
        dur = (DUR - start) if last else (t + BAR + 0.9 - start)
        for m in voicing:
            add(tonal, start, pad(hz(m), dur, 1.2 if b == 0 else 0.45, 0.05 if last else 1.0, 0.035))
            if finale:  # shimmer an octave up for the finale
                add(tonal, start, pad(hz(m + 12), dur, 0.8, 0.05 if last else 1.0, 0.012))

        # electric piano comping
        vs = 0.55 if intro else (0.9 if finale else 0.8)
        if last:
            hits = [(0, 0.9, voicing, DUR - t)]
        elif intro:
            hits = [(0, 1.0, voicing, 2.4)]
        else:
            hits = [(0, 1.0, voicing, 1.6), (1.5, 0.45, voicing[-2:], 1.0), (2.5, 0.7, voicing, 1.6)]
        for beat, v, notes, d in hits:
            for j, m in enumerate(notes):
                tj = t + beat * BEAT + (SW if beat % 1 else 0) + j * 0.012 + rng.normal(0, 0.003)
                pan = (j / max(1, len(notes) - 1) - 0.5) * 0.5
                add(tonal, max(0.0, tj), epiano(hz(m), vs * v * rng.uniform(0.9, 1.05), d) * 0.13, pan)

        # bass: enters at bar 1
        if b >= 1:
            if intro:
                add(low, t, bass(hz(root), 0.7, BAR * 0.95) * 0.16)
            elif last:
                add(low, t, bass(hz(root), 0.8, DUR - t) * 0.16)
            else:
                add(low, t, bass(hz(root), 0.9, BEAT * 2.2) * 0.16)
                add(low, t + 2.5 * BEAT + SW, bass(hz(root), 0.6, BEAT * 1.3) * 0.16)

        # muted pulse: soft kick on 1 and 3 from bar 1; rim, hats, shaker from the demo lift
        if 1 <= b and not last:
            kv = 0.45 if intro else 0.8
            add(low, t, kick(kv) * 0.28)
            add(low, t + 2 * BEAT, kick(kv * 0.8) * 0.28)
            if not intro:
                for k in (1, 3):
                    add(rims, t + k * BEAT + rng.normal(0, 0.002), rim(0.5) * 0.07, -0.1)
                for e in range(8):
                    add(drums, t + e * BEAT / 2 + (SW if e % 2 else 0) + rng.normal(0, 0.002),
                        hat((0.55 if e % 2 else 0.3) * rng.uniform(0.85, 1.1)) * 0.05, 0.35)
                for s in range(16):
                    add(drums, t + s * BEAT / 4 + (SW / 2 if s % 2 else 0),
                        shaker([0.6, 0.3, 0.45, 0.3][s % 4] * rng.uniform(0.85, 1.1)) * 0.025, -0.35)

    add(drums, DEMO - 1.0, riser(1.0) * 0.04)
    add(drums, FINALE - 1.3, riser(1.3) * 0.04)

    # brightness automation: crossfade dark/bright low-passed copies (zero-phase so they sum cleanly)
    tg = np.arange(N) / SR
    bright = np.interp(tg, [0, DEMO - 0.8, DEMO, FINALE - 1.3, FINALE, LAST, DUR], [0.15, 0.2, 0.6, 0.6, 1.0, 1.0, 0.4])
    tonal = filt(tonal, 'low', 2000, zero_phase=True) * (1 - bright) + filt(tonal, 'low', 6500, zero_phase=True) * bright

    # synthetic stereo room: decorrelated exponentially decaying noise IRs
    irs = []
    for _ in range(2):
        t = tt(2.2)
        ir = np.concatenate([np.zeros(int(0.02 * SR)), filt(rng.standard_normal(len(t)) * np.exp(-6.9 * t / 2.2), 'low', 4500)])
        irs.append(ir / np.sqrt((ir ** 2).sum()))
    send = tonal * 0.45 + rims * 0.6
    wet = filt(np.stack([signal.oaconvolve(send[c], irs[c])[:N] for c in range(2)]), 'high', 250)

    mix = tonal + low + drums + rims + 0.35 * wet
    mix = filt(mix, 'low', 12000, order=1)              # take the edge off
    mix /= np.abs(mix).max()
    mix = np.tanh(1.3 * mix) / np.tanh(1.3)             # gentle tape-ish saturation
    mix = filt(mix, 'high', 28)                         # DC / subsonic (after the saturation)
    swell = np.clip(tg / 1.2, 0, 1)
    out = np.clip((DUR - tg) / (DUR - FADE), 0, 1)
    mix *= (0.5 - 0.5 * np.cos(np.pi * swell)) * (0.5 - 0.5 * np.cos(np.pi * out))
    return mix * 10 ** (-1 / 20) / np.abs(mix).max()


# ---------------------------------------------------------------- sfx
def sfx_click():
    t = tt(0.025)
    x = np.sin(2 * np.pi * 1900 * t) * np.exp(-t / 0.0035) + 0.25 * filt(noise(0.025), 'band', [2500, 7000]) * np.exp(-t / 0.0012)
    return fades(x, 0.0004, 0.004)


def sfx_whoosh():
    d = 0.35
    t = tt(d)
    n = noise(d)
    env = np.sin(np.pi * (t / d) ** 1.3) ** 2               # builds, peaks ~60 %, falls away
    x = (filt(n, 'band', [250, 1200], zero_phase=True) * (1 - env) + filt(n, 'band', [600, 4000], zero_phase=True) * env) * env
    a = (np.linspace(-0.5, 0.5, len(t)) + 1) * np.pi / 4   # drifts left to right
    return fades(filt(np.stack([x * np.cos(a), x * np.sin(a)]), 'low', 5000), 0.005, 0.02)


def sfx_ping():
    d = 0.6
    out = np.zeros((2, int(d * SR)))
    for t0, f, v, pan in ((0.0, 987.77, 0.8, -0.15), (0.085, 1318.51, 1.0, 0.15)):   # B5 -> E6
        t = tt(d - t0)
        x = (np.sin(2 * np.pi * f * t) + 0.2 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-t * 18)
             + 0.08 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-t * 40)) * np.exp(-t * 7) * v
        add(out, t0, fades(x, 0.002, 0.01), pan)
    return fades(filt(out, 'low', 9000), 0.0, 0.08)


def sfx_pop():
    t = tt(0.08)
    f = 380 + 900 * (1 - np.exp(-t / 0.012))               # quick upward chirp = bubble
    return fades(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.018), 0.0008, 0.01)


# ---------------------------------------------------------------- io + checks
def write(path, x, peak_db):
    x = np.atleast_2d(x)
    if x.shape[0] == 1:
        x = np.vstack([x, x])
    x = x * 10 ** (peak_db / 20) / np.abs(x).max()
    dither = (rng.random(x.shape) - rng.random(x.shape)) / 32768
    wavfile.write(path, SR, np.clip(np.round((x + dither) * 32767), -32768, 32767).astype(np.int16).T)
    y = wavfile.read(path)[1].T / 32768.0   # check the file as written
    rms = 20 * np.log10(np.sqrt((y ** 2).mean()))
    jump = np.abs(np.diff(y, axis=1)).max()
    print(f"{path}: {y.shape[1] / SR:.3f}s peak {20 * np.log10(np.abs(y).max()):.2f} dBFS  rms {rms:.1f} dBFS  "
          f"dc {np.abs(y.mean(axis=1)).max():.1e}  max-jump {jump:.3f}  ends {np.abs(y[:, [0, -1]]).max():.1e}  "
          f"clipped {(np.abs(y) >= 1).sum()}")
    return y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='data/film/audio')
    out = ap.parse_args().out
    os.makedirs(os.path.join(out, 'sfx'), exist_ok=True)

    m = write(os.path.join(out, 'music.wav'), music(), -1.0)
    # click check: largest jump within +-5 ms of every bar line vs the file's typical jump
    d = np.abs(np.diff(m, axis=1)).max(0)
    at_bars = max(d[int((T0 + b * BAR - 0.005) * SR):int((T0 + b * BAR + 0.005) * SR)].max() for b in range(NBARS))
    print(f"  bar-line max jump {at_bars:.4f} vs 99.9th pct {np.percentile(d, 99.9):.4f}")

    bars = [round(T0 + b * BAR, 4) for b in range(NBARS)]
    beats = [round(T0 + k * BEAT, 4) for k in range((NBARS - 1) * 4 + 1)]
    names = ['Fmaj7', 'Am7', 'Dm7', 'Cmaj7']
    with open(os.path.join(out, 'beats.json'), 'w') as f:
        json.dump({'bpm': round(240 / BAR, 3), 'beat_sec': BEAT, 'bar_sec': BAR, 'first_bar': T0,
                   'bars': bars, 'bar_chords': [names[b % 4] for b in range(NBARS)], 'beats': beats,
                   'cues': {'swell': [0.0, 1.2], 'demo_lift': DEMO, 'finale_lift': FINALE,
                            'resolve': LAST, 'fade': [FADE, DUR]}}, f, indent=1)

    for name, fn, pk in (('click', sfx_click, -1), ('whoosh', sfx_whoosh, -3), ('ping', sfx_ping, -2), ('pop', sfx_pop, -2)):
        write(os.path.join(out, 'sfx', name + '.wav'), fn(), pk)


if __name__ == '__main__':
    main()
