#!/usr/bin/env python3
"""Stream every replayed frame through held-out equivalent-delay lattices."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np


DELTA_F_HZ = 20_000_000 / 64
SPACINGS_NS = (50.0, 40.0, 45.0, 55.0, 60.0)
TOL_FRAC = 0.10


def equiv_ns(slope):
    return -np.asarray(slope, dtype=np.float64) / (2 * np.pi * DELTA_F_HZ) * 1e9


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    replay, out = Path(args.replay), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    input_frames = 0

    for meta_path in sorted(replay.glob("*.meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not meta.get("complete"):
            continue
        input_frames += int(meta["written_frames"])
        stem = meta_path.name[:-10]
        receiver = "s3" if stem.startswith("s3_") else "d0wd"
        stamp = stem.split("_", 1)[1]
        midpoint = (int(meta["origin_pc_us"]) + int(meta["last_pc_us"])) // 2
        paths = [replay / item["name"] for item in meta["chunks"]]

        sums = {(b, s): 0j for b in (1, 2, 3) for s in SPACINGS_NS}
        train_n = Counter()
        for path in paths:
            a = np.load(path, mmap_mode="r")
            train = a[a["pc_us"] < midpoint]
            for beacon in (1, 2, 3):
                y = equiv_ns(train["arb"][train["beacon"] == beacon])
                train_n[beacon] += len(y)
                for spacing in SPACINGS_NS:
                    sums[(beacon, spacing)] += np.exp(
                        1j * 2 * np.pi * y / spacing).sum()

        origins = {(b, s): float(np.angle(sums[(b, s)]) * s / (2 * np.pi))
                   for b in (1, 2, 3) for s in SPACINGS_NS}
        test_n = Counter()
        on_n = Counter()
        levels = {(b, s): Counter() for b in (1, 2, 3) for s in SPACINGS_NS}

        for path in paths:
            a = np.load(path, mmap_mode="r")
            test = a[a["pc_us"] >= midpoint]
            for beacon in (1, 2, 3):
                y = equiv_ns(test["arb"][test["beacon"] == beacon])
                test_n[beacon] += len(y)
                for spacing in SPACINGS_NS:
                    origin = origins[(beacon, spacing)]
                    z = (y - origin) / spacing
                    nearest = np.rint(z)
                    mask = np.abs(z - nearest) <= TOL_FRAC
                    on_n[(beacon, spacing)] += int(mask.sum())
                    values, counts = np.unique(nearest[mask].astype(np.int32),
                                               return_counts=True)
                    levels[(beacon, spacing)].update(
                        {int(v): int(n) for v, n in zip(values, counts)})

        for beacon in (1, 2, 3):
            if not test_n[beacon]:
                continue
            for spacing in SPACINGS_NS:
                counts = levels[(beacon, spacing)]
                material = sum(n >= 0.05 * test_n[beacon] for n in counts.values())
                rows.append({"stamp": stamp, "receiver": receiver,
                             "beacon": f"B{beacon}", "spacing_ns": spacing,
                             "train_frames": train_n[beacon],
                             "test_frames": test_n[beacon],
                             "origin_ns": origins[(beacon, spacing)],
                             "on_lattice_frames": on_n[(beacon, spacing)],
                             "on_lattice_fraction": (
                                 on_n[(beacon, spacing)] / test_n[beacon]),
                             "occupied_levels": len(counts),
                             "material_levels": material,
                             "multi_level_evidence": material >= 2})
        print(f"done {stem}: {sum(train_n.values()) + sum(test_n.values()):,} frames",
              flush=True)

    fields = list(rows[0])
    with (out / "frame_lattice_holdout.csv").open(
            "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summary = {"input_frames_processed": input_frames,
               "heldout_frames_scored_once_per_spacing": sum(
                   r["test_frames"] for r in rows if r["spacing_ns"] == 50.0),
               "series": sum(r["spacing_ns"] == 50.0 for r in rows),
               "spacings": {}}
    for spacing in SPACINGS_NS:
        q = [r for r in rows if r["spacing_ns"] == spacing]
        summary["spacings"][str(spacing)] = {
            "median_on_lattice_fraction": float(np.median(
                [r["on_lattice_fraction"] for r in q])),
            "min_on_lattice_fraction": float(min(
                r["on_lattice_fraction"] for r in q)),
            "max_on_lattice_fraction": float(max(
                r["on_lattice_fraction"] for r in q)),
            "multi_level_series": sum(r["multi_level_evidence"] for r in q),
        }
    (out / "frame_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
