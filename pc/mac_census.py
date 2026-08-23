#!/usr/bin/env python3
r"""Cross-session MAC census: every distinct transmitter this array has
ever captured, across every raw session file -- not just the handful of
MACs previous analyses happened to focus on.

Answers a basic, previously-unasked question: out of everything this
array could see, how many distinct devices actually showed up, how much
each talked, and how many separate session files each persisted across
(a real recurring device looks very different from a MAC that drifted
through once and never came back).

Cheap by design: counts frames per MAC via CSV field access only, no
CSI amplitude parsing -- this is a survey, not per-source
characterization (that's rff_offline.py's job, run afterward on
whatever candidates this turns up).

Usage:
  python pc\mac_census.py "data\raw\*.csv"
  python pc\mac_census.py "data\raw\*.csv" --min-frames 20 --top 80
"""
import argparse
import csv
import glob
import os
import sys
import time
from collections import defaultdict

from occ import BEACON_MACS


def is_locally_administered(mac):
    try:
        first_octet = int(mac.split(":")[0], 16)
    except (ValueError, IndexError):
        return None
    return bool(first_octet & 0x02)


def census_file(path, counts, sessions):
    n_rows = 0
    seen_here = set()
    with open(path, newline="", errors="replace") as f:
        r = csv.reader(f)
        header = next(r, None)
        if header is None or "mac" not in header:
            return 0
        i_mac = header.index("mac")
        for row in r:
            if len(row) <= i_mac:
                continue
            m = row[i_mac].lower()
            counts[m] += 1
            seen_here.add(m)
            n_rows += 1
    for m in seen_here:
        sessions[m].add(os.path.basename(path))
    return n_rows


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csvs", nargs="+")
    ap.add_argument("--min-frames", type=int, default=5)
    ap.add_argument("--top", type=int, default=80)
    args = ap.parse_args()

    paths = sorted({p for pat in args.csvs for p in glob.glob(pat)})
    paths = [p for p in paths if os.path.getsize(p) > 0]
    print(f"scanning {len(paths)} non-empty file(s)...", file=sys.stderr)

    counts = defaultdict(int)
    sessions = defaultdict(set)
    t0 = time.time()
    total_rows = 0
    for i, p in enumerate(paths):
        n = census_file(p, counts, sessions)
        total_rows += n
        print(f"  [{i+1}/{len(paths)}] {os.path.basename(p)}: {n:,} rows "
              f"({time.time()-t0:.0f}s elapsed)", file=sys.stderr)

    print(f"\n{len(counts)} distinct MAC(s) seen across {total_rows:,} total "
          f"rows, {len(paths)} files, in {time.time()-t0:.0f}s\n")

    rows = sorted(counts.items(), key=lambda kv: -kv[1])
    print(f"{'mac':<18} {'frames':>10} {'sessions':>9} {'kind':<10} role")
    for m, c in rows:
        if c < args.min_frames:
            break
        la = is_locally_administered(m)
        kind = "beacon" if m in BEACON_MACS else \
               ("private" if la else "real-OUI")
        role = BEACON_MACS.get(m, "")
        print(f"{m:<18} {c:>10,} {len(sessions[m]):>9} {kind:<10} {role}")

    n_over = sum(1 for _, c in rows if c >= args.min_frames)
    print(f"\n{n_over} MAC(s) with >= {args.min_frames} frames "
          f"(of {len(rows)} total distinct MACs ever seen)")


if __name__ == "__main__":
    sys.exit(main())
