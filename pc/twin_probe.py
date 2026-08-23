#!/usr/bin/env python3
r"""Twin probe: search the 2026-07-13 captures for the *phenomenon* of a
clock twin, rather than for a MAC address.

Read-only. Writes nothing into data/, pc/rff/, pc/occ/ or site/.

Why this exists
---------------
A previous investigation asked "is f4:2d:c9:70:72:30 in the 07-13 data?",
found the string absent, and concluded the twin is not there. That test is
invalid on this project's own premise: a MAC is not an identity. The
hardware inventory that names that MAC is dated 07-15; the captures are
07-13. A unit reflashed or reconfigured in between changes address and a
string search cannot follow it.

So this tool asks the physical question instead: in the single-receiver
(desk-only) 07-13 data, are there two or more transmitting sources whose
(CFO, SFO) clock signatures are statistically inseparable?

Method
------
The DSP is NOT reimplemented here. `collect_observations` and `feature`
are imported directly from `rff_offline` so that every number this tool
prints comes out of the same FrameEstimator / WindowAggregator /
ReferenceNormalizer / Discriminator path the project's own science run
uses. This file only adds bookkeeping: caching, pair ranking, bootstrap
spreads, transmit-timing statistics, and cross-epoch signature matching.

Subcommands
-----------
  collect   replay a set of CSVs -> cached per-source observations
  sep       per-source signatures + full pairwise separation matrix,
            ranked closest-pair-first, with bootstrap CIs
  holdout   blind chronological train/test classification (reproduces the
            headline accuracy number under a stated condition)
  timing    transmit-cadence / regularity profile of a source: is this a
            configured beacon or a passing consumer device?
  match     compare every source in one epoch against every source in
            another epoch in clock-signature space -- the test for "same
            physical device under a different address"

Usage
-----
  python pc/twin_probe.py collect --tag desk0713 "data/raw/desk_20260713_*.csv"
  python pc/twin_probe.py sep --tag desk0713
  python pc/twin_probe.py timing --tag desk0713 --mac 84:7b:57:cc:20:0e
  python pc/twin_probe.py match --tag-a desk0713 --tag-b rx0714
"""
import argparse
import csv as csvmod
import glob
import json
import os
import pickle
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rff_offline import collect_observations, feature, TRAIN_FRACTION
from rff.discriminator import Discriminator, CHI2_95, CHI2_99

REF_MAC = "a4:f0:0f:77:91:20"

# cache lives outside the repo data tree on purpose: another experiment is
# running against data/cache/expwin and must not be raced.
CACHE_DIR = os.environ.get(
    "TWIN_PROBE_CACHE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "..", "twin_probe_cache"))


def shard_path(tag, path):
    return os.path.join(os.path.abspath(CACHE_DIR),
                        f"{tag}__{os.path.basename(path)}.pkl")


# ---------------------------------------------------------------- collect

def cmd_collect(args):
    """Replay CSVs one file at a time, one cache shard per file.

    Sharded and resumable on purpose: rff_offline already resets estimator
    and reference state per file (the ESP clock and the unwrap anchor do
    not survive a session boundary), so per-file collection is not an
    approximation of the whole-set run -- it is the identical computation,
    just checkpointed. Re-running skips shards that already exist.
    """
    paths = sorted({p for pat in args.csvs for p in glob.glob(pat)})
    paths = [p for p in paths if os.path.getsize(p) > 0]
    if not paths:
        print("no non-empty CSV matched", file=sys.stderr)
        return 1
    os.makedirs(os.path.abspath(CACHE_DIR), exist_ok=True)
    done = 0
    for p in paths:
        sp = shard_path(args.tag, p)
        if os.path.exists(sp) and not args.force:
            done += 1
            continue
        by_mac = collect_observations([p], args.window, args.ref_mac)
        with open(sp + ".tmp", "wb") as f:
            pickle.dump({"by_mac": dict(by_mac), "path": p,
                         "window": args.window, "ref_mac": args.ref_mac}, f)
        os.replace(sp + ".tmp", sp)
        done += 1
        print(f"  [{done}/{len(paths)}] shard {os.path.basename(sp)}: "
              f"{sum(len(v) for v in by_mac.values())} windows",
              file=sys.stderr)
        if args.max_files and done >= args.max_files:
            break
    remaining = [p for p in paths if not os.path.exists(shard_path(args.tag, p))]
    print(f"tag '{args.tag}': {len(paths)-len(remaining)}/{len(paths)} "
          f"shards present; {len(remaining)} remaining")
    return 0


def load(tag):
    """Merge every shard for a tag (or comma-separated tags).

    Merging several tags reproduces what rff_offline does when handed
    files from more than one receiver: windows carrying the same source
    MAC land in one source model regardless of which node heard them.
    """
    shards = []
    for t in tag.split(","):
        shards += glob.glob(os.path.join(os.path.abspath(CACHE_DIR),
                                         f"{t.strip()}__*.pkl"))
    shards.sort(key=os.path.basename)
    if not shards:
        raise SystemExit(f"no cache shards for tag '{tag}' in {CACHE_DIR}")
    by_mac = defaultdict(list)
    paths, window, ref_mac = [], None, None
    for s in shards:
        with open(s, "rb") as f:
            d = pickle.load(f)
        window, ref_mac = d["window"], d["ref_mac"]
        paths.append(d["path"])
        for m, obs in d["by_mac"].items():
            by_mac[m].extend(obs)
    # NOTE: deliberately NOT re-sorted by wall-clock. rff_offline replays
    # sorted(paths), so in a two-receiver run every desk_* window precedes
    # every node3_* window for the same source. The chronological 60/40
    # holdout split inherits that order, and re-sorting by timestamp here
    # would silently change which windows train and which test.
    return {"by_mac": dict(by_mac), "paths": paths, "window": window,
            "ref_mac": ref_mac}


def feats_of(blob, mac):
    ref = bool(blob["ref_mac"])
    return [f for f in (feature(o, ref) for o in blob["by_mac"][mac])
            if f is not None]


def eligible(blob, min_windows):
    return sorted(m for m, o in blob["by_mac"].items()
                  if len(o) >= min_windows)


# -------------------------------------------------------------------- sep

def build_disc(blob, macs, frac=1.0):
    """Learn a model per source from the first `frac` of its windows."""
    disc = Discriminator()
    used = {}
    for m in macs:
        fs = feats_of(blob, m)
        cut = max(int(len(fs) * frac), 1) if frac < 1.0 else len(fs)
        used[m] = fs[:cut]
        for f in used[m]:
            disc.learn(m, f)
    return disc, used


def bootstrap_sep(blob, macs, n_boot, seed=0, frac=1.0):
    """Resample each source's windows -> distribution of pairwise sigma.

    Reports a spread, not a single estimate: a separation quoted without
    its sampling uncertainty is the failure mode this project logs as
    'prediction printed as measurement'.
    """
    rng = np.random.default_rng(seed)
    per_pair = defaultdict(list)
    pool = {}
    for m in macs:
        fs = feats_of(blob, m)
        cut = max(int(len(fs) * frac), 1) if frac < 1.0 else len(fs)
        pool[m] = np.array(fs[:cut])
    for _ in range(n_boot):
        disc = Discriminator()
        for m in macs:
            a = pool[m]
            if len(a) < 2:
                continue
            idx = rng.integers(0, len(a), size=len(a))
            for f in a[idx]:
                disc.learn(m, f)
        ids, sep = disc.separation_matrix()
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                per_pair[(ids[i], ids[j])].append(sep[i][j])
    return per_pair


def cmd_sep(args):
    blob = load(args.tag)
    macs = eligible(blob, args.min_windows)
    dropped = sorted(set(blob["by_mac"]) - set(macs))
    print(f"tag={args.tag}  window={blob['window']}  "
          f"ref_mac={blob['ref_mac']}")
    print(f"{len(blob['by_mac'])} sources seen, {len(macs)} with "
          f">= {args.min_windows} windows; dropped {len(dropped)}")

    print("\n=== per-source clock signature ===")
    hdr = (f"{'source':<20}{'wins':>6}{'sess':>6}{'CFO med':>11}"
           f"{'CFO IQR':>10}{'CFO p5..p95':>20}"
           f"{'SFO med':>12}{'SFO IQR':>11}{'RSSI':>8}")
    print(hdr)
    stats = {}
    for m in macs:
        a = np.array(feats_of(blob, m))
        if not len(a):
            continue
        obs = blob["by_mac"][m]
        rssi = np.mean([o["rssi"] for o in obs])
        sess = len({o["session"] for o in obs})
        c, s = a[:, 0], a[:, 1]
        ciqr = np.subtract(*np.percentile(c, [75, 25]))
        siqr = np.subtract(*np.percentile(s, [75, 25]))
        stats[m] = dict(n=len(a), sess=sess, cfo=float(np.median(c)),
                        sfo=float(np.median(s)), cfo_iqr=float(ciqr),
                        sfo_iqr=float(siqr), rssi=float(rssi))
        print(f"{m:<20}{len(a):>6}{sess:>6}{np.median(c):>+11.2f}"
              f"{ciqr:>10.2f}"
              f"{f'{np.percentile(c,5):+.1f}..{np.percentile(c,95):+.1f}':>20}"
              f"{np.median(s):>+12.5f}{siqr:>11.5f}{rssi:>8.1f}")

    # rff_offline prints its separation matrix from the *training* 60% of
    # each source (report() learns only train[mac] before calling
    # separation_matrix). --train-frac 0.6 reproduces that number exactly;
    # the default 1.0 uses every window, which is the better estimate of
    # the true separation and is what the pair rankings below use.
    disc, _ = build_disc(blob, macs, frac=args.train_frac)
    ids, sep = disc.separation_matrix()
    if args.train_frac < 1.0:
        print(f"\n(models built from the first {args.train_frac:.0%} of each "
              f"source's windows, matching rff_offline.report())")
    if len(ids) < 2:
        print("\n(need >= 2 characterized sources)")
        return 0

    print("\n=== full pairwise separation matrix (sigma, pooled cov) ===")
    short = [i[-8:] for i in ids]
    print(f"{'':>10}" + "".join(f"{s:>10}" for s in short))
    for a in range(len(ids)):
        print(f"{short[a]:>10}" + "".join(
            f"{sep[a][b]:>10.2f}" if b != a else f"{'-':>10}"
            for b in range(len(ids))))

    boot = (bootstrap_sep(blob, macs, args.boot, frac=args.train_frac)
            if args.boot else {})
    pairs = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            b = boot.get((ids[i], ids[j]), [])
            lo, hi = (np.percentile(b, [2.5, 97.5]) if len(b) else
                      (float("nan"), float("nan")))
            pairs.append((sep[i][j], ids[i], ids[j], lo, hi))
    pairs.sort()
    print(f"\n=== closest pairs (bootstrap 95% CI over "
          f"{args.boot} resamples) ===")
    print(f"{'sigma':>8}{'  95% CI':>20}   pair")
    for d, a, b, lo, hi in pairs[:args.top]:
        print(f"{d:>8.2f}{f'[{lo:.2f}, {hi:.2f}]':>20}   {a}  vs  {b}")
    off = np.array([p[0] for p in pairs])
    print(f"\nmin {off.min():.2f}sigma   median {np.median(off):.2f}sigma   "
          f"max {off.max():.2f}sigma   "
          f"(project rule of thumb: >3sigma reliably separable)")
    print(f"pairs below 3sigma: {(off < 3).sum()} / {len(off)}")

    # ---- per-axis decomposition ----------------------------------------
    # A single pooled-Mahalanobis sigma hides which crystal property is
    # doing the work. It matters here because CFO is aliased by the
    # source's own transmit cadence (a 100 Hz beacon and a 2.4 Hz beacon
    # are not measured in the same band), while SFO is not. If a pair's
    # separation lives entirely in CFO, it may be a cadence artifact
    # rather than a crystal difference.
    print("\n=== per-axis separation (|dmean| / pooled sd of that axis) ===")
    print(f"{'pair':<44}{'CFO d':>9}{'SFO d':>9}{'dCFO Hz':>11}"
          f"{'dSFO rad/sc':>14}")
    pooled_sd = {}
    for ax, name in ((0, "cfo"), (1, "sfo")):
        num = den = 0.0
        for m in macs:
            a = np.array(feats_of(blob, m))
            if len(a) < 2:
                continue
            num += a[:, ax].var(ddof=1) * (len(a) - 1)
            den += len(a) - 1
        pooled_sd[name] = float(np.sqrt(num / max(den, 1)))
    for d, a, b, lo, hi in pairs[:args.top]:
        fa, fb = np.array(feats_of(blob, a)), np.array(feats_of(blob, b))
        dc = float(fa[:, 0].mean() - fb[:, 0].mean())
        ds = float(fa[:, 1].mean() - fb[:, 1].mean())
        print(f"{a[-8:]+' vs '+b[-8:]:<44}"
              f"{abs(dc)/pooled_sd['cfo']:>9.2f}"
              f"{abs(ds)/pooled_sd['sfo']:>9.2f}{dc:>+11.2f}{ds:>+14.5f}")
    print(f"pooled sd: CFO {pooled_sd['cfo']:.3f} Hz, "
          f"SFO {pooled_sd['sfo']:.5f} rad/sc")
    print("HANDOFF's stated true-twin scale for reference: "
          "0.0004 rad/sc apart, 0.3 sigma")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"tag": args.tag, "stats": stats,
                       "ids": ids, "sep": sep.tolist(),
                       "pairs": [[float(d), a, b, float(lo), float(hi)]
                                 for d, a, b, lo, hi in pairs]}, f, indent=1)
        print(f"\nwrote {args.json}")
    return 0


# ---------------------------------------------------------------- holdout

def cmd_holdout(args):
    blob = load(args.tag)
    macs = eligible(blob, args.min_windows)
    if args.only:
        keep = {m.strip().lower() for m in args.only.split(",")}
        macs = [m for m in macs if m in keep]
    if args.exclude:
        drop = {m.strip().lower() for m in args.exclude.split(",")}
        macs = [m for m in macs if m not in drop]
    disc = Discriminator()
    test = {}
    for m in macs:
        fs = feats_of(blob, m)
        cut = max(int(len(fs) * TRAIN_FRACTION), 1)
        test[m] = fs[cut:]
        for f in fs[:cut]:
            disc.learn(m, f)
    total = correct = strangers = 0
    print(f"=== blind holdout ({TRAIN_FRACTION:.0%}/"
          f"{1-TRAIN_FRACTION:.0%} chronological), {len(macs)} sources ===")
    for m in macs:
        ok = st = 0
        preds = defaultdict(int)
        for f in test[m]:
            best, d2, verdict = disc.classify(f)
            if verdict == "UNSCORED":
                continue
            total += 1
            if verdict == "STRANGER":
                st += 1
                strangers += 1
            elif best == m:
                ok += 1
                correct += 1
            else:
                preds[best] += 1
        conf = ", ".join(f"{k}x{v}" for k, v in
                         sorted(preds.items(), key=lambda kv: -kv[1]))
        print(f"{m:<20}{len(test[m]):>6} test  correct {ok:>5}  "
              f"stranger {st:>4}" + (f"  confused-> {conf}" if conf else ""))
    if total:
        print(f"\naccuracy {correct}/{total} = {correct/total:.2%}  "
              f"(strangers {strangers}; chi2_95={CHI2_95} "
              f"chi2_99={CHI2_99})")
    return 0


# ----------------------------------------------------------------- timing

def cmd_timing(args):
    """Transmit cadence of one source, straight from the CSV timestamps."""
    blob = load(args.tag)
    target = args.mac.lower()
    per_file = []
    allgaps = []
    for p in blob["paths"]:
        ts, rssi, seqs, chans, lens = [], [], [], [], []
        with open(p, newline="", errors="replace") as f:
            for row in csvmod.DictReader(f):
                if row.get("mac", "").lower() != target:
                    continue
                try:
                    ts.append(int(row["pc_time_us"]))
                    rssi.append(int(row["rssi"]))
                    seqs.append(int(row["seq"]))
                    chans.append(int(row["channel"]))
                    lens.append(int(row["len"]))
                except (KeyError, ValueError):
                    continue
        if len(ts) < 2:
            continue
        t = np.array(sorted(ts), dtype=np.float64) * 1e-6
        g = np.diff(t)
        allgaps.append(g)
        per_file.append((os.path.basename(p), len(t), t[-1] - t[0],
                         np.median(g), np.percentile(g, 5),
                         np.percentile(g, 95), np.mean(rssi),
                         np.std(rssi), len(set(chans)),
                         sorted(set(lens))[:4],
                         np.mean(np.diff(sorted(seqs)) == 1)))
    if not per_file:
        print(f"{target}: fewer than 2 frames anywhere in tag {args.tag}")
        return 0
    print(f"=== transmit profile: {target}  (tag {args.tag}) ===")
    print(f"{'session':<32}{'frames':>8}{'span_s':>9}{'gap med':>10}"
          f"{'gap p5':>9}{'gap p95':>9}{'RSSI':>8}{'sd':>6}{'chans':>7}"
          f"{'seq+1':>7}  lens")
    for (n, c, span, gm, g5, g95, r, rs, nch, ln, sq) in per_file:
        print(f"{n:<32}{c:>8}{span:>9.0f}{gm:>10.4f}{g5:>9.4f}{g95:>9.4f}"
              f"{r:>8.1f}{rs:>6.1f}{nch:>7}{sq:>7.2f}  {ln}")
    g = np.concatenate(allgaps)
    print(f"\npooled: {g.size+len(allgaps)} frames, gap median "
          f"{np.median(g):.4f}s  mean {g.mean():.4f}s  "
          f"cv {g.std()/max(g.mean(),1e-9):.2f}")
    for q in (1, 5, 25, 50, 75, 95, 99):
        print(f"   p{q:<3} gap {np.percentile(g, q):.4f}s")
    frac = float(np.mean(np.abs(g - np.median(g)) < 0.2 * np.median(g)))
    print(f"fraction of inter-frame gaps within +-20% of the median: "
          f"{frac:.1%}")
    return 0


# ------------------------------------------------------------------ match

def cmd_match(args):
    """Cross-epoch signature matching.

    Learns a model per source in epoch A, then scores every epoch-B
    source's windows against them (and vice versa). A B-source whose
    windows land inside an A-source's ellipse is a candidate for being the
    same physical oscillator under a different address.
    """
    A, B = load(args.tag_a), load(args.tag_b)
    amacs = eligible(A, args.min_windows)
    bmacs = eligible(B, args.min_windows)
    if args.a_only:
        amacs = [m for m in amacs
                 if m in {x.strip().lower() for x in args.a_only.split(",")}]
    if args.b_only:
        bmacs = [m for m in bmacs
                 if m in {x.strip().lower() for x in args.b_only.split(",")}]

    print(f"epoch A = {args.tag_a} ({len(amacs)} sources)")
    print(f"epoch B = {args.tag_b} ({len(bmacs)} sources)")

    def centroid(blob, m):
        a = np.array(feats_of(blob, m))
        return a.mean(axis=0), a

    print("\n=== raw centroids (reference-corrected feature space) ===")
    print(f"{'epoch':<3}{'source':<20}{'wins':>6}{'CFO mean':>12}"
          f"{'CFO sd':>10}{'SFO mean':>12}{'SFO sd':>11}")
    cent = {}
    for tagname, blob, ms in (("A", A, amacs), ("B", B, bmacs)):
        for m in ms:
            mu, a = centroid(blob, m)
            cent[(tagname, m)] = (mu, a)
            print(f"{tagname:<3}{m:<20}{len(a):>6}{mu[0]:>+12.2f}"
                  f"{a[:,0].std():>10.2f}{mu[1]:>+12.5f}{a[:,1].std():>11.5f}")

    discA = Discriminator()
    for m in amacs:
        for f in feats_of(A, m):
            discA.learn(m, f)
    discB = Discriminator()
    for m in bmacs:
        for f in feats_of(B, m):
            discB.learn(m, f)

    print("\n=== every B source scored against every A model ===")
    print("(d2 = Mahalanobis^2 of the B centroid in the A model; "
          f"MATCH if <= {CHI2_95})")
    print(f"{'B source':<20}{'A source':<20}{'d2':>12}{'verdict':>10}"
          f"{'B wins in A 95% ellipse':>26}")
    for bm in bmacs:
        mu_b, arr_b = cent[("B", bm)]
        rows = []
        for am in amacs:
            model = discA.models.get(am)
            if model is None or model.n < Discriminator.MIN_CHARACTERIZED:
                continue
            d2 = model.mahalanobis2(mu_b)
            inside = float(np.mean([model.mahalanobis2(f) <= CHI2_95
                                    for f in arr_b]))
            rows.append((d2, am, inside))
        rows.sort()
        for d2, am, inside in rows[:args.top]:
            v = ("MATCH" if d2 <= CHI2_95 else
                 "MARGINAL" if d2 <= CHI2_99 else "no")
            print(f"{bm:<20}{am:<20}{d2:>12.2f}{v:>10}{inside:>25.1%}")
        print()
    return 0


# ------------------------------------------------------------------ drift

def cmd_drift(args):
    """Per-session signature of one source: how far does it wander?

    This bounds the cross-epoch match test. If a source's own SFO moves by
    X across a day, then an X-sized gap between two epochs is not evidence
    of two different crystals. HANDOFF already records that clock
    signatures wander thermally (a pair went 2.7 sigma -> 1.3 sigma inside
    one session), so this has to be measured, not assumed away.
    """
    blob = load(args.tag)
    for mac in [m.strip().lower() for m in args.macs.split(",")]:
        obs = blob["by_mac"].get(mac)
        if not obs:
            print(f"\n{mac}: absent from tag {args.tag}")
            continue
        ref = bool(blob["ref_mac"])
        per = defaultdict(list)
        for o in obs:
            f = feature(o, ref)
            if f is not None:
                per[o["session"]].append(f)
        print(f"\n=== {mac} per-session drift (tag {args.tag}) ===")
        print(f"{'session':<34}{'wins':>6}{'CFO med':>10}{'SFO med':>12}"
              f"{'SFO IQR':>11}")
        meds = []
        for s in sorted(per):
            a = np.array(per[s])
            meds.append(np.median(a[:, 1]))
            print(f"{s:<34}{len(a):>6}{np.median(a[:,0]):>+10.2f}"
                  f"{np.median(a[:,1]):>+12.5f}"
                  f"{np.subtract(*np.percentile(a[:,1],[75,25])):>11.5f}")
        if len(meds) > 1:
            m = np.array(meds)
            print(f"session-to-session SFO median spread: "
                  f"range {m.max()-m.min():.5f} rad/sc, "
                  f"sd {m.std(ddof=1):.5f} rad/sc over {len(m)} sessions")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect")
    c.add_argument("csvs", nargs="+")
    c.add_argument("--tag", required=True)
    c.add_argument("--window", type=int, default=64)
    c.add_argument("--ref-mac", default=REF_MAC)
    c.add_argument("--force", action="store_true",
                   help="recompute shards that already exist")
    c.add_argument("--max-files", type=int, default=0,
                   help="stop after N files (checkpointing for long runs)")
    c.set_defaults(fn=cmd_collect)

    s = sub.add_parser("sep")
    s.add_argument("--tag", required=True)
    s.add_argument("--min-windows", type=int, default=5)
    s.add_argument("--boot", type=int, default=200)
    s.add_argument("--top", type=int, default=25)
    s.add_argument("--train-frac", type=float, default=1.0,
                   help="fraction of each source's windows used to build "
                        "the models (0.6 reproduces rff_offline's matrix)")
    s.add_argument("--json")
    s.set_defaults(fn=cmd_sep)

    h = sub.add_parser("holdout")
    h.add_argument("--tag", required=True)
    h.add_argument("--min-windows", type=int, default=5)
    h.add_argument("--only")
    h.add_argument("--exclude")
    h.set_defaults(fn=cmd_holdout)

    t = sub.add_parser("timing")
    t.add_argument("--tag", required=True)
    t.add_argument("--mac", required=True)
    t.set_defaults(fn=cmd_timing)

    m = sub.add_parser("match")
    m.add_argument("--tag-a", required=True)
    m.add_argument("--tag-b", required=True)
    m.add_argument("--min-windows", type=int, default=5)
    m.add_argument("--a-only")
    m.add_argument("--b-only")
    m.add_argument("--top", type=int, default=4)
    m.set_defaults(fn=cmd_match)

    d = sub.add_parser("drift")
    d.add_argument("--tag", required=True)
    d.add_argument("--macs", required=True)
    d.set_defaults(fn=cmd_drift)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
