#!/usr/bin/env python3
"""Is `kappa` a hardware property? The U/L-bit definitional test.

Pre-registered design, thresholds and caveats: docs/UL_BIT_GROUND_TRUTH.md
(Stage 1 written and saved before this file was run).

`1c:ce:51:f3:0d:fa` and `1e:ce:51:f3:0d:fa` differ only in the IEEE
locally-administered bit (0x02 of octet 0). That is ONE radio presenting two
interfaces -- ground truth that is definitional rather than inferred from
similarity, unlike every other identity pair in this repo. If kappa is a
hardware property, the two must agree.

The SFO slope already fails this: docs/BLIND_CLUSTERING.md 9.5 measures the
pair 21.7 x BETWEEN_UNIT_SD apart. C:\\dev\\.astory\\ERROR_LOG.md E41 is the
entry that identified the pair and named the test.

Read-only. Imports the kappa estimator from exp_iq_imbalance.py rather than
reimplementing it, so this pass cannot disagree with docs/IQ_IMBALANCE.md
about what kappa is. Modifies nothing in pc/rff/.

  python pc/exp_ul_ground_truth.py
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exp_iq_imbalance as iq                                  # noqa: E402

CACHE = os.environ.get("KXS_CACHE", "/tmp/kxs")

# ---- frozen in docs/UL_BIT_GROUND_TRUTH.md 2-3, not tunable from the CLI
UL_PAIR = ("1c:ce:51:f3:0d:fa", "1e:ce:51:f3:0d:fa")
BEACONS = ("a4:f0:0f:77:91:20", "f4:2d:c9:70:72:30", "28:05:a5:2f:fa:48")
MIN_FRAMES = iq.FLOOR_CHUNK          # 2000, taken unchanged (prereg 1.11)
PASS_BAR = 1.0                       # 2: Delta_UL / S_dev
MARGINAL_BAR = 3.0


def receiver_of(tag):
    return tag.split("_", 1)[0]


def pooled_cells():
    """{receiver: {mac: Cell}} -- every 600 s cell summed per source.

    The accumulators are plain sums by construction (exp_iq_imbalance.Cell
    docstring); add_cells() exists for exactly this. Chunking at 600 s is a
    stability-analysis choice, and a single kappa per source is what this
    test needs. docs/UL_BIT_GROUND_TRUTH.md 3.
    """
    import glob
    buckets = defaultdict(lambda: defaultdict(list))
    for p in sorted(glob.glob(os.path.join(CACHE, "*_strue_scan.pkl"))):
        tag = os.path.basename(p).replace("_strue_scan.pkl", "")
        try:
            st = iq.load(tag, "strue")
        except Exception:
            continue
        rx = receiver_of(tag)
        for (mac, _chunk), cell in st.cells.items():
            buckets[rx][mac].append(cell)
    return {rx: {m: iq.add_cells(cs) for m, cs in d.items()}
            for rx, d in buckets.items()}


def kappa_of(cell):
    """(kappa, split_half_noise, n, rssi, slope, detected2) or None."""
    f = iq.features(cell)
    if f is None:
        return None
    noise = abs(f["kh1"] - f["kh2"]) / 2.0
    return dict(kappa=f["kappa"], noise=noise, n=f["n"],
                rssi=f["rssi"], slope=f["slope_med"],
                det=bool(f.get("detected2")), coh=f["coh"],
                coh_floor=f["coh_floor"])


def main():
    pools = pooled_cells()
    out = {"min_frames": MIN_FRAMES, "pass_bar": PASS_BAR,
           "marginal_bar": MARGINAL_BAR, "receivers": {}}

    print("\n" + "=" * 74)
    print("U/L-BIT GROUND TRUTH -- docs/UL_BIT_GROUND_TRUTH.md")
    print("one radio, two addresses. if kappa is hardware, they must agree.")
    print(f"floor: >= {MIN_FRAMES:,} admitted frames AND detected2, per "
          f"(MAC, receiver). never pooled across receivers.")
    print("=" * 74)

    for rx in sorted(pools):
        d = pools[rx]
        print(f"\n---- receiver {rx} ----")
        vals = {}
        for m in list(UL_PAIR) + list(BEACONS):
            if m not in d:
                print(f"  {m}   ABSENT")
                continue
            k = kappa_of(d[m])
            if k is None:
                print(f"  {m}   no features")
                continue
            ok = k["n"] >= MIN_FRAMES and k["det"]
            flag = ("" if ok else
                    f"  <-- FLOOR FAIL (n={k['n']:,}"
                    f"{', detected2=False' if not k['det'] else ''})")
            tag = "UL-PAIR" if m in UL_PAIR else "beacon "
            print(f"  {tag} {m}  n={k['n']:>9,}  rssi={k['rssi']:>6.1f}  "
                  f"|k|={abs(k['kappa']):.5f}  arg={math.degrees(math.atan2(k['kappa'].imag, k['kappa'].real)):+7.1f}deg"
                  f"  +-{k['noise']:.5f}{flag}")
            if ok:
                vals[m] = k

        bs = [m for m in BEACONS if m in vals]
        if len(bs) < 2:
            print("\n  positive control C1 unavailable: fewer than two "
                  "beacons clear the floor. No verdict on this receiver.")
            out["receivers"][rx] = dict(verdict="C1 UNAVAILABLE")
            continue

        # C1 / S_dev : median pairwise |dkappa| between genuinely different
        # radios, same cells, same code path.
        pw = []
        for i in range(len(bs)):
            for j in range(i + 1, len(bs)):
                pw.append(abs(vals[bs[i]]["kappa"] - vals[bs[j]]["kappa"]))
        S_dev = float(np.median(pw))
        print(f"\n  C1  beacon pairwise |dk|: "
              f"{', '.join(f'{x:.5f}' for x in sorted(pw))}"
              f"   -> S_dev (median) = {S_dev:.5f}")

        have = [m for m in UL_PAIR if m in vals]
        if len(have) < 2:
            missing = [m for m in UL_PAIR if m not in vals]
            print(f"  FLOOR FAILURE: {', '.join(missing)} does not clear "
                  f"the floor on {rx}. That is a floor failure, not a null, "
                  f"and no verdict is quoted.")
            out["receivers"][rx] = dict(verdict="FLOOR FAILURE",
                                        S_dev=S_dev, missing=missing)
            continue

        a, b = vals[UL_PAIR[0]], vals[UL_PAIR[1]]
        D = abs(a["kappa"] - b["kappa"])
        ratio = D / S_dev if S_dev > 0 else float("inf")
        noise = math.hypot(a["noise"], b["noise"])
        # C3 comparator: the slope, same cells
        Dslope = abs(a["slope"] - b["slope"])
        bslope = [abs(vals[bs[i]]["slope"] - vals[bs[j]]["slope"])
                  for i in range(len(bs)) for j in range(i + 1, len(bs))]
        S_slope = float(np.median(bslope))
        rslope = Dslope / S_slope if S_slope > 0 else float("inf")
        # C2 negative control
        c2 = min(abs(vals[m]["kappa"] - x["kappa"])
                 for m in bs for x in (a, b))

        verdict = ("PASS" if ratio <= PASS_BAR else
                   "MARGINAL" if ratio <= MARGINAL_BAR else "FAIL")
        under = D < noise

        print(f"\n  Delta_UL  |k(1c) - k(1e)| = {D:.5f}"
              f"   split-half noise +-{noise:.5f}"
              f"{'   <-- INSIDE NOISE: underpowered, not passed' if under else ''}")
        print(f"  Delta_UL / S_dev = {ratio:.2f}    "
              f"(bar: <=1.0 PASS, <=3.0 MARGINAL, >3.0 FAIL)")
        print(f"  C2  nearest beacon to either address: {c2:.5f} "
              f"({c2/S_dev:.2f} x S_dev)")
        print(f"  C3  same test on the SFO slope: |dslope| = {Dslope:.6f}, "
              f"S_slope = {S_slope:.6f}, ratio = {rslope:.2f}")
        print(f"  C4  RSSI  1c {a['rssi']:.1f} dBm   1e {b['rssi']:.1f} dBm"
              f"   delta {abs(a['rssi']-b['rssi']):.1f} dB")
        print(f"\n  VERDICT ({rx}): {verdict}"
              f"{'  [UNDERPOWERED]' if under else ''}")

        out["receivers"][rx] = dict(
            verdict=verdict, underpowered=bool(under),
            Delta_UL=D, S_dev=S_dev, ratio=ratio, noise=noise,
            slope_ratio=rslope, d_slope=Dslope, S_slope=S_slope,
            c2_nearest_beacon=c2,
            rssi={UL_PAIR[0]: a["rssi"], UL_PAIR[1]: b["rssi"]},
            n={UL_PAIR[0]: a["n"], UL_PAIR[1]: b["n"]})

    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, "ul_ground_truth.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"\n  -> {os.path.join(CACHE, 'ul_ground_truth.json')}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
