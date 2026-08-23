#!/usr/bin/env python3
"""Synthetic ground-truth checks for the RFF phase DSP (no hardware needed).

The question this answers: **if you feed `pc/rff/dsp.py` a signal with a
known SFO slope and a known CFO, does it give them back?** Nothing else in
the repo asks that. `pc/test_occ_synth.py` does it for the amplitude
(occupancy) pipeline; this is the phase-domain equivalent.

Nothing here touches serial ports, `data/raw/`, or the network. It needs
only numpy and `pc/rff/dsp.py`.

Signal model
------------
`rff/dsp.py` states it as `phase(k) = slope*k + intercept + channel(k) +
noise`. The generator below builds exactly that and nothing else, so the
answer the estimator *should* return is known by construction.

Buffer layout, per `rff/dsp.py:22-26` — and the generator is verified
against `csi_to_complex` in test 0 before any other test runs:

  - 64 complex LLTF samples, stored as 128 interleaved int8 **[imag, real]**
    (`dsp.py:52` reads `iq[1::2] + 1j*iq[0::2]`, i.e. imag first);
  - FFT order: buffer index 0..31 = subcarriers 0..+31, index 32..63 =
    subcarriers -32..-1;
  - only |k| in 1..26 carry signal. DC (index 0) and the guard band
    (indices 27..37) are written as **exact** complex zero, which is what
    real captures contain (`docs/CODE_INVENTORY.md` C2/C3 measured
    precisely those 11 guard bins as exactly zero on 2026-08-21 data);
  - every sample is rounded and clipped to int8. Quantisation noise is
    part of what the estimator faces on real data, so it is part of every
    test here — there is no float-precision escape hatch.

Nominal subcarrier amplitude is `AMP` = 40 counts. That is a *choice*, not
a measurement: no captured amplitude was read for this file. Absolute
error figures scale roughly as 1/AMP, so treat them as characterising the
estimator at a stated operating point rather than as a prediction of field
performance.

Frame rate
----------
Tests 2 and 3 use 100 frames/s, because that is the beacon's transmit
cadence (`git show HEAD:firmware/csi_tx/main/main.c:17`,
`SEND_INTERVAL_MS 10`) and the rate `dsp.py:73-74` names. Note that
`docs/CODE_INVENTORY.md` D5 measures the *received* rate at 37-41 fps.
The ±50 Hz CFO limit demonstrated in test 3 is therefore the best case;
at 40 fps the unambiguous range is ±20 Hz.

Yardsticks (both read out of the tree, not from memory)
-------------------------------------------------------
`pc/exp_thermal_evidence.py:129-130`:
  BETWEEN_UNIT_SD = 0.00237 rad/sc  (sd over 3 units of their grand means)
  WITHIN_UNIT_SD  = 0.00570 rad/sc
`pc/exp_lot_hypothesis.py:85-86` twin scale: TWIN_DSFO = 0.00080 rad/sc.

The tests
---------
0. Generator round-trip. Must pass first; everything downstream is void
   otherwise.
1. Noiseless SFO recovery.
2. CFO recovery from the per-frame intercept rotation.
3. Aliasing boundary. **This documents a known and unavoidable limit, not
   a bug.** CFO is derived from a wrapped frame-to-frame phase difference
   (`dsp.py:142`), so any |CFO| above half the frame rate folds. Inside
   ±50 Hz at 100 fps it recovers; outside, it aliases by exactly the frame
   rate. Nothing in `pc/` flags this, so a genuinely large CFO reads as a
   small one.
4. Noise tolerance: SFO error vs per-subcarrier SNR, per frame and after
   the 64-frame window median.
5. Multipath: RANSAC vs `np.polyfit` on identical unwrapped phase, under
   two different channel shapes.
6. Resolution floor: smallest ΔSFO two synthetic units can be told apart
   at 3σ over 64-frame windows, against BETWEEN_UNIT_SD.
7. Guard/DC exclusion, pinned against the wrong mask in `pc/phase_skew.py`.
8. `WindowAggregator` on a synthetic stream.
9. **The one-turn unwrap failure.** Test 4 found that noise makes the
   estimator go *silent*; this one finds the case where it goes *confidently
   wrong* — `np.unwrap` (`dsp.py:64`) puts one subcarrier onto the wrong 2π
   branch, RANSAC then builds a consensus that straddles the break, and the
   returned slope is off by one turn over the lever arm between the two
   branch groups. See `docs/UNWRAP_DEFECT.md`.

Run: python pc/test_rff_synth.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rff import dsp                                        # noqa: E402

# dsp keeps the FFT-order tables private; a ground-truth generator has to
# build frames in exactly that layout, so it reads them rather than
# restating them (a restated copy could drift out of step silently).
K_OF_IDX = dsp._K_OF_IDX
USABLE_MASK = dsp._USABLE_MASK
USABLE_IDX = dsp._USABLE_IDX
K = dsp.K_USABLE.astype(np.float64)

AMP = 40.0                     # nominal per-subcarrier magnitude, counts
FPS = 100.0                    # beacon transmit cadence

BETWEEN_UNIT_SD = 0.00237      # pc/exp_thermal_evidence.py:129
WITHIN_UNIT_SD = 0.00570       # pc/exp_thermal_evidence.py:130
TWIN_DSFO = 0.00080            # pc/exp_lot_hypothesis.py:86

SEP_SIGMA = 3.0                # the tree's separability line, 5 hard-codings


# --------------------------------------------------------------- generator

def make_frame(slope, intercept, amp=AMP, channel=None, noise_sigma=0.0,
               rng=None):
    """One synthetic LLTF frame as int8 [imag, real, ...], length 128.

    slope        rad/subcarrier (the SFO signature)
    intercept    rad (common phase; its rate of change is the CFO)
    channel      complex array over the 52 usable bins, or None
    noise_sigma  sd of the complex AWGN added *per component*, so the
                 noise power per complex sample is 2*noise_sigma**2

    Returns (int8 array of 128, n_clipped).
    """
    k = K_OF_IDX[USABLE_MASK].astype(np.float64)
    h = amp * np.exp(1j * (slope * k + intercept))
    if channel is not None:
        h = h * np.asarray(channel)
    if noise_sigma:
        h = h + (rng.normal(0.0, noise_sigma, k.size)
                 + 1j * rng.normal(0.0, noise_sigma, k.size))

    csi = np.zeros(dsp.N_CPLX, dtype=complex)
    csi[USABLE_MASK] = h                     # DC + guards stay exactly 0

    buf = np.zeros(dsp.N_CPLX * 2, dtype=np.float64)
    buf[0::2] = csi.imag                     # imag first, per dsp.py:52
    buf[1::2] = csi.real
    q = np.rint(buf)
    n_clip = int((np.abs(q) > 127).sum())
    return np.clip(q, -128, 127).astype(np.int8), n_clip


def channel_ordered(frame):
    """The unwrapped usable-bin phase, ordered by physical k, as dsp sees it.

    Reproduces dsp.FrameEstimator.feed's first two steps so that a fit
    other than RANSAC can be run on byte-identical input (test 5).
    """
    csi = dsp.csi_to_complex(frame)
    return dsp.unwrap_continuity(np.angle(csi[USABLE_IDX]))


def two_ray(rho, tau_norm, theta):
    """Two-ray channel over the usable bins: 1 + rho*exp(j(theta - 2pi k tau)).

    Smooth, bounded, and NOT linear in k — the shape dsp.py's docstring
    names as the reason for RANSAC.
    """
    return 1.0 + rho * np.exp(1j * (theta - 2 * np.pi * K * tau_norm))


def stream(slope, cfo_hz=0.0, n=200, fps=FPS, amp=AMP, noise_sigma=0.0,
           channel_fn=None, seed=0, est_seed=7, b0=0.3):
    """Feed n synthetic frames through one FrameEstimator; return its dicts.

    The intercept advances by 2*pi*cfo_hz*dt per frame, which is what a
    residual carrier offset does, and esp_ts_us advances by dt.
    """
    rng = np.random.default_rng(seed)
    est = dsp.FrameEstimator(rng_seed=est_seed)
    dt = 1.0 / fps
    out, clipped = [], 0
    for i in range(n):
        b = 2 * np.pi * cfo_hz * i * dt + b0
        ch = channel_fn(i, rng) if channel_fn is not None else None
        f, nc = make_frame(slope, b, amp, ch, noise_sigma, rng)
        clipped += nc
        r = est.feed(f, int(round(i * dt * 1e6)))
        if r is not None:
            out.append(r)
    return out, clipped


def snr_to_sigma(snr_db, amp=AMP):
    """Per-component AWGN sd for a given per-subcarrier SNR in dB."""
    return np.sqrt(amp * amp / (10.0 ** (snr_db / 10.0)) / 2.0)


def hdr(n, title):
    print(f"\n--- {n}. {title} " + "-" * max(0, 58 - len(title)))


def verdict(ok, msg):
    print(f"[{'ok  ' if ok else 'FAIL'}] {msg}")
    return 0 if ok else 1


# ------------------------------------------------------------------ tests

def t0_roundtrip():
    """The generator must land on the phases it intended, or nothing holds."""
    hdr(0, "generator round-trip through csi_to_complex")
    fails = 0
    slope, intercept = 0.0123, 0.7
    frame, n_clip = make_frame(slope, intercept)

    ok = frame.dtype == np.int8 and frame.size == dsp.N_CPLX * 2
    fails += verdict(ok, f"frame is int8[{frame.size}], dtype {frame.dtype}, "
                         f"{n_clip} clipped")

    csi = dsp.csi_to_complex(frame)
    got = np.angle(csi[USABLE_IDX])
    want = slope * K + intercept
    err = np.abs(np.angle(np.exp(1j * (got - want))))
    ok = err.max() < 0.05
    fails += verdict(ok, f"phase round-trip: max |err| {err.max():.5f} rad, "
                         f"rms {err.std():.5f} rad (int8 quantisation at "
                         f"AMP={AMP:.0f})")

    null = np.where(~USABLE_MASK)[0]
    ok = np.all(csi[null] == 0) and null.size == 12
    fails += verdict(ok, f"DC+guard bins exactly zero: indices "
                         f"{null.min()},{null[1]}..{null.max()} "
                         f"({null.size} bins), usable {USABLE_MASK.sum()}")

    # Real captures are csi_len 256 (LLTF+HT-LTF merged); dsp stops at 128.
    f256 = np.concatenate([frame, np.zeros(128, dtype=np.int8)])
    a = dsp.FrameEstimator(rng_seed=5).feed(frame, 0)
    b = dsp.FrameEstimator(rng_seed=5).feed(f256, 0)
    ok = a["slope"] == b["slope"]
    fails += verdict(ok, f"len-256 frame gives the identical slope "
                         f"({a['slope']:+.7f}) — dsp reads only the LLTF")

    short = dsp.csi_to_complex(np.zeros(100, dtype=np.int8))
    fails += verdict(short is None, "short frame rejected (returns None)")
    return fails


def t1_noiseless_sfo():
    hdr(1, "noiseless SFO recovery")
    fails = 0
    print("    slope injected     recovered      error      |err|/BETWEEN_UNIT_SD")
    worst = 0.0
    for s in [0.0, -0.00040, 0.00080, 0.00237, 0.0120, 0.0500, 0.2000]:
        # Intercept swept by a 7.3 Hz CFO so frames are not byte-identical;
        # a fixed intercept makes every frame's quantisation error the same
        # and turns a random error into a fixed bias (reported below).
        ests, _ = stream(s, cfo_hz=7.3, n=200)
        sl = np.array([e["slope"] for e in ests])
        e = float(np.median(sl) - s)
        worst = max(worst, abs(e))
        print(f"    {s:+.5f}       {np.median(sl):+.7f}   {e:+.3e}   "
              f"{abs(e) / BETWEEN_UNIT_SD:8.4f}")
    ok = worst < 0.1 * BETWEEN_UNIT_SD
    fails += verdict(ok, f"worst median error {worst:.3e} rad/sc = "
                         f"{worst / BETWEEN_UNIT_SD:.3f}x BETWEEN_UNIT_SD "
                         f"({BETWEEN_UNIT_SD})")

    # The pathological case: identical frames, so quantisation is a bias.
    print("    fixed intercept (every frame byte-identical, no averaging):")
    worst_b = 0.0
    for s in [-0.00040, 0.00080, 0.00237]:
        ests, _ = stream(s, cfo_hz=0.0, n=8)
        e = float(np.median([x["slope"] for x in ests]) - s)
        worst_b = max(worst_b, abs(e))
        print(f"      slope {s:+.5f} -> bias {e:+.3e} "
              f"({abs(e) / BETWEEN_UNIT_SD:.3f}x BETWEEN_UNIT_SD)")
    print(f"      -> int8 quantisation alone can hold a fixed "
          f"{worst_b:.2e} rad/sc bias on a static intercept; it averages "
          f"out only because a real CFO keeps rotating the frame.")
    return fails


def t2_cfo():
    hdr(2, "CFO recovery from the intercept rotation (100 fps)")
    fails = 0
    print("    injected      median        mean        sd      err(median)")
    worst = 0.0
    for f_true in [0.0, 0.5, 5.0, 12.5, 25.0, -18.0, 49.0]:
        ests, _ = stream(-0.00040, cfo_hz=f_true, n=400)
        c = np.array([e["cfo_hz"] for e in ests if e["cfo_hz"] is not None])
        e = float(np.median(c) - f_true)
        worst = max(worst, abs(e))
        print(f"    {f_true:+7.2f} Hz   {np.median(c):+9.4f}  "
              f"{c.mean():+9.4f}  {c.std():7.4f}   {e:+.4f} Hz")
    ok = worst < 0.25
    fails += verdict(ok, f"worst |median CFO error| {worst:.4f} Hz over "
                         f"0..49 Hz")

    n_none = sum(1 for e in stream(0.0, 5.0, n=10)[0] if e["cfo_hz"] is None)
    fails += verdict(n_none == 1, f"exactly {n_none} frame reports cfo_hz "
                                  f"None (the first, no predecessor)")
    print("    note: the median is the biased statistic here, not the mean —"
          "\n    at 12.5 Hz the quantisation pattern repeats every 8 frames,"
          "\n    so the median of a periodic sequence sits off-centre while"
          "\n    the mean is exact. WindowAggregator medians (dsp.py:190).")
    return fails


def t3_aliasing():
    """Documented limit, not a defect — see the module docstring."""
    hdr(3, "aliasing boundary at +-fps/2 (known limit, not a bug)")
    fails = 0
    print(f"    unambiguous range at {FPS:.0f} fps: "
          f"+-{FPS / 2:.0f} Hz")
    print("    injected     recovered     folded-to-expected   verdict")
    for f_true in [45.0, 49.5, -49.5, 55.0, 70.0, 130.0, -80.0]:
        ests, _ = stream(-0.00040, cfo_hz=f_true, n=300)
        c = np.array([e["cfo_hz"] for e in ests if e["cfo_hz"] is not None])
        got = float(np.median(c))
        folded = (f_true + FPS / 2) % FPS - FPS / 2      # wrap into +-fps/2
        inside = abs(f_true) < FPS / 2
        ok = abs(got - folded) < 0.25
        tag = "recovers" if inside else f"ALIASES to {folded:+.1f}"
        print(f"    {f_true:+8.2f}    {got:+9.4f}      {folded:+9.2f}"
              f"          {tag}")
        fails += 0 if ok else 1
    fails += verdict(fails == 0,
                     "every case lands within 0.25 Hz of the folded value: "
                     "inside +-50 Hz it recovers, outside it aliases by "
                     "exactly one frame rate")
    print("    This is inherent: dsp.py:142 wraps the intercept difference"
          "\n    with np.angle before dividing by dt, so >pi per frame is"
          "\n    unrecoverable. Nothing in pc/ flags it, so a large true CFO"
          "\n    is reported as a small one with normal-looking IQR.")
    return fails


def t4_noise():
    hdr(4, "noise tolerance: SFO error vs per-subcarrier SNR")
    fails = 0
    s_true = 0.00237
    snrs = [40, 35, 30, 25, 20, 15, 12, 10, 8, 6, 4, 2, 0]
    print("     SNR   sigma   per-frame med|err|   p90        kept   clip%"
          "   window gate    64-frame window med|err|")
    per_frame, windowed = [], []
    for snr in snrs:
        sig = snr_to_sigma(snr)
        errs, kept, tot, clip = [], 0, 0, 0
        for seed in range(4):
            ests, nc = stream(s_true, cfo_hz=7.3, n=200,
                              noise_sigma=sig, seed=1000 + seed)
            tot += 200
            kept += len(ests)
            clip += nc
            errs += [e["slope"] - s_true for e in ests]
        a = np.abs(np.array(errs))
        med = float(np.median(a))
        per_frame.append(med)

        # what the analysis actually consumes: 64-frame window medians.
        # 2 independent streams x 8 windows, and the loop runs until 8
        # windows are *emitted*, so frames the gate rejects do not silently
        # shorten the sample at low SNR.
        werr, w_fed, w_pass = [], 0, 0
        for seed in range(2):
            agg = dsp.WindowAggregator(window=64)
            est = dsp.FrameEstimator(rng_seed=seed + 1)
            rng = np.random.default_rng(2000 + seed)
            got, i, dt = 0, 0, 1.0 / FPS
            while got < 8 and i < 64 * 8 * 4:
                f, _ = make_frame(s_true, 2 * np.pi * 7.3 * i * dt + 0.3,
                                  AMP, None, sig, rng)
                ts = int(round(i * dt * 1e6))
                e = est.feed(f, ts)
                w_fed += 1
                if e is not None and e["inlier_ratio"] >= 0.6 \
                        and e["resid_std"] <= 0.8:
                    w_pass += 1
                w = agg.feed(e, ts, -55.0)
                if w is not None:
                    werr.append(abs(w["sfo"] - s_true))
                    got += 1
                i += 1
        wmed = float(np.median(werr)) if len(werr) >= 8 else float("nan")
        windowed.append(wmed)
        gate = 100.0 * w_pass / w_fed
        shown = f"{wmed:.3e}" if np.isfinite(wmed) else (
            f"gate starved ({len(werr)} windows)")
        print(f"    {snr:3d} dB {sig:6.2f}   {med:.3e}        "
              f"{np.percentile(a, 90):.3e}  {kept}/{tot}  "
              f"{100.0 * clip / (tot * 128):5.2f}   {gate:5.1f}%        "
              f"{shown}")

    def crossing(vals, level):
        """SNR (dB) at which median |err| grows past `level`, log-interp."""
        for i in range(len(snrs) - 1):
            a_, b_ = vals[i], vals[i + 1]
            if not (np.isfinite(a_) and np.isfinite(b_)):
                continue
            if a_ <= level < b_:
                lo, hi = np.log(a_), np.log(b_)
                t = (np.log(level) - lo) / (hi - lo)
                return snrs[i] + t * (snrs[i + 1] - snrs[i])
        return float("nan")

    for name, vals in (("per-frame", per_frame),
                       ("64-frame window", windowed)):
        for lvl, lbl in ((BETWEEN_UNIT_SD, "BETWEEN_UNIT_SD"),
                         (TWIN_DSFO, "TWIN_DSFO")):
            c = crossing(vals, lvl)
            if np.isfinite(c):
                print(f"    {name:16s} error exceeds {lbl} ({lvl}) below "
                      f"{c:.1f} dB SNR")
            else:
                print(f"    {name:16s} error never reaches {lbl} ({lvl}) "
                      f"anywhere in the swept range — the "
                      f"inlier_ratio>=0.6 gate starves the window first")
    ok = per_frame[0] < 1e-4 and all(
        per_frame[i] <= per_frame[i + 1] * 1.35
        for i in range(len(per_frame) - 1))
    fails += verdict(ok, "error degrades monotonically with SNR and is "
                         f"{per_frame[0]:.1e} at 40 dB")
    return fails


def t5_multipath():
    hdr(5, "multipath: RANSAC vs np.polyfit on identical unwrapped phase")
    fails = 0
    s_true = 0.00237
    n_trial = 400

    def bench(chan_fn, label):
        er, ep, ir, rs = [], [], [], []
        rng = np.random.default_rng(11)
        for _ in range(n_trial):
            ch = chan_fn(rng)
            f, _ = make_frame(s_true, rng.uniform(-np.pi, np.pi), AMP, ch,
                              0.0, rng)
            ph = channel_ordered(f)
            fit = dsp.ransac_line(K, ph, rng=np.random.default_rng(3))
            if fit is None:
                continue
            er.append(fit[0] - s_true)
            ir.append(fit[2])
            rs.append(fit[3])
            ep.append(np.polyfit(K, ph, 1)[0] - s_true)
        er, ep = np.abs(er), np.abs(ep)
        ir, rs = np.array(ir), np.array(rs)
        gate = (ir >= 0.6) & (rs <= 0.8)      # WindowAggregator's own gate
        print(f"    {label}")
        print(f"      RANSAC   med|err| {np.median(er):.3e}  "
              f"p90 {np.percentile(er, 90):.3e}")
        print(f"      polyfit  med|err| {np.median(ep):.3e}  "
              f"p90 {np.percentile(ep, 90):.3e}")
        print(f"      polyfit/RANSAC = {np.median(ep) / np.median(er):.2f}x  "
              f"| inlier_ratio med {np.median(ir):.2f}, resid med "
              f"{np.median(rs):.3f}, passes WindowAggregator gate "
              f"{100 * gate.mean():.0f}%")
        return float(np.median(er)), float(np.median(ep))

    # (a) the case dsp.py's docstring names: sparse corrupted bins.
    def sparse(n_bad, mag):
        def f(rng):
            ch = np.ones(K.size, dtype=complex)
            idx = rng.choice(K.size, n_bad, replace=False)
            ch[idx] = np.exp(1j * rng.uniform(-mag, mag, n_bad))
            return ch
        return f

    a_r, a_p = bench(sparse(4, 1.5), "(a) 4/52 bins corrupted by +-1.5 rad")
    b_r, b_p = bench(sparse(12, 2.0), "(b) 12/52 bins corrupted by +-2.0 rad")

    # (c) smooth two-ray multipath: bounded, non-linear, no outliers.
    def tworay(rho, tau):
        def f(rng):
            return two_ray(rho, tau, rng.uniform(0, 2 * np.pi))
        return f

    c_r, c_p = bench(tworay(0.3, 0.010),
                     "(c) two-ray rho=0.30, tau=0.010 (ripple < 0.30 thresh)")
    d_r, d_p = bench(tworay(0.7, 0.020),
                     "(d) two-ray rho=0.70, tau=0.020 (ripple > 0.30 thresh)")

    ok = a_p / a_r > 3.0 and b_p / b_r > 3.0
    fails += verdict(ok, f"on sparse outliers RANSAC beats least squares by "
                         f"{a_p / a_r:.0f}x and {b_p / b_r:.0f}x — the "
                         f"design intent holds")
    ok2 = d_r <= d_p
    fails += verdict(ok2, f"on smooth two-ray multipath RANSAC is "
                          f"{d_r / d_p:.2f}x least squares "
                          f"({d_r:.3e} vs {d_p:.3e} rad/sc)")
    if not ok2:
        print("    ^ REPORTED AS MEASURED, NOT TUNED AWAY. When the channel"
              "\n      ripple exceeds inlier_thresh=0.30 rad (dsp.py:71) there"
              "\n      is no outlier minority to reject: RANSAC locks onto one"
              "\n      locally-straight arc of the ripple and inherits its"
              "\n      tilt, while least squares averages the ripple over the"
              "\n      whole band. dsp.py's docstring claims RANSAC is used"
              "\n      because 'multipath bumps ... become outliers'. That is"
              "\n      true of sparse corruption (a,b) and false of smooth"
              "\n      two-ray fading (d). Both errors here are >> "
              f"BETWEEN_UNIT_SD={BETWEEN_UNIT_SD},"
              "\n      and the WindowAggregator gate does not reject them.")
    return fails


def t6_resolution():
    hdr(6, "resolution floor: smallest separable dSFO over 64-frame windows")
    fails = 0
    s0 = 0.00237
    n_win = 20

    def win_sfos(slope, noise_sigma, seed):
        agg = dsp.WindowAggregator(window=64)
        est = dsp.FrameEstimator(rng_seed=seed + 1)
        rng = np.random.default_rng(seed)
        out, i, dt = [], 0, 1.0 / FPS
        while len(out) < n_win and i < n_win * 64 * 3:
            f, _ = make_frame(slope, 2 * np.pi * 7.3 * i * dt + 0.3,
                              AMP, None, noise_sigma, rng)
            ts = int(round(i * dt * 1e6))
            w = agg.feed(est.feed(f, ts), ts, -55.0)
            if w is not None:
                out.append(w["sfo"])
            i += 1
        return np.array(out)

    def sep(delta, sigma):
        a = win_sfos(s0, sigma, 100)
        b = win_sfos(s0 + delta, sigma, 200)
        sd = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2.0)
        return (abs(a.mean() - b.mean()) / sd if sd > 0 else np.inf), sd

    print(f"    criterion: {SEP_SIGMA:.0f}-sigma over {n_win} windows of 64 "
          f"frames each (1.28 s/window at {FPS:.0f} fps)")
    for label, sigma in (("quantisation only", 0.0),
                         ("20 dB SNR", snr_to_sigma(20)),
                         ("10 dB SNR", snr_to_sigma(10))):
        lo, hi = 1e-6, 3e-2                      # bisect on delta
        s_hi, sd = sep(hi, sigma)
        if s_hi < SEP_SIGMA:
            print(f"    {label:18s}: not separable even at dSFO={hi:.0e}")
            fails += 1
            continue
        for _ in range(18):
            mid = np.sqrt(lo * hi)
            s_mid, sd = sep(mid, sigma)
            if s_mid >= SEP_SIGMA:
                hi = mid
            else:
                lo = mid
        print(f"    {label:18s}: floor {hi:.3e} rad/sc   "
              f"(window sd {sd:.3e})   "
              f"= {hi / BETWEEN_UNIT_SD:8.4f} x BETWEEN_UNIT_SD, "
              f"{hi / TWIN_DSFO:8.4f} x TWIN_DSFO")
        if sigma == 0.0:
            quiet_floor = hi
    ok = quiet_floor < BETWEEN_UNIT_SD
    fails += verdict(ok, f"noiseless floor {quiet_floor:.2e} rad/sc is "
                         f"{BETWEEN_UNIT_SD / quiet_floor:.0f}x finer than "
                         f"BETWEEN_UNIT_SD — the estimator is not the "
                         f"limiting factor at that SNR")
    print("    Caveat: this is a *precision* floor under one stationary"
          "\n    channel. Test 5(d) shows a single smooth multipath"
          "\n    realisation biases the slope by ~1e-2 rad/sc, four orders"
          "\n    above the quiet floor and 4-15x BETWEEN_UNIT_SD. In the"
          "\n    field, multipath, not estimator noise, sets the resolution.")
    return fails


def t7_guards():
    hdr(7, "guard-band and DC exclusion (pins the phase_skew.py defect)")
    fails = 0
    s_true, b = 0.00237, 0.4
    frame, _ = make_frame(s_true, b)
    csi = dsp.csi_to_complex(frame)
    null = np.where(~USABLE_MASK)[0]

    fails += verdict(np.all(csi[null] == 0) and USABLE_MASK.sum() == 52,
                     f"52 usable bins; {null.size} null bins "
                     f"{null.tolist()} are exactly 0+0j")

    correct = dsp.ransac_line(K, channel_ordered(frame),
                              rng=np.random.default_rng(3))[0]
    fails += verdict(abs(correct - s_true) < 1e-4,
                     f"dsp mask       -> {correct:+.6f} (true {s_true:+.6f}, "
                     f"err {correct - s_true:+.2e})")

    # Wrong mask A: physical k kept, but DC and guards left in. np.angle of
    # an exact zero is 0, so 12 hard zeros enter the unwrap and the fit.
    allk = K_OF_IDX.astype(np.float64)
    order = np.argsort(allk)
    ph_all = dsp.unwrap_continuity(np.angle(csi[order]))
    bad_a = dsp.ransac_line(allk[order], ph_all,
                            rng=np.random.default_rng(3))
    bad_a = bad_a[0] if bad_a else float("nan")
    ok = abs(bad_a - s_true) > 10 * abs(correct - s_true)
    fails += verdict(ok, f"nulls included -> {bad_a:+.6f}  "
                         f"({abs(bad_a - s_true) / BETWEEN_UNIT_SD:.2f}x "
                         f"BETWEEN_UNIT_SD off) — mask demonstrably matters")

    # Wrong mask B: pc/phase_skew.py:31's actual recipe, verbatim — a
    # contiguous buffer-index mask fitted against buffer index.
    ps = np.r_[np.arange(6, 32), np.arange(33, 59)]
    ph_ps = dsp.unwrap_continuity(np.angle(csi[ps]))
    bad_b = dsp.ransac_line(ps.astype(np.float64), ph_ps,
                            rng=np.random.default_rng(3))
    bad_b = bad_b[0] if bad_b else float("nan")
    overlap = sorted(set(ps.tolist()) & set(null.tolist()))
    dropped = sorted(set(np.where(USABLE_MASK)[0].tolist()) - set(ps.tolist()))
    ok = abs(bad_b - s_true) > 10 * abs(correct - s_true)
    fails += verdict(ok, f"phase_skew.py -> {bad_b:+.6f} vs true "
                         f"{s_true:+.6f} — opposite sign, "
                         f"{abs(bad_b / s_true):.2f}x the magnitude")
    print(f"      it admits {len(overlap)} of the {null.size} null bins "
          f"{overlap}")
    print(f"      and drops real signal at buffer indices {dropped} "
          f"(k = +-1..5)")
    print("      Matches docs/CODE_INVENTORY.md C2 exactly. pc/fingerprint.py"
          "\n      (C3) has the same 64-bin blind spot in the amplitude"
          "\n      domain. Neither is on the rff/ path; this test exists so"
          "\n      the defect cannot be reintroduced into dsp.py unnoticed.")
    return fails


def t8_aggregator():
    hdr(8, "WindowAggregator over a synthetic stream")
    fails = 0
    s_true, f_cfo = 0.00237, 11.0
    agg = dsp.WindowAggregator(window=64)
    est = dsp.FrameEstimator(rng_seed=3)
    rng = np.random.default_rng(42)
    sigma = snr_to_sigma(25)
    dt = 1.0 / FPS
    wins = []
    for i in range(64 * 10):
        f, _ = make_frame(s_true, 2 * np.pi * f_cfo * i * dt + 0.3,
                          AMP, None, sigma, rng)
        ts = int(round(i * dt * 1e6))
        w = agg.feed(est.feed(f, ts), ts, -55.0 + 0.001 * i)
        if w is not None:
            wins.append(w)
    sfos = np.array([w["sfo"] for w in wins])
    cfos = np.array([w["cfo"] for w in wins])
    print(f"    {len(wins)} windows from 640 frames at 25 dB SNR")
    print(f"    sfo  median of medians {np.median(sfos):+.7f}  "
          f"(true {s_true:+.7f}, err {np.median(sfos) - s_true:+.2e})")
    print(f"    cfo  median of medians {np.median(cfos):+.4f} Hz  "
          f"(true {f_cfo:+.1f}, err {np.median(cfos) - f_cfo:+.4f} Hz)")
    print(f"    sfo_iqr median {np.median([w['sfo_iqr'] for w in wins]):.3e}"
          f"   cfo_iqr median "
          f"{np.median([w['cfo_iqr'] for w in wins]):.4f} Hz"
          f"   quality {np.mean([w['quality'] for w in wins]):.3f}")

    fails += verdict(len(wins) == 10, f"emitted {len(wins)} windows for 640 "
                                      f"clean frames (expected 10)")
    fails += verdict(all(w["n_frames"] == 64 for w in wins),
                     "every window carries n_frames=64")
    fails += verdict(abs(np.median(sfos) - s_true) < 0.1 * BETWEEN_UNIT_SD,
                     f"window sfo within 0.1x BETWEEN_UNIT_SD of truth")
    fails += verdict(abs(np.median(cfos) - f_cfo) < 0.25,
                     f"window cfo within 0.25 Hz of truth")

    # Garbage must be rejected rather than averaged.
    agg2 = dsp.WindowAggregator(window=64)
    est2 = dsp.FrameEstimator(rng_seed=4)
    rng2 = np.random.default_rng(9)
    emitted, produced = 0, 0
    for i in range(64 * 6):
        vals = rng2.integers(-127, 128, dsp.N_CPLX * 2).astype(np.int8)
        r = est2.feed(vals, int(round(i * dt * 1e6)))
        produced += r is not None
        if agg2.feed(r, i, -90.0) is not None:
            emitted += 1
    fails += verdict(emitted == 0,
                     f"uniform-random int8 frames: {produced}/384 fit at all, "
                     f"{emitted} windows emitted (gate holds)")
    return fails



# ------------------------------------------- test 9 helpers (the turn defect)

# `two_ray` above builds its channel on K (sorted -26..+26) while `make_frame`
# applies the channel in FFT order (+1..+26, -26..-1) — see the assert in
# t9_one_turn. The helpers below build in FFT order so the channel that
# reaches the estimator is the one that was written down.
KF = K_OF_IDX[USABLE_MASK].astype(np.float64)   # the order make_frame applies

TURN32 = 2 * np.pi / 32          # the offset docs/AMBIENT_SEPARATION.md §5 saw


def sym_two_ray(rho, tau, rng, dead_k=None):
    """Two echoes at -tau and +tau samples, plus an optional dead subcarrier.

    The +/-tau pair is deliberate: a one-sided echo adds its own group delay
    and would bias the slope, so ground truth would stop being the injected
    slope. A symmetric pair has zero mean group delay, so the injected slope
    stays the right answer and any offset the estimator returns is its own.

    `dead_k` sets one subcarrier's channel gain to exactly 0, so that bin
    carries noise only and its phase is uniform on (-pi, pi]. That is the
    condition measured on node 68 (`d0wd`), where subcarrier k = +1 has
    |CSI| = 3.0 counts in 100 % of frames against a band median of 20.0
    (docs/UNWRAP_DEFECT.md §2).
    """
    c = (1.0 + rho * np.exp(1j * (rng.uniform(0, 2 * np.pi)
                                  - 2 * np.pi * KF * tau))
             + rho * np.exp(1j * (rng.uniform(0, 2 * np.pi)
                                  + 2 * np.pi * KF * tau)))
    if dead_k is not None:
        c[KF == dead_k] = 0.0
    return c


def ransac_inliers(x, y, rng):
    """`dsp.ransac_line` (dsp.py:71-103) verbatim, plus the inlier mask.

    The mask is not on dsp's public return, and t9 needs it to measure the
    lever arm. Constants are read from dsp so this cannot drift silently.
    """
    n = x.size
    if n < 8:
        return None
    i = rng.integers(0, n, size=64)
    j = rng.integers(0, n, size=64)
    ok = x[i] != x[j]
    if not ok.any():
        return None
    i, j = i[ok], j[ok]
    m = (y[j] - y[i]) / (x[j] - x[i])
    b = y[i] - m * x[i]
    resid = np.abs(y[None, :] - (m[:, None] * x[None, :] + b[:, None]))
    counts = (resid < 0.30).sum(axis=1)
    best = int(np.argmax(counts))
    best_count = int(counts[best])
    if best_count < max(4, n // 4):
        return None
    inl = resid[best] < 0.30
    A = np.column_stack([x[inl], np.ones(best_count)])
    (m_f, b_f), *_ = np.linalg.lstsq(A, y[inl], rcond=None)
    r = y[inl] - (m_f * x[inl] + b_f)
    return float(m_f), float(b_f), best_count / n, float(r.std()), inl


def fit_coherence(ph_raw, m, b):
    """|mean exp(j * residual)| over ALL 52 bins, residual taken un-unwrapped.

    exp(j*2*pi) == 1, so this is blind to which branch any bin was put on:
    it cannot be measuring the unwrap, only the slope. A fit that is one turn
    out over the band leaves a residual that ramps through several turns, and
    the sum cancels. Computed on the *inliers* it is useless (they are within
    0.30 rad of the line by construction) — the 52-bin version is the point.
    """
    return float(np.abs(np.sum(np.exp(1j * (ph_raw - (m * K + b))))) / K.size)


def _t9_run(slope, snr_db, rho, tau, dead_k, n, seed):
    """n frames -> (slope, inlier_ratio, resid_std, coherence, slope with the
    branching fixed, lever arm)."""
    sig = snr_to_sigma(snr_db)
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        ch = sym_two_ray(rho, tau, rng, dead_k)
        f, _ = make_frame(slope, 2 * np.pi * 7.3 * i / FPS + 0.3, AMP, ch,
                          sig, rng)
        ph = np.angle(dsp.csi_to_complex(f)[USABLE_IDX])
        uw = np.unwrap(ph)
        fit = ransac_inliers(K, uw, np.random.default_rng(3))
        if fit is None:
            continue
        m, b, ir, rs, inl = fit

        # The control: the same frame, the same RANSAC, the same seed, with
        # every bin forced onto one branch around the *known* injected slope
        # instead of np.unwrap's serial choice. Nothing else differs, so any
        # difference between `m` and `m_fix` is the unwrap and only the unwrap.
        ph_fix = slope * K + np.angle(np.exp(1j * (ph - slope * K)))
        gfit = ransac_inliers(K, ph_fix, np.random.default_rng(3))
        m_fix = gfit[0] if gfit is not None else np.nan

        # Geometry: split the winning consensus by which branch np.unwrap put
        # each bin on, relative to that same one-branch reference. A line that
        # straddles the break has to climb dturns whole turns between the two
        # groups, so its slope is off by 2*pi*dturns / (their k separation).
        w = np.round((uw - ph_fix) / (2 * np.pi)).astype(int)[inl]
        lever = pred = np.nan
        if w.max() != w.min():
            lever = (np.mean(K[inl][w == w.max()])
                     - np.mean(K[inl][w == w.min()]))
            if lever != 0.0:
                pred = 2 * np.pi * (w.max() - w.min()) / lever
        out.append((m, ir, rs, fit_coherence(ph, m, b), m_fix, lever, pred))
    return np.array(out)


def t9_one_turn():
    """The failure test 4 missed: not noisy, wrong — and wrong by 2*pi/32."""
    hdr(9, "one-turn unwrap failure (confidently wrong, not noisy)")
    fails = 0
    s_true = 0.142        # the slope node 68 actually reports for 1c:ce:51:f3:0d:fa
    n = 1500

    ok = not np.array_equal(KF, K)
    print(f"    note: make_frame applies `channel` in FFT order "
          f"({int(KF[0]):+d},{int(KF[1]):+d},..,{int(KF[-1]):+d}) while "
          f"two_ray builds on sorted K "
          f"({int(K[0]):+d},..,{int(K[-1]):+d}); orders differ: {ok}.")
    print("    Test 5 is left as it stands (the ordering does not change its"
          "\n    verdict — see docs/UNWRAP_DEFECT.md §7); t9 builds in FFT order.")

    # "turn-out" is defined by size only — an error far outside anything the
    # estimator's own noise produces — so that nothing about 2*pi/32 is
    # assumed by the definition. 9.1 then measures what the size actually is.
    def turnout(a):
        return np.abs(a[:, 0] - s_true) > 0.05

    # 9.1 --- what it takes to fire: one dead bin, at full signal strength
    print(f"\n    9.1  slope {s_true:+.3f}, band SNR 25 dB, symmetric two-ray"
          f" rho=0.60 tau=0.08 samples")
    print("      dead bin   kept   median slope   |err| p50 (right frames)"
          "   turn-outs (|err|>0.05)")
    res = {}
    for dead in (1, None):
        a = _t9_run(s_true, 25, 0.60, 0.08, dead, n, 20260822)
        res[dead] = a
        t = turnout(a)
        print(f"      {str(dead):8s} {a.shape[0]:6d}   {np.median(a[:, 0]):+.5f}"
              f"          {np.median(np.abs(a[~t, 0] - s_true)):.5f}"
              f"              {int(t.sum()):4d}  ({100 * t.mean():5.2f}%)")
    a_dead, a_ok = res[1], res[None]
    t_dead, t_ok = turnout(a_dead), turnout(a_ok)
    fails += verdict(t_dead.mean() > 0.01 and t_ok.mean() == 0.0,
                     f"the dead subcarrier is necessary and sufficient: "
                     f"{100 * t_dead.mean():.2f}% turn-outs with it, "
                     f"{100 * t_ok.mean():.2f}% without, same channel and SNR")

    off = a_dead[t_dead, 0] - s_true
    fix = a_dead[t_dead, 4] - s_true
    lev, pred = a_dead[t_dead, 5], a_dead[t_dead, 6]
    fin = np.isfinite(lev)
    print(f"      the wrong frames are not scattered: |offset| p10..p90 "
          f"{np.percentile(np.abs(off), 10):.4f}"
          f"..{np.percentile(np.abs(off), 90):.4f},"
          f" median {np.median(np.abs(off)):.5f}")
    print(f"      same {int(t_dead.sum())} frames, same RANSAC, same seed, "
          f"branching forced onto one branch:\n      median |error| falls from "
          f"{np.median(np.abs(off)):.5f} to "
          f"{np.median(np.abs(fix)):.5f} rad/sc")
    fails += verdict(np.median(np.abs(fix)) < 0.05 * np.median(np.abs(off)),
                     f"the unwrap is the whole cause: fixing the branching "
                     f"and changing nothing else removes "
                     f"{100 * (1 - np.median(np.abs(fix)) / np.median(np.abs(off))):.1f}% "
                     f"of the error")
    print(f"      {int(fin.sum())} of {int(t_dead.sum())} have their winning "
          f"consensus split across two or more 2pi branches;"
          f"\n      for those the two groups' inlier centroids sit "
          f"{np.median(np.abs(lev[fin])):.1f} subcarriers apart (median) and"
          f"\n      2pi*dturns/that predicts the measured offset to "
          f"{np.median(np.abs(pred[fin] - off[fin])):.4f} rad/sc, median.")
    print(f"      Written as one turn over a lever arm, the measured offset is "
          f"2pi/{2 * np.pi / np.median(np.abs(off)):.1f} here\n      and "
          f"2pi/30.7 on node 68's real frames for 1c:ce:51:f3:0d:fa, whose "
          f"winning\n      consensus splits into groups whose inlier centroids "
          f"sit 32.0 subcarriers apart\n      (IQR 31.5..32.5). That is the "
          f"whole of where docs/AMBIENT_SEPARATION.md §5's\n      2pi/32 = "
          f"{TURN32:.4f} comes from: a per-frame lever arm, not a constant of"
          f"\n      the estimator, not a span of the 52-wide usable set "
          f"(2pi/52 = {2 * np.pi / 52:.4f}),\n      and not a count of "
          f"subcarriers in the fit.")

    # 9.2 --- the gate cannot see it
    print("\n    9.2  what the pipeline's own quality numbers say about the"
          " wrong frames")
    g = ~t_dead
    print(f"      inlier_ratio  correct {np.median(a_dead[g, 1]):.3f}   "
          f"turn-out {np.median(a_dead[t_dead, 1]):.3f}")
    print(f"      resid_std     correct {np.median(a_dead[g, 2]):.3f}   "
          f"turn-out {np.median(a_dead[t_dead, 2]):.3f}")
    shipped = (a_dead[t_dead, 1] >= 0.6) & (a_dead[t_dead, 2] <= 0.8)
    loose = (a_dead[t_dead, 1] >= 0.3) & (a_dead[t_dead, 2] <= 0.8)
    print(f"      turn-outs admitted by WindowAggregator(64, 0.6, 0.8): "
          f"{100 * shipped.mean():.1f}%;  at min_inlier 0.3 "
          f"(docs/AMBIENT_SEPARATION.md §3.5): {100 * loose.mean():.1f}%")
    fails += verdict((a_dead[t_dead, 2] <= 0.8).all(),
                     f"the residual gate is blind to all "
                     f"{int(t_dead.sum())} of them: worst turn-out resid_std "
                     f"{a_dead[t_dead, 2].max():.3f} against max_resid = 0.8")
    print("      inlier_ratio is not a usable flag either, because its sign is"
          "\n      not stable: turn-outs sit *below* the correct frames here and"
          "\n      *above* them on node 68's real frames for 1c:ce:51:f3:0d:fa"
          "\n      (0.404 against 0.365, docs/UNWRAP_DEFECT.md §5).")

    # 9.3 --- the SNR sweep test 4 should have carried
    print("\n    9.2b  SNR sweep, flat channel, dead bin at k=+1 (no multipath)")
    print("       SNR   kept   turn-out rate   median offset")
    onset = None
    for snr in (25, 15, 10, 8, 6, 4, 2, 0):
        a = _t9_run(s_true, snr, 0.0, 0.0, 1, 800, 4242)
        t = turnout(a)
        if t.mean() > 0 and onset is None:
            onset = snr
        off = np.median(np.abs(a[t, 0] - s_true)) if t.any() else float("nan")
        print(f"      {snr:4d} {a.shape[0]:6d}      {100 * t.mean():6.2f}%"
              f"        {off:.5f}")
    print(f"      -> with a flat channel it needs {onset} dB before it fires "
          f"at all; 9.1 fires\n         at 25 dB, so this is not an SNR "
          f"failure — it is a channel-shape failure.")

    # 9.4 --- a detector that does work
    print("\n    9.3  detector: branch-invariant coherence of the fitted line")
    c_ok, c_bad = a_dead[g, 3], a_dead[t_dead, 3]
    print(f"      C over all 52 bins:  correct median {np.median(c_ok):.3f} "
          f"(p1 {np.percentile(c_ok, 1):.3f})   turn-out median "
          f"{np.median(c_bad):.3f} (p99 {np.percentile(c_bad, 99):.3f})")
    rec = float((c_bad < 0.5).mean())
    fpr = float((c_ok < 0.5).mean())
    print(f"      threshold C < 0.5:  recall {100 * rec:.1f}%   "
          f"false-positive rate {100 * fpr:.2f}%")
    fails += verdict(rec == 1.0 and fpr <= 0.001,
                     f"C < 0.5 separates the two populations completely on "
                     f"{a_dead.shape[0]} frames "
                     f"({int(t_dead.sum())} wrong, {int(g.sum())} right)")

    print("\n    REPORTED AS MEASURED, NOT TUNED AWAY. The next verdict is the"
          "\n    defect itself and it is expected to FAIL against dsp.py as it"
          "\n    stands. dsp.py was deliberately not changed — docs/"
          "UNWRAP_DEFECT.md §6\n    gives the three candidate repairs that were"
          " built and measured, and why\n    none of them is clearly correct."
          " Fix dsp.py and this verdict turns green.")
    fails += verdict(t_dead.mean() <= 0.001,
                     f"the estimator should not return a one-turn-out slope "
                     f"on a 25 dB frame: measured {100 * t_dead.mean():.2f}% "
                     f"({int(t_dead.sum())} of {a_dead.shape[0]})")
    return fails


def main():
    print("RFF synthetic ground truth — pc/rff/dsp.py")
    print(f"numpy {np.__version__} | AMP={AMP:.0f} counts | {FPS:.0f} fps | "
          f"52 usable subcarriers")
    print(f"yardsticks: BETWEEN_UNIT_SD={BETWEEN_UNIT_SD}  "
          f"WITHIN_UNIT_SD={WITHIN_UNIT_SD}  TWIN_DSFO={TWIN_DSFO} rad/sc")

    fails = t0_roundtrip()
    if fails:
        print("\nGenerator round-trip failed; the remaining tests would be "
              "meaningless. Stopping.")
        return 2
    for t in (t1_noiseless_sfo, t2_cfo, t3_aliasing, t4_noise,
              t5_multipath, t6_resolution, t7_guards, t8_aggregator,
              t9_one_turn):
        fails += t()

    print()
    print("=" * 70)
    print("ALL OK" if not fails else f"{fails} FAILURES")
    print("Tolerances here were set from the physics and from the repo's own"
          "\nyardsticks before the numbers were seen, and were not relaxed to"
          "\nmake anything pass. Any FAIL above is a real measured result.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
