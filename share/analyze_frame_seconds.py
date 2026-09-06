#!/usr/bin/env python3
"""Analyze one-second beacon telemetry emitted by frame_deep_dive.py."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np


BEACONS = ("B1", "B2", "B3")


def load(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def arrays(doc, beacon):
    nsec = int(np.floor(doc["duration_s"])) + 1
    n = np.zeros(nsec, dtype=np.int32)
    rssi = np.full(nsec, np.nan)
    for key, cell in doc["beacon_seconds"].items():
        b, sec = key.split(":")
        if b != beacon:
            continue
        sec = int(sec)
        if 0 <= sec < nsec:
            n[sec] = cell["n"]
            if cell["n"]:
                rssi[sec] = cell["rssi_sum"] / cell["n"]
    return n, rssi


def corr(a, b):
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 3 or np.std(a[mask]) == 0 or np.std(b[mask]) == 0:
        return float("nan")
    return float(np.corrcoef(a[mask], b[mask])[0, 1])


def longest_zero(n):
    best_len = best_start = 0
    start = None
    for i, v in enumerate(n):
        if v == 0 and start is None:
            start = i
        elif v != 0 and start is not None:
            if i - start > best_len:
                best_len, best_start = i - start, start
            start = None
    if start is not None and len(n) - start > best_len:
        best_len, best_start = len(n) - start, start
    return best_start, best_len


def q(a, ps):
    return np.percentile(a, ps).tolist() if len(a) else [float("nan")] * len(ps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    args = ap.parse_args()
    docs = [load(p) for p in sorted(Path(args.root).glob("*.census.json.gz"))]
    by_stamp = {}
    for d in docs:
        rx, stamp_csv = d["file"].split("_", 1)
        stamp = stamp_csv[:-4]
        by_stamp.setdefault(stamp, {})[rx] = d
        print(f"\n{d['file']}")
        aa = {}
        for b in BEACONS:
            n, rssi = arrays(d, b); aa[b] = n
            active = n[n > 0]
            rs = rssi[np.isfinite(rssi)]
            zs, zl = longest_zero(n)
            p10, med, p90 = q(active, [10, 50, 90])
            print(f"  {b}: active={len(active):>6}/{len(n):<6} "
                  f"rate p10/med/p90={p10:5.1f}/{med:5.1f}/{p90:5.1f} "
                  f"rssi med={np.median(rs) if len(rs) else float('nan'):6.2f} "
                  f"corr(rate,rssi)={corr(n.astype(float),rssi):+.3f} "
                  f"longest-zero={zl}s@{zs}s last={np.flatnonzero(n)[-1] if active.size else -1}s")
        print("  rate correlations: " + ", ".join(
            f"{a}-{b}={corr(aa[a].astype(float),aa[b].astype(float)):+.3f}"
            for a, b in (("B1", "B2"), ("B1", "B3"), ("B2", "B3"))))

    print("\nCROSS-RECEIVER PER-SECOND CORRELATIONS AND YIELD RATIOS")
    for stamp, pair in sorted(by_stamp.items()):
        if set(pair) != {"d0wd", "s3"}:
            continue
        parts = []
        for b in BEACONS:
            nd, rd = arrays(pair["d0wd"], b); ns, rs = arrays(pair["s3"], b)
            z = min(len(nd), len(ns)); nd, ns = nd[:z], ns[:z]
            mask = (nd > 0) & (ns > 0)
            ratio = np.median(ns[mask] / nd[mask]) if mask.any() else float("nan")
            parts.append(f"{b}:r={corr(nd.astype(float),ns.astype(float)):+.3f},S3/D={ratio:.2f}")
        print(stamp + "  " + " | ".join(parts))


if __name__ == "__main__":
    main()
