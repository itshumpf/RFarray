#!/usr/bin/env python3
"""ROTATION — does the signature follow the board, or the position?

Pre-registered design and decision rule: docs/ROTATION_PREREG.md (Stage 1
written and saved before the capture existed; this file written after, as
that document promised).

Capture 2026-08-27 14:06:42, 2:07:29. Blocks are defined from the operator's
in-band `label` column, not from a clock, with +-120 s guards around every
label (his stated round-trip from desk to hardware and back). Arrangements,
from HOME = B2@POS1, B3@POS2, B1@POS3:

    A   B2@POS1  B1@POS3      HOME
    B   B1@POS1  B2@POS3      after `b1 b2 switch`
    A'  B2@POS1  B1@POS3      after `original positions`

B3 relocated at t=1924 (`b3 moved`), between A and B, and was in motion again
at the end. It is NOT a control here and is reported without being used.

    python pc/exp_rotation.py
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import tempfile
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exp_iq_imbalance as iq                                   # noqa: E402

CACHE = os.environ.get("ROT_CACHE",
                       os.path.join(tempfile.gettempdir(), "rot"))
iq.CACHE = CACHE                      # the scan writes where we read
SRC = {"s3": "data/raw/s3_20260827_140642.csv",
       "d0wd": "data/raw/d0wd_20260827_140642.csv"}

# Block windows in seconds from each file's own first row, derived from the
# operator's in-band `label` column with +-120 s guards. Label times:
#   1075 it-is-now | 1867 ac-went-on | 2411 b1-b2-switch | 4699 house-empty
#   6843 original-positions | 6899 well-after | 7649 end
WINDOWS = {"A": (1195, 1747), "B": (2531, 4579), "Ap": (7019, 7640)}


def extract():
    """Split each capture into per-block CSVs, once. Row filter only — the
    corrupt-row screening is left to the scan, unchanged."""
    os.makedirs(CACHE, exist_ok=True)
    made = []
    for rx, path in SRC.items():
        want = [b for b in WINDOWS
                if not os.path.exists(os.path.join(CACHE, f"{rx}_{b}.csv"))]
        if not want:
            continue
        if not os.path.exists(path):
            print(f"  missing {path} — skipping {rx}", file=sys.stderr)
            continue
        csv.field_size_limit(10 ** 7)
        outs = {}
        with open(path, newline="") as fh:
            r = csv.reader(fh); hdr = next(r); it = hdr.index("pc_time_us")
            for b in want:
                f = open(os.path.join(CACHE, f"{rx}_{b}.csv"), "w",
                         newline="")
                w = csv.writer(f); w.writerow(hdr); outs[b] = [f, w, 0]
            t0 = None
            for row in r:
                try:
                    t = int(row[it])
                except (ValueError, IndexError):
                    continue
                if t0 is None:
                    t0 = t
                s = (t - t0) / 1e6
                for b in want:
                    lo, hi = WINDOWS[b]
                    if lo <= s < hi:
                        outs[b][1].writerow(row); outs[b][2] += 1
                        break
        for b, (f, _w, n) in outs.items():
            f.close()
            print(f"  extracted {rx}_{b}: {n:,} rows")
            made.append((rx, b))
    return made


def ensure_scans():
    extract()
    for rx in SRC:
        for b in WINDOWS:
            src = os.path.join(CACHE, f"{rx}_{b}.csv")
            pkl = os.path.join(CACHE, f"{rx}_{b}_strue_scan.pkl")
            if os.path.exists(pkl) or not os.path.exists(src):
                continue
            print(f"  scanning {rx}_{b} ...", file=sys.stderr)
            iq.run_scan(argparse.Namespace(
                path=src, tag=f"{rx}_{b}", convention="divided",
                svar="strue", max_rows=0, seconds=0, resume=False))
B1, B2, B3 = "a4:f0:0f:77:91:20", "28:05:a5:2f:fa:48", "f4:2d:c9:70:72:30"
NAME = {B1: "B1", B2: "B2", B3: "B3"}
BLOCKS = ("A", "B", "Ap")
# arrangement[block][pos] = mac
ARR = {"A": {1: B2, 3: B1}, "B": {1: B1, 3: B2}, "Ap": {1: B2, 3: B1}}
MIN_FRAMES = iq.FLOOR_CHUNK          # 2000, unchanged


def pooled(tag):
    """{mac: Cell} — every 600 s cell in one block summed per source."""
    st = iq.load(tag, "strue")
    d = defaultdict(list)
    for (mac, _c), cell in st.cells.items():
        d[mac].append(cell)
    return {m: iq.add_cells(cs) for m, cs in d.items()}


def feat(cell):
    f = iq.features(cell)
    if f is None:
        return None
    return dict(k=f["kappa"], slope=f["slope_med"], n=f["n"],
                rssi=f["rssi"], det=bool(f.get("detected2")),
                noise=abs(f["kh1"] - f["kh2"]) / 2.0)


def main():
    ensure_scans()
    print("\n" + "=" * 76)
    print("ROTATION — docs/ROTATION_PREREG.md")
    print("blocks from the label column, +-120 s guards. B3 excluded (moved "
          "between A and B).")
    print("=" * 76)

    for rx in ("s3", "d0wd"):
        V = {}
        print(f"\n{'='*76}\nRECEIVER {rx}\n{'='*76}")
        print(f"{'block':<6}{'beacon':<8}{'pos':<5}{'n':>9}{'rssi':>8}"
              f"{'|k|':>10}{'arg k':>9}{'slope':>11}")
        for b in BLOCKS:
            try:
                P = pooled(f"{rx}_{b}")
            except FileNotFoundError:
                print(f"  {b}: no scan"); continue
            for mac in (B1, B2, B3):
                if mac not in P:
                    continue
                f = feat(P[mac])
                if f is None:
                    continue
                pos = next((p for p, m in ARR[b].items() if m == mac), None)
                ok = f["n"] >= MIN_FRAMES and f["det"]
                flag = "" if ok else "   <-- FLOOR FAIL"
                print(f"{b:<6}{NAME[mac]:<8}{str(pos or '-'):<5}{f['n']:>9,}"
                      f"{f['rssi']:>8.1f}{abs(f['k']):>10.5f}"
                      f"{math.degrees(math.atan2(f['k'].imag, f['k'].real)):>9.1f}"
                      f"{f['slope']:>11.6f}{flag}")
                if ok and mac in (B1, B2):
                    V[(b, mac)] = f

        need = [(b, m) for b in BLOCKS for m in (B1, B2)]
        if not all(k in V for k in need):
            missing = [f"{b}/{NAME[m]}" for b, m in need if (b, m) not in V]
            print(f"\n  FLOOR FAILURE — missing {', '.join(missing)}. "
                  f"No verdict on {rx}.")
            continue

        def dk(a, b_):
            return abs(V[a]["k"] - V[b_]["k"])

        # R_drift: same device, same position, time only (A vs A')
        rd = {m: dk(("A", m), ("Ap", m)) for m in (B1, B2)}
        R = float(np.mean(list(rd.values())))
        # D_dev: same device, position changed (A vs B)
        dd = {m: dk(("A", m), ("B", m)) for m in (B1, B2)}
        # D_pos: same position, device changed
        dp = {1: dk(("A", ARR["A"][1]), ("B", ARR["B"][1])),
              3: dk(("A", ARR["A"][3]), ("B", ARR["B"][3]))}

        print(f"\n  R_drift  (A vs A', same device same position — the null "
              f"band this experiment measures for itself)")
        for m in (B1, B2):
            print(f"      {NAME[m]}  {rd[m]:.5f}")
        print(f"      mean R_drift = {R:.5f}")

        print(f"\n  D_dev    (A vs B, device moved)          ratio vs R_drift")
        for m in (B1, B2):
            print(f"      {NAME[m]}  {dd[m]:.5f}                    "
                  f"{dd[m]/R:>6.2f}x")
        print(f"  D_pos    (A vs B, position held)         ratio vs R_drift")
        for p in (1, 3):
            print(f"      POS{p}  {dp[p]:.5f}                    "
                  f"{dp[p]/R:>6.2f}x")

        # Pre-registered sign test: a swap is ANTISYMMETRIC (B1 gains what B2
        # loses); occupancy is SYMMETRIC (both move together). Frozen before
        # scoring — docs/ROTATION_PREREG.md.
        d1 = V[("B", B1)]["k"] - V[("A", B1)]["k"]
        d2 = V[("B", B2)]["k"] - V[("A", B2)]["k"]
        cos = ((d1.real*d2.real + d1.imag*d2.imag)
               / (abs(d1)*abs(d2))) if abs(d1)*abs(d2) > 0 else float("nan")
        if cos < -0.3:
            sign = "ANTISYMMETRIC — consistent with a position swap"
        elif cos > 0.3:
            sign = "SYMMETRIC — consistent with a room/occupancy change"
        else:
            sign = "NEITHER — the two moves are roughly orthogonal"
        print(f"\n  SIGN TEST  cos(angle between dk(B1) and dk(B2)) = "
              f"{cos:+.3f}")
        print(f"      {sign}")

        mdd, mdp = max(dd.values()), max(dp.values())
        v = ("SILICON — signature follows the board"
             if mdd <= R and mdp > 3*R else
             "POSITION — signature stays with the room"
             if mdp <= R and mdd > 3*R else
             "UNDERPOWERED — both inside the drift band"
             if mdd <= R and mdp <= R else
             f"MIXED — D_pos/D_dev = {mdp/mdd:.2f}, neither claimed")
        print(f"\n  VERDICT ({rx}): {v}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
