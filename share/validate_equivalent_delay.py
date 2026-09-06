#!/usr/bin/env python3
"""Validate the fixed eight-night equivalent-delay output invariants."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "deep_dive" / "equivalent_delay"
EXPECTED_FRAMES = 69_510_186


def read_csv(name):
    with (ROOT / name).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    aggregate = json.loads((ROOT / "summary.json").read_text(encoding="utf-8"))
    frames = json.loads((ROOT / "frame_summary.json").read_text(encoding="utf-8"))
    scale = read_csv("equivalent_delay_scale_summary.csv")
    lattice = read_csv("lattice_holdout.csv")
    frame_lattice = read_csv("frame_lattice_holdout.csv")
    jumps = read_csv("persistent_jumps.csv")
    controls = read_csv("jump_controls.csv")
    match_observations = read_csv("sfo_match_observations.csv")
    match_deviation = read_csv("sfo_match_by_deviation.csv")
    match_events = read_csv("sfo_match_event_windows.csv")

    assert aggregate["input_frame_contributions"] == EXPECTED_FRAMES
    assert frames["input_frames_processed"] == EXPECTED_FRAMES
    assert len(scale) == 192
    assert len(lattice) == 240
    assert len(frame_lattice) == 230
    assert len(controls) == 18
    primary_lattice = [r for r in lattice if float(r["spacing_ns"]) == 50.0]
    primary_frames = [r for r in frame_lattice if float(r["spacing_ns"]) == 50.0]
    primary_jumps = [r for r in jumps if float(r["spacing_ns"]) == 50.0]
    assert len(primary_lattice) == 48
    assert len(primary_frames) == 46
    assert not any(r["multi_level_evidence"] == "True" for r in primary_lattice)
    assert not any(r["multi_level_evidence"] == "True" for r in primary_frames)
    assert len(primary_jumps) == 3
    assert not any(r["sample_aligned"] == "True" for r in primary_jumps)
    assert not any(r["cross_receiver_replicated"] == "True" for r in primary_jumps)
    assert {r["beacon"] for r in primary_jumps} == {"B1"}
    assert len(match_observations) == 51_635
    assert len(match_deviation) == 15
    assert len(match_events) == 15
    far = [r for r in match_deviation
           if r["deviation_band_ns"] in ("25-50", ">=50")]
    assert all(float(r["accuracy"]) == 0.0 for r in far)
    print(json.dumps({"valid": True, "input_frames": EXPECTED_FRAMES,
                      "aggregate_series": len(primary_lattice),
                      "frame_series": len(primary_frames),
                      "primary_jumps": len(primary_jumps),
                      "sfo_match_observations": len(match_observations)}, indent=2))


if __name__ == "__main__":
    main()
