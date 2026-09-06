#!/usr/bin/env python3
"""Exhaustive multi-estimator replay of selected CSI intervals.

Every CSV row from file start through the target is screened in strict file
order.  The shipped FrameEstimator is fed every preceding clean frame for a
target MAC so its RNG state matches a whole-file production replay.  Detailed
alternative estimates are retained for every clean target frame.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, r"C:\dev\csi-array\pc")
from rff import dsp  # noqa: E402


BEACONS = {
    "B1": "a4:f0:0f:77:91:20",
    "B2": "28:05:a5:2f:fa:48",
    "B3": "f4:2d:c9:70:72:30",
}
TARGETS = {
    # seconds from the first valid row in each receiver file
    "20260830_013943": {"start": 2520, "end": 3720, "beacons": ["B3"],
                         "reason": "night-2 going-to-bed label +/- 10 min"},
    "20260903_013851": {"start": 0, "end": 1200, "beacons": ["B1", "B2"],
                         "reason": "night-6 startup convergence"},
    "20260902_000949": {"start": 4800, "end": 6900, "beacons": ["B2", "B3"],
                         "reason": "night-5 d0wd B2-B3 23-min collapse"},
    "20260905_025053": {"start": 0, "end": 6300, "beacons": ["B2", "B3"],
                         "reason": "night-8 S3 B2-B3 88-min collapse"},
}

K = dsp.K_USABLE.astype(np.float64)
IDX = dsp._USABLE_IDX
CSI_LEN_OK = (128, 256, 384)
NF_LO, NF_HI = -110, -70
RSSI_LO, RSSI_HI = -100, -10
MED_W, MED_TOL, U16 = 9, 100, 65536
MIN_INLIER, MAX_RESID = 0.6, 0.8
FFT_PAD = 1024
REFINE_STEP = 0.0002
REFINE_RADIUS = 2 * np.pi / FFT_PAD
REFINE_OFFSETS = np.arange(-REFINE_RADIUS, REFINE_RADIUS
                           + REFINE_STEP / 2, REFINE_STEP)
REFINE_EXP = np.exp(-1j * np.outer(REFINE_OFFSETS, K))

DTYPE = np.dtype([
    ("pc_us", "i8"), ("elapsed_s", "f8"), ("beacon", "u1"),
    ("rssi", "i2"), ("noise", "i2"), ("length", "i2"),
    ("prod", "f4"), ("prod_inlier", "f4"), ("prod_resid", "f4"),
    ("prod_gate", "?"), ("det", "f4"), ("det_inlier", "f4"),
    ("det_resid", "f4"), ("ols", "f4"), ("e1024", "f4"),
    ("arb", "f4"), ("coh_prod", "f4"), ("coh_det", "f4"),
    ("coh_e1024", "f4"), ("coh_arb", "f4"),
])


def circ(a, b):
    return ((a - b + 32768) % U16) - 32768


def med_flag(vals, ci):
    c = vals[ci]
    offsets = sorted(circ(v, c) for v in vals)
    return abs(offsets[len(offsets) // 2]) > MED_TOL


def field_ok(row, node_expected):
    return (int(row["node_id"]) == node_expected and int(row["env_id"]) == 0
            and int(row["channel"]) == 6 and int(row["len"]) in CSI_LEN_OK
            and NF_LO <= int(row["noise_floor"]) <= NF_HI
            and RSSI_LO <= int(row["rssi"]) <= RSSI_HI)


def fft_coarse(ph):
    z = np.zeros(FFT_PAD, dtype=np.complex128)
    z[np.rint(K).astype(int) % FFT_PAD] = np.exp(1j * ph)
    m = 2 * np.pi * int(np.argmax(np.abs(np.fft.fft(z)))) / FFT_PAD
    return m - 2 * np.pi if m > np.pi else m


def rebranch(ph, m0):
    return m0 * K + np.angle(np.exp(1j * (ph - m0 * K)))


def coherence(ph, m, b):
    return float(abs(np.mean(np.exp(1j * (ph - (m * K + b))))))


def refined_arbiter(ph, coarse):
    # The 1024-point FFT locates the global circular-objective peak. Refine
    # one FFT bin on either side at the same 0.0002 rad/sc resolution used by
    # docs/UNWRAP_DEFECT.md's exhaustive arbiter.
    grid = coarse + REFINE_OFFSETS
    grid = (grid + np.pi) % (2 * np.pi) - np.pi
    z = np.exp(1j * ph)
    # Avoid dispatching a tiny matrix multiply per frame: factor the coarse
    # ramp from the fixed, precomputed refinement offsets.
    base = z * np.exp(-1j * coarse * K)
    score = np.abs(np.sum(REFINE_EXP * base[None, :], axis=1))
    m = float(grid[int(np.argmax(score))])
    b = float(np.angle(np.sum(z * np.exp(-1j * m * K))))
    return m, b


def independent_fit(y):
    return dsp.ransac_line(K, y, rng=np.random.default_rng(3))


def target_metrics(row, prod):
    vals = np.fromstring(row["csi_data"], dtype=np.float64, sep=",")
    csi = dsp.csi_to_complex(vals)
    if csi is None:
        return None
    ph = np.angle(csi[IDX])
    uw = np.unwrap(ph)
    det = independent_fit(uw)
    if det is None:
        return None
    ols_m, _ = np.polyfit(K, uw, 1)
    coarse = fft_coarse(ph)
    ef = independent_fit(rebranch(ph, coarse))
    if ef is None:
        return None
    am, ab = refined_arbiter(ph, coarse)
    dm, db, di, dr = det
    em, eb, _, _ = ef
    return (float(ols_m), dm, di, dr, em, am,
            coherence(ph, prod["slope"], prod["intercept"]),
            coherence(ph, dm, db), coherence(ph, em, eb),
            coherence(ph, am, ab))


def as_record(row, elapsed, beacon_num, prod, alt):
    ols, dm, di, dr, em, am, cp, cd, ce, ca = alt
    gate = prod["inlier_ratio"] >= MIN_INLIER and prod["resid_std"] <= MAX_RESID
    return (int(row["pc_time_us"]), elapsed, beacon_num, int(row["rssi"]),
            int(row["noise_floor"]), int(row["len"]), prod["slope"],
            prod["inlier_ratio"], prod["resid_std"], gate, dm, di, dr,
            ols, em, am, cp, cd, ce, ca)


def write_seconds(arr, path):
    fields = ["second", "beacon", "frames", "prod_gate_frac"]
    ests = ["prod", "det", "ols", "e1024", "arb"]
    fields += [f"{e}_median" for e in ests]
    fields += ["prod_minus_arb_abs_median", "prod_turnout_frac",
               "prod_minus_det_abs_median", "e1024_minus_arb_abs_median",
               "coh_prod_median", "coh_arb_median"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader()
        sec = np.floor(arr["elapsed_s"]).astype(np.int64)
        for b in sorted(set(arr["beacon"].tolist())):
            for s in sorted(set(sec[arr["beacon"] == b].tolist())):
                q = arr[(arr["beacon"] == b) & (sec == s)]
                dpa = np.abs(q["prod"].astype(float) - q["arb"])
                w.writerow({
                    "second": s, "beacon": f"B{b}", "frames": len(q),
                    "prod_gate_frac": float(np.mean(q["prod_gate"])),
                    **{f"{e}_median": float(np.median(q[e])) for e in ests},
                    "prod_minus_arb_abs_median": float(np.median(dpa)),
                    "prod_turnout_frac": float(np.mean(dpa > 0.05)),
                    "prod_minus_det_abs_median": float(np.median(
                        np.abs(q["prod"].astype(float) - q["det"]))),
                    "e1024_minus_arb_abs_median": float(np.median(
                        np.abs(q["e1024"].astype(float) - q["arb"]))),
                    "coh_prod_median": float(np.median(q["coh_prod"])),
                    "coh_arb_median": float(np.median(q["coh_arb"])),
                })


def replay(path, outdir, cfg, progress_rows):
    started = time.time(); rows = parsed = corrupt = target_clean = 0
    field_bad = median_bad = both_bad = nofit = alt_nofit = 0
    origin = None; pend = []; hist = 0; records = []
    mac_to_num = {BEACONS[b]: int(b[1:]) for b in cfg["beacons"]}
    ests = {mac: dsp.FrameEstimator(rng_seed=0) for mac in mac_to_num}
    end_us = None
    node_expected = 108 if path.name.startswith("s3_") else 68

    def emit(rec, mbad):
        nonlocal corrupt, field_bad, median_bad, both_bad, nofit, alt_nofit
        nonlocal target_clean
        row, fbad = rec
        field_bad += int(fbad); median_bad += int(mbad); both_bad += int(fbad and mbad)
        if fbad or mbad:
            corrupt += 1
            return
        mac = row["mac"].lower()
        if mac not in ests:
            return
        vals = np.fromstring(row["csi_data"], dtype=np.float64, sep=",")
        prod = ests[mac].feed(vals, int(row["esp_timestamp_us"]))
        if prod is None:
            nofit += 1
            return
        elapsed = (int(row["pc_time_us"]) - origin) / 1e6
        if not (cfg["start"] <= elapsed < cfg["end"]):
            return
        target_clean += 1
        alt = target_metrics(row, prod)
        if alt is None:
            alt_nofit += 1
            return
        records.append(as_record(row, elapsed, mac_to_num[mac], prod, alt))

    with path.open("r", newline="", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows += 1
            try:
                pc = int(row["pc_time_us"]); drop = int(row["dropped"])
                if origin is None:
                    origin = pc; end_us = origin + int(cfg["end"] * 1e6)
                fbad = not field_ok(row, node_expected)
            except (KeyError, ValueError):
                continue
            parsed += 1
            pend.append((row, fbad, drop))
            while hist < len(pend) and len(pend) - 1 - hist >= MED_W // 2:
                lo = max(0, hist - MED_W // 2); hi = min(len(pend), hist + MED_W // 2 + 1)
                vals = [pend[k][2] for k in range(lo, hi)]
                emit(pend[hist][:2], med_flag(vals, hist - lo) if len(vals) >= 3 else False)
                hist += 1
                while hist > MED_W // 2:
                    del pend[0]; hist -= 1
            if progress_rows and rows % progress_rows == 0:
                print(f"{path.name}: {rows:,} rows, retained {len(records):,}, "
                      f"{rows / max(time.time()-started, 1e-9):,.0f} rows/s",
                      file=sys.stderr, flush=True)
            if end_us is not None and pc >= end_us:
                break
        while hist < len(pend):
            lo = max(0, hist - MED_W // 2); hi = min(len(pend), hist + MED_W // 2 + 1)
            vals = [pend[k][2] for k in range(lo, hi)]
            emit(pend[hist][:2], med_flag(vals, hist - lo) if len(vals) >= 3 else False)
            hist += 1

    arr = np.array(records, dtype=DTYPE)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = path.stem
    tmp = outdir / f"{stem}.frames.tmp.npz"
    final = outdir / f"{stem}.frames.npz"
    np.savez_compressed(tmp, frames=arr)
    # numpy appends .npz when needed; tmp already has it.
    os.replace(tmp, final)
    write_seconds(arr, outdir / f"{stem}.seconds.csv")
    meta = {
        "source": str(path.resolve()), "source_size": path.stat().st_size,
        "source_mtime_ns": path.stat().st_mtime_ns, "config": cfg,
        "rows_scanned": rows, "parsed": parsed, "origin_pc_us": origin,
        "corrupt_union": corrupt, "field_bad": field_bad,
        "median_bad": median_bad, "both_bad": both_bad,
        "production_nofit_before_or_within_target": nofit,
        "target_clean_fitted": target_clean, "alternative_nofit": alt_nofit,
        "retained": len(arr), "elapsed_wall_s": time.time() - started,
        "estimators": {
            "prod": "stateful FrameEstimator seed=0, exact preceding target-MAC stream",
            "det": "np.unwrap + RANSAC, fresh seed=3 per frame",
            "ols": "np.unwrap + all-bin ordinary least squares",
            "e1024": "1024 FFT anchor + rebranch + fresh-seed RANSAC",
            "arb": "1024 FFT global peak + 0.0002 rad/sc circular-objective refinement",
        },
    }
    (outdir / f"{stem}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"done {path.name}: {rows:,} rows, {len(arr):,} target frames, "
          f"{meta['elapsed_wall_s']:.1f}s", file=sys.stderr, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--progress-rows", type=int, default=250_000)
    args = ap.parse_args()
    out = Path(args.out)
    for raw in args.paths:
        path = Path(raw); stamp = path.stem.split("_", 1)[1]
        if stamp not in TARGETS:
            raise SystemExit(f"no target configured for {stamp}")
        replay(path, out, TARGETS[stamp], args.progress_rows)


if __name__ == "__main__":
    main()
