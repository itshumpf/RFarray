#!/usr/bin/env python3
r"""exp_display_live_0822 — the 2026-08-22 23:57:39 dual-receiver capture.

The one thing new about this pair of files: the Heltec ESP32-S3 (node_id
108) has a working SSD1306 panel for the first time in this project, so
`display_task` (firmware/csi_rx/main/main.c:427-580) actually runs. Every
earlier capture in data/raw/ was taken with `oled_init()` failing and the
task never created (docs/OLED_AND_MARGINAL_CELL.md section 2.1), so the
4 Hz I2C load has never been in the data before. The D0WD (node_id 68) is
the control in the same session, same host process, same host clock.

Four questions, four subcommands, plus `report` which runs all of them:

  census   per-node / per-MAC census, corrupt-row screens, drop accounting
  phase    is there periodic structure in frame ARRIVAL timing?
  events   locate the two operator-reported events from |dRSSI|
  dsp      per-beacon phase-domain health via rff.dsp.FrameEstimator

Read-only. It opens the two CSVs and writes nothing but stdout and an
optional --cache .npz under the system temp dir.

WHAT IS AND IS NOT COMBINED HERE
--------------------------------
`dsp` is the phase domain (pc/rff/). `events` is the amplitude domain
(RSSI level). CLAUDE.md forbids combining or cross-citing their numbers
and nothing below does: no `events` figure is derived from a `dsp` figure
or the reverse. They are printed by one script only because they read the
same two files.

THREE CLOCKS, AND WHY THE DISTINCTION DECIDES THE PHASE TEST
------------------------------------------------------------
  pc_time_us        host wall clock, stamped per decoded record inside the
                    serial drain loop (pc/capture.py:129). Records decoded
                    out of one ser.read(8192) get near-identical stamps, so
                    this clock is BATCHED at the host's serial read
                    granularity, not per frame (docs/HANDOFF.md trap #1).
  esp_timestamp_us  node clock, per frame, u32 us, wraps at 4294.967 s.
                    It is info->rx_ctrl.timestamp, the WiFi MAC RECEIVE
                    clock (main.c:127) -- assigned in the CSI callback,
                    strictly UPSTREAM of the queue and of csi_drain_task.
  FreeRTOS ticks    what display_task's vTaskDelay is scheduled off.

Consequence, stated up front because it bounds what this script can
conclude: a display_task stall can only ever delay a frame's DELIVERY, so
it can only show in pc_time_us. It cannot move esp_timestamp_us, which is
stamped before the frame is queued. With zero drops on the S3 there is no
third channel. The `phase` subcommand therefore folds a HOST-time quantity
onto a NODE-clock phase, and reports a detection ceiling, not just a p.
"""
import argparse
import csv
import json
import math
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rff.dsp import FrameEstimator                      # noqa: E402

# --------------------------------------------------------------- inputs ----

FILES = {
    "s3":   "data/raw/s3_20260822_235739.csv",
    "d0wd": "data/raw/d0wd_20260822_235739.csv",
}
NODE_ID = {"s3": 108, "d0wd": 68}

# Beacon MACs and names, from firmware/csi_rx/main/main.c:180-185, which
# mirrors pc/occ/__init__.py BEACON_MACS.
BEACONS = [
    ("a4:f0:0f:77:91:20", "B1"),
    ("28:05:a5:2f:fa:48", "B2"),
    ("f4:2d:c9:70:72:30", "B3"),
]
BEACON_OF = dict(BEACONS)

DROP_WRAP = 1 << 16          # `dropped` is u16 (main.c:170)
TS_WRAP = 1 << 32            # esp_timestamp_us is u32 us

# Corrupt-row screen, route 2 (field plausibility) — six fields that have
# nothing to do with `dropped`, per docs/OVERNIGHT_2026-08-22.md section 1.
# csi_len 384 IS admitted: pc/rff/protocol.py:31 sets CSI_MAX = 384 and :59
# rejects only what is longer. Excluding it misclassified a real device once
# already (that doc's "one correction made during this pass").
FIELD_LEN = (128, 256, 384)
NF_LO, NF_HI = -110, -70
RSSI_LO, RSSI_HI = -100, -10

# Corrupt-row screen, route 1 (dropped-column median filter), from
# docs/DUAL_RX_2026-08-21.md Appendix A.
MF_W, MF_TOL = 9, 100


# ---------------------------------------------------------------- ingest ----

def read_capture(path, want_csi=False):
    """Parse one capture CSV with a real CSV reader.

    csi_data is a QUOTED comma-separated list nested inside the CSV, so a
    naive line.split(",") mis-splits every row. csv.reader handles the
    quoting; row counts below are len() of what it yields, never a byte or
    field-arithmetic estimate.

    A short final row (the capture still being written when this runs) is
    counted and skipped rather than crashing or silently truncating a
    column.
    """
    csv.field_size_limit(10 ** 7)
    cols = {k: [] for k in ("pc", "seq", "rssi", "nf", "ch", "esp", "ln",
                            "node", "env", "drop")}
    mac, csi = [], []
    n_short = n_unparsable = 0
    with open(path, newline="", errors="replace") as fh:
        rd = csv.reader(fh)
        header = next(rd)
        for row in rd:
            if len(row) != len(header):
                n_short += 1
                continue
            try:
                cols["pc"].append(int(row[0]))
                cols["seq"].append(int(row[2]))
                cols["rssi"].append(int(row[4]))
                cols["nf"].append(int(row[5]))
                cols["ch"].append(int(row[6]))
                cols["esp"].append(int(row[7]))
                cols["ln"].append(int(row[8]))
                cols["node"].append(int(row[10]))
                cols["env"].append(int(row[11]))
                cols["drop"].append(int(row[12]))
            except ValueError:
                n_unparsable += 1
                for k in cols:                       # keep columns aligned
                    if len(cols[k]) > len(mac):
                        cols[k].pop()
                continue
            mac.append(row[3])
            if want_csi:
                csi.append(row[9])
    macs, inv = np.unique(np.array(mac), return_inverse=True)
    d = {k: np.asarray(v, dtype=np.int64) for k, v in cols.items()}
    d["mi"] = inv.astype(np.int32)
    d["macs"] = macs
    d["n_rows"] = len(mac)
    d["n_short"] = n_short
    d["n_unparsable"] = n_unparsable
    d["header"] = header
    if want_csi:
        d["csi"] = csi
    return d


def load(tag, cache=None, want_csi=False):
    if cache and not want_csi:
        p = os.path.join(cache, tag + ".npz")
        if os.path.exists(p):
            z = np.load(p, allow_pickle=True)
            d = {k: z[k] for k in z.files}
            d["n_rows"] = int(d["n_rows"])
            d["n_short"] = int(d["n_short"])
            d["n_unparsable"] = int(d["n_unparsable"])
            return d
    d = read_capture(FILES[tag], want_csi=want_csi)
    if cache and not want_csi:
        os.makedirs(cache, exist_ok=True)
        np.savez(os.path.join(cache, tag + ".npz"),
                 **{k: v for k, v in d.items() if k not in ("csi", "header")})
    return d


# --------------------------------------------------------------- screens ----

def field_screen(d):
    """Route 2. Returns (clean_mask, mode_node, mode_channel)."""
    node_mode = int(np.bincount(d["node"][d["node"] >= 0]).argmax())
    ch_mode = int(np.bincount(d["ch"][d["ch"] >= 0]).argmax())
    ok = ((d["node"] == node_mode)
          & (d["env"] == 0)
          & (d["ch"] == ch_mode)
          & np.isin(d["ln"], FIELD_LEN)
          & (d["nf"] >= NF_LO) & (d["nf"] <= NF_HI)
          & (d["rssi"] >= RSSI_LO) & (d["rssi"] <= RSSI_HI))
    return ok, node_mode, ch_mode


def median_screen(vals, w=MF_W, tol=MF_TOL):
    """Route 1: |value - running median| > tol. Independent of route 2."""
    from numpy.lib.stride_tricks import sliding_window_view
    h = w // 2
    pad = np.pad(vals.astype(np.float64), (h, h), mode="edge")
    med = np.median(sliding_window_view(pad, w), axis=1)
    return np.abs(vals - med) > tol, med


def drop_total(dropped):
    """Wrap-safe u16 accumulation over an already-screened series.

    Returns (total, n_wraps). Every negative delta left after screening is
    treated as a wrap; the caller must have screened first, because a
    corrupt row produces a negative delta that is NOT a wrap and counting
    it as one overstated the D0WD by 514x once (docs/OVERNIGHT_2026-08-22.md
    section 4.2) and by 51x again tonight in a throwaway command.
    """
    dd = np.diff(dropped.astype(np.int64))
    wraps = int((dd < 0).sum())
    return int(np.where(dd < 0, dd + DROP_WRAP, dd).sum()), wraps


# ---------------------------------------------------------------- census ----

def cmd_census(args):
    for tag in ("s3", "d0wd"):
        d = load(tag, args.cache)
        pc, esp = d["pc"], d["esp"]
        span = (pc[-1] - pc[0]) / 1e6
        ok, node_mode, ch_mode = field_screen(d)
        print("=" * 74)
        print("%s  %s" % (tag, FILES[tag]))
        print("  rows (len of csv.reader output)   %d" % d["n_rows"])
        print("  short/truncated rows skipped      %d" % d["n_short"])
        print("  unparsable rows skipped           %d" % d["n_unparsable"])
        print("  node_id mode %d   channel mode %d" % (node_mode, ch_mode))
        print("  host span   %.3f s   (%.2f min)" % (span, span / 60))
        de = np.diff(esp)
        ts_wraps = int((de < 0).sum())
        print("  node span   %.3f s   esp u32 wraps %d"
              % (((esp[-1] - esp[0]) + ts_wraps * TS_WRAP) / 1e6, ts_wraps))
        print("  delivered rate  %.2f fps (host span)" % (d["n_rows"] / span))

        # --- corrupt rows, two independent routes
        bad_field = ~ok
        bad_med, _ = median_screen(d["drop"])
        print("  corrupt rows: field screen %d, median filter %d, union %d"
              % (bad_field.sum(), bad_med.sum(), (bad_field | bad_med).sum()))
        for i in np.where(bad_field | bad_med)[0]:
            why = []
            if d["node"][i] != node_mode:
                why.append("node_id")
            if d["env"][i] != 0:
                why.append("env_id")
            if d["ch"][i] != ch_mode:
                why.append("channel")
            if d["ln"][i] not in FIELD_LEN:
                why.append("csi_len")
            if not (NF_LO <= d["nf"][i] <= NF_HI):
                why.append("noise_floor")
            if not (RSSI_LO <= d["rssi"][i] <= RSSI_HI):
                why.append("rssi")
            if bad_med[i]:
                why.append("median-filter")
            print("    line %-8d t=%8.1f s  mac %s  rssi %4d nf %4d ch %3d "
                  "len %3d dropped %6d   [%s]"
                  % (i + 2, (pc[i] - pc[0]) / 1e6, d["macs"][d["mi"][i]],
                     d["rssi"][i], d["nf"][i], d["ch"][i], d["ln"][i],
                     d["drop"][i], ",".join(why)))

        # --- drops
        clean = d["drop"][ok]
        tot, wraps = drop_total(clean)
        endpoint = int(clean[-1]) - int(clean[0]) + DROP_WRAP * wraps
        naive, naive_neg = drop_total(d["drop"])
        print("  dropped column: first %d last %d (screened first %d last %d)"
              % (d["drop"][0], d["drop"][-1], clean[0], clean[-1]))
        print("  SCREENED wrap-safe drops  %d   u16 wraps %d" % (tot, wraps))
        print("  endpoint cross-check last-first+65536*wraps = %d  %s"
              % (endpoint, "OK" if endpoint == tot else "MISMATCH"))
        print("  UNSCREENED (wrong) same accumulation       %d   'wraps' %d"
              % (naive, naive_neg))
        if tot:
            print("  overstatement factor if unscreened          %.1fx"
                  % (naive / tot))
        deliv = int(ok.sum())
        print("  loss  %d / (%d + %d) = %.4f %% of offered frames"
              % (tot, deliv, tot, 100.0 * tot / (deliv + tot)))

        # --- delivered rate over time, 60 s bins
        t = (pc - pc[0]) / 1e6
        nb = int(math.ceil(t[-1] / 60.0))
        cnt = np.bincount((t / 60).astype(int), minlength=nb).astype(float)
        full = cnt[:-1] / 60.0
        print("  fps by 60 s bin: mean %.2f  min %.2f @ %d s  max %.2f @ %d s"
              % (full.mean(), full.min(), int(full.argmin()) * 60,
                 full.max(), int(full.argmax()) * 60))
        print("   ", " ".join("%.0f" % v for v in full))

        # --- per-MAC census
        print("  per-MAC (clean rows only):")
        print("    %-18s %8s %8s %8s %7s  %-14s %s"
              % ("mac", "frames", "fps", "rssi", "sd", "csi_len", "t0..t1 s"))
        order = np.argsort([-(d["mi"][ok] == i).sum()
                            for i in range(len(d["macs"]))])
        for i in order:
            sel = ok & (d["mi"] == i)
            n = int(sel.sum())
            if n == 0:
                continue
            rs = d["rssi"][sel].astype(float)
            lh, lc = np.unique(d["ln"][sel], return_counts=True)
            ts = t[sel]
            print("    %-18s %8d %8.3f %8.2f %7.2f  %-14s %.1f..%.1f%s"
                  % (d["macs"][i], n, n / span, rs.mean(), rs.std(),
                     ",".join("%d:%d" % (a, b) for a, b in zip(lh, lc)),
                     ts[0], ts[-1],
                     "  <- " + BEACON_OF[d["macs"][i]]
                     if d["macs"][i] in BEACON_OF else ""))

        # --- per-beacon rate over time
        print("  per-beacon delivered fps by 300 s block:")
        for m, b in BEACONS:
            i = int(np.where(d["macs"] == m)[0][0])
            sel = ok & (d["mi"] == i)
            nblk = int(math.ceil(t[-1] / 300))
            bb = np.bincount((t[sel] / 300).astype(int), minlength=nblk)
            # the last block is partial; divide by its real width, not 300
            wid = np.full(nblk, 300.0)
            wid[-1] = t[-1] - 300.0 * (nblk - 1)
            print("    %s %-18s %s" % (b, m,
                  " ".join("%6.2f" % (v / w) for v, w in zip(bb, wid))))
        print("  noise_floor histogram:",
              dict(zip(*[x.tolist() for x in
                         np.unique(d["nf"][ok], return_counts=True)])))


def cmd_newmac(args):
    """Characterise 64:fa:2b:6d:05:3b, which appears on both receivers."""
    target = args.mac
    print("Characterising %s on both receivers" % target)
    seen = {}
    for tag in ("s3", "d0wd"):
        d = load(tag, args.cache)
        ok, _, _ = field_screen(d)
        w = np.where(d["macs"] == target)[0]
        if not len(w):
            print("  %s: absent" % tag)
            continue
        sel = (d["mi"] == int(w[0]))
        t = (d["pc"] - d["pc"][0]) / 1e6
        span = t[-1]
        print("  %s: %d frames (%d survive the field screen), %.5f fps"
              % (tag, int(sel.sum()), int((sel & ok).sum()),
                 sel.sum() / span))
        for i in np.where(sel)[0]:
            print("     t=%9.3f s  pc=%d  rssi %4d  nf %4d  ch %3d  len %3d "
                  " seq %d  screen=%s"
                  % (t[i], d["pc"][i], d["rssi"][i], d["nf"][i], d["ch"][i],
                     d["ln"][i], d["seq"][i], "clean" if ok[i] else "CORRUPT"))
        seen[tag] = d["pc"][sel]
        # octet distance to every bulk source in the same file
        tb = [int(x, 16) for x in target.split(":")]
        for i, m in enumerate(d["macs"]):
            n = int((d["mi"] == i).sum())
            if n < 1000:
                continue
            ob = [int(x, 16) for x in m.split(":")]
            nd = sum(1 for a, b in zip(tb, ob) if a != b)
            hd = sum(bin(a ^ b).count("1") for a, b in zip(tb, ob))
            print("     vs %-18s (n=%7d): octets differing %d, hamming %d"
                  % (m, n, nd, hd))
    if len(seen) == 2:
        print("  cross-receiver coincidence (host clock):")
        for a in seen["s3"]:
            dt = np.min(np.abs(seen["d0wd"] - a)) / 1e6
            print("     s3 sighting -> nearest d0wd sighting %.3f s away" % dt)
    b0 = int(target.split(":")[0], 16)
    print("  first octet 0x%02x: locally-administered bit %d, multicast bit %d"
          % (b0, (b0 >> 1) & 1, b0 & 1))

    # Are the payloads real LLTF buffers? A mis-decoded / corrupt frame does
    # not respect the guard band. PROJECT_NOTES.md section 2 checked exactly
    # this on 5,000 frames and found guards zero in 99.88 %.
    from rff.dsp import _K_OF_IDX, csi_to_complex
    guard = np.abs(_K_OF_IDX) > 26          # |k| 27..32; DC is counted apart
    dc = _K_OF_IDX == 0
    print("  payload check (guard bins must be zero, PROJECT_NOTES.md s.2;"
          " DC counted separately\n  because it is separately and correctly"
          " dropped):")
    for tag in ("s3", "d0wd"):
        d = load(tag, None, want_csi=True)
        w = np.where(d["macs"] == target)[0]
        if not len(w):
            continue
        est = FrameEstimator()
        for i in np.where(d["mi"] == int(w[0]))[0]:
            v = np.array(d["csi"][i].split(","), dtype=np.float64)
            z = csi_to_complex(v)
            gz = int(np.count_nonzero(z[guard])) if z is not None else -1
            dz = int(np.count_nonzero(z[dc])) if z is not None else -1
            r = est.feed(v, int(d["esp"][i]))
            print("     %-5s t=%9.3f  n_int %3d  nonzero guards %2d/%d  "
                  "DC nonzero %d  %s"
                  % (tag, (d["pc"][i] - d["pc"][0]) / 1e6, v.size, gz,
                     int(guard.sum()), dz,
                     ("slope %+.5f inlier %.3f resid %.4f"
                      % (r["slope"], r["inlier_ratio"], r["resid_std"]))
                     if r else "ransac_line returned None"))


# ----------------------------------------------------------------- phase ----

def bin_resultant(phase_us, val, period_us, nb=25):
    """Rate-normalised circular resultant, docs/OLED_AND_MARGINAL_CELL.md 3.1.

    Frames are not uniform in phase, so a raw value-weighted resultant is
    biased by frame density. Build the statistic from the per-bin MEAN of
    `val` instead:

        r_b = sum(val in bin b) / (frames in bin b)
        C = sum_b r_b cos th_b,  S = sum_b r_b sin th_b
        Rbar = hypot(C, S) / sum_b r_b

    For r(th) = r0 (1 + m cos(th - phi)) this tends to m/2, so m = 2*Rbar is
    the fractional sinusoidal modulation of the mean — the effect size, in
    units of the mean itself.
    """
    b = (phase_us / period_us * nb).astype(np.int64) % nb
    cnt = np.bincount(b, minlength=nb).astype(float)
    tot = np.bincount(b, weights=val, minlength=nb)
    good = cnt > 0
    r = np.zeros(nb)
    r[good] = tot[good] / cnt[good]
    th = (np.arange(nb) + 0.5) / nb * 2 * math.pi
    s = r[good].sum()
    if s == 0:
        return 0.0, r, cnt
    C = float((r[good] * np.cos(th[good])).sum())
    S = float((r[good] * np.sin(th[good])).sum())
    return math.hypot(C, S) / abs(s), r, cnt


def rotation_null(phase_us, val, period_us, nb=25, n=2000, seed=0):
    """Circular rotations of the value series against the phase series.

    Rotation preserves the frame phase distribution AND the autocorrelation
    of the values exactly. That matters here: host arrival gaps are hugely
    autocorrelated (pc/capture.py reads 8192 bytes at a time, so ~20 frames
    share one near-identical stamp and are then followed by one ~200 ms
    gap), and any i.i.d. null — including a Pearson chi-square — treats
    those as independent and over-rejects.
    """
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    m = val.size
    for i in range(n):
        out[i] = bin_resultant(phase_us, np.roll(val, int(rng.integers(1, m))),
                               period_us, nb)[0]
    return out


def rayleigh(phase_us, period_us):
    """Classical Rayleigh test on arrival phases alone. p = exp(-n Rbar^2)."""
    th = phase_us / period_us * 2 * math.pi
    n = th.size
    R = math.hypot(float(np.cos(th).sum()), float(np.sin(th).sum())) / n
    return R, math.exp(-n * R * R)


def _phase_series(d):
    """(node-clock phase carrier, host arrival gap) for every frame but the
    first.

    The gap is measured in HOST time because that is the only clock a
    csi_drain_task stall can move. The phase is taken from the NODE clock
    because that is the clock display_task's FreeRTOS ticks live on; using
    the host clock for phase would add host-vs-node crystal drift to the
    fold. esp_timestamp_us is unwrapped first.
    """
    esp = d["esp"].astype(np.float64).copy()
    de = np.diff(d["esp"].astype(np.int64))
    if (de < 0).any():
        esp += TS_WRAP * np.concatenate([[0], np.cumsum(de < 0)])
    t = esp - esp[0]
    gap = np.diff(d["pc"].astype(np.float64))
    return t[1:], gap, t, esp


def cmd_phase(args):
    nb = 25
    for tag in ("s3", "d0wd"):
        d = load(tag, args.cache)
        ph, gap, t_all, _ = _phase_series(d)
        esp_gap = np.diff(t_all)
        print("=" * 74)
        print("%s   n gaps %d   mean host arrival gap %.1f us"
              % (tag, gap.size, gap.mean()))
        print("  host gap distribution (us): p50 %.0f p90 %.0f p99 %.0f "
              "max %.0f" % tuple(np.percentile(gap, [50, 90, 99, 100])))
        big = gap[gap > 100000]
        print("  gaps > 100 ms: %d, carrying %.1f s of the %.1f s span"
              % (big.size, big.sum() / 1e6, (t_all[-1]) / 1e6))
        print("  -> host delivery is BATCHED at ~%.0f ms; that batch period "
              "is the dominant\n     structure in this clock and is "
              "byte-count driven (ser.read(8192),\n     pc/capture.py:88), "
              "not phase-locked to anything on the node."
              % (big.mean() / 1000 if big.size else 0))

        print("\n  -- harmonic table: rate-normalised resultant of the host "
              "arrival gap,\n     folded on the node clock, %d bins, "
              "%d-rotation null" % (nb, args.rot))
        print("    %9s %10s %10s %10s %8s | %11s %10s"
              % ("period ms", "Rbar", "m=2Rbar", "null p95", "p",
                 "density Rbar", "rayleigh p"))
        for P in (250., 500., 1000., 1250., 2500., 5000., 10000.):
            pu = P * 1000.
            R, _, _ = bin_resultant(ph, gap, pu, nb)
            null = rotation_null(ph, gap, pu, nb, n=args.rot, seed=0)
            p = (1 + int((null >= R).sum())) / (args.rot + 1)
            dR, dp = rayleigh(t_all, pu)
            print("    %9.1f %10.6f %10.5f %10.6f %8.4f | %11.6f %10.3g"
                  % (P, R, 2 * R, np.percentile(null, 95), p, dR, dp))

        print("\n  -- effect-size ceiling at 250 ms (what a stall would have "
              "to be to show)")
        pu = 250000.
        R, r, cnt = bin_resultant(ph, gap, pu, nb)
        null = rotation_null(ph, gap, pu, nb, n=args.rot, seed=0)
        p95 = float(np.percentile(null, 95))
        ceil_m = 2 * p95
        print("     mean gap per 10 ms phase bin, us:")
        print("      ", " ".join("%.0f" % v for v in r))
        print("     bin mean %.0f us, peak-to-peak %.0f us, bin sd %.0f us"
              % (r.mean(), np.ptp(r), r.std()))
        print("     null p95 of Rbar = %.6f  ->  detectable m >= %.5f"
              % (p95, ceil_m))
        print("     i.e. a sinusoidal modulation of the mean host arrival "
              "gap larger than\n     %.5f x %.0f us = %.0f us would have "
              "been detected."
              % (ceil_m, r.mean(), ceil_m * r.mean()))
        # translate the ceiling into the drain stall it corresponds to.
        # For a flat rate r0 with ONE bin lifted by H, C and S from the flat
        # part cancel exactly, so Rbar = H / (nb*r0 + H) ~ H / (nb*r0).
        H = p95 * nb * r.mean()
        fpb = gap.size / (t_all[-1] / pu) / nb        # frames per bin per cycle
        print("     one-bin-bump form: a stall confined to a single 10 ms "
              "phase bin lifts\n     that bin's mean gap by H, and Rbar = "
              "H/(%d*r0). p95 -> H <= %.0f us." % (nb, H))
        print("     at %.3f frames per phase bin per cycle, that is a "
              "per-cycle drain stall\n     of at most %.2f ms."
              % (fpb, H * fpb / 1000.0))

        print("\n  -- period scan (peak Rbar), host gap folded on node clock")
        fine = np.arange(240., 290., 0.1)
        rs = np.array([bin_resultant(ph, gap, p * 1000., nb)[0] for p in fine])
        k = int(rs.argmax())
        print("     fine   240-290 ms /0.1: peak Rbar %.6f @ %.3f ms   "
              "(Rbar at 250.000 = %.6f)" % (rs[k], fine[k], R))
        # scan-max null: 500 trial periods is 500 chances, so the pointwise
        # p95 above is not the right bar for the scan maximum.
        grid = np.arange(240., 290., 0.5)
        rng = np.random.default_rng(1)
        mx = np.empty(args.scanrot)
        for i in range(args.scanrot):
            g2 = np.roll(gap, int(rng.integers(1, gap.size)))
            mx[i] = max(bin_resultant(ph, g2, p * 1000., nb)[0] for p in grid)
        print("     scan-max null (%d rotations, 0.5 ms grid): p95 %.6f, "
              "max %.6f  -> p = %.4f"
              % (args.scanrot, np.percentile(mx, 95), mx.max(),
                 (1 + int((mx >= rs[k]).sum())) / (args.scanrot + 1)))
        coarse = np.arange(150., 350., 0.5)
        rc = np.array([bin_resultant(ph, gap, p * 1000., nb)[0]
                       for p in coarse])
        top = np.argsort(-rc)[:1]
        print("     coarse 150-350 ms /0.5: peak Rbar %.6f @ %.1f ms"
              % (rc[top[0]], coarse[top[0]]))
        print("     (that peak is the HOST serial batch line, not a node "
              "task; it is what a\n      real periodicity in this quantity "
              "looks like at this sample size.)")

        print("\n  -- the 250 ms / 5000 ms alias check")
        print("     5000 = 20 x 250 exactly, so a 5 s source lands in the "
              "same 250 ms phase\n     slot every cycle and masquerades as "
              "250 ms structure. status_task is\n     5000 ms "
              "(main.c:62,339) and rf_liveness_check is 5 s "
              "(node_hal.c:257).\n     Folding at 5000 ms into 20 slots of "
              "250 ms: one hot slot = a 5 s source,\n     twenty equal "
              "peaks = a genuine 250 ms source.")
        _, r20, c20 = bin_resultant(ph, gap, 5000000., 20)
        share = c20 / c20.sum()
        print("     slot mean gap us:", " ".join("%.0f" % v for v in r20))
        z = (r20 - r20.mean()) / r20.std()
        print("     slot z-scores    :", " ".join("%+.2f" % v for v in z))
        print("     hottest slot %d at %+.2f sd; frame share %.4f "
              "(expected %.4f)"
              % (int(z.argmax()), z.max(), share[int(z.argmax())], 1 / 20))
        _, r100, _ = bin_resultant(ph, gap, 5000000., 100)
        hot = np.where(r100 > r100.mean() + 1.5 * r100.std())[0]
        print("     at 100 bins of 50 ms, bins above +1.5 sd: %s"
              % (hot.tolist() if hot.size else "none"))
        if hot.size > 1:
            print("     their spacing (bins of 50 ms): %s"
                  % np.diff(hot).tolist())

        print("\n  -- drift-robust block fold (60 s blocks, resultants "
              "averaged, 250 ms)")
        blocks = (ph / 60e6).astype(int)
        sels = [blocks == b for b in range(blocks.max() + 1)]
        sels = [s for s in sels if s.sum() >= 500]

        def blockstat(g):
            return float(np.mean([bin_resultant(ph[s], g[s], 250000., nb)[0]
                                  for s in sels]))
        rb = blockstat(gap)
        rng = np.random.default_rng(2)
        nullb = np.array([blockstat(np.roll(gap, int(rng.integers(1, gap.size))))
                          for _ in range(args.blockrot)])
        print("     %d blocks, mean per-block Rbar %.5f; rotation null "
              "(%d) mean %.5f p95 %.5f -> p = %.4f"
              % (len(sels), rb, args.blockrot, nullb.mean(),
                 np.percentile(nullb, 95),
                 (1 + int((nullb >= rb).sum())) / (args.blockrot + 1)))
        print("     (a per-block Rbar is positively biased -- 27x fewer "
              "samples per fold -- so\n      it must be read against its "
              "own rotation null, not against the global one.)")

        print("\n  -- control quantity: node-clock inter-frame gap, same fold")
        Re, _, _ = bin_resultant(ph, esp_gap, 250000., nb)
        print("     Rbar %.6f at 250 ms. This is RF arrival cadence. "
              "esp_timestamp_us is\n     stamped in the CSI callback, "
              "upstream of the queue and the drain, so a\n     display "
              "stall CANNOT move it. With zero drops on the S3 this fold "
              "is\n     uninformative about the display BY CONSTRUCTION "
              "and is printed only to\n     show the fold machinery on a "
              "quantity known to be blind." % Re)


# ---------------------------------------------------------------- events ----

def _cells(cache):
    """10 s binned mean RSSI per node x beacon cell, clean rows only.

    Amplitude domain (pc/occ/). Statistic and bin width from
    docs/OCCUPANCY_TEST_0822.md section 5.1: bin-to-bin |delta| of the 10 s
    MEAN RSSI, each cell normalised by its own whole-run median, the cells
    then averaged. No smoothing before the index is formed.
    """
    BIN = 10e6
    R, N, names = [], [], []
    t0 = t1 = None
    for tag in ("s3", "d0wd"):
        d = load(tag, cache)
        ok, _, _ = field_screen(d)
        if t0 is None:
            t0, t1 = d["pc"][0], d["pc"][-1]
        nb = int(math.ceil((t1 - t0) / BIN))
        for m, b in BEACONS:
            i = int(np.where(d["macs"] == m)[0][0])
            sel = ok & (d["mi"] == i)
            bi = ((d["pc"][sel] - t0) / BIN).astype(int)
            cnt = np.bincount(bi, minlength=nb).astype(float)[:nb]
            tot = np.bincount(bi, weights=d["rssi"][sel].astype(float),
                              minlength=nb)[:nb]
            with np.errstate(invalid="ignore"):
                mean = np.where(cnt >= 5, tot / np.maximum(cnt, 1), np.nan)
            R.append(mean)
            N.append(cnt)
            names.append("%s/%s" % (tag, b))
    return np.array(R), np.array(N), names


def cmd_events(args):
    R, N, names = _cells(args.cache)
    nc, nb = R.shape
    t = np.arange(nb) * 10
    D = np.abs(np.diff(R, axis=1))
    med = np.nanmedian(D, axis=1, keepdims=True)
    idx = np.nanmean(D / med, axis=0)
    ti = t[1:]
    print("cells:", ", ".join(names))
    print("per-cell whole-run median |dRSSI| (dB): %s"
          % " ".join("%s=%.4f" % (n, m) for n, m in zip(names, med.ravel())))
    base = float(np.median(idx))
    mad = float(np.median(np.abs(idx - base)))
    thr = base + 3 * mad * 1.4826
    print("motion index: median %.4f MAD %.4f -> 3 sigma(MAD) threshold %.3f"
          % (base, mad, thr))
    above = np.where(idx > thr)[0]
    print("bins above threshold: %s"
          % [(int(ti[j]), round(float(idx[j]), 2)) for j in above])

    # --- coherent level-step scan
    W = args.win // 10
    sig = np.array([np.nanstd(np.diff(R[c])) for c in range(nc)]) / math.sqrt(2)
    S = np.full((nc, nb), np.nan)
    for j in range(W, nb - W):
        for c in range(nc):
            a, b = R[c, j - W:j], R[c, j:j + W]
            if np.isnan(a).sum() > W // 4 or np.isnan(b).sum() > W // 4:
                continue
            S[c, j] = ((np.nanmean(b) - np.nanmean(a))
                       / (sig[c] * math.sqrt(2.0 / W)))
    with np.errstate(invalid="ignore"):
        allnan = np.all(np.isnan(S), axis=0)
        rms = np.full(nb, np.nan)
        rms[~allnan] = np.sqrt(np.nanmean(S[:, ~allnan] ** 2, axis=0))
    V = np.full(nb, np.nan)
    for j in range(W, nb - W - 1):
        V[j] = np.nanmean(idx[j:j + W]) / np.nanmean(idx[j - W:j])
    print("\nper-cell per-bin RSSI sd (dB): %s"
          % " ".join("%s=%.3f" % (n, s) for n, s in zip(names, sig)))
    print("\ncoherent level-step scan, half-window %d s, non-maximum "
          "suppressed +-60 s" % args.win)
    print("  %6s %8s %6s  %s  %9s" % ("t (s)", "rms z", "|z|>=3",
                                      "  ".join("%9s" % n for n in names),
                                      "var ratio"))
    seen = []
    for j in np.argsort(-np.nan_to_num(rms)):
        if np.isnan(rms[j]) or any(abs(j - s) < 6 for s in seen):
            continue
        seen.append(j)
        print("  %6d %8.2f %6d  %s  %9.2f"
              % (t[j], rms[j], int(np.nansum(np.abs(S[:, j]) >= 3)),
                 "  ".join("%+9.1f" % S[c, j] for c in range(nc)), V[j]))
        if len(seen) >= args.top:
            break

    # --- report the two operator windows explicitly
    for lab, lo, hi in (("antenna knock (reported ~6-7 min = 360-420 s)",
                         300, 620),
                        ("departure (reported ~26 min = ~1560 s)",
                         1330, int(t[-1]))):
        print("\n-- %s" % lab)
        print("     (both columns are indexed by the BIN BOUNDARY at t: idx"
              " is |mean(t)-mean(t-10)|,\n      rms_z is the +-%d s level "
              "step across the same boundary)" % args.win)
        for j in range(lo // 10, min(hi // 10, nb - 1)):
            mark = "  <<<" if idx[j] > thr else ""
            rz = rms[j + 1] if j + 1 < nb and not np.isnan(rms[j + 1]) else 0.0
            print("     t=%5d idx=%6.3f rms_z=%6.2f %s%s"
                  % (ti[j], idx[j], rz,
                     "#" * int(min(28, idx[j] * 4)), mark))

    # --- before/after comparisons
    def cmp(l1, r1, l2, r2, lab):
        a = np.nanmean(R[:, l1 // 10:r1 // 10], axis=1)
        b = np.nanmean(R[:, l2 // 10:r2 // 10], axis=1)
        e = sig * np.sqrt(10.0 / (r1 - l1) + 10.0 / (r2 - l2))
        print("  %-44s %s" % (lab, " ".join(
            "%s %+5.2f(z%+6.1f)" % (n, dv, dv / ee)
            for n, dv, ee in zip(names, b - a, e))))

    print("\nlevel persistence, antenna candidate:")
    cmp(150, 370, 380, 450, "pre[150,370) -> burst[380,450)")
    cmp(150, 370, 460, 580, "pre[150,370) -> settled[460,580)")
    cmp(150, 370, 700, 1300, "pre[150,370) -> later[700,1300)")
    print("level persistence, departure candidate:")
    cmp(1000, 1420, 1430, 1490, "pre[1000,1420) -> burst[1430,1490)")
    cmp(1000, 1420, 1490, int(t[-1]), "pre[1000,1420) -> after[1490,end)")
    cmp(1300, 1420, 1490, int(t[-1]), "pre[1300,1420) -> after[1490,end)")
    print("\nmotion-index mean by stretch:")
    for lab, a, b in (("[150,370) pre-antenna", 150, 370),
                      ("[380,450) antenna burst", 380, 450),
                      ("[460,580) post-antenna", 460, 580),
                      ("[700,1300) mid-run", 700, 1300),
                      ("[1300,1420) pre-departure", 1300, 1420),
                      ("[1430,end) post-departure", 1430, int(t[-1]))):
        print("  %-28s %.3f" % (lab, np.nanmean(idx[a // 10:b // 10])))


# ------------------------------------------------------------------- dsp ----

def cmd_dsp(args):
    """Phase-domain link health via rff.dsp.FrameEstimator.

    One FrameEstimator per (node, source MAC) stream, exactly as its
    docstring specifies. Reported as per-cell health only. These are
    pc/rff/ numbers; nothing here is combined with the RSSI figures in
    `events`, which are pc/occ/ numbers (CLAUDE.md).
    """
    print("%-6s %-4s %9s %9s %8s %9s %10s %9s %9s"
          % ("node", "b", "frames", "fitted", "nofit %", "med slope",
             "med resid", "med inl", "gate rej %"))
    for tag in ("s3", "d0wd"):
        d = load(tag, None, want_csi=True)
        ok, _, _ = field_screen(d)
        for m, b in BEACONS:
            w = np.where(d["macs"] == m)[0]
            if not len(w):
                continue
            sel = np.where(ok & (d["mi"] == int(w[0])))[0]
            if args.stride > 1:
                sel = sel[::args.stride]
            est = FrameEstimator()
            slopes, resid, inl = [], [], []
            for i in sel:
                v = np.array(d["csi"][i].split(","), dtype=np.float64)
                r = est.feed(v, int(d["esp"][i]))
                if r is None:
                    continue
                slopes.append(r["slope"])
                resid.append(r["resid_std"])
                inl.append(r["inlier_ratio"])
            n, a = len(sel), len(slopes)
            inl = np.asarray(inl)
            resid = np.asarray(resid)
            # WindowAggregator's own admission gate, dsp.py:164
            gate = (inl >= 0.6) & (resid <= 0.8)
            print("%-6s %-4s %9d %9d %8.3f %9.5f %10.4f %9.4f %9.3f"
                  % (tag, b, n, a, 100.0 * (n - a) / max(n, 1),
                     np.median(slopes) if a else float("nan"),
                     np.median(resid) if a else float("nan"),
                     np.median(inl) if a else float("nan"),
                     100.0 * (1 - gate.mean()) if a else float("nan")))
    print("nofit % = ransac_line returned None (dsp.py:97). gate rej % = "
          "share failing\nWindowAggregator's min_inlier_ratio 0.6 / max_resid"
          " 0.8 (dsp.py:164).")


# ------------------------------------------------------------------ main ----

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", default=os.path.join(tempfile.gettempdir(),
                                                    "display_live_0822"),
                    help="scratch .npz cache dir (outside the repo)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("census").set_defaults(fn=cmd_census)

    p = sub.add_parser("newmac")
    p.add_argument("--mac", default="64:fa:2b:6d:05:3b")
    p.set_defaults(fn=cmd_newmac)

    p = sub.add_parser("phase")
    p.add_argument("--rot", type=int, default=2000)
    p.add_argument("--scanrot", type=int, default=200)
    p.add_argument("--blockrot", type=int, default=200)
    p.set_defaults(fn=cmd_phase)

    p = sub.add_parser("events")
    p.add_argument("--win", type=int, default=120)
    p.add_argument("--top", type=int, default=12)
    p.set_defaults(fn=cmd_events)

    p = sub.add_parser("dsp")
    p.add_argument("--stride", type=int, default=1)
    p.set_defaults(fn=cmd_dsp)

    p = sub.add_parser("report")
    p.add_argument("--rot", type=int, default=2000)
    p.add_argument("--scanrot", type=int, default=200)
    p.add_argument("--blockrot", type=int, default=200)
    p.add_argument("--win", type=int, default=120)
    p.add_argument("--top", type=int, default=12)
    p.add_argument("--stride", type=int, default=1)
    p.add_argument("--mac", default="64:fa:2b:6d:05:3b")
    p.set_defaults(fn=None)

    args = ap.parse_args()
    if args.cmd == "report":
        for name, fn in (("CENSUS", cmd_census), ("NEW MAC", cmd_newmac),
                         ("PHASE", cmd_phase), ("EVENTS", cmd_events),
                         ("DSP", cmd_dsp)):
            print("\n" + "#" * 74 + "\n# " + name + "\n" + "#" * 74)
            fn(args)
    else:
        args.fn(args)


if __name__ == "__main__":
    main()
