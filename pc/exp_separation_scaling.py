#!/usr/bin/env python3
"""Does beacon separation improve with averaging time, or does it plateau?

One question, asked of the 2026-08-22 overnight capture over its empty-room
window only:

  1. ALLAN DEVIATION of the per-beacon SFO estimate against averaging time
     tau. Falling as tau^-1/2 => white noise, averaging longer buys
     separation. Flat or rising => flicker / random walk, and the limit is
     physical rather than statistical.
  2. WINDOW-LENGTH SWEEP. 64 .. 16384 frames per observation window,
     pairwise Mahalanobis separation matrix at each.
  3. GATE SWEEP. --max-resid x --min-inlier, separation against surviving
     windows: the trade-off curve, not one chosen point.

Design
------
The DSP is run ONCE per file and every per-frame result is cached; parts 1-3
are then re-derived from that cache. This is exact, not an approximation:

  * `rff.dsp.FrameEstimator` state (unwrap anchor, CFO finite difference)
    depends only on the order of a source's own frames and on nothing the
    gates do, so one pass serves every gate setting.
  * `rff.dsp.WindowAggregator` gating happens strictly after the estimator
    (`pc/rff/dsp.py:190-197`), and a window is emitted every `window`
    accepted frames with the buffer cleared. Re-chunking the cached
    accepted-frame sequence into consecutive groups of `window` therefore
    reproduces the aggregator exactly; `_reagg()` below asserts this against
    the real `WindowAggregator` on a sample.

`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` are
NOT used (`docs/CODE_INVENTORY.md` §4.2 C1/C2/C3: all three have the
DC/guard-band index wrong).

Parse
-----
`docs/POSITIVE_CONTROL_0822.md` §1.2 records that `cs.split(",", 128)` in
`pc/exp_overnight_0822.py:303` and `pc/exp_s3_sfo_steps.py:153,590` silently
drops every `csi_len = 128` row, because `maxsplit=128` returns AT MOST 129
items and a 128-value row yields exactly 128. This script uses
`np.fromstring(cs, sep=",")` — the same read as `pc/rff_offline.py:203` —
and counts 128- and 256-length rows separately so the defect cannot recur
unnoticed. `scan` also phase-estimates the 128-length ambient sources, which
is the check with teeth: a parser carrying the defect returns zero fits for
them.

Read-only on data/raw/. No serial port. Nothing staged, committed or pushed.

Usage (from the repo root):

  D=data/raw/d0wd_20260822_023034.csv
  S=data/raw/s3_20260822_023034.csv
  for p in 0 1 2 3 4 5; do
      python3 pc/exp_separation_scaling.py scan $D --tag d0wd --part $p --nparts 6
      python3 pc/exp_separation_scaling.py scan $S --tag s3   --part $p --nparts 6
  done
  python3 pc/exp_separation_scaling.py merge --tag d0wd --nparts 6 --expect-rows 2983560
  python3 pc/exp_separation_scaling.py merge --tag s3   --nparts 6 --expect-rows 3564005
  python3 pc/exp_separation_scaling.py report --tags d0wd,s3
"""
import argparse
import os
import pickle
import sys
import warnings
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rff.dsp import FrameEstimator, WindowAggregator          # noqa: E402
from rff.discriminator import Discriminator                    # noqa: E402

warnings.filterwarnings("ignore", category=DeprecationWarning)

# ---------------------------------------------------------------- constants

CACHE = os.environ.get("SEPSCALE_CACHE", "/tmp/sepscale_cache")

# Empty-room window, in seconds of pc_time_us since each file's first
# decodable row. Established in docs/POSITIVE_CONTROL_0822.md §0/§2.1: the
# operator re-entered the room at t ~ 23,067 s, and the capture's first
# minutes are power-on settle.
T_LO, T_HI = 300.0, 23000.0

B1 = "a4:f0:0f:77:91:20"      # reference beacon
B2 = "28:05:a5:2f:fa:48"
B3 = "f4:2d:c9:70:72:30"      # the clock twin (docs/LOT_HYPOTHESIS.md)
BEACONS = [B1, B2, B3]
BNAME = {B1: "B1", B2: "B2", B3: "B3"}

# yardsticks, quoted with their source
BETWEEN_UNIT_SD = 0.00237     # pc/exp_thermal_evidence.py:129
TWIN_DSFO = 0.00080           # pc/exp_lot_hypothesis.py:85-86
# pc/test_rff_synth.py test 6, 64-frame windows, 3-sigma criterion
FLOOR_QUANT = 1.8e-05
FLOOR_20DB = 3.5e-04

SHIPPED_WINDOW = 64
SHIPPED_MIN_INLIER = 0.6
SHIPPED_MAX_RESID = 0.8

WINDOWS = [64, 256, 1024, 4096, 16384]
RESIDS = [0.80, 0.30, 0.20, 0.16, 0.14, 0.12, 0.10]
INLIERS = [0.60, 0.70, 0.80, 0.90, 0.95]

TAU0 = 0.5                    # Allan bin width, seconds
MIN_BIN_FRAC = 0.90           # fraction of tau0-bins an average must cover


def cpath(tag, name):
    return os.path.join(CACHE, f"{tag}_{name}")


# -------------------------------------------------------------------- scan

class Growable:
    """Append-only typed column that grows geometrically."""

    def __init__(self, dtype, n=1 << 20):
        self.a = np.empty(n, dtype=dtype)
        self.n = 0

    def push(self, v):
        if self.n == self.a.size:
            self.a = np.resize(self.a, self.a.size * 2)
        self.a[self.n] = v
        self.n += 1

    def out(self):
        return self.a[:self.n].copy()


def line_range(path, part, nparts):
    """Byte range [lo, hi) for this part, snapped to line starts.

    lo is the first byte of a whole line; the reader keeps going past hi
    until the current line ends, so the parts tile the file exactly with
    neither loss nor duplication.
    """
    size = os.path.getsize(path)
    lo = size * part // nparts
    hi = size * (part + 1) // nparts
    if part == 0:
        with open(path, "rb") as f:
            f.readline()                   # header
            lo = f.tell()
    else:
        with open(path, "rb") as f:
            f.seek(lo)
            f.readline()                   # discard the partial line
            lo = f.tell()
    return lo, hi


def cmd_scan(args):
    os.makedirs(CACHE, exist_ok=True)
    tag = args.tag
    lo, hi = line_range(args.path, args.part, args.nparts)

    if args.part == 0:
        st = {"origin": None, "est": {}, "rows": 0,
              "len_rows": defaultdict(int),      # csi_len column value
              "vals_rows": defaultdict(int),     # parsed CSI vector length
              "naive_dropped": 0,                # what split(",",128) loses
              "bad_line": 0, "bad_field": 0,
              "node_ids": defaultdict(int), "mac_rows": defaultdict(int),
              "amb": {},
              "byte_hi": lo}
    else:
        with open(cpath(tag, f"state{args.part - 1}.pkl"), "rb") as f:
            st = pickle.load(f)
        assert st["byte_hi"] == lo, (
            f"part {args.part} starts at {lo} but part {args.part-1} ended "
            f"at {st['byte_hi']} — the parts do not tile the file")

    est = st["est"]
    origin = st["origin"]

    c_pc = Growable(np.int64)
    c_esp = Growable(np.int64)
    c_mac = Growable(np.int8)
    c_slope = Growable(np.float32)
    c_cfo = Growable(np.float32)
    c_inl = Growable(np.float32)
    c_res = Growable(np.float32)
    c_rssi = Growable(np.int16)

    bidx = {m: i for i, m in enumerate(BEACONS)}
    nan = np.float32("nan")

    with open(args.path, "rb") as fb:
        fb.seek(lo)
        for raw in fb:
            st["rows"] += 1
            line = raw.decode("ascii", "replace")
            p9 = line.split(",", 9)
            if len(p9) != 10:
                st["bad_line"] += 1
                if fb.tell() >= hi:
                    break
                continue
            rest = p9[9].rsplit(",", 3)
            if len(rest) != 4:
                st["bad_line"] += 1
                if fb.tell() >= hi:
                    break
                continue
            try:
                pc_us = int(p9[0])
                mac = p9[3].lower()
                rssi = int(p9[4])
                esp_us = int(p9[7])
                csi_len = int(p9[8])
                node_id = int(rest[1])
            except ValueError:
                st["bad_field"] += 1
                if fb.tell() >= hi:
                    break
                continue

            cs = rest[0]
            if cs[:1] == '"':
                cs = cs[1:-1] if cs[-1:] == '"' else cs[1:]
            vals = np.fromstring(cs, dtype=np.float64, sep=",")

            st["len_rows"][csi_len] += 1
            st["vals_rows"][vals.size] += 1
            st["node_ids"][node_id] += 1
            st["mac_rows"][mac] += 1
            # what pc/exp_overnight_0822.py:303 would have thrown away
            if len(cs.split(",", 128)) < 129:
                st["naive_dropped"] += 1

            if origin is None:
                origin = pc_us
                st["origin"] = origin
            t = (pc_us - origin) * 1e-6
            if t < T_LO or t >= T_HI:
                if fb.tell() >= hi:
                    break
                continue

            if mac in bidx:
                e = est.setdefault(mac, FrameEstimator()).feed(vals, esp_us)
                c_pc.push(pc_us)
                c_esp.push(esp_us)
                c_mac.push(bidx[mac])
                c_rssi.push(max(-32768, min(32767, rssi)))
                if e is None:
                    c_slope.push(nan)
                    c_cfo.push(nan)
                    c_inl.push(nan)
                    c_res.push(nan)
                else:
                    c_slope.push(e["slope"])
                    c_cfo.push(nan if e["cfo_hz"] is None else e["cfo_hz"])
                    c_inl.push(e["inlier_ratio"])
                    c_res.push(e["resid_std"])
            else:
                # ambient: cheap (a few thousand rows) and it is the direct
                # proof that 128-length rows reach the estimator
                a = st["amb"].setdefault(
                    mac, {"n": 0, "fit": 0, "slope": []})
                a["n"] += 1
                e = est.setdefault(mac, FrameEstimator()).feed(vals, esp_us)
                if e is not None:
                    a["fit"] += 1
                    if len(a["slope"]) < 4000:
                        a["slope"].append(e["slope"])

            if fb.tell() >= hi:
                break
        st["byte_hi"] = fb.tell()

    np.savez(cpath(tag, f"part{args.part}.npz"),
             pc=c_pc.out(), esp=c_esp.out(), mac=c_mac.out(),
             slope=c_slope.out(), cfo=c_cfo.out(),
             inlier=c_inl.out(), resid=c_res.out(), rssi=c_rssi.out())
    with open(cpath(tag, f"state{args.part}.pkl"), "wb") as f:
        pickle.dump(st, f)
    print(f"{tag} part {args.part}/{args.nparts}: bytes [{lo},{st['byte_hi']}) "
          f"rows so far {st['rows']} frames cached {c_pc.n}")
    return 0


def cmd_merge(args):
    tag = args.tag
    with open(cpath(tag, f"state{args.nparts - 1}.pkl"), "rb") as f:
        st = pickle.load(f)
    parts = [np.load(cpath(tag, f"part{p}.npz")) for p in range(args.nparts)]
    out = {}
    for k in ("pc", "esp", "mac", "slope", "cfo", "inlier", "resid", "rssi"):
        out[k] = np.concatenate([p[k] for p in parts])
    # order check: pc_time_us must not go backwards across a seam
    back = int((np.diff(out["pc"]) < 0).sum())
    np.savez(cpath(tag, "frames.npz"), **out)
    st["len_rows"] = dict(st["len_rows"])
    st["vals_rows"] = dict(st["vals_rows"])
    st["node_ids"] = dict(st["node_ids"])
    st["mac_rows"] = dict(st["mac_rows"])
    st.pop("est", None)
    with open(cpath(tag, "meta.pkl"), "wb") as f:
        pickle.dump(st, f)
    ok = (args.expect_rows is None or st["rows"] == args.expect_rows)
    print(f"{tag}: rows {st['rows']}"
          f"{' == expected' if ok else ' != expected %d' % args.expect_rows}"
          f"; frames cached {out['pc'].size}; pc_time_us reversals {back}")
    if not ok:
        return 1
    return 0


# ----------------------------------------------------------- re-aggregation

def _reagg(slope, cfo, inlier, resid, esp, rssi, window,
           min_inlier, max_resid):
    """Chunk gated frames into windows; returns (sfo, cfo, n, t_us) arrays.

    Equivalent to feeding the same frames to `WindowAggregator(window,
    min_inlier, max_resid)`; `selftest_reagg()` checks that against the real
    class rather than asserting it.
    """
    keep = np.isfinite(slope) & (inlier >= min_inlier) & (resid <= max_resid)
    s = slope[keep]
    c = cfo[keep]
    t = esp[keep]
    nw = s.size // window
    if nw == 0:
        return (np.empty(0), np.empty(0), np.empty(0), np.empty(0))
    s = s[:nw * window].reshape(nw, window)
    c = c[:nw * window].reshape(nw, window)
    t = t[:nw * window].reshape(nw, window)
    sfo = np.median(s, axis=1)
    tmid = np.median(t, axis=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cfo_med = np.nanmedian(c, axis=1)
    return sfo, cfo_med, np.full(nw, window), tmid


def selftest_reagg(fr, tag):
    """Prove the re-chunking equals the shipped WindowAggregator."""
    sel = np.where(fr["mac"] == 0)[0][:20000]
    slope = fr["slope"][sel].astype(np.float64)
    cfo = fr["cfo"][sel].astype(np.float64)
    inl = fr["inlier"][sel].astype(np.float64)
    res = fr["resid"][sel].astype(np.float64)
    esp = fr["esp"][sel]
    rssi = fr["rssi"][sel].astype(np.float64)
    agg = WindowAggregator(window=SHIPPED_WINDOW,
                           min_inlier_ratio=SHIPPED_MIN_INLIER,
                           max_resid=SHIPPED_MAX_RESID)
    ref_sfo, ref_cfo = [], []
    for i in range(sel.size):
        est = None if not np.isfinite(slope[i]) else {
            "slope": slope[i], "intercept": 0.0,
            "cfo_hz": None if not np.isfinite(cfo[i]) else cfo[i],
            "inlier_ratio": inl[i], "resid_std": res[i]}
        o = agg.feed(est, int(esp[i]), rssi[i])
        if o is not None:
            ref_sfo.append(o["sfo"])
            ref_cfo.append(o["cfo"] if o["cfo"] is not None else np.nan)
    g_sfo, g_cfo, _, _ = _reagg(slope, cfo, inl, res, esp, rssi,
                                SHIPPED_WINDOW, SHIPPED_MIN_INLIER,
                                SHIPPED_MAX_RESID)
    ok_n = len(ref_sfo) == g_sfo.size
    ok_s = ok_n and np.allclose(np.array(ref_sfo), g_sfo, rtol=0, atol=0)
    rc = np.array(ref_cfo)
    ok_c = ok_n and np.allclose(np.nan_to_num(rc, nan=-9e9),
                                np.nan_to_num(g_cfo, nan=-9e9),
                                rtol=0, atol=1e-9)
    print(f"  {tag}: re-aggregation vs WindowAggregator over "
          f"{sel.size} frames -> {g_sfo.size} windows: "
          f"count {'OK' if ok_n else 'MISMATCH'}, "
          f"sfo {'bit-identical' if ok_s else 'MISMATCH'}, "
          f"cfo {'identical' if ok_c else 'MISMATCH'}")
    return ok_n and ok_s and ok_c


# ------------------------------------------------------------ 1. Allan dev

def allan(y, valid, taus_m):
    """Overlapping Allan deviation of a gappy series y sampled at TAU0.

    sigma^2(m*tau0) = 1/2 * < (Ybar_{j+m} - Ybar_j)^2 >, where Ybar_j is the
    mean of y over the m bins starting at j. A block counts only if at least
    MIN_BIN_FRAC of its bins carry data, so gaps drop pairs rather than
    biasing them toward zero.
    Returns (sigma, n_pairs, n_independent) per tau.
    """
    yy = np.where(valid, y, 0.0)
    S = np.concatenate([[0.0], np.cumsum(yy)])
    C = np.concatenate([[0], np.cumsum(valid.astype(np.int64))])
    N = y.size
    sig, npair, nind = [], [], []
    for m in taus_m:
        if 2 * m > N:
            sig.append(np.nan)
            npair.append(0)
            nind.append(0)
            continue
        cnt = C[m:] - C[:-m]
        tot = S[m:] - S[:-m]
        good = cnt >= max(1, int(np.ceil(MIN_BIN_FRAC * m)))
        with np.errstate(invalid="ignore", divide="ignore"):
            blk = np.where(good, tot / np.maximum(cnt, 1), np.nan)
        a = blk[:-m]
        b = blk[m:]
        d = b - a
        ok = np.isfinite(d)
        n = int(ok.sum())
        if n < 3:
            sig.append(np.nan)
            npair.append(n)
            nind.append(0)
            continue
        sig.append(float(np.sqrt(0.5 * np.mean(d[ok] ** 2))))
        npair.append(n)
        nind.append(max(0, N // (2 * m)))
    return np.array(sig), np.array(npair), np.array(nind)


def loglog_slope(tau, sig, lo, hi):
    m = np.isfinite(sig) & (tau >= lo) & (tau <= hi) & (sig > 0)
    if m.sum() < 3:
        return float("nan"), int(m.sum())
    p = np.polyfit(np.log10(tau[m]), np.log10(sig[m]), 1)
    return float(p[0]), int(m.sum())


# ------------------------------------------------------- 2/3. separation

def separation(feats_by_mac, min_windows=5):
    """Pairwise centroid Mahalanobis distances via rff.discriminator."""
    d = Discriminator()
    used = []
    for mac, F in feats_by_mac.items():
        if F.shape[0] < min_windows:
            continue
        used.append(mac)
        for f in F:
            d.learn(mac, f)
    ids, sep = d.separation_matrix()
    if len(ids) < 2:
        return ids, sep, np.nan, np.nan
    off = sep[np.triu_indices(len(ids), 1)]
    return ids, sep, float(off.min()), float(np.median(off))


# rff.discriminator._VAR_FLOOR = [1.0 Hz^2, 1e-8 (rad/sc)^2]. Once a
# beacon's per-window SFO sd falls below 1e-4 rad/sc the floor, not the
# data, sets the denominator of every Mahalanobis distance — so a sweep
# that keeps averaging past that point stops being able to show a gain.
SFO_SD_FLOOR = 1e-4
CFO_SD_FLOOR = 1.0


def sep1d(feats_by_mac, col, min_windows=5):
    """Plain 1-D separation |mu_a - mu_b| / pooled sd, no variance floor.

    Reported alongside the 2-D Mahalanobis numbers because the shipped
    discriminator's variance floor can bind at long windows (see
    SFO_SD_FLOOR) and because SFO alone is the crystal quantity.
    """
    macs = [m for m, F in feats_by_mac.items() if F.shape[0] >= min_windows]
    if len(macs) < 2:
        return {}, np.nan, np.nan
    num = sum((feats_by_mac[m].shape[0] - 1) * feats_by_mac[m][:, col].var(ddof=1)
              for m in macs)
    dof = sum(feats_by_mac[m].shape[0] - 1 for m in macs)
    sd = np.sqrt(num / max(dof, 1))
    out = {}
    for a in range(len(macs)):
        for b in range(a + 1, len(macs)):
            d = abs(np.mean(feats_by_mac[macs[a]][:, col])
                    - np.mean(feats_by_mac[macs[b]][:, col]))
            out[frozenset((macs[a], macs[b]))] = d / sd if sd > 0 else np.inf
    v = np.array(list(out.values()))
    return out, float(v.min()), float(np.median(v))


_SPLIT = {}       # tag -> {mac: (slope, cfo, inlier, resid, esp, rssi)}
_FCACHE = {}      # (tag, window, min_inlier, max_resid) -> (feats, counts)


def split_by_mac(tag, fr):
    if tag in _SPLIT:
        return _SPLIT[tag]
    d = {}
    for i, mac in enumerate(BEACONS):
        s = fr["mac"] == i
        d[mac] = (fr["slope"][s].astype(np.float64),
                  fr["cfo"][s].astype(np.float64),
                  fr["inlier"][s].astype(np.float64),
                  fr["resid"][s].astype(np.float64),
                  fr["esp"][s],
                  fr["rssi"][s].astype(np.float64))
    _SPLIT[tag] = d
    return d


def feats(tag, fr, window, min_inlier, max_resid):
    """{mac: (n,2) array of (CFO, SFO)} plus per-mac window counts."""
    key = (tag, window, min_inlier, max_resid)
    if key in _FCACHE:
        return _FCACHE[key]
    d = split_by_mac(tag, fr)
    out, counts = {}, {}
    for mac in BEACONS:
        sfo, cfo, _, _ = _reagg(*d[mac], window, min_inlier, max_resid)
        ok = np.isfinite(sfo) & np.isfinite(cfo)
        out[mac] = np.column_stack([cfo[ok], sfo[ok]])
        counts[mac] = int(ok.sum())
    _FCACHE[key] = (out, counts)
    return out, counts


# ------------------------------------------------------------------ report

def load(tag):
    fr = dict(np.load(cpath(tag, "frames.npz")))
    with open(cpath(tag, "meta.pkl"), "rb") as f:
        meta = pickle.load(f)
    return fr, meta


def cmd_report(args):
    tags = args.tags.split(",")
    data = {t: load(t) for t in tags}

    print("=" * 78)
    print("SEPARATION SCALING — 2026-08-22 overnight, empty-room window only")
    print("=" * 78)
    print(f"window: {T_LO:g} s <= t < {T_HI:g} s of pc_time_us since each "
          "file's first decodable row")
    print(f"yardsticks: BETWEEN_UNIT_SD={BETWEEN_UNIT_SD} "
          f"TWIN_DSFO={TWIN_DSFO} "
          f"estimator floor {FLOOR_QUANT:.1e} (quantisation) / "
          f"{FLOOR_20DB:.1e} (20 dB SNR)")

    # ---- 0. parse verification -------------------------------------------
    print("\n### 0. PARSE VERIFICATION (the split(\",\",128) defect) ###")
    for t in tags:
        fr, meta = data[t]
        vr = meta["vals_rows"]
        lr = meta["len_rows"]
        print(f"\n{t}: {meta['rows']} data rows, "
              f"undecodable line {meta['bad_line']}, field {meta['bad_field']}")
        print(f"  node_id values: {dict(meta['node_ids'])}")
        print("  parsed CSI vector length -> rows: " +
              ", ".join(f"{k}:{v}" for k, v in sorted(vr.items())))
        print("  csi_len column        -> rows: " +
              ", ".join(f"{k}:{v}" for k, v in sorted(lr.items())))
        n128 = vr.get(128, 0)
        n256 = vr.get(256, 0)
        print(f"  128-length rows seen by THIS parser: {n128}")
        print(f"  256-length rows seen by THIS parser: {n256}")
        print(f"  rows split(\",\",128) would have dropped: "
              f"{meta['naive_dropped']}")
        amb = meta["amb"]
        fit = sum(v["fit"] for v in amb.values())
        nrow = sum(v["n"] for v in amb.values())
        top = sorted(amb.items(), key=lambda kv: -kv[1]["n"])[:6]
        print(f"  ambient (non-beacon) rows {nrow}, RANSAC fits obtained "
              f"{fit}  <- 0 here would mean the defect was inherited")
        for m, v in top:
            sl = np.array(v["slope"])
            med = f"{np.median(sl):+.5f}" if sl.size else "—"
            print(f"    {m:<20} n={v['n']:>5} fits={v['fit']:>5} "
                  f"slope median {med}")

    # ---- self-test -------------------------------------------------------
    print("\n### 0b. RE-AGGREGATION SELF-TEST ###")
    allok = all(selftest_reagg(data[t][0], t) for t in tags)
    print(f"  all cells reproduce the shipped aggregator: {allok}")

    # ---- cross-check against the published whole-night figures -----------
    print("\n### 0c. CROSS-CHECK, shipped config, this window vs "
          "docs/OVERNIGHT_2026-08-22.md §3.1 (whole file) ###")
    print(f"{'node':<6}{'b':<4}{'fed':>10}{'accepted':>10}{'rej %':>8}"
          f"{'windows':>9}{'SFO median':>12}{'IQR':>10}")
    for t in tags:
        fr, _ = data[t]
        for i, mac in enumerate(BEACONS):
            s = fr["mac"] == i
            sl = fr["slope"][s].astype(np.float64)
            inl = fr["inlier"][s].astype(np.float64)
            res = fr["resid"][s].astype(np.float64)
            keep = (np.isfinite(sl) & (inl >= SHIPPED_MIN_INLIER)
                    & (res <= SHIPPED_MAX_RESID))
            sfo, _, _, _ = _reagg(sl, fr["cfo"][s].astype(np.float64), inl,
                                  res, fr["esp"][s],
                                  fr["rssi"][s].astype(np.float64),
                                  SHIPPED_WINDOW, SHIPPED_MIN_INLIER,
                                  SHIPPED_MAX_RESID)
            n = int(s.sum())
            iqr = (np.subtract(*np.percentile(sfo, [75, 25]))
                   if sfo.size else np.nan)
            print(f"{t:<6}{BNAME[mac]:<4}{n:>10}{int(keep.sum()):>10}"
                  f"{100*(1-keep.sum()/max(n,1)):>8.3f}{sfo.size:>9}"
                  f"{np.median(sfo) if sfo.size else np.nan:>+12.5f}"
                  f"{iqr:>10.5f}")

    # ---- 1. Allan deviation ---------------------------------------------
    print("\n\n" + "=" * 78)
    print("### 1. ALLAN DEVIATION of the SFO estimate ###")
    print("=" * 78)
    print(f"tau0 = {TAU0:g} s bins of accepted per-frame slopes "
          f"(shipped gates inlier>={SHIPPED_MIN_INLIER}, "
          f"resid<={SHIPPED_MAX_RESID}); overlapping estimator; a block "
          f"counts only if >= {MIN_BIN_FRAC:.0%} of its bins carry data")

    ms = np.unique(np.round(np.logspace(0, np.log10(7200), 34)).astype(int))
    taus = ms * TAU0
    allan_store = {}
    for t in tags:
        fr, meta = data[t]
        # meta["origin"] is the file's first pc_time_us, i.e. the same t = 0
        # that rff_offline.py's --after/--before use.
        tsec = (fr["pc"] - meta["origin"]) * 1e-6
        nb = int(np.ceil((T_HI - T_LO) / TAU0))
        for i, mac in enumerate(BEACONS):
            s = fr["mac"] == i
            sl = fr["slope"][s].astype(np.float64)
            inl = fr["inlier"][s].astype(np.float64)
            res = fr["resid"][s].astype(np.float64)
            keep = (np.isfinite(sl) & (inl >= SHIPPED_MIN_INLIER)
                    & (res <= SHIPPED_MAX_RESID))
            tb = ((tsec[s][keep] - T_LO) / TAU0).astype(np.int64)
            tb = np.clip(tb, 0, nb - 1)
            cnt = np.bincount(tb, minlength=nb)
            tot = np.bincount(tb, weights=sl[keep], minlength=nb)
            valid = cnt > 0
            y = np.zeros(nb)
            y[valid] = tot[valid] / cnt[valid]
            sig, npair, nind = allan(y, valid, ms)
            allan_store[(t, mac)] = (taus, sig, npair, nind, valid.mean(),
                                     cnt[valid].mean())
            print(f"\n{t} / {BNAME[mac]} ({mac}) — "
                  f"{valid.mean():.1%} of {nb} bins populated, "
                  f"mean {cnt[valid].mean():.1f} accepted frames/bin")
            print(f"  {'tau s':>9}{'sigma(tau)':>13}{'/BU_SD':>9}"
                  f"{'pairs':>9}{'indep':>7}")
            for k in range(len(taus)):
                if not np.isfinite(sig[k]):
                    continue
                print(f"  {taus[k]:>9.2f}{sig[k]:>13.3e}"
                      f"{sig[k]/BETWEEN_UNIT_SD:>9.3f}"
                      f"{npair[k]:>9}{nind[k]:>7}")
            fin = np.isfinite(sig)
            kmin = int(np.nanargmin(np.where(fin, sig, np.inf)))
            for lo, hi, lab in ((0.5, 5.0, "0.5–5 s"),
                                (5.0, 60.0, "5–60 s"),
                                (60.0, 600.0, "60–600 s"),
                                (600.0, 3600.0, "600–3600 s")):
                sl_, n_ = loglog_slope(taus, sig, lo, hi)
                print(f"    log-log slope {lab:<12} {sl_:+.3f}  (n={n_})")
            print(f"    minimum sigma = {sig[kmin]:.3e} rad/sc at "
                  f"tau = {taus[kmin]:.1f} s "
                  f"({sig[kmin]/BETWEEN_UNIT_SD:.3f} x BETWEEN_UNIT_SD, "
                  f"{sig[kmin]/TWIN_DSFO:.2f} x TWIN_DSFO)")

    # ---- 2. window sweep -------------------------------------------------
    print("\n\n" + "=" * 78)
    print("### 2. WINDOW-LENGTH SWEEP (shipped gates) ###")
    print("=" * 78)
    for t in tags:
        fr, _ = data[t]
        print(f"\n--- {t} ---")
        print("2-D Mahalanobis (CFO,SFO) via rff.discriminator, all windows:")
        print(f"{'window':>7}{'sec@100fps':>11}"
              f"{'w:B1':>7}{'w:B2':>7}{'w:B3':>7}"
              f"{'minSep':>9}{'medSep':>9}"
              f"{'B1-B2':>9}{'B1-B3':>9}{'B2-B3':>9}{'  floor?':>9}")
        for W in WINDOWS:
            F, cnt = feats(t, fr, W, SHIPPED_MIN_INLIER, SHIPPED_MAX_RESID)
            ids, sep, mn, md = separation(F)
            pair = {}
            for a in range(len(ids)):
                for b in range(a + 1, len(ids)):
                    pair[frozenset((ids[a], ids[b]))] = sep[a, b]

            def g(x, y, _p=pair):
                return _p.get(frozenset((x, y)), float("nan"))
            binds = [BNAME[m] for m in BEACONS
                     if F[m].shape[0] >= 2
                     and F[m][:, 1].std(ddof=1) < SFO_SD_FLOOR]
            print(f"{W:>7}{W/100.0:>11.1f}"
                  f"{cnt[B1]:>7}{cnt[B2]:>7}{cnt[B3]:>7}"
                  f"{mn:>9.2f}{md:>9.2f}"
                  f"{g(B1,B2):>9.2f}{g(B1,B3):>9.2f}{g(B2,B3):>9.2f}"
                  f"{(','.join(binds) if binds else '-'):>9}")
        print("  floor? = beacons whose per-window SFO sd has fallen below "
              f"the discriminator's variance floor {SFO_SD_FLOOR:g} rad/sc "
              "(rff/discriminator.py:29); for those the denominator is the "
              "floor, not the data.")

        print("\n1-D SFO-only separation |dmu| / pooled sd, NO variance "
              "floor (same windows):")
        print(f"{'window':>7}{'minSep':>9}{'medSep':>9}"
              f"{'B1-B2':>9}{'B1-B3':>9}{'B2-B3':>9}{'pooled sd':>12}")
        for W in WINDOWS:
            F, cnt = feats(t, fr, W, SHIPPED_MIN_INLIER, SHIPPED_MAX_RESID)
            pair, mn, md = sep1d(F, 1)

            def g(x, y, _p=pair):
                return _p.get(frozenset((x, y)), float("nan"))
            macs = [m for m in BEACONS if F[m].shape[0] >= 5]
            if macs:
                num = sum((F[m].shape[0] - 1) * F[m][:, 1].var(ddof=1)
                          for m in macs)
                dof = sum(F[m].shape[0] - 1 for m in macs)
                psd = np.sqrt(num / max(dof, 1))
            else:
                psd = np.nan
            print(f"{W:>7}{mn:>9.2f}{md:>9.2f}"
                  f"{g(B1,B2):>9.2f}{g(B1,B3):>9.2f}{g(B2,B3):>9.2f}"
                  f"{psd:>12.3e}")

        print(f"\n  per-beacon (CFO Hz, SFO rad/sc) medians and sd by window")
        print(f"{'window':>7}  " + "".join(
            f"{BNAME[m]+' sfo':>12}{BNAME[m]+' sd':>11}" for m in BEACONS))
        for W in WINDOWS:
            F, _ = feats(t, fr, W, SHIPPED_MIN_INLIER, SHIPPED_MAX_RESID)
            row = f"{W:>7}  "
            for m in BEACONS:
                a = F[m]
                if a.shape[0] < 2:
                    row += f"{'—':>12}{'—':>11}"
                else:
                    row += f"{np.median(a[:,1]):>+12.5f}{a[:,1].std(ddof=1):>11.5f}"
            print(row)
        print(f"{'':>7}  " + "".join(
            f"{BNAME[m]+' cfo':>12}{BNAME[m]+' sd':>11}" for m in BEACONS))
        for W in WINDOWS:
            F, _ = feats(t, fr, W, SHIPPED_MIN_INLIER, SHIPPED_MAX_RESID)
            row = f"{W:>7}  "
            for m in BEACONS:
                a = F[m]
                if a.shape[0] < 2:
                    row += f"{'—':>12}{'—':>11}"
                else:
                    row += f"{np.median(a[:,0]):>+12.2f}{a[:,0].std(ddof=1):>11.2f}"
            print(row)

    # ---- 3. gate sweep ---------------------------------------------------
    print("\n\n" + "=" * 78)
    print("### 3. GATE SWEEP ###")
    print("=" * 78)
    for t in tags:
        fr, _ = data[t]
        for W in (SHIPPED_WINDOW, args.gate_window):
            print(f"\n--- {t}, window = {W} frames ---")
            print(f"{'max_resid':>10}{'min_inlier':>11}"
                  f"{'frames kept':>13}{'kept %':>8}"
                  f"{'w:B1':>7}{'w:B2':>7}{'w:B3':>7}"
                  f"{'nsrc':>6}{'minSep':>9}{'medSep':>9}"
                  f"{'sfoMin':>9}{'sfoMed':>9}")
            nfr = int(np.isfinite(fr["slope"]).sum())
            for R in RESIDS:
                for I in INLIERS:
                    F, cnt = feats(t, fr, W, I, R)
                    ids, sep, mn, md = separation(F)
                    _, mn1, md1 = sep1d(F, 1)
                    keep = (np.isfinite(fr["slope"])
                            & (fr["inlier"] >= I) & (fr["resid"] <= R))
                    k = int(keep.sum())
                    tagsh = ""
                    if R == SHIPPED_MAX_RESID and I == SHIPPED_MIN_INLIER:
                        tagsh = "  <- shipped"
                    print(f"{R:>10.2f}{I:>11.2f}{k:>13}"
                          f"{100*k/max(nfr,1):>8.2f}"
                          f"{cnt[B1]:>7}{cnt[B2]:>7}{cnt[B3]:>7}"
                          f"{len(ids):>6}{mn:>9.2f}{md:>9.2f}"
                          f"{mn1:>9.2f}{md1:>9.2f}{tagsh}")

    # ---- 4. best configuration ------------------------------------------
    print("\n\n" + "=" * 78)
    print("### 4. BEST ACHIEVABLE, and what it cost ###")
    print("=" * 78)
    for t in tags:
        fr, _ = data[t]
        nfr = int(np.isfinite(fr["slope"]).sum())
        best = None
        rows = []
        for W in WINDOWS:
            for R in RESIDS:
                for I in INLIERS:
                    F, cnt = feats(t, fr, W, I, R)
                    ids, sep, mn, md = separation(F)
                    if not np.isfinite(mn):
                        continue
                    if len(ids) < 3:
                        continue          # all three beacons must be present
                    _, mn1, md1 = sep1d(F, 1)
                    keep = (np.isfinite(fr["slope"])
                            & (fr["inlier"] >= I) & (fr["resid"] <= R))
                    binds = any(F[m].shape[0] >= 2
                                and F[m][:, 1].std(ddof=1) < SFO_SD_FLOOR
                                for m in BEACONS)
                    rows.append((mn, md, W, R, I, int(keep.sum()),
                                 min(cnt.values()), mn1, md1, binds))
        rows.sort(key=lambda r: -r[0])
        print(f"\n--- {t} --- top 10 configurations by MINIMUM pairwise "
              f"separation (all 3 beacons must reach 5 windows)")
        print(f"{'minSep':>9}{'medSep':>9}{'window':>8}{'resid':>8}"
              f"{'inlier':>8}{'frames':>12}{'kept %':>8}{'minWins':>9}"
              f"{'avg s':>9}{'sfoMin':>9}{'sfoMed':>9}{'  floor?':>9}")
        for r in rows[:10]:
            print(f"{r[0]:>9.2f}{r[1]:>9.2f}{r[2]:>8}{r[3]:>8.2f}"
                  f"{r[4]:>8.2f}{r[5]:>12}{100*r[5]/max(nfr,1):>8.2f}"
                  f"{r[6]:>9}{r[2]/100.0:>9.1f}{r[7]:>9.2f}{r[8]:>9.2f}"
                  f"{('YES' if r[9] else '-'):>9}")
        print(f"\n  shipped config for comparison:")
        F, cnt = feats(t, fr, SHIPPED_WINDOW, SHIPPED_MIN_INLIER,
                       SHIPPED_MAX_RESID)
        ids, sep, mn, md = separation(F)
        print(f"    window 64, resid 0.80, inlier 0.60 -> "
              f"min {mn:.2f} sigma, median {md:.2f} sigma, "
              f"windows {dict((BNAME[k], v) for k, v in cnt.items())}")
    return 0


def cmd_detail(args):
    """Per-pair breakdown, drift decomposition and blind holdout at two
    named configurations, so the summary rests on printed pairs rather than
    on a min/median that hides which pair is which."""
    tags = args.tags.split(",")
    configs = [("shipped", SHIPPED_WINDOW, SHIPPED_MAX_RESID,
                SHIPPED_MIN_INLIER),
               ("best-honest", args.window, args.max_resid, args.min_inlier)]
    print("=" * 78)
    print("DETAIL — named configurations, per pair")
    print("=" * 78)
    print(f"window {T_LO:g} s <= t < {T_HI:g} s")
    for t in tags:
        fr, meta = load(t)
        for label, W, R, I in configs:
            F, cnt = feats(t, fr, W, I, R)
            ids, sep, mn, md = separation(F)
            print(f"\n--- {t} / {label}: window {W} frames "
                  f"({W/100.0:.1f} s at 100 fps), max_resid {R:g}, "
                  f"min_inlier {I:g} ---")
            print(f"{'beacon':<6}{'windows':>9}{'SFO mean':>12}{'SFO sd':>11}"
                  f"{'SFO sd|30min':>14}{'CFO mean':>10}{'CFO sd':>9}")
            for m in BEACONS:
                a = F[m]
                if a.shape[0] < 2:
                    print(f"{BNAME[m]:<6}{a.shape[0]:>9}  (too few windows)")
                    continue
                # within-30-minute-block sd: how much of the spread is NOT
                # slow drift. Windows are chronological, so blocks are
                # contiguous slices of 1800 s worth of windows.
                per_block = max(1, int(round(1800.0 / (W / 100.0))))
                nb = max(1, a.shape[0] // per_block)
                resid = []
                for k in range(nb):
                    seg = a[k * per_block:(k + 1) * per_block, 1]
                    if seg.size >= 2:
                        resid.append(seg - seg.mean())
                sd_in = np.concatenate(resid).std(ddof=1) if resid else np.nan
                print(f"{BNAME[m]:<6}{a.shape[0]:>9}{a[:,1].mean():>+12.5f}"
                      f"{a[:,1].std(ddof=1):>11.5f}{sd_in:>14.5f}"
                      f"{a[:,0].mean():>+10.3f}{a[:,0].std(ddof=1):>9.3f}")
            print(f"  pairwise: ", end="")
            for x in range(len(ids)):
                for y in range(x + 1, len(ids)):
                    print(f"{BNAME[ids[x]]}-{BNAME[ids[y]]} {sep[x,y]:.2f}σ  ",
                          end="")
            print(f"\n  min {mn:.2f}σ  median {md:.2f}σ  "
                  f"(codebase rule of thumb: >3σ reliably separable, "
                  f"pc/rff_offline.py:322)")
            _, mn1, md1 = sep1d(F, 1)
            _, mnc, mdc = sep1d(F, 0)
            print(f"  SFO axis alone: min {mn1:.2f}σ median {md1:.2f}σ   "
                  f"CFO axis alone: min {mnc:.2f}σ median {mdc:.2f}σ")
            # blind holdout, same protocol as pc/rff_offline.py:report()
            d = Discriminator()
            test = {}
            for m in BEACONS:
                a = F[m]
                if a.shape[0] < 5:
                    continue
                cut = max(int(a.shape[0] * 0.6), 1)
                for f in a[:cut]:
                    d.learn(m, f)
                test[m] = a[cut:]
            tot = ok = strg = 0
            conf = defaultdict(int)
            for m, A in test.items():
                for f in A:
                    best, d2, verdict = d.classify(f)
                    if verdict == "UNSCORED":
                        continue
                    tot += 1
                    if verdict == "STRANGER":
                        strg += 1
                    elif best == m:
                        ok += 1
                    else:
                        conf[(BNAME[m], BNAME[best])] += 1
            if tot:
                print(f"  blind holdout (train 60%/test 40%, chronological): "
                      f"{ok}/{tot} = {ok/tot:.1%}, stranger {strg}, "
                      f"confusions " +
                      (", ".join(f"{a}->{b} x{c}" for (a, b), c
                                 in sorted(conf.items())) or "none"))

    # receiver term vs beacon term, same window
    print("\n--- the receiver term against the beacon term (SFO medians, "
          "shipped config, this window) ---")
    if len(tags) == 2:
        a, b = tags
        Fa, _ = feats(a, load(a)[0], SHIPPED_WINDOW, SHIPPED_MIN_INLIER,
                      SHIPPED_MAX_RESID)
        Fb, _ = feats(b, load(b)[0], SHIPPED_WINDOW, SHIPPED_MIN_INLIER,
                      SHIPPED_MAX_RESID)
        for m in BEACONS:
            ma = np.median(Fa[m][:, 1])
            mb = np.median(Fb[m][:, 1])
            print(f"  {BNAME[m]} ({m}): {a} {ma:+.5f}  {b} {mb:+.5f}  "
                  f"{a}-{b} {ma-mb:+.5f} = {abs(ma-mb)/BETWEEN_UNIT_SD:.2f} "
                  f"x BETWEEN_UNIT_SD")
        for node, F in ((a, Fa), (b, Fb)):
            print(f"  within {node}: " + "  ".join(
                f"{BNAME[x]}-{BNAME[y]} {np.median(F[x][:,1]) - np.median(F[y][:,1]):+.5f}"
                for i, x in enumerate(BEACONS) for y in BEACONS[i+1:]))
    return 0


def cmd_control(args):
    """Non-circular control: shuffle each beacon's accepted frames in time,
    then re-window.

    Chunking a shuffled sequence averages exactly the same numbers, so any
    difference is purely the temporal correlation between neighbouring
    frames. If the real per-window sd plateaus while the shuffled one keeps
    falling as 1/sqrt(W), the plateau is correlated drift and not a
    property of the estimator, the gate or the aggregator.
    """
    rng = np.random.default_rng(0)
    print("=" * 78)
    print("CONTROL — real order vs time-shuffled order, same frames")
    print("=" * 78)
    print("per-window SFO sd (rad/sc); 1/sqrt(W) is what uncorrelated "
          "frames would give")
    for t in args.tags.split(","):
        fr, _ = load(t)
        d = split_by_mac(t, fr)
        print(f"\n--- {t} ---")
        print(f"{'beacon':<7}{'window':>8}{'n win':>7}{'sd real':>11}"
              f"{'sd shuffled':>13}{'sd @W=64 /sqrt(W/64)':>22}")
        for mac in BEACONS:
            slope, cfo, inl, res, esp, rssi = d[mac]
            keep = (np.isfinite(slope) & (inl >= SHIPPED_MIN_INLIER)
                    & (res <= SHIPPED_MAX_RESID))
            s = slope[keep]
            perm = rng.permutation(s.size)
            base = None
            for W in WINDOWS:
                nw = s.size // W
                if nw < 2:
                    continue
                real = np.median(s[:nw * W].reshape(nw, W), axis=1)
                shuf = np.median(s[perm][:nw * W].reshape(nw, W), axis=1)
                if base is None:
                    base = real.std(ddof=1)
                print(f"{BNAME[mac]:<7}{W:>8}{nw:>7}"
                      f"{real.std(ddof=1):>11.2e}{shuf.std(ddof=1):>13.2e}"
                      f"{base / np.sqrt(W / WINDOWS[0]):>22.2e}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan")
    s.add_argument("path")
    s.add_argument("--tag", required=True)
    s.add_argument("--part", type=int, required=True)
    s.add_argument("--nparts", type=int, required=True)
    s.set_defaults(fn=cmd_scan)

    m = sub.add_parser("merge")
    m.add_argument("--tag", required=True)
    m.add_argument("--nparts", type=int, required=True)
    m.add_argument("--expect-rows", type=int, default=None)
    m.set_defaults(fn=cmd_merge)

    r = sub.add_parser("report")
    r.add_argument("--tags", required=True)
    r.add_argument("--gate-window", type=int, default=4096)
    r.set_defaults(fn=cmd_report)

    d = sub.add_parser("detail")
    d.add_argument("--tags", required=True)
    d.add_argument("--window", type=int, default=16384)
    d.add_argument("--max-resid", type=float, default=0.80)
    d.add_argument("--min-inlier", type=float, default=0.90)
    d.set_defaults(fn=cmd_detail)

    c = sub.add_parser("control")
    c.add_argument("--tags", required=True)
    c.set_defaults(fn=cmd_control)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
