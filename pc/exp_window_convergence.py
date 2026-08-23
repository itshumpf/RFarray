#!/usr/bin/env python3
"""EXPERIMENT: how short can the observation window get before the RF
fingerprint stops being usable?

Motivation
----------
`pc/rff/` was built around sustained observation: our own beacons transmit
all day and the RANSAC/Kalman estimator has effectively unlimited frames to
settle. The outward-facing question is the opposite regime -- a radio that
passes the building and is audible for *seconds*. This script measures the
degradation directly instead of predicting it.

Method (what this actually does)
--------------------------------
1. `extract` reads one session CSV **read-only**, once, and caches the raw
   interleaved CSI byte vectors for a chosen set of source MACs to .npz.
   Timestamps are the ESP clock, unwrapped across its 32-bit microsecond
   rollover. Nothing else is precomputed -- the cache is raw input, so every
   later measurement runs the real DSP.

2. `run` cuts each cached source stream into **non-overlapping** tiles of
   length L seconds (non-overlapping so the trials are independent, not
   sliding-window correlated), and for each tile builds a fingerprint from
   scratch:

       est = FrameEstimator()            # fresh: no unwrap anchor, no
       agg = WindowAggregator(...)       # CFO history from before the tile

   That is a faithful simulation of "this is the entire time you could hear
   this radio". The estimator and aggregator are the *real* ones imported
   from `rff/` -- this script reimplements no DSP.

   Aggregation mode matters and both are reported:
     --agg-mode all  (default) one observation per tile, aggregating every
                     accepted frame in the tile. This is the transient case:
                     you get one look, you use all of it.
     --agg-mode fixed  production behaviour: WindowAggregator(window=N),
                     which emits nothing at all until N frames are accepted.

   The `all` mode needs the aggregator's window set to the number of frames
   the aggregator itself would accept. That count is obtained by feeding the
   per-frame estimates through a real WindowAggregator(window=1) first and
   counting emissions, then re-feeding the same estimates through a real
   WindowAggregator(window=n_accepted). No acceptance logic is duplicated
   here.

3. Metrics per (source, L), over many tiles:
     - convergence: fraction of tiles that yield a usable (CFO, SFO) feature
     - error vs the long-window value for the same source in the same session
     - pairwise separation in sigma (rff.discriminator, pooled covariance)
     - chronological train/holdout classification accuracy (same 60/40 split
       rule as rff_offline.py)

4. `transients` is a separate, later question: which sources appear briefly
   and never recur, and did any of them produce enough frames to fingerprint
   under the threshold measured above. It reads the per-file MAC census only.

Dependencies: numpy (required, already in requirements.txt), matplotlib
(optional, only for --plot, already in requirements.txt). This script does
NOT use pandas or scipy.

Usage
-----
  python exp_window_convergence.py extract ../data/raw/rx_20260714_011619.csv \\
      --macs a4:f0:0f:77:91:20,28:05:a5:2f:fa:48,f4:2d:c9:70:72:30
  python exp_window_convergence.py run --session rx_20260714_011619 \\
      --lengths 60,30,10,5,2,1 --json results.json
  python exp_window_convergence.py census ../data/raw/*.csv --out census.csv
  python exp_window_convergence.py transients --census census.csv
"""
import argparse
import csv as csvmod
import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rff.dsp import FrameEstimator, WindowAggregator          # noqa: E402
from rff.discriminator import Discriminator                    # noqa: E402
from rff.kalman import DriftTracker                            # noqa: E402
from rff_offline import iter_frames, TRAIN_FRACTION            # noqa: E402

ESP_CLOCK_WRAP_US = 1 << 32        # ESP timestamp is 32-bit microseconds
DEFAULT_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "data", "cache", "expwin")


# --------------------------------------------------------------------------
# stage 1: extract
# --------------------------------------------------------------------------

def unwrap_esp_us(ts):
    """Undo the 32-bit microsecond rollover of the ESP timestamp column.

    Returns int64 monotonic microseconds. A single negative step of roughly
    -2^32 is a rollover; anything else negative is left alone and shows up
    as a non-monotonic sample the caller can count.
    """
    ts = np.asarray(ts, dtype=np.int64)
    if ts.size == 0:
        return ts
    d = np.diff(ts)
    wraps = np.zeros(ts.size, dtype=np.int64)
    wraps[1:] = np.cumsum((d < -(ESP_CLOCK_WRAP_US // 2)).astype(np.int64))
    return ts + wraps * ESP_CLOCK_WRAP_US


def extract(path, macs, cache_dir, max_frames=None):
    """Read one session CSV read-only; cache raw CSI per target MAC."""
    targets = {m.strip().lower() for m in macs}
    buf = {m: {"csi": [], "esp": [], "pc": [], "rssi": []} for m in targets}
    n_rows = 0
    n_kept = 0
    n_short = defaultdict(int)
    seen_len = defaultdict(set)
    # rff.dsp.csi_to_complex reads only vals[:128] (64 complex LLTF bins) and
    # returns None below that, so the cache stores exactly those 128 values.
    # Ambient devices emit both len=128 and len=256 rows; truncating to 128
    # keeps both, and dropping the tail is what the real DSP does anyway.
    CSI_KEEP = 128
    for pc_us, mac, rssi, esp_us, vals in iter_frames(path):
        n_rows += 1
        if mac not in targets:
            continue
        seen_len[mac].add(int(vals.size))
        if vals.size < CSI_KEEP:
            n_short[mac] += 1            # below a full LLTF; DSP rejects it
            continue
        vals = vals[:CSI_KEEP]
        b = buf[mac]
        if vals.min() < -128 or vals.max() > 127:
            raise ValueError(f"CSI value outside int8 range in {path}: "
                             f"[{vals.min()}, {vals.max()}] — the cache "
                             f"assumes the documented int8 LLTF layout")
        b["csi"].append(vals.astype(np.int8))
        b["esp"].append(esp_us)
        b["pc"].append(pc_us)
        b["rssi"].append(rssi)
        n_kept += 1
        if max_frames and n_kept >= max_frames:
            break
        if n_rows % 500000 == 0:
            print(f"    ...{n_rows} rows, {n_kept} kept", file=sys.stderr)

    os.makedirs(cache_dir, exist_ok=True)
    session = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(cache_dir, session + ".npz")
    payload = {}
    meta = {"session": session, "source_csv": os.path.abspath(path),
            "rows_read": n_rows, "csi_kept_values": CSI_KEEP, "sources": {}}
    for mac, b in buf.items():
        if not b["csi"]:
            print(f"  {mac}: 0 frames (absent from this session)",
                  file=sys.stderr)
            continue
        key = mac.replace(":", "")
        esp = unwrap_esp_us(b["esp"])
        payload[key + "__csi"] = np.asarray(b["csi"], dtype=np.int8)
        payload[key + "__esp"] = esp
        payload[key + "__pc"] = np.asarray(b["pc"], dtype=np.int64)
        payload[key + "__rssi"] = np.asarray(b["rssi"], dtype=np.int16)
        span = (esp[-1] - esp[0]) / 1e6 if esp.size > 1 else 0.0
        nonmono = int((np.diff(esp) <= 0).sum())
        meta["sources"][mac] = {
            "frames": len(b["csi"]),
            "span_s": round(span, 1),
            "mean_fps": round(len(b["csi"]) / span, 2) if span > 0 else None,
            "nonmonotonic_steps": nonmono,
            "dropped_short_frames": n_short.get(mac, 0),
            "raw_csi_lengths": sorted(seen_len.get(mac, [])),
        }
        print(f"  {mac}: {len(b['csi'])} frames, span {span:.1f}s, "
              f"{len(b['csi'])/span if span else 0:.1f} fps, "
              f"{nonmono} non-monotonic steps", file=sys.stderr)
    np.savez_compressed(out, **payload)
    with open(os.path.join(cache_dir, session + ".meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"cached -> {out}", file=sys.stderr)
    return out


def load_cache(session, cache_dir):
    npz = np.load(os.path.join(cache_dir, session + ".npz"))
    with open(os.path.join(cache_dir, session + ".meta.json")) as f:
        meta = json.load(f)
    sources = {}
    for mac in meta["sources"]:
        key = mac.replace(":", "")
        sources[mac] = {
            "csi": npz[key + "__csi"],
            "esp": npz[key + "__esp"],
            "rssi": npz[key + "__rssi"],
        }
    return sources, meta


# --------------------------------------------------------------------------
# stage 2: fingerprint one truncated stream
# --------------------------------------------------------------------------

def frame_estimates(csi, esp, rssi):
    """Run the real FrameEstimator from a cold start over these frames."""
    est = FrameEstimator()
    out = []
    for i in range(csi.shape[0]):
        e = est.feed(csi[i], int(esp[i]))
        out.append((e, int(esp[i]), float(rssi[i])))
    return out


def aggregate_all(fests):
    """One observation from every frame the real aggregator would accept.

    Two passes over the SAME per-frame estimates, both using a real
    WindowAggregator so the acceptance rule (inlier ratio, residual std) is
    never reimplemented here:
      pass 1 window=1  -> one emission per accepted frame, so emissions
                          counts the accepted frames
      pass 2 window=n  -> exactly one observation over all of them
    """
    probe = WindowAggregator(window=1)
    n_acc = sum(1 for e, t, r in fests if probe.feed(e, t, r) is not None)
    if n_acc < 1:
        return None, 0
    agg = WindowAggregator(window=n_acc)
    obs = None
    for e, t, r in fests:
        o = agg.feed(e, t, r)
        if o is not None:
            obs = o
    return obs, n_acc


def aggregate_fixed(fests, window):
    """Production behaviour: fixed-size windows, may emit zero or many."""
    agg = WindowAggregator(window=window)
    out = []
    for e, t, r in fests:
        o = agg.feed(e, t, r)
        if o is not None:
            out.append(o)
    n_acc = sum(1 for e, t, r in fests
                if e is not None and e["inlier_ratio"] >= agg.min_inlier_ratio
                and e["resid_std"] <= agg.max_resid)
    return out, n_acc


def quality_report(sources, meta, max_frames=None):
    """Per-frame RANSAC quality vs the WindowAggregator's acceptance gates.

    Answers 'why did this source yield no observations' without guessing:
    a frame is accepted only if inlier_ratio >= 0.6 AND resid_std <= 0.8
    (WindowAggregator defaults). A source can be strong in RSSI, produce a
    RANSAC fit on every frame, and still be rejected wholesale.
    """
    gate = WindowAggregator()
    print(f"{'source':<20}{'frames':>8}{'fit':>7}{'inl p10':>9}{'inl p50':>9}"
          f"{'inl p90':>9}{'res p50':>9}{'pass inl':>10}{'pass res':>10}"
          f"{'ACCEPT':>8}{'RSSI':>7}")
    out = {}
    for mac, src in sorted(sources.items()):
        n = src["csi"].shape[0]
        if max_frames:
            n = min(n, max_frames)
        fe = frame_estimates(src["csi"][:n], src["esp"][:n], src["rssi"][:n])
        ok = [e for e, _, _ in fe if e is not None]
        if not ok:
            print(f"{mac:<20}{n:>8}{0:>7}")
            continue
        ir = np.array([e["inlier_ratio"] for e in ok])
        rs = np.array([e["resid_std"] for e in ok])
        pi = float((ir >= gate.min_inlier_ratio).mean())
        pr = float((rs <= gate.max_resid).mean())
        acc = float(((ir >= gate.min_inlier_ratio) &
                     (rs <= gate.max_resid)).mean())
        rssi = float(np.median(src["rssi"][:n]))
        out[mac] = {"frames": n, "fits": len(ok),
                    "inlier_p10": float(np.percentile(ir, 10)),
                    "inlier_p50": float(np.percentile(ir, 50)),
                    "inlier_p90": float(np.percentile(ir, 90)),
                    "resid_p50": float(np.percentile(rs, 50)),
                    "pass_inlier": pi, "pass_resid": pr,
                    "accept_rate": acc, "rssi_median": rssi,
                    "min_inlier_ratio": gate.min_inlier_ratio,
                    "max_resid": gate.max_resid}
        print(f"{mac:<20}{n:>8}{len(ok):>7}{np.percentile(ir, 10):>9.3f}"
              f"{np.percentile(ir, 50):>9.3f}{np.percentile(ir, 90):>9.3f}"
              f"{np.percentile(rs, 50):>9.3f}{pi:>9.1%}{pr:>10.1%}"
              f"{acc:>8.1%}{rssi:>7.0f}")
    return out


def max_frames_in_window(esp, window_s):
    """Largest number of frames in any sliding window of this length.

    Requires the unwrapped, monotonic ESP clock — run on raw 32-bit values
    a rollover makes the two-pointer scan return nonsense.
    """
    esp = np.asarray(esp, dtype=np.int64)
    if esp.size == 0:
        return 0
    if np.any(np.diff(esp) < 0):
        raise ValueError("timestamps are not monotonic; unwrap them first")
    w = int(window_s * 1e6)
    j = 0
    best = 0
    for i in range(esp.size):
        while esp[i] - esp[j] > w:
            j += 1
        best = max(best, i - j + 1)
    return best


def tile_starts(esp, length_us):
    """Non-overlapping consecutive tiles -> list of (i0, i1) index pairs."""
    if esp.size == 0:
        return []
    t0 = esp[0]
    edges = np.arange(t0, esp[-1] + 1, length_us)
    idx = np.searchsorted(esp, edges)
    spans = []
    for a, b in zip(idx[:-1], idx[1:]):
        if b > a:
            spans.append((int(a), int(b)))
    return spans


# --------------------------------------------------------------------------
# stage 3: the experiment
# --------------------------------------------------------------------------

def long_window_reference(src, agg_window=64):
    """The 'converged' value for a source: production pipeline, whole stream.

    Full-session run through FrameEstimator + WindowAggregator(window=64),
    exactly as rff_offline.py does it, plus the same DriftTracker. Reported
    value is the median over all windows (matching rff_offline's per-source
    stability table).
    """
    fests = frame_estimates(src["csi"], src["esp"], src["rssi"])
    obs, _ = aggregate_fixed(fests, agg_window)
    if not obs:
        return None
    sfos = np.array([o["sfo"] for o in obs if o["sfo"] is not None])
    cfos = np.array([o["cfo"] for o in obs if o["cfo"] is not None])
    tr = DriftTracker()
    for o in obs:
        tr.update(o)
    return {
        "n_windows": len(obs),
        "sfo_median": float(np.median(sfos)) if sfos.size else None,
        "sfo_iqr": (float(np.subtract(*np.percentile(sfos, [75, 25])))
                    if sfos.size else None),
        "cfo_median": float(np.median(cfos)) if cfos.size else None,
        "cfo_iqr": (float(np.subtract(*np.percentile(cfos, [75, 25])))
                    if cfos.size else None),
        "kf_sfo": tr.sfo.x,
        "kf_cfo": tr.cfo.x,
    }


def trials_for_length(src, length_s, agg_mode, agg_window, max_trials):
    """Every independent tile of this length -> list of trial dicts."""
    spans = tile_starts(src["esp"], int(length_s * 1e6))
    if max_trials and len(spans) > max_trials:
        pick = np.linspace(0, len(spans) - 1, max_trials).astype(int)
        spans = [spans[i] for i in sorted(set(pick.tolist()))]
    trials = []
    for i0, i1 in spans:
        csi = src["csi"][i0:i1]
        esp = src["esp"][i0:i1]
        rssi = src["rssi"][i0:i1]
        fests = frame_estimates(csi, esp, rssi)
        if agg_mode == "all":
            obs, n_acc = aggregate_all(fests)
            obs_list = [obs] if obs is not None else []
        else:
            obs_list, n_acc = aggregate_fixed(fests, agg_window)
        rec = {
            "t_start_us": int(esp[0]) if esp.size else None,
            "n_frames": int(csi.shape[0]),
            "n_accepted": int(n_acc),
            "n_obs": len(obs_list),
            "sfo": None, "cfo": None, "quality": None,
        }
        if obs_list:
            o = obs_list[0] if agg_mode == "all" else obs_list[
                len(obs_list) // 2]
            rec["sfo"] = o["sfo"]
            rec["cfo"] = o["cfo"]
            rec["quality"] = o["quality"]
            rec["obs_frames"] = o["n_frames"]
        trials.append(rec)
    return trials


def spread(vals):
    a = np.asarray([v for v in vals if v is not None], dtype=np.float64)
    if a.size == 0:
        return {"n": 0}
    return {
        "n": int(a.size),
        "median": float(np.median(a)),
        "p25": float(np.percentile(a, 25)),
        "p75": float(np.percentile(a, 75)),
        "p90": float(np.percentile(a, 90)),
        "max": float(a.max()),
    }


def sfo_only_separation(feats_a, feats_b):
    """Standardized 1-D SFO separation, pooled-variance (Cohen's d style).

    Computed here, not in rff/: the production Discriminator is 2-D by
    construction. Reported only as a diagnostic against HANDOFF.md's claim
    that SFO slope, not the aliased CFO, is the discriminating feature.
    """
    a = np.asarray([f[1] for f in feats_a], dtype=np.float64)
    b = np.asarray([f[1] for f in feats_b], dtype=np.float64)
    if a.size < 2 or b.size < 2:
        return None
    pooled = ((a.size - 1) * a.var(ddof=1) + (b.size - 1) * b.var(ddof=1)) / \
             (a.size + b.size - 2)
    if pooled <= 0:
        return None
    return float(abs(a.mean() - b.mean()) / np.sqrt(pooled))


def run_experiment(sources, meta, lengths, agg_mode, agg_window, max_trials,
                   twin_macs, lw_cache_path=None, trial_dump=None):
    result = {"session": meta["session"], "source_csv": meta["source_csv"],
              "agg_mode": agg_mode, "agg_window": agg_window,
              "twin_macs": sorted(twin_macs), "lengths": {},
              "long_window": {}, "sources": meta["sources"]}

    print("=== long-window reference values "
          "(production pipeline, window=64, whole session) ===")
    lw_cache = {}
    if lw_cache_path and os.path.exists(lw_cache_path):
        with open(lw_cache_path) as f:
            lw_cache = json.load(f)
        print(f"  (reusing cached long-window values from "
              f"{os.path.basename(lw_cache_path)}; delete it to recompute)")
    dirty = False
    for mac, src in sorted(sources.items()):
        if mac in lw_cache:
            lw = lw_cache[mac]
        else:
            lw = long_window_reference(src, 64)
            lw_cache[mac] = lw
            dirty = True
            if lw_cache_path:      # write incrementally: a long session can
                with open(lw_cache_path, "w") as f:   # outlive one process
                    json.dump(lw_cache, f, indent=2, default=float)
        result["long_window"][mac] = lw
        if lw:
            print(f"  {mac}  {lw['n_windows']:>6} windows  "
                  f"SFO {lw['sfo_median']:+.5f} +-IQR {lw['sfo_iqr']:.5f}  "
                  f"CFO {lw['cfo_median']:+.2f} +-IQR {lw['cfo_iqr']:.2f}")
        else:
            print(f"  {mac}  NO WINDOWS")
    if lw_cache_path and dirty:
        with open(lw_cache_path, "w") as f:
            json.dump(lw_cache, f, indent=2, default=float)

    for L in lengths:
        print(f"\n=== window length {L}s ===")
        per_source = {}
        per_source_trials = {}
        feats = {}
        for mac, src in sorted(sources.items()):
            trials = trials_for_length(src, L, agg_mode, agg_window,
                                       max_trials)
            per_source_trials[mac] = trials
            lw = result["long_window"].get(mac) or {}
            conv_sfo = [t for t in trials if t["sfo"] is not None]
            conv_full = [t for t in trials
                         if t["sfo"] is not None and t["cfo"] is not None]
            sfo_err = [abs(t["sfo"] - lw["sfo_median"]) for t in conv_sfo
                       if lw.get("sfo_median") is not None]
            cfo_err = [abs(t["cfo"] - lw["cfo_median"]) for t in conv_full
                       if lw.get("cfo_median") is not None]
            feats[mac] = [np.array([t["cfo"], t["sfo"]]) for t in conv_full]
            per_source[mac] = {
                "trials": len(trials),
                "frames_per_tile": spread([t["n_frames"] for t in trials]),
                "accepted_per_tile": spread([t["n_accepted"] for t in trials]),
                "converged_sfo": len(conv_sfo),
                "converged_full": len(conv_full),
                "conv_rate_sfo": len(conv_sfo) / len(trials) if trials else 0,
                "conv_rate_full": len(conv_full) / len(trials) if trials else 0,
                "sfo_abs_err": spread(sfo_err),
                "cfo_abs_err": spread(cfo_err),
                "sfo_iqr_long": lw.get("sfo_iqr"),
            }
            ps = per_source[mac]
            print(f"  {mac}  tiles {ps['trials']:>4}  "
                  f"frames/tile med {ps['frames_per_tile'].get('median', 0):.0f}  "
                  f"converged(CFO+SFO) {ps['conv_rate_full']:.0%}  "
                  f"|dSFO| med "
                  f"{ps['sfo_abs_err'].get('median', float('nan')):.5f}")

        if trial_dump is not None:
            for mac, tl in per_source_trials.items():
                for t in tl:
                    trial_dump.append(
                        (mac, L, t["t_start_us"], t["n_frames"],
                         t["n_accepted"], t["sfo"], t["cfo"]))

        # --- separation + classification over the short-window features ---
        disc = Discriminator()
        train, test = {}, {}
        for mac, fl in feats.items():
            cut = max(int(len(fl) * TRAIN_FRACTION), 1)
            train[mac], test[mac] = fl[:cut], fl[cut:]
            for f in train[mac]:
                disc.learn(mac, f)
        ids, sep = disc.separation_matrix()
        pairs = {}
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                key = f"{ids[a]}|{ids[b]}"
                is_twin = {ids[a], ids[b]} == set(twin_macs)
                pairs[key] = {
                    "sigma": float(sep[a][b]),
                    "sfo_only_sigma": sfo_only_separation(
                        train[ids[a]], train[ids[b]]),
                    "is_clock_twin": is_twin,
                    "n_a": len(train[ids[a]]), "n_b": len(train[ids[b]]),
                }
        nontwin = [v["sigma"] for v in pairs.values()
                   if not v["is_clock_twin"]]
        total = correct = strangers = 0
        per_mac_acc = {}
        for mac in feats:
            n_ok = n_str = n_tot = 0
            for f in test[mac]:
                best, d2, verdict = disc.classify(f)
                if verdict == "UNSCORED":
                    continue
                n_tot += 1
                total += 1
                if verdict == "STRANGER":
                    n_str += 1
                    strangers += 1
                elif best == mac:
                    n_ok += 1
                    correct += 1
            per_mac_acc[mac] = {"tested": n_tot, "correct": n_ok,
                                "stranger": n_str}
        result["lengths"][str(L)] = {
            "per_source": per_source,
            "pairs": pairs,
            "nontwin_min_sigma": min(nontwin) if nontwin else None,
            "nontwin_median_sigma": (float(np.median(nontwin))
                                     if nontwin else None),
            "twin_sigma": next((v["sigma"] for v in pairs.values()
                                if v["is_clock_twin"]), None),
            "holdout_total": total, "holdout_correct": correct,
            "holdout_stranger": strangers,
            "holdout_accuracy": correct / total if total else None,
            "per_mac_accuracy": per_mac_acc,
        }
        r = result["lengths"][str(L)]
        ns = r["nontwin_min_sigma"]
        print(f"  -> non-twin separation min "
              f"{ns if ns is None else round(ns, 1)}sigma, "
              f"twin pair {r['twin_sigma'] if r['twin_sigma'] is None else round(r['twin_sigma'], 2)}sigma, "
              f"holdout {correct}/{total}"
              f"{' = %.1f%%' % (100*correct/total) if total else ''}")
    return result


# --------------------------------------------------------------------------
# stage 4: census + transient survey
# --------------------------------------------------------------------------

def build_census(paths, out_path):
    """Per (file, MAC): frame count and first/last pc_time. Read-only."""
    rows = []
    for path in sorted(paths):
        stats = {}
        try:
            with open(path, newline="") as f:
                for row in csvmod.DictReader(f):
                    mac = (row.get("mac") or "").lower()
                    if len(mac) != 17:
                        continue
                    try:
                        t = int(row["pc_time_us"])
                    except (KeyError, ValueError):
                        continue
                    s = stats.get(mac)
                    if s is None:
                        stats[mac] = [1, t, t]
                    else:
                        s[0] += 1
                        if t < s[1]:
                            s[1] = t
                        if t > s[2]:
                            s[2] = t
        except OSError as e:
            print(f"  skip {path}: {e}", file=sys.stderr)
            continue
        for mac, (n, t0, t1) in stats.items():
            rows.append((os.path.basename(path), mac, n, t0, t1))
        print(f"  {os.path.basename(path)}: {len(stats)} MACs",
              file=sys.stderr)
    with open(out_path, "w", newline="") as f:
        w = csvmod.writer(f)
        w.writerow(["file", "mac", "frames", "first_pc_us", "last_pc_us"])
        w.writerows(rows)
    print(f"census -> {out_path} ({len(rows)} rows)", file=sys.stderr)
    return out_path


def load_census(path):
    rows = []
    with open(path, newline="") as f:
        for r in csvmod.DictReader(f):
            rows.append((r["file"], r["mac"], int(r["frames"]),
                         int(r["first_pc_us"]), int(r["last_pc_us"])))
    return rows


def transients(census_rows, frame_threshold, known_macs, max_audible_s):
    """Sources that appear briefly. Counts and durations only.

    A source's 'audible duration' inside a file is last-seen minus
    first-seen on the pc clock. That is an upper bound on contiguous
    presence, not a measurement of it: a MAC seen once at the start and
    once at the end of a session reads as a long duration here.
    """
    by_mac = defaultdict(list)
    for fn, mac, n, t0, t1 in census_rows:
        by_mac[mac].append((fn, n, t0, t1))
    out = []
    for mac, apps in by_mac.items():
        if mac in known_macs:
            continue
        total = sum(a[1] for a in apps)
        durs = [(a[3] - a[2]) / 1e6 for a in apps]
        out.append({
            "mac": mac,
            "files": len(apps),
            "total_frames": total,
            "max_frames_one_file": max(a[1] for a in apps),
            "max_span_s": max(durs),
            "min_span_s": min(durs),
            "locally_administered": bool(int(mac[:2], 16) & 0x02),
            "appearances": [{"file": a[0], "frames": a[1],
                             "span_s": round((a[3] - a[2]) / 1e6, 1)}
                            for a in apps],
        })
    out.sort(key=lambda d: -d["total_frames"])
    brief = [d for d in out
             if d["files"] == 1 and d["max_span_s"] <= max_audible_s]
    recurring = [d for d in out if d["files"] > 1]
    fingerprintable = [d for d in out
                       if d["max_frames_one_file"] >= frame_threshold]
    return {"all": out, "single_appearance_brief": brief,
            "recurring": recurring, "fingerprintable": fingerprintable,
            "frame_threshold": frame_threshold,
            "max_audible_s": max_audible_s}


# --------------------------------------------------------------------------
# plotting (optional)
# --------------------------------------------------------------------------

def plot(result, out_png):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available; skipping plot", file=sys.stderr)
        return None
    lengths = sorted((float(k) for k in result["lengths"]), reverse=True)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    macs = sorted(result["long_window"])
    for mac in macs:
        conv = [result["lengths"][fmt_len(L)]["per_source"][mac]
                ["conv_rate_full"] * 100 for L in lengths]
        err = [result["lengths"][fmt_len(L)]["per_source"][mac]
               ["sfo_abs_err"].get("median", np.nan) for L in lengths]
        axes[0].plot(lengths, conv, "o-", label=mac[-8:])
        axes[1].plot(lengths, err, "o-", label=mac[-8:])
    sep = [result["lengths"][fmt_len(L)]["nontwin_min_sigma"] for L in lengths]
    twin = [result["lengths"][fmt_len(L)]["twin_sigma"] for L in lengths]
    axes[2].plot(lengths, [s if s is not None else np.nan for s in sep],
                 "o-", label="min non-twin pair")
    axes[2].plot(lengths, [s if s is not None else np.nan for s in twin],
                 "s--", label="clock-twin pair")
    axes[2].axhline(3.0, color="k", ls=":", lw=1, label="3 sigma")
    for ax, t, y in zip(axes,
                        ["convergence rate", "|SFO - long-window SFO|",
                         "pairwise separation"],
                        ["% of tiles yielding (CFO,SFO)", "rad/subcarrier",
                         "sigma"]):
        ax.set_xscale("log")
        ax.set_xlabel("window length (s)")
        ax.set_ylabel(y)
        ax.set_title(t)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    axes[1].set_yscale("log")
    fig.suptitle(f"Window-length convergence — {result['session']} "
                 f"(agg-mode={result['agg_mode']})")
    fig.tight_layout()
    fig.savefig(out_png, dpi=130)
    print(f"plot -> {out_png}", file=sys.stderr)
    return out_png


def fmt_len(L):
    """Result keys are str() of the parsed float, e.g. '120.0' / '0.5'."""
    return str(float(L))


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("extract", help="cache raw CSI for target MACs")
    pe.add_argument("csv")
    pe.add_argument("--macs", required=True, help="comma-separated MACs")
    pe.add_argument("--cache-dir", default=DEFAULT_CACHE)
    pe.add_argument("--max-frames", type=int, default=None)

    pr = sub.add_parser("run", help="the truncation experiment")
    pr.add_argument("--session", required=True,
                    help="cached session name (CSV basename without .csv)")
    pr.add_argument("--cache-dir", default=DEFAULT_CACHE)
    pr.add_argument("--lengths", default="60,30,10,5,2,1",
                    help="comma-separated window lengths in seconds")
    pr.add_argument("--agg-mode", choices=["all", "fixed"], default="all")
    pr.add_argument("--agg-window", type=int, default=64,
                    help="frames per observation in --agg-mode fixed")
    pr.add_argument("--max-trials", type=int, default=400,
                    help="cap on independent tiles per (source, length)")
    pr.add_argument("--exclude-macs", default="",
                    help="comma-separated MACs to drop from the analysis "
                         "entirely — e.g. drop one half of the clock-twin "
                         "pair so window length is not confounded with a "
                         "known physical collision")
    pr.add_argument("--twin-macs",
                    default="f4:2d:c9:70:72:30,a4:f0:0f:77:91:20",
                    help="the known clock-twin pair, reported separately")
    pr.add_argument("--dump-trials",
                    help="write every individual tile's result to this CSV "
                         "(lets convergence be re-binned by frame count "
                         "rather than by seconds)")
    pr.add_argument("--json", help="write full results JSON here")
    pr.add_argument("--plot", help="write a PNG figure here")

    pq = sub.add_parser("quality", help="per-frame RANSAC quality vs the "
                                        "aggregator's acceptance gates")
    pq.add_argument("--session", required=True)
    pq.add_argument("--cache-dir", default=DEFAULT_CACHE)
    pq.add_argument("--max-frames", type=int, default=None,
                    help="cap frames per source (default: whole stream)")
    pq.add_argument("--burst-window", type=float, default=None,
                    help="also report the max frames in any sliding window "
                         "of this many seconds")
    pq.add_argument("--json")

    pm = sub.add_parser("merge", help="combine per-length result JSONs")
    pm.add_argument("jsons", nargs="+")
    pm.add_argument("--out", required=True)

    pp = sub.add_parser("plot", help="figure from a (merged) results JSON")
    pp.add_argument("json")
    pp.add_argument("--out", required=True)

    pc_ = sub.add_parser("census", help="per-file per-MAC frame census")
    pc_.add_argument("csvs", nargs="+")
    pc_.add_argument("--out", required=True)

    pt = sub.add_parser("transients", help="brief / non-recurring sources")
    pt.add_argument("--census", required=True)
    pt.add_argument("--frame-threshold", type=int, required=True,
                    help="frames needed to fingerprint (measure it first)")
    pt.add_argument("--known-macs",
                    default="a4:f0:0f:77:91:20,28:05:a5:2f:fa:48,"
                            "f4:2d:c9:70:72:30,f4:2d:c9:6f:8b:44",
                    help="our own hardware, excluded from the survey")
    pt.add_argument("--max-audible-s", type=float, default=10.0)
    pt.add_argument("--json")

    args = ap.parse_args()

    if args.cmd == "extract":
        extract(args.csv, args.macs.split(","), args.cache_dir,
                args.max_frames)
        return 0

    if args.cmd == "run":
        sources, meta = load_cache(args.session, args.cache_dir)
        drop = {m.strip().lower() for m in args.exclude_macs.split(",")
                if m.strip()}
        if drop:
            sources = {m: s for m, s in sources.items() if m not in drop}
            meta = dict(meta)
            meta["sources"] = {m: v for m, v in meta["sources"].items()
                               if m not in drop}
            meta["excluded_macs"] = sorted(drop)
            print(f"(excluded {sorted(drop)}; {len(sources)} sources remain)",
                  file=sys.stderr)
        lengths = [float(x) for x in args.lengths.split(",")]
        twins = {m.strip().lower() for m in args.twin_macs.split(",")}
        lw_path = os.path.join(args.cache_dir,
                               f"{args.session}.longwindow.json")
        dump = [] if args.dump_trials else None
        res = run_experiment(sources, meta, lengths, args.agg_mode,
                             args.agg_window, args.max_trials, twins,
                             lw_cache_path=lw_path, trial_dump=dump)
        if args.dump_trials:
            with open(args.dump_trials, "w", newline="") as f:
                w = csvmod.writer(f)
                w.writerow(["mac", "length_s", "t_start_us", "n_frames",
                            "n_accepted", "sfo", "cfo"])
                w.writerows(dump)
            print(f"per-trial records -> {args.dump_trials} ({len(dump)} rows)",
                  file=sys.stderr)
        if args.json:
            with open(args.json, "w") as f:
                json.dump(res, f, indent=2, default=float)
            print(f"\nresults -> {args.json}", file=sys.stderr)
        if args.plot:
            plot(res, args.plot)
        return 0

    if args.cmd == "quality":
        sources, meta = load_cache(args.session, args.cache_dir)
        res = quality_report(sources, meta, args.max_frames)
        if args.burst_window:
            print(f"\nmax frames in any sliding {args.burst_window}s window "
                  f"(unwrapped ESP clock):")
            for mac, src in sorted(sources.items()):
                n = max_frames_in_window(src["esp"], args.burst_window)
                print(f"  {mac:<20}{n:>8}")
                if mac in res:
                    res[mac][f"max_frames_in_{args.burst_window}s"] = n
        if args.json:
            with open(args.json, "w") as f:
                json.dump(res, f, indent=2)
        return 0

    if args.cmd == "merge":
        merged = None
        for p in sorted(args.jsons):
            with open(p) as f:
                r = json.load(f)
            if merged is None:
                merged = r
                continue
            if r["session"] != merged["session"]:
                print(f"refusing to merge different sessions: "
                      f"{r['session']} != {merged['session']}", file=sys.stderr)
                return 1
            if r["agg_mode"] != merged["agg_mode"]:
                print("refusing to merge different agg modes", file=sys.stderr)
                return 1
            merged["lengths"].update(r["lengths"])
        with open(args.out, "w") as f:
            json.dump(merged, f, indent=2, default=float)
        print(f"merged {len(args.jsons)} file(s), "
              f"{len(merged['lengths'])} window lengths -> {args.out}",
              file=sys.stderr)
        return 0

    if args.cmd == "plot":
        with open(args.json) as f:
            plot(json.load(f), args.out)
        return 0

    if args.cmd == "census":
        paths = []
        for pat in args.csvs:
            paths.extend(glob.glob(pat))
        build_census(paths, args.out)
        return 0

    if args.cmd == "transients":
        rows = load_census(args.census)
        known = {m.strip().lower() for m in args.known_macs.split(",")}
        res = transients(rows, args.frame_threshold, known,
                         args.max_audible_s)
        print(f"distinct non-ours MACs: {len(res['all'])}")
        print(f"single appearance, span <= {args.max_audible_s}s: "
              f"{len(res['single_appearance_brief'])}")
        print(f"appearing in >1 session file: {len(res['recurring'])}")
        print(f"reaching {args.frame_threshold} frames in one file: "
              f"{len(res['fingerprintable'])}")
        print("\ntop sources by total frames (excluding our hardware):")
        print(f"{'mac':<20}{'files':>6}{'frames':>9}{'max/file':>10}"
              f"{'max span s':>12}  LAA")
        for d in res["all"][:25]:
            print(f"{d['mac']:<20}{d['files']:>6}{d['total_frames']:>9}"
                  f"{d['max_frames_one_file']:>10}{d['max_span_s']:>12.1f}"
                  f"  {'y' if d['locally_administered'] else 'n'}")
        if args.json:
            with open(args.json, "w") as f:
                json.dump(res, f, indent=2)
            print(f"\n-> {args.json}", file=sys.stderr)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
