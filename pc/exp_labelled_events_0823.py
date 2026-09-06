#!/usr/bin/env python3
"""LABELLED_EVENTS_0823 -- the 18:00 capture with an operator event log.

Pre-registration: docs/LABELLED_EVENTS_0823.md (Stage 1, frozen before this
script produced a number).

Two features on every test:
  * the SHIPPED SFO slope -- pc/rff/dsp.py FrameEstimator + WindowAggregator,
    imported unmodified, one estimator per (file, MAC) stream, fed every
    screened frame in file order from the first row (ransac_line's RNG
    advances once per fitted frame, dsp.py:118,132).
  * kappa -- pc/exp_iq_imbalance.py's estimator, IMPORTED not rewritten
    (frames_to_H / deslope / process_batch / features / add_cells / Cell).

Read-only on data/raw/: every input opened "rb". pc/rff/dsp.py is not
modified. pc/capture.py:compute_cfo, pc/phase_skew.py and pc/fingerprint.py
are not used. No serial port is opened.

Scratch lives in $IQ_CACHE (default /tmp/lab0823), outside the repo tree.
"""
import argparse
import array
import csv
import hashlib
import json
import math
import os
import pickle
import sys
import time
from collections import defaultdict

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from rff import dsp                                   # NOT modified
import exp_iq_imbalance as IQ                         # estimator reused as-is

CACHE = os.environ.get("IQ_CACHE", "/tmp/lab0823")

# ----------------------------------------------------------------- constants
BIN_S = 10.0                       # kappa/RSSI accumulation bin (prereg 2.3)
W_EVENT = 240.0                    # analysis half-window (prereg 4.4)
GUARD_LOG = 30.0                   # guard around a LOGGED time (prereg 4.4)
GUARD_MEAS = 5.0                   # guard around a MEASURED gap (prereg 4.4)
FLOOR_BLOCK = 240.0                # Q2 floor block length (prereg 4.3)
Q1_BLOCK = 90.0                    # Q1 short-timescale block length
SIGMA_SFO = 0.00237                # BETWEEN_UNIT_SD, docs/LOT_HYPOTHESIS 5
GAP_MIN_S = 1.0                    # gap listing threshold (prereg 3.1)
GAP_MATCH_S = 2.0                  # cross-receiver gap coincidence (prereg 3.1)

BEACONS = dict(IQ.BEACONS)         # a4:f0..=B1, 28:05..=B2, f4:2d..=B3
BMACS = list(BEACONS)

# prereg 1.1 -- logged wall-clock events, seconds from capture start
EVENTS = [
    ("PC-B2",      57.4, "28:05:a5:2f:fa:48", "18:01 B2 power cycle, in place"),
    ("PC-B1",     477.4, "a4:f0:0f:77:91:20", "18:08 B1 power cycle, in place"),
    ("MOVE-IN",   657.4, "f4:2d:c9:70:72:30", "18:11 B3 car -> interior, battery"),
    ("RB1",      1137.4, "f4:2d:c9:70:72:30", "18:19 B3 battery -> wall (REBOOT 1)"),
    ("RB2",      2097.4, "f4:2d:c9:70:72:30", "18:35 B3 wall -> battery (REBOOT 2)"),
    ("POS-FRIDGE", 2397.4, "f4:2d:c9:70:72:30", "18:40 B3 -> fridge top, LOS"),
    ("POS-OVEN",  4197.4, "f4:2d:c9:70:72:30", "19:10 B3 -> oven, LOS blocked"),
]
EV_T = {e[0]: e[1] for e in EVENTS}

Q1 = (117.4, 477.4)                # 18:02 -> 18:08
Q2 = (4197.4, 7586.3)              # 19:10 -> end


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


# ---------------------------------------------------------------------- scan

class Bin:
    """One (MAC, 10 s bin): an IQ.Cell plus RSSI samples."""
    __slots__ = ("cell", "rssi", "n_clean")

    def __init__(self):
        self.cell = IQ.Cell()
        self.rssi = array.array("b")
        self.n_clean = 0


class ScanState:
    def __init__(self, tag, path):
        self.tag = tag
        self.path = path
        self.rows = 0
        self.bad_parse = 0
        self.n_field_bad = 0
        self.n_med_bad = 0
        self.n_both = 0
        self.n_corrupt = 0
        self.raw_n = defaultdict(int)          # every MAC
        self.clean_n = defaultdict(int)
        self.corrupt_n = defaultdict(int)
        self.bins = defaultdict(Bin)           # (mac, bin_idx) -> Bin
        self.ts = {m: array.array("q") for m in BMACS}   # clean pc_time_us
        self.win = {m: [] for m in BMACS}      # shipped-SFO window records
        self.est = {m: dsp.FrameEstimator() for m in BMACS}
        self.agg = {m: dsp.WindowAggregator() for m in BMACS}
        self.t0_us = None
        self.t_last_us = None
        self.node_mode = None
        self.chan_mode = None
        self.byte_pos = 0
        self.pend = []
        self.n_hist = 0
        self.eof = False
        self.resumes = []
        self.frames_fed = defaultdict(int)


def _spath(tag):
    return os.path.join(CACHE, f"{tag}_scan.pkl")


def run_scan(args):
    os.makedirs(CACHE, exist_ok=True)
    csv.field_size_limit(10 ** 7)
    sp = _spath(args.tag)

    if args.resume and os.path.exists(sp):
        with open(sp, "rb") as f:
            st = pickle.load(f)
        if st.eof:
            print(f"[{args.tag}] already at EOF, rows={st.rows:,}",
                  file=sys.stderr)
            return
        st.resumes.append((st.rows, st.byte_pos))
        L = IQ.Lines(args.path, st.byte_pos)
        rdr = csv.reader(iter(L))
    else:
        st = ScanState(args.tag, args.path)
        nh, ch = defaultdict(int), defaultdict(int)
        L = IQ.Lines(args.path)
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
        L = IQ.Lines(args.path)
        it2 = iter(L)
        next(it2)
        st.byte_pos = L.pos
        L.close()
        L = IQ.Lines(args.path, st.byte_pos)
        rdr = csv.reader(iter(L))

    pend = st.pend
    n_hist = st.n_hist
    half = IQ.MED_W // 2
    bufs = defaultdict(list)                   # (mac, bin) -> [csi vals]
    t0 = time.time()

    def emit(rec):
        (pc_us, mac, rssi, esp_us, csi_s, fbad, mbad) = rec
        if fbad:
            st.n_field_bad += 1
        if mbad:
            st.n_med_bad += 1
        if fbad and mbad:
            st.n_both += 1
        if fbad or mbad:
            st.n_corrupt += 1
            st.corrupt_n[mac] += 1
            return
        st.clean_n[mac] += 1
        if mac not in BEACONS:
            return
        tsec = (pc_us - st.t0_us) * 1e-6
        bi = int(tsec // BIN_S)
        b = st.bins[(mac, bi)]
        b.n_clean += 1
        b.cell.n_clean += 1
        b.cell.rssi_sum += rssi
        if -128 <= rssi <= 127:
            b.rssi.append(rssi)
        st.ts[mac].append(pc_us)
        try:
            vals = [int(x) for x in csi_s.split(",", dsp.N_CPLX * 2)
                    [: dsp.N_CPLX * 2]]
        except ValueError:
            b.cell.n_inadm += 1
            return
        if len(vals) < dsp.N_CPLX * 2:
            b.cell.n_inadm += 1
            return
        # --- shipped SFO arm: EVERY screened frame, in file order
        e = st.est[mac].feed(vals, esp_us)
        st.frames_fed[mac] += 1
        w = st.agg[mac].feed(e, pc_us, rssi)
        if w is not None:
            st.win[mac].append((w["ts_us"], w["sfo"], w["rssi"],
                                w["quality"], w["n_frames"]))
        # --- kappa arm
        bb = bufs[(mac, bi)]
        bb.append(vals)
        if len(bb) >= IQ.BATCH:
            IQ.process_batch(b.cell, bb, IQ.S_TRUE, True)
            bufs[(mac, bi)] = []

    def flush_pend(force):
        nonlocal n_hist
        while n_hist < len(pend):
            ci = n_hist
            if not force and (len(pend) - 1 - ci) < half:
                return
            lo = max(0, ci - half)
            hi = min(len(pend), ci + half + 1)
            vals = [pend[k][5] for k in range(lo, hi)]
            mbad = IQ.med_flag(vals, ci - lo) if len(vals) >= 3 else False
            r = pend[ci]
            emit((r[0], r[1], r[2], r[3], r[4], r[6], mbad))
            n_hist += 1
            while n_hist > half:
                del pend[0]
                n_hist -= 1

    deadline = time.time() + args.seconds if args.seconds else None
    stopped_early = False
    for row in rdr:
        st.rows += 1
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
        st.raw_n[mac] += 1
        fbad = not IQ.field_ok(node, env, chan, ln, nf, rssi,
                               st.node_mode, st.chan_mode)
        pend.append((pc_us, mac, rssi, esp_us, row[9], drop, fbad))
        flush_pend(False)
        if st.rows % 20000 == 0:
            if st.rows % 500000 == 0:
                print(f"[{args.tag}] {st.rows:,} rows {time.time()-t0:.0f}s",
                      file=sys.stderr, flush=True)
            if deadline and time.time() > deadline:
                stopped_early = True
                break

    st.byte_pos = L.pos
    if not stopped_early:
        flush_pend(True)
        st.eof = True
    for key, bb in bufs.items():
        if bb:
            IQ.process_batch(st.bins[key].cell, bb, IQ.S_TRUE, True)
    L.close()
    st.pend = pend
    st.n_hist = n_hist
    with open(sp, "wb") as f:
        pickle.dump(st, f, protocol=4)
    print(f"[{args.tag}] {'DONE' if st.eof else 'CHECKPOINT'} "
          f"rows={st.rows:,} corrupt={st.n_corrupt} "
          f"(field={st.n_field_bad} med={st.n_med_bad} both={st.n_both}) "
          f"byte_pos={st.byte_pos:,} in {time.time()-t0:.0f}s",
          file=sys.stderr, flush=True)


def load_scan(tag):
    with open(_spath(tag), "rb") as f:
        return pickle.load(f)


# ------------------------------------------------------------- window algebra

def sum_cells(st, mac, t_lo, t_hi):
    """Sum the IQ.Cell accumulators of every 10 s bin inside [t_lo, t_hi)."""
    lo = int(math.ceil(t_lo / BIN_S))
    hi = int(math.floor(t_hi / BIN_S))
    cells = [st.bins[(mac, i)].cell for i in range(lo, hi)
             if (mac, i) in st.bins]
    if not cells:
        return None
    return IQ.add_cells(cells)


def kappa_window(st, mac, t_lo, t_hi):
    c = sum_cells(st, mac, t_lo, t_hi)
    if c is None or c.n == 0:
        return None
    f = IQ.features(c)
    if f is None:
        return None
    return f


def sfo_window(st, mac, t_lo, t_hi):
    """Median shipped-SFO window slope inside [t_lo, t_hi)."""
    lo = st.t0_us + int(t_lo * 1e6)
    hi = st.t0_us + int(t_hi * 1e6)
    v = [w[1] for w in st.win[mac] if lo <= w[0] < hi]
    if not v:
        return None
    a = np.array(v)
    return {"med": float(np.median(a)), "n_win": a.size,
            "iqr": float(np.subtract(*np.percentile(a, [75, 25])))}


def rssi_window(st, mac, t_lo, t_hi):
    lo = int(math.ceil(t_lo / BIN_S))
    hi = int(math.floor(t_hi / BIN_S))
    v = []
    for i in range(lo, hi):
        b = st.bins.get((mac, i))
        if b is not None:
            v.extend(b.rssi)
    if not v:
        return None
    a = np.array(v, dtype=np.float64)
    return {"med": float(np.median(a)), "mean": float(a.mean()), "n": a.size}


def fps_window(st, mac, t_lo, t_hi):
    lo = st.t0_us + int(t_lo * 1e6)
    hi = st.t0_us + int(t_hi * 1e6)
    a = np.frombuffer(st.ts[mac], dtype=np.int64)
    n = int(((a >= lo) & (a < hi)).sum())
    return n / (t_hi - t_lo) if t_hi > t_lo else float("nan")


# ------------------------------------------------------------------ census

def octet_hamming(a, b):
    ta, tb = a.split(":"), b.split(":")
    if len(ta) != 6 or len(tb) != 6:
        return 99
    return sum(1 for x, y in zip(ta, tb) if x != y), \
        [i for i, (x, y) in enumerate(zip(ta, tb)) if x != y]


def run_census(a):
    out = {}
    for tag in a.tags.split(","):
        st = load_scan(tag)
        macs = sorted(st.raw_n, key=lambda m: -st.raw_n[m])
        print(f"\n===== {tag}: MAC census "
              f"({len(macs)} distinct, {st.rows:,} rows) =====")
        print(f"corrupt rows {st.n_corrupt} "
              f"(field={st.n_field_bad} med={st.n_med_bad} both={st.n_both}) "
              f"bad_parse={st.bad_parse}")
        only_corrupt = [m for m in macs if st.clean_n.get(m, 0) == 0]
        pair0d0a = [m for m in macs if "0d:0a" in m or "0a:0d" in m]
        any0d0a = [m for m in macs
                   if any(o in ("0d", "0a") for o in m.split(":"))]
        print(f"seen ONLY on corrupt rows: {len(only_corrupt)}")
        print(f"'0d:0a' adjacent-pair screen: {len(pair0d0a)} {pair0d0a}")
        print(f"any octet 0d or 0a: {len(any0d0a)} {any0d0a}")
        near = []
        for m in macs:
            if m in BEACONS:
                continue
            for bm, bn in BEACONS.items():
                d, pos = octet_hamming(m, bm)
                if d <= 3:
                    near.append((d, m, bn, pos, st.raw_n[m],
                                 st.clean_n.get(m, 0), st.corrupt_n.get(m, 0)))
        near.sort()
        print(f"byte-neighbours of a beacon MAC, d<=3: {len(near)}")
        for d, m, bn, pos, raw, cl, co in near:
            print(f"   d={d} {m} ~{bn} pos={pos} raw={raw} clean={cl} corrupt={co}")
        print("  -- top sources --")
        for m in macs[:8]:
            print(f"   {m:20s} raw={st.raw_n[m]:>9,} "
                  f"clean={st.clean_n.get(m,0):>9,} "
                  f"corrupt={st.corrupt_n.get(m,0):>7,}"
                  f"{'   <-- ' + BEACONS[m] if m in BEACONS else ''}")
        out[tag] = {"n_macs": len(macs), "near": len(near),
                    "only_corrupt": len(only_corrupt)}
    return out


# ------------------------------------------------------------------- verify

def run_verify(a):
    res = {}
    for tag in a.tags.split(","):
        st = load_scan(tag)
        span = (st.t_last_us - st.t0_us) * 1e-6
        print(f"\n===== {tag}: gap census (clean rows, span {span:.1f} s) =====")
        res[tag] = {}
        for m in BMACS:
            ts = np.frombuffer(st.ts[m], dtype=np.int64)
            if ts.size < 10:
                print(f"  {BEACONS[m]} {m}: {ts.size} clean frames -- skipped")
                continue
            d = np.diff(ts) * 1e-6
            t_rel = (ts[:-1] - st.t0_us) * 1e-6
            big = np.where(d >= GAP_MIN_S)[0]
            print(f"  {BEACONS[m]} {m}: n={ts.size:,} fps={ts.size/span:.2f} "
                  f"gap med={np.median(d)*1e3:.1f} ms p99={np.percentile(d,99)*1e3:.1f} ms "
                  f"max={d.max():.2f} s  |  gaps>={GAP_MIN_S}s: {big.size}")
            gl = []
            for i in big:
                print(f"      t={t_rel[i]:9.1f}s  gap={d[i]:7.2f}s  "
                      f"(ends t={t_rel[i]+d[i]:.1f}s)")
                gl.append((float(t_rel[i]), float(d[i])))
            res[tag][m] = gl
        # ---- RSSI changepoints, whole-file search (prereg 3.2)
        print(f"\n----- {tag}: RSSI changepoints (10 s bins, +-120 s medians) -----")
        for m in BMACS:
            nb = int(span // BIN_S) + 1
            med = np.full(nb, np.nan)
            for i in range(nb):
                b = st.bins.get((m, i))
                if b is not None and len(b.rssi) >= 5:
                    med[i] = np.median(np.array(b.rssi, dtype=np.float64))
            k = 12                                   # 120 s
            stat = np.full(nb, np.nan)
            for i in range(k, nb - k):
                pre = med[i - k:i]
                post = med[i:i + k]
                pre = pre[np.isfinite(pre)]
                post = post[np.isfinite(post)]
                if pre.size >= 6 and post.size >= 6:
                    stat[i] = abs(np.median(post) - np.median(pre))
            order = np.argsort(np.where(np.isfinite(stat), -stat, 0))
            picked, used = [], []
            for i in order:
                if not np.isfinite(stat[i]) or stat[i] <= 0:
                    continue
                if any(abs(i - j) < k for j in used):
                    continue
                used.append(i)
                picked.append((float(i * BIN_S), float(stat[i])))
                if len(picked) >= 5:
                    break
            print(f"  {BEACONS[m]}: top-5 |Delta median RSSI| "
                  + "  ".join(f"t={t:.0f}s:{v:.1f}dB" for t, v in picked))
            # value of the statistic at each logged event for this beacon,
            # and the nearest local maximum within +-90 s (prereg 3.2)
            for code, t_log, tmac, _d in EVENTS:
                if tmac != m:
                    continue
                i0 = int(round(t_log / BIN_S))
                loc = [(j, stat[j]) for j in range(max(k, i0 - 9),
                                                   min(nb - k, i0 + 10))
                       if np.isfinite(stat[j])]
                if not loc:
                    print(f"      {code}: no statistic near t={t_log:.0f}s")
                    continue
                jb, vb = max(loc, key=lambda z: z[1])
                print(f"      {code}: logged t={t_log:.0f}s  "
                      f"stat@logged={stat[i0] if np.isfinite(stat[i0]) else float('nan'):.1f}dB  "
                      f"best within +-90s: t={jb*BIN_S:.0f}s ({jb*BIN_S-t_log:+.0f}s) "
                      f"{vb:.1f}dB")
        # ---- level / rate per inter-event interval
        print(f"\n----- {tag}: level and rate per inter-event interval -----")
        edges = [0.0] + [e[1] for e in EVENTS] + [span]
        names = ["pre-18:01"] + [e[0] for e in EVENTS]
        for m in BMACS:
            print(f"  {BEACONS[m]}:")
            for i in range(len(edges) - 1):
                lo, hi = edges[i] + 40.0, edges[i + 1]
                if hi - lo < 30:
                    continue
                r = rssi_window(st, m, lo, hi)
                s_ = sfo_window(st, m, lo, hi)
                print(f"     {names[i]:>10s} [{lo:6.0f},{hi:6.0f})  "
                      f"rssi={r['med'] if r else float('nan'):6.1f}  "
                      f"fps={fps_window(st, m, lo, hi):6.2f}  "
                      f"sfo={s_['med'] if s_ else float('nan'):+.6f}  "
                      f"nwin={s_['n_win'] if s_ else 0}")
    return res


# -------------------------------------------------------------------- floor

def block_series(st, mac, t_lo, t_hi, blk):
    """Per-block (sfo, kappa, argkappa, absk, rssi, n_adm) over [t_lo,t_hi)."""
    out = []
    t = t_lo
    while t + blk <= t_hi:
        s = sfo_window(st, mac, t, t + blk)
        f = kappa_window(st, mac, t, t + blk)
        r = rssi_window(st, mac, t, t + blk)
        out.append({
            "t": t,
            "sfo": s["med"] if s else float("nan"),
            "n_win": s["n_win"] if s else 0,
            "kappa": f["kappa"] if f else complex("nan"),
            "arg": math.degrees(np.angle(f["kappa"])) if f else float("nan"),
            "abs": abs(f["kappa"]) if f else float("nan"),
            "n_adm": f["n"] if f else 0,
            "align": f["align"] if f else float("nan"),
            "align_sh": f["align_shift"] if f else float("nan"),
            "rssi": r["med"] if r else float("nan"),
        })
        t += blk
    return out


def _adj_stats(v):
    v = np.asarray(v, dtype=np.float64)
    ok = np.isfinite(v)
    if ok.sum() < 3:
        return float("nan"), float("nan"), float("nan")
    d = np.abs(np.diff(v[ok]))
    return float(d.max()), float(np.percentile(d, 95)), \
        float(np.nanmax(v[ok]) - np.nanmin(v[ok]))


def compute_floor(st):
    """FLOOR_adj / FLOOR_range per (mac, feature) from Q2 (prereg 4.3)."""
    fl = {}
    for m in BMACS:
        bs = block_series(st, m, Q2[0], Q2[1], FLOOR_BLOCK)
        kv = np.array([b["kappa"] for b in bs])
        okk = np.isfinite(kv)
        dk = np.abs(np.diff(kv[okk])) if okk.sum() >= 3 else np.array([np.nan])
        fl[m] = {
            "n_blocks": len(bs),
            "sfo": _adj_stats([b["sfo"] for b in bs]),
            "arg": _adj_stats([b["arg"] for b in bs]),
            "abs": _adj_stats([b["abs"] for b in bs]),
            "dkappa_max": float(np.nanmax(dk)),
            "dkappa_p95": float(np.nanpercentile(dk, 95)),
            "kappa_mean": complex(np.nanmean(kv[okk])) if okk.any() else complex("nan"),
            "blocks": bs,
        }
    mus = [fl[m]["kappa_mean"] for m in BMACS if np.isfinite(fl[m]["kappa_mean"])]
    if len(mus) >= 2:
        cen = np.mean(mus)
        fl["sigma_kappa"] = float(np.sqrt(np.mean([abs(u - cen) ** 2 for u in mus])))
    else:
        fl["sigma_kappa"] = float("nan")
    return fl


def run_floor(a):
    for tag in a.tags.split(","):
        st = load_scan(tag)
        fl = compute_floor(st)
        print(f"\n===== {tag}: WANDER FLOOR from Q2 "
              f"({Q2[0]:.0f}-{Q2[1]:.0f}s, {FLOOR_BLOCK:.0f}s blocks) =====")
        print(f"  sigma_kappa (this file, Q2, 3 beacons) = {fl['sigma_kappa']:.5f}")
        print(f"  sigma_sfo   (BETWEEN_UNIT_SD)          = {SIGMA_SFO:.5f}")
        for m in BMACS:
            f = fl[m]
            print(f"  -- {BEACONS[m]} ({f['n_blocks']} blocks) mean kappa="
                  f"{f['kappa_mean']:.5f}")
            print(f"     sfo   adj_max={f['sfo'][0]:.6f} ({f['sfo'][0]/SIGMA_SFO:5.2f} s) "
                  f"p95={f['sfo'][1]:.6f}  range={f['sfo'][2]:.6f} "
                  f"({f['sfo'][2]/SIGMA_SFO:.2f} s)")
            print(f"     |dk|  adj_max={f['dkappa_max']:.6f} "
                  f"({f['dkappa_max']/fl['sigma_kappa']:5.2f} sk) "
                  f"p95={f['dkappa_p95']:.6f}")
            print(f"     arg   adj_max={f['arg'][0]:7.2f} deg  range={f['arg'][2]:7.2f} deg")
            print(f"     |k|   adj_max={f['abs'][0]:.6f}  range={f['abs'][2]:.6f}")
        # Q1 short-timescale sanity check
        print(f"  -- Q1 ({Q1[0]:.0f}-{Q1[1]:.0f}s, {Q1_BLOCK:.0f}s blocks) --")
        for m in BMACS:
            bs = block_series(st, m, Q1[0], Q1[1], Q1_BLOCK)
            sfo_a = _adj_stats([b["sfo"] for b in bs])
            kv = np.array([b["kappa"] for b in bs])
            ok = np.isfinite(kv)
            dk = np.abs(np.diff(kv[ok])) if ok.sum() >= 2 else np.array([np.nan])
            print(f"     {BEACONS[m]}: n={len(bs)} sfo adj_max={sfo_a[0]:.6f} "
                  f"({sfo_a[0]/SIGMA_SFO:.2f} s)  |dk| max={np.nanmax(dk):.6f} "
                  f"n_adm={[b['n_adm'] for b in bs]}")


# ------------------------------------------------------------------- report

def resolve_events(measured, uselogged=False):
    """measured: {code: [t_start, t_end, kind]}.

    Returns {code: (t_start, t_end, guard, kind)}. A gap-located event carries
    its measured off-air interval and the tight +-5 s guard (prereg 4.4); an
    RSSI-located one is a single instant at 10 s resolution and keeps the
    +-30 s guard.
    """
    ev = {}
    for code, t_log, mac, desc in EVENTS:
        mm = measured.get(code)
        if mm is None or uselogged:
            ev[code] = (t_log, t_log, GUARD_LOG, "logged")
        elif mm[2] == "gap":
            ev[code] = (float(mm[0]), float(mm[1]), GUARD_MEAS, "gap")
        else:
            ev[code] = (float(mm[0]), float(mm[1]), GUARD_LOG, "rssi")
    return ev


def windows_for(code, ev, span):
    """Before/after windows, truncated at neighbouring event guards."""
    t0_, t1_, g, _k = ev[code]
    prev_lim, next_lim = 0.0, span
    for c, (ot0, ot1, og, _) in ev.items():
        if c == code:
            continue
        if ot1 < t0_ and ot1 + og > prev_lim:
            prev_lim = ot1 + og
        if ot0 > t1_ and ot0 - og < next_lim:
            next_lim = ot0 - og
    b_hi = t0_ - g
    b_lo = max(prev_lim, b_hi - W_EVENT)
    a_lo = t1_ + g
    a_hi = min(next_lim, a_lo + W_EVENT)
    return (b_lo, max(b_lo, b_hi)), (a_lo, max(a_lo, a_hi))


def cell_report(st, fl, mac, w_b, w_a, sk):
    sb, sa = sfo_window(st, mac, *w_b), sfo_window(st, mac, *w_a)
    kb, ka = kappa_window(st, mac, *w_b), kappa_window(st, mac, *w_a)
    rb, ra = rssi_window(st, mac, *w_b), rssi_window(st, mac, *w_a)
    d = {"mac": mac, "beacon": BEACONS[mac]}
    d["sfo_b"] = sb["med"] if sb else float("nan")
    d["sfo_a"] = sa["med"] if sa else float("nan")
    d["nwin_b"] = sb["n_win"] if sb else 0
    d["nwin_a"] = sa["n_win"] if sa else 0
    d["dsfo"] = d["sfo_a"] - d["sfo_b"]
    d["dsfo_sig"] = d["dsfo"] / SIGMA_SFO
    d["sfo_floor"] = fl[mac]["sfo"][0]
    d["sfo_above"] = (abs(d["dsfo"]) > fl[mac]["sfo"][0]
                      and abs(d["dsfo_sig"]) > 1.0)
    d["kb"] = kb["kappa"] if kb else complex("nan")
    d["ka"] = ka["kappa"] if ka else complex("nan")
    d["n_b"] = kb["n"] if kb else 0
    d["n_a"] = ka["n"] if ka else 0
    d["align_b"] = kb["align"] if kb else float("nan")
    d["align_shb"] = kb["align_shift"] if kb else float("nan")
    d["align_a"] = ka["align"] if ka else float("nan")
    d["align_sha"] = ka["align_shift"] if ka else float("nan")
    d["dk"] = abs(d["ka"] - d["kb"])
    d["dk_sig"] = d["dk"] / sk
    d["dk_floor"] = fl[mac]["dkappa_max"]
    d["dk_above"] = (d["dk"] > fl[mac]["dkappa_max"] and d["dk_sig"] > 1.0)
    d["darg"] = math.degrees(np.angle(d["ka"] / d["kb"])) \
        if np.isfinite(d["ka"]) and np.isfinite(d["kb"]) and abs(d["kb"]) > 0 \
        else float("nan")
    d["arg_floor"] = fl[mac]["arg"][0]
    d["dabs"] = abs(d["ka"]) - abs(d["kb"])
    d["rssi_b"] = rb["med"] if rb else float("nan")
    d["rssi_a"] = ra["med"] if ra else float("nan")
    d["runnable_k"] = (d["n_b"] >= IQ.FLOOR_CHUNK and d["n_a"] >= IQ.FLOOR_CHUNK)
    d["noise_b"] = (d["align_b"] <= d["align_shb"]) if kb else True
    d["noise_a"] = (d["align_a"] <= d["align_sha"]) if ka else True
    if not d["runnable_k"]:
        d["k_verdict"] = "NOT RUNNABLE"
    elif d["noise_b"] or d["noise_a"]:
        d["k_verdict"] = "NOISE FLOOR"
    elif d["dk_above"]:
        d["k_verdict"] = "ABOVE FLOOR"
    else:
        d["k_verdict"] = "wander"
    if d["nwin_b"] < 20 or d["nwin_a"] < 20:
        d["s_verdict"] = "THIN (<20 win)"
    elif d["sfo_above"]:
        d["s_verdict"] = "ABOVE FLOOR"
    else:
        d["s_verdict"] = "wander"
    return d


def run_summary(a):
    tags = a.tags.split(",")
    meas = {}
    mp = os.path.join(CACHE, "measured.json")
    if os.path.exists(mp) and not getattr(a, "uselogged", False):
        with open(mp) as f:
            meas = {k: v for k, v in json.load(f).items() if v is not None}
    S = {}
    for tag in tags:
        st = load_scan(tag)
        span = (st.t_last_us - st.t0_us) * 1e-6
        fl = compute_floor(st)
        ev = resolve_events(meas, getattr(a, "uselogged", False))
        S[tag] = (st, fl, ev, span)
        print(f"# {tag}: sigma_kappa={fl['sigma_kappa']:.5f} "
              f"sigma_sfo={SIGMA_SFO:.5f}")
    hdr = (f"{'event':<11}{'rx':<6}{'bcn':<4}{'role':<8}"
           f"{'dSFO/s':>8}{'flr/s':>7} {'SFOverdict':<14}"
           f"{'|dk|/sk':>8}{'flr/sk':>7} {'KAPverdict':<14}"
           f"{'darg':>8}{'/flr':>6}{'dRSSI':>7}{'cm|dk|':>8}")
    print(hdr)
    print("-" * len(hdr))
    for code, t_log, tmac, desc in EVENTS:
        for tag in tags:
            st, fl, ev, span = S[tag]
            sk = fl["sigma_kappa"]
            w_b, w_a = windows_for(code, ev, span)
            ds = {m: cell_report(st, fl, m, w_b, w_a, sk) for m in BMACS}
            # common-mode removal (docs/IDENTITY_STABILITY 13 / IQ_IMBALANCE 4.1):
            # componentwise median of the CONTROL deltas at this receiver
            cd = [ds[m]["ka"] - ds[m]["kb"] for m in BMACS if m != tmac]
            cm = complex(np.median([z.real for z in cd]),
                         np.median([z.imag for z in cd]))
            for m in BMACS:
                d = ds[m]
                res = abs((d["ka"] - d["kb"]) - cm) if m == tmac else float("nan")
                print(f"{code:<11}{tag:<6}{BEACONS[m]:<4}"
                      f"{'TREATED' if m == tmac else 'control':<8}"
                      f"{d['dsfo_sig']:>8.2f}{d['sfo_floor']/SIGMA_SFO:>7.2f} "
                      f"{d['s_verdict']:<14}"
                      f"{d['dk_sig']:>8.2f}{d['dk_floor']/sk:>7.2f} "
                      f"{d['k_verdict']:<14}"
                      f"{d['darg']:>8.1f}"
                      f"{abs(d['darg'])/d['arg_floor'] if d['arg_floor']>0 else float('nan'):>6.2f}"
                      f"{d['rssi_a']-d['rssi_b']:>7.1f}"
                      f"{res/sk if np.isfinite(res) else float('nan'):>8.2f}")
        print()


def run_periodic(a):
    """P3d: is there 20-40 min structure in Q2 that could mimic a settle?"""
    for tag in a.tags.split(","):
        st = load_scan(tag)
        blk = 60.0
        print(f"\n===== {tag}: Q2 periodicity scan, {blk:.0f}s blocks "
              f"({(Q2[1]-Q2[0])/60:.1f} min = "
              f"{(Q2[1]-Q2[0])/60/20:.2f} cycles at 20 min, "
              f"{(Q2[1]-Q2[0])/60/40:.2f} at 40 min) =====")
        bs_all = {m: block_series(st, m, Q2[0], Q2[1], blk) for m in BMACS}
        periods = np.arange(10.0, 45.0, 0.5) * 60.0
        w = 2 * np.pi / periods
        for m in BMACS:
            bs = bs_all[m]
            t = np.array([b["t"] for b in bs])
            for name, v in (("sfo", np.array([b["sfo"] for b in bs])),
                            ("argk", np.array([b["arg"] for b in bs])),
                            ("|k|", np.array([b["abs"] for b in bs])),
                            ("rssi", np.array([b["rssi"] for b in bs]))):
                ok = np.isfinite(v)
                if ok.sum() < 20:
                    print(f"  {BEACONS[m]} {name}: n={ok.sum()} too few")
                    continue
                tt, vv = t[ok], v[ok] - v[ok].mean()
                # remove the linear trend first: with only 1.4-2.8 cycles in
                # the window a low-frequency sinusoid otherwise just fits drift
                Al = np.column_stack([tt - tt.mean(), np.ones(tt.size)])
                cl, *_ = np.linalg.lstsq(Al, vv, rcond=None)
                vv = vv - Al @ cl
                # least-squares sinusoid power at each trial period
                pw = []
                for wi in w:
                    A = np.column_stack([np.cos(wi * tt), np.sin(wi * tt),
                                         np.ones(tt.size)])
                    c, *_ = np.linalg.lstsq(A, vv, rcond=None)
                    r = vv - A @ c
                    pw.append(1.0 - (r ** 2).sum() / (vv ** 2).sum())
                pw = np.array(pw)
                band = (periods >= 20 * 60) & (periods <= 40 * 60)
                ib = int(np.argmax(pw[band]))
                print(f"  {BEACONS[m]:<3}{name:<5} n={ok.sum():3d} "
                      f"best-in-20-40min: T={periods[band][ib]/60:5.1f} min "
                      f"R2={pw[band][ib]:.3f}   "
                      f"best-overall: T={periods[int(np.argmax(pw))]/60:5.1f} min "
                      f"R2={pw.max():.3f}")


def run_report(a):
    tags = a.tags.split(",")
    meas = {}
    mp = os.path.join(CACHE, "measured.json")
    if os.path.exists(mp):
        with open(mp) as f:
            meas = {k: v for k, v in json.load(f).items() if v is not None}
        print(f"[measured event times loaded from {mp}: {meas}]")
    for tag in tags:
        st = load_scan(tag)
        span = (st.t_last_us - st.t0_us) * 1e-6
        fl = compute_floor(st)
        sk = fl["sigma_kappa"]
        ev = resolve_events(meas, getattr(a, "uselogged", False))
        print(f"\n########## {tag}  (sigma_kappa={sk:.5f}, "
              f"sigma_sfo={SIGMA_SFO:.5f}) ##########")
        for code, t_log, tmac, desc in EVENTS:
            t0_, t1_, g, kind = ev[code]
            w_b, w_a = windows_for(code, ev, span)
            print(f"\n=== {code}  {desc}")
            print(f"    logged t={t_log:.1f}s  used [{t0_:.1f},{t1_:.1f}]s "
                  f"({t0_-t_log:+.1f}s) guard={g:.0f}s  source={kind}")
            print(f"    before=[{w_b[0]:.0f},{w_b[1]:.0f}) {w_b[1]-w_b[0]:.0f}s   "
                  f"after=[{w_a[0]:.0f},{w_a[1]:.0f}) {w_a[1]-w_a[0]:.0f}s")
            for m in BMACS:
                role = "TREATED" if m == tmac else "control"
                d = cell_report(st, fl, m, w_b, w_a, sk)
                flag_s = "ABOVE" if d["sfo_above"] else "  -  "
                flag_k = "ABOVE" if d["dk_above"] else "  -  "
                extra = ""
                if not d["runnable_k"]:
                    extra += "  [kappa NOT RUNNABLE: n<2000]"
                if d["noise_b"] or d["noise_a"]:
                    extra += "  [kappa AT NOISE FLOOR]"
                print(f"    {BEACONS[m]} {role:8s} "
                      f"rssi {d['rssi_b']:6.1f}->{d['rssi_a']:6.1f}  "
                      f"n {d['n_b']:>7,}/{d['n_a']:>7,}")
                print(f"        SFO  {d['sfo_b']:+.6f} -> {d['sfo_a']:+.6f}  "
                      f"D={d['dsfo']:+.6f} = {d['dsfo_sig']:+6.2f} s   "
                      f"floor={d['sfo_floor']:.6f} ({d['sfo_floor']/SIGMA_SFO:.2f} s)  {flag_s}")
                print(f"        kap  {d['kb']:.5f} -> {d['ka']:.5f}  "
                      f"|Dk|={d['dk']:.6f} = {d['dk_sig']:6.2f} sk  "
                      f"floor={d['dk_floor']:.6f} ({d['dk_floor']/sk:.2f} sk)  {flag_k}")
                print(f"        arg  {math.degrees(np.angle(d['kb'])):+7.2f} -> "
                      f"{math.degrees(np.angle(d['ka'])):+7.2f} deg  "
                      f"Darg={d['darg']:+7.2f} deg  floor={d['arg_floor']:.2f} deg   "
                      f"|k| {abs(d['kb']):.5f}->{abs(d['ka']):.5f}{extra}")


# ---------------------------------------------------------------- selfcheck

def run_selfcheck(a):
    dp = os.path.join(_HERE, "rff", "dsp.py")
    ip = os.path.join(_HERE, "exp_iq_imbalance.py")
    print(f"dsp.py     sha256 {sha256(dp)}  mtime {os.path.getmtime(dp)}")
    print(f"exp_iq_imbalance.py sha256 {sha256(ip)}  mtime {os.path.getmtime(ip)}")
    src = open(dp, "rb").read().decode()
    assert "iq[1::2] + 1j * iq[0::2]" in src, "interleave convention changed"
    print("interleave convention on disk: iq[1::2] + 1j*iq[0::2]  (imag,real)  OK")
    import inspect
    for fn in (IQ.frames_to_H, IQ.deslope, IQ.process_batch, IQ.features,
               IQ.add_cells):
        assert inspect.getsourcefile(fn) == ip, fn
    print("kappa estimator functions imported from exp_iq_imbalance.py  OK")
    assert dsp.FrameEstimator.__module__ == "rff.dsp"
    print("FrameEstimator imported from rff.dsp, unmodified  OK")
    # checkpoint/resume equivalence of the RANSAC RNG (prereg 2.1)
    e1 = dsp.FrameEstimator()
    rng_a = pickle.loads(pickle.dumps(e1))
    x = np.arange(52.0)
    y = 0.01 * x + 0.3
    r1 = [dsp.ransac_line(x, y, rng=e1._rng)[0] for _ in range(50)]
    r2 = [dsp.ransac_line(x, y, rng=rng_a._rng)[0] for _ in range(50)]
    assert r1 == r2, "pickle does not preserve Generator state"
    print("pickle round-trip preserves numpy Generator state  OK "
          "-> checkpointed replay == uninterrupted replay")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--tag", required=True)
    s.add_argument("--path", required=True)
    s.add_argument("--resume", action="store_true")
    s.add_argument("--seconds", type=float, default=0.0)
    for name in ("census", "verify", "report", "selfcheck", "floor",
                 "summary", "periodic"):
        q = sub.add_parser(name)
        q.add_argument("--tags", default="d0wd,s3")
        q.add_argument("--uselogged", action="store_true")
    a = p.parse_args()
    globals()["run_" + a.cmd](a)


if __name__ == "__main__":
    main()
