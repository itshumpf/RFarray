#!/usr/bin/env python3
"""Does the choice of reference beacon change how much of the shared
receiver-and-environment term gets absorbed?

`docs/SEPARATION_SCALING.md` §0 established that on the 2026-08-22 overnight
capture the same-beacon receiver-to-receiver SFO differences (0.00897,
0.01721, 0.05750 rad/sc) all exceed every within-receiver beacon-to-beacon
difference on the S3 (0.00104, 0.00439, 0.00542). That inversion is what
makes the fingerprint non-transferable between receivers. Reference
normalisation is supposed to absorb the shared term. This script measures
whether it does.

FIVE REFERENCE CONDITIONS
  none  raw SFO, no normalisation
  B1    subtract B1's simultaneous SFO, measured on the SAME receiver
  B2    subtract B2's
  B3    subtract B3's
  pop   subtract the per-window median across all available sources on that
        receiver (common-mode rejection by the population; the target
        contributes to its own reference, so nothing collapses to zero).
        `popLOO` is the leave-one-out variant, reported as a sensitivity
        check.

THE PRIMARY METRIC is not classification accuracy. It is, per beacon per
condition, the d0wd-minus-s3 difference of the corrected SFO. A beacon used
as the reference is normalised against itself and collapses to ~0, so it is
excluded from its own condition rather than reported as a meaningless zero.

Reference correction is always WITHIN a receiver — the term being cancelled
is that receiver's. The correction is simultaneous: a window's reference is
the median of the reference source's gated frames lying inside that same
window's own time span on that same node.

Method notes
------------
* Phase work is `pc/rff/dsp.py`'s `FrameEstimator` / `WindowAggregator`.
  `pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py`
  are NOT used (`docs/CODE_INVENTORY.md` §4.2 C1/C2/C3: DC/guard-band index
  wrong; `pc/test_rff_synth.py` test 7: `phase_skew` mask sign inverted).
* The DSP runs once and every per-frame result is cached; the conditions are
  re-derived from that cache. Exact, for the reason
  `pc/exp_separation_scaling.py` states and `selftest_reagg()` re-checks:
  `FrameEstimator` state depends only on the order of a source's own frames
  and on nothing the gates do, and `WindowAggregator` gating is strictly
  downstream, emitting every `window` accepted frames with the buffer
  cleared.
* Parse is `np.fromstring(cs, sep=",")`, the same read as
  `pc/rff_offline.py:203`. `cs.split(",", 128)`
  (`pc/exp_overnight_0822.py:303`, `pc/exp_s3_sfo_steps.py:153,590`) drops
  every `csi_len = 128` row; §0 of `report` counts 128- and 256-length rows
  separately so the defect cannot recur unnoticed.
* Corrupt rows are screened by the two routes of
  `docs/OVERNIGHT_2026-08-22.md` §1: a width-9 median filter on `dropped`
  (tolerance 100, compared circularly mod 65536 so the u16 wraps are not
  false positives) and field plausibility on `node_id`, `env_id`, `channel`,
  `csi_len` in {128, 256, 384}, `noise_floor` in [-110, -70], `rssi` in
  [-100, -10]. Expected: 142 flagged on the d0wd, 0 on the S3.

Read-only on data/raw/. No serial port is opened. Nothing is staged,
committed or pushed.

Usage (from the repo root):

  export REFCHOICE_CACHE=/some/dir/outside/the/repo
  D=data/raw/d0wd_20260822_023034.csv
  S=data/raw/s3_20260822_023034.csv
  for p in $(seq 0 15); do
      python3 pc/exp_reference_choice.py scan $D --tag d0wd --part $p --nparts 16
      python3 pc/exp_reference_choice.py scan $S --tag s3   --part $p --nparts 16
  done
  python3 pc/exp_reference_choice.py merge --tag d0wd --nparts 16 --expect-rows 2983560
  python3 pc/exp_reference_choice.py merge --tag s3   --nparts 16 --expect-rows 3564005
  python3 pc/exp_reference_choice.py report --tags d0wd,s3
"""
import argparse
import os
import pickle
import sys
import warnings
from collections import defaultdict, deque

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rff.dsp import FrameEstimator, WindowAggregator          # noqa: E402

warnings.filterwarnings("ignore", category=DeprecationWarning)

CACHE = os.environ.get("REFCHOICE_CACHE", "/tmp/refchoice_cache")

# Empty-room window, seconds of pc_time_us since each file's first decodable
# row. docs/SEPARATION_SCALING.md "Inputs and window"; the operator re-entered
# at t ~ 23,067 s (docs/POSITIVE_CONTROL_0822.md §0, §2.1).
T_LO, T_HI = 300.0, 23000.0

B1 = "a4:f0:0f:77:91:20"      # the current default reference
B2 = "28:05:a5:2f:fa:48"
B3 = "f4:2d:c9:70:72:30"      # clock twin of B1 (docs/LOT_HYPOTHESIS.md)
BEACONS = [B1, B2, B3]
BNAME = {B1: "B1", B2: "B2", B3: "B3"}

# yardsticks, each with its source
BETWEEN_UNIT_SD = 0.00237     # pc/exp_thermal_evidence.py:129
TWIN_DSFO = 0.00080           # pc/exp_lot_hypothesis.py:85-86

SHIPPED_WINDOW = 64
SHIPPED_MIN_INLIER = 0.6
SHIPPED_MAX_RESID = 0.8

# docs/SEPARATION_SCALING.md §5.1's best configuration
BEST_WINDOW = 16384
BEST_MIN_INLIER = 0.90
BEST_MAX_RESID = 0.80

# corrupt-row screen (docs/OVERNIGHT_2026-08-22.md §1)
MEDFILT_W = 9
MEDFILT_TOL = 100
OK_CSI_LEN = (128, 256, 384)          # pc/rff/protocol.py:31 admits up to 384
NF_LO, NF_HI = -110, -70
RSSI_LO, RSSI_HI = -100, -10

MIN_REF_FRAMES = 8         # reference frames required inside a window's span
BOOT = 4000
TAU0 = 0.5
MIN_BIN_FRAC = 0.90

CONDITIONS = ["none", "B1", "B2", "B3", "pop", "popLOO"]


def cpath(tag, name):
    return os.path.join(CACHE, f"{tag}_{name}")


# ---------------------------------------------------------------- scan ----

class Growable:
    def __init__(self, dtype, n=1 << 20):
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
    """Byte range [lo, hi) snapped to line starts, tiling the file exactly."""
    size = os.path.getsize(path)
    lo = size * part // nparts
    hi = size * (part + 1) // nparts
    with open(path, "rb") as f:
        if part == 0:
            f.readline()                    # header
        else:
            f.seek(lo)
            f.readline()                    # discard the partial line
        lo = f.tell()
    return lo, hi


def circ_dev(x, med):
    """Signed distance x - med on the u16 ring, so counter wraps are not
    flagged as corruption."""
    d = (x - med) % 65536
    return d - 65536 if d > 32768 else d


def cmd_scan(args):
    os.makedirs(CACHE, exist_ok=True)
    tag = args.tag
    lo, hi = line_range(args.path, args.part, args.nparts)

    if args.part == 0:
        st = {"origin": None, "est": {}, "rows": 0,
              "len_rows": defaultdict(int), "vals_rows": defaultdict(int),
              "naive_dropped": 0, "bad_line": 0, "bad_field": 0,
              "node_ids": defaultdict(int), "channels": defaultdict(int),
              "env_ids": defaultdict(int), "mac_rows": defaultdict(int),
              "screened": 0, "screen_field": 0, "screen_med": 0,
              "screen_both": 0, "screened_examples": [],
              "emitted": 0, "in_window": 0,
              "mode_node": None, "mode_chan": None,
              "amb": {}, "pend": [], "byte_hi": lo}
        # The field screen compares node_id and channel against "the file's
        # own mode" (docs/OVERNIGHT_2026-08-22.md §1). Establish it from a
        # pre-scan of the head so the screen is live from the first row;
        # cmd_merge re-checks it against the whole-file histogram.
        ns, ch = defaultdict(int), defaultdict(int)
        with open(args.path, "rb") as f0:
            f0.readline()
            for _ in range(20000):
                ln = f0.readline()
                if not ln:
                    break
                q = ln.decode("ascii", "replace").split(",", 9)
                if len(q) != 10:
                    continue
                rr = q[9].rsplit(",", 3)
                if len(rr) != 4:
                    continue
                try:
                    ns[int(rr[1])] += 1
                    ch[int(q[6])] += 1
                except ValueError:
                    continue
        st["mode_node"] = max(ns.items(), key=lambda kv: kv[1])[0]
        st["mode_chan"] = max(ch.items(), key=lambda kv: kv[1])[0]
        print(f"  head pre-scan: node_id mode {st['mode_node']} "
              f"({ns[st['mode_node']]}/{sum(ns.values())}), "
              f"channel mode {st['mode_chan']} "
              f"({ch[st['mode_chan']]}/{sum(ch.values())})")
    else:
        with open(cpath(tag, f"state{args.part - 1}.pkl"), "rb") as f:
            st = pickle.load(f)
        assert st["byte_hi"] == lo, (
            f"part {args.part} starts at {lo} but part {args.part-1} ended at "
            f"{st['byte_hi']} — the parts do not tile the file")

    est = st["est"]
    bidx = {m: i for i, m in enumerate(BEACONS)}
    nan = np.float32("nan")

    c_t = Growable(np.int32)          # ms since origin
    c_mac = Growable(np.int8)
    c_slope = Growable(np.float32)
    c_cfo = Growable(np.float32)
    c_inl = Growable(np.float32)
    c_res = Growable(np.float32)
    c_rssi = Growable(np.int16)

    pend = deque(st["pend"])
    st["pend"] = []

    def emit(row, med):
        """Screen one row against both routes, then estimate if it survives."""
        (pc_us, mac, rssi, esp_us, csi_len, node_id, env_id, chan, nf,
         drop, vals) = row
        st["emitted"] += 1
        bad_f = not (node_id == st["mode_node"] and env_id == 0
                     and chan == st["mode_chan"]
                     and csi_len in OK_CSI_LEN
                     and NF_LO <= nf <= NF_HI
                     and RSSI_LO <= rssi <= RSSI_HI)
        bad_m = (med is not None and abs(circ_dev(drop, med)) > MEDFILT_TOL)
        if bad_f or bad_m:
            st["screened"] += 1
            st["screen_field"] += bool(bad_f)
            st["screen_med"] += bool(bad_m)
            st["screen_both"] += bool(bad_f and bad_m)
            if len(st["screened_examples"]) < 12:
                st["screened_examples"].append(
                    (int(pc_us), mac, int(rssi), int(nf), int(chan),
                     int(csi_len), int(drop), bool(bad_f), bool(bad_m)))
            return
        t = (pc_us - st["origin"]) * 1e-6
        if t < T_LO or t >= T_HI:
            return
        st["in_window"] += 1
        t_ms = int(round((t - T_LO) * 1000.0))
        if mac in bidx:
            e = est.setdefault(mac, FrameEstimator()).feed(vals, esp_us)
            c_t.push(t_ms)
            c_mac.push(bidx[mac])
            c_rssi.push(max(-32768, min(32767, rssi)))
            if e is None:
                c_slope.push(nan); c_cfo.push(nan)
                c_inl.push(nan); c_res.push(nan)
            else:
                c_slope.push(e["slope"])
                c_cfo.push(nan if e["cfo_hz"] is None else e["cfo_hz"])
                c_inl.push(e["inlier_ratio"])
                c_res.push(e["resid_std"])
        else:
            # ambient: a few thousand rows, and the direct proof that
            # 128-length rows reach the estimator
            a = st["amb"].setdefault(
                mac, {"n": 0, "fit": 0, "acc": 0, "rssi": 0.0,
                      "t": [], "slope": [], "inlier": []})
            a["n"] += 1
            a["rssi"] += rssi
            e = est.setdefault(mac, FrameEstimator()).feed(vals, esp_us)
            if e is not None:
                a["fit"] += 1
                if (e["inlier_ratio"] >= SHIPPED_MIN_INLIER
                        and e["resid_std"] <= SHIPPED_MAX_RESID):
                    a["acc"] += 1
                if len(a["slope"]) < 8000:
                    a["t"].append(t_ms)
                    a["slope"].append(e["slope"])
                    a["inlier"].append(e["inlier_ratio"])

    with open(args.path, "rb") as fb:
        fb.seek(lo)
        for raw in fb:
            st["rows"] += 1
            line = raw.decode("ascii", "replace")
            p9 = line.split(",", 9)
            done = fb.tell() >= hi
            if len(p9) != 10:
                st["bad_line"] += 1
                if done:
                    break
                continue
            rest = p9[9].rsplit(",", 3)
            if len(rest) != 4:
                st["bad_line"] += 1
                if done:
                    break
                continue
            try:
                pc_us = int(p9[0])
                mac = p9[3].lower()
                rssi = int(p9[4])
                nf = int(p9[5])
                chan = int(p9[6])
                esp_us = int(p9[7])
                csi_len = int(p9[8])
                node_id = int(rest[1])
                env_id = int(rest[2])
                drop = int(rest[3])
            except ValueError:
                st["bad_field"] += 1
                if done:
                    break
                continue

            cs = rest[0]
            if cs[:1] == '"':
                cs = cs[1:-1] if cs[-1:] == '"' else cs[1:]
            vals = np.fromstring(cs, dtype=np.float64, sep=",")

            st["len_rows"][csi_len] += 1
            st["vals_rows"][vals.size] += 1
            st["node_ids"][node_id] += 1
            st["channels"][chan] += 1
            st["env_ids"][env_id] += 1
            st["mac_rows"][mac] += 1
            if len(cs.split(",", 128)) < 129:
                st["naive_dropped"] += 1     # what split(",",128) would lose

            if st["origin"] is None:
                st["origin"] = pc_us

            pend.append((pc_us, mac, rssi, esp_us, csi_len, node_id, env_id,
                         chan, nf, drop, vals))
            if len(pend) == MEDFILT_W:
                med = float(np.median([r[9] for r in pend]))
                emit(pend[MEDFILT_W // 2], med)
                pend.popleft()
            if done:
                break
        st["byte_hi"] = fb.tell()

    if st["byte_hi"] >= os.path.getsize(args.path):
        # end of file: flush the tail with a short filter window
        while pend:
            med = float(np.median([r[9] for r in pend])) if len(pend) >= 3 \
                else None
            emit(pend[0], med)
            pend.popleft()
    st["pend"] = list(pend)

    np.savez(cpath(tag, f"part{args.part}.npz"),
             t=c_t.out(), mac=c_mac.out(), slope=c_slope.out(),
             cfo=c_cfo.out(), inlier=c_inl.out(), resid=c_res.out(),
             rssi=c_rssi.out())
    with open(cpath(tag, f"state{args.part}.pkl"), "wb") as f:
        pickle.dump(st, f)
    print(f"{tag} part {args.part}/{args.nparts}: bytes [{lo},{st['byte_hi']}) "
          f"rows so far {st['rows']} emitted {st['emitted']} "
          f"screened {st['screened']} cached {c_t.n}")
    return 0


def cmd_merge(args):
    tag = args.tag
    with open(cpath(tag, f"state{args.nparts - 1}.pkl"), "rb") as f:
        st = pickle.load(f)
    parts = [np.load(cpath(tag, f"part{p}.npz")) for p in range(args.nparts)]
    out = {}
    for k in ("t", "mac", "slope", "cfo", "inlier", "resid", "rssi"):
        out[k] = np.concatenate([p[k] for p in parts])
    back = int((np.diff(out["t"].astype(np.int64)) < 0).sum())
    np.savez(cpath(tag, "frames.npz"), **out)
    for k in ("len_rows", "vals_rows", "node_ids", "channels", "env_ids",
              "mac_rows"):
        st[k] = dict(st[k])
    # re-check the head pre-scan's modes against the whole-file histograms
    wn = max(st["node_ids"].items(), key=lambda kv: kv[1])[0]
    wc = max(st["channels"].items(), key=lambda kv: kv[1])[0]
    st["mode_ok"] = (wn == st["mode_node"] and wc == st["mode_chan"])
    print(f"{tag}: screen modes node_id={st['mode_node']} "
          f"channel={st['mode_chan']}; whole-file modes {wn}/{wc} -> "
          f"{'AGREE' if st['mode_ok'] else 'DISAGREE'}")
    st.pop("est", None)
    st.pop("pend", None)
    with open(cpath(tag, "meta.pkl"), "wb") as f:
        pickle.dump(st, f)
    ok = (args.expect_rows is None or st["rows"] == args.expect_rows)
    print(f"{tag}: rows {st['rows']}"
          f"{' == expected' if ok else ' != expected %d' % args.expect_rows}"
          f"; emitted {st['emitted']}; screened corrupt {st['screened']}"
          f" (field {st['screen_field']}, medfilt {st['screen_med']},"
          f" both {st['screen_both']}); in-window frames {st['in_window']};"
          f" cached {out['t'].size}; t reversals {back}")
    return 0 if ok else 1


# --------------------------------------------------------- re-aggregation --

def _chunks(slope, t, window, min_inlier, max_resid, inlier, resid):
    """Gate, then chunk into consecutive groups of `window` accepted frames.

    Returns (sfo, t_lo, t_hi, idx0) arrays — one entry per emitted window.
    Equivalent to WindowAggregator(window, min_inlier, max_resid); checked
    against the real class by selftest_reagg().
    """
    keep = np.isfinite(slope) & (inlier >= min_inlier) & (resid <= max_resid)
    s = slope[keep]
    tt = t[keep]
    nw = s.size // window
    if nw == 0:
        z = np.empty(0)
        return z, z, z
    s = s[:nw * window].reshape(nw, window)
    tt = tt[:nw * window].reshape(nw, window)
    return np.median(s, axis=1), tt[:, 0], tt[:, -1]


def selftest_reagg(fr, tag):
    sel = np.where(fr["mac"] == 0)[0][:20000]
    slope = fr["slope"][sel].astype(np.float64)
    inl = fr["inlier"][sel].astype(np.float64)
    res = fr["resid"][sel].astype(np.float64)
    t = fr["t"][sel].astype(np.int64)
    agg = WindowAggregator(window=SHIPPED_WINDOW,
                           min_inlier_ratio=SHIPPED_MIN_INLIER,
                           max_resid=SHIPPED_MAX_RESID)
    ref = []
    for i in range(sel.size):
        e = None if not np.isfinite(slope[i]) else {
            "slope": slope[i], "intercept": 0.0, "cfo_hz": None,
            "inlier_ratio": inl[i], "resid_std": res[i]}
        o = agg.feed(e, int(t[i]), 0.0)
        if o is not None:
            ref.append(o["sfo"])
    got, _, _ = _chunks(slope, t, SHIPPED_WINDOW, SHIPPED_MIN_INLIER,
                        SHIPPED_MAX_RESID, inl, res)
    ok_n = len(ref) == got.size
    ok_s = ok_n and np.array_equal(np.array(ref), got)
    print(f"  {tag}: {sel.size} frames -> {got.size} windows; "
          f"count {'OK' if ok_n else 'MISMATCH'}, "
          f"sfo {'bit-identical' if ok_s else 'MISMATCH'}")
    return ok_n and ok_s


# ------------------------------------------------------------- conditions --

_SPLIT = {}


def split_by_mac(tag, fr):
    if tag in _SPLIT:
        return _SPLIT[tag]
    d = {}
    for i, mac in enumerate(BEACONS):
        s = fr["mac"] == i
        d[mac] = {"slope": fr["slope"][s].astype(np.float64),
                  "t": fr["t"][s].astype(np.int64),
                  "inlier": fr["inlier"][s].astype(np.float64),
                  "resid": fr["resid"][s].astype(np.float64),
                  "cfo": fr["cfo"][s].astype(np.float64)}
    _SPLIT[tag] = d
    return d


def gated(d, mac, min_inlier, max_resid):
    a = d[mac]
    k = (np.isfinite(a["slope"]) & (a["inlier"] >= min_inlier)
         & (a["resid"] <= max_resid))
    return a["slope"][k], a["t"][k]


def span_median(s_ref, t_ref, t_lo, t_hi):
    """Median of the reference's gated slopes inside [t_lo, t_hi]."""
    i = np.searchsorted(t_ref, t_lo, "left")
    j = np.searchsorted(t_ref, t_hi, "right")
    n = j - i
    out = np.full(t_lo.size, np.nan)
    ok = n >= MIN_REF_FRAMES
    for k in np.where(ok)[0]:
        out[k] = np.median(s_ref[i[k]:j[k]])
    return out, n


def corrected_windows(tag, fr, window, min_inlier, max_resid):
    """{condition: {mac: (sfo array, t_lo array)}} plus the reference
    coverage counts. All corrections are within this node."""
    d = split_by_mac(tag, fr)
    g = {m: gated(d, m, min_inlier, max_resid) for m in BEACONS}
    win = {}
    for m in BEACONS:
        s, t = g[m]
        sfo, tlo, thi = _chunks(s, t, window, 0.0, np.inf,
                                np.ones(s.size), np.zeros(s.size))
        win[m] = (sfo, tlo, thi)

    out = {c: {} for c in CONDITIONS}
    cover = {}
    for m in BEACONS:
        sfo, tlo, thi = win[m]
        out["none"][m] = (sfo, tlo)
        if sfo.size == 0:
            for c in CONDITIONS[1:]:
                out[c][m] = (np.empty(0), np.empty(0))
            continue
        refvals = {}
        for r in BEACONS:
            rv, n = span_median(g[r][0], g[r][1], tlo, thi)
            refvals[r] = rv
            cover[(m, r)] = (int(n.min()) if n.size else 0,
                             int(np.isfinite(rv).sum()), int(rv.size))
        for r in BEACONS:
            if r == m:
                out[BNAME[r]][m] = (np.empty(0), np.empty(0))   # self: excluded
                continue
            k = np.isfinite(refvals[r])
            out[BNAME[r]][m] = (sfo[k] - refvals[r][k], tlo[k])
        # population median across all available sources (target included)
        M = np.column_stack([refvals[r] for r in BEACONS])
        k = np.isfinite(M).all(axis=1)
        out["pop"][m] = (sfo[k] - np.median(M[k], axis=1), tlo[k])
        others = [refvals[r] for r in BEACONS if r != m]
        M2 = np.column_stack(others)
        k2 = np.isfinite(M2).all(axis=1)
        out["popLOO"][m] = (sfo[k2] - np.median(M2[k2], axis=1), tlo[k2])
    return out, cover


def _boot_medians(x, rng, n):
    """n bootstrap medians of x, in batches so the index array stays small."""
    out = np.empty(n)
    step = max(1, min(n, int(4e6 // max(x.size, 1))))
    done = 0
    while done < n:
        k = min(step, n - done)
        idx = rng.integers(0, x.size, size=(k, x.size))
        out[done:done + k] = np.median(x[idx], axis=1)
        done += k
    return out


def boot_diff_ci(a, b, rng, n=BOOT):
    """95 % CI on median(a) - median(b), resampling each node's windows
    independently. Windows are autocorrelated, so this understates."""
    if a.size < 2 or b.size < 2:
        return np.nan, np.nan
    if max(a.size, b.size) > 5000:
        n = 1000          # thousands of windows: the CI is narrow regardless
    dd = _boot_medians(a, rng, n) - _boot_medians(b, rng, n)
    return float(np.percentile(dd, 2.5)), float(np.percentile(dd, 97.5))


def sep1d_sfo(vals_by_mac, min_windows=5):
    """|mu_a - mu_b| / pooled sd on the SFO axis, no variance floor."""
    macs = [m for m, v in vals_by_mac.items() if v.size >= min_windows]
    if len(macs) < 2:
        return {}, np.nan
    num = sum((vals_by_mac[m].size - 1) * vals_by_mac[m].var(ddof=1)
              for m in macs)
    dof = sum(vals_by_mac[m].size - 1 for m in macs)
    sd = np.sqrt(num / max(dof, 1))
    out = {}
    for i in range(len(macs)):
        for j in range(i + 1, len(macs)):
            dmu = abs(vals_by_mac[macs[i]].mean() - vals_by_mac[macs[j]].mean())
            out[(BNAME[macs[i]], BNAME[macs[j]])] = (
                dmu / sd if sd > 0 else np.inf)
    return out, sd


# ------------------------------------------------------------- Allan -------

def allan(y, valid, taus_m):
    yy = np.where(valid, y, 0.0)
    S = np.concatenate([[0.0], np.cumsum(yy)])
    C = np.concatenate([[0], np.cumsum(valid.astype(np.int64))])
    N = y.size
    sig = []
    for m in taus_m:
        if 2 * m > N:
            sig.append(np.nan)
            continue
        cnt = C[m:] - C[:-m]
        tot = S[m:] - S[:-m]
        good = cnt >= max(1, int(np.ceil(MIN_BIN_FRAC * m)))
        with np.errstate(invalid="ignore", divide="ignore"):
            blk = np.where(good, tot / np.maximum(cnt, 1), np.nan)
        dd = blk[m:] - blk[:-m]
        ok = np.isfinite(dd)
        if int(ok.sum()) < 3:
            sig.append(np.nan)
            continue
        sig.append(float(np.sqrt(0.5 * np.mean(dd[ok] ** 2))))
    return np.array(sig)


def binned(tag, fr, min_inlier, max_resid):
    """Per-0.5 s-bin mean gated slope per beacon, on a common grid."""
    d = split_by_mac(tag, fr)
    nb = int(np.ceil((T_HI - T_LO) / TAU0))
    Y, V = {}, {}
    for m in BEACONS:
        s, t = gated(d, m, min_inlier, max_resid)
        b = np.clip((t / (TAU0 * 1000.0)).astype(np.int64), 0, nb - 1)
        cnt = np.bincount(b, minlength=nb)
        tot = np.bincount(b, weights=s, minlength=nb)
        v = cnt > 0
        y = np.zeros(nb)
        y[v] = tot[v] / cnt[v]
        Y[m] = y
        V[m] = v
    return Y, V, nb


# ------------------------------------------------------------------ report -

def load(tag):
    fr = dict(np.load(cpath(tag, "frames.npz")))
    with open(cpath(tag, "meta.pkl"), "rb") as f:
        meta = pickle.load(f)
    return fr, meta


def cmd_report(args):
    tags = args.tags.split(",")
    data = {t: load(t) for t in tags}
    rng = np.random.default_rng(0)

    print("=" * 78)
    print("REFERENCE CHOICE — 2026-08-22 overnight, empty-room window only")
    print("=" * 78)
    print(f"window: {T_LO:g} s <= t < {T_HI:g} s of pc_time_us since each "
          "file's first decodable row")
    print(f"yardsticks: BETWEEN_UNIT_SD={BETWEEN_UNIT_SD} "
          f"(pc/exp_thermal_evidence.py:129), TWIN_DSFO={TWIN_DSFO} "
          f"(pc/exp_lot_hypothesis.py:85-86)")
    print("all reference correction is WITHIN a receiver and simultaneous: "
          "a window's reference is the median of the reference source's "
          "gated frames inside that window's own time span on that node.")

    # ---- 0. parse + screen verification ---------------------------------
    print("\n### 0. PARSE AND CORRUPT-ROW VERIFICATION ###")
    for t in tags:
        fr, meta = data[t]
        vr, lr = meta["vals_rows"], meta["len_rows"]
        print(f"\n{t}: {meta['rows']} data rows; undecodable line "
              f"{meta['bad_line']}, field {meta['bad_field']}")
        print(f"  node_id {dict(meta['node_ids'])}  "
              f"channel {dict(meta['channels'])}  "
              f"env_id {dict(meta['env_ids'])}")
        print(f"  screen modes used: node_id={meta['mode_node']} "
              f"channel={meta['mode_chan']}")
        print("  parsed CSI vector length -> rows: " +
              ", ".join(f"{k}:{v}" for k, v in sorted(vr.items())))
        print("  csi_len column           -> rows: " +
              ", ".join(f"{k}:{v}" for k, v in sorted(lr.items())))
        print(f"  128-length rows seen by THIS parser: {vr.get(128, 0)}")
        print(f"  256-length rows seen by THIS parser: {vr.get(256, 0)}")
        print(f"  rows split(\",\",128) would have dropped: "
              f"{meta['naive_dropped']}")
        print(f"  rows put through the screen: {meta['emitted']}; "
              f"flagged corrupt {meta['screened']} "
              f"(field-plausibility {meta['screen_field']}, "
              f"dropped-median-filter {meta['screen_med']}, "
              f"both {meta['screen_both']})")
        for e in meta["screened_examples"][:6]:
            print(f"    e.g. mac {e[1]} rssi {e[2]} nf {e[3]} ch {e[4]} "
                  f"len {e[5]} dropped {e[6]} "
                  f"[field {'X' if e[7] else '-'} med {'X' if e[8] else '-'}]")
        amb = meta["amb"]
        print(f"  in-window frames kept: {meta['in_window']}; "
              f"ambient rows {sum(v['n'] for v in amb.values())}, "
              f"RANSAC fits {sum(v['fit'] for v in amb.values())} "
              "<- 0 here would mean the split(\",\",128) defect was inherited")
        for m, v in sorted(amb.items(), key=lambda kv: -kv[1]["n"])[:6]:
            sl = np.array(v["slope"])
            med = f"{np.median(sl):+.5f}" if sl.size else "—"
            print(f"    {m:<20} n={v['n']:>5} fits={v['fit']:>5} "
                  f"acc={v['acc']:>5} slope median {med}")

    print("\n### 0b. RE-AGGREGATION SELF-TEST vs the shipped "
          "WindowAggregator ###")
    allok = all(selftest_reagg(data[t][0], t) for t in tags)
    print(f"  all cells reproduce the shipped aggregator: {allok}")

    print("\n### 0c. CROSS-CHECK, shipped config, against "
          "docs/SEPARATION_SCALING.md §1 §0c ###")
    print(f"{'node':<6}{'b':<4}{'fed':>10}{'accepted':>10}{'rej %':>8}"
          f"{'windows':>9}{'SFO median':>12}{'IQR':>10}")
    for t in tags:
        fr, _ = data[t]
        d = split_by_mac(t, fr)
        for m in BEACONS:
            a = d[m]
            k = (np.isfinite(a["slope"]) & (a["inlier"] >= SHIPPED_MIN_INLIER)
                 & (a["resid"] <= SHIPPED_MAX_RESID))
            sfo, _, _ = _chunks(a["slope"], a["t"], SHIPPED_WINDOW,
                                SHIPPED_MIN_INLIER, SHIPPED_MAX_RESID,
                                a["inlier"], a["resid"])
            n = a["slope"].size
            iqr = (np.subtract(*np.percentile(sfo, [75, 25]))
                   if sfo.size else np.nan)
            print(f"{t:<6}{BNAME[m]:<4}{n:>10}{int(k.sum()):>10}"
                  f"{100*(1-k.sum()/max(n,1)):>8.3f}{sfo.size:>9}"
                  f"{np.median(sfo) if sfo.size else np.nan:>+12.5f}"
                  f"{iqr:>10.5f}")

    # ---- 1. THE PRIMARY METRIC ------------------------------------------
    configs = [("shipped", SHIPPED_WINDOW, SHIPPED_MIN_INLIER,
                SHIPPED_MAX_RESID),
               ("W16384/inlier0.60", BEST_WINDOW, SHIPPED_MIN_INLIER,
                BEST_MAX_RESID),
               ("W16384/inlier0.90 (SEPSCALE best)", BEST_WINDOW,
                BEST_MIN_INLIER, BEST_MAX_RESID)]

    store = {}
    for label, W, I, R in configs:
        print("\n\n" + "=" * 78)
        print(f"### 1. PRIMARY METRIC — d0wd minus s3, per beacon per "
              f"reference condition")
        print(f"###    config: {label}  (window {W} accepted frames, "
              f"min_inlier {I:g}, max_resid {R:g})")
        print("=" * 78)
        C = {}
        for t in tags:
            C[t], cov = corrected_windows(t, data[t][0], W, I, R)
            print(f"  {t}: windows per beacon (uncorrected) " + "  ".join(
                f"{BNAME[m]} {C[t]['none'][m][0].size}" for m in BEACONS))
            worst = [f"{BNAME[m]}<-{BNAME[r]} minframes {v[0]} "
                     f"covered {v[1]}/{v[2]}"
                     for (m, r), v in sorted(
                         cov.items(), key=lambda kv: kv[1][0])[:3]
                     if m != r]
            if worst:
                print(f"      reference coverage, worst 3: " + "; ".join(worst))
        store[label] = C
        if len(tags) != 2:
            continue
        a, b = tags
        print(f"\n{'cond':<8}{'beacon':<8}{f'{a} med':>12}{'n':>5}"
              f"{f'{b} med':>12}{'n':>5}{'d0wd-s3':>11}"
              f"{'95% CI':>26}{'x BU_SD':>9}")
        for c in CONDITIONS:
            for m in BEACONS:
                xa = C[a][c][m][0]
                xb = C[b][c][m][0]
                if xa.size == 0 or xb.size == 0:
                    why = ("reference is itself" if c == BNAME[m]
                           else "no windows")
                    print(f"{c:<8}{BNAME[m]:<8}"
                          f"{'—' if xa.size==0 else '%+.5f'%np.median(xa):>12}"
                          f"{xa.size:>5}"
                          f"{'—' if xb.size==0 else '%+.5f'%np.median(xb):>12}"
                          f"{xb.size:>5}{'—':>11}{'  (' + why + ')':>26}")
                    continue
                ma, mb = float(np.median(xa)), float(np.median(xb))
                dd = ma - mb
                lo, hi = boot_diff_ci(xa, xb, rng)
                print(f"{c:<8}{BNAME[m]:<8}{ma:>+12.5f}{xa.size:>5}"
                      f"{mb:>+12.5f}{xb.size:>5}{dd:>+11.5f}"
                      f"{f'[{lo:+.5f}, {hi:+.5f}]':>26}"
                      f"{abs(dd)/BETWEEN_UNIT_SD:>9.2f}")

        print(f"\n  summary — like-for-like: each condition's mean "
              f"|d0wd - s3| against 'none' over EXACTLY the same beacons")
        print(f"{'cond':<8}{'beacons':>26}{'mean |diff|':>13}"
              f"{'none, same set':>16}{'shrink':>9}{'max |diff|':>12}")
        for c in CONDITIONS:
            ds, dn, names = [], [], []
            for m in BEACONS:
                xa, xb = C[a][c][m][0], C[b][c][m][0]
                na, nb = C[a]["none"][m][0], C[b]["none"][m][0]
                if xa.size and xb.size and na.size and nb.size:
                    ds.append(abs(np.median(xa) - np.median(xb)))
                    dn.append(abs(np.median(na) - np.median(nb)))
                    names.append(BNAME[m])
            if not ds:
                print(f"{c:<8}{'(none measurable)':>26}")
                continue
            mu, mn = float(np.mean(ds)), float(np.mean(dn))
            print(f"{c:<8}{','.join(names):>26}{mu:>13.5f}{mn:>16.5f}"
                  f"{(mn/mu if mu > 0 else np.inf):>8.2f}x{max(ds):>12.5f}")
        print("  'shrink' > 1 means the condition reduced the "
              "receiver-to-receiver term on that beacon set; < 1 means it "
              "made it worse. A beacon used as its own reference is excluded "
              "from its condition, so each row states its own beacon set.")

    # ---- 2. within-source spread ----------------------------------------
    print("\n\n" + "=" * 78)
    print("### 2. WITHIN-SOURCE SPREAD of the corrected per-window SFO ###")
    print("=" * 78)
    for label, W, I, R in configs[1:]:
        print(f"\n--- {label} ---")
        C = store[label]
        for t in tags:
            print(f"  {t}:")
            print(f"    {'cond':<8}" + "".join(
                f"{BNAME[m]+' IQR':>13}{BNAME[m]+' sd':>12}" for m in BEACONS))
            for c in CONDITIONS:
                row = f"    {c:<8}"
                for m in BEACONS:
                    x = C[t][c][m][0]
                    if x.size < 2:
                        row += f"{'—':>13}{'—':>12}"
                    else:
                        row += (f"{np.subtract(*np.percentile(x,[75,25])):>13.5f}"
                                f"{x.std(ddof=1):>12.5f}")
                print(row)

    print("\n### 2b. ALLAN DEVIATION FLOOR of the corrected 0.5 s-bin "
          "series (shipped gates) ###")
    ms = np.unique(np.round(np.logspace(0, np.log10(7200), 28)).astype(int))
    taus = ms * TAU0
    for t in tags:
        Y, V, nb = binned(t, data[t][0], SHIPPED_MIN_INLIER, SHIPPED_MAX_RESID)
        print(f"\n  {t}: {'cond':<8}" + "".join(
            f"{BNAME[m]+' floor':>14}{'@tau':>8}" for m in BEACONS))
        for c in CONDITIONS:
            row = f"  {'':<6}{c:<8}"
            for m in BEACONS:
                if c == BNAME[m]:
                    row += f"{'(self)':>14}{'':>8}"
                    continue
                if c == "none":
                    y, v = Y[m], V[m]
                elif c in ("pop", "popLOO"):
                    src = BEACONS if c == "pop" else [r for r in BEACONS
                                                      if r != m]
                    M = np.column_stack([Y[r] for r in src])
                    v = V[m] & np.column_stack([V[r] for r in src]).all(axis=1)
                    y = Y[m] - np.median(M, axis=1)
                else:
                    r = [x for x in BEACONS if BNAME[x] == c][0]
                    v = V[m] & V[r]
                    y = Y[m] - Y[r]
                sig = allan(np.where(v, y, 0.0), v, ms)
                if not np.isfinite(sig).any():
                    row += f"{'—':>14}{'':>8}"
                    continue
                k = int(np.nanargmin(np.where(np.isfinite(sig), sig, np.inf)))
                row += f"{sig[k]:>14.3e}{taus[k]:>8.1f}"
            print(row)

    # ---- 3. pairwise separation ------------------------------------------
    print("\n\n" + "=" * 78)
    print("### 3. PAIRWISE SEPARATION among the sources each condition "
          "leaves ###")
    print("=" * 78)
    print("SFO axis only, |dmu| / pooled sd, no variance floor. CONFOUND: "
          "with three beacons each single-beacon reference leaves a "
          "different pair, and B2-as-reference leaves the B1/B3 clock twins, "
          "which cannot separate for reasons that have nothing to do with "
          "reference quality (docs/LOT_HYPOTHESIS.md). Only 'none', 'pop' "
          "and 'popLOO' leave all three.")
    for label, W, I, R in configs[1:]:
        print(f"\n--- {label} ---")
        C = store[label]
        for t in tags:
            print(f"  {t}:")
            for c in CONDITIONS:
                vals = {m: C[t][c][m][0] for m in BEACONS
                        if C[t][c][m][0].size >= 5}
                pairs, sd = sep1d_sfo(vals)
                if not pairs:
                    print(f"    {c:<8} (fewer than two sources with >= 5 "
                          f"windows)")
                    continue
                txt = "  ".join(f"{a}-{b} {v:.2f}s" for (a, b), v
                                in sorted(pairs.items()))
                print(f"    {c:<8} pooled sd {sd:.5f}   {txt}   "
                      f"min {min(pairs.values()):.2f}s")

    # ---- 4. ambient sources ---------------------------------------------
    print("\n\n" + "=" * 78)
    print("### 4. AMBIENT MACs — which can support a cross-receiver "
          "estimate ###")
    print("=" * 78)
    if len(tags) == 2:
        a, b = tags
        A = data[a][1]["amb"]
        B = data[b][1]["amb"]
        macs = sorted(set(A) | set(B),
                      key=lambda m: -(A.get(m, {"n": 0})["n"]
                                      + B.get(m, {"n": 0})["n"]))
        print(f"{'mac':<20}{a+' n':>9}{'fit':>7}{'acc':>7}{'rssi':>8}"
              f"{b+' n':>9}{'fit':>7}{'acc':>7}{'rssi':>8}  verdict")
        for m in macs:
            x = A.get(m, {"n": 0, "fit": 0, "acc": 0, "rssi": 0.0})
            y = B.get(m, {"n": 0, "fit": 0, "acc": 0, "rssi": 0.0})
            if x["n"] + y["n"] < 5:
                continue
            rx = x["rssi"] / x["n"] if x["n"] else float("nan")
            ry = y["rssi"] / y["n"] if y["n"] else float("nan")
            if x["acc"] >= 20 and y["acc"] >= 20:
                v = "QUALIFIES for a per-frame cross-receiver estimate"
                if min(x["acc"], y["acc"]) < BEST_WINDOW:
                    v += f"; cannot fill a {BEST_WINDOW}-frame window"
            elif x["acc"] < 20 and y["acc"] < 20:
                v = "no: too few accepted frames on either node"
            else:
                v = (f"no: one receiver accepts too few "
                     f"({x['acc']} vs {y['acc']} at the shipped gate)")
            print(f"{m:<20}{x['n']:>9}{x['fit']:>7}{x['acc']:>7}{rx:>8.2f}"
                  f"{y['n']:>9}{y['fit']:>7}{y['acc']:>7}{ry:>8.2f}  {v}")
        print("\n  'acc' is frames passing the shipped gates "
              f"(inlier >= {SHIPPED_MIN_INLIER}, resid <= {SHIPPED_MAX_RESID})"
              " inside the empty-room window. The inclusion rule is "
              "docs/POSITIVE_CONTROL_0822.md §3.1's: both receivers must "
              "accept >= 20 frames. No ambient source has enough accepted "
              "traffic to serve as a reference for the beacons, and none can "
              f"fill even one {BEST_WINDOW}-frame window.")

    # ---- 5. the receiver term against the device term --------------------
    print("\n\n" + "=" * 78)
    print("### 5. THE RECEIVER TERM AGAINST THE DEVICE TERM, per condition ###")
    print("=" * 78)
    print("docs/SEPARATION_SCALING.md §0's inversion, restated under each "
          "reference condition: the same-beacon d0wd-vs-s3 differences "
          "against the within-receiver beacon-to-beacon differences on the "
          "S3 (the primary node). Reference correction 'works' only if the "
          "left column falls below the right one.")
    if len(tags) == 2:
        a, b = tags
        for label, W, I, R in configs[1:2]:
            C = store[label]
            print(f"\n--- {label} ---")
            for c in CONDITIONS:
                rec = {}
                for m in BEACONS:
                    xa, xb = C[a][c][m][0], C[b][c][m][0]
                    if xa.size and xb.size:
                        rec[BNAME[m]] = abs(np.median(xa) - np.median(xb))
                dev = {}
                med_b = {m: (np.median(C[b][c][m][0])
                             if C[b][c][m][0].size else np.nan)
                         for m in BEACONS}
                for i, x in enumerate(BEACONS):
                    for y in BEACONS[i + 1:]:
                        if np.isfinite(med_b[x]) and np.isfinite(med_b[y]):
                            dev[f"{BNAME[x]}-{BNAME[y]}"] = abs(med_b[x]
                                                                - med_b[y])
                if not rec or not dev:
                    print(f"  {c:<8} (not measurable)")
                    continue
                rmin, rmax = min(rec.values()), max(rec.values())
                dmax = max(dev.values())
                print(f"  {c:<8} receiver term " +
                      " ".join(f"{k} {v:.5f}" for k, v in rec.items()) +
                      f"  |  {b} device term " +
                      " ".join(f"{k} {v:.5f}" for k, v in dev.items()))
                print(f"  {'':<8}   smallest receiver term {rmin:.5f} vs "
                      f"largest device term {dmax:.5f} -> "
                      f"{'INVERTED (receiver still larger)' if rmin > dmax else 'device term now larger for at least one beacon'}"
                      f"; largest receiver term {rmax:.5f}")
            print(f"\n  {b} SFO medians per condition (the rank order of B1 "
                  f"and B2 reverses between receivers under 'none' — "
                  f"docs/SEPARATION_SCALING.md §0):")
            for c in CONDITIONS:
                row_a = "  ".join(
                    f"{BNAME[m]} " + (f"{np.median(C[a][c][m][0]):+.5f}"
                                      if C[a][c][m][0].size else "—")
                    for m in BEACONS)
                row_b = "  ".join(
                    f"{BNAME[m]} " + (f"{np.median(C[b][c][m][0]):+.5f}"
                                      if C[b][c][m][0].size else "—")
                    for m in BEACONS)
                print(f"    {c:<8} {a}: {row_a}   |   {b}: {row_b}")

        print("\n  Degeneracy warning for 'pop': with three sources the "
              "population median IS one of the sources, so on each receiver "
              "exactly one beacon is normalised against itself and reads "
              "identically 0.00000. 'popLOO' (median of the other sources) "
              "is the non-degenerate form.")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan")
    s.add_argument("path")
    s.add_argument("--tag", required=True)
    s.add_argument("--part", type=int, required=True)
    s.add_argument("--nparts", type=int, required=True)
    s.set_defaults(fn=cmd_scan)

    m = sub.add_parser("merge")
    m.add_argument("--tag", required=True)
    m.add_argument("--nparts", type=int, required=True)
    m.add_argument("--expect-rows", type=int, default=None)
    m.set_defaults(fn=cmd_merge)

    r = sub.add_parser("report")
    r.add_argument("--tags", required=True)
    r.set_defaults(fn=cmd_report)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
