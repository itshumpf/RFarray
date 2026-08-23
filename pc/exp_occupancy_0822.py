#!/usr/bin/env python3
"""Every real-data figure in docs/OCCUPANCY_TEST_0822.md.

The deliberate occupancy test of 2026-08-22 14:44:24, 32.5 minutes, both
receivers, three beacons.

READ-ONLY on data/raw/. Both CSVs are opened "r" through Python's csv
module and never written, renamed or deleted. No serial port is opened.

`csi_data` is a quoted comma-separated list nested INSIDE the CSV, so a
128-value row splits into 140 fields on a naive comma split. This file
uses csv.reader and reports row counts by len(row) -- the defect at
pc/exp_overnight_0822.py:303 and pc/exp_s3_sfo_steps.py:153,590
(docs/POSITIVE_CONTROL_0822.md 1.2) is not reproduced here.

Phase work is pc/rff/dsp.py's FrameEstimator with the shipped gates
inlier_ratio >= 0.6, resid_std <= 0.8 and WindowAggregator(window=64).
pc/capture.py:compute_cfo, pc/phase_skew.py and pc/fingerprint.py are NOT
used (docs/CODE_INVENTORY.md 4.2 C1/C2/C3).

From the repo root:

    D=data/raw/d0wd_20260822_144424.csv
    S=data/raw/s3_20260822_144424.csv
    python3 pc/exp_occupancy_0822.py run $D --tag d0wd
    python3 pc/exp_occupancy_0822.py run $S --tag s3
    python3 pc/exp_occupancy_0822.py report --tags d0wd,s3
"""
import argparse
import csv
import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from rff import dsp                                        # noqa: E402

CACHE = "/tmp/occ0822_cache"

B1 = "a4:f0:0f:77:91:20"
B2 = "28:05:a5:2f:fa:48"
B3 = "f4:2d:c9:70:72:30"
BEACONS = [B1, B2, B3]
BNAME = {B1: "B1", B2: "B2", B3: "B3"}

# docs/LOT_HYPOTHESIS.md 5, reference-corrected; the yardstick every SFO
# move in docs/POSITIVE_CONTROL_0822.md 2.5 is quoted against.
BETWEEN_UNIT_SD = 0.00237          # pc/exp_thermal_evidence.py:129

BIN_S = 10.0                       # docs/POSITIVE_CONTROL_0822.md 2.1
MAD_K = 6.0                        # ditto
COH_FLAG = 0.5                     # docs/UNWRAP_DEFECT.md 7

# Pre-registered before the files were opened; see 1 of the document.
BASE_LO, BASE_HI = 120.0, 720.0    # baseline A, early occupied stretch
T_REPORTED = 1040.0                # operator's one firm timestamp, +-60 s

K = dsp.K_USABLE.astype(np.float64)
IDX = dsp._USABLE_IDX

CSI_LENS = {128, 256, 384}


# ---------------------------------------------------------------- helpers

def coherence(raw_phase, slope, intercept):
    """docs/UNWRAP_DEFECT.md 7's branch-invariant coherence.

        C = | sum_k exp( j ( phi_k - (m k + b) ) ) | / 52

    over all 52 usable bins with the RAW principal angles. exp(j 2 pi) == 1,
    so C cannot see which 2 pi branch np.unwrap put a bin on, nor the
    integer-turn shift unwrap_continuity applies to the intercept
    (dsp.py:65-67). It can only be measuring the slope.
    """
    return float(np.abs(np.sum(np.exp(1j * (raw_phase
                                            - (slope * K + intercept)))))
                 / K.size)


def median_filter(x, width=9):
    """docs/DUAL_RX_2026-08-21.md Appendix A, reused by
    docs/OVERNIGHT_2026-08-22.md 1 as corrupt-row screen route 1."""
    n = x.size
    h = width // 2
    out = np.empty(n, dtype=np.float64)
    pad = np.pad(x.astype(np.float64), h, mode="edge")
    for i in range(n):
        out[i] = np.median(pad[i:i + width])
    return out


def mad(a):
    a = np.asarray(a, dtype=np.float64)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return np.nan
    return float(np.median(np.abs(a - np.median(a))))


def boot_median_ci(x, n=4000, seed=0):
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size < 3:
        return (np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(n, x.size))
    m = np.median(x[idx], axis=1)
    return (float(np.median(x)), float(np.percentile(m, 2.5)),
            float(np.percentile(m, 97.5)))


def boot_diff_ci(a, b, n=4000, seed=0):
    """median(b) - median(a), CI by independent bootstrap over each set."""
    a = np.asarray(a, float)[np.isfinite(a)]
    b = np.asarray(b, float)[np.isfinite(b)]
    if a.size < 3 or b.size < 3:
        return (np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    ma = np.median(a[rng.integers(0, a.size, size=(n, a.size))], axis=1)
    mb = np.median(b[rng.integers(0, b.size, size=(n, b.size))], axis=1)
    d = mb - ma
    return (float(np.median(b) - np.median(a)),
            float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5)))


# -------------------------------------------------------------------- run

def cmd_run(args):
    os.makedirs(CACHE, exist_ok=True)
    path, tag = args.csv, args.tag

    st = os.stat(path)
    print(f"[{tag}] {path}  {st.st_size} bytes  mtime {st.st_mtime_ns}")

    # ---- pass 1: read every row with a real CSV reader ------------------
    lenhist = {}
    raw = []            # (pc_us, mac, rssi, nf, chan, node, env, csilen,
                        #  esp_ts, dropped, vals)
    macseen = {}
    n_rows = 0
    n_badfields = 0
    with open(path, newline="") as f:
        rd = csv.reader(f)
        hdr = next(rd)
        for row in rd:
            n_rows += 1
            lenhist[len(row)] = lenhist.get(len(row), 0) + 1
            if len(row) != 13:
                n_badfields += 1
                continue
            try:
                pc_us = int(row[0])
                mac = row[3].lower()
                rssi = int(row[4])
                nf = int(row[5])
                chan = int(row[6])
                ets = int(row[7])
                clen = int(row[8])
                node = int(row[10])
                env = int(row[11])
                drop = int(row[12])
            except ValueError:
                n_badfields += 1
                continue
            macseen[mac] = macseen.get(mac, 0) + 1
            raw.append((pc_us, mac, rssi, nf, chan, node, env, clen, ets,
                        drop, row[9]))

    print(f"[{tag}] header {hdr}")
    print(f"[{tag}] data rows {n_rows}; row-length histogram "
          f"{sorted(lenhist.items())}; unparseable-field rows {n_badfields}")

    # What a NAIVE comma split would have done -- docs/V2_SPEC.md 2.10.
    naive = {}
    with open(path) as f:
        f.readline()
        for line in f:
            k = line.rstrip("\n").count(",") + 1
            naive[k] = naive.get(k, 0) + 1
    print(f"[{tag}] a naive line.split(',') gives field counts "
          f"{sorted(naive.items())} -- i.e. {n_rows - naive.get(13, 0)} of "
          f"{n_rows} rows would be mis-parsed. csv.reader gives 13 on all.")

    raw.sort(key=lambda r: r[0])
    pc = np.array([r[0] for r in raw], dtype=np.int64)
    rssi = np.array([r[2] for r in raw], dtype=np.float64)
    nf = np.array([r[3] for r in raw], dtype=np.float64)
    chan = np.array([r[4] for r in raw], dtype=np.int64)
    node = np.array([r[5] for r in raw], dtype=np.int64)
    env = np.array([r[6] for r in raw], dtype=np.int64)
    clen = np.array([r[7] for r in raw], dtype=np.int64)
    ets = np.array([r[8] for r in raw], dtype=np.int64)
    drop = np.array([r[9] for r in raw], dtype=np.int64)

    # ---- corrupt-row screen, two independent routes ---------------------
    # route 1: width-9 median filter on `dropped`, tolerance 100
    med = median_filter(drop, 9)
    bad1 = np.abs(drop - med) > 100
    # route 2: field plausibility on six columns unrelated to `dropped`
    node_mode = int(np.bincount(node[node >= 0]).argmax())
    chan_mode = int(np.bincount(chan[chan >= 0]).argmax())
    bad2 = ((node != node_mode) | (env != 0) | (chan != chan_mode)
            | ~np.isin(clen, list(CSI_LENS))
            | (nf < -110) | (nf > -70) | (rssi < -100) | (rssi > -10))
    bad = bad1 | bad2
    print(f"[{tag}] node_id mode {node_mode}, channel mode {chan_mode}")
    print(f"[{tag}] corrupt rows: route1(median filter) {int(bad1.sum())}, "
          f"route2(field plausibility) {int(bad2.sum())}, "
          f"both {int((bad1 & bad2).sum())}, union {int(bad.sum())}")

    t0 = int(pc[0])
    t = (pc - t0) * 1e-6

    # ---- queue drops, wrap-safe (u16), corrupt rows removed -------------
    d_ok = drop[~bad]
    t_ok = t[~bad]
    dd = np.diff(d_ok.astype(np.int64))
    dd = np.where(dd < 0, dd + 65536, dd)
    nwrap = int((np.diff(d_ok.astype(np.int64)) < 0).sum())
    print(f"[{tag}] queue drops wrap-safe {int(dd.sum())}, u16 wraps {nwrap}")

    # esp_timestamp_us: u32 us, wraps every 4294.967 s -- V2_SPEC 2.3
    de = np.diff(ets[~bad].astype(np.int64))
    neg = de < 0
    wrapm = de < -2147483648
    u32w = int(wrapm.sum())
    # A wrap's true increment is de + 2**32. A genuine backward step
    # (corrupt row) contributes nothing. Adding 2**32 per wrap WITHOUT
    # also keeping the negative de double-counts by 4294.967 s per wrap.
    unw = de.copy()
    unw[wrapm] += 4294967296
    unw[neg & ~wrapm] = 0
    print(f"[{tag}] esp_timestamp_us: {int(neg.sum())} negative steps, "
          f"{u32w} u32 wraps, {int(neg.sum()) - u32w} true backward steps; "
          f"esp span {unw.sum()*1e-6:.3f} s "
          f"vs pc span {t[-1]-t[0]:.3f} s")

    # ---- pass 2: phase, per beacon --------------------------------------
    est = {b: dsp.FrameEstimator(rng_seed=0) for b in BEACONS}
    agg = {b: dsp.WindowAggregator(window=64) for b in BEACONS}
    per = {b: dict(t=[], rssi=[], slope=[], inl=[], res=[], coh=[],
                   fitted=[]) for b in BEACONS}
    win = {b: dict(t=[], sfo=[], q=[]) for b in BEACONS}
    fed = {b: 0 for b in BEACONS}

    for i, r in enumerate(raw):
        if bad[i]:
            continue
        mac = r[1]
        if mac not in est:
            continue
        vals = np.fromstring(r[10], dtype=np.float64, sep=",")
        if vals.size < 128:                 # NOT `< 129`; see module docstring
            continue
        fed[mac] += 1
        e = est[mac].feed(vals, r[8])
        p = per[mac]
        p["t"].append(t[i])
        p["rssi"].append(rssi[i])
        if e is None:
            p["slope"].append(np.nan)
            p["inl"].append(np.nan)
            p["res"].append(np.nan)
            p["coh"].append(np.nan)
            p["fitted"].append(False)
            continue
        cs = dsp.csi_to_complex(vals)
        ph = np.angle(cs[IDX])
        p["slope"].append(e["slope"])
        p["inl"].append(e["inlier_ratio"])
        p["res"].append(e["resid_std"])
        p["coh"].append(coherence(ph, e["slope"], e["intercept"]))
        p["fitted"].append(True)
        w = agg[mac].feed(e, r[0], rssi[i])
        if w is not None:
            win[mac]["t"].append((w["ts_us"] - t0) * 1e-6)
            win[mac]["sfo"].append(w["sfo"])
            win[mac]["q"].append(w["quality"])

    out = dict(t0=t0, t=t, rssi=rssi, nf=nf, clen=clen, ets=ets,
               drop=drop, bad=bad, t_ok=t_ok, dd=dd, tdd=t_ok[1:],
               node_mode=node_mode, chan_mode=chan_mode, n_rows=n_rows,
               lenhist=np.array(sorted(lenhist.items())),
               macs=np.array(sorted(macseen.items(), key=lambda kv: -kv[1]),
                             dtype=object))
    for b in BEACONS:
        n = BNAME[b]
        for k2, v in per[b].items():
            out[f"{n}_{k2}"] = np.array(v)
        for k2, v in win[b].items():
            out[f"{n}_w{k2}"] = np.array(v)
        out[f"{n}_fed"] = fed[b]

    np.savez_compressed(os.path.join(CACHE, f"{tag}.npz"), **out,
                        allow_pickle=True)
    for b in BEACONS:
        n = BNAME[b]
        f = np.array(per[b]["fitted"])
        inl = np.array(per[b]["inl"])
        res = np.array(per[b]["res"])
        acc = f & (inl >= 0.6) & (res <= 0.8)
        print(f"[{tag}] {n}: fed {fed[b]}  fitted {int(f.sum())}  "
              f"accepted {int(acc.sum())}  reject {100*(1-acc.mean()):.3f}%  "
              f"windows {len(win[b]['sfo'])}")
    st2 = os.stat(path)
    print(f"[{tag}] after: {st2.st_size} bytes  mtime {st2.st_mtime_ns}  "
          f"unchanged={st2.st_size == st.st_size and st2.st_mtime_ns == st.st_mtime_ns}")


# ----------------------------------------------------------------- report

def load(tag):
    return np.load(os.path.join(CACHE, f"{tag}.npz"), allow_pickle=True)


def binseries(t, v, bin_s=BIN_S, tmax=None, how="mean"):
    """Bin (t, v) into fixed bins. Returns (bin_left_edges, value)."""
    t = np.asarray(t, float)
    v = np.asarray(v, float)
    ok = np.isfinite(t) & np.isfinite(v)
    t, v = t[ok], v[ok]
    if tmax is None:
        tmax = t.max() if t.size else 0.0
    nb = int(np.ceil(tmax / bin_s))
    idx = np.floor(t / bin_s).astype(int)
    idx = np.clip(idx, 0, nb - 1)
    out = np.full(nb, np.nan)
    for i in range(nb):
        s = v[idx == i]
        if s.size:
            out[i] = np.mean(s) if how == "mean" else np.median(s)
    return np.arange(nb) * bin_s, out


def flags(edges, series, lo, hi, k=MAD_K):
    """6 x MAD departure from the baseline window [lo, hi)."""
    m = (edges >= lo) & (edges < hi) & np.isfinite(series)
    if m.sum() < 5:
        return None
    base = float(np.median(series[m]))
    d = mad(series[m])
    if not np.isfinite(d) or d == 0:
        d = float(np.std(series[m])) or np.nan
    if not np.isfinite(d) or d == 0:
        return None
    fl = np.isfinite(series) & (np.abs(series - base) > k * d)
    return base, d, fl


def step_stat(edges, series, tau, w=120.0, scale=None):
    """Matched-filter step: median(after w) - median(before w).

    Returned in raw units and in units of `scale`, which is the series'
    baseline-A MAD -- the SAME scale the pre-registered 6 x MAD test uses.
    Normalising by a LOCAL MAD instead is unusable here: two of the 24
    series (s3 B3 accfrac, s3 B2 accfrac) have a local MAD of ~1e-5 in
    places, which turns a 0.0014 step into "206 MAD".
    """
    a = series[(edges >= tau - w) & (edges < tau) & np.isfinite(series)]
    b = series[(edges >= tau) & (edges < tau + w) & np.isfinite(series)]
    if a.size < 5 or b.size < 5:
        return np.nan, np.nan
    delta = float(np.median(b) - np.median(a))
    if scale is None or not np.isfinite(scale) or scale <= 0:
        return delta, np.nan
    return delta, delta / scale


def cmd_report(args):
    tags = args.tags.split(",")
    D = {tg: load(tg) for tg in tags}

    print("=" * 78)
    print("R0  FILES, ROWS, SCREEN")
    print("=" * 78)
    for tg in tags:
        d = D[tg]
        print(f"{tg}: rows {int(d['n_rows'])}  span "
              f"{d['t'].max():.3f} s  node_id mode {int(d['node_mode'])}  "
              f"channel mode {int(d['chan_mode'])}")
        print(f"    row-length histogram (len(row)): "
              f"{[tuple(map(int, r)) for r in d['lenhist']]}")
        print(f"    corrupt rows (union of two routes): {int(d['bad'].sum())}")
        print(f"    csi_len histogram: "
              f"{sorted((int(k), int(v)) for k, v in zip(*np.unique(d['clen'], return_counts=True)))}")
        print(f"    distinct MACs {len(d['macs'])}; top 6 "
              f"{[(m, int(c)) for m, c in d['macs'][:6]]}")
        print(f"    queue drops wrap-safe {int(d['dd'].sum())}  "
              f"({d['dd'].sum()/d['t'].max():.3f}/s)")
        nfv, nfc = np.unique(d["nf"][~d["bad"]], return_counts=True)
        print(f"    noise_floor values: "
              f"{[(int(a), int(b)) for a, b in zip(nfv, nfc)]}")
    d0, d1 = D[tags[0]], D[tags[1]]
    print(f"t0 offset between files: "
          f"{(int(d1['t0']) - int(d0['t0']))*1e-6:+.6f} s")

    tmax = min(D[tg]["t"].max() for tg in tags)

    # ---- build the 24 monitored series ---------------------------------
    print()
    print("=" * 78)
    print("R1  THE 24 MONITORED SERIES (2 nodes x 3 beacons x 4 quantities)")
    print(f"    bin {BIN_S:.0f} s, threshold {MAD_K:.0f} x MAD, "
          f"baseline A = [{BASE_LO:.0f}, {BASE_HI:.0f}) s")
    print("=" * 78)
    S = {}
    for tg in tags:
        d = D[tg]
        for b in BEACONS:
            n = BNAME[b]
            t = d[f"{n}_t"]
            fitted = d[f"{n}_fitted"]
            inl = d[f"{n}_inl"]
            res = d[f"{n}_res"]
            acc = fitted & (inl >= 0.6) & (res <= 0.8)
            e, v = binseries(t, d[f"{n}_rssi"], tmax=tmax)
            S[(tg, n, "rssi")] = v
            _, v = binseries(t[acc], res[acc], tmax=tmax)
            S[(tg, n, "resid_std")] = v
            _, v = binseries(t[acc], d[f"{n}_slope"][acc], tmax=tmax,
                             how="median")
            S[(tg, n, "SFO")] = v
            _, v = binseries(t, acc.astype(float), tmax=tmax)
            S[(tg, n, "accfrac")] = v
            EDGES = e
    print(f"{'series':28s} {'baseline':>10s} {'MAD':>9s} "
          f"{'flagged bins':>12s} {'first':>8s} {'flag rate':>9s}")
    rows = []
    SCALE = {}
    for tg in tags:
        for n in ("B1", "B2", "B3"):
            for q in ("rssi", "resid_std", "SFO", "accfrac"):
                r = flags(EDGES, S[(tg, n, q)], BASE_LO, BASE_HI)
                if r is None:
                    print(f"{tg+' '+n+' '+q:28s}  -- baseline unusable")
                    continue
                base, dv, fl = r
                nfin = int(np.isfinite(S[(tg, n, q)]).sum())
                first = EDGES[fl][0] if fl.any() else np.nan
                print(f"{tg+' '+n+' '+q:28s} {base:+10.4f} {dv:9.5f} "
                      f"{int(fl.sum()):6d}/{nfin:<5d} {first:8.0f} "
                      f"{100*fl.sum()/max(nfin,1):8.1f}%")
                rows.append((tg, n, q, base, dv, fl))
                SCALE[(tg, n, q)] = dv

    # ---- every excursion, with its timestamp ----------------------------
    print()
    print("=" * 78)
    print("R2  EVERY EXCURSION: contiguous runs of >=2 flagged bins")
    print("=" * 78)
    allexc = []
    for tg, n, q, base, dv, fl in rows:
        i = 0
        while i < fl.size:
            if fl[i]:
                j = i
                while j + 1 < fl.size and fl[j + 1]:
                    j += 1
                if j - i + 1 >= 2:
                    allexc.append((EDGES[i], EDGES[j] + BIN_S,
                                   f"{tg} {n} {q}", j - i + 1))
                i = j + 1
            else:
                i += 1
    allexc.sort()
    for a, b, name, nb in allexc:
        print(f"  t = {a:7.0f} .. {b:7.0f} s  ({nb:3d} bins)  {name}")
    print(f"  total: {len(allexc)} excursions of >=2 bins across 24 series")

    # how many distinct series are in excursion in each bin
    print()
    print("  concurrency: bins where >=6 of 24 series are simultaneously "
          "flagged")
    conc = np.zeros(EDGES.size)
    for tg, n, q, base, dv, fl in rows:
        conc += fl.astype(float)
    hot = np.where(conc >= 6)[0]
    if hot.size:
        i = 0
        while i < hot.size:
            j = i
            while j + 1 < hot.size and hot[j + 1] == hot[j] + 1:
                j += 1
            seg = hot[i:j + 1]
            print(f"    t = {EDGES[seg[0]]:7.0f} .. "
                  f"{EDGES[seg[-1]] + BIN_S:7.0f} s   peak "
                  f"{int(conc[seg].max())}/24 series")
            i = j + 1
    else:
        print("    none")
    print(f"  max concurrency anywhere: {int(conc.max())}/24 at "
          f"t = {EDGES[int(np.argmax(conc))]:.0f} s")
    print("  (docs/POSITIVE_CONTROL_0822.md 2.1: 23 of 24 at 08:55, "
          "20 of them inside one 70 s band)")
    print("  concurrency in the +-30 s around each named time:")
    for lab, tt in (("t = 1040 (reported)", T_REPORTED),
                    ("T_DEP", 790.0), ("T_RET", 920.0)):
        w = np.abs(EDGES - tt) <= 30.0
        print(f"    {lab:22s} peak {int(conc[w].max())}/24")

    # ---- motion index, computed here because R3/R5/R6/R8 need its edges --
    MI = {}
    for tg in tags:
        d = D[tg]
        for b in BEACONS:
            n = BNAME[b]
            t = d[f"{n}_t"]
            rs = d[f"{n}_rssi"]
            nb = EDGES.size
            idx = np.clip(np.floor(t / BIN_S).astype(int), 0, nb - 1)
            sd = np.full(nb, np.nan)
            for i in range(nb):
                s = rs[idx == i]
                if s.size >= 20:
                    sd[i] = np.std(s)
            # bin-to-bin |change| in the mean level: how fast the channel
            # is moving. 10 s resolution, no smoothing window to smear the
            # edges. This is the quantity that separates the two states;
            # the within-bin sd does not (it is dominated by fast fading
            # that is there whether or not anything in the room moves).
            lev = S[(tg, n, "rssi")]
            rm = np.full(nb, np.nan)
            rm[:-1] = np.abs(np.diff(lev))
            MI[(tg, n)] = (sd, rm)
    comb_sd = np.nanmean(np.array([MI[k][0] / np.nanmedian(MI[k][0])
                                   for k in MI]), axis=0)
    comb_rm = np.nanmean(np.array([MI[k][1] / np.nanmedian(MI[k][1])
                                   for k in MI]), axis=0)
    bm = (EDGES >= BASE_LO) & (EDGES < BASE_HI)
    base_sd = np.nanmedian(comb_sd[bm])
    mad_sd = mad(comb_sd[bm])
    base_rm = np.nanmedian(comb_rm[bm])
    mad_rm = mad(comb_rm[bm])
    sm = median_filter(np.nan_to_num(comb_rm, nan=base_rm), 5)
    thr = 0.5 * float(np.nanmedian(sm[bm]))
    quiet = sm < thr
    runs = []
    i = 0
    while i < quiet.size:
        if quiet[i]:
            j = i
            while j + 1 < quiet.size and quiet[j + 1]:
                j += 1
            runs.append((EDGES[i], EDGES[j] + BIN_S, j - i + 1))
            i = j + 1
        else:
            i += 1
    lo_run = max(runs, key=lambda r: r[2]) if runs else (np.nan, np.nan, 0)
    T_DEP, T_RET = float(lo_run[0]), float(lo_run[1])

    # ---- node-level series ----------------------------------------------
    print()
    print("=" * 78)
    print("R3  NODE-LEVEL SERIES: noise_floor, delivered rate, drop rate")
    print("=" * 78)
    NODE = {}
    for tg in tags:
        d = D[tg]
        ok = ~d["bad"]
        e, v = binseries(d["t"][ok], d["nf"][ok], tmax=tmax)
        r = flags(e, v, BASE_LO, BASE_HI)
        nfv = d["nf"][ok]
        modal = int(np.bincount((-nfv).astype(int)).argmax()) * -1
        fr = np.histogram(d["t"][ok], bins=np.arange(0, tmax + BIN_S,
                                                     BIN_S))[0] / BIN_S
        dr = np.histogram(d["tdd"], bins=np.arange(0, tmax + BIN_S, BIN_S),
                          weights=d["dd"])[0] / BIN_S
        print(f"{tg}: noise_floor modal {modal}, "
              f"mean {np.nanmean(v):+.4f}, transitions "
              f"{int((np.diff(nfv) != 0).sum())} of {nfv.size} rows")
        if r is not None:
            base, dv, fl = r
            print(f"    nf baseline {base:+.4f} MAD {dv:.5f} -> "
                  f"{int(fl.sum())} flagged bins"
                  + (f", first t = {e[fl][0]:.0f} s" if fl.any() else ""))
        print(f"    delivered {fr.mean():.2f} fps (min {fr.min():.1f}, "
              f"max {fr.max():.1f}); drops {dr.mean():.3f}/s")
        NODE[tg] = {}
        for nm, ser in (("noise_floor", v), ("delivered fps", fr),
                        ("drop rate", dr)):
            rr = flags(e, ser, BASE_LO, BASE_HI)
            sc = rr[1] if rr else np.nan
            NODE[tg][nm] = (ser, sc)
            for tt in (T_REPORTED, T_DEP, T_RET):
                dl, z = step_stat(e, ser, tt, scale=sc)
                print(f"    step at t={tt:4.0f}: {nm:14s} d={dl:+9.4f} "
                      f"({z:+7.2f} x baseline MAD {sc:.5f})")

    # ---- the arrival test ------------------------------------------------
    print()
    print("=" * 78)
    print("R4  THE REPORTED ARRIVAL, t = 1040 s +- 60 s")
    print("    effect sizes in docs/POSITIVE_CONTROL_0822.md 2.4/2.5 units")
    print("=" * 78)
    W = 300.0
    print(f"    boundary t = {T_REPORTED:.0f} s; before = "
          f"[{T_REPORTED-W:.0f}, {T_REPORTED:.0f}), after = "
          f"[{T_REPORTED:.0f}, {T_REPORTED+W:.0f})")
    print(f"{'node':5s} {'b':3s} {'rssi be':>8s} {'rssi af':>8s} {'d dB':>7s} "
          f"{'SFO be':>9s} {'SFO af':>9s} {'d SFO':>10s} {'xSD':>6s} "
          f"{'CI excl 0':>10s} {'rej%':>13s} {'resid':>15s}")
    for tg in tags:
        d = D[tg]
        for b in BEACONS:
            n = BNAME[b]
            t = d[f"{n}_t"]
            fitted = d[f"{n}_fitted"]
            acc = fitted & (d[f"{n}_inl"] >= 0.6) & (d[f"{n}_res"] <= 0.8)
            pre = (t >= T_REPORTED - W) & (t < T_REPORTED)
            post = (t >= T_REPORTED) & (t < T_REPORTED + W)
            r_be = np.mean(d[f"{n}_rssi"][pre])
            r_af = np.mean(d[f"{n}_rssi"][post])
            wt = d[f"{n}_wt"]
            wsfo = d[f"{n}_wsfo"]
            wpre = wsfo[(wt >= T_REPORTED - W) & (wt < T_REPORTED)]
            wpost = wsfo[(wt >= T_REPORTED) & (wt < T_REPORTED + W)]
            dd_, lo, hi = boot_diff_ci(wpre, wpost)
            excl = "yes" if np.isfinite(lo) and (lo > 0) == (hi > 0) else "no"
            rej_be = 100 * (1 - acc[pre].mean()) if pre.sum() else np.nan
            rej_af = 100 * (1 - acc[post].mean()) if post.sum() else np.nan
            res_be = np.nanmean(d[f"{n}_res"][pre & acc])
            res_af = np.nanmean(d[f"{n}_res"][post & acc])
            print(f"{tg:5s} {n:3s} {r_be:8.2f} {r_af:8.2f} {r_af-r_be:+7.2f} "
                  f"{np.median(wpre):+9.5f} {np.median(wpost):+9.5f} "
                  f"{dd_:+10.5f} {abs(dd_)/BETWEEN_UNIT_SD:6.2f} "
                  f"{excl:>10s} {rej_be:5.2f}->{rej_af:5.2f} "
                  f"  {res_be:.4f}->{res_af:.4f}")

    # ---- R4b: the same test with windows that do NOT straddle the gap ---
    print()
    print("=" * 78)
    print("R4b THE ARRIVAL TEST AGAIN, WITH CLEAN WINDOWS")
    print(f"    R4's 'before' window [{T_REPORTED-W:.0f}, {T_REPORTED:.0f}) "
          f"contains the quiet interval [{T_DEP:.0f}, {T_RET:.0f}], so R4 "
          "measures")
    print("    the absence, not the sit-down. Two clean comparisons:")
    print("=" * 78)
    for lab, (a0, a1), (b0, b1) in (
            ("sit-down only:  [920,1040) -> [1040,1160)",
             (T_RET, T_REPORTED), (T_REPORTED, T_REPORTED + 120)),
            ("occupied vs occupied: [400,700) -> [1200,1900)",
             (400.0, 700.0), (1200.0, 1900.0))):
        print(f"  {lab}")
        print(f"  {'node':5s} {'b':3s} {'d rssi dB':>10s} {'d SFO':>10s} "
              f"{'xSD':>6s} {'CI excl 0':>10s} {'rej%':>14s}")
        for tg in tags:
            d = D[tg]
            for b in BEACONS:
                n = BNAME[b]
                t = d[f"{n}_t"]
                acc = (d[f"{n}_fitted"] & (d[f"{n}_inl"] >= 0.6)
                       & (d[f"{n}_res"] <= 0.8))
                pa = (t >= a0) & (t < a1)
                pb = (t >= b0) & (t < b1)
                wt, ws = d[f"{n}_wt"], d[f"{n}_wsfo"]
                wa = ws[(wt >= a0) & (wt < a1)]
                wb = ws[(wt >= b0) & (wt < b1)]
                dl, lo, hi = boot_diff_ci(wa, wb)
                ex = ("yes" if np.isfinite(lo) and (lo > 0) == (hi > 0)
                      else "no")
                dr = (np.mean(d[f"{n}_rssi"][pb])
                      - np.mean(d[f"{n}_rssi"][pa]))
                print(f"  {tg:5s} {n:3s} {dr:+10.2f} {dl:+10.5f} "
                      f"{abs(dl)/BETWEEN_UNIT_SD:6.2f} {ex:>10s} "
                      f"{100*(1-acc[pa].mean()):6.2f}->"
                      f"{100*(1-acc[pb].mean()):6.2f}")

    # ---- R3b: the S3 noise_floor excursion census -----------------------
    print()
    print("=" * 78)
    print("R3b S3 noise_floor EXCURSIONS FROM ITS MODAL VALUE")
    print("    comparable to docs/OVERNIGHT_2026-08-22.md 0: 129 excursions")
    print("    over 6.5 h, median duration 10 s, maximum 220 s")
    print("=" * 78)
    d = D["s3"]
    ok = ~d["bad"]
    e3, v3 = binseries(d["t"][ok], d["nf"][ok], tmax=tmax, how="median")
    modal = float(np.median(v3[np.isfinite(v3)]))
    off = np.isfinite(v3) & (v3 != modal)
    exc, i = [], 0
    while i < off.size:
        if off[i]:
            j = i
            while j + 1 < off.size and off[j + 1]:
                j += 1
            exc.append((e3[i], e3[j] + BIN_S, j - i + 1,
                        float(np.nanmean(v3[i:j + 1]) - modal)))
            i = j + 1
        else:
            i += 1
    durs = np.array([x[1] - x[0] for x in exc])
    print(f"  modal 10 s value {modal:+.1f} dB; {len(exc)} excursions in "
          f"{tmax:.0f} s; median duration {np.median(durs):.0f} s, "
          f"maximum {durs.max():.0f} s")
    print(f"  bins at the modal value: "
          f"{100*np.mean(v3[np.isfinite(v3)] == modal):.2f}% "
          f"(overnight: 86.89 % of 2,327 bins)")
    for a, bb, nb_, dv in sorted(exc, key=lambda x: -(x[1] - x[0]))[:6]:
        print(f"    t = {a:6.0f} .. {bb:6.0f} s   {bb-a:5.0f} s   "
              f"mean offset {dv:+.3f} dB")

    # ---- locate BOTH transitions from the data --------------------------
    print()
    print("=" * 78)
    print("R5  TRANSITION LOCALISATION: coherent step statistic over the")
    print("    24 series, w = 120 s half-window, scanned over the whole run")
    print("=" * 78)
    taus = np.arange(180.0, tmax - 180.0, BIN_S)
    NSER = np.zeros(taus.size)          # how many of 24 exceed 6 x MAD
    ZBAR = np.zeros(taus.size)          # mean |step| in baseline MAD
    for tg, n, q, base, dv, fl in rows:
        s = S[(tg, n, q)]
        z = np.array([step_stat(EDGES, s, tt, scale=SCALE[(tg, n, q)])[1]
                      for tt in taus])
        z = np.nan_to_num(z)
        NSER += (np.abs(z) > MAD_K).astype(float)
        ZBAR += np.abs(z)
    ZBAR /= len(rows)
    print("  top 10 candidate transition times, ranked by how many of the")
    print("  24 series show a step larger than 6 x their baseline-A MAD:")
    order = np.lexsort((-ZBAR, -NSER))
    for i in order[:10]:
        print(f"    t = {taus[i]:7.0f} s   {int(NSER[i]):2d}/24 series "
              f"> 6 x MAD   mean |step| = {ZBAR[i]:6.2f} x MAD")
    peak = float(taus[order[0]])
    sup = taus[(NSER >= NSER[order[0]] - 1) & (np.abs(taus - peak) <= 120)]
    print(f"  strongest transition T_A = {peak:.0f} s; the band within one "
          f"series of the peak is [{sup.min():.0f}, {sup.max():.0f}] s")
    mask2 = np.abs(taus - peak) > 200.0
    i2 = int(np.lexsort((-ZBAR, -NSER))[
        np.argmax([mask2[j] for j in np.lexsort((-ZBAR, -NSER))])])
    peak2 = float(taus[i2])
    print(f"  second transition (>200 s from T_A): T_B = {peak2:.0f} s, "
          f"{int(NSER[i2])}/24 series > 6 x MAD, mean |step| "
          f"{ZBAR[i2]:.2f} x MAD")

    print("\n  full profile, every bin with >=1 series over 6 x MAD:")
    for i, tt in enumerate(taus):
        if NSER[i] >= 1:
            print(f"    t = {tt:7.0f} s   {int(NSER[i]):2d}/24   "
                  f"mean |step| {ZBAR[i]:6.2f}")

    print("\n  NOTE: the level-step scan above is the PRE-REGISTERED test.")
    print("  The times it ranks are NOT the transitions -- the transitions")
    print("  are found by the motion index of R11, at T_DEP = "
          f"{T_DEP:.0f} s and T_RET = {T_RET:.0f} s. Both are tabulated.")
    for label, tt in (("T_DEP (departure)", T_DEP),
                      ("T_RET (return)", T_RET),
                      ("T_reported", T_REPORTED),
                      ("T_A (level-scan peak)", peak),
                      ("T_B (level-scan 2nd)", peak2)):
        print(f"\n  per-series step at {label} = {tt:.0f} s "
              f"(delta, and delta / baseline-A MAD):")
        for tg in tags:
            for n in ("B1", "B2", "B3"):
                line = f"    {tg:5s} {n:3s}"
                for q in ("rssi", "resid_std", "SFO", "accfrac"):
                    dlt, z = step_stat(EDGES, S[(tg, n, q)], tt,
                                       scale=SCALE[(tg, n, q)])
                    line += f"  {q}={dlt:+8.4f}({z:+7.1f})"
                print(line)

    # ---- sharp edge on the single strongest series ----------------------
    print()
    print("  EDGE LOCALISATION on the strongest single series, at 2 s bins.")
    print("  Uncertainty is the span over which the step statistic stays")
    print("  within 90 % of its maximum.")
    for tg, n, q in (("d0wd", "B3", "rssi"), ("s3", "B3", "rssi"),
                     ("d0wd", "B1", "rssi")):
        d = D[tg]
        e2, v2 = binseries(d[f"{n}_t"], d[f"{n}_rssi"], bin_s=2.0, tmax=tmax)
        tt2 = np.arange(200.0, tmax - 200.0, 2.0)
        zz = np.array([step_stat(e2, v2, t_, w=100.0, scale=1.0)[0]
                       for t_ in tt2])
        zz = np.nan_to_num(zz)
        for nm, sel in (("falling edge", np.argmin(zz)),
                        ("rising edge", np.argmax(zz))):
            val = zz[sel]
            band = tt2[np.abs(zz) >= 0.9 * abs(val)]
            band = band[np.sign(zz[np.abs(zz) >= 0.9 * abs(val)])
                        == np.sign(val)]
            near = band[np.abs(band - tt2[sel]) <= 60]
            print(f"    {tg} {n} rssi {nm:13s} t = {tt2[sel]:7.1f} s  "
                  f"step {val:+7.2f} dB  90%-band "
                  f"[{near.min():.0f}, {near.max():.0f}] s "
                  f"(+-{(near.max()-near.min())/2:.0f} s)")

    # ---- mirror test -----------------------------------------------------
    print()
    print("=" * 78)
    print("R6  ARE THE TWO TRANSITIONS MIRROR IMAGES?")
    print("=" * 78)
    opp = same = 0
    print(f"  T_DEP = {T_DEP:.0f} s, T_RET = {T_RET:.0f} s")
    print(f"{'series':28s} {'@T_DEP':>12s} {'@T_RET':>12s} "
          f"{'-DEP/RET':>9s}  dir")
    for tg in tags:
        for n in ("B1", "B2", "B3"):
            for q in ("rssi", "resid_std", "SFO", "accfrac"):
                sc = SCALE[(tg, n, q)]
                da, _ = step_stat(EDGES, S[(tg, n, q)], T_DEP, scale=sc)
                db, _ = step_stat(EDGES, S[(tg, n, q)], T_RET, scale=sc)
                if not (np.isfinite(da) and np.isfinite(db)):
                    continue
                o = "opposite" if da * db < 0 else "same"
                if da * db < 0:
                    opp += 1
                else:
                    same += 1
                print(f"{tg+' '+n+' '+q:28s} {da:+12.5f} {db:+12.5f} "
                      f"{(-da/db if db else np.nan):8.2f}  {o}")
    print(f"  opposite in {opp} of {opp+same} series; same in {same}")

    # ---- coherence detector ---------------------------------------------
    print()
    print("=" * 78)
    print(f"R7  BRANCH-INVARIANT COHERENCE (docs/UNWRAP_DEFECT.md 7), "
          f"C < {COH_FLAG}")
    print("=" * 78)
    print(f"{'node':5s} {'b':3s} {'frames fitted':>14s} {'C median':>9s} "
          f"{'flagged':>10s} {'rate':>8s}")
    cohbins = {}
    for tg in tags:
        d = D[tg]
        for b in BEACONS:
            n = BNAME[b]
            c = d[f"{n}_coh"]
            f = d[f"{n}_fitted"]
            cc = c[f]
            fl = cc < COH_FLAG
            print(f"{tg:5s} {n:3s} {int(f.sum()):14d} "
                  f"{np.median(cc):9.4f} {int(fl.sum()):10d} "
                  f"{100*fl.mean():7.3f}%")
            e, v = binseries(d[f"{n}_t"][f], fl.astype(float), tmax=tmax)
            cohbins[(tg, n)] = v
    print()
    print(f"  flag rate within +-120 s of T_DEP={T_DEP:.0f}, "
          f"T_RET={T_RET:.0f} or t=1040, vs the rest of the run:")
    for tg in tags:
        for n in ("B1", "B2", "B3"):
            v = cohbins[(tg, n)]
            near = np.zeros(EDGES.size, bool)
            for tt in (T_DEP, T_RET, T_REPORTED):
                if np.isfinite(tt):
                    near |= np.abs(EDGES - tt) <= 120.0
            a = np.nanmean(v[near]) if np.isfinite(v[near]).any() else np.nan
            bq = np.nanmean(v[~near]) if np.isfinite(v[~near]).any() else np.nan
            print(f"    {tg:5s} {n:3s} near {100*a:7.3f}%   "
                  f"elsewhere {100*bq:7.3f}%   ratio "
                  f"{(a/bq if bq else np.nan):6.2f}")

    # ---- fraction of the 08:55 signature reproduced ----------------------
    print()
    print("=" * 78)
    print("R8  FRACTION OF THE 08:55 SIGNATURE REPRODUCED")
    print("=" * 78)
    pc55 = {
        ("d0wd", "B1", "rssi"): +0.28, ("d0wd", "B2", "rssi"): +0.43,
        ("d0wd", "B3", "rssi"): +1.68, ("s3", "B1", "rssi"): -3.58,
        ("s3", "B2", "rssi"): -1.47, ("s3", "B3", "rssi"): -3.69,
        ("d0wd", "B1", "SFO"): -0.00751, ("d0wd", "B2", "SFO"): +0.00383,
        ("d0wd", "B3", "SFO"): -0.05410, ("s3", "B1", "SFO"): +0.00420,
        ("s3", "B2", "SFO"): +0.00945, ("s3", "B3", "SFO"): -0.00162,
    }
    print("  docs/POSITIVE_CONTROL_0822.md 2.4/2.5 against this run:")
    print(f"{'series':22s} {'08:55':>10s} {'@T_DEP':>10s} {'@T_RET':>10s} "
          f"{'@1040':>10s} {'|DEP|/|08:55|':>14s} {'|RET|/|08:55|':>14s}")
    fdep, fret, f1040 = [], [], []
    for (tg, n, q), ref in pc55.items():
        sc = SCALE[(tg, n, q)]
        dd_ = step_stat(EDGES, S[(tg, n, q)], T_DEP, scale=sc)[0]
        dr_ = step_stat(EDGES, S[(tg, n, q)], T_RET, scale=sc)[0]
        d10 = step_stat(EDGES, S[(tg, n, q)], T_REPORTED, scale=sc)[0]
        fdep.append(abs(dd_) / abs(ref))
        fret.append(abs(dr_) / abs(ref))
        f1040.append(abs(d10) / abs(ref))
        print(f"{tg+' '+n+' '+q:22s} {ref:+10.5f} {dd_:+10.5f} "
              f"{dr_:+10.5f} {d10:+10.5f} {abs(dd_)/abs(ref):14.3f} "
              f"{abs(dr_)/abs(ref):14.3f}")
    print(f"  median ratio to 08:55 over the 12 series: "
          f"T_DEP {np.nanmedian(fdep):.3f}, T_RET {np.nanmedian(fret):.3f}, "
          f"t=1040 {np.nanmedian(f1040):.3f}")
    print("  sign agreement with 08:55 (same direction as the arrival):")
    for lab, tt in (("T_DEP", T_DEP), ("T_RET", T_RET),
                    ("t=1040", T_REPORTED)):
        ag = sum(1 for (tg, n, q), ref in pc55.items()
                 if np.isfinite(step_stat(EDGES, S[(tg, n, q)], tt,
                                          scale=SCALE[(tg, n, q)])[0])
                 and step_stat(EDGES, S[(tg, n, q)], tt,
                               scale=SCALE[(tg, n, q)])[0] * ref > 0)
        print(f"    at {lab:7s} t={tt:6.0f} s: {ag}/12 series agree in sign "
              f"with the 08:55 arrival")
    print("  largest SFO move anywhere in this run, in BETWEEN_UNIT_SD:")
    best, bw = 0.0, None
    for tg in tags:
        for n in ("B1", "B2", "B3"):
            for tt in taus:
                dlt = step_stat(EDGES, S[(tg, n, "SFO")], tt,
                                scale=SCALE[(tg, n, "SFO")])[0]
                if np.isfinite(dlt) and abs(dlt) > abs(best):
                    best, bw = dlt, (tg, n, tt)
    print(f"    {best:+.5f} rad/sc = {abs(best)/BETWEEN_UNIT_SD:.2f} x SD "
          f"at {bw[0]} {bw[1]}, t = {bw[2]:.0f} s")
    print("    excluding the 83 %-reject cell s3/B2:")
    best2, bw2 = 0.0, None
    for tg in tags:
        for n in ("B1", "B2", "B3"):
            if (tg, n) == ("s3", "B2"):
                continue
            for tt in taus:
                dlt = step_stat(EDGES, S[(tg, n, "SFO")], tt,
                                scale=SCALE[(tg, n, "SFO")])[0]
                if np.isfinite(dlt) and abs(dlt) > abs(best2):
                    best2, bw2 = dlt, (tg, n, tt)
    print(f"    {best2:+.5f} rad/sc = {abs(best2)/BETWEEN_UNIT_SD:.2f} x SD "
          f"at {bw2[0]} {bw2[1]}, t = {bw2[2]:.0f} s")
    print("    (08:55's largest was -0.05410 = 22.83 x SD)")

    # ---- does the post-arrival state match the pre-departure state? ------
    print()
    print("=" * 78)
    print("R9  IS THE POST-ARRIVAL STATE THE SAME AS THE PRE-DEPARTURE ONE?")
    print("    baseline A [120,720) vs [1100, 1900); occupancy says yes")
    print("=" * 78)
    for tg in tags:
        for n in ("B1", "B2", "B3"):
            line = f"  {tg:5s} {n:3s}"
            for q in ("rssi", "SFO"):
                s = S[(tg, n, q)]
                a = np.nanmedian(s[(EDGES >= BASE_LO) & (EDGES < BASE_HI)])
                b = np.nanmedian(s[(EDGES >= 1100) & (EDGES < 1900)])
                line += f"  {q}: {a:+9.4f} -> {b:+9.4f} (d={b-a:+8.4f})"
            print(line)


    # ---- motion index: RSSI VARIABILITY, not RSSI level ------------------
    print()
    print("=" * 78)
    print("R11 MOTION INDEX -- RSSI VARIABILITY PER 10 s BIN")
    print("    within-bin sd of per-frame RSSI, and the bin-to-bin |dRSSI|")
    print("    of the binned mean. Only the second one separates the states.")
    print("=" * 78)
    print(f"  combined within-bin-sd index: baseline A median {base_sd:.4f}, "
          f"MAD {mad_sd:.4f}")
    print(f"  combined bin-to-bin |dRSSI| index (the motion index): "
          f"baseline A median {base_rm:.4f}, MAD {mad_rm:.4f}")
    print(f"    bins with sd-index below baseline - 6 x MAD: "
          f"{int((comb_sd < base_sd - MAD_K*mad_sd).sum())}")
    print(f"    bins with motion index below baseline - 2 x MAD: "
          f"{int((comb_rm < base_rm - 2.0*mad_rm).sum())} of "
          f"{int(np.isfinite(comb_rm).sum())}   "
          f"(6 x MAD is below zero for this one-sided quantity: "
          f"{base_rm - MAD_K*mad_rm:+.4f}, so a 2 x MAD one-sided gate and "
          f"a half-baseline gate are both reported)")
    # 5-bin (50 s) RUNNING MEDIAN of the motion index before run
    # extraction: the raw index is spiky and a single quiet bin inside an
    # occupied stretch must not open an interval. 50 s is the resolution
    # limit this buys, and the uncertainty below is quoted against it.
    print(f"    running-median (50 s) motion index: baseline A median "
          f"{np.nanmedian(sm[bm]):.4f}; quiet threshold = half that = "
          f"{thr:.4f}")
    for a, bb, nb_ in runs:
        print(f"    quiet run t = {a:6.0f} .. {bb:6.0f} s  ({nb_} bins, "
              f"{bb-a:.0f} s)")
    print()
    print("  the index bin by bin, t = 600 .. 1300 s:")
    print(f"  {'t':>6s} {'sd-idx':>7s} {'motion':>7s} {'run-med':>8s} "
          f"{'quiet?':>6s}   "
          + " ".join(f"{tg[:2]}{n}" for tg in tags for n in
                     ("B1", "B2", "B3")))
    for i, tt in enumerate(EDGES):
        if 600 <= tt <= 1300:
            per = " ".join(f"{MI[(tg, n)][1][i]:5.2f}" for tg in tags
                           for n in ("B1", "B2", "B3"))
            print(f"  {tt:6.0f} {comb_sd[i]:7.3f} {comb_rm[i]:7.3f} "
                  f"{sm[i]:8.3f} {'QUIET' if quiet[i] else '':>6s}   {per}")
    print(f"\n  longest quiet interval: [{T_DEP:.0f}, {T_RET:.0f}] s, "
          f"{T_RET-T_DEP:.0f} s long. Next longest is "
          f"{sorted(r[2] for r in runs)[-2]*BIN_S:.0f} s.")
    print("  per-cell motion index and within-bin sd, inside vs outside:")
    ins = (EDGES >= T_DEP) & (EDGES < T_RET)
    for tg in tags:
        for n in ("B1", "B2", "B3"):
            sd, rmv = MI[(tg, n)]
            print(f"    {tg:5s} {n:3s} |dRSSI| inside "
                  f"{np.nanmedian(rmv[ins]):5.3f} dB  outside "
                  f"{np.nanmedian(rmv[~ins]):5.3f} dB  ratio "
                  f"{np.nanmedian(rmv[~ins])/np.nanmedian(rmv[ins]):5.2f}"
                  f"   |  within-bin sd inside {np.nanmedian(sd[ins]):5.3f}"
                  f"  outside {np.nanmedian(sd[~ins]):5.3f}")
    print("\n  raw (unsmoothed) index at the two edges, to bound them:")
    for lab, tt in (("departure", T_DEP), ("return", T_RET)):
        i0 = int(tt / BIN_S)
        seg = [(EDGES[k], comb_rm[k]) for k in range(max(0, i0 - 3),
                                                     min(EDGES.size, i0 + 4))]
        print(f"    {lab:10s} "
              + "  ".join(f"{a:.0f}:{b:.2f}" for a, b in seg))

    # ---- coherence vs acceptance ----------------------------------------
    print()
    print("=" * 78)
    print("R12 IS C < 0.5 FLAGGING THE BRANCH DEFECT, OR JUST A BAD CELL?")
    print("=" * 78)
    print(f"{'node':5s} {'b':3s} {'C<.5 | accepted':>17s} "
          f"{'C<.5 | rejected':>17s} {'median C acc':>13s} "
          f"{'median C rej':>13s}")
    for tg in tags:
        d = D[tg]
        for b in BEACONS:
            n = BNAME[b]
            f = d[f"{n}_fitted"]
            acc = f & (d[f"{n}_inl"] >= 0.6) & (d[f"{n}_res"] <= 0.8)
            rej = f & ~acc
            c = d[f"{n}_coh"]
            fa = 100 * np.mean(c[acc] < COH_FLAG) if acc.any() else np.nan
            fr_ = 100 * np.mean(c[rej] < COH_FLAG) if rej.any() else np.nan
            print(f"{tg:5s} {n:3s} {fa:16.3f}% {fr_:16.3f}% "
                  f"{np.median(c[acc]) if acc.any() else np.nan:13.4f} "
                  f"{np.median(c[rej]) if rej.any() else np.nan:13.4f}")

    # ---- R13: the marginal cell, and the departure step with a CI -------
    print()
    print("=" * 78)
    print("R13 WHICH CELL IS MARGINAL THIS SESSION, AND THE DEPARTURE STEP")
    print("=" * 78)
    print("  whole-run reject rate per cell, against the two earlier runs:")
    print(f"  {'cell':10s} {'this run':>10s} {'overnight':>10s} "
          f"{'2026-08-21':>11s}")
    prev = {("d0wd", "B1"): (7.422, 3.70), ("d0wd", "B2"): (4.114, 1.34),
            ("d0wd", "B3"): (58.814, 43.54), ("s3", "B1"): (0.664, 0.37),
            ("s3", "B2"): (0.794, 1.03), ("s3", "B3"): (0.314, 12.53)}
    for tg in tags:
        d = D[tg]
        for b in BEACONS:
            n = BNAME[b]
            f = d[f"{n}_fitted"]
            acc = f & (d[f"{n}_inl"] >= 0.6) & (d[f"{n}_res"] <= 0.8)
            o, y = prev[(tg, n)]
            print(f"  {tg+' '+n:10s} {100*(1-acc.mean()):9.3f}% "
                  f"{o:9.3f}% {y:10.2f}%")
    print("  (overnight = docs/OVERNIGHT_2026-08-22.md 3.1 via")
    print("   docs/POSITIVE_CONTROL_0822.md 1.1; 08-21 = "
          "docs/S3_SFO_STEPS.md 1,")
    print("   where 'd0wd' is the same board under the name 'desk')")
    print()
    print("  the departure step in SFO, window-level bootstrap, 4000 "
          "resamples,")
    print(f"  np.random.default_rng(0): [{T_DEP-120:.0f}, {T_DEP:.0f}) "
          f"vs [{T_DEP:.0f}, {T_DEP+120:.0f}) s")
    print(f"  {'node':5s} {'b':3s} {'n win':>6s} {'n win':>6s} "
          f"{'d SFO':>10s} {'95% CI':>24s} {'xSD':>6s}")
    for tg in tags:
        d = D[tg]
        for b in BEACONS:
            n = BNAME[b]
            wt, ws = d[f"{n}_wt"], d[f"{n}_wsfo"]
            a = ws[(wt >= T_DEP - 120) & (wt < T_DEP)]
            bq = ws[(wt >= T_DEP) & (wt < T_DEP + 120)]
            dl, lo, hi = boot_diff_ci(a, bq)
            print(f"  {tg:5s} {n:3s} {a.size:6d} {bq.size:6d} {dl:+10.5f} "
                  f"[{lo:+9.5f}, {hi:+9.5f}] "
                  f"{abs(dl)/BETWEEN_UNIT_SD:6.2f}")
    print()
    print("  s3/B2 accepted fraction per 200 s block (it is not stationary):")
    d = D["s3"]
    f = d["B2_fitted"]
    acc = f & (d["B2_inl"] >= 0.6) & (d["B2_res"] <= 0.8)
    t = d["B2_t"]
    for a0 in np.arange(0, tmax, 200.0):
        m = (t >= a0) & (t < a0 + 200)
        if m.sum():
            print(f"    t = {a0:5.0f} .. {a0+200:5.0f}  n = {int(m.sum()):6d}"
                  f"  accepted {100*acc[m].mean():6.2f}%  median C "
                  f"{np.median(d['B2_coh'][m & f]):.4f}")

    # ---- the raw series through the interesting stretch ------------------
    print()
    print("=" * 78)
    print("R10 THE 10 s SERIES THROUGH t = 600 .. 1400 s, PRINTED IN FULL")
    print("=" * 78)
    nf_s3 = binseries(D["s3"]["t"][~D["s3"]["bad"]],
                      D["s3"]["nf"][~D["s3"]["bad"]], tmax=tmax)[1]
    hdr = ("   t  | d0wd rssi B1/B2/B3     | s3 rssi B1/B2/B3       | "
           "s3 nf | d0wd SFO B1/B2/B3        | s3 SFO B1/B2/B3")
    print(hdr)
    for i, tt in enumerate(EDGES):
        if not (600 <= tt <= 1400):
            continue
        r = f"{tt:5.0f} |"
        for tg in ("d0wd", "s3"):
            for n in ("B1", "B2", "B3"):
                r += f" {S[(tg, n, 'rssi')][i]:7.2f}"
            r += " |"
            if tg == "d0wd":
                pass
        r += f"{nf_s3[i]:6.2f} |"
        for tg in ("d0wd", "s3"):
            for n in ("B1", "B2", "B3"):
                v = S[(tg, n, "SFO")][i]
                r += f" {v:+8.5f}" if np.isfinite(v) else "        . "
            r += " |"
        print(r)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("csv")
    p.add_argument("--tag", required=True)
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("report")
    p.add_argument("--tags", required=True)
    p.set_defaults(func=cmd_report)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
