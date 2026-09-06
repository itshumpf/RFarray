#!/usr/bin/env python3
r"""Pre-registered test: why does the inter-receiver SFO disagreement vary?

Implements docs/RECEIVER_TERM_PREREG.md exactly. That document was written
and frozen BEFORE this script produced a number; the hypotheses, predicted
signs, statistics, confound control, decision rules and detection floors are
all fixed there and this script only evaluates them.

The question (docs/RECEIVER_TERM_PREREG.md 1): for a source heard by both
receivers, the two disagree about that source's SFO, and across three known
beacons that disagreement varies 23x (docs/COLOCATED_0823.md 5.1). Why?

  H1 estimator noise      -> Delta correlates NEGATIVELY with RSSI
  H2 relative baseline    -> Delta correlates POSITIVELY with RSSI
  H3 fixed rx-pair offset -> Delta_signed roughly constant across sources

n is every source heard by BOTH receivers with >= 20 admissible frames on
each -- beacons on equal footing with ambient devices, because the receivers
are the instrument and the transmitters are sources (prereg 1.1).

Also run, equal billing (prereg 8): are the clean-but-sparse d0wd addresses
passers-by? Per-source normalised sample range against its exact Beta(k-1,2)
uniform-arrival null. pc/mac_census.py counts frames only and never looks at
arrival time.

Read-only with respect to data/raw/: every input is opened "rb" and never
written. No serial port is opened. Nothing is staged or committed.

Design constraints obeyed, and why
----------------------------------
* Replay from the start of each file with a fresh estimator, one per
  (node, source-MAC). FrameEstimator owns a per-instance RNG
  (pc/rff/dsp.py:118) handed to ransac_line every frame (:132), which draws
  two rng.integers(..., size=64) per call (:85-86); the generator advances
  once per fitted frame, so a slope depends on how many frames preceded it
  in that stream (docs/V2_SPEC.md 5.5). The part/merge split pickles
  estimator state forward, so an N-part run is frame-for-frame what one
  uninterrupted pass would produce; merge re-checks rather than asserting.
* Screen corrupt rows with BOTH routes before any delta arithmetic. The
  d0wd fabricates MACs from corrupt rows -- 126 of its 166 addresses were
  corruption -- and three corrupt rows are invisible to the field screen and
  need the width-9 median filter (docs/COLOCATED_0823.md 2, 3.3).
* csi_data is a quoted comma-separated list nested in the CSV. Parsed with
  csv.reader, never a naive line.split(",").
* pc/rff/dsp.py is used exactly as shipped and is NOT modified
  (docs/V2_SPEC.md 5.5). pc/capture.py:compute_cfo, pc/phase_skew.py and
  pc/fingerprint.py are NOT used -- docs/CODE_INVENTORY.md 4.2 C1/C2/C3
  establishes all three have the DC/guard-band index wrong.
* No scipy. The repo does not depend on it (CLAUDE.md); the Student-t
  quantile needed for the detection floor is computed here from a
  continued-fraction incomplete beta.

Usage (from the repo root; state goes to $RXTERM_CACHE, default /tmp/rxterm)
----------------------------------------------------------------------------
  D=data/raw/d0wd_20260823_014740.csv
  S=data/raw/s3_20260823_014740.csv
  for p in 0 1 2 3 4; do
    python3 pc/exp_receiver_term_prereg.py part $D --tag d0wd \
        --part $p --nparts 5 --total-rows 3344351
    python3 pc/exp_receiver_term_prereg.py part $S --tag s3 \
        --part $p --nparts 5 --total-rows 4330849
  done
  python3 pc/exp_receiver_term_prereg.py merge --tag d0wd --nparts 5 \
      --expect-rows 3344351
  python3 pc/exp_receiver_term_prereg.py merge --tag s3   --nparts 5 \
      --expect-rows 4330849
  python3 pc/exp_receiver_term_prereg.py report --tags d0wd,s3
"""
import argparse
import array
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

CACHE = os.environ.get("RXTERM_CACHE", "/tmp/rxterm")

# --- the project's yardsticks -------------------------------------------
# sd over the 3 units of their grand means (pc/exp_thermal_evidence.py:129,
# from docs/LOT_HYPOTHESIS.md 5). Every "x SD" below is this one, so the
# numbers stay comparable to docs/COLOCATED_0823.md 5.1.
BETWEEN_UNIT_SD = 0.00237
TWIN_DSFO = 0.00080

# Shipped gates, pc/rff/dsp.py:164. "Admissible" == passes both.
MIN_INLIER = 0.6
MAX_RESID = 0.8
# docs/REFERENCE_CHOICE.md 1.3 primary window, and the shipped window.
WIN_LONG = 16384
WIN_SHIP = 64

# Field-plausibility screen, docs/OVERNIGHT_2026-08-22.md 1.
CSI_LEN_OK = (128, 256, 384)
NF_LO, NF_HI = -110, -70
RSSI_LO, RSSI_HI = -100, -10
# Width-9 circular median filter on `dropped`, docs/DUAL_RX_2026-08-21.md
# Appendix A.
MED_W = 9
MED_TOL = 100
U16 = 65536

# prereg 4.5 / 8 / 3.3
FLOOR_PRIMARY = 20          # pc/mac_census.py --min-frames 20
FLOOR_SENS = 64             # one shipped window
SPARSE_MAX = 20             # "clean but sparse" == 1 <= n < 20 clean frames
BOOT_B = 200
BOOT_LMAX = 1024
BOOT_SEED = 20260823
BIN_SPARSE_S = 600.0        # 600 s occupancy bins, 41 over the span
BATCH_RES_S = 1.0           # pc_time_us drain-batch resolution floor

# Arrival times are retained per source up to this cap. The sparse test
# needs at most 19 of them; the cap only bounds memory on the beacons.
TIMES_CAP = 20000


# ----------------------------------------------------------------- state

class MacStat:
    """Per-source accumulators. `raw_n` counts every row bearing this MAC;
    everything else is over rows surviving BOTH corrupt-row screens.

    `slopes` holds every admissible per-frame slope in file order -- the
    frame-level statistic of prereg 2.3 needs the exact median, and the
    moving-block bootstrap of prereg 3.3 needs the order preserved."""

    __slots__ = ("raw_n", "n", "rssi_sum", "rssi_sq", "rssi_min", "rssi_max",
                 "t_first", "t_last", "times", "times_trunc",
                 "est", "agg_ship", "agg_long", "win_ship", "win_long",
                 "n_fit", "n_nofit", "n_gate_rej", "n_adm", "max_resid",
                 "slopes")

    def __init__(self):
        self.raw_n = 0
        self.n = 0
        self.rssi_sum = 0.0
        self.rssi_sq = 0.0
        self.rssi_min = None
        self.rssi_max = None
        self.t_first = None
        self.t_last = None
        self.times = []             # seconds since the file's own t0
        self.times_trunc = 0
        self.est = None
        self.agg_ship = None
        self.agg_long = None
        self.win_ship = []          # (ts_us, sfo, rssi)
        self.win_long = []
        self.n_fit = 0
        self.n_nofit = 0
        self.n_gate_rej = 0
        self.n_adm = 0              # fitted AND passing both shipped gates
        self.max_resid = 0.0
        self.slopes = array.array("d")


class State:
    def __init__(self, tag, path):
        self.tag = tag
        self.path = path
        self.byte_pos = 0
        self.rows = 0
        self.bad_parse = 0
        self.macs = defaultdict(MacStat)
        self.t0_us = None
        self.t_last_us = None
        self.node_hist = defaultdict(int)
        self.chan_hist = defaultdict(int)
        self.node_mode = None
        self.chan_mode = None
        # corrupt-row screening; `pend` holds rows in file order, the first
        # `n_hist` already emitted and retained as look-behind context.
        self.pend = []
        self.n_hist = 0
        self.n_field_bad = 0
        self.n_med_bad = 0
        self.n_both = 0
        self.n_corrupt = 0
        self.corrupt_macs = defaultdict(int)
        self.seam_checks = []


def spath(tag, part=None):
    if part is None:
        return os.path.join(CACHE, f"{tag}_state.pkl")
    return os.path.join(CACHE, f"{tag}_part{part}.pkl")


# ------------------------------------------------------------ line input

class Lines:
    """Byte-exact line source. Tracks the absolute byte offset AFTER the
    last line handed out so a part records where the next must resume.
    Opened "rb": the file is never written."""

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
        # Screen mode from a 20,000-row prescan, re-checked against the
        # whole-file histogram at merge (docs/REFERENCE_CHOICE.md 1.2).
        nh, ch = defaultdict(int), defaultdict(int)
        L = Lines(args.path, 0)
        it = iter(L)
        next(it)
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
        st.seam_checks.append((args.part, st.rows, st.byte_pos, st.t_last_us))

    per = math.ceil(args.total_rows / args.nparts)
    stop_at = min(args.total_rows, per * (args.part + 1))

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
            _flush(st, False)
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
            _flush(st, False)
            if st.rows >= stop_at:
                hit_limit = True
                break
            continue

        st.node_hist[node] += 1
        st.chan_hist[chan] += 1
        if st.t0_us is None:
            st.t0_us = pc_us
        st.t_last_us = pc_us

        fbad = not field_ok(node, env, chan, ln, nf, rssi,
                            st.node_mode, st.chan_mode)
        st.macs[mac].raw_n += 1
        st.pend.append((st.rows, pc_us, mac, rssi, esp_us, drop, row[9],
                        fbad))
        _flush(st, False)

        if st.rows >= stop_at:
            hit_limit = True
            break

    at_eof = (not hit_limit) or st.rows >= args.total_rows
    if at_eof:
        _flush(st, True)
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
    EOF, where the last rows are judged on the shorter window they have --
    all a filter can do at a boundary. Emission order is the file's."""
    half = MED_W // 2
    while st.n_hist < len(st.pend):
        ci = st.n_hist
        ahead = len(st.pend) - 1 - ci
        if not force and ahead < half:
            return
        lo = max(0, ci - half)
        hi = min(len(st.pend), ci + half + 1)
        vals = [st.pend[k][5] for k in range(lo, hi)]
        mbad = med_flag(vals, ci - lo) if len(vals) >= 3 else False
        _emit(st, st.pend[ci], mbad)
        st.n_hist += 1
        while st.n_hist > half:
            del st.pend[0]
            st.n_hist -= 1


def _emit(st, rec, mbad):
    (ridx, pc_us, mac, rssi, esp_us, drop, csi_s, fbad) = rec

    if fbad:
        st.n_field_bad += 1
    if mbad:
        st.n_med_bad += 1
    if fbad and mbad:
        st.n_both += 1
    if fbad or mbad:
        st.n_corrupt += 1
        st.corrupt_macs[mac] += 1
        return

    # ---- from here on the row is clean ----
    m = st.macs[mac]
    m.n += 1
    m.rssi_sum += rssi
    m.rssi_sq += rssi * rssi
    m.rssi_min = rssi if m.rssi_min is None else min(m.rssi_min, rssi)
    m.rssi_max = rssi if m.rssi_max is None else max(m.rssi_max, rssi)
    if m.t_first is None:
        m.t_first = pc_us
    m.t_last = pc_us
    if len(m.times) < TIMES_CAP:
        m.times.append((pc_us - st.t0_us) * 1e-6)
    else:
        m.times_trunc += 1

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
    if est["inlier_ratio"] < MIN_INLIER or est["resid_std"] > MAX_RESID:
        m.n_gate_rej += 1
    else:
        # admissible: exactly what WindowAggregator lets through
        m.n_adm += 1
        m.slopes.append(est["slope"])
    for agg, out in ((m.agg_ship, m.win_ship), (m.agg_long, m.win_long)):
        w = agg.feed(est, esp_us, rssi)
        if w is not None:
            out.append((w["ts_us"], w["sfo"], w["rssi"]))


# ------------------------------------------------------------------ merge

def run_merge(args):
    with open(spath(args.tag, args.nparts - 1), "rb") as f:
        st = pickle.load(f)
    ok_rows = (st.rows == args.expect_rows)
    seam_ok = all(a[3] is not None for a in st.seam_checks)
    print(f"[{args.tag} merge] rows={st.rows:,} expect={args.expect_rows:,} "
          f"{'MATCH' if ok_rows else 'MISMATCH'}; "
          f"{len(st.seam_checks)} seam(s), pc_time_us present at each: "
          f"{seam_ok}", file=sys.stderr)
    nm = max(st.node_hist.items(), key=lambda kv: kv[1])[0]
    cm = max(st.chan_hist.items(), key=lambda kv: kv[1])[0]
    agree = (nm, cm) == (st.node_mode, st.chan_mode)
    print(f"[{args.tag} merge] screen mode node={st.node_mode} "
          f"chan={st.chan_mode}; whole-file mode node={nm} chan={cm}; "
          f"{'AGREE' if agree else 'DISAGREE'}", file=sys.stderr)
    adm = sum(s.n_adm for s in st.macs.values())
    print(f"[{args.tag} merge] admissible frames retained {adm:,}",
          file=sys.stderr)
    st.pend = []
    with open(spath(args.tag), "wb") as f:
        pickle.dump(st, f, protocol=4)


# --------------------------------------------------- statistics, no scipy

def _betacf(a, b, x, itmax=300, eps=3e-16):
    """Continued fraction for the incomplete beta (modified Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def betainc(a, b, x):
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbeta) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta) * _betacf(b, a, 1.0 - x) / b


def t_sf(t, df):
    """Upper tail P(T > t) for Student-t with df degrees of freedom."""
    if df <= 0:
        return float("nan")
    x = df / (df + t * t)
    p = 0.5 * betainc(df / 2.0, 0.5, x)
    return p if t > 0 else 1.0 - p


def t_ppf975(df):
    """Two-tailed 5 % critical value, by bisection on t_sf."""
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_sf(mid, df) > 0.025:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def r_crit(n, k_ctrl):
    """Detection floor: smallest |r| clearing p<0.05 two-tailed at this n.
    k_ctrl = 0 for a raw correlation, 1 for a first-order partial."""
    df = n - 2 - k_ctrl
    if df < 1:
        return float("nan"), df
    tc = t_ppf975(df)
    return tc / math.sqrt(tc * tc + df), df


def r_pvalue(r, n, k_ctrl):
    df = n - 2 - k_ctrl
    if df < 1 or not (-1.0 < r < 1.0):
        return float("nan")
    t = abs(r) * math.sqrt(df / (1.0 - r * r))
    return 2.0 * t_sf(t, df)


def ranks(a):
    """Average ranks, ties shared."""
    a = np.asarray(a, float)
    order = np.argsort(a, kind="mergesort")
    r = np.empty(a.size, float)
    sa = a[order]
    i = 0
    while i < a.size:
        j = i
        while j + 1 < a.size and sa[j + 1] == sa[i]:
            j += 1
        r[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return r


def pearson(x, y):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    xc, yc = x - x.mean(), y - y.mean()
    d = math.sqrt(float((xc * xc).sum()) * float((yc * yc).sum()))
    return float((xc * yc).sum()) / d if d > 0 else float("nan")


def partial(rxy, rxz, ryz):
    den = math.sqrt(max(0.0, (1 - rxz ** 2) * (1 - ryz ** 2)))
    return (rxy - rxz * ryz) / den if den > 0 else float("nan")


def block_boot_var(x, seed):
    """Moving-block bootstrap variance of the median (prereg 3.3).
    Blocks rather than iid resampling because docs/SEPARATION_SCALING.md 0
    establishes the per-frame SFO series is not white beyond tau ~ 10-30 s;
    an iid bootstrap would understate the variance badly."""
    x = np.asarray(x, float)
    n = x.size
    if n < 4:
        return float("nan")
    L = max(1, min(BOOT_LMAX, n // 8))
    nb = int(math.ceil(n / L))
    rng = np.random.default_rng(seed)
    off = np.arange(L)
    hi = max(1, n - L + 1)
    out = np.empty(BOOT_B)
    for b in range(BOOT_B):
        starts = rng.integers(0, hi, size=nb)
        idx = (starts[:, None] + off[None, :]).ravel()[:n]
        idx = np.minimum(idx, n - 1)
        out[b] = np.median(x[idx])
    return float(out.var(ddof=1))


def range_p(k, w):
    """Exact P(normalised sample range <= w) for k iid Uniform arrivals:
    the Beta(k-1, 2) CDF, k*w^(k-1) - (k-1)*w^k. Undefined for k < 2."""
    if k < 2:
        return float("nan")
    w = min(max(w, 0.0), 1.0)
    return k * w ** (k - 1) - (k - 1) * w ** k


def range_wcrit(k, alpha=0.05):
    """Largest w that still rejects the uniform-arrival null at alpha."""
    if k < 2:
        return float("nan")
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if range_p(k, mid) < alpha:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def ks_uniform(u):
    """One-sample KS statistic against Uniform(0,1)."""
    u = np.sort(np.asarray(u, float))
    k = u.size
    if k == 0:
        return float("nan")
    i = np.arange(1, k + 1)
    return float(max((i / k - u).max(), (u - (i - 1) / k).max()))


def hl(t):
    print("\n" + t)
    print("-" * len(t))


# ----------------------------------------------------------------- report

def run_report(args):
    tags = args.tags.split(",")
    A, B = tags[0], tags[1]
    S = {}
    for t in tags:
        with open(spath(t), "rb") as f:
            S[t] = pickle.load(f)

    inv = {v: k for k, v in BEACON_MACS.items()}
    bn = ["B1", "B2", "B3"]
    span = {t: (S[t].t_last_us - S[t].t0_us) * 1e-6 for t in tags}

    hl("0. SPAN, INTEGRITY, AND THE TWO CORRUPT-ROW SCREENS")
    for t in tags:
        st = S[t]
        print(f"{t}: {st.path}")
        print(f"  data rows                     {st.rows:,}")
        print(f"  != 13 fields or unparseable   {st.bad_parse}")
        print(f"  node_id hist                  {dict(st.node_hist)}")
        print(f"  channel hist                  {dict(st.chan_hist)}")
        print(f"  span                          {span[t]:,.3f} s "
              f"= {span[t]/3600:.4f} h")
        print(f"  corrupt: field={st.n_field_bad} median={st.n_med_bad} "
              f"both={st.n_both} union={st.n_corrupt} "
              f"({1e6*st.n_corrupt/st.rows:.2f} ppm)")
        print(f"    caught by median filter ONLY  "
              f"{st.n_med_bad - st.n_both}   <-- invisible to the field screen")
        print(f"  clean rows                    {st.rows - st.n_corrupt:,}")

    # ------------------------------------------------ prereg 4: the funnel
    hl("1. INCLUSION FUNNEL -- n at every filtering step (prereg 4)")
    clean = {}
    for t in tags:
        st = S[t]
        clean[t] = {m: s for m, s in st.macs.items() if s.n > 0}
        only_corrupt = [m for m, s in st.macs.items()
                        if s.raw_n > 0 and s.n == 0]
        print(f"\n{t}:")
        print(f"  step 1  distinct MACs, every row          "
              f"{len([1 for s in st.macs.values() if s.raw_n > 0])}")
        print(f"  step 2  seen ONLY on corrupt rows         "
              f"-{len(only_corrupt)}")
        print(f"  step 3  distinct MACs on clean rows       {len(clean[t])}")
        print(f"          of which >= {FLOOR_PRIMARY} clean frames        "
              f"{len([1 for s in clean[t].values() if s.n >= FLOOR_PRIMARY])}"
              f"   <-- the 'real population' of docs/COLOCATED_0823.md 2")

    both = sorted(set(clean[A]) & set(clean[B]))
    print(f"\n  step 4  heard by BOTH receivers (>= 1 clean frame each)  "
          f"{len(both)}")
    only_a = sorted(set(clean[A]) - set(clean[B]))
    only_b = sorted(set(clean[B]) - set(clean[A]))
    print(f"          heard only by {A}: {len(only_a)}  "
          f"only by {B}: {len(only_b)}")

    def adm(t, m):
        s = S[t].macs.get(m)
        return s.n_adm if s else 0

    # Intermediate funnel row, required by prereg 4 ("n at every filtering
    # step"): the CLEAN-frame floor, which is what docs/COLOCATED_0823.md 2
    # applies, before admissibility is imposed on top of it. The gap between
    # this row and step 5 is the cost of the shipped gates, not of the census.
    both20c = [m for m in both
               if clean[A][m].n >= FLOOR_PRIMARY
               and clean[B][m].n >= FLOOR_PRIMARY]
    print(f"\n  step 4b >= {FLOOR_PRIMARY} CLEAN frames on both            "
          f"{len(both20c)}   (the census floor, admissibility not yet applied)")

    incl, dropped = [], []
    for m in both:
        na, nb = adm(A, m), adm(B, m)
        (incl if min(na, nb) >= FLOOR_PRIMARY else dropped).append(m)
    incl.sort(key=lambda m: -min(adm(A, m), adm(B, m)))
    print(f"\n  step 5  >= {FLOOR_PRIMARY} ADMISSIBLE frames on both        "
          f"{len(incl)}   <-- n FOR THE TEST")
    incl64 = [m for m in both
              if min(adm(A, m), adm(B, m)) >= FLOOR_SENS]
    print(f"          (sensitivity floor {FLOOR_SENS}: n = {len(incl64)})")
    print(f"\n  admissible / clean frame ratio, every source heard by both "
          f"with >= {FLOOR_PRIMARY} clean frames on both:")
    print(f"    {'mac':<18} {'adm/clean '+A:>16} {'adm/clean '+B:>16}  kept?")
    for m in sorted(both20c, key=lambda m: -min(clean[A][m].n,
                                                clean[B][m].n)):
        ca, cb = clean[A][m].n, clean[B][m].n
        na, nb = adm(A, m), adm(B, m)
        print(f"    {m:<18} {na/ca:>15.3f}  {nb/cb:>15.3f}  "
              f"{'yes' if m in [x for x in both if min(adm(A,x),adm(B,x)) >= FLOOR_PRIMARY] else 'no'}")

    print(f"\n  every source dropped at step 4 or 5, with its reason:")
    print(f"    {'mac':<18} {'clean '+A:>11} {'clean '+B:>11} "
          f"{'adm '+A:>10} {'adm '+B:>10}  reason")
    for m in only_a + only_b + dropped:
        ca = clean[A][m].n if m in clean[A] else 0
        cb = clean[B][m].n if m in clean[B] else 0
        na, nb = adm(A, m), adm(B, m)
        if m not in clean[A]:
            why = f"not heard by {A}"
        elif m not in clean[B]:
            why = f"not heard by {B}"
        else:
            why = (f"admissible frames below {FLOOR_PRIMARY} on "
                   + ("both" if na < FLOOR_PRIMARY and nb < FLOOR_PRIMARY
                      else (A if na < FLOOR_PRIMARY else B)))
        flag = ""
        if m in BEACON_MACS:
            flag = f"  [{BEACON_MACS[m]}]"
        print(f"    {m:<18} {ca:>11,} {cb:>11,} {na:>10,} {nb:>10,}  "
              f"{why}{flag}")

    if len(incl) < 3:
        print("\n  FEWER THAN 3 SOURCES SURVIVE. No correlation is defined.")
        return

    # ------------------------------------- prereg 2.3: the statistic table
    def sfo_frame(t, m):
        s = S[t].macs[m]
        return float(np.median(np.frombuffer(s.slopes, dtype=np.float64)))

    def sfo_win(t, m, attr):
        s = S[t].macs.get(m)
        w = [x[1] for x in getattr(s, attr)] if s else []
        return (float(np.median(w)), len(w)) if len(w) >= 3 else \
               (float("nan"), len(w))

    hl("2. THE PER-SOURCE DISAGREEMENT STATISTIC (prereg 2.3)")
    print(f"Delta_signed = SFO({A}) - SFO({B}); SFO = median of admissible "
          f"per-frame slopes")
    print(f"sigma = BETWEEN_UNIT_SD = {BETWEEN_UNIT_SD} "
          f"(pc/exp_thermal_evidence.py:129)")
    print(f"\n{'mac':<18} {'role':<5} {'adm '+A:>10} {'adm '+B:>10} "
          f"{'SFO '+A:>11} {'SFO '+B:>11} {'D_signed':>11} {'|D|/sd':>8} "
          f"{'RSSI':>7} {'rej% '+A:>8} {'rej% '+B:>8}")
    rows = []
    for m in incl:
        sa, sb = sfo_frame(A, m), sfo_frame(B, m)
        d = sa - sb
        ma, mb = S[A].macs[m], S[B].macs[m]
        ra, rb = ma.rssi_sum / ma.n, mb.rssi_sum / mb.n
        rja = 100.0 * ma.n_gate_rej / max(1, ma.n_fit)
        rjb = 100.0 * mb.n_gate_rej / max(1, mb.n_fit)
        rows.append(dict(mac=m, role=BEACON_MACS.get(m, ""),
                         na=ma.n_adm, nb=mb.n_adm, sa=sa, sb=sb,
                         d=d, ad=abs(d), rssi=0.5 * (ra + rb),
                         rssi_min=min(ra, rb), ra=ra, rb=rb,
                         nmin=min(ma.n_adm, mb.n_adm), rja=rja, rjb=rjb))
        print(f"{m:<18} {BEACON_MACS.get(m,''):<5} {ma.n_adm:>10,} "
              f"{mb.n_adm:>10,} {sa:>+11.5f} {sb:>+11.5f} {d:>+11.5f} "
              f"{abs(d)/BETWEEN_UNIT_SD:>8.2f} {0.5*(ra+rb):>7.2f} "
              f"{rja:>8.2f} {rjb:>8.2f}")

    # ------------------- prereg 2.4: does the substitution reproduce 5.1?
    hl("3. VALIDATION OF THE SUBSTITUTED STATISTIC (prereg 2.4)")
    print("The three beacons under all three statistics, against "
          "docs/COLOCATED_0823.md 5.1")
    ref51 = {"B1": 0.00168, "B2": 0.03870, "B3": -0.01610}
    print(f"{'b':<3} {'frame-level':>13} {'win 16384':>13} {'win 64':>13} "
          f"{'COLOCATED 5.1':>14} {'frame vs w16384':>16}")
    val_ok, val_notes = True, []
    beac_frame, beac_w16 = {}, {}
    for b in bn:
        m = inv[b]
        if m not in S[A].macs or m not in S[B].macs:
            print(f"{b:<3} (missing)")
            val_ok = False
            continue
        df_ = sfo_frame(A, m) - sfo_frame(B, m)
        w16a, na16 = sfo_win(A, m, "win_long")
        w16b, nb16 = sfo_win(B, m, "win_long")
        w64a, _ = sfo_win(A, m, "win_ship")
        w64b, _ = sfo_win(B, m, "win_ship")
        dw16 = w16a - w16b
        dw64 = w64a - w64b
        beac_frame[b] = df_
        beac_w16[b] = dw16
        rel = (abs(abs(df_) - abs(dw16)) / abs(dw16)
               if dw16 == dw16 and dw16 != 0 else float("nan"))
        print(f"{b:<3} {df_:>+13.5f} {dw16:>+13.5f} {dw64:>+13.5f} "
              f"{ref51[b]:>+14.5f} {100*rel:>15.1f}%")
        if not (rel == rel and rel <= 0.25):
            val_ok = False
            val_notes.append(f"{b}: frame-level differs from win16384 by "
                             f"{100*rel:.1f}% (> 25 %)")
    order_frame = sorted(bn, key=lambda b: -abs(beac_frame.get(b, 0)))
    print(f"\n  rank order by |Delta|, frame-level: "
          f"{' > '.join(order_frame)}   (prereg requires B2 > B3 > B1)")
    if order_frame != ["B2", "B3", "B1"]:
        val_ok = False
        val_notes.append(f"rank order is {order_frame}, not ['B2','B3','B1']")
    print(f"  ACCEPTANCE CRITERION (prereg 2.4): "
          f"{'PASS -- frame-level statistic is the primary' if val_ok else 'FAIL'}")
    for nnote in val_notes:
        print(f"    - {nnote}")

    # --------------------------------------- prereg 3.3/3.4: the test
    hl("4. THE TEST (prereg 3.4) -- partial Spearman, control = log10 n_min")
    d_signed = np.array([r["d"] for r in rows])
    d_abs = np.array([r["ad"] for r in rows])
    rssi = np.array([r["rssi"] for r in rows])
    rssi_min = np.array([r["rssi_min"] for r in rows])
    logn = np.log10(np.array([r["nmin"] for r in rows], float))
    n = len(rows)

    def report_corr(label, dvals, yvals, zvals):
        x, y, z = ranks(dvals), ranks(yvals), ranks(zvals)
        rxy, rxz, ryz = pearson(x, y), pearson(x, z), pearson(y, z)
        rp = partial(rxy, rxz, ryz)
        rc0, df0 = r_crit(n, 0)
        rc1, df1 = r_crit(n, 1)
        print(f"\n  {label}")
        print(f"    n = {n}")
        print(f"    raw     r(|D|, RSSI)            = {rxy:+.4f}   "
              f"p = {r_pvalue(rxy, n, 0):.4f}   floor |r| > {rc0:.4f} "
              f"(df {df0})")
        print(f"    control r(|D|, log10 n_min)     = {rxz:+.4f}   "
              f"p = {r_pvalue(rxz, n, 0):.4f}")
        print(f"    collin. r(RSSI, log10 n_min)    = {ryz:+.4f}   "
              f"p = {r_pvalue(ryz, n, 0):.4f}")
        print(f"    PARTIAL r(|D|, RSSI . log n)    = {rp:+.4f}   "
              f"p = {r_pvalue(rp, n, 1):.4f}   "
              f"DETECTION FLOOR |r| > {rc1:.4f} (df {df1})")
        return rxy, rp, rc0, rc1

    rxy, rp, rc0, rc1 = report_corr(
        "PRIMARY: Spearman, RSSI = mean of the two receivers", d_abs,
        rssi, logn)

    hl("5. PRE-REGISTERED SENSITIVITIES (prereg 3.5)")
    report_corr("(1) RSSI_min substituted", d_abs, rssi_min, logn)

    keep = [i for i, r in enumerate(rows)
            if r["rja"] <= 50.0 and r["rjb"] <= 50.0]
    dropped_hi = [rows[i]["mac"] + (f" [{rows[i]['role']}]"
                                    if rows[i]["role"] else "")
                  for i in range(n) if i not in keep]
    print(f"\n  (2) sources with > 50 % gate rejection on either receiver, "
          f"excluded: {len(dropped_hi)}")
    for dh in dropped_hi:
        print(f"        {dh}")
    if len(keep) >= 5:
        n_save = n
        n = len(keep)
        report_corr("(2) high-rejection cells excluded", d_abs[keep],
                    rssi[keep], logn[keep])
        n = n_save
    else:
        print("        too few remain to correlate")

    pos = d_abs > 0
    if pos.sum() >= 5:
        n_save = n
        n = int(pos.sum())
        x, y, z = np.log10(d_abs[pos]), rssi[pos], logn[pos]
        rxy3, rxz3, ryz3 = pearson(x, y), pearson(x, z), pearson(y, z)
        rp3 = partial(rxy3, rxz3, ryz3)
        rc1b, df1b = r_crit(n, 1)
        print(f"\n  (3) Pearson on log10|D| (parametric check), n = {n}")
        print(f"        raw     r = {rxy3:+.4f}   partial r = {rp3:+.4f}   "
              f"p = {r_pvalue(rp3, n, 1):.4f}   floor {rc1b:.4f} (df {df1b})")
        n = n_save

    w64 = []
    for r in rows:
        a64, ca = sfo_win(A, r["mac"], "win_ship")
        b64, cb = sfo_win(B, r["mac"], "win_ship")
        if a64 == a64 and b64 == b64:
            w64.append((abs(a64 - b64), r["rssi"], r["nmin"]))
    print(f"\n  (4) window-64 Delta substituted: "
          f"{len(w64)} of {len(rows)} sources emit >= 3 windows on both")
    if len(w64) >= 5:
        n_save = n
        n = len(w64)
        report_corr("(4) window-64 statistic", [q[0] for q in w64],
                    [q[1] for q in w64],
                    np.log10([q[2] for q in w64]))
        n = n_save

    # -------------------------------------------------- prereg 3.3: H3
    hl("6. H3 -- IS THE DISAGREEMENT A FIXED RECEIVER-PAIR OFFSET? "
       "(prereg 3.3)")
    print("H3 is tested on Delta_SIGNED: a fixed offset is a signed "
          "constant.")
    bvars = []
    print(f"\n  {'mac':<18} {'role':<5} {'D_signed':>11} {'boot sd(D)':>12} "
          f"{'block L '+A:>11} {'block L '+B:>11}")
    for i, r in enumerate(rows):
        xa = np.frombuffer(S[A].macs[r["mac"]].slopes, dtype=np.float64)
        xb = np.frombuffer(S[B].macs[r["mac"]].slopes, dtype=np.float64)
        va = block_boot_var(xa, BOOT_SEED + i)
        vb = block_boot_var(xb, BOOT_SEED + 10000 + i)
        v = va + vb
        bvars.append(v)
        print(f"  {r['mac']:<18} {r['role']:<5} {r['d']:>+11.5f} "
              f"{math.sqrt(v):>12.6f} "
              f"{max(1, min(BOOT_LMAX, xa.size//8)):>11,} "
              f"{max(1, min(BOOT_LMAX, xb.size//8)):>11,}")
    bvars = np.array(bvars)
    var_across = float(d_signed.var(ddof=1))
    med_boot = float(np.nanmedian(bvars))
    R_disp = var_across / med_boot if med_boot > 0 else float("inf")
    print(f"\n    Var across sources of D_signed      {var_across:.6e}")
    print(f"    median block-bootstrap Var(D)       {med_boot:.6e}   "
          f"(a LOWER bound, prereg 2.5)")
    print(f"    R_disp                              {R_disp:,.1f}   "
          f"(H3 survives only if < 2)")
    print(f"    range ratio max|D| / min|D|         "
          f"{d_abs.max()/d_abs.min():,.1f}")
    print(f"    signs of D_signed: {int((d_signed>0).sum())} positive, "
          f"{int((d_signed<0).sum())} negative")
    print(f"    H3: {'SURVIVES' if R_disp < 2 else 'FALSIFIED'}")

    # ------------------------------------------------- prereg 6/7: verdict
    hl("7. VERDICT (prereg 7, applied mechanically)")
    print(f"  n = {n}   detection floor for the partial |r| > {rc1:.4f}")
    underpowered = (n < 6) or (rc1 > 0.70 and abs(rp) < rc1)
    if n < 6:
        v = "UNDERPOWERED (n < 6). No hypothesis supported or rejected."
    elif rp <= -rc1:
        v = "H1 SUPPORTED, H2 REJECTED -- disagreement is fit noise."
    elif rp >= rc1:
        v = "H2 SUPPORTED, H1 REJECTED -- disagreement is baseline geometry."
    elif abs(rxy) >= rc0 and abs(rp) < rc1:
        v = ("CONSISTENT WITH FRAME COUNT, NOT RSSI -- the raw correlation "
             "clears its floor, the partial does not.")
    elif R_disp < 2:
        v = f"H3 SURVIVES -- no RSSI effect above |r| = {rc1:.3f}."
    else:
        v = (f"NEITHER -- |r_partial| = {abs(rp):.3f} < {rc1:.3f}, and "
             f"R_disp = {R_disp:,.0f} >= 2 so H3 is falsified too.")
    print(f"  {v}")
    if underpowered:
        print(f"  UNDERPOWERED: the floor {rc1:.3f} exceeds 0.70, so a "
              f"non-significant partial is not support for H3.")

    # ------------------------------------ prereg 8: the sparse-address test
    hl("8. THE OPERATOR'S HYPOTHESIS -- ARE THE SPARSE ADDRESSES "
       "PASSERS-BY? (prereg 8)")
    print("Statistic: normalised sample range W = (t_k - t_1)/T against its "
          "exact")
    print("Beta(k-1, 2) uniform-arrival null, p = k*W^(k-1) - (k-1)*W^k.")
    print("pc/mac_census.py counts frames only and never looks at arrival "
          "time.")

    for t in tags:
        st = S[t]
        T = span[t]
        sparse = sorted([m for m, s in clean[t].items()
                         if 0 < s.n < SPARSE_MAX],
                        key=lambda m: -clean[t][m].n)
        print(f"\n{t}: {len(sparse)} clean-but-sparse addresses "
              f"(1 <= clean frames < {SPARSE_MAX})")
        ks_present = sorted({clean[t][m].n for m in sparse})
        print(f"  detection floor, largest W that still rejects at 0.05 "
              f"(prereg 8.4):")
        print("    " + "  ".join(
            f"k={k}: W<={range_wcrit(k):.4f} ({range_wcrit(k)*T:,.0f}s)"
            for k in ks_present if k >= 2))
        print(f"\n  {'mac':<18} {'k':>3} {'span s':>10} {'W':>8} {'p':>9} "
              f"{'KS':>6} {'bins/41':>8} {'maxgap s':>10}  class")
        cls = defaultdict(list)
        for m in sparse:
            s = clean[t][m]
            tt = sorted(s.times)
            k = len(tt)
            spn = tt[-1] - tt[0] if k >= 2 else 0.0
            W = spn / T
            p = range_p(k, W)
            ks = ks_uniform([x / T for x in tt]) if k >= 1 else float("nan")
            nbins = len({int(x // BIN_SPARSE_S) for x in tt})
            gap = max((tt[i + 1] - tt[i] for i in range(k - 1)), default=0.0)
            if k < 2:
                c = "undecidable"
            elif p < 0.05:
                c = "TRANSIENT"
            elif W >= 0.5:
                c = "resident"
            else:
                c = "undecidable"
            cls[c].append(m)
            tagsfx = ""
            if k >= 2 and spn < BATCH_RES_S:
                tagsfx = " single-batch(p is an upper bound)"
            if c == "TRANSIENT" and spn <= 600:
                tagsfx += " passer-by scale(<=600s)"
            print(f"  {m:<18} {k:>3} {spn:>10.1f} {W:>8.5f} {p:>9.5f} "
                  f"{ks:>6.3f} {nbins:>8} {gap:>10.1f}  {c}{tagsfx}")
        print(f"\n  {t} SPLIT: transient {len(cls['TRANSIENT'])}, "
              f"resident {len(cls['resident'])}, "
              f"undecidable {len(cls['undecidable'])}  "
              f"(of {len(sparse)})")
        if t == A:
            sparse_a, cls_a = sparse, cls

    # cross-receiver check, prereg 8.5
    hl("9. CROSS-RECEIVER CHECK ON THE SPARSE ADDRESSES (prereg 8.5)")
    print("A real passer-by is a physical event and should look transient "
          "on BOTH")
    print("receivers. Disagreement is evidence of a per-receiver artefact, "
          "not a device.")
    print(f"\n  {'mac':<18} {A+' k':>7} {A+' class':>12} "
          f"{B+' k':>7} {B+' class':>12}  agree?")
    agree = dis = nocheck = 0
    for m in sparse_a:
        ka = clean[A][m].n
        ca = ("TRANSIENT" if m in cls_a["TRANSIENT"]
              else ("resident" if m in cls_a["resident"] else "undecidable"))
        if m not in clean[B]:
            print(f"  {m:<18} {ka:>7} {ca:>12} {0:>7} {'not heard':>12}  "
                  f"n/a")
            nocheck += 1
            continue
        sb = clean[B][m]
        tt = sorted(sb.times)
        kb = len(tt)
        if kb < 2:
            cb = "undecidable"
        else:
            W = (tt[-1] - tt[0]) / span[B]
            p = range_p(kb, W)
            cb = ("TRANSIENT" if p < 0.05
                  else ("resident" if W >= 0.5 else "undecidable"))
        same = (ca == cb)
        if ca == "undecidable" or cb == "undecidable":
            nocheck += 1
            mark = "n/a"
        elif same:
            agree += 1
            mark = "yes"
        else:
            dis += 1
            mark = "NO"
        print(f"  {m:<18} {ka:>7} {ca:>12} {kb:>7} {cb:>12}  {mark}")
    print(f"\n  agree {agree}, disagree {dis}, not comparable {nocheck}")

    hl("10. YARDSTICKS")
    print(f"  BETWEEN_UNIT_SD = {BETWEEN_UNIT_SD} "
          f"(pc/exp_thermal_evidence.py:129, docs/LOT_HYPOTHESIS.md 5)")
    print(f"  twin dSFO       = {TWIN_DSFO} (docs/LOT_HYPOTHESIS.md)")
    print(f"  shipped gates   = inlier >= {MIN_INLIER}, resid <= {MAX_RESID} "
          f"(pc/rff/dsp.py:164)")


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
    p.set_defaults(fn=run_report)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
