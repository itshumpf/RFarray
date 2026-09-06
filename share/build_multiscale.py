#!/usr/bin/env python3
"""Build exact robust time-bin summaries from full arbiter replay chunks."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np


SCALES = (1, 10, 60, 300)
OUT_DTYPE = np.dtype([
    ("receiver", "u1"), ("night", "u1"), ("beacon", "u1"),
    ("scale_s", "<u2"), ("bin", "<i8"), ("count", "<u4"),
    ("arb", "<f4"), ("arb_iqr", "<f4"), ("ols", "<f4"),
    ("coh_arb", "<f4"), ("rssi", "<f4"), ("amp_med", "<f4"),
    ("kp1_amp", "<f4"), ("cir_peak", "<f4"), ("cir_rms", "<f4"),
])
STAMPS = ["20260829_025355", "20260830_013943", "20260831_020408",
          "20260901_035805", "20260902_000949", "20260903_013851",
          "20260904_010024", "20260905_025053"]


def aggregate(a, scale, receiver, night):
    rows = []
    div = int(scale * 1_000_000)
    for beacon in (1, 2, 3):
        q = a[a["beacon"] == beacon]
        if not len(q): continue
        bins = q["pc_us"] // div
        cuts = np.r_[0, np.flatnonzero(np.diff(bins)) + 1, len(q)]
        for lo, hi in zip(cuts[:-1], cuts[1:]):
            z = q[lo:hi]; slopes = z["arb"].astype(np.float64)
            rows.append((receiver, night, beacon, scale, int(bins[lo]), len(z),
                         np.median(slopes), np.subtract(*np.percentile(slopes, [75, 25])),
                         np.median(z["ols"]), np.median(z["coh_arb"]),
                         np.median(z["rssi"]), np.median(z["amp_med"]),
                         np.median(z["kp1_amp"]), np.median(z["cir_peak"]),
                         np.median(z["cir_rms"])))
    out = np.array(rows, dtype=OUT_DTYPE)
    return out[np.lexsort((out["beacon"], out["bin"]))]


def build(meta_path, replay_dir, outdir):
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not meta.get("complete"): return
    stem = meta_path.name[:-10]  # remove .meta.json
    rx = 1 if stem.startswith("s3_") else 0
    stamp = stem.split("_", 1)[1]; night = STAMPS.index(stamp) + 1
    chunks = [replay_dir / d["name"] for d in meta["chunks"]]
    a = np.concatenate([np.load(p, mmap_mode="r") for p in chunks])
    outdir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    outputs = []
    for scale in SCALES:
        dest = outdir / f"{stem}.{scale}s.npy"
        tmp = outdir / f"{stem}.{scale}s.tmp.npy"
        x = aggregate(a, scale, rx, night)
        np.save(tmp, x, allow_pickle=False); os.replace(tmp, dest)
        outputs.append({"scale_s": scale, "rows": len(x), "name": dest.name})
    m = {"source_meta": str(meta_path.resolve()), "source_frames": len(a),
         "receiver": "s3" if rx else "d0wd", "night": night, "stamp": stamp,
         "outputs": outputs, "wall_s": time.time()-started, "complete": True}
    (outdir / f"{stem}.meta.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    print(f"done {stem}: {len(a):,} frames, {m['wall_s']:.1f}s", flush=True)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--replay", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--stems", nargs="*")
    a = ap.parse_args(); replay, out = Path(a.replay), Path(a.out)
    metas = sorted(replay.glob("*.meta.json"))
    if a.stems: metas = [p for p in metas if p.name[:-10] in set(a.stems)]
    for p in metas: build(p, replay, out)


if __name__ == "__main__": main()
