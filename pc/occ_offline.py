#!/usr/bin/env python3
r"""Offline occupancy science run: motion, presence, zones from raw CSVs.

Replays capture CSVs through the occupancy pipeline (occ/): per-link
amplitude grids -> calibrated motion detection -> respiration scan of
quiet segments -> cross-link zone profiles -> timeline report.

Calibration: --calib points at a session (or time slice) believed to be
an empty room; per-link median/MAD of the motion metric from that data
set the detection thresholds. Without --calib the tool self-calibrates
on the analyzed file's own quietest half — fine for exploration, but the
report says so, because self-calibration on an occupied session inflates
the threshold and hides motion.

If the CSV's label column is populated (scripted ground-truth session),
the report scores the detectors against the labels — that is where the
honest detection/false-alarm rates come from.

Usage:
  python pc\occ_offline.py data\raw\rx_evening.csv --calib data\raw\rx_overnight.csv
  python pc\occ_offline.py data\raw\labeled_walk.csv --calib data\raw\rx_overnight.csv --plot out.png
"""
import argparse
import glob
import os
import sys
import time
from collections import defaultdict

import numpy as np

from occ import BEACON_MACS
from occ.ingest import build_link_grids
from occ.motion import (motion_metric, robust_stats, zscore, FusedDetector,
                        segments, CountConditionedFloor)
from occ.breathing import respiration_scan, presence_verdict
from occ.zones import event_profiles, profile_spread, kmeans_zones

MIN_BREATH_S = 120.0          # quiet run length needed for a respiration scan
BUCKET_S = 300                # timeline bucket (5 min)
RSSI_GUARD_DB = 5.0           # calibration transfer limit (see guard below)


def fmt_clock(t):
    return time.strftime("%H:%M", time.localtime(t))


def calibrate(csv_path, grid_hz, window_s, verbose=True):
    """Empty-room calibration: per-link count-conditioned metric floor.

    Conditioning on frame count matters: per-link rates shift between
    sessions as the channel-6 collision balance moves, and the metric
    floor scales ~1/sqrt(frames per bin). An unconditioned floor turns
    a rate change into fake motion (measured: +19.6 sigma of it).
    """
    grids, _ = build_link_grids(csv_path, grid_hz, verbose=verbose)
    floors = {}
    for mac, g in grids.items():
        m = motion_metric(g, window_s)
        w = max(3, int(round(window_s / g.dt)))
        floors[mac] = CountConditionedFloor.fit(m, g.count, w, g.dt, g.rssi)
    return floors


def analyze(csv_path, calib_stats, grid_hz, window_s, det_kw, plot=None):
    print(f"\n=== {os.path.basename(csv_path)} ===")
    grids, labels = build_link_grids(csv_path, grid_hz)
    macs = [m for m in BEACON_MACS if m in grids]
    names = [BEACON_MACS[m] for m in macs]
    if not macs:
        print("  no beacon links in this file")
        return
    dt = grids[macs[0]].dt
    n = max(grids[m].n for m in macs)

    # ---- per-link motion metric -> count-conditioned z-scores ----
    w = max(3, int(round(window_s / dt)))
    metrics, zs = {}, []
    self_cal = calib_stats is None
    op_lines = []
    for mac in macs:
        g = grids[mac]
        m = np.full(n, np.nan)
        m[:g.n] = motion_metric(g, window_s)
        metrics[mac] = m
        count = np.zeros(n, dtype=g.count.dtype)
        count[:g.n] = g.count
        fl = None if self_cal else calib_stats.get(mac)
        if fl is not None:
            fps_now = float(g.count.mean()) / dt
            rssi_now = float(np.nanmedian(g.rssi))
            fps_cal, rssi_cal = fl.fps, fl.rssi_med
            note = ""
            # Operating-point guard: a link whose RSSI moved far from
            # its calibration value has a physically different noise
            # floor (CSI amplitude noise scales with 1/SNR) -- the
            # transferred floor would fake continuous motion. Measured
            # example: B3 shifted -64 -> -77 dBm between sessions and
            # sat at z=+18 with no motion evidence.
            if abs(rssi_now - rssi_cal) > RSSI_GUARD_DB:
                note = (f"  [floor INVALID: RSSI shifted "
                        f"{rssi_now - rssi_cal:+.0f} dB "
                        f"-> link self-recalibrated]")
                fl = None
            op_lines.append(
                f"          {BEACON_MACS[mac]} operating point: "
                f"{fps_cal:.0f} -> {fps_now:.0f} fps, "
                f"RSSI {rssi_cal:.0f} -> {rssi_now:.0f} dBm{note}")
        if fl is None:
            # quietest half of this session sets the floor
            v = m[np.isfinite(m)]
            quiet_m = np.where(m <= np.median(v), m, np.nan)
            fl = CountConditionedFloor.fit(quiet_m, count, w, dt, g.rssi)
        zs.append(fl.z(m, count, w))
    Z = np.stack(zs)
    if self_cal:
        print("  [self-calibrated on this session's quietest half -- "
              "use --calib with an empty-room capture for honest numbers]")

    # ---- fused detection ----
    det = FusedDetector(dt, **det_kw)
    active = det.detect(Z)
    have = np.isfinite(Z).any(axis=0)
    n_have = int(have.sum())
    act_frac = float(active[have].mean()) if n_have else 0.0
    events = segments(active, dt, min_len_s=1.0)
    t0 = grids[macs[0]].t0
    span_h = n * dt / 3600
    print(f"\n  span {span_h:.2f} h, grid {1/dt:g} Hz, links: "
          + ", ".join(f"{nm}({grids[m].coverage()*100:.0f}% cov)"
                      for m, nm in zip(macs, names)))
    print(f"  motion: {act_frac*100:.1f}% of covered time active, "
          f"{len(events)} events")
    for line in op_lines:
        print(line)
    if events:
        durs = np.array([e[2] for e in events])
        print(f"          event duration median {np.median(durs):.0f}s, "
              f"max {durs.max():.0f}s")
    for mac, nm in zip(macs, names):
        zi = Z[macs.index(mac)]
        v = zi[np.isfinite(zi)]
        if v.size:
            print(f"          {nm} z: median {np.median(v):+.1f}, "
                  f"p99 {np.percentile(v, 99):+.1f}, max {v.max():+.1f}")

    # ---- respiration scan on quiet runs ----
    quiet = ~active & have
    filled, valid = {}, {}
    for mac in macs:
        f, vd = grids[mac].filled_shape(max_gap_s=5.0)
        pad_f = np.full((n, f.shape[1]), np.nan, dtype=f.dtype)
        pad_f[:f.shape[0]] = f
        pad_v = np.zeros(n, dtype=bool)
        pad_v[:vd.size] = vd
        filled[mac], valid[mac] = pad_f, pad_v

    print("\n  --- respiration scan (quiet runs >= "
          f"{MIN_BREATH_S:.0f}s) ---")
    scans = []           # (i0, i1, mac, scan, verdict)
    q_segs = segments(quiet, dt, min_len_s=MIN_BREATH_S)
    for i0, i1, dur in q_segs:
        for mac, nm in zip(macs, names):
            # maximal fully-valid runs inside the quiet segment
            vd = valid[mac][i0:i1]
            for j0, j1, jdur in segments(vd, dt, min_len_s=MIN_BREATH_S):
                A = filled[mac][i0 + j0:i0 + j1]
                scan = respiration_scan(A, dt)
                if scan is None:
                    continue
                verdict = presence_verdict(scan)
                scans.append((i0 + j0, i0 + j1, mac, scan, verdict))
    if scans:
        pos = [s for s in scans if s[4]]
        print(f"  {len(q_segs)} quiet segments -> {len(scans)} link-scans, "
              f"{len(pos)} above presence threshold")
        # summarize the strongest few
        top = sorted(scans, key=lambda s: -s[3]["snr_db"])[:8]
        print(f"  {'when':<13} {'link':<4} {'dur':>5} {'SNR dB':>7} "
              f"{'bpm':>6} {'agree':>5}  verdict")
        for i0, i1, mac, sc, vv in top:
            print(f"  {fmt_clock(t0+i0*dt)}-{fmt_clock(t0+i1*dt):<7} "
                  f"{BEACON_MACS[mac]:<4} {(i1-i0)*dt:>4.0f}s "
                  f"{sc['snr_db']:>7.1f} {sc['bpm']:>6.1f} "
                  f"{sc['n_agree']:>5}  "
                  f"{'PRESENCE' if vv else 'below-threshold'}")
    else:
        print(f"  no quiet runs long enough (>= {MIN_BREATH_S:.0f}s) "
              f"for a respiration scan")

    # ---- zone profiles ----
    print("\n  --- cross-link zone profiles ---")
    profs = event_profiles(events, Z, names)
    sp = profile_spread(profs)
    if sp is None:
        print("  too few motion events for zone analysis")
    else:
        c = sp["centroid"]
        print(f"  {len(profs)} events; centroid profile "
              + " ".join(f"{nm}:{c[i]:.2f}" for i, nm in enumerate(names))
              + f"; spread mean L1 {sp['mean_l1']:.2f} "
              f"(0 = links see no geometry)")
        km = kmeans_zones(profs, k=min(3, max(2, len(profs) // 4)))
        if km is not None:
            assign, C = km
            for j in range(C.shape[0]):
                cnt = int((assign == j).sum())
                print(f"    zone-{j}: {cnt:>3} events, profile "
                      + " ".join(f"{nm}:{C[j][i]:.2f}"
                                 for i, nm in enumerate(names)))

    # ---- label scoring (scripted ground truth) ----
    lab_arr = labels_to_bins(labels, t0, dt, n)
    if lab_arr is not None:
        print("\n  --- label scoring (scripted session) ---")
        score_against_labels(lab_arr, active, scans, dt, n)

    # ---- timeline ----
    print("\n  --- timeline (5-min buckets: # motion>50%  + motion>10%  "
          "b breathing  . quiet  ' ' no data) ---")
    breath_mask = np.zeros(n, dtype=bool)
    for i0, i1, mac, sc, vv in scans:
        if vv:
            breath_mask[i0:i1] = True
    per_bucket = int(BUCKET_S / dt)
    row = []
    marks = []
    for b0 in range(0, n, per_bucket):
        b1 = min(n, b0 + per_bucket)
        h = have[b0:b1]
        if not h.any():
            row.append(" ")
        else:
            af = active[b0:b1][h].mean()
            if af > 0.5:
                row.append("#")
            elif af > 0.1:
                row.append("+")
            elif breath_mask[b0:b1].any():
                row.append("b")
            else:
                row.append(".")
        marks.append(fmt_clock(t0 + b0 * dt))
    for i in range(0, len(row), 60):
        seg = "".join(row[i:i + 60])
        print(f"  {marks[i]:>6} {seg}")

    if plot:
        render_plot(plot, t0, dt, Z, names, active, scans)
    return {"active_frac": act_frac, "events": events, "scans": scans}


def labels_to_bins(labels, t0, dt, n):
    """Label transitions -> per-bin label array, or None if unlabeled."""
    lab = [(t, s.strip()) for t, s in labels if s and s.strip()]
    if not lab:
        return None
    arr = np.full(n, "", dtype=object)
    trans = sorted(labels, key=lambda x: x[0])
    for idx, (t, s) in enumerate(trans):
        i0 = max(0, int((t - t0) / dt))
        i1 = n if idx + 1 >= len(trans) else \
            max(0, int((trans[idx + 1][0] - t0) / dt))
        arr[i0:i1] = s.strip()
    return arr


def score_against_labels(lab_arr, active, scans, dt, n):
    """Honest per-label detection stats. Convention for scripted runs:
    labels containing 'empty' = vacant truth, 'walk'/'move' = motion
    truth, 'still'/'sit' = present-but-still truth."""
    breath_mask = np.zeros(n, dtype=bool)
    for i0, i1, mac, sc, vv in scans:
        if vv:
            breath_mask[i0:i1] = True
    for val in sorted(set(lab_arr) - {""}):
        m = lab_arr == val
        n_s = m.sum() * dt
        af = float(active[m].mean()) if m.any() else 0.0
        bf = float(breath_mask[m].mean()) if m.any() else 0.0
        print(f"    '{val}': {n_s:.0f}s  motion-flagged {af*100:5.1f}%  "
              f"breathing-flagged {bf*100:5.1f}%")


def render_plot(path, t0, dt, Z, names, active, scans):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime

    n = Z.shape[1]
    tt = [datetime.fromtimestamp(t0 + i * dt) for i in range(0, n, 10)]
    fig, ax = plt.subplots(figsize=(14, 5))
    for l, nm in enumerate(names):
        ax.plot(tt, Z[l, ::10], lw=0.5, label=nm, alpha=0.8)
    yl = ax.get_ylim()
    ax.fill_between(tt, yl[0], yl[1],
                    where=active[::10], alpha=0.15, color="red",
                    label="motion")
    for i0, i1, mac, sc, vv in scans:
        if vv:
            ax.axvspan(datetime.fromtimestamp(t0 + i0 * dt),
                       datetime.fromtimestamp(t0 + i1 * dt),
                       alpha=0.15, color="green")
    ax.set_ylabel("motion z-score")
    ax.set_yscale("symlog")
    ax.legend(loc="upper right", fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    print(f"\n  plot -> {path}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csvs", nargs="+", help="session CSVs / globs to analyze")
    ap.add_argument("--calib", help="empty-room CSV for threshold "
                    "calibration")
    ap.add_argument("--grid-hz", type=float, default=10.0)
    ap.add_argument("--window-s", type=float, default=2.0,
                    help="motion metric window (default 2 s)")
    ap.add_argument("--z-on", type=float, default=5.0)
    ap.add_argument("--z-solo", type=float, default=12.0)
    ap.add_argument("--z-off", type=float, default=3.0)
    ap.add_argument("--plot", help="write a PNG timeline here")
    args = ap.parse_args()

    paths = []
    for pat in args.csvs:
        paths.extend(glob.glob(pat))
    if not paths:
        print("no CSV files matched", file=sys.stderr)
        return 1

    calib_stats = None
    if args.calib:
        print(f"calibrating on {os.path.basename(args.calib)} ...")
        calib_stats = calibrate(args.calib, args.grid_hz, args.window_s)
        for mac, fl in sorted(calib_stats.items(),
                              key=lambda kv: BEACON_MACS.get(kv[0], "")):
            print(f"  {BEACON_MACS.get(mac, mac)}: {fl.fps:.0f} fps, "
                  f"RSSI {fl.rssi_med:.0f} dBm, floor "
                  f"{fl.meds[-1]:.4f}@{fl.cs[-1]:.0f}fr"
                  f" .. {fl.meds[0]:.4f}@{fl.cs[0]:.0f}fr")

    det_kw = dict(z_on=args.z_on, z_solo=args.z_solo, z_off=args.z_off)
    for p in sorted(paths):
        age_h = (time.time() - os.path.getmtime(p)) / 3600
        if age_h < 0.05:
            print(f"[note: {os.path.basename(p)} modified "
                  f"{age_h*60:.0f} min ago — capture may still be running]")
        analyze(p, calib_stats, args.grid_hz, args.window_s, det_kw,
                plot=args.plot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
