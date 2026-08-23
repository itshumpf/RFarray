#!/usr/bin/env python3
"""exp_v2_pre_checks_0823 — the four unrun docs/V2_SPEC.md section 7(a) checks.

Runs (a)3, (a)4, (a)6, (a)7 against files already in data/raw/. Read-only:
every file is opened "r" and never written, renamed or deleted. No serial
port is opened. A capture may be running while this executes, so every
reader drops a final line that does not end in "\\n" (a partially written
row) and counts it.

Subcommands:
    a3    tail-drop bias           s3_20260822_023034.csv
    a4    k=+1 bin, July history   desk_* node3_* rx_* occ_* d0wd_* s3_*
    a67   peak delivered rate + corrupt-row rate (one shared scan)
    rng   FrameEstimator RANSAC path-dependence demonstration (for 5.5)

Usage:  python pc/exp_v2_pre_checks_0823.py <sub> [<sub> ...]
"""
import os
import sys
import math
import glob
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rff.dsp import (FrameEstimator, csi_to_complex, _USABLE_IDX, K_USABLE)

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "data", "raw")

B1 = "a4:f0:0f:77:91:20"
B2 = "28:05:a5:2f:fa:48"
B3 = "f4:2d:c9:70:72:30"
BEACONS = {B1: "B1", B2: "B2", B3: "B3"}

V1_OVERHEAD = 28          # 12 B header + 15 B payload preamble + 1 B xor
V2_OVERHEAD = 39          # 17 B header + 20 B payload preamble + 2 B CRC
UART_BPS = 46080          # 460800 baud 8N1 = 10 bit/byte (throughput_test.py:134)


# --------------------------------------------------------------------------
# row access.  csi_data is a quoted comma-separated list, so field 10 is not
# a single split(",") token.  Fields 1..9 come off the front with a bounded
# split; node_id/env_id/dropped (13-column era only) come off the back with
# a bounded rsplit.  Nothing here uses split(",", 128) -- see spec 2.10.
# --------------------------------------------------------------------------
def ncols(path):
    with open(path, "r") as f:
        return len(f.readline().split(","))


def rows(path, want_csi=False):
    """Yield (head9, csi_str_or_None, tail3_or_None) for each complete row.

    A trailing line with no "\\n" is a partially written row and is skipped;
    the count is reported by the caller through `rows.partial`.
    """
    rows.partial = 0
    rows.short = 0
    nc = ncols(path)
    with open(path, "r") as f:
        f.readline()
        for line in f:
            if not line.endswith("\n"):
                rows.partial += 1
                break
            p = line.split(",", 9)
            if len(p) < 10:
                rows.short += 1
                continue
            body = p[9]
            if nc == 13:
                q = body.rsplit(",", 3)
                if len(q) < 4:
                    rows.short += 1
                    continue
                tail = q[1:]
                cs = q[0]
            else:
                tail = None
                cs = body
            yield p[:9], (cs.strip().strip('"') if want_csi else None), tail


def wrap16(d):
    return d + 65536 if d < 0 else d


# --------------------------------------------------------------------------
# the six-column field-plausibility screen of OVERNIGHT_2026-08-22.md section 1
# (route 2).  On 10-column era-A files only four of the six columns exist;
# `common4` is the subset every era carries, so rates stay comparable.
# --------------------------------------------------------------------------
def screens(path):
    """Return (mode_node, mode_chan) after one cheap pre-pass."""
    hn, hc = {}, {}
    n = 0
    for head, _, tail in rows(path):
        n += 1
        if n > 20000:
            break
        hc[head[6]] = hc.get(head[6], 0) + 1
        if tail is not None:
            hn[tail[0]] = hn.get(tail[0], 0) + 1
    mode_c = max(hc, key=hc.get) if hc else None
    mode_n = max(hn, key=hn.get) if hn else None
    return mode_n, mode_c


def plausible4(head, mode_c):
    """channel, csi_len, noise_floor, rssi -- the columns every era carries."""
    try:
        if head[6] != mode_c:
            return False
        if head[8] not in ("128", "256", "384"):
            return False
        nf = int(head[5])
        if not (-110 <= nf <= -70):
            return False
        rs = int(head[4])
        if not (-100 <= rs <= -10):
            return False
    except ValueError:
        return False
    return True


def plausible6(head, tail, mode_n, mode_c):
    if not plausible4(head, mode_c):
        return False
    if tail is None:
        return None                      # not askable on a 10-column file
    if tail[0] != mode_n or tail[1] != "0":
        return False
    return True


# ==========================================================================
# (a)3 -- does tail-drop bias the survivors?
# ==========================================================================
CACHE = os.path.join(os.environ.get("TMPDIR", "/tmp"), "v2_pre_checks_0823")


def a3p(f0=0.0, f1=1.0, path=None):
    """One byte-range part of (a)3.  Writes a cache OUTSIDE the repo tree.

    Each part restarts the FrameEstimator, so its RANSAC RNG restarts too.
    That changes individual slopes -- exactly the effect measured for 5.5 --
    but not the association being tested, and the alternative (one 3.5 M
    frame replay) does not fit in one run here.  Stated, not hidden.
    """
    path = path or os.path.join(RAW, "s3_20260822_023034.csv")
    os.makedirs(CACHE, exist_ok=True)
    size = os.path.getsize(path)
    a, b = int(size * f0), int(size * f1)
    mode_n, mode_c = screens(path)
    est = {m: FrameEstimator() for m in BEACONS}
    rec = {m: {"d": [], "s": [], "ir": [], "rs": [], "t": []} for m in BEACONS}
    prev_drop = None
    nrow = nscreen = nfit_none = npart = 0
    t0 = time.time()
    with open(path, "r") as f:
        if a:
            f.seek(a)
            f.readline()
        else:
            f.readline()
        while f.tell() < b:
            line = f.readline()
            if not line:
                break
            if not line.endswith("\n"):
                npart += 1
                break
            nrow += 1
            p = line.split(",", 9)
            if len(p) < 10:
                continue
            q = p[9].rsplit(",", 3)
            if len(q) < 4:
                continue
            head, tail = p[:9], q[1:]
            if plausible6(head, tail, mode_n, mode_c) is False:
                nscreen += 1
                prev_drop = None         # a corrupt row breaks the delta chain
                continue
            d = int(tail[2])
            delta = wrap16(d - prev_drop) if prev_drop is not None else None
            prev_drop = d
            mac = head[3]
            if mac not in BEACONS or delta is None:
                continue
            vals = np.array(q[0].strip().strip('"').split(","),
                            dtype=np.float64)
            r = est[mac].feed(vals, int(head[7]))
            if r is None:
                nfit_none += 1
                continue
            g = rec[mac]
            g["d"].append(delta)
            g["s"].append(r["slope"])
            g["ir"].append(r["inlier_ratio"])
            g["rs"].append(r["resid_std"])
            g["t"].append(int(head[0]))
    out = os.path.join(CACHE, f"a3_{f0:.3f}.npz")
    kw = {}
    for m, name in BEACONS.items():
        for k in ("d", "s", "ir", "rs", "t"):
            kw[f"{name}_{k}"] = np.array(rec[m][k])
    kw["meta"] = np.array([nrow, nscreen, nfit_none, npart, time.time() - t0])
    np.savez_compressed(out, **kw)
    print(f"part {f0:.3f}-{f1:.3f}: rows {nrow:,}  screened {nscreen:,}  "
          f"fit-None {nfit_none:,}  partial {npart}  "
          f"[{time.time()-t0:.0f} s]  -> {out}")


def a3():
    """Aggregate the (a)3 parts written by a3p."""
    path = os.path.join(RAW, "s3_20260822_023034.csv")
    print(f"\n=== (a)3 tail-drop bias :: {os.path.basename(path)} ===")
    print("per-frame SFO against the `dropped` delta on the row immediately\n"
          "before it -- the samples the 64-deep queue refused just before "
          "this\nframe was accepted (spec 7(a)3's named proxy for the 2.6 "
          "field).")
    parts = sorted(glob.glob(os.path.join(CACHE, "a3_*.npz")))
    if not parts:
        print("no parts in cache; run a3p first")
        return
    rec = {m: {k: [] for k in ("d", "s", "ir", "rs", "t")} for m in BEACONS}
    meta = np.zeros(5)
    for p in parts:
        z = np.load(p)
        meta += z["meta"]
        for m, name in BEACONS.items():
            for k in ("d", "s", "ir", "rs", "t"):
                rec[m][k].append(z[f"{name}_{k}"])
    for m in BEACONS:
        for k in rec[m]:
            rec[m][k] = np.concatenate(rec[m][k])
    print(f"\n{len(parts)} byte-range parts, each replaying its own "
          f"FrameEstimator from its\nown origin (see 5.5): rows {int(meta[0]):,}"
          f"  field-screen rejects {int(meta[1]):,}"
          f"  RANSAC None {int(meta[2]):,}  partial rows {int(meta[3])}")
    print("\n-- ALL fitted frames --")
    _a3_tables(rec, accepted_only=False)
    print("\n-- frames the shipped gates ACCEPT "
          "(inlier_ratio >= 0.6 and resid_std <= 0.8, dsp.py:164,173,175) --")
    _a3_tables(rec, accepted_only=True)


def _pearson(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    if a.size < 3 or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _partial(x, y, z):
    rxy, rxz, ryz = _pearson(x, y), _pearson(x, z), _pearson(y, z)
    den = math.sqrt(max(1e-12, (1 - rxz ** 2) * (1 - ryz ** 2)))
    return (rxy - rxz * ryz) / den, rxy, rxz, ryz


def _a3_tables(rec, accepted_only):
    BUCKETS = [(0, 0), (1, 1), (2, 2), (3, 5), (6, 10), (11, 10 ** 9)]
    hdr = (f"{'cell':<6}{'n':>10}{'median SFO':>13}{'r(SFO,drop)':>13}"
           f"{'r partial|resid':>17}{'r(SFO,resid)':>14}{'r(drop,resid)':>15}")
    print(hdr)
    for mac, name in BEACONS.items():
        b = rec[mac]
        d = np.array(b["d"], float)
        s = np.array(b["s"], float)
        ir = np.array(b["ir"], float)
        rs = np.array(b["rs"], float)
        if accepted_only:
            k = (ir >= 0.6) & (rs <= 0.8)
            d, s, ir, rs = d[k], s[k], ir[k], rs[k]
        if s.size < 100:
            print(f"{name:<6}{s.size:>10}  (too few)")
            continue
        pr, rxy, rxz, ryz = _partial(d, s, rs)
        print(f"{name:<6}{s.size:>10,}{np.median(s):>13.5f}{rxy:>13.4f}"
              f"{pr:>17.4f}{ryz:>14.4f}{rxz:>15.4f}")

    print(f"\n{'cell':<6}{'bucket':<10}{'n':>10}{'median SFO':>13}"
          f"{'delta vs bucket 0':>20}{'in BETWEEN_UNIT_SD':>20}")
    BUS = 0.00237                       # pc/exp_thermal_evidence.py:129
    for mac, name in BEACONS.items():
        b = rec[mac]
        d = np.array(b["d"], float)
        s = np.array(b["s"], float)
        ir = np.array(b["ir"], float)
        rs = np.array(b["rs"], float)
        if accepted_only:
            k = (ir >= 0.6) & (rs <= 0.8)
            d, s = d[k], s[k]
        if s.size < 100:
            continue
        base = None
        for lo, hi in BUCKETS:
            k = (d >= lo) & (d <= hi)
            if k.sum() < 30:
                print(f"{name:<6}{f'{lo}-{hi}' if hi < 10**9 else f'{lo}+':<10}"
                      f"{int(k.sum()):>10,}   (too few)")
                continue
            m = float(np.median(s[k]))
            if base is None:
                base = m
            lbl = f"{lo}-{hi}" if hi < 10 ** 9 else f"{lo}+"
            print(f"{name:<6}{lbl:<10}{int(k.sum()):>10,}{m:>13.5f}"
                  f"{m-base:>+20.6f}{abs(m-base)/BUS:>20.2f}")


# ==========================================================================
# (a)4 -- does the d0wd's k=+1 bin predate the S3 entirely?
# ==========================================================================
def _chunk_stats(path, mac, offsets=7, per_chunk=2500):
    size = os.path.getsize(path)
    if size < 4096:
        return None
    fracs = [0.02, 0.15, 0.30, 0.45, 0.60, 0.75, 0.90][:offsets]
    out = []
    nc = ncols(path)
    with open(path, "r") as f:
        for fr in fracs:
            f.seek(int(size * fr))
            f.readline()                 # discard the partial line at the seek
            acc = []
            for line in f:
                if not line.endswith("\n"):
                    break
                p = line.split(",", 9)
                if len(p) < 10 or p[3] != mac or p[8] != "256":
                    continue
                body = p[9]
                cs = (body.rsplit(",", 3)[0] if nc == 13 else body)
                v = np.array(cs.strip().strip('"').split(","), dtype=np.float64)
                if v.size < 128:
                    continue
                acc.append(v[:128])
                if len(acc) >= per_chunk:
                    break
            if len(acc) < 200:
                continue
            m = np.array(acc)
            csi = m[:, 1::2] + 1j * m[:, 0::2]        # dsp.py:52 convention
            u = csi[:, _USABLE_IDX]                   # sorted by physical k
            amp = np.abs(u)
            per_bin = np.median(amp, axis=0)
            band = float(np.median(per_bin))
            k1 = float(per_bin[list(K_USABLE).index(1)])
            low = [int(K_USABLE[i]) for i in range(len(K_USABLE))
                   if per_bin[i] < 0.40 * band]
            ph = np.angle(u)
            dphi = np.angle(np.exp(1j * np.diff(ph, axis=1)))
            frac = (np.abs(dphi) > 2.5).mean(axis=0)
            wi = int(np.argmax(frac))
            out.append(dict(n=len(acc), band=band, k1=k1, low=low,
                            worst=float(frac[wi]),
                            gap=(int(K_USABLE[wi]), int(K_USABLE[wi + 1]))))
    return out or None


def a4():
    print("\n=== (a)4 does the k=+1 bin predate the S3? ===")
    print("(a)1's sweep re-run on the reference beacon a4:f0:0f:77:91:20, "
          "len=256,\n7 byte offsets x up to 2,500 frames per file.\n")
    print("NOTE ON IDENTITY: docs/NODE_CENSUS.md 3.3 states that whether the "
          "era-B/C\ncollector (node_id 68) is the same physical board as "
          "era A's `desk` is\n'not established by anything in the data'. This "
          "sweep therefore measures\nfile lineages, not boards. node3_* is "
          "included as the era-A contrast.\n")
    groups = [("desk_*", "era A 07-12/13, filename `desk`"),
              ("node3_*", "era A 07-12/13, filename `node3`"),
              ("harvest_afternoon.csv", "era A, unattributed"),
              ("rx_*", "era B/C 07-14..07-23, node_id 68"),
              ("occ_*", "era C 07-22, node_id 68"),
              ("d0wd_*", "2026-08, node_id 68"),
              ("s3_*", "2026-08, node_id 108 (control)")]
    hdr = (f"{'file':<34}{'chunks':>7}{'frames':>9}{'band med':>10}"
           f"{'k=+1 med':>10}{'ratio':>8}  {'bins <40% band':<20}"
           f"{'worst gap':>12}{'frac>2.5rad':>12}")
    for pat, what in groups:
        print(f"\n--- {pat}  ({what}) ---")
        print(hdr)
        for path in sorted(glob.glob(os.path.join(RAW, pat))):
            if not path.endswith(".csv"):
                continue
            try:
                st = _chunk_stats(path, B1)
            except Exception as e:                        # noqa: BLE001
                print(f"{os.path.basename(path):<34}  ERROR {e}")
                continue
            if st is None:
                print(f"{os.path.basename(path):<34}"
                      f"  no chunk reached 200 reference-beacon len-256 frames")
                continue
            n = sum(s["n"] for s in st)
            band = float(np.median([s["band"] for s in st]))
            k1 = float(np.median([s["k1"] for s in st]))
            low = sorted({b for s in st for b in s["low"]})
            wi = int(np.argmax([s["worst"] for s in st]))
            print(f"{os.path.basename(path):<34}{len(st):>7}{n:>9,}"
                  f"{band:>10.2f}{k1:>10.2f}{k1/band:>8.3f}  "
                  f"{str(low if low else 'none'):<20}"
                  f"{str(st[wi]['gap']):>12}{st[wi]['worst']*100:>11.2f}%")


# ==========================================================================
# (a)6 peak delivered rate  +  (a)7 corrupt rows per byte -- one scan
# ==========================================================================
def a67():
    print("\n=== (a)6 + (a)7 :: one shared scan of data/raw/ ===")
    print(f"V1 frame = {V1_OVERHEAD} + csi_len B; V2 frame = "
          f"{V2_OVERHEAD} + csi_len B (spec section 3);\n"
          f"UART budget = {UART_BPS} B/s (460800 8N1, "
          f"pc/throughput_test.py:134).\n")
    files = sorted(glob.glob(os.path.join(RAW, "*.csv")))
    hdr = (f"{'file':<34}{'rows':>11}{'bytes':>14}{'corrupt4':>9}"
           f"{'corrupt6':>9}{'per byte':>11}{'span s':>10}"
           f"{'mean fps':>9}{'pk1s fps':>9}{'pk V1 %':>9}{'pk V2 %':>9}"
           f"{'s>100% V2':>10}")
    print(hdr)
    for path in files:
        try:
            _a67_one(path)
        except Exception as e:                            # noqa: BLE001
            print(f"{os.path.basename(path):<34}  ERROR {e}")


def _a67_one(path):
    size = os.path.getsize(path)
    if size < 4096:
        print(f"{os.path.basename(path):<34}  (empty or header only, "
              f"{size} B)")
        return
    mode_n, mode_c = screens(path)
    sec_rows = {}
    sec_v1 = {}
    sec_v2 = {}
    n = c4 = c6 = 0
    t_lo = t_hi = None
    for head, _, tail in rows(path):
        n += 1
        ok4 = plausible4(head, mode_c)
        if not ok4:
            c4 += 1
        ok6 = plausible6(head, tail, mode_n, mode_c)
        if ok6 is False:
            c6 += 1
        try:
            t = int(head[0])
            ln = int(head[8])
        except ValueError:
            continue
        if t_lo is None:
            t_lo = t
        t_hi = t
        s = t // 1000000
        sec_rows[s] = sec_rows.get(s, 0) + 1
        sec_v1[s] = sec_v1.get(s, 0) + V1_OVERHEAD + ln
        sec_v2[s] = sec_v2.get(s, 0) + V2_OVERHEAD + ln
    if not sec_rows or t_lo is None:
        print(f"{os.path.basename(path):<34}  (no parsable rows)")
        return
    # drop the first and last second: both are partial by construction
    ks = sorted(sec_rows)
    interior = ks[1:-1] if len(ks) > 2 else ks
    span = (t_hi - t_lo) / 1e6
    mean_fps = n / span if span > 0 else float("nan")
    pk_rows = max(sec_rows[k] for k in interior)
    pk_v1 = max(sec_v1[k] for k in interior)
    pk_v2 = max(sec_v2[k] for k in interior)
    over = sum(1 for k in interior if sec_v2[k] > UART_BPS)
    nc = ncols(path)
    c6s = f"{c6:,}" if nc == 13 else "n/a"
    flag = "  <- partial final row skipped" if rows.partial else ""
    print(f"{os.path.basename(path):<34}{n:>11,}{size:>14,}{c4:>9,}"
          f"{c6s:>9}{(c6 if nc == 13 else c4)/size:>11.2e}"
          f"{span:>10.1f}{mean_fps:>9.2f}{pk_rows:>9,}"
          f"{100*pk_v1/UART_BPS:>8.1f}%{100*pk_v2/UART_BPS:>8.1f}%"
          f"{over:>10,}{flag}")


# ==========================================================================
# 5.5 -- is a slope path-dependent through the per-instance RANSAC RNG?
# ==========================================================================
def rng():
    print("\n=== 5.5 :: FrameEstimator RANSAC RNG path-dependence ===")
    path = os.path.join(RAW, "d0wd_20260822_144424.csv")
    frames = []
    for head, cs, tail in rows(path, want_csi=True):
        if head[3] != B1 or head[8] != "256":
            continue
        frames.append((np.array(cs.split(","), dtype=np.float64),
                       int(head[7])))
        if len(frames) >= 400:
            break
    print(f"source: {os.path.basename(path)}, first 400 B1 len-256 frames\n")

    def run(fs):
        e = FrameEstimator()
        return [e.feed(v, t) for v, t in fs]

    full = run(frames)
    for skip in (0, 1, 2, 10):
        part = run(frames[skip:])
        # compare frame index 300 of the file under both replay origins
        a = full[300]["slope"]
        b = part[300 - skip]["slope"]
        same = "identical" if a == b else "DIFFERENT"
        print(f"  replay from frame {skip:>2}: slope of file-frame 300 = "
              f"{b:+.9f}  vs {a:+.9f} from frame 0  -> {same}"
              f"   delta {b-a:+.3e} rad/sc")
    n_diff = 0
    part = run(frames[1:])
    for i in range(1, 400):
        if full[i] is None or part[i - 1] is None:
            continue
        if full[i]["slope"] != part[i - 1]["slope"]:
            n_diff += 1
    print(f"\n  over 399 frames, replaying from frame 1 instead of frame 0 "
          f"changes\n  the slope of {n_diff} of them "
          f"({100*n_diff/399:.1f} %).")
    print("\n  ransac_line draws two rng.integers(size=64) per call "
          "(dsp.py:85-86)\n  from the estimator's own generator "
          "(dsp.py:118,132), so the hypothesis\n  set at frame N depends on "
          "N. csi_to_complex returning None (dsp.py:128)\n  is the one path "
          "that does NOT advance it.")
    _rng_window()


def _rng_window(path=None, mac=None, nmax=60000):
    """How far the path dependence reaches into an emitted window median."""
    from rff.dsp import WindowAggregator
    path = path or os.path.join(RAW, "d0wd_20260822_144424.csv")
    mac = mac or B3
    fs = []
    for head, cs, tail in rows(path, want_csi=True):
        if head[3] != mac or head[8] != "256":
            continue
        fs.append((np.array(cs.split(","), dtype=np.float64), int(head[7]),
                   int(head[4])))
        if len(fs) >= nmax:
            break

    def run(seq):
        """Per-frame slope and accept flag, indexed by position in `seq`,
        plus the window medians the shipped aggregator would emit."""
        e = FrameEstimator()
        w = WindowAggregator()
        slope = np.full(len(seq), np.nan)
        acc = np.zeros(len(seq), bool)
        win = []
        for i, (v, t, r) in enumerate(seq):
            est = e.feed(v, t)
            if est is not None:
                slope[i] = est["slope"]
                acc[i] = (est["inlier_ratio"] >= 0.6
                          and est["resid_std"] <= 0.8)
            o = w.feed(est, t, r)
            if o:
                win.append(o["sfo"])
        return slope, acc, win

    s0, k0, w0 = run(fs)
    s1, k1, w1 = run(fs[1:])
    # index-align: file-frame i is s0[i] and s1[i-1]
    s0a, k0a = s0[1:], k0[1:]
    n = len(s1)
    both = k0a & k1 & ~np.isnan(s0a) & ~np.isnan(s1)
    d = np.abs(s0a[both] - s1[both])
    BUS = 0.00237
    print(f"\n  -- how far it reaches -- {os.path.basename(path)}, "
          f"{BEACONS[mac]}, {len(fs):,} frames, index-aligned "
          f"(file-frame i under both replay origins)")
    print(f"  gate decision flipped on {int((k0a != k1).sum()):,} of {n:,} "
          f"frames ({100*(k0a != k1).mean():.2f} %) -- the accepted set "
          f"itself is path-dependent")
    print(f"  frames accepted under BOTH ({int(both.sum()):,}): "
          f"{100*(d>0).mean():.1f} % differ, "
          f"median |delta| {np.median(d):.2e}, p99 {np.percentile(d,99):.2e}, "
          f"max {d.max():.2e} rad/sc "
          f"(median = {np.median(d)/BUS:.2f} x BETWEEN_UNIT_SD)")
    nw = min(len(w0), len(w1))
    if nw:
        dw = np.abs(np.array(w0[:nw]) - np.array(w1[:nw]))
        print(f"  emitted 64-frame window medians, {len(w0)} vs {len(w1)} "
              f"windows, first {nw} compared in order:")
        print(f"    {100*(dw>0).mean():.1f} % differ, median |delta| "
              f"{np.median(dw):.2e} ({np.median(dw)/BUS:.2f} x SD), "
              f"max {dw.max():.2e} ({dw.max()/BUS:.2f} x SD)")
        print("    (windows are cut on accepted frames, so a flipped gate "
              "decision shifts\n     every later window boundary -- this "
              "compares window k to window k, not\n     the same 64 frames "
              "to the same 64 frames)")


# ==========================================================================
# (a)6, second route -- loss against offered load, and sustained-window rate.
# pc_time_us is a per-serial-drain-batch host stamp (OVERNIGHT 1), so a
# 1 s bin measures host batching as much as wire rate.  Longer windows
# smooth it; the queue's own drop rate is the independent witness.
# ==========================================================================
def a6b():
    print("\n=== (a)6 second route :: loss vs offered load, 13-column "
          "captures ===")
    print("`dropped` is screened by the six-column field plausibility test "
          "and\naccumulated wrap-safe (OVERNIGHT_2026-08-22.md 1, 4.2). "
          "Offered = delivered + drops.\n"
          "V1 = 28 + csi_len B on the wire; V2 = 39 + csi_len B "
          "(spec 3).\n")
    pats = ["desk_20260821*.csv", "occ_*.csv", "rx_*.csv", "d0wd_*.csv"]
    hdr = (f"{'file':<34}{'delivered':>11}{'drops':>10}{'loss %':>9}"
           f"{'mean fps':>9}{'meanV1 %':>9}{'meanV2 %':>9}"
           f"{'max10s V1':>10}{'max10s V2':>10}{'max60s V1':>10}"
           f"{'max60s V2':>10}{'max60s fps':>10}{'spike':>7}")
    print(hdr)
    for pat in pats:
        for path in sorted(glob.glob(os.path.join(RAW, pat))):
            try:
                _a6b_one(path)
            except Exception as e:                        # noqa: BLE001
                print(f"{os.path.basename(path):<34}  ERROR {e}")


def _a6b_one(path):
    if ncols(path) != 13 or os.path.getsize(path) < 4096:
        return
    mode_n, mode_c = screens(path)
    prev = None
    drops = 0
    delivered = 0
    spike = 0
    sec_v1, sec_v2, sec_n = {}, {}, {}
    t_lo = t_hi = None
    pend = []                            # 3-deep pipeline for the spike test
    for head, _, tail in rows(path):
        if plausible6(head, tail, mode_n, mode_c) is False:
            continue                     # route 2: six-column field screen
        pend.append((head, int(tail[2])))
        if len(pend) < 3:
            continue
        (h0, d0), (h1, d1), (h2, d2) = pend
        pend.pop(0)
        # route 1, narrowed: a one-row `dropped` spike whose neighbours agree.
        # This is what catches d0wd line 95,349 (9743 / 15 / 9743), the row
        # OVERNIGHT_2026-08-22.md 4.2 says only the median filter sees.
        if abs(d1 - d0) > 100 and abs(d1 - d2) > 100 and abs(d2 - d0) <= 100:
            spike += 1
            continue
        delivered += 1
        if prev is not None:
            drops += wrap16(d1 - prev)
        prev = d1
        try:
            t = int(h1[0])
            ln = int(h1[8])
        except ValueError:
            continue
        if t_lo is None:
            t_lo = t
        t_hi = t
        s = t // 1000000
        sec_v1[s] = sec_v1.get(s, 0) + V1_OVERHEAD + ln
        sec_v2[s] = sec_v2.get(s, 0) + V2_OVERHEAD + ln
        sec_n[s] = sec_n.get(s, 0) + 1
    if not sec_v1:
        return
    span = (t_hi - t_lo) / 1e6
    ks = sorted(sec_v1)
    lo, hi = ks[0] + 1, ks[-1] - 1          # drop both partial end seconds

    def rollmax(dd, w):
        best = 0.0
        run = 0
        q = []
        for s in range(lo, hi + 1):
            v = dd.get(s, 0)
            q.append(v)
            run += v
            if len(q) > w:
                run -= q.pop(0)
            if len(q) == w:
                best = max(best, run / w)
        return best

    off = delivered + drops
    loss = 100.0 * drops / off if off else 0.0
    fps = delivered / span if span > 0 else float("nan")
    mv1 = sum(sec_v1[k] for k in ks[1:-1]) / max(1, len(ks) - 2)
    mv2 = sum(sec_v2[k] for k in ks[1:-1]) / max(1, len(ks) - 2)
    print(f"{os.path.basename(path):<34}{delivered:>11,}{drops:>10,}"
          f"{loss:>9.3f}{fps:>9.2f}{100*mv1/UART_BPS:>8.1f}%"
          f"{100*mv2/UART_BPS:>8.1f}%"
          f"{100*rollmax(sec_v1,10)/UART_BPS:>9.1f}%"
          f"{100*rollmax(sec_v2,10)/UART_BPS:>9.1f}%"
          f"{100*rollmax(sec_v1,60)/UART_BPS:>9.1f}%"
          f"{100*rollmax(sec_v2,60)/UART_BPS:>9.1f}%"
          f"{rollmax(sec_n,60):>10.2f}{spike:>7}")


if __name__ == "__main__":
    subs = sys.argv[1:] or ["a3", "a4", "a67", "a6b", "rng"]
    i = 0
    while i < len(subs):
        s = subs[i]
        if s == "a3p":
            a3p(float(subs[i + 1]), float(subs[i + 2]))
            i += 3
            continue
        {"a3": a3, "a4": a4, "a67": a67, "a6b": a6b, "rng": rng}[s]()
        i += 1
