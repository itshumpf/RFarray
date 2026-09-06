#!/usr/bin/env python3
"""Statistical summaries for stratified_frame_probe.py outputs."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd


SIGMA = 0.00237
FEATURES = ["rssi_median", "all_frames", "amplitude_median", "inlier_median",
            "k_plus1_amplitude_median", "phase_coherence_median",
            "phase_roughness_median", "cir_peak_fraction_median",
            "cir_rms_delay_median"]


def spearman(a, b):
    z = pd.concat([pd.Series(a), pd.Series(b)], axis=1).dropna()
    if len(z) < 3:
        return np.nan
    # Avoid scipy as a runtime dependency: Spearman is Pearson on ranks.
    ra = z.iloc[:, 0].rank(method="average").to_numpy(float)
    rb = z.iloc[:, 1].rank(method="average").to_numpy(float)
    if np.std(ra) == 0 or np.std(rb) == 0:
        return np.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def acf(x, lag):
    x = np.asarray(x, float)
    if len(x) <= lag or np.std(x[:-lag]) == 0 or np.std(x[lag:]) == 0:
        return np.nan
    return float(np.corrcoef(x[:-lag], x[lag:])[0, 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--out", required=True)
    ap.add_argument("--census", required=True,
                    help="census directory used to recover absolute PC time")
    args = ap.parse_args()
    files = sorted(Path(args.root).glob("*.minute_probe.csv"))
    df = pd.concat([pd.read_csv(p) for p in files], ignore_index=True)
    origins = {}
    for p in Path(args.census).glob("*.census.json.gz"):
        with gzip.open(p, "rt", encoding="utf-8") as f:
            d = json.load(f)
        origins[d["file"]] = d["pc_first_us"] / 1e6
    df["absolute_minute"] = np.floor(
        (df["file"].map(origins) + df["minute"] * 60 + 30) / 60).astype("Int64")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "minute_probe_all.csv", index=False)
    print(f"files={len(files)} minute_rows={len(df):,} sampled_fitted_frames={df.sampled.sum():,}")

    metrics = ["slope_median", "slope_iqr", "ransac_ols_abs_median",
               "ransac_ols_gt_0p05_frac", "inlier_median", "resid_median",
               "phase_coherence_median", "amplitude_median", "amplitude_cv_median",
               "k_plus1_amplitude_median", "cir_peak_fraction_median", "cir_rms_delay_median"]
    group_rows = []
    print("\nGROUP MEDIANS")
    for (rx, b), g in df.groupby(["receiver", "beacon"]):
        row = {"receiver": rx, "beacon": b, "minute_rows": len(g),
               "sampled": int(g.sampled.sum())}
        for m in metrics: row[m] = g[m].median()
        group_rows.append(row)
        print(f"{rx}/{b}: mins={len(g):>4} frames={g.sampled.sum():>7,} "
              f"slope={g.slope_median.median():+.5f} IQRframe={g.slope_iqr.median():.5f} "
              f"inlier={g.inlier_median.median():.3f} resid={g.resid_median.median():.3f} "
              f"R-OLS={g.ransac_ols_abs_median.median():.4f} "
              f">.05={g.ransac_ols_gt_0p05_frac.median():.1%} "
              f"k+1amp={g.k_plus1_amplitude_median.median():.2f} "
              f"CIRpeak={g.cir_peak_fraction_median.median():.3f}")
    pd.DataFrame(group_rows).to_csv(out / "probe_group_summary.csv", index=False)

    print("\nWITHIN-SESSION ASSOCIATION WITH SLOPE (Spearman; centered / first-difference)")
    assoc_rows = []
    for (rx, b), g in df.groupby(["receiver", "beacon"]):
        centered = g.copy()
        centered["ys"] = centered.slope_median - centered.groupby("stamp").slope_median.transform("median")
        pieces = []
        for _, h in g.sort_values(["stamp", "minute"]).groupby("stamp"):
            q = h.copy()
            q["ys"] = q.slope_median.diff()
            for f in FEATURES: q[f] = q[f].diff()
            pieces.append(q.iloc[1:])
        dif = pd.concat(pieces, ignore_index=True)
        vals = []
        for f in FEATURES:
            rc = spearman(centered.ys, centered[f] - centered.groupby("stamp")[f].transform("median"))
            rd = spearman(dif.ys, dif[f])
            assoc_rows.append({"receiver": rx, "beacon": b, "feature": f,
                               "rho_centered": rc, "rho_diff": rd})
            vals.append(f"{f.replace('_median','')}: {rc:+.2f}/{rd:+.2f}")
        print(f"{rx}/{b}: " + " | ".join(vals))
    pd.DataFrame(assoc_rows).to_csv(out / "slope_feature_associations.csv", index=False)

    print("\nSLOPE AUTOCORRELATION (median across sessions)")
    ac_rows = []
    for (rx, b), g in df.groupby(["receiver", "beacon"]):
        vals = {lag: [] for lag in (1, 5, 30, 60)}
        for _, h in g.sort_values("minute").groupby("stamp"):
            # Retain only consecutive-minute stretches.
            h = h.set_index("minute").slope_median
            full = h.reindex(range(int(h.index.min()), int(h.index.max()) + 1))
            for lag in vals:
                z = pd.concat([full, full.shift(lag)], axis=1).dropna()
                if len(z) >= 10:
                    vals[lag].append(spearman(z.iloc[:, 0], z.iloc[:, 1]))
        row = {"receiver": rx, "beacon": b}
        for lag, a in vals.items(): row[f"lag{lag}"] = float(np.nanmedian(a)) if a else np.nan
        ac_rows.append(row)
        print(f"{rx}/{b}: " + " ".join(f"lag{k}={row[f'lag{k}']:+.3f}" for k in vals))
    pd.DataFrame(ac_rows).to_csv(out / "slope_autocorrelation.csv", index=False)

    # Receiver comparison at corresponding minute index.
    print("\nCROSS-RECEIVER SLOPE CORRELATION")
    cross_rows = []
    for (stamp, b), g in df.groupby(["stamp", "beacon"]):
        p = g.pivot_table(index="absolute_minute", columns="receiver", values="slope_median")
        if {"d0wd", "s3"}.issubset(p.columns):
            p = p.dropna(subset=["d0wd", "s3"])
            rlev = spearman(p.d0wd, p.s3)
            rdiff = spearman(p.d0wd.diff(), p.s3.diff())
            cross_rows.append({"stamp": stamp, "beacon": b, "n": len(p),
                               "rho_level": rlev, "rho_diff": rdiff,
                               "median_s3_minus_d0wd": float(np.median(p.s3-p.d0wd))})
            print(f"{stamp}/{b}: n={len(p):>4} level={rlev:+.3f} diff={rdiff:+.3f} "
                  f"median(S3-D)={np.median(p.s3-p.d0wd):+.5f}")
    pd.DataFrame(cross_rows).to_csv(out / "cross_receiver_slope.csv", index=False)

    # Pair distances minute by minute, then simultaneous receiver events.
    pair_rows = []
    pairs = [("B1", "B2"), ("B1", "B3"), ("B2", "B3")]
    for (rx, stamp), g in df.groupby(["receiver", "stamp"]):
        p = g.pivot_table(index="minute", columns="beacon", values="slope_median")
        for minute, row in p.iterrows():
            for a, b in pairs:
                if a in row and b in row and pd.notna(row[a]) and pd.notna(row[b]):
                    delta = abs(row[a] - row[b])
                    absolute_minute = int(g.loc[g.minute == minute, "absolute_minute"].iloc[0])
                    pair_rows.append({"receiver": rx, "stamp": stamp, "minute": minute,
                                      "absolute_minute": absolute_minute,
                                      "pair": f"{a}-{b}", "delta": delta,
                                      "sigma": delta / SIGMA})
    pairs_df = pd.DataFrame(pair_rows)
    pairs_df.to_csv(out / "pairwise_minute_distances.csv", index=False)
    print("\nPAIRWISE MINUTES BELOW 1 BETWEEN-UNIT SIGMA")
    for keys, g in pairs_df.groupby(["receiver", "stamp", "pair"]):
        n = int((g.sigma < 1).sum())
        if n:
            print(f"{'/'.join(keys)}: {n}/{len(g)} ({n/len(g):.1%}), min={g.sigma.min():.3f} sigma")
    z = pairs_df.pivot_table(index=["stamp", "absolute_minute", "pair"], columns="receiver", values="sigma").dropna()
    both = z[(z.d0wd < 1) & (z.s3 < 1)]
    print(f"simultaneous same-pair <1 sigma: {len(both)}/{len(z)} paired receiver-minutes")
    if len(both): print(both.sort_values(["d0wd", "s3"]).head(30).to_string())


if __name__ == "__main__":
    main()
