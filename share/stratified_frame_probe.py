#!/usr/bin/env python3
"""Deterministic frame-level DSP probe sampled from every capture minute.

Every CSV row is visited.  For each (minute, beacon), reservoir-sample N raw
CSI frames, compute independent per-frame diagnostics, and emit one summary
row.  Independent fits intentionally avoid production FrameEstimator state;
this is a defect/pattern probe, not a replacement for production replay.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, r"C:\dev\csi-array\pc")
from rff import dsp  # noqa: E402


BEACONS = {
    "a4:f0:0f:77:91:20": "B1",
    "28:05:a5:2f:fa:48": "B2",
    "f4:2d:c9:70:72:30": "B3",
}
FIELDS = [
    "file", "receiver", "stamp", "minute", "beacon", "mac", "all_frames",
    "sampled", "rssi_median", "noise_median", "slope_median", "slope_iqr",
    "slope_ols_median", "ransac_ols_abs_median", "ransac_ols_gt_0p05_frac",
    "inlier_median", "inlier_p10", "resid_median", "phase_coherence_median",
    "phase_roughness_median", "amplitude_median", "amplitude_cv_median",
    "k_plus1_amplitude_median", "zero_usable_bins_median",
    "saturation_frac_median", "cir_peak_fraction_median", "cir_rms_delay_median",
]


def seed_for(*parts):
    blob = "|".join(map(str, parts)).encode()
    return int.from_bytes(hashlib.blake2b(blob, digest_size=8).digest(), "little")


class Reservoir:
    def __init__(self, cap, seed):
        self.cap = cap
        self.seen = 0
        self.items = []
        self.rng = random.Random(seed)

    def add(self, item):
        self.seen += 1
        if len(self.items) < self.cap:
            self.items.append(item)
        else:
            j = self.rng.randrange(self.seen)
            if j < self.cap:
                self.items[j] = item


def med(a):
    return float(np.median(a)) if len(a) else float("nan")


def pct(a, p):
    return float(np.percentile(a, p)) if len(a) else float("nan")


def iqr(a):
    return float(np.subtract(*np.percentile(a, [75, 25]))) if len(a) else float("nan")


def frame_features(csi_text, seed):
    vals = np.fromstring(csi_text, dtype=np.float64, sep=",")
    H = dsp.csi_to_complex(vals)
    if H is None:
        return None
    Hu = H[dsp._USABLE_IDX]
    phase = np.unwrap(np.angle(Hu))
    fit = dsp.ransac_line(dsp.K_USABLE.astype(float), phase,
                          rng=np.random.default_rng(seed))
    if fit is None:
        return None
    slope, intercept, inlier, resid = fit
    slope_ols, intercept_ols = np.polyfit(dsp.K_USABLE, phase, 1)
    circular_resid = np.angle(np.exp(1j * (phase - (slope * dsp.K_USABLE + intercept))))
    coherence = abs(np.mean(np.exp(1j * circular_resid)))
    roughness = np.median(np.abs(np.diff(circular_resid, n=2)))
    amp = np.abs(Hu)
    kp1 = int(np.flatnonzero(dsp.K_USABLE == 1)[0])
    sat = np.mean(np.abs(vals[:128]) >= 127)
    cir = np.fft.ifft(H)
    power = np.abs(cir) ** 2
    peak = int(np.argmax(power))
    dist = np.minimum((np.arange(64) - peak) % 64, (peak - np.arange(64)) % 64)
    psum = power.sum()
    rms_delay = np.sqrt(np.sum(power * dist ** 2) / psum) if psum else np.nan
    return {
        "slope": slope, "slope_ols": float(slope_ols), "inlier": inlier,
        "resid": resid, "coherence": float(coherence), "roughness": float(roughness),
        "amp": float(np.median(amp)),
        "amp_cv": float(np.std(amp) / np.mean(amp)) if np.mean(amp) else np.nan,
        "kp1": float(amp[kp1]), "zeros": int(np.sum(amp == 0)),
        "sat": float(sat), "cir_peak": float(power[peak] / psum) if psum else np.nan,
        "cir_rms": float(rms_delay),
    }


def summarize(path, minute, mac, reservoir):
    ff = []
    rssis, noises = [], []
    for j, (rssi, noise, csi) in enumerate(reservoir.items):
        x = frame_features(csi, seed_for(path.name, minute, mac, j))
        if x is not None:
            ff.append(x); rssis.append(rssi); noises.append(noise)
    def col(name): return [x[name] for x in ff if np.isfinite(x[name])]
    delta = [abs(x["slope"] - x["slope_ols"]) for x in ff]
    return {
        "file": path.name,
        "receiver": path.name.split("_", 1)[0],
        "stamp": path.stem.split("_", 1)[1],
        "minute": minute, "beacon": BEACONS[mac], "mac": mac,
        "all_frames": reservoir.seen, "sampled": len(ff),
        "rssi_median": med(rssis), "noise_median": med(noises),
        "slope_median": med(col("slope")), "slope_iqr": iqr(col("slope")),
        "slope_ols_median": med(col("slope_ols")),
        "ransac_ols_abs_median": med(delta),
        "ransac_ols_gt_0p05_frac": float(np.mean(np.asarray(delta) > 0.05)) if delta else np.nan,
        "inlier_median": med(col("inlier")), "inlier_p10": pct(col("inlier"), 10),
        "resid_median": med(col("resid")),
        "phase_coherence_median": med(col("coherence")),
        "phase_roughness_median": med(col("roughness")),
        "amplitude_median": med(col("amp")), "amplitude_cv_median": med(col("amp_cv")),
        "k_plus1_amplitude_median": med(col("kp1")),
        "zero_usable_bins_median": med(col("zeros")),
        "saturation_frac_median": med(col("sat")),
        "cir_peak_fraction_median": med(col("cir_peak")),
        "cir_rms_delay_median": med(col("cir_rms")),
    }


def scan(path, dest, per_minute, progress_rows):
    started = time.time(); rows = 0; origin = None; current_minute = None
    cells = {}
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with path.open("r", newline="", errors="replace") as f, \
            tmp.open("w", newline="", encoding="utf-8") as g:
        reader = csv.DictReader(f)
        writer = csv.DictWriter(g, fieldnames=FIELDS)
        writer.writeheader()

        def flush():
            for mac, reservoir in sorted(cells.items()):
                writer.writerow(summarize(path, current_minute, mac, reservoir))
            cells.clear()

        for row in reader:
            rows += 1
            try:
                pc = int(row["pc_time_us"]); mac = row["mac"].lower()
                rssi = int(row["rssi"]); noise = int(row["noise_floor"])
                ln = int(row["len"])
            except (ValueError, KeyError):
                continue
            if origin is None:
                origin = pc
            minute = (pc - origin) // 60_000_000
            if current_minute is None:
                current_minute = minute
            if minute != current_minute:
                flush(); current_minute = minute
            if mac in BEACONS and ln >= 128:
                cell = cells.get(mac)
                if cell is None:
                    cell = cells[mac] = Reservoir(
                        per_minute, seed_for(path.name, minute, mac))
                cell.add((rssi, noise, row["csi_data"]))
            if progress_rows and rows % progress_rows == 0:
                rate = rows / max(time.time() - started, 1e-9)
                print(f"{path.name}: {rows:,} rows, {rate:,.0f} rows/s",
                      file=sys.stderr, flush=True)
        if current_minute is not None:
            flush()
    os.replace(tmp, dest)
    meta = {"file": str(path.resolve()), "size_bytes": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns, "rows": rows,
            "per_minute": per_minute, "elapsed_s": time.time() - started}
    dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"done {path.name}: {rows:,} rows in {meta['elapsed_s']:.1f}s",
          file=sys.stderr, flush=True)


def is_complete(dest, path, per_minute):
    meta = dest.with_suffix(".meta.json")
    if not dest.exists() or not meta.exists(): return False
    try: d = json.loads(meta.read_text(encoding="utf-8"))
    except Exception: return False
    st = path.stat()
    return (d.get("size_bytes") == st.st_size and d.get("mtime_ns") == st.st_mtime_ns
            and d.get("per_minute") == per_minute)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-minute", type=int, default=24)
    ap.add_argument("--progress-rows", type=int, default=1_000_000)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(); out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    for raw in args.paths:
        path = Path(raw); dest = out / f"{path.stem}.minute_probe.csv"
        if not args.force and is_complete(dest, path, args.per_minute):
            print(f"skip completed {path.name}", file=sys.stderr); continue
        scan(path, dest, args.per_minute, args.progress_rows)


if __name__ == "__main__":
    main()
