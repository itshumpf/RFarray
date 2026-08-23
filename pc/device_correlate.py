#!/usr/bin/env python3
r"""Correlate ambient device presence with occupancy/motion events.

Fuses the two independently-validated pipelines on the same capture
file, on a shared time axis:

  occ/    "what is happening in the space" -- the beacon-driven motion
          detector (unchanged, same code occ_offline.py uses).
  rff/'s underlying raw data -- "who is transmitting" -- here reduced to
          the simplest honest signal, MAC presence, not full Mahalanobis
          clock-fingerprint classification (a household device's MAC is
          normally stable while associated to the home network; the
          spoofing/rotation problem rff/ solves is for *strangers*, not
          for correlating your own already-known devices with your own
          motion events).

For every ambient (non-beacon) MAC seen often enough in the file, this
reports what fraction of that MAC's active time bins overlap with a
motion-flagged bin, against the file's baseline motion-active fraction
-- a "lift" ratio. Lift >> 1 means that device's presence is enriched
during motion (consistent with "this is the device the moving person is
carrying"); lift ~= 1 means no relationship; this is correlation over a
single session, not proof of who owns which device.

Usage:
  python pc\device_correlate.py data\raw\occ_20260722_191220.csv
  python pc\device_correlate.py data\raw\occ_20260722_191220.csv --min-frames 20
"""
import argparse
import sys
import time

import numpy as np

from occ import BEACON_MACS
from occ.ingest import build_link_grids, iter_amp_rows
from occ.motion import motion_metric, CountConditionedFloor, FusedDetector
from zone_calib import labels_to_bins, label_runs


def build_motion_timeline(csv_path, grid_hz=10.0, window_s=2.0,
                          calib_clock=None):
    """Motion timeline. Calibration source, in priority order:
      1. calib_clock = (HH:MM, HH:MM) -- an explicit local-clock window
         on this file's own date, for raw captures with no label column
         (e.g. an overnight session where you know a stretch was
         human-vacant by other means, not a scripted occ_capture label).
      2. this file's own 'empty'-labeled segment, if one exists.
      3. self-calibration on the quietest half (occ_offline.py's
         fallback) -- flagged, since it can be unreliable on files where
         "quieter half" isn't representative of "actually empty" (e.g.
         multi-hour sessions with real drift; measured on this exact
         overnight file: self-cal gives 84.9% active vs. a expected
         sub-1% overnight rate).
    Returns (t0, dt, n, active, have, calib_note)."""
    grids, labels = build_link_grids(csv_path, grid_hz, verbose=False)
    macs = [m for m in BEACON_MACS if m in grids]
    if not macs:
        raise ValueError(f"{csv_path}: no beacon links present")
    dt = grids[macs[0]].dt
    t0 = grids[macs[0]].t0
    n = max(grids[m].n for m in macs)
    w = max(3, int(round(window_s / dt)))

    empty_i0 = empty_i1 = None
    calib_desc = None
    if calib_clock is not None:
        day0 = time.localtime(t0)
        def clock_to_epoch(hhmm):
            hh, mm = (int(x) for x in hhmm.split(":"))
            t = time.struct_time((day0.tm_year, day0.tm_mon, day0.tm_mday,
                                  hh, mm, 0, 0, 0, -1))
            e = time.mktime(t)
            if e < t0 - 3600:      # HH:MM rolled past midnight into next day
                e += 86400
            return e
        e0, e1 = clock_to_epoch(calib_clock[0]), clock_to_epoch(calib_clock[1])
        empty_i0 = max(0, int(round((e0 - t0) / dt)))
        empty_i1 = min(n, int(round((e1 - t0) / dt)))
        calib_desc = f"manual clock window {calib_clock[0]}-{calib_clock[1]}"
    else:
        lab_arr = labels_to_bins(labels, t0, dt, n)
        for lab, i0, i1 in label_runs(lab_arr):
            if "empty" in lab.lower() and (i1 - i0) * dt >= 10.0:
                empty_i0, empty_i1 = i0, i1
                calib_desc = f"this file's own 'empty' segment ({(i1-i0)*dt:.0f}s)"
                break

    zs = []
    for mac in macs:
        g = grids[mac]
        m = np.full(n, np.nan)
        m[:g.n] = motion_metric(g, window_s)
        count = np.zeros(n, dtype=g.count.dtype)
        count[:g.n] = g.count
        if empty_i0 is not None:
            seg = np.full(n, np.nan)
            seg[empty_i0:empty_i1] = m[empty_i0:empty_i1]
            fl = CountConditionedFloor.fit(seg, count, w, dt, g.rssi)
        else:
            v = m[np.isfinite(m)]
            quiet_m = np.where(m <= np.median(v), m, np.nan)
            fl = CountConditionedFloor.fit(quiet_m, count, w, dt, g.rssi)
        zs.append(fl.z(m, count, w))
    Z = np.stack(zs)
    det = FusedDetector(dt)
    active = det.detect(Z)
    have = np.isfinite(Z).any(axis=0)
    note = (f"calibrated on {calib_desc}" if calib_desc is not None else
            "[self-calibrated on this file's quietest half -- unreliable "
            "on some files, see occ_offline.py --calib for an external floor]")
    return t0, dt, n, active, have, note


def ambient_mac_totals(csv_path, exclude):
    """One cheap pass: frame count per non-excluded MAC."""
    import csv as csvmod
    counts = {}
    with open(csv_path, newline="") as f:
        r = csvmod.reader(f)
        header = next(r)
        i_mac = header.index("mac")
        for row in r:
            m = row[i_mac].lower()
            if m in exclude:
                continue
            counts[m] = counts.get(m, 0) + 1
    return counts


def bin_presence_multi(csv_path, macs, t0, dt, n):
    """Per-bin frame count for every mac in `macs`, in ONE pass over the
    file (not one pass per mac -- matters on multi-GB overnight
    captures). Aligned to an existing (t0, dt, n) grid built from a
    different mac set: t_s is real wall-clock time either way, so
    alignment only needs the shared t0/dt, not re-running the beacon
    ingest."""
    counts = {m: np.zeros(n, dtype=np.int32) for m in macs}
    for t_s, _label, m, _rssi, _amp, _rms in iter_amp_rows(csv_path, macs=macs):
        b = int(round((t_s - t0) / dt))
        if 0 <= b < n:
            counts[m][b] += 1
    return counts


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="a single capture CSV (promiscuous, has "
                                "ambient traffic alongside the beacons)")
    ap.add_argument("--min-frames", type=int, default=15,
                     help="skip ambient MACs with fewer total frames than "
                          "this (default 15 -- too sparse to say anything)")
    ap.add_argument("--grid-hz", type=float, default=10.0)
    ap.add_argument("--window-s", type=float, default=2.0)
    ap.add_argument("--calib-clock", nargs=2, metavar=("HH:MM", "HH:MM"),
                     help="manual local-clock window (this file's own "
                          "date) to treat as human-vacant for motion "
                          "calibration, e.g. --calib-clock 03:30 08:30")
    args = ap.parse_args()

    calib_clock = tuple(args.calib_clock) if args.calib_clock else None
    print(f"=== {args.csv} ===")
    t0, dt, n, active, have, note = build_motion_timeline(
        args.csv, args.grid_hz, args.window_s, calib_clock=calib_clock)
    n_have = int(have.sum())
    baseline = float(active[have].mean()) if n_have else float("nan")
    print(note)
    print(f"motion baseline: {baseline*100:.1f}% of {n_have} covered bins "
          f"flagged active\n")

    print("scanning MAC totals...")
    totals = ambient_mac_totals(args.csv, exclude=set(BEACON_MACS))
    candidates = sorted(((m, c) for m, c in totals.items()
                        if c >= args.min_frames), key=lambda kv: -kv[1])
    if not candidates:
        print(f"no ambient MAC has >= {args.min_frames} frames in this file")
        return 0
    print(f"binning presence for {len(candidates)} candidate MAC(s)...")
    presence_by_mac = bin_presence_multi(
        args.csv, {m for m, _ in candidates}, t0, dt, n)

    print(f"{'mac':<18} {'frames':>7} {'present bins':>13} "
          f"{'active-overlap':>15} {'lift':>6}")
    for mac, total in candidates:
        presence = presence_by_mac[mac] > 0
        seen = presence & have
        n_seen = int(seen.sum())
        if n_seen == 0:
            continue
        overlap = float(active[seen].mean())
        lift = overlap / baseline if baseline > 0 else float("nan")
        print(f"{mac:<18} {total:>7} {n_seen:>13} "
              f"{overlap*100:>14.1f}% {lift:>5.2f}x")

    print("\nlift >> 1 = this device's presence is enriched during motion "
          "(consistent with being carried by the moving person); "
          "lift ~= 1 = no relationship on this file. Single session, "
          "MAC identity only -- not a Mahalanobis-verified match, and "
          "correlation isn't proof of ownership.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
