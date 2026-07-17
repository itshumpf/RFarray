#!/usr/bin/env python3
"""Synthetic sanity checks for the occupancy DSP (no hardware needed).

1. respiration_scan must find an injected 0.25 Hz line (SNR consensus)
   and must NOT claim presence on white noise.
2. motion rolling_std must flag an injected dispersion burst and stay
   quiet on the stationary floor.
Run: python pc\\test_occ_synth.py
"""
import numpy as np

from occ.breathing import respiration_scan, presence_verdict, welch_psd
from occ.motion import rolling_std, robust_stats, zscore, FusedDetector


def synth_shape(n, n_sc=52, breath_hz=None, breath_amp=0.01,
                noise=0.02, seed=1):
    rng = np.random.default_rng(seed)
    base = 1.0 + 0.3 * np.sin(np.linspace(0, 3, n_sc))     # static ripple
    A = np.tile(base, (n, 1))
    if breath_hz:
        t = np.arange(n) / 10.0
        # breathing couples into a subset of subcarriers with random
        # sign/strength, as real multipath geometry does
        coup = rng.normal(0, 1, n_sc) * (rng.random(n_sc) < 0.4)
        A += breath_amp * np.outer(np.sin(2 * np.pi * breath_hz * t), coup)
    A += rng.normal(0, noise, (n, n_sc))
    return (A / A.mean(axis=1, keepdims=True)).astype(np.float32)


def main():
    dt = 0.1
    n = 3000                                   # 5 min at 10 Hz
    fails = 0

    # --- breathing: injected 0.25 Hz (15 bpm) ---
    A = synth_shape(n, breath_hz=0.25)
    sc = respiration_scan(A, dt)
    ok = sc is not None and abs(sc["bpm"] - 15.0) < 1.5 \
        and presence_verdict(sc)
    print(f"[{'ok' if ok else 'FAIL'}] injected 15 bpm -> "
          f"{sc['bpm']:.1f} bpm, SNR {sc['snr_db']:.1f} dB, "
          f"agree {sc['n_agree']}" if sc else "[FAIL] scan returned None")
    fails += not ok

    # --- breathing: pure noise must not pass ---
    false_pos = 0
    for seed in range(10):
        An = synth_shape(n, breath_hz=None, seed=100 + seed)
        scn = respiration_scan(An, dt)
        if presence_verdict(scn):
            false_pos += 1
    ok = false_pos == 0
    print(f"[{'ok' if ok else 'FAIL'}] noise-only: {false_pos}/10 "
          f"false presence calls")
    fails += not ok

    # --- welch frequency accuracy on a clean tone ---
    t = np.arange(6000) * dt
    x = np.sin(2 * np.pi * 0.3 * t) + np.random.default_rng(0).normal(
        0, 0.1, t.size)
    f, p = welch_psd(x, 1 / dt)
    fpk = f[np.argmax(p)]
    ok = abs(fpk - 0.3) < 0.02
    print(f"[{'ok' if ok else 'FAIL'}] welch tone 0.300 Hz -> "
          f"{fpk:.3f} Hz")
    fails += not ok

    # --- motion: dispersion burst detection ---
    rng = np.random.default_rng(7)
    B = synth_shape(n, noise=0.02, seed=3).astype(np.float64)
    B[1500:1700] += rng.normal(0, 0.15, (200, 52))          # 20 s of motion
    std = rolling_std(B, 20)
    m = np.nanmedian(std, axis=1)
    med, mad = robust_stats(m[:1400])
    z = zscore(m, med, mad)
    det = FusedDetector(dt)
    act = det.detect(np.stack([z, z, z]))
    hit = act[1520:1680].mean()
    fa = act[:1400].mean()
    ok = hit > 0.8 and fa < 0.01
    print(f"[{'ok' if ok else 'FAIL'}] motion burst: detected "
          f"{hit*100:.0f}% of burst, false-alarm {fa*100:.2f}% of floor")
    fails += not ok

    print(f"\n{'ALL OK' if not fails else f'{fails} FAILURES'}")
    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
