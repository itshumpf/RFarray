#!/usr/bin/env python3
"""Summarize frame_deep_dive.py census artifacts."""

import argparse
import csv
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path


BEACONS = {
    "a4:f0:0f:77:91:20": "B1",
    "28:05:a5:2f:fa:48": "B2",
    "f4:2d:c9:70:72:30": "B3",
}


def load_all(root):
    out = []
    for path in sorted(Path(root).glob("*.census.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            out.append(json.load(f))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--csv")
    args = ap.parse_args()
    docs = load_all(args.root)
    rows = []
    grand = Counter()
    receiver_rows = Counter()
    beacon_rows = Counter()
    for d in docs:
        counts = d["mac_counts"]
        beacons = {b: counts.get(mac, 0) for mac, b in BEACONS.items()}
        nonempty_labels = sum(v for k, v in d["label_counts"].items() if k)
        row = {
            "file": d["file"],
            "receiver": d["file"].split("_", 1)[0],
            "stamp": d["file"].split("_", 1)[1][:-4],
            "rows": d["rows"],
            "duration_s": d.get("duration_s"),
            "B1": beacons["B1"], "B2": beacons["B2"], "B3": beacons["B3"],
            "ambient": d["rows"] - sum(beacons.values()),
            "distinct_macs": len(counts),
            "bad_columns": d["bad_column_count"],
            "bad_integers": d["bad_integer_parse"],
            "bad_mac": d["bad_mac"],
            "csi_width_mismatch": d["csi_width_mismatch"],
            "field_implausible": d["field_implausible"],
            "pc_backsteps": d["pc_backsteps"],
            "pc_dt_max_us": d["pc_dt_max_us"],
            "esp_wraps": d["esp_wraps"],
            "esp_backsteps": d["esp_backsteps_nonwrap"],
            "drop_change_rows": d["drop_change_rows"],
            "drop_large_jumps": d["drop_large_jumps_gt100"],
            "nonempty_labels": nonempty_labels,
        }
        rows.append(row)
        grand.update({k: row[k] for k in (
            "rows", "ambient", "bad_columns", "bad_integers", "bad_mac",
            "csi_width_mismatch", "field_implausible", "pc_backsteps",
            "esp_wraps", "esp_backsteps", "drop_change_rows",
            "drop_large_jumps", "nonempty_labels")})
        receiver_rows[row["receiver"]] += row["rows"]
        for b in ("B1", "B2", "B3"):
            beacon_rows[(row["receiver"], b)] += row[b]

    fields = list(rows[0]) if rows else []
    if args.csv and rows:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader(); w.writerows(rows)

    for r in rows:
        print(f"{r['file']:<29} rows={r['rows']:>9,} "
              f"dur={r['duration_s']/3600:>5.2f}h "
              f"B1={r['B1']:>9,} B2={r['B2']:>9,} B3={r['B3']:>9,} "
              f"ambient={r['ambient']:>6,} macs={r['distinct_macs']:>3} "
              f"bad={r['bad_columns']+r['bad_integers']:>3} "
              f"width={r['csi_width_mismatch']:>3} field={r['field_implausible']:>4} "
              f"pcback={r['pc_backsteps']:>3} espback={r['esp_backsteps']:>3}")
    print(f"\nTOTAL rows={grand['rows']:,} ambient={grand['ambient']:,} "
          f"parse_bad={grand['bad_columns']+grand['bad_integers']:,} "
          f"width_mismatch={grand['csi_width_mismatch']:,} "
          f"field_implausible={grand['field_implausible']:,} "
          f"pc_backsteps={grand['pc_backsteps']:,} "
          f"esp_backsteps={grand['esp_backsteps']:,} "
          f"nonempty_labels={grand['nonempty_labels']:,}")
    print("receiver rows:", dict(receiver_rows))
    print("beacon rows:", {f"{rx}/{b}": n for (rx, b), n in beacon_rows.items()})

    print("\nSEQUENCE TRANSITIONS")
    for d in docs:
        parts = []
        for mac, beacon in BEACONS.items():
            q = d["sequence"].get(mac, {})
            parts.append(
                f"{beacon}:same={q.get('same',0):,},+1={q.get('forward_one',0):,},"
                f"skip={q.get('forward_other',0):,},back={q.get('back_or_large',0):,}")
        print(f"{d['file']}: " + " | ".join(parts))


if __name__ == "__main__":
    main()
