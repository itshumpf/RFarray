#!/usr/bin/env python3
"""Extract contiguous label intervals without parsing CSI payload values."""

import argparse
import csv
import json
from pathlib import Path


def scan(path):
    intervals = []
    first_pc = last_pc = start_pc = None
    current = None
    rows = count = 0
    with path.open("r", newline="", errors="replace") as f:
        for row in csv.DictReader(f):
            rows += 1
            try: pc = int(row["pc_time_us"])
            except (ValueError, KeyError): continue
            label = row.get("label", "")
            if first_pc is None: first_pc = pc
            last_pc = pc
            if current is None:
                current, start_pc, count = label, pc, 1
            elif label == current:
                count += 1
            else:
                intervals.append({"label": current, "start_s": (start_pc-first_pc)/1e6,
                                  "end_s": (pc-first_pc)/1e6, "rows": count})
                current, start_pc, count = label, pc, 1
    if current is not None:
        intervals.append({"label": current, "start_s": (start_pc-first_pc)/1e6,
                          "end_s": (last_pc-first_pc)/1e6, "rows": count})
    return {"file": path.name, "rows": rows, "intervals": intervals}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("paths", nargs="+"); ap.add_argument("--out", required=True)
    args = ap.parse_args(); out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    for raw in args.paths:
        path = Path(raw); result = scan(path)
        dest = out / f"{path.stem}.labels.json"
        dest.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(path.name, f"rows={result['rows']:,}")
        for x in result["intervals"]:
            print(f"  {x['start_s']:9.3f}..{x['end_s']:9.3f}s rows={x['rows']:>9,} label={x['label']!r}")


if __name__ == "__main__": main()
