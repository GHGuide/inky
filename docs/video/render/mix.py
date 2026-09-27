#!/usr/bin/env python3
"""Mix voiceover + ducked music bed + timed SFX into a loudness-normalised 48 kHz stereo WAV.

  python3 docs/video/render/mix.py --voice data/voiceover/inky-voiceover.mp3 \
      --music data/film/audio/music.wav --events events.json --out data/film/out/mix.wav

events.json: [{"t": 11.2, "sfx": "whoosh", "gain_db": -2}, ...]
  sfx = a name in --sfx-dir (click, whoosh, ping, pop) or a path to any audio file; gain_db optional.

Levels: while the voice speaks the music sits --music-under LU below it; a sidechain envelope computed
from the voice ducks it by --duck dB, releasing back up in gaps. SFX play at --sfx-db (voice at unity).
The premix is gained to target, true-peak limited, then ffmpeg loudnorm (two-pass, linear) lands it on
--lufs integrated / --tp dBTP. Needs ffmpeg, numpy, scipy.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from scipy import signal
from scipy.io import wavfile
from scipy.ndimage import maximum_filter1d, minimum_filter1d, uniform_filter1d

SR = 48000


def load(path):
    """Decode any audio file to float32 stereo at 48 kHz via ffmpeg."""
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).T.astype(np.float64)


def loudnorm(inp, af_extra='', out=None, I=-16.0, TP=-1.5):
    """Run ffmpeg loudnorm; returns its JSON stats. Without `out` it only measures."""
    af = f'loudnorm=I={I}:TP={TP}:LRA=20{af_extra}:print_format=json'
    cmd = ['ffmpeg', '-hide_banner', '-nostats', '-y', '-i', inp, '-af', af + ',aresample=48000']
    cmd += ['-ar', str(SR), '-ac', '2', '-c:a', 'pcm_s24le', out] if out else ['-f', 'null', '-']
    err = subprocess.run(cmd, capture_output=True, text=True, check=True).stderr
    return json.loads(err[err.rindex('{'):err.rindex('}') + 1])


def measure(x):
    with tempfile.NamedTemporaryFile(suffix='.wav') as f:
        wavfile.write(f.name, SR, x.T.astype(np.float32))
        return loudnorm(f.name)


def duck_envelope(voice, n, duck_db):
    """Per-sample gain (dB, 0..-duck_db) that dips while the voice speaks. Offline, so it looks ahead."""
    hop = SR // 100                                                     # 10 ms frames
    mono = voice.mean(0)
    frames = mono[:len(mono) // hop * hop].reshape(-1, hop)
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(1)) + 1e-9)
    active = (db > np.percentile(db, 95) - 30).astype(float)            # speech vs silence
    active = maximum_filter1d(active, 60)                               # +-0.3 s: bridge word gaps, pre-roll
    active = uniform_filter1d(active, 30)                               # 0.3 s soft ramps
    t = (np.arange(len(active)) + 0.5) * hop / SR
    return np.interp(np.arange(n) / SR, t, -duck_db * active, right=0.0)


def true_peak_limit(x, ceiling_db):
    """Brick-wall gain riding against the 4x-oversampled peak (hold 10 ms, 5 ms smoothing)."""
    pk = np.abs(signal.resample_poly(x, 4, 1, axis=1)).max(0)
    pk = pk[:x.shape[1] * 4].reshape(-1, 4).max(1)
    need = np.minimum(1.0, 10 ** (ceiling_db / 20) / np.maximum(pk, 1e-9))
    g = uniform_filter1d(minimum_filter1d(need, int(0.02 * SR) + 1), int(0.005 * SR))
    return x * g


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--voice', required=True)
    ap.add_argument('--music', required=True)
    ap.add_argument('--events', help='JSON list of {t, sfx, gain_db?}')
    ap.add_argument('--out', required=True)
    ap.add_argument('--sfx-dir', default='data/film/audio/sfx')
    ap.add_argument('--music-under', type=float, default=24.0, help='LU the music sits below the voice while it speaks')
    ap.add_argument('--duck', type=float, default=8.0, help='dB the music dips while the voice speaks')
    ap.add_argument('--sfx-db', type=float, default=-18.0)
    ap.add_argument('--lufs', type=float, default=-16.0)
    ap.add_argument('--tp', type=float, default=-1.5)
    a = ap.parse_args()

    voice, music = load(a.voice), load(a.music)
    events = json.load(open(a.events)) if a.events else []
    sfx = {}
    for e in events:
        if not isinstance(e.get('t'), (int, float)) or e['t'] < 0 or not e.get('sfx'):
            sys.exit(f'bad event {e!r}: need {{"t": seconds >= 0, "sfx": name}}')
        p = e['sfx'] if os.path.isfile(e['sfx']) else os.path.join(a.sfx_dir, e['sfx'] + '.wav')
        if not os.path.isfile(p):
            sys.exit(f'sfx not found: {p}')
        sfx.setdefault(e['sfx'], load(p))

    n = max(voice.shape[1], music.shape[1],
            *(int(e['t'] * SR) + sfx[e['sfx']].shape[1] for e in events))
    mix = np.zeros((2, n))
    mix[:, :voice.shape[1]] += voice

    # music: its un-ducked level is (voice - under + duck) so under the voice it lands at voice - under
    vi, mi = float(measure(voice)['input_i']), float(measure(music)['input_i'])
    base_db = vi - a.music_under + a.duck - mi
    gain = 10 ** ((base_db + duck_envelope(voice, n, a.duck)) / 20)
    mix[:, :music.shape[1]] += music * gain[:music.shape[1]]

    for e in events:
        s, i = sfx[e['sfx']], int(round(e['t'] * SR))
        mix[:, i:i + s.shape[1]] += s * 10 ** ((a.sfx_db + e.get('gain_db', 0)) / 20)

    # gain to target, true-peak limit with 0.7 dB headroom, then two-pass linear loudnorm for the last bit
    mix *= 10 ** ((a.lufs - float(measure(mix)['input_i'])) / 20)
    mix = true_peak_limit(mix, a.tp - 0.7)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix='.wav') as f:
        wavfile.write(f.name, SR, mix.T.astype(np.float32))
        m = loudnorm(f.name, I=a.lufs, TP=a.tp)
        extra = (f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
                 f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
        r = loudnorm(f.name, extra, a.out, I=a.lufs, TP=a.tp)
    print(f"{a.out}: {n / SR:.2f}s  pre-norm: voice {vi:.1f} LUFS, music {vi - a.music_under:.1f} LUFS under voice / "
          f"{vi - a.music_under + a.duck:.1f} in gaps, {len(events)} sfx  ->  "
          f"{r['output_i']} LUFS, {r['output_tp']} dBTP, LRA {r['output_lra']} ({r['normalization_type']})")


if __name__ == '__main__':
    main()
