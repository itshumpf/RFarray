#!/usr/bin/env python3
"""Summarize exhaustive targeted replay arrays on common accepted frames."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

UNIT_SD = 0.00237
ESTS = ("prod", "det", "ols", "e1024", "arb")
LABEL_S = {("d0wd", "20260830_013943"): 3120.372,
           ("s3", "20260830_013943"): 3120.516}


def receiver_stamp(path):
    base = path.name.split(".frames.npz")[0]
    return tuple(base.split("_", 1))


def longest_runs(minutes):
    vals = sorted(set(int(x) for x in minutes))
    if not vals:
        return []
    out = []; a = z = vals[0]
    for x in vals[1:]:
        if x == z + 1:
            z = x
        else:
            out.append((a, z, z - a + 1)); a = z = x
    out.append((a, z, z - a + 1))
    return sorted(out, key=lambda q: (-q[2], q[0]))


def load_all(indir):
    data = {}
    for p in sorted(indir.glob("*.frames.npz")):
        rx, stamp = receiver_stamp(p)
        data[(rx, stamp)] = np.load(p)["frames"]
    return data


def estimator_summary(data):
    rows = []
    for (rx, stamp), a in sorted(data.items()):
        for b in sorted(set(a["beacon"].tolist())):
            q = a[a["beacon"] == b]; g = q[q["prod_gate"]]
            for e in ESTS:
                d = np.abs(g[e].astype(float) - g["arb"].astype(float))
                rows.append({
                    "receiver": rx, "stamp": stamp, "beacon": f"B{b}",
                    "estimator": e, "retained": len(q), "common_gated": len(g),
                    "gate_reject_frac": float(1 - len(g) / len(q)),
                    "median": float(np.median(g[e])),
                    "median_abs_from_arb": float(np.median(d)),
                    "p99_abs_from_arb": float(np.percentile(d, 99)),
                    "turnout_gt_0p05_frac": float(np.mean(d > 0.05)),
                })
            pd = np.abs(g["prod"].astype(float) - g["det"].astype(float))
            rows[-len(ESTS)]["prod_det_median_abs"] = float(np.median(pd))
            rows[-len(ESTS)]["prod_det_gt_unit_frac"] = float(np.mean(pd > UNIT_SD))
    return rows


def minute_rows(data):
    rows = []
    for (rx, stamp), a in sorted(data.items()):
        a = a[a["prod_gate"]]
        am = a["pc_us"] // 60_000_000
        for b in sorted(set(a["beacon"].tolist())):
            for m in sorted(set(am[a["beacon"] == b].tolist())):
                q = a[(a["beacon"] == b) & (am == m)]
                row = {"receiver": rx, "stamp": stamp, "absolute_minute": int(m),
                       "beacon": f"B{b}", "frames": len(q),
                       "elapsed_s_median": float(np.median(q["elapsed_s"]))}
                row.update({e: float(np.median(q[e])) for e in ESTS})
                rows.append(row)
    return rows


def pair_summary(minutes):
    by = defaultdict(dict)
    for r in minutes:
        by[(r["receiver"], r["stamp"], r["absolute_minute"])][r["beacon"]] = r
    detail = []
    for (rx, stamp, minute), d in sorted(by.items()):
        for b1, b2 in (("B1", "B2"), ("B2", "B3")):
            if b1 not in d or b2 not in d:
                continue
            for e in ESTS:
                delta = abs(d[b1][e] - d[b2][e])
                detail.append({"receiver": rx, "stamp": stamp,
                               "absolute_minute": minute, "pair": f"{b1}-{b2}",
                               "estimator": e, "delta": delta,
                               "sigma": delta / UNIT_SD})
    groups = defaultdict(list)
    for r in detail:
        groups[(r["receiver"], r["stamp"], r["pair"], r["estimator"])].append(r)
    summary = []
    for key, rr in sorted(groups.items()):
        low = [x["absolute_minute"] for x in rr if x["delta"] < UNIT_SD]
        runs = longest_runs(low)
        summary.append({
            "receiver": key[0], "stamp": key[1], "pair": key[2],
            "estimator": key[3], "minutes": len(rr), "below_1sd": len(low),
            "below_1sd_frac": len(low) / len(rr),
            "longest_run_min": runs[0][2] if runs else 0,
            "longest_run_start_abs_min": runs[0][0] if runs else None,
        })
    return detail, summary


def event_contrasts(data):
    out = []
    for key, t in LABEL_S.items():
        if key not in data:
            continue
        a = data[key]; a = a[a["beacon"] == 3]
        pre_all = a[(a["elapsed_s"] >= t - 600) & (a["elapsed_s"] < t)]
        post_all = a[(a["elapsed_s"] >= t) & (a["elapsed_s"] < t + 600)]
        for scope, pre, post in (
                ("all_fitted", pre_all, post_all),
                ("common_prod_gate", pre_all[pre_all["prod_gate"]],
                 post_all[post_all["prod_gate"]])):
            for e in ESTS:
                x = float(np.median(pre[e])); y = float(np.median(post[e]))
                out.append({"event": "night2_going_to_bed", "receiver": key[0],
                            "beacon": "B3", "scope": scope, "estimator": e,
                            "pre_n": len(pre), "post_n": len(post), "pre": x,
                            "post": y, "shift": y - x,
                            "shift_sigma": (y - x) / UNIT_SD,
                            "pre_gate_frac": float(np.mean(pre_all["prod_gate"])),
                            "post_gate_frac": float(np.mean(post_all["prod_gate"]))})
    return out


def simultaneous(detail):
    d = {(r["receiver"], r["stamp"], r["absolute_minute"], r["pair"],
          r["estimator"]): r for r in detail}
    out = []
    keys = {(r["stamp"], r["absolute_minute"], r["pair"], r["estimator"])
            for r in detail}
    groups = defaultdict(list)
    for stamp, minute, pair, est in keys:
        a = d.get(("d0wd", stamp, minute, pair, est))
        b = d.get(("s3", stamp, minute, pair, est))
        if a and b:
            groups[(stamp, pair, est)].append((minute, a["delta"] < UNIT_SD
                                               and b["delta"] < UNIT_SD))
    for key, vals in sorted(groups.items()):
        low = [m for m, ok in vals if ok]; runs = longest_runs(low)
        out.append({"stamp": key[0], "pair": key[1], "estimator": key[2],
                    "aligned_minutes": len(vals), "both_below_1sd": len(low),
                    "both_below_frac": len(low) / len(vals),
                    "longest_both_run_min": runs[0][2] if runs else 0})
    return out


def write_csv(path, rows):
    if not rows:
        return
    fields = []
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--in", dest="indir", required=True)
    ap.add_argument("--out", required=True); args = ap.parse_args()
    indir, out = Path(args.indir), Path(args.out); out.mkdir(parents=True, exist_ok=True)
    data = load_all(indir)
    es = estimator_summary(data); mins = minute_rows(data)
    pd, ps = pair_summary(mins); ev = event_contrasts(data); sim = simultaneous(pd)
    write_csv(out / "estimator_summary.csv", es)
    write_csv(out / "minute_medians.csv", mins)
    write_csv(out / "pair_minute_detail.csv", pd)
    write_csv(out / "pair_summary.csv", ps)
    write_csv(out / "event_contrasts.csv", ev)
    write_csv(out / "simultaneous_pair_summary.csv", sim)
    manifest = {"files": len(data), "frames": int(sum(len(x) for x in data.values())),
                "common_gate_rule": "production inlier>=0.6 and residual<=0.8",
                "between_unit_sd": UNIT_SD}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
