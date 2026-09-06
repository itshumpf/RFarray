#!/usr/bin/env python3
"""Eight-night equivalent-delay analysis from exact multiscale replay bins."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np


DELTA_F_HZ = 20_000_000 / 64
SAMPLE_NS = 50.0
SLOPE_PER_SAMPLE = 2 * np.pi / 64
LATTICES_NS = (50.0, 40.0, 45.0, 55.0, 60.0)
TOL_FRAC = 0.10
JUMP_MIN_FRAC = 0.50
WINDOW_MIN = 5
EXCLUSION_MIN = 10


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_scale(root: Path, scale: int) -> np.ndarray:
    paths = sorted(root.glob(f"*.{scale}s.npy"))
    if not paths:
        raise FileNotFoundError(f"no {scale}s summaries under {root}")
    return np.concatenate([np.load(path, mmap_mode="r") for path in paths])


def equiv_ns(slope):
    return -np.asarray(slope, dtype=np.float64) / (2 * np.pi * DELTA_F_HZ) * 1e9


def groups(a: np.ndarray):
    for night in range(1, 9):
        for receiver in (0, 1):
            for beacon in (1, 2, 3):
                q = a[(a["night"] == night) & (a["receiver"] == receiver)
                      & (a["beacon"] == beacon)]
                if len(q):
                    yield night, receiver, beacon, q[np.argsort(q["bin"])]


def base_row(night: int, receiver: int, beacon: int) -> dict:
    return {"night": night, "receiver": "s3" if receiver else "d0wd",
            "beacon": f"B{beacon}"}


def scale_summaries(root: Path) -> list[dict]:
    rows = []
    for scale in (1, 10, 60, 300):
        a = load_scale(root, scale)
        for night, receiver, beacon, q in groups(a):
            y = equiv_ns(q["arb"])
            row = base_row(night, receiver, beacon)
            row.update({"scale_s": scale, "bins": len(y),
                        "frames": int(np.sum(q["count"])),
                        "median_ns": float(np.median(y)),
                        "iqr_ns": float(np.subtract(*np.percentile(y, [75, 25]))),
                        "p05_ns": float(np.percentile(y, 5)),
                        "p95_ns": float(np.percentile(y, 95)),
                        "p05_p95_span_samples": float(
                            (np.percentile(y, 95) - np.percentile(y, 5)) / SAMPLE_NS)})
            rows.append(row)
    return rows


def circular_origin(train: np.ndarray, spacing: float) -> float:
    phase = 2 * np.pi * train / spacing
    return float(np.angle(np.mean(np.exp(1j * phase))) * spacing / (2 * np.pi))


def lattice_distance(y: np.ndarray, origin: float, spacing: float) -> np.ndarray:
    z = (y - origin) / spacing
    return np.abs(z - np.rint(z))


def lattice_holdout(a: np.ndarray) -> list[dict]:
    rows = []
    for night, receiver, beacon, q in groups(a):
        y = equiv_ns(q["arb"])
        cut = len(y) // 2
        if cut < 10 or len(y) - cut < 10:
            continue
        train, test = y[:cut], y[cut:]
        for spacing in LATTICES_NS:
            origin = circular_origin(train, spacing)
            dist = lattice_distance(test, origin, spacing)
            on = dist <= TOL_FRAC
            levels = np.rint((test[on] - origin) / spacing).astype(int)
            counts = Counter(levels.tolist())
            material = sum(v >= 0.05 * len(test) for v in counts.values())
            row = base_row(night, receiver, beacon)
            row.update({"spacing_ns": spacing, "train_bins": len(train),
                        "test_bins": len(test), "origin_ns": origin,
                        "on_lattice_fraction": float(np.mean(on)),
                        "occupied_levels": len(counts),
                        "material_levels": material,
                        "multi_level_evidence": material >= 2})
            rows.append(row)
    return rows


def contiguous(q: np.ndarray, window: int):
    t = q["bin"].astype(np.int64)
    y = equiv_ns(q["arb"])
    for i in range(window, len(q) - window):
        if t[i + window - 1] - t[i - window] != 2 * window - 1:
            continue
        shift = float(np.median(y[i:i + window]) - np.median(y[i - window:i]))
        yield i, int(t[i]), shift


def jump_candidates(a: np.ndarray, spacing: float) -> list[dict]:
    rows = []
    for night, receiver, beacon, q in groups(a):
        start_bin = int(q["bin"][0])
        y = equiv_ns(q["arb"])
        candidates = [(abs(s), i, boundary, s)
                      for i, boundary, s in contiguous(q, WINDOW_MIN)
                      if abs(s) >= JUMP_MIN_FRAC * spacing]
        chosen = []
        for _, i, boundary, shift in sorted(candidates, reverse=True):
            if any(abs(boundary - old_boundary) < EXCLUSION_MIN
                   for old_boundary in chosen):
                continue
            chosen.append(boundary)
            multiple = abs(shift) / spacing
            nearest = max(1, int(round(multiple)))
            pre_y = y[(q["bin"] >= boundary - WINDOW_MIN)
                      & (q["bin"] < boundary)]
            post_end = i
            while (post_end + 1 < len(q)
                   and int(q["bin"][post_end + 1]) == int(q["bin"][post_end]) + 1):
                post_end += 1
            tail_y = y[i:post_end + 1]
            row = base_row(night, receiver, beacon)
            row.update({"spacing_ns": spacing, "boundary_min": boundary,
                        "relative_min": boundary - start_bin,
                        "contiguous_post_minutes": post_end - i + 1,
                        "shift_ns": shift, "shift_samples": shift / spacing,
                        "tail_median_shift_ns": float(
                            np.median(tail_y) - np.median(pre_y)),
                        "nearest_nonzero_multiple": nearest,
                        "distance_to_integer_samples": abs(multiple - nearest),
                        "sample_aligned": abs(multiple - nearest) <= TOL_FRAC})
            rows.append(row)
    return rows


def mark_replication(rows: list[dict]) -> None:
    for row in rows:
        matches = [other for other in rows
                   if other["spacing_ns"] == row["spacing_ns"]
                   and other["night"] == row["night"]
                   and other["beacon"] == row["beacon"]
                   and other["receiver"] != row["receiver"]
                   and abs(other["boundary_min"] - row["boundary_min"]) <= 2
                   and np.sign(other["shift_ns"]) == np.sign(row["shift_ns"])]
        row["cross_receiver_replicated"] = bool(matches)


def jump_controls(a: np.ndarray, jump_rows: list[dict]) -> list[dict]:
    """Five-minute before/after controls around primary 50 ns candidates."""
    rows = []
    primary = [r for r in jump_rows if r["spacing_ns"] == SAMPLE_NS]
    for event_id, event in enumerate(primary, 1):
        boundary = int(event["boundary_min"])
        target_beacon = int(event["beacon"][1:])
        for receiver in (0, 1):
            for beacon in (1, 2, 3):
                q = a[(a["night"] == event["night"])
                      & (a["receiver"] == receiver) & (a["beacon"] == beacon)]
                pre = q[(q["bin"] >= boundary - WINDOW_MIN)
                        & (q["bin"] < boundary)]
                post = q[(q["bin"] >= boundary)
                         & (q["bin"] < boundary + WINDOW_MIN)]
                if not len(pre) or not len(post):
                    continue
                row = {"event_id": event_id, "event_night": event["night"],
                       "event_receiver": event["receiver"],
                       "event_beacon": event["beacon"],
                       "event_relative_min": event["relative_min"],
                       "control_receiver": "s3" if receiver else "d0wd",
                       "control_beacon": f"B{beacon}",
                       "is_target_link": (receiver == (1 if event["receiver"] == "s3" else 0)
                                          and beacon == target_beacon),
                       "pre_bins": len(pre), "post_bins": len(post)}
                row["equiv_delay_shift_ns"] = float(
                    np.median(equiv_ns(post["arb"]))
                    - np.median(equiv_ns(pre["arb"])))
                row["ols_equiv_delay_shift_ns"] = float(
                    np.median(equiv_ns(post["ols"]))
                    - np.median(equiv_ns(pre["ols"])))
                for field in ("coh_arb", "rssi", "amp_med", "kp1_amp",
                              "cir_peak", "cir_rms"):
                    row[f"{field}_shift"] = float(
                        np.median(post[field]) - np.median(pre[field]))
                rows.append(row)
    return rows


def binomial_tail(n: int, k: int, p: float) -> float:
    return min(1.0, float(sum(math.comb(n, i) * p**i * (1-p)**(n-i)
                              for i in range(k, n + 1))))


def aggregate_results(scale_rows, lattice_rows, jump_rows) -> dict:
    primary_lattice = [r for r in lattice_rows if r["spacing_ns"] == SAMPLE_NS]
    primary_jumps = [r for r in jump_rows if r["spacing_ns"] == SAMPLE_NS]
    controls = {}
    for spacing in LATTICES_NS:
        lr = [r for r in lattice_rows if r["spacing_ns"] == spacing]
        jr = [r for r in jump_rows if r["spacing_ns"] == spacing]
        controls[str(spacing)] = {
            "median_holdout_on_lattice_fraction": float(np.median(
                [r["on_lattice_fraction"] for r in lr])) if lr else None,
            "multi_level_series": sum(r["multi_level_evidence"] for r in lr),
            "jump_candidates": len(jr),
            "aligned_jumps": sum(r["sample_aligned"] for r in jr),
        }
    n = len(primary_jumps)
    k = sum(r["sample_aligned"] for r in primary_jumps)
    return {
        "input_frame_contributions": int(sum(r["frames"] for r in scale_rows
                                              if r["scale_s"] == 1)),
        "series_at_60s": len(primary_lattice),
        "sample_period_ns": SAMPLE_NS,
        "slope_per_sample_rad_per_subcarrier": SLOPE_PER_SAMPLE,
        "primary_holdout_multi_level_series": sum(
            r["multi_level_evidence"] for r in primary_lattice),
        "primary_jump_candidates": n,
        "primary_aligned_jumps": k,
        "primary_alignment_fraction": k / n if n else None,
        "descriptive_binomial_tail_p": binomial_tail(n, k, 0.20) if n else None,
        "primary_cross_receiver_replicated_jumps": sum(
            r["cross_receiver_replicated"] for r in primary_jumps),
        "spacing_controls": controls,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--multiscale", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root, out = Path(args.multiscale), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    scale_rows = scale_summaries(root)
    minute = load_scale(root, 60)
    lattice_rows = lattice_holdout(minute)
    jump_rows = []
    for spacing in LATTICES_NS:
        jump_rows.extend(jump_candidates(minute, spacing))
    mark_replication(jump_rows)
    control_rows = jump_controls(minute, jump_rows)
    summary = aggregate_results(scale_rows, lattice_rows, jump_rows)

    write_csv(out / "equivalent_delay_scale_summary.csv", scale_rows)
    write_csv(out / "lattice_holdout.csv", lattice_rows)
    write_csv(out / "persistent_jumps.csv", jump_rows)
    write_csv(out / "jump_controls.csv", control_rows)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
