#!/usr/bin/env python3
r"""Co-located receivers, 2026-08-23 overnight (the last V1 capture).

Both receivers were remounted onto the same wall on 2026-08-22 and are now
roughly 10 inches apart chip-to-chip. Every prior capture had them
separated. The load-bearing question this pass exists to answer:

    docs/SEPARATION_SCALING.md 0 and docs/REFERENCE_CHOICE.md 0 established
    an inversion -- the same-beacon receiver-to-receiver SFO difference
    exceeds every within-receiver beacon-to-beacon difference on the S3.
    That is why a fingerprint enrolled on one receiver does not transfer.
    If that receiver term is *geometric* (different path, different
    multipath) it should collapse when the two boards share a wall. If it
    is *silicon* (per-unit estimator/RF bias) it should not move.

This script measures that term in exactly the statistic those documents
used, plus the health/census figures needed to know whether the file can
carry the claim at all.

Read-only with respect to data/raw/: every input is opened "rb" and never
written. No serial port is opened. Nothing is staged or committed.

Design constraints this script obeys, and why
---------------------------------------------
* **Replay from the start of each file with a fresh estimator.**
  `FrameEstimator` owns a per-instance RNG (`pc/rff/dsp.py:118`) handed to
  `ransac_line` every frame (`:132`), which draws two `rng.integers(...,
  size=64)` per call (`:85-86`). The generator advances once per fitted
  frame, so a slope depends on how many frames preceded it in that stream.
  Windowed or filtered replays are not comparable to baseline
  (`docs/V2_SPEC.md` 5.5). The `part`/`merge` split below pickles the
  estimator state forward, so an N-part run is frame-for-frame what one
  uninterrupted pass would have produced; `merge` re-checks rather than
  asserting it.
* **Screen corrupt rows before any delta arithmetic.** A negative `dropped`
  delta is as likely to be a corrupt row as a u16 wrap; conflating them
  overstated the d0wd by 514x once (`docs/OVERNIGHT_2026-08-22.md` 4.2) and
  101x before that (`docs/DUAL_RX_2026-08-21.md` 2.1). Two independent
  routes are used, as that document requires: field plausibility on six
  columns, and a width-9 circular median filter on `dropped`.
* **`csi_data` is a quoted comma-separated list nested in the CSV.** Parsed
  with `csv.reader`, never a naive `line.split(",")`.
* `pc/rff/dsp.py` is used exactly as shipped and is not modified
  (`docs/V2_SPEC.md` 5.5). `pc/capture.py:compute_cfo`, `pc/phase_skew.py`
  and `pc/fingerprint.py` are not used -- `docs/CODE_INVENTORY.md` 4.2
  C1/C2/C3 establishes all three have the DC/guard-band index wrong.

Usage (from the repo root; state goes to $COLO_CACHE, default /tmp/colo)
------------------------------------------------------------------------
  D=data/raw/d0wd_20260823_014740.csv
  S=data/raw/s3_20260823_014740.csv
  python3 pc/exp_colocated_0823.py part $D --tag d0wd --part 0 --nparts 4
  ...                                                  --part 3 --nparts 4
  python3 pc/exp_colocated_0823.py merge --tag d0wd --nparts 4 \
      --expect-rows 3344351
  python3 pc/exp_colocated_0823.py report --tags d0wd,s3
"""
import argparse
import csv
import math
import os
import pickle
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rff.dsp import FrameEstimator, WindowAggregator   # noqa: E402
from occ import BEACON_MACS                            # noqa: E402

CACHE = os.environ.get("COLO_CACHE", "/tmp/colo")

# --- the project's yardsticks -------------------------------------------
# sd over the 3 units of their grand means (pc/exp_thermal_evidence.py:129,
# from docs/LOT_HYPOTHESIS.md 5). Every sigma in this pass is this one.
BETWEEN_UNIT_SD = 0.00237
WITHIN_UNIT_SD = 0.00570
# The documented clock-twin separation, the other standing yardstick.
TWIN_DSFO = 0.00080

# Shipped gates, pc/rff/dsp.py:164.
MIN_INLIER = 0.6
MAX_RESID = 0.8
# Primary metric window: docs/REFERENCE_CHOICE.md 1.3 -- the longest
# averaging that keeps all three beacons alive on BOTH receivers.
WIN_LONG = 16384
# Shipped configuration, reported alongside for its tighter CIs.
WIN_SHIP = 64

# Field-plausibility screen, docs/OVERNIGHT_2026-08-22.md 1.
CSI_LEN_OK = (128, 256, 384)      # 384 is accepted by pc/rff/protocol.py:31
NF_LO, NF_HI = -110, -70
RSSI_LO, RSSI_HI = -100, -10
# Width-9 circular median filter on `dropped`, docs/DUAL_RX_2026-08-21.md
# Appendix A.
MED_W = 9
MED_TOL = 100
U16 = 65536

BIN_S = 60.0        # rate / RSSI time-series bin
BLOCK_S = 300.0     # the 300 s blocks docs/DISPLAY_LIVE_0822.md 5.1 uses
BEACON_MIN_FPS = 10.0   # firmware BEACON_MIN_FPS_X10 = 100, main.c:150


# ----------------------------------------------------------------- state

def _zero_bin():
    """Module-level so State pickles (a lambda would not)."""
    return [0, 0.0]


class MacStat:
    """Per-source accumulators. `raw_n` counts every row bearing this MAC;
    everything else is over rows that survive both corrupt-row screens."""

    __slots__ = ("raw_n", "n", "rssi_sum", "rssi_sq", "rssi_min", "rssi_max",
                 "t_first", "t_last", "len_hist", "nf_hist", "chan_hist",
                 "est", "agg_ship", "agg_long", "win_ship", "win_long",
                 "n_fit", "n_nofit", "n_gate_rej", "n_inl90", "max_resid",
                 "bins", "blocks", "raw_bins")

    def __init__(self):
        self.raw_n = 0
        self.n = 0
        self.rssi_sum = 0.0
        self.rssi_sq = 0.0
        self.rssi_min = None
        self.rssi_max = None
        self.t_first = None
        self.t_last = None
        self.len_hist = defaultdict(int)
        self.nf_hist = defaultdict(int)
        self.chan_hist = defaultdict(int)
        self.est = None
        self.agg_ship = None
        self.agg_long = None
        self.win_ship = []          # (ts_us, sfo, cfo, rssi, quality)
        self.win_long = []
        self.n_fit = 0
        self.n_nofit = 0
        self.n_gate_rej = 0
        self.n_inl90 = 0
        self.max_resid = 0.0
        self.bins = defaultdict(int)               # 60 s bin -> frames
        self.blocks = defaultdict(int)             # 300 s block -> frames
        self.raw_bins = defaultdict(_zero_bin)      # bin -> [n, rssi_sum]


class State:
    def __init__(self, tag, path):
        self.tag = tag
        self.path = path
        self.byte_pos = 0
        self.rows = 0                 # data rows consumed
        self.bad_parse = 0            # wrong field count / unparseable
        self.macs = defaultdict(MacStat)
        self.t0_us = None             # first decodable pc_time_us
        self.t_last_us = None
        self.node_hist = defaultdict(int)
        self.chan_hist = defaultdict(int)
        self.env_hist = defaultdict(int)
        self.nf_hist = defaultdict(int)
        self.node_mode = None
        self.chan_mode = None
        # corrupt-row screening. `pend` holds rows in file order; the first
        # `n_hist` of them have already been emitted and are retained only
        # as look-behind context for the width-9 filter.
        self.pend = []
        self.n_hist = 0
        self.n_field_bad = 0
        self.n_med_bad = 0
        self.n_both = 0
        self.n_corrupt = 0
        self.corrupt_macs = defaultdict(int)
        self.corrupt_examples = []
        # drop accounting over CLEAN rows only
        self.d_first = None
        self.d_prev = None
        self.d_total = 0
        self.d_wraps = 0
        self.d_neg = 0
        self.d_last = None
        self.drops_per_s = defaultdict(int)
        # the same accounting with NO screen, to size the error the screen
        # prevents (docs/OVERNIGHT_2026-08-22.md 4.2)
        self.u_prev = None
        self.u_total = 0
        self.u_neg = 0
        self.u_first = None
        self.u_last = None
        # frames delivered per 60 s bin, all clean rows
        self.bins = defaultdict(int)
        self.seam_checks = []


def spath(tag, part=None):
    if part is None:
        return os.path.join(CACHE, f"{tag}_state.pkl")
    return os.path.join(CACHE, f"{tag}_part{part}.pkl")


# ------------------------------------------------------------ line input

class Lines:
    """Byte-exact line source. Yields decoded lines and tracks the absolute
    byte offset AFTER the last line handed out, so a part can record where
    the next part must resume. Opened "rb": the file is never written."""

    def __init__(self, path, start):
        self.f = open(path, "rb")
        self.f.seek(start)
        self.pos = start

    def __iter__(self):
        for raw in self.f:
            self.pos += len(raw)
            yield raw.decode("utf-8", "replace")

    def close(self):
        self.f.close()


# ------------------------------------------------------- corrupt screens

def field_ok(node, env, chan, ln, nf, rssi, node_mode, chan_mode):
    return (node == node_mode and env == 0 and chan == chan_mode
            and ln in CSI_LEN_OK and NF_LO <= nf <= NF_HI
            and RSSI_LO <= rssi <= RSSI_HI)


def circ(a, b):
    """Signed circular difference a-b on a u16 counter."""
    return ((a - b + 32768) % U16) - 32768


def med_flag(vals, ci):
    """Width-9 median filter, compared circularly mod 65536. `ci` is the
    index of the centre row inside `vals`."""
    c = vals[ci]
    offs = sorted(circ(v, c) for v in vals)
    m = offs[len(offs) // 2]
    return abs(m) > MED_TOL


# ------------------------------------------------------------- the parts

def run_part(args):
    os.makedirs(CACHE, exist_ok=True)
    csv.field_size_limit(10 ** 7)

    if args.part == 0:
        st = State(args.tag, args.path)
        # prescan for the screen's mode, docs/REFERENCE_CHOICE.md 1.2: the
        # mode is taken from the first 20,000 rows and re-checked against
        # the whole-file histogram at merge.
        nh, ch = defaultdict(int), defaultdict(int)
        L = Lines(args.path, 0)
        it = iter(L)
        next(it)                       # header
        for i, line in enumerate(it):
            if i >= 20000:
                break
            row = next(csv.reader([line]), None)
            if row is None or len(row) != 13:
                continue
            try:
                nh[int(row[10])] += 1
                ch[int(row[6])] += 1
            except ValueError:
                continue
        L.close()
        st.node_mode = max(nh.items(), key=lambda kv: kv[1])[0]
        st.chan_mode = max(ch.items(), key=lambda kv: kv[1])[0]
        # rewind and start for real, past the header
        L = Lines(args.path, 0)
        it = iter(L)
        header = next(csv.reader([next(it)]))
        assert header[:13] == ["pc_time_us", "label", "seq", "mac", "rssi",
                               "noise_floor", "channel", "esp_timestamp_us",
                               "len", "csi_data", "node_id", "env_id",
                               "dropped"], header
        st.byte_pos = L.pos
        L.close()
    else:
        with open(spath(args.tag, args.part - 1), "rb") as f:
            st = pickle.load(f)
        st.seam_checks.append((args.part, st.rows, st.byte_pos,
                               st.t_last_us))

    total_rows = args.total_rows
    per = math.ceil(total_rows / args.nparts)
    stop_at = min(total_rows, per * (args.part + 1))

    L = Lines(args.path, st.byte_pos)
    r = csv.reader(iter(L))
    t0 = time.time()
    processed = 0
    hit_limit = False

    for row in r:
        st.rows += 1
        processed += 1
        if len(row) != 13:
            st.bad_parse += 1
            _flush(st, force=False)
            if st.rows >= stop_at:
                hit_limit = True
                break
            continue
        try:
            pc_us = int(row[0])
            mac = row[3].lower()
            rssi = int(row[4])
            nf = int(row[5])
            chan = int(row[6])
            esp_us = int(row[7])
            ln = int(row[8])
            node = int(row[10])
            env = int(row[11])
            drop = int(row[12])
        except ValueError:
            st.bad_parse += 1
            _flush(st, force=False)
            if st.rows >= stop_at:
                hit_limit = True
                break
            continue

        st.node_hist[node] += 1
        st.chan_hist[chan] += 1
        st.env_hist[env] += 1
        st.nf_hist[nf] += 1
        if st.t0_us is None:
            st.t0_us = pc_us
        st.t_last_us = pc_us

        # unscreened drop accumulation, for the size-of-error figure only
        if st.u_prev is None:
            st.u_first = drop
        else:
            d = drop - st.u_prev
            if d < 0:
                st.u_neg += 1
                d += U16
            st.u_total += d
        st.u_prev = drop
        st.u_last = drop

        fbad = not field_ok(node, env, chan, ln, nf, rssi,
                            st.node_mode, st.chan_mode)
        st.macs[mac].raw_n += 1
        st.pend.append((st.rows, pc_us, mac, rssi, nf, chan, esp_us, ln,
                        node, env, drop, row[9], fbad))
        _flush(st, force=False)

        if st.rows >= stop_at:
            hit_limit = True
            break

    # The file ends here if we ran out of rows rather than hitting the
    # part boundary, or if this part's boundary IS the end of the file.
    at_eof = (not hit_limit) or st.rows >= total_rows
    if at_eof:
        _flush(st, force=True)
    L.close()

    st.byte_pos = L.pos
    with open(spath(args.tag, args.part), "wb") as f:
        pickle.dump(st, f, protocol=4)
    print(f"[{args.tag} part {args.part}/{args.nparts}] rows={st.rows:,} "
          f"(+{processed:,}) byte_pos={st.byte_pos:,} "
          f"corrupt={st.n_corrupt} in {time.time()-t0:.1f}s", file=sys.stderr)


def _flush(st, force):
    """Emit rows in strict file order, each judged by the width-9 filter
    once its 4 look-ahead rows have arrived. `force` drains the tail at
    EOF, where the last rows have fewer than 4 followers -- those are
    judged on the shorter window they have, which is all a filter can do at
    a boundary. Emission order is the file's order, always."""
    half = MED_W // 2
    while st.n_hist < len(st.pend):
        ci = st.n_hist
        ahead = len(st.pend) - 1 - ci
        if not force and ahead < half:
            return
        lo = max(0, ci - half)
        hi = min(len(st.pend), ci + half + 1)
        vals = [st.pend[k][10] for k in range(lo, hi)]
        mbad = med_flag(vals, ci - lo) if len(vals) >= 3 else False
        _emit(st, st.pend[ci], mbad)
        st.n_hist += 1
        while st.n_hist > half:
            del st.pend[0]
            st.n_hist -= 1


def _emit(st, rec, mbad):
    (ridx, pc_us, mac, rssi, nf, chan, esp_us, ln, node, env, drop, csi_s,
     fbad) = rec

    if fbad:
        st.n_field_bad += 1
    if mbad:
        st.n_med_bad += 1
    if fbad and mbad:
        st.n_both += 1
    if fbad or mbad:
        st.n_corrupt += 1
        st.corrupt_macs[mac] += 1
        if len(st.corrupt_examples) < 12:
            st.corrupt_examples.append(
                (ridx, mac, rssi, nf, chan, ln, node, env, drop,
                 "field" if fbad else "", "median" if mbad else ""))
        return

    # ---- from here on the row is clean ----
    t = (pc_us - st.t0_us) * 1e-6
    b = int(t // BIN_S)
    blk = int(t // BLOCK_S)
    st.bins[b] += 1

    if st.d_prev is None:
        st.d_first = drop
    else:
        d = drop - st.d_prev
        if d < 0:
            st.d_neg += 1
            st.d_wraps += 1
            d += U16
        st.d_total += d
        if d:
            st.drops_per_s[int(t)] += d
    st.d_prev = drop
    st.d_last = drop

    m = st.macs[mac]
    m.n += 1
    m.rssi_sum += rssi
    m.rssi_sq += rssi * rssi
    m.rssi_min = rssi if m.rssi_min is None else min(m.rssi_min, rssi)
    m.rssi_max = rssi if m.rssi_max is None else max(m.rssi_max, rssi)
    if m.t_first is None:
        m.t_first = pc_us
    m.t_last = pc_us
    m.len_hist[ln] += 1
    m.nf_hist[nf] += 1
    m.chan_hist[chan] += 1
    m.bins[b] += 1
    m.blocks[blk] += 1
    rb = m.raw_bins[b]
    rb[0] += 1
    rb[1] += rssi

    # ---- phase domain, shipped dsp.py, one fresh estimator per stream ----
    if m.est is None:
        m.est = FrameEstimator()
        m.agg_ship = WindowAggregator(window=WIN_SHIP,
                                      min_inlier_ratio=MIN_INLIER,
                                      max_resid=MAX_RESID)
        m.agg_long = WindowAggregator(window=WIN_LONG,
                                      min_inlier_ratio=MIN_INLIER,
                                      max_resid=MAX_RESID)
    try:
        vals = [int(x) for x in csi_s.split(",")] if csi_s else []
    except ValueError:
        vals = []
    est = m.est.feed(vals, esp_us)
    if est is None:
        m.n_nofit += 1
        return
    m.n_fit += 1
    if est["resid_std"] > m.max_resid:
        m.max_resid = est["resid_std"]
    if est["inlier_ratio"] >= 0.90:
        m.n_inl90 += 1
    if est["inlier_ratio"] < MIN_INLIER or est["resid_std"] > MAX_RESID:
        m.n_gate_rej += 1
    for agg, out in ((m.agg_ship, m.win_ship), (m.agg_long, m.win_long)):
        w = agg.feed(est, esp_us, rssi)
        if w is not None:
            out.append((w["ts_us"], w["sfo"], w["cfo"], w["rssi"],
                        w["quality"]))


# ------------------------------------------------------------------ merge

def run_merge(args):
    with open(spath(args.tag, args.nparts - 1), "rb") as f:
        st = pickle.load(f)
    ok_rows = (st.rows == args.expect_rows)
    seam_ok = all(a[3] is not None for a in st.seam_checks)
    print(f"[{args.tag} merge] rows={st.rows:,} expect={args.expect_rows:,} "
          f"{'MATCH' if ok_rows else 'MISMATCH'}; "
          f"{len(st.seam_checks)} seam(s), pc_time_us monotone at each: "
          f"{seam_ok}", file=sys.stderr)
    node_mode_full = max(st.node_hist.items(), key=lambda kv: kv[1])[0]
    chan_mode_full = max(st.chan_hist.items(), key=lambda kv: kv[1])[0]
    print(f"[{args.tag} merge] screen mode node={st.node_mode} "
          f"chan={st.chan_mode}; whole-file mode node={node_mode_full} "
          f"chan={chan_mode_full}; "
          f"{'AGREE' if (node_mode_full, chan_mode_full) == (st.node_mode, st.chan_mode) else 'DISAGREE'}",
          file=sys.stderr)
    st.pend = []
    with open(spath(args.tag), "wb") as f:
        pickle.dump(st, f, protocol=4)


# ----------------------------------------------------------------- report

def med(a):
    return float(np.median(a)) if len(a) else float("nan")


def boot_ci(a, n=2000, seed=12345):
    """Percentile bootstrap 95 % CI of the median."""
    a = np.asarray(a, dtype=float)
    if a.size < 3:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, a.size, size=(n, a.size))
    ms = np.median(a[idx], axis=1)
    return (float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5)))


def diff_ci(a, b, n=2000, seed=999):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    if a.size < 3 or b.size < 3:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, a.size, size=(n, a.size))
    ib = rng.integers(0, b.size, size=(n, b.size))
    d = np.median(a[ia], axis=1) - np.median(b[ib], axis=1)
    return (float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5)))


def sig(x):
    return x / BETWEEN_UNIT_SD


def hl(t):
    print("\n" + t)
    print("-" * len(t))


def run_report(args):
    tags = args.tags.split(",")
    S = {}
    for t in tags:
        with open(spath(t), "rb") as f:
            S[t] = pickle.load(f)

    inv = {v: k for k, v in BEACON_MACS.items()}
    bn = ["B1", "B2", "B3"]

    hl("0. SPAN AND INTEGRITY")
    for t in tags:
        st = S[t]
        span = (st.t_last_us - st.t0_us) * 1e-6
        print(f"{t}: file={st.path}")
        print(f"  data rows                    {st.rows:,}")
        print(f"  rows with != 13 fields or unparseable ints   {st.bad_parse}")
        print(f"  node_id hist                 {dict(st.node_hist)}")
        print(f"  channel hist                 {dict(st.chan_hist)}")
        print(f"  env_id hist                  {dict(st.env_hist)}")
        print(f"  noise_floor hist             {dict(sorted(st.nf_hist.items()))}")
        print(f"  first pc_time_us             {st.t0_us}")
        print(f"  last  pc_time_us             {st.t_last_us}")
        print(f"  span                         {span:,.3f} s "
              f"= {span/3600:.4f} h")
        print(f"  delivered fps over span      "
              f"{(st.rows - st.n_corrupt)/span:,.3f}")

    hl("1. CORRUPT ROWS (two independent screens)")
    print(f"{'node':<6} {'rows':>12} {'field':>8} {'median':>8} {'both':>8} "
          f"{'corrupt':>9} {'ppm':>8}")
    for t in tags:
        st = S[t]
        print(f"{t:<6} {st.rows:>12,} {st.n_field_bad:>8,} "
              f"{st.n_med_bad:>8,} {st.n_both:>8,} {st.n_corrupt:>9,} "
              f"{1e6*st.n_corrupt/st.rows:>8.2f}")
    for t in tags:
        st = S[t]
        if st.corrupt_examples:
            print(f"\n  {t} first corrupt rows "
                  f"(row, mac, rssi, nf, ch, len, node, env, dropped, "
                  f"caught-by):")
            for e in st.corrupt_examples:
                print("   ", e)
        only_med = st.n_med_bad - st.n_both
        only_fld = st.n_field_bad - st.n_both
        print(f"  {t}: caught by median filter only {only_med}, "
              f"by field screen only {only_fld}")

    hl("2. DROPS (screened, wrap-safe) vs the unscreened error")
    print(f"{'node':<6} {'clean drops':>13} {'wraps':>7} {'first':>8} "
          f"{'last':>8} {'endpoint xcheck':>17} {'loss %':>9}")
    for t in tags:
        st = S[t]
        deliv = st.rows - st.n_corrupt
        xc = (st.d_last - st.d_first + U16 * st.d_wraps
              if st.d_first is not None else 0)
        loss = 100.0 * st.d_total / (deliv + st.d_total) if deliv else 0.0
        print(f"{t:<6} {st.d_total:>13,} {st.d_wraps:>7} {st.d_first:>8} "
              f"{st.d_last:>8} {xc:>17,} {loss:>9.4f}")
    print()
    print(f"{'node':<6} {'UNSCREENED total':>18} {'neg deltas':>11} "
          f"{'overstatement':>14} {'shipped 1-wrap est':>19}")
    for t in tags:
        st = S[t]
        over = (st.u_total / st.d_total) if st.d_total else float("inf")
        ship = st.u_last - st.u_first
        print(f"{t:<6} {st.u_total:>18,} {st.u_neg:>11,} "
              f"{over:>13.1f}x {ship:>19,}")
    print("\n  drops/s burstiness over clean rows:")
    for t in tags:
        st = S[t]
        span = int((st.t_last_us - st.t0_us) * 1e-6) + 1
        v = np.zeros(span, dtype=np.int64)
        for k, n in st.drops_per_s.items():
            if 0 <= k < span:
                v[k] += n
        print(f"    {t}: seconds={span:,} median={np.median(v):.0f} "
              f"mean={v.mean():.3f} p90={np.percentile(v,90):.0f} "
              f"p99={np.percentile(v,99):.0f} max={v.max()} "
              f"zero-drop s={int((v==0).sum()):,} "
              f"({100.0*(v==0).sum()/span:.1f} %)")

    hl("3. MAC CENSUS -- unscreened vs screened, and the reconciliation")
    for t in tags:
        st = S[t]
        raw_all = [m for m, s in st.macs.items() if s.raw_n > 0]
        raw20 = [m for m, s in st.macs.items() if s.raw_n >= args.min_frames]
        cl_all = [m for m, s in st.macs.items() if s.n > 0]
        cl20 = [m for m, s in st.macs.items() if s.n >= args.min_frames]
        only_corrupt = [m for m, s in st.macs.items()
                        if s.raw_n > 0 and s.n == 0]
        print(f"\n{t}:")
        print(f"  distinct MACs, every row, no floor        {len(raw_all)}")
        print(f"  distinct MACs, every row, >= {args.min_frames} frames   "
              f"{len(raw20)}")
        print(f"  distinct MACs, clean rows, no floor       {len(cl_all)}")
        print(f"  distinct MACs, clean rows, >= {args.min_frames} frames  "
              f"{len(cl20)}   <-- REAL POPULATION")
        print(f"  MACs seen ONLY on corrupt rows            "
              f"{len(only_corrupt)}")
        print(f"  corrupt rows on this node                 {st.n_corrupt}")
        print(f"  corrupt rows bearing a MAC seen only on corrupt rows  "
              f"{sum(st.macs[m].raw_n for m in only_corrupt)}")
        print(f"  corrupt rows bearing an otherwise-real MAC            "
              f"{st.n_corrupt - sum(st.macs[m].raw_n for m in only_corrupt)}")
        print(f"\n  {'mac':<18} {'clean':>10} {'raw':>10} {'corrupt':>8} "
              f"{'kind':<9} {'rssi mean':>10} {'fps':>9} role")
        span = (st.t_last_us - st.t0_us) * 1e-6
        for m in sorted(cl20, key=lambda x: -st.macs[x].n):
            s = st.macs[m]
            try:
                la = bool(int(m.split(":")[0], 16) & 0x02)
            except (ValueError, IndexError):
                la = None
            kind = ("beacon" if m in BEACON_MACS
                    else ("private" if la else "real-OUI"))
            print(f"  {m:<18} {s.n:>10,} {s.raw_n:>10,} "
                  f"{st.corrupt_macs.get(m,0):>8,} {kind:<9} "
                  f"{s.rssi_sum/s.n:>10.2f} {s.n/span:>9.4f} "
                  f"{BEACON_MACS.get(m,'')}")

    hl("4. PER-BEACON RATE AND RSSI")
    print(f"{'node':<6} {'b':<3} {'frames':>12} {'fps':>9} {'rssi mean':>10} "
          f"{'sd':>6} {'min':>5} {'max':>5} {'floor':>8}")
    for t in tags:
        st = S[t]
        span = (st.t_last_us - st.t0_us) * 1e-6
        for b in bn:
            m = inv[b]
            s = st.macs.get(m)
            if s is None or s.n == 0:
                print(f"{t:<6} {b:<3} {'0':>12}")
                continue
            mu = s.rssi_sum / s.n
            sd = math.sqrt(max(0.0, s.rssi_sq / s.n - mu * mu))
            fps = s.n / span
            print(f"{t:<6} {b:<3} {s.n:>12,} {fps:>9.3f} {mu:>10.2f} "
                  f"{sd:>6.2f} {s.rssi_min:>5} {s.rssi_max:>5} "
                  f"{'UNDER' if fps < BEACON_MIN_FPS else 'ok':>8}")
    print(f"\n  per-{int(BLOCK_S)} s block delivered fps, per beacon "
          f"(floor {BEACON_MIN_FPS}):")
    for t in tags:
        st = S[t]
        span = (st.t_last_us - st.t0_us) * 1e-6
        # A trailing partial block would read as a rate collapse that is
        # only a truncated denominator; count whole blocks only.
        nb_full = int(span // BLOCK_S)
        for b in bn:
            s = st.macs.get(inv[b])
            if s is None or not s.blocks or nb_full < 1:
                continue
            nb = nb_full
            v = [s.blocks.get(k, 0) / BLOCK_S for k in range(nb)]
            under = sum(1 for x in v if x < BEACON_MIN_FPS)
            print(f"    {t}/{b}: {nb} whole blocks, under floor in {under} "
                  f"({100.0*under/nb:.1f} %), "
                  f"min={min(v):.2f} max={max(v):.2f} "
                  f"first6={[round(x,2) for x in v[:6]]} "
                  f"last3={[round(x,2) for x in v[-3:]]}")

    hl("5. PHASE-DOMAIN HEALTH (shipped gates, dsp.py:164)")
    print(f"{'node':<6} {'b':<3} {'frames':>12} {'fitted':>12} "
          f"{'nofit %':>8} {'gate rej %':>11} {'inl>=.90 %':>11} "
          f"{'max resid':>10}")
    for t in tags:
        st = S[t]
        for b in bn:
            s = st.macs.get(inv[b])
            if s is None or s.n == 0:
                continue
            tot = s.n_fit + s.n_nofit
            print(f"{t:<6} {b:<3} {s.n:>12,} {s.n_fit:>12,} "
                  f"{100.0*s.n_nofit/max(1,tot):>8.3f} "
                  f"{100.0*s.n_gate_rej/max(1,s.n_fit):>11.3f} "
                  f"{100.0*s.n_inl90/max(1,s.n_fit):>11.3f} "
                  f"{s.max_resid:>10.4f}")

    for wname, attr in (("SHIPPED window=64", "win_ship"),
                        (f"PRIMARY window={WIN_LONG}", "win_long")):
        hl(f"6. SFO MEDIANS -- {wname}")
        print(f"{'node':<6} {'b':<3} {'windows':>9} {'median SFO':>12} "
              f"{'95 % CI':>26} {'IQR of windows':>15}")
        for t in tags:
            st = S[t]
            for b in bn:
                s = st.macs.get(inv[b])
                if s is None:
                    continue
                w = [x[1] for x in getattr(s, attr)]
                if not w:
                    print(f"{t:<6} {b:<3} {0:>9}")
                    continue
                lo, hi = boot_ci(w)
                iqr = float(np.subtract(*np.percentile(w, [75, 25])))
                ci = f"[{lo:+.5f}, {hi:+.5f}]"
                print(f"{t:<6} {b:<3} {len(w):>9,} {med(w):>+12.5f} "
                      f"{ci:>26} {iqr:>15.5f}")

        hl(f"7. THE INTER-RECEIVER TERM -- {wname}")
        print("d0wd-minus-s3 same-beacon SFO difference, no reference "
              "correction")
        print(f"{'b':<3} {'d0wd':>11} {'s3':>11} {'diff':>11} "
              f"{'x SD':>8} {'95 % CI of diff':>28}")
        rec = {}
        for b in bn:
            a = [x[1] for x in getattr(S[tags[0]].macs[inv[b]], attr)] \
                if inv[b] in S[tags[0]].macs else []
            c = [x[1] for x in getattr(S[tags[1]].macs[inv[b]], attr)] \
                if inv[b] in S[tags[1]].macs else []
            if not a or not c:
                print(f"{b:<3} (missing)")
                continue
            d = med(a) - med(c)
            rec[b] = abs(d)
            lo, hi = diff_ci(a, c)
            print(f"{b:<3} {med(a):>+11.5f} {med(c):>+11.5f} {d:>+11.5f} "
                  f"{sig(abs(d)):>8.2f} [{lo:>+.5f}, {hi:>+.5f}]")
        print("\nwithin-receiver beacon-to-beacon differences "
              "(the DEVICE term)")
        dev = {}
        for t in tags:
            st = S[t]
            for i in range(3):
                for j in range(i + 1, 3):
                    si = st.macs.get(inv[bn[i]])
                    sj = st.macs.get(inv[bn[j]])
                    if si is None or sj is None:
                        continue
                    a = [x[1] for x in getattr(si, attr)]
                    c = [x[1] for x in getattr(sj, attr)]
                    if not a or not c:
                        continue
                    d = med(a) - med(c)
                    dev[(t, bn[i], bn[j])] = abs(d)
                    lo, hi = diff_ci(a, c)
                    print(f"  {t:<6} {bn[i]}-{bn[j]}  {d:>+11.5f}  "
                          f"{sig(abs(d)):>6.2f} x SD   "
                          f"[{lo:>+.5f}, {hi:>+.5f}]")
        if rec and dev:
            s3dev = {k: v for k, v in dev.items() if k[0] == tags[1]}
            print(f"\n  smallest receiver term  {min(rec.values()):.5f} "
                  f"({min(rec, key=rec.get)})  = {sig(min(rec.values())):.2f} x SD")
            if s3dev:
                lg = max(s3dev.values())
                lk = max(s3dev, key=s3dev.get)
                print(f"  largest S3 device term  {lg:.5f} "
                      f"({lk[1]}-{lk[2]})  = {sig(lg):.2f} x SD")
                print(f"  RATIO receiver/device   "
                      f"{min(rec.values())/lg:.3f}   "
                      f"(> 1 means the inversion survives)")
            print(f"  receiver terms as x TWIN_DSFO ({TWIN_DSFO}): "
                  + ", ".join(f"{b}={rec[b]/TWIN_DSFO:.1f}" for b in rec))

    hl("8. S3 RSSI TIME SERIES -- step-change search (antenna)")
    st = S[tags[1]] if len(tags) > 1 else S[tags[0]]
    for t in tags:
        st = S[t]
        print(f"\n{t}:")
        for b in bn:
            s = st.macs.get(inv[b])
            if s is None or not s.raw_bins:
                continue
            nb = max(s.raw_bins) + 1
            mu = np.full(nb, np.nan)
            cnt = np.zeros(nb)
            for k, (n, ssum) in s.raw_bins.items():
                if 0 <= k < nb and n > 0:
                    mu[k] = ssum / n
                    cnt[k] = n
            good = ~np.isnan(mu)
            g = np.where(good)[0]
            if g.size < 20:
                continue
            v = mu[g]
            # largest split-point difference of means, with a 10-bin margin
            best = (0.0, -1)
            for k in range(10, g.size - 10):
                d = abs(v[k:].mean() - v[:k].mean())
                if d > best[0]:
                    best = (d, k)
            # largest single-bin jump
            jd = np.abs(np.diff(v))
            ji = int(np.argmax(jd))
            print(f"  {b}: bins={g.size} mean={v.mean():+.2f} "
                  f"sd={v.std():.2f} first10={v[:10].mean():+.2f} "
                  f"last10={v[-10:].mean():+.2f} "
                  f"range={v.min():+.1f}..{v.max():+.1f}")
            print(f"     best split at bin {g[best[1]]} "
                  f"(t={g[best[1]]*BIN_S/3600:.3f} h): "
                  f"|Δmean| = {best[0]:.3f} dB")
            print(f"     largest 1-bin jump at bin {g[ji]} "
                  f"(t={g[ji]*BIN_S/3600:.3f} h): "
                  f"{jd[ji]:.3f} dB  ({v[ji]:+.2f} -> {v[ji+1]:+.2f})")
        # per-node delivered-rate series, for a coincident step
        nb = max(st.bins) + 1
        v = np.array([st.bins.get(k, 0) / BIN_S for k in range(nb)])
        v = v[:-1] if nb > 1 else v          # last bin is partial
        print(f"  delivered fps by {int(BIN_S)} s bin: mean={v.mean():.2f} "
              f"min={v.min():.2f}@{int(np.argmin(v))} "
              f"max={v.max():.2f}@{int(np.argmax(v))} sd={v.std():.2f}")

    hl("9. YARDSTICKS")
    print(f"  BETWEEN_UNIT_SD = {BETWEEN_UNIT_SD}  "
          f"(pc/exp_thermal_evidence.py:129)")
    print(f"  WITHIN_UNIT_SD  = {WITHIN_UNIT_SD}")
    print(f"  twin ΔSFO       = {TWIN_DSFO}  (docs/LOT_HYPOTHESIS.md)")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("part")
    p.add_argument("path")
    p.add_argument("--tag", required=True)
    p.add_argument("--part", type=int, required=True)
    p.add_argument("--nparts", type=int, required=True)
    p.add_argument("--total-rows", type=int, required=True)
    p.set_defaults(fn=run_part)

    p = sub.add_parser("merge")
    p.add_argument("--tag", required=True)
    p.add_argument("--nparts", type=int, required=True)
    p.add_argument("--expect-rows", type=int, required=True)
    p.set_defaults(fn=run_merge)

    p = sub.add_parser("report")
    p.add_argument("--tags", required=True)
    p.add_argument("--min-frames", type=int, default=20)
    p.set_defaults(fn=run_report)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
