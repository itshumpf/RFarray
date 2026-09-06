#!/usr/bin/env python3
r"""RIPPLE_TEST — is the "SFO" slope contaminated by multipath delay?

Pre-registration: `docs/RIPPLE_TEST.md`, frozen before this script was run.

The physics, briefly (full derivation in the pre-registration §0): a reflection
arriving tau seconds late multiplies the channel by exp(-j*2*pi*f*tau), and
since subcarrier k sits at f = k*Delta_f, that one path adds a *pure linear
phase ramp* of -2*pi*Delta_f*tau rad/subcarrier — the identical functional form
`pc/rff/dsp.py` attributes to the transmitter's sampling-clock offset. In a
single frame the two are indistinguishable and RANSAC cannot help, because the
contaminant is a perfect inlier rather than an outlier. The same delay also
ripples the *amplitude* spectrum with period 1/tau, so amplitude carries an
independent readout of the delay contaminating the phase.

Primary test: do frames with flatter amplitude spectra yield more stable
slopes? Measured *within narrow RSSI strata*, because low SNR independently
roughens amplitude and noisens phase and would fake the whole result.

Design constraints this script obeys, and why
---------------------------------------------
* **`pc/rff/dsp.py` is used exactly as shipped and is NOT modified**
  (`docs/V2_SPEC.md` §5.5). Computing an amplitude from the same buffer is new
  analysis, not an estimator change. `_USABLE_IDX` is *imported* from it (and
  cross-checked against an independently reconstructed copy) so the amplitude
  and the phase provably come from the same 52 bins.
* **Replay from the start of each file with a fresh estimator.**
  `FrameEstimator` owns a per-instance RNG (`dsp.py:118`) handed to
  `ransac_line` every frame (`:132`), which draws two `rng.integers(...,
  size=64)` per call (`:85-86`); the generator advances once per fitted frame,
  so a slope depends on how many frames preceded it in that stream
  (`docs/V2_SPEC.md` §5.5). The `run`/`resume` checkpoint pickles the estimator
  state and the exact byte offset forward, so an N-call run is frame-for-frame
  what one uninterrupted pass would have produced. `verify` re-checks this on a
  short file rather than asserting it.
* **Screen corrupt rows before the estimator and before any delta arithmetic.**
  The d0wd fabricates MAC addresses from corrupt rows — 126 of them on this
  file (`docs/COLOCATED_0823.md` §2). Field plausibility on six columns.
* **`csi_data` is a quoted comma-separated list nested in the CSV.** Parsed
  with `csv.reader`, never a naive `line.split(",")`.
* `pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` are
  NOT used — `docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 establishes all three have
  the DC/guard-band index wrong.
* Read-only on `data/raw/`; no serial port is opened; nothing is staged.

Usage (from the repo root; state goes to $RIPPLE_CACHE, default /tmp/ripple)
---------------------------------------------------------------------------
  export RIPPLE_CACHE=/tmp/ripple
  python3 pc/exp_ripple_test.py run data/raw/d0wd_20260823_014740.csv --tag d0wd
  ...repeat until it prints DONE...
  python3 pc/exp_ripple_test.py run data/raw/s3_20260823_014740.csv   --tag s3
  python3 pc/exp_ripple_test.py report --tags d0wd,s3
  python3 pc/exp_ripple_test.py verify data/raw/d0wd_20260823_013537.csv
"""
import argparse
import csv
import math
import os
import pickle
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rff.dsp import (FrameEstimator, csi_to_complex, K_USABLE,   # noqa: E402
                     SUBCARRIER_SPACING_HZ, _USABLE_IDX)
from occ import BEACON_MACS                                      # noqa: E402

CACHE = os.environ.get("RIPPLE_CACHE", "/tmp/ripple")

# ---------------------------------------------------------------- frozen cfg
# All of these are fixed by docs/RIPPLE_TEST.md and must not be tuned here.
W_PRIMARY = 64            # frames per stability window (~1 s on a beacon)
W_ROBUST = 256            # robustness replicate (~4 s)
MAX_WIN_SPAN_S = 5.0      # windows spanning longer than this are excluded
MIN_INLIER = 0.6          # shipped gate, dsp.py:164
MAX_RESID = 0.8           # shipped gate, dsp.py:164
RSSI_STRATUM_DB = 1.0     # narrow-strata width
MIN_WIN_PER_STRATUM = 200
MIN_FRAMES_PER_STREAM = 640     # >= 10 windows at W=64
E1_MEDIAN_RHO = -0.20
E1_STRATUM_RHO = -0.10
E1_STRATUM_FRAC = 0.70
E2_MAD_RATIO = 1.5
E3_PARTIAL_RHO = -0.10
E5_RHO = 0.30
E5_COEF_LO, E5_COEF_HI = 0.5, 2.0

# Field-plausibility screen, docs/OVERNIGHT_2026-08-22.md §1.
CSI_LEN_OK = (128, 256, 384)
NF_LO, NF_HI = -110, -70
RSSI_LO, RSSI_HI = -100, -10

# tau estimation from the amplitude spectrum
NFFT = 512
BAND_HZ = 52.0 * SUBCARRIER_SPACING_HZ     # 16.25 MHz
MIN_CYCLES = 2.0                            # >= 2 ripple cycles across band
PEAK_PROM = 3.0                             # peak power / median spectral power

# per-frame sample for the secondary quantitative test
FRAME_SAMPLE_STRIDE = 8
FRAME_SAMPLE_CAP = 150_000

TIME_BUDGET_S = float(os.environ.get("RIPPLE_BUDGET", "150"))
CHUNK_LINES = 20_000

# --- independent reconstruction of the usable-bin mask (cross-check) -------
_k_of_idx = np.r_[np.arange(0, 32), np.arange(-32, 0)]
_mask = (np.abs(_k_of_idx) >= 1) & (np.abs(_k_of_idx) <= 26)
_idx_local = np.where(_mask)[0][np.argsort(_k_of_idx[_mask])]
assert np.array_equal(_idx_local, _USABLE_IDX), "usable-bin mask disagrees with dsp.py"
assert K_USABLE.size == 52
KF = K_USABLE.astype(np.float64)


# ------------------------------------------------------------------ helpers

def spectral_flatness(power):
    """Geometric mean / arithmetic mean of power. Bounded (0, 1]; 1 = flat.

    Returns 0.0 if any usable bin is exactly zero (counted, not floored).
    """
    if np.any(power <= 0.0):
        return 0.0
    return float(math.exp(np.log(power).mean()) / power.mean())


def ripple_db(mag):
    """Robustness metric: sd of the log-magnitude across usable bins (dB)."""
    if np.any(mag <= 0.0):
        return float("nan")
    return float((20.0 * np.log10(mag)).std())


_WIN = np.hanning(53)
_KGRID = np.arange(-26, 27)
_FILL = np.where(_KGRID == 0)[0][0]


def estimate_tau(mag):
    """Delay estimate (s) from the amplitude ripple, or None.

    Builds log|H| on the contiguous grid k=-26..26 (DC filled by the mean of
    its two neighbours, since it is null by design), removes the mean, windows,
    zero-pads and takes the FFT. A dominant two-path channel with delay tau
    ripples with period 1/tau in frequency, so the spectrum peaks at that tau.
    Rejected unless the ripple completes >= MIN_CYCLES across the 16.25 MHz
    band (docs/RIPPLE_TEST.md §0.1) and the peak stands PEAK_PROM above the
    median of the spectrum.
    """
    if np.any(mag <= 0.0):
        return None
    g = np.empty(53)
    g[:26] = np.log(mag[:26])
    g[27:] = np.log(mag[26:])
    g[_FILL] = 0.5 * (g[_FILL - 1] + g[_FILL + 1])
    g -= g.mean()
    sp = np.abs(np.fft.rfft(g * _WIN, NFFT)) ** 2
    # bin m <-> delay m / (NFFT * Delta_f); cycles across band = tau * BAND_HZ
    lo = int(np.ceil(MIN_CYCLES * NFFT / 53.0))
    if lo >= sp.size - 1:
        return None
    seg = sp[lo:]
    m = int(np.argmax(seg)) + lo
    med = float(np.median(sp[1:]))
    if med <= 0 or sp[m] < PEAK_PROM * med:
        return None
    return m / (NFFT * SUBCARRIER_SPACING_HZ)


def _mad(a):
    med = np.median(a)
    return float(1.4826 * np.median(np.abs(a - med))), float(med)


def _rank(a):
    """Average-rank transform (ties averaged), matching Spearman's usage."""
    a = np.asarray(a, dtype=np.float64)
    n = a.size
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(n, dtype=np.float64)
    sa = a[order]
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sa[j + 1] == sa[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return ranks


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 10:
        return float("nan")
    rx, ry = _rank(x[ok]), _rank(y[ok])
    rx -= rx.mean(); ry -= ry.mean()
    d = math.sqrt(float((rx * rx).sum()) * float((ry * ry).sum()))
    return float((rx * ry).sum() / d) if d > 0 else float("nan")


def partial_spearman(x, y, controls):
    """Spearman of x,y after least-squares removal of the ranked controls."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    cs = [np.asarray(c, float) for c in controls]
    ok = np.isfinite(x) & np.isfinite(y)
    for c in cs:
        ok &= np.isfinite(c)
    if ok.sum() < 20:
        return float("nan")
    rx, ry = _rank(x[ok]), _rank(y[ok])
    cols = [_rank(c[ok]) for c in cs] + [np.ones(int(ok.sum()))]
    A = np.column_stack(cols)
    ex = rx - A @ np.linalg.lstsq(A, rx, rcond=None)[0]
    ey = ry - A @ np.linalg.lstsq(A, ry, rcond=None)[0]
    return spearman(ex, ey)


# -------------------------------------------------------------------- state

class Stream:
    """Per-(node, source-MAC) accumulators."""
    __slots__ = ("est", "buf64", "buf256", "win64", "win256",
                 "n_raw", "n_fed", "n_acc", "n_zero_bin", "n_tau",
                 "s_slope", "s_tau", "s_rssi", "s_sf", "s_stride")

    def __init__(self):
        self.est = FrameEstimator()
        self.buf64 = []          # (slope, sf, rdb, rssi, resid, ts_us)
        self.buf256 = []
        self.win64 = []          # window records
        self.win256 = []
        self.n_raw = 0           # rows bearing this MAC (pre-screen)
        self.n_fed = 0           # screened rows fed to the estimator
        self.n_acc = 0           # frames passing the shipped gates
        self.n_zero_bin = 0      # frames with a zero usable bin (SF undefined)
        self.n_tau = 0
        self.s_slope, self.s_tau = [], []
        self.s_rssi, self.s_sf = [], []
        self.s_stride = 0


class State:
    def __init__(self, tag, path):
        self.tag = tag
        self.path = path
        self.offset = 0
        self.rows = 0
        self.bad_field = 0
        self.bad_parse = 0
        self.short_csi = 0
        self.node_mode = None
        self.chan_mode = None
        self.streams = defaultdict(Stream)
        self.elapsed = 0.0
        self.done = False
        self.t_first = None
        self.t_last = None


def _spath(tag):
    return os.path.join(CACHE, f"{tag}.pkl")


def save(st):
    os.makedirs(CACHE, exist_ok=True)
    tmp = _spath(st.tag) + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(st, f, protocol=4)
    os.replace(tmp, _spath(st.tag))


def load(tag):
    with open(_spath(tag), "rb") as f:
        return pickle.load(f)


# ------------------------------------------------------------------ prescan

def prescan(path, n=20000):
    """File's own mode for node_id and channel, from the first n data rows."""
    nodes, chans = defaultdict(int), defaultdict(int)
    with open(path, "rb") as f:
        f.readline()
        raw = f.read(4 * 1024 * 1024)
    text = raw.decode("utf-8", "replace")
    lines = text.split("\n")[:-1][:n]
    for row in csv.reader(lines):
        if len(row) != 13:
            continue
        try:
            nodes[int(row[10])] += 1
            chans[int(row[6])] += 1
        except ValueError:
            continue
    if not nodes:
        raise SystemExit(f"prescan found no parseable rows in {path}")
    return (max(nodes, key=nodes.get), max(chans, key=chans.get),
            dict(nodes), dict(chans))


# --------------------------------------------------------------- window emit

def _emit(buf, out):
    slopes = np.fromiter((b[0] for b in buf), float, len(buf))
    sfs = np.fromiter((b[1] for b in buf), float, len(buf))
    rdbs = np.fromiter((b[2] for b in buf), float, len(buf))
    rssis = np.fromiter((b[3] for b in buf), float, len(buf))
    resids = np.fromiter((b[4] for b in buf), float, len(buf))
    ts = np.fromiter((b[5] for b in buf), float, len(buf))
    mad, med = _mad(slopes)
    span = (ts.max() - ts.min()) * 1e-6
    out.append((float(np.median(sfs)), float(np.nanmedian(rdbs)),
                float(rssis.mean()), float(np.median(resids)),
                mad, med, span, float(len(buf))))


# ------------------------------------------------------------------- the run

def do_run(args):
    tag, path = args.tag, args.file
    if os.path.exists(_spath(tag)) and not args.restart:
        st = load(tag)
        if st.path != os.path.abspath(path):
            raise SystemExit(f"checkpoint {tag} is for {st.path}")
        if st.done:
            print(f"[{tag}] already DONE  rows={st.rows}")
            return
    else:
        st = State(tag, os.path.abspath(path))
        nm, cm, nh, ch = prescan(path)
        st.node_mode, st.chan_mode = nm, cm
        print(f"[{tag}] prescan node_id mode={nm} {nh}  channel mode={cm} {ch}")

    size = os.path.getsize(path)
    t0 = time.time()
    beacons = set(BEACON_MACS)
    with open(path, "rb") as f:
        if st.offset == 0:
            f.readline()
            st.offset = f.tell()
        f.seek(st.offset)
        pending = b""
        while True:
            raw = f.read(8 * 1024 * 1024)
            if not raw:
                st.done = True
                break
            pending += raw
            nl = pending.rfind(b"\n")
            if nl < 0:
                continue
            block, pending = pending[:nl + 1], pending[nl + 1:]
            st.offset += len(block)
            lines = block.decode("utf-8", "replace").splitlines()
            _process(st, lines, beacons)
            if time.time() - t0 > TIME_BUDGET_S:
                break
        if st.done and pending.strip():
            # trailing bytes with no final newline: a truncated row
            st.offset += len(pending)
            lines = pending.decode("utf-8", "replace").splitlines()
            _process(st, lines, beacons)

    st.elapsed += time.time() - t0
    save(st)
    pct = 100.0 * st.offset / size
    print(f"[{tag}] {'DONE' if st.done else 'PART'} "
          f"offset={st.offset}/{size} ({pct:.2f}%) rows={st.rows} "
          f"bad_field={st.bad_field} bad_parse={st.bad_parse} "
          f"streams={len(st.streams)} cpu={st.elapsed:.0f}s")


def _process(st, lines, beacons):
    node_mode, chan_mode = st.node_mode, st.chan_mode
    streams = st.streams
    for row in csv.reader(lines):
        if len(row) != 13:
            st.bad_parse += 1
            continue
        st.rows += 1
        mac = row[3]
        try:
            rssi = int(row[4]); nf = int(row[5]); chan = int(row[6])
            clen = int(row[8]); node = int(row[10]); env = int(row[11])
            ts_us = int(row[7]); pc_us = int(row[0])
        except ValueError:
            st.bad_parse += 1
            continue
        # --- corrupt-row screen, before the estimator ----------------------
        if (node != node_mode or env != 0 or chan != chan_mode
                or clen not in CSI_LEN_OK
                or not (NF_LO <= nf <= NF_HI)
                or not (RSSI_LO <= rssi <= RSSI_HI)):
            st.bad_field += 1
            continue
        if st.t_first is None:
            st.t_first = pc_us
        st.t_last = pc_us

        s = streams[mac]
        s.n_raw += 1
        parts = row[9].split(",", 128)
        if len(parts) < 128:
            st.short_csi += 1
            continue
        try:
            iq = np.array(parts[:128], dtype=np.float64)
        except ValueError:
            st.bad_parse += 1
            continue

        s.n_fed += 1
        est = s.est.feed(iq, ts_us)
        if est is None:
            continue
        if (est["inlier_ratio"] < MIN_INLIER or est["resid_std"] > MAX_RESID):
            continue
        s.n_acc += 1

        csi = csi_to_complex(iq)
        mag = np.abs(csi[_USABLE_IDX])
        sf = spectral_flatness(mag * mag)
        if sf == 0.0:
            s.n_zero_bin += 1
            continue
        rdb = ripple_db(mag)
        rec = (est["slope"], sf, rdb, float(rssi), est["resid_std"], pc_us)
        s.buf64.append(rec)
        if len(s.buf64) == W_PRIMARY:
            _emit(s.buf64, s.win64)
            s.buf64 = []
        s.buf256.append(rec)
        if len(s.buf256) == W_ROBUST:
            _emit(s.buf256, s.win256)
            s.buf256 = []

        # --- per-frame sample for the secondary quantitative test ----------
        if mac in beacons:
            s.s_stride += 1
            if (s.s_stride % FRAME_SAMPLE_STRIDE == 0
                    and len(s.s_slope) < FRAME_SAMPLE_CAP):
                tau = estimate_tau(mag)
                if tau is not None:
                    s.n_tau += 1
                s.s_slope.append(est["slope"])
                s.s_tau.append(tau if tau is not None else float("nan"))
                s.s_rssi.append(float(rssi))
                s.s_sf.append(sf)


# --------------------------------------------------------------- reproduction

def do_verify(args):
    """Prove the checkpointed split reproduces one uninterrupted pass.

    Runs the short 013537 file twice — once with a large time budget (single
    pass) and once with a deliberately tiny one (many resumes) — and compares
    every window record. This is the check `docs/V2_SPEC.md` §5.5 requires,
    done rather than asserted.
    """
    global TIME_BUDGET_S
    out = {}
    for label, budget in (("single", 1e9), ("split", args.split_budget)):
        tag = f"_ver_{label}"
        p = _spath(tag)
        if os.path.exists(p):
            os.remove(p)
        TIME_BUDGET_S = budget
        n = 0
        while True:
            ns = argparse.Namespace(tag=tag, file=args.file, restart=(n == 0))
            do_run(ns)
            n += 1
            if load(tag).done:
                break
            if n > 200:
                raise SystemExit("verify: too many resumes")
        st = load(tag)
        out[label] = st
        print(f"[verify] {label}: {n} call(s), rows={st.rows}")
    a, b = out["single"], out["split"]
    same = (a.rows == b.rows and set(a.streams) == set(b.streams))
    diffs = 0
    for mac in a.streams:
        wa, wb = a.streams[mac].win64, b.streams[mac].win64
        if len(wa) != len(wb):
            diffs += 1
            continue
        for ra, rb in zip(wa, wb):
            if any(not (x == y or (math.isnan(x) and math.isnan(y)))
                   for x, y in zip(ra, rb)):
                diffs += 1
                break
    print(f"[verify] rows/streams identical: {same}   "
          f"streams with any differing window: {diffs}")
    print("[verify] VERDICT:",
          "split reproduces single pass exactly" if same and diffs == 0
          else "MISMATCH — checkpointing is NOT transparent")


# ------------------------------------------------------------------- report

def _arr(wins):
    a = np.asarray(wins, dtype=np.float64)
    return dict(sf=a[:, 0], rdb=a[:, 1], rssi=a[:, 2], resid=a[:, 3],
                mad=a[:, 4], med=a[:, 5], span=a[:, 6], n=a[:, 7])


def _strata(d, key="sf", ykey="mad"):
    """Within-1 dB-RSSI-band Spearman of key vs ykey. Returns list of dicts."""
    out = []
    bins = np.round(d["rssi"] / RSSI_STRATUM_DB).astype(int)
    for b in np.unique(bins):
        m = bins == b
        k = int(m.sum())
        if k < MIN_WIN_PER_STRATUM:
            continue
        x, y = d[key][m], d[ykey][m]
        rho = spearman(x, y)
        q = np.nanpercentile(x, [20, 80])
        lo = y[x <= q[0]]
        hi = y[x >= q[1]]
        ratio = (float(np.median(lo) / np.median(hi))
                 if lo.size >= 10 and hi.size >= 10 and np.median(hi) > 0
                 else float("nan"))
        out.append(dict(rssi=b * RSSI_STRATUM_DB, n=k, rho=rho, ratio=ratio,
                        sf_lo=float(q[0]), sf_hi=float(q[1])))
    return out


def _fmt_strata(rows):
    lines = ["  RSSI   nwin      rho   MADratio   SF p20    SF p80",
             "  " + "-" * 52]
    for r in rows:
        lines.append(f"  {r['rssi']:>5.0f} {r['n']:>6d}  {r['rho']:>7.3f}"
                     f"   {r['ratio']:>7.3f}  {r['sf_lo']:>7.4f} {r['sf_hi']:>7.4f}")
    return "\n".join(lines)


def _stream_block(tag, mac, name, s, out):
    if s.n_acc < MIN_FRAMES_PER_STREAM or not s.win64:
        out.append(f"\n### {tag} / {name} {mac} — BELOW FLOOR "
                   f"(accepted {s.n_acc} < {MIN_FRAMES_PER_STREAM})")
        return None
    d = _arr(s.win64)
    keep = d["span"] <= MAX_WIN_SPAN_S
    n_drop = int((~keep).sum())
    if not keep.any():
        # A source slow enough that 64 accepted frames always span more than
        # MAX_WIN_SPAN_S cannot form a short window at all, so drift could not
        # be excluded from its dispersion. Reported, not silently dropped.
        out.append(f"\n### {tag} / {name} {mac} — NO SHORT WINDOW "
                   f"(accepted {s.n_acc}; all {len(s.win64)} windows of "
                   f"{W_PRIMARY} frames span > {MAX_WIN_SPAN_S}s, median "
                   f"{np.median(d['span']):.1f}s — too slow for this test)")
        return None
    d = {k: v[keep] for k, v in d.items()}
    d256 = _arr(s.win256) if s.win256 else None
    if d256 is not None:
        k2 = d256["span"] <= MAX_WIN_SPAN_S * (W_ROBUST / W_PRIMARY)
        d256 = {k: v[k2] for k, v in d256.items()}

    out.append(f"\n### {tag} / {name} {mac}")
    out.append(f"  rows(pre-screen) {s.n_raw}   fed {s.n_fed}   "
               f"accepted {s.n_acc} ({100.0*s.n_acc/max(s.n_fed,1):.1f}%)   "
               f"zero-bin frames {s.n_zero_bin}")
    out.append(f"  windows W=64: {len(s.win64)}  kept(span<=5s) {d['sf'].size}"
               f"  dropped {n_drop}   median span "
               f"{np.median(d['span']):.3f}s")
    out.append(f"  SF median {np.median(d['sf']):.4f}  "
               f"IQR [{np.percentile(d['sf'],25):.4f},"
               f"{np.percentile(d['sf'],75):.4f}]   "
               f"slope_mad median {np.median(d['mad']):.3e}   "
               f"RSSI {d['rssi'].min():.0f}..{d['rssi'].max():.0f}")

    pooled = spearman(d["sf"], d["mad"])
    pooled_rdb = spearman(d["rdb"], d["mad"])
    par_rssi = partial_spearman(d["sf"], d["mad"], [d["rssi"]])
    par_both = partial_spearman(d["sf"], d["mad"], [d["rssi"], d["resid"]])
    rho_resid = spearman(d["resid"], d["mad"])
    rho_sf_resid = spearman(d["sf"], d["resid"])
    out.append(f"  POOLED   rho(SF,mad) {pooled:+.3f}   "
               f"rho(ripple_dB,mad) {pooled_rdb:+.3f}")
    out.append(f"  PARTIAL  rho(SF,mad|RSSI) {par_rssi:+.3f}   "
               f"rho(SF,mad|RSSI,resid_std) {par_both:+.3f}")
    out.append(f"  context  rho(resid_std,mad) {rho_resid:+.3f}   "
               f"rho(SF,resid_std) {rho_sf_resid:+.3f}")

    rows = _strata(d)
    if len(rows) < 5:
        out.append(f"  STRATA   only {len(rows)} strata with >= "
                   f"{MIN_WIN_PER_STRATUM} windows — VOID for this stream")
        strat = None
    else:
        rhos = np.array([r["rho"] for r in rows])
        ratios = np.array([r["ratio"] for r in rows])
        frac = float(np.mean(rhos <= E1_STRATUM_RHO))
        out.append(f"  STRATA (1 dB, >= {MIN_WIN_PER_STRATUM} windows): "
                   f"{len(rows)} qualifying, {int(rhos.size)} rho values")
        out.append(_fmt_strata(rows))
        out.append(f"  STRATA median rho {np.median(rhos):+.3f}   "
                   f"frac(rho <= {E1_STRATUM_RHO}) {frac:.2f}   "
                   f"median MAD ratio (lowSF/highSF) "
                   f"{np.nanmedian(ratios):.3f}")
        strat = dict(median_rho=float(np.median(rhos)), frac=frac,
                     ratio=float(np.nanmedian(ratios)), k=len(rows))
        rows_rdb = _strata(d, key="rdb")
        if rows_rdb:
            out.append("  STRATA median rho(ripple_dB,mad) "
                       f"{np.median([r['rho'] for r in rows_rdb]):+.3f} "
                       "(predicted sign: POSITIVE)")

    if d256 is not None and d256["sf"].size > 100:
        r256 = _strata(d256)
        out.append(f"  W=256 windows {d256['sf'].size}  pooled rho "
                   f"{spearman(d256['sf'], d256['mad']):+.3f}   "
                   + (f"strata median rho "
                      f"{np.median([r['rho'] for r in r256]):+.3f} "
                      f"({len(r256)} strata)" if r256 else "no strata"))

    # ---- secondary quantitative test
    if s.s_slope:
        sl = np.asarray(s.s_slope); tau = np.asarray(s.s_tau)
        det = np.isfinite(tau)
        frac_det = float(det.mean())
        out.append(f"  TAU  sampled frames {sl.size}  detected "
                   f"{int(det.sum())} ({100*frac_det:.2f}%)")
        if det.sum() >= 200 and frac_det >= 0.20:
            dev = np.abs(sl[det] - np.median(sl))
            pred = 2.0 * math.pi * SUBCARRIER_SPACING_HZ * tau[det]
            rho = spearman(pred, dev)
            A = np.column_stack([pred, np.ones(pred.size)])
            coef = float(np.linalg.lstsq(A, dev, rcond=None)[0][0])
            out.append(f"       tau median {np.median(tau[det])*1e9:.1f} ns  "
                       f"p90 {np.percentile(tau[det],90)*1e9:.1f} ns   "
                       f"rho(pred,|dev|) {rho:+.3f}   coef {coef:.4f}")
        elif det.sum() >= 200:
            dev = np.abs(sl[det] - np.median(sl))
            pred = 2.0 * math.pi * SUBCARRIER_SPACING_HZ * tau[det]
            out.append(f"       below the 20% tractability floor; "
                       f"rho on detected subset {spearman(pred, dev):+.3f} "
                       "(reported, NOT counted as E5)")
    return dict(pooled=pooled, par_rssi=par_rssi, par_both=par_both,
                rho_resid=rho_resid, strat=strat, name=name, tag=tag)


def do_report(args):
    tags = args.tags.split(",")
    out = []
    results = []
    out.append("=" * 72)
    out.append("RIPPLE_TEST — results.  Pre-registration: docs/RIPPLE_TEST.md")
    out.append("=" * 72)
    for tag in tags:
        st = load(tag)
        out.append(f"\n## {tag}  {os.path.basename(st.path)}")
        out.append(f"  done={st.done}  rows(len==13) {st.rows}  "
                   f"screened-out(field) {st.bad_field}  "
                   f"unparseable {st.bad_parse}  short-csi {st.short_csi}  "
                   f"distinct MACs {len(st.streams)}  cpu {st.elapsed:.0f}s")
        span = ((st.t_last - st.t_first) * 1e-6) if st.t_first else 0.0
        out.append(f"  clean pc_time span {span:.1f} s")
        macs = sorted(st.streams, key=lambda m: -st.streams[m].n_acc)
        out.append("\n" + "-" * 30 + " BEACONS " + "-" * 31)
        for mac in macs:
            if mac in BEACON_MACS:
                r = _stream_block(tag, mac, BEACON_MACS[mac],
                                  st.streams[mac], out)
                if r:
                    r["beacon"] = True
                    results.append(r)
        out.append("\n" + "-" * 27 + " AMBIENT (separate) " + "-" * 25)
        n_amb = 0
        for mac in macs:
            if mac in BEACON_MACS:
                continue
            s = st.streams[mac]
            if s.n_acc < MIN_FRAMES_PER_STREAM:
                continue
            n_amb += 1
            r = _stream_block(tag, mac, "ambient", s, out)
            if r:
                r["beacon"] = False
                results.append(r)
        if n_amb == 0:
            out.append("  no ambient source cleared the "
                       f"{MIN_FRAMES_PER_STREAM}-accepted-frame floor")

    # ------------------------------------------------ frozen-criteria verdict
    out.append("\n" + "=" * 72)
    out.append("VERDICT against the frozen minimum effect sizes")
    out.append("=" * 72)
    bc = [r for r in results if r["beacon"] and r["strat"]]
    if not bc:
        out.append("  VOID — no beacon stream produced >= 5 qualifying strata")
    else:
        med = np.array([r["strat"]["median_rho"] for r in bc])
        frac = np.array([r["strat"]["frac"] for r in bc])
        rat = np.array([r["strat"]["ratio"] for r in bc])
        pb = np.array([r["par_both"] for r in bc])
        e1a = bool(np.all(med <= E1_MEDIAN_RHO))
        e1b = bool(np.all(frac >= E1_STRATUM_FRAC))
        e2 = bool(np.nanmedian(rat) >= E2_MAD_RATIO)
        e3 = bool(np.all(pb <= E3_PARTIAL_RHO))
        for r in bc:
            out.append(f"  {r['tag']:>5}/{r['name']}: strata median rho "
                       f"{r['strat']['median_rho']:+.3f}  "
                       f"frac<={E1_STRATUM_RHO} {r['strat']['frac']:.2f}  "
                       f"MADratio {r['strat']['ratio']:.3f}  "
                       f"partial|RSSI,resid {r['par_both']:+.3f}")
        out.append(f"\n  E1 median rho <= {E1_MEDIAN_RHO} on every beacon: "
                   f"{'MET' if e1a else 'NOT MET'}")
        out.append(f"  E1 frac(rho <= {E1_STRATUM_RHO}) >= {E1_STRATUM_FRAC} "
                   f"on every beacon: {'MET' if e1b else 'NOT MET'}")
        out.append(f"  E2 MAD ratio >= {E2_MAD_RATIO}: "
                   f"{'MET' if e2 else 'NOT MET'} "
                   f"(median {np.nanmedian(rat):.3f})")
        out.append(f"  E3 partial rho <= {E3_PARTIAL_RHO}: "
                   f"{'MET' if e3 else 'NOT MET'} "
                   f"(worst {np.max(pb):+.3f})")
        out.append("\n  PRIMARY (E1, within-RSSI-strata) = "
                   + ("SUPPORTED" if (e1a and e1b) else "NULL"))
        out.append("  Ripple beyond resid_std (E3) = "
                   + ("YES" if e3 else "NO"))
    txt = "\n".join(out)
    print(txt)
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, "report.txt"), "w") as f:
        f.write(txt + "\n")


# ------------------------------------------------------------------- checks

def _synth_tau_null(n=20000, seed=1):
    """Detection rate of estimate_tau on pure noise.

    The tau estimator is an argmax over an FFT; an argmax always lands
    somewhere. If white noise in the log-amplitude spectrum clears the
    PEAK_PROM gate at a high rate, then a high 'detection' rate on real data
    is evidence of nothing. This is the calibration that decides how to read
    the secondary test (CLAUDE.md failure mode E: open the record before
    blaming the mechanism).
    """
    rng = np.random.default_rng(seed)
    det = 0
    taus = []
    for _ in range(n):
        g = rng.standard_normal(53)
        g -= g.mean()
        sp = np.abs(np.fft.rfft(g * _WIN, NFFT)) ** 2
        lo = int(np.ceil(MIN_CYCLES * NFFT / 53.0))
        seg = sp[lo:]
        m = int(np.argmax(seg)) + lo
        med = float(np.median(sp[1:]))
        if med > 0 and sp[m] >= PEAK_PROM * med:
            det += 1
            taus.append(m / (NFFT * SUBCARRIER_SPACING_HZ))
    return det / n, (float(np.median(taus)) if taus else float("nan"))


def _load_frames(path, mac, limit, node_mode, chan_mode):
    """Raw interleaved int vectors for one MAC, screened, in file order."""
    out = []
    with open(path, "rb") as f:
        f.readline()
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            lines = chunk.decode("utf-8", "replace").splitlines()
            if lines and not chunk.endswith(b"\n"):
                lines = lines[:-1]
            for row in csv.reader(lines):
                if len(row) != 13 or row[3] != mac:
                    continue
                try:
                    rssi = int(row[4]); nf = int(row[5]); chan = int(row[6])
                    clen = int(row[8]); node = int(row[10]); env = int(row[11])
                    ts = int(row[7]); pc = int(row[0])
                except ValueError:
                    continue
                if (node != node_mode or env != 0 or chan != chan_mode
                        or clen not in CSI_LEN_OK
                        or not (NF_LO <= nf <= NF_HI)
                        or not (RSSI_LO <= rssi <= RSSI_HI)):
                    continue
                p = row[9].split(",", 128)
                if len(p) < 128:
                    continue
                out.append((np.array(p[:128], dtype=np.float64), ts, pc, rssi))
                if len(out) >= limit:
                    return out
    return out


def _inject(iq, tau, amp, rng):
    """Add a second path of delay tau and relative amplitude amp.

    H'(k) = H(k) * (1 + amp * exp(-j*2*pi*k*Delta_f*tau)), applied to the 52
    usable bins only (guards stay null), then re-quantised to the int8 grid the
    real capture lives on so the injected frame is no cleaner than a real one.
    """
    csi = csi_to_complex(iq).copy()
    ph = -2.0 * math.pi * SUBCARRIER_SPACING_HZ * tau * KF
    csi[_USABLE_IDX] *= (1.0 + amp * np.exp(1j * ph))
    out = np.empty(128)
    out[0::2] = np.clip(np.round(csi.imag), -128, 127)
    out[1::2] = np.clip(np.round(csi.real), -128, 127)
    return out


def do_checks(args):
    print("=" * 72)
    print("RIPPLE_TEST — verification checks")
    print("=" * 72)

    # --- 1. is the tau detector measuring delay, or an argmax over noise?
    rate, tmed = _synth_tau_null()
    print(f"\n[1] tau detector on pure noise: detection rate {100*rate:.2f}% "
          f", median tau {tmed*1e9:.1f} ns")
    print("    (compare with the per-stream detection rates in the report)")

    # --- 2/3. within-stratum residual-RSSI control and a shuffle placebo
    for tag in args.tags.split(","):
        st = load(tag)
        for mac, name in BEACON_MACS.items():
            s = st.streams.get(mac)
            if not s or not s.win64:
                continue
            d = _arr(s.win64)
            k = d["span"] <= MAX_WIN_SPAN_S
            d = {kk: vv[k] for kk, vv in d.items()}
            bins = np.round(d["rssi"] / RSSI_STRATUM_DB).astype(int)
            raw, res, shuf = [], [], []
            rng = np.random.default_rng(7)
            for b in np.unique(bins):
                m = bins == b
                if m.sum() < MIN_WIN_PER_STRATUM:
                    continue
                raw.append(spearman(d["sf"][m], d["mad"][m]))
                res.append(partial_spearman(d["sf"][m], d["mad"][m],
                                            [d["rssi"][m]]))
                sf2 = d["sf"][m].copy(); rng.shuffle(sf2)
                shuf.append(spearman(sf2, d["mad"][m]))
            if raw:
                print(f"\n[2] {tag}/{name}: strata median rho {np.median(raw):+.3f}"
                      f"  -> after removing residual within-stratum RSSI "
                      f"{np.median(res):+.3f}")
                print(f"[3] {tag}/{name}: shuffle placebo strata median rho "
                      f"{np.median(shuf):+.3f} (should be ~0)")

    # --- 4. POWER: would this test have seen a channel effect if one existed?
    print("\n[4] POWER CALIBRATION — inject a known varying two-path delay "
          "into real frames")
    nm, cm, _, _ = prescan(args.power_file)
    frames = _load_frames(args.power_file, args.power_mac, args.power_n, nm, cm)
    print(f"    {len(frames)} screened frames of {args.power_mac} from "
          f"{os.path.basename(args.power_file)}, amp={args.amp}")
    print("    tau spread    windows   SF median   rho(SF,mad)   "
          "MADratio(lowSF/highSF)   mad median")
    modes = args.power_mode.split(",")
    for mode in modes:
        print(f"    --- mode={mode} " + (
            "(tau i.i.d. per frame: every window gets the same delay-spread "
            "mixture)" if mode == "iid" else
            "(delay spread redrawn per 64-frame block: windows genuinely "
            "differ in delay spread, which is what the hypothesis compares)"))
        _power_sweep(frames, args, mode)


def _power_sweep(frames, args, mode):
    for spread_ns in [0.0] + [float(x) for x in args.spreads.split(",")]:
        rng = np.random.default_rng(11)
        est = FrameEstimator()
        buf, wins = [], []
        blk_spread, blk_i = 0.0, 0
        for iq, ts, pc, rssi in frames:
            if mode == "block" and blk_i % W_PRIMARY == 0:
                blk_spread = rng.uniform(0.0, spread_ns)
            blk_i += 1
            if spread_ns > 0:
                top = spread_ns if mode == "iid" else blk_spread
                tau = rng.uniform(0.0, top * 1e-9)
                v = _inject(iq, tau, args.amp, rng)
            else:
                v = iq
            e = est.feed(v, ts)
            if e is None or e["inlier_ratio"] < MIN_INLIER \
                    or e["resid_std"] > MAX_RESID:
                continue
            mag = np.abs(csi_to_complex(v)[_USABLE_IDX])
            sf = spectral_flatness(mag * mag)
            if sf == 0.0:
                continue
            buf.append((e["slope"], sf, ripple_db(mag), float(rssi),
                        e["resid_std"], pc))
            if len(buf) == W_PRIMARY:
                _emit(buf, wins)
                buf = []
        if not wins:
            print(f"    {spread_ns:>8.0f} ns   (no windows)")
            continue
        d = _arr(wins)
        q = np.percentile(d["sf"], [20, 80])
        lo, hi = d["mad"][d["sf"] <= q[0]], d["mad"][d["sf"] >= q[1]]
        ratio = float(np.median(lo) / np.median(hi)) if hi.size else float("nan")
        print(f"    {spread_ns:>8.0f} ns  {d['sf'].size:>8d}   "
              f"{np.median(d['sf']):>9.4f}   {spearman(d['sf'], d['mad']):>+11.3f}"
              f"   {ratio:>20.3f}   {np.median(d['mad']):>10.3e}")
    print("\n    A test that cannot show a large effect on injected data "
          "cannot interpret a null on real data.")


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("file")
    r.add_argument("--tag", required=True)
    r.add_argument("--restart", action="store_true")
    r.set_defaults(func=do_run)
    v = sub.add_parser("verify")
    v.add_argument("file")
    v.add_argument("--split-budget", type=float, default=8.0)
    v.set_defaults(func=do_verify)
    p = sub.add_parser("report")
    p.add_argument("--tags", required=True)
    p.set_defaults(func=do_report)
    c = sub.add_parser("checks")
    c.add_argument("--tags", required=True)
    c.add_argument("--power-file",
                   default="data/raw/d0wd_20260823_013537.csv")
    c.add_argument("--power-mac", default="28:05:a5:2f:fa:48")
    c.add_argument("--power-n", type=int, default=18000)
    c.add_argument("--amp", type=float, default=0.5)
    c.add_argument("--spreads", default="5,20,60,200")
    c.add_argument("--power-mode", default="iid,block")
    c.set_defaults(func=do_checks)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
