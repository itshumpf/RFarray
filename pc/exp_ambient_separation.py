#!/usr/bin/env python3
"""Do heterogeneous ambient devices separate by SFO better than three
same-batch ESP32 beacons do?

The three beacons are probably one reel, and B1/B3 are a characterised clock
twin pair (`docs/LOT_HYPOTHESIS.md`), so every separation figure this repo
has measured may be a worst case. The ambient traffic in the 2026-08-22
overnight capture is real heterogeneous hardware and is the natural control.
No ambient source has ever been successfully phase-estimated here — the
`split(",", 128)` defect of `docs/POSITIVE_CONTROL_0822.md` §1.2 silently
discarded all of it, and the one pass that fixed the parse then lost 16 of
17 sources to `inlier_ratio >= 0.6`.

This script is SFO-only. CFO is dead on this capture
(`docs/SEPARATION_SCALING.md` §3.3: 0.01-0.21 sigma, all medians within
0.06 Hz of zero), so every separation below is one-dimensional and the
relevant chi-square thresholds are chi2(1) = 3.841 / 6.635, NOT the
5.991 / 9.210 that `pc/rff/discriminator.py:23-24` uses for 2 dof.

Phase work is `pc/rff/dsp.py`'s `FrameEstimator` / `WindowAggregator`.
`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` are
NOT used (`docs/CODE_INVENTORY.md` §4.2 C1/C2/C3: all three have the
DC/guard-band index wrong).

Read-only on `data/raw/`: both CSVs are opened "rb" and never written.
No serial port is opened. Nothing is staged, committed or pushed.

Commands
--------
  lltf   PATH                       structural check: is a 128-length record
                                    really a valid LLTF for dsp.py's mask?
  modes  PATH                       global node_id / channel modes
  scan   PATH --tag T --part p --nparts N --node-mode M --chan-mode C
  merge  --tag T --nparts N [--expect-rows R]
  census --tags a,b
  sweep  --tags a,b
  compare --tags a,b --min-inlier X
"""
import argparse
import os
import pickle
import sys
import warnings
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rff.dsp import (FrameEstimator, WindowAggregator, csi_to_complex,   # noqa: E402
                     K_USABLE, _K_OF_IDX, _USABLE_IDX, N_CPLX)
from rff.discriminator import Discriminator                              # noqa: E402

warnings.filterwarnings("ignore", category=DeprecationWarning)

CACHE = os.environ.get("AMBSEP_CACHE", "/tmp/ambsep_cache")

# Empty-room window, seconds of pc_time_us since each file's own first
# decodable row. docs/SEPARATION_SCALING.md uses exactly this window;
# docs/POSITIVE_CONTROL_0822.md §0/§2.1 establishes the operator re-entered
# at t ~ 23,067 s and the head is power-on settle.
T_LO, T_HI = 300.0, 23000.0
BIN_S = 300.0
N_BINS = int(np.ceil((T_HI - T_LO) / BIN_S))       # 76

B1 = "a4:f0:0f:77:91:20"      # reference beacon
B2 = "28:05:a5:2f:fa:48"
B3 = "f4:2d:c9:70:72:30"      # the clock twin (docs/LOT_HYPOTHESIS.md)
BEACONS = [B1, B2, B3]
BNAME = {B1: "B1", B2: "B2", B3: "B3"}

# Field-plausibility bounds, copied from pc/exp_overnight_0822.py:90-97 so
# the artefact screen here is the same screen docs/OVERNIGHT_2026-08-22.md
# §5.2 ran. Not re-derived; quoted.
RSSI_LO, RSSI_HI = -100, -10
NF_LO, NF_HI = -110, -70
VALID_LEN = (128, 256, 384)                    # pc/rff/protocol.py:31

# yardsticks, each with its source
BETWEEN_UNIT_SD = 0.00237     # pc/exp_thermal_evidence.py:129
TWIN_DSFO = 0.00080           # pc/exp_lot_hypothesis.py:85-86

SHIPPED_MIN_INLIER = 0.6
SHIPPED_MAX_RESID = 0.8
INLIERS = [0.60, 0.50, 0.40, 0.30, 0.20]

CHI2_1_95 = 3.841
CHI2_1_99 = 6.635
VAR_FLOOR_SFO = 1e-8          # pc/rff/discriminator.py:27


def cpath(tag, name):
    return os.path.join(CACHE, f"{tag}_{name}")


def hexmac(m):
    return m.replace(":", "")


# ----------------------------------------------------------------- parsing

def parse_row(line):
    """Split one data line. Returns dict or None with a reason.

    Layout: pc_time_us,label,seq,mac,rssi,noise_floor,channel,
            esp_timestamp_us,len,csi_data,node_id,env_id,dropped
    csi_data is quoted and full of commas, so the first 9 fields come off the
    front and the last 3 off the back.

    The CSI field is read with np.fromstring(sep=",") — the same read as
    pc/rff_offline.py:203 — NOT cs.split(",", 128), which returns at most
    129 items and therefore silently drops every exactly-128-value row
    (docs/POSITIVE_CONTROL_0822.md §1.2).
    """
    p9 = line.split(",", 9)
    if len(p9) != 10:
        return None, "bad_line"
    rest = p9[9].rsplit(",", 3)
    if len(rest) != 4:
        return None, "bad_line"
    try:
        d = {
            "pc_us": int(p9[0]),
            "mac": p9[3].lower(),
            "rssi": int(p9[4]),
            "nf": int(p9[5]),
            "chan": int(p9[6]),
            "esp_us": int(p9[7]),
            "csi_len": int(p9[8]),
            "node_id": int(rest[1]),
            "env_id": int(rest[2]),
        }
    except ValueError:
        return None, "bad_field"
    cs = rest[0]
    if cs[:1] == '"':
        cs = cs[1:-1] if cs[-1:] == '"' else cs[1:]
    d["cs"] = cs
    return d, None


# -------------------------------------------------------------------- lltf

def cmd_lltf(args):
    """Is a 128-value record a valid LLTF under dsp.py's mask and ordering?

    csi_to_complex takes the first 64 complex samples, so a 128-byte record
    (LLTF only) and a 256-byte record (LLTF + HT-LTF) *should* both yield a
    valid LLTF vector. If the null pattern differs — if the DC bin and the
    |k| > 26 guards are not zero on 128-length rows — then dsp.py's mask is
    reading signal as guard or guard as signal on ambient traffic, and the
    beacon-vs-ambient comparison is invalid rather than merely weak.
    """
    print(f"# LLTF STRUCTURE CHECK  {args.path}")
    print(f"# dsp.py mask: N_CPLX={N_CPLX}, usable |k| in 1..26, "
          f"{K_USABLE.size} bins, k from {K_USABLE[0]} to {K_USABLE[-1]}")
    want = args.per_len
    got = defaultdict(list)
    macs = defaultdict(lambda: defaultdict(int))
    n = 0
    with open(args.path, "rb") as fb:
        fb.readline()
        for raw in fb:
            n += 1
            if n > args.max_rows:
                break
            d, _ = parse_row(raw.decode("ascii", "replace").rstrip("\n"))
            if d is None:
                continue
            vals = np.fromstring(d["cs"], dtype=np.float64, sep=",")
            L = vals.size
            macs[L][d["mac"]] += 1
            if len(got[L]) < want:
                got[L].append((d["mac"], vals))
    print(f"# scanned {n - 1} rows from the head of the file\n")

    for L in sorted(got):
        rows = got[L]
        print(f"## parsed vector length {L}   "
              f"({len(macs[L])} distinct MAC(s) at this length in the sample)")
        for m, c in sorted(macs[L].items(), key=lambda kv: -kv[1])[:6]:
            print(f"     {m}  {c}")
        # stack the sampled rows and look at the null structure
        arr = np.array([v[:N_CPLX * 2] for _, v in rows
                        if v.size >= N_CPLX * 2])
        if arr.size == 0:
            print("     TOO SHORT for a full LLTF: csi_to_complex returns "
                  "None for every sampled row\n")
            continue
        z = arr[:, 1::2] + 1j * arr[:, 0::2]          # csi_to_complex, vectorised
        mag = np.abs(z)
        zero_frac = (mag == 0).mean(axis=0)           # per buffer index
        # regroup by physical subcarrier k
        order = np.argsort(_K_OF_IDX)
        k_sorted = _K_OF_IDX[order]
        zf = zero_frac[order]
        guard = np.abs(k_sorted) > 26
        dc = k_sorted == 0
        sig = (~guard) & (~dc)
        print(f"     n sampled rows with >= 128 values: {arr.shape[0]}")
        print(f"     fraction of samples that are exactly zero:")
        print(f"       guard bins (|k| > 26, {guard.sum()} bins): "
              f"{zf[guard].mean():.4f}   (want 1.0000)")
        print(f"       DC bin (k = 0): {zf[dc].mean():.4f}   (want 1.0000)")
        print(f"       signal bins (1 <= |k| <= 26, {sig.sum()} bins): "
              f"{zf[sig].mean():.4f}   (want ~0.0000)")
        nz = [f"{int(k):+d}" for k, f in zip(k_sorted, zf)
              if (guard[list(k_sorted).index(k)] or k == 0) and f < 1.0]
        if nz:
            print(f"       !! non-zero guard/DC bins: {' '.join(nz)}")
        # first sampled row verbatim, in physical-k order, so the claim is
        # inspectable rather than asserted
        m0, v0 = rows[0]
        z0 = csi_to_complex(v0)
        print(f"     first sampled row, mac {m0}:")
        if z0 is None:
            print("       csi_to_complex -> None")
        else:
            full = np.abs(z0)[order]
            print("       |CSI| by physical k (guard|dc marked *):")
            s = []
            for k, a in zip(k_sorted, full):
                mark = "*" if (abs(k) > 26 or k == 0) else " "
                s.append(f"{int(k):+3d}{mark}{a:6.1f}")
            for i in range(0, len(s), 8):
                print("       " + " ".join(s[i:i + 8]))
            est = FrameEstimator()
            e = est.feed(v0, None)
            print(f"       FrameEstimator: {e}")
        print()
    return 0


# ------------------------------------------------------------------- modes

def cmd_modes(args):
    node = defaultdict(int)
    chan = defaultdict(int)
    n = 0
    with open(args.path, "rb") as fb:
        fb.readline()
        for raw in fb:
            n += 1
            if n > args.max_rows:
                break
            d, _ = parse_row(raw.decode("ascii", "replace").rstrip("\n"))
            if d is None:
                continue
            node[d["node_id"]] += 1
            chan[d["chan"]] += 1
    print(f"{args.path}: {n - 1} rows sampled")
    print("  node_id:", dict(sorted(node.items(), key=lambda kv: -kv[1])[:6]))
    print("  channel:", dict(sorted(chan.items(), key=lambda kv: -kv[1])[:6]))
    return 0


# -------------------------------------------------------------------- scan

class Growable:
    def __init__(self, dtype, n=1 << 18):
        self.a = np.empty(n, dtype=dtype)
        self.n = 0

    def push(self, v):
        if self.n == self.a.size:
            self.a = np.resize(self.a, self.a.size * 2)
        self.a[self.n] = v
        self.n += 1

    def out(self):
        return self.a[:self.n].copy()


def line_range(path, part, nparts):
    """Byte range [lo, hi) snapped to line starts; parts tile exactly."""
    size = os.path.getsize(path)
    lo = size * part // nparts
    hi = size * (part + 1) // nparts
    with open(path, "rb") as f:
        if part == 0:
            f.readline()
            lo = f.tell()
        else:
            f.seek(lo)
            f.readline()
            lo = f.tell()
    return lo, hi


def new_mac_rec():
    return {"n": 0, "flag": 0, "in_win": 0, "flag_win": 0,
            "len": defaultdict(int), "vlen": defaultdict(int),
            "bins": set(), "rssi_sum": 0.0, "rssi_sq": 0.0,
            "rssi_min": 127, "rssi_max": -127,
            "t_first": None, "t_last": None,
            "nf_sum": 0.0}


def cmd_scan(args):
    os.makedirs(CACHE, exist_ok=True)
    tag, part = args.tag, args.part
    lo, hi = line_range(args.path, part, args.nparts)

    if part == 0:
        st = {"rows": 0, "bad_line": 0, "bad_field": 0,
              "len_rows": defaultdict(int), "vals_rows": defaultdict(int),
              "naive_dropped": 0, "node_ids": defaultdict(int),
              "chans": defaultdict(int), "origin": None,
              "mac": defaultdict(new_mac_rec), "amb_macs": [],
              "byte_lo": lo}
        est = {}
    else:
        with open(cpath(tag, f"state{part - 1}.pkl"), "rb") as f:
            st = pickle.load(f)
        with open(cpath(tag, f"est{part - 1}.pkl"), "rb") as f:
            est = pickle.load(f)
        assert st["byte_hi"] == lo, (
            f"seam mismatch: previous part ended at {st['byte_hi']}, "
            f"this part starts at {lo}")

    bidx = {m: i for i, m in enumerate(BEACONS)}
    aidx = {m: i for i, m in enumerate(st["amb_macs"])}

    b_t = Growable(np.float32)
    b_esp = Growable(np.int64)
    b_mac = Growable(np.int8)
    b_slope = Growable(np.float64)
    b_inl = Growable(np.float32)
    b_res = Growable(np.float32)
    b_rssi = Growable(np.int16)

    a_t, a_mac, a_slope = [], [], []
    a_inl, a_res, a_rssi, a_len, a_fit = [], [], [], [], []

    nan = np.nan
    origin = st["origin"]
    node_mode, chan_mode = args.node_mode, args.chan_mode

    with open(args.path, "rb") as fb:
        fb.seek(lo)
        for raw in fb:
            st["rows"] += 1
            d, why = parse_row(raw.decode("ascii", "replace").rstrip("\n"))
            if d is None:
                st[why] += 1
                if fb.tell() >= hi:
                    break
                continue

            cs = d["cs"]
            vals = np.fromstring(cs, dtype=np.float64, sep=",")
            mac = d["mac"]

            st["len_rows"][d["csi_len"]] += 1
            st["vals_rows"][vals.size] += 1
            st["node_ids"][d["node_id"]] += 1
            st["chans"][d["chan"]] += 1
            # exactly what pc/exp_overnight_0822.py:303 would have discarded
            if len(cs.split(",", 128)) < 129:
                st["naive_dropped"] += 1

            if origin is None:
                origin = d["pc_us"]
                st["origin"] = origin
            t = (d["pc_us"] - origin) * 1e-6

            flagged = (
                d["node_id"] != node_mode or d["env_id"] != 0
                or d["chan"] != chan_mode
                or d["csi_len"] not in VALID_LEN
                or d["nf"] < NF_LO or d["nf"] > NF_HI
                or d["rssi"] < RSSI_LO or d["rssi"] > RSSI_HI)

            r = st["mac"][mac]
            r["n"] += 1
            if flagged:
                r["flag"] += 1

            in_win = T_LO <= t < T_HI
            if not in_win:
                if fb.tell() >= hi:
                    break
                continue

            r["in_win"] += 1
            if flagged:
                r["flag_win"] += 1
            r["len"][d["csi_len"]] += 1
            r["vlen"][vals.size] += 1
            r["bins"].add(int((t - T_LO) // BIN_S))
            r["rssi_sum"] += d["rssi"]
            r["rssi_sq"] += d["rssi"] * d["rssi"]
            r["rssi_min"] = min(r["rssi_min"], d["rssi"])
            r["rssi_max"] = max(r["rssi_max"], d["rssi"])
            r["nf_sum"] += d["nf"]
            if r["t_first"] is None:
                r["t_first"] = t
            r["t_last"] = t

            e = est.setdefault(mac, FrameEstimator()).feed(vals, d["esp_us"])

            if mac in bidx:
                b_t.push(t)
                b_esp.push(d["esp_us"])
                b_mac.push(bidx[mac])
                b_rssi.push(max(-32768, min(32767, d["rssi"])))
                if e is None:
                    b_slope.push(nan); b_inl.push(nan); b_res.push(nan)
                else:
                    b_slope.push(e["slope"])
                    b_inl.push(e["inlier_ratio"])
                    b_res.push(e["resid_std"])
            else:
                if mac not in aidx:
                    aidx[mac] = len(st["amb_macs"])
                    st["amb_macs"].append(mac)
                a_t.append(t)
                a_mac.append(aidx[mac])
                a_rssi.append(d["rssi"])
                a_len.append(d["csi_len"])
                if e is None:
                    a_fit.append(0)
                    a_slope.append(nan); a_inl.append(nan); a_res.append(nan)
                else:
                    a_fit.append(1)
                    a_slope.append(e["slope"])
                    a_inl.append(e["inlier_ratio"])
                    a_res.append(e["resid_std"])

            if fb.tell() >= hi:
                break
        st["byte_hi"] = fb.tell()

    np.savez(cpath(tag, f"part{part}.npz"),
             b_t=b_t.out(), b_esp=b_esp.out(), b_mac=b_mac.out(),
             b_slope=b_slope.out(), b_inl=b_inl.out(), b_res=b_res.out(),
             b_rssi=b_rssi.out(),
             a_t=np.array(a_t, dtype=np.float32),
             a_mac=np.array(a_mac, dtype=np.int32),
             a_slope=np.array(a_slope, dtype=np.float64),
             a_inl=np.array(a_inl, dtype=np.float32),
             a_res=np.array(a_res, dtype=np.float32),
             a_rssi=np.array(a_rssi, dtype=np.int16),
             a_len=np.array(a_len, dtype=np.int32),
             a_fit=np.array(a_fit, dtype=np.int8))
    with open(cpath(tag, f"state{part}.pkl"), "wb") as f:
        pickle.dump(st, f)
    with open(cpath(tag, f"est{part}.pkl"), "wb") as f:
        pickle.dump(est, f)
    print(f"{tag} part {part}/{args.nparts}: bytes [{lo},{st['byte_hi']}) "
          f"rows {st['rows']} beacon-frames {b_t.n} ambient-frames {len(a_t)}")
    return 0


def cmd_merge(args):
    tag = args.tag
    with open(cpath(tag, f"state{args.nparts - 1}.pkl"), "rb") as f:
        st = pickle.load(f)
    parts = [np.load(cpath(tag, f"part{p}.npz")) for p in range(args.nparts)]
    out = {}
    for k in parts[0].files:
        out[k] = np.concatenate([p[k] for p in parts])
    # seams: pc_time must be monotone across the whole concatenation
    rev = int((np.diff(out["b_t"]) < 0).sum())
    np.savez(cpath(tag, "merged.npz"), **out)
    with open(cpath(tag, "state.pkl"), "wb") as f:
        pickle.dump(st, f)
    print(f"{tag}: rows {st['rows']}  beacon-frames {out['b_t'].size}  "
          f"ambient-frames {out['a_t'].size}  t-reversals {rev}")
    if args.expect_rows and st["rows"] != args.expect_rows:
        print(f"  !! row count {st['rows']} != expected {args.expect_rows}")
    else:
        print("  row count matches wc -l minus header")
    return 0


def load(tag):
    fr = np.load(cpath(tag, "merged.npz"))
    with open(cpath(tag, "state.pkl"), "rb") as f:
        st = pickle.load(f)
    return fr, st


# ------------------------------------------------------------------ census

def classify(st, tag):
    """Artefact screen, docs/OVERNIGHT_2026-08-22.md §5.2, in order.

    X decode artefact / R sustained / P intermittent-corroborated /
    S unresolved. The cross-receiver limb of P is applied by the caller,
    which has both tags; here P is provisional on this node alone.
    """
    macs = st["mac"]
    counts = {m: r["in_win"] for m, r in macs.items()}
    cls = {}
    for m, r in macs.items():
        n = r["in_win"]
        if n == 0:
            cls[m] = "-"
            continue
        dom_len = max(r["len"].items(), key=lambda kv: kv[1])[0] if r["len"] else 0
        near = False
        if n <= 4:
            for m2, n2 in counts.items():
                if m2 == m or n2 < 20 * max(n, 1):
                    continue
                a = m.split(":")
                b = m2.split(":")
                if sum(x != y for x, y in zip(a, b)) <= 2:
                    near = True
                    break
        if r["flag_win"] >= 0.5 * n or dom_len not in VALID_LEN or near:
            cls[m] = "X"
        elif n >= 1000 and r["flag_win"] < 0.01 * n and len(r["bins"]) >= 20:
            cls[m] = "R"
        elif n >= 5 and r["flag_win"] < 0.01 * n:
            cls[m] = "P?"          # needs the cross-receiver check
        else:
            cls[m] = "S"
    return cls


def cmd_census(args):
    tags = args.tags.split(",")
    S, C = {}, {}
    for t in tags:
        _, st = load(t)
        S[t] = st
        C[t] = classify(st, t)

    print("=" * 78)
    print("TABLE 1 - PARSE INTEGRITY.  Does the parser see 128-length rows?")
    print("=" * 78)
    print(f"{'':38s}" + "".join(f"{t:>18s}" for t in tags))
    rows = [("data rows", lambda s: s["rows"]),
            ("undecodable by line", lambda s: s["bad_line"]),
            ("undecodable by field", lambda s: s["bad_field"]),
            ("rows split(',',128) would drop",
             lambda s: s["naive_dropped"])]
    for name, f in rows:
        print(f"{name:38s}" + "".join(f"{f(S[t]):>18,d}" for t in tags))
    lens = sorted({L for t in tags for L in S[t]["len_rows"]}
                  | {L for t in tags for L in S[t]["vals_rows"]})
    for L in lens:
        print(f"{'csi_len column == ' + str(L):38s}"
              + "".join(f"{S[t]['len_rows'].get(L, 0):>18,d}" for t in tags))
    for L in lens:
        print(f"{'parsed vector length == ' + str(L):38s}"
              + "".join(f"{S[t]['vals_rows'].get(L, 0):>18,d}" for t in tags))
    for t in tags:
        same = all(S[t]["len_rows"].get(L, 0) == S[t]["vals_rows"].get(L, 0)
                   for L in lens)
        print(f"  {t}: parsed-length histogram == csi_len histogram: {same}")
        print(f"  {t}: node_id "
              f"{dict(sorted(S[t]['node_ids'].items(), key=lambda kv: -kv[1]))}")
        print(f"  {t}: channel "
              f"{dict(sorted(S[t]['chans'].items(), key=lambda kv: -kv[1])[:4])}")

    print()
    print("=" * 78)
    print(f"TABLE 2 - MAC CENSUS over the window "
          f"[{T_LO:.0f}, {T_HI:.0f}) s  ({N_BINS} bins of {BIN_S:.0f} s)")
    print("=" * 78)

    # cross-receiver corroboration: promote P? -> P when the MAC is seen on
    # both nodes inside at least one shared bin
    fin = {t: dict(C[t]) for t in tags}
    if len(tags) == 2:
        ta, tb = tags
        for m in set(fin[ta]) & set(fin[tb]):
            shared = S[ta]["mac"][m]["bins"] & S[tb]["mac"][m]["bins"]
            for t in tags:
                if fin[t].get(m) == "P?":
                    fin[t][m] = "P" if shared else "S"
    for t in tags:
        for m, c in fin[t].items():
            if c == "P?":
                fin[t][m] = "S"

    allm = sorted({m for t in tags for m in S[t]["mac"]
                   if S[t]["mac"][m]["in_win"] > 0},
                  key=lambda m: -max(S[t]["mac"][m]["in_win"]
                                     for t in tags if m in S[t]["mac"]))
    hdr = f"{'mac':19s}{'kind':5s}"
    for t in tags:
        hdr += f"|{t + ' cls':>8s}{'n':>10s}{'len':>16s}{'rssi mean/min/max':>22s}{'bins':>6s}{'duty':>7s}"
    print(hdr)
    keep = []
    for m in allm:
        cls_any = {fin[t].get(m, "-") for t in tags}
        kind = "LAA" if (int(m.split(":")[0], 16) & 2) else "OUI"
        if m in BNAME:
            kind = BNAME[m]
        line = f"{m:19s}{kind:5s}"
        for t in tags:
            r = S[t]["mac"].get(m)
            if r is None or r["in_win"] == 0:
                line += f"|{'-':>8s}{'-':>10s}{'-':>16s}{'-':>22s}{'-':>6s}{'-':>7s}"
                continue
            n = r["in_win"]
            lh = ",".join(f"{L}:{c}" for L, c in
                          sorted(r["len"].items(), key=lambda kv: -kv[1])[:2])
            mu = r["rssi_sum"] / n
            duty = len(r["bins"]) / N_BINS
            rs = f"{mu:.1f}/{r['rssi_min']:.0f}/{r['rssi_max']:.0f}"
            line += (f"|{fin[t].get(m, '-'):>8s}{n:>10,d}{lh:>16s}"
                     f"{rs:>22s}{len(r['bins']):>6d}{duty:>7.2f}")
        if cls_any & {"R", "P"}:
            print(line)
            keep.append(m)
    nX = {t: sum(1 for c in fin[t].values() if c == "X") for t in tags}
    nS = {t: sum(1 for c in fin[t].values() if c == "S") for t in tags}
    nR = {t: sum(1 for c in fin[t].values() if c == "R") for t in tags}
    nP = {t: sum(1 for c in fin[t].values() if c == "P") for t in tags}
    print()
    for t in tags:
        tot = sum(1 for m, r in S[t]["mac"].items() if r["in_win"] > 0)
        print(f"  {t}: R {nR[t]}  P {nP[t]}  S {nS[t]}  X {nX[t]}   "
              f"total MACs with traffic in the window {tot}")
    print(f"  MACs printed above (R or P on at least one node): {len(keep)}")

    print()
    print("=" * 78)
    print("TABLE 3 - CAN IT SUPPORT AN SFO ESTIMATE?  fitted / gated frames")
    print("=" * 78)
    print(f"{'mac':19s}" + "".join(
        f"| {t:<6s}{'rows':>10s}{'fit':>10s}{'fit%':>7s}"
        f"{'acc@.6':>10s}{'acc@.3':>10s}{'medinl':>8s}" for t in tags))
    FR = {t: load(t) for t in tags}
    for m in keep:
        line = f"{m:19s}"
        for t in tags:
            line += "|" + amb_line(FR[t][0], FR[t][1], m, t)
        print(line)
    print("\n  'fit' = frames for which FrameEstimator returned a RANSAC fit.")
    print("  'acc@g' = fit AND inlier_ratio >= g AND resid_std <= "
          f"{SHIPPED_MAX_RESID}.")
    print("  A source with fit == rows but acc@.6 == 0 is a GATE exclusion,")
    print("  not sparsity and not a parse failure.")
    return 0


def src_frames(fr, st, mac):
    """(slope, inlier, resid, rssi, t) for one source, fitted frames only."""
    if mac in BNAME:
        i = BEACONS.index(mac)
        sel = (fr["b_mac"] == i) & np.isfinite(fr["b_slope"])
        return (fr["b_slope"][sel], fr["b_inl"][sel], fr["b_res"][sel],
                fr["b_rssi"][sel], fr["b_t"][sel])
    if mac not in st["amb_macs"]:
        return (np.array([]),) * 5
    i = st["amb_macs"].index(mac)
    sel = (fr["a_mac"] == i) & (fr["a_fit"] == 1)
    return (fr["a_slope"][sel], fr["a_inl"][sel], fr["a_res"][sel],
            fr["a_rssi"][sel], fr["a_t"][sel])


def amb_line(fr, st, mac, tag):
    r = st["mac"].get(mac)
    n = r["in_win"] if r else 0
    sl, inl, res, _, _ = src_frames(fr, st, mac)
    nf = sl.size
    a6 = int(((inl >= 0.6) & (res <= SHIPPED_MAX_RESID)).sum())
    a3 = int(((inl >= 0.3) & (res <= SHIPPED_MAX_RESID)).sum())
    mi = float(np.median(inl)) if nf else float("nan")
    return (f"{'':7s}{n:>10,d}{nf:>10,d}"
            f"{(100.0 * nf / n if n else 0):>7.1f}{a6:>10,d}{a3:>10,d}"
            f"{mi:>8.3f}")


# ------------------------------------------------------------------- sweep

def cmd_sweep(args):
    tags = args.tags.split(",")
    for tag in tags:
        fr, st = load(tag)
        C = classify(st, tag)
        srcs = BEACONS + [m for m in st["amb_macs"]
                          if C.get(m) in ("R", "P?", "P")]
        print("=" * 78)
        print(f"TABLE 4[{tag}] - min_inlier SWEEP "
              f"(max_resid fixed at the shipped {SHIPPED_MAX_RESID})")
        print("=" * 78)
        print(f"{'mac':19s}{'kind':5s}{'fit':>7s}" + "".join(
            f"{'n@' + f'{g:.1f}':>8s}{'%':>6s}" for g in INLIERS))
        for m in srcs:
            sl, inl, res, _, _ = src_frames(fr, st, m)
            if sl.size == 0:
                continue
            kind = BNAME.get(m, "LAA" if (int(m.split(":")[0], 16) & 2)
                             else "OUI")
            line = f"{m:19s}{kind:5s}{sl.size:>7,d}"
            for g in INLIERS:
                k = int(((inl >= g) & (res <= SHIPPED_MAX_RESID)).sum())
                line += f"{k:>8,d}{100.0 * k / sl.size:>6.1f}"
            print(line)

        print()
        print(f"TABLE 5[{tag}] - THE COST OF LOOSENING: does the SFO estimate")
        print("  move as the gate drops?  median SFO (rad/sc) and IQR per gate.")
        print(f"{'mac':19s}" + "".join(f"{'@' + f'{g:.1f}':>11s}{'iqr':>9s}"
                                       for g in INLIERS))
        for m in srcs:
            sl, inl, res, _, _ = src_frames(fr, st, m)
            if sl.size == 0:
                continue
            line = f"{m:19s}"
            for g in INLIERS:
                k = (inl >= g) & (res <= SHIPPED_MAX_RESID)
                if k.sum() < 3:
                    line += f"{'-':>11s}{'-':>9s}"
                else:
                    v = sl[k]
                    line += (f"{np.median(v):>+11.5f}"
                             f"{np.subtract(*np.percentile(v, [75, 25])):>9.5f}")
            print(line)

        print()
        print(f"TABLE 6[{tag}] - THE BIAS THE GATE IS THERE TO STOP, measured")
        print("  on the beacons, where every inlier stratum has many frames.")
        print("  Reference = frames with inlier >= 0.9.  A stratum's offset is")
        print("  how far admitting only that stratum would move the estimate.")
        strata = [(0.2, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, 0.6),
                  (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
        print(f"{'beacon':10s}{'ref':>8s}{'ref med':>11s}" + "".join(
            f"{f'[{a:.1f},{b:.1f})':>16s}" for a, b in strata))
        for m in BEACONS:
            sl, inl, res, _, _ = src_frames(fr, st, m)
            # the top populated stratum is the reference; on d0wd B3 nothing
            # reaches 0.9, so say which reference was used rather than nan
            rlo = None
            for cand in (0.9, 0.8, 0.7, 0.6):
                if (inl >= cand).sum() >= 1000:
                    rlo = cand
                    break
            if rlo is None:
                print(f"{BNAME[m]:10s}  no stratum with >= 1000 frames")
                continue
            ref = float(np.median(sl[inl >= rlo]))
            line = f"{BNAME[m]:10s}{'>=' + f'{rlo:.1f}':>8s}{ref:>+11.5f}"
            for a, b in strata:
                k = (inl >= a) & (inl < b)
                if k.sum() < 20:
                    line += f"{'n<20':>16s}"
                else:
                    line += (f"{np.median(sl[k]) - ref:>+10.5f}"
                             f"{'(' + f'{k.sum() / 1000:.0f}k)':>6s}")
            print(line)

        print()
        print(f"TABLE 7[{tag}] - the estimator's own consensus floor.")
        allinl = np.concatenate([src_frames(fr, st, m)[1] for m in srcs
                                 if src_frames(fr, st, m)[1].size])
        print(f"  min inlier_ratio over all {allinl.size:,} fitted frames: "
              f"{allinl.min():.4f}")
        print("  pc/rff/dsp.py:97 rejects any hypothesis with fewer than")
        print("  max(4, n//4) inliers; with n = 52 usable subcarriers that is")
        print("  13/52 = 0.250, so no frame can ever reach the estimator with")
        print("  inlier_ratio < 0.25 and a min_inlier below 0.25 is degenerate.")
        print()
    return 0


def cmd_crossrx(args):
    """Do the two receivers agree on a source's SFO?

    A crystal property must be the same on both boards. The beacons already
    disagree (docs/SEPARATION_SCALING.md §0: same-beacon receiver-to-receiver
    differences of 0.00897 to 0.05750 exceed every within-receiver
    beacon-to-beacon difference). This asks the same question of the ambient
    population, which is the direct test of whether an ambient "SFO" is a
    transmitter property at all.
    """
    ta, tb = args.tags.split(",")
    fa, sa = load(ta)
    fb, sb = load(tb)
    Ca, Cb = classify(sa, ta), classify(sb, tb)
    gate = args.min_inlier
    macs = BEACONS + sorted(
        {m for m in sa["amb_macs"] if Ca.get(m) in ("R", "P?", "P")}
        & {m for m in sb["amb_macs"] if Cb.get(m) in ("R", "P?", "P")})
    print("=" * 78)
    print(f"TABLE 8 - CROSS-RECEIVER AGREEMENT at min_inlier = {gate}")
    print("=" * 78)
    print(f"{'mac':19s}{'kind':5s}" + f"{ta + ' med':>12s}{'n':>9s}{'medinl':>8s}"
          + f"{tb + ' med':>12s}{'n':>9s}{'medinl':>8s}"
          + f"{'diff':>11s}{'x SD':>8s}")
    rows = []
    for m in macs:
        va = gated(fa, sa, m, gate)
        vb = gated(fb, sb, m, gate)
        if va.size < args.min_frames or vb.size < args.min_frames:
            continue
        ia = src_frames(fa, sa, m)[1]
        ib = src_frames(fb, sb, m)[1]
        ma, mb = float(np.median(va)), float(np.median(vb))
        kind = BNAME.get(m, "LAA" if (int(m.split(":")[0], 16) & 2) else "OUI")
        d = ma - mb
        rows.append((m, kind, ma, va.size, float(np.median(ia)),
                     mb, vb.size, float(np.median(ib)), d))
    for r in sorted(rows, key=lambda x: abs(x[8])):
        print(f"{r[0]:19s}{r[1]:5s}{r[2]:>+12.5f}{r[3]:>9,d}{r[4]:>8.3f}"
              f"{r[5]:>+12.5f}{r[6]:>9,d}{r[7]:>8.3f}"
              f"{r[8]:>+11.5f}{abs(r[8]) / BETWEEN_UNIT_SD:>8.1f}")
    if len(rows) >= 3:
        q = np.array([min(r[4], r[7]) for r in rows])
        e = np.array([abs(r[8]) for r in rows])
        print(f"\n  Spearman(min median inlier_ratio, |cross-receiver diff|) "
              f"over n = {len(rows)}: "
              f"{spearman(q, e):+.3f}")
        print("  A source whose two receivers disagree is a source whose slope")
        print("  is not a pure transmitter property. pc/rff/dsp.py's docstring")
        print("  says the slope carries timing AND sampling offset; only the")
        print("  sampling part is crystal-bound.")
    return 0


def cmd_alias(args):
    """Is a large cross-receiver slope disagreement a mis-unwrap?

    RANSAC fits a line through a consensus subset. If that subset sits one
    turn away from the rest, the fitted slope moves by 2*pi/dk where dk is
    the span of the subset. Over the 52 usable subcarriers that is
    2*pi/52 = 0.1208 to 2*pi/26 = 0.2417 rad/sc. If the observed
    disagreements land in that band, the ambient "SFO" spread is partly an
    estimator branch choice rather than a transmitter property.
    """
    tags = args.tags.split(",")
    print("=" * 78)
    print(f"TABLE 9 - SLOPE DISTRIBUTION for {args.mac}, "
          f"min_inlier = {args.min_inlier}")
    print("=" * 78)
    print("  one-turn mis-unwrap moves a slope by 2*pi/dk:")
    for dk in (52, 40, 32, 26):
        print(f"    dk = {dk:3d} usable subcarriers -> {2 * np.pi / dk:.4f} rad/sc")
    print()
    for t in tags:
        fr, st = load(t)
        sl, inl, res, rssi, _ = src_frames(fr, st, args.mac)
        if sl.size == 0:
            print(f"  {t}: no frames")
            continue
        k = (inl >= args.min_inlier) & (res <= SHIPPED_MAX_RESID)
        v = sl[k]
        qs = np.percentile(v, [0, 5, 25, 50, 75, 95, 100])
        print(f"  {t}: n = {v.size:,}  median inlier {np.median(inl[k]):.3f}  "
              f"median rssi {np.median(rssi[k]):.1f}")
        print("     slope percentiles 0/5/25/50/75/95/100: "
              + " ".join(f"{q:+.4f}" for q in qs))
        h, edges = np.histogram(v, bins=24)
        for c, lo, hi in zip(h, edges[:-1], edges[1:]):
            if c:
                print(f"     [{lo:+.4f},{hi:+.4f})  {c:6,d}  "
                      + "#" * min(50, int(50 * c / h.max())))
    return 0


def spearman(x, y):
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    rx -= rx.mean()
    ry -= ry.mean()
    den = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float((rx * ry).sum() / den) if den else float("nan")


# ----------------------------------------------------------------- compare

def sfo_stats(sl):
    return float(np.mean(sl)), float(np.var(sl, ddof=1) if sl.size > 1 else 0.0)


def sep_matrix(vals, robust=False):
    """1-D SFO separation under pooled variance.

    Same construction as pc/rff/discriminator.py:116-140 (pooled covariance,
    returns d not d-squared) restricted to the SFO axis, with the same
    per-source variance floor of 1e-8 (rad/sc)^2 applied before pooling.
    SFO only: the relevant chi-square is chi2(1) = 3.841 / 6.635, not the
    2-dof 5.991 / 9.210 the shipped code uses.

    vals: dict id -> 1-D array of per-frame slopes.
    """
    ids = [k for k, v in vals.items() if v.size >= Discriminator.MIN_CHARACTERIZED]
    mu, var, n = {}, {}, {}
    floored = []
    for i in ids:
        v = vals[i]
        n[i] = v.size
        if robust:
            mu[i] = float(np.median(v))
            # normal-consistent MAD; squared to be a variance
            mad = float(np.median(np.abs(v - mu[i]))) * 1.4826
            var[i] = mad * mad
        else:
            mu[i] = float(np.mean(v))
            var[i] = float(np.var(v, ddof=1))
        if var[i] < VAR_FLOOR_SFO:
            floored.append(i)
            var[i] = VAR_FLOOR_SFO
    num = sum(var[i] * (n[i] - 1) for i in ids)
    den = max(sum(n[i] - 1 for i in ids), 1)
    pooled = num / den
    sd = np.sqrt(pooled)
    d = {}
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            i, j = ids[a], ids[b]
            d[(i, j)] = abs(mu[i] - mu[j]) / sd
    return ids, mu, var, n, sd, d, floored


BOOT_CAP = 20000


def boot_sep(va, vb, sd_fixed, n_boot=2000, seed=0):
    """Percentile bootstrap over frames, pooled sd held fixed.

    Above BOOT_CAP frames the resample runs on a without-replacement
    subsample of that size, which widens the interval rather than narrowing
    it — the same convention as docs/POSITIVE_CONTROL_0822.md §3.2. Neither
    this nor a bootstrap over windows models autocorrelation, so both
    understate; nothing in this document rests on the width.
    """
    rng = np.random.default_rng(seed)
    if va.size > BOOT_CAP:
        va = rng.choice(va, BOOT_CAP, replace=False)
    if vb.size > BOOT_CAP:
        vb = rng.choice(vb, BOOT_CAP, replace=False)
    a = va[rng.integers(0, va.size, (n_boot, va.size))].mean(axis=1)
    b = vb[rng.integers(0, vb.size, (n_boot, vb.size))].mean(axis=1)
    out = np.abs(a - b) / sd_fixed
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def gated(fr, st, mac, gate):
    sl, inl, res, _, _ = src_frames(fr, st, mac)
    k = (inl >= gate) & (res <= SHIPPED_MAX_RESID)
    return sl[k]


def print_matrix(title, ids, d, names, mu, n, extra=""):
    print(f"\n{title}{extra}")
    lab = [names.get(i, i) for i in ids]
    w = max(len(x) for x in lab) + 2
    print(" " * w + "".join(f"{x:>{w}s}" for x in lab))
    for a, ia in enumerate(ids):
        row = f"{lab[a]:<{w}s}"
        for b, ib in enumerate(ids):
            if a == b:
                row += f"{'.':>{w}s}"
            else:
                key = (ia, ib) if (ia, ib) in d else (ib, ia)
                row += f"{d[key]:>{w}.2f}"
        print(row + f"   n={n[ia]:,}  mu={mu[ia]:+.5f}")


def summarise(d, keys):
    v = sorted(d[k] for k in keys)
    if not v:
        return None
    return {"min": v[0], "med": float(np.median(v)), "max": v[-1], "n": len(v)}


def cmd_compare(args):
    tags = args.tags.split(",")
    gate = args.min_inlier
    minf = args.min_frames
    for tag in tags:
        fr, st = load(tag)
        C = classify(st, tag)
        drop = {x.strip().lower() for x in args.drop.split(",") if x.strip()}
        amb_all = [m for m in st["amb_macs"]
                   if C.get(m) in ("P?", "P", "R") and m not in drop]
        if drop:
            print(f"  (excluded by --drop: {sorted(drop)})")
        vals = {}
        for m in BEACONS:
            vals[m] = gated(fr, st, m, gate)
        amb = []
        excluded = []
        for m in amb_all:
            v = gated(fr, st, m, gate)
            if v.size >= minf:
                vals[m] = v
                amb.append(m)
            else:
                excluded.append((m, v.size, src_frames(fr, st, m)[0].size,
                                 st["mac"][m]["in_win"]))
        names = dict(BNAME)
        for m in amb:
            names[m] = m[-8:]

        print("=" * 78)
        print(f"NODE {tag}   min_inlier = {gate}   max_resid = "
              f"{SHIPPED_MAX_RESID}   min accepted frames = {minf}")
        print(f"  qualifying: {len(BEACONS)} beacons + {len(amb)} ambient")
        print("=" * 78)
        if excluded:
            print("  ambient sources that did NOT qualify, with the count that")
            print("  excluded them (accepted / fitted / rows in window):")
            for m, a, f, r in sorted(excluded, key=lambda x: -x[1]):
                print(f"    {m}  accepted {a:>5,d}   fitted {f:>5,d}"
                      f"   rows {r:>6,d}")

        # ---- the three matrices
        ids_b, mu, var, n, sd_b, d_b, fl_b = sep_matrix(
            {m: vals[m] for m in BEACONS})
        print_matrix("SFO separation, BEACONS only (pooled over beacons)",
                     ids_b, d_b, names, mu, n,
                     extra=f"   pooled sd = {sd_b:.6f} rad/sc")
        if fl_b:
            print(f"  !! variance floor tripped by: {fl_b}")

        if len(amb) >= 2:
            ids_a, mua, vara, na, sd_a, d_a, fl_a = sep_matrix(
                {m: vals[m] for m in amb})
            print_matrix("SFO separation, AMBIENT only (pooled over ambient)",
                         ids_a, d_a, names, mua, na,
                         extra=f"   pooled sd = {sd_a:.6f} rad/sc")
            if fl_a:
                print(f"  !! variance floor tripped by: {fl_a}")
        else:
            ids_a, d_a, sd_a = [], {}, float("nan")
            print("\n  fewer than 2 ambient sources qualify: no ambient matrix")

        ids_x, mux, varx, nx, sd_x, d_x, fl_x = sep_matrix(vals)
        print_matrix("SFO separation, ALL SOURCES (single pooled sd)",
                     ids_x, d_x, names, mux, nx,
                     extra=f"   pooled sd = {sd_x:.6f} rad/sc")
        if fl_x:
            print(f"  !! variance floor tripped by: {fl_x}")

        # ---- the answer
        bk = [k for k in d_x if k[0] in BEACONS and k[1] in BEACONS]
        ak = [k for k in d_x if k[0] in amb and k[1] in amb]
        xk = [k for k in d_x if (k[0] in BEACONS) != (k[1] in BEACONS)]
        print("\n  UNDER THE COMMON POOLED SD (all sources), by group:")
        print(f"  {'group':22s}{'pairs':>7s}{'min':>9s}{'median':>9s}{'max':>9s}"
              f"{'raw min':>11s}{'raw med':>11s}{'raw spread':>12s}")
        for label, keys, members in (("beacon-beacon", bk, BEACONS),
                                     ("ambient-ambient", ak, amb),
                                     ("beacon-ambient", xk, None)):
            s = summarise(d_x, keys)
            if not s:
                continue
            raw = sorted(abs(mux[a] - mux[b]) for a, b in keys)
            if members:
                vv = [mux[m] for m in members if m in mux]
                spread = max(vv) - min(vv) if len(vv) > 1 else float("nan")
            else:
                spread = float("nan")
            print(f"  {label:22s}{s['n']:>7d}{s['min']:>9.2f}{s['med']:>9.2f}"
                  f"{s['max']:>9.2f}{raw[0]:>11.5f}"
                  f"{float(np.median(raw)):>11.5f}{spread:>12.5f}")
        print("  ^ WARNING. The pooled sd above is a variance pooled with")
        print("    weight (n-1). The three beacons bring ~3.5 M frames and the")
        print("    ambient sources ~2 k, so this denominator IS the beacon")
        print("    denominator, and dividing ambient centroid gaps by it")
        print("    flatters them. It is printed because it is what")
        print("    pc/rff/discriminator.py:116 would compute on a library")
        print("    holding all eleven sources. The like-for-like comparison is")
        print("    the next table.")

        print("\n  EACH GROUP AGAINST ITS OWN POOLED SD (like for like):")
        print(f"  {'group':22s}{'srcs':>6s}{'pairs':>7s}{'pooled sd':>12s}"
              f"{'min':>9s}{'median':>9s}{'max':>9s}"
              f"{'raw min':>11s}{'raw med':>11s}{'raw spread':>12s}")
        own = {}
        for label, members in (("beacon-beacon", BEACONS),
                               ("ambient-ambient", amb)):
            if len(members) < 2:
                continue
            idg, mug, _, ng, sdg, dg, flg = sep_matrix(
                {m: vals[m] for m in members})
            own[label] = (idg, mug, ng, sdg, dg)
            s = summarise(dg, list(dg))
            raw = sorted(abs(mug[a] - mug[b]) for a, b in dg)
            vv = [mug[m] for m in idg]
            print(f"  {label:22s}{len(idg):>6d}{s['n']:>7d}{sdg:>12.6f}"
                  f"{s['min']:>9.2f}{s['med']:>9.2f}{s['max']:>9.2f}"
                  f"{raw[0]:>11.5f}{float(np.median(raw)):>11.5f}"
                  f"{max(vv) - min(vv):>12.5f}")
            if flg:
                print(f"    !! variance floor tripped by: {flg}")

        print(f"\n  yardsticks: BETWEEN_UNIT_SD = {BETWEEN_UNIT_SD} "
              f"(pc/exp_thermal_evidence.py:129), "
              f"twin dSFO = {TWIN_DSFO} (pc/exp_lot_hypothesis.py:85-86)")
        print(f"  chi2(1) thresholds for a 1-D separation: "
              f"{CHI2_1_95} (95%) -> d = {np.sqrt(CHI2_1_95):.3f} sigma, "
              f"{CHI2_1_99} (99%) -> d = {np.sqrt(CHI2_1_99):.3f} sigma.")
        print("  pc/rff/discriminator.py:23-24 ships 5.991/9.210, which are the")
        print("  2-dof values; these separations are 1-D, so those are wrong")
        print("  here. The codebase's separate >3 sigma rule of thumb")
        print("  (pc/rff_offline.py:322) is unaffected by the dof question.")

        print("\n  CAN YOU ACTUALLY TELL THE PAIR APART WITH THE FRAMES YOU")
        print("  HAVE?  |dmu| divided by the standard error of the difference")
        print("  of means, not by a population sd. This is the statistic that")
        print("  charges a source for having only 20 frames; the sigma columns")
        print("  above do not.")
        print(f"  {'group':22s}{'pairs':>7s}{'min t':>9s}{'median t':>10s}"
              f"{'max t':>9s}{'pairs |t|>3':>13s}")
        for label, keys in (("beacon-beacon", bk), ("ambient-ambient", ak),
                            ("beacon-ambient", xk)):
            if not keys:
                continue
            ts = []
            for a, b in keys:
                va, vb = vals[a], vals[b]
                se = np.sqrt(np.var(va, ddof=1) / va.size
                             + np.var(vb, ddof=1) / vb.size)
                ts.append(abs(mux[a] - mux[b]) / se if se > 0 else np.inf)
            ts = sorted(ts)
            print(f"  {label:22s}{len(ts):>7d}{ts[0]:>9.2f}"
                  f"{float(np.median(ts)):>10.2f}{ts[-1]:>9.2f}"
                  f"{sum(1 for t in ts if t > 3):>7d}/{len(ts):<5d}")

        # ---- robustness: median/MAD instead of mean/variance
        print("\n  ROBUSTNESS: median/MAD in place of mean/variance, each")
        print("  group against its OWN pool. A handful of wild frames on a")
        print("  20-frame source would move a mean and a variance a long way;")
        print("  if the group comparison survives this it is not that.")
        print(f"  {'group':22s}{'pairs':>7s}{'pooled sd':>12s}"
              f"{'min':>9s}{'median':>9s}{'max':>9s}")
        for label, members in (("beacon-beacon", BEACONS),
                               ("ambient-ambient", amb)):
            if len(members) < 2:
                continue
            _, _, _, _, sdr, dr, flr = sep_matrix(
                {m: vals[m] for m in members}, robust=True)
            s = summarise(dr, list(dr))
            print(f"  {label:22s}{s['n']:>7d}{sdr:>12.6f}{s['min']:>9.2f}"
                  f"{s['med']:>9.2f}{s['max']:>9.2f}")
            if flr:
                print(f"    !! variance floor tripped by: {flr}")

        # ---- bootstrap CIs on every pair, since ambient n is small
        print("\n  BOOTSTRAP 95% CI on each separation (2,000 resamples over")
        print("  frames, pooled sd held fixed; does not model autocorrelation,")
        print("  so it understates).")
        print(f"  {'pair':26s}{'n_a':>8s}{'n_b':>8s}{'d':>8s}{'95% CI':>18s}")
        for (a, b), dd in sorted(d_x.items(), key=lambda kv: kv[1]):
            lo, hi = boot_sep(vals[a], vals[b], sd_x)
            print(f"  {names[a] + ' vs ' + names[b]:26s}{vals[a].size:>8,d}"
                  f"{vals[b].size:>8,d}{dd:>8.2f}"
                  f"   [{lo:6.2f}, {hi:6.2f}]")

        # ---- matched-n control
        print("\n  MATCHED-n CONTROL: beacons subsampled to the median")
        print("  qualifying-ambient frame count, 200 draws.  If the beacon")
        print("  separations survive the subsample, the group difference is")
        print("  not an artefact of n.")
        if amb:
            nmed = int(np.median([vals[m].size for m in amb]))
            rng = np.random.default_rng(0)
            acc = defaultdict(list)
            for _ in range(200):
                sub = {m: rng.choice(vals[m], min(nmed, vals[m].size),
                                     replace=False) for m in BEACONS}
                _, _, _, _, _, dsub, _ = sep_matrix(sub)
                for k, v in dsub.items():
                    acc[k].append(v)
            print(f"  subsample size n = {nmed}")
            for k, v in acc.items():
                print(f"    {names[k[0]]} vs {names[k[1]]:12s} "
                      f"median {np.median(v):5.2f}  "
                      f"[{np.percentile(v, 2.5):5.2f}, "
                      f"{np.percentile(v, 97.5):5.2f}]  "
                      f"(full-n {d_b.get(k, d_b.get((k[1], k[0]))):.2f})")

        # ---- the window-based beacon figures, for continuity with the repo
        print("\n  FOR CONTINUITY with docs/SEPARATION_SCALING.md, which works")
        print("  in 64-frame windows: the same beacons, same gate, aggregated")
        print("  by pc/rff/dsp.py's real WindowAggregator.  Ambient sources")
        print("  cannot fill a 64-frame window, which is why the primary")
        print("  statistic above is the per-frame slope.")
        wv = {}
        for m in BEACONS:
            sl, inl, res, rssi, t = src_frames(fr, st, m)
            agg = WindowAggregator(64, gate, SHIPPED_MAX_RESID)
            outw = []
            for s, i2, r2, rs, tt in zip(sl, inl, res, rssi, t):
                w = agg.feed({"slope": float(s), "intercept": 0.0,
                              "cfo_hz": None, "inlier_ratio": float(i2),
                              "resid_std": float(r2)},
                             int(tt * 1e6), float(rs))
                if w:
                    outw.append(w["sfo"])
            wv[m] = np.array(outw)
        idsw, muw, varw, nw, sdw, dw, flw = sep_matrix(wv)
        print_matrix("  SFO separation, beacons, 64-frame windows",
                     idsw, dw, names, muw, nw,
                     extra=f"   pooled sd = {sdw:.6f} rad/sc")
        print()
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("lltf")
    p.add_argument("path")
    p.add_argument("--max-rows", type=int, default=400000)
    p.add_argument("--per-len", type=int, default=200)
    p.set_defaults(fn=cmd_lltf)

    p = sub.add_parser("modes")
    p.add_argument("path")
    p.add_argument("--max-rows", type=int, default=200000)
    p.set_defaults(fn=cmd_modes)

    p = sub.add_parser("scan")
    p.add_argument("path")
    p.add_argument("--tag", required=True)
    p.add_argument("--part", type=int, required=True)
    p.add_argument("--nparts", type=int, required=True)
    p.add_argument("--node-mode", type=int, required=True)
    p.add_argument("--chan-mode", type=int, required=True)
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("merge")
    p.add_argument("--tag", required=True)
    p.add_argument("--nparts", type=int, required=True)
    p.add_argument("--expect-rows", type=int, default=0)
    p.set_defaults(fn=cmd_merge)

    p = sub.add_parser("census")
    p.add_argument("--tags", required=True)
    p.set_defaults(fn=cmd_census)

    p = sub.add_parser("sweep")
    p.add_argument("--tags", required=True)
    p.set_defaults(fn=cmd_sweep)

    p = sub.add_parser("crossrx")
    p.add_argument("--tags", required=True)
    p.add_argument("--min-inlier", type=float, default=0.3)
    p.add_argument("--min-frames", type=int, default=20)
    p.set_defaults(fn=cmd_crossrx)

    p = sub.add_parser("alias")
    p.add_argument("--tags", required=True)
    p.add_argument("--mac", required=True)
    p.add_argument("--min-inlier", type=float, default=0.3)
    p.set_defaults(fn=cmd_alias)

    p = sub.add_parser("compare")
    p.add_argument("--tags", required=True)
    p.add_argument("--min-inlier", type=float, default=0.3)
    p.add_argument("--min-frames", type=int, default=20)
    p.add_argument("--drop", default="",
                   help="comma-separated ambient MACs to exclude")
    p.set_defaults(fn=cmd_compare)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
