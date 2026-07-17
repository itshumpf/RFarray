#!/usr/bin/env python3
r"""Survey raw capture CSVs for occupancy-sensing suitability.

Streams each file cheaply (no CSI parse — just timestamp + MAC columns)
and reports, per session: wall-clock span, per-source frame counts and
effective rates, and dead-air gaps on the beacon links. This answers
"which sessions can carry motion/respiration analysis" before any heavy
signal processing runs.

Usage:
  python pc\occ_survey.py data\raw\rx_*.csv
"""
import argparse
import glob
import os
import sys
import time
from collections import defaultdict

BEACONS = {
    "a4:f0:0f:77:91:20": "B1(ref/wall)",
    "28:05:a5:2f:fa:48": "B2",
    "f4:2d:c9:70:72:30": "B3",
}
GAP_S = 2.0          # dead-air threshold on a beacon link


def survey(path):
    per_mac = defaultdict(int)
    t0 = t1 = None
    # per-beacon gap tracking on pc_time
    last_seen = {}
    gaps = defaultdict(list)
    n_rows = 0
    with open(path, "r", newline="") as f:
        header = f.readline().strip().split(",")
        try:
            i_t = header.index("pc_time_us")
            i_mac = header.index("mac")
        except ValueError:
            print(f"  {os.path.basename(path)}: unrecognized header, skipped")
            return
        for line in f:
            parts = line.split(",", 4)
            if len(parts) < 5:
                continue
            try:
                t = int(parts[i_t]) * 1e-6
            except ValueError:
                continue
            mac = parts[i_mac].lower()
            n_rows += 1
            per_mac[mac] += 1
            if t0 is None:
                t0 = t
            t1 = t
            if mac in BEACONS:
                prev = last_seen.get(mac)
                if prev is not None and t - prev > GAP_S:
                    gaps[mac].append((prev, t - prev))
                last_seen[mac] = t

    if not n_rows or t0 is None:
        print(f"  {os.path.basename(path)}: empty")
        return
    span = t1 - t0
    print(f"\n{os.path.basename(path)}")
    print(f"  span {span/3600:.2f} h   "
          f"({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t0))} -> "
          f"{time.strftime('%H:%M:%S', time.localtime(t1))})   "
          f"{n_rows:,} frames total")
    top = sorted(per_mac.items(), key=lambda kv: -kv[1])
    for mac, n in top[:8]:
        tag = BEACONS.get(mac, "ambient")
        rate = n / span if span > 0 else 0
        line = f"    {mac}  {tag:<12} {n:>9,} fr  {rate:6.1f} fps"
        if mac in BEACONS:
            g = gaps[mac]
            worst = max((d for _, d in g), default=0.0)
            line += f"   gaps>{GAP_S:.0f}s: {len(g)}"
            if g:
                line += f" (worst {worst:.0f}s)"
        print(line)
    others = len(per_mac) - min(8, len(per_mac))
    if others > 0:
        print(f"    ... plus {others} more ambient sources")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csvs", nargs="+")
    args = ap.parse_args()
    paths = []
    for pat in args.csvs:
        paths.extend(glob.glob(pat))
    if not paths:
        print("no files matched", file=sys.stderr)
        return 1
    for p in sorted(paths):
        mtime = os.path.getmtime(p)
        age_h = (time.time() - mtime) / 3600
        sz = os.path.getsize(p) / 1e6
        print(f"[{os.path.basename(p)}: {sz:,.0f} MB, mtime "
              f"{time.strftime('%m-%d %H:%M', time.localtime(mtime))} "
              f"({age_h:.1f} h ago)]")
        survey(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
