#!/usr/bin/env python3
"""NIGHT_EIGHT_PREREG Stage 2 — one command, no judgement calls.

Scores docs/NIGHT_EIGHT_PREREG.md sec.6 against a capture. Everything that could
be argued about was argued about in that document, before the data existed. If
this script and that document disagree, THE DOCUMENT WINS and this is the bug.

    python pc/exp_night_eight.py --stamp 20260905_012345 [--t0 0]

Nothing here reimplements the pipeline: FrameEstimator, WindowAggregator, the
gates, the window size, the pooled covariance and the chi2 thresholds all come
from rff_offline / rff.discriminator unchanged. Read-only on data/raw/.
Resumable — each block is cached, so a re-run costs nothing already done.
"""
import argparse
import json
import os
import tempfile
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
_ROOT = os.path.dirname(_HERE)

from rff_offline import collect_observations            # noqa: E402
from rff.discriminator import Discriminator             # noqa: E402

BEACONS = {"28:05:a5:2f:fa:48": "B2",
           "a4:f0:0f:77:91:20": "B1",
           "f4:2d:c9:70:72:30": "B3"}
BETWEEN_UNIT_SD = 0.00237          # pc/exp_ambient_separation.py:79
SEP_LINE = 3.0                     # pc/rff_offline.py:353, and sec.6 R3
LEAD_S = 500                       # validated in SEVEN_NIGHT_REREAD sec.9A
BLOCK_S = 300
# sec.4 — fixed before the capture existed
BLOCKS = [("E", 600), ("+1", 4200), ("+2", 7800), ("+3", 11400),
          ("+4", 15000), ("+5", 18600)]
CORE = {"E", "+1", "+2", "+3", "+4"}
RECEIVERS = ("s3", "d0wd")
CACHE = os.path.join(_ROOT, "data", "cache", "night8")


# ----------------------------------------------------------------- slicing

def _first_ts(f, pos):
    f.seek(pos)
    if pos:
        f.readline()
    while True:
        p = f.tell()
        line = f.readline()
        if not line:
            return None, p
        if line.startswith(b"pc_time_us"):
            continue
        try:
            return int(line.split(b",", 1)[0]), p
        except ValueError:
            continue


def slice_window(src, dst, a_s, b_s):
    """Byte-slice [a_s, b_s) seconds of a capture. pc_time_us is monotonic."""
    size = os.path.getsize(src)
    with open(src, "rb") as f:
        header = f.readline()
        t0, _ = _first_ts(f, len(header))

        def find(target, lo, hi):
            while lo < hi:
                mid = (lo + hi) // 2
                ts, _ = _first_ts(f, mid)
                if ts is None or ts >= target:
                    hi = mid
                else:
                    lo = mid + 1
            return lo

        s = find(t0 + int(a_s * 1e6), len(header), size)
        e = find(t0 + int(b_s * 1e6), s, size)
        f.seek(s)
        data = f.read(e - s)
    with open(dst, "wb") as g:
        g.write(header)
        g.write(data)
        if data and not data.endswith(b"\n"):
            g.write(b"\n")
    with open(dst, "rb") as g:
        g.readline()
        first, _ = _first_ts(g, len(header))
    return (first - t0) / 1e6 if first is not None else a_s


# ------------------------------------------------------------- one block

def block_features(path, t_abs, tag):
    """(cfo, sfo) per accepted window for one 300 s block. Cached."""
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, f"{tag}@{int(t_abs)}.npz")
    if os.path.exists(out):
        z = np.load(out)
        return {m: z[m] for m in z.files}
    # scratch goes to the OS temp dir, never into the repo: the working tree
    # may be on a mount that refuses unlink (and scratch does not belong here)
    tmp = os.path.join(tempfile.gettempdir(), f"_n8_{tag}_{int(t_abs)}.csv")
    lead = max(0.0, t_abs - LEAD_S)
    origin = slice_window(path, tmp, lead, t_abs + BLOCK_S)
    try:
        by = collect_observations([tmp], 64, None,
                                  after=round(t_abs - origin, 1),
                                  before=round(t_abs + BLOCK_S - origin, 1))
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    d = {}
    for m, obs in by.items():
        if m not in BEACONS:
            continue
        rows = [(o["cfo"], o["sfo"]) for o in obs
                if o.get("cfo") is not None and o.get("sfo") is not None]
        if len(rows) >= 10:
            d[m] = np.array(rows, dtype=np.float64)
    np.savez_compressed(out, **d)
    return d


def classify(train, test, self_split=False):
    """correct / wrong-identity / refused counts, shipped Discriminator."""
    disc = Discriminator()
    for m, a in train.items():
        rows = a[:max(int(len(a) * 0.6), 1)] if self_split else a
        for f in rows:
            disc.learn(m, f)
    c = w = r = 0
    for m, a in test.items():
        if m not in train:
            continue
        rows = a[max(int(len(a) * 0.6), 1):] if self_split else a
        for f in rows:
            best, _, verdict = disc.classify(f)
            if verdict == "UNSCORED":
                continue
            if verdict == "STRANGER":
                r += 1
            elif best == m:
                c += 1
            else:
                w += 1
    n = c + w + r
    if not n:
        return None
    return dict(n=n, acc=100 * c / n, wrong=100 * w / n, refuse=100 * r / n,
                precision=(100 * c / (c + w)) if (c + w) else float("nan"))


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stamp", required=True)
    ap.add_argument("--t0", type=float, default=0.0,
                    help="seconds; read from the operator label if one exists, "
                         "else 0 and recorded as declared (sec.3)")
    ap.add_argument("--drift-step", type=float, default=1800.0)
    a = ap.parse_args()

    res = {}
    for rx in RECEIVERS:
        path = os.path.join(_ROOT, "data", "raw", f"{rx}_{a.stamp}.csv")
        if not os.path.exists(path):
            print(f"MISSING {path}", file=sys.stderr)
            continue
        tag = f"{rx}_{a.stamp}"
        blocks = {}
        for name, off in BLOCKS:
            t = a.t0 + off
            try:
                blocks[name] = block_features(path, t, tag)
            except Exception as exc:                     # noqa: BLE001
                print(f"  {tag} {name}: {exc}", file=sys.stderr)
                blocks[name] = {}
            print(f"  {tag} {name} (T0+{off}): "
                  f"{ {BEACONS[m]: len(v) for m, v in blocks[name].items()} }")
        res[rx] = blocks

    print("\n" + "=" * 78)
    print(f"NIGHT EIGHT — {a.stamp}   T0 = {a.t0:g} s"
          f"{'  (declared, no label)' if a.t0 == 0 else '  (read from label)'}")
    print("=" * 78)

    report = {}
    for rx, blocks in res.items():
        E = blocks.get("E", {})
        if len(E) < 2:
            print(f"\n{rx}: enrolment block unusable — {len(E)} sources")
            continue
        med = {BEACONS[m]: float(np.median(v[:, 1])) for m, v in E.items()}
        spread = (max(med.values()) - min(med.values())) / BETWEEN_UNIT_SD
        n_live = len(E)
        print(f"\n{rx}   beacons in enrolment: {n_live}   "
              f"SFO {', '.join(f'{k} {v:+.4f}' for k, v in sorted(med.items()))}")
        print(f"{rx}   POPULATION SPREAD = {spread:.1f} sigma  "
              f"-> R3 {'APPLIES' if spread >= SEP_LINE else 'makes no prediction (collapse cell)'}")
        rows = {}
        for name, _ in BLOCKS:
            t = blocks.get(name, {})
            if name == "E":
                s = classify(E, E, self_split=True)
            else:
                s = classify(E, t) if t else None
            rows[name] = s
            if s:
                s["n_sources"] = len(t) if name != "E" else len(E)
                print(f"  {name:>3}  n={s['n']:>5}  acc {s['acc']:>5.1f}%   "
                      f"wrong {s['wrong']:>5.1f}%   refuse {s['refuse']:>5.1f}%   "
                      f"precision {s['precision']:>5.1f}%")
            else:
                print(f"  {name:>3}  no data")
        report[rx] = dict(spread=spread, rows=rows, n_live=n_live)

    # -------------------------------------------------- drift curve, sec.6 R4/R5
    print("\n" + "-" * 78)
    print("drift sampling for R4 / R5 — every "
          f"{a.drift_step:g} s for as long as the capture runs")
    series = {}
    for rx in RECEIVERS:
        path = os.path.join(_ROOT, "data", "raw", f"{rx}_{a.stamp}.csv")
        if not os.path.exists(path):
            continue
        size_s = None
        t = a.t0 + 600
        while True:
            try:
                d = block_features(path, t, f"{rx}_{a.stamp}")
            except Exception:                            # noqa: BLE001
                break
            if not d:
                break
            for m, v in d.items():
                series.setdefault((rx, BEACONS[m]), {})[t] = float(np.median(v[:, 1]))
            t += a.drift_step
            if size_s is None:
                size_s = 0
    import itertools
    pairs = []
    for (rx, b), s in series.items():
        for x, y in itertools.combinations(sorted(s), 2):
            pairs.append(((y - x) / 3600.0, abs(s[y] - s[x]) / BETWEEN_UNIT_SD, rx))

    def band(lo, hi, rx=None):
        v = [d for l, d, r in pairs if lo <= l < hi and (rx is None or r == rx)]
        return (float(np.median(v)), len(v)) if v else (float("nan"), 0)

    b_short = band(0.5, 1.0)
    b_mid = band(4.0, 6.0)
    b_long = band(6.0, 9.0)
    print(f"  0.5-1 h {b_short[0]:.2f} sig (n={b_short[1]})   "
          f"4-6 h {b_mid[0]:.2f} (n={b_mid[1]})   6-9 h {b_long[0]:.2f} (n={b_long[1]})")

    # --------------------------------------------------------- frozen verdicts
    print("\n" + "=" * 78)
    print("FROZEN VERDICT TABLE — docs/NIGHT_EIGHT_PREREG.md sec.6")
    print("=" * 78)

    def both(fn):
        vals = [fn(rx, r) for rx, r in report.items()]
        return vals and all(v is True for v in vals), vals

    r1_ok, r1 = both(lambda rx, r: r["rows"]["E"] is not None
                     and r["rows"]["E"]["acc"] >= 90.0)
    print(f"R1  enrolment >= 90% both receivers          : "
          f"{'HELD' if r1_ok else 'FAILED'}   " +
          ", ".join(f"{rx} {r['rows']['E']['acc']:.1f}%" for rx, r in report.items()
                    if r['rows']['E']))

    def drop(r):
        e, f = r["rows"]["E"], r["rows"]["+4"]
        return (e["acc"] - f["acc"]) if (e and f) else None
    r2_ok, _ = both(lambda rx, r: (drop(r) or -1) >= 15.0)
    print(f"R2  >= 15 pt drop by +4 h both receivers     : "
          f"{'HELD' if r2_ok else 'FAILED'}   " +
          ", ".join(f"{rx} {drop(r):.0f} pt" for rx, r in report.items()
                    if drop(r) is not None))

    applies = {rx: r for rx, r in report.items() if r["spread"] >= SEP_LINE}
    if not applies:
        print("R3  refusal not confusion                    : UNTESTABLE "
              "(both receivers below 3.0 sigma — collapse night)")
    else:
        ok = True
        detail = []
        for rx, r in applies.items():
            for name in ("+1", "+2", "+3", "+4", "+5"):
                s = r["rows"].get(name)
                # sec.4: +5 is a bonus tier, scored only if every beacon that
                # was enrolled is still transmitting in that block
                if not s or (name not in CORE
                             and s.get("n_sources", 0) < r["n_live"]):
                    continue
                a_ok = s["wrong"] <= 10.0
                b_ok = (s["refuse"] > s["wrong"]) if name in ("+2", "+3", "+4", "+5") else True
                c_ok = s["precision"] >= 85.0
                if not (a_ok and b_ok and c_ok):
                    ok = False
                    detail.append(f"{rx}{name} wrong {s['wrong']:.1f}% "
                                  f"refuse {s['refuse']:.1f}% prec {s['precision']:.1f}%")
        print(f"R3  wrong<=10%, refuse>wrong, prec>=85%      : "
              f"{'HELD' if ok else 'FAILED'}   "
              f"(applies to {', '.join(applies)})")
        for d in detail:
            print(f"      violated: {d}")
    for rx, r in report.items():
        if r["spread"] < SEP_LINE:
            print(f"      {rx} is a COLLAPSE CELL at {r['spread']:.1f} sigma — "
                  "R3 makes no prediction, figures reported above")

    # An empty lag bin means the question was never asked, not that it was
    # answered badly. ERROR_LOG mode C: a capability failure must never be
    # reported as a negative result.
    if b_short[1] == 0 or b_mid[1] == 0:
        print("R4  4-6h >= 2.5x 0.5-1h; 6-9h <= 1.5x 4-6h   : NOT RUNNABLE   "
              f"(0.5-1 h bin n={b_short[1]}, 4-6 h bin n={b_mid[1]}; "
              "--drift-step must be <= 1800 and the capture long enough)")
    else:
        r4a = b_mid[0] >= 2.5 * b_short[0]
        if b_long[1] == 0:
            r4b, r4b_s = True, "NOT RUNNABLE (nothing survived to 6 h)"
        else:
            r4b = b_long[0] <= 1.5 * b_mid[0]
            r4b_s = f"{b_long[0] / b_mid[0]:.2f}x"
        print(f"R4  4-6h >= 2.5x 0.5-1h; 6-9h <= 1.5x 4-6h   : "
              f"{'HELD' if (r4a and r4b) else 'FAILED'}   "
              f"(a) {b_mid[0] / b_short[0]:.2f}x  (b) {r4b_s}")

    r5 = {rx: band(0.5, 1.0, rx) for rx in RECEIVERS}
    if all(n == 0 for _, n in r5.values()):
        print("R5  0.5-1 h wander < 0.35 sig both receivers : NOT RUNNABLE   "
              "(no pairs in the 0.5-1 h bin — use --drift-step 1800)")
    else:
        r5_ok = all(n > 0 and v < 0.35 for v, n in r5.values())
        print(f"R5  0.5-1 h wander < 0.35 sig both receivers : "
              f"{'HELD' if r5_ok else 'FAILED'}   " +
              ", ".join(f"{rx} {v:.2f} (n={n})" if n else f"{rx} no data"
                        for rx, (v, n) in r5.items()))

    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, f"night8_{a.stamp}.json"), "w") as f:
        json.dump({"stamp": a.stamp, "t0": a.t0,
                   "report": {rx: {"spread": r["spread"], "rows": r["rows"]}
                              for rx, r in report.items()},
                   "drift": {"0.5-1h": b_short, "4-6h": b_mid, "6-9h": b_long}},
                  f, indent=1, default=float)
    print(f"\nwrote {CACHE}/night8_{a.stamp}.json")
    print("Paste the block above into docs/NIGHT_EIGHT_PREREG.md sec.9.")


if __name__ == "__main__":
    sys.exit(main())
