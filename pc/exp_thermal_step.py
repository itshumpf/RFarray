#!/usr/bin/env python3
"""THERMAL_STEP -- a controlled thermal step on B3, scored on two features.

Pre-registration: docs/THERMAL_STEP.md (Stage 1, frozen before this ran).

Design in one paragraph. B3 spent ~1 h outdoors and was carried back in; the
capture pair data/raw/{s3,d0wd}_20260823_151725.csv opens immediately on
return and runs 70.29 min. B1, B2 and both receivers were untouched. So the
early bins of the file hold B3 equilibrating and the tail holds it settled,
while B1 and B2 supply a contemporaneous no-treatment control. Two features
are tracked per (receiver x beacon x time bin):

  1. the SHIPPED SFO slope -- pc/rff/dsp.py FrameEstimator + WindowAggregator,
     imported and used as-is, never modified. Its RANSAC draws from a
     per-instance RNG that advances once per fitted frame (dsp.py:118,132),
     so each (file, MAC) stream is replayed from the first data row with one
     fresh estimator, in file order, no subsampling and no seeking.
  2. kappa, the IQ imbalance coefficient of docs/IQ_IMBALANCE.md -- the
     estimator is IMPORTED from pc/exp_iq_imbalance.py (Cell, process_batch,
     features, add_cells, frames_to_H, deslope, field_ok, med_flag, S_TRUE,
     S_NULL, SHIFTS) and is not reimplemented here.

Cells are accumulated at 20 s granularity. Every Cell field is a plain sum, so
coarser bins are formed by add_cells() rather than by a second pass -- which
is why one scan yields the 60 s primary binning, the 20 s reboot-resolution
binning and the whole-file value.

Constraints (docs/THERMAL_STEP.md section 8): read-only on data/raw/, every
input opened "rb"; no serial port; pc/rff/dsp.py not modified;
pc/capture.py:compute_cfo, pc/phase_skew.py and pc/fingerprint.py not used;
corrupt rows screened before any delta arithmetic; csi_data read with
csv.reader, never line.split(','); scratch under $TSTEP_CACHE outside the
repo; nothing staged, committed or pushed.

Usage
-----
  export TSTEP_CACHE=/tmp/tstep PYTHONDONTWRITEBYTECODE=1
  python3 pc/exp_thermal_step.py scan --tag s3 \
      --path data/raw/s3_20260823_151725.csv --resume --seconds 150
  python3 pc/exp_thermal_step.py scan --tag d0wd \
      --path data/raw/d0wd_20260823_151725.csv --resume --seconds 150
  python3 pc/exp_thermal_step.py report
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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pc.rff import dsp                      # noqa: E402  (used AS-IS)
import pc.exp_iq_imbalance as iq            # noqa: E402  (kappa estimator)

CACHE = os.environ.get("TSTEP_CACHE", "/tmp/tstep")

# ------------------------------------------------------------------ config
BIN_S = 20.0                 # accumulation granularity; 60 s formed by summing
PRIMARY_BIN_S = 60.0         # docs/THERMAL_STEP.md 3.1
BEACONS = {
    "f4:2d:c9:70:72:30": "B3",     # TREATED -- outdoors ~1 h, returned
    "a4:f0:0f:77:91:20": "B1",     # control -- untouched
    "28:05:a5:2f:fa:48": "B2",     # control -- untouched
}
TREATED = "f4:2d:c9:70:72:30"
BETWEEN_UNIT_SD = 0.00237    # pc/exp_thermal_evidence.py:129, via exp_b3_moved.py:64
THERMAL_EVIDENCE_MED = 0.00061   # docs/THERMAL_EVIDENCE.md section 3, rad/sc
# docs/B3_MOVED.md 9.1 -- stationary-beacon wander bar, in BETWEEN_UNIT_SD
WANDER_BAR = {("s3", "B3"): 4.91, ("s3", "B1"): 2.72, ("s3", "B2"): 0.42,
              ("d0wd", "B3"): 2.76, ("d0wd", "B1"): 2.52,
              ("d0wd", "B2"): 17.99}
# docs/B3_MOVED.md 9.6 -- the channel-reversal control
B2_CHANNEL = {"d0wd": {"present_rssi": -79, "absent_rssi": -73,
                       "present_fps": 42.06, "absent_fps": 62.02},
              "s3": {"present_rssi": -75, "absent_rssi": -71,
                     "present_fps": 65.27, "absent_fps": 76.30}}

BATCH = 2048
TAU_GRID = np.exp(np.linspace(math.log(0.5), math.log(35.0), 48))   # minutes
PERM_BLOCK = 5
PERM_N = 2000
PERM_SEED = 20260823
DBIC_GATE = 10.0
TAU_LO, TAU_HI = 1.0, 30.0
EARLY_S, LATE_S = 300.0, 1200.0    # first 5 min vs last 20 min


# ------------------------------------------------------ integrity at import
def _check_convention():
    """docs/THERMAL_STEP.md 2.4 -- the interleave convention, checked not
    assumed, on real int8 values rather than by reading the source."""
    rng = np.random.default_rng(7)
    v = rng.integers(-40, 40, size=dsp.N_CPLX * 2).astype(np.float64)
    a = dsp.csi_to_complex(v)                      # dsp.py:43-52
    b = iq.frames_to_H(v[None, :])[0]              # exp_iq_imbalance.py:172
    assert np.allclose(a[iq.IDX], b), "kappa arm and dsp disagree on interleave"
    assert np.allclose(a, v[1::2] + 1j * v[0::2]), "dsp is not imag,real"
    return True


_check_convention()


# ---------------------------------------------------------------- scanning
class Scan:
    """Resumable state for one file. Pickled between host time-cap chunks."""

    def __init__(self, tag, path):
        self.tag = tag
        self.path = path
        self.rows = 0
        self.bad_parse = 0
        self.n_field_bad = 0
        self.n_med_bad = 0
        self.n_both = 0
        self.n_corrupt = 0
        self.n_medonly = 0
        self.corrupt_macs = defaultdict(int)
        self.clean_macs = defaultdict(int)
        self.raw_macs = defaultdict(int)
        self.cells = defaultdict(iq.Cell)        # (mac, bin20) -> Cell
        self.win = defaultdict(list)             # mac -> [(tsec, sfo, rssi, q)]
        self.est = {}                            # mac -> FrameEstimator
        self.agg = {}                            # mac -> WindowAggregator
        self.rssi_bin = defaultdict(lambda: [0.0, 0])   # (mac,bin20)->[sum,n]
        self.t0_us = None
        self.t_last_us = None
        self.node_mode = None
        self.chan_mode = None
        self.byte_pos = 0
        self.pend = []
        self.n_hist = 0
        self.eof = False
        self.resumes = []
        self.guard_zero = [0, 0]                 # [zero, total] sampled


def run_scan(args):
    os.makedirs(CACHE, exist_ok=True)
    csv.field_size_limit(10 ** 7)
    # docs/IQ_IMBALANCE.md 10.2: the ESP32 LLTF buffer is ALREADY a channel
    # estimate divided by L(k) (roughness 19x/38x smoother). exp_iq_imbalance
    # spells that "divided", and its process_batch multiplies by L only when
    # variant_div is False. So the resolved branch is variant_div=True.
    variant_div = (args.convention == "divided")
    s_vec = np.ones(iq.NK) if args.svar == "s1" else iq.S_TRUE
    spath = os.path.join(CACHE, f"{args.tag}_{args.svar}_scan.pkl")

    if args.resume and os.path.exists(spath):
        with open(spath, "rb") as f:
            st = pickle.load(f)
        if st.eof:
            print(f"[{args.tag}] already at EOF, rows={st.rows:,}",
                  file=sys.stderr)
            return
        st.resumes.append((st.rows, st.byte_pos))
        L = iq.Lines(args.path, st.byte_pos)
        r = csv.reader(iter(L))
    else:
        st = Scan(args.tag, args.path)
        nh, ch = defaultdict(int), defaultdict(int)
        L = iq.Lines(args.path)
        it = iter(L)
        header = next(csv.reader([next(it)]))
        assert header[:13] == ["pc_time_us", "label", "seq", "mac", "rssi",
                               "noise_floor", "channel", "esp_timestamp_us",
                               "len", "csi_data", "node_id", "env_id",
                               "dropped"], header
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
        L = iq.Lines(args.path)
        it2 = iter(L)
        next(it2)
        st.byte_pos = L.pos
        L.close()
        L = iq.Lines(args.path, st.byte_pos)
        r = csv.reader(iter(L))

    pend = st.pend
    n_hist = st.n_hist
    half = iq.MED_W // 2
    bufs = defaultdict(list)
    t0 = time.time()

    def emit(rec):
        (pc_us, mac, rssi, esp_us, drop, csi_s, fbad, mbad) = rec
        if fbad:
            st.n_field_bad += 1
        if mbad:
            st.n_med_bad += 1
        if fbad and mbad:
            st.n_both += 1
        if mbad and not fbad:
            st.n_medonly += 1
        if fbad or mbad:
            st.n_corrupt += 1
            st.corrupt_macs[mac] += 1
            return
        st.clean_macs[mac] += 1
        if mac not in BEACONS:
            return
        tsec = (pc_us - st.t0_us) * 1e-6
        b20 = int(tsec // BIN_S)
        try:
            vals = [int(x) for x in csi_s.split(",", dsp.N_CPLX * 2)
                    [: dsp.N_CPLX * 2]]
        except ValueError:
            return
        if len(vals) < dsp.N_CPLX * 2:
            return

        # ---- feature 1: the SHIPPED estimator, one fresh instance per stream
        if mac not in st.est:
            st.est[mac] = dsp.FrameEstimator()
            st.agg[mac] = dsp.WindowAggregator()
        e = st.est[mac].feed(vals, esp_us)
        w = st.agg[mac].feed(e, pc_us, rssi)
        if w is not None:
            st.win[mac].append(((w["ts_us"] - st.t0_us) * 1e-6, w["sfo"],
                                w["rssi"], w["quality"]))

        # ---- feature 2: kappa, via the imported estimator
        key = (mac, b20)
        rb = st.rssi_bin[key]
        rb[0] += rssi
        rb[1] += 1
        c = st.cells[key]
        c.n_clean += 1
        c.rssi_sum += rssi
        b = bufs[key]
        b.append(vals)
        if len(b) >= BATCH:
            iq.process_batch(c, b, s_vec, variant_div)
            bufs[key] = []

    def flush_pend(force):
        nonlocal n_hist
        while n_hist < len(pend):
            ci = n_hist
            if not force and (len(pend) - 1 - ci) < half:
                return
            lo = max(0, ci - half)
            hi = min(len(pend), ci + half + 1)
            vals = [pend[k][4] for k in range(lo, hi)]
            mbad = iq.med_flag(vals, ci - lo) if len(vals) >= 3 else False
            rec = pend[ci]
            emit((rec[0], rec[1], rec[2], rec[3], rec[4], rec[5], rec[6],
                  mbad))
            n_hist += 1
            while n_hist > half:
                del pend[0]
                n_hist -= 1

    deadline = time.time() + args.seconds if args.seconds else None
    stopped_early = False
    for row in r:
        st.rows += 1
        if args.max_rows and st.rows > args.max_rows:
            st.rows -= 1
            stopped_early = True
            break
        if len(row) != 13:
            st.bad_parse += 1
            flush_pend(False)
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
            flush_pend(False)
            continue
        if st.t0_us is None:
            st.t0_us = pc_us
        st.t_last_us = pc_us
        st.raw_macs[mac] += 1
        fbad = not iq.field_ok(node, env, chan, ln, nf, rssi,
                               st.node_mode, st.chan_mode)
        pend.append((pc_us, mac, rssi, esp_us, drop, row[9], fbad))
        flush_pend(False)
        if st.rows % 20000 == 0:
            if st.rows % 1000000 == 0:
                print(f"[{args.tag}] {st.rows:,} rows {time.time()-t0:.0f}s "
                      f"corrupt={st.n_corrupt}", file=sys.stderr, flush=True)
            if deadline and time.time() > deadline:
                stopped_early = True
                break

    st.byte_pos = L.pos
    if not stopped_early:
        flush_pend(True)
        st.eof = True
    for key, b in bufs.items():
        if b:
            iq.process_batch(st.cells[key], b, s_vec, variant_div)
    L.close()
    st.pend = pend
    st.n_hist = n_hist
    st.cells = dict(st.cells)
    st.win = dict(st.win)
    st.rssi_bin = {k: v for k, v in st.rssi_bin.items()}
    with open(spath, "wb") as f:
        pickle.dump(st, f, protocol=4)
    print(f"[{args.tag}] {'DONE' if st.eof else 'CHECKPOINT'} "
          f"rows={st.rows:,} corrupt={st.n_corrupt} "
          f"(field={st.n_field_bad} med={st.n_med_bad} both={st.n_both} "
          f"med-only={st.n_medonly}) byte_pos={st.byte_pos:,} "
          f"in {time.time()-t0:.0f}s", file=sys.stderr, flush=True)


# ------------------------------------------------------------ model fitting
def _bic(rss, n, k):
    if rss <= 0 or n <= 0:
        return -np.inf
    return n * math.log(rss / n) + k * math.log(n)


def fit_models(t_min, y):
    """M0 const, M1 linear, M2 a+b*exp(-t/tau), M3 step at unknown time.

    t_min in minutes, y the binned feature. Returns a dict of BICs, params and
    shape diagnostics. docs/THERMAL_STEP.md sections 3.1 and 5.
    """
    n = y.size
    out = {"n": n}
    if n < 8:
        return None
    # M0
    r0 = y - y.mean()
    rss0 = float((r0 ** 2).sum())
    out["bic0"] = _bic(rss0, n, 1)
    out["rss0"] = rss0
    # M1
    A1 = np.column_stack([np.ones(n), t_min])
    c1, *_ = np.linalg.lstsq(A1, y, rcond=None)
    rss1 = float(((y - A1 @ c1) ** 2).sum())
    out["bic1"] = _bic(rss1, n, 2)
    out["m1_slope"] = float(c1[1])
    # M2 -- tau on a grid, linear in (a, b) given tau
    best = None
    for tau in TAU_GRID:
        A2 = np.column_stack([np.ones(n), np.exp(-t_min / tau)])
        c2, *_ = np.linalg.lstsq(A2, y, rcond=None)
        rss = float(((y - A2 @ c2) ** 2).sum())
        if best is None or rss < best[0]:
            best = (rss, tau, c2)
    rss2, tau2, c2 = best
    out["bic2"] = _bic(rss2, n, 3)
    out["tau"] = float(tau2)
    out["m2_a"] = float(c2[0])
    out["m2_b"] = float(c2[1])
    out["rss2"] = rss2
    out["r_shape"] = 1.0 - rss2 / rss0 if rss0 > 0 else 0.0
    out["tau_at_edge"] = bool(tau2 <= TAU_GRID[1] or tau2 >= TAU_GRID[-2])
    # M3 -- step at unknown boundary
    bestS = None
    for i in range(2, n - 2):
        m1_, m2_ = y[:i].mean(), y[i:].mean()
        rss = float(((y[:i] - m1_) ** 2).sum() + ((y[i:] - m2_) ** 2).sum())
        if bestS is None or rss < bestS[0]:
            bestS = (rss, i, m2_ - m1_)
    rss3, i3, d3 = bestS
    out["bic3"] = _bic(rss3, n, 3)
    out["step_bin"] = int(i3)
    out["step_t"] = float(t_min[i3])
    out["step_d"] = float(d3)
    # deltas (positive = the named model is better than M0/M1)
    out["d20"] = out["bic0"] - out["bic2"]
    out["d21"] = out["bic1"] - out["bic2"]
    out["d10"] = out["bic0"] - out["bic1"]
    out["d23"] = out["bic3"] - out["bic2"]      # >0 => settle beats step
    # rho_decay: a settle's increments shrink
    d = np.abs(np.diff(y))
    out["rho_decay"] = float(_spearman(np.arange(d.size, dtype=float), d))
    return out


def _spearman(a, b):
    if a.size < 3:
        return float("nan")
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    den = math.sqrt(float((ra ** 2).sum() * (rb ** 2).sum()))
    return float((ra * rb).sum() / den) if den > 0 else float("nan")


def perm_test(t_min, y, obs_d20, nperm=PERM_N, block=PERM_BLOCK,
              seed=PERM_SEED):
    """Block permutation of the bins, preserving short-range autocorrelation.

    docs/THERMAL_STEP.md 3.1: an F-test lies here because the bins are not
    independent; this is the test.
    """
    n = y.size
    rng = np.random.default_rng(seed)
    nb = int(math.ceil(n / block))
    blocks = [y[i * block:(i + 1) * block] for i in range(nb)]
    hits = 0
    for _ in range(nperm):
        order = rng.permutation(nb)
        ys = np.concatenate([blocks[i] for i in order])[:n]
        rss0 = float(((ys - ys.mean()) ** 2).sum())
        b0 = _bic(rss0, n, 1)
        bestr = None
        for tau in TAU_GRID:
            A2 = np.column_stack([np.ones(n), np.exp(-t_min / tau)])
            c2, *_ = np.linalg.lstsq(A2, ys, rcond=None)
            rss = float(((ys - A2 @ c2) ** 2).sum())
            if bestr is None or rss < bestr:
                bestr = rss
        if (b0 - _bic(bestr, n, 3)) >= obs_d20:
            hits += 1
    return (hits + 1) / (nperm + 1)


def verdict(f, pperm):
    """docs/THERMAL_STEP.md 3.2, applied unchanged."""
    if f is None:
        return "NO DATA"
    if f["d20"] < DBIC_GATE or pperm > 0.01:
        return "NO STRUCTURE"
    if (f["d21"] >= DBIC_GATE and TAU_LO <= f["tau"] <= TAU_HI
            and f["rho_decay"] < 0):
        return "SETTLE"
    return "DRIFT, NOT SETTLE"


# ------------------------------------------------------------- MAC screens
def mac_bytes(m):
    try:
        return [int(x, 16) for x in m.split(":")]
    except ValueError:
        return None


def hamming_octets(a, b):
    return sum(1 for x, y in zip(a, b) if x != y)


def screen_macs(all_macs):
    """docs/THERMAL_STEP.md 6.1 -- the two near-miss screens."""
    crlf_pair, crlf_any, neigh = [], [], []
    bref = {m: mac_bytes(m) for m in BEACONS}
    for m in all_macs:
        mb = mac_bytes(m)
        if mb is None:
            continue
        if "0d:0a" in m:
            crlf_pair.append(m)
        if any(o in (0x0d, 0x0a) for o in mb):
            crlf_any.append(m)
        if m in BEACONS:
            continue
        best = None
        for bm, bb in bref.items():
            d = hamming_octets(mb, bb)
            if best is None or d < best[0]:
                pos = [i for i in range(6) if mb[i] != bb[i]]
                best = (d, BEACONS[bm], bm, pos)
        if best and best[0] <= 4:
            neigh.append((m, best[0], best[1], best[3]))
    return crlf_pair, crlf_any, sorted(neigh, key=lambda r: r[1])


# ------------------------------------------------------------------ report
def bin_cells(st, mac, width_s):
    """Sum 20 s Cells into bins of width_s. Every Cell field is a plain sum,
    which is exactly why add_cells() can do this (exp_iq_imbalance.py:418)."""
    per = int(round(width_s / BIN_S))
    grp = defaultdict(list)
    for (m, b20), c in st.cells.items():
        if m != mac:
            continue
        grp[b20 // per].append(c)
    out = {}
    for b, cs in grp.items():
        out[b] = iq.add_cells(cs)
    return out


def series_kappa(st, mac, width_s, min_frames=2000):
    """(t_min, kappa complex, rssi, n) per bin, bins below the floor dropped."""
    cells = bin_cells(st, mac, width_s)
    ts, ks, ns, rs, nus = [], [], [], [], []
    for b in sorted(cells):
        f = iq.features(cells[b])
        if f is None or f["n"] < min_frames:
            continue
        ts.append((b + 0.5) * width_s / 60.0)
        ks.append(f["kappa"])
        nus.append(f["nu"])
        ns.append(f["n"])
        rs.append(f["rssi"])
    return (np.array(ts), np.array(ks), np.array(rs, dtype=float),
            np.array(ns), np.array(nus))


def series_sfo(st, mac, width_s, min_win=8):
    w = st.win.get(mac, [])
    if not w:
        return np.array([]), np.array([]), np.array([])
    grp = defaultdict(list)
    for tsec, sfo, rssi, q in w:
        grp[int(tsec // width_s)].append((sfo, rssi))
    ts, ys, rs = [], [], []
    for b in sorted(grp):
        v = grp[b]
        if len(v) < min_win:
            continue
        ts.append((b + 0.5) * width_s / 60.0)
        ys.append(float(np.median([x[0] for x in v])))
        rs.append(float(np.mean([x[1] for x in v])))
    return np.array(ts), np.array(ys), np.array(rs)


def excursion(t_min, y, early_s=EARLY_S, late_s=LATE_S):
    """|mean(first 5 min) - mean(last 20 min)| and the full bin range."""
    if t_min.size < 4:
        return float("nan"), float("nan")
    tmax = t_min.max()
    e = y[t_min <= early_s / 60.0]
    l = y[t_min >= tmax - late_s / 60.0]
    if e.size == 0 or l.size == 0:
        return float("nan"), float("nan")
    d = np.mean(e) - np.mean(l)
    return abs(d), float(np.abs(y - y.mean()).max() * 2)


def run_report(args):
    lines = []

    def P(s=""):
        print(s)
        lines.append(s)

    tags = ["s3", "d0wd"]
    sts = {}
    for t in tags:
        p = os.path.join(CACHE, f"{t}_{args.svar}_scan.pkl")
        if not os.path.exists(p):
            print(f"missing scan {p}", file=sys.stderr)
            return
        with open(p, "rb") as f:
            sts[t] = pickle.load(f)

    P("=" * 78)
    P(f"THERMAL_STEP -- results   (s variant={args.svar}, "
      f"convention={args.convention}, bin={PRIMARY_BIN_S:.0f}s)")
    P("=" * 78)

    # ---------------------------------------------------------- 0. scan hygiene
    P("\n--- 0. SCAN, and the corrupt-row screen (COLOCATED_0823 s1) ---")
    P(f"{'tag':<6}{'rows':>12}{'eof':>6}{'corrupt':>9}{'field':>8}"
      f"{'med':>6}{'both':>6}{'med-only':>10}{'badparse':>10}{'span_s':>10}")
    for t in tags:
        s = sts[t]
        span = (s.t_last_us - s.t0_us) * 1e-6 if s.t0_us else 0
        P(f"{t:<6}{s.rows:>12,}{str(s.eof):>6}{s.n_corrupt:>9}"
          f"{s.n_field_bad:>8}{s.n_med_bad:>6}{s.n_both:>6}"
          f"{s.n_medonly:>10}{s.bad_parse:>10}{span:>10.1f}")

    # ------------------------------------------------------ 1. the MAC census
    P("\n--- 1. MAC census, and the near-miss fabrications (s6.1) ---")
    for t in tags:
        s = sts[t]
        allm = set(s.raw_macs)
        clean20 = {m for m, n in s.clean_macs.items() if n >= 20}
        conly = {m for m in allm if m not in s.clean_macs}
        cp, ca, ng = screen_macs(allm)
        P(f"\n  [{t}] distinct MACs any row = {len(allm)} | "
          f"clean & >=20 frames = {len(clean20)} | "
          f"seen only on corrupt rows = {len(conly)}")
        P(f"  [{t}] 0d:0a adjacent-pair screen: {len(cp)}  "
          f"| any octet 0d or 0a: {len(ca)}")
        if cp:
            P(f"        pair-hits: {', '.join(sorted(cp))}")
        byd = defaultdict(list)
        for m, d, nm, pos in ng:
            byd[d].append((m, nm, pos))
        for d in sorted(byd):
            tot = len(byd[d])
            P(f"  [{t}] byte-neighbours of a beacon MAC at d={d}: {tot}")
            for m, nm, pos in sorted(byd[d])[:12]:
                nfr = s.raw_macs.get(m, 0)
                cln = s.clean_macs.get(m, 0)
                cor = s.corrupt_macs.get(m, 0)
                P(f"        {m}  ~{nm} pos={pos}  raw={nfr} clean={cln} "
                  f"corrupt={cor}")
            if tot > 12:
                P(f"        ... and {tot-12} more")
        nm3 = sum(len(byd[d]) for d in byd if d <= 3)
        P(f"  [{t}] REPORTABLE near-miss fabrications (d<=3): {nm3}")

    # ------------------------------------------ 2. channel reversal control
    P("\n--- 2. B2 channel-reversal control (B3_MOVED s9.6) (s4.2) ---")
    P(f"{'rx':<6}{'beacon':<8}{'raw_n':>10}{'clean_n':>10}{'fps_raw':>10}"
      f"{'rssi':>8}{'|B3 present':>12}{'B3 absent':>11}")
    for t in tags:
        s = sts[t]
        span = (s.t_last_us - s.t0_us) * 1e-6
        for mac, nm in BEACONS.items():
            raw = s.raw_macs.get(mac, 0)
            cln = s.clean_macs.get(mac, 0)
            fps = raw / span if span else 0
            rs = [v for (m, b), v in s.rssi_bin.items() if m == mac]
            rssi = (sum(x[0] for x in rs) / max(1, sum(x[1] for x in rs))
                    if rs else float("nan"))
            ref = B2_CHANNEL[t] if nm == "B2" else None
            c1 = (f"{ref['present_rssi']}/{ref['present_fps']:.1f}"
                  if ref else "")
            c2 = (f"{ref['absent_rssi']}/{ref['absent_fps']:.1f}"
                  if ref else "")
            P(f"{t:<6}{nm:<8}{raw:>10,}{cln:>10,}{fps:>10.2f}{rssi:>8.1f}"
              f"{c1:>12}{c2:>11}")

    # ------------------------------------------------- 3. the shape test
    P(f"\n--- 3. SHAPE TEST, {PRIMARY_BIN_S:.0f}s bins (s3.1, s3.2) ---")
    res = {}
    for t in tags:
        s = sts[t]
        for mac, nm in BEACONS.items():
            for feat in ("sfo", "kabs", "karg"):
                if feat == "sfo":
                    tt, yy, rr = series_sfo(s, mac, PRIMARY_BIN_S)
                else:
                    tt, kk, rr, nn, vv = series_kappa(s, mac, PRIMARY_BIN_S)
                    if kk.size == 0:
                        tt, yy = np.array([]), np.array([])
                    elif feat == "kabs":
                        yy = np.abs(kk)
                    else:
                        yy = np.unwrap(np.angle(kk))
                if tt.size < 8:
                    res[(t, nm, feat)] = None
                    continue
                f = fit_models(tt, yy)
                f["pperm"] = (perm_test(tt, yy, f["d20"])
                              if f["d20"] >= 2.0 else 1.0)
                f["verdict"] = verdict(f, f["pperm"])
                f["exc"], f["rng"] = excursion(tt, yy)
                f["t"], f["y"], f["r"] = tt, yy, rr
                res[(t, nm, feat)] = f
    hdr = (f"{'rx':<6}{'unit':<5}{'feature':<7}{'nbin':>5}{'dBIC20':>9}"
           f"{'dBIC21':>9}{'tau_min':>9}{'rho_dec':>9}{'p_perm':>8}"
           f"{'R2shape':>9}  verdict")
    for t in tags:
        P("")
        P(hdr)
        for mac, nm in BEACONS.items():
            for feat in ("sfo", "kabs", "karg"):
                f = res[(t, nm, feat)]
                if f is None:
                    P(f"{t:<6}{nm:<5}{feat:<7}{'--':>5}   (insufficient bins)")
                    continue
                edge = "*" if f["tau_at_edge"] else " "
                mark = " <== TREATED" if nm == "B3" else ""
                P(f"{t:<6}{nm:<5}{feat:<7}{f['n']:>5}{f['d20']:>9.1f}"
                  f"{f['d21']:>9.1f}{f['tau']:>8.2f}{edge}"
                  f"{f['rho_decay']:>9.2f}{f['pperm']:>8.4f}"
                  f"{f['r_shape']:>9.3f}  {f['verdict']}{mark}")
    P("\n  * = tau pinned at a grid edge; read as 'the window is the wrong "
      "length', not as a fitted time constant (s3.2).")

    # --------------------------------------------- 4. the wander bar (s3.4)
    P("\n--- 4. MAGNITUDE against the stationary-wander bar (s3.4) ---")
    P("  SFO: excursion = |mean(first 5 min) - mean(last 20 min)|, rad/sc,")
    P(f"  in BETWEEN_UNIT_SD = {BETWEEN_UNIT_SD}. Bar = B3_MOVED s9.1.")
    P(f"\n{'rx':<6}{'unit':<5}{'exc_rad/sc':>12}{'x_sigma':>9}{'bar':>7}"
      f"{'clears?':>9}{'binrange_x':>12}{'vs THERM_EV':>12}")
    for t in tags:
        for mac, nm in BEACONS.items():
            f = res[(t, nm, "sfo")]
            if f is None:
                continue
            xs = f["exc"] / BETWEEN_UNIT_SD
            bar = WANDER_BAR.get((t, nm), float("nan"))
            rngx = f["rng"] / BETWEEN_UNIT_SD
            clr = "YES" if xs >= bar else "no"
            P(f"{t:<6}{nm:<5}{f['exc']:>12.6f}{xs:>9.2f}{bar:>7.2f}"
              f"{clr:>9}{rngx:>12.2f}{f['exc']/THERMAL_EVIDENCE_MED:>12.2f}x")
    P("\n  last column: excursion / THERMAL_EVIDENCE s3's median opening")
    P(f"  drift of {THERMAL_EVIDENCE_MED} rad/sc (0.26x between-unit spread).")

    # -------- 4b. this file's OWN contemporaneous wander null (s3.4)
    # B3_MOVED s9.1's bar is a range of block medians over 3111 s blocks of a
    # 6.70 h file. This file is 70 min, so only one such block fits. The same
    # STATISTIC is therefore recomputed here on blocks scaled to this file --
    # 6 non-overlapping blocks of 703 s -- so the treated unit is compared to
    # its own untouched neighbours measured the same way, in the same minutes.
    NB = 6
    blk = 4217.45 / NB
    P(f"\n  [4b] same statistic on THIS file: range of block medians over "
      f"{NB} x {blk:.0f}s blocks")
    P(f"  {'rx':<6}{'unit':<5}{'feature':<7}{'range':>11}{'x_sigma_or_Sbd':>16}")
    for t in tags:
        s = sts[t]
        kv = []
        for mac in BEACONS:
            cl = bin_cells(s, mac, 1e9)
            if cl:
                fk = iq.features(list(cl.values())[0])
                if fk:
                    kv.append(fk["kappa"])
        kv = np.array(kv)
        S_kap = (float(np.sqrt((np.abs(kv - kv.mean()) ** 2).mean()))
                 if kv.size > 1 else float("nan"))
        for mac, nm in BEACONS.items():
            tt, yy, _ = series_sfo(s, mac, blk, min_win=8)
            if yy.size >= 4:
                rg = float(yy.max() - yy.min())
                P(f"  {t:<6}{nm:<5}{'sfo':<7}{rg:>11.6f}"
                  f"{rg/BETWEEN_UNIT_SD:>15.2f}s")
            tt, kk, _, _, _ = series_kappa(s, mac, blk, min_frames=2000)
            if kk.size >= 4:
                d = np.abs(kk[:, None] - kk[None, :])
                rg = float(d.max())
                P(f"  {t:<6}{nm:<5}{'kappa':<7}{rg:>11.6f}"
                  f"{rg/S_kap if S_kap>0 else np.nan:>15.2f}S")

    # ------------------------------------- 5. head-to-head, own-spread units
    P("\n--- 5. HEAD-TO-HEAD: kappa vs slope in own-spread units (s3.5) ---")
    for t in tags:
        s = sts[t]
        wholes, wholek = {}, {}
        for mac, nm in BEACONS.items():
            tt, yy, _ = series_sfo(s, mac, PRIMARY_BIN_S)
            if yy.size:
                wholes[nm] = float(np.median(yy))
            cells = bin_cells(s, mac, 1e9)
            if cells:
                fk = iq.features(list(cells.values())[0])
                if fk:
                    wholek[nm] = fk["kappa"]
        if len(wholes) < 2 or len(wholek) < 2:
            continue
        sv = np.array(list(wholes.values()))
        S_sfo = float(sv.std(ddof=1))
        kv = np.array(list(wholek.values()))
        S_kap = float(np.sqrt((np.abs(kv - kv.mean()) ** 2).mean()))
        P(f"\n  [{t}] between-device spread on THIS file: "
          f"S_bd(sfo) = {S_sfo:.6f} rad/sc | S_bd(kappa) = {S_kap:.6f}")
        P(f"  {'unit':<5}{'sfo_exc/S':>11}{'kap_exc/S':>11}{'ratio k/s':>11}"
          f"   (>1 => kappa moved MORE)")
        for mac, nm in BEACONS.items():
            fs = res[(t, nm, "sfo")]
            tt, kk, rr, nn, vv = series_kappa(s, mac, PRIMARY_BIN_S)
            if fs is None or kk.size < 8:
                continue
            tmax = tt.max()
            e = kk[tt <= EARLY_S / 60.0]
            l = kk[tt >= tmax - LATE_S / 60.0]
            kexc = abs(e.mean() - l.mean()) if e.size and l.size else np.nan
            a = fs["exc"] / S_sfo if S_sfo > 0 else np.nan
            b = kexc / S_kap if S_kap > 0 else np.nan
            P(f"  {nm:<5}{a:>11.3f}{b:>11.3f}{b/a if a else np.nan:>11.3f}")

    # -------------------------------------------- 6. kappa's own controls
    P("\n--- 6. kappa's controls: nu, and the RSSI dilution hazard (s2.2, s7.8) ---")
    P(f"{'rx':<6}{'unit':<5}{'|kappa|':>9}{'|nu|':>9}{'k/nu':>7}"
      f"{'arg k':>8}{'exc|k|':>9}{'exc|nu|':>9}{'r(|k|,rssi)':>12}"
      f"{'d_rssi':>8}")
    for t in tags:
        s = sts[t]
        for mac, nm in BEACONS.items():
            tt, kk, rr, nn, vv = series_kappa(s, mac, PRIMARY_BIN_S)
            if kk.size < 8:
                continue
            cells = bin_cells(s, mac, 1e9)
            fk = iq.features(list(cells.values())[0])
            ek, _ = excursion(tt, np.abs(kk))
            ev, _ = excursion(tt, np.abs(vv))
            ak = np.abs(kk)
            cr = (float(np.corrcoef(ak, rr)[0, 1])
                  if np.std(rr) > 0 else float("nan"))
            drs, _ = excursion(tt, rr)
            P(f"{t:<6}{nm:<5}{abs(fk['kappa']):>9.5f}{abs(fk['nu']):>9.5f}"
              f"{abs(fk['kappa'])/max(abs(fk['nu']),1e-12):>7.2f}"
              f"{np.angle(fk['kappa']):>8.3f}{ek:>9.5f}{ev:>9.5f}"
              f"{cr:>12.2f}{drs:>8.2f}")
    P("\n  If exc|kappa| ~ exc|nu| the statistic is reading the channel, not")
    P("  the silicon (IQ_IMBALANCE s1.6). d_rssi is the same 5min-vs-20min")
    P("  excursion in dB: |kappa| is diluted by noise (IQ_IMBALANCE s18).")

    # --------------------------------------- 7. reboot vs settle (s5)
    P("\n--- 7. REBOOT vs SETTLE discriminator (s5) ---")
    P(f"{'rx':<6}{'unit':<5}{'feature':<7}{'dBIC(M2-M3)':>13}{'step_t_min':>11}"
      f"{'step_size':>11}{'reading':>26}")
    for t in tags:
        for mac, nm in BEACONS.items():
            for feat in ("sfo", "kabs", "karg"):
                f = res[(t, nm, feat)]
                if f is None:
                    continue
                d = f["d23"]
                if d >= DBIC_GATE:
                    rd = "settle beats step"
                elif d <= -DBIC_GATE:
                    rd = "STEP beats settle"
                else:
                    rd = "NOT SEPARABLE"
                P(f"{t:<6}{nm:<5}{feat:<7}{d:>13.1f}{f['step_t']:>11.2f}"
                  f"{f['step_d']:>11.5f}{rd:>26}")

    # --------------------------- 8. arg(kappa) jumps at 20 s resolution
    P("\n--- 8. arg(kappa) at 20 s resolution: is any jump 1-bin or 3-bin? ---")
    P(f"{'rx':<6}{'unit':<5}{'nbin':>5}{'max|d arg| deg':>15}{'at_min':>8}"
      f"{'spread_bins':>12}{'shape':>14}")
    for t in tags:
        s = sts[t]
        for mac, nm in BEACONS.items():
            tt, kk, rr, nn, vv = series_kappa(s, mac, BIN_S, min_frames=600)
            if kk.size < 8:
                continue
            ph = np.unwrap(np.angle(kk))
            dph = np.diff(ph)
            i = int(np.argmax(np.abs(dph)))
            mx = math.degrees(abs(dph[i]))
            thr = 0.5 * abs(dph[i])
            spread = int((np.abs(dph) >= thr).sum())
            shape = "step-like" if spread <= 1 else ("settle-like"
                                                     if spread >= 3 else "amb")
            P(f"{t:<6}{nm:<5}{kk.size:>5}{mx:>15.1f}{tt[i]:>8.2f}"
              f"{spread:>12}{shape:>14}")
    P("\n  A common rotation of EVERY beacon at one receiver is receiver-side")
    P("  (IQ_IMBALANCE s15.1's unexplained ~155 deg signature) and is NOT")
    P("  attributable to B3's power cycle. B3-only is transmitter-side.")

    # --------------------------------------------- 9. the per-bin series
    P("\n--- 9. PER-BIN SERIES (first 12 and last 4 bins) ---")
    for t in tags:
        for mac, nm in BEACONS.items():
            for feat in ("sfo", "kabs"):
                f = res[(t, nm, feat)]
                if f is None:
                    continue
                y = f["y"]
                head = " ".join(f"{v:+.5f}" for v in y[:12])
                tail = " ".join(f"{v:+.5f}" for v in y[-4:])
                P(f"  [{t}] {nm} {feat}: {head} ... {tail}")

    with open(os.path.join(CACHE, f"report_{args.svar}.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--tag", required=True)
    s.add_argument("--path", required=True)
    s.add_argument("--resume", action="store_true")
    s.add_argument("--seconds", type=float, default=0)
    s.add_argument("--max-rows", type=int, default=0)
    s.add_argument("--convention", default="divided",
                   choices=("divided", "raw"))
    s.add_argument("--svar", default="strue", choices=("strue", "s1"))
    r = sub.add_parser("report")
    r.add_argument("--svar", default="strue")
    r.add_argument("--convention", default="divided")
    r.add_argument("--bin", type=float, default=PRIMARY_BIN_S)
    a = ap.parse_args()
    if a.cmd == "report" and a.bin != PRIMARY_BIN_S:
        globals()["PRIMARY_BIN_S"] = a.bin
    if a.cmd == "scan":
        run_scan(a)
    else:
        run_report(a)


if __name__ == "__main__":
    main()
