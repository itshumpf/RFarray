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
  python rff_offline.py data/raw/desk_*.csv --after 960 --max-resid 0.35
"""
import argparse
import csv as csvmod
import glob
import inspect
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

# Read the frame-gate defaults out of dsp.WindowAggregator rather than
# restating them, so the CLI defaults cannot drift away from the library.
_AGG_PARAMS = inspect.signature(WindowAggregator.__init__).parameters
DEFAULT_MAX_RESID = _AGG_PARAMS["max_resid"].default
DEFAULT_MIN_INLIER = _AGG_PARAMS["min_inlier_ratio"].default


class CountingAggregator(WindowAggregator):
    """WindowAggregator that records why frames did not enter a window.

    Acceptance is read off the parent's own behaviour (buffer grew, or a
    window was emitted), never re-derived, so the counts cannot disagree
    with what the pipeline actually did. Only the *attribution* of a
    rejection mirrors dsp's gate order; anything the mirror fails to
    explain lands in `n_rej_other` instead of being quietly absorbed.
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.n_fed = 0            # frames handed to this aggregator
        self.n_unusable = 0       # no RANSAC fit / short frame (est is None)
        self.n_rej_inlier = 0
        self.n_rej_resid = 0
        self.n_rej_other = 0
        self.n_accepted = 0
        self.n_windows = 0

    def feed(self, est, ts_us, rssi):
        self.n_fed += 1
        n_before = len(self._buf)
        obs = super().feed(est, ts_us, rssi)
        if obs is not None or len(self._buf) != n_before:
            self.n_accepted += 1
            if obs is not None:
                self.n_windows += 1
        elif est is None:
            self.n_unusable += 1
        elif est["inlier_ratio"] < self.min_inlier_ratio:
            self.n_rej_inlier += 1
        elif est["resid_std"] > self.max_resid:
            self.n_rej_resid += 1
        else:
            self.n_rej_other += 1
        return obs


class FilterStats:
    """Frame/window accounting for one run, aggregated over all files."""

    def __init__(self, window, max_resid, min_inlier, after, before):
        self.window = window
        self.max_resid = max_resid
        self.min_inlier = min_inlier
        self.after = after
        self.before = before
        self.rows = 0             # CSV data rows read
        self.unparseable = 0      # rows that iter_frames could not decode
        self.excluded_time = 0    # dropped by --after/--before
        self.reached_dsp = 0
        self.unusable = 0
        self.rej_inlier = 0
        self.rej_resid = 0
        self.rej_other = 0
        self.accepted = 0
        self.windows = 0
        # frames that would have been accepted under dsp.py's own defaults,
        # counted per (file, mac) so the baseline window count is exact
        self._default_accept = defaultdict(int)

    def note_default_gate(self, key, est):
        if est is None:
            return
        if est["inlier_ratio"] < DEFAULT_MIN_INLIER:
            return
        if est["resid_std"] > DEFAULT_MAX_RESID:
            return
        self._default_accept[key] += 1

    def absorb(self, agg):
        self.unusable += agg.n_unusable
        self.rej_inlier += agg.n_rej_inlier
        self.rej_resid += agg.n_rej_resid
        self.rej_other += agg.n_rej_other
        self.accepted += agg.n_accepted
        self.windows += agg.n_windows

    @property
    def default_windows(self):
        """Windows the same DSP frames would have formed at dsp.py defaults.

        A window is emitted every `window` accepted frames and the buffer is
        per (file, mac), so this is floor division over measured accept
        counts, not an estimate. It is a baseline for the *gates only*: the
        frames excluded by --after/--before never reached the DSP and are
        not represented here.
        """
        return sum(n // self.window for n in self._default_accept.values())

    def report(self):
        w = 46
        rng = "unrestricted"
        if self.after is not None or self.before is not None:
            lo = "start" if self.after is None else f"{self.after:g}s"
            hi = "end" if self.before is None else f"{self.before:g}s"
            rng = f"[{lo}, {hi})"
        print("\n=== Filter accounting ===")
        print("  time window is seconds of pc_time_us since the first "
              "decodable frame of each input file")
        print(f"  {'CSV data rows read':<{w}}{self.rows:>9}")
        if self.unparseable:
            print(f"  {'rows skipped (undecodable)':<{w}}"
                  f"{self.unparseable:>9}")
        print(f"  {'excluded by --after/--before ' + rng:<{w}}"
              f"{self.excluded_time:>9}")
        print(f"  {'frames reaching the DSP':<{w}}{self.reached_dsp:>9}")
        print(f"  {'no RANSAC fit (unusable frame)':<{w}}{self.unusable:>9}")
        tag_i = " (dsp default)" if self.min_inlier == DEFAULT_MIN_INLIER else ""
        tag_r = " (dsp default)" if self.max_resid == DEFAULT_MAX_RESID else ""
        print(f"  {'rejected by --min-inlier %g%s' % (self.min_inlier, tag_i):<{w}}"
              f"{self.rej_inlier:>9}")
        print(f"  {'rejected by --max-resid %g%s' % (self.max_resid, tag_r):<{w}}"
              f"{self.rej_resid:>9}")
        if self.rej_other:
            print(f"  {'rejected by some other dsp gate':<{w}}"
                  f"{self.rej_other:>9}")
        print(f"  {'frames accepted into windows':<{w}}{self.accepted:>9}")
        print(f"  {'windows formed (after)':<{w}}{self.windows:>9}")
        print(f"  {'windows at dsp defaults, same frames (before)':<{w}}"
              f"{self.default_windows:>9}")
        # say it out loud when a gate removed nothing — silence reads as
        # "not checked", which is how a no-op gate gets mistaken for a
        # working one.
        for name, val, n in (("--min-inlier", self.min_inlier, self.rej_inlier),
                             ("--max-resid", self.max_resid, self.rej_resid)):
            if n == 0:
                print(f"  note: {name} {val:g} rejected NOTHING — it passed "
                      f"100% of the {self.reached_dsp - self.unusable} "
                      "fitted frames.")
        if self.excluded_time:
            pct = self.excluded_time / self.rows if self.rows else 0.0
            print(f"  note: {pct:.1%} of rows were cut by the time window; "
                  "every figure below describes the remainder only.")


def iter_frames(path, after=None, before=None, stats=None):
    """Yield (pc_time_us, mac, rssi, esp_ts_us, csi_vals) rows.

    `after`/`before` are seconds relative to the first decodable frame of
    *this file*, measured on pc_time_us (host clock, shared by all nodes in
    one capture; esp_timestamp_us is node-boot-relative and wraps, so it
    cannot express "seconds into the session"). The interval is half-open:
    after <= t < before. Filtering happens here, before the estimator, so
    excluded frames leave no trace in the unwrap anchor or the CFO
    difference.
    """
    origin = None
    with open(path, newline="") as f:
        for row in csvmod.DictReader(f):
            if stats is not None:
                stats.rows += 1
            try:
                vals = np.fromstring(row["csi_data"], dtype=np.float64,
                                     sep=",")
                pc_us = int(row["pc_time_us"])
                rec = (pc_us, row["mac"].lower(), int(row["rssi"]),
                       int(row["esp_timestamp_us"]), vals)
            except (KeyError, ValueError):
                if stats is not None:
                    stats.unparseable += 1
                continue
            if after is not None or before is not None:
                if origin is None:
                    origin = pc_us
                t = (pc_us - origin) * 1e-6
                if (after is not None and t < after) or \
                        (before is not None and t >= before):
                    if stats is not None:
                        stats.excluded_time += 1
                    continue
            if stats is not None:
                stats.reached_dsp += 1
            yield rec


def collect_observations(paths, window, ref_mac,
                         max_resid=DEFAULT_MAX_RESID,
                         min_inlier=DEFAULT_MIN_INLIER,
                         after=None, before=None, stats=None):
    """Replay all files chronologically -> {mac: [obs, ...]}.

    Estimator/aggregator state is per (file, mac): the ESP clock and the
    unwrap continuity anchor reset between sessions, so state must not
    leak across files. The reference normalizer also restarts per file for
    the same reason.
    """
    by_mac = defaultdict(list)
    for path in sorted(paths):
        estimators = defaultdict(FrameEstimator)
        if stats is None:
            aggregators = defaultdict(
                lambda: WindowAggregator(window=window,
                                         min_inlier_ratio=min_inlier,
                                         max_resid=max_resid))
        else:
            aggregators = defaultdict(
                lambda: CountingAggregator(window=window,
                                           min_inlier_ratio=min_inlier,
                                           max_resid=max_resid))
        ref = ReferenceNormalizer(ref_mac)
        n_rows = 0
        for pc_us, mac, rssi, esp_us, vals in iter_frames(path, after, before,
                                                          stats):
            n_rows += 1
            est = estimators[mac].feed(vals, esp_us)
            if stats is not None:
                stats.note_default_gate((path, mac), est)
            obs = aggregators[mac].feed(est, esp_us, rssi)
            if obs is None:
                continue
            obs, _ = ref.feed(mac, obs)
            obs["ts_pc"] = pc_us * 1e-6
            obs["session"] = os.path.basename(path)
            by_mac[mac].append(obs)
        if stats is not None:
            for agg in aggregators.values():
                stats.absorb(agg)
        print(f"  {os.path.basename(path)}: {n_rows} frames", file=sys.stderr)
    return by_mac


def feature(obs, require_ref=False):
    """(CFO, SFO) feature vector, preferring reference-corrected values.

    With a reference beacon configured, uncorrected windows are dropped:
    mixing raw and corrected values in one source model shifts its
    centroid (see rff_live for the live-side equivalent).
    """
    if require_ref and "cfo_ref" not in obs and "sfo_ref" not in obs:
        return None
    cfo = obs.get("cfo_ref", obs.get("cfo"))
    sfo = obs.get("sfo_ref", obs.get("sfo"))
    if cfo is None or sfo is None:
        return None
    return np.array([cfo, sfo])


def report(by_mac, min_windows, ref_mac, stats=None):
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
        feats = [f for f in (feature(o, bool(ref_mac)) for o in obs_list)
                 if f is not None]
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
        feats = [f for f in (feature(o, bool(ref_mac)) for o in by_mac[mac])
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
        if stats is not None:
            print(f"SCOPE: filtered run — {stats.reached_dsp} of "
                  f"{stats.rows} rows reached the DSP, "
                  f"{stats.windows} windows formed "
                  f"(dsp defaults on the same frames: "
                  f"{stats.default_windows}). This accuracy describes that "
                  "subset only; see the filter accounting above.")
    return disc, trackers


def persist(by_mac, disc, db_path, require_ref=False):
    store = Store(db_path)
    now = time.time()
    for mac, obs_list in by_mac.items():
        sid = store.source_id(mac, now=now)
        for o in obs_list:
            f = feature(o, require_ref)
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
    ap.add_argument("--max-resid", type=float, default=DEFAULT_MAX_RESID,
                    help="drop frames whose RANSAC residual std exceeds this "
                         f"(default {DEFAULT_MAX_RESID:g}, read from "
                         "rff.dsp.WindowAggregator)")
    ap.add_argument("--min-inlier", type=float, default=DEFAULT_MIN_INLIER,
                    help="drop frames whose RANSAC inlier ratio is below this "
                         f"(default {DEFAULT_MIN_INLIER:g}, read from "
                         "rff.dsp.WindowAggregator)")
    ap.add_argument("--after", type=float, default=None,
                    help="keep only frames at or after this many SECONDS of "
                         "pc_time_us (host clock) measured from the first "
                         "decodable frame of each input file; t=0 is that "
                         "file's own first frame, not wall clock and not "
                         "esp_timestamp_us (which is boot-relative and wraps)")
    ap.add_argument("--before", type=float, default=None,
                    help="keep only frames strictly before this many SECONDS "
                         "on the same pc_time_us clock and the same per-file "
                         "t=0 origin as --after; the interval is half-open, "
                         "after <= t < before")
    ap.add_argument("--only-macs", help="comma-separated MACs to classify "
                    "(others still used for reference correction, then "
                    "dropped from the analysis) — e.g. to exclude a "
                    "clock-twin from the discrimination test")
    ap.add_argument("--db", nargs="?", const=DEFAULT_DB, default=None,
                    help="persist observations+models to SQLite "
                    "(default path data/rff.db)")
    args = ap.parse_args()

    if (args.after is not None and args.before is not None
            and args.after >= args.before):
        print(f"--after {args.after:g} is not before --before "
              f"{args.before:g}; that selects no frames", file=sys.stderr)
        return 1

    # The accounting block only appears when the run is not the stock one,
    # so an invocation without the new flags stays byte-for-byte as before.
    filtered = (args.max_resid != DEFAULT_MAX_RESID
                or args.min_inlier != DEFAULT_MIN_INLIER
                or args.after is not None
                or args.before is not None)
    stats = (FilterStats(args.window, args.max_resid, args.min_inlier,
                         args.after, args.before) if filtered else None)

    paths = []
    for pat in args.csvs:
        paths.extend(glob.glob(pat))
    if not paths:
        print("no CSV files matched", file=sys.stderr)
        return 1

    print(f"replaying {len(paths)} session file(s)...", file=sys.stderr)
    by_mac = collect_observations(paths, args.window, args.ref_mac,
                                  max_resid=args.max_resid,
                                  min_inlier=args.min_inlier,
                                  after=args.after, before=args.before,
                                  stats=stats)
    if stats is not None:
        stats.report()
    if args.only_macs:
        keep = {m.strip().lower() for m in args.only_macs.split(",")}
        # reference correction already applied during collection; now
        # restrict the analysis to the chosen classification targets
        by_mac = {m: o for m, o in by_mac.items() if m in keep}
        print(f"(classifying only {len(by_mac)} of the collected sources)",
              file=sys.stderr)
    result = report(by_mac, args.min_windows, args.ref_mac, stats)
    if result is None:
        return 1
    if args.db:
        persist(by_mac, result[0], args.db, require_ref=bool(args.ref_mac))
    return 0


if __name__ == "__main__":
    sys.exit(main())
