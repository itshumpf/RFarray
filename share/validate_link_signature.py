#!/usr/bin/env python3
"""Structural and numerical audit of the link-signature result bundle."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


EXPECTED_ROWS = {
    "support.csv": 72,
    "same_receiver_identification.csv": 144,
    "paired_receiver_fusion.csv": 216,
    "claimed_link_verification.csv": 48,
    "receiver_invariance.csv": 96,
    "exploratory_night_transfer.csv": 384,
    "exploratory_early_late.csv": 72,
    "exploratory_feature_receiver_transfer.csv": 256,
}


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="deep_dive/link_signature")
    ap.add_argument("--out", default="deep_dive/LINK_SIGNATURE_VALIDATION.json")
    args = ap.parse_args(); root = Path(args.results)
    errors, counts = [], {}
    for name, expected in EXPECTED_ROWS.items():
        path = root / name
        if not path.exists():
            errors.append(f"missing {name}"); continue
        rows = read_csv(path); counts[name] = len(rows)
        if len(rows) != expected:
            errors.append(f"{name}: expected {expected} rows, got {len(rows)}")
        for row_i, row in enumerate(rows, 2):
            for field, value in row.items():
                bounded_metric = (field.endswith("accuracy") or field in
                                  {"auc", "eer", "macro_auc", "macro_eer"})
                if bounded_metric:
                    try: x = float(value)
                    except ValueError:
                        errors.append(f"{name}:{row_i} invalid {field}"); continue
                    if not np.isfinite(x) or not 0 <= x <= 1:
                        errors.append(f"{name}:{row_i} out-of-range {field}={value}")
    summary_path = root / "summary.json"
    if not summary_path.exists():
        errors.append("missing summary.json")
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("passes", {}).get("spoof_resistance_tested") is not False:
            errors.append("claim boundary missing: spoof_resistance_tested must be false")
    if (root / "support.csv").exists():
        support = read_csv(root / "support.csv")
        if any(int(r["complete_bins_per_class"]) <= 0 for r in support):
            errors.append("one or more receiver-night supports are empty")
    result = {"valid": not errors, "expected_files": len(EXPECTED_ROWS) + 1,
              "row_counts": counts, "errors": errors}
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
