#!/usr/bin/env python3
r"""EXPERIMENT: are all three ESP32 D0WD beacons clock twins of each other?

Read-only. Writes nothing into data/, pc/rff/, pc/occ/, site/ or any
existing entry point.

The hypothesis under test
-------------------------
Braeden's conjecture: the three D0WD TX beacons were bought in one order,
so their crystals plausibly came off one reel / one manufacturing lot, and
within-lot oscillator variance is far tighter than across-lot. If that is
true, the project's published "same-model ESP32 discrimination tops out at
~77%, units 1.8-2.7 sigma apart" (docs/HANDOFF.md) is not a same-*model*
result at all -- it is a same-*lot* result, and same-model units from
different lots might separate cleanly.

Falsifiable form of the hypothesis, in this project's own units:

  STRONG  all three pairwise separations sit at the recorded clock-twin
          scale (0.26 sigma / dSFO 0.0008 rad/sc, docs/TWIN_INVESTIGATION.md).
  WEAK    all three pairs sit below the project's own 3 sigma
          reliable-separation line, but not all at twin scale.
  REFUTED at least one pair separates like genuinely different crystals.

Why this tool exists rather than plain rff_offline.py
-----------------------------------------------------
`Discriminator.separation_matrix()` pools covariance over *every*
characterized source in the library. Run over a whole session that includes
ambient traffic, the three-beacon sigmas are therefore computed against a
pooled covariance that ambient devices helped set, and are not the
three-beacon numbers the hypothesis is about. `rff_offline.py --only-macs`
drops sources *after* reference correction but still pools over whatever
survives, and it has no bootstrap. This script restricts the pool to a
named MAC set and resamples it.

No DSP is reimplemented and none is imported twice: observations come from
`twin_probe.load()`, whose cache shards are produced by `twin_probe collect`,
which itself calls `rff_offline.collect_observations`. The chain to the
production estimator is:

    rff.dsp.FrameEstimator / WindowAggregator
      -> rff.reference.ReferenceNormalizer
        -> rff_offline.collect_observations
          -> twin_probe.collect (cache shard)
            -> twin_probe.load
              -> this file (selection, bootstrap, reporting only)

Subcommands
-----------
  overlap   simultaneity test: are the named sources on air at the same
            time in one capture? Removes thermal/environmental drift as a
            confound, the way docs/TWIN_INVESTIGATION.md 5a did.
  matrix    restricted pairwise separation matrix for one tag, in sigma
            and in raw dCFO/dSFO, with bootstrap 95% CIs.
  sessions  run `matrix` across several tags and print one row per
            (session, pair) -- the replication table.

Usage
-----
  TWIN_PROBE_CACHE=/some/scratch python twin_probe.py collect \
      --tag lot14a ../data/raw/rx_20260714_011619.csv
  python exp_lot_hypothesis.py overlap ../data/raw/rx_20260714_011619.csv
  python exp_lot_hypothesis.py matrix --tag lot14a --boot 400
  python exp_lot_hypothesis.py sessions --tags lot14a,lot14c,lot15 --boot 400
"""
import argparse
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from twin_probe import load, REF_MAC          # noqa: E402
from rff.discriminator import Discriminator    # noqa: E402
from rff_offline import feature                # noqa: E402

# docs/HANDOFF.md "Hardware inventory (2026-07-15)". These are the three
# ESP32 D0WD TX beacons whose lot identity is in question.
BEACONS = ["a4:f0:0f:77:91:20", "28:05:a5:2f:fa:48", "f4:2d:c9:70:72:30"]

# The recorded clock-twin yardstick, docs/TWIN_INVESTIGATION.md 3 /
# docs/HANDOFF.md "Measured results".
TWIN_SIGMA = 0.26
TWIN_DSFO = 0.00080
SEPARABLE_SIGMA = 3.0     # the project's own rule of thumb


# ------------------------------------------------------------------ feats

def feats_mode(blob, mac, mode):
    """(CFO, SFO) windows for one source.

    mode='ref'  reference-corrected, i.e. exactly what rff_offline.report()
                and twin_probe use when a --ref-mac was configured. This is
                the space the published 1.8-2.7 sigma figure lives in.
    mode='raw'  the uncorrected estimator output from the same observation
                dicts. docs/HANDOFF.md records that reference subtraction
                does NOT help within-session same-model separation, and
                docs/WINDOW_CONVERGENCE.md ran raw, so both are reported.
    """
    obs = blob["by_mac"].get(mac, [])
    if mode == "ref":
        return [f for f in (feature(o, True) for o in obs) if f is not None]
    out = []
    for o in obs:
        c, s = o.get("cfo"), o.get("sfo")
        if c is not None and s is not None:
            out.append(np.array([float(c), float(s)]))
    return out


def pool_of(blob, macs, mode, train_frac=1.0):
    pool = {}
    for m in macs:
        fs = feats_mode(blob, m, mode)
        if train_frac < 1.0:
            fs = fs[:max(int(len(fs) * train_frac), 1)]
        pool[m] = np.array(fs) if fs else np.empty((0, 2))
    return pool


def sep_from_pool(pool):
    disc = Discriminator()
    for m, a in pool.items():
        for f in a:
            disc.learn(m, f)
    return disc.separation_matrix()


def bootstrap_pairs(pool, n_boot, seed=0):
    """Resample each source's windows -> distribution of pairwise sigma.

    A separation quoted without its sampling uncertainty is this project's
    logged failure mode A. Resampling is per-source with replacement at the
    source's own n, which propagates the very different window counts the
    three beacons contribute.
    """
    rng = np.random.default_rng(seed)
    per = defaultdict(list)
    for _ in range(n_boot):
        boot = {}
        for m, a in pool.items():
            if len(a) < 2:
                continue
            boot[m] = a[rng.integers(0, len(a), size=len(a))]
        ids, sep = sep_from_pool(boot)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                per[tuple(sorted((ids[i], ids[j])))].append(sep[i][j])
    return per


def axis_stats(pool, macs):
    """Pooled per-axis sd, so dCFO/dSFO can be read in units and in d."""
    sd = {}
    for ax, name in ((0, "cfo"), (1, "sfo")):
        num = den = 0.0
        for m in macs:
            a = pool[m]
            if len(a) < 2:
                continue
            num += a[:, ax].var(ddof=1) * (len(a) - 1)
            den += len(a) - 1
        sd[name] = float(np.sqrt(num / max(den, 1.0)))
    return sd


# ---------------------------------------------------------------- overlap

def read_times(path, macs):
    """pc_time_us per MAC, straight from the CSV. Read-only, one pass.

    Only the first ten comma-separated fields are split, so the long quoted
    csi_data column is never parsed -- this is a timeline test, not a DSP
    test.
    """
    want = {m.lower() for m in macs}
    out = {m: [] for m in want}
    with open(path, newline="", errors="replace") as f:
        head = f.readline().rstrip("\n").split(",")
        try:
            i_t, i_m = head.index("pc_time_us"), head.index("mac")
        except ValueError:
            raise SystemExit(f"{path}: unexpected header {head[:6]}")
        n = max(i_t, i_m) + 1
        for line in f:
            p = line.split(",", n)
            if len(p) <= n:
                continue
            m = p[i_m].lower()
            if m in want:
                try:
                    out[m].append(int(p[i_t]))
                except ValueError:
                    continue
    return {m: np.array(sorted(v), dtype=np.int64) for m, v in out.items()}


def cmd_overlap(args):
    macs = [m.strip().lower() for m in args.macs.split(",")]
    for path in args.csvs:
        t = read_times(path, macs)
        present = [m for m in macs if len(t[m]) > 1]
        print(f"\n=== {os.path.basename(path)} ===")
        print(f"{'source':<20}{'frames':>10}{'first_s':>12}{'last_s':>12}"
              f"{'span_s':>10}{'fps':>8}")
        t0g = min(t[m][0] for m in present) if present else 0
        for m in macs:
            a = t[m]
            if len(a) < 2:
                print(f"{m:<20}{len(a):>10}   (absent / <2 frames)")
                continue
            span = (a[-1] - a[0]) * 1e-6
            print(f"{m:<20}{len(a):>10}{(a[0]-t0g)*1e-6:>12.1f}"
                  f"{(a[-1]-t0g)*1e-6:>12.1f}{span:>10.1f}"
                  f"{len(a)/max(span,1e-9):>8.1f}")
        if len(present) < 2:
            print("fewer than two sources on air -- no overlap to measure")
            continue

        lo = max(t[m][0] for m in present)
        hi = min(t[m][-1] for m in present)
        print(f"\nmutual on-air window (all {len(present)} present): "
              f"{(hi-lo)*1e-6:.1f} s = {(hi-lo)*1e-6/60:.1f} min")

        # co-presence: bins in which EVERY present source has a frame.
        bs = int(args.bin_s * 1e6)
        nb = max(int((hi - lo) // bs), 1)
        edges = lo + np.arange(nb + 1) * bs
        occ = []
        for m in present:
            a = t[m]
            a = a[(a >= lo) & (a < edges[-1])]
            occ.append(np.histogram(a, bins=edges)[0] > 0)
        allthree = np.logical_and.reduce(occ)
        print(f"{args.bin_s:g}s bins in the mutual window: {nb}; "
              f"bins containing a frame from every source: "
              f"{allthree.sum()} = {allthree.mean():.2%}")

        # nearest-neighbour frame proximity, pair by pair
        print(f"\n{'pair':<44}{'p50 ms':>10}{'p90 ms':>10}{'p99 ms':>10}"
              f"{'max ms':>10}")
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                a, b = t[present[i]], t[present[j]]
                a = a[(a >= lo) & (a <= hi)]
                if not len(a):
                    continue
                idx = np.searchsorted(b, a)
                idx = np.clip(idx, 1, len(b) - 1)
                d = np.minimum(np.abs(a - b[idx]), np.abs(a - b[idx - 1]))
                d = d * 1e-3
                nm = f"{present[i][-8:]} vs {present[j][-8:]}"
                print(f"{nm:<44}{np.percentile(d,50):>10.2f}"
                      f"{np.percentile(d,90):>10.2f}"
                      f"{np.percentile(d,99):>10.2f}{d.max():>10.2f}")
    return 0


# ----------------------------------------------------------------- matrix

def one_matrix(tag, macs, mode, boot, min_windows, train_frac, seed=0):
    blob = load(tag)
    pool = pool_of(blob, macs, mode, train_frac)
    usable = [m for m in macs if len(pool[m]) >= min_windows]
    pool = {m: pool[m] for m in usable}
    if len(usable) < 2:
        return blob, pool, usable, [], {}, {}
    ids, sep = sep_from_pool(pool)
    bt = bootstrap_pairs(pool, boot, seed) if boot else {}
    sd = axis_stats(pool, usable)
    pairs = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            key = tuple(sorted((ids[i], ids[j])))
            b = bt.get(key, [])
            lo, hi = (np.percentile(b, [2.5, 97.5]) if len(b)
                      else (float("nan"), float("nan")))
            a1, a2 = pool[ids[i]], pool[ids[j]]
            pairs.append(dict(a=ids[i], b=ids[j], sigma=float(sep[i][j]),
                              lo=float(lo), hi=float(hi),
                              dcfo=float(a1[:, 0].mean() - a2[:, 0].mean()),
                              dsfo=float(a1[:, 1].mean() - a2[:, 1].mean())))
    for p in pairs:
        p["dcfo_d"] = abs(p["dcfo"]) / sd["cfo"] if sd["cfo"] else float("nan")
        p["dsfo_d"] = abs(p["dsfo"]) / sd["sfo"] if sd["sfo"] else float("nan")
    pairs.sort(key=lambda p: p["sigma"])
    return blob, pool, usable, pairs, sd, dict(ids=ids, sep=sep)


def print_signatures(pool, usable, blob):
    print(f"\n{'source':<20}{'wins':>7}{'CFO mean':>11}{'CFO sd':>10}"
          f"{'SFO mean':>12}{'SFO sd':>11}{'SFO IQR':>11}{'RSSI':>8}")
    for m in usable:
        a = pool[m]
        obs = blob["by_mac"].get(m, [])
        rssi = np.mean([o["rssi"] for o in obs]) if obs else float("nan")
        iqr = np.subtract(*np.percentile(a[:, 1], [75, 25]))
        print(f"{m:<20}{len(a):>7}{a[:,0].mean():>+11.2f}{a[:,0].std():>10.2f}"
              f"{a[:,1].mean():>+12.5f}{a[:,1].std():>11.5f}{iqr:>11.5f}"
              f"{rssi:>8.1f}")


def verdict_line(pairs):
    if not pairs:
        return "no verdict: fewer than two characterizable sources"
    sig = [p["sigma"] for p in pairs]
    dsfo = [abs(p["dsfo"]) for p in pairs]
    at_twin = [s <= 2 * TWIN_SIGMA and d <= 3 * TWIN_DSFO
               for s, d in zip(sig, dsfo)]
    if all(at_twin):
        return ("STRONG hypothesis SUPPORTED: every pair sits at the "
                "recorded clock-twin scale")
    if all(s < SEPARABLE_SIGMA for s in sig):
        return ("STRONG hypothesis REFUTED, WEAK form holds: all pairs "
                f"below {SEPARABLE_SIGMA:g} sigma but not all at twin scale "
                f"(twin scale = {TWIN_SIGMA:g} sigma / {TWIN_DSFO:.5f} "
                "rad/sc)")
    return ("Hypothesis REFUTED: at least one pair separates at or above "
            f"{SEPARABLE_SIGMA:g} sigma")


def cmd_matrix(args):
    macs = [m.strip().lower() for m in args.macs.split(",")]
    for mode in (["ref", "raw"] if args.mode == "both" else [args.mode]):
        blob, pool, usable, pairs, sd, mat = one_matrix(
            args.tag, macs, mode, args.boot, args.min_windows,
            args.train_frac, args.seed)
        print(f"\n{'='*72}")
        print(f"tag={args.tag}  mode={mode}  window={blob['window']}  "
              f"ref_mac={blob['ref_mac']}  train_frac={args.train_frac}")
        print(f"sessions: {', '.join(sorted({os.path.basename(p) for p in blob['paths']}))}")
        print(f"{'='*72}")
        if len(usable) < 2:
            print(f"only {len(usable)} source(s) with >= {args.min_windows} "
                  f"windows: {usable} -- no matrix")
            continue
        print_signatures(pool, usable, blob)
        print(f"\n--- pairwise separation matrix (sigma, pooled cov over "
              f"these {len(usable)} sources only) ---")
        ids, sep = mat["ids"], mat["sep"]
        short = [i[-8:] for i in ids]
        print(f"{'':>10}" + "".join(f"{s:>10}" for s in short))
        for a in range(len(ids)):
            print(f"{short[a]:>10}" + "".join(
                f"{sep[a][b]:>10.2f}" if b != a else f"{'-':>10}"
                for b in range(len(ids))))
        print(f"\n--- pairs, closest first (bootstrap 95% CI, "
              f"{args.boot} resamples) ---")
        print(f"{'pair':<42}{'sigma':>8}{'95% CI':>18}{'dCFO Hz':>10}"
              f"{'dSFO rad/sc':>14}{'CFO d':>8}{'SFO d':>8}")
        for p in pairs:
            nm = f"{p['a'][-8:]} vs {p['b'][-8:]}"
            ci = f"[{p['lo']:.2f}, {p['hi']:.2f}]"
            print(f"{nm:<42}{p['sigma']:>8.2f}{ci:>18}{p['dcfo']:>+10.2f}"
                  f"{p['dsfo']:>+14.5f}{p['dcfo_d']:>8.2f}{p['dsfo_d']:>8.2f}")
        print(f"\npooled sd: CFO {sd['cfo']:.3f} Hz, "
              f"SFO {sd['sfo']:.5f} rad/sc")
        print(f"yardsticks: recorded clock twin {TWIN_SIGMA:g} sigma / "
              f"dSFO {TWIN_DSFO:.5f} rad/sc; "
              f"project separability line {SEPARABLE_SIGMA:g} sigma")
        print(f"\nVERDICT ({mode}): {verdict_line(pairs)}")
    return 0


# --------------------------------------------------------------- sessions

def cmd_sessions(args):
    macs = [m.strip().lower() for m in args.macs.split(",")]
    tags = [t.strip() for t in args.tags.split(",")]
    for mode in (["ref", "raw"] if args.mode == "both" else [args.mode]):
        print(f"\n=== replication across sessions, mode={mode} "
              f"(bootstrap 95% CI, {args.boot} resamples) ===")
        print(f"{'tag':<9}{'session':<26}{'pair':<24}{'wins a/b':>14}"
              f"{'sigma':>8}{'95% CI':>18}{'dSFO rad/sc':>14}")
        allrows = defaultdict(list)
        for tag in tags:
            blob, pool, usable, pairs, sd, _ = one_matrix(
                tag, macs, mode, args.boot, args.min_windows,
                args.train_frac, args.seed)
            sess = ",".join(sorted({os.path.basename(p)[:-4]
                                    for p in blob["paths"]}))
            if len(pairs) == 0:
                print(f"{tag:<9}{sess[:25]:<26}"
                      f"(only {len(usable)} characterizable source(s))")
                continue
            for p in pairs:
                nm = f"{p['a'][-8:]} vs {p['b'][-8:]}"
                ci = f"[{p['lo']:.2f}, {p['hi']:.2f}]"
                na, nb = len(pool[p['a']]), len(pool[p['b']])
                print(f"{tag:<9}{sess[:25]:<26}{nm:<24}"
                      f"{f'{na}/{nb}':>14}{p['sigma']:>8.2f}{ci:>18}"
                      f"{p['dsfo']:>+14.5f}")
                allrows[nm].append((p["sigma"], p["dsfo"]))
        print(f"\n--- per-pair summary across {len(tags)} session(s) ---")
        print(f"{'pair':<24}{'n sess':>8}{'sigma min':>11}{'median':>10}"
              f"{'max':>10}{'|dSFO| med':>13}{'x twin scale':>14}")
        for nm, rows in sorted(allrows.items(),
                               key=lambda kv: np.median([r[0]
                                                         for r in kv[1]])):
            s = np.array([r[0] for r in rows])
            d = np.abs([r[1] for r in rows])
            print(f"{nm:<24}{len(rows):>8}{s.min():>11.2f}"
                  f"{np.median(s):>10.2f}{s.max():>10.2f}"
                  f"{np.median(d):>13.5f}{np.median(d)/TWIN_DSFO:>13.1f}x")
    return 0


# -------------------------------------------------------------- stability

def cmd_stability(args):
    """Within-session temporal stability of each pair's dSFO.

    A pairwise separation is only a statement about two crystals if it
    holds still. docs/HANDOFF.md already records that clock signatures
    wander thermally (a pair moved 2.7 sigma -> 1.3 sigma inside one
    session), so before any pairwise number is read as a lot signal, the
    wander has to be measured on the same data, not assumed away.

    Each source's windows are cut into `--chunks` consecutive equal-count
    blocks; the pair statistics are recomputed inside each block.
    """
    macs = [m.strip().lower() for m in args.macs.split(",")]
    for tag in [t.strip() for t in args.tags.split(",")]:
        blob = load(tag)
        sess = ",".join(sorted({os.path.basename(p)[:-4]
                                for p in blob["paths"]}))
        full = pool_of(blob, macs, args.mode)
        usable = [m for m in macs if len(full[m]) >= args.chunks * 5]
        print(f"\n=== {tag} ({sess}) mode={args.mode}, "
              f"{args.chunks} consecutive chunks ===")
        if len(usable) < 2:
            print(f"  only {len(usable)} source(s) with enough windows")
            continue
        rows = defaultdict(list)
        for k in range(args.chunks):
            pool = {}
            for m in usable:
                a = full[m]
                lo = len(a) * k // args.chunks
                hi = len(a) * (k + 1) // args.chunks
                pool[m] = a[lo:hi]
            ids, sep = sep_from_pool(pool)
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    nm = f"{ids[i][-8:]} vs {ids[j][-8:]}"
                    ds = float(pool[ids[i]][:, 1].mean()
                               - pool[ids[j]][:, 1].mean())
                    rows[nm].append((k, float(sep[i][j]), ds))
        print(f"{'pair':<24}" + "".join(f"{'c'+str(k):>9}"
                                        for k in range(args.chunks))
              + f"{'sigma rng':>11}")
        for nm, r in rows.items():
            s = [x[1] for x in r]
            print(f"{nm:<24}" + "".join(f"{v:>9.2f}" for v in s)
                  + f"{max(s)-min(s):>11.2f}")
        print(f"{'  (dSFO rad/sc)':<24}")
        for nm, r in rows.items():
            d = [x[2] for x in r]
            print(f"{nm:<24}" + "".join(f"{v:>+9.5f}" for v in d)
                  + f"{max(d)-min(d):>11.5f}")
    return 0


# --------------------------------------------------------------- variance

def cmd_variance(args):
    """Between-unit vs within-unit-across-session variance of SFO.

    The lot hypothesis is a claim about *between-unit* spread being small.
    That is only meaningful relative to how much a single unit's own
    signature moves between sessions. This computes both from the same
    windows:

      between  sd over the three units of (that unit's grand mean SFO)
      within   for each unit, sd over sessions of its per-session mean SFO

    If within >= between, no unit holds a position of its own across
    sessions and no pairwise separation measured in one session
    generalizes -- which is a statement about the measurement, not about
    the crystals.
    """
    macs = [m.strip().lower() for m in args.macs.split(",")]
    tags = [t.strip() for t in args.tags.split(",")]
    per = defaultdict(dict)          # mac -> tag -> mean SFO
    for tag in tags:
        blob = load(tag)
        pool = pool_of(blob, macs, args.mode)
        for m in macs:
            if len(pool[m]) >= args.min_windows:
                per[m][tag] = float(pool[m][:, 1].mean())
    print(f"\n=== per-session mean SFO (rad/sc), mode={args.mode} ===")
    print(f"{'tag':<10}" + "".join(f"{m[-8:]:>12}" for m in macs))
    for tag in tags:
        print(f"{tag:<10}" + "".join(
            f"{per[m][tag]:>+12.5f}" if tag in per[m] else f"{'-':>12}"
            for m in macs))
    print(f"\n{'source':<20}{'n sess':>8}{'grand mean':>13}"
          f"{'across-sess sd':>16}{'range':>11}")
    gm, wsd = {}, {}
    for m in macs:
        v = np.array(list(per[m].values()))
        if len(v) < 2:
            continue
        gm[m] = float(v.mean())
        wsd[m] = float(v.std(ddof=1))
        print(f"{m:<20}{len(v):>8}{v.mean():>+13.5f}{v.std(ddof=1):>16.5f}"
              f"{v.max()-v.min():>11.5f}")
    if len(gm) >= 2:
        b = float(np.std(list(gm.values()), ddof=1))
        w = float(np.mean(list(wsd.values())))
        print(f"\nbetween-unit sd of grand means : {b:.5f} rad/sc")
        print(f"mean within-unit across-session sd: {w:.5f} rad/sc")
        print(f"ratio within/between            : {w/b:.2f}")
        print("ratio >= 1 means a unit's own session-to-session wander is "
              "as large as the spread between units")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("overlap")
    o.add_argument("csvs", nargs="+")
    o.add_argument("--macs", default=",".join(BEACONS))
    o.add_argument("--bin-s", type=float, default=10.0)
    o.set_defaults(fn=cmd_overlap)

    m = sub.add_parser("matrix")
    m.add_argument("--tag", required=True)
    m.add_argument("--macs", default=",".join(BEACONS))
    m.add_argument("--mode", choices=("ref", "raw", "both"), default="both")
    m.add_argument("--boot", type=int, default=400)
    m.add_argument("--min-windows", type=int, default=5)
    m.add_argument("--train-frac", type=float, default=1.0)
    m.add_argument("--seed", type=int, default=0)
    m.set_defaults(fn=cmd_matrix)

    s = sub.add_parser("sessions")
    s.add_argument("--tags", required=True)
    s.add_argument("--macs", default=",".join(BEACONS))
    s.add_argument("--mode", choices=("ref", "raw", "both"), default="both")
    s.add_argument("--boot", type=int, default=400)
    s.add_argument("--min-windows", type=int, default=5)
    s.add_argument("--train-frac", type=float, default=1.0)
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(fn=cmd_sessions)

    st = sub.add_parser("stability")
    st.add_argument("--tags", required=True)
    st.add_argument("--macs", default=",".join(BEACONS))
    st.add_argument("--mode", choices=("ref", "raw"), default="ref")
    st.add_argument("--chunks", type=int, default=6)
    st.set_defaults(fn=cmd_stability)

    v = sub.add_parser("variance")
    v.add_argument("--tags", required=True)
    v.add_argument("--macs", default=",".join(BEACONS))
    v.add_argument("--mode", choices=("ref", "raw"), default="ref")
    v.add_argument("--min-windows", type=int, default=5)
    v.set_defaults(fn=cmd_variance)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
