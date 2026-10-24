#!/usr/bin/env python3
"""Offline audio analysis for the terminal PV.

Decodes song.mp3 (via ffmpeg pipe) to mono PCM, then computes:
  - overall RMS energy envelope (per hop, ~23ms)
  - spectral onset strength (low / mid / high band flux)
  - BPM estimate via onset autocorrelation
  - a quantised beat grid snapped to onset peaks

Output: assets/timeline.json  (consumed by world_execute_me.py)

Only needed to (re)generate the timeline; the player ships with a
precomputed copy so it runs without numpy/ffmpeg.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SONG = ROOT / "song.mp3"
OUT = ROOT / "assets" / "timeline.json"

SR = 22050
HOP = 512          # ~23.2 ms per frame
BPM_MIN, BPM_MAX = 60, 200


def decode_mono(path: Path) -> np.ndarray:
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-ac", "1", "-ar", str(SR), "-f", "s16le", "-",
    ]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return pcm


def envelope(pcm: np.ndarray) -> np.ndarray:
    n = (len(pcm) - 1024) // HOP
    idx = np.arange(n)[:, None] * HOP + np.arange(1024)[None, :]
    frames = pcm[idx]
    return np.sqrt((frames ** 2).mean(axis=1))


def band_flux(pcm: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """Half-wave-rectified log-magnitude flux of one frequency band."""
    win = np.hanning(1024).astype(np.float32)
    freqs = np.fft.rfftfreq(1024, 1.0 / SR)
    band = (freqs >= lo) & (freqs < hi)
    n = (len(pcm) - 1024) // HOP
    out = np.empty(n, dtype=np.float32)
    prev = None
    for i in range(n):
        spec = np.abs(np.fft.rfft(pcm[i * HOP:i * HOP + 1024] * win))[band]
        log = np.log1p(spec * 20.0)
        if prev is not None:
            out[i] = np.maximum(log - prev, 0.0).sum()
        prev = log
    return out


def smooth(x: np.ndarray, k: int) -> np.ndarray:
    ker = np.ones(k, dtype=np.float32) / k
    return np.convolve(x, ker, mode="same")


def estimate_bpm(onset: np.ndarray) -> float:
    fps = SR / HOP
    x = onset - onset.mean()
    ac = np.correlate(x, x, mode="full")[len(x) - 1:]
    lag_min = int(fps * 60.0 / BPM_MAX)
    lag_max = int(fps * 60.0 / BPM_MIN)
    lag = lag_min + int(np.argmax(ac[lag_min:lag_max]))
    bpm = 60.0 * fps / lag
    while bpm < 85:      # prefer the tactus in the 85-170 range
        bpm *= 2.0
    while bpm > 170:
        bpm /= 2.0
    return float(bpm)


def beat_grid(onset: np.ndarray, bpm: float) -> list[float]:
    fps = SR / HOP
    period = 60.0 / bpm * fps
    best_phase, best_score = 0.0, -1.0
    for phase in np.arange(0, period, 0.25):
        pts = np.arange(phase, len(onset), period)
        pts = pts[pts < len(onset)].astype(int)
        score = onset[pts].mean()
        if score > best_score:
            best_score, best_phase = score, phase
    beats = []
    t = best_phase
    while t < len(onset):
        i = int(t)
        lo, hi = max(0, i - 3), min(len(onset), i + 4)
        beats.append(round((lo + int(np.argmax(onset[lo:hi]))) / fps, 4))
        t += period
    return beats


def main() -> None:
    print("decoding ...", file=sys.stderr)
    pcm = decode_mono(SONG)
    dur = len(pcm) / SR
    print(f"duration {dur:.2f}s", file=sys.stderr)

    print("envelope ...", file=sys.stderr)
    rms = envelope(pcm)

    print("onset bands ...", file=sys.stderr)
    f_low = band_flux(pcm, 30, 180)
    f_mid = band_flux(pcm, 180, 2000)
    f_high = band_flux(pcm, 2000, 11000)
    onset = smooth(f_low * 1.5 + f_mid + f_high * 0.8, 3)

    bpm = estimate_bpm(onset)
    print(f"bpm ~ {bpm:.2f}", file=sys.stderr)
    beats = beat_grid(onset, bpm)
    print(f"{len(beats)} beats", file=sys.stderr)

    fps = SR / HOP
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "duration": round(dur, 3),
        "sr": SR,
        "hop_ms": round(1000.0 * HOP / SR, 3),
        "bpm": round(bpm, 2),
        "beats": beats,
        # energy 0..1 per hop, lightly smoothed for visuals
        "energy": [round(float(v), 4) for v in smooth(rms / (rms.max() + 1e-6), 2)],
        "onset": [round(float(v), 4) for v in
                  smooth(onset / (onset.max() + 1e-6), 2)],
    }))
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
