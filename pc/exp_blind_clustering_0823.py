#!/usr/bin/env python3
r"""Blind clustering of the fingerprint space -- no MAC in the features or
the grouping. 2026-08-23 co-located overnight capture.

Design, success criteria and failure criteria are pre-registered in
docs/BLIND_CLUSTERING.md Part I, written before this script was run.

Every analysis in this repo groups by MAC first. Modern devices randomise
their addresses, so one device becomes many short-lived MACs, each fragment
falls under the 20-frame floor and gets discarded. This script asks whether
the fingerprint space can group transmitters with the labels withheld --
starting with the free positive control: three beacons with fixed MACs that
transmit constantly. If blind clustering cannot recover those three, the
feature space is too thin and nothing downstream matters.

Read-only with respect to data/raw/: every input is opened "rb" and never
written. No serial port is opened (a capture is running on COM6/COM12).
Nothing is staged or committed.

Constraints obeyed (docs/BLIND_CLUSTERING.md Part I ss2-ss4, ss8):
  * pc/rff/dsp.py used exactly as shipped, not modified. FrameEstimator
    output only. pc/capture.py:compute_cfo, pc/phase_skew.py and
    pc/fingerprint.py are NOT used (docs/CODE_INVENTORY.md ss4.2 C1/C2/C3).
  * Replay from the start of each file with a fresh estimator per
    (node, source-MAC): FrameEstimator owns a per-instance RNG
    (dsp.py:118) that advances every fitted frame (dsp.py:85-86,132).
    The part/merge split pickles estimator state forward.
  * Corrupt rows screened FIRST, by both independent routes -- field
    plausibility on six columns and a width-9 circular median filter on
    `dropped` (docs/OVERNIGHT_2026-08-22.md ss1; neither alone suffices,
    docs/COLOCATED_0823.md ss3.3).
  * csi_data parsed with csv.reader, never a naive split of the line.
  * RSSI is NOT a feature. It encodes distance and position
    (docs/BLIND_CLUSTERING.md ss3.2). Carried for reporting only.
  * scipy/sklearn are not installed on this host and nothing in the repo
    imports them; k-means, agglomerative linkage, ARI and silhouette are
    implemented here in plain numpy.

Usage (from the repo root; state goes to $BLIND_CACHE, default /tmp/blind)
--------------------------------------------------------------------------
  D=data/raw/d0wd_20260823_014740.csv
  S=data/raw/s3_20260823_014740.csv
  for p in 0 1 2 3 4 5 6; do
    python3 pc/exp_blind_clustering_0823.py replay $D --tag d0wd \
        --part $p --nparts 7 --total-rows 3344351
  done
  python3 pc/exp_blind_clustering_0823.py merge --tag d0wd --nparts 7 \
      --expect-rows 3344351
  ... same for s3 with --nparts 9 --total-rows 4330849 ...
  python3 pc/exp_blind_clustering_0823.py analyze --tags d0wd,s3
"""
import argparse
import csv
import math
import os
import pickle
import sys
import time
import warnings
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rff.dsp import FrameEstimator                     # noqa: E402

warnings.filterwarnings("ignore", category=DeprecationWarning)

CACHE = os.environ.get("BLIND_CACHE", "/tmp/blind")

# ---- the three beacons, fixed factory MACs, the positive control ----------
# Values mirror pc/occ/__init__.py:19-23; restated rather than imported so
# that importing pc/occ does not write a .pyc this session cannot delete
# (docs/BLIND_CLUSTERING.md ss7, ss8).
B1 = "a4:f0:0f:77:91:20"     # reference beacon
B2 = "28:05:a5:2f:fa:48"
B3 = "f4:2d:c9:70:72:30"
BEACONS = {B1: "B1", B2: "B2", B3: "B3"}

# ---- the project's yardstick --------------------------------------------
# sd over the 3 units of their grand means (pc/exp_thermal_evidence.py:129,
# from docs/LOT_HYPOTHESIS.md ss5).
BETWEEN_UNIT_SD = 0.00237

# ---- gates, frozen in docs/BLIND_CLUSTERING.md ss4 -----------------------
MIN_INLIER = 0.3      # not the shipped 0.6: at 0.6 the gate, not sparsity,
                      # destroys ambient sources (AMBIENT_SEPARATION ss3.1)
MAX_RESID = 0.8       # shipped, and inoperative on this data (max 0.2233)
WINDOWS = (64, 16)    # W=64 shipped/headline, W=16 relaxed

# ---- field-plausibility screen, docs/OVERNIGHT_2026-08-22.md ss1 ---------
CSI_LEN_OK = (128, 256, 384)
NF_LO, NF_HI = -110, -70
RSSI_LO, RSSI_HI = -100, -10
MED_W = 9
MED_TOL = 100
U16 = 65536

# ---- 2*pi/dk mis-unwrap ladder, docs/AMBIENT_SEPARATION.md ss5 -----------
UNWRAP_LADDER = {52: 2 * math.pi / 52, 40: 2 * math.pi / 40,
                 32: 2 * math.pi / 32, 26: 2 * math.pi / 26}

SEED = 20260823

FRAME_DTYPE = np.dtype([
    ("mac", np.int32), ("ts", np.int64), ("slope", np.float32),
    ("intercept", np.float32), ("cfo", np.float32), ("inlier", np.float32),
    ("resid", np.float32), ("rssi", np.int16),
])


def is_locally_administered(mac):
    """The LAA bit. Byte-equivalent to pc/mac_census.py:32-37, restated
    inline rather than imported: importing that module writes
    pc/__pycache__/mac_census.cpython-310.pyc and this session cannot
    delete files it creates under the repo (rm -> Operation not
    permitted). Checked against the source in `analyze`."""
    try:
        first_octet = int(mac.split(":")[0], 16)
    except (ValueError, IndexError):
        return None
    return bool(first_octet & 0x02)


# =========================================================== replay state

class MacStat:
    """Per-source counters. `raw_n` counts every row bearing this MAC,
    corrupt or not; the rest are over rows surviving BOTH screens."""

    __slots__ = ("raw_n", "clean_n", "fitted", "nofit", "est", "idx",
                 "len_hist")

    def __init__(self, idx):
        self.raw_n = 0
        self.clean_n = 0
        self.fitted = 0
        self.nofit = 0
        self.est = None
        self.idx = idx
        self.len_hist = defaultdict(int)


class State:
    def __init__(self, tag, path):
        self.tag = tag
        self.path = path
        self.rows = 0
        self.byte_pos = 0
        self.bad_parse = 0
        self.node_mode = None
        self.chan_mode = None
        self.node_hist = defaultdict(int)
        self.chan_hist = defaultdict(int)
        self.macs = {}
        self.mac_list = []
        self.t0_us = None
        self.t_last_us = None
        self.n_field_bad = 0
        self.n_med_bad = 0
        self.n_both = 0
        self.n_corrupt = 0
        self.corrupt_macs = defaultdict(int)
        self.pend = []
        self.n_hist = 0
        self.seams = []
        self.monotone_ok = True

    def mac_stat(self, mac):
        st = self.macs.get(mac)
        if st is None:
            st = self.macs[mac] = MacStat(len(self.mac_list))
            self.mac_list.append(mac)
        return st


def spath(tag, part=None):
    if part is None:
        return os.path.join(CACHE, f"{tag}_state.pkl")
    return os.path.join(CACHE, f"{tag}_part{part}.pkl")


def fpath(tag, part=None):
    if part is None:
        return os.path.join(CACHE, f"{tag}_frames.npy")
    return os.path.join(CACHE, f"{tag}_frames{part}.npy")


class Lines:
    """Byte-exact line source, opened "rb" -- the file is never written.
    Tracks the absolute offset after the last line handed out so the next
    part resumes at exactly the right byte."""

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
    """Width-9 median filter compared circularly mod 65536, so a genuine
    u16 wrap is not a false positive."""
    c = vals[ci]
    offs = sorted(circ(v, c) for v in vals)
    m = offs[len(offs) // 2]
    return abs(m) > MED_TOL


# =============================================================== replay

class Sink:
    """Accumulates per-frame estimator output for one part."""

    def __init__(self):
        self.mac, self.ts, self.slope, self.icept = [], [], [], []
        self.cfo, self.inl, self.res, self.rssi = [], [], [], []

    def add(self, mi, ts, e, rssi):
        self.mac.append(mi)
        self.ts.append(ts)
        self.slope.append(e["slope"])
        self.icept.append(e["intercept"])
        self.cfo.append(np.nan if e["cfo_hz"] is None else e["cfo_hz"])
        self.inl.append(e["inlier_ratio"])
        self.res.append(e["resid_std"])
        self.rssi.append(rssi)

    def to_array(self):
        n = len(self.mac)
        a = np.empty(n, dtype=FRAME_DTYPE)
        a["mac"] = self.mac
        a["ts"] = self.ts
        a["slope"] = self.slope
        a["intercept"] = self.icept
        a["cfo"] = self.cfo
        a["inlier"] = self.inl
        a["resid"] = self.res
        a["rssi"] = self.rssi
        return a


def run_replay(args):
    os.makedirs(CACHE, exist_ok=True)
    csv.field_size_limit(10 ** 7)

    if args.part == 0:
        st = State(args.tag, args.path)
        # prescan for the screen's modes, then re-checked whole-file at merge
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
        st.seams.append((args.part, st.rows, st.byte_pos, st.t_last_us))

    per = math.ceil(args.total_rows / args.nparts)
    stop_at = min(args.total_rows, per * (args.part + 1))

    sink = Sink()
    L = Lines(args.path, st.byte_pos)
    r = csv.reader(iter(L))
    t0 = time.time()
    processed = 0
    hit_limit = False

    for row in r:
        st.rows += 1
        processed += 1
        bad = len(row) != 13
        if not bad:
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
                bad = True
        if bad:
            st.bad_parse += 1
            _flush(st, sink, force=False)
            if st.rows >= stop_at:
                hit_limit = True
                break
            continue

        st.node_hist[node] += 1
        st.chan_hist[chan] += 1
        if st.t0_us is None:
            st.t0_us = pc_us
        if st.t_last_us is not None and pc_us < st.t_last_us:
            st.monotone_ok = False
        st.t_last_us = pc_us

        fbad = not field_ok(node, env, chan, ln, nf, rssi,
                            st.node_mode, st.chan_mode)
        st.mac_stat(mac).raw_n += 1
        st.pend.append((pc_us, mac, rssi, esp_us, ln, drop, row[9], fbad))
        _flush(st, sink, force=False)

        if st.rows >= stop_at:
            hit_limit = True
            break

    at_eof = (not hit_limit) or st.rows >= args.total_rows
    if at_eof:
        _flush(st, sink, force=True)
    L.close()
    st.byte_pos = L.pos

    arr = sink.to_array()
    np.save(fpath(args.tag, args.part), arr)
    with open(spath(args.tag, args.part), "wb") as f:
        pickle.dump(st, f, protocol=4)
    print(f"[{args.tag} replay {args.part}/{args.nparts}] rows={st.rows:,} "
          f"(+{processed:,}) frames+={len(arr):,} corrupt={st.n_corrupt} "
          f"byte_pos={st.byte_pos:,} {time.time()-t0:.1f}s", file=sys.stderr)


def _flush(st, sink, force):
    """Emit rows in strict file order, each judged by the width-9 filter
    once its 4 look-ahead rows have arrived. `force` drains the tail at
    EOF on the shorter window it has, which is all a filter can do at a
    boundary. Emission order is always the file's order."""
    half = MED_W // 2
    while st.n_hist < len(st.pend):
        ci = st.n_hist
        if not force and (len(st.pend) - 1 - ci) < half:
            return
        lo = max(0, ci - half)
        hi = min(len(st.pend), ci + half + 1)
        vals = [st.pend[k][5] for k in range(lo, hi)]
        mbad = med_flag(vals, ci - lo) if len(vals) >= 3 else False
        _emit(st, sink, st.pend[ci], mbad)
        st.n_hist += 1
        while st.n_hist > half:
            del st.pend[0]
            st.n_hist -= 1


def _emit(st, sink, rec, mbad):
    pc_us, mac, rssi, esp_us, ln, drop, csi_s, fbad = rec

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

    m = st.mac_stat(mac)
    m.clean_n += 1
    m.len_hist[ln] += 1
    if m.est is None:
        m.est = FrameEstimator()
    vals = np.fromstring(csi_s, dtype=np.float64, sep=",")
    e = m.est.feed(vals, esp_us)
    if e is None:
        m.nofit += 1
        return
    m.fitted += 1
    sink.add(m.idx, pc_us, e, rssi)


# ================================================================ merge

def run_merge(args):
    with open(spath(args.tag, args.nparts - 1), "rb") as f:
        st = pickle.load(f)
    ok_rows = st.rows == args.expect_rows
    node_mode_full = max(st.node_hist.items(), key=lambda kv: kv[1])[0]
    chan_mode_full = max(st.chan_hist.items(), key=lambda kv: kv[1])[0]
    parts = [np.load(fpath(args.tag, p)) for p in range(args.nparts)]
    arr = np.concatenate(parts)
    np.save(fpath(args.tag), arr)
    meta = {
        "tag": args.tag, "rows": st.rows, "bad_parse": st.bad_parse,
        "node_mode": st.node_mode, "chan_mode": st.chan_mode,
        "node_mode_full": node_mode_full, "chan_mode_full": chan_mode_full,
        "n_corrupt": st.n_corrupt, "n_field_bad": st.n_field_bad,
        "n_med_bad": st.n_med_bad, "n_both": st.n_both,
        "corrupt_macs": dict(st.corrupt_macs),
        "mac_list": st.mac_list,
        "mac_raw": {m: s.raw_n for m, s in st.macs.items()},
        "mac_clean": {m: s.clean_n for m, s in st.macs.items()},
        "mac_fitted": {m: s.fitted for m, s in st.macs.items()},
        "mac_nofit": {m: s.nofit for m, s in st.macs.items()},
        "t0_us": st.t0_us, "t_last_us": st.t_last_us,
        "seams": st.seams, "monotone_ok": st.monotone_ok,
        "byte_pos": st.byte_pos,
    }
    with open(os.path.join(CACHE, f"{args.tag}_meta.pkl"), "wb") as f:
        pickle.dump(meta, f, protocol=4)
    fsz = os.path.getsize(st.path)
    print(f"[{args.tag} merge] rows={st.rows:,} expect={args.expect_rows:,} "
          f"{'OK' if ok_rows else 'MISMATCH'}  frames={len(arr):,}")
    print(f"  byte_pos={st.byte_pos:,} filesize={fsz:,} "
          f"{'OK' if st.byte_pos == fsz else 'MISMATCH'}")
    print(f"  pc_time_us monotone across all seams: "
          f"{'OK' if st.monotone_ok else 'VIOLATED'}  seams={len(st.seams)}")
    print(f"  screen mode node={st.node_mode} chan={st.chan_mode}  "
          f"whole-file node={node_mode_full} chan={chan_mode_full}  "
          f"{'AGREE' if (st.node_mode == node_mode_full and st.chan_mode == chan_mode_full) else 'DISAGREE'}")
    print(f"  corrupt={st.n_corrupt} (field {st.n_field_bad}, median "
          f"{st.n_med_bad}, both {st.n_both})  bad_parse={st.bad_parse}")
    print(f"  distinct MACs any row={len(st.macs)}  "
          f">=20 clean frames={sum(1 for s in st.macs.values() if s.clean_n >= 20)}")


# ====================================================== numpy clustering

def robust_standardize(X):
    """median/MAD per column -- not mean/sd: the 1c:ce-style mis-unwrap
    outliers (docs/AMBIENT_SEPARATION.md ss5) would otherwise set the
    scale."""
    med = np.median(X, axis=0)
    mad = np.median(np.abs(X - med), axis=0) * 1.4826
    mad = np.where(mad <= 0, 1.0, mad)
    return (X - med) / mad, med, mad


def kmeans(X, k, seed=SEED, restarts=None, iters=100):
    # 50 restarts as pre-registered; thinned to 12 above 50,000 points so
    # one shell call stays inside the host's ~178 s cap. Disclosed in
    # docs/BLIND_CLUSTERING.md Part II.
    if restarts is None:
        restarts = 50 if len(X) <= 50_000 else 12
    rng = np.random.default_rng(seed)
    best, best_lab, best_c = np.inf, None, None
    for _ in range(restarts):
        # k-means++ init
        idx = [int(rng.integers(len(X)))]
        d2 = ((X - X[idx[0]]) ** 2).sum(1)
        for _ in range(k - 1):
            tot = d2.sum()
            if tot <= 0:
                idx.append(int(rng.integers(len(X))))
            else:
                idx.append(int(rng.choice(len(X), p=d2 / tot)))
            d2 = np.minimum(d2, ((X - X[idx[-1]]) ** 2).sum(1))
        C = X[idx].copy()
        lab = None
        for _ in range(iters):
            D = ((X[:, None, :] - C[None, :, :]) ** 2).sum(2) \
                if len(X) * k < 4_000_000 else _cdist2(X, C)
            new = D.argmin(1)
            if lab is not None and np.array_equal(new, lab):
                break
            lab = new
            for j in range(k):
                m = lab == j
                if m.any():
                    C[j] = X[m].mean(0)
        inertia = float(_cdist2(X, C)[np.arange(len(X)), lab].sum())
        if inertia < best:
            best, best_lab, best_c = inertia, lab.copy(), C.copy()
    return best_lab, best_c, best


def _cdist2(X, C):
    return ((X ** 2).sum(1)[:, None] - 2 * X @ C.T + (C ** 2).sum(1)[None, :])


def adjusted_rand(a, b):
    """Adjusted Rand index by the standard pair-counting formula."""
    a = np.asarray(a)
    b = np.asarray(b)
    ua, ia = np.unique(a, return_inverse=True)
    ub, ib = np.unique(b, return_inverse=True)
    n = len(a)
    cont = np.zeros((len(ua), len(ub)), dtype=np.int64)
    np.add.at(cont, (ia, ib), 1)

    def c2(x):
        return x * (x - 1) // 2
    # Python ints throughout: with >10^5 windows si*sj exceeds int64.
    sij = int(c2(cont).sum())
    si = int(c2(cont.sum(1)).sum())
    sj = int(c2(cont.sum(0)).sum())
    tot = int(c2(np.int64(n)))
    exp = si * sj / tot if tot else 0.0
    mx = (si + sj) / 2.0
    return float((sij - exp) / (mx - exp)) if mx != exp else 1.0


def silhouette(X, lab, seed=SEED, cap=3000):
    """Mean silhouette on a fixed-seed subsample -- it is O(n^2) and the
    beacon runs have >10^5 windows."""
    rng = np.random.default_rng(seed)
    if len(X) > cap:
        sel = rng.choice(len(X), cap, replace=False)
        X, lab = X[sel], lab[sel]
    u = np.unique(lab)
    if len(u) < 2:
        return float("nan")
    D = np.sqrt(np.maximum(_cdist2(X, X), 0))
    n = len(X)
    k = len(u)
    pos = {c: i for i, c in enumerate(u)}
    li = np.array([pos[c] for c in lab])
    # S[i, c] = sum of distances from i to every member of cluster c
    S = np.zeros((n, k))
    for c in range(k):
        S[:, c] = D[:, li == c].sum(1)
    cnt = np.bincount(li, minlength=k).astype(np.float64)
    own = S[np.arange(n), li]
    a = np.where(cnt[li] > 1, own / np.maximum(cnt[li] - 1, 1), 0.0)
    other = S / np.maximum(cnt, 1)[None, :]
    other[np.arange(n), li] = np.inf
    b = other.min(1)
    mx = np.maximum(a, b)
    s = np.where((cnt[li] > 1) & (mx > 0), (b - a) / np.where(mx > 0, mx, 1),
                 0.0)
    return float(s.mean())


def grid_cells(X, target=1800):
    """Label-blind pre-aggregation of the window cloud onto a grid, so that
    average-linkage (O(m^2) memory, O(m^2) time) is tractable on >10^5
    windows. Rare points keep their own cell exactly; only points already
    within one cell width of each other are merged, and the cell width is
    coarsened until the occupied-cell count fits. Disclosed in
    docs/BLIND_CLUSTERING.md Part II as a deviation forced by n."""
    w = 0.02
    for _ in range(40):
        key = np.floor(X / w).astype(np.int64)
        _, inv, cnt = np.unique(key, axis=0, return_inverse=True,
                                return_counts=True)
        if len(cnt) <= target:
            break
        w *= 1.6
    m = len(cnt)
    cent = np.zeros((m, X.shape[1]))
    np.add.at(cent, inv, X)
    cent /= cnt[:, None]
    return inv, cent, cnt.astype(np.float64), w


def average_linkage(C, wts):
    """UPGMA average linkage via Lance-Williams, with a cached row-minimum
    so each merge is amortised O(m). Returns the merge sequence
    (i, j, height) and lets the caller cut at any threshold."""
    m = len(C)
    D = np.sqrt(np.maximum(_cdist2(C, C), 0)).astype(np.float64)
    np.fill_diagonal(D, np.inf)
    active = np.ones(m, bool)
    n = wts.copy()
    parent = list(range(m))
    rmin = D.min(1)
    rarg = D.argmin(1)
    merges = []
    for _ in range(m - 1):
        cand = np.where(active, rmin, np.inf)
        i = int(cand.argmin())
        if not np.isfinite(cand[i]):
            break
        j = int(rarg[i])
        if i > j:
            i, j = j, i
        h = float(D[i, j])
        merges.append((i, j, h))
        # Lance-Williams UPGMA update into i
        ni, nj = n[i], n[j]
        newrow = (ni * D[i] + nj * D[j]) / (ni + nj)
        newrow[i] = newrow[j] = np.inf
        D[i, :] = newrow
        D[:, i] = newrow
        D[j, :] = np.inf
        D[:, j] = np.inf
        n[i] = ni + nj
        active[j] = False
        parent[j] = i
        rmin[i] = D[i].min()
        rarg[i] = D[i].argmin()
        stale = np.where(active & ((rarg == i) | (rarg == j)))[0]
        for s in stale:
            rmin[s] = D[s].min()
            rarg[s] = D[s].argmin()
    return merges


def cut(merges, m, thresh):
    """Cluster labels for the m leaves at a linkage height threshold."""
    par = list(range(m))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for i, j, h in merges:
        if h > thresh:
            break
        ri, rj = find(i), find(j)
        if ri != rj:
            par[rj] = ri
    roots = [find(x) for x in range(m)]
    u = {r: k for k, r in enumerate(sorted(set(roots)))}
    return np.array([u[r] for r in roots], dtype=np.int32)


# ================================================================ windows

def build_windows(fr, W):
    """Non-overlapping windows of W accepted frames, in file order, per
    (receiver, MAC) stream -- the same construction WindowAggregator uses
    (dsp.py:156), reimplemented only so one replay can be re-windowed at
    two lengths."""
    keep = (fr["inlier"] >= MIN_INLIER) & (fr["resid"] <= MAX_RESID)
    g = fr[keep]
    out = defaultdict(list)
    order = np.argsort(g["mac"], kind="stable")
    g = g[order]
    macs = g["mac"]
    bounds = np.searchsorted(macs, np.unique(macs), side="left").tolist()
    bounds.append(len(g))
    blocks = []
    for b in range(len(bounds) - 1):
        seg = g[bounds[b]:bounds[b + 1]]
        mi = int(seg["mac"][0])
        nwin = len(seg) // W
        out[mi] = nwin
        if nwin == 0:
            continue
        blocks.append((mi, seg[:nwin * W]))
    if not blocks:
        return None
    parts = {k: [] for k in ("mac", "sfo", "iqr", "resid", "inlier", "cfo",
                             "ts", "rssi", "cfo_frac")}
    for mi, seg in blocks:
        n = len(seg) // W
        agg = _win_agg(seg, n, W)
        parts["mac"].append(np.full(n, mi, dtype=np.int32))
        for k, v in agg.items():
            parts[k].append(v)
    res = {k: np.concatenate(v) for k, v in parts.items()}
    res["mac"] = res["mac"].astype(np.int32)
    res["gated"] = g
    return res


def _win_agg(seg, n, W):
    """Vectorised window aggregation: reshape (n*W,) -> (n, W) and reduce
    along the window axis. Identical to reducing each window separately;
    the reshape only removes a Python loop."""
    sl = seg["slope"][:n * W].astype(np.float64).reshape(n, W)
    cf = seg["cfo"][:n * W].astype(np.float64).reshape(n, W)
    fin = np.isfinite(cf)
    cfm = np.where(fin, cf, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        cfo = np.nanmedian(cfm, axis=1)
    q = np.percentile(sl, [75, 25], axis=1)
    return {
        "sfo": np.median(sl, axis=1),
        "iqr": q[0] - q[1],
        "resid": np.median(seg["resid"][:n * W].astype(np.float64)
                           .reshape(n, W), axis=1),
        "inlier": np.median(seg["inlier"][:n * W].astype(np.float64)
                            .reshape(n, W), axis=1),
        "cfo": cfo,
        "ts": np.median(seg["ts"][:n * W].astype(np.float64).reshape(n, W),
                        axis=1),
        "rssi": seg["rssi"][:n * W].astype(np.float64).reshape(n, W).mean(1),
        "cfo_frac": fin.sum(1) / float(W),
    }


def featmat(w, setname):
    if setname == "A":
        return np.column_stack([w["sfo"], w["iqr"]])
    c = np.where(np.isfinite(w["cfo"]), w["cfo"], 0.0)
    return np.column_stack([w["sfo"], w["iqr"], w["resid"], w["inlier"], c])


def shuffle_frames(g, sizes, seed=SEED):
    """Negative control: permute the assignment of frames to windows,
    preserving window count and every window size exactly."""
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(g))
    gs = g[perm]
    W = sizes[0]                      # every window is the same length here
    n = min(len(sizes), len(gs) // W)
    return _win_agg(gs[:n * W], n, W)


# =============================================================== analyze

def hl(t):
    print("\n" + "=" * 74)
    print(t)
    print("=" * 74)


def load(tag):
    with open(os.path.join(CACHE, f"{tag}_meta.pkl"), "rb") as f:
        meta = pickle.load(f)
    fr = np.load(fpath(tag))
    return meta, fr


def run_analyze(args):
    tags = args.tags.split(",")
    data = {t: load(t) for t in tags}

    hl("0. INPUT, SCREENS, AND THE CHECKS THAT MUST PASS "
       "(docs/BLIND_CLUSTERING.md ss8)")
    for t in tags:
        meta, fr = data[t]
        macs = meta["mac_list"]
        n20 = sum(1 for m in macs if meta["mac_clean"].get(m, 0) >= 20)
        print(f"\n[{t}] rows={meta['rows']:,}  bad_parse={meta['bad_parse']}  "
              f"fitted frames={len(fr):,}")
        print(f"  corrupt rows={meta['n_corrupt']} "
              f"(field {meta['n_field_bad']}, median {meta['n_med_bad']}, "
              f"both {meta['n_both']})")
        print(f"  distinct MACs any row={len(macs)}   "
              f">=20 clean frames={n20}")
        only_corrupt = sum(1 for m in macs
                           if meta["mac_clean"].get(m, 0) == 0)
        print(f"  MACs seen ONLY on corrupt rows={only_corrupt}   "
              f"clean but <20 frames="
              f"{len(macs) - n20 - only_corrupt}")
        print(f"  screen modes node={meta['node_mode']}/"
              f"{meta['node_mode_full']} chan={meta['chan_mode']}/"
              f"{meta['chan_mode_full']}  "
              f"monotone={meta['monotone_ok']}")
        span = (meta["t_last_us"] - meta["t0_us"]) * 1e-6
        print(f"  span={span:.3f} s = {span/3600:.4f} h")

    # LAA cross-check against pc/mac_census.py's own implementation
    hl("0.1 is_locally_administered() vs pc/mac_census.py:32-37")
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "mac_census.py")
    ns = {}
    with open(src) as f:
        txt = f.read()
    start = txt.index("def is_locally_administered")
    end = txt.index("def census_file")
    exec(compile(txt[start:end], src, "exec"), ns)
    ref = ns["is_locally_administered"]
    allm = sorted({m for t in tags for m in data[t][0]["mac_list"]})
    dis = [m for m in allm if ref(m) != is_locally_administered(m)]
    print(f"  {len(allm)} addresses checked, {len(dis)} disagreements "
          f"-> {'AGREE' if not dis else 'MISMATCH ' + str(dis[:5])}")

    wins = ([int(x) for x in args.windows.split(",")] if args.windows
            else list(WINDOWS))
    for W in wins:
        for t in tags:
            analyze_receiver(t, data[t], W, args)


def analyze_receiver(tag, md, W, args):
    meta, fr = md
    macs = meta["mac_list"]
    w = build_windows(fr, W)
    hl(f"[{tag}]  W={W}  gate min_inlier={MIN_INLIER} max_resid={MAX_RESID}")
    if w is None:
        print("no windows")
        return
    nsrc = len(np.unique(w["mac"]))
    print(f"windows={len(w['mac']):,}  sources with >=1 window={nsrc}")

    # ---------------- floor relaxation accounting -------------------
    n20 = sum(1 for m in macs if meta["mac_clean"].get(m, 0) >= 20)
    print(f"\n-- FLOOR RELAXATION (docs/BLIND_CLUSTERING.md ss6) --")
    print(f"  sources at the repo's >=20-frame floor : {n20}")
    print(f"  sources clusterable here, no floor     : {nsrc}")
    print(f"  additional sources made clusterable    : {nsrc - n20:+d}")
    unclusterable = []
    for m in macs:
        mi = meta["mac_list"].index(m)
        if (w["mac"] == mi).sum() > 0:
            continue
        cl = meta["mac_clean"].get(m, 0)
        ft = meta["mac_fitted"].get(m, 0)
        gated = int(((fr["mac"] == mi)
                     & ((fr["inlier"] >= MIN_INLIER)
                        & (fr["resid"] <= MAX_RESID))).sum())
        if cl == 0:
            reason = "corrupt-only"
        elif ft < 0.9 * cl:
            reason = "parse/nofit"
        elif gated < W:
            reason = "sparsity" if ft < W else "gate"
        else:
            reason = "other"
        unclusterable.append((m, cl, ft, gated, reason))
    rc = defaultdict(int)
    for _, _, _, _, r in unclusterable:
        rc[r] += 1
    print(f"  not clusterable at W={W}: {len(unclusterable)}  "
          + "  ".join(f"{k}={v}" for k, v in sorted(rc.items())))

    # ---------------- dimensionality -------------------
    print(f"\n-- USABLE DIMENSIONS (docs/BLIND_CLUSTERING.md ss3.4) --")
    print(f"  windows with a defined cfo_hz: "
          f"{100*np.mean(w['cfo_frac'] > 0):.1f}%   "
          f"mean frac of frames in a window with cfo: "
          f"{100*np.mean(w['cfo_frac']):.1f}%")
    for sn in ("A", "B"):
        X = featmat(w, sn)
        Z, _, _ = robust_standardize(X)
        Z = np.clip(Z, -20, 20)
        Cm = np.corrcoef(Z.T)
        Cm = np.nan_to_num(Cm, nan=0.0)
        ev = np.sort(np.linalg.eigvalsh(Cm))[::-1]
        ev = np.maximum(ev, 0)
        pr = ev.sum() ** 2 / (ev ** 2).sum()
        print(f"  set {sn} ({X.shape[1]} nominal dims): eigenvalues "
              + " ".join(f"{e:.3f}" for e in ev)
              + f"   participation ratio = {pr:.2f}")

    # ---------------- per-source table -------------------
    print(f"\n-- PER-SOURCE (RSSI shown for reporting only, never a "
          f"feature; ss3.2) --")
    print(f"  {'mac':<18} {'kind':<7} {'raw':>9} {'clean':>9} {'gated':>9} "
          f"{'wins':>7} {'SFO med':>10} {'SFO sd':>9} {'RSSI':>7}")
    order = sorted(np.unique(w["mac"]).tolist(),
                   key=lambda x: -int((w["mac"] == x).sum()))
    for x in order:
        m = macs[int(x)]
        sel = w["mac"] == x
        gated = int(((fr["mac"] == x)
                     & (fr["inlier"] >= MIN_INLIER)
                     & (fr["resid"] <= MAX_RESID)).sum())
        kind = BEACONS.get(m, "LAA" if is_locally_administered(m) else "OUI")
        print(f"  {m:<18} {kind:<7} {meta['mac_raw'].get(m,0):>9,} "
              f"{meta['mac_clean'].get(m,0):>9,} {gated:>9,} "
              f"{int(sel.sum()):>7,} {np.median(w['sfo'][sel]):>+10.5f} "
              f"{w['sfo'][sel].std():>9.5f} {w['rssi'][sel].mean():>7.1f}")

    # ---------------- POSITIVE CONTROL -------------------
    print(f"\n-- POSITIVE CONTROL: 3 beacons, labels withheld, k=3 --")
    bidx = [macs.index(b) for b in (B1, B2, B3) if b in macs]
    bmask = np.isin(w["mac"], bidx)
    res = {}
    for sn in ("A", "B"):
        X = featmat(w, sn)[bmask]
        Z, _, _ = robust_standardize(X)
        Z = np.clip(Z, -20, 20)
        truth = w["mac"][bmask]
        lab, _, _ = kmeans(Z, 3)
        ari = adjusted_rand(truth, lab)
        sil = silhouette(Z, lab)
        res[sn] = (ari, sil, lab, truth, Z)
        verdict = "PASS" if ari >= 0.80 else ("MARGINAL" if ari >= 0.30
                                              else "FAIL")
        print(f"  set {sn}: n={len(Z):,} windows  ARI={ari:.4f}  "
              f"silhouette={sil:.3f}   [{verdict}]")
    # per-beacon window counts and confusion on set A
    ari, sil, lab, truth, Z = res["A"]
    print("  set A confusion (rows = true beacon, cols = blind cluster):")
    for bi in sorted(set(truth.tolist())):
        row = [int(((truth == bi) & (lab == c)).sum()) for c in range(3)]
        print(f"    {BEACONS[macs[bi]]} {macs[bi]}  " +
              "".join(f"{v:>9,}" for v in row))
    # without B2/d0wd
    if tag == "d0wd" and B2 in macs:
        keep = bmask & (w["mac"] != macs.index(B2))
        X = featmat(w, "A")[keep]
        Z2, _, _ = robust_standardize(X)
        Z2 = np.clip(Z2, -20, 20)
        l2, _, _ = kmeans(Z2, 2)
        print(f"  set A, B2/d0wd (the 79.8%-reject cell) excluded, k=2: "
              f"ARI={adjusted_rand(w['mac'][keep], l2):.4f}")

    # ---------------- NEGATIVE CONTROL -------------------
    print(f"\n-- NEGATIVE CONTROL: frame->window assignment shuffled --")
    g = w["gated"]
    gb = g[np.isin(g["mac"], bidx)]
    sizes = [W] * int(bmask.sum())
    sh = shuffle_frames(gb, sizes)
    Xs = np.column_stack([sh["sfo"], sh["iqr"]])
    Zs, _, _ = robust_standardize(Xs)
    Zs = np.clip(Zs, -20, 20)
    ls, _, _ = kmeans(Zs, 3)
    ari_s = adjusted_rand(res["A"][3][:len(ls)], ls)
    sil_s = silhouette(Zs, ls)
    print(f"  beacons, set A: ARI={ari_s:.4f} (real {res['A'][0]:.4f})  "
          f"silhouette={sil_s:.3f} (real {res['A'][1]:.3f})  "
          f"[{'CLEAN' if abs(ari_s) < 0.05 else 'NOT CLEAN'}]")

    # ---------------- OPEN SET -------------------
    print(f"\n-- OPEN SET: every source with >=1 window, floor relaxed --")
    X = featmat(w, "A")
    Z, med, mad = robust_standardize(X)
    Z = np.clip(Z, -20, 20)
    inv, cent, cnt, cw = grid_cells(Z)
    print(f"  {len(w['mac']):,} windows -> {len(cent):,} grid cells "
          f"(cell width {cw:.4f} MAD-units)")
    merges = average_linkage(cent, cnt)
    heights = np.array([h for _, _, h in merges])
    want = args.cuts
    best = None
    if want in ("sil", "both"):
      for th in np.unique(np.quantile(heights, np.linspace(0.5, 0.999, 24))):
        cl = cut(merges, len(cent), th)[inv]
        k = len(np.unique(cl))
        if k < 2 or k > 200:
            continue
        s = silhouette(Z, cl)
        if best is None or (np.isfinite(s) and s > best[0]):
            best = (s, th, cl, k)
    cl_o = None
    if best is not None:
        sil_o, th_o, cl_o, k_o = best
        print(f"  silhouette-optimal cut: height={th_o:.3f}  k={k_o}  "
              f"silhouette={sil_o:.3f}  "
              f"ARI vs MAC={adjusted_rand(w['mac'], cl_o):.4f}")
    elif want in ("sil", "both"):
        print("  no usable silhouette cut")

    # physical cut: within-cluster raw SFO spread <= BETWEEN_UNIT_SD
    phys = None
    if want in ("phys", "both"):
      for th in np.unique(np.quantile(heights, np.linspace(0.01, 0.999, 60))):
        cl = cut(merges, len(cent), th)[inv]
        # per-cluster sd by bincount rather than a mask per cluster: same
        # number, O(n) per threshold instead of O(n*k).
        k = int(cl.max()) + 1
        n_c = np.bincount(cl, minlength=k).astype(np.float64)
        s1 = np.bincount(cl, weights=w["sfo"], minlength=k)
        s2 = np.bincount(cl, weights=w["sfo"] ** 2, minlength=k)
        with np.errstate(invalid="ignore", divide="ignore"):
            var = np.where(n_c > 0, s2 / np.maximum(n_c, 1)
                           - (s1 / np.maximum(n_c, 1)) ** 2, 0.0)
        sd = np.sqrt(np.maximum(var, 0.0))
        if not np.any((n_c > 1) & (sd > BETWEEN_UNIT_SD)):
            phys = (th, cl, int((n_c > 0).sum()))
      # (loop body indented one level in for the --cuts switch above)
    if phys:
        print(f"  physical cut (every cluster's SFO sd <= "
              f"BETWEEN_UNIT_SD={BETWEEN_UNIT_SD}): height={phys[0]:.3f}  "
              f"k={phys[2]}  ARI vs MAC={adjusted_rand(w['mac'], phys[1]):.4f}")

    for name, cl in (("silhouette-optimal", cl_o),
                     ("physical", phys[1] if phys else None)):
        if cl is None:
            continue
        report_clusters(name, tag, W, w, cl, macs, meta,
                        pairtest=(name == "silhouette-optimal"))


def pair_cocluster_test(w, cl, xa, xb, seed=SEED, nperm=400):
    """Criterion 1 of docs/BLIND_CLUSTERING.md ss7.1, per pair: does this
    pair of addresses co-cluster more than MAC labels permuted across
    windows would? Statistic is the fraction of (window_a, window_b) pairs
    landing in the same cluster."""
    ncl = int(cl.max()) + 1
    ca = np.bincount(cl[w["mac"] == xa], minlength=ncl).astype(np.float64)
    cb = np.bincount(cl[w["mac"] == xb], minlength=ncl).astype(np.float64)
    na, nb = ca.sum(), cb.sum()
    obs = float(ca @ cb) / (na * nb)
    rng = np.random.default_rng(seed)
    N = len(cl)
    null = np.empty(nperm)
    ia, ib = int(na), int(nb)
    for t in range(nperm):
        p = rng.permutation(N)
        pa = np.bincount(cl[p[:ia]], minlength=ncl).astype(np.float64)
        pb = np.bincount(cl[p[ia:ia + ib]], minlength=ncl).astype(np.float64)
        null[t] = (pa @ pb) / (na * nb)
    p95 = float(np.percentile(null, 95))
    pval = float((null >= obs).mean())
    return obs, float(null.mean()), p95, pval


def report_clusters(name, tag, W, w, cl, macs, meta, pairtest=False):
    print(f"\n  ---- {name} cut: multi-MAC clusters "
          f"(docs/BLIND_CLUSTERING.md ss7) ----")
    rng = np.random.default_rng(SEED)
    multi = []
    for c in np.unique(cl):
        mm = w["mac"][cl == c]
        u, ct = np.unique(mm, return_counts=True)
        if len(u) > 1:
            multi.append((c, u, ct))
    print(f"  clusters={len(np.unique(cl))}  multi-MAC clusters={len(multi)}")

    # Permutation null for the number of multi-MAC clusters: permute the
    # MAC labels across windows, preserving each MAC's window count and the
    # cluster assignment. Counted by the identity
    #   multi-MAC clusters = #distinct (cluster, MAC) pairs - #clusters,
    # which is exact and one np.unique per permutation.
    ncl = len(np.unique(cl))
    base = int(w["mac"].max()) + 2
    cl64 = cl.astype(np.int64) * base
    nbins = int(cl64.max()) + base + 1
    null = []
    for _ in range(1000):
        pm = rng.permutation(w["mac"]).astype(np.int64)
        occ = np.bincount(cl64 + pm, minlength=nbins)
        null.append(int(np.count_nonzero(occ)) - ncl)
    null = np.array(null)
    print(f"  permutation null (1000 label shuffles): "
          f"mean={null.mean():.1f} p95={np.percentile(null,95):.0f} "
          f"-> observed {len(multi)} is "
          f"{'ABOVE' if len(multi) > np.percentile(null,95) else 'WITHIN'} "
          f"the null")

    shown = 0
    for c, u, ct in sorted(multi, key=lambda x: -x[2].sum()):
        if shown >= (12 if pairtest else 6):
            print(f"  ... {len(multi)-shown} more multi-MAC clusters")
            break
        shown += 1
        sel = cl == c
        sd = float(w["sfo"][sel].std())
        tight = sd <= BETWEEN_UNIT_SD
        laa = [is_locally_administered(macs[int(x)]) for x in u]
        allla = all(laa)
        print(f"\n   cluster {c}: {len(u)} MACs, {int(ct.sum())} windows, "
              f"SFO sd={sd:.5f} ({'TIGHT' if tight else 'wide'}), "
              f"all-LAA={allla}")
        spans = []
        for x, n in zip(u, ct):
            m = macs[int(x)]
            s = w["ts"][sel & (w["mac"] == x)]
            spans.append((m, n, s.min(), s.max()))
            print(f"     {m}  {'LAA' if is_locally_administered(m) else 'OUI'}"
                  f"{'  ' + BEACONS[m] if m in BEACONS else '     '}  "
                  f"win={int(n):>7,}  raw_frames="
                  f"{meta['mac_raw'].get(m,0):>9,}  "
                  f"t=[{(s.min()-w['ts'].min())*1e-6:9.1f},"
                  f"{(s.max()-w['ts'].min())*1e-6:9.1f}] s")
        if len(spans) == 2:
            (_, _, a0, a1), (_, _, b0, b1) = spans
            ov = max(0.0, min(a1, b1) - max(a0, b0)) * 1e-6
            print(f"     time structure: "
                  f"{'INTERLEAVED (concurrent)' if ov > 0 else 'SEQUENTIAL (disjoint)'}"
                  f"  overlap={ov:.1f} s")
        # Skipped when the cut has fewer than 10 clusters: with 3 clusters
        # the permutation null sits at ~0.999 and the test has no power.
        if pairtest and len(np.unique(cl)) >= 10 and len(u) <= 6:
            for ai in range(len(u)):
                for bi in range(ai + 1, len(u)):
                    ma, mb = macs[int(u[ai])], macs[int(u[bi])]
                    if not (is_locally_administered(ma)
                            or is_locally_administered(mb)):
                        continue
                    o, mn, p95, pv = pair_cocluster_test(w, cl, u[ai], u[bi])
                    c1 = "PASS" if o > p95 else "FAIL"
                    print(f"     ss7.1 c1 co-cluster {ma[-8:]}/{mb[-8:]}: "
                          f"obs={o:.4f} null_mean={mn:.4f} null_p95={p95:.4f} "
                          f"p={pv:.3f} -> criterion 1 {c1}")

    # ss7.1 criterion 1 on the cut that actually has resolving power: every
    # non-beacon pair sharing a cluster, ranked by shared windows.
    if not pairtest:
        srcs = [x for x in np.unique(w["mac"])
                if macs[int(x)] not in BEACONS]
        ncl = int(cl.max()) + 1
        cnts = {int(x): np.bincount(cl[w["mac"] == x], minlength=ncl)
                for x in srcs}
        cand = []
        for ai in range(len(srcs)):
            for bi in range(ai + 1, len(srcs)):
                a, b = int(srcs[ai]), int(srcs[bi])
                sh = int(np.minimum(cnts[a], cnts[b]).sum())
                if sh > 0:
                    cand.append((sh, a, b))
        cand.sort(reverse=True)
        print(f"\n  ---- {name} cut: ss7.1 criterion 1, non-beacon pairs "
              f"sharing a cluster ({len(cand)} such pairs) ----")
        if not cand:
            print("   none")
        for sh, a, b in cand[:6]:
            o, mn, p95, pv = pair_cocluster_test(w, cl, a, b, nperm=300)
            ma, mb = macs[a], macs[b]
            la = "LAA" if is_locally_administered(ma) else "OUI"
            lb = "LAA" if is_locally_administered(mb) else "OUI"
            print(f"   {ma}({la}) / {mb}({lb})  shared={sh}  "
                  f"obs={o:.4f} null_mean={mn:.4f} p95={p95:.4f} p={pv:.3f}"
                  f"  -> criterion 1 {'PASS' if o > p95 else 'FAIL'}")

    # inverse question: does a single MAC split across clusters?
    print(f"\n  ---- {name} cut: single MACs split across clusters "
          f"(ss7.3) ----")
    for x in np.unique(w["mac"]):
        m = macs[int(x)]
        cs, ct = np.unique(cl[w["mac"] == x], return_counts=True)
        if len(cs) > 1:
            tagb = f" [{BEACONS[m]}]" if m in BEACONS else ""
            print(f"   {m}{tagb}: {len(cs)} clusters, "
                  f"largest holds {100*ct.max()/ct.sum():.1f}% of "
                  f"{int(ct.sum()):,} windows")

    # 2*pi/dk mis-unwrap ladder check on centroid separations
    print(f"\n  ---- {name} cut: 2*pi/dk mis-unwrap check (ss7.2) ----")
    cents = np.array([w["sfo"][cl == c].mean() for c in np.unique(cl)])
    cents.sort()
    hits = []
    for i in range(len(cents) - 1):
        d = cents[i + 1] - cents[i]
        for dk, v in UNWRAP_LADDER.items():
            if abs(d - v) / v <= 0.05:
                hits.append((d, dk, v))
    if hits:
        for d, dk, v in hits[:8]:
            print(f"   adjacent centroid gap {d:.5f} rad/sc is within 5% of "
                  f"2pi/{dk}={v:.5f}  -> CANDIDATE ESTIMATOR ARTEFACT")
    else:
        print("   no adjacent centroid gap lands on the ladder "
              "(0.1208 / 0.1571 / 0.1963 / 0.2417)")


def run_focus(args):
    """Criteria 2 and 3 of ss7.1, plus fine time structure and RSSI, for one
    named pair of addresses on one receiver. Criterion 1 is reported by
    `analyze`; this is the follow-up on whichever pair passed it."""
    meta, fr = load(args.tag)
    macs = meta["mac_list"]
    ma, mb = args.a.lower(), args.b.lower()
    for W in [int(x) for x in args.windows.split(",")]:
        w = build_windows(fr, W)
        ia, ib = macs.index(ma), macs.index(mb)
        sa, sb = w["mac"] == ia, w["mac"] == ib
        both = np.concatenate([w["sfo"][sa], w["sfo"][sb]])
        print(f"\n[{args.tag}] W={W}   {ma} vs {mb}")
        print(f"  ss7.1 criterion 2 (pooled window SFO sd <= "
              f"BETWEEN_UNIT_SD={BETWEEN_UNIT_SD}):")
        print(f"    {ma}: n={int(sa.sum()):>4}  median={np.median(w['sfo'][sa]):+.5f}"
              f"  sd={w['sfo'][sa].std():.5f}  RSSI={w['rssi'][sa].mean():+.1f} dB")
        print(f"    {mb}: n={int(sb.sum()):>4}  median={np.median(w['sfo'][sb]):+.5f}"
              f"  sd={w['sfo'][sb].std():.5f}  RSSI={w['rssi'][sb].mean():+.1f} dB")
        print(f"    pooled sd={both.std():.5f}  "
              f"-> criterion 2 "
              f"{'PASS' if both.std() <= BETWEEN_UNIT_SD else 'FAIL'}")
        d = abs(np.median(w["sfo"][sa]) - np.median(w["sfo"][sb]))
        lad = [(dk, v, abs(d - v) / v) for dk, v in UNWRAP_LADDER.items()]
        near = min(lad, key=lambda t: t[2])
        print(f"  ss7.2/criterion 3: |median gap|={d:.5f} rad/sc "
              f"({d/BETWEEN_UNIT_SD:.2f} x BETWEEN_UNIT_SD); nearest ladder "
              f"rung 2pi/{near[0]}={near[1]:.5f} is {100*near[2]:.0f}% away "
              f"-> {'ARTEFACT CANDIDATE' if near[2] <= 0.05 else 'criterion 3 PASS (not a mis-unwrap)'}")
        # fine time structure: 60 s bins, both active in the same bin?
        t0 = w["ts"].min()
        for nm, sel in ((ma, sa), (mb, sb)):
            t = (w["ts"][sel] - t0) * 1e-6
            print(f"  {nm}: first={t.min():.1f}s last={t.max():.1f}s "
                  f"distinct 60s bins={len(np.unique((t//60).astype(int)))}")
        ta = set(((w["ts"][sa] - t0) * 1e-6 // 60).astype(int).tolist())
        tb = set(((w["ts"][sb] - t0) * 1e-6 // 60).astype(int).tolist())
        print(f"  60 s bins active for BOTH: {len(ta & tb)}  "
              f"-> {'INTERLEAVED (concurrent) -- not an address rotation' if (ta & tb) else 'SEQUENTIAL (disjoint) -- consistent with rotation'}")
        # raw-frame level concurrency, independent of windowing
        fa = fr["ts"][fr["mac"] == ia]
        fb = fr["ts"][fr["mac"] == ib]
        ba = set(((fa - fr["ts"].min()) // 60_000_000).tolist())
        bb = set(((fb - fr["ts"].min()) // 60_000_000).tolist())
        print(f"  raw frames, 60 s bins: {ma} in {len(ba)} bins, "
              f"{mb} in {len(bb)} bins, BOTH in {len(ba & bb)}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("replay")
    p.add_argument("path")
    p.add_argument("--tag", required=True)
    p.add_argument("--part", type=int, required=True)
    p.add_argument("--nparts", type=int, required=True)
    p.add_argument("--total-rows", type=int, required=True)
    p.set_defaults(fn=run_replay)

    p = sub.add_parser("merge")
    p.add_argument("--tag", required=True)
    p.add_argument("--nparts", type=int, required=True)
    p.add_argument("--expect-rows", type=int, required=True)
    p.set_defaults(fn=run_merge)

    p = sub.add_parser("analyze")
    p.add_argument("--tags", required=True)
    p.add_argument("--windows", default=None,
                   help="comma-separated window lengths; default 64,16. "
                        "Split only so one shell call stays inside the "
                        "host's ~178 s cap -- the analysis is identical.")
    p.add_argument("--cuts", default="both", choices=("sil", "phys", "both"),
                   help="which open-set cut to report; splitting the two "
                        "is a runtime accommodation only, both are "
                        "computed from the same linkage")
    p.set_defaults(fn=run_analyze)

    p = sub.add_parser("focus")
    p.add_argument("--tag", required=True)
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--windows", default="64,16")
    p.set_defaults(fn=run_focus)

    args = ap.parse_args()
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
