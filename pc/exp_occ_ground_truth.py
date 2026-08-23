#!/usr/bin/env python3
r"""exp_occ_ground_truth — score the 2026-07-22 labeled occupancy session.

Read-only experiment script. Imports pc/occ/ and pc/occ_offline.py without
modifying either, so every detector, threshold and floor model used here is
the committed one. Nothing is tuned; thresholds are the stock defaults of
`occ_offline.py` (z_on=5, z_solo=12, z_off=3) and `breathing.presence_verdict`
(>= 6.0 dB SNR, >= 5 of the top-10 subcarriers agreeing on the rate).

What it does that `occ_offline.py` does not:

  1. Scores each label separately *per file*, and reports the denominator
     (covered seconds) alongside every percentage, instead of one aggregate.
  2. Splits the session into its two-link block (2026-07-22 afternoon, beacon
     B2 = 28:05:a5:2f:fa:48 off air) and its three-link block (that evening),
     and never mixes them.
  3. Supports an interval-interior guard band, because the protocol says the
     scorer trims the label transition (the operator is still walking out of
     the room for the first seconds of an `empty` interval) and the committed
     scorer does not actually do that. Both trimmed and untrimmed are printed.
  4. Supports calibrating the motion floor on *labeled empty bins* from a
     held-out file of the same session, so the false-alarm rate is not
     measured on the same data that set the threshold.
  5. Dumps every respiration scan's full (SNR, bpm, agreement) rather than
     the strongest eight, so the reported range is the observed range.

Usage (run from pc/):
  python exp_occ_ground_truth.py --report ..\docs\_occ_scoring_raw.txt
  python exp_occ_ground_truth.py --json out.json
"""
import argparse
import json
import os
import sys

import numpy as np

from occ import BEACON_MACS
from occ.ingest import build_link_grids
from occ.motion import motion_metric, CountConditionedFloor, FusedDetector, segments
from occ.breathing import respiration_scan, presence_verdict
import occ_offline

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "data", "raw")

# The session, in capture order. `block` records how many beacon links were
# actually on air, established in docs/NODE_CENSUS.md P7 and re-verified here.
SESSION = [
    "occ_20260722_151807",
    "occ_20260722_152849",
    "occ_20260722_154312",
    "occ_20260722_154716",
    "occ_20260722_155622",
    "occ_20260722_191220",
]

GRID_HZ = 10.0
WINDOW_S = 2.0
DET_KW = dict(z_on=5.0, z_solo=12.0, z_off=3.0)   # occ_offline defaults
GUARD_S = 15.0        # protocol: "first ~15 s of `empty` will contain your exit"
MIN_SCAN_S = 60.0     # respiration_scan's own floor (one Welch segment)
STOCK_SCAN_S = 120.0  # occ_offline.MIN_BREATH_S


# --------------------------------------------------------------------------
# grids, metrics, labels
# --------------------------------------------------------------------------

def load(name):
    path = os.path.join(RAW, name + ".csv")
    grids, labels = build_link_grids(path, GRID_HZ, verbose=False)
    macs = [m for m in BEACON_MACS if m in grids]
    dt = grids[macs[0]].dt
    n = max(grids[m].n for m in macs)
    lab = occ_offline.labels_to_bins(labels, grids[macs[0]].t0, dt, n)
    if lab is None:
        lab = np.full(n, "", dtype=object)
    return dict(name=name, grids=grids, macs=macs,
                names=[BEACON_MACS[m] for m in macs], dt=dt, n=n,
                labels=lab, t0=grids[macs[0]].t0)


def restrict(S, keep):
    """Shallow copy of a session with only the named links kept.

    Used to score the three-link evening file with the afternoon's link set
    (B1+B3), which measures the cost of B2 being off air against *identical*
    ground truth instead of against a different capture.
    """
    T = dict(S)
    T["macs"] = [m for m in S["macs"] if BEACON_MACS[m] in keep]
    T["names"] = [BEACON_MACS[m] for m in T["macs"]]
    T["grids"] = {m: g for m, g in S["grids"].items() if m in T["macs"]}
    T["name"] = S["name"] + "[" + ",".join(T["names"]) + "]"
    return T


def metrics_of(S):
    """Per-link motion metric and frame count on the common bin axis."""
    n, dt = S["n"], S["dt"]
    w = max(3, int(round(WINDOW_S / dt)))
    met, cnt, rssi = {}, {}, {}
    for mac in S["macs"]:
        g = S["grids"][mac]
        m = np.full(n, np.nan)
        m[:g.n] = motion_metric(g, WINDOW_S)
        c = np.zeros(n, dtype=g.count.dtype)
        c[:g.n] = g.count
        r = np.full(n, np.nan, dtype=np.float32)
        r[:g.n] = g.rssi
        met[mac], cnt[mac], rssi[mac] = m, c, r
    return met, cnt, rssi, w


def trim(mask, dt, guard_s):
    """Drop the first guard_s of every contiguous run of `mask`."""
    if guard_s <= 0:
        return mask.copy()
    out = mask.copy()
    k = int(round(guard_s / dt))
    for i0, i1, _ in segments(mask, dt):
        out[i0:min(i1, i0 + k)] = False
    return out


# --------------------------------------------------------------------------
# calibration
# --------------------------------------------------------------------------

def floors_from_empty(sessions, guard_s=GUARD_S):
    """Fit CountConditionedFloor per link on labeled `empty` bins only.

    Pools the given sessions along the time axis. Uses the committed
    CountConditionedFloor unchanged; the only thing this function decides is
    *which bins* are handed to it -- the labeled-vacant ones.
    """
    acc = {}
    for S in sessions:
        met, cnt, rssi, w = metrics_of(S)
        sel = trim(S["labels"] == "empty", S["dt"], guard_s)
        for mac in S["macs"]:
            m = np.where(sel, met[mac], np.nan)
            a = acc.setdefault(mac, ([], [], []))
            a[0].append(m)
            a[1].append(cnt[mac])
            a[2].append(rssi[mac])
    out = {}
    dt = sessions[0]["dt"]
    w = max(3, int(round(WINDOW_S / dt)))
    for mac, (ms, cs, rs) in acc.items():
        m = np.concatenate(ms)
        c = np.concatenate(cs)
        r = np.concatenate(rs)
        if np.isfinite(m).sum() < 50:
            continue
        out[mac] = CountConditionedFloor.fit(m, c, w, dt, r, min_group=50)
    return out


def floors_from_csv(name):
    path = os.path.join(RAW, name + ".csv")
    return occ_offline.calibrate(path, GRID_HZ, WINDOW_S, verbose=False)


# --------------------------------------------------------------------------
# detection
# --------------------------------------------------------------------------

def detect(S, floors, rssi_guard=occ_offline.RSSI_GUARD_DB):
    """Per-link z, fused motion mask. Mirrors occ_offline.analyze()'s logic,
    including its RSSI operating-point guard and self-recalibration fallback."""
    met, cnt, rssi, w = metrics_of(S)
    Z, notes = [], []
    for mac in S["macs"]:
        m, c, g = met[mac], cnt[mac], S["grids"][mac]
        fl = None if floors is None else floors.get(mac)
        src = "transferred"
        if fl is not None:
            rssi_now = float(np.nanmedian(g.rssi))
            if abs(rssi_now - fl.rssi_med) > rssi_guard:
                notes.append(f"{BEACON_MACS[mac]}: floor INVALID "
                             f"(RSSI {fl.rssi_med:+.0f} -> {rssi_now:+.0f} dBm, "
                             f"{rssi_now - fl.rssi_med:+.0f} dB) -> self-recalibrated")
                fl = None
        if fl is None:
            src = "self (quietest half)"
            v = m[np.isfinite(m)]
            quiet = np.where(m <= np.median(v), m, np.nan)
            fl = CountConditionedFloor.fit(quiet, c, w, S["dt"], g.rssi)
        notes.append(f"{BEACON_MACS[mac]}: floor = {src}")
        Z.append(fl.z(m, c, w))
    Z = np.stack(Z)
    active = FusedDetector(S["dt"], **DET_KW).detect(Z)
    have = np.isfinite(Z).any(axis=0)
    return Z, active, have, notes


def scan_label_runs(S, active, have, min_s):
    """Respiration scans confined to motion-quiet, single-label runs.

    Confining to one label is what makes the result attributable to a
    condition; occ_offline scans quiet runs that may straddle labels.
    """
    n, dt = S["n"], S["dt"]
    filled, valid = {}, {}
    for mac in S["macs"]:
        f, vd = S["grids"][mac].filled_shape(max_gap_s=5.0)
        pf = np.full((n, f.shape[1]), np.nan, dtype=f.dtype)
        pf[:f.shape[0]] = f
        pv = np.zeros(n, dtype=bool)
        pv[:vd.size] = vd
        filled[mac], valid[mac] = pf, pv
    quiet = ~active & have
    out = []
    for lab in sorted(set(S["labels"]) - {""}):
        base = quiet & (S["labels"] == lab)
        for i0, i1, _ in segments(base, dt, min_len_s=min_s):
            for mac in S["macs"]:
                vd = valid[mac][i0:i1]
                for j0, j1, _ in segments(vd, dt, min_len_s=min_s):
                    A = filled[mac][i0 + j0:i0 + j1]
                    sc = respiration_scan(A, dt)
                    if sc is None:
                        continue
                    out.append(dict(file=S["name"], label=lab,
                                    link=BEACON_MACS[mac],
                                    i0=int(i0 + j0), i1=int(i0 + j1),
                                    dur_s=round((j1 - j0) * dt, 1),
                                    snr_db=float(sc["snr_db"]),
                                    bpm=float(sc["bpm"]),
                                    n_agree=int(sc["n_agree"]),
                                    verdict=bool(presence_verdict(sc))))
    return out


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------

def score(S, active, have, scans, guard_s):
    breath = np.zeros(S["n"], dtype=bool)
    for sc in scans:
        if sc["verdict"]:
            breath[sc["i0"]:sc["i1"]] = True
    rows = []
    labs = sorted(set(S["labels"]) - {""}) + ["(unlabeled)"]
    for lab in labs:
        raw = (S["labels"] == "") if lab == "(unlabeled)" \
            else (S["labels"] == lab)
        modes = (("all", raw),) if lab == "(unlabeled)" else \
            (("all", raw), ("interior", trim(raw, S["dt"], guard_s)))
        for mode, m in modes:
            sel = m & have
            secs = float(sel.sum() * S["dt"])
            if secs <= 0:
                continue
            rows.append(dict(file=S["name"], label=lab, mode=mode,
                             seconds=round(secs, 1),
                             bins=int(sel.sum()),
                             motion_pct=round(float(active[sel].mean()) * 100, 2),
                             breath_pct=round(float(breath[sel].mean()) * 100, 2),
                             any_pct=round(float((active | breath)[sel].mean()) * 100, 2)))
    return rows


def z_dist(S, Z, guard_s):
    rows = []
    for lab in sorted(set(S["labels"]) - {""}):
        m = trim(S["labels"] == lab, S["dt"], guard_s)
        for li, nm in enumerate(S["names"]):
            v = Z[li][m & np.isfinite(Z[li])]
            if v.size < 10:
                continue
            rows.append(dict(file=S["name"], label=lab, link=nm, n=int(v.size),
                             p50=round(float(np.median(v)), 2),
                             p90=round(float(np.percentile(v, 90)), 2),
                             p99=round(float(np.percentile(v, 99)), 2),
                             mx=round(float(v.max()), 2)))
    return rows


# --------------------------------------------------------------------------

def run(sessions, floors, tag, guard_s, min_scan_s, out):
    out.append(f"\n{'='*74}\nCONFIG: {tag}\n{'='*74}")
    all_rows, all_scans, all_z = [], [], []
    for S in sessions:
        Z, active, have, notes = detect(S, floors)
        scans = scan_label_runs(S, active, have, min_scan_s)
        # breathing-flagged fraction per label needs the mask, recompute
        rows = score(S, active, have, scans, guard_s)
        all_rows += rows
        all_scans += scans
        all_z += z_dist(S, Z, guard_s)
        out.append(f"\n-- {S['name']}  links={','.join(S['names'])}  "
                   f"span={S['n']*S['dt']:.0f}s")
        for nline in notes:
            out.append(f"     {nline}")
        for r in rows:
            out.append(f"     {r['label']:<12} {r['mode']:<9} "
                       f"{r['seconds']:>7.1f}s  motion {r['motion_pct']:>6.2f}%"
                       f"  breathing {r['breath_pct']:>6.2f}%"
                       f"  either {r['any_pct']:>6.2f}%")
    return all_rows, all_scans, all_z


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", help="write machine-readable results here")
    ap.add_argument("--report", help="write the text report here")
    ap.add_argument("--guard-s", type=float, default=GUARD_S)
    args = ap.parse_args()

    out = []

    def p(s=""):
        out.append(s)
        print(s)

    p("exp_occ_ground_truth — 2026-07-22 scripted occupancy session")
    p(f"thresholds: {DET_KW}, presence_verdict stock (>=6.0 dB, >=5 agree)")
    p(f"grid {GRID_HZ:g} Hz, motion window {WINDOW_S:g} s, "
      f"interval-interior guard {args.guard_s:g} s")

    sessions = [load(n) for n in SESSION]

    p("\n--- link census (which beacons were actually on air) ---")
    for S in sessions:
        miss = [BEACON_MACS[m] for m in BEACON_MACS if m not in S["grids"]]
        p(f"  {S['name']}: links {','.join(S['names'])}"
          + (f"   MISSING {','.join(miss)}" if miss else "")
          + f"   span {S['n']*S['dt']:.0f}s")
        for mac in S["macs"]:
            g = S["grids"][mac]
            p(f"      {BEACON_MACS[mac]}: {g.count.mean()/g.dt:5.1f} fps, "
              f"RSSI {np.nanmedian(g.rssi):+.0f} dBm, "
              f"coverage {g.coverage()*100:.1f}%")

    p("\n--- label inventory (protocol ground truth as actually recorded) ---")
    for S in sessions:
        for lab in sorted(set(S["labels"]) - {""}):
            m = S["labels"] == lab
            runs = segments(m, S["dt"])
            p(f"  {S['name']:<22} {lab:<10} "
              f"{m.sum()*S['dt']:7.1f}s in {len(runs)} run(s): "
              + ", ".join(f"{d:.0f}s" for _, _, d in runs))
        m0 = S["labels"] == ""
        p(f"  {S['name']:<22} {'(none)':<10} {m0.sum()*S['dt']:7.1f}s unlabeled")

    two = [S for S in sessions if len(S["macs"]) == 2]
    three = [S for S in sessions if len(S["macs"]) == 3]

    results = {}

    # Config A: cross-session calibration on the overnight assumed-empty file,
    # which is what occ_offline.py's docstring tells you to do.
    fl_a = floors_from_csv("rx_20260714_031131")
    ra, sa, za = run(sessions, fl_a, "A: --calib rx_20260714_031131 "
                     "(overnight, assumed-empty, 2026-07-14)",
                     args.guard_s, MIN_SCAN_S, out)
    results["A"] = dict(rows=ra, scans=sa, z=za)

    # Config B: held-out in-session empty. Score each afternoon empty file with
    # floors fitted on the OTHER afternoon empty file, so no file sets its own
    # threshold. Files with no empty of their own get the pooled pair.
    e1 = next(S for S in sessions if S["name"] == "occ_20260722_154312")
    e2 = next(S for S in sessions if S["name"] == "occ_20260722_155622")
    pairs = [([e2], [e1]), ([e1], [e2]),
             ([e1, e2], [S for S in two if S["name"] not in
                         (e1["name"], e2["name"])])]
    rb, sb, zb = [], [], []
    out.append(f"\n{'='*74}\nCONFIG: B: held-out in-session labeled `empty` "
               f"floors (two-link block only)\n{'='*74}")
    for cal, tgt in pairs:
        if not tgt:
            continue
        fl = floors_from_empty(cal, args.guard_s)
        r, s, z = run(tgt, fl, "B: floors from " +
                      "+".join(c["name"] for c in cal),
                      args.guard_s, MIN_SCAN_S, out)
        rb += r
        sb += s
        zb += z
    results["B"] = dict(rows=rb, scans=sb, z=zb)

    # Config C: evening three-link file against its own labeled empty. In-sample
    # for the empty label -- reported, and flagged as such, not hidden.
    ev = three[0]
    fl_c = floors_from_empty([ev], args.guard_s)
    rc, sc_, zc = run([ev], fl_c, "C: evening three-link file, floors from its "
                      "OWN labeled `empty` (IN-SAMPLE for the empty row)",
                      args.guard_s, MIN_SCAN_S, out)
    results["C"] = dict(rows=rc, scans=sc_, z=zc)

    # Config D: link ablation. Same file, same truth, same floor-fitting
    # procedure -- only the link set changes. This is the two-link caveat
    # measured rather than asserted.
    ev2 = restrict(ev, {"B1", "B3"})
    fl_d = floors_from_empty([ev2], args.guard_s)
    rd, sd, zd = run([ev2], fl_d, "D: evening file scored with the AFTERNOON's "
                     "link set (B1+B3 only, B2 discarded) -- ablation",
                     args.guard_s, MIN_SCAN_S, out)
    results["D"] = dict(rows=rd, scans=sd, z=zd)

    # ---- respiration: every scan, not the strongest few ----
    for tag in ("A", "B", "C", "D"):
        sc = results[tag]["scans"]
        out.append(f"\n--- respiration scans, config {tag} "
                   f"({len(sc)} link-scans >= {MIN_SCAN_S:.0f}s) ---")
        for s in sorted(sc, key=lambda x: (x["file"], x["label"], x["link"])):
            out.append(f"     {s['file']:<22} {s['label']:<8} {s['link']:<3} "
                       f"{s['dur_s']:>6.1f}s  SNR {s['snr_db']:>6.2f} dB  "
                       f"{s['bpm']:>5.1f} bpm  agree {s['n_agree']:>2}  "
                       f"{'PRESENCE' if s['verdict'] else 'below-threshold'}")
        if sc:
            snr = np.array([s["snr_db"] for s in sc])
            bpm = np.array([s["bpm"] for s in sc])
            fin = np.isfinite(snr)
            out.append(f"     ALL scans:  SNR {snr[fin].min():.2f}..{snr[fin].max():.2f} dB "
                       f"(median {np.median(snr[fin]):.2f}); "
                       f"bpm {bpm.min():.1f}..{bpm.max():.1f} "
                       f"(median {np.median(bpm):.1f})")
            pos = [s for s in sc if s["verdict"]]
            if pos:
                psnr = np.array([s["snr_db"] for s in pos])
                pbpm = np.array([s["bpm"] for s in pos])
                out.append(f"     PRESENCE only ({len(pos)}/{len(sc)}): "
                           f"SNR {psnr.min():.2f}..{psnr.max():.2f} dB "
                           f"(median {np.median(psnr):.2f}); "
                           f"bpm {pbpm.min():.1f}..{pbpm.max():.1f} "
                           f"(median {np.median(pbpm):.1f})")
            else:
                out.append("     PRESENCE only: none")

    # ---- pooled per-condition summary (seconds-weighted, per config) ----
    out.append("\n--- pooled per-condition summary "
               "(seconds-weighted over files, interval interiors) ---")
    out.append(f"     {'cfg':<4} {'condition':<12} {'files':>5} {'sec':>8} "
               f"{'motion%':>8} {'breath%':>8} {'either%':>8}")
    for tag in ("A", "B", "C", "D"):
        agg = {}
        for r in results[tag]["rows"]:
            if r["mode"] != "interior" or r["label"] == "(unlabeled)":
                continue
            a = agg.setdefault(r["label"], [0.0, 0.0, 0.0, 0.0, set()])
            a[0] += r["seconds"]
            a[1] += r["seconds"] * r["motion_pct"]
            a[2] += r["seconds"] * r["breath_pct"]
            a[3] += r["seconds"] * r["any_pct"]
            a[4].add(r["file"])
        for lab, a in sorted(agg.items()):
            out.append(f"     {tag:<4} {lab:<12} {len(a[4]):>5} {a[0]:>8.1f} "
                       f"{a[1]/a[0]:>8.2f} {a[2]/a[0]:>8.2f} {a[3]/a[0]:>8.2f}")

    # ---- cross-link respiration rate consensus ----
    out.append("\n--- cross-link respiration agreement "
               "(same file+label, >=2 links scanned) ---")
    out.append("     a real breather should give the same rate on every link "
               "that sees it")
    for tag in ("A", "B", "C", "D"):
        buckets = {}
        for s in results[tag]["scans"]:
            buckets.setdefault((s["file"], s["label"]), []).append(s)
        for (f, lab), ss in sorted(buckets.items()):
            if len(ss) < 2:
                continue
            b = [s["bpm"] for s in ss]
            out.append(f"     [{tag}] {f:<24} {lab:<7} "
                       + ", ".join(f"{s['link']}={s['bpm']:.1f}" for s in ss)
                       + f"   spread {max(b) - min(b):.1f} bpm")

    # ---- motion z distributions ----
    for tag in ("A", "B", "C", "D"):
        out.append(f"\n--- per-label motion z distribution, config {tag} "
                   f"(interval interiors) ---")
        out.append(f"     {'file':<22} {'label':<9} {'link':<4} {'n':>6} "
                   f"{'p50':>7} {'p90':>7} {'p99':>7} {'max':>8}")
        for r in results[tag]["z"]:
            out.append(f"     {r['file']:<22} {r['label']:<9} {r['link']:<4} "
                       f"{r['n']:>6} {r['p50']:>7.2f} {r['p90']:>7.2f} "
                       f"{r['p99']:>7.2f} {r['mx']:>8.2f}")

    text = "\n".join(out)
    print(text[text.index("\n" + "=" * 74):])
    if args.report:
        with open(args.report, "w") as f:
            f.write(text + "\n")
        print(f"\nreport -> {args.report}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=1)
        print(f"json   -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
