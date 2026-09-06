#!/usr/bin/env python3
"""Strict conservation and source-signature audit for the full replay."""

import argparse
import json
from pathlib import Path

import numpy as np


EXPECTED_FILES = 16
EXPECTED_ROWS = 69_688_145


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--replay",required=True)
    ap.add_argument("--multiscale",required=True); ap.add_argument("--out",required=True)
    a=ap.parse_args(); replay=Path(a.replay); multi=Path(a.multiscale)
    metas=sorted(replay.glob("*.meta.json")); errors=[]; files=[]
    if len(metas)!=EXPECTED_FILES: errors.append(f"replay meta count {len(metas)} != {EXPECTED_FILES}")
    total_rows=total_frames=total_corrupt=total_bad=0
    for p in metas:
        m=json.loads(p.read_text(encoding="utf-8")); stem=p.name[:-10]
        source=Path(m["source"]); st=source.stat()
        if not m.get("complete"): errors.append(f"{stem}: incomplete")
        if st.st_size!=m["source_size"] or st.st_mtime_ns!=m["source_mtime_ns"]:
            errors.append(f"{stem}: source signature changed")
        n=0
        for c in m["chunks"]:
            q=replay/c["name"]
            if not q.exists(): errors.append(f"{stem}: missing {q.name}"); continue
            z=np.load(q,mmap_mode="r"); n+=len(z)
            if len(z)!=c["frames"]: errors.append(f"{stem}: chunk length mismatch {q.name}")
        if n!=m["written_frames"]: errors.append(f"{stem}: chunk sum {n} != {m['written_frames']}")
        mp=multi/f"{stem}.meta.json"
        if not mp.exists(): errors.append(f"{stem}: missing multiscale meta")
        else:
            mm=json.loads(mp.read_text(encoding="utf-8"))
            if mm["source_frames"]!=n: errors.append(f"{stem}: multiscale source count mismatch")
            for o in mm["outputs"]:
                z=np.load(multi/o["name"],mmap_mode="r")
                if len(z)!=o["rows"]: errors.append(f"{stem}: multiscale row mismatch {o['name']}")
                if int(z["count"].sum())!=n: errors.append(f"{stem}: frame conservation failed {o['scale_s']}s")
        total_rows+=m["rows"]; total_frames+=n; total_corrupt+=m["corrupt_union"]
        total_bad+=m["bad_csi"]
        files.append({"stem":stem,"rows":m["rows"],"frames":n,
                      "corrupt":m["corrupt_union"],"bad_csi":m["bad_csi"]})
    if total_rows!=EXPECTED_ROWS: errors.append(f"row sum {total_rows} != {EXPECTED_ROWS}")
    result={"valid":not errors,"expected_files":EXPECTED_FILES,"files":len(metas),
            "expected_rows":EXPECTED_ROWS,"rows":total_rows,"beacon_frames":total_frames,
            "corrupt_union_all_rows":total_corrupt,"bad_csi":total_bad,
            "errors":errors,"file_detail":files}
    Path(a.out).write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="file_detail"},indent=2))
    if errors: raise SystemExit(1)


if __name__=="__main__": main()
