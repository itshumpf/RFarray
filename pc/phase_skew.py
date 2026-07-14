#!/usr/bin/env python3
"""Experimental CFO / SFO estimator from CSI phase — the RFF v2 probe.

Radios drift because their crystals aren't perfect:
  - CFO (carrier frequency offset): the TX carrier sits slightly off the
    nominal frequency. Over time it adds a *common* phase rotation that
    accumulates frame-to-frame.
  - SFO (sampling frequency offset): the TX/RX sample clocks differ, adding
    a phase *slope across subcarriers* that grows with subcarrier index.

Both are physical properties of the transmitter's hardware, so they make
excellent fingerprints — and unlike our amplitude template, they don't
change when a device moves. The catch: the ESP32 gives uncalibrated phase,
so every capture carries an unknown packet-boundary timing offset (another
slope) and an unknown common phase. This script measures what's actually
recoverable and tells you honestly whether the phase is clean enough.

Usage:
  python phase_skew.py data/raw/harvest_afternoon.csv          # auto-pick busiest MAC
  python phase_skew.py data/raw/node3_cfo.csv --mac aa:bb:..   # a specific device
"""
import argparse
import csv as csvmod
import sys
from collections import defaultdict

import numpy as np

N_SC = 64                    # LLTF subcarriers
# LLTF guard/null subcarriers carry no usable phase; keep the data-bearing ones.
USABLE = np.r_[np.arange(6, 32), np.arange(33, 59)]   # skip DC(32) + edges


def load(path, only_mac=None):
    """Return {mac: (times[N], phases[N, N_SC])} of unwrapped per-frame phase."""
    by_mac_ph = defaultdict(list)
    by_mac_t = defaultdict(list)
    with open(path, newline="") as f:
        for row in csvmod.DictReader(f):
            mac = row["mac"].lower()
            if only_mac and mac != only_mac:
                continue
            try:
                v = np.array(row["csi_data"].split(","), dtype=np.float32)
                t = int(row["esp_timestamp_us"])
            except (KeyError, ValueError):
                continue
            if v.size < N_SC * 2:
                continue
            iq = v[: N_SC * 2]
            csi = iq[1::2] + 1j * iq[0::2]        # re + j*im  (CSV is i,q = im,re)
            by_mac_ph[mac].append(np.angle(csi))
            by_mac_t[mac].append(t)
    return {m: (np.array(by_mac_t[m]), np.array(by_mac_ph[m]))
            for m in by_mac_ph}


def analyze(mac, times, phases):
    n = len(times)
    sc = USABLE
    x = sc - sc.mean()

    # --- SFO proxy: slope of unwrapped phase across subcarriers, per frame ---
    slopes = np.empty(n)
    resid = np.empty(n)
    for i in range(n):
        ph = np.unwrap(phases[i, sc])
        A = np.vstack([x, np.ones_like(x)]).T
        (slope, _), *_ = np.linalg.lstsq(A, ph, rcond=None)
        slopes[i] = slope
        resid[i] = np.std(ph - (slope * x + ph.mean()))

    # --- CFO proxy: common-phase change between consecutive frames ---
    common = phases[:, sc].mean(axis=1)
    dphi = np.angle(np.exp(1j * np.diff(common)))       # wrapped delta
    dt = np.diff(times).astype(float) * 1e-6            # seconds (esp clock)
    good = dt > 0
    cfo_hz = dphi[good] / (2 * np.pi * dt[good]) if good.any() else np.array([])
    interval = np.median(dt[good]) if good.any() else 0.0
    nyquist = 0.5 / interval if interval > 0 else 0.0   # max unaliased CFO

    print(f"\n=== {mac}   ({n} frames) ===")
    print(f"SFO slope  : {slopes.mean():+.4f} rad/sc   "
          f"(std {slopes.std():.4f}, stability {_stab(slopes)})")
    print(f"per-frame residual after slope removal: {resid.mean():.3f} rad")
    print(f"frame interval: {interval*1000:.1f} ms   "
          f"-> CFO measurable only up to +/-{nyquist:.0f} Hz (Nyquist)")
    if cfo_hz.size:
        # robust center: trim wild wrap outliers
        c = cfo_hz[np.abs(cfo_hz) < np.percentile(np.abs(cfo_hz), 90) + 1e-9]
        aliased = "" if nyquist > 500 else "  [ALIASED — interval too slow/irregular for CFO]"
        print(f"residual CFO: {np.median(c):+.0f} Hz   "
              f"(IQR {np.percentile(c,75)-np.percentile(c,25):.0f} Hz){aliased}")

    # --- honest usability verdict ---
    slope_stable = slopes.std() < 0.05
    resid_low = resid.mean() < 0.6
    if slope_stable and resid_low:
        print("VERDICT: phase looks structured — CFO/SFO fingerprinting is "
              "worth pursuing on this device.")
    elif resid_low:
        print("VERDICT: clean per-frame phase but slope wanders — likely "
              "packet-timing jitter swamping SFO. Try a dedicated clean "
              "capture (node 3) before concluding.")
    else:
        print("VERDICT: phase is noisy/uncalibrated here — single-packet "
              "recovery unreliable. Needs more frames and/or phase "
              "sanitization; expected for casual traffic.")


def _stab(a):
    m = np.abs(a).mean()
    return "high" if a.std() < 0.02 else "med" if a.std() < 0.08 else "low"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--mac", help="analyze only this MAC (default: busiest)")
    ap.add_argument("--min-frames", type=int, default=30)
    args = ap.parse_args()

    data = load(args.csv, args.mac.lower() if args.mac else None)
    if not data:
        print("no usable rows found", file=sys.stderr)
        return 1

    if args.mac:
        targets = list(data)
    else:
        # busiest MAC = most frames (usually the beacon)
        busiest = max(data, key=lambda m: len(data[m][0]))
        targets = [busiest]
        print(f"(auto-selected busiest MAC {busiest}; use --mac to override)")

    ran = False
    for mac in targets:
        t, ph = data[mac]
        if len(t) < args.min_frames:
            print(f"skip {mac}: only {len(t)} frames (<{args.min_frames})")
            continue
        analyze(mac, t, ph)
        ran = True
    return 0 if ran else 1


if __name__ == "__main__":
    sys.exit(main())
