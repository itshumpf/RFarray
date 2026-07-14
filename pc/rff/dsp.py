#!/usr/bin/env python3
"""DSP core: CSI phase -> robust per-frame (SFO slope, CFO intercept).

Physics
-------
For a 20 MHz non-HT frame the LLTF gives one complex channel estimate per
OFDM subcarrier. The transmitter's clock imperfections leave two linear
signatures in the *phase* across subcarriers k:

    phase(k) = slope * k + intercept + channel(k) + noise

  - slope     ∝ timing/sampling offset. The sampling-frequency-offset (SFO)
                component is a hardware property of the TX crystal.
  - intercept = common phase. Its frame-to-frame *rate of change* is the
                residual carrier-frequency offset (CFO) — also crystal-bound.

channel(k) is multipath: smooth but NOT linear, and it moves when the room
moves. That is exactly why we fit with RANSAC instead of least squares:
multipath bumps and guard-band garbage become outliers instead of biasing
the slope.

ESP32 buffer layout (LLTF, 20 MHz): 64 complex int8 pairs stored
imag,real in FFT order — buffer index 0..31 holds subcarriers 0..+31,
index 32..63 holds subcarriers -32..-1. Only |k| in 1..26 carry signal
(52 data+pilot subcarriers); DC and the guard band are null and must be
excluded. The recorded data confirms this: guard bins are exactly zero.
"""
import numpy as np

N_CPLX = 64                       # LLTF complex samples on ESP32

# FFT-order -> physical subcarrier index for each buffer position.
_K_OF_IDX = np.r_[np.arange(0, 32), np.arange(-32, 0)]
# usable subcarriers: skip DC (k=0) and guards (|k|>26)
_USABLE_MASK = (np.abs(_K_OF_IDX) >= 1) & (np.abs(_K_OF_IDX) <= 26)
_ORDER = np.argsort(_K_OF_IDX[_USABLE_MASK])       # sort usable bins by k
K_USABLE = np.sort(_K_OF_IDX[_USABLE_MASK])        # -26..-1, 1..26
_USABLE_IDX = np.where(_USABLE_MASK)[0][_ORDER]    # buffer index per k

SUBCARRIER_SPACING_HZ = 312500.0  # 20 MHz / 64


def csi_to_complex(vals):
    """Interleaved int8 [imag, real, ...] -> complex LLTF vector (FFT order).

    Returns None if the frame is too short for a full LLTF.
    """
    v = np.asarray(vals, dtype=np.float64)
    if v.size < N_CPLX * 2:
        return None
    iq = v[: N_CPLX * 2]
    return iq[1::2] + 1j * iq[0::2]


def unwrap_continuity(phase, prev_mean=None):
    """Unwrap across subcarriers, then pin temporal continuity.

    np.unwrap fixes intra-frame 2π jumps; the whole frame is still free to
    sit an arbitrary multiple of 2π away from the previous frame. If
    prev_mean (last frame's mean phase) is given, shift by the integer
    number of turns that keeps the frame mean closest to it, so the
    intercept time-series is differentiable instead of saw-toothed.
    """
    ph = np.unwrap(phase)
    if prev_mean is not None:
        turns = np.round((ph.mean() - prev_mean) / (2 * np.pi))
        ph -= turns * 2 * np.pi
    return ph


def ransac_line(x, y, n_iter=64, inlier_thresh=0.30, rng=None, seed=0):
    """Robust line fit y = m*x + b.

    Random 2-point hypotheses (evaluated as one broadcast — this runs per
    frame at 100 Hz, a Python loop here dominates the whole pipeline),
    inlier consensus, then a least-squares refit on the winning set.
    Returns (slope, intercept, inlier_ratio, resid_std) or None when no
    hypothesis gathers >= 25% inliers (frame is garbage).
    """
    n = x.size
    if n < 8:
        return None
    if rng is None:
        rng = np.random.default_rng(seed)
    i = rng.integers(0, n, size=n_iter)
    j = rng.integers(0, n, size=n_iter)
    ok = x[i] != x[j]
    if not ok.any():
        return None
    i, j = i[ok], j[ok]
    m = (y[j] - y[i]) / (x[j] - x[i])              # (h,)
    b = y[i] - m * x[i]
    resid = np.abs(y[None, :] - (m[:, None] * x[None, :] + b[:, None]))
    counts = (resid < inlier_thresh).sum(axis=1)   # inliers per hypothesis
    best = int(np.argmax(counts))
    best_count = int(counts[best])
    if best_count < max(4, n // 4):
        return None
    inl = resid[best] < inlier_thresh
    A = np.column_stack([x[inl], np.ones(best_count)])
    (m_f, b_f), *_ = np.linalg.lstsq(A, y[inl], rcond=None)
    r = y[inl] - (m_f * x[inl] + b_f)
    return float(m_f), float(b_f), best_count / n, float(r.std())


class FrameEstimator:
    """Stateful per-stream estimator: feed frames, get (slope, cfo_hz, ...).

    One instance per (node, source-MAC) stream. Keeps the previous frame's
    mean phase (for continuity correction) and intercept/timestamp (for the
    CFO finite difference).
    """

    def __init__(self, rng_seed=0):
        self._prev_mean = None
        self._prev_intercept = None
        self._prev_ts = None
        self._rng = np.random.default_rng(rng_seed)

    def feed(self, csi_vals, esp_ts_us):
        """Process one frame. Returns a dict or None if unusable.

        Keys: slope (rad/subcarrier, SFO proxy), intercept (rad),
        cfo_hz (from intercept delta; None on the first frame or after a
        timestamp glitch), inlier_ratio, resid_std.
        """
        csi = csi_to_complex(csi_vals)
        if csi is None:
            return None
        ph = np.angle(csi[_USABLE_IDX])           # sorted by physical k
        ph = unwrap_continuity(ph, self._prev_mean)
        fit = ransac_line(K_USABLE.astype(np.float64), ph, rng=self._rng)
        if fit is None:
            return None
        slope, intercept, inlier_ratio, resid_std = fit
        self._prev_mean = ph.mean()

        cfo_hz = None
        if self._prev_intercept is not None and esp_ts_us is not None:
            dt = (esp_ts_us - self._prev_ts) * 1e-6
            if 0 < dt < 1.0:                      # skip gaps/clock wraps
                dphi = np.angle(np.exp(1j * (intercept - self._prev_intercept)))
                cfo_hz = dphi / (2 * np.pi * dt)
        self._prev_intercept = intercept
        self._prev_ts = esp_ts_us

        return {
            "slope": slope,
            "intercept": intercept,
            "cfo_hz": cfo_hz,
            "inlier_ratio": inlier_ratio,
            "resid_std": resid_std,
        }


class WindowAggregator:
    """Collapse per-frame estimates into one robust observation per window.

    Medians over `window` accepted frames: outlier frames (bad RANSAC
    consensus, high residual) are rejected before they enter the window.
    Emits dicts with slope/cfo medians and spreads plus bookkeeping.
    """

    def __init__(self, window=64, min_inlier_ratio=0.6, max_resid=0.8):
        self.window = window
        self.min_inlier_ratio = min_inlier_ratio
        self.max_resid = max_resid
        self._buf = []

    def feed(self, est, ts_us, rssi):
        if est is None:
            return None
        if est["inlier_ratio"] < self.min_inlier_ratio:
            return None
        if est["resid_std"] > self.max_resid:
            return None
        self._buf.append((est, ts_us, rssi))
        if len(self._buf) < self.window:
            return None
        ests, times, rssis = zip(*self._buf)
        self._buf = []
        slopes = np.array([e["slope"] for e in ests])
        cfos = np.array([e["cfo_hz"] for e in ests
                         if e["cfo_hz"] is not None])
        return {
            "ts_us": int(np.median(times)),
            "rssi": float(np.mean(rssis)),
            "sfo": float(np.median(slopes)),
            "sfo_iqr": float(np.subtract(*np.percentile(slopes, [75, 25]))),
            "cfo": float(np.median(cfos)) if cfos.size else None,
            "cfo_iqr": (float(np.subtract(*np.percentile(cfos, [75, 25])))
                        if cfos.size else None),
            "n_frames": len(ests),
            "quality": float(np.mean([e["inlier_ratio"] for e in ests])),
        }
