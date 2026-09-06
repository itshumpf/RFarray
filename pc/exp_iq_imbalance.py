#!/usr/bin/env python3
"""IQ imbalance from existing CSI -- estimator, controls, and the four tests
pre-registered in docs/IQ_IMBALANCE.md.

Read-only on data/raw/. No serial port. pc/rff/dsp.py is imported unmodified
and never written. pc/capture.py:compute_cfo, pc/phase_skew.py and
pc/fingerprint.py are not used.

Physics (docs/IQ_IMBALANCE.md 1.2-1.3). A direct-conversion front end maps
x(t) -> a*x(t) + b*conj(x(t)), i.e. X(k) -> a*X(k) + b*conj(X(-k)): conjugate
coupling between mirrored subcarriers. Multipath is linear and time-invariant
and CANNOT couple k to -k, which is the whole reason the feature is testable.
Carried through an L-LTF-based channel estimate with the real +-1 sequence
L(k):

    Hhat(k) ~ H(k)*(1 + e_t*s(k)) + e_r*s(k)*conj(H(-k)),  s(k)=L(k)*L(-k)

so the CONJUGATE term carries the receiver's imbalance and the transmitter's
appears as an s(k)-patterned ripple on the direct term. Both are estimated.

Subcommands
    selftest   convention check (1.4) + injection test (1.7) + synthetic
    scan       one capture file -> per (source, 600 s chunk) accumulators
    report     the four tests
"""
import argparse
import array
import csv
import hashlib
import json
import math
import os
import pickle
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from rff import dsp                                        # NOT modified

CACHE = os.environ.get("IQ_CACHE", "/tmp/iqimb")

# ------------------------------------------------------------- constants
# Corrupt-row screens, identical constants to pc/exp_receiver_term_prereg.py
# (docs/COLOCATED_0823.md 1, docs/DUAL_RX_2026-08-21.md Appendix A).
CSI_LEN_OK = (128, 256, 384)
NF_LO, NF_HI = -110, -70
RSSI_LO, RSSI_HI = -100, -10
MED_W = 9
MED_TOL = 100
U16 = 65536

CHUNK_S = 600.0            # docs/RECEIVER_TERM_PREREG.md 8.3's own binning
N_NULL = 64                # random even +-1 patterns (control 3)
NULL_SEED = 20260823
BOOT_B = 200
BOOT_SEED = 20260823

FLOOR_REPORT = 20          # pc/mac_census.py --min-frames 20
FLOOR_POWER = 2000         # prereg 6.1
FLOOR_CHUNK = 2000         # prereg 1.11

BEACONS = {
    "a4:f0:0f:77:91:20": "B1",
    "28:05:a5:2f:fa:48": "B2",
    "f4:2d:c9:70:72:30": "B3",
}

SLOPE_STRIDE = 8           # 1-in-8 subsample of admissible slopes
SLOPE_CAP = 8000
BATCH = 2048

# IEEE 802.11-2020 17.3.3 L-LTF frequency sequence, k = -26..26 (DC = 0).
# Its correctness is checked empirically by the roughness test of prereg 1.4
# when the buffer turns out to be the raw training symbol; if the buffer is
# already channel-divided the check cannot validate it, which is why the
# whole analysis is also run with s(k) == 1 (variant "s1").
LLTF_M26_26 = [
    1, 1, -1, -1, 1, 1, -1, 1, -1, 1, 1, 1, 1, 1, 1, -1, -1, 1, 1, -1,
    1, -1, 1, 1, 1, 1,
    0,
    1, -1, -1, 1, 1, -1, 1, -1, 1, -1, -1, -1, -1, -1, 1, 1, -1, -1, 1,
    -1, 1, -1, 1, 1, 1, 1,
]

# --------------------------------------------------- subcarrier geometry
K = dsp.K_USABLE.astype(np.float64)          # -26..-1, 1..26  (52)
NK = K.size
IDX = dsp._USABLE_IDX                        # buffer index per physical k
MIR = np.arange(NK)[::-1]                    # mirror: index of -k is 51-i
assert np.allclose(K[MIR], -K)

_L = np.array([LLTF_M26_26[int(k) + 26] for k in K], dtype=np.float64)
assert np.all(np.abs(_L) == 1.0)
S_TRUE = _L * _L[MIR]                        # s(k) = L(k) L(-k), even
assert np.allclose(S_TRUE, S_TRUE[MIR])

# adjacent-k pairs inside each contiguous block, never across DC
_ADJ = np.array([i for i in range(NK - 1) if i != 25], dtype=np.int64)

_rng = np.random.default_rng(NULL_SEED)
_r = _rng.integers(0, 2, size=(N_NULL, 26)) * 2 - 1        # +-1 per |k|
S_NULL = np.concatenate([_r[:, ::-1], _r], axis=1).astype(np.float64)
assert np.allclose(S_NULL, S_NULL[:, MIR])

# Wrong-pairing null: pair k with a SHIFTED mirror instead of -k. Same data,
# same coherent averaging, same frame-to-frame correlation structure -- only
# the conjugate relation is destroyed. This is the floor the alternate-frame
# split-half cannot give, because consecutive frames are not independent.
SHIFTS = (2, 5, 9, 13)
PART = np.stack([(51 - np.arange(NK) + d) % NK for d in SHIFTS])

GUARD_IDX = np.array([i for i in range(dsp.N_CPLX)
                      if not dsp._USABLE_MASK[i] and dsp._K_OF_IDX[i] != 0])


# ------------------------------------------------------------- utilities

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def circ(a, b):
    return ((a - b + 32768) % U16) - 32768


def med_flag(vals, ci):
    c = vals[ci]
    offs = sorted(circ(v, c) for v in vals)
    return abs(offs[len(offs) // 2]) > MED_TOL


def field_ok(node, env, chan, ln, nf, rssi, node_mode, chan_mode):
    return (node == node_mode and env == 0 and chan == chan_mode
            and ln in CSI_LEN_OK and NF_LO <= nf <= NF_HI
            and RSSI_LO <= rssi <= RSSI_HI)


def smooth_blocks(X, w=5):
    """Moving average of width w within each contiguous block, shrinking at
    the block edges. X is (F, 52)."""
    out = np.empty_like(X)
    half = w // 2
    for a, b in ((0, 26), (26, 52)):
        Y = X[:, a:b]
        n = b - a
        z = np.zeros((Y.shape[0], 1), dtype=Y.dtype)
        c = np.cumsum(np.concatenate([z, Y], axis=1), axis=1)
        lo = np.maximum(np.arange(n) - half, 0)
        hi = np.minimum(np.arange(n) + half + 1, n)
        out[:, a:b] = (c[:, hi] - c[:, lo]) / (hi - lo)
    return out


def roughness(V):
    """Normalised across-k roughness, adjacent pairs inside blocks only."""
    d = V[:, _ADJ + 1] - V[:, _ADJ]
    num = (np.abs(d) ** 2).sum(axis=1)
    den = (np.abs(V) ** 2).sum(axis=1)
    ok = den > 0
    return float(np.mean(num[ok] / den[ok])) if ok.any() else float("nan")


# --------------------------------------------------------- the estimator

def frames_to_H(raw):
    """(F, >=128) int8 CSI values -> (F, 52) complex, physical-k order.

    Uses dsp.csi_to_complex's convention verbatim: the buffer is imag,real
    interleaved so the complex value is iq[1::2] + 1j*iq[0::2]. Getting this
    backwards inverts every conjugate relationship under test.
    """
    iq = raw[:, :dsp.N_CPLX * 2]
    Z = iq[:, 1::2] + 1j * iq[:, 0::2]
    return Z[:, IDX]


def deslope(H):
    """Remove the per-frame linear phase ramp and the flat across-k mean.

    THE PER-FRAME COMMON PHASE IS DELIBERATELY *NOT* REMOVED. With
    Hhat(k) = a*H(k)*e^{j p} + b*s(k)*conj(H(-k))*e^{-j p}, the direct term
    rotates with the residual carrier phase p and the image term
    counter-rotates. In D(k)D(-k) the cross terms are therefore
    phase-INVARIANT and carry the imbalance, while the pure-channel term
    carries e^{2 j p} and averages away across frames. Removing the
    intercept inverts that: it makes the channel term coherent and the
    imbalance term incoherent, which destroys the measurement. See
    docs/IQ_IMBALANCE.md 10.1 -- the Stage-1 text specified intercept
    removal and the 1.7 stop-condition test caught it.

    Deterministic and order-independent, unlike dsp.ransac_line, whose
    per-instance RNG advances once per frame (dsp.py:118,132) and therefore
    forbids subsampling or per-chunk analysis. This slope is NOT the shipped
    SFO estimator and is never compared to BETWEEN_UNIT_SD.
    """
    d = H[:, _ADJ + 1] * np.conj(H[:, _ADJ])
    m = np.angle(d.sum(axis=1))                       # rad / subcarrier
    D = H * np.exp(-1j * m[:, None] * K[None, :])
    return D - D.mean(axis=1, keepdims=True), D, m


class Cell:
    """Accumulators for one (source MAC, 600 s chunk). Every field is a plain
    sum, so chunk cells add to give the whole-source value."""
    __slots__ = ("n", "n_clean", "n_inadm", "P", "A", "B", "A0", "B0",
                 "Aabs", "Ah1", "Ah2", "Arand", "Tn", "Td", "Trand",
                 "rssi_sum", "slopes", "t_lo", "t_hi", "parity",
                 "Ck", "Ck1", "Ck2", "n1", "n2", "Wk", "Csh")

    def __init__(self):
        self.Csh = np.zeros((len(SHIFTS), NK), dtype=np.complex128)
        self.Ck = np.zeros(NK, dtype=np.complex128)
        self.Ck1 = np.zeros(NK, dtype=np.complex128)
        self.Ck2 = np.zeros(NK, dtype=np.complex128)
        self.Wk = np.zeros(NK, dtype=np.float64)
        self.n1 = 0
        self.n2 = 0
        self.n = 0
        self.n_clean = 0
        self.n_inadm = 0
        self.P = 0.0
        self.A = 0j
        self.B = 0j
        self.A0 = 0j
        self.B0 = 0j
        self.Aabs = 0.0
        self.Ah1 = 0j
        self.Ah2 = 0j
        self.Arand = np.zeros(N_NULL, dtype=np.complex128)
        self.Tn = 0j
        self.Td = 0.0
        self.Trand = np.zeros(N_NULL, dtype=np.complex128)
        self.rssi_sum = 0.0
        self.slopes = array.array("d")
        self.t_lo = None
        self.t_hi = None
        self.parity = 0


def process_batch(cell, raw, s_vec, variant_div):
    """Fold one batch of frames of one cell into its accumulators."""
    X = np.asarray(raw, dtype=np.float64)
    H = frames_to_H(X)

    # admissibility (prereg 1.9)
    guard = X[:, :dsp.N_CPLX * 2].reshape(X.shape[0], dsp.N_CPLX, 2)[:, GUARD_IDX, :]
    ok = (np.abs(guard).sum(axis=(1, 2)) == 0)
    ok &= (np.abs(H) == 0).sum(axis=1) <= 4
    cell.n_inadm += int((~ok).sum())
    if not ok.any():
        return
    H = H[ok]

    if not variant_div:                     # buffer is the raw training sym
        H = H * _L[None, :]

    G, D, m = deslope(H)
    P = (np.abs(G) ** 2).sum(axis=1)
    good = np.isfinite(P) & (P > 0)
    if not good.all():
        G, D, m, P = G[good], D[good], m[good], P[good]
        cell.n_inadm += int((~good).sum())
    F = G.shape[0]
    if F == 0:
        return

    Gm = G[:, MIR]
    prodC = G * Gm                       # G(k) G(-k)      conjugate coupling
    prodN = G * np.conj(Gm)              # G(k) G*(-k)     mirror symmetry

    Af = prodC @ s_vec
    Bf = prodN @ s_vec
    A0f = prodC.sum(axis=1)
    B0f = prodN.sum(axis=1)
    Arand = prodC @ S_NULL.T             # (F, N_NULL)

    # TX ripple: relative to the SMOOTH channel, so the full D (not the
    # mean-removed G) is the right reference. Phase-invariant already.
    Db = smooth_blocks(D)
    Tf = ((D * np.conj(Db)) * s_vec[None, :]).sum(axis=1)
    Tdf = (np.abs(Db) ** 2).sum(axis=1)
    Trand = (D * np.conj(Db)) @ S_NULL.T

    cell.n += F
    cell.P += float(P.sum())
    cell.A += complex(Af.sum())
    cell.B += complex(Bf.sum())
    cell.A0 += complex(A0f.sum())
    cell.B0 += complex(B0f.sum())
    cell.Aabs += float(np.abs(Af).sum())
    cell.Arand += Arand.sum(axis=0)
    cell.Tn += complex(Tf.sum())
    cell.Td += float(Tdf.sum())
    cell.Trand += Trand.sum(axis=0)

    # per-subcarrier coherent mirror product -- the pattern-free route.
    # E[ D~(k) D~(-k) ] = 2*a*b*s(k)*E|H~(k)|^2 : the channel term carries
    # e^{2 j p} and averages away, the imbalance term does not.
    cell.Ck += prodC.sum(axis=0)
    cell.Wk += (np.abs(G) ** 2).sum(axis=0)
    for d in range(len(SHIFTS)):
        cell.Csh[d] += (G * G[:, PART[d]]).sum(axis=0)

    # split-half on alternate admissible frames, parity carried across batches
    par = (np.arange(F) + cell.parity) % 2
    cell.Ah1 += complex(Af[par == 0].sum())
    cell.Ah2 += complex(Af[par == 1].sum())
    cell.Ck1 += prodC[par == 0].sum(axis=0)
    cell.Ck2 += prodC[par == 1].sum(axis=0)
    cell.n1 += int((par == 0).sum())
    cell.n2 += int((par == 1).sum())
    cell.parity = int((cell.parity + F) % 2)

    if len(cell.slopes) < SLOPE_CAP:
        take = m[::SLOPE_STRIDE][: SLOPE_CAP - len(cell.slopes)]
        cell.slopes.extend(take.tolist())


# ---------------------------------------------------------------- derived

def features(c):
    """Cell accumulators -> the pre-registered feature dict."""
    if c.n == 0 or c.P <= 0:
        return None
    twoP = 2.0 * c.P
    kap = c.A / twoP
    nul = np.abs(c.Arand / twoP)
    kh1 = c.Ah1 / (c.P if c.P else 1.0)      # halves share the normaliser
    kh2 = c.Ah2 / (c.P if c.P else 1.0)
    coh = abs(c.A) / c.Aabs if c.Aabs > 0 else 0.0
    coh_floor = 5.0 * 0.886 / math.sqrt(c.n)
    tau = c.Tn / c.Td if c.Td > 0 else 0j
    tnull = np.abs(c.Trand / c.Td) if c.Td > 0 else np.zeros(N_NULL)
    det = (abs(kap) > float(nul.max())
           and abs(kh1 - kh2) < abs(kh1 + kh2) / 2.0
           and coh >= coh_floor)

    # ---- pattern-free route (Stage-2 addition, docs/IQ_IMBALANCE.md 10.2)
    # c(k) = coherent mean of D~(k)D~(-k). Under the model this is
    # 2*a*b*s(k)*w(k) with w(k) >= 0, so |eps| = sum_k |c(k)| / (2p) needs
    # no knowledge of s(k) at all. Noise on c(k) is estimated from the two
    # independent alternate-frame halves: Var(c) = |c1-c2|^2 / 4.
    p = c.P / c.n
    ck = c.Ck / c.n
    if c.n1 > 0 and c.n2 > 0:
        c1, c2 = c.Ck1 / c.n1, c.Ck2 / c.n2
        vk = np.abs(c1 - c2) ** 2 / 4.0
    else:
        vk = np.zeros(NK)
    mag = np.sqrt(np.maximum(np.abs(ck) ** 2 - vk, 0.0))
    kfree = float(mag.sum() / (2 * p))
    kfree_floor = float(np.sqrt(vk).sum() / (2 * p))
    # ALIGNMENT (Stage-2 primary, docs/IQ_IMBALANCE.md 10.3): under the
    # model c(k) = 2*a*b*s(k)*w(k) with w(k) >= 0 real, so every c(k) lies
    # on ONE complex axis with exactly the sign pattern s(k). align -> 1.
    # For any wrong pairing the phases scatter and align -> ~1/sqrt(52).
    # sum_k|c(k)| CANNOT discriminate -- it discards the phase that carries
    # the mirror specificity -- so it is reported but is not the test.
    sck = np.abs((S_TRUE * ck).sum())
    align = float(sck / np.abs(ck).sum()) if np.abs(ck).sum() > 0 else 0.0
    al_sh, kap_sh = [], []
    for d in range(len(SHIFTS)):
        cd = c.Csh[d] / c.n
        sd = np.abs((S_TRUE * cd).sum())
        al_sh.append(float(sd / np.abs(cd).sum()) if np.abs(cd).sum() > 0
                     else 0.0)
        kap_sh.append(float(sd / (2 * p)))
    align_sh = max(al_sh)
    kappa_mir = float(sck / (2 * p))
    det2 = (align > align_sh
            and abs(kh1 - kh2) < abs(kh1 + kh2) / 2.0
            and coh >= coh_floor)
    sh = np.abs(c.Csh / c.n).sum(axis=1) / (2 * p)
    kfree_wrongpair = float(sh.max())
    kfree_wp_all = [float(x) for x in sh]
    # dominant complex axis of c(k), found without reference to s(k)
    u = 0.5 * np.angle((ck ** 2).sum()) if np.abs(ck).sum() > 0 else 0.0
    proj = np.real(ck * np.exp(-1j * u))
    axis_frac = (float((proj ** 2).sum() / (np.abs(ck) ** 2).sum())
                 if (np.abs(ck) ** 2).sum() > 0 else float("nan"))
    shat = np.where(proj >= 0, 1.0, -1.0)
    agree = float(max((shat == S_TRUE).mean(), (shat == -S_TRUE).mean()))

    return {
        "align": align, "align_shift": align_sh,
        "align_ratio": align / align_sh if align_sh > 0 else float("nan"),
        "kappa_mir": kappa_mir, "kappa_shift_max": max(kap_sh),
        "detected2": bool(det2), "al_sh": al_sh,
        "kfree": kfree, "kfree_floor": kfree_floor,
        "kfree_wrongpair": kfree_wrongpair, "kfree_wp_all": kfree_wp_all,
        "kfree_wp_snr": (kfree / kfree_wrongpair
                         if kfree_wrongpair > 0 else float("nan")),
        "kfree_snr": kfree / kfree_floor if kfree_floor > 0 else float("nan"),
        "ck": ck, "vk": vk, "wk": c.Wk / c.n, "p": p,
        "axis_frac": axis_frac, "s_agree": agree, "axis_arg": u,
        "ck_vec": ck / (2 * p),
        "n": c.n, "n_clean": c.n_clean, "n_inadm": c.n_inadm,
        "kappa": kap, "nu": c.B / twoP,
        "kappa0": c.A0 / twoP, "nu0": c.B0 / twoP,
        "null_max": float(nul.max()), "null_rms": float(np.sqrt((nul ** 2).mean())),
        "coh": coh, "coh_floor": coh_floor,
        "kh1": kh1, "kh2": kh2,
        "tau": tau, "tau_null_max": float(tnull.max()),
        "detected": bool(det),
        "slope_med": (float(np.median(np.frombuffer(c.slopes, dtype=np.float64)))
                      if len(c.slopes) else float("nan")),
        "rssi": c.rssi_sum / c.n_clean if c.n_clean else float("nan"),
    }


def add_cells(cells):
    out = Cell()
    for c in cells:
        out.n += c.n
        out.n_clean += c.n_clean
        out.n_inadm += c.n_inadm
        out.P += c.P
        out.A += c.A
        out.B += c.B
        out.A0 += c.A0
        out.B0 += c.B0
        out.Aabs += c.Aabs
        out.Ah1 += c.Ah1
        out.Ah2 += c.Ah2
        out.Arand = out.Arand + c.Arand
        out.Tn += c.Tn
        out.Td += c.Td
        out.Trand = out.Trand + c.Trand
        out.rssi_sum += c.rssi_sum
        out.Ck = out.Ck + c.Ck
        out.Ck1 = out.Ck1 + c.Ck1
        out.Ck2 = out.Ck2 + c.Ck2
        out.Wk = out.Wk + c.Wk
        out.Csh = out.Csh + c.Csh
        out.n1 += c.n1
        out.n2 += c.n2
        if len(out.slopes) < SLOPE_CAP:
            out.slopes.extend(c.slopes[: SLOPE_CAP - len(out.slopes)])
    return out


# ------------------------------------------------------------------ scan

class Lines:
    """Byte-exact line source; opened 'rb', the file is never written."""

    def __init__(self, path, start=0):
        self.f = open(path, "rb")
        self.f.seek(start)
        self.pos = start

    def __iter__(self):
        for raw in self.f:
            self.pos += len(raw)
            yield raw.decode("utf-8", "replace")

    def close(self):
        self.f.close()


class Scan:
    def __init__(self, tag, path):
        self.tag = tag
        self.path = path
        self.rows = 0
        self.bad_parse = 0
        self.n_field_bad = 0
        self.n_med_bad = 0
        self.n_both = 0
        self.n_corrupt = 0
        self.n_medonly = 0
        self.corrupt_macs = defaultdict(int)
        self.cells = defaultdict(Cell)          # (mac, chunk) -> Cell
        self.raw_n = defaultdict(int)
        self.t0_us = None
        self.t_last_us = None
        self.node_hist = defaultdict(int)
        self.chan_hist = defaultdict(int)
        self.node_mode = None
        self.chan_mode = None
        self.byte_pos = 0
        self.pend = []
        self.n_hist = 0
        self.eof = False
        self.resumes = []


def run_scan(args):
    os.makedirs(CACHE, exist_ok=True)
    csv.field_size_limit(10 ** 7)
    variant_div = (args.convention == "divided")
    s_vec = np.ones(NK) if args.svar == "s1" else S_TRUE
    spath = os.path.join(CACHE, f"{args.tag}_{args.svar}_scan.pkl")

    if args.resume and os.path.exists(spath):
        with open(spath, "rb") as f:
            st = pickle.load(f)
        if st.eof:
            print(f"[{args.tag}] already at EOF, rows={st.rows:,}",
                  file=sys.stderr)
            return
        st.resumes.append((st.rows, st.byte_pos))
        L = Lines(args.path, st.byte_pos)
        r = csv.reader(iter(L))
    else:
        st = Scan(args.tag, args.path)
        # --- 20,000-row prescan for the screen modes, re-checked whole-file
        nh, ch = defaultdict(int), defaultdict(int)
        L = Lines(args.path)
        it = iter(L)
        header = next(csv.reader([next(it)]))
        assert header[:13] == ["pc_time_us", "label", "seq", "mac", "rssi",
                               "noise_floor", "channel", "esp_timestamp_us",
                               "len", "csi_data", "node_id", "env_id",
                               "dropped"], header
        for i, line in enumerate(it):
            if i >= 20000:
                break
            row = next(csv.reader([line]), None)
            if row is None or len(row) != 13:
                continue
            try:
                nh[int(row[10])] += 1
                ch[int(row[6])] += 1
            except ValueError:
                continue
        L.close()
        st.node_mode = max(nh.items(), key=lambda kv: kv[1])[0]
        st.chan_mode = max(ch.items(), key=lambda kv: kv[1])[0]
        L = Lines(args.path)
        it2 = iter(L)
        next(it2)
        st.byte_pos = L.pos
        L.close()
        L = Lines(args.path, st.byte_pos)
        r = csv.reader(iter(L))
    pend = st.pend
    n_hist = st.n_hist
    half = MED_W // 2
    bufs = defaultdict(list)                 # (mac, chunk) -> [csi rows]
    t0 = time.time()

    def emit(rec):
        (pc_us, mac, rssi, drop, csi_s, fbad, mbad) = rec
        if fbad:
            st.n_field_bad += 1
        if mbad:
            st.n_med_bad += 1
        if fbad and mbad:
            st.n_both += 1
        if mbad and not fbad:
            st.n_medonly += 1
        if fbad or mbad:
            st.n_corrupt += 1
            st.corrupt_macs[mac] += 1
            return
        tsec = (pc_us - st.t0_us) * 1e-6
        chunk = int(tsec // CHUNK_S)
        key = (mac, chunk)
        c = st.cells[key]
        c.n_clean += 1
        c.rssi_sum += rssi
        if c.t_lo is None:
            c.t_lo = tsec
        c.t_hi = tsec
        try:
            vals = [int(x) for x in csi_s.split(",", dsp.N_CPLX * 2)
                    [: dsp.N_CPLX * 2]]
        except ValueError:
            c.n_inadm += 1
            return
        if len(vals) < dsp.N_CPLX * 2:
            c.n_inadm += 1
            return
        b = bufs[key]
        b.append(vals)
        if len(b) >= BATCH:
            process_batch(c, b, s_vec, variant_div)
            bufs[key] = []

    def flush_pend(force):
        nonlocal n_hist
        while n_hist < len(pend):
            ci = n_hist
            if not force and (len(pend) - 1 - ci) < half:
                return
            lo = max(0, ci - half)
            hi = min(len(pend), ci + half + 1)
            vals = [pend[k][3] for k in range(lo, hi)]
            mbad = med_flag(vals, ci - lo) if len(vals) >= 3 else False
            rec = pend[ci]
            emit((rec[0], rec[1], rec[2], rec[3], rec[4], rec[5], mbad))
            n_hist += 1
            while n_hist > half:
                del pend[0]
                n_hist -= 1

    deadline = time.time() + args.seconds if args.seconds else None
    stopped_early = False
    for row in r:
        st.rows += 1
        if args.max_rows and st.rows > args.max_rows:
            st.rows -= 1
            stopped_early = True
            break
        if len(row) != 13:
            st.bad_parse += 1
            flush_pend(False)
            continue
        try:
            pc_us = int(row[0])
            mac = row[3].lower()
            rssi = int(row[4])
            nf = int(row[5])
            chan = int(row[6])
            ln = int(row[8])
            node = int(row[10])
            env = int(row[11])
            drop = int(row[12])
        except ValueError:
            st.bad_parse += 1
            flush_pend(False)
            continue
        st.node_hist[node] += 1
        st.chan_hist[chan] += 1
        if st.t0_us is None:
            st.t0_us = pc_us
        st.t_last_us = pc_us
        st.raw_n[mac] += 1
        fbad = not field_ok(node, env, chan, ln, nf, rssi,
                            st.node_mode, st.chan_mode)
        pend.append((pc_us, mac, rssi, drop, row[9], fbad))
        flush_pend(False)
        if st.rows % 20000 == 0:
            if st.rows % 500000 == 0:
                print(f"[{args.tag}] {st.rows:,} rows  "
                      f"{time.time()-t0:.0f}s  corrupt={st.n_corrupt}",
                      file=sys.stderr, flush=True)
            if deadline and time.time() > deadline:
                stopped_early = True
                break

    st.byte_pos = L.pos
    if not stopped_early:
        # true EOF: the tail rows are judged on the shorter window they
        # have, which is all a filter can do at a boundary
        flush_pend(True)
        st.eof = True
    for key, b in bufs.items():
        if b:
            process_batch(st.cells[key], b, s_vec, variant_div)
    L.close()
    st.pend = pend
    st.n_hist = n_hist

    with open(spath, "wb") as f:
        pickle.dump(st, f, protocol=4)
    print(f"[{args.tag}] {'DONE' if st.eof else 'CHECKPOINT'} "
          f"rows={st.rows:,} corrupt={st.n_corrupt} "
          f"(field={st.n_field_bad} med={st.n_med_bad} both={st.n_both} "
          f"med-only={st.n_medonly}) byte_pos={st.byte_pos:,} "
          f"in {time.time()-t0:.0f}s", file=sys.stderr, flush=True)


# -------------------------------------------------------------- selftest

def sample_frames(path, mac, want=20000, max_rows=400000):
    """Clean-screened frames of one MAC, for the convention and injection
    checks. Field screen only -- these frames are used to exercise the
    estimator, not to produce a reported feature value."""
    csv.field_size_limit(10 ** 7)
    L = Lines(path)
    r = csv.reader(iter(L))
    next(r)
    out = []
    for i, row in enumerate(r):
        if i >= max_rows or len(out) >= want:
            break
        if len(row) != 13 or row[3].lower() != mac:
            continue
        try:
            if int(row[11]) != 0 or int(row[8]) not in CSI_LEN_OK:
                continue
            vals = [int(x) for x in row[9].split(",", 128)[:128]]
        except ValueError:
            continue
        if len(vals) == 128:
            out.append(vals)
    L.close()
    return np.asarray(out, dtype=np.float64)


def kappa_nu(G, s_vec):
    """Coherent (complex) mean over frames -- correct only because the
    intercept is NOT removed (see deslope)."""
    P = (np.abs(G) ** 2).sum()
    Gm = G[:, MIR]
    A = ((G * Gm) * s_vec[None, :]).sum()
    B = ((G * np.conj(Gm)) * s_vec[None, :]).sum()
    return A / (2 * P), B / (2 * P)


def kappa_null(G, s_null=S_NULL):
    P = (np.abs(G) ** 2).sum()
    prodC = G * G[:, MIR]
    return np.abs((prodC @ s_null.T).sum(axis=0) / (2 * P))


def run_selftest(args):
    print("=" * 74)
    print("SELFTEST -- docs/IQ_IMBALANCE.md 1.1, 1.4, 1.7")
    print("=" * 74)

    d = os.path.dirname(os.path.abspath(dsp.__file__))
    p = os.path.join(d, "dsp.py")
    print(f"\npc/rff/dsp.py  sha256={sha256(p)}")
    print(f"               mtime={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(p)))}")
    src = open(p, "rb").read().decode()
    conv = "iq[1::2] + 1j * iq[0::2]"
    print(f"  interleave convention '{conv}' present in dsp.py: "
          f"{conv in src}")
    v = np.array([7.0, 3.0] + [0.0] * 126)           # imag=7, real=3
    z = dsp.csi_to_complex(v)
    print(f"  csi_to_complex([imag=7,real=3,...])[0] = {z[0]}  "
          f"-> real={z[0].real:.0f} imag={z[0].imag:.0f}  "
          f"(expect 3+7j)")
    mine = frames_to_H(v[None, :])
    k0 = int(np.where(dsp.K_USABLE == 1)[0][0])
    print(f"  frames_to_H agrees with csi_to_complex on all 52 usable k: "
          f"{np.allclose(mine[0], z[IDX])}")
    print(f"  L-LTF s(k)=L(k)L(-k): even={np.allclose(S_TRUE, S_TRUE[MIR])}, "
          f"n(+1)={int((S_TRUE > 0).sum())}, n(-1)={int((S_TRUE < 0).sum())}")
    print(f"  L(k) k=1..26: "
          f"{''.join('+' if x > 0 else '-' for x in _L[26:])}")

    # ---- synthetic recovery: known epsilon on a known channel -----------
    print("\n--- synthetic: does kappa recover a known conjugate term? ---")
    rng = np.random.default_rng(7)
    F = 4000
    taps = rng.normal(size=(F, 6)) + 1j * rng.normal(size=(F, 6))
    delays = np.array([0, 1.5, 3.1, 5.0, 7.7, 11.0])
    Hs = (taps[:, None, :] * np.exp(-2j * np.pi * K[None, :, None]
                                    * delays[None, None, :] / 64.0)).sum(-1)
    Hs *= np.exp(-1j * (0.03 * K[None, :] + rng.uniform(0, 2 * np.pi, (F, 1))))
    print(f"{'eps_r injected':>18} {'kappa':>24} {'|kappa|':>9} "
          f"{'arg':>7} {'|nu|':>9} {'null_max':>9}")
    k_ref = None
    for eps in (0.0, 0.005, 0.02, 0.05, 0.10):
        e = eps * np.exp(1j * 0.7)
        Hm = Hs + e * S_TRUE[None, :] * np.conj(Hs[:, MIR])
        G, _, _ = deslope(Hm)
        kap, nu = kappa_nu(G, S_TRUE)
        if k_ref is None:
            k_ref = kap
        print(f"{eps:>18.4f} {cfmt(kap):>24} {abs(kap):>9.5f} "
              f"{np.angle(kap):>7.3f} {abs(nu):>9.5f} "
              f"{kappa_null(G).max():>9.5f}"
              + ("   (arg injected 0.700)" if eps else ""))
    print("    recovery slope d(kappa)/d(eps) should be ~1.0 with arg 0.700")

    # ---- convention check + injection on real frames --------------------
    for tag, path, mac in args.pairs:
        print(f"\n--- {tag}: {os.path.basename(path)}  mac={mac} ---")
        X = sample_frames(path, mac, want=args.nframes)
        print(f"  frames sampled: {X.shape[0]}")
        if X.shape[0] < 100:
            print("  too few frames; skipping")
            continue
        H = frames_to_H(X)
        g = X[:, :128].reshape(-1, 64, 2)[:, GUARD_IDX, :]
        ok = np.abs(g).sum(axis=(1, 2)) == 0
        print(f"  guard bins exactly zero on {ok.sum()}/{len(ok)} frames "
              f"({100.0*ok.mean():.2f}%)")
        H = H[ok]
        r0 = roughness(H)
        r1 = roughness(H * _L[None, :])
        print(f"  ROUGH(V0 = buffer as-is)        {r0:.5f}")
        print(f"  ROUGH(V1 = buffer x L(k))       {r1:.5f}")
        if r0 < r1 / 2:
            verdict = "ALREADY DIVIDED (use V0, s(k) from the standard)"
        elif r1 < r0 / 2:
            verdict = "RAW TRAINING SYMBOL (use V1; this validates L(k))"
        else:
            verdict = "INCONCLUSIVE -- carry both branches"
        print(f"  -> {verdict}")

        for use_div, name in ((True, "V0"), (False, "V1")):
            Hx = H if use_div else H * _L[None, :]
            G, Dfull, _ = deslope(Hx)
            nullmax = kappa_null(G).max()
            print(f"\n  [{name}] injection test (prereg 1.7), s = L(k)L(-k)")
            print(f"    {'inject':>22} {'kappa':>22} {'nu':>22} "
                  f"{'|d kappa|':>10} {'|d nu|':>10}")
            k0v, n0v = kappa_nu(G, S_TRUE)
            print(f"    {'none':>22} {cfmt(k0v):>22} {cfmt(n0v):>22}"
                  f"     (null_max over 64 random patterns "
                  f"{nullmax:.5f})")
            for b in (0.01, 0.05):
                # a conjugate injection acts on the un-mean-removed frame,
                # so its image counter-rotates exactly as the physics says
                Hi = Hx + b * S_TRUE[None, :] * np.conj(Hx[:, MIR])
                Gi, _, _ = deslope(Hi)
                kk, nn = kappa_nu(Gi, S_TRUE)
                print(f"    {'conj beta=%.3f' % b:>22} {cfmt(kk):>22} "
                      f"{cfmt(nn):>22} {abs(kk-k0v):>10.5f} "
                      f"{abs(nn-n0v):>10.5f}")
            for gm in (0.01, 0.05):
                # a mirror-symmetric (NON-conjugate) channel perturbation
                Hi = Hx + gm * S_TRUE[None, :] * Hx[:, MIR]
                Gi, _, _ = deslope(Hi)
                kk, nn = kappa_nu(Gi, S_TRUE)
                print(f"    {'nonconj gamma=%.3f' % gm:>22} {cfmt(kk):>22} "
                      f"{cfmt(nn):>22} {abs(kk-k0v):>10.5f} "
                      f"{abs(nn-n0v):>10.5f}")


# ---------------------------------------------------------------- report

def cfmt(z):
    return f"{z.real:+.5f}{z.imag:+.5f}j"


def load(tag, svar):
    with open(os.path.join(CACHE, f"{tag}_{svar}_scan.pkl"), "rb") as f:
        return pickle.load(f)


def dispersion(vals, mu):
    return math.sqrt(float(np.mean(np.abs(np.asarray(vals) - mu) ** 2)))


def kmeans_complex(X, k, seed=20260823, restarts=50):
    rng = np.random.default_rng(seed)
    P = np.column_stack([X.real, X.imag])
    best, best_lab, best_in = None, None, None
    for _ in range(restarts):
        c = P[rng.choice(len(P), k, replace=False)]
        lab = None
        for _ in range(100):
            d = ((P[:, None, :] - c[None, :, :]) ** 2).sum(-1)
            nl = d.argmin(1)
            if lab is not None and (nl == lab).all():
                break
            lab = nl
            for j in range(k):
                if (lab == j).any():
                    c[j] = P[lab == j].mean(0)
        inert = ((P - c[lab]) ** 2).sum()
        if best is None or inert < best:
            best, best_lab, best_in = inert, lab.copy(), c.copy()
    return best_lab


def purity_ari(lab, truth):
    lab = np.asarray(lab)
    truth = np.asarray(truth)
    n = len(lab)
    cm = defaultdict(lambda: defaultdict(int))
    for a, b in zip(lab, truth):
        cm[a][b] += 1
    pur = sum(max(v.values()) for v in cm.values()) / n
    # adjusted Rand
    def comb2(x):
        return x * (x - 1) / 2
    sij = sum(comb2(v) for row in cm.values() for v in row.values())
    ai = sum(comb2(sum(row.values())) for row in cm.values())
    bj = defaultdict(int)
    for row in cm.values():
        for b, v in row.items():
            bj[b] += v
    bjs = sum(comb2(v) for v in bj.values())
    exp = ai * bjs / comb2(n)
    mx = (ai + bjs) / 2
    ari = (sij - exp) / (mx - exp) if mx != exp else 1.0
    return pur, ari


def run_report(args):
    tags = args.tags.split(",")
    svar = args.svar
    sts = {t: load(t, svar) for t in tags}
    out = []
    P = out.append

    P("=" * 78)
    P(f"IQ IMBALANCE -- results   (s variant = {svar}, "
      f"convention = {args.convention})")
    P("=" * 78)

    # ---------------------------------------------------- integrity
    P("\n## Integrity")
    for t in tags:
        st = sts[t]
        sz = os.path.getsize(st.path)
        P(f"  {t}: rows={st.rows:,}  bad_parse={st.bad_parse}  "
          f"byte_pos={st.byte_pos:,}  file_size={sz:,}  "
          f"{'EOF-EXACT' if st.byte_pos == sz else 'PARTIAL'}")
        P(f"      corrupt union={st.n_corrupt}  field={st.n_field_bad}  "
          f"median={st.n_med_bad}  both={st.n_both}  "
          f"median-ONLY={st.n_medonly}")
        nm = max(st.node_hist.items(), key=lambda kv: kv[1])[0]
        cm = max(st.chan_hist.items(), key=lambda kv: kv[1])[0]
        P(f"      prescan mode node={st.node_mode} chan={st.chan_mode}; "
          f"whole-file node={nm} chan={cm}; "
          f"{'AGREE' if (nm, cm) == (st.node_mode, st.chan_mode) else 'DISAGREE'}")
        P(f"      fabricated-MAC check: {len(st.corrupt_macs)} distinct MACs "
          f"appear on corrupt rows and were screened out")
        span = (st.t_last_us - st.t0_us) * 1e-6
        P(f"      span={span:,.2f} s = {span/3600:.4f} h")

    # ---------------------------------------------------- per-source
    P("\n## Whole-session per-source features "
      "(kappa = conjugate, nu = non-conjugate control)")
    src = {}
    for t in tags:
        st = sts[t]
        bym = defaultdict(list)
        for (mac, ch), c in st.cells.items():
            bym[mac].append(c)
        src[t] = {}
        for mac, cs in bym.items():
            tot = add_cells(cs)
            f = features(tot)
            if f is not None:
                f["raw_n"] = st.raw_n[mac]
                src[t][mac] = f
        P(f"\n  --- {t} ---")
        P(f"  {'mac':<19}{'role':>5}{'adm':>10}"
          f"{'|kappa|':>9}{'kfree':>9}"
          f"{'ALIGN':>8}{'algShft':>8}{'ratio':>7}"
          f"{'kapShft':>8}{'|nu|':>9}{'coh':>8}{'cohflr':>8}"
          f"{'axis%':>7}{'sAgr%':>7}{'DET':>5}")
        rows = sorted(src[t].items(), key=lambda kv: -kv[1]["n"])
        for mac, f in rows:
            if f["n"] < FLOOR_REPORT:
                continue
            P(f"  {mac:<19}{BEACONS.get(mac,''):>5}{f['n']:>10,}"
              f"{abs(f['kappa']):>9.5f}{f['kfree']:>9.5f}"
              f"{f['align']:>8.4f}{f['align_shift']:>8.4f}"
              f"{f['align_ratio']:>7.2f}{f['kappa_shift_max']:>8.5f}"
              f"{abs(f['nu']):>9.5f}"
              f"{f['coh']:>8.4f}{f['coh_floor']:>8.4f}"
              f"{100*f['axis_frac']:>7.1f}{100*f['s_agree']:>7.1f}"
              f"{'YES' if f['detected2'] else 'no':>5}")

    # ------------------------------------------- 2: does a term exist
    P("\n## TEST 0 (prereg 2) -- does a conjugate term exist above noise?")
    for t in tags:
        for mac, role in BEACONS.items():
            f = src[t].get(mac)
            if not f:
                P(f"  {t} {role} {mac}: NOT PRESENT")
                continue
            P(f"  {t} {role} {mac}: |kappa|={abs(f['kappa']):.5f} "
              f"({20*math.log10(max(abs(f['kappa']),1e-12)):.1f} dB)  "
              f"null_max={f['null_max']:.5f}  "
              f"ratio={abs(f['kappa'])/max(f['null_max'],1e-12):.2f}x  "
              f"coh={f['coh']:.4f} (floor {f['coh_floor']:.4f})  "
              f"halves |k1-k2|={abs(f['kh1']-f['kh2']):.5f} vs "
              f"|k1+k2|/2={abs(f['kh1']+f['kh2'])/2:.5f}  "
              f"-> {'DETECTED' if f['detected'] else 'AT NOISE FLOOR'}")
            P(f"      MIRROR-SPECIFICITY (Stage-2 primary): "
              f"align={f['align']:.4f}  wrong-pairing aligns="
              + ",".join(f"{a:.4f}" for a in f['al_sh'])
              + f"  ratio={f['align_ratio']:.2f}x  "
              f"-> {'CONJUGATE TERM PRESENT' if f['detected2'] else 'NOT MIRROR-SPECIFIC'}")
            P(f"      kappa={cfmt(f['kappa'])}  nu={cfmt(f['nu'])}  "
              f"kappa0={cfmt(f['kappa0'])}  nu0={cfmt(f['nu0'])}  "
              f"tau={cfmt(f['tau'])} (null {f['tau_null_max']:.5f})")
            P(f"      PATTERN-FREE: kfree={f['kfree']:.5f} "
              f"({20*math.log10(max(f['kfree'],1e-12)):.1f} dB)  "
              f"noise floor={f['kfree_floor']:.5f}  "
              f"SNR(alt-frame)={f['kfree_snr']:.2f}x  "
              f"wrong-pair floor={f['kfree_wrongpair']:.5f} "
              f"(SNR {f['kfree_wp_snr']:.2f}x)  "
              f"energy on one complex axis={100*f['axis_frac']:.1f}%  "
              f"sign agreement with the standard L-LTF s(k)="
              f"{100*f['s_agree']:.1f}% of 52")
            ck = f["ck_vec"]
            P("      c(k)/2p, k=-26..-1 : "
              + " ".join(f"{abs(z):.4f}" for z in ck[:26]))
            P("      c(k)/2p, k=  1..26 : "
              + " ".join(f"{abs(z):.4f}" for z in ck[26:]))

    # ------------------------------------------------ chunk-level cells
    chunks = {}
    for t in tags:
        st = sts[t]
        d = defaultdict(dict)
        for (mac, ch), c in st.cells.items():
            if c.n >= FLOOR_CHUNK:
                f = features(c)
                if f:
                    d[mac][ch] = f
        chunks[t] = d

    # ---------------------------------------------- TEST 1 separation
    P("\n## TEST 1 (prereg 3) -- do the three beacons separate? "
      "labels withheld from the estimator")
    sep_store = {}
    for t in tags:
        P(f"\n  --- {t} ---")
        for feat in ("kappa", "kfree", "tau"):
            pts, labs = [], []
            for mac in BEACONS:
                for ch, f in sorted(chunks[t].get(mac, {}).items()):
                    pts.append(f[feat])
                    labs.append(mac)
            if len(set(labs)) < 2:
                P(f"  {feat}: fewer than 2 devices clear the chunk floor")
                continue
            pts = np.asarray(pts)
            labs = np.asarray(labs)
            mus, sds = {}, {}
            for mac in BEACONS:
                v = pts[labs == mac]
                if v.size:
                    mus[mac] = v.mean()
                    sds[mac] = dispersion(v, v.mean())
            P(f"  [{feat}] per-device mean +- dispersion over "
              f"{len(pts)} chunk cells:")
            for mac in mus:
                rs = np.mean([f["rssi"] for ch, f in
                              sorted(chunks[t].get(mac, {}).items())])
                P(f"      {BEACONS[mac]} {mac}  mean={cfmt(mus[mac])}  "
                  f"|mean|={abs(mus[mac]):.5f}  arg={np.angle(mus[mac]):+.3f}"
                  f"  disp={sds[mac]:.5f}  n_chunks={(labs==mac).sum()}"
                  f"  mean RSSI={rs:.2f} dB")
            seps = []
            ms = list(mus)
            for i in range(len(ms)):
                for j in range(i + 1, len(ms)):
                    a, b = ms[i], ms[j]
                    s = abs(mus[a] - mus[b]) / math.sqrt(
                        (sds[a] ** 2 + sds[b] ** 2) / 2)
                    seps.append(((a, b), s))
                    P(f"      sep {BEACONS[a]}-{BEACONS[b]}: {s:.2f} sigma")
            if len(mus) >= 3 and len(pts) >= 3:
                lab = kmeans_complex(pts, 3)
                pur, ari = purity_ari(lab, labs)
                P(f"      blind k-means(3): purity={pur:.3f}  ARI={ari:.3f}")
            else:
                pur = float("nan")
            mn = min(s for _, s in seps) if seps else 0.0
            verdict = ("separates" if (mn >= 3.0 and pur >= 0.90)
                       else "partially separates"
                       if any(s >= 3.0 for _, s in seps)
                       else "does not separate")
            P(f"      VERDICT ({feat}): {verdict}   min sep {mn:.2f} sigma")
            sep_store[(t, feat)] = (mus, sds, seps)

    # ----------------------------------------------- TEST 2 stability
    P("\n## TEST 2 (prereg 4) -- stability across the 6.70 h session")
    P("   ratio = per-device residual RMS / between-device spread")
    P("   SFO slope baseline (docs/IDENTITY_STABILITY.md 13): 2.2x - 7.1x")
    for t in tags:
        P(f"\n  --- {t} ---")
        for feat, lbl in (("kappa", "kappa (IQ conjugate, s-projected)"),
                          ("kfree", "kfree (IQ conjugate, pattern-free)"),
                          ("tau", "tau (TX ripple)"),
                          ("slope_med", "deterministic slope [NOT the "
                                        "shipped SFO estimator]")):
            series = {}
            for mac in BEACONS:
                d = chunks[t].get(mac, {})
                if len(d) >= 2:
                    series[mac] = {ch: f[feat] for ch, f in d.items()}
            if len(series) < 2:
                P(f"  [{lbl}] fewer than 2 devices with >=2 chunks")
                continue
            common = set.intersection(*[set(v) for v in series.values()])
            common = sorted(common)
            devs = sorted(series)
            if len(common) < 2:
                P(f"  [{lbl}] fewer than 2 shared chunks")
                continue
            mu = {d: np.mean([series[d][c] for c in common]) for d in devs}
            cen = np.mean([mu[d] for d in devs])
            S_bd = math.sqrt(np.mean([abs(mu[d] - cen) ** 2 for d in devs]))

            def ratio_over(pairs):
                res, tot = [], []
                for a, b in pairs:
                    dl = {d: series[d][b] - series[d][a] for d in devs}
                    arr = np.array([dl[d] for d in devs])
                    cmn = (np.median(np.real(arr))
                           + 1j * np.median(np.imag(arr))
                           if np.iscomplexobj(arr) else np.median(arr))
                    for d in devs:
                        res.append(abs(dl[d] - cmn))
                        tot.append(abs(dl[d]))
                rr = math.sqrt(np.mean(np.square(res)))
                tt = math.sqrt(np.mean(np.square(tot)))
                energy = 1 - (rr ** 2) / (tt ** 2) if tt > 0 else float("nan")
                return rr, tt, energy

            allp = [(common[i], common[j])
                    for i in range(len(common))
                    for j in range(i + 1, len(common))]
            adjp = [(common[i], common[i + 1])
                    for i in range(len(common) - 1)]
            widep = [(common[0], common[-1])]
            P(f"  [{lbl}]  devices={len(devs)}  shared chunks={len(common)}"
              f"  between-device spread S_bd={S_bd:.6g}")
            for nm, pr in (("all pairs", allp), ("adjacent (10 min)", adjp),
                           ("widest (~6.5 h)", widep)):
                rr, tt, en = ratio_over(pr)
                P(f"      {nm:<20} total RMS={tt:.6g}  residual RMS={rr:.6g}"
                  f"  energy removed={100*en:.1f}%  "
                  f"**ratio = {rr/S_bd:.2f}x**")
            rr, tt, en = ratio_over(allp)
            r = rr / S_bd
            v = ("STABLE" if r < 1.0 else
                 "BETTER THAN THE SLOPE, still not usable" if r < 2.2 else
                 "NO BETTER THAN THE SLOPE")
            P(f"      VERDICT ({feat}): {v}  (ratio {r:.2f}x vs slope "
              f"2.2-7.1x)")

    # --------------------------------------------- TEST 3 TX vs RX
    P("\n## TEST 3 (prereg 5) -- transmitter vs receiver imbalance")
    if len(tags) == 2:
        ta, tb = tags
        for feat in ("kappa", "kfree", "tau"):
            both = [m for m in src[ta]
                    if m in src[tb]
                    and src[ta][m]["n"] >= FLOOR_POWER
                    and src[tb][m]["n"] >= FLOOR_POWER]
            both.sort(key=lambda m: -(src[ta][m]["n"] + src[tb][m]["n"]))
            if len(both) < 2:
                P(f"  [{feat}] fewer than 2 sources clear the power floor "
                  f"on both receivers -- decomposition not runnable")
                continue
            P(f"\n  [{feat}] sources heard by both with >= {FLOOR_POWER} "
              f"admissible frames: n={len(both)}")
            P(f"  {'mac':<19}{'role':>5}{'x('+ta+')':>20}{'x('+tb+')':>20}"
              f"{'D = a-b':>20}{'|D|':>9}")
            Ds = []
            for m in both:
                xa = src[ta][m][feat]
                xb = src[tb][m][feat]
                D = xa - xb
                Ds.append(D)
                P(f"  {m:<19}{BEACONS.get(m,''):>5}{cfmt(xa):>20}"
                  f"{cfmt(xb):>20}{cfmt(D):>20}{abs(D):>9.5f}")
            Ds = np.asarray(Ds)
            rho = np.median(np.real(Ds)) + 1j * np.median(np.imag(Ds))
            # block bootstrap of each source's D over its chunk series
            rng = np.random.default_rng(BOOT_SEED)
            bvars = []
            for m in both:
                sa = [f[feat] for _, f in sorted(chunks[ta].get(m, {}).items())]
                sb = [f[feat] for _, f in sorted(chunks[tb].get(m, {}).items())]
                if len(sa) < 3 or len(sb) < 3:
                    continue
                vs = []
                for arr in (sa, sb):
                    a = np.asarray(arr)
                    Lb = max(1, len(a) // 4)
                    bs = []
                    for _ in range(BOOT_B):
                        idx = []
                        while len(idx) < len(a):
                            s0 = rng.integers(0, len(a))
                            idx.extend(range(s0, min(s0 + Lb, len(a))))
                        bs.append(a[np.array(idx[:len(a)])].mean())
                    bs = np.asarray(bs)
                    vs.append(float(np.mean(np.abs(bs - bs.mean()) ** 2)))
                bvars.append(sum(vs))
            var_across = float(np.mean(np.abs(Ds - Ds.mean()) ** 2))
            med_boot = float(np.median(bvars)) if bvars else float("nan")
            R_disp = var_across / med_boot if med_boot and med_boot > 0 \
                else float("inf")
            # between-transmitter spread from the beacon means at tag a
            bm = [src[ta][m][feat] for m in BEACONS if m in src[ta]]
            S_bd = (math.sqrt(np.mean(np.abs(np.asarray(bm)
                                             - np.mean(bm)) ** 2))
                    if len(bm) >= 2 else float("nan"))
            frac = abs(rho) / S_bd if S_bd and S_bd == S_bd else float("nan")
            P(f"\n      receiver difference rho({ta})-rho({tb}) "
              f"= median D = {cfmt(rho)}   |rho_diff| = {abs(rho):.5f}")
            P(f"      Var across sources of D = {var_across:.6e}")
            P(f"      median block-bootstrap Var(D) = {med_boot:.6e} "
              f"(a LOWER bound; these series are not white)")
            P(f"      R_disp = {R_disp:.1f}   (D is constant across sources "
              f"iff R_disp < 2)")
            P(f"      between-transmitter spread S_bd ({ta}, 3 beacons) "
              f"= {S_bd:.5f}")
            P(f"      **frac_rx = |rho_diff| / S_bd = {frac:.2f}**")
            v = ("RECEIVER-DOMINATED -- feature unusable as-is"
                 if frac >= 1.0 else
                 "INTERMEDIATE" if frac >= 0.5 else
                 ("TRANSMITTER-DOMINATED" if R_disp < 2 else
                  "frac_rx small but D is not constant across sources "
                  "(R_disp >= 2): additive model not supported"))
            P(f"      VERDICT ({feat}): {v}")
            P(f"      NOTE: with two receivers only the receiver DIFFERENCE "
              f"is identifiable. A component common to both receivers is "
              f"absorbed into the transmitter term, so this is a LOWER "
              f"bound on the receiver share (prereg 5.2).")
    else:
        P("  needs exactly two receiver tags")

    # ------------------------------------------------ TEST 4 ambient
    P("\n## TEST 4 (prereg 6) -- ambient sources, reported separately")
    P(f"   reporting floor {FLOOR_REPORT} admissible frames; "
      f"power floor {FLOOR_POWER}")
    for t in tags:
        P(f"\n  --- {t} ---")
        amb = [(m, f) for m, f in src[t].items()
               if m not in BEACONS and f["n"] >= FLOOR_REPORT]
        amb.sort(key=lambda kv: -kv[1]["n"])
        if not amb:
            P("      no ambient source clears the reporting floor")
            continue
        P(f"  {'mac':<19}{'adm':>9}{'raw':>9}{'|kappa|':>10}"
          f"{'align':>8}{'algShft':>8}{'ratio':>7}{'|nu|':>9}"
          f"{'coh':>8}{'mirr':>6}  status")
        n_power = 0
        for m, f in amb:
            status = ("above power floor" if f["n"] >= FLOOR_POWER
                      else "below the estimator's power floor")
            if f["n"] >= FLOOR_POWER:
                n_power += 1
            P(f"  {m:<19}{f['n']:>9,}{f['raw_n']:>9,}"
              f"{abs(f['kappa']):>10.5f}{f['align']:>8.4f}"
              f"{f['align_shift']:>8.4f}{f['align_ratio']:>7.2f}"
              f"{abs(f['nu']):>9.5f}{f['coh']:>8.4f}"
              f"{'YES' if f['detected2'] else 'no':>6}  {status}")
        P(f"      ambient sources clearing the power floor "
          f"({FLOOR_POWER} admissible frames): {n_power}")
        if n_power == 0:
            P("      -> NO AMBIENT SOURCE QUALIFIED. No beacon number is "
              "substituted and the floor is not lowered (prereg 6.2).")

    txt = "\n".join(out)
    print(txt)
    with open(os.path.join(CACHE, f"report_{svar}.txt"), "w") as f:
        f.write(txt + "\n")


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("selftest")
    s.add_argument("--nframes", type=int, default=20000)
    s.set_defaults(func=lambda a: run_selftest(a))

    s = sub.add_parser("scan")
    s.add_argument("path")
    s.add_argument("--tag", required=True)
    s.add_argument("--convention", default="divided",
                   choices=("divided", "raw"))
    s.add_argument("--svar", default="strue", choices=("strue", "s1"))
    s.add_argument("--max-rows", type=int, default=0)
    s.add_argument("--seconds", type=float, default=0,
                   help="checkpoint and exit after this long (host caps "
                        "shell calls); rerun with --resume to continue")
    s.add_argument("--resume", action="store_true")
    s.set_defaults(func=run_scan)

    s = sub.add_parser("report")
    s.add_argument("--tags", required=True)
    s.add_argument("--svar", default="strue")
    s.add_argument("--convention", default="divided")
    s.set_defaults(func=run_report)

    a = ap.parse_args()
    if a.cmd == "selftest":
        a.pairs = [
            ("d0wd", "data/raw/d0wd_20260823_014740.csv",
             "a4:f0:0f:77:91:20"),
            ("s3", "data/raw/s3_20260823_014740.csv",
             "a4:f0:0f:77:91:20"),
        ]
    a.func(a)


if __name__ == "__main__":
    main()
