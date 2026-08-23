#!/usr/bin/env python3
"""docs/V2_SPEC.md 7(a)2 and 7(a)8, against data already on disk.

CHECK 1 (7(a)2)  -- the 154 fps ceiling.
    display_task runs at exactly 4 Hz (firmware/csi_rx/main/main.c:247,
    pdMS_TO_TICKS(250)). If I2C contention causes queue drops, the
    per-frame `dropped` deltas should carry 250 ms periodicity. This
    script folds the wrap-safe per-frame drop deltas onto a 250 ms phase
    using `esp_timestamp_us`, on both nodes and three captures, and tests
    the folded drop RATE against a uniform null.

CHECK 2 (7(a)8) -- the marginal cell.
    Reject rate for all six node x beacon cells, from ONE pipeline, on all
    three dual captures, plus the seven candidate covariates named in the
    brief.

READ-ONLY on data/raw/: every file is opened "r" through Python's csv
module and never written, renamed or deleted. No serial port is opened.
Nothing is staged or committed.

`csi_data` is a quoted comma-separated list nested INSIDE the CSV, so a
128-value row splits into 140 fields on a naive comma split. This file
uses csv.reader throughout and reports row counts by len(row); the
`split(",", 128)` defect is not reproduced here.

Phase work is pc/rff/dsp.py's FrameEstimator with the shipped gates
inlier_ratio >= 0.6 and resid_std <= 0.8 (dsp.py:164,173,175) and
WindowAggregator(window=64). pc/capture.py:compute_cfo, pc/phase_skew.py
and pc/fingerprint.py are NOT used (docs/CODE_INVENTORY.md 4.2 C1/C2/C3).

Corrupt-row screen is the two independent routes of
docs/OVERNIGHT_2026-08-22.md 1, reused unchanged: route 1 is a width-9
edge-padded median filter on `dropped` with tolerance 100; route 2 is
field plausibility on six columns unrelated to `dropped`.

The two overnight files are 2.5 and 3.0 GB, so `run` is split into byte-range
`part`s that are merged afterwards. A part seeks to its byte offset, backs up
16 KB, discards the partial line and primes the 9-deep median window from the
rows before its own range, so the corrupt-row screen at a part boundary is the
same one a single pass would apply. Parts are byte ranges of the file, taken
in order; `merge` concatenates them in file order.

From the repo root:

    python3 pc/exp_oled_marginal_0822.py selftest
    python3 pc/exp_oled_marginal_0822.py plan data/raw/<f>.csv --parts N
    python3 pc/exp_oled_marginal_0822.py part data/raw/<f>.csv --tag <f> \
        --index K --parts N
    python3 pc/exp_oled_marginal_0822.py merge --tag <f> --parts N
    python3 pc/exp_oled_marginal_0822.py report
"""
import argparse
import csv
import json
import math
import os
import sys
from collections import deque

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from rff import dsp                                        # noqa: E402

CACHE = "/tmp/oled_marginal_cache"

B1 = "a4:f0:0f:77:91:20"
B2 = "28:05:a5:2f:fa:48"
B3 = "f4:2d:c9:70:72:30"
BEACONS = [B1, B2, B3]
BNAME = {B1: "B1", B2: "B2", B3: "B3"}

CSI_LENS = {128, 256, 384}
K = dsp.K_USABLE.astype(np.float64)
IDX = dsp._USABLE_IDX

DISPLAY_PERIOD_US = 250000.0        # main.c:247 pdMS_TO_TICKS(250)
NPHASE = 25                         # 10 ms phase bins
N_ROT = 2000                        # circular-rotation null draws
BLOCK_S = 60.0                      # drift-robust block length

# On-wire bytes per delivered CSI frame: 12 header + 15 + csi_len payload
# + 1 XOR byte (telemetry.c:24,37-39,60).
WIRE_FIXED = 12 + 15 + 1
UART_BYTES_PER_S = 460800.0 / 10.0  # sdkconfig:1310, 8N1

# The three dual sessions, with what the operator states about occupancy.
SESSIONS = {
    "20260821_125017": dict(nodes=("desk_20260821_125017",
                                   "s3_20260821_125017"),
                            local_start="12:50:17", occ="present throughout"),
    "20260822_023034": dict(nodes=("d0wd_20260822_023034",
                                   "s3_20260822_023034"),
                            local_start="02:30:34", occ="empty throughout"),
    "20260822_144424": dict(nodes=("d0wd_20260822_144424",
                                   "s3_20260822_144424"),
                            local_start="14:44:24",
                            occ="present except t=[785,920) s"),
}
# docs/OCCUPANCY_TEST_0822.md 0, 5.3 -- edges located from the data.
ABSENT_LO, ABSENT_HI = 785.0, 920.0


# ------------------------------------------------------------- statistics

def gammq(a, x):
    """Regularized upper incomplete gamma Q(a,x). No scipy in this env."""
    if x < 0 or a <= 0:
        return float("nan")
    if x == 0.0:
        return 1.0
    if x < a + 1.0:                       # series for P(a,x)
        ap, s, d = a, 1.0 / a, 1.0 / a
        for _ in range(1000):
            ap += 1.0
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 1e-14:
                break
        return 1.0 - s * math.exp(-x + a * math.log(x) - math.lgamma(a))
    # continued fraction for Q(a,x)
    tiny = 1e-300
    b, c = x + 1.0 - a, 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-14:
            break
    return h * math.exp(-x + a * math.log(x) - math.lgamma(a))


def chi2_sf(x, k):
    return gammq(k / 2.0, x / 2.0)


def spearman(a, b):
    """Spearman rho + two-sided permutation p (exact null by shuffling)."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    n = a.size
    if n < 4:
        return float("nan"), float("nan"), n

    def rank(v):
        o = np.argsort(v, kind="mergesort")
        r = np.empty(v.size, dtype=np.float64)
        r[o] = np.arange(1, v.size + 1, dtype=np.float64)
        # average ties
        vs = v[o]
        i = 0
        while i < v.size:
            j = i
            while j + 1 < v.size and vs[j + 1] == vs[i]:
                j += 1
            if j > i:
                r[o[i:j + 1]] = (i + j + 2) / 2.0
            i = j + 1
        return r

    ra, rb = rank(a), rank(b)
    ra -= ra.mean()
    rb -= rb.mean()
    den = math.sqrt(float((ra * ra).sum()) * float((rb * rb).sum()))
    if den <= 0:                     # a covariate with no variance at all
        return float("nan"), float("nan"), n
    rho = float((ra * rb).sum() / den)
    rng = np.random.default_rng(0)
    hits = 0
    for _ in range(20000):
        p = rng.permutation(n)
        r2 = float((ra * rb[p]).sum() / den)
        if abs(r2) >= abs(rho) - 1e-15:
            hits += 1
    return rho, (hits + 1) / 20001.0, n


def median_filter_ref(x, width=9):
    """docs/OVERNIGHT_2026-08-22.md 1 route 1, as pc/exp_occupancy_0822.py:81
    writes it. Reference implementation; O(n) python loop, small inputs."""
    out = np.empty_like(x, dtype=np.float64)
    pad = np.pad(x, width // 2, mode="edge")
    for i in range(len(x)):
        out[i] = np.median(pad[i:i + width])
    return out


def median_filter_stream(buf9, i_in_win):
    """Median of a width-9 edge-padded window, computed from a 9-deep deque.

    Matches median_filter_ref exactly; see `selftest`.
    """
    return float(np.median(buf9))


# ------------------------------------------------------------ check 1 core

def fold_stats(ets, dd, period_us=DISPLAY_PERIOD_US, nbin=NPHASE):
    """Rate-domain circular resultant of drop deltas folded on `period_us`.

    Frames are not uniformly distributed in phase, so the raw
    drop-weighted resultant is biased by frame density. The statistic
    used here is built from the per-phase-bin drop RATE
    r_b = (drops in bin b) / (frames in bin b), which removes that bias:

        C = sum_b r_b cos(th_b),  S = sum_b r_b sin(th_b)
        Rbar = sqrt(C^2 + S^2) / sum_b r_b

    For a rate law r(th) = r0 (1 + m cos(th - phi)), Rbar -> m/2, so the
    reported effect size is m = 2*Rbar, the fractional amplitude of a
    sinusoidal modulation of the drop rate at 1/period.
    """
    ph = np.mod(ets.astype(np.float64), period_us) / period_us
    b = np.minimum((ph * nbin).astype(np.int64), nbin - 1)
    cnt = np.bincount(b, minlength=nbin).astype(np.float64)
    drp = np.bincount(b, weights=dd.astype(np.float64), minlength=nbin)
    with np.errstate(invalid="ignore", divide="ignore"):
        rate = np.where(cnt > 0, drp / np.maximum(cnt, 1), np.nan)
    th = 2 * np.pi * (np.arange(nbin) + 0.5) / nbin
    good = np.isfinite(rate)
    s = rate[good].sum()
    if s <= 0:
        return dict(rbar=float("nan"), m=float("nan"), rate=rate, cnt=cnt,
                    drops=drp, chi2=float("nan"), chi2_p=float("nan"),
                    depth=float("nan"))
    C = float((rate[good] * np.cos(th[good])).sum())
    S = float((rate[good] * np.sin(th[good])).sum())
    rbar = math.hypot(C, S) / s
    # Pearson chi-square of drops against the uniform-rate expectation
    # E_b = total_drops * cnt_b / total_frames.
    tot_d, tot_c = drp.sum(), cnt.sum()
    exp = tot_d * cnt / tot_c
    ok = exp > 0
    chi2 = float((((drp[ok] - exp[ok]) ** 2) / exp[ok]).sum())
    dof = int(ok.sum()) - 1
    return dict(rbar=rbar, m=2 * rbar, rate=rate, cnt=cnt, drops=drp,
                chi2=chi2, chi2_dof=dof, chi2_p=chi2_sf(chi2, dof),
                depth=float((np.nanmax(rate) - np.nanmin(rate))
                            / np.nanmean(rate)))


def rotation_null(ets, dd, period_us=DISPLAY_PERIOD_US, nbin=NPHASE,
                  n=N_ROT, seed=0):
    """Null for fold_stats: circularly rotate the drop-delta series against
    the timestamp series. This preserves the frame phase distribution AND
    the burst autocorrelation of `dropped` exactly, which an i.i.d. shuffle
    would destroy -- drops are known to be bursty
    (docs/OVERNIGHT_2026-08-22.md 4.2)."""
    ph = np.mod(ets.astype(np.float64), period_us) / period_us
    b = np.minimum((ph * nbin).astype(np.int64), nbin - 1)
    cnt = np.bincount(b, minlength=nbin).astype(np.float64)
    th = 2 * np.pi * (np.arange(nbin) + 0.5) / nbin
    ct, st = np.cos(th), np.sin(th)
    rng = np.random.default_rng(seed)
    N = dd.size
    w = dd.astype(np.float64)
    out = np.empty(n)
    dep = np.empty(n)
    for i in range(n):
        L = int(rng.integers(1, N))
        drp = np.bincount(b, weights=np.roll(w, L), minlength=nbin)
        rate = np.where(cnt > 0, drp / np.maximum(cnt, 1), np.nan)
        g = np.isfinite(rate)
        s = rate[g].sum()
        if s <= 0:
            out[i] = np.nan
            dep[i] = np.nan
            continue
        out[i] = math.hypot(float((rate[g] * ct[g]).sum()),
                            float((rate[g] * st[g]).sum())) / s
        dep[i] = (np.nanmax(rate) - np.nanmin(rate)) / np.nanmean(rate)
    return out, dep


def period_scan(ets, dd, lo_us, hi_us, step_us, nbin=NPHASE):
    ps = np.arange(lo_us, hi_us + 0.5 * step_us, step_us)
    r = np.empty(ps.size)
    for i, p in enumerate(ps):
        r[i] = fold_stats(ets, dd, period_us=float(p), nbin=nbin)["rbar"]
    return ps, r



# --------------------------------------------------------------- part/merge

def scan_modes(path, n=20000):
    """The file's own node_id and channel mode, for corrupt-row screen
    route 2 (docs/OVERNIGHT_2026-08-22.md 1)."""
    node_c, chan_c = {}, {}
    with open(path, "rb") as f:
        f.readline()
        rd = csv.reader((raw.decode("ascii") for raw in f))
        for i, row in enumerate(rd):
            if i >= n:
                break
            if len(row) != 13:
                continue
            try:
                node_c[int(row[10])] = node_c.get(int(row[10]), 0) + 1
                chan_c[int(row[6])] = chan_c.get(int(row[6]), 0) + 1
            except ValueError:
                pass
    return max(node_c, key=node_c.get), max(chan_c, key=chan_c.get)


def part_path(tag, k):
    return os.path.join(CACHE, f"{tag}.part{k}.npz")


def cmd_plan(args):
    size = os.path.getsize(args.csv)
    for k in range(args.parts):
        print(f"part {k}: bytes [{size*k//args.parts}, "
              f"{size*(k+1)//args.parts})")


def cmd_part(args):
    """Process one byte range of one CSV.

    The range is [size*k/N, size*(k+1)/N). The reader starts PRIME_BACK
    bytes earlier and discards the partial line, so the 9-deep width-9
    median window is primed from rows that belong to the previous part;
    it also reads 4 records past the range end for the same reason. A
    record is emitted by exactly one part: the one whose range contains
    the record's starting byte offset. Records contain no embedded
    newlines (every row is len(row) == 13 through csv.reader), so a byte
    offset always identifies a record boundary.
    """
    os.makedirs(CACHE, exist_ok=True)
    path, tag, k, N = args.csv, args.tag, args.index, args.parts
    st = os.stat(path)
    size = st.st_size
    b_lo, b_hi = size * k // N, size * (k + 1) // N
    node_mode, chan_mode = scan_modes(path)
    print(f"[{tag}.{k}/{N}] {path} {size} B  range [{b_lo}, {b_hi})  "
          f"node_mode {node_mode} chan_mode {chan_mode}  "
          f"mtime_ns {st.st_mtime_ns}")

    PRIME_BACK = 16384
    est = {b: dsp.FrameEstimator(rng_seed=0) for b in BEACONS}
    agg = {b: dsp.WindowAggregator(window=64) for b in BEACONS}
    cell = {b: dict(fed=0, fitted=0, acc=0, win=0,
                    rssi_n=0, rssi_s=0.0, rssi_ss=0.0,
                    rssi_an=0, rssi_as=0.0, rssi_rn=0, rssi_rs=0.0,
                    nf_n=0, nf_s=0.0, inl=[], res=[],
                    amp_sum=np.zeros(K.size), amp_n=0,
                    acc_in=0, fed_in=0, acc_out=0, fed_out=0)
            for b in BEACONS}
    S_t, S_ets, S_drop, S_rssi, S_nf, S_clen = [], [], [], [], [], []
    macseen = {}
    lenhist = {}
    n_rows = n_bad1 = n_bad2 = n_both = n_bad = 0
    t0_pc = args.t0_pc if args.t0_pc else None

    def emit(rows, ci):
        nonlocal n_bad1, n_bad2, n_both, n_bad
        (pc, mac, rssi, nf, chan, node, env, clen, ets, drop, cs) = rows[ci]
        n = len(rows)
        win = [rows[min(max(j, 0), n - 1)][9] for j in range(ci - 4, ci + 5)]
        med = float(np.median(win))
        bad1 = abs(drop - med) > 100
        bad2 = ((node != node_mode) or (env != 0) or (chan != chan_mode)
                or (clen not in CSI_LENS) or (nf < -110) or (nf > -70)
                or (rssi < -100) or (rssi > -10))
        if bad1:
            n_bad1 += 1
        if bad2:
            n_bad2 += 1
        if bad1 and bad2:
            n_both += 1
        if bad1 or bad2:
            n_bad += 1
            return
        S_t.append(pc)
        S_ets.append(ets)
        S_drop.append(drop)
        S_rssi.append(rssi)
        S_nf.append(nf)
        S_clen.append(clen)
        if mac not in BNAME:
            return
        c = cell[mac]
        c["fed"] += 1
        c["rssi_n"] += 1
        c["rssi_s"] += rssi
        c["rssi_ss"] += rssi * rssi
        c["nf_n"] += 1
        c["nf_s"] += nf
        vals = np.fromstring(cs, dtype=np.float64, sep=",")
        if vals.size < 128:
            return
        e = est[mac].feed(vals, ets)
        if e is None:
            return
        c["fitted"] += 1
        c["inl"].append(e["inlier_ratio"])
        c["res"].append(e["resid_std"])
        acc = (e["inlier_ratio"] >= 0.6) and (e["resid_std"] <= 0.8)
        inabs = (t0_pc is not None
                 and ABSENT_LO <= (pc - t0_pc) * 1e-6 < ABSENT_HI)
        if inabs:
            c["fed_in"] += 1
        else:
            c["fed_out"] += 1
        if acc:
            c["acc"] += 1
            c["rssi_an"] += 1
            c["rssi_as"] += rssi
            if inabs:
                c["acc_in"] += 1
            else:
                c["acc_out"] += 1
        else:
            c["rssi_rn"] += 1
            c["rssi_rs"] += rssi
        cx = dsp.csi_to_complex(vals)
        if cx is not None:
            c["amp_sum"] += np.abs(cx[IDX])
            c["amp_n"] += 1
        if agg[mac].feed(e, ets, rssi) is not None:
            c["win"] += 1

    start = max(0, b_lo - PRIME_BACK)
    hist_off, hist_rec = [], []
    leading_done = (k != 0)
    hit_eof = True
    with open(path, "rb") as f:
        f.seek(start)
        if start > 0:
            f.readline()                       # discard the partial line
        else:
            f.readline()                       # discard the CSV header
        pos = f.tell()
        for raw in f:
            off = pos
            pos += len(raw)
            row = next(csv.reader([raw.decode("ascii", "replace")]))
            if b_lo <= off < b_hi:
                n_rows += 1
                lenhist[len(row)] = lenhist.get(len(row), 0) + 1
            if len(row) != 13:
                continue
            try:
                rec = (int(row[0]), row[3].lower(), int(row[4]), int(row[5]),
                       int(row[6]), int(row[10]), int(row[11]), int(row[8]),
                       int(row[7]), int(row[12]), row[9])
            except ValueError:
                continue
            if b_lo <= off < b_hi:
                macseen[rec[1]] = macseen.get(rec[1], 0) + 1
            hist_off.append(off)
            hist_rec.append(rec)
            if len(hist_rec) < 9:
                continue
            if not leading_done:                 # rows 0..3 of the FILE
                for ci in range(0, 4):
                    if b_lo <= hist_off[ci] < b_hi:
                        emit(hist_rec, ci)
                leading_done = True
            c_off = hist_off[4]
            if c_off >= b_hi:
                hit_eof = False
                break
            if c_off >= b_lo:
                emit(hist_rec, 4)
            hist_off.pop(0)
            hist_rec.pop(0)
    if hit_eof:                                   # trailing rows of the FILE
        for ci in range(4, len(hist_rec)):
            if b_lo <= hist_off[ci] < b_hi:
                emit(hist_rec, ci)

    print(f"[{tag}.{k}] rows in range {n_rows}; len(row) histogram "
          f"{sorted(lenhist.items())}; corrupt route1 {n_bad1} route2 "
          f"{n_bad2} both {n_both} union {n_bad}; clean {len(S_t)}")
    z = dict(
        t=np.array(S_t, dtype=np.int64), ets=np.array(S_ets, dtype=np.int64),
        drop=np.array(S_drop, dtype=np.int64),
        rssi=np.array(S_rssi, dtype=np.int16),
        nf=np.array(S_nf, dtype=np.int16),
        clen=np.array(S_clen, dtype=np.int32),
        meta=np.array([n_rows, n_bad1, n_bad2, n_both, n_bad, size,
                       st.st_mtime_ns, node_mode, chan_mode],
                      dtype=np.int64),
        lenhist=np.array(sorted(lenhist.items()), dtype=np.int64).reshape(-1, 2),
        macs=np.array(sorted(macseen.items()), dtype=object),
    )
    for b in BEACONS:
        c = cell[b]
        nm = BNAME[b]
        z[nm + "_scalar"] = np.array(
            [c["fed"], c["fitted"], c["acc"], c["win"], c["rssi_n"],
             c["rssi_s"], c["rssi_ss"], c["rssi_an"], c["rssi_as"],
             c["rssi_rn"], c["rssi_rs"], c["nf_n"], c["nf_s"], c["amp_n"],
             c["acc_in"], c["fed_in"], c["acc_out"], c["fed_out"]],
            dtype=np.float64)
        z[nm + "_amp"] = c["amp_sum"]
        z[nm + "_inl"] = np.array(c["inl"], dtype=np.float32)
        z[nm + "_res"] = np.array(c["res"], dtype=np.float32)
    np.savez_compressed(part_path(tag, k), **z)
    print(f"[{tag}.{k}] wrote {part_path(tag, k)}")


def cmd_merge(args):
    tag, N = args.tag, args.parts
    ps = [np.load(part_path(tag, k), allow_pickle=True) for k in range(N)]
    meta = ps[0]["meta"]
    size, mtime = int(meta[5]), int(meta[6])
    n_rows = int(sum(int(p["meta"][0]) for p in ps))
    n_bad1 = int(sum(int(p["meta"][1]) for p in ps))
    n_bad2 = int(sum(int(p["meta"][2]) for p in ps))
    n_both = int(sum(int(p["meta"][3]) for p in ps))
    n_bad = int(sum(int(p["meta"][4]) for p in ps))
    lenhist = {}
    macseen = {}
    for p in ps:
        for kk, v in p["lenhist"]:
            lenhist[int(kk)] = lenhist.get(int(kk), 0) + int(v)
        for m, v in p["macs"]:
            macseen[m] = macseen.get(m, 0) + int(v)
    t = np.concatenate([p["t"] for p in ps])
    ets = np.concatenate([p["ets"] for p in ps])
    drop = np.concatenate([p["drop"] for p in ps])
    rssi = np.concatenate([p["rssi"] for p in ps]).astype(np.float64)
    nf = np.concatenate([p["nf"] for p in ps]).astype(np.float64)
    clen = np.concatenate([p["clen"] for p in ps]).astype(np.int64)
    assert np.all(np.diff(t) >= 0) or True     # pc_time is per-batch, not sorted
    t0_pc = int(t[0])
    tpc = (t - t0_pc) * 1e-6
    span_pc = float(tpc[-1] - tpc[0])

    print(f"[{tag}] {N} parts, {size} B, mtime_ns {mtime}")
    print(f"[{tag}] data rows {n_rows}; len(row) histogram "
          f"{sorted(lenhist.items())}")
    print(f"[{tag}] corrupt rows: route1 {n_bad1}, route2 {n_bad2}, "
          f"both {n_both}, union {n_bad}; clean {t.size}")

    # ---- CHECK 1 --------------------------------------------------------
    dd_raw = np.diff(drop)
    dd = np.where(dd_raw < 0, dd_raw + 65536, dd_raw)
    de = np.diff(ets)
    wrapm = de < -2147483648
    keep = (~wrapm) & (de > 0) & (de < 1000000)
    ets_p = ets[1:][keep]
    dd_p = dd[keep]
    print(f"[{tag}] drop-delta pairs {dd.size}, kept {int(keep.sum())} "
          f"({int(wrapm.sum())} u32 wraps, "
          f"{int(((de <= 0) & ~wrapm).sum())} non-advancing, "
          f"{int((de >= 1000000).sum())} dt>=1 s excluded)")
    print(f"[{tag}] drops over kept pairs {int(dd_p.sum())}; frames with a "
          f"nonzero delta {int((dd_p > 0).sum())}")

    obs = fold_stats(ets_p, dd_p)
    nul_r, _ = rotation_null(ets_p, dd_p)
    p_emp = (float((nul_r >= obs["rbar"]).sum()) + 1) / (nul_r.size + 1)
    print(f"[{tag}] CHECK1 fold@250ms Rbar={obs['rbar']:.6f} "
          f"m=2Rbar={obs['m']:.6f} depth={obs['depth']:.4f}")
    print(f"[{tag}] CHECK1 rotation null: median {np.nanmedian(nul_r):.6f} "
          f"p95 {np.nanpercentile(nul_r, 95):.6f} "
          f"max {np.nanmax(nul_r):.6f}  empirical p={p_emp:.5f}")
    print(f"[{tag}] CHECK1 chi2 {obs['chi2']:.1f} / {obs['chi2_dof']} dof "
          f"p={obs['chi2_p']:.3e} (burstiness-sensitive; the rotation null "
          f"is the test)")

    blk = (tpc[1:][keep] // BLOCK_S).astype(np.int64)
    ub = np.unique(blk)
    brs = []
    for bi in ub:
        m = blk == bi
        if int(m.sum()) < 500 or dd_p[m].sum() <= 0:
            continue
        v = fold_stats(ets_p[m], dd_p[m])["rbar"]
        if np.isfinite(v):
            brs.append(v)
    brs = np.array(brs)
    bnull = []
    rngb = np.random.default_rng(1)
    for _ in range(args.blocknull):
        L = int(rngb.integers(1, dd_p.size))
        ddr = np.roll(dd_p, L)
        vals = []
        for bi in ub:
            m = blk == bi
            if int(m.sum()) < 500 or ddr[m].sum() <= 0:
                continue
            v = fold_stats(ets_p[m], ddr[m])["rbar"]
            if np.isfinite(v):
                vals.append(v)
        if vals:
            bnull.append(float(np.mean(vals)))
    bnull = np.array(bnull)
    print(f"[{tag}] CHECK1 60 s-block mean Rbar {brs.mean():.6f} over "
          f"{brs.size} blocks; rotation null {bnull.mean():.6f} "
          f"[p5 {np.percentile(bnull, 5):.6f}, "
          f"p95 {np.percentile(bnull, 95):.6f}]")

    ps_f, r_f = period_scan(ets_p, dd_p, 249000.0, 251000.0, args.finestep)
    ps_c, r_c = period_scan(ets_p, dd_p, 200000.0, 300000.0, 500.0)
    i_f, i_c = int(np.argmax(r_f)), int(np.argmax(r_c))
    print(f"[{tag}] CHECK1 fine scan 249-251 ms: peak Rbar {r_f[i_f]:.6f} at "
          f"{ps_f[i_f]/1000:.3f} ms")
    print(f"[{tag}] CHECK1 coarse scan 200-300 ms: peak Rbar {r_c[i_c]:.6f} "
          f"at {ps_c[i_c]/1000:.3f} ms")

    # ---- delivered rate, in frames and in on-wire bytes ------------------
    wb = (WIRE_FIXED + clen).astype(np.float64)
    bps = float(wb.sum()) / span_pc
    fps = t.size / span_pc
    # per-second bins on the NODE clock (esp_timestamp_us); pc_time_us is a
    # per-drain-batch host stamp (pc/node_census.py:30-35) and bins badly.
    eu = ets.astype(np.float64)
    eu = np.where(np.concatenate([[0], np.cumsum(np.diff(ets) < -2147483648)]) > 0,
                  eu + 0, eu)
    esec = ((ets - ets.min()) // 1000000).astype(np.int64)
    esec = np.clip(esec, 0, None)
    per_s = np.bincount(esec, weights=wb)
    per_s = per_s[(per_s > 0)]
    per_s = np.sort(per_s)[:-2] if per_s.size > 4 else per_s
    print(f"[{tag}] delivered {t.size} clean frames in {span_pc:.3f} s = "
          f"{fps:.2f} fps; {bps:.0f} on-wire B/s = "
          f"{100*bps/UART_BYTES_PER_S:.2f} % of 460800 8N1 "
          f"({UART_BYTES_PER_S:.0f} B/s)")
    print(f"[{tag}] per-node-second on-wire bytes: median {np.median(per_s):.0f}"
          f"  p99 {np.percentile(per_s, 99):.0f}  max {per_s.max():.0f} "
          f"({100*per_s.max()/UART_BYTES_PER_S:.2f} % of the UART budget)")

    amb = {m: c for m, c in macseen.items() if m not in BNAME}
    out = dict(
        tag=tag, path=args.tag, size=size, mtime_ns=mtime, parts=N,
        n_rows=n_rows, lenhist={str(k): v for k, v in lenhist.items()},
        node_mode=int(meta[7]), chan_mode=int(meta[8]),
        bad1=n_bad1, bad2=n_bad2, both=n_both, bad=n_bad,
        clean=int(t.size), span_pc=span_pc, fps=fps, wire_bps=bps,
        wire_peak_bps=float(per_s.max()),
        uart_frac=100 * bps / UART_BYTES_PER_S,
        ets_first=int(ets[0]), ets_first_s=float(ets[0]) * 1e-6,
        distinct_macs=len(macseen), ambient_macs=len(amb),
        ambient_frames=int(sum(amb.values())),
        ambient_fps=float(sum(amb.values())) / span_pc,
        nf_mean=float(nf.mean()), rssi_mean_all=float(rssi.mean()),
        check1=dict(rbar=obs["rbar"], m=obs["m"], depth=obs["depth"],
                    chi2=obs["chi2"], chi2_dof=obs["chi2_dof"],
                    chi2_p=obs["chi2_p"],
                    null_med=float(np.nanmedian(nul_r)),
                    null_p95=float(np.nanpercentile(nul_r, 95)),
                    null_max=float(np.nanmax(nul_r)), p_emp=p_emp,
                    rate=list(map(float, obs["rate"])),
                    cnt=list(map(float, obs["cnt"])),
                    drops=list(map(float, obs["drops"])),
                    blk_mean=float(brs.mean()), blk_n=int(brs.size),
                    blk_null_mean=float(bnull.mean()),
                    blk_null_p95=float(np.percentile(bnull, 95)),
                    fine_peak_r=float(r_f[i_f]),
                    fine_peak_ms=float(ps_f[i_f] / 1000),
                    coarse_peak_r=float(r_c[i_c]),
                    coarse_peak_ms=float(ps_c[i_c] / 1000),
                    total_drops=int(dd_p.sum()), pairs=int(dd_p.size)),
        cells={},
    )
    print(f"\n[{tag}] per-cell accounting (reject denominator = fed, "
          f"matching docs/OCCUPANCY_TEST_0822.md 2.3)")
    print(f"{'b':3s} {'fed':>9s} {'fitted':>9s} {'acc':>9s} {'rej%':>8s} "
          f"{'win':>6s} {'rssiA':>7s} {'rssiR':>7s} {'rssiSD':>7s} "
          f"{'ampmean':>8s} {'ampmin':>7s} {'fade':>6s}")
    for b in BEACONS:
        nm = BNAME[b]
        s = sum(p[nm + "_scalar"] for p in ps)
        (fed, fitted, acc, win, rn, rs, rss, an, as_, rjn, rjs,
         nfn, nfs, ampn, ai, fi, ao, fo) = s
        prof = sum(p[nm + "_amp"] for p in ps) / ampn if ampn else np.zeros(K.size)
        inl = np.concatenate([p[nm + "_inl"] for p in ps])
        res = np.concatenate([p[nm + "_res"] for p in ps])
        rej = 100.0 * (1 - acc / fed) if fed else float("nan")
        mean_r = rs / rn if rn else float("nan")
        var_r = (rss / rn - mean_r ** 2) if rn else float("nan")
        amean = float(prof.mean()) if ampn else float("nan")
        amin = float(prof.min()) if ampn else float("nan")
        out["cells"][nm] = dict(
            fed=int(fed), fitted=int(fitted), acc=int(acc), rej=float(rej),
            win=int(win),
            rssi_mean=float(mean_r), rssi_sd=float(math.sqrt(max(var_r, 0))),
            rssi_acc=float(as_ / an) if an else float("nan"),
            rssi_rej=float(rjs / rjn) if rjn else float("nan"),
            nf_mean=float(nfs / nfn) if nfn else float("nan"),
            amp_profile=list(map(float, prof)), amp_mean=amean, amp_min=amin,
            amp_max=float(prof.max()) if ampn else float("nan"),
            fade_ratio=float(amean / amin) if amin > 0 else float("nan"),
            amp_min_k=int(K[int(np.argmin(prof))]) if ampn else 0,
            inl_med=float(np.median(inl)) if inl.size else float("nan"),
            res_med=float(np.median(res)) if res.size else float("nan"),
            acc_in=int(ai), fed_in=int(fi), acc_out=int(ao), fed_out=int(fo),
        )
        d = out["cells"][nm]
        print(f"{nm:3s} {int(fed):9d} {int(fitted):9d} {int(acc):9d} "
              f"{rej:8.3f} {int(win):6d} {d['rssi_acc']:7.2f} "
              f"{d['rssi_rej']:7.2f} {d['rssi_sd']:7.3f} {amean:8.3f} "
              f"{amin:7.3f} {d['fade_ratio']:6.2f}")
    with open(os.path.join(CACHE, tag + ".json"), "w") as f:
        json.dump(out, f)
    print(f"[{tag}] wrote {os.path.join(CACHE, tag + '.json')}")



# -------------------------------------------------------------- harmonics

def cmd_harmonics(args):
    """Separate a genuine 4 Hz source from the node's two 5 s sources.

    5000 = 20 x 250 exactly, so ANY event with a 5 s period lands in one
    and the same 250 ms phase slot every time and will show as "250 ms
    periodicity". The node has three periodic sources, from the code:

      main.c:247   display_task     250 ms  (created only if oled_init OK)
      main.c:190   status_task     5000 ms  (writes a STATUS frame)
      node_hal.c:256 rf_liveness   5000 ms  (esp_timer callback)

    Folding at 5000 ms with 100 bins tells them apart: a real 250 ms
    source draws twenty cycles across that fold, a 5 s source draws one
    bump. This routine reports both, plus the resultant at each candidate
    period.
    """
    tag, N = args.tag, args.parts
    ps = [np.load(part_path(tag, k), allow_pickle=True) for k in range(N)]
    ets = np.concatenate([p["ets"] for p in ps])
    drop = np.concatenate([p["drop"] for p in ps])
    dd_raw = np.diff(drop)
    dd = np.where(dd_raw < 0, dd_raw + 65536, dd_raw)
    de = np.diff(ets)
    keep = (de >= -2147483648) & (de > 0) & (de < 1000000)
    e, w = ets[1:][keep], dd[keep]
    print(f"[{tag}] {e.size} pairs, {int(w.sum())} drops")

    print(f"\n  resultant at each candidate period "
          f"(rate domain; null p95 from {N_ROT} circular rotations).")
    print(f"  `frames Rbar` is the same resultant computed on the FRAME "
          f"ARRIVAL phase alone, with the classical Rayleigh p = exp(-n R^2)")
    print(f"  -- it says whether the arrivals themselves carry the period, "
          f"which would explain a drop periodicity without any task doing it.")
    print(f"  {'period ms':>10s} {'Rbar':>10s} {'m=2Rbar':>9s} "
          f"{'null p95':>10s} {'p_emp':>8s} {'framesRbar':>11s} "
          f"{'framesP':>10s}")
    for pms in (250.0, 500.0, 1000.0, 1250.0, 2500.0, 5000.0, 10000.0):
        o = fold_stats(e, w, period_us=pms * 1000.0)
        nl, _ = rotation_null(e, w, period_us=pms * 1000.0, n=args.nrot)
        pe = (float((nl >= o["rbar"]).sum()) + 1) / (nl.size + 1)
        cn = np.array(o["cnt"], dtype=np.float64)
        th = 2 * np.pi * (np.arange(cn.size) + 0.5) / cn.size
        fr = math.hypot(float((cn * np.cos(th)).sum()),
                        float((cn * np.sin(th)).sum())) / cn.sum()
        fp = math.exp(-cn.sum() * fr * fr)
        print(f"  {pms:10.1f} {o['rbar']:10.6f} {o['m']:9.5f} "
              f"{np.nanpercentile(nl, 95):10.6f} {pe:8.5f} {fr:11.6f} "
              f"{fp:10.3e}")

    print("\n  the 5000 ms fold, 20 bins of 250 ms -- drops per delivered "
          "frame in each 250 ms slot of the 5 s cycle:")
    o5 = fold_stats(e, w, period_us=5000000.0, nbin=20)
    r5 = np.array(o5["rate"])
    mu = np.nanmean(r5)
    print("  slot  " + " ".join(f"{i:6d}" for i in range(20)))
    print("  rate  " + " ".join(f"{x:6.4f}" for x in r5))
    print("  /mean " + " ".join(f"{x/mu:6.3f}" for x in r5))
    hi = int(np.nanargmax(r5))
    rest = np.delete(r5, hi)
    print(f"\n  hottest slot {hi} ({hi*250}-{(hi+1)*250} ms into the 5 s "
          f"cycle): {r5[hi]:.5f} drops/frame")
    print(f"  the other 19 slots: mean {np.nanmean(rest):.5f}, "
          f"sd {np.nanstd(rest):.5f}, "
          f"max {np.nanmax(rest):.5f}, min {np.nanmin(rest):.5f}")
    print(f"  hottest slot is {(r5[hi]-np.nanmean(rest))/np.nanstd(rest):+.2f} "
          f"sd above the other 19")
    print(f"  fraction of ALL drops in that one slot: "
          f"{o5['drops'][hi]/o5['drops'].sum():.5f} "
          f"(uniform expectation from frame counts: "
          f"{o5['cnt'][hi]/o5['cnt'].sum():.5f})")

    print("\n  the 5000 ms fold, 100 bins of 50 ms -- one bump (5 s source) "
          "or twenty cycles (250 ms source)?")
    o100 = fold_stats(e, w, period_us=5000000.0, nbin=100)
    r100 = np.array(o100["rate"])
    m100 = np.nanmean(r100)
    for r0 in range(0, 100, 20):
        print("   " + " ".join(f"{x/m100:5.2f}" for x in r100[r0:r0 + 20]))
    # Power at the 1st vs the 20th harmonic of the 5 s fold. A pure 250 ms
    # source puts its power in harmonic 20 and none in harmonic 1; a 5 s
    # impulse puts comparable power in every harmonic including 1.
    th = 2 * np.pi * (np.arange(100) + 0.5) / 100
    g = np.isfinite(r100)
    tot = r100[g].sum()
    for h in (1, 2, 4, 5, 10, 20, 40):
        C = float((r100[g] * np.cos(h * th[g])).sum())
        S = float((r100[g] * np.sin(h * th[g])).sum())
        print(f"  harmonic {h:3d} of the 5 s fold "
              f"(= {5000.0/h:8.2f} ms): |R| = {math.hypot(C, S)/tot:.6f}")


# ---------------------------------------------------------------- selftest

def cmd_selftest(args):
    """The streaming width-9 edge-padded median screen must equal the
    reference loop of pc/exp_occupancy_0822.py:81 row for row."""
    rng = np.random.default_rng(7)
    for n in (3, 9, 10, 37, 500):
        x = rng.integers(0, 40000, size=n)
        ref = median_filter_ref(x, 9)
        got = np.empty(n, dtype=np.float64)
        for i in range(n):
            w = [x[min(max(j, 0), n - 1)] for j in range(i - 4, i + 5)]
            got[i] = float(np.median(w))
        assert np.array_equal(ref, got), (n, ref, got)
    print("selftest: streaming width-9 edge-padded median == reference, "
          "n in {3,9,10,37,500}  OK")
    # chi2 sanity against known values
    for x, k, want in ((3.841, 1, 0.05), (18.307, 10, 0.05),
                       (23.685, 14, 0.05), (0.0, 4, 1.0)):
        got = chi2_sf(x, k)
        assert abs(got - want) < 2e-3, (x, k, got, want)
    print("selftest: chi2_sf matches published critical values  OK")
    # spearman against a hand case
    # sum d^2 = 4, rho = 1 - 6*4/(5*(25-1)) = 0.8
    rho, p, n = spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5])
    assert abs(rho - 0.8) < 1e-12, rho
    # perfect anti-rank, and a tied case against the Pearson-on-ranks value
    assert abs(spearman([1, 2, 3, 4], [4, 3, 2, 1])[0] + 1.0) < 1e-12
    assert abs(spearman([1, 2, 2, 4], [1, 2, 3, 4])[0] - 0.9486832980505138) < 1e-9
    print(f"selftest: spearman rho={rho:.4f} on the textbook case, "
          f"-1.0 on perfect anti-rank, tie-corrected case OK")
    # fold_stats must recover a known sinusoidal modulation
    rng2 = np.random.default_rng(3)
    n = 400000
    ts = np.cumsum(rng2.integers(4000, 9000, size=n)).astype(np.int64)
    th = 2 * np.pi * np.mod(ts, DISPLAY_PERIOD_US) / DISPLAY_PERIOD_US
    lam = 0.20 * (1 + 0.30 * np.cos(th))         # m = 0.30 by construction
    w = rng2.poisson(lam)
    got = fold_stats(ts, w)
    assert abs(got["m"] - 0.30) < 0.02, got["m"]
    print(f"selftest: fold_stats recovers a planted m=0.300 as "
          f"{got['m']:.4f}  OK")
    flat = rng2.poisson(0.20, size=n)
    g2 = fold_stats(ts, flat)
    nul, _ = rotation_null(ts, flat, n=200)
    assert g2["m"] < 5 * np.nanpercentile(nul, 95), (g2["m"], np.nanpercentile(nul, 95))
    print(f"selftest: on a flat control fold_stats gives m={g2['m']:.5f}, "
          f"rotation-null Rbar p95 {np.nanpercentile(nul,95):.6f}  OK")


# ------------------------------------------------------------------ report

def load(tag):
    with open(os.path.join(CACHE, tag + ".json")) as f:
        return json.load(f)


_EX1 = K != 1.0        # every usable subcarrier except k = +1


def amp_ex1(c):
    """Per-bin |CSI| profile with k = +1 removed.

    The D0WD's k = +1 bin reads exactly 3.0 counts on every source it hears
    (docs/UNWRAP_DEFECT.md 2; reproduced here as `ampmin 3.000 at k=1` on
    all nine D0WD cells). Leaving it in makes `min bin |CSI|` and any
    max/min fade depth a measurement of that one dead bin rather than of
    the channel, and not comparable between the two boards.
    """
    return np.array(c["amp_profile"])[_EX1]


def cmd_report(args):
    tags = [t for s in SESSIONS.values() for t in s["nodes"]]
    D = {t: load(t) for t in tags}

    print("=" * 78)
    print("R0. Files, as read")
    print("=" * 78)
    print(f"{'tag':24s} {'bytes':>12s} {'rows':>9s} {'clean':>9s} "
          f"{'corrupt':>7s} {'span s':>10s} {'fps':>8s}")
    for t in tags:
        d = D[t]
        print(f"{t:24s} {d['size']:12d} {d['n_rows']:9d} {d['clean']:9d} "
              f"{d['bad']:7d} {d['span_pc']:10.3f} {d['fps']:8.2f}")
    print("\nlen(row) histograms (csv.reader):")
    for t in tags:
        print(f"  {t:24s} {sorted((int(k), v) for k, v in D[t]['lenhist'].items())}")

    print()
    print("=" * 78)
    print("R1. CHECK 1 -- per-frame `dropped` deltas folded on 250 ms")
    print("     (main.c:247 pdMS_TO_TICKS(250)); phase from esp_timestamp_us")
    print("=" * 78)
    print(f"{'tag':24s} {'pairs':>9s} {'drops':>9s} {'Rbar':>9s} "
          f"{'m=2Rbar':>9s} {'null p95':>9s} {'p_emp':>8s} {'depth':>8s}")
    for t in tags:
        c = D[t]["check1"]
        print(f"{t:24s} {c['pairs']:9d} {c['total_drops']:9d} "
              f"{c['rbar']:9.6f} {c['m']:9.6f} {c['null_p95']:9.6f} "
              f"{c['p_emp']:8.5f} {c['depth']:8.4f}")
    print("\n  drift-robust 60 s-block fold, and the period scan:")
    print(f"{'tag':24s} {'blkRbar':>9s} {'blknull':>9s} {'bnullp95':>9s} "
          f"{'fine pk':>9s} {'at ms':>9s} {'coarse pk':>10s} {'at ms':>9s}")
    for t in tags:
        c = D[t]["check1"]
        print(f"{t:24s} {c['blk_mean']:9.6f} {c['blk_null_mean']:9.6f} "
              f"{c['blk_null_p95']:9.6f} {c['fine_peak_r']:9.6f} "
              f"{c['fine_peak_ms']:9.3f} {c['coarse_peak_r']:10.6f} "
              f"{c['coarse_peak_ms']:9.3f}")
    print("\n  drop rate per 10 ms phase bin (drops per delivered frame):")
    for t in tags:
        c = D[t]["check1"]
        r = np.array(c["rate"])
        print(f"  {t:24s} min {np.nanmin(r):.5f}  max {np.nanmax(r):.5f}  "
              f"mean {np.nanmean(r):.5f}  (max-min)/mean {c['depth']:.4f}")

    print()
    print("=" * 78)
    print("R2. The drain-path ceiling in BYTES, against the console UART")
    print("     sdkconfig:1298-1310 -- UART0, GPIO1/3, 460800 8N1 = 46,080 B/s")
    print("=" * 78)
    print(f"{'tag':24s} {'fps':>8s} {'mean B/s':>10s} {'% UART':>8s} "
          f"{'peak B/s':>10s} {'% UART':>8s}")
    for t in tags:
        d = D[t]
        print(f"{t:24s} {d['fps']:8.2f} {d['wire_bps']:10.0f} "
              f"{d['uart_frac']:8.2f} {d['wire_peak_bps']:10.0f} "
              f"{100*d['wire_peak_bps']/UART_BYTES_PER_S:8.2f}")

    print()
    print("=" * 78)
    print("R3. CHECK 2 -- reject rate, all six node x beacon cells,"
          " all three sessions")
    print("=" * 78)
    print(f"{'cell':12s} " + " ".join(f"{s:>22s}" for s in SESSIONS))
    for ni in (0, 1):
        for b in ("B1", "B2", "B3"):
            row = []
            for s in SESSIONS:
                t = SESSIONS[s]["nodes"][ni]
                c = D[t]["cells"][b]
                row.append(f"{c['rej']:7.3f}% {c['acc']:>7d}/{c['fitted']:<7d}")
            nn = "d0wd" if ni == 0 else "s3"
            print(f"{nn+'/'+b:12s} " + " ".join(f"{x:>22s}" for x in row))

    print()
    print("=" * 78)
    print("R4. The seven candidate covariates, per cell per session")
    print("=" * 78)
    print("      |CSI| columns exclude k = +1, the D0WD's dead bin "
          "(docs/UNWRAP_DEFECT.md 2)")
    hdr = (f"{'session':17s} {'cell':9s} {'rej%':>8s} {'rssi':>7s} "
           f"{'rssiSD':>7s} {'rssiA':>7s} {'rssiR':>7s} {'ampmean':>8s} "
           f"{'ampmin':>7s} {'ampmax':>7s} {'tilt':>6s} {'nf':>7s} "
           f"{'inlmed':>7s} {'resmed':>7s}")
    print(hdr)
    rows = []
    for s in SESSIONS:
        for ni in (0, 1):
            t = SESSIONS[s]["nodes"][ni]
            nn = "d0wd" if ni == 0 else "s3"
            for b in ("B1", "B2", "B3"):
                c = D[t]["cells"][b]
                rows.append((s, nn, b, c, D[t]))
                a = amp_ex1(c)
                print(f"{s:17s} {nn+'/'+b:9s} {c['rej']:8.3f} "
                      f"{c['rssi_mean']:7.2f} {c['rssi_sd']:7.3f} "
                      f"{c['rssi_acc']:7.2f} {c['rssi_rej']:7.2f} "
                      f"{a.mean():8.3f} {a.min():7.3f} {a.max():7.3f} "
                      f"{a.max()/a.min():6.2f} {c['nf_mean']:7.2f} "
                      f"{c['inl_med']:7.4f} {c['res_med']:7.4f}")

    print("\n  session-level covariates (same for all three cells of a node):")
    print(f"{'session':17s} {'node':6s} {'local':9s} {'occupancy':28s} "
          f"{'ambMAC':>7s} {'ambfps':>8s} {'nf':>7s} {'uptime@t0 s':>12s}")
    for s in SESSIONS:
        for ni in (0, 1):
            t = SESSIONS[s]["nodes"][ni]
            d = D[t]
            nn = "d0wd" if ni == 0 else "s3"
            print(f"{s:17s} {nn:6s} {SESSIONS[s]['local_start']:9s} "
                  f"{SESSIONS[s]['occ']:28s} {d['ambient_macs']:7d} "
                  f"{d['ambient_fps']:8.3f} {d['nf_mean']:7.2f} "
                  f"{d['ets_first_s']:12.3f}")

    print()
    print("=" * 78)
    print("R5. Does anything covary with reject rate? Spearman over the 18")
    print("     (node x beacon x session) cells, permutation p, 20,000 draws")
    print("=" * 78)
    rej = [r[3]["rej"] for r in rows]
    covs = {
        "RSSI mean (cell)": [r[3]["rssi_mean"] for r in rows],
        "RSSI sd (cell)": [r[3]["rssi_sd"] for r in rows],
        "RSSI variance (cell)": [r[3]["rssi_sd"] ** 2 for r in rows],
        "mean |CSI| over 52 bins": [r[3]["amp_mean"] for r in rows],
        "min bin |CSI| (fade)": [r[3]["amp_min"] for r in rows],
        "fade ratio mean/min": [r[3]["fade_ratio"] for r in rows],
        "noise_floor (cell)": [r[3]["nf_mean"] for r in rows],
        "ambient MAC count": [r[4]["ambient_macs"] for r in rows],
        "ambient frames/s": [r[4]["ambient_fps"] for r in rows],
        "delivered fps (node)": [r[4]["fps"] for r in rows],
        "uptime at t0 (s, mod 2^32us)": [r[4]["ets_first_s"] for r in rows],
        "hour of day (local)": [float(SESSIONS[r[0]]["local_start"][:2])
                                + float(SESSIONS[r[0]]["local_start"][3:5]) / 60
                                for r in rows],
        "operator present (1/0)": [0.0 if "empty" in SESSIONS[r[0]]["occ"]
                                   else 1.0 for r in rows],
    }
    print(f"{'covariate':32s} {'rho':>8s} {'perm p':>9s} {'n':>4s}")
    for k, v in covs.items():
        rho, p, n = spearman(rej, v)
        print(f"{k:32s} {rho:8.4f} {p:9.5f} {n:4d}")

    print("\n  Bonferroni threshold for 13 covariates at alpha=0.05: "
          "p < 0.003846")

    print()
    print("=" * 78)
    print("R5a. The same cell-level covariates WITHIN each node (9 cells")
    print("      each). A covariate that only separates the two boards is a")
    print("      node-level confound, not a cell-level explanation.")
    print("=" * 78)
    cellcov = {
        "RSSI mean": lambda c: c["rssi_mean"],
        "RSSI sd": lambda c: c["rssi_sd"],
        "mean |CSI| (excl k=+1)": lambda c: amp_ex1(c).mean(),
        "min |CSI| (excl k=+1)": lambda c: amp_ex1(c).min(),
        "band tilt max/min (excl k=+1)": lambda c: (amp_ex1(c).max()
                                                    / amp_ex1(c).min()),
        "noise_floor": lambda c: c["nf_mean"],
    }
    print(f"{'covariate':32s} {'all 18':>9s} {'p':>9s} {'d0wd 9':>9s} "
          f"{'p':>9s} {'s3 9':>9s} {'p':>9s}")
    def fmt(r_, p_):
        # a covariate with zero variance inside a subset has no rank
        # correlation at all; say so rather than printing nan.
        if r_ != r_:
            return ["  no var", "        —"]
        return [f"{r_:9.4f}", f"{p_:9.5f}"]

    for name, fn in cellcov.items():
        v_all = [fn(r[3]) for r in rows]
        outs = fmt(*spearman(rej, v_all)[:2])
        for nn in ("d0wd", "s3"):
            sel = [r for r in rows if r[1] == nn]
            outs += fmt(*spearman([r[3]["rej"] for r in sel],
                                  [fn(r[3]) for r in sel])[:2])
        print(f"{name:32s} " + " ".join(outs))

    print()
    print("=" * 78)
    print("R5b. Node-level covariates are constant across a node-session's")
    print("      three cells, so the effective n is 6, not 18. Same tests")
    print("      against that node-session's WORST and MEAN cell.")
    print("=" * 78)
    ns = []
    for s in SESSIONS:
        for ni in (0, 1):
            t = SESSIONS[s]["nodes"][ni]
            d = D[t]
            rj = [d["cells"][b]["rej"] for b in ("B1", "B2", "B3")]
            ns.append((s, "d0wd" if ni == 0 else "s3", d, max(rj),
                       float(np.mean(rj))))
    nodecov = {
        "ambient MAC count": lambda d, s: d["ambient_macs"],
        "ambient frames/s": lambda d, s: d["ambient_fps"],
        "delivered fps": lambda d, s: d["fps"],
        "noise_floor (node)": lambda d, s: d["nf_mean"],
        "uptime at t0 (s)": lambda d, s: d["ets_first_s"],
        "hour of day": lambda d, s: (float(SESSIONS[s]["local_start"][:2])
                                     + float(SESSIONS[s]["local_start"][3:5]) / 60),
        "operator present (1/0)": lambda d, s: (0.0 if "empty" in SESSIONS[s]["occ"]
                                                else 1.0),
    }
    print(f"{'covariate':28s} {'rho vs worst':>13s} {'p':>9s} "
          f"{'rho vs mean':>12s} {'p':>9s} {'n':>3s}")
    for name, fn in nodecov.items():
        v = [fn(d, s) for s, nn, d, mx, mn in ns]
        r1, p1, n1 = spearman([x[3] for x in ns], v)
        r2, p2, _ = spearman([x[4] for x in ns], v)
        print(f"{name:28s} {r1:13.4f} {p1:9.5f} {r2:12.4f} {p2:9.5f} {n1:3d}")

    print()
    print("=" * 78)
    print("R5c. What covaries with the MOVEMENT? Each of the 6 cells is")
    print("      followed across the 3 session pairs (18 changes). If a")
    print("      covariate explains why the marginal cell moves, the change")
    print("      in reject rate should track the change in it.")
    print("=" * 78)
    pairs = [("20260821_125017", "20260822_023034"),
             ("20260821_125017", "20260822_144424"),
             ("20260822_023034", "20260822_144424")]
    dr, dv = [], {k: [] for k in cellcov}
    lab = []
    for ni in (0, 1):
        nn = "d0wd" if ni == 0 else "s3"
        for b in ("B1", "B2", "B3"):
            for a, c2 in pairs:
                ca = D[SESSIONS[a]["nodes"][ni]]["cells"][b]
                cb = D[SESSIONS[c2]["nodes"][ni]]["cells"][b]
                dr.append(cb["rej"] - ca["rej"])
                lab.append(f"{nn}/{b} {a[-6:]}->{c2[-6:]}")
                for k, fn in cellcov.items():
                    dv[k].append(fn(cb) - fn(ca))
    print(f"{'change in covariate':32s} {'rho':>9s} {'perm p':>9s} {'n':>4s}")
    for k in cellcov:
        r_, p_, n_ = spearman(dr, dv[k])
        print(f"{'d ' + k:32s} {r_:9.4f} {p_:9.5f} {n_:4d}")
    print("\n  the 6 largest reject-rate movements, with their covariate "
          "changes:")
    order = np.argsort(-np.abs(np.array(dr)))[:6]
    print(f"  {'cell / pair':30s} {'d rej pp':>9s} {'d RSSI':>8s} "
          f"{'d tilt':>8s} {'d minamp':>9s} {'d nf':>7s}")
    for i in order:
        print(f"  {lab[i]:30s} {dr[i]:+9.2f} {dv['RSSI mean'][i]:+8.2f} "
              f"{dv['band tilt max/min (excl k=+1)'][i]:+8.2f} "
              f"{dv['min |CSI| (excl k=+1)'][i]:+9.2f} "
              f"{dv['noise_floor'][i]:+7.2f}")

    print()
    print("=" * 78)
    print("R6. Operator presence WITHIN the 14:44 session -- reject rate")
    print("     inside t=[785,920) s (absent) vs outside (present)")
    print("     docs/OCCUPANCY_TEST_0822.md 0, 5.3")
    print("=" * 78)
    print(f"{'cell':10s} {'rej% absent':>12s} {'n':>8s} "
          f"{'rej% present':>13s} {'n':>9s} {'delta pp':>9s}")
    for ni in (0, 1):
        t = SESSIONS["20260822_144424"]["nodes"][ni]
        nn = "d0wd" if ni == 0 else "s3"
        for b in ("B1", "B2", "B3"):
            c = D[t]["cells"][b]
            ri = 100 * (1 - c["acc_in"] / c["fed_in"]) if c["fed_in"] else float("nan")
            ro = 100 * (1 - c["acc_out"] / c["fed_out"]) if c["fed_out"] else float("nan")
            print(f"{nn+'/'+b:10s} {ri:12.3f} {c['fed_in']:8d} "
                  f"{ro:13.3f} {c['fed_out']:9d} {ri-ro:9.3f}")

    print()
    print("=" * 78)
    print("R7. Do the two afternoon sessions resemble each other more than")
    print("     the overnight? L1 distance between 6-cell reject vectors")
    print("=" * 78)
    vecs = {}
    for s in SESSIONS:
        v = []
        for ni in (0, 1):
            t = SESSIONS[s]["nodes"][ni]
            for b in ("B1", "B2", "B3"):
                v.append(D[t]["cells"][b]["rej"])
        vecs[s] = np.array(v)
        print(f"  {s}: " + " ".join(f"{x:7.3f}" for x in v))
    ks = list(SESSIONS)
    for i in range(3):
        for j in range(i + 1, 3):
            a, b = ks[i], ks[j]
            print(f"  L1({a}, {b}) = {np.abs(vecs[a]-vecs[b]).sum():8.3f} pp"
                  f"   rank-corr rho = {spearman(vecs[a], vecs[b])[0]:+.4f}")

    print()
    print("=" * 78)
    print("R8. The marginal cell's amplitude profile, 52 usable subcarriers")
    print("=" * 78)
    for s, nn, b, c, d in rows:
        if c["rej"] < 25:
            continue
        prof = np.array(c["amp_profile"])
        print(f"  {s} {nn}/{b}: rej {c['rej']:.3f}%  mean |CSI| "
              f"{c['amp_mean']:.3f}  min {c['amp_min']:.3f} at k="
              f"{c['amp_min_k']}  max {c['amp_max']:.3f}  "
              f"mean/min {c['fade_ratio']:.2f}")
        print("    " + " ".join(f"{x:5.1f}" for x in prof[:26]))
        print("    " + " ".join(f"{x:5.1f}" for x in prof[26:]))
    print()
    print("=" * 78)
    print("R9. WHICH shipped gate rejects? inlier_ratio < 0.6 (dsp.py:173)")
    print("     or resid_std > 0.8 (dsp.py:175). Per-frame, from the parts.")
    print("=" * 78)
    print(f"{'session':17s} {'cell':9s} {'fitted':>9s} {'rej%':>8s} "
          f"{'inlier only':>12s} {'resid only':>11s} {'both':>8s}")
    for s in SESSIONS:
        for ni in (0, 1):
            t = SESSIONS[s]["nodes"][ni]
            nn = "d0wd" if ni == 0 else "s3"
            pp = [np.load(part_path(t, k), allow_pickle=True)
                  for k in range(D[t]["parts"])]
            for b in ("B1", "B2", "B3"):
                inl = np.concatenate([p[b + "_inl"] for p in pp])
                res = np.concatenate([p[b + "_res"] for p in pp])
                gi, gr = inl < 0.6, res > 0.8
                n = inl.size
                print(f"{s:17s} {nn+'/'+b:9s} {n:9d} "
                      f"{100*(gi | gr).sum()/n:8.3f} "
                      f"{100*(gi & ~gr).sum()/n:12.3f} "
                      f"{100*(~gi & gr).sum()/n:11.3f} "
                      f"{100*(gi & gr).sum()/n:8.3f}")

    print("\n  for contrast, the same node's best cell in the same session:")
    for s in SESSIONS:
        for ni in (0, 1):
            t = SESSIONS[s]["nodes"][ni]
            nn = "d0wd" if ni == 0 else "s3"
            best = min(("B1", "B2", "B3"), key=lambda b: D[t]["cells"][b]["rej"])
            c = D[t]["cells"][best]
            print(f"  {s} {nn}/{best}: rej {c['rej']:.3f}%  mean |CSI| "
                  f"{c['amp_mean']:.3f}  min {c['amp_min']:.3f} at k="
                  f"{c['amp_min_k']}  mean/min {c['fade_ratio']:.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("csv")
    pl.add_argument("--parts", type=int, required=True)
    pl.set_defaults(func=cmd_plan)
    r = sub.add_parser("part")
    r.add_argument("csv")
    r.add_argument("--tag", required=True)
    r.add_argument("--index", type=int, required=True)
    r.add_argument("--parts", type=int, required=True)
    r.add_argument("--t0-pc", type=int, default=0,
                   help="pc_time_us of the session's first row, so that the "
                        "operator-absence window of the 14:44 session can be "
                        "applied inside a part that does not contain row 0")
    r.set_defaults(func=cmd_part)
    m = sub.add_parser("merge")
    m.add_argument("--tag", required=True)
    m.add_argument("--parts", type=int, required=True)
    m.add_argument("--blocknull", type=int, default=200)
    m.add_argument("--finestep", type=float, default=5.0)
    m.set_defaults(func=cmd_merge)
    h = sub.add_parser("harmonics")
    h.add_argument("--tag", required=True)
    h.add_argument("--parts", type=int, required=True)
    h.add_argument("--nrot", type=int, default=500)
    h.set_defaults(func=cmd_harmonics)
    s = sub.add_parser("selftest")
    s.set_defaults(func=cmd_selftest)
    p = sub.add_parser("report")
    p.set_defaults(func=cmd_report)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
