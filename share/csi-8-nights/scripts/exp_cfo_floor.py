#!/usr/bin/env python3
"""Per-source CFO/SFO at full precision, plus the pooled covariance that
P1's sigma is actually measured in. Imports the project's own pipeline --
no DSP is reimplemented here.

Usage: cfo_floor.py SLICE.csv --after A --before B --tag NAME
"""
import argparse, json, sys
import numpy as np
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rff_offline import collect_observations, feature, TRAIN_FRACTION
from rff.discriminator import Discriminator

ap = argparse.ArgumentParser()
ap.add_argument("csv"); ap.add_argument("--after", type=float)
ap.add_argument("--before", type=float); ap.add_argument("--tag", default="")
ap.add_argument("--min-windows", type=int, default=4)
a = ap.parse_args()

by_mac = collect_observations([a.csv], 64, None, after=a.after, before=a.before)
macs = sorted(m for m, o in by_mac.items() if len(o) >= a.min_windows)
dropped = {m: len(by_mac[m]) for m in by_mac if m not in macs}

rows = {}
disc = Discriminator()
for m in macs:
    feats = [f for f in (feature(o, False) for o in by_mac[m]) if f is not None]
    arr = np.array(feats)
    cut = max(int(len(feats) * TRAIN_FRACTION), 1)
    for f in feats[:cut]:
        disc.learn(m, f)
    q = lambda c: float(np.subtract(*np.percentile(arr[:, c], [75, 25])))
    rows[m] = dict(windows=len(feats),
                   cfo_med=float(np.median(arr[:, 0])), cfo_iqr=q(0),
                   cfo_sd=float(arr[:, 0].std(ddof=1)),
                   sfo_med=float(np.median(arr[:, 1])), sfo_iqr=q(1),
                   sfo_sd=float(arr[:, 1].std(ddof=1)))

# the pooled covariance separation_matrix() builds, reproduced exactly
ids = [s for s, mo in disc.models.items() if mo.n >= disc.MIN_CHARACTERIZED]
pooled, dof = np.zeros((2, 2)), 0
for s in ids:
    mo = disc.models[s]; pooled += mo.cov * (mo.n - 1); dof += mo.n - 1
if dof: pooled /= dof
_, sep = disc.separation_matrix()
pairs = {f"{ids[i][-8:]}|{ids[j][-8:]}": float(sep[i][j])
         for i in range(len(ids)) for j in range(i + 1, len(ids))}

print("JSON " + json.dumps(dict(
    tag=a.tag, sources=rows, dropped_lt_minwindows=dropped,
    in_pool=[i for i in ids], n_in_pool=len(ids),
    pooled_cov=pooled.tolist(),
    pooled_sd_cfo=float(np.sqrt(pooled[0, 0])),
    pooled_sd_sfo=float(np.sqrt(pooled[1, 1])),
    pairs_sigma=pairs), sort_keys=True))
