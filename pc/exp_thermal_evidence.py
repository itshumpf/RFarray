#!/usr/bin/env python3
r"""EXPERIMENT: is there a thermal signature in the existing captures?

Read-only. Writes nothing into data/, pc/rff/, pc/occ/, site/, firmware/
or any existing entry point. Creates only its own outputs (JSON/PNG) at
paths given on the command line.

What this is for
----------------
`docs/LOT_HYPOTHESIS.md` §5 established that each beacon's
session-to-session SFO wander (0.00570 rad/sc) is 2.4x the spread between
the three units' grand means (0.00237), and that within the 42-minute
prefix of one capture the three pairs' separations range from 0.05 to
9.08 sigma across six consecutive chunks (those two extremes belong to
different pairs). The fingerprint is not stable in time and that
instability dominates everything else.

**No temperature was ever recorded anywhere in this project.** Thermal
drift is the leading hypothesis for that instability and nothing more.
Nothing in this file measures temperature, and no output of it may be
described as having measured temperature. Every result here is
correlational at best.

The three tests
---------------
1. `trajectory` -- power-on warm-up transient. A board switched on heats
   for ~10-30 min before plateauing. If crystal temperature drives the
   offset, every capture should show a systematic drift in its opening
   minutes that then flattens, sharing a direction across captures.

   Two controls are built in because the naive version of this test is
   not sound:

   (a) **Back-to-back captures.** A capture start is NOT a power-on. Many
       captures in `data/raw/` begin seconds after the previous one ended
       (see `sessions`), so the transmitter demonstrably did not cool.
       If the "warm-up" transient appears just as strongly in those, it
       is not board warm-up.

   (b) **Matched later intervals.** The opening T minutes are compared
       against every other T-minute interval in the same capture. If the
       opening interval's drift rate is unremarkable inside that
       distribution, there is no transient -- only ongoing wander.

2. `tod` -- time of day. Underpowered by construction; reported as a
   scatter, with n stated, and no curve fitted.

3. `wander` -- does discarding the warm-up region reduce the
   session-to-session wander figure? With a tail-drop control, because
   discarding any 25% of a session also changes n and the window mix.

The estimator-settling confound
-------------------------------
The obvious objection to test 1 is that the estimator converges over the
opening minutes and that would look like drift. Read from the code, the
two feature spaces differ in exactly the way that matters:

  mode='raw'  (`obs['cfo']`, `obs['sfo']`) -- `FrameEstimator` carries
      only a ONE-FRAME lookback (`_prev_mean`, `_prev_intercept`,
      `_prev_ts`) and `WindowAggregator` clears `_buf` on every emit.
      No state in this path spans more than one window, so a
      minutes-long trend in raw per-window SFO cannot be filter
      settling. The single exception is the unwrap continuity anchor,
      which is unset for the first frame of a file and therefore can
      only affect window 0.

  mode='ref'  (`obs['cfo_ref']`, `obs['sfo_ref']`) -- subtracts
      `ReferenceNormalizer`'s Kalman track of the reference beacon.
      This one CAN settle, and for the reference beacon itself
      `sfo_ref` is its own innovation against its own smoothed track,
      which removes a slow trend by construction.

So raw is the primary space for test 1 and ref is the control, which is
the opposite of the convention used elsewhere in this repo. Both are
reported everywhere.

The empirical version of the same check needs no extra code: slice a
capture from the middle of the file, collect it under its own tag, and
run `trajectory` against that tag. Every piece of pipeline state gets a
fresh cold start at the slice's t=0 while the transmitter has been on for
hours. If a fresh opening ramp appears there, the ramp belongs to the
start of processing; if it does not, the ramp seen at real capture starts
is not an artifact of the offline estimator.

No DSP is reimplemented. Observations come from `twin_probe.load()`,
whose cache shards are produced by `twin_probe collect`, which calls
`rff_offline.collect_observations`. The chain to the production estimator
is unbroken:

    rff.dsp.FrameEstimator / WindowAggregator
      -> rff.reference.ReferenceNormalizer
        -> rff_offline.collect_observations
          -> twin_probe collect (cache shard)
            -> twin_probe.load
              -> this file (binning, statistics, plotting only)

numpy and matplotlib only, both already in `pc/requirements.txt`. pandas
and scipy are not used.

Usage
-----
  export TWIN_PROBE_CACHE=/scratch/thermal_cache   # NOT data/cache
  python pc/twin_probe.py collect --tag thermal data/raw/rx_20260714_011619.csv
  python pc/exp_thermal_evidence.py sessions --raw-dir data/raw
  python pc/exp_thermal_evidence.py trajectory --tag thermal --json traj.json
  python pc/exp_thermal_evidence.py wander --tag thermal --skip-list 5,10,15
  python pc/exp_thermal_evidence.py tod --tag thermal
  python pc/exp_thermal_evidence.py plots --tag thermal --outdir docs/img
"""
import argparse
import glob
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from twin_probe import load                    # noqa: E402

# docs/HANDOFF.md "Hardware inventory (2026-07-15)".
BEACONS = ["a4:f0:0f:77:91:20", "28:05:a5:2f:fa:48", "f4:2d:c9:70:72:30"]

# docs/LOT_HYPOTHESIS.md 5, reference-corrected. These are the two
# yardsticks a warm-up transient has to be measured against.
BETWEEN_UNIT_SD = 0.00237      # sd over the 3 units of their grand means
WITHIN_UNIT_SD = 0.00570       # mean within-unit across-session sd

# Local clock. desk_20260713_104513.csv's first pc_time_us is 15:45:14
# UTC and the file is named 104513; docs/TWIN_INVESTIGATION.md 4
# independently states "15:45-21:06 UTC = 10:45-16:06 local". Two routes,
# same answer. Used only for the time-of-day scatter.
UTC_OFFSET_H = -5.0


# ------------------------------------------------------------- file times

def file_first_last_us(path):
    """(first, last) pc_time_us of a capture CSV, without reading it all.

    The first data line is read directly; the last is found by seeking to
    the tail. Used for capture spans and inter-capture gaps only.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return None, None
    if size < 2:
        return None, None
    first = None
    with open(path, "rb") as f:
        f.readline()                       # header
        for _ in range(64):                # skip any malformed leading rows
            line = f.readline()
            if not line:
                break
            tok = line.split(b",", 1)[0]
            if tok.isdigit():
                first = int(tok)
                break
        if first is None:
            return None, None
        back = min(size, 4 << 20)
        f.seek(size - back)
        tail = f.read(back)
    last = None
    for line in reversed(tail.split(b"\n")):
        tok = line.split(b",", 1)[0]
        if tok.isdigit() and len(tok) >= 10:
            last = int(tok)
            break
    return first, last


def local_dt(us):
    import datetime
    return (datetime.datetime.utcfromtimestamp(us / 1e6)
            + datetime.timedelta(hours=UTC_OFFSET_H))


def local_hour(us):
    """Fractional local hour-of-day of a pc_time_us stamp."""
    d = local_dt(us)
    return d.hour + d.minute / 60.0 + d.second / 3600.0


def gap_before(rows, i):
    """Minutes between the end of the last capture that finished before
    `rows[i]` started, and its start.

    Only captures that ENDED before this one began count. `desk_*` and
    `node3_*` are two receivers recording the same session concurrently,
    so a naive "latest end so far" gives a negative gap for the second
    file of such a pair. A concurrent capture means the board was on at
    that instant, which is a gap of zero, not a negative one.
    """
    t0 = rows[i]["t0"]
    ends = [x["t1"] for j, x in enumerate(rows) if j != i and x["t1"] <= t0]
    overlap = any(j != i and x["t0"] <= t0 < x["t1"]
                  for j, x in enumerate(rows))
    if overlap:
        return 0.0
    if not ends:
        return float("nan")
    return (t0 - max(ends)) / 6e7


# -------------------------------------------------------------- sessions

def cmd_sessions(args):
    """Capture inventory: span, local start, and gap since the previous
    capture.

    The gap is the load-bearing column. `docs/LOT_HYPOTHESIS.md` and this
    file both want to treat a capture start as an independent trial with
    a cold board. That premise is testable here and it does not survive:
    several captures begin within seconds of the previous one ending, so
    for those the transmitter was demonstrably still on and still warm.

    Stated precisely, because the asymmetry matters:
      - WARM is established. A capture starting 6 s after another ended
        proves the beacon was powered and transmitting 6 s earlier.
      - COLD is NOT established. A long gap between captures only means
        nothing was recorded. Nothing in the repo records whether any
        board was powered off, so "cold" here means "unobserved for N
        hours", never "known to have been off".
    """
    paths = sorted(glob.glob(os.path.join(args.raw_dir, "*.csv")))
    rows = []
    for p in paths:
        a, b = file_first_last_us(p)
        if a is None or b is None or b <= a:
            continue
        rows.append(dict(path=p, name=os.path.basename(p), t0=a, t1=b,
                         span_min=(b - a) / 6e7,
                         mb=os.path.getsize(p) / 1e6))
    rows.sort(key=lambda r: r["t0"])
    for i, r in enumerate(rows):
        r["gap_min"] = gap_before(rows, i)
        r["local_h"] = local_hour(r["t0"])
    print(f"{len(rows)} capture files with a readable timeline in "
          f"{args.raw_dir}")
    print(f"\n{'capture':<32}{'local start':>12}{'span min':>10}"
          f"{'gap min':>10}{'MB':>8}  class")
    for r in rows:
        g = r["gap_min"]
        if math.isnan(g):
            cls = "first-in-dataset"
        elif g <= args.warm_max_min:
            cls = "WARM (board on <=%.0f min before)" % args.warm_max_min
        elif g >= args.cold_min_min * 60:
            cls = "unobserved >=%.0f h" % args.cold_min_min
        else:
            cls = "intermediate"
        stamp = local_dt(r["t0"]).strftime("%m-%d %H:%M")
        gtxt = "-" if math.isnan(g) else "%.1f" % g
        print(f"{r['name']:<32}{stamp:>12}{r['span_min']:>10.1f}"
              f"{gtxt:>10}{r['mb']:>8.0f}  {cls}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(rows, f, indent=1)
        print(f"\nwrote {args.json}")
    return 0


# ------------------------------------------------------------- trajectory

def obs_series(blob, mac, mode):
    """[(elapsed_s, value_sfo, value_cfo)] for one source in one session.

    Elapsed time is measured from the first frame of the capture file, read
    from the CSV, not from the first emitted window. `pc_time_us` is
    stamped per serial drain batch rather than per frame
    (`docs/HANDOFF.md` trap #1); at the 30 s binning used here that is
    immaterial, and it is the same basis `docs/WINDOW_CONVERGENCE.md` 6
    used for its census.
    """
    starts = {}
    for p in blob["paths"]:
        a, _ = file_first_last_us(p)
        if a is not None:
            starts[os.path.basename(p)] = a * 1e-6
    out = defaultdict(list)
    for o in blob["by_mac"].get(mac, []):
        sess = o["session"]
        t0 = starts.get(sess)
        if t0 is None:
            continue
        if mode == "raw":
            s, c = o.get("sfo"), o.get("cfo")
        else:
            s, c = o.get("sfo_ref"), o.get("cfo_ref")
        if s is None or c is None:
            continue
        out[sess].append((o["ts_pc"] - t0, float(s), float(c)))
    for k in out:
        out[k].sort(key=lambda r: r[0])
    return out


def binned(series, bin_s, min_per_bin):
    """Median SFO / CFO per fixed-width elapsed-time bin.

    Returns (centres_min, med_sfo, iqr_sfo, med_cfo, n). Bins holding
    fewer than `min_per_bin` windows are dropped rather than reported as
    noisy point estimates.
    """
    if not series:
        return (np.empty(0),) * 5
    t = np.array([r[0] for r in series])
    s = np.array([r[1] for r in series])
    c = np.array([r[2] for r in series])
    idx = (t // bin_s).astype(int)
    cen, ms, iq, mc, ns = [], [], [], [], []
    for b in range(idx.min(), idx.max() + 1):
        m = idx == b
        n = int(m.sum())
        if n < min_per_bin:
            continue
        cen.append((b + 0.5) * bin_s / 60.0)
        ms.append(float(np.median(s[m])))
        iq.append(float(np.subtract(*np.percentile(s[m], [75, 25]))))
        mc.append(float(np.median(c[m])))
        ns.append(n)
    return (np.array(cen), np.array(ms), np.array(iq), np.array(mc),
            np.array(ns))


def theil_sen(x, y, max_pairs=20000, seed=0):
    """Median of pairwise slopes. Robust, no scipy, deterministic.

    Exhaustive for small n; a seeded random subsample of pairs above
    `max_pairs` so the cost stays bounded and the result stays
    reproducible.
    """
    n = len(x)
    if n < 3:
        return float("nan")
    if n * (n - 1) // 2 <= max_pairs:
        i, j = np.triu_indices(n, 1)
    else:
        rng = np.random.default_rng(seed)
        i = rng.integers(0, n, max_pairs)
        j = rng.integers(0, n, max_pairs)
        ok = i != j
        i, j = i[ok], j[ok]
    dx = x[j] - x[i]
    ok = dx != 0
    if not ok.any():
        return float("nan")
    return float(np.median((y[j] - y[i])[ok] / dx[ok]))


def window_slopes(cen, val, T):
    """Theil-Sen slope (rad/sc per min) inside each successive T-minute
    interval of the trajectory: [0,T), [T,2T), ...

    This is the matched-later control. The warm-up claim is not "the
    opening minutes drift" -- a wandering signal drifts everywhere. It is
    "the opening minutes drift *more than the rest of the same capture
    does*". Only the second is testable without a thermometer.
    """
    out = []
    if len(cen) == 0:
        return out
    k = 0
    while (k + 1) * T <= cen.max() + 1e-9:
        m = (cen >= k * T) & (cen < (k + 1) * T)
        if m.sum() >= 4:
            out.append((k, theil_sen(cen[m], val[m]),
                        float(np.median(val[m])), int(m.sum())))
        k += 1
    return out


def trials(blob, macs, mode, args):
    """One trial per (session, source) with enough span and windows."""
    rows = []
    for mac in macs:
        for sess, ser in obs_series(blob, mac, mode).items():
            if len(ser) < args.min_windows:
                continue
            span = (ser[-1][0]) / 60.0
            if span < args.min_span_min:
                continue
            cen, ms, iq, mc, ns = binned(ser, args.bin_s, args.min_per_bin)
            if len(cen) < args.min_bins:
                continue
            T = args.warm_min
            early = ms[cen < T]
            late = ms[cen >= T]
            if len(early) < 3 or len(late) < 3:
                continue
            slopes = window_slopes(cen, ms, T)
            s0 = next((s for k, s, _, _ in slopes if k == 0), float("nan"))
            later = [s for k, s, _, _ in slopes if k > 0]
            # dispersion early vs late: a settling filter should shrink
            # the spread as it converges; a physical ramp need not.
            iq_e = float(np.median(iq[cen < T])) if (cen < T).any() else float("nan")
            iq_l = float(np.median(iq[cen >= T])) if (cen >= T).any() else float("nan")
            rows.append(dict(
                session=sess, mac=mac, mode=mode, span_min=float(span),
                n_windows=len(ser),
                med_early=float(np.median(early)),
                med_late=float(np.median(late)),
                d_warm=float(np.median(early) - np.median(late)),
                slope0=float(s0),
                slope_later_absmed=(float(np.median(np.abs(later)))
                                    if later else float("nan")),
                n_later=len(later),
                slope_rank=(float(np.mean(np.abs(later) < abs(s0)))
                            if later and not math.isnan(s0)
                            else float("nan")),
                iqr_early=iq_e, iqr_late=iq_l,
                traj_cen=cen.tolist(), traj_sfo=ms.tolist(),
                traj_iqr=iq.tolist(),
                traj_n=ns.tolist()))
    return rows


def binom_two_sided(k, n, p=0.5):
    """Exact two-sided binomial p-value. math.comb, no scipy."""
    if n == 0:
        return float("nan")
    probs = [math.comb(n, i) * p ** i * (1 - p) ** (n - i)
             for i in range(n + 1)]
    obs = probs[k]
    return float(min(1.0, sum(q for q in probs if q <= obs * (1 + 1e-12))))


def gaps_for(blob, args):
    """Inter-capture gap in minutes, keyed by session basename."""
    paths = sorted(glob.glob(os.path.join(args.raw_dir, "*.csv")))
    rows = []
    for p in paths:
        a, b = file_first_last_us(p)
        if a is not None and b is not None and b > a:
            rows.append(dict(t0=a, t1=b, name=os.path.basename(p)))
    rows.sort(key=lambda r: r["t0"])
    return {r["name"]: gap_before(rows, i) for i, r in enumerate(rows)}


def cmd_trajectory(args):
    macs = [m.strip().lower() for m in args.macs.split(",")]
    blob = load(args.tag)
    gaps = gaps_for(blob, args)
    allrows = {}
    for mode in ("raw", "ref"):
        rows = trials(blob, macs, mode, args)
        allrows[mode] = rows
        print(f"\n{'='*100}")
        print(f"TEST 1 -- opening-interval drift, mode={mode}  "
              f"(T = {args.warm_min:g} min, {args.bin_s:g} s bins)")
        print(f"{'='*100}")
        if not rows:
            print("no trial met the span/window gates")
            continue
        print(f"{'session':<30}{'source':<12}{'span':>7}{'wins':>7}"
              f"{'gap min':>9}{'dSFO warm':>11}{'slope0':>11}"
              f"{'|later| med':>12}{'rank':>7}{'IQR e/l':>16}")
        for r in sorted(rows, key=lambda r: (r["session"], r["mac"])):
            g = gaps.get(r["session"], float("nan"))
            iqtxt = "%.5f/%.5f" % (r["iqr_early"], r["iqr_late"])
            print(f"{r['session'][:29]:<30}{r['mac'][-8:]:<12}"
                  f"{r['span_min']:>7.0f}{r['n_windows']:>7}"
                  f"{g:>9.1f}{r['d_warm']:>+11.5f}{r['slope0']:>+11.5f}"
                  f"{r['slope_later_absmed']:>12.5f}"
                  f"{r['slope_rank']:>7.2f}{iqtxt:>16}")

        d = np.array([r["d_warm"] for r in rows])
        s0 = np.array([r["slope0"] for r in rows])
        sl = np.array([r["slope_later_absmed"] for r in rows])
        rk = np.array([r["slope_rank"] for r in rows])
        npos = int((d > 0).sum())
        print(f"\n  trials: {len(rows)}  "
              f"({len({r['session'] for r in rows})} captures, "
              f"{len({r['mac'] for r in rows})} units)")
        print(f"  dSFO(first {args.warm_min:g} min - rest): "
              f"median {np.median(d):+.5f}  "
              f"|median| {abs(np.median(d)):.5f}  "
              f"p10..p90 {np.percentile(d,10):+.5f}..{np.percentile(d,90):+.5f}  "
              f"max|.| {np.abs(d).max():.5f}")
        print(f"    vs between-unit spread {BETWEEN_UNIT_SD:.5f} : "
              f"median {abs(np.median(d))/BETWEEN_UNIT_SD:.2f}x, "
              f"p90|.| {np.percentile(np.abs(d),90)/BETWEEN_UNIT_SD:.2f}x")
        print(f"    vs session-to-session wander {WITHIN_UNIT_SD:.5f} : "
              f"median {abs(np.median(d))/WITHIN_UNIT_SD:.2f}x, "
              f"p90|.| {np.percentile(np.abs(d),90)/WITHIN_UNIT_SD:.2f}x")
        print(f"  direction: {npos}/{len(d)} positive  "
              f"(exact two-sided binomial p = "
              f"{binom_two_sided(npos, len(d)):.3f})")
        ok = ~np.isnan(s0) & ~np.isnan(sl)
        print(f"  |opening slope| {np.median(np.abs(s0[ok])):.6f} vs "
              f"|later slopes| {np.median(sl[ok]):.6f} rad/sc/min  "
              f"ratio {np.median(np.abs(s0[ok]))/max(np.median(sl[ok]),1e-12):.2f}x")
        rk = rk[~np.isnan(rk)]
        if len(rk):
            print(f"  opening-slope rank among later intervals of the same "
                  f"capture: median {np.median(rk):.2f} "
                  f"(0.50 = opening interval is typical; 1.00 = steepest)")
        # warm vs unobserved-gap split
        warm = [r for r in rows
                if gaps.get(r["session"], float("nan")) <= args.warm_max_min]
        cold = [r for r in rows
                if gaps.get(r["session"], float("inf")) >= args.cold_min_min * 60]
        for nm, grp in (("back-to-back starts (board provably on)", warm),
                        ("no capture for >= %gh before" % args.cold_min_min,
                         cold)):
            if not grp:
                continue
            dd = np.abs([r["d_warm"] for r in grp])
            print(f"  {nm}: n={len(grp)}  median |dSFO| {np.median(dd):.5f}")
        # Is the excursion where the data is thin? A physical transient
        # should not care how densely the source was heard; measurement
        # noise should. Rank correlation, so one sparse outlier cannot
        # set it.
        rate = np.array([r["n_windows"] / max(r["span_min"], 1e-9)
                         for r in rows])
        ad = np.abs(d)
        if len(rows) >= 6:
            rr = float(np.corrcoef(np.argsort(np.argsort(rate)),
                                   np.argsort(np.argsort(ad)))[0, 1])
            med = np.median(rate)
            print(f"  windows/min vs |dSFO|: rank r {rr:+.2f}  "
                  f"median |dSFO| in the sparse half "
                  f"{np.median(ad[rate < med]):.5f} vs dense half "
                  f"{np.median(ad[rate >= med]):.5f}")
        # dispersion, the settling tell
        ie = np.array([r["iqr_early"] for r in rows])
        il = np.array([r["iqr_late"] for r in rows])
        m = ~np.isnan(ie) & ~np.isnan(il)
        print(f"  within-bin SFO IQR: early {np.median(ie[m]):.5f}  "
              f"late {np.median(il[m]):.5f}  "
              f"ratio {np.median(ie[m])/max(np.median(il[m]),1e-12):.2f}x  "
              f"(a settling filter should give early >> late)")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"warm_min": args.warm_min, "bin_s": args.bin_s,
                       "gaps": gaps, "rows": allrows}, f)
        print(f"\nwrote {args.json}")
    return 0


# ----------------------------------------------------------------- wander

def session_means(blob, macs, mode, skip_min, drop_tail_min, min_windows,
                  only=None):
    """Per (source, session) mean SFO, optionally trimming the opening
    `skip_min` minutes or the closing `drop_tail_min` minutes.

    The tail-drop control exists because discarding the first 15 minutes
    of every session also removes windows, shifts the window mix and
    shortens each session. Any reduction in wander has to beat what
    discarding an equally long slice from the other end achieves, or it
    is not evidence about warm-up specifically.
    """
    per = defaultdict(dict)
    for mac in macs:
        for sess, ser in obs_series(blob, mac, mode).items():
            if not ser or (only is not None and sess not in only):
                continue
            t = np.array([r[0] for r in ser]) / 60.0
            s = np.array([r[1] for r in ser])
            if drop_tail_min:
                keep = t <= (t.max() - drop_tail_min)
            else:
                keep = t >= skip_min
            if keep.sum() < min_windows:
                continue
            per[mac][sess] = float(s[keep].mean())
    return per


def long_enough(blob, macs, mode, need_min, min_windows):
    """Sessions that still have >= `min_windows` windows for at least one
    source after both the opening and the closing `need_min` minutes are
    removed.

    Every variant is restricted to this set. Without it the comparison is
    worthless: the seven concurrent sessions include three that are
    shorter than 15 minutes, so "skip the first 15 minutes" silently
    becomes "drop three sessions", and the wander figure then changes
    because the session set changed, not because warm-up was removed.
    """
    out = set()
    for mac in macs:
        for sess, ser in obs_series(blob, mac, mode).items():
            t = np.array([r[0] for r in ser]) / 60.0
            if not len(t):
                continue
            if ((t >= need_min).sum() >= min_windows
                    and (t <= t.max() - need_min).sum() >= min_windows):
                out.add(sess)
    return out


def decomp(per, macs):
    gm, wsd, ns = {}, {}, {}
    for m in macs:
        v = np.array(list(per.get(m, {}).values()))
        if len(v) < 2:
            continue
        gm[m], wsd[m], ns[m] = float(v.mean()), float(v.std(ddof=1)), len(v)
    if len(gm) < 2:
        return None
    b = float(np.std(list(gm.values()), ddof=1))
    w = float(np.mean(list(wsd.values())))
    return dict(between=b, within=w, ratio=w / b if b else float("nan"),
                gm=gm, wsd=wsd, ns=ns)


def boot_ratio(per, macs, n_boot, seed=0):
    """Resample SESSIONS with replacement -> CI on within, between, ratio.

    n is 7 sessions and 3 units. A sd computed from 7 points moves a lot
    under resampling, and a reduction that does not survive this is not a
    reduction. Sessions are the resampling unit because they are the
    replicate the wander figure is defined over.
    """
    sessions = sorted({s for m in macs for s in per.get(m, {})})
    if len(sessions) < 3:
        return None
    rng = np.random.default_rng(seed)
    out = defaultdict(list)
    for _ in range(n_boot):
        pick = rng.integers(0, len(sessions), len(sessions))
        sub = {m: {f"{sessions[i]}#{k}": per[m][sessions[i]]
                   for k, i in enumerate(pick) if sessions[i] in per.get(m, {})}
               for m in macs}
        d = decomp(sub, macs)
        if d is None:
            continue
        for k in ("between", "within", "ratio"):
            out[k].append(d[k])
    return {k: (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)))
            for k, v in out.items() if v}


def cmd_wander(args):
    macs = [m.strip().lower() for m in args.macs.split(",")]
    blob = load(args.tag)
    only = ({s.strip() for s in args.sessions.split(",")}
            if args.sessions else None)
    skips = [float(x) for x in args.skip_list.split(",")]
    for mode in (["ref", "raw"] if args.mode == "both" else [args.mode]):
        print(f"\n{'='*92}")
        print(f"TEST 3 -- does discarding the opening minutes reduce "
              f"session-to-session wander?  mode={mode}")
        print(f"{'='*92}")
        keep = long_enough(blob, macs, mode, max(skips), args.min_windows)
        if only:
            keep &= only
        print(f"sessions retained by every variant "
              f"(span allows both a {max(skips):g} min head-trim and a "
              f"{max(skips):g} min tail-trim): {len(keep)}")
        for s in sorted(keep):
            print(f"    {s}")
        dropped = ({s for m in macs
                    for s in obs_series(blob, m, mode)} - keep)
        if dropped:
            print(f"  excluded as too short: {', '.join(sorted(dropped))}")
        variants = [("baseline (all windows)", 0.0, 0.0)]
        for t in skips:
            variants.append((f"skip first {t:g} min", t, 0.0))
        for t in skips:
            variants.append((f"CONTROL drop last {t:g} min", 0.0, t))
        print(f"\n{'variant':<26}{'between':>10}{'within':>10}{'ratio':>8}"
              f"{'within 95% CI':>22}{'sessions/unit':>15}")
        base = None
        rows = []
        for name, skip, tail in variants:
            per = session_means(blob, macs, mode, skip, tail,
                                args.min_windows, only=keep)
            d = decomp(per, macs)
            if d is None:
                print(f"{name:<26}  (insufficient data)")
                continue
            ci = boot_ratio(per, macs, args.boot, args.seed) or {}
            w = ci.get("within", (float('nan'), float('nan')))
            if base is None:
                base = d
            ns = "/".join(str(d["ns"].get(m, 0)) for m in macs)
            print(f"{name:<26}{d['between']:>10.5f}{d['within']:>10.5f}"
                  f"{d['ratio']:>8.2f}"
                  f"{f'[{w[0]:.5f}, {w[1]:.5f}]':>22}{ns:>15}")
            rows.append((name, d, ci))
        if base:
            print(f"\n  reference values from docs/LOT_HYPOTHESIS.md 5 "
                  f"(reference-corrected, 7 concurrent sessions): "
                  f"between {BETWEEN_UNIT_SD:.5f}, within "
                  f"{WITHIN_UNIT_SD:.5f}, ratio "
                  f"{WITHIN_UNIT_SD/BETWEEN_UNIT_SD:.2f}")
            print(f"  change vs this run's own baseline:")
            for name, d, ci in rows[1:]:
                w = ci.get("within", (float('nan'), float('nan')))
                overlaps = not (w[1] < base["within"] or w[0] > base["within"])
                print(f"    {name:<26} within "
                      f"{d['within']:.5f} "
                      f"({(d['within']/base['within']-1)*100:+.0f}%)  "
                      f"CI {'includes' if overlaps else 'EXCLUDES'} baseline")
            print("\n  per-unit across-session sd:")
            for name, d, _ in rows:
                print(f"    {name:<26}" + "".join(
                    f"{d['wsd'].get(m, float('nan')):>11.5f}" for m in macs))
            print(f"    {'(units, in order)':<26}" +
                  "".join(f"{m[-8:]:>11}" for m in macs))
    return 0


# -------------------------------------------------------------------- tod

def cmd_tod(args):
    """TEST 2 -- stable-region offset against local time of day.

    Underpowered by construction and reported as such. Captures exist on
    five calendar days only, no capture runs continuously across a day
    boundary, and several share a start hour. A scatter is printed and no
    curve is fitted; the correlation is shown only so that its smallness
    is on the record.
    """
    macs = [m.strip().lower() for m in args.macs.split(",")]
    blob = load(args.tag)
    starts = {}
    for p in blob["paths"]:
        a, _ = file_first_last_us(p)
        if a is not None:
            starts[os.path.basename(p)] = a
    for mode in (["raw", "ref"] if args.mode == "both" else [args.mode]):
        print(f"\n{'='*80}")
        print(f"TEST 2 -- time of day, mode={mode} "
              f"(windows after minute {args.skip_min:g} only)")
        print(f"{'='*80}")
        pts = defaultdict(list)
        for mac in macs:
            for sess, ser in obs_series(blob, mac, mode).items():
                t = np.array([r[0] for r in ser]) / 60.0
                s = np.array([r[1] for r in ser])
                keep = t >= args.skip_min
                if keep.sum() < args.min_windows:
                    continue
                us = starts.get(sess)
                if us is None:
                    continue
                # mid-point of the retained region, in local hours
                mid_us = us + (t[keep].mean() * 60e6)
                pts[mac].append((local_hour(mid_us), float(s[keep].mean()),
                                 sess, int(keep.sum())))
        print(f"{'source':<20}{'local h':>9}{'mean SFO':>12}{'wins':>7}  session")
        for mac in macs:
            for h, v, sess, n in sorted(pts[mac]):
                print(f"{mac:<20}{h:>9.2f}{v:>+12.5f}{n:>7}  {sess}")
        print()
        for mac in macs:
            p = pts[mac]
            if len(p) < 3:
                print(f"{mac}: n={len(p)} -- too few points to say anything")
                continue
            h = np.array([x[0] for x in p])
            v = np.array([x[1] for x in p])
            r = float(np.corrcoef(h, v)[0, 1]) if h.std() > 0 else float("nan")
            print(f"{mac}: n={len(p)} points spanning local "
                  f"{h.min():.1f}h..{h.max():.1f}h, "
                  f"{len(set(np.round(h)))} distinct hours; "
                  f"SFO range {v.max()-v.min():.5f}; Pearson r={r:+.2f}")
        print("\n  No curve is fitted. With this many points spread over "
              "five calendar days,\n  any shape read into the scatter "
              "would be a shape read into noise.")
    return 0


# ------------------------------------------------------------------ plots

def cmd_plots(args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    macs = [m.strip().lower() for m in args.macs.split(",")]
    blob = load(args.tag)
    gaps = gaps_for(blob, args)
    os.makedirs(args.outdir, exist_ok=True)
    colour = {m: c for m, c in zip(BEACONS, ["#1f77b4", "#d62728", "#2ca02c"])}

    for mode in ("raw", "ref"):
        rows = trials(blob, macs, mode, args)
        if not rows:
            continue
        # --- panel 1: every trajectory, referenced to its own late median
        fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
        for ax, want_warm in zip(axes, (False, True)):
            n = 0
            grid = np.arange(0.25, args.plot_max_min, 0.5)
            stack = []
            for r in rows:
                g = gaps.get(r["session"], float("nan"))
                is_warm = g <= args.warm_max_min
                if is_warm != want_warm:
                    continue
                cen = np.array(r["traj_cen"])
                y = np.array(r["traj_sfo"]) - r["med_late"]
                ax.plot(cen, y, lw=1.0, alpha=0.55,
                        color=colour.get(r["mac"], "#777777"))
                stack.append(np.interp(grid, cen, y, left=np.nan,
                                       right=np.nan))
                n += 1
            if stack:
                # median across trials at each elapsed minute. A power-on
                # warm-up transient would show here as a shared excursion
                # in the first bins decaying to zero; ordinary wander
                # cancels because it has no shared direction.
                med = np.nanmedian(np.vstack(stack), axis=0)
                ax.plot(grid, med, color="k", lw=2.6,
                        label="median across trials")
                ax.legend(fontsize=8, loc="upper right")
            ax.axvline(args.warm_min, color="k", ls=":", lw=1)
            ax.axhline(0, color="k", lw=0.6)
            ax.axhspan(-BETWEEN_UNIT_SD, BETWEEN_UNIT_SD, color="grey",
                       alpha=0.18, zorder=0)
            ax.set_xlabel("minutes since capture start")
            ax.set_title(("back-to-back starts (board provably still on), "
                          f"n={n}") if want_warm else
                         f"all other starts, n={n}", fontsize=10)
            ax.set_xlim(0, args.plot_max_min)
        axes[0].set_ylabel("SFO - that trial's post-%g min median (rad/sc)"
                           % args.warm_min)
        fig.suptitle(f"Opening-minutes trajectory per (capture, unit), "
                     f"mode={mode}. Grey band = between-unit spread "
                     f"{BETWEEN_UNIT_SD:.5f} rad/sc", fontsize=11)
        fig.tight_layout()
        p = os.path.join(args.outdir, f"thermal_warmup_{mode}.png")
        fig.savefig(p, dpi=110)
        plt.close(fig)
        print(f"wrote {p}")

        # --- panel 2: opening slope vs later slopes, same captures
        fig, ax = plt.subplots(figsize=(7.5, 5))
        s0, sl = [], []
        for r in rows:
            if math.isnan(r["slope0"]) or math.isnan(r["slope_later_absmed"]):
                continue
            s0.append(abs(r["slope0"]))
            sl.append(r["slope_later_absmed"])
            ax.plot([0, 1], [abs(r["slope0"]), r["slope_later_absmed"]],
                    color=colour.get(r["mac"], "#777777"), alpha=0.55, lw=1)
        ax.plot([0, 1], [np.median(s0), np.median(sl)], color="k", lw=2.5,
                marker="o", label="median")
        ax.set_xticks([0, 1])
        ax.set_xticklabels([f"opening {args.warm_min:g} min",
                            f"later {args.warm_min:g}-min intervals\n"
                            "(same captures)"])
        ax.set_ylabel("|Theil-Sen slope| of SFO (rad/sc per min)")
        ax.set_yscale("log")
        ax.legend()
        ax.set_title(f"Is the opening interval special? mode={mode}",
                     fontsize=11)
        fig.tight_layout()
        p = os.path.join(args.outdir, f"thermal_slopes_{mode}.png")
        fig.savefig(p, dpi=110)
        plt.close(fig)
        print(f"wrote {p}")

    # --- panel 3: time of day
    fig, ax = plt.subplots(figsize=(8, 5))
    starts = {}
    for p in blob["paths"]:
        a, _ = file_first_last_us(p)
        if a is not None:
            starts[os.path.basename(p)] = a
    for mac in macs:
        h, v = [], []
        for sess, ser in obs_series(blob, mac, "raw").items():
            t = np.array([r[0] for r in ser]) / 60.0
            s = np.array([r[1] for r in ser])
            keep = t >= args.warm_min
            if keep.sum() < args.min_windows or sess not in starts:
                continue
            h.append(local_hour(starts[sess] + t[keep].mean() * 60e6))
            v.append(s[keep].mean())
        if h:
            ax.scatter(h, v, s=42, label=f"{mac}  (n={len(h)})",
                       color=colour.get(mac, "#777777"),
                       edgecolor="k", linewidth=0.5, zorder=3)
    ax.set_xlabel("local time of day (h)")
    ax.set_ylabel("mean SFO of the post-warm-up region (rad/sc), raw")
    ax.set_xlim(0, 24)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    ax.set_title("TEST 2: stable-region offset vs time of day.\n"
                 "No curve is fitted -- n is far too small for one.",
                 fontsize=10)
    fig.tight_layout()
    p = os.path.join(args.outdir, "thermal_timeofday.png")
    fig.savefig(p, dpi=110)
    plt.close(fig)
    print(f"wrote {p}")
    return 0


# ----------------------------------------------------------------- paired
#
# The mid-file-slice ablation ("replay the middle of a capture as if it
# were its own capture, so every piece of pipeline state gets a fresh
# cold start while the transmitter has been on for hours") needs no
# separate subcommand: slice the CSV, collect it under its own tag, and
# run `trajectory` against that tag. See docs/THERMAL_EVIDENCE.md 3.5.

def pair_sessions(sessions, prefix_a=None, prefix_b=None):
    """Group concurrent captures into (base, name_a, name_b, label_a, label_b).

    `pc/capture.py:102` names every capture `<collector>_<YYYYmmdd_HHMMSS>.csv`,
    so two receivers recording the same session differ only in the leading
    token. This groups on the timestamp part rather than on a fixed pair of
    prefixes.

    The original form of the caller hard-coded `desk_` and `node3_`
    (`docs/CODE_INVENTORY.md` 4.4, S11); no `node3_*` file has been written
    since 2026-07-13, so the 2026-08-21 `desk_`/`s3_` pair was invisible and
    `cmd_paired` printed a header and nothing else. Every `desk_`/`node3_`
    pair the old code found is still returned here, so this is additive.

    The two collectors are ordered by name, which keeps `desk` on the left of
    both `node3` and `s3` — the sign of every reported difference is
    therefore unchanged from the original. Pass `prefix_a`/`prefix_b` to fix
    the pair and its order explicitly.

    Returns (pairs, ambiguous) where `ambiguous` lists timestamps recorded by
    a number of collectors other than two; they are reported, not guessed at.
    """
    sessions = set(sessions)
    if prefix_a and prefix_b:
        la, lb = prefix_a.rstrip("_"), prefix_b.rstrip("_")
        a, b = la + "_", lb + "_"
        pairs = [(s[len(a):], s, b + s[len(a):], la, lb)
                 for s in sorted(sessions)
                 if s.startswith(a) and b + s[len(a):] in sessions]
        return pairs, []
    groups = defaultdict(dict)
    for s in sessions:
        pre, _, base = s.partition("_")
        if base:
            groups[base][pre] = s
    pairs, ambiguous = [], []
    for base in sorted(groups):
        pres = sorted(groups[base])
        if len(pres) != 2:
            ambiguous.append(f"{base}[{'|'.join(pres)}]")
            continue
        la, lb = pres
        pairs.append((base, groups[base][la], groups[base][lb], la, lb))
    return pairs, ambiguous


def cmd_paired(args):
    """Two receivers, one transmitter, the same minutes.

    Two captures sharing a timestamp — `desk_*` with `node3_*`, or `desk_*`
    with `s3_*` — are the same session recorded concurrently by
    two collectors. The transmitter's crystal is shared; the receivers'
    crystals are not, and every measured offset is (TX drift - RX drift).
    So for any wander at all -- warm-up or otherwise -- this splits the
    two candidate sides:

      trajectories agree across the two receivers -> the movement is on
        the transmitter's side, or common to both receivers
      trajectories disagree -> it is receiver-side, and no amount of
        thermal control at the beacon would remove it

    Reported as Pearson r on the binned trajectories plus a variance
    split: sd of the difference between the two receivers' traces against
    the sd of each trace. A shared TX signal makes the difference small
    relative to the traces.
    """
    blob = load(args.tag)
    macs = [m.strip().lower() for m in args.macs.split(",")]
    for mode in ("raw", "ref"):
        print(f"\n{'='*94}")
        print(f"PAIRED RECEIVERS -- same session, same transmitter, "
              f"mode={mode}")
        print(f"{'='*94}")
        print(f"{'session (both receivers)':<26}{'pair A/B':<15}"
              f"{'source':<11}{'bins':>6}"
              f"{'r':>8}{'sd A':>10}{'sd B':>10}{'sd diff':>10}"
              f"{'diff/mean sd':>14}")
        rs, fr, dmu = [], [], []
        reported_skip = False
        for mac in macs:
            ser = obs_series(blob, mac, mode)
            pairs, ambiguous = pair_sessions(set(ser), args.prefix_a,
                                             args.prefix_b)
            if ambiguous and not reported_skip:
                reported_skip = True
                print(f"  (not paired — timestamp recorded by other than two "
                      f"collectors: {', '.join(ambiguous)})")
            for b, name_a, name_b, la, lb in pairs:
                # stable-region mean per receiver, same session, same
                # transmitter: the cross-receiver disagreement floor
                sd_ = ser[name_a]
                sn_ = ser[name_b]
                td = np.array([r[0] for r in sd_]) / 60.0
                tn = np.array([r[0] for r in sn_]) / 60.0
                vd = np.array([r[1] for r in sd_])
                vn = np.array([r[1] for r in sn_])
                kd, kn = td >= args.warm_min, tn >= args.warm_min
                if kd.sum() >= args.min_windows and kn.sum() >= args.min_windows:
                    dmu.append(abs(vd[kd].mean() - vn[kn].mean()))
                cd, md, *_ = binned(ser[name_a], args.bin_s,
                                    args.min_per_bin)
                cn, mn, *_ = binned(ser[name_b], args.bin_s,
                                    args.min_per_bin)
                if len(cd) < args.min_bins or len(cn) < args.min_bins:
                    continue
                # align on the bin centres both receivers produced
                keyd = {round(c, 4): v for c, v in zip(cd, md)}
                keyn = {round(c, 4): v for c, v in zip(cn, mn)}
                common = sorted(set(keyd) & set(keyn))
                if len(common) < args.min_bins:
                    continue
                a = np.array([keyd[k] for k in common])
                c = np.array([keyn[k] for k in common])
                r = (float(np.corrcoef(a, c)[0, 1])
                     if a.std() > 0 and c.std() > 0 else float("nan"))
                sd_d = float((a - c).std(ddof=1))
                msd = (a.std(ddof=1) + c.std(ddof=1)) / 2
                rs.append(r)
                fr.append(sd_d / msd if msd else float("nan"))
                print(f"{b[:-4][:25]:<26}{(la + '/' + lb)[:14]:<15}"
                      f"{mac[-8:]:<11}{len(common):>6}"
                      f"{r:>+8.2f}{a.std(ddof=1):>10.5f}"
                      f"{c.std(ddof=1):>10.5f}{sd_d:>10.5f}"
                      f"{sd_d/msd if msd else float('nan'):>14.2f}")
        if rs:
            rs = np.array(rs)
            fr = np.array(fr)
            print(f"\n  {len(rs)} paired sessions.  Pearson r: median "
                  f"{np.median(rs):+.2f}, min {rs.min():+.2f}, "
                  f"max {rs.max():+.2f}")
            print(f"  sd(A - B) / mean sd of the two traces: median "
                  f"{np.median(fr):.2f}   (A/B named per row above)")
            print("  ~0 means the two receivers saw the same movement "
                  "(transmitter-side or common-mode);")
            print("  ~1.4 is what two independent traces of equal spread "
                  "would give.")
        if dmu:
            dmu = np.array(dmu)
            print(f"\n  |A - B| of the post-{args.warm_min:g} min "
                  f"mean SFO, same session and transmitter: n={len(dmu)}, "
                  f"median {np.median(dmu):.5f}, max {dmu.max():.5f} rad/sc")
            print(f"    = {np.median(dmu)/BETWEEN_UNIT_SD:.2f}x the "
                  f"between-unit spread ({BETWEEN_UNIT_SD:.5f}) and "
                  f"{np.median(dmu)/WITHIN_UNIT_SD:.2f}x the "
                  f"session-to-session wander ({WITHIN_UNIT_SD:.5f})")
            print("    Two collectors, one beacon, the same minutes. Any "
                  "part of this is receiver-side by construction.")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--macs", default=",".join(BEACONS))
        p.add_argument("--raw-dir", default="../data/raw")
        p.add_argument("--warm-min", type=float, default=10.0,
                       help="length of the opening interval under test, min")
        p.add_argument("--bin-s", type=float, default=30.0)
        p.add_argument("--min-per-bin", type=int, default=3)
        p.add_argument("--min-bins", type=int, default=20)
        p.add_argument("--min-span-min", type=float, default=30.0)
        p.add_argument("--min-windows", type=int, default=60)
        p.add_argument("--warm-max-min", type=float, default=5.0,
                       help="gap at or below which the previous capture "
                            "proves the board was still on")
        p.add_argument("--cold-min-min", type=float, default=2.0,
                       help="hours with no capture to call a start "
                            "'unobserved' (NOT 'cold' -- see cmd_sessions)")

    s = sub.add_parser("sessions")
    s.add_argument("--raw-dir", default="../data/raw")
    s.add_argument("--warm-max-min", type=float, default=5.0)
    s.add_argument("--cold-min-min", type=float, default=2.0)
    s.add_argument("--json")
    s.set_defaults(fn=cmd_sessions)

    t = sub.add_parser("trajectory")
    t.add_argument("--tag", required=True)
    common(t)
    t.add_argument("--json")
    t.set_defaults(fn=cmd_trajectory)

    w = sub.add_parser("wander")
    w.add_argument("--tag", required=True)
    w.add_argument("--macs", default=",".join(BEACONS))
    w.add_argument("--raw-dir", default="../data/raw")
    w.add_argument("--mode", choices=("ref", "raw", "both"), default="both")
    w.add_argument("--skip-list", default="5,10,15,20,30")
    w.add_argument("--min-windows", type=int, default=20)
    w.add_argument("--sessions", help="restrict to these session basenames")
    w.add_argument("--boot", type=int, default=2000)
    w.add_argument("--seed", type=int, default=0)
    w.set_defaults(fn=cmd_wander)

    d = sub.add_parser("tod")
    d.add_argument("--tag", required=True)
    d.add_argument("--macs", default=",".join(BEACONS))
    d.add_argument("--raw-dir", default="../data/raw")
    d.add_argument("--mode", choices=("ref", "raw", "both"), default="both")
    d.add_argument("--skip-min", type=float, default=15.0)
    d.add_argument("--min-windows", type=int, default=60)
    d.set_defaults(fn=cmd_tod)

    p = sub.add_parser("plots")
    p.add_argument("--tag", required=True)
    common(p)
    p.add_argument("--outdir", default="../docs/img")
    p.add_argument("--plot-max-min", type=float, default=60.0)
    p.set_defaults(fn=cmd_plots)

    pr = sub.add_parser("paired")
    pr.add_argument("--tag", required=True)
    common(pr)
    pr.add_argument("--prefix-a", help="collector prefix for the left-hand "
                    "receiver, e.g. 'desk'. Omit both to pair automatically "
                    "on the capture timestamp")
    pr.add_argument("--prefix-b", help="collector prefix for the right-hand "
                    "receiver, e.g. 's3' or 'node3'")
    pr.set_defaults(fn=cmd_paired)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
