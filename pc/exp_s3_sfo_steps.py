#!/usr/bin/env python3
"""Why does the Heltec S3's per-beacon SFO step mid-session (docs/DUAL_RX_2026-08-21.md 3.3)?

Read-only. Opens no serial port, writes nothing into data/raw/, and touches
no file in the repo. Caches go to --cache-dir, which defaults OUTSIDE the
repo tree.

Two passes over each capture CSV:

  scan   cheap streaming pass, no CSI parse. Per frame it keeps
         pc_time_us, mac, rssi, noise_floor, channel, esp_timestamp_us,
         csi_len, env_id, dropped. Everything in the front-end /
         housekeeping domain lives here: AGC proxies (noise_floor, rssi),
         throughput proxies (delivered rate, wrap-safe queue drops),
         and the constants that are supposed to be constant.

  sfo    the phase pass. pc/rff/dsp.py FrameEstimator + WindowAggregator,
         64-frame windows, gates inlier_ratio >= 0.6 and resid_std <= 0.8 --
         i.e. pc/rff_offline.py:54-79 with a MAC restriction and a
         pc_time_us window added, which is the pipeline
         docs/DUAL_RX_2026-08-21.md Appendix B used. It additionally
         records per-window inlier_ratio and resid_std (WindowAggregator
         returns mean inlier_ratio as "quality" but drops resid_std), and
         counts *why* frames were rejected.

  report  aligns the two nodes on the common pc_time_us window and prints
          the tables docs/S3_SFO_STEPS.md quotes.

pc/capture.py:compute_cfo, pc/phase_skew.py and pc/fingerprint.py are NOT
used: docs/CODE_INVENTORY.md 4.2 C1/C2/C3 establishes all three have the
DC/guard-band index wrong.

Usage
-----
    python3 pc/exp_s3_sfo_steps.py scan   data/raw/desk_20260821_125017.csv --tag desk
    python3 pc/exp_s3_sfo_steps.py scan   data/raw/s3_20260821_125017.csv   --tag s3
    python3 pc/exp_s3_sfo_steps.py sfo    data/raw/desk_20260821_125017.csv --tag desk
    python3 pc/exp_s3_sfo_steps.py sfo    data/raw/s3_20260821_125017.csv   --tag s3
    python3 pc/exp_s3_sfo_steps.py report --tags desk,s3
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rff.dsp import FrameEstimator, WindowAggregator  # noqa: E402

# pc/occ/__init__.py:19-23 labels. B1 is the reference beacon,
# B3 is the clock twin (docs/LOT_HYPOTHESIS.md).
BEACONS = {
    "a4:f0:0f:77:91:20": "B1",
    "28:05:a5:2f:fa:48": "B2",
    "f4:2d:c9:70:72:30": "B3",
}
BLAB = list(BEACONS.values())

WINDOW = 64                 # pc/rff/dsp.py:164
MIN_INLIER = 0.6            # pc/rff/dsp.py:164
MAX_RESID = 0.8             # pc/rff/dsp.py:164

DEFAULT_CACHE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "s3_sfo_steps_cache")


# ----------------------------------------------------------------- scan ----

def scan(path, tag, cache_dir):
    """Streaming metadata pass. No CSI parse, so this is I/O bound."""
    pc, esp, rssi, nf, ch, clen, env, drop, mi = [], [], [], [], [], [], [], [], []
    macs = {}
    n_lines = n_short = 0
    with open(path) as f:
        f.readline()
        for line in f:
            n_lines += 1
            p = line.split(",", 9)
            if len(p) < 10:
                n_short += 1
                continue
            r = p[9].rsplit(",", 3)
            if len(r) != 4:
                n_short += 1
                continue
            try:
                pc.append(int(p[0]))
                rssi.append(int(p[4]))
                nf.append(int(p[5]))
                ch.append(int(p[6]))
                esp.append(int(p[7]))
                clen.append(int(p[8]))
                env.append(int(r[2]))
                drop.append(int(r[3]))
            except ValueError:
                n_short += 1
                continue
            m = p[3]
            if m not in macs:
                macs[m] = len(macs)
            mi.append(macs[m])

    out = dict(
        pc=np.array(pc, np.int64), esp=np.array(esp, np.int64),
        rssi=np.array(rssi, np.int16), nf=np.array(nf, np.int16),
        ch=np.array(ch, np.int16), clen=np.array(clen, np.int32),
        env=np.array(env, np.int32), drop=np.array(drop, np.int64),
        mi=np.array(mi, np.int32),
        mac_list=np.array(list(macs.keys())),
        n_lines=np.array([n_lines, n_short]),
    )
    os.makedirs(cache_dir, exist_ok=True)
    np.savez_compressed(os.path.join(cache_dir, "scan_%s.npz" % tag), **out)
    print("scan %-5s rows=%d unparsable=%d distinct_macs=%d span=%.3f s"
          % (tag, len(pc), n_short, len(macs), (pc[-1] - pc[0]) * 1e-6))


# ------------------------------------------------------------------ sfo ----

def sfo(path, tag, cache_dir, t0=None, t1=None):
    """Phase pass. pc/rff_offline.py:54-79 with a MAC set + pc window."""
    est = {m: FrameEstimator() for m in BEACONS}          # seed 0, as shipped
    agg = {m: WindowAggregator(window=WINDOW,
                               min_inlier_ratio=MIN_INLIER,
                               max_resid=MAX_RESID) for m in BEACONS}
    buf = {m: {"pc": [], "inl": [], "res": []} for m in BEACONS}
    obs = {m: [] for m in BEACONS}
    # rejection accounting, per beacon, in 60 s pc-time bins
    seen = {m: [] for m in BEACONS}      # (t_s, rej_code) per frame
    # rej_code: 0 accepted, 1 estimator returned None (RANSAC gave up /
    # frame too short), 2 inlier_ratio gate, 3 resid_std gate

    with open(path) as f:
        f.readline()
        for line in f:
            p = line.split(",", 9)
            if len(p) < 10 or p[3] not in BEACONS:
                continue
            m = p[3]
            try:
                pc = int(p[0])
            except ValueError:
                continue
            if t0 is not None and (pc < t0 or pc > t1):
                continue
            r = p[9].rsplit(",", 3)
            if len(r) != 4:
                continue
            cs = r[0]
            if cs[:1] == '"':
                cs = cs[1:-1] if cs[-1:] == '"' else cs[1:]
            parts = cs.split(",", 128)         # csi_to_complex uses [:128]
            if len(parts) < 129:
                continue
            try:
                esp = int(p[7])
                rs = int(p[4])
                v = np.array(parts[:128], dtype=np.float64)
            except ValueError:
                continue

            e = est[m].feed(v, esp)
            ts = pc
            if e is None:
                seen[m].append((ts, 1))
                continue
            if e["inlier_ratio"] < MIN_INLIER:
                seen[m].append((ts, 2))
                continue
            if e["resid_std"] > MAX_RESID:
                seen[m].append((ts, 3))
                continue
            seen[m].append((ts, 0))

            buf[m]["pc"].append(pc)
            buf[m]["inl"].append(e["inlier_ratio"])
            buf[m]["res"].append(e["resid_std"])
            o = agg[m].feed(e, esp, rs)
            if o is not None:
                o["ts_pc"] = float(np.median(buf[m]["pc"])) * 1e-6
                o["inlier_mean"] = float(np.mean(buf[m]["inl"]))
                o["inlier_min"] = float(np.min(buf[m]["inl"]))
                o["resid_mean"] = float(np.mean(buf[m]["res"]))
                o["resid_p95"] = float(np.percentile(buf[m]["res"], 95))
                buf[m] = {"pc": [], "inl": [], "res": []}
                obs[m].append(o)

    out = {}
    for mac, lab in BEACONS.items():
        O = obs[mac]
        out["%s_ts" % lab] = np.array([o["ts_pc"] for o in O])
        out["%s_sfo" % lab] = np.array([o["sfo"] for o in O])
        out["%s_sfoiqr" % lab] = np.array([o["sfo_iqr"] for o in O])
        out["%s_rssi" % lab] = np.array([o["rssi"] for o in O])
        out["%s_inl" % lab] = np.array([o["inlier_mean"] for o in O])
        out["%s_inlmin" % lab] = np.array([o["inlier_min"] for o in O])
        out["%s_res" % lab] = np.array([o["resid_mean"] for o in O])
        out["%s_res95" % lab] = np.array([o["resid_p95"] for o in O])
        out["%s_cfo" % lab] = np.array(
            [o["cfo"] if o["cfo"] is not None else np.nan for o in O])
        S = np.array(seen[mac], dtype=np.int64)
        out["%s_seen_t" % lab] = S[:, 0] if S.size else np.zeros(0, np.int64)
        out["%s_seen_c" % lab] = S[:, 1] if S.size else np.zeros(0, np.int64)
        print("sfo %-5s %s windows=%d frames=%d rejected=%.2f%%"
              % (tag, lab, len(O), len(S),
                 100.0 * (S[:, 1] != 0).mean() if S.size else 0.0))
    os.makedirs(cache_dir, exist_ok=True)
    np.savez_compressed(os.path.join(cache_dir, "sfo_%s.npz" % tag), **out)


# --------------------------------------------------------------- report ----

def med_filt(x, w=9):
    pad = w // 2
    xp = np.pad(x, pad, mode="edge")
    s = np.lib.stride_tricks.sliding_window_view(xp, w)
    return np.median(s, axis=1)


def binstat(t, v, edges, fn):
    """fn over v in each [edges[i], edges[i+1]) bin; NaN where empty."""
    idx = np.digitize(t, edges) - 1
    out = np.full(len(edges) - 1, np.nan)
    for i in range(len(edges) - 1):
        s = v[idx == i]
        if s.size:
            out[i] = fn(s)
    return out


def report(tags, cache_dir, bin_s, lo, hi):
    S = {t: np.load(os.path.join(cache_dir, "scan_%s.npz" % t),
                    allow_pickle=True) for t in tags}
    F = {t: np.load(os.path.join(cache_dir, "sfo_%s.npz" % t)) for t in tags}

    t0 = max(int(S[t]["pc"][0]) for t in tags)
    t1 = min(int(S[t]["pc"][-1]) for t in tags)
    print("common pc_time_us window: %d .. %d  (%.3f s)"
          % (t0, t1, (t1 - t0) * 1e-6))

    span = (t1 - t0) * 1e-6
    edges = np.arange(0, span + bin_s, bin_s)
    centres = edges[:-1] / 60.0

    # ---- per-node constants and housekeeping -----------------------------
    print("\n=== 0. constants that should be constant ===")
    print("%-6s %-10s %-24s %-10s %-16s" % ("node", "channel", "csi_len", "env_id", "node rows"))
    for t in tags:
        d = S[t]
        cl, cc = np.unique(d["clen"], return_counts=True)
        lens = " ".join("%d:%d" % (a, b) for a, b in zip(cl, cc))
        print("%-6s %-10s %-24s %-10s %-16d"
              % (t, np.unique(d["ch"]), lens, np.unique(d["env"]), d["pc"].size))

    # ---- 1. noise_floor --------------------------------------------------
    print("\n=== 1. noise_floor, whole session, per node per beacon ===")
    print("%-6s %-4s %-8s %-8s %-8s %-28s" % ("node", "b", "median", "mean", "sd", "distinct values:count"))
    for t in tags:
        d = S[t]
        macs = list(d["mac_list"])
        for mac, lab in BEACONS.items():
            if mac not in macs:
                continue
            sel = d["mi"] == macs.index(mac)
            v = d["nf"][sel].astype(float)
            u, c = np.unique(v, return_counts=True)
            top = " ".join("%d:%d" % (a, b) for a, b in
                           sorted(zip(u, c), key=lambda z: -z[1])[:5])
            print("%-6s %-4s %-8.2f %-8.3f %-8.3f %-28s"
                  % (t, lab, np.median(v), v.mean(), v.std(), top))

    print("\n=== 1b. noise_floor mean per %ds bin (all frames, per node) ===" % bin_s)
    hdr = "%-8s" % "t(min)"
    for t in tags:
        hdr += " %-12s" % ("nf/" + t)
    print(hdr)
    nfb = {}
    for t in tags:
        d = S[t]
        tt = (d["pc"] - t0) * 1e-6
        nfb[t] = binstat(tt, d["nf"].astype(float), edges, np.mean)
    for i, c in enumerate(centres):
        if not (lo <= c <= hi):
            continue
        row = "%-8.1f" % c
        for t in tags:
            row += " %-12.4f" % nfb[t][i]
        print(row)

    print("\n=== 1c. noise_floor mean per %ds bin, per beacon ===" % bin_s)
    nfbb = {}
    for t in tags:
        d = S[t]
        macs = list(d["mac_list"])
        tt = (d["pc"] - t0) * 1e-6
        for mac, lab in BEACONS.items():
            if mac not in macs:
                continue
            sel = d["mi"] == macs.index(mac)
            nfbb[(t, lab)] = binstat(tt[sel], d["nf"][sel].astype(float),
                                     edges, np.mean)
    keys = [(t, l) for t in tags for l in BLAB if (t, l) in nfbb]
    print("%-8s" % "t(min)" + "".join(" %-11s" % ("%s/%s" % (l, t)) for t, l in keys))
    for i, c in enumerate(centres):
        if not (lo <= c <= hi):
            continue
        print("%-8.1f" % c + "".join(" %-11.4f" % nfbb[k][i] for k in keys))

    # ---- 2. RSSI ---------------------------------------------------------
    print("\n=== 2. RSSI mean per %ds bin, per node per beacon ===" % bin_s)
    rsb = {}
    for t in tags:
        d = S[t]
        macs = list(d["mac_list"])
        tt = (d["pc"] - t0) * 1e-6
        for mac, lab in BEACONS.items():
            if mac not in macs:
                continue
            sel = d["mi"] == macs.index(mac)
            rsb[(t, lab)] = binstat(tt[sel], d["rssi"][sel].astype(float),
                                    edges, np.mean)
    print("%-8s" % "t(min)" + "".join(" %-11s" % ("%s/%s" % (l, t)) for t, l in keys))
    for i, c in enumerate(centres):
        if not (lo <= c <= hi):
            continue
        print("%-8.1f" % c + "".join(" %-11.3f" % rsb[k][i] for k in keys))

    # ---- 3. SFO, all three beacons, common axis --------------------------
    print("\n=== 3. SFO median per %ds bin (rad/sc), per node per beacon ===" % bin_s)
    sfb, nwb = {}, {}
    for t in tags:
        for lab in BLAB:
            tt = F[t]["%s_ts" % lab] - t0 * 1e-6
            vv = F[t]["%s_sfo" % lab]
            sfb[(t, lab)] = binstat(tt, vv, edges, np.median)
            nwb[(t, lab)] = binstat(tt, vv, edges, lambda s: float(s.size))
    print("%-8s" % "t(min)" + "".join(" %-11s" % ("%s/%s" % (l, t)) for t, l in keys))
    for i, c in enumerate(centres):
        if not (lo <= c <= hi):
            continue
        print("%-8.1f" % c + "".join(
            (" %-+11.5f" % sfb[k][i]) if np.isfinite(sfb[k][i]) else " %-11s" % "-"
            for k in keys))

    # ---- 4. estimator health --------------------------------------------
    print("\n=== 4a. per-window mean inlier_ratio per %ds bin ===" % bin_s)
    print("%-8s" % "t(min)" + "".join(" %-11s" % ("%s/%s" % (l, t)) for t, l in keys))
    inb = {}
    for t in tags:
        for lab in BLAB:
            tt = F[t]["%s_ts" % lab] - t0 * 1e-6
            inb[(t, lab)] = binstat(tt, F[t]["%s_inl" % lab], edges, np.mean)
    for i, c in enumerate(centres):
        if not (lo <= c <= hi):
            continue
        print("%-8.1f" % c + "".join(" %-11.4f" % inb[k][i] for k in keys))

    print("\n=== 4b. per-window mean resid_std per %ds bin ===" % bin_s)
    rb = {}
    for t in tags:
        for lab in BLAB:
            tt = F[t]["%s_ts" % lab] - t0 * 1e-6
            rb[(t, lab)] = binstat(tt, F[t]["%s_res" % lab], edges, np.mean)
    print("%-8s" % "t(min)" + "".join(" %-11s" % ("%s/%s" % (l, t)) for t, l in keys))
    for i, c in enumerate(centres):
        if not (lo <= c <= hi):
            continue
        print("%-8.1f" % c + "".join(" %-11.4f" % rb[k][i] for k in keys))

    print("\n=== 4c. frame reject rate (%% of frames) per %ds bin ===" % bin_s)
    rjb = {}
    for t in tags:
        for lab in BLAB:
            st = (F[t]["%s_seen_t" % lab] - t0) * 1e-6
            sc = F[t]["%s_seen_c" % lab]
            rjb[(t, lab)] = binstat(st, (sc != 0).astype(float), edges,
                                    lambda s: 100.0 * s.mean())
    print("%-8s" % "t(min)" + "".join(" %-11s" % ("%s/%s" % (l, t)) for t, l in keys))
    for i, c in enumerate(centres):
        if not (lo <= c <= hi):
            continue
        print("%-8.1f" % c + "".join(" %-11.3f" % rjb[k][i] for k in keys))

    print("\n=== 4d. reject reason mix, whole session "
          "(1=estimator None, 2=inlier gate, 3=resid gate) ===")
    print("%-6s %-4s %-10s %-10s %-10s %-10s" % ("node", "b", "frames", "code1%", "code2%", "code3%"))
    for t in tags:
        for lab in BLAB:
            sc = F[t]["%s_seen_c" % lab]
            if not sc.size:
                continue
            print("%-6s %-4s %-10d %-10.3f %-10.3f %-10.3f"
                  % (t, lab, sc.size, 100 * (sc == 1).mean(),
                     100 * (sc == 2).mean(), 100 * (sc == 3).mean()))

    # ---- 5. throughput / USB proxies ------------------------------------
    print("\n=== 5. delivered fps and wrap-safe queue drops/s per %ds bin ===" % bin_s)
    print("%-8s" % "t(min)" + "".join(
        " %-10s %-10s" % ("fps/" + t, "drp/" + t) for t in tags))
    fpsb, drpb = {}, {}
    for t in tags:
        d = S[t]
        dd = d["drop"].astype(float)
        mf = med_filt(dd, 9)
        good = ~(np.abs(dd - mf) > 100)       # corrupt rows out (DUAL_RX A)
        dg = d["drop"][good]
        tg = (d["pc"][good] - t0) * 1e-6
        delta = np.diff(dg)
        delta = np.where(delta < 0, delta + 65536, delta)
        idx = np.digitize(tg[1:], edges) - 1
        dsum = np.zeros(len(edges) - 1)
        for i in range(len(edges) - 1):
            dsum[i] = delta[idx == i].sum()
        drpb[t] = dsum / bin_s
        tt = (d["pc"] - t0) * 1e-6
        cnt = np.histogram(tt, bins=edges)[0]
        fpsb[t] = cnt / bin_s
    for i, c in enumerate(centres):
        if not (lo <= c <= hi):
            continue
        print("%-8.1f" % c + "".join(
            " %-10.2f %-10.2f" % (fpsb[t][i], drpb[t][i]) for t in tags))

    # ---- 6. esp clock -----------------------------------------------------
    print("\n=== 6. esp_timestamp_us backward steps (u32 wraps / reboots) ===")
    for t in tags:
        d = S[t]
        e = d["esp"]
        neg = np.where(np.diff(e) < 0)[0]
        print("%-6s backward steps=%d" % (t, neg.size))
        for i in neg[:10]:
            print("        at t=%.1f s  %d -> %d" %
                  ((d["pc"][i] - t0) * 1e-6, e[i], e[i + 1]))

    # ---- 7. step-boundary contrast ---------------------------------------
    print("\n=== 7. before/after contrast across the two S3 steps ===")
    windows = [("pre  0-12min", 0, 720), ("post 16-58min", 960, 3480),
               ("late 60-70min", 3600, 4212)]
    print("%-6s %-4s %-16s %-11s %-9s %-9s %-9s %-9s"
          % ("node", "b", "window", "sfo med", "sfo iqr", "rssi", "nf", "inlier"))
    for t in tags:
        d = S[t]
        macs = list(d["mac_list"])
        tt = (d["pc"] - t0) * 1e-6
        for lab in BLAB:
            mac = [k for k, v in BEACONS.items() if v == lab][0]
            fts = F[t]["%s_ts" % lab] - t0 * 1e-6
            for name, a, b in windows:
                w = (fts >= a) & (fts < b)
                if not w.any():
                    continue
                sv = F[t]["%s_sfo" % lab][w]
                sel = (d["mi"] == macs.index(mac)) & (tt >= a) & (tt < b) \
                    if mac in macs else np.zeros(tt.size, bool)
                print("%-6s %-4s %-16s %-+11.5f %-9.5f %-9.3f %-9.4f %-9.4f"
                      % (t, lab, name, np.median(sv),
                         np.subtract(*np.percentile(sv, [75, 25])),
                         d["rssi"][sel].mean() if sel.any() else np.nan,
                         d["nf"][sel].mean() if sel.any() else np.nan,
                         F[t]["%s_inl" % lab][w].mean()))


# ----------------------------------------------------------------- mech ----

def mech(tags, cache_dir, t_step, pre, post):
    """The four reductions docs/S3_SFO_STEPS.md quotes for the mechanism.

    Runs off the caches `scan` and `sfo` already wrote; opens no CSV.
    """
    S = {t: np.load(os.path.join(cache_dir, "scan_%s.npz" % t),
                    allow_pickle=True) for t in tags}
    F = {t: np.load(os.path.join(cache_dir, "sfo_%s.npz" % t)) for t in tags}
    t0 = max(int(S[t]["pc"][0]) for t in tags)

    print("=== M1. 10 s trace across the transition (t_step = %d s) ===" % t_step)
    for tag in tags:
        d = S[tag]
        mm = [str(x) for x in d["mac_list"]]
        tt = (d["pc"] - t0) * 1e-6
        e = np.arange(t_step - 90, t_step + 90, 10)
        idx = np.digitize(tt, e) - 1
        print("-- %s" % tag)
        print("t(s)    nf_mean  frac-94 |" +
              "".join(" %-4s rssi   sfo       inl  |" % l for l in BLAB))
        for i in range(len(e) - 1):
            m = idx == i
            if not m.any():
                continue
            row = "%6.0f  %7.3f %7.3f |" % (
                e[i], d["nf"][m].mean(), (d["nf"][m] == -94).mean())
            for mac, lab in BEACONS.items():
                s = m & (d["mi"] == mm.index(mac)) if mac in mm \
                    else np.zeros(m.size, bool)
                ts = F[tag]["%s_ts" % lab] - t0 * 1e-6
                w = (ts >= e[i]) & (ts < e[i + 1])
                row += " %8.2f  %s %s |" % (
                    d["rssi"][s].mean() if s.any() else np.nan,
                    ("%+.5f" % np.median(F[tag]["%s_sfo" % lab][w])) if w.any()
                    else "    -    ",
                    ("%.3f" % F[tag]["%s_inl" % lab][w].mean()) if w.any()
                    else "  -  ")
            print(row)

    print("\n=== M2. per-60s-bin correlation of SFO median vs fit quality ===")
    print("%-6s %-4s %-7s %-13s %-13s %-11s"
          % ("node", "b", "bins", "r(sfo,resid)", "r(sfo,inlier)", "d sfo/d resid"))
    e = np.arange(0, 4260, 60)
    for tag in tags:
        for lab in BLAB:
            ts = F[tag]["%s_ts" % lab] - t0 * 1e-6
            idx = np.digitize(ts, e) - 1
            s, r, q = [], [], []
            for i in range(len(e) - 1):
                m = idx == i
                if m.sum() < 5:
                    continue
                s.append(np.median(F[tag]["%s_sfo" % lab][m]))
                r.append(F[tag]["%s_res" % lab][m].mean())
                q.append(F[tag]["%s_inl" % lab][m].mean())
            s, r, q = np.array(s), np.array(r), np.array(q)
            a, _ = np.polyfit(r, s, 1)
            print("%-6s %-4s %-7d %-+13.3f %-+13.3f %-11.4f"
                  % (tag, lab, s.size, np.corrcoef(s, r)[0, 1],
                     np.corrcoef(s, q)[0, 1], a))

    print("\n=== M3. bootstrap medians either side of the transition ===")
    rng = np.random.default_rng(0)
    print("%-6s %-4s %-12s %-11s %-24s %-7s"
          % ("node", "b", "window(s)", "median", "95% CI", "n"))
    for tag in tags:
        for lab in BLAB:
            for a, b in (pre, post):
                ts = F[tag]["%s_ts" % lab] - t0 * 1e-6
                v = F[tag]["%s_sfo" % lab][(ts >= a) & (ts < b)]
                if v.size < 10:
                    continue
                bs = np.median(rng.choice(v, size=(4000, v.size),
                                          replace=True), axis=1)
                lo, hi = np.percentile(bs, [2.5, 97.5])
                print("%-6s %-4s %-12s %-+11.5f [%-+.5f, %-+.5f]     %-7d"
                      % (tag, lab, "%d-%d" % (a, b), np.median(v), lo, hi, v.size))

    print("\n=== M4. per-frame slope vs residual gate (needs `frames` caches) ===")
    print("%-10s %-12s %-9s %-8s %-10s" % ("set", "resid gate", "n", "kept%", "slope med"))
    for k in ("s3pre", "s3post", "deskpre", "deskpost"):
        p = os.path.join(cache_dir, "frames_%s.npz" % k)
        if not os.path.exists(p):
            continue
        d = np.load(p)
        for g in (0.80, 0.16, 0.14, 0.12, 0.10):
            m = d["resid"] <= g
            print("%-10s %-12.2f %-9d %-8.1f %-+10.5f"
                  % (k, g, m.sum(), 100 * m.mean(),
                     np.median(d["slope"][m]) if m.sum() > 50 else np.nan))
        print()


# --------------------------------------------------------------- frames ----

def frames(path, tag, cache_dir, mac, t0, t1):
    """Per-FRAME slope/quality dump for one beacon over one pc_time window.

    The window-median tables cannot separate "the estimator is biased on
    poor frames" from "the channel really had that slope": a window median
    of 64 frames hides the per-frame distribution. This dumps it, so the
    pre-step population can be stratified by inlier_ratio and asked whether
    its *best* frames agree with its worst.
    """
    est = FrameEstimator()                      # seed 0, as shipped
    sl, inl, res, rs, ts = [], [], [], [], []
    with open(path) as f:
        f.readline()
        for line in f:
            p = line.split(",", 9)
            if len(p) < 10 or p[3] != mac:
                continue
            try:
                pc = int(p[0])
            except ValueError:
                continue
            if pc < t0 or pc > t1:
                continue
            r = p[9].rsplit(",", 3)
            if len(r) != 4:
                continue
            cs = r[0]
            if cs[:1] == '"':
                cs = cs[1:-1] if cs[-1:] == '"' else cs[1:]
            parts = cs.split(",", 128)
            if len(parts) < 129:
                continue
            try:
                v = np.array(parts[:128], dtype=np.float64)
                e = est.feed(v, int(p[7]))
            except ValueError:
                continue
            if e is None:
                continue
            sl.append(e["slope"])
            inl.append(e["inlier_ratio"])
            res.append(e["resid_std"])
            rs.append(int(p[4]))
            ts.append(pc)
    out = dict(slope=np.array(sl), inlier=np.array(inl), resid=np.array(res),
               rssi=np.array(rs, np.int16), ts=np.array(ts, np.int64))
    os.makedirs(cache_dir, exist_ok=True)
    np.savez_compressed(os.path.join(cache_dir, "frames_%s.npz" % tag), **out)
    print("frames %s n=%d" % (tag, len(sl)))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    fr = sub.add_parser("frames")
    fr.add_argument("path")
    fr.add_argument("--tag", required=True)
    fr.add_argument("--mac", required=True)
    fr.add_argument("--t0", type=int, required=True)
    fr.add_argument("--t1", type=int, required=True)
    fr.add_argument("--cache-dir", default=DEFAULT_CACHE)
    for c in ("scan", "sfo"):
        s = sub.add_parser(c)
        s.add_argument("path")
        s.add_argument("--tag", required=True)
        s.add_argument("--cache-dir", default=DEFAULT_CACHE)
        if c == "sfo":
            s.add_argument("--t0", type=int, default=None)
            s.add_argument("--t1", type=int, default=None)
    mp = sub.add_parser("mech")
    mp.add_argument("--tags", default="desk,s3")
    mp.add_argument("--cache-dir", default=DEFAULT_CACHE)
    mp.add_argument("--t-step", type=float, default=930.0)
    mp.add_argument("--pre", default="330,930")
    mp.add_argument("--post", default="960,1560")
    r = sub.add_parser("report")
    r.add_argument("--tags", default="desk,s3")
    r.add_argument("--cache-dir", default=DEFAULT_CACHE)
    r.add_argument("--bin-s", type=float, default=60.0)
    r.add_argument("--lo", type=float, default=-1e9, help="min t in minutes")
    r.add_argument("--hi", type=float, default=1e9, help="max t in minutes")
    a = ap.parse_args()

    if a.cmd == "frames":
        frames(a.path, a.tag, a.cache_dir, a.mac, a.t0, a.t1)
    elif a.cmd == "scan":
        scan(a.path, a.tag, a.cache_dir)
    elif a.cmd == "sfo":
        sfo(a.path, a.tag, a.cache_dir, a.t0, a.t1)
    elif a.cmd == "mech":
        mech([x for x in a.tags.split(",") if x], a.cache_dir, a.t_step,
             tuple(int(x) for x in a.pre.split(",")),
             tuple(int(x) for x in a.post.split(",")))
    else:
        report([x for x in a.tags.split(",") if x], a.cache_dir,
               a.bin_s, a.lo, a.hi)


if __name__ == "__main__":
    main()
