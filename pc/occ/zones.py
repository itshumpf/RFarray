#!/usr/bin/env python3
"""Coarse zone localization from cross-link differential response.

Physics
-------
The three beacons sit at different points in the space, so the three
TX->collector links are three distinct geometric paths. A perturbation
(person) close to link L's path disturbs L strongly and the others
weakly; the *relative* distribution of motion energy across links is
therefore a coarse spatial signature — not coordinates, but a repeatable
"zone" label once calibrated against a labeled walk.

Without a labeled walk this module can still do useful science: it
computes per-event link profiles and reports how distinct they are. If
events cluster into a few stable profiles, the geometry is resolvable
and a labeled calibration walk will map clusters to rooms/zones.
"""
import numpy as np


def event_profiles(events, z_by_link, link_names):
    """Per-event motion-energy distribution across links.

    events: [(i0, i1, dur_s)] bin ranges from motion.segments()
    z_by_link: (L, n) per-link z-scored metric
    Returns list of dicts: t bins, duration, per-link mean excess z,
    normalized profile (sums to 1), dominant link.
    """
    out = []
    Z = np.asarray(z_by_link)
    for i0, i1, dur in events:
        e = np.array([np.nanmean(np.clip(Z[l, i0:i1], 0, None))
                      for l in range(Z.shape[0])])
        e = np.where(np.isfinite(e), e, 0.0)
        total = e.sum()
        if total <= 0:
            continue
        prof = e / total
        out.append({
            "i0": i0, "i1": i1, "dur_s": dur,
            "energy": e, "profile": prof,
            "dominant": link_names[int(np.argmax(e))],
        })
    return out


def profile_spread(profiles):
    """How much spatial information do the profiles carry?

    If every event has the same link profile, the links are not seeing
    geometry (or every event is in the same place). Reports the spread
    of profiles around their centroid (mean L1 distance) — 0 means no
    spatial signal, higher means events differ across links.
    """
    if len(profiles) < 2:
        return None
    P = np.stack([p["profile"] for p in profiles])
    centroid = P.mean(axis=0)
    d = np.abs(P - centroid).sum(axis=1)
    return {
        "centroid": centroid,
        "mean_l1": float(d.mean()),
        "max_l1": float(d.max()),
    }


def kmeans_zones(profiles, k=3, iters=50, seed=0):
    """Tiny k-means over event link-profiles -> provisional zone ids.

    Returns (assignments, centroids) or None if too few events. These
    are unlabeled clusters; naming them (door / desk / hallway) needs
    the calibration walk.
    """
    if len(profiles) < k * 2:
        return None
    P = np.stack([p["profile"] for p in profiles])
    rng = np.random.default_rng(seed)
    C = P[rng.choice(len(P), size=k, replace=False)]
    assign = np.zeros(len(P), dtype=int)
    for _ in range(iters):
        d = ((P[:, None, :] - C[None, :, :]) ** 2).sum(axis=2)
        new = d.argmin(axis=1)
        if (new == assign).all():
            break
        assign = new
        for j in range(k):
            if (assign == j).any():
                C[j] = P[assign == j].mean(axis=0)
    return assign, C
