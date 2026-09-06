#!/usr/bin/env python3
r"""Calibrate the frame-admission gates from synthetic ground truth, then
re-run the census at the calibrated gates as a parallel branch.

The criterion this script tests against was frozen in
`docs/GATE_CALIBRATION.md` §2 **before this file was written**:

    C1  median |slope_hat - slope_true| <= 0.50 * BETWEEN_UNIT_SD
    C2  p90    |slope_hat - slope_true| <= 1.00 * BETWEEN_UNIT_SD

evaluated over the frames a gate admits, on synthetic streams whose true
slope is known. C3 (the "noise wearing a MAC" rule) and the swept grid are
also frozen there. Nothing in this file chooses a threshold; it measures
where the estimator stops meeting the frozen criterion.

Design constraints, and why
---------------------------
* **`pc/rff/dsp.py` is imported and used exactly as shipped. No default
  anywhere is changed** (`docs/V2_SPEC.md` §5.5). Loosened thresholds are
  passed as arguments only. The shipped-gate branch and the loosened branch
  are computed in the SAME pass over the SAME frames and reported side by
  side; neither overwrites the other.
* **Replay from the start of each file with a fresh estimator.**
  `FrameEstimator` owns a per-instance RNG (`pc/rff/dsp.py:118`) handed to
  `ransac_line` every frame (`:132`), which draws two
  `rng.integers(..., size=64)` per call (`:85-86`), so the generator
  advances once per fitted frame and a slope depends on how many frames
  preceded it in that stream (`docs/V2_SPEC.md` §5.5 correction). The
  `part`/`merge` split pickles estimator state forward so an N-part run is
  frame-for-frame what one uninterrupted pass would have produced.
* **One replay serves every gate.** `WindowAggregator.feed` (`dsp.py:170`)
  gates on values `FrameEstimator.feed` has already returned and never
  touches estimator state, so the per-frame slope stream is gate-
  independent. Running K aggregators at K thresholds off one estimator is
  therefore *exactly* K separate runs, not an approximation — and it is the
  only way to compare gates without the RNG path-dependence above
  invalidating the comparison.
* **Screen corrupt rows before anything else.** The d0wd fabricates MACs
  from corrupt rows (126 of 166 addresses,
  `docs/COLOCATED_0823.md`). Loosening a gate without screening would
  inflate the apparent gain with fake devices. Two independent routes, as
  `docs/OVERNIGHT_2026-08-22.md` §1 requires: field plausibility on six
  columns, and a width-9 circular median filter on `dropped`.
* **`csi_data` is a quoted comma-separated list nested in the CSV.** Parsed
  with `csv.reader`, never a naive `line.split(",")`.
* Read-only on `data/raw/`. No serial port is opened. Nothing is staged,
  committed or pushed. `pc/capture.py:compute_cfo`, `pc/phase_skew.py` and
  `pc/fingerprint.py` are not used (`docs/CODE_INVENTORY.md` §4.2).

Usage (from the repo root; state goes to $GATE_CACHE, default /tmp/gatecal)
--------------------------------------------------------------------------
  python3 pc/exp_gate_calibration.py calib
  python3 pc/exp_gate_calibration.py scan data/raw/d0wd_20260823_014740.csv \
      --tag d0wd --part 0 --nparts 3 --gates 0.60,0.35,0.20
  python3 pc/exp_gate_calibration.py merge --tag d0wd --nparts 3
  python3 pc/exp_gate_calibration.py report --tags d0wd,s3
"""
import argparse
import csv
import os
import pickle
import sys
import time
import zlib
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rff import dsp                                        # noqa: E402
from rff.dsp import FrameEstimator, WindowAggregator       # noqa: E402
from occ import BEACON_MACS                                # noqa: E402

CACHE = os.environ.get("GATE_CACHE", "/tmp/gatecal")

# --- the project's yardsticks (pc/exp_thermal_evidence.py:129-130) -------
BETWEEN_UNIT_SD = 0.00237
WITHIN_UNIT_SD = 0.00570
TWIN_DSFO = 0.00080

# --- the frozen criterion, docs/GATE_CALIBRATION.md §2 ------------------
C1_FRAC = 0.50          # median |err| <= C1_FRAC * BETWEEN_UNIT_SD
C2_FRAC = 1.00          # p90    |err| <= C2_FRAC * BETWEEN_UNIT_SD
C1 = C1_FRAC * BETWEEN_UNIT_SD
C2 = C2_FRAC * BETWEEN_UNIT_SD
STRICT_FRAC = 0.25      # secondary column, §2.1

# --- the frozen grid, docs/GATE_CALIBRATION.md §2.4 ---------------------
INLIER_GRID = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60,
               0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
RESID_GRID = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.80]

# shipped values, pc/rff/dsp.py:164 — read from the library, not restated,
# so this file cannot drift away from what ships.
import inspect                                             # noqa: E402
_P = inspect.signature(WindowAggregator.__init__).parameters
SHIP_INLIER = _P["min_inlier_ratio"].default
SHIP_RESID = _P["max_resid"].default
SHIP_WINDOW = _P["window"].default

# --- field-plausibility screen, docs/OVERNIGHT_2026-08-22.md §1 ---------
CSI_LEN_OK = (128, 256, 384)
NF_LO, NF_HI = -110, -70
RSSI_LO, RSSI_HI = -100, -10
MED_W, MED_TOL, U16 = 9, 100, 65536

COLS = ["pc_time_us", "label", "seq", "mac", "rssi", "noise_floor",
        "channel", "esp_timestamp_us", "len", "csi_data", "node_id",
        "env_id", "dropped"]


# ======================================================================
#  PART A — synthetic calibration
# ======================================================================

def make_frame(slope, intercept, amp, channel, noise_sigma, rng):
    """One synthetic LLTF frame as int8 [imag, real, ...], length 128.

    Byte-identical construction to pc/test_rff_synth.py:113-141, which
    round-trips through dsp.csi_to_complex to < 0.05 rad (its test 0) and
    recovers SFO to 2.44e-05 noiselessly (its test 1).
    """
    k = dsp._K_OF_IDX[dsp._USABLE_MASK].astype(np.float64)
    h = amp * np.exp(1j * (slope * k + intercept))
    if channel is not None:
        h = h * np.asarray(channel)
    if noise_sigma:
        h = h + (rng.normal(0.0, noise_sigma, k.size)
                 + 1j * rng.normal(0.0, noise_sigma, k.size))
    csi = np.zeros(dsp.N_CPLX, dtype=complex)
    csi[dsp._USABLE_MASK] = h
    buf = np.zeros(dsp.N_CPLX * 2, dtype=np.float64)
    buf[0::2] = csi.imag
    buf[1::2] = csi.real
    return np.clip(np.rint(buf), -128, 127).astype(np.int8)


def snr_to_sigma(snr_db, amp):
    return np.sqrt(amp * amp / (10.0 ** (snr_db / 10.0)) / 2.0)


def two_ray(rho, tau, theta):
    K = dsp.K_USABLE.astype(np.float64)
    return 1.0 + rho * np.exp(1j * (theta - 2 * np.pi * K * tau))


def gen_condition(slope, snr_db, rho, tau, n, seed, amp=40.0, fps=100.0):
    """Replay one synthetic stream from its start with a fresh estimator.

    Returns (inlier_ratio, resid_std, slope_err) arrays over fitted frames.
    """
    rng = np.random.default_rng(seed)
    est = FrameEstimator(rng_seed=seed % 97)
    sig = snr_to_sigma(snr_db, amp) if snr_db is not None else 0.0
    dt = 1.0 / fps
    ir, rs, er = [], [], []
    for i in range(n):
        b = 2 * np.pi * 7.3 * i * dt + 0.3
        ch = two_ray(rho, tau, rng.uniform(0, 2 * np.pi)) if rho else None
        f = make_frame(slope, b, amp, ch, sig, rng)
        e = est.feed(f, int(round(i * dt * 1e6)))
        if e is None:
            continue
        ir.append(e["inlier_ratio"])
        rs.append(e["resid_std"])
        er.append(e["slope"] - slope)
    return (np.array(ir), np.array(rs), np.abs(np.array(er)))


# The condition families. Chosen in docs/GATE_CALIBRATION.md §3 to bracket
# the inlier_ratio distribution real ambient sources occupy; the criterion
# is not matched to the data, only the conditions are.
CONDITIONS = [
    # label,               snr_db, rho,  tau
    ("clean 30 dB",            30, 0.0,  0.0),
    ("clean 20 dB",            20, 0.0,  0.0),
    ("clean 12 dB",            12, 0.0,  0.0),
    ("clean  8 dB",             8, 0.0,  0.0),
    ("clean  4 dB",             4, 0.0,  0.0),
    ("clean  0 dB",             0, 0.0,  0.0),
    ("mp rho.3 tau.010 20 dB",  20, 0.3, 0.010),
    ("mp rho.3 tau.010 10 dB",  10, 0.3, 0.010),
    ("mp rho.7 tau.020 20 dB",  20, 0.7, 0.020),
    ("mp rho.7 tau.020 10 dB",  10, 0.7, 0.020),
    ("mp rho.7 tau.050 20 dB",  20, 0.7, 0.050),
    ("mp rho.9 tau.020 15 dB",  15, 0.9, 0.020),
    # added after 4 measured the real operating point: families that land
    # inside the resid_std 0.07-0.23 band every real source occupies.
    ("clean 18 dB",            18, 0.0,  0.0),
    ("clean 16 dB",            16, 0.0,  0.0),
    ("clean 14 dB",            14, 0.0,  0.0),
    ("clean 10 dB",            10, 0.0,  0.0),
    ("mp rho.15 tau.010 16 dB", 16, 0.15, 0.010),
    ("mp rho.15 tau.010 10 dB", 10, 0.15, 0.010),
    ("mp rho.5 tau.015 16 dB",  16, 0.5, 0.015),
    ("mp rho.5 tau.005 16 dB",  16, 0.5, 0.005),
]

IBINS = [0.0, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60,
         0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.001]


def q(a, p):
    return float(np.percentile(a, p)) if a.size else float("nan")


def cmd_calib(args):
    slope_true = 0.00237          # a between-unit-sized slope, as test 4 uses
    n = args.frames
    print("=== SYNTHETIC GATE CALIBRATION ===")
    print(f"criterion frozen in docs/GATE_CALIBRATION.md 2 BEFORE this run:")
    print(f"  C1 median |err| <= {C1_FRAC:.2f} x BETWEEN_UNIT_SD = {C1:.6f} rad/sc")
    print(f"  C2 p90    |err| <= {C2_FRAC:.2f} x BETWEEN_UNIT_SD = {C2:.6f} rad/sc")
    print(f"shipped gate: min_inlier {SHIP_INLIER:g}, max_resid {SHIP_RESID:g} "
          f"(read from rff.dsp.WindowAggregator)")
    print(f"true slope {slope_true:+.5f} rad/sc, {n} frames x "
          f"{args.reps} seeds per condition\n")

    allir, allrs, aller, alllab = [], [], [], []
    print(f"{'condition':<26}{'fit':>7}{'ir med':>8}{'ir p10':>8}"
          f"{'rs med':>8}{'rs max':>8}{'|err| med':>11}{'p90':>11}")
    per_cond = {}
    for lab, snr, rho, tau in CONDITIONS:
        ir, rs, er = [], [], []
        for k in range(args.reps):
            # zlib.crc32, not hash(): Python salts str hashing per process
            # (PYTHONHASHSEED), so hash()-derived seeds would make this
            # sweep unreproducible between runs. Rule A, CLAUDE.md.
            seed = (zlib.crc32(f"{lab}|{k}".encode()) % (2 ** 31))
            a, b, c = gen_condition(slope_true, snr, rho, tau, n, seed=seed)
            ir.append(a); rs.append(b); er.append(c)
        ir = np.concatenate(ir); rs = np.concatenate(rs); er = np.concatenate(er)
        per_cond[lab] = (ir, rs, er)
        allir.append(ir); allrs.append(rs); aller.append(er)
        alllab += [lab] * ir.size
        print(f"{lab:<26}{ir.size:>7}{np.median(ir):>8.3f}{q(ir,10):>8.3f}"
              f"{np.median(rs):>8.3f}{rs.max():>8.3f}"
              f"{np.median(er):>11.3e}{q(er,90):>11.3e}")
    IR = np.concatenate(allir); RS = np.concatenate(allrs)
    ER = np.concatenate(aller); LAB = np.array(alllab)

    # ---- 1. is |err| predictable from inlier_ratio alone? --------------
    print(f"\n--- error conditional on inlier_ratio (pooled over all "
          f"{len(CONDITIONS)} conditions, {IR.size} frames) ---")
    print(f"{'inlier bin':<14}{'n':>9}{'med |err|':>11}{'/sd':>7}"
          f"{'p90 |err|':>11}{'/sd':>7}{'  C1':>5}{'  C2':>5}")
    for lo, hi in zip(IBINS[:-1], IBINS[1:]):
        m = (IR >= lo) & (IR < hi)
        if m.sum() < 30:
            continue
        e = ER[m]
        med, p90 = float(np.median(e)), q(e, 90)
        print(f"[{lo:.2f},{hi:.2f})  {m.sum():>9}{med:>11.3e}"
              f"{med/BETWEEN_UNIT_SD:>7.2f}{p90:>11.3e}"
              f"{p90/BETWEEN_UNIT_SD:>7.2f}"
              f"{'  ok' if med <= C1 else ' FAIL':>5}"
              f"{'  ok' if p90 <= C2 else ' FAIL':>5}")

    # ---- 1b. does that conditional hold ACROSS conditions? -------------
    print("\n--- stability of that conditional: med |err| / BETWEEN_UNIT_SD "
          "per (condition, inlier bin) ---")
    cb = [(0.15, 0.30), (0.30, 0.45), (0.45, 0.60), (0.60, 0.75),
          (0.75, 0.90), (0.90, 1.001)]
    print(f"{'condition':<26}" + "".join(f"{f'[{a:.2f},{b:.2f})':>14}"
                                         for a, b in cb))
    for lab, _, _, _ in CONDITIONS:
        ir, rs, er = per_cond[lab]
        cells = ""
        for a, b in cb:
            m = (ir >= a) & (ir < b)
            cells += (f"{np.median(er[m])/BETWEEN_UNIT_SD:>10.2f}"
                      f"{'(' + str(min(m.sum(), 99999)) + ')':>4}"
                      if m.sum() >= 30 else f"{'-':>14}")
        print(f"{lab:<26}{cells}")

    # ---- 2. error conditional on resid_std ------------------------------
    print(f"\n--- error conditional on resid_std (pooled); note resid_std is "
          f"bounded by construction, observed max {RS.max():.3f} ---")
    rb = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.80, 10.0]
    print(f"{'resid bin':<14}{'n':>9}{'med |err|':>11}{'/sd':>7}"
          f"{'p90 |err|':>11}{'/sd':>7}")
    for lo, hi in zip(rb[:-1], rb[1:]):
        m = (RS >= lo) & (RS < hi)
        if m.sum() < 30:
            continue
        e = ER[m]
        print(f"[{lo:.2f},{hi:.2f})  {m.sum():>9}{np.median(e):>11.3e}"
              f"{np.median(e)/BETWEEN_UNIT_SD:>7.2f}{q(e,90):>11.3e}"
              f"{q(e,90)/BETWEEN_UNIT_SD:>7.2f}")

    # ---- 3. the frozen grid: which settings meet C1 and C2? -------------
    print("\n--- the frozen grid (docs/GATE_CALIBRATION.md 2.4): admitted-"
          "frame error per gate ---")
    print(f"{'min_inlier':>11}{'max_resid':>10}{'admit%':>8}"
          f"{'med/sd':>9}{'p90/sd':>9}{'  C1':>5}{'  C2':>5}{'  0.25sd':>9}")
    passing = []
    for mi in INLIER_GRID:
        for mr in RESID_GRID:
            m = (IR >= mi) & (RS <= mr)
            if m.sum() < 200:
                continue
            e = ER[m]
            med, p90 = float(np.median(e)), q(e, 90)
            ok1, ok2 = med <= C1, p90 <= C2
            if ok1 and ok2:
                passing.append((mi, mr, m.mean(), med, p90))
            print(f"{mi:>11.2f}{mr:>10.2f}{100*m.mean():>8.2f}"
                  f"{med/BETWEEN_UNIT_SD:>9.3f}{p90/BETWEEN_UNIT_SD:>9.3f}"
                  f"{'  ok' if ok1 else ' FAIL':>5}"
                  f"{'  ok' if ok2 else ' FAIL':>5}"
                  f"{'  ok' if med <= STRICT_FRAC*BETWEEN_UNIT_SD else ' fail':>9}")

    # ---- 4. the same grid, restricted to the REAL operating box --------
    # docs/GATE_CALIBRATION.md 2.4 promised the *conditions* would be
    # matched to the data after the criterion was frozen. This is that
    # match, and it is a match on conditions only: C1 and C2 are unchanged.
    if args.rs_lo is not None:
        box = ((RS >= args.rs_lo) & (RS <= args.rs_hi)
               & (IR >= args.ir_lo) & (IR <= args.ir_hi))
        print(f"\n--- the frozen grid restricted to the REAL operating box "
              f"(measured, 4): inlier_ratio in [{args.ir_lo:g},{args.ir_hi:g}], "
              f"resid_std in [{args.rs_lo:g},{args.rs_hi:g}] ---")
        print(f"    {box.sum()} of {IR.size} synthetic frames "
              f"({100*box.mean():.1f}%) land in the box")
        print(f"{'min_inlier':>11}{'max_resid':>10}{'admit%':>8}"
              f"{'med/sd':>9}{'p90/sd':>9}{'  C1':>5}{'  C2':>5}")
        bpass = []
        for mi in INLIER_GRID:
            for mr in RESID_GRID:
                m = box & (IR >= mi) & (RS <= mr)
                if m.sum() < 200:
                    continue
                e = ER[m]
                med, p90 = float(np.median(e)), q(e, 90)
                if med <= C1 and p90 <= C2:
                    bpass.append((mi, mr))
                print(f"{mi:>11.2f}{mr:>10.2f}{100*m.sum()/box.sum():>8.2f}"
                      f"{med/BETWEEN_UNIT_SD:>9.3f}{p90/BETWEEN_UNIT_SD:>9.3f}"
                      f"{'  ok' if med <= C1 else ' FAIL':>5}"
                      f"{'  ok' if p90 <= C2 else ' FAIL':>5}")
        print(f"    settings meeting C1 and C2 inside the real box: "
              f"{bpass if bpass else 'NONE'}")
        print("\n--- per-condition, inside the box (so the pooled mixture "
              "weights cannot be doing the work silently) ---")
        print(f"{'condition':<26}{'n in box':>10}{'ir med':>8}{'rs med':>8}"
              f"{'med/sd':>9}{'p90/sd':>9}{'  C1':>5}")
        for lab, _, _, _ in CONDITIONS:
            ir, rs, er = per_cond[lab]
            m = ((rs >= args.rs_lo) & (rs <= args.rs_hi)
                 & (ir >= args.ir_lo) & (ir <= args.ir_hi))
            if m.sum() < 50:
                print(f"{lab:<26}{m.sum():>10}  (too few in box)")
                continue
            e = er[m]
            print(f"{lab:<26}{m.sum():>10}{np.median(ir[m]):>8.3f}"
                  f"{np.median(rs[m]):>8.3f}"
                  f"{np.median(e)/BETWEEN_UNIT_SD:>9.2f}"
                  f"{q(e,90)/BETWEEN_UNIT_SD:>9.2f}"
                  f"{'  ok' if np.median(e) <= C1 else ' FAIL':>5}")

    print("\n--- verdict ---")
    if not passing:
        print("NO setting on the frozen grid meets C1 and C2. Per "
              "docs/GATE_CALIBRATION.md 2.5(1) the answer is that the data "
              "does not support these devices; no threshold is reported.")
        return 0
    # loosest = lowest min_inlier; ties broken by the loosest max_resid
    best_mi = min(p[0] for p in passing)
    cand = [p for p in passing if p[0] == best_mi]
    best = max(cand, key=lambda p: p[1])
    print(f"loosest setting meeting both: min_inlier {best[0]:.2f}, "
          f"max_resid {best[1]:.2f}  "
          f"(admits {100*best[2]:.2f}% of fitted frames; "
          f"med {best[3]/BETWEEN_UNIT_SD:.3f} sd, "
          f"p90 {best[4]/BETWEEN_UNIT_SD:.3f} sd)")
    print(f"shipped for comparison: min_inlier {SHIP_INLIER:g}, "
          f"max_resid {SHIP_RESID:g}")
    mship = (IR >= SHIP_INLIER) & (RS <= SHIP_RESID)
    if mship.sum():
        print(f"  shipped admits {100*mship.mean():.2f}% of fitted frames, "
              f"med {np.median(ER[mship])/BETWEEN_UNIT_SD:.3f} sd, "
              f"p90 {q(ER[mship],90)/BETWEEN_UNIT_SD:.3f} sd")
    # what the strict 0.25 sd column would have given
    strict = [(mi, mr) for mi in INLIER_GRID for mr in RESID_GRID
              if ((IR >= mi) & (RS <= mr)).sum() >= 200
              and np.median(ER[(IR >= mi) & (RS <= mr)]) <= STRICT_FRAC*BETWEEN_UNIT_SD
              and q(ER[(IR >= mi) & (RS <= mr)], 90) <= C2]
    if strict:
        smi = min(s[0] for s in strict)
        print(f"secondary (0.25 sd median, same C2): loosest min_inlier "
              f"{smi:.2f}")
    else:
        print("secondary (0.25 sd median): no grid setting meets it")
    return 0


# ======================================================================
#  PART B — real-data scan
# ======================================================================

class Lines:
    """Byte-exact line iterator, so a part can resume where the last one
    stopped. `io.TextIOWrapper` cannot be used for this: it reads ahead in
    blocks, so `tell()` after `detach()` is past the last line csv.reader
    actually consumed and the resume would silently skip rows."""

    def __init__(self, path, pos):
        self.f = open(path, "rb")
        self.f.seek(pos)
        self.pos = pos

    def __iter__(self):
        return self

    def __next__(self):
        b = self.f.readline()
        if not b:
            raise StopIteration
        self.pos += len(b)
        return b.decode("utf-8", "replace")

    def close(self):
        self.f.close()


def circ(a, b):
    return ((a - b + 32768) % U16) - 32768


def med_flag(vals, ci):
    c = vals[ci]
    offs = sorted(circ(v, c) for v in vals)
    return abs(offs[len(offs) // 2]) > MED_TOL


SLOPE_BIN = 1e-5          # 0.0042 x BETWEEN_UNIT_SD — far finer than any
                          # threshold this pass compares against


def hist_add(h, v, w=SLOPE_BIN):
    h[int(np.floor(v / w))] += 1


def hist_q(h, ps, w=SLOPE_BIN):
    """Quantiles from a sparse integer-binned histogram over ALL values.

    A first-N reservoir would not do here: different gates admit different
    frames, so 'the first N admitted' spans a different stretch of the
    session at each gate and the gate comparison would be confounded with
    time. The histogram is over every admitted frame at every gate.
    """
    if not h:
        return [float("nan")] * len(ps)
    ks = sorted(h)
    tot = sum(h.values())
    out, cum, i = [], 0, 0
    counts = [h[k] for k in ks]
    for p in ps:
        target = p / 100.0 * tot
        while i < len(ks) and cum + counts[i] < target:
            cum += counts[i]
            i += 1
        out.append((ks[min(i, len(ks) - 1)] + 0.5) * w)
    return out


class GateAcc:
    """Per-(mac, gate) accumulator. Mirrors WindowAggregator's arithmetic
    on the frames the gate admits (dsp.py:170-195): a window is emitted
    every `window` accepted frames, median of their slopes."""

    __slots__ = ("n_admit", "buf", "wins", "hist", "whist")

    def __init__(self):
        self.n_admit = 0
        self.buf = []            # slopes of admitted frames, current window
        self.wins = 0            # count of emitted windows
        self.hist = defaultdict(int)     # per-frame slope, all frames
        self.whist = defaultdict(int)    # window-median slope, all windows

    def feed(self, slope, window):
        self.n_admit += 1
        self.buf.append(slope)
        hist_add(self.hist, slope)
        if len(self.buf) >= window:
            hist_add(self.whist, float(np.median(self.buf)))
            self.wins += 1
            self.buf = []


class MacStat:
    __slots__ = ("raw_n", "clean_n", "fit_n", "corrupt_n", "rssi_sum",
                 "t_first", "t_last", "ir_hist", "rs_hist", "gates",
                 "len_hist")

    def __init__(self):
        self.raw_n = 0          # every row bearing this MAC
        self.clean_n = 0        # rows surviving both corrupt screens
        self.fit_n = 0          # frames RANSAC actually fitted
        self.corrupt_n = 0
        self.rssi_sum = 0.0
        self.t_first = None
        self.t_last = None
        self.ir_hist = defaultdict(int)   # inlier_ratio, 0.01 bins
        self.rs_hist = defaultdict(int)   # resid_std, 0.01 bins
        self.len_hist = defaultdict(int)
        self.gates = {}                   # gate key -> GateAcc


class State:
    def __init__(self, tag, path, gates, window):
        self.tag = tag
        self.path = path
        self.gates = gates          # list of (min_inlier, max_resid)
        self.window = window
        self.rows = 0
        self.bad_parse = 0
        self.n_corrupt = 0
        self.n_field_bad = 0
        self.n_med_bad = 0
        self.byte_pos = 0
        self.node_mode = None
        self.chan_mode = None
        self.macs = defaultdict(MacStat)
        self.est = {}               # mac -> FrameEstimator (carried forward)
        self.pend = []              # width-9 median-filter pipeline
        self.node_hist = defaultdict(int)
        self.seam = []


def spath(tag, part):
    return os.path.join(CACHE, f"{tag}.p{part}.pkl")


GKEY = lambda mi, mr: f"{mi:.2f}/{mr:.2f}"      # noqa: E731


def _process(st, rec):
    """rec = (pc_us, mac, rssi, nf, chan, esp_us, ln, vals, node, env, drop,
    field_ok_flag). Called only after the median filter has decided."""
    (pc_us, mac, rssi, ln, esp_us, vals, ok) = rec
    ms = st.macs[mac]
    ms.raw_n += 1
    ms.len_hist[ln] += 1
    if not ok:
        ms.corrupt_n += 1
        st.n_corrupt += 1
        return
    ms.clean_n += 1
    ms.rssi_sum += rssi
    if ms.t_first is None:
        ms.t_first = pc_us
    ms.t_last = pc_us
    est = st.est.get(mac)
    if est is None:
        est = st.est[mac] = FrameEstimator()
    e = est.feed(vals, esp_us)
    if e is None:
        return
    ms.fit_n += 1
    ir, rs, sl = e["inlier_ratio"], e["resid_std"], e["slope"]
    ms.ir_hist[int(ir * 100)] += 1
    ms.rs_hist[min(int(rs * 100), 300)] += 1
    for mi, mr in st.gates:
        if ir >= mi and rs <= mr:
            k = GKEY(mi, mr)
            g = ms.gates.get(k)
            if g is None:
                g = ms.gates[k] = GateAcc()
            g.feed(sl, st.window)


def cmd_scan(args):
    os.makedirs(CACHE, exist_ok=True)
    csv.field_size_limit(10 ** 7)
    gates = []
    for tok in args.gates.split(","):
        if "/" in tok:
            a, b = tok.split("/")
            gates.append((float(a), float(b)))
        else:
            gates.append((float(tok), SHIP_RESID))

    if args.part == 0:
        st = State(args.tag, args.path, gates, args.window)
        # prescan for the screen's modes, docs/REFERENCE_CHOICE.md 1.2
        nh, ch = defaultdict(int), defaultdict(int)
        with open(args.path, newline="", errors="replace") as f:
            r = csv.reader(f)
            hdr = next(r)
            assert hdr[:13] == COLS, hdr
            for i, row in enumerate(r):
                if i >= 20000:
                    break
                if len(row) != 13:
                    continue
                try:
                    nh[int(row[10])] += 1
                    ch[int(row[6])] += 1
                except ValueError:
                    continue
            st.node_mode = max(nh.items(), key=lambda kv: kv[1])[0]
            st.chan_mode = max(ch.items(), key=lambda kv: kv[1])[0]
        # byte position just past the header
        with open(args.path, "rb") as f:
            f.readline()
            st.byte_pos = f.tell()
    else:
        with open(spath(args.tag, args.part - 1), "rb") as f:
            st = pickle.load(f)
        st.seam.append((args.part, st.rows, st.byte_pos))

    per = (args.total_rows + args.nparts - 1) // args.nparts
    stop_at = min(args.total_rows, per * (args.part + 1))

    L = Lines(args.path, st.byte_pos)
    r = csv.reader(L)
    t0 = time.time()
    n_here = 0
    for row in r:
        st.rows += 1
        n_here += 1
        if len(row) != 13:
            st.bad_parse += 1
            if st.rows >= stop_at:
                break
            continue
        try:
            pc_us = int(row[0]); mac = row[3].lower(); rssi = int(row[4])
            nf = int(row[5]); chan = int(row[6]); esp_us = int(row[7])
            ln = int(row[8]); node = int(row[10]); env = int(row[11])
            drop = int(row[12])
            vals = np.fromstring(row[9], dtype=np.float64, sep=",")
        except ValueError:
            st.bad_parse += 1
            if st.rows >= stop_at:
                break
            continue
        st.node_hist[node] += 1
        # route 1: field plausibility on six columns
        fok = (node == st.node_mode and env == 0 and chan == st.chan_mode
               and ln in CSI_LEN_OK and NF_LO <= nf <= NF_HI
               and RSSI_LO <= rssi <= RSSI_HI)
        if not fok:
            st.n_field_bad += 1
        st.pend.append([pc_us, mac, rssi, ln, esp_us, vals, fok, drop])
        # route 2: width-9 circular median filter on `dropped`
        if len(st.pend) == MED_W:
            ci = MED_W // 2
            mbad = med_flag([p[7] for p in st.pend], ci)
            if mbad:
                st.n_med_bad += 1
                st.pend[ci][6] = False
            p = st.pend.pop(0)
            # the row leaving the window is the one 4 back from centre; we
            # emit the head only once its own centre-pass has happened,
            # which for the head is guaranteed after MED_W rows have
            # accumulated at least ci+1 times. Emit head with its flag.
            _process(st, tuple(p[:7]))
        if st.rows >= stop_at:
            break
    # flush remaining pipeline only on the final part
    st.byte_pos = L.pos
    L.close()
    if args.part == args.nparts - 1:
        while st.pend:
            p = st.pend.pop(0)
            _process(st, tuple(p[:7]))
    with open(spath(args.tag, args.part), "wb") as g:
        pickle.dump(st, g, protocol=4)
    print(f"[{args.tag} part {args.part}/{args.nparts}] {n_here:,} rows "
          f"(total {st.rows:,}), corrupt {st.n_corrupt:,}, "
          f"{len(st.macs)} MACs, {time.time()-t0:.1f}s", file=sys.stderr)
    return 0


def cmd_merge(args):
    with open(spath(args.tag, args.nparts - 1), "rb") as f:
        st = pickle.load(f)
    st.est = {}                      # estimators are not needed downstream
    with open(os.path.join(CACHE, f"{args.tag}.final.pkl"), "wb") as f:
        pickle.dump(st, f, protocol=4)
    print(f"[{args.tag}] merged: {st.rows:,} rows, {st.bad_parse} unparseable, "
          f"corrupt {st.n_corrupt:,} (field {st.n_field_bad:,}, "
          f"median-filter {st.n_med_bad:,}), {len(st.macs)} MACs, "
          f"seams {st.seam}", file=sys.stderr)
    return 0


# ======================================================================
#  PART C — report
# ======================================================================

def iqr(a):
    a = np.asarray(a)
    return float(np.subtract(*np.percentile(a, [75, 25]))) if a.size >= 4 \
        else float("nan")


def cmd_report(args):
    tags = args.tags.split(",")
    S = {}
    for t in tags:
        with open(os.path.join(CACHE, f"{t}.final.pkl"), "rb") as f:
            S[t] = pickle.load(f)
    ship = GKEY(SHIP_INLIER, SHIP_RESID)
    gate_keys = [GKEY(a, b) for a, b in S[tags[0]].gates]
    loose = [k for k in gate_keys if k != ship]

    # ---------- 0. health + corrupt-row screen ----------
    print("=== 0. capture health and corrupt-row screen ===")
    print(f"{'node':<8}{'rows':>12}{'unparse':>9}{'field-bad':>11}"
          f"{'med-bad':>9}{'corrupt':>9}{'ppm':>8}{'MACs':>7}")
    for t in tags:
        st = S[t]
        print(f"{t:<8}{st.rows:>12,}{st.bad_parse:>9}{st.n_field_bad:>11,}"
              f"{st.n_med_bad:>9,}{st.n_corrupt:>9,}"
              f"{1e6*st.n_corrupt/max(st.rows,1):>8.2f}{len(st.macs):>7}")
    print("\n  MACs that exist ONLY on rows the screen rejected "
          "(fabricated addresses):")
    for t in tags:
        st = S[t]
        only = [m for m, s in st.macs.items() if s.clean_n == 0]
        real = [m for m, s in st.macs.items() if s.clean_n > 0]
        print(f"    {t:<8} {len(only)} fabricated of {len(st.macs)} "
              f"distinct MACs; {len(real)} survive the screen")
        print(f"      -> every census figure below is over the "
              f"{len(real)} screened MACs only")

    # ---------- 1. census delta ----------
    print("\n=== 1. census at each gate (screened rows only) ===")
    print("  'sources' = MACs with >= --min-frames ADMITTED frames on this "
          "node, the docs/RECEIVER_TERM_PREREG.md 2.3 admissibility floor")
    mf = args.min_frames
    print(f"\n{'node':<8}{'gate (inl/res)':>16}{'sources>=' + str(mf):>14}"
          f"{'admitted frames':>18}{'windows w=' + str(S[tags[0]].window):>16}")
    src = {}
    for t in tags:
        st = S[t]
        for k in gate_keys:
            names = [m for m, s in st.macs.items()
                     if s.clean_n > 0 and k in s.gates
                     and s.gates[k].n_admit >= mf]
            src[(t, k)] = set(names)
            tot = sum(s.gates[k].n_admit for m, s in st.macs.items()
                      if s.clean_n > 0 and k in s.gates)
            wins = sum(s.gates[k].wins for m, s in st.macs.items()
                       if s.clean_n > 0 and k in s.gates)
            print(f"{t:<8}{k:>16}{len(names):>14}{tot:>18,}{wins:>16,}")

    print(f"\n--- the source list at each gate (>= {mf} admitted frames) ---")
    for t in tags:
        for k in gate_keys:
            names = sorted(src[(t, k)], key=lambda m: -S[t].macs[m]
                           .gates[k].n_admit)
            print(f"  {t} {k}: " + ", ".join(
                f"{m}({S[t].macs[m].gates[k].n_admit:,})" for m in names))

    print("\n--- delta vs the shipped gate, per node ---")
    for t in tags:
        base = src[(t, ship)]
        for k in loose:
            new = src[(t, k)] - base
            lost = base - src[(t, k)]
            print(f"  {t} {ship} -> {k}: {len(base)} -> {len(src[(t,k)])} "
                  f"sources  (+{len(new)}, -{len(lost)})")

    # ---------- 2. per newly-admitted source: quantity AND quality ----
    print("\n=== 2. newly-admitted sources: frames gained and estimate "
          "quality (C3, docs/GATE_CALIBRATION.md 2.3) ===")
    print(f"  gain rule: slope IQR < BETWEEN_UNIT_SD = {BETWEEN_UNIT_SD} "
          f"rad/sc counts as a GAIN; IQR >= that is NOISE WEARING A MAC")
    for t in tags:
        st = S[t]
        for k in loose:
            new = sorted(src[(t, k)] - src[(t, ship)])
            print(f"\n  --- {t}, gate {k} (shipped {ship}) ---")
            if not new:
                print("    (no newly-admitted source)")
                continue
            print(f"    {'mac':<19}{'kind':<9}{'clean':>8}{'fit':>8}"
                  f"{'adm@ship':>9}{'adm@new':>8}{'med SFO':>10}"
                  f"{'IQR':>10}{'IQR/sd':>8}{'win':>4}  verdict")
            n_gain = n_noise = 0
            for m in new:
                s = st.macs[m]
                g = s.gates[k]
                base_n = s.gates[ship].n_admit if ship in s.gates else 0
                p25, p50, p75 = hist_q(g.hist, [25, 50, 75])
                d = p75 - p25
                kind = ("beacon" if m in BEACON_MACS else
                        ("private" if int(m.split(":")[0], 16) & 2
                         else "real-OUI"))
                good = np.isfinite(d) and d < BETWEEN_UNIT_SD
                n_gain += good
                n_noise += (not good)
                print(f"    {m:<19}{kind:<9}{s.clean_n:>8,}{s.fit_n:>8,}"
                      f"{base_n:>9}{g.n_admit:>8}"
                      f"{p50:>+10.5f}{d:>10.5f}"
                      f"{d/BETWEEN_UNIT_SD:>8.2f}{g.wins:>4}  "
                      f"{'GAIN' if good else 'noise wearing a MAC'}")
            print(f"    -> {n_gain} real gain(s), {n_noise} noise-wearing-a-"
                  f"MAC, of {len(new)} newly admitted")

    # ---------- 3. do the beacons move? ----------
    print("\n=== 3. do the beacons move? (falsifier 2, "
          "docs/GATE_CALIBRATION.md 2.5) ===")
    print("  threshold set in advance: any beacon median moving > 0.10 x "
          "BETWEEN_UNIT_SD rejects the setting")
    print(f"\n{'node':<7}{'beacon':<20}" +
          "".join(f"{k:>13}" for k in gate_keys) + f"{'max move/sd':>13}")
    worst = 0.0
    for t in tags:
        st = S[t]
        for m, nm in BEACON_MACS.items():
            s = st.macs.get(m)
            if s is None or s.clean_n == 0:
                continue
            meds = {}
            for k in gate_keys:
                g = s.gates.get(k)
                meds[k] = hist_q(g.hist, [50])[0] if g else float("nan")
            base = meds[ship]
            mv = max((abs(meds[k] - base) for k in gate_keys
                      if np.isfinite(meds[k])), default=float("nan"))
            worst = max(worst, mv if np.isfinite(mv) else 0.0)
            print(f"{t:<7}{m + ' ' + nm:<20}" +
                  "".join(f"{meds[k]:>+13.5f}" for k in gate_keys) +
                  f"{mv/BETWEEN_UNIT_SD:>13.3f}")
    # The loosening branch on its own. A gate that is TIGHTER than shipped
    # starves a marginal cell and moves it for a different reason than a
    # looser one does; pooling the two hides which direction failed.
    loosen = [k for k in gate_keys
              if float(k.split("/")[0]) <= SHIP_INLIER
              and float(k.split("/")[1]) >= SHIP_RESID]
    print(f"\n  loosening branch only ({', '.join(loosen)}):")
    print(f"  {'node':<7}{'beacon':<22}{'move rad/sc':>13}{'x sd':>8}"
          f"{'  verdict':>10}")
    wl = 0.0
    for t in tags:
        st = S[t]
        for m, nm in BEACON_MACS.items():
            s = st.macs.get(m)
            if s is None or s.clean_n == 0:
                continue
            v = [hist_q(s.gates[k].hist, [50])[0] for k in loosen
                 if k in s.gates]
            if len(v) < 2:
                continue
            mv = max(v) - min(v)
            wl = max(wl, mv)
            print(f"  {t:<7}{m + ' ' + nm:<22}{mv:>13.5f}"
                  f"{mv/BETWEEN_UNIT_SD:>8.3f}"
                  f"{'  ok' if mv <= 0.10*BETWEEN_UNIT_SD else '  MOVES':>10}")
    print(f"  -> loosening alone moves a beacon by at most {wl:.5f} rad/sc "
          f"= {wl/BETWEEN_UNIT_SD:.3f} x sd -> "
          f"{'PASSES' if wl <= 0.10*BETWEEN_UNIT_SD else 'FAILS'}")

    print(f"\n  largest beacon median movement across all gates: "
          f"{worst:.6f} rad/sc = {worst/BETWEEN_UNIT_SD:.3f} x "
          f"BETWEEN_UNIT_SD -> "
          f"{'PASSES' if worst <= 0.10*BETWEEN_UNIT_SD else 'FAILS'} "
          f"the 0.10 sd falsifier")

    # ---------- 4. both-receiver population ----------
    if len(tags) >= 2:
        print("\n=== 4. sources heard by BOTH receivers "
              "(docs/RECEIVER_TERM_PREREG.md 11 replication) ===")
        a, b = tags[0], tags[1]
        clean_a = {m for m, s in S[a].macs.items() if s.clean_n > 0}
        clean_b = {m for m, s in S[b].macs.items() if s.clean_n > 0}
        both = clean_a & clean_b
        print(f"  screened MACs on {a}: {len(clean_a)}, on {b}: "
              f"{len(clean_b)}, on both: {len(both)}")
        for k in gate_keys:
            n = len(src[(a, k)] & src[(b, k)])
            print(f"    gate {k}: {n} source(s) with >= {mf} admitted "
                  f"frames on BOTH receivers")

    # ---------- 5. inlier_ratio distribution, real ambient vs beacon ----
    print("\n=== 5. where real sources actually sit on inlier_ratio ===")
    print(f"{'node':<7}{'mac':<19}{'kind':<9}{'fit':>9}"
          f"{'ir p10':>8}{'ir p50':>8}{'ir p90':>8}{'rs p50':>8}{'rs max':>8}")
    for t in tags:
        st = S[t]
        rows = sorted((m for m, s in st.macs.items()
                       if s.clean_n > 0 and s.fit_n >= 20),
                      key=lambda m: -st.macs[m].fit_n)
        for m in rows[:args.top]:
            s = st.macs[m]
            i10, i50, i90 = hist_q(s.ir_hist, [10, 50, 90], w=0.01)
            rs50, = hist_q(s.rs_hist, [50], w=0.01)
            rsmax = (max(s.rs_hist) + 1) / 100.0 if s.rs_hist else float("nan")
            kind = ("beacon" if m in BEACON_MACS else
                    ("private" if int(m.split(":")[0], 16) & 2
                     else "real-OUI"))
            print(f"{t:<7}{m:<19}{kind:<9}{s.fit_n:>9,}"
                  f"{i10:>8.3f}{i50:>8.3f}{i90:>8.3f}"
                  f"{rs50:>8.3f}{rsmax:>8.3f}")

    # ---------- 6. exact-reproduction check of the shipped branch -------
    print("\n=== 6. shipped-branch reproduction check ===")
    print("  The shipped-gate column above must reproduce a run that knows "
          "nothing about the loosened gates. Compare against "
          "`python pc/rff_offline.py` / `pc/mac_census.py` output quoted in "
          "docs/GATE_CALIBRATION.md 6.")
    for t in tags:
        st = S[t]
        g = st.macs.get("a4:f0:0f:77:91:20")
        if g and ship in g.gates:
            a = g.gates[ship]
            print(f"    {t} B1 a4:f0:0f:77:91:20 @ {ship}: "
                  f"{a.n_admit:,} admitted frames, {a.wins:,} windows, "
                  f"median SFO {hist_q(a.hist,[50])[0]:+.5f}")
    return 0


# ======================================================================

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("calib")
    c.add_argument("--frames", type=int, default=3000)
    c.add_argument("--reps", type=int, default=3)
    c.add_argument("--ir-lo", type=float, default=0.30)
    c.add_argument("--ir-hi", type=float, default=1.01)
    c.add_argument("--rs-lo", type=float, default=None,
                   help="restrict the grid to the measured real operating "
                        "box; see docs/GATE_CALIBRATION.md 4")
    c.add_argument("--rs-hi", type=float, default=0.23)
    c.set_defaults(fn=cmd_calib)

    s = sub.add_parser("scan")
    s.add_argument("path")
    s.add_argument("--tag", required=True)
    s.add_argument("--part", type=int, required=True)
    s.add_argument("--nparts", type=int, required=True)
    s.add_argument("--total-rows", type=int, required=True)
    s.add_argument("--gates", required=True,
                   help="comma list of min_inlier or min_inlier/max_resid")
    s.add_argument("--window", type=int, default=SHIP_WINDOW)
    s.set_defaults(fn=cmd_scan)

    m = sub.add_parser("merge")
    m.add_argument("--tag", required=True)
    m.add_argument("--nparts", type=int, required=True)
    m.set_defaults(fn=cmd_merge)

    r = sub.add_parser("report")
    r.add_argument("--tags", required=True)
    r.add_argument("--min-frames", type=int, default=20)
    r.add_argument("--top", type=int, default=25)
    r.set_defaults(fn=cmd_report)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
