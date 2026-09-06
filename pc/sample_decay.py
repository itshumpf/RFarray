#!/usr/bin/env python3
"""One sample point: 500 s lead-in + 300 s measured, median per source.

The lead-in method is the one validated in SEVEN_NIGHT_REREAD sec.9A against
sec.10's table on 40 of 40 cells. Pipeline imported from rff_offline unchanged.
"""
import argparse, json, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rff_offline as RO
ap = argparse.ArgumentParser()
ap.add_argument("csv"); ap.add_argument("--after", type=float)
ap.add_argument("--before", type=float); ap.add_argument("--tag", required=True)
ap.add_argument("--t", type=float, required=True)   # absolute centre-start, s
a = ap.parse_args()
by = RO.collect_observations([a.csv], 64, None, after=a.after, before=a.before)
out = {}
for m, obs in by.items():
    v = np.array([o["sfo"] for o in obs if o.get("sfo") is not None])
    c = np.array([o["cfo"] for o in obs if o.get("cfo") is not None])
    if len(v) < 8: continue
    out[m] = dict(n=len(v), sfo=float(np.median(v)),
                  sfo_iqr=float(np.subtract(*np.percentile(v, [75, 25]))),
                  cfo=float(np.median(c)) if len(c) else None)
print("JSON " + json.dumps(dict(tag=a.tag, t=a.t, src=out), sort_keys=True))
