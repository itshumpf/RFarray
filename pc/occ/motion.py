#!/usr/bin/env python3
"""Motion metric + calibrated detector.

Physics
-------
A moving body changes multipath geometry on a timescale of ~0.1-1 s,
which shows up as broadband dispersion of the per-subcarrier amplitude
shape. The metric here is deliberately simple and interpretable:

    metric(t) = median over subcarriers k of
                std over a trailing window of shape[t, k]

on the unit-mean-normalized shape, so AGC steps are already cancelled.
The median across subcarriers makes a single glitchy bin harmless; the
std over ~2 s captures the motion timescale while staying blind to slow
thermal drift (which moves over minutes).

An empty room is NOT metric == 0: receiver noise sets a floor. So the
detector is calibrated on quiet data: per-link robust z-scores
(median/MAD from a calibration distribution), fused across links, with
hysteresis so one noisy bin doesn't chatter the state.
"""
import numpy as np


def rolling_std(A, w, min_frac=0.5):
    """Trailing-window std per column, NaN-aware via cumsum.

    A: (n, k) with NaN for missing bins. Bins whose window holds fewer
    than min_frac*w valid samples get NaN (not 0 — absence of data must
    not read as absence of motion).
    """
    X = np.nan_to_num(A, nan=0.0).astype(np.float64)
    M = np.isfinite(A).astype(np.float64)
    c1 = np.cumsum(X, axis=0)
    c2 = np.cumsum(X * X, axis=0)
    cm = np.cumsum(M, axis=0)

    def wsum(C):
        S = C.copy()
        S[w:] = C[w:] - C[:-w]
        return S

    s1, s2, m = wsum(c1), wsum(c2), wsum(cm)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = s1 / m
        var = s2 / m - mean * mean
    std = np.sqrt(np.maximum(var, 0.0))
    std[m < max(3.0, min_frac * w)] = np.nan
    return std


def motion_metric(grid, window_s=2.0):
    """Per-bin motion metric for one LinkGrid. Returns (n,) float64."""
    w = max(3, int(round(window_s / grid.dt)))
    std = rolling_std(grid.shape, w)
    out = np.full(std.shape[0], np.nan)
    rows = np.isfinite(std).any(axis=1)
    if rows.any():
        out[rows] = np.nanmedian(std[rows], axis=1)
    return out


def rolling_mean_count(count, w):
    """Trailing-window mean of the per-bin frame count."""
    c = np.cumsum(count.astype(np.float64))
    s = c.copy()
    s[w:] = c[w:] - c[:-w]
    s[:w] = c[:w]
    denom = np.minimum(np.arange(count.size) + 1, w)
    return s / denom


class CountConditionedFloor:
    """Motion-metric noise floor as a function of sampling density.

    The metric is built from per-bin medians of however many frames
    landed in each bin, so its empty-room floor rises like ~1/sqrt(n)
    when the link's frame rate drops. Frame rates move between sessions
    (channel-6 collision balance shifts), and a link whose rate changed
    since calibration would otherwise read as permanently 'moving' —
    measured on real data: B3 went 55 -> 37 fps between two sessions
    and its raw z-median sat at +19.6 with zero actual motion evidence.

    Fix: group calibration bins by windowed mean frame count and learn
    (median, sigma) per count level; scoring interpolates the floor at
    the test data's own sampling density.
    """

    def __init__(self, cs, meds, sigs, fps, rssi_med):
        self.cs, self.meds, self.sigs = cs, meds, sigs
        self.fps, self.rssi_med = fps, rssi_med

    @classmethod
    def fit(cls, metric, count, w, dt, rssi, min_group=300):
        cbar = rolling_mean_count(count, w)
        fin = np.isfinite(metric)
        cs, meds, sigs = [], [], []
        for c in np.unique(np.round(cbar[fin]).astype(int)):
            sel = fin & (np.round(cbar).astype(int) == c)
            if sel.sum() < min_group:
                continue
            med, sig = robust_stats(metric[sel])
            if np.isfinite(med) and np.isfinite(sig):
                cs.append(c)
                meds.append(med)
                sigs.append(sig)
        if not cs:                       # fall back to unconditioned
            med, sig = robust_stats(metric[fin])
            cs, meds, sigs = [1], [med], [sig]
        fps = float(count.mean()) / dt if count.size else 0.0
        rmed = float(np.nanmedian(rssi)) if rssi.size else np.nan
        return cls(np.array(cs, dtype=float), np.array(meds),
                   np.array(sigs), fps, rmed)

    def z(self, metric, count, w):
        cbar = np.clip(rolling_mean_count(count, w),
                       self.cs[0], self.cs[-1])
        med = np.interp(cbar, self.cs, self.meds)
        sig = np.interp(cbar, self.cs, self.sigs)
        with np.errstate(invalid="ignore"):
            return (metric - med) / sig


def robust_stats(x):
    """(median, MAD*1.4826) of finite values — a Gaussian-consistent
    scale that ignores the motion tail."""
    v = x[np.isfinite(x)]
    if v.size < 10:
        return np.nan, np.nan
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med))) * 1.4826
    return med, mad if mad > 0 else float(v.std()) or 1e-9


def zscore(metric, med, sigma):
    with np.errstate(invalid="ignore"):
        return (metric - med) / sigma


class FusedDetector:
    """2-of-3-style fusion of per-link z-scores with hysteresis.

    ON when (a) the second-largest link z exceeds z_on (two links agree
    something moved — a single-link artifact can't trigger), or (b) any
    single link exceeds z_solo (a strong event near one path only).
    OFF when the largest z falls below z_off for min_off_s.
    """

    def __init__(self, dt, z_on=5.0, z_solo=12.0, z_off=3.0,
                 min_on_s=1.0, min_off_s=5.0):
        self.dt = dt
        self.z_on, self.z_solo, self.z_off = z_on, z_solo, z_off
        self.min_on = max(1, int(round(min_on_s / dt)))
        self.min_off = max(1, int(round(min_off_s / dt)))

    def detect(self, z_by_link):
        """z_by_link: (L, n) array. Returns (active: (n,) bool, trigger)."""
        Z = np.asarray(z_by_link, dtype=np.float64)
        Z = np.where(np.isfinite(Z), Z, -np.inf)
        Zs = np.sort(Z, axis=0)                 # ascending over links
        top = Zs[-1]
        second = Zs[-2] if Z.shape[0] >= 2 else Zs[-1]
        raw_on = (second > self.z_on) | (top > self.z_solo)
        raw_off = top < self.z_off

        n = top.size
        active = np.zeros(n, dtype=bool)
        state = False
        run_on = run_off = 0
        for i in range(n):
            if state:
                run_off = run_off + 1 if raw_off[i] else 0
                if run_off >= self.min_off:
                    state = False
                    run_off = 0
            else:
                run_on = run_on + 1 if raw_on[i] else 0
                if run_on >= self.min_on:
                    state = True
                    run_on = 0
            active[i] = state
        return active


def segments(mask, dt, min_len_s=0.0):
    """Boolean mask -> [(i0, i1, dur_s)] half-open bin ranges."""
    out = []
    n = mask.size
    i = 0
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            dur = (j - i) * dt
            if dur >= min_len_s:
                out.append((i, j, dur))
            i = j
        else:
            i += 1
    return out
