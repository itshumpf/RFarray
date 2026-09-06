#!/usr/bin/env python3
r"""B1_MOVED — the first deliberate manipulation on this bench.

Pre-registration: `docs/B1_MOVED.md`, frozen before this script was run.

Beacon B1 (a4:f0:0f:77:91:20) was moved outdoors to a car park ~100 ft away
and three storeys down. B2, B3 and both receivers were not touched. The whole
after-file is one condition. B2 and B3 are the control: if all three beacons'
slope distributions shift, something other than the move changed between the
captures and B1's number carries no information about geometry.

Design constraints this script obeys, and why
---------------------------------------------
* **`pc/rff/dsp.py` is used exactly as shipped and is NOT modified**
  (`docs/V2_SPEC.md` §5.5). `FrameEstimator` is imported and used as-is.
* **Replay from row 1 with a fresh estimator per (node, source-MAC) stream.**
  `FrameEstimator` owns a per-instance RNG (`dsp.py:118`) handed to
  `ransac_line` every frame (`:132`), which draws two `rng.integers(...,
  size=64)` per call (`:85-86`); the generator advances once per fitted frame,
  so a slope depends on how many frames preceded it in that stream. The
  run/resume checkpoint pickles estimator state AND the exact byte offset, so
  an N-call run is frame-for-frame what one uninterrupted pass would produce.
  `verify` re-checks that on a short file rather than asserting it.
* **Screen corrupt rows before the estimator and before any delta arithmetic.**
  The d0wd fabricates MACs from corrupt rows. Six-column field plausibility.
* **`0d:0a` addresses are framing artifacts, not devices.** `0d 0a` is CR/LF:
  the framer lost sync. Screened and counted separately (docs/B1_MOVED.md §3).
* **`csi_data` is a quoted comma-separated list nested in the CSV.** Parsed
  with `csv.reader`, never a naive `line.split(",")`.
* `pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` are
  NOT used (`docs/CODE_INVENTORY.md` §4.2 C1/C2/C3: DC/guard-band index wrong).
* Read-only on `data/raw/`; no serial port opened; nothing staged.
* Receivers are never pooled.

Usage (from the repo root; state goes to $B1M_CACHE, default /tmp/b1moved)
-------------------------------------------------------------------------
  export B1M_CACHE=/tmp/b1moved
  python3 pc/exp_b1_moved.py run data/raw/d0wd_20260823_141358.csv --tag a_d0wd
  ...repeat until it prints DONE...
  python3 pc/exp_b1_moved.py floors  --tags b_d0wd,b_s3,a_d0wd,a_s3,t_d0wd,t_s3
  python3 pc/exp_b1_moved.py report  --before b_d0wd,b_s3 --after a_d0wd,a_s3 \
                                     --tod t_d0wd,t_s3
  python3 pc/exp_b1_moved.py verify data/raw/d0wd_20260823_013537.csv
"""
import argparse
import csv
import os
import pickle
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rff.dsp import FrameEstimator                    # noqa: E402
from occ import BEACON_MACS                           # noqa: E402

CACHE = os.environ.get("B1M_CACHE", "/tmp/b1moved")

# ---------------------------------------------------------------- frozen cfg
# Fixed by docs/B1_MOVED.md. Not to be tuned here.
SIGMA = 0.00237           # BETWEEN_UNIT_SD, pc/exp_thermal_evidence.py:129
W_PRIMARY = 64            # frames per window (~1 s on a beacon)
W_ROBUST = 256            # robustness replicate
MAX_WIN_SPAN_S = 5.0      # windows spanning longer than this are excluded
MIN_INLIER = 0.6          # shipped gate, dsp.py:164
MAX_RESID = 0.8           # shipped gate, dsp.py:164
MIN_ACC_FRAMES = 640      # frame floor, >= 10 windows at W=64
WIN_FLOOR_PRIMARY = 100   # >= this: primary comparison proceeds
WIN_FLOOR_PROV = 30       # 30..99: provisional; < 30: insufficient
BLOCK_S = 3111.3          # after-capture duration: the within-before block size
SHIFT_SIGMA_MIN = 1.0     # |delta| must exceed this AND the block range

# Field-plausibility screen (docs/B1_MOVED.md §3).
CSI_LEN_OK = (128, 256, 384)
NF_LO, NF_HI = -110, -70
RSSI_LO, RSSI_HI = -100, -10

TIME_BUDGET_S = float(os.environ.get("B1M_BUDGET", "150"))

MAC_B1 = "a4:f0:0f:77:91:20"


# ------------------------------------------------------------------ helpers

def _mad(a):
    a = np.asarray(a, dtype=np.float64)
    return float(1.4826 * np.median(np.abs(a - np.median(a))))


def _pct_from_hist(hist, q):
    """Exact percentile from an integer-valued {value: count} histogram."""
    if not hist:
        return float("nan")
    ks = sorted(hist)
    cs = np.cumsum([hist[k] for k in ks])
    tot = cs[-1]
    target = q * tot
    i = int(np.searchsorted(cs, target, side="left"))
    return float(ks[min(i, len(ks) - 1)])


def _octets(mac):
    return mac.split(":")


def has_crlf_pair(mac):
    """True if the MAC text contains an adjacent 0d,0a octet pair (CR/LF).

    Proof the framer lost sync: this is a framing artifact, not a device.
    """
    o = _octets(mac)
    return any(o[i] == "0d" and o[i + 1] == "0a" for i in range(len(o) - 1))


def has_crlf_octet(mac):
    """Weaker: any 0d or 0a octet anywhere. Counted, NOT used to exclude --
    both are legal octets in a real address (docs/B1_MOVED.md §3)."""
    return any(x in ("0d", "0a") for x in _octets(mac))


# -------------------------------------------------------------------- state

class Stream:
    """Per-(node, source-MAC) accumulators. Slopes kept for beacons only."""
    __slots__ = ("est", "buf64", "buf256", "win64", "win256",
                 "n_raw", "n_fed", "n_acc", "n_span_drop",
                 "rssi_hist", "nf_hist", "is_beacon")

    def __init__(self, is_beacon):
        self.is_beacon = is_beacon
        self.est = FrameEstimator() if is_beacon else None
        self.buf64 = []
        self.buf256 = []
        self.win64 = []
        self.win256 = []
        self.n_raw = 0        # rows bearing this MAC that passed the screen
        self.n_fed = 0        # rows fed to the estimator
        self.n_acc = 0        # frames passing both shipped gates
        self.n_span_drop = 0  # windows excluded for spanning > MAX_WIN_SPAN_S
        self.rssi_hist = defaultdict(int)
        self.nf_hist = defaultdict(int)


class State:
    def __init__(self, tag, path):
        self.tag = tag
        self.path = path
        self.offset = 0
        self.rows = 0
        self.bad_field = 0
        self.bad_parse = 0
        self.short_csi = 0
        self.crlf_pair_rows = 0       # rows with an adjacent 0d:0a -> excluded
        self.crlf_pair_macs = {}      # mac -> count (capped)
        self.crlf_octet_rows = 0      # weaker screen, counted only
        self.crlf_octet_macs = {}
        self.node_mode = None
        self.chan_mode = None
        self.streams = {}
        self.ambient = defaultdict(int)   # non-beacon MAC -> screened row count
        self.elapsed = 0.0
        self.done = False
        self.t_first = None
        self.t_last = None

    def stream(self, mac):
        s = self.streams.get(mac)
        if s is None:
            s = Stream(mac in BEACON_MACS)
            self.streams[mac] = s
        return s


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
    lines = raw.decode("utf-8", "replace").split("\n")[:-1][:n]
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

def _emit(buf, out, stream):
    """One window record from W buffered accepted frames.

    Record: (median slope, within-window slope MAD, mean rssi, median resid,
             span_s, ts_mid_us, n)
    """
    slopes = np.fromiter((b[0] for b in buf), float, len(buf))
    rssis = np.fromiter((b[1] for b in buf), float, len(buf))
    resids = np.fromiter((b[2] for b in buf), float, len(buf))
    ts = np.fromiter((b[3] for b in buf), float, len(buf))
    span = (ts.max() - ts.min()) * 1e-6
    if span > MAX_WIN_SPAN_S:
        stream.n_span_drop += 1
        return
    out.append((float(np.median(slopes)), _mad(slopes), float(rssis.mean()),
                float(np.median(resids)), float(span), float(np.median(ts)),
                len(buf)))


# ------------------------------------------------------------------- the run

def do_run(args):
    tag, path = args.tag, args.file
    if os.path.exists(_spath(tag)) and not args.restart:
        st = load(tag)
        if st.path != os.path.abspath(path):
            raise SystemExit(f"checkpoint {tag} is for {st.path}")
        if st.done:
            print(f"[{tag}] already DONE rows={st.rows}")
            return
    else:
        st = State(tag, os.path.abspath(path))
        nm, cm, nh, ch = prescan(path)
        st.node_mode, st.chan_mode = nm, cm
        print(f"[{tag}] prescan node_id mode={nm} {nh} channel mode={cm} {ch}")

    size = os.path.getsize(path)
    t0 = time.time()
    with open(path, "rb") as f:            # read-only, never written
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
            _process(st, block.decode("utf-8", "replace").splitlines())
            if time.time() - t0 > TIME_BUDGET_S:
                break
        if st.done and pending.strip():
            st.offset += len(pending)
            _process(st, pending.decode("utf-8", "replace").splitlines())

    st.elapsed += time.time() - t0
    save(st)
    pct = 100.0 * st.offset / size
    print(f"[{tag}] {'DONE' if st.done else 'PART'} offset={st.offset}/{size} "
          f"({pct:.2f}%) rows={st.rows} bad_field={st.bad_field} "
          f"bad_parse={st.bad_parse} short_csi={st.short_csi} "
          f"crlf_pair={st.crlf_pair_rows} streams={len(st.streams)} "
          f"cpu={st.elapsed:.0f}s")


def _process(st, lines):
    node_mode, chan_mode = st.node_mode, st.chan_mode
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

        # --- framing-artifact screen: 0d 0a is CR/LF, not a device ---------
        if has_crlf_octet(mac):
            st.crlf_octet_rows += 1
            if len(st.crlf_octet_macs) < 4000 or mac in st.crlf_octet_macs:
                st.crlf_octet_macs[mac] = st.crlf_octet_macs.get(mac, 0) + 1
        if has_crlf_pair(mac):
            st.crlf_pair_rows += 1
            if len(st.crlf_pair_macs) < 4000 or mac in st.crlf_pair_macs:
                st.crlf_pair_macs[mac] = st.crlf_pair_macs.get(mac, 0) + 1
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

        if mac not in BEACON_MACS:
            st.ambient[mac] += 1
            continue

        s = st.stream(mac)
        s.n_raw += 1
        s.rssi_hist[rssi] += 1
        s.nf_hist[nf] += 1

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
        est = s.est.feed(iq, ts_us)          # dsp.py, unmodified
        if est is None:
            continue
        if est["inlier_ratio"] < MIN_INLIER or est["resid_std"] > MAX_RESID:
            continue
        s.n_acc += 1

        rec = (est["slope"], rssi, est["resid_std"], pc_us)
        s.buf64.append(rec)
        if len(s.buf64) >= W_PRIMARY:
            _emit(s.buf64, s.win64, s)
            s.buf64 = []
        s.buf256.append(rec)
        if len(s.buf256) >= W_ROBUST:
            _emit(s.buf256, s.win256, s)
            s.buf256 = []


# ------------------------------------------------------------------- report

def _wins(st, mac, robust=False):
    s = st.streams.get(mac)
    if s is None:
        return np.zeros((0, 7))
    w = s.win256 if robust else s.win64
    return np.array(w, dtype=np.float64) if w else np.zeros((0, 7))


def _dur(st):
    if st.t_first is None or st.t_last is None:
        return float("nan")
    return (st.t_last - st.t_first) * 1e-6


def _floor_status(n_win, n_acc):
    if n_acc < MIN_ACC_FRAMES or n_win < WIN_FLOOR_PROV:
        return "INSUFFICIENT"
    if n_win < WIN_FLOOR_PRIMARY:
        return "provisional"
    return "ok"


def do_floors(args):
    tags = args.tags.split(",")
    print("\n=== ITEM 1: FRAME AND WINDOW FLOORS "
          "(reported before any slope) ===")
    hdr = (f"{'tag':>8} {'beacon':>7} {'raw':>10} {'acc':>10} {'acc/raw':>8} "
           f"{'raw fps':>8} {'acc fps':>8} {'rssi p50':>9} {'rssi p10':>9} "
           f"{'nf p50':>7} {'win64':>7} {'span_drop':>9} {'status':>13}")
    print(hdr)
    for tag in tags:
        st = load(tag)
        dur = _dur(st)
        for mac, name in sorted(BEACON_MACS.items(), key=lambda kv: kv[1]):
            s = st.streams.get(mac)
            if s is None:
                print(f"{tag:>8} {name:>7} {'0':>10} {'0':>10} "
                      f"{'-':>8} {'0.00':>8} {'0.00':>8} {'-':>9} {'-':>9} "
                      f"{'-':>7} {'0':>7} {'0':>9} {'ABSENT':>13}")
                continue
            nw = len(s.win64)
            print(f"{tag:>8} {name:>7} {s.n_raw:>10d} {s.n_acc:>10d} "
                  f"{(s.n_acc / s.n_raw if s.n_raw else 0):>8.3f} "
                  f"{s.n_raw / dur:>8.2f} {s.n_acc / dur:>8.2f} "
                  f"{_pct_from_hist(s.rssi_hist, 0.50):>9.0f} "
                  f"{_pct_from_hist(s.rssi_hist, 0.10):>9.0f} "
                  f"{_pct_from_hist(s.nf_hist, 0.50):>7.0f} "
                  f"{nw:>7d} {s.n_span_drop:>9d} "
                  f"{_floor_status(nw, s.n_acc):>13}")
    print("\n=== ITEM 3: 0d:0a FRAMING-ARTIFACT SCREEN ===")
    print(f"{'tag':>8} {'rows':>12} {'crlf_pair':>10} {'crlf_octet':>11} "
          f"{'bad_field':>10} {'bad_parse':>10} {'short_csi':>10} "
          f"{'ambient MACs':>13}")
    for tag in tags:
        st = load(tag)
        print(f"{tag:>8} {st.rows:>12d} {st.crlf_pair_rows:>10d} "
              f"{st.crlf_octet_rows:>11d} {st.bad_field:>10d} "
              f"{st.bad_parse:>10d} {st.short_csi:>10d} {len(st.ambient):>13d}")
        for m, c in sorted(st.crlf_pair_macs.items(),
                           key=lambda kv: -kv[1])[:8]:
            print(f"{'':>8}   pair  {m}  x{c}")
        for m, c in sorted(st.crlf_octet_macs.items(),
                           key=lambda kv: -kv[1])[:8]:
            print(f"{'':>8}   octet {m}  x{c}")


def _blocks(st, mac):
    """Within-before null band: median window-slope per BLOCK_S block."""
    w = _wins(st, mac)
    if not len(w):
        return []
    t0 = w[:, 5].min()
    idx = ((w[:, 5] - t0) * 1e-6 / BLOCK_S).astype(int)
    out = []
    for b in range(idx.max() + 1):
        sel = w[idx == b, 0]
        if sel.size >= WIN_FLOOR_PROV:
            out.append((b, float(np.median(sel)), sel.size))
    return out


def _summ(w):
    if not len(w):
        return None
    return {
        "n": len(w),
        "med": float(np.median(w[:, 0])),
        "between_mad": _mad(w[:, 0]),
        "within_mad": float(np.median(w[:, 1])),
        "rssi": float(np.median(w[:, 2])),
        "resid": float(np.median(w[:, 3])),
    }


def do_report(args):
    before = args.before.split(",")
    after = args.after.split(",")
    tod = args.tod.split(",") if args.tod else []
    rxs = args.rx.split(",")
    W = "W=256" if args.robust else "W=64"
    print(f"\n################ REPORT  ({W}, sigma={SIGMA} rad/sc) ############")

    for i, rx in enumerate(rxs):
        bst, ast = load(before[i]), load(after[i])
        tst = load(tod[i]) if tod else None
        print(f"\n=============== RECEIVER {rx}  "
              f"(before={before[i]} after={after[i]}"
              f"{' tod=' + tod[i] if tod else ''}) ===============")
        print("--- within-before block medians (null band, "
              f"{BLOCK_S:.0f} s blocks = the after-capture duration) ---")
        band = {}
        for mac, name in sorted(BEACON_MACS.items(), key=lambda kv: kv[1]):
            bl = _blocks(bst, mac)
            if not bl:
                print(f"  {name}: no qualifying block")
                band[name] = float("nan")
                continue
            meds = np.array([b[1] for b in bl])
            rng = float(meds.max() - meds.min())
            band[name] = rng
            print(f"  {name}: {len(bl)} blocks  medians "
                  + " ".join(f"{m:+.6f}" for m in meds)
                  + f"   range={rng:.6f} = {rng / SIGMA:.2f} sigma")

        print("\n--- slope distributions and shift ---")
        print(f"{'beacon':>7} {'cond':>8} {'n_win':>7} {'median slope':>13} "
              f"{'betw MAD':>10} {'with MAD':>10} {'rssi':>6} "
              f"{'resid':>6} {'status':>13}")
        rows = {}
        for mac, name in sorted(BEACON_MACS.items(), key=lambda kv: kv[1]):
            for label, st in (("before", bst), ("after", ast),
                              ("tod", tst) if tst else (None, None)):
                if label is None:
                    continue
                w = _wins(st, mac, args.robust)
                s = _summ(w)
                sm = st.streams.get(mac)
                acc = sm.n_acc if sm else 0
                if s is None:
                    print(f"{name:>7} {label:>8} {0:>7} "
                          f"{'-':>13} {'-':>10} {'-':>10} {'-':>6} {'-':>6} "
                          f"{'ABSENT':>13}")
                    continue
                rows[(name, label)] = s
                print(f"{name:>7} {label:>8} {s['n']:>7} {s['med']:>+13.6f} "
                      f"{s['between_mad']:>10.6f} {s['within_mad']:>10.6f} "
                      f"{s['rssi']:>6.1f} {s['resid']:>6.3f} "
                      f"{_floor_status(s['n'], acc):>13}")

        print("\n--- DELTAS in BETWEEN_UNIT_SD (sigma = 0.00237 rad/sc) ---")
        print(f"{'beacon':>7} {'comparison':>16} {'delta rad/sc':>13} "
              f"{'x sigma':>9} {'null band':>10} {'exceeds?':>9} "
              f"{'disp ratio (betw/with)':>24}")
        for mac, name in sorted(BEACON_MACS.items(), key=lambda kv: kv[1]):
            b = rows.get((name, "before"))
            for label in ("after", "tod"):
                a = rows.get((name, label))
                if b is None or a is None:
                    continue
                d = a["med"] - b["med"]
                nb = band.get(name, float("nan"))
                exceeds = (abs(d) / SIGMA >= SHIFT_SIGMA_MIN
                           and abs(d) > nb)
                dr_b = a["between_mad"] / b["between_mad"] if b["between_mad"] else float("nan")
                dr_w = a["within_mad"] / b["within_mad"] if b["within_mad"] else float("nan")
                print(f"{name:>7} {'before->' + label:>16} {d:>+13.6f} "
                      f"{d / SIGMA:>+9.2f} {nb / SIGMA:>10.2f} "
                      f"{('YES' if exceeds else 'no'):>9} "
                      f"{dr_b:>11.2f}x {dr_w:>11.2f}x")

        # time-adjacent before: last BLOCK_S of the before file
        print("\n--- time-adjacent before (last "
              f"{BLOCK_S:.0f} s of the before file) ---")
        for mac, name in sorted(BEACON_MACS.items(), key=lambda kv: kv[1]):
            w = _wins(bst, mac, args.robust)
            a = rows.get((name, "after"))
            if not len(w) or a is None:
                continue
            tmax = w[:, 5].max()
            sel = w[w[:, 5] >= tmax - BLOCK_S * 1e6]
            if len(sel) < WIN_FLOOR_PROV:
                print(f"  {name}: only {len(sel)} windows, below floor")
                continue
            m = float(np.median(sel[:, 0]))
            d = a["med"] - m
            print(f"  {name}: n={len(sel)} median={m:+.6f} "
                  f"delta_to_after={d:+.6f} = {d / SIGMA:+.2f} sigma")


# ------------------------------------------------------------------- verify

def do_verify(args):
    """Prove the checkpoint split is transparent: one pass vs N resumed parts."""
    path = args.file
    global TIME_BUDGET_S
    keep = TIME_BUDGET_S
    TIME_BUDGET_S = 1e9
    ns = argparse.Namespace(tag="_v_whole", file=path, restart=True)
    do_run(ns)
    TIME_BUDGET_S = args.split_budget
    ns = argparse.Namespace(tag="_v_split", file=path, restart=True)
    do_run(ns)
    parts = 1
    while not load("_v_split").done:
        do_run(argparse.Namespace(tag="_v_split", file=path, restart=False))
        parts += 1
    TIME_BUDGET_S = keep
    a, b = load("_v_whole"), load("_v_split")
    bad = 0
    macs = set(a.streams) | set(b.streams)
    for m in macs:
        wa = _wins(a, m), _wins(a, m, True)
        wb = _wins(b, m), _wins(b, m, True)
        for x, y in zip(wa, wb):
            if x.shape != y.shape or not np.array_equal(x, y):
                bad += 1
                print(f"  MISMATCH {m} {x.shape} vs {y.shape}")
    print(f"[verify] parts={parts} rows {a.rows} vs {b.rows} "
          f"streams {len(a.streams)} vs {len(b.streams)} "
          f"differing-window-sets={bad}")
    print("[verify] " + ("PASS" if bad == 0 and a.rows == b.rows else "FAIL"))


# --------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("file")
    r.add_argument("--tag", required=True)
    r.add_argument("--restart", action="store_true")
    r.set_defaults(func=do_run)

    f = sub.add_parser("floors")
    f.add_argument("--tags", required=True)
    f.set_defaults(func=do_floors)

    o = sub.add_parser("report")
    o.add_argument("--before", required=True)
    o.add_argument("--after", required=True)
    o.add_argument("--tod", default="")
    o.add_argument("--rx", default="d0wd,s3")
    o.add_argument("--robust", action="store_true")
    o.set_defaults(func=do_report)

    v = sub.add_parser("verify")
    v.add_argument("file")
    v.add_argument("--split-budget", type=float, default=1.5)
    v.set_defaults(func=do_verify)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
