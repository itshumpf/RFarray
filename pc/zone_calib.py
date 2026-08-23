#!/usr/bin/env python3
r"""Zone-fingerprint classifier: turn labeled walk sessions into a scored
coarse-localization result.

`pc/occ/zones.py` clusters motion events into UNLABELED groups and says
explicitly that naming them needs a labeled calibration walk. This is
that calibration step: given one or more `occ_capture.py` sessions whose
label column names physical spots (e.g. `zone1`..`zoneN`, `empty`), it

  1. builds per-link uniform-time amplitude grids (occ.ingest, same
     validated code occupancy/motion/breathing use),
  2. slices each contiguous same-label run ("visit") into short windows,
     each window's fingerprint = per-link median unit-mean |H| shape
     (52 subcarriers) concatenated across links,
  3. splits visits chronologically per label: with >=2 visits, all but
     the last train and the last is a blind holdout; with exactly 1
     visit (not enough data for an independent-visit test), it splits
     that visit's windows in half and says so -- weaker evidence, not
     hidden as if it were a real repeat-visit holdout,
  4. classifies test windows by nearest label centroid (Euclidean, on
     raw fingerprints -- translation-invariant, so no baseline
     subtraction is needed for the accuracy number itself) and reports
     an honest confusion matrix, per-zone recall, and overall accuracy.

This is a single-session, same-day result. It does not test stability
across time of day, thermal drift, furniture, or a different visit on a
different day -- same caveat rff/ already carries for clock signatures.
Report it as such.

Drift correction (--detrend-s, default 180): measured on real data that
a link's coverage/RSSI can drift noticeably *within* one session (one
session: a beacon's coverage swung 9%->94% over minutes) -- exactly the
receiver/channel-side drift rff/reference.py cancels for CFO/SFO by
subtracting a smoothed reference track. There is no separate stationary
reference here, so each link's own trailing rolling mean (over a window
much longer than one visit) stands in as the "non-positional" component;
subtracting it isolates the faster, position-driven deviation. Trailing
(not centered) so the estimate only ever uses past data, same
chronological discipline as the train/test split. Pass --detrend-s 0 to
disable and see the raw-fingerprint result for comparison.

Usage:
  python pc\zone_calib.py "data\raw\occ_2026*.csv"
  python pc\zone_calib.py "data\raw\occ_2026*.csv" --win-s 3 --min-visit-s 10
  python pc\zone_calib.py "data\raw\occ_2026*.csv" --detrend-s 0   # disable
"""
import argparse
import glob
import sys
from collections import defaultdict

import numpy as np

from occ.ingest import build_link_grids


def rolling_mean_nan(A, w):
    """Trailing-window NaN-aware mean per column, expanding at the start
    (same convention as occ.motion.rolling_mean_count): index i uses
    min(w, i+1) samples so there is no look-ahead into the future."""
    X = np.nan_to_num(A, nan=0.0).astype(np.float64)
    M = np.isfinite(A).astype(np.float64)
    c1 = np.cumsum(X, axis=0)
    cm = np.cumsum(M, axis=0)

    def wsum(C):
        S = C.copy()
        S[w:] = C[w:] - C[:-w]
        return S

    s1, m = wsum(c1), wsum(cm)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = s1 / m
    return mean


def labels_to_bins(labels, t0, dt, n):
    """Label transitions -> per-bin label array ("" = unscored)."""
    arr = np.full(n, "", dtype=object)
    if not labels:
        return arr
    trans = sorted(labels, key=lambda x: x[0])
    for idx, (t, s) in enumerate(trans):
        i0 = max(0, min(n, int(round((t - t0) / dt))))
        i1 = n if idx + 1 >= len(trans) else \
            max(0, min(n, int(round((trans[idx + 1][0] - t0) / dt))))
        arr[i0:i1] = s.strip() if s else ""
    return arr


def label_runs(lab_arr):
    """Contiguous same-nonempty-label runs -> [(label, i0, i1)]."""
    out = []
    n = len(lab_arr)
    i = 0
    while i < n:
        if lab_arr[i]:
            j = i
            while j < n and lab_arr[j] == lab_arr[i]:
                j += 1
            out.append((lab_arr[i], i, j))
            i = j
        else:
            i += 1
    return out


def window_fingerprints(grids, shapes, macs, i0, i1, w, min_valid_frac=0.15):
    """[i0,i1) -> list of (i_mid, vec) for each non-overlapping w-bin
    window where every live link has *some* real data. A window missing
    coverage on one link is dropped, not filled -- a fingerprint built
    from an absent link would silently encode "link had no signal" as
    if it were spatial information. min_valid_frac is deliberately low
    (not a density requirement): a link that only delivered a handful
    of frames in a window still gives a real, if noisier, median shape;
    a link with *zero* frames does not. Measured need for this: one
    session had a beacon's coverage swing 9%->94% over minutes for
    link-establishment reasons unrelated to zone position -- a strict
    density gate silently turned that into a biased training sample for
    whichever zones happened to be visited during the low-coverage
    window, not a fair one.

    `shapes[mac]` (n, 52) is what actually gets medianed into the
    fingerprint -- either the grid's raw unit-mean |H| shape, or a
    drift-corrected version of it; `grids[mac].count` still gates
    validity either way, since detrending doesn't manufacture coverage.
    """
    out = []
    for a in range(i0, i1, w):
        b = min(i1, a + w)
        if b - a < w * min_valid_frac:
            continue
        parts = []
        ok = True
        for mac in macs:
            if (grids[mac].count[a:b] > 0).sum() < (b - a) * min_valid_frac:
                ok = False
                break
            with np.errstate(invalid="ignore"):
                parts.append(np.nanmedian(shapes[mac][a:b], axis=0))
        if not ok or any(np.isnan(p).any() for p in parts):
            continue
        out.append(((a + b) // 2, np.concatenate(parts)))
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csvs", nargs="+", help="labeled session CSVs / globs")
    ap.add_argument("--grid-hz", type=float, default=10.0)
    ap.add_argument("--win-s", type=float, default=3.0,
                     help="fingerprint window length (default 3s)")
    ap.add_argument("--min-visit-s", type=float, default=10.0,
                     help="drop label runs shorter than this (default 10s "
                          "-- too short to trust as a real visit)")
    ap.add_argument("--detrend-s", type=float, default=180.0,
                     help="trailing rolling-mean window (seconds) "
                          "subtracted per link before fingerprinting, to "
                          "cancel within-session drift unrelated to zone "
                          "position; 0 disables (default 180)")
    args = ap.parse_args()

    paths = sorted({p for pat in args.csvs for p in glob.glob(pat)})
    if not paths:
        print("no CSV files matched", file=sys.stderr)
        return 1

    # ---- load every file, collect per-label visits (chronologically) ----
    per_file = []
    all_macs = None
    for p in paths:
        grids, labels = build_link_grids(p, args.grid_hz)
        macs = sorted(grids, key=lambda m: m)
        all_macs = set(macs) if all_macs is None else (all_macs & set(macs))
        t0 = grids[macs[0]].t0
        dt = grids[macs[0]].dt
        n = grids[macs[0]].n
        lab_arr = labels_to_bins(labels, t0, dt, n)
        runs = label_runs(lab_arr)
        if args.detrend_s > 0:
            w_roll = max(1, int(round(args.detrend_s / dt)))
            shapes = {m: grids[m].shape - rolling_mean_nan(grids[m].shape, w_roll)
                      for m in macs}
        else:
            shapes = {m: grids[m].shape for m in macs}
        per_file.append((p, grids, shapes, t0, dt, runs))
    print(f"drift correction: {'trailing ' + str(args.detrend_s) + 's rolling-mean subtraction per link' if args.detrend_s > 0 else 'DISABLED (raw fingerprints)'}")

    if not all_macs:
        print("no beacon link is present in every file -- can't build a "
              "consistent fingerprint", file=sys.stderr)
        return 1
    from occ import BEACON_MACS
    macs = sorted(all_macs, key=lambda m: BEACON_MACS.get(m, m))
    names = [BEACON_MACS.get(m, m) for m in macs]
    print(f"live links used: {', '.join(names)}"
          + (f"  (note: {', '.join(n for n in BEACON_MACS.values() if n not in names)} "
             f"had no data in these files and is excluded)"
             if len(names) < len(BEACON_MACS) else ""))

    w = max(1, int(round(args.win_s / (1.0 / args.grid_hz))))

    # visits[label] = [(t_abs_start_s, file_idx, i0, i1, dur_s), ...]
    visits = defaultdict(list)
    for fi, (p, grids, shapes, t0, dt, runs) in enumerate(per_file):
        for lab, i0, i1 in runs:
            dur = (i1 - i0) * dt
            if dur < args.min_visit_s:
                continue
            visits[lab].append((t0 + i0 * dt, fi, i0, i1, dur))

    print(f"\nvisits found (>= {args.min_visit_s:.0f}s):")
    for lab in sorted(visits):
        vv = sorted(visits[lab])
        print(f"  {lab:10s} {len(vv)} visit(s): "
              + ", ".join(f"{d:.0f}s" for _, _, _, _, d in vv))

    # ---- chronological split + windowed fingerprints ----
    train_fp, test_fp = defaultdict(list), defaultdict(list)
    split_kind = {}
    for lab, vv in visits.items():
        vv = sorted(vv)
        if len(vv) >= 2:
            train_visits, test_visits = vv[:-1], vv[-1:]
            split_kind[lab] = "visit"
        else:
            _, fi, i0, i1, _ = vv[0]
            mid = (i0 + i1) // 2
            train_visits = [(vv[0][0], fi, i0, mid, 0)]
            test_visits = [(vv[0][0], fi, mid, i1, 0)]
            split_kind[lab] = "half"
        for _, fi, i0, i1, _ in train_visits:
            _, grids, shapes, t0, dt, _ = per_file[fi]
            train_fp[lab] += [v for _, v in
                               window_fingerprints(grids, shapes, macs, i0, i1, w)]
        for _, fi, i0, i1, _ in test_visits:
            _, grids, shapes, t0, dt, _ = per_file[fi]
            test_fp[lab] += [v for _, v in
                              window_fingerprints(grids, shapes, macs, i0, i1, w)]

    labs = sorted(train_fp)
    print(f"\nchronological split ({args.win_s:.0f}s windows):")
    for lab in labs:
        note = " [SINGLE VISIT -- split in half, not an independent " \
               "repeat-visit test]" if split_kind[lab] == "half" else ""
        print(f"  {lab:10s} train {len(train_fp[lab]):3d} windows, "
              f"test {len(test_fp[lab]):3d} windows{note}")

    usable = [l for l in labs if train_fp[l] and test_fp[l]]
    if len(usable) < 2:
        print("\nnot enough labeled data with both train and test windows "
              "to classify", file=sys.stderr)
        return 1

    centroids = {l: np.mean(train_fp[l], axis=0) for l in usable}

    # ---- classify test windows: nearest centroid ----
    confusion = defaultdict(lambda: defaultdict(int))
    for true_lab in usable:
        for vec in test_fp[true_lab]:
            d = {l: float(np.linalg.norm(vec - c)) for l, c in centroids.items()}
            pred = min(d, key=d.get)
            confusion[true_lab][pred] += 1

    print(f"\n=== confusion matrix (rows = true zone, cols = predicted) ===")
    header = "true\\pred".ljust(10) + "".join(l.ljust(10) for l in usable)
    print(header)
    n_correct = n_total = 0
    for true_lab in usable:
        row = confusion[true_lab]
        n_row = sum(row.values())
        line = true_lab.ljust(10)
        for pred_lab in usable:
            line += str(row.get(pred_lab, 0)).ljust(10)
        acc = row.get(true_lab, 0) / n_row if n_row else float("nan")
        print(f"{line}  recall {acc*100:5.1f}%  (n={n_row})")
        n_correct += row.get(true_lab, 0)
        n_total += n_row

    print(f"\noverall holdout accuracy: {n_correct}/{n_total} = "
          f"{100*n_correct/n_total:.1f}%")
    if any(split_kind[l] == "half" for l in usable):
        halved = [l for l in usable if split_kind[l] == "half"]
        print(f"NOTE: {', '.join(halved)} had only one visit -- its "
              f"train/test split is a within-visit time split, not an "
              f"independent repeat-visit holdout like the others. Treat "
              f"its recall as weaker evidence.")
    print("NOTE: single session, same day -- this has not been tested "
          "for stability across time of day, thermal drift, or a "
          "different day's walk.")

    # ---- interpretability: per-link deviation from the weakest-signal
    # centroid, just to show the fingerprint is picking up real spatial
    # structure and not classifying on noise ----
    print(f"\n=== centroid separation (Euclidean, raw fingerprint space) ===")
    for i, l1 in enumerate(usable):
        for l2 in usable[i + 1:]:
            d = float(np.linalg.norm(centroids[l1] - centroids[l2]))
            print(f"  {l1} <-> {l2}: {d:.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
