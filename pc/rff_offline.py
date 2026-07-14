#!/usr/bin/env python3
"""Offline science run: full RFF v2 pipeline over recorded session CSVs.

This is the controlled experiment. It replays recorded captures through
the exact pipeline the live tool uses — phase unwrap with continuity
correction, RANSAC slope/intercept, windowed robust aggregation, optional
reference-beacon normalization, Kalman drift tracks — then answers the
scientific questions:

  1. Per source: how stable are CFO and SFO? (mean, spread, Kalman track)
  2. Between sources: how separable are they? (pairwise Mahalanobis
     separation matrix under pooled covariance — 'sigmas apart')
  3. Does it generalize? Chronological train/holdout split per source,
     holdout windows classified blind against the learned centroids ->
     confusion counts and accuracy.

Usage:
  python rff_offline.py data/raw/*.csv
  python rff_offline.py data/raw/desk_*.csv --ref-mac a4:f0:0f:77:91:20
  python rff_offline.py data/raw/*.csv --min-windows 4 --window 48 --db
"""
import argparse
import csv as csvmod
import glob
import os
import sys
import time
from collections import defaultdict

import numpy as np

from rff.dsp import FrameEstimator, WindowAggregator
from rff.kalman import DriftTracker
from rff.discriminator import Discriminator, CHI2_95, CHI2_99
from rff.reference import ReferenceNormalizer
from rff.store import Store, DEFAULT_DB

TRAIN_FRACTION = 0.6


def iter_frames(path):
    """Yield (pc_time_us, mac, rssi, esp_ts_us, csi_vals) rows."""
    with open(path, newline="") as f:
        for row in csvmod.DictReader(f):
            try:
                vals = np.fromstring(row["csi_data"], dtype=np.float64,
                                     sep=",")
                yield (int(row["pc_time_us"]), row["mac"].lower(),
                       int(row["rssi"]), int(row["esp_timestamp_us"]), vals)
            except (KeyError, ValueError):
                continue


def collect_observations(paths, window, ref_mac):
    """Replay all files chronologically -> {mac: [obs, ...]}.

    Estimator/aggregator state is per (file, mac): the ESP clock and the
    unwrap continuity anchor reset between sessions, so state must not
    leak across files. The reference normalizer also restarts per file for
    the same reason.
    """
    by_mac = defaultdict(list)
    for path in sorted(paths):
        estimators = defaultdict(FrameEstimator)
        aggregators = defaultdict(lambda: WindowAggregator(window=window))
        ref = ReferenceNormalizer(ref_mac)
        n_rows = 0
        for pc_us, mac, rssi, esp_us, vals in iter_frames(path):
            n_rows += 1
            est = estimators[mac].feed(vals, esp_us)
            obs = aggregators[mac].feed(est, esp_us, rssi)
            if obs is None:
                continue
            obs, _ = ref.feed(mac, obs)
            obs["ts_pc"] = pc_us * 1e-6
            obs["session"] = os.path.basename(path)
            by_mac[mac].append(obs)
        print(f"  {os.path.basename(path)}: {n_rows} frames", file=sys.stderr)
    return by_mac


def feature(obs):
    """(CFO, SFO) feature vector, preferring reference-corrected values."""
    cfo = obs.get("cfo_ref", obs.get("cfo"))
    sfo = obs.get("sfo_ref", obs.get("sfo"))
    if cfo is None or sfo is None:
        return None
    return np.array([cfo, sfo])


def report(by_mac, min_windows, ref_mac):
    macs = sorted(m for m, o in by_mac.items() if len(o) >= min_windows)
    skipped = sorted(set(by_mac) - set(macs))
    if skipped:
        print(f"\n(skipping {len(skipped)} source(s) with < {min_windows} "
              f"windows: {', '.join(skipped)})")
    if not macs:
        print("no source produced enough windows — nothing to analyze",
              file=sys.stderr)
        return None

    # ---------- 1. per-source stability ----------
    print("\n=== Per-source clock signatures "
          f"({'reference-corrected' if ref_mac else 'raw'}) ===")
    print(f"{'source':<20} {'wins':>4} {'sess':>4}  "
          f"{'CFO Hz':>10} {' +-IQR':>7}   {'SFO rad/sc':>11} {' +-IQR':>9}  "
          f"{'KF cfo':>8} {'KF sfo':>9}")
    trackers = {}
    for mac in macs:
        obs_list = by_mac[mac]
        feats = [f for f in (feature(o) for o in obs_list) if f is not None]
        tr = DriftTracker()
        for o in obs_list:
            tr.update({"cfo": o.get("cfo_ref", o.get("cfo")),
                       "cfo_iqr": o.get("cfo_iqr"),
                       "sfo": o.get("sfo_ref", o.get("sfo")),
                       "sfo_iqr": o.get("sfo_iqr")})
        trackers[mac] = tr
        if not feats:
            continue
        a = np.array(feats)
        ciqr = np.subtract(*np.percentile(a[:, 0], [75, 25]))
        siqr = np.subtract(*np.percentile(a[:, 1], [75, 25]))
        sessions = len({o["session"] for o in obs_list})
        print(f"{mac:<20} {len(obs_list):>4} {sessions:>4}  "
              f"{np.median(a[:, 0]):>+10.1f} {ciqr:>7.1f}   "
              f"{np.median(a[:, 1]):>+11.4f} {siqr:>9.4f}  "
              f"{tr.cfo.x if tr.cfo.initialized else float('nan'):>+8.1f} "
              f"{tr.sfo.x if tr.sfo.initialized else float('nan'):>+9.4f}")

    # ---------- 2. train/holdout discrimination ----------
    disc = Discriminator()
    train, test = {}, {}
    for mac in macs:
        feats = [f for f in (feature(o) for o in by_mac[mac])
                 if f is not None]
        cut = max(int(len(feats) * TRAIN_FRACTION), 1)
        train[mac], test[mac] = feats[:cut], feats[cut:]
        for f in train[mac]:
            disc.learn(mac, f)

    print("\n=== Pairwise separation (centroid Mahalanobis distance, "
          "pooled cov) ===")
    ids, sep = disc.separation_matrix()
    if len(ids) >= 2:
        short = [i[-8:] for i in ids]
        print(f"{'':>10}" + "".join(f"{s:>10}" for s in short))
        for a, sid in enumerate(ids):
            cells = "".join(f"{sep[a][b]:>10.1f}" if b != a else f"{'-':>10}"
                            for b in range(len(ids)))
            print(f"{short[a]:>10}" + cells)
        offdiag = sep[np.triu_indices(len(ids), 1)]
        print(f"\nmin separation {offdiag.min():.1f}sigma, "
              f"median {np.median(offdiag):.1f}sigma  "
              f"(rule of thumb: >3sigma reliably separable)")
    else:
        print("(need >= 2 characterized sources for a separation matrix)")

    print("\n=== Blind holdout classification "
          f"(train {TRAIN_FRACTION:.0%} / test {1-TRAIN_FRACTION:.0%}, "
          "chronological) ===")
    total, correct, strangers = 0, 0, 0
    for mac in macs:
        n_ok = n_stranger = 0
        preds = defaultdict(int)
        for f in test[mac]:
            best, d2, verdict = disc.classify(f)
            if verdict == "UNSCORED":
                continue
            total += 1
            if verdict == "STRANGER":
                n_stranger += 1
                strangers += 1
            elif best == mac:
                n_ok += 1
                correct += 1
            else:
                preds[best] += 1
        n_test = len(test[mac])
        confused = ", ".join(f"{m[-8:]}x{c}" for m, c in preds.items())
        print(f"{mac:<20} {n_test:>3} test windows  "
              f"correct {n_ok:>3}  stranger {n_stranger:>3}"
              f"{'  confused-> ' + confused if confused else ''}")
    if total:
        print(f"\naccuracy {correct}/{total} = {correct/total:.1%}   "
              f"(rejected as stranger: {strangers}, chi2_95={CHI2_95}, "
              f"chi2_99={CHI2_99})")
    return disc, trackers


def persist(by_mac, disc, db_path):
    store = Store(db_path)
    now = time.time()
    for mac, obs_list in by_mac.items():
        sid = store.source_id(mac, now=now)
        for o in obs_list:
            f = feature(o)
            d2 = disc.self_consistency(mac, f) if f is not None else None
            store.add_observation(sid, "offline", o.get("ts_pc"), o,
                                  d2_self=d2)
        model = disc.models.get(mac)
        if model is not None:
            store.save_model(sid, model)
    store.close()
    print(f"\nwrote history + models to {db_path}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csvs", nargs="+", help="session CSV files or globs")
    ap.add_argument("--ref-mac", help="reference beacon MAC for "
                    "systemic-drift subtraction")
    ap.add_argument("--window", type=int, default=64,
                    help="frames per observation window (default 64)")
    ap.add_argument("--min-windows", type=int, default=4,
                    help="min windows for a source to enter the analysis")
    ap.add_argument("--db", nargs="?", const=DEFAULT_DB, default=None,
                    help="persist observations+models to SQLite "
                    "(default path data/rff.db)")
    args = ap.parse_args()

    paths = []
    for pat in args.csvs:
        paths.extend(glob.glob(pat))
    if not paths:
        print("no CSV files matched", file=sys.stderr)
        return 1

    print(f"replaying {len(paths)} session file(s)...", file=sys.stderr)
    by_mac = collect_observations(paths, args.window, args.ref_mac)
    result = report(by_mac, args.min_windows, args.ref_mac)
    if result is None:
        return 1
    if args.db:
        persist(by_mac, result[0], args.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
