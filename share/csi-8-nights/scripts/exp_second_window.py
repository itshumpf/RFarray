#!/usr/bin/env python3
"""SECOND_WINDOW_PREREG Stage 2 runner. One pass per capture.

Nothing is reimplemented: collect_observations and report come straight from
rff_offline, so DSP, gates, window size, pooled covariance and the blind
holdout split are the shipped ones. This adds full-precision medians and a
per-window dump on top of the same single pass.
"""
import argparse, io, json, os, sys, contextlib
import numpy as np
import os
R = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, R)
import rff_offline as RO

ap = argparse.ArgumentParser()
ap.add_argument("csv"); ap.add_argument("--after", type=float)
ap.add_argument("--before", type=float); ap.add_argument("--tag", required=True)
ap.add_argument("--outdir", required=True)
a = ap.parse_args()

stats = RO.FilterStats(64, RO.DEFAULT_MAX_RESID, RO.DEFAULT_MIN_INLIER,
                       a.after, a.before)
by_mac = RO.collect_observations([a.csv], 64, None, after=a.after,
                                 before=a.before, stats=stats)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    stats.report()
    res = RO.report(by_mac, 4, None, stats)
text = buf.getvalue()
os.makedirs(a.outdir, exist_ok=True)
open(os.path.join(a.outdir, a.tag + ".txt"), "w").write(text)

disc = res[0] if res else None
src, dump = {}, {}
for m, obs in by_mac.items():
    rows = [(o["ts_pc"], o.get("cfo"), o.get("sfo")) for o in obs
            if o.get("cfo") is not None and o.get("sfo") is not None]
    if len(rows) < 4: continue
    arr = np.array(rows, dtype=np.float64); dump[m] = arr
    q = lambda c: float(np.subtract(*np.percentile(arr[:, c], [75, 25])))
    src[m] = dict(windows=len(arr),
                  sfo_med=float(np.median(arr[:, 2])), sfo_iqr=q(2),
                  cfo_med=float(np.median(arr[:, 1])), cfo_iqr=q(1))
np.savez_compressed(os.path.join(a.outdir, a.tag + ".npz"), **dump)

pairs, pooled_sd = {}, None
if disc is not None:
    ids, sep = disc.separation_matrix()
    pairs = {f"{ids[i][-8:]}|{ids[j][-8:]}": float(sep[i][j])
             for i in range(len(ids)) for j in range(i + 1, len(ids))}
    P, dof = np.zeros((2, 2)), 0
    for s in ids:
        mo = disc.models[s]; P += mo.cov * (mo.n - 1); dof += mo.n - 1
    if dof: P /= dof
    pooled_sd = float(np.sqrt(P[1, 1]))
acc = [l for l in text.splitlines() if l.startswith("accuracy")]
print("JSON " + json.dumps(dict(tag=a.tag, sources=src, pairs_sigma=pairs,
      pooled_sd_sfo=pooled_sd, accuracy_line=acc[0] if acc else None,
      windows_formed=stats.windows, rej_inlier=stats.rej_inlier,
      reached_dsp=stats.reached_dsp), sort_keys=True))
