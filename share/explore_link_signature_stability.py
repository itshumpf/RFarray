#!/usr/bin/env python3
"""Post-preregistration exploratory temporal stability checks.

This imports the frozen data preparation and classifier implementation, but the
analyses here are explicitly exploratory and cannot change preregistered outcomes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from analyze_link_signatures import (
    FEATURE_NAMES, REPS, RX_NAMES, aligned_observations, balanced_accuracy,
    complete_observations, fit_centroids, load_scale, predict_distance, write_csv,
)


def temporal_split(data, inds):
    X, y, bins = data
    unique = np.unique(bins)
    n = len(unique)
    early = set(unique[:max(1, int(.4 * n))])
    late = set(unique[int(.6 * n):])
    im_train = np.array([int(t) in early for t in bins])
    im_test = np.array([int(t) in late for t in bins])
    return X[im_train][:, inds], y[im_train], X[im_test][:, inds], y[im_test]


def single_night_transfer(obs):
    rows = []
    for rep, inds in REPS.items():
        for rx in (0, 1):
            for train_night in range(1, 9):
                Xtr, ytr, _ = obs[(rx, train_night)]
                model = fit_centroids(Xtr[:, inds], ytr)
                for test_night in range(1, 9):
                    Xte, yte, _ = obs[(rx, test_night)]
                    pred, _ = predict_distance(model, Xte[:, inds])
                    rows.append({"representation": rep, "receiver": RX_NAMES[rx],
                        "train_night": train_night, "test_night": test_night,
                        "same_night_resubstitution": train_night == test_night,
                        "balanced_accuracy": balanced_accuracy(yte, pred)})
    return rows


def early_late(obs, aligned):
    rows = []
    for rep, inds in REPS.items():
        for night in range(1, 9):
            for rx in (0, 1):
                Xtr, ytr, Xte, yte = temporal_split(obs[(rx, night)], inds)
                pred, _ = predict_distance(fit_centroids(Xtr, ytr), Xte)
                rows.append({"representation": rep, "model": RX_NAMES[rx],
                    "night": night, "train_early_bins_per_class": len(ytr) // 3,
                    "test_late_bins_per_class": len(yte) // 3,
                    "balanced_accuracy": balanced_accuracy(yte, pred)})
            d0, s3, y, bins = aligned[night]
            unique = np.unique(bins); n = len(unique)
            early = set(unique[:max(1, int(.4*n))]); late = set(unique[int(.6*n):])
            itr = np.array([int(t) in early for t in bins])
            ite = np.array([int(t) in late for t in bins])
            X = np.c_[d0[:, inds], s3[:, inds]]
            pred, _ = predict_distance(fit_centroids(X[itr], y[itr]), X[ite])
            rows.append({"representation": rep, "model": "fused", "night": night,
                "train_early_bins_per_class": int(np.sum(itr) // 3),
                "test_late_bins_per_class": int(np.sum(ite) // 3),
                "balanced_accuracy": balanced_accuracy(y[ite], pred)})
    return rows


def feature_receiver_transfer(obs):
    """Exploratory decomposition of the preregistered T4 diagnostic."""
    norm = {k: normalize_night(v) for k, v in obs.items()}
    rows = []
    for feature_i, feature in enumerate(FEATURE_NAMES):
        inds = np.array([feature_i])
        for source, target in ((0, 0), (1, 1), (0, 1), (1, 0)):
            for test_night in range(1, 9):
                train = [norm[(source, n)] for n in range(1, 9) if n != test_night]
                Xtr = np.concatenate([z[0][:, inds] for z in train])
                ytr = np.concatenate([z[1] for z in train])
                Xte, yte, _ = norm[(target, test_night)]
                pred, _ = predict_distance(fit_centroids(Xtr, ytr), Xte[:, inds])
                rows.append({"feature": feature, "train_receiver": RX_NAMES[source],
                    "test_receiver": RX_NAMES[target], "test_night": test_night,
                    "balanced_accuracy": balanced_accuracy(yte, pred)})
    return rows


def normalize_night(data):
    X, y, bins = data
    center = np.median(X, axis=0)
    scale = 1.4826 * np.median(np.abs(X - center), axis=0)
    scale[~np.isfinite(scale) | (scale == 0)] = 1.0
    return (X - center) / scale, y, bins


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--multiscale", default="deep_dive/multiscale")
    ap.add_argument("--out", default="deep_dive/link_signature")
    args = ap.parse_args(); out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    obs = complete_observations(load_scale(Path(args.multiscale), 300))
    transfer = single_night_transfer(obs)
    temporal = early_late(obs, aligned_observations(obs))
    feature_transfer = feature_receiver_transfer(obs)
    write_csv(out / "exploratory_night_transfer.csv", transfer)
    write_csv(out / "exploratory_early_late.csv", temporal)
    write_csv(out / "exploratory_feature_receiver_transfer.csv", feature_transfer)
    for rep in REPS:
        for model in ("d0wd", "s3", "fused"):
            q = [r["balanced_accuracy"] for r in temporal
                 if r["representation"] == rep and r["model"] == model]
            print(f"{rep:8s} {model:5s} early->late macro={np.mean(q):.3f} "
                  f"range={np.min(q):.3f}-{np.max(q):.3f}")
    for rep in REPS:
        for rx in RX_NAMES.values():
            q = [r for r in transfer if r["representation"] == rep and
                 r["receiver"] == rx]
            same = [r["balanced_accuracy"] for r in q
                    if r["same_night_resubstitution"]]
            cross = [r["balanced_accuracy"] for r in q
                     if not r["same_night_resubstitution"]]
            adjacent = [r["balanced_accuracy"] for r in q
                        if abs(r["train_night"] - r["test_night"]) == 1]
            print(f"{rep:8s} {rx:5s} single-night templates: "
                  f"resub={np.mean(same):.3f} cross={np.mean(cross):.3f} "
                  f"adjacent={np.mean(adjacent):.3f} "
                  f"cross-range={np.min(cross):.3f}-{np.max(cross):.3f}")
    print("feature-level cross-receiver T4 diagnostic")
    for feature in FEATURE_NAMES:
        q = [r["balanced_accuracy"] for r in feature_transfer if r["feature"] == feature
             and r["train_receiver"] != r["test_receiver"]]
        print(f"  {feature:16s} macro={np.mean(q):.3f}")


if __name__ == "__main__":
    main()
