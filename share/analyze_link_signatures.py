#!/usr/bin/env python3
"""Frozen retrospective link-signature tests for the eight-night CSI corpus.

The protocol is defined in LINK_SIGNATURE_PREREGISTRATION.md.  This script uses
only multiscale products; it never opens or modifies the raw captures.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


FEATURE_NAMES = (
    "arb", "arb_iqr", "coh_arb", "ols_minus_arb",
    "rssi", "log_amp_med", "cir_peak", "log_cir_rms",
)
REPS = {
    "slope": np.array([0, 1, 2, 3]),
    "channel": np.array([4, 5, 6, 7]),
    "combined": np.arange(8),
}
RX_NAMES = {0: "d0wd", 1: "s3"}
SEED = 20260905


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_scale(root: Path, scale: int) -> np.ndarray:
    if scale in (60, 300):
        paths = sorted(root.glob(f"*.{scale}s.npy"))
        return np.concatenate([np.load(p) for p in paths])
    if scale != 600:
        raise ValueError(scale)
    base = load_scale(root, 300)
    rows = []
    fields = ("arb", "arb_iqr", "ols", "coh_arb", "rssi", "amp_med",
              "kp1_amp", "cir_peak", "cir_rms")
    keys = np.stack((base["receiver"], base["night"], base["beacon"],
                     base["bin"] // 2), axis=1)
    order = np.lexsort((keys[:, 3], keys[:, 2], keys[:, 1], keys[:, 0]))
    base, keys = base[order], keys[order]
    cuts = np.r_[0, np.flatnonzero(np.any(np.diff(keys, axis=0), axis=1)) + 1, len(base)]
    dtype = base.dtype
    for lo, hi in zip(cuts[:-1], cuts[1:]):
        z = base[lo:hi]
        row = np.zeros((), dtype=dtype)
        row["receiver"], row["night"], row["beacon"] = keys[lo, :3]
        row["scale_s"], row["bin"] = 600, keys[lo, 3]
        row["count"] = np.sum(z["count"], dtype=np.uint64)
        for field in fields:
            row[field] = np.median(z[field])
        rows.append(row)
    return np.array(rows, dtype=dtype)


def feature_vector(row) -> np.ndarray:
    tiny = np.finfo(float).tiny
    return np.array([
        row["arb"], row["arb_iqr"], row["coh_arb"], row["ols"] - row["arb"],
        row["rssi"], np.log(max(float(row["amp_med"]), tiny)), row["cir_peak"],
        np.log(max(float(row["cir_rms"]), tiny)),
    ], dtype=float)


def complete_observations(a: np.ndarray):
    """Return {(rx, night): (X, y, bin)} with all three beacons per bin."""
    out = {}
    for rx in (0, 1):
        for night in range(1, 9):
            q = a[(a["receiver"] == rx) & (a["night"] == night)]
            maps = {b: {int(r["bin"]): r for r in q[q["beacon"] == b]}
                    for b in (1, 2, 3)}
            common = sorted(set(maps[1]) & set(maps[2]) & set(maps[3]))
            X, y, bins = [], [], []
            for t in common:
                for b in (1, 2, 3):
                    X.append(feature_vector(maps[b][t]))
                    y.append(b)
                    bins.append(t)
            out[(rx, night)] = (np.asarray(X), np.asarray(y), np.asarray(bins))
    return out


def aligned_observations(obs):
    """Return {night: (Xd0, Xs3, y, bin)} on the identical paired support."""
    out = {}
    for night in range(1, 9):
        d0, s3 = obs[(0, night)], obs[(1, night)]
        dm = {(int(t), int(y)): x for x, y, t in zip(*d0)}
        sm = {(int(t), int(y)): x for x, y, t in zip(*s3)}
        keys = sorted(set(dm) & set(sm))
        out[night] = (np.asarray([dm[k] for k in keys]),
                      np.asarray([sm[k] for k in keys]),
                      np.asarray([k[1] for k in keys]),
                      np.asarray([k[0] for k in keys]))
    return out


def fit_centroids(X: np.ndarray, y: np.ndarray):
    center = np.median(X, axis=0)
    scale = 1.4826 * np.median(np.abs(X - center), axis=0)
    scale[~np.isfinite(scale) | (scale == 0)] = 1.0
    z = (X - center) / scale
    centroids = np.stack([np.median(z[y == b], axis=0) for b in (1, 2, 3)])
    return center, scale, centroids


def predict_distance(model, X: np.ndarray):
    center, scale, centroids = model
    z = (X - center) / scale
    dist = np.sqrt(np.sum((z[:, None, :] - centroids[None, :, :]) ** 2, axis=2))
    return np.argmin(dist, axis=1) + 1, dist


def balanced_accuracy(y, pred) -> float:
    vals = [np.mean(pred[y == b] == b) for b in (1, 2, 3) if np.any(y == b)]
    return float(np.mean(vals)) if vals else float("nan")


def confusion(y, pred):
    return [[int(np.sum((y == a) & (pred == b))) for b in (1, 2, 3)]
            for a in (1, 2, 3)]


def bootstrap_ci(values, draws=20_000):
    v = np.asarray(values, dtype=float)
    rng = np.random.default_rng(SEED)
    ix = rng.integers(0, len(v), size=(draws, len(v)))
    means = np.mean(v[ix], axis=1)
    return [float(x) for x in np.percentile(means, [2.5, 97.5])]


def auc_score(genuine_score, impostor_score):
    g, i = np.asarray(genuine_score), np.asarray(impostor_score)
    # Probability that a random genuine score exceeds a random impostor score,
    # with half credit for ties.  Arrays are small enough for exact comparison.
    wins = sum(np.sum(x > i) + 0.5 * np.sum(x == i) for x in g)
    return float(wins / (len(g) * len(i)))


def eer_score(genuine_dist, impostor_dist):
    g, i = np.asarray(genuine_dist), np.asarray(impostor_dist)
    thresholds = np.unique(np.r_[g, i])
    far = np.array([np.mean(i <= t) for t in thresholds])
    frr = np.array([np.mean(g > t) for t in thresholds])
    j = int(np.argmin(np.abs(far - frr)))
    return float((far[j] + frr[j]) / 2), float(thresholds[j])


def subset(data, inds):
    X, y, bins = data
    return X[:, inds], y, bins


def t1_same_receiver(all_obs, scale):
    rows, verification = [], []
    for rep, inds in REPS.items():
        for rx in (0, 1):
            for test_night in range(1, 9):
                train = [subset(all_obs[(rx, n)], inds) for n in range(1, 9)
                         if n != test_night]
                Xtr = np.concatenate([z[0] for z in train])
                ytr = np.concatenate([z[1] for z in train])
                Xte, yte, bins = subset(all_obs[(rx, test_night)], inds)
                model = fit_centroids(Xtr, ytr)
                pred, dist = predict_distance(model, Xte)
                conf = confusion(yte, pred)
                rows.append({
                    "scale_s": scale, "representation": rep,
                    "receiver": RX_NAMES[rx], "test_night": test_night,
                    "test_bins_per_class": int(len(yte) // 3),
                    "balanced_accuracy": balanced_accuracy(yte, pred),
                    "confusion_json": json.dumps(conf, separators=(",", ":")),
                })
                if scale == 300:
                    gd = dist[np.arange(len(yte)), yte - 1]
                    impostor_mask = np.ones_like(dist, dtype=bool)
                    impostor_mask[np.arange(len(yte)), yte - 1] = False
                    idist = dist[impostor_mask]
                    eer, threshold = eer_score(gd, idist)
                    verification.append({
                        "representation": rep, "receiver": RX_NAMES[rx],
                        "test_night": test_night, "genuine_claims": len(gd),
                        "impostor_claims": len(idist),
                        "auc": auc_score(-gd, -idist), "eer": eer,
                        "eer_distance_threshold": threshold,
                    })
    return rows, verification


def t2_fusion(aligned, scale):
    rows = []
    for rep, inds in REPS.items():
        for test_night in range(1, 9):
            tr = [aligned[n] for n in range(1, 9) if n != test_night]
            dtr, str_, ytr = (np.concatenate([z[j] for z in tr]) for j in range(3))
            dte, ste, yte, bins = aligned[test_night]
            datasets = {
                "d0wd": (dtr[:, inds], dte[:, inds]),
                "s3": (str_[:, inds], ste[:, inds]),
                "fused": (np.c_[dtr[:, inds], str_[:, inds]],
                          np.c_[dte[:, inds], ste[:, inds]]),
            }
            for model_name, (Xtr, Xte) in datasets.items():
                model = fit_centroids(Xtr, ytr)
                pred, _ = predict_distance(model, Xte)
                rows.append({
                    "scale_s": scale, "representation": rep,
                    "model": model_name, "test_night": test_night,
                    "paired_bins_per_class": int(len(yte) // 3),
                    "balanced_accuracy": balanced_accuracy(yte, pred),
                    "confusion_json": json.dumps(confusion(yte, pred), separators=(",", ":")),
                })
    return rows


def normalize_receiver_night(data):
    X, y, bins = data
    center = np.median(X, axis=0)
    scale = 1.4826 * np.median(np.abs(X - center), axis=0)
    scale[~np.isfinite(scale) | (scale == 0)] = 1.0
    return (X - center) / scale, y, bins


def t4_invariance(obs):
    norm = {k: normalize_receiver_night(v) for k, v in obs.items()}
    rows = []
    for rep, inds in REPS.items():
        for source, target in ((0, 0), (1, 1), (0, 1), (1, 0)):
            for test_night in range(1, 9):
                train = [subset(norm[(source, n)], inds) for n in range(1, 9)
                         if n != test_night]
                Xtr = np.concatenate([z[0] for z in train])
                ytr = np.concatenate([z[1] for z in train])
                Xte, yte, _ = subset(norm[(target, test_night)], inds)
                pred, _ = predict_distance(fit_centroids(Xtr, ytr), Xte)
                rows.append({
                    "representation": rep, "train_receiver": RX_NAMES[source],
                    "test_receiver": RX_NAMES[target], "test_night": test_night,
                    "test_bins_per_class": int(len(yte) // 3),
                    "balanced_accuracy": balanced_accuracy(yte, pred),
                })
    return rows


def summarize(t1, t2, t3, t4):
    summary = {"seed": SEED, "bootstrap_draws": 20_000, "chance_accuracy": 1/3,
               "t1": [], "t2": [], "t3": [], "t4": [], "passes": {}}
    for scale in (60, 300, 600):
        for rep in REPS:
            for rx in RX_NAMES.values():
                q = [r for r in t1 if r["scale_s"] == scale and
                     r["representation"] == rep and r["receiver"] == rx]
                vals = [r["balanced_accuracy"] for r in q]
                summary["t1"].append({"scale_s": scale, "representation": rep,
                    "receiver": rx, "macro_accuracy": float(np.mean(vals)),
                    "median_night_accuracy": float(np.median(vals)),
                    "nights_at_least_0_50": int(np.sum(np.asarray(vals) >= .5)),
                    "night_bootstrap_95ci": bootstrap_ci(vals)})
            for model in ("d0wd", "s3", "fused"):
                q = [r for r in t2 if r["scale_s"] == scale and
                     r["representation"] == rep and r["model"] == model]
                vals = [r["balanced_accuracy"] for r in q]
                summary["t2"].append({"scale_s": scale, "representation": rep,
                    "model": model, "macro_accuracy": float(np.mean(vals)),
                    "median_night_accuracy": float(np.median(vals)),
                    "night_bootstrap_95ci": bootstrap_ci(vals)})
    for rep in REPS:
        for rx in RX_NAMES.values():
            q = [r for r in t3 if r["representation"] == rep and r["receiver"] == rx]
            summary["t3"].append({"representation": rep, "receiver": rx,
                "macro_auc": float(np.mean([r["auc"] for r in q])),
                "macro_eer": float(np.mean([r["eer"] for r in q])),
                "median_night_auc": float(np.median([r["auc"] for r in q])),
                "median_night_eer": float(np.median([r["eer"] for r in q]))})
        for source, target in (("d0wd", "d0wd"), ("s3", "s3"),
                               ("d0wd", "s3"), ("s3", "d0wd")):
            q = [r for r in t4 if r["representation"] == rep and
                 r["train_receiver"] == source and r["test_receiver"] == target]
            summary["t4"].append({"representation": rep, "train_receiver": source,
                "test_receiver": target,
                "macro_accuracy": float(np.mean([r["balanced_accuracy"] for r in q]))})

    # Apply only the frozen primary-scale criteria.
    t1_pass = {}
    t3_pass = {}
    for rep in REPS:
        t1_pass[rep] = all(next(z for z in summary["t1"] if z["scale_s"] == 300 and
            z["representation"] == rep and z["receiver"] == rx)["night_bootstrap_95ci"][0] > 1/3
            and next(z for z in summary["t1"] if z["scale_s"] == 300 and
            z["representation"] == rep and z["receiver"] == rx)["median_night_accuracy"] >= .70
            and next(z for z in summary["t1"] if z["scale_s"] == 300 and
            z["representation"] == rep and z["receiver"] == rx)["nights_at_least_0_50"] >= 6
            for rx in RX_NAMES.values())
        t3_pass[rep] = all(next(z for z in summary["t3"] if
            z["representation"] == rep and z["receiver"] == rx)["macro_auc"] >= .90
            and next(z for z in summary["t3"] if z["representation"] == rep and
            z["receiver"] == rx)["macro_eer"] <= .15 for rx in RX_NAMES.values())
    fusion_pass = {}
    for rep in REPS:
        q = [r for r in t2 if r["scale_s"] == 300 and r["representation"] == rep]
        bynight = defaultdict(dict)
        for r in q:
            bynight[r["test_night"]][r["model"]] = r["balanced_accuracy"]
        fv = [x["fused"] for x in bynight.values()]
        d0 = [x["d0wd"] for x in bynight.values()]
        s3 = [x["s3"] for x in bynight.values()]
        improvement = float(np.mean(fv) - max(np.mean(d0), np.mean(s3)))
        nights_tie_or_better = int(sum(f >= max(a, b) for f, a, b in zip(fv, d0, s3)))
        fusion_pass[rep] = {"pass": improvement >= .05 and nights_tie_or_better >= 6,
                            "macro_improvement_over_best_single": improvement,
                            "nights_tie_or_better": nights_tie_or_better}
    summary["passes"] = {"t1_by_representation": t1_pass,
                         "t2_by_representation": fusion_pass,
                         "t3_by_representation": t3_pass,
                         "spoof_resistance_tested": False}
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--multiscale", default="deep_dive/multiscale")
    ap.add_argument("--out", default="deep_dive/link_signature")
    args = ap.parse_args()
    root, out = Path(args.multiscale), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t1_all, t2_all, verification, obs300 = [], [], [], None
    support = []
    for scale in (60, 300, 600):
        a = load_scale(root, scale)
        obs = complete_observations(a)
        aligned = aligned_observations(obs)
        for (rx, night), z in obs.items():
            support.append({"scale_s": scale, "receiver": RX_NAMES[rx],
                            "night": night, "complete_bins_per_class": len(z[1]) // 3})
        for night, z in aligned.items():
            support.append({"scale_s": scale, "receiver": "paired",
                            "night": night, "complete_bins_per_class": len(z[2]) // 3})
        t1, ver = t1_same_receiver(obs, scale)
        t1_all.extend(t1); verification.extend(ver)
        t2_all.extend(t2_fusion(aligned, scale))
        if scale == 300:
            obs300 = obs
    t4 = t4_invariance(obs300)
    summary = summarize(t1_all, t2_all, verification, t4)
    write_csv(out / "support.csv", support)
    write_csv(out / "same_receiver_identification.csv", t1_all)
    write_csv(out / "paired_receiver_fusion.csv", t2_all)
    write_csv(out / "claimed_link_verification.csv", verification)
    write_csv(out / "receiver_invariance.csv", t4)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary["passes"], indent=2))


if __name__ == "__main__":
    main()
