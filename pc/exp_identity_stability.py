#!/usr/bin/env python3
"""Does a device's SFO signature survive across sessions on a FIXED receiver?

Pre-registered design, thresholds and caveats: docs/IDENTITY_STABILITY.md
(Stage 1 written and saved before this file was run).

Read-only on data/raw/. Opens no serial port. Modifies nothing in pc/rff/.
All state goes to $IDST_CACHE (default /tmp/idst), outside the repo tree.

  extract <csv> [--cap N]   replay one file from byte one with a fresh
                            estimator per (file, mac); checkpoint to cache
  score                     all receivers, all ordered session pairs
  report                    print the scored result

Everything the DSP does is pc/rff/dsp.py as shipped: FrameEstimator +
WindowAggregator at window 64, min_inlier 0.6, max_resid 0.8. The
classifier is pc/rff/discriminator.py as shipped. pc/capture.py's
compute_cfo, pc/phase_skew.py and pc/fingerprint.py are not used
(docs/CODE_INVENTORY.md 4.2 C1/C2/C3).
"""
import argparse
import csv as csvmod
import itertools
import json
import math
import os
import pickle
import random
import sys
from collections import defaultdict, deque

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rff.dsp import FrameEstimator, WindowAggregator          # noqa: E402
from rff.discriminator import Discriminator                    # noqa: E402
from rff.reference import ReferenceNormalizer                  # noqa: E402

csvmod.field_size_limit(10 ** 7)

CACHE = os.environ.get("IDST_CACHE", "/tmp/idst")
REF_MAC = "a4:f0:0f:77:91:20"
BEACONS = {"a4:f0:0f:77:91:20", "f4:2d:c9:70:72:30", "28:05:a5:2f:fa:48"}
WATCH = "84:7b:57:cc:20:0e"          # CLAUDE.md's largest single error mode

WINDOW = 64                          # dsp.py shipped default
TRAIN_FRACTION = 0.6                 # rff_offline.TRAIN_FRACTION
MIN_WIN = 10                         # per (session, device), pre-registered
BETWEEN_UNIT_SD = 0.00237            # LOT_HYPOTHESIS 5; COLOCATED_0823 5
DEFAULT_CAP = 300000

# ---------------------------------------------------------------- receivers
# Pre-registered blocks. Era A identity is a filename prefix typed at
# capture.py's command line and is a LABEL, not a measurement
# (docs/NODE_CENSUS.md 1, I3). node_id is a compiled-in firmware constant
# and identifies a build, not a board (NODE_CENSUS I2).
# COLOCATED_0823.md 0: both receivers were remounted onto the same wall on
# 2026-08-22. The remount is NOT at midnight — DISPLAY_LIVE_0822.md 5.1 uses
# the 08-22 23:57 capture as the pre-co-location baseline and COLOCATED_0823
# 5.2 compares it against the 08-23 file. So the boundary sits between
# *_20260822_235739 and *_20260823_013537, and is expressed as a session
# key rather than a date.
REMOUNT_KEY = "20260823_013537"
REMOUNT = "between *_20260822_235739 and *_20260823_013537"

BLOCKS = {
    "R1_desk_eraA": dict(
        note="era A, filename prefix only, no node_id in data",
        files=["desk_20260712_124142", "desk_20260712_140038",
               "desk_20260713_112617", "desk_20260713_131746",
               "desk_20260713_133556", "desk_20260713_145302",
               "desk_20260713_160253", "desk_20260713_172009",
               "desk_20260713_194922"]),
    "R2_node3_eraA": dict(
        note="era A, promiscuous era only (NODE_CENSUS P5)",
        files=["node3_20260713_131746", "node3_20260713_133556",
               "node3_20260713_145302", "node3_20260713_160253",
               "node3_20260713_172009", "node3_20260713_194922"]),
    "R3_node68_july": dict(
        note="node_id 68, era B/C, rx_* only (occ_* excluded)",
        files=["rx_20260714_011619", "rx_20260714_030915",
               "rx_20260714_031131", "rx_20260715_201703",
               "rx_20260722_204658", "rx_20260722_XXXXXX"]),
    "R4_node68_august": dict(
        note="node_id 68, August; spans the 08-22 remount",
        files=["desk_20260821_125017", "d0wd_20260822_023034",
               "d0wd_20260822_144424", "d0wd_20260822_235739",
               "d0wd_20260823_013537", "d0wd_20260823_014740"]),
    "R5_node108_august": dict(
        note="node_id 108, August; spans the 08-22 remount",
        files=["s3_20260821_125017", "s3_20260822_023034",
               "s3_20260822_144424", "s3_20260822_235739",
               "s3_20260823_013537", "s3_20260823_014740"]),
}


def session_date(stem):
    """YYYY-MM-DD from a data/raw stem, or None."""
    for part in stem.split("_"):
        if len(part) == 8 and part.isdigit():
            return f"{part[:4]}-{part[4:6]}-{part[6:]}"
    return None


def session_key(stem):
    """YYYYMMDD_HHMMSS token, or '' — sorts chronologically as a string."""
    parts = stem.split("_")
    for i, p in enumerate(parts):
        if len(p) == 8 and p.isdigit() and i + 1 < len(parts):
            return p + "_" + parts[i + 1]
    return ""


def straddles_remount(a, b):
    ka, kb = session_key(a), session_key(b)
    if not ka or not kb:
        return True
    # Only August sessions can straddle it at all.
    if max(ka, kb) < "20260800_000000":
        return False
    return (ka < REMOUNT_KEY) != (kb < REMOUNT_KEY)


# ------------------------------------------------------------------ extract
def circdiff(a, b):
    d = (a - b) % 65536
    return d - 65536 if d > 32768 else d


class Screen:
    """Corrupt-row screen, both routes docs/COLOCATED_0823.md 1 requires.

    Route 1: field plausibility on the columns that exist.
    Route 2: width-9 median filter on `dropped`, tolerance 100, compared
             CIRCULARLY mod 65536 so genuine u16 wraps are not flagged.

    Era A files are 10-column and carry no `dropped`, `node_id` or `env_id`
    column at all, so route 2 DOES NOT EXIST for them. That is a missing
    column, not an unrun check, and it is recorded as such in the manifest.
    """

    def __init__(self, wide, node_mode, chan_mode, tol=100, width=9):
        self.wide = wide
        self.node_mode = node_mode
        self.chan_mode = chan_mode
        self.tol = tol
        self.width = width
        self.half = width // 2
        self.buf = deque()
        self.n_field = 0
        self.n_median = 0

    def field_ok(self, rec):
        if rec["chan"] != self.chan_mode:
            return False
        if rec["clen"] not in (128, 256, 384):
            return False
        if not (-110 <= rec["nf"] <= -70):
            return False
        if not (-100 <= rec["rssi"] <= -10):
            return False
        if self.wide:
            if rec["node"] != self.node_mode or rec["env"] != 0:
                return False
        return True

    def push(self, rec):
        """Feed one field-screen survivor; yield rows cleared by both."""
        if not self.wide:
            yield rec
            return
        self.buf.append(rec)
        if len(self.buf) < self.width:
            return
        c = self.buf[self.half]
        offs = sorted(circdiff(r["dropped"], c["dropped"]) for r in self.buf)
        med = offs[len(offs) // 2]
        if abs(med) > self.tol:
            self.n_median += 1
        else:
            yield c
        self.buf.popleft()

    def drain(self):
        """Tail rows that never became a window centre pass on field screen."""
        if not self.wide:
            return
        while self.buf:
            yield self.buf.popleft()


def prescan(path, n=20000):
    """Modal node_id and channel from the head of the file (COLOCATED 1)."""
    node, chan, wide = defaultdict(int), defaultdict(int), False
    with open(path, newline="") as f:
        r = csvmod.reader(f)
        hdr = next(r)
        wide = len(hdr) >= 13
        for i, row in enumerate(r):
            if i >= n:
                break
            if len(row) != len(hdr):
                continue
            try:
                chan[int(row[6])] += 1
                if wide:
                    node[int(row[10])] += 1
            except ValueError:
                continue
    cm = max(chan, key=chan.get) if chan else 6
    nm = max(node, key=node.get) if node else None
    return wide, nm, cm


def extract(path, cap):
    stem = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(CACHE, stem + ".pkl")
    if os.path.exists(out):
        return out, True

    wide, node_mode, chan_mode = prescan(path)
    scr = Screen(wide, node_mode, chan_mode)
    ests = {}
    aggs = {}
    ref = ReferenceNormalizer(REF_MAC)
    wins = defaultdict(list)
    frames = defaultdict(int)
    rssi_sum = defaultdict(float)
    nf_hist = defaultdict(lambda: defaultdict(int))
    len256 = defaultdict(int)
    rows = 0
    unparse = 0
    t0 = None
    tlast = None

    def handle(rec):
        nonlocal t0, tlast
        mac = rec["mac"]
        if t0 is None:
            t0 = rec["pc"]
        tlast = rec["pc"]
        frames[mac] += 1
        rssi_sum[mac] += rec["rssi"]
        nf_hist[mac][rec["nf"]] += 1
        if rec["clen"] == 256:
            len256[mac] += 1
        e = ests.get(mac)
        if e is None:
            e = ests[mac] = FrameEstimator()
            aggs[mac] = WindowAggregator(window=WINDOW)
        est = e.feed(rec["vals"], rec["esp"])
        obs = aggs[mac].feed(est, rec["esp"], rec["rssi"])
        if obs is None:
            return
        obs, _ = ref.feed(mac, obs)
        wins[mac].append((rec["pc"], obs.get("cfo"), obs.get("sfo"),
                          obs.get("cfo_ref"), obs.get("sfo_ref"),
                          obs.get("rssi"), obs.get("quality")))

    with open(path, newline="") as f:
        r = csvmod.reader(f)
        hdr = next(r)
        ncol = len(hdr)
        for row in r:
            rows += 1
            if rows > cap:
                rows -= 1
                break
            if len(row) != ncol:
                unparse += 1
                continue
            try:
                rec = {
                    "pc": int(row[0]), "mac": row[3].lower(),
                    "rssi": int(row[4]), "nf": int(row[5]),
                    "chan": int(row[6]), "esp": int(row[7]),
                    "clen": int(row[8]),
                }
                if wide:
                    rec["node"] = int(row[10])
                    rec["env"] = int(row[11])
                    rec["dropped"] = int(row[12])
            except (ValueError, IndexError):
                unparse += 1
                continue
            if not scr.field_ok(rec):
                scr.n_field += 1
                continue
            rec["vals"] = np.fromstring(row[9], dtype=np.float64, sep=",")
            for ok in scr.push(rec):
                handle(ok)
        for ok in scr.drain():
            handle(ok)

    meta = dict(stem=stem, wide=wide, node_mode=node_mode,
                chan_mode=chan_mode, rows=rows, unparseable=unparse,
                n_field_screened=scr.n_field, n_median_screened=scr.n_median,
                median_filter_available=wide, cap=cap, t0=t0, tlast=tlast,
                frames=dict(frames),
                mean_rssi={m: rssi_sum[m] / frames[m] for m in frames},
                modal_nf={m: max(h, key=h.get) for m, h in nf_hist.items()},
                len256_frac={m: len256[m] / frames[m] for m in frames})
    os.makedirs(CACHE, exist_ok=True)
    with open(out, "wb") as fh:
        pickle.dump(dict(meta=meta, wins={m: v for m, v in wins.items()}), fh)
    return out, False


# -------------------------------------------------------------------- score
def feats(wins, space):
    """[(ts, np.array([cfo, sfo]))] in the requested space.

    Strict: BOTH components must exist. rff_offline.feature() falls back to
    raw CFO when only sfo_ref is present; that mixes spaces inside one model,
    so it is not done here (same choice docs/THERMAL_EVIDENCE.md 2.5 made,
    and the reason its numbers differ from LOT_HYPOTHESIS 5 in the 4th dp).
    """
    i = (1, 2) if space == "raw" else (3, 4)
    out = []
    for w in wins:
        a, b = w[i[0]], w[i[1]]
        if a is None or b is None:
            continue
        out.append((w[0], np.array([a, b], dtype=np.float64)))
    return out


def evaluate(enroll, test):
    """enroll/test: {mac: [feat]}. Returns gated + nearest-centroid stats."""
    disc = Discriminator()
    for mac, fs in enroll.items():
        for f in fs:
            disc.learn(mac, f)
    ids = [s for s, m in disc.models.items()
           if m.n >= Discriminator.MIN_CHARACTERIZED]
    res = dict(n_classes=len(ids), classes=sorted(ids),
               gated=defaultdict(int), nn=defaultdict(int),
               conf_gated=defaultdict(lambda: defaultdict(int)),
               conf_nn=defaultdict(lambda: defaultdict(int)),
               per=defaultdict(lambda: dict(n=0, tp_g=0, tp_n=0,
                                            stranger=0)))
    tot_g = cor_g = tot_n = cor_n = strangers = 0
    for mac, fs in test.items():
        for f in fs:
            best, d2, verdict = disc.classify(f)
            if verdict == "UNSCORED":
                continue
            res["per"][mac]["n"] += 1
            tot_g += 1
            tot_n += 1
            if verdict == "STRANGER":
                strangers += 1
                res["per"][mac]["stranger"] += 1
                res["conf_gated"][mac]["<stranger>"] += 1
            else:
                res["conf_gated"][mac][best] += 1
                if best == mac:
                    cor_g += 1
                    res["per"][mac]["tp_g"] += 1
            res["conf_nn"][mac][best] += 1
            if best == mac:
                cor_n += 1
                res["per"][mac]["tp_n"] += 1
    res["A_gated"] = cor_g / tot_g if tot_g else None
    res["A_nn"] = cor_n / tot_n if tot_n else None
    res["n_test"] = tot_g
    res["strangers"] = strangers
    return res


def prec_recall(res, mac):
    """(recall, precision, n_true, n_attributed) under the shipped gate."""
    p = res["per"].get(mac)
    if not p or p["n"] == 0:
        return None
    recall = p["tp_g"] / p["n"]
    attributed = sum(res["conf_gated"][t].get(mac, 0)
                     for t in res["conf_gated"])
    prec = p["tp_g"] / attributed if attributed else None
    fp = attributed - p["tp_g"]
    other = sum(res["per"][t]["n"] for t in res["per"] if t != mac)
    fpr = fp / other if other else None
    return dict(recall=recall, precision=prec, n_true=p["n"],
                n_attributed=attributed, fp=fp, fpr=fpr, n_other=other)


def spearman(x, y, n_perm=20000, seed=0):
    n = len(x)
    if n < 3:
        return None, None, n

    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(x), rank(y)

    def pearson(a, b):
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        da = [v - ma for v in a]
        db = [v - mb for v in b]
        na = math.sqrt(sum(v * v for v in da))
        nb = math.sqrt(sum(v * v for v in db))
        if na == 0 or nb == 0:
            return 0.0
        return sum(p * q for p, q in zip(da, db)) / (na * nb)

    rho = pearson(rx, ry)
    rnd = random.Random(seed)
    hit = 0
    perm = list(ry)
    for _ in range(n_perm):
        rnd.shuffle(perm)
        if abs(pearson(rx, perm)) >= abs(rho) - 1e-12:
            hit += 1
    return rho, (hit + 1) / (n_perm + 1), n


def score(caps):
    data = {}
    for stem in itertools.chain.from_iterable(b["files"]
                                              for b in BLOCKS.values()):
        p = os.path.join(CACHE, stem + ".pkl")
        if os.path.exists(p):
            with open(p, "rb") as fh:
                data[stem] = pickle.load(fh)
    out = dict(blocks={}, manifest={s: d["meta"] for s, d in data.items()})

    for bname, bdef in BLOCKS.items():
        stems = [s for s in bdef["files"] if s in data]
        if len(stems) < 2:
            out["blocks"][bname] = dict(note=bdef["note"], sessions=stems,
                                        pairs=[], skipped="fewer than 2 "
                                        "sessions extracted")
            continue
        stems.sort(key=lambda s: data[s]["meta"]["t0"] or 0)
        # floor accounting: how many sessions each device clears MIN_WIN in
        floor = defaultdict(int)
        seen_any = defaultdict(int)
        for s in stems:
            for m, v in data[s]["wins"].items():
                seen_any[m] += 1
                if len(feats(v, "raw")) >= MIN_WIN:
                    floor[m] += 1
        pairs = []
        for A, B in itertools.permutations(stems, 2):
            wA, wB = data[A]["wins"], data[B]["wins"]
            rec = dict(A=A, B=B,
                       elapsed_s=abs((data[B]["meta"]["t0"] or 0)
                                     - (data[A]["meta"]["t0"] or 0)) / 1e6,
                       straddles_remount=straddles_remount(A, B),
                       spaces={})
            for space in ("raw", "ref"):
                fA = {m: feats(v, space) for m, v in wA.items()}
                fB = {m: feats(v, space) for m, v in wB.items()}
                cls = sorted(m for m in fA
                             if len(fA[m]) >= MIN_WIN
                             and len(fB.get(m, [])) >= MIN_WIN)
                if len(cls) < 2:
                    rec["spaces"][space] = dict(n_classes=len(cls),
                                                skipped="<2 shared classes")
                    continue
                enr_within, enr_cross, test = {}, {}, {}
                for m in cls:
                    b = [f for _, f in fB[m]]
                    cut = max(int(len(b) * TRAIN_FRACTION), 1)
                    enr_within[m] = b[:cut]
                    test[m] = b[cut:]
                    enr_cross[m] = [f for _, f in fA[m]]
                if not any(test.values()):
                    rec["spaces"][space] = dict(n_classes=len(cls),
                                                skipped="empty test set")
                    continue
                within = evaluate(enr_within, test)
                cross = evaluate(enr_cross, test)

                # --- drift decomposition, on the SFO component (index 1)
                delta = {}
                for m in cls:
                    a = float(np.median([f[1] for _, f in fA[m]]))
                    bb = float(np.median([f[1] for _, f in fB[m]]))
                    delta[m] = bb - a
                d = np.array([delta[m] for m in cls])
                cm = float(np.median(d))
                resid = d - cm
                total_rms = float(np.sqrt(np.mean(d ** 2)))
                res_rms = float(np.sqrt(np.mean(resid ** 2)))
                # Fraction of the TOTAL drift energy removed by subtracting
                # one shared constant. NOT 1 - Var(resid)/Var(delta): Var is
                # taken about the mean, so subtracting a constant leaves it
                # unchanged and that expression is identically 0. The
                # meaningful quantity is about ZERO, i.e. mean-square.
                ms_t = float(np.mean(d ** 2))
                ms_r = float(np.mean(resid ** 2))
                ve = (1 - ms_r / ms_t) if ms_t > 0 else None

                sub = {}
                for tag, sel in (("beacon", lambda m: m in BEACONS),
                                 ("ambient", lambda m: m not in BEACONS)):
                    sc = [m for m in cls if sel(m)]
                    if len(sc) < 2:
                        sub[tag] = dict(n_classes=len(sc),
                                        skipped="<2 classes")
                        continue
                    w2 = evaluate({m: enr_within[m] for m in sc},
                                  {m: test[m] for m in sc})
                    c2 = evaluate({m: enr_cross[m] for m in sc},
                                  {m: test[m] for m in sc})
                    sub[tag] = dict(n_classes=len(sc),
                                    within_gated=w2["A_gated"],
                                    within_nn=w2["A_nn"],
                                    cross_gated=c2["A_gated"],
                                    cross_nn=c2["A_nn"],
                                    n_test=c2["n_test"])

                rec["spaces"][space] = dict(
                    n_classes=len(cls), classes=cls, n_test=cross["n_test"],
                    within_gated=within["A_gated"], within_nn=within["A_nn"],
                    cross_gated=cross["A_gated"], cross_nn=cross["A_nn"],
                    within_strangers=within["strangers"],
                    cross_strangers=cross["strangers"],
                    ref_within=prec_recall(within, REF_MAC),
                    ref_cross=prec_recall(cross, REF_MAC),
                    conf_cross={t: dict(v) for t, v
                                in cross["conf_gated"].items()},
                    conf_cross_nn={t: dict(v) for t, v
                                   in cross["conf_nn"].items()},
                    per_cross={m: dict(prec_recall(cross, m) or {})
                               for m in cls},
                    drift=dict(delta=delta, common_mode=cm,
                               total_rms=total_rms, residual_rms=res_rms,
                               var_explained=ve, n_devices=len(cls)),
                    breakdown=sub)
            pairs.append(rec)
        out["blocks"][bname] = dict(
            note=bdef["note"], sessions=stems, pairs=pairs,
            floor=dict(n_sessions=len(stems),
                       seen_any=dict(seen_any), clears=dict(floor),
                       clears_2plus=sorted(m for m, c in floor.items()
                                           if c >= 2)))

    # ---- drift vs elapsed time, per block, unordered + ordered
    for bname, blk in out["blocks"].items():
        stats = {}
        for space in ("raw", "ref"):
            rows_o, seen = [], {}
            for p in blk.get("pairs", []):
                s = p["spaces"].get(space, {})
                if s.get("skipped") or s.get("within_gated") is None:
                    continue
                if p["straddles_remount"]:
                    continue
                gap = s["within_gated"] - s["cross_gated"]
                gapn = s["within_nn"] - s["cross_nn"]
                rows_o.append((p["elapsed_s"], gap, gapn))
                key = tuple(sorted((p["A"], p["B"])))
                seen.setdefault(key, []).append((p["elapsed_s"], gap, gapn))
            rows_u = [(v[0][0], sum(x[1] for x in v) / len(v),
                       sum(x[2] for x in v) / len(v))
                      for v in seen.values()]
            st = {}
            for tag, rr in (("unordered", rows_u), ("ordered", rows_o)):
                if len(rr) >= 3:
                    rho, p_, n_ = spearman([r[0] for r in rr],
                                           [r[1] for r in rr])
                    rhon, pn, _ = spearman([r[0] for r in rr],
                                           [r[2] for r in rr])
                    st[tag] = dict(n=n_, rho_gated=rho, p_gated=p_,
                                   rho_nn=rhon, p_nn=pn)
                else:
                    st[tag] = dict(n=len(rr), rho_gated=None, p_gated=None)
            # common-mode vs elapsed / time-of-day
            cmrows = []
            for p in blk.get("pairs", []):
                s = p["spaces"].get(space, {})
                if s.get("skipped") or "drift" not in s:
                    continue
                if p["straddles_remount"]:
                    continue
                t0B = out["manifest"][p["B"]]["t0"]
                tod = ((t0B / 1e6) - 5 * 3600) % 86400 / 3600.0
                cmrows.append((p["elapsed_s"], abs(s["drift"]["common_mode"]),
                               tod, s["drift"]["residual_rms"]))
            if len(cmrows) >= 3:
                st["cm_vs_elapsed"] = dict(zip(
                    ("rho", "p", "n"),
                    spearman([r[0] for r in cmrows],
                             [r[1] for r in cmrows])))
                st["cm_vs_tod"] = dict(zip(
                    ("rho", "p", "n"),
                    spearman([r[2] for r in cmrows],
                             [r[1] for r in cmrows])))
                st["resid_vs_elapsed"] = dict(zip(
                    ("rho", "p", "n"),
                    spearman([r[0] for r in cmrows],
                             [r[3] for r in cmrows])))
            stats[space] = st
        blk["drift_stats"] = stats

    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, "scored.json"), "w") as fh:
        json.dump(out, fh, default=float)
    return out


# ------------------------------------------------------------------- report
def med(v):
    v = [x for x in v if x is not None]
    return float(np.median(v)) if v else None


def pct(x):
    return "n/a" if x is None else f"{100*x:5.1f}%"


def report(out):
    print("=" * 78)
    print("IDENTITY STABILITY — per receiver, never pooled")
    print("=" * 78)
    print("\n--- manifest (extraction) ---")
    print(f"{'session':<26}{'rows':>9}{'field':>7}{'median':>8}"
          f"{'medfilt?':>10}{'macs':>6}")
    for s, m in sorted(out["manifest"].items()):
        print(f"{s:<26}{m['rows']:>9}{m['n_field_screened']:>7}"
              f"{m['n_median_screened']:>8}"
              f"{'yes' if m['median_filter_available'] else 'NO COLUMN':>10}"
              f"{len(m['frames']):>6}")

    for bname, blk in out["blocks"].items():
        print("\n" + "=" * 78)
        print(f"{bname}   [{blk['note']}]")
        print(f"sessions: {len(blk['sessions'])}")
        if blk.get("skipped"):
            print(f"  SKIPPED: {blk['skipped']}")
            continue
        fl = blk["floor"]
        cand = sorted(fl["clears"].items(), key=lambda x: -x[1])
        print(f"  class-set availability: {len(fl['seen_any'])} distinct MACs"
              f" emitted >=1 window somewhere; "
              f"{len(fl['clears'])} clear the {MIN_WIN}-window floor in >=1"
              f" session; {len(fl['clears_2plus'])} clear it in >=2 "
              f"(only these can ever be a cross-session class)")
        for m, c in cand[:8]:
            tag = "BEACON " if m in BEACONS else "ambient"
            print(f"      {tag} {m}  clears floor in {c}/{fl['n_sessions']}"
                  f" sessions")
        amb2 = [m for m in fl["clears_2plus"] if m not in BEACONS]
        print(f"      ambient devices eligible as a cross-session class: "
              f"{len(amb2)} {amb2 if amb2 else ''}")
        for space in ("raw", "ref"):
            usable = [p for p in blk["pairs"]
                      if not p["spaces"].get(space, {}).get("skipped")
                      and p["spaces"].get(space, {}).get("within_gated")
                      is not None]
            ctrl = [p for p in usable if not p["straddles_remount"]]
            print(f"\n  [{space}]  ordered pairs usable: {len(usable)}"
                  f"   controlled (not straddling the {REMOUNT} remount): "
                  f"{len(ctrl)}")
            if not ctrl:
                print("    no controlled pair")
                continue
            print(f"    {'A -> B':<52}{'N':>3}{'test':>6}"
                  f"{'winG':>7}{'crsG':>7}{'gapG':>7}"
                  f"{'winN':>7}{'crsN':>7}{'gapN':>7}{'elapsed':>10}")
            for p in sorted(ctrl, key=lambda q: q["elapsed_s"]):
                s = p["spaces"][space]
                lab = f"{p['A'][:24]} -> {p['B'][:24]}"
                print(f"    {lab:<52}{s['n_classes']:>3}{s['n_test']:>6}"
                      f"{pct(s['within_gated']):>7}{pct(s['cross_gated']):>7}"
                      f"{pct(s['within_gated']-s['cross_gated']):>7}"
                      f"{pct(s['within_nn']):>7}{pct(s['cross_nn']):>7}"
                      f"{pct(s['within_nn']-s['cross_nn']):>7}"
                      f"{p['elapsed_s']/3600:>9.1f}h")
            ns = [p["spaces"][space]["n_classes"] for p in ctrl]
            wg = med([p["spaces"][space]["within_gated"] for p in ctrl])
            cg = med([p["spaces"][space]["cross_gated"] for p in ctrl])
            wn = med([p["spaces"][space]["within_nn"] for p in ctrl])
            cn = med([p["spaces"][space]["cross_nn"] for p in ctrl])
            print(f"    MEDIAN over {len(ctrl)} pairs, N={min(ns)}-{max(ns)}"
                  f" classes: within {pct(wg)} cross {pct(cg)}"
                  f"  gap {pct(wg-cg)}   |  nn within {pct(wn)}"
                  f" cross {pct(cn)} gap {pct(wn-cn)}")
            nmed = float(np.median(ns))
            if cg is not None and wg:
                deg = "  [N=2: 2/N=100%, that arm is DEGENERATE — use gap]" \
                    if nmed <= 2 else ""
                print(f"    ratio cross/within (gated) {cg/wg:.3f}"
                      f"   chance 1/N = {pct(1/nmed)}"
                      f"   threshold 2/N = {pct(2/nmed)}{deg}")
            for tag in ("beacon", "ambient"):
                bw = med([p["spaces"][space]["breakdown"][tag]
                          .get("within_gated") for p in ctrl])
                bc = med([p["spaces"][space]["breakdown"][tag]
                          .get("cross_gated") for p in ctrl])
                bn = [p["spaces"][space]["breakdown"][tag]["n_classes"]
                      for p in ctrl]
                if bw is None:
                    print(f"    {tag}-only: not scorable "
                          f"(N={min(bn)}-{max(bn)} classes)")
                else:
                    print(f"    {tag}-only  N={min(bn)}-{max(bn)}: "
                          f"within {pct(bw)} cross {pct(bc)} gap "
                          f"{pct(bw-bc)}")
            rr = [p["spaces"][space]["ref_cross"] for p in ctrl
                  if p["spaces"][space].get("ref_cross")]
            if rr:
                print(f"    REFERENCE {REF_MAC} cross-session, n={len(rr)}"
                      f" pairs: recall {pct(med([r['recall'] for r in rr]))}"
                      f"  precision {pct(med([r['precision'] for r in rr]))}"
                      f"  FPR {pct(med([r['fpr'] for r in rr]))}")
            # per-device recall / precision, median over controlled pairs
            agg = defaultdict(lambda: defaultdict(list))
            for p in ctrl:
                for m, d in p["spaces"][space]["per_cross"].items():
                    if not d:
                        continue
                    for k in ("recall", "precision", "fpr"):
                        if d.get(k) is not None:
                            agg[m][k].append(d[k])
                    agg[m]["n"].append(d["n_true"])
            print(f"    per-device CROSS-SESSION (median over {len(ctrl)} "
                  f"pairs):")
            print(f"      {'device':<20}{'kind':>8}{'recall':>9}"
                  f"{'precis':>9}{'FPR':>9}{'n_test':>8}")
            for m in sorted(agg, key=lambda x: -med(agg[x]["recall"] or [0])):
                a = agg[m]
                print(f"      {m:<20}{'beacon' if m in BEACONS else 'ambient':>8}"
                      f"{pct(med(a['recall'])):>9}{pct(med(a['precision'])):>9}"
                      f"{pct(med(a['fpr'])):>9}{int(med(a['n'])):>8}")
            dr = [p["spaces"][space]["drift"] for p in ctrl]
            rr_ = med([d['residual_rms'] for d in dr])
            print(f"    DRIFT (SFO, rad/sc) n_dev={min(d['n_devices'] for d in dr)}-"
                  f"{max(d['n_devices'] for d in dr)}, median over {len(dr)}"
                  f" pairs:")
            print(f"      total RMS      {med([d['total_rms'] for d in dr]):.5f}")
            print(f"      |common-mode|  {med([abs(d['common_mode']) for d in dr]):.5f}"
                  f"   energy removed by the shared constant: "
                  f"{pct(med([d['var_explained'] for d in dr]))}")
            print(f"      per-device residual RMS {rr_:.5f} = "
                  f"{rr_/BETWEEN_UNIT_SD:.2f}x BETWEEN_UNIT_SD "
                  f"({BETWEEN_UNIT_SD}) -> "
                  f"{'NOT COMPENSABLE' if rr_ > BETWEEN_UNIT_SD else 'within the between-device spread'}")
            # 84:7b confusion persistence
            elig = [p for p in ctrl if WATCH in p["spaces"][space]["classes"]
                    and REF_MAC in p["spaces"][space]["classes"]]
            if not elig:
                inany = any(WATCH in out["manifest"][s]["frames"]
                            for s in blk["sessions"])
                print(f"    {WATCH}: NOT IN THE CLASS SET on this receiver "
                      f"(present in some session's raw frames: {inany}; "
                      f"below the {MIN_WIN}-window floor) — not 'measured "
                      f"and absent'")
            else:
                hit = 0
                rates_x, rates_w, tot_hits = [], [], 0
                for p in elig:
                    s = p["spaces"][space]
                    c = s["conf_cross"].get(REF_MAC, {})
                    oth = {k: v for k, v in c.items()
                           if k not in (REF_MAC, "<stranger>")}
                    if oth and max(oth, key=oth.get) == WATCH:
                        hit += 1
                    n_ref = s["per_cross"].get(REF_MAC, {}).get("n_true", 0)
                    if n_ref:
                        rates_x.append(c.get(WATCH, 0) / n_ref)
                        tot_hits += c.get(WATCH, 0)
                nvac = max(p["spaces"][space]["n_classes"] for p in elig)
                vac = ("  [N<=2: only one other class exists, so 'largest' "
                       "is VACUOUS — read the rate]" if nvac <= 2 else "")
                print(f"    {WATCH}: largest ref confusion in {hit}/"
                      f"{len(elig)} eligible pairs = "
                      f"{100*hit/len(elig):.0f}%{vac}")
                print(f"      rate: median {pct(med(rates_x))} of reference "
                      f"test windows land on it cross-session; "
                      f"{tot_hits} windows total over {len(elig)} pairs")
            ds = blk["drift_stats"][space]
            for tag in ("unordered", "ordered"):
                t = ds.get(tag, {})
                if t.get("rho_gated") is not None:
                    print(f"    GAP vs ELAPSED ({tag}) n={t['n']}: "
                          f"rho={t['rho_gated']:+.3f} p={t['p_gated']:.3f}"
                          f"  (nn: rho={t['rho_nn']:+.3f} p={t['p_nn']:.3f})")
                else:
                    print(f"    GAP vs ELAPSED ({tag}): n={t.get('n')} "
                          f"— too few pairs")
            for k in ("cm_vs_elapsed", "cm_vs_tod", "resid_vs_elapsed"):
                if k in ds:
                    t = ds[k]
                    print(f"    {k}: rho={t['rho']:+.3f} p={t['p']:.3f} "
                          f"n={t['n']}")
        strad = [p for p in blk["pairs"] if p["straddles_remount"]
                 and not p["spaces"].get("raw", {}).get("skipped")
                 and p["spaces"].get("raw", {}).get("within_gated")
                 is not None]
        if strad:
            wg = med([p["spaces"]["raw"]["within_gated"] for p in strad])
            cg = med([p["spaces"]["raw"]["cross_gated"] for p in strad])
            ns = [p["spaces"]["raw"]["n_classes"] for p in strad]
            print(f"\n  [raw] {len(strad)} pairs STRADDLE the {REMOUNT} "
                  f"remount — NOT a controlled comparison "
                  f"(COLOCATED_0823 5.5). N={min(ns)}-{max(ns)}: "
                  f"within {pct(wg)} cross {pct(cg)} gap {pct(wg-cg)}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("csvs", nargs="+")
    e.add_argument("--cap", type=int, default=DEFAULT_CAP)
    sub.add_parser("score")
    sub.add_parser("report")
    a = ap.parse_args()

    if a.cmd == "extract":
        for p in a.csvs:
            out, cached = extract(p, a.cap)
            print(f"{'cached ' if cached else 'wrote  '}{out}",
                  file=sys.stderr)
    elif a.cmd == "score":
        report(score(a))
    else:
        with open(os.path.join(CACHE, "scored.json")) as fh:
            report(json.load(fh))
    return 0


if __name__ == "__main__":
    sys.exit(main())
