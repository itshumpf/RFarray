#!/usr/bin/env python3
"""Compare equivalent-delay deviations with exploratory SFO-only matchups."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np


DELTA_F_HZ = 20_000_000 / 64
ENROL_MINUTES = (5, 10, 30)
DEVIATION_BINS = ((0, 5), (5, 10), (10, 25), (25, 50), (50, np.inf))


def equiv_ns(slope):
    return -np.asarray(slope, dtype=np.float64) / (2 * np.pi * DELTA_F_HZ) * 1e9


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def first_contiguous(values, n):
    values = sorted(values)
    for i in range(len(values) - n + 1):
        block = values[i:i + n]
        if block[-1] - block[0] == n - 1:
            return block
    return []


def classify(a):
    observations = []
    models = {}
    for enrol_n in ENROL_MINUTES:
        for night in range(1, 9):
            for receiver in (0, 1):
                q = a[(a["night"] == night) & (a["receiver"] == receiver)]
                maps = {b: {int(r["bin"]): r for r in q[q["beacon"] == b]}
                        for b in (1, 2, 3)}
                common = set(maps[1]) & set(maps[2]) & set(maps[3])
                enrol_bins = first_contiguous(common, enrol_n)
                if not enrol_bins:
                    continue
                templates = {b: float(np.median(
                    [equiv_ns(maps[b][t]["arb"]) for t in enrol_bins]))
                    for b in (1, 2, 3)}
                key = (enrol_n, night, receiver)
                models[key] = {"start": enrol_bins[0], "end": enrol_bins[-1],
                               "templates": templates}
                for beacon in (1, 2, 3):
                    for t, row in maps[beacon].items():
                        if t <= enrol_bins[-1]:
                            continue
                        value = float(equiv_ns(row["arb"]))
                        distance = {b: abs(value - templates[b]) for b in templates}
                        pred = min(distance, key=distance.get)
                        impostor = min(distance[b] for b in distance if b != beacon)
                        observations.append({
                            "enrol_minutes": enrol_n, "night": night,
                            "receiver": "s3" if receiver else "d0wd",
                            "beacon": f"B{beacon}", "bin": t,
                            "relative_min": t - enrol_bins[0],
                            "equiv_delay_ns": value,
                            "enrolled_own_ns": templates[beacon],
                            "own_deviation_ns": distance[beacon],
                            "nearest_impostor_distance_ns": impostor,
                            "own_margin_ns": impostor - distance[beacon],
                            "prediction": f"B{pred}",
                            "correct": pred == beacon,
                        })
    return observations, models


def deviation_summary(observations):
    rows = []
    for enrol_n in ENROL_MINUTES:
        q = [r for r in observations if r["enrol_minutes"] == enrol_n]
        for lo, hi in DEVIATION_BINS:
            z = [r for r in q if lo <= r["own_deviation_ns"] < hi]
            rows.append({"enrol_minutes": enrol_n,
                         "deviation_band_ns": f"{lo:g}-{hi:g}" if np.isfinite(hi)
                         else f">={lo:g}",
                         "observations": len(z),
                         "fraction_of_tests": len(z) / len(q) if q else np.nan,
                         "accuracy": np.mean([r["correct"] for r in z]) if z else np.nan,
                         "wrong_identity_fraction": np.mean(
                             [not r["correct"] for r in z]) if z else np.nan,
                         "median_own_margin_ns": np.median(
                             [r["own_margin_ns"] for r in z]) if z else np.nan})
    return rows


def event_summary(observations, models, jump_path):
    with jump_path.open(newline="", encoding="utf-8") as fh:
        events = [r for r in csv.DictReader(fh) if float(r["spacing_ns"]) == 50.0]
    rows = []
    for event_id, event in enumerate(events, 1):
        receiver_num = 1 if event["receiver"] == "s3" else 0
        boundary = int(event["boundary_min"])
        for enrol_n in ENROL_MINUTES:
            model = models.get((enrol_n, int(event["night"]), receiver_num))
            if not model:
                continue
            q = [r for r in observations
                 if r["enrol_minutes"] == enrol_n
                 and r["night"] == int(event["night"])
                 and r["receiver"] == event["receiver"]
                 and r["beacon"] == event["beacon"]]
            for period, lo, hi in (("pre", boundary - 5, boundary),
                                   ("post", boundary, boundary + 5)):
                z = [r for r in q if lo <= r["bin"] < hi]
                if not z:
                    continue
                predictions = Counter(r["prediction"] for r in z)
                rows.append({"event_id": event_id,
                             "night": int(event["night"]),
                             "receiver": event["receiver"],
                             "beacon": event["beacon"],
                             "event_relative_min": event["relative_min"],
                             "enrol_minutes": enrol_n, "period": period,
                             "observations": len(z),
                             "accuracy": float(np.mean([r["correct"] for r in z])),
                             "median_own_deviation_ns": float(np.median(
                                 [r["own_deviation_ns"] for r in z])),
                             "median_own_margin_ns": float(np.median(
                                 [r["own_margin_ns"] for r in z])),
                             "predictions_json": json.dumps(predictions,
                                                             sort_keys=True)})
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minute", required=True)
    parser.add_argument("--jumps", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    paths = sorted(Path(args.minute).glob("*.60s.npy"))
    a = np.concatenate([np.load(path) for path in paths])
    observations, models = classify(a)
    summary = deviation_summary(observations)
    events = event_summary(observations, models, Path(args.jumps))
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "sfo_match_observations.csv", observations)
    write_csv(out / "sfo_match_by_deviation.csv", summary)
    write_csv(out / "sfo_match_event_windows.csv", events)
    result = {"minute_observations": len(observations),
              "models": len(models), "deviation_rows": summary,
              "event_rows": events}
    (out / "sfo_match_summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"minute_observations": len(observations),
                      "models": len(models), "event_rows": len(events)}, indent=2))


if __name__ == "__main__":
    main()
