#!/usr/bin/env python3
"""Dump every accepted window's (ts_pc, cfo, sfo) per source to .npz.

Uses the project's own pipeline unchanged; only persistence is new. With the
per-window values on disk, split-half tests, autocorrelation, block bootstraps
and any other follow-up cost nothing.
"""
import argparse, os, sys
import numpy as np
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rff_offline import collect_observations

ap = argparse.ArgumentParser()
ap.add_argument("csv"); ap.add_argument("--after", type=float)
ap.add_argument("--before", type=float); ap.add_argument("--tag", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

by_mac = collect_observations([a.csv], 64, None, after=a.after, before=a.before)
d = {}
for m, obs in by_mac.items():
    rows = [(o["ts_pc"], o.get("cfo"), o.get("sfo")) for o in obs
            if o.get("cfo") is not None and o.get("sfo") is not None]
    if rows:
        d[m] = np.array(rows, dtype=np.float64)
np.savez_compressed(a.out, **d)
print(f"{a.tag}: {len(d)} sources, " +
      ", ".join(f"{m[-8:]}={len(v)}" for m, v in sorted(d.items())))
