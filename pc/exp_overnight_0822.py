#!/usr/bin/env python3
"""Overnight two-receiver capture, 2026-08-22 02:30:34 -> 08:58. Read-only.

Answers the pre-registered question in `docs/OVERNIGHT_2026-08-22.md`:
does the Heltec S3's `noise_floor` step recur (periodic), not occur at all
(absent), or occur once at a random time?

Scope and safety
----------------
- `data/raw/*` is opened `"r"` only. Nothing there is written, renamed or
  deleted. No serial port is opened. Nothing is staged or committed.
- Caches are written to `--cache`, which defaults to a directory OUTSIDE
  the repo tree, so a run leaves exactly one repo file changed (this one).

Phase work
----------
All phase estimation is `pc/rff/dsp.py`'s `FrameEstimator` +
`WindowAggregator(window=64)` with the shipped gates
(`inlier_ratio >= 0.6`, `resid_std <= 0.8`) -- i.e. `pc/rff_offline.py:54-79`
with a MAC restriction added.  `pc/capture.py:compute_cfo`,
`pc/phase_skew.py` and `pc/fingerprint.py` are NOT used:
`docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 establishes all three have the
DC/guard-band index wrong, and `pc/test_rff_synth.py` test 7 shows
`phase_skew`'s mask returns the opposite sign.

The `dropped` column
--------------------
`uint16_t` (`firmware/csi_rx/main/main.c:85`).  Two corrections, both from
`docs/DUAL_RX_2026-08-21.md` §2.1: wrap-safe accumulation of frame-to-frame
deltas (negative delta -> +65536), and removal of corrupt rows first, since
a corrupt row looks like a wrap-and-back inside one frame.  Corrupt rows
are identified here by TWO independent routes (median-filter deviation, and
field-plausibility on columns that have nothing to do with `dropped`).

`pc_time_us` is a per-serial-drain-batch host stamp
(`pc/node_census.py:30-35`, `docs/HANDOFF.md` trap #1).  It is used here to
place bins and to measure host-side delivered rate, never as per-frame
cadence.  Per-frame node-side timing is `esp_timestamp_us` (u32 µs, wraps
every 4294.967 s).

Usage
-----
    D=data/raw/d0wd_20260822_023034.csv
    S=data/raw/s3_20260822_023034.csv
    for p in 0 1 2 3 4 5; do
        python3 pc/exp_overnight_0822.py part $D --tag d0wd --part $p --nparts 6
        python3 pc/exp_overnight_0822.py part $S --tag s3   --part $p --nparts 6
    done
    python3 pc/exp_overnight_0822.py merge $D --tag d0wd --nparts 6 --expect-lines 2983560
    python3 pc/exp_overnight_0822.py merge $S --tag s3   --nparts 6 --expect-lines 3564005
    python3 pc/exp_overnight_0822.py report --tags d0wd,s3

`part` must be run in order per tag: each part reads the previous part's
pickled estimator/aggregator/MAC-table state, which is what makes the
six-part run identical to one pass.  Parts of *different* tags are
independent and may run concurrently.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from array import array
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rff.dsp import FrameEstimator, WindowAggregator  # noqa: E402

BEACONS = {
    "a4:f0:0f:77:91:20": "B1",
    "28:05:a5:2f:fa:48": "B2",
    "f4:2d:c9:70:72:30": "B3",
}
WINDOW = 64
U16 = 65536
U32 = 4294967296

# Corrupt-row screen, route 1 (dropped-column median filter)
MF_W = 9
MF_TOL = 100

# Corrupt-row screen, route 2 (field plausibility).  These bounds are
# deliberately generous: they are meant to catch bytes that cannot be the
# field at all, not to catch unusual-but-possible values.
RSSI_LO, RSSI_HI = -100, -10
NF_LO, NF_HI = -110, -70
# 384 is legal: `pc/rff/protocol.py:31` sets CSI_MAX = 384 and rejects
# anything longer, and `data/fingerprints/f46942f2d2af.json` records a
# device seen across 44 sessions whose len_hist is 100 % 384.  An earlier
# draft of this screen listed only (128, 256) and misclassified that
# device's every frame as corrupt.
VALID_LEN = (128, 256, 384)

DEFAULT_CACHE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "..", "overnight_0822_cache")

# Yardsticks, quoted from the code that defines them so this file cannot
# drift away from them.
BETWEEN_UNIT_SD = 0.00237     # pc/exp_thermal_evidence.py:129
TWIN_DSFO = 0.00080           # pc/exp_lot_hypothesis.py:85-86

DETAIL_CAP = 40          # rows kept verbatim per rare MAC
RARE_MAX = 500           # a MAC is "rare" (detail kept) below this count


# ----------------------------------------------------------------- helpers

def med_filt_chunked(x, w=MF_W, chunk=1_000_000):
    """Running median, computed in chunks so the sliding view never
    materialises the whole (n, w) copy at once (3 GB box)."""
    pad = w // 2
    out = np.empty(x.size, dtype=np.float64)
    xp = np.pad(x, pad, mode="edge")
    for s in range(0, x.size, chunk):
        e = min(s + chunk, x.size)
        sw = np.lib.stride_tricks.sliding_window_view(xp[s:e + 2 * pad], w)
        out[s:e] = np.median(sw, axis=1)
    return out


class TrackedAggregator(WindowAggregator):
    """WindowAggregator + per-window mean resid_std + reject accounting.

    The shipped aggregator returns mean `inlier_ratio` as `quality` and
    discards `resid_std` (`pc/rff/dsp.py:185-195`), so the residual is
    accumulated here alongside.  Acceptance is read off the parent's own
    behaviour (buffer grew, or a window was emitted), never re-derived, so
    these counts cannot disagree with what the pipeline actually did; only
    the *attribution* of a rejection mirrors dsp's gate order, and anything
    the mirror fails to explain lands in `n_rej_other`.
    """

    def __init__(self, *a, **kw):
        WindowAggregator.__init__(self, *a, **kw)
        self.n_fed = self.n_unusable = 0
        self.n_rej_inlier = self.n_rej_resid = self.n_rej_other = 0
        self.n_accepted = self.n_windows = 0
        self._resids = []

    def feed(self, est, ts_us, rssi):
        self.n_fed += 1
        n_before = len(self._buf)
        obs = WindowAggregator.feed(self, est, ts_us, rssi)
        grew = (obs is not None) or (len(self._buf) != n_before)
        if grew:
            self.n_accepted += 1
            self._resids.append(est["resid_std"])
        elif est is None:
            self.n_unusable += 1
        elif est["inlier_ratio"] < self.min_inlier_ratio:
            self.n_rej_inlier += 1
        elif est["resid_std"] > self.max_resid:
            self.n_rej_resid += 1
        else:
            self.n_rej_other += 1
        if obs is not None:
            self.n_windows += 1
            obs["resid"] = float(np.mean(self._resids))
            self._resids = []
        return obs


def mac_octet_distance(a, b):
    """Number of differing octets between two colon MAC strings."""
    pa, pb = a.split(":"), b.split(":")
    if len(pa) != 6 or len(pb) != 6:
        return 6
    return sum(1 for x, y in zip(pa, pb) if x != y)


def rle(vals, times):
    """Run-length encode an integer series, returning (value, n, t_start)."""
    out = []
    if vals.size == 0:
        return out
    cut = np.flatnonzero(np.diff(vals)) + 1
    starts = np.r_[0, cut]
    ends = np.r_[cut, vals.size]
    for s, e in zip(starts, ends):
        out.append((int(vals[s]), int(e - s), float(times[s])))
    return out


# -------------------------------------------------- parse, one byte-range

def cmd_part(args):
    """Parse one byte range of one capture.

    The host this ran on kills any process when the shell call that started
    it returns, so a 6-minute single pass is not available; the file is cut
    into `--nparts` byte ranges instead.  Ranges are cut on line boundaries
    with no overlap and no loss (a range that is not the first seeks to
    `start - 1` and discards through the next newline, so a boundary that
    lands on a newline neither drops nor duplicates a row), and the
    aggregator + MAC-table state is pickled forward from part to part, so
    the concatenation is frame-for-frame identical to one uninterrupted
    pass.  `merge` re-checks that: it verifies the parts' row counts sum to
    the file's own line count and that `pc_time_us` is non-decreasing
    across every seam.
    """
    path = args.path
    tag = args.tag
    part, nparts = args.part, args.nparts
    os.makedirs(args.cache, exist_ok=True)
    t_start = time.time()

    size = os.path.getsize(path)
    start = size * part // nparts
    end = size * (part + 1) // nparts

    statef = os.path.join(args.cache, f"{tag}_state.pkl")
    if part == 0:
        mac_ids, mac_names = {}, []
        est = {m: FrameEstimator() for m in BEACONS}
        agg = {m: TrackedAggregator(window=WINDOW) for m in BEACONS}
        pcbuf = {m: [] for m in BEACONS}
        n_short_csi = {m: 0 for m in BEACONS}
        header = None
    else:
        with open(statef, "rb") as fh:
            st = pickle.load(fh)
        if st["next_part"] != part:
            raise SystemExit(f"state file is at part {st['next_part']}, "
                             f"asked for {part} — run parts in order")
        mac_ids, mac_names = st["mac_ids"], st["mac_names"]
        est, agg, pcbuf = st["est"], st["agg"], st["pcbuf"]
        n_short_csi = st["n_short_csi"]
        header = st["header"]

    pc = array("q"); esp = array("q")
    rssi = array("h"); nf = array("h"); chan = array("h"); ln = array("h")
    node = array("h"); envid = array("h")
    drop = array("i"); midx = array("i")
    obs = {m: [] for m in BEACONS}
    n_lines = n_badsplit = n_badint = 0

    with open(path, "rb") as f:
        if part == 0:
            header = f.readline().decode().strip()
        else:
            # seek one byte early so a range boundary that lands exactly on
            # a newline does not swallow the line that starts at `start`
            f.seek(start - 1)
            f.readline()
        pos = f.tell()
        for raw in f:
            pos += len(raw)
            n_lines += 1
            line = raw.decode("utf-8", "replace")
            p = line.split(",", 9)
            if len(p) < 10:
                n_badsplit += 1
                if pos >= end:
                    break
                continue
            r = p[9].rsplit(",", 3)
            if len(r) != 4:
                n_badsplit += 1
                if pos >= end:
                    break
                continue
            try:
                v_pc = int(p[0])
                v_rssi = int(p[4])
                v_nf = int(p[5])
                v_ch = int(p[6])
                v_esp = int(p[7])
                v_len = int(p[8])
                v_node = int(r[1])
                v_env = int(r[2])
                v_drop = int(r[3])
            except ValueError:
                n_badint += 1
                if pos >= end:
                    break
                continue

            m = p[3]
            i = mac_ids.get(m)
            if i is None:
                i = mac_ids[m] = len(mac_names)
                mac_names.append(m)

            pc.append(v_pc); esp.append(v_esp)
            rssi.append(max(-32768, min(32767, v_rssi)))
            nf.append(max(-32768, min(32767, v_nf)))
            chan.append(max(-32768, min(32767, v_ch)))
            ln.append(max(-32768, min(32767, v_len)))
            node.append(max(-32768, min(32767, v_node)))
            envid.append(max(-32768, min(32767, v_env)))
            drop.append(v_drop)
            midx.append(i)

            if m in BEACONS:
                cs = r[0]
                if cs[:1] == '"':
                    cs = cs[1:-1] if cs[-1:] == '"' else cs[1:]
                parts = cs.split(",", 128)
                if len(parts) < 129:
                    n_short_csi[m] += 1
                else:
                    try:
                        vv = np.array(parts[:128], dtype=np.float64)
                    except ValueError:
                        n_short_csi[m] += 1
                    else:
                        e = est[m].feed(vv, v_esp)
                        pcbuf[m].append(v_pc)
                        o = agg[m].feed(e, v_esp, v_rssi)
                        if o is not None:
                            o["ts_pc"] = float(np.median(pcbuf[m])) * 1e-6
                            pcbuf[m] = []
                            obs[m].append(o)
            if pos >= end:
                break

    np.savez(
        os.path.join(args.cache, f"{tag}_p{part:02d}.npz"),
        pc=np.frombuffer(pc, dtype=np.int64),
        esp=np.frombuffer(esp, dtype=np.int64),
        rssi=np.frombuffer(rssi, dtype=np.int16),
        nf=np.frombuffer(nf, dtype=np.int16),
        chan=np.frombuffer(chan, dtype=np.int16),
        ln=np.frombuffer(ln, dtype=np.int16),
        node=np.frombuffer(node, dtype=np.int16),
        envid=np.frombuffer(envid, dtype=np.int16),
        drop=np.frombuffer(drop, dtype=np.int32),
        midx=np.frombuffer(midx, dtype=np.int32),
    )
    with open(os.path.join(args.cache, f"{tag}_obs_p{part:02d}.pkl"),
              "wb") as fh:
        pickle.dump(obs, fh)
    with open(statef, "wb") as fh:
        pickle.dump(dict(
            next_part=part + 1, mac_ids=mac_ids, mac_names=mac_names,
            est=est, agg=agg, pcbuf=pcbuf, n_short_csi=n_short_csi,
            header=header,
            n_lines=n_lines + (0 if part == 0 else 0),
        ), fh)
    meta = dict(part=part, nparts=nparts, start=start, end=end,
                n_lines=n_lines, n_rows=len(pc), n_badsplit=n_badsplit,
                n_badint=n_badint, path=path, header=header,
                windows={b: agg[m].n_windows for m, b in BEACONS.items()})
    with open(os.path.join(args.cache, f"{tag}_meta_p{part:02d}.json"),
              "w") as fh:
        json.dump(meta, fh)
    print(f"[{tag} part {part}/{nparts}] bytes {start}..{end} "
          f"lines={n_lines} rows={len(pc)} "
          f"in {time.time()-t_start:.1f}s", flush=True)


# ------------------------------------------------------------------- merge

def cmd_merge(args):
    path = args.path
    tag = args.tag
    t_start = time.time()

    metas = []
    for p in range(args.nparts):
        with open(os.path.join(args.cache,
                               f"{tag}_meta_p{p:02d}.json")) as fh:
            metas.append(json.load(fh))
    with open(os.path.join(args.cache, f"{tag}_state.pkl"), "rb") as fh:
        st = pickle.load(fh)
    if st["next_part"] != args.nparts:
        raise SystemExit(f"only {st['next_part']} parts done")
    mac_names = st["mac_names"]
    mac_ids = st["mac_ids"]
    n_short_csi = st["n_short_csi"]
    agg = st["agg"]
    header = st["header"]

    cols = {}
    for name in ("pc", "esp", "rssi", "nf", "chan", "ln", "node", "envid",
                 "drop", "midx"):
        cols[name] = []
    seams = []
    for p in range(args.nparts):
        z = np.load(os.path.join(args.cache, f"{tag}_p{p:02d}.npz"))
        for name in cols:
            cols[name].append(z[name])
        if p:
            seams.append((int(cols["pc"][p - 1][-1]), int(z["pc"][0])))
    pc = np.concatenate(cols["pc"])
    esp = np.concatenate(cols["esp"])
    rssi = np.concatenate(cols["rssi"]).astype(np.int32)
    nf = np.concatenate(cols["nf"]).astype(np.int32)
    chan = np.concatenate(cols["chan"]).astype(np.int32)
    ln = np.concatenate(cols["ln"]).astype(np.int32)
    node = np.concatenate(cols["node"]).astype(np.int32)
    envid = np.concatenate(cols["envid"]).astype(np.int32)
    drop = np.concatenate(cols["drop"]).astype(np.int64)
    midx = np.concatenate(cols["midx"])
    del cols

    obs = {m: [] for m in BEACONS}
    for p in range(args.nparts):
        with open(os.path.join(args.cache,
                               f"{tag}_obs_p{p:02d}.pkl"), "rb") as fh:
            o = pickle.load(fh)
        for m in BEACONS:
            obs[m].extend(o[m])

    n_lines = sum(m["n_lines"] for m in metas)
    n_badsplit = sum(m["n_badsplit"] for m in metas)
    n_badint = sum(m["n_badint"] for m in metas)

    # ---- seam integrity: no gap, no overlap, no reordering
    seam_bad = sum(1 for a, b in seams if b < a)
    print(f"[{tag}] merged {args.nparts} parts: {n_lines:,} lines, "
          f"{pc.size:,} rows, {len(seams)} seams, "
          f"{seam_bad} with pc_time going backwards", flush=True)
    if args.expect_lines and n_lines != args.expect_lines:
        print(f"  !! line count {n_lines} != expected {args.expect_lines}")

    n = pc.size
    t = (pc - pc[0]) * 1e-6

    # ---- corrupt-row screen, route 2: field plausibility
    node_mode = int(np.bincount(node - node.min()).argmax() + node.min())
    ch_mode = int(np.bincount(np.clip(chan, 0, 300)).argmax())
    bad_field = (
        (node != node_mode)
        | (envid != 0)
        | (chan != ch_mode)
        | ~np.isin(ln, VALID_LEN)
        | (nf < NF_LO) | (nf > NF_HI)
        | (rssi < RSSI_LO) | (rssi > RSSI_HI)
    )

    # ---- corrupt-row screen, route 1: dropped median-filter deviation
    mf = med_filt_chunked(drop.astype(np.float64))
    bad_drop = np.abs(drop - mf) > MF_TOL

    corrupt = bad_field | bad_drop
    good = ~corrupt

    # ---- loss, wrap-safe, corrupt rows removed
    dg = drop[good]
    delta = np.diff(dg)
    wraps = int((delta < 0).sum())
    delta_uw = np.where(delta < 0, delta + U16, delta)
    drops_total = int(delta_uw.sum())
    endpoint = int(dg[-1] - dg[0] + U16 * wraps)
    # naive one-wrap estimator, what field_diag.py:106 / diagnose.py:540 do
    naive_onewrap = int(dg[-1] - dg[0]) + (U16 if dg[-1] < dg[0] else 0)
    naive_positive = int(delta[delta > 0].sum())

    tg = t[good]
    span = float(t[-1])
    sec = t.astype(np.int64)
    nsec = int(sec[-1]) + 1
    kept_per_s = np.bincount(sec, minlength=nsec)
    drops_per_s = np.bincount(sec[good][1:], weights=delta_uw,
                              minlength=nsec)

    # ---- esp_timestamp_us unwrap (u32) -> node-side elapsed
    espg = esp[good]
    de = np.diff(espg)
    esp_wraps = int((de < 0).sum())
    esp_neg = np.flatnonzero(de < 0)
    esp_neg_detail = [(float(tg[i]), int(espg[i]), int(espg[i + 1]))
                      for i in esp_neg[:20]]
    de_uw = np.where(de < 0, de + U32, de)
    esp_span = float(de_uw.sum()) * 1e-6
    esp_gap_max = int(de_uw.max())
    esp_gap_idx = int(de_uw.argmax())

    # ---- pc_time_us batch gaps
    dpc = np.diff(pc)
    pc_gap_max = int(dpc.max())
    pc_gap_top = np.argsort(dpc)[-10:][::-1]
    pc_gap_detail = [(float(t[i]), int(dpc[i])) for i in pc_gap_top]

    # ---- noise_floor, per node
    nf_good = nf[good]
    t_nfg = tg
    nf_hist = dict(Counter(nf_good.tolist()))
    nf_runs = rle(nf_good, t_nfg)
    # modal value per 10 s bin
    BIN = 10
    b10 = (t_nfg / BIN).astype(np.int64)
    nb10 = int(b10[-1]) + 1
    lo = int(nf_good.min())
    off = -lo
    span_v = int(nf_good.max()) - lo + 1
    cnt = np.bincount(b10 * span_v + (nf_good + off),
                      minlength=nb10 * span_v).reshape(nb10, span_v)
    modal10 = cnt.argmax(axis=1) - off
    mean10 = np.where(cnt.sum(1) > 0,
                      (cnt * (np.arange(span_v) - off)).sum(1)
                      / np.maximum(cnt.sum(1), 1), np.nan)

    # ---- per-MAC census
    nmac = len(mac_names)
    mac_count = np.bincount(midx, minlength=nmac)
    mac_count_good = np.bincount(midx[good], minlength=nmac)
    mac_first = np.full(nmac, np.inf)
    mac_last = np.full(nmac, -np.inf)
    np.minimum.at(mac_first, midx, t)
    np.maximum.at(mac_last, midx, t)
    # rssi histogram per mac: rssi in [-128, 0]
    rs = np.clip(rssi, -128, 0) + 128
    rs_hist = np.bincount(midx * 129 + rs,
                          minlength=nmac * 129).reshape(nmac, 129)
    # per-300 s bin activity
    BINA = 300
    ba = (t / BINA).astype(np.int64)
    nba = int(ba[-1]) + 1
    act = np.bincount(midx * nba + ba,
                      minlength=nmac * nba).reshape(nmac, nba)
    len_hist = {}
    for L in np.unique(ln):
        c = np.bincount(midx[ln == L], minlength=nmac)
        for i in np.flatnonzero(c):
            len_hist.setdefault(mac_names[i], {})[int(L)] = int(c[i])

    mac_bad = np.bincount(midx[corrupt], minlength=nmac)

    # verbatim detail for rare MACs
    rare = np.flatnonzero((mac_count > 0) & (mac_count <= RARE_MAX))
    detail = {}
    for i in rare:
        sel = np.flatnonzero(midx == i)[:DETAIL_CAP]
        detail[mac_names[i]] = [
            dict(t=float(t[k]), rssi=int(rssi[k]), nf=int(nf[k]),
                 ch=int(chan[k]), ln=int(ln[k]), node=int(node[k]),
                 env=int(envid[k]), drop=int(drop[k]),
                 corrupt=bool(corrupt[k])) for k in sel
        ]

    out = dict(
        tag=tag, path=path, header=header,
        nparts=args.nparts, seams=seams, seam_bad=seam_bad,
        n_lines=n_lines, n_rows=n, n_badsplit=n_badsplit, n_badint=n_badint,
        pc_first=int(pc[0]), pc_last=int(pc[-1]), span_s=span,
        node_mode=node_mode, ch_mode=ch_mode,
        node_hist={int(k): int(v) for k, v in Counter(node.tolist()).items()},
        env_hist={int(k): int(v) for k, v in Counter(envid.tolist()).items()},
        ch_hist={int(k): int(v) for k, v in Counter(chan.tolist()).items()},
        len_hist_all={int(k): int(v) for k, v in Counter(ln.tolist()).items()},
        n_corrupt=int(corrupt.sum()), n_bad_field=int(bad_field.sum()),
        n_bad_drop=int(bad_drop.sum()),
        n_bad_both=int((bad_field & bad_drop).sum()),
        drops_total=drops_total, drops_endpoint=endpoint,
        drop_wraps=wraps, naive_onewrap=naive_onewrap,
        naive_positive=naive_positive,
        delivered=int(good.sum()),
        esp_wraps=esp_wraps, esp_neg_detail=esp_neg_detail,
        esp_span_s=esp_span, esp_gap_max_us=esp_gap_max,
        esp_gap_max_t=float(tg[esp_gap_idx]),
        pc_gap_max_us=pc_gap_max, pc_gap_detail=pc_gap_detail,
        nf_hist=nf_hist, nf_runs_n=len(nf_runs),
        nf_runs=nf_runs[:5000],
        nf_modal10=modal10.tolist(), nf_mean10=mean10.tolist(),
        mac_names=mac_names,
        mac_count=mac_count.tolist(), mac_count_good=mac_count_good.tolist(),
        mac_bad=mac_bad.tolist(),
        mac_first=mac_first.tolist(), mac_last=mac_last.tolist(),
        len_hist=len_hist, detail=detail,
        n_short_csi=n_short_csi,
        agg_stats={m: dict(fed=agg[m].n_fed, unusable=agg[m].n_unusable,
                           rej_inlier=agg[m].n_rej_inlier,
                           rej_resid=agg[m].n_rej_resid,
                           rej_other=agg[m].n_rej_other,
                           accepted=agg[m].n_accepted,
                           windows=agg[m].n_windows) for m in BEACONS},
    )

    with open(os.path.join(args.cache, f"{tag}_scan.json"), "w") as f:
        json.dump(out, f)
    np.savez_compressed(
        os.path.join(args.cache, f"{tag}_series.npz"),
        kept_per_s=kept_per_s, drops_per_s=drops_per_s,
        rs_hist=rs_hist, act=act, modal10=modal10, mean10=mean10,
        nf_runs_v=np.array([r[0] for r in nf_runs]),
        nf_runs_n=np.array([r[1] for r in nf_runs]),
        nf_runs_t=np.array([r[2] for r in nf_runs]),
    )
    with open(os.path.join(args.cache, f"{tag}_obs.pkl"), "wb") as f:
        pickle.dump({m: obs[m] for m in BEACONS}, f)

    # ---- per-beacon per-bin noise_floor / rssi, to test co-movement
    perb = {}
    for m, b in BEACONS.items():
        i = mac_ids.get(m)
        if i is None:
            continue
        sel = (midx == i) & good
        tb = t[sel]
        bb = (tb / 60).astype(np.int64)
        nbb = int(bb.max()) + 1
        cntb = np.bincount(bb, minlength=nbb)
        sumnf = np.bincount(bb, weights=nf[sel], minlength=nbb)
        sumrs = np.bincount(bb, weights=rssi[sel], minlength=nbb)
        perb[b] = dict(n=cntb.tolist(),
                       nf=(sumnf / np.maximum(cntb, 1)).tolist(),
                       rssi=(sumrs / np.maximum(cntb, 1)).tolist())
    with open(os.path.join(args.cache, f"{tag}_perbeacon.json"), "w") as f:
        json.dump(perb, f)

    print(f"[{tag}] rows={n} span={span:.1f}s corrupt={int(corrupt.sum())} "
          f"drops={drops_total} wraps={wraps} macs={nmac} "
          f"windows={ {b: agg[m].n_windows for m, b in BEACONS.items()} }",
          flush=True)


# ------------------------------------------------------------------ report

def load(cache, tag):
    with open(os.path.join(cache, f"{tag}_scan.json")) as f:
        s = json.load(f)
    z = np.load(os.path.join(cache, f"{tag}_series.npz"))
    with open(os.path.join(cache, f"{tag}_obs.pkl"), "rb") as f:
        o = pickle.load(f)
    with open(os.path.join(cache, f"{tag}_perbeacon.json")) as f:
        pb = json.load(f)
    return s, z, o, pb


def binned_median(obs, bin_s, t0=0.0, min_n=5):
    if not obs:
        return {}
    ts = np.array([o["ts_pc"] for o in obs]) - t0
    sf = np.array([o["sfo"] for o in obs])
    rd = np.array([o.get("resid", np.nan) for o in obs])
    b = (ts / bin_s).astype(np.int64)
    out = {}
    for bi in np.unique(b):
        sel = b == bi
        if sel.sum() < min_n:
            continue
        out[int(bi)] = (float(np.median(sf[sel])), int(sel.sum()),
                        float(np.nanmean(rd[sel])))
    return out


def cmd_report(args):
    tags = args.tags.split(",")
    data = {t: load(args.cache, t) for t in tags}

    print("=" * 78)
    print("TABLE 0 — the two captures")
    print("=" * 78)
    for t in tags:
        s, z, o, pb = data[t]
        print(f"\n[{t}] {s['path']}")
        print(f"  rows parsed          {s['n_rows']:,} "
              f"(lines {s['n_lines']:,}, bad split {s['n_badsplit']}, "
              f"bad int {s['n_badint']})")
        print(f"  node_id hist         {s['node_hist']}")
        print(f"  env_id hist          {s['env_hist']}")
        print(f"  channel hist (top6)  "
              f"{dict(sorted(s['ch_hist'].items(), key=lambda kv: -kv[1])[:6])}")
        print(f"  csi_len hist         {s['len_hist_all']}")
        print(f"  pc span              {s['span_s']:.3f} s "
              f"[{s['pc_first']} .. {s['pc_last']}]")
        print(f"  esp span (unwrapped) {s['esp_span_s']:.3f} s "
              f"({s['esp_wraps']} u32 wraps)")
        print(f"  delivered rate       {s['n_rows']/s['span_s']:.2f} fps")
        print(f"  distinct source MACs {len(s['mac_names'])}")
        mc = np.array(s["mac_count"])
        print(f"  MACs seen exactly 1x {int((mc == 1).sum())}   "
              f"<=5x {int((mc <= 5).sum())}   >=1000x {int((mc >= 1000).sum())}")
        print(f"  corrupt rows          {s['n_corrupt']} "
              f"(field route {s['n_bad_field']}, dropped route "
              f"{s['n_bad_drop']}, both {s['n_bad_both']})")

    print()
    print("=" * 78)
    print("TABLE 1 — noise_floor over the night, per node")
    print("=" * 78)
    for t in tags:
        s, z, o, pb = data[t]
        h = {int(k): v for k, v in s["nf_hist"].items()}
        tot = sum(h.values())
        print(f"\n[{t}] distinct values on clean rows ({tot:,} rows):")
        for v, c in sorted(h.items(), key=lambda kv: -kv[1]):
            print(f"    {v:5d}  {c:>10,}  {100*c/tot:6.3f} %")
        print(f"  raw value transitions (row to row): {s['nf_runs_n']-1:,}")
        modal = np.array(s["nf_modal10"])
        chg = np.flatnonzero(np.diff(modal)) + 1
        print(f"  10 s-modal transitions: {len(chg)}")
        if len(chg) <= 60:
            for i in chg:
                print(f"    t = {i*10:8.0f} s   "
                      f"{modal[i-1]:+d} -> {modal[i]:+d}")
        else:
            print(f"    (first 30 of {len(chg)})")
            for i in chg[:30]:
                print(f"    t = {i*10:8.0f} s   "
                      f"{modal[i-1]:+d} -> {modal[i]:+d}")
        # longest runs
        rv, rn, rt = z["nf_runs_v"], z["nf_runs_n"], z["nf_runs_t"]
        top = np.argsort(rn)[-8:][::-1]
        print("  longest constant runs (value, rows, t_start):")
        for i in top:
            print(f"    {int(rv[i]):+5d}  {int(rn[i]):>9,} rows  "
                  f"t = {rt[i]:9.1f} s")
        # hourly mean
        m10 = np.array(s["nf_mean10"])
        print("  mean noise_floor by 30-min block:")
        per = 180
        for k in range(0, len(m10), per):
            seg = m10[k:k + per]
            seg = seg[~np.isnan(seg)]
            if seg.size:
                print(f"    t = {k*10/3600:5.2f}-{min((k+per)*10,len(m10)*10)/3600:5.2f} h  "
                      f"mean {seg.mean():+9.4f}  min {seg.min():+7.2f}  "
                      f"max {seg.max():+7.2f}")

    print()
    print("=" * 78)
    print("TABLE 1c — noise_floor step detector")
    print("=" * 78)
    print("  series: mean noise_floor per 10 s bin, smoothed by a 30-bin")
    print("  (5 min) running median; an 'event' is a run of consecutive")
    print(f"  bins whose smoothed value moves by >= {args.step_thresh} dB in")
    print("  total, reported with its start, end and size.")
    for t in tags:
        s, z, o, pb = data[t]
        m10 = np.array(s["nf_mean10"], dtype=float)
        ok = ~np.isnan(m10)
        if ok.sum() < 60:
            print(f"\n[{t}] too few bins")
            continue
        sm = med_filt_chunked(np.nan_to_num(m10, nan=np.nanmedian(m10)), 31)
        d = np.diff(sm)
        moving = np.abs(d) > 1e-9
        events = []
        i = 0
        while i < d.size:
            if not moving[i]:
                i += 1
                continue
            j = i
            while j < d.size and moving[j]:
                j += 1
            tot = sm[j] - sm[i]
            if abs(tot) >= args.step_thresh:
                events.append((i * 10.0, j * 10.0, sm[i], sm[j], tot))
            i = j
        print(f"\n[{t}] full-night range of the smoothed series: "
              f"{sm.min():+.4f} .. {sm.max():+.4f} "
              f"(peak-to-peak {sm.max()-sm.min():.4f} dB)")
        print(f"      events >= {args.step_thresh} dB: {len(events)}")
        for a, b, va, vb, tot in events[:40]:
            print(f"        t = {a:8.0f} -> {b:8.0f} s "
                  f"({a/3600:5.2f} -> {b/3600:5.2f} h)   "
                  f"{va:+8.4f} -> {vb:+8.4f}   Δ {tot:+7.4f} dB")
        if len(events) >= 2:
            mids = np.array([(a + b) / 2 for a, b, *_ in events])
            iv = np.diff(mids)
            print(f"      intervals between event midpoints (s): "
                  f"{np.round(iv, 1).tolist()[:20]}")
            if iv.size >= 2:
                print(f"      mean {iv.mean():.1f} s  sd {iv.std():.1f} s  "
                      f"CV {iv.std()/max(iv.mean(),1e-9):.3f}  "
                      f"min {iv.min():.1f}  max {iv.max():.1f}")
                print("      (a periodic process has CV near 0; a Poisson "
                      "process has CV near 1)")
        # dwell: how long the 10 s modal value sits away from the night's
        # own modal value, and the longest such excursion
        mo = np.array(s["nf_modal10"])
        base = int(np.bincount(mo - mo.min()).argmax() + mo.min())
        away = mo != base
        runs, cur = [], 0
        for v in away:
            if v:
                cur += 1
            elif cur:
                runs.append(cur); cur = 0
        if cur:
            runs.append(cur)
        print(f"      night's modal noise_floor {base:+d} dB, held by "
              f"{100*(~away).mean():.2f} % of the {mo.size} 10 s bins")
        if runs:
            print(f"      excursions away from it: {len(runs)}, "
                  f"longest {max(runs)*10} s, "
                  f"median {int(np.median(runs))*10} s, "
                  f"total {sum(runs)*10} s")
        else:
            print("      excursions away from it: none")
        # interior only, so start-up and shutdown transients cannot
        # dominate the peak-to-peak
        k0, k1 = 30, sm.size - 30
        if k1 > k0:
            interior = sm[k0:k1]
            print(f"      interior only (t = 300 .. {k1*10} s): "
                  f"{interior.min():+.4f} .. {interior.max():+.4f} "
                  f"(peak-to-peak {interior.max()-interior.min():.4f} dB)")

    print()
    print("=" * 78)
    print("TABLE 1b — noise_floor per beacon per 60 s bin (is it per-node?)")
    print("=" * 78)
    for t in tags:
        s, z, o, pb = data[t]
        bs = sorted(pb.keys())
        print(f"\n[{t}] t(min)  " + "  ".join(f"{b:>10s}" for b in bs))
        nbb = min(len(pb[b]["nf"]) for b in bs)
        for k in range(0, nbb, max(1, nbb // 24)):
            row = "  ".join(f"{pb[b]['nf'][k]:+10.4f}" for b in bs)
            print(f"        {k:5d}  {row}")

    print()
    print("=" * 78)
    print("TABLE 2 — SFO per beacon per node (whole night)")
    print("=" * 78)
    print(f"{'node':6s} {'b':3s} {'fed':>10s} {'acc':>10s} {'rej%':>7s} "
          f"{'windows':>8s} {'sfo med':>10s} {'IQR':>9s} {'resid':>7s} "
          f"{'rssi acc':>7s} {'rssi all':>9s}")
    for t in tags:
        s, z, o, pb = data[t]
        for m, b in BEACONS.items():
            st = s["agg_stats"][m]
            ob = o[m]
            if not ob:
                print(f"{t:6s} {b:3s} {st['fed']:>10,} — no windows")
                continue
            sf = np.array([x["sfo"] for x in ob])
            rd = np.array([x.get("resid", np.nan) for x in ob])
            rs = np.array([x["rssi"] for x in ob])
            rej = 100 * (st["fed"] - st["accepted"]) / max(st["fed"], 1)
            cnt = np.array(pb[b]["n"], dtype=float)
            rall = np.array(pb[b]["rssi"], dtype=float)
            rssi_all = float((rall * cnt).sum() / max(cnt.sum(), 1))
            print(f"{t:6s} {b:3s} {st['fed']:>10,} {st['accepted']:>10,} "
                  f"{rej:7.3f} {st['windows']:>8,} {np.median(sf):+10.5f} "
                  f"{np.subtract(*np.percentile(sf,[75,25])):9.5f} "
                  f"{np.nanmean(rd):7.4f} {rs.mean():7.2f} "
                  f"{rssi_all:9.2f}")

    print()
    print("=" * 78)
    print("TABLE 3 — SFO in 30-min blocks, per beacon per node")
    print("=" * 78)
    for t in tags:
        s, z, o, pb = data[t]
        t0 = s["pc_first"] * 1e-6
        bins = {b: binned_median(o[m], 1800, t0, min_n=5)
                for m, b in BEACONS.items()}
        allb = sorted(set().union(*[set(v) for v in bins.values()]))
        print(f"\n[{t}]  t(h)   " + "   ".join(f"{b:>9s}" for b in bins))
        for bi in allb:
            row = "   ".join(
                (f"{bins[b][bi][0]:+9.5f}" if bi in bins[b] else "    —    ")
                for b in bins)
            print(f"      {bi*0.5:5.2f}   {row}")

    print()
    print("=" * 78)
    print("TABLE 3c — SFO stationarity over the night")
    print("=" * 78)
    print(f"  yardsticks: BETWEEN_UNIT_SD = {BETWEEN_UNIT_SD} "
          f"(pc/exp_thermal_evidence.py:129), twin ΔSFO = {TWIN_DSFO} "
          f"(pc/exp_lot_hypothesis.py:85-86)")
    print(f"\n{'node':6s} {'b':3s} {'1st half':>10s} {'2nd half':>10s} "
          f"{'Δ':>10s} {'Δ 95% CI':>22s} {'max adj':>9s} {'x SD':>6s}")
    rng = np.random.default_rng(0)
    for t in tags:
        s, z, o, pb = data[t]
        t0 = s["pc_first"] * 1e-6
        for m, b in BEACONS.items():
            ob = o[m]
            if len(ob) < 100:
                continue
            ts = np.array([x["ts_pc"] for x in ob]) - t0
            sf = np.array([x["sfo"] for x in ob])
            half = ts < s["span_s"] / 2
            a, bb = sf[half], sf[~half]
            d = float(np.median(bb) - np.median(a))
            bs = np.array([
                np.median(rng.choice(bb, bb.size)) -
                np.median(rng.choice(a, a.size)) for _ in range(2000)])
            lo, hi = np.percentile(bs, [2.5, 97.5])
            blk = binned_median(ob, 1800, t0, min_n=5)
            ks = sorted(blk)
            adj = max(abs(blk[ks[i + 1]][0] - blk[ks[i]][0])
                      for i in range(len(ks) - 1)) if len(ks) > 1 else 0.0
            print(f"{t:6s} {b:3s} {np.median(a):+10.5f} "
                  f"{np.median(bb):+10.5f} {d:+10.5f} "
                  f"[{lo:+8.5f},{hi:+8.5f}] {adj:9.5f} "
                  f"{adj/BETWEEN_UNIT_SD:6.2f}")

    print()
    print("=" * 78)
    print("TABLE 3b — SFO in 60 s bins vs noise_floor, per node")
    print("=" * 78)
    for t in tags:
        s, z, o, pb = data[t]
        t0 = s["pc_first"] * 1e-6
        m10 = np.array(s["nf_mean10"])
        nf60 = np.array([np.nanmean(m10[k * 6:(k + 1) * 6])
                         for k in range(len(m10) // 6)])
        bins = {b: binned_median(o[m], 60, t0, min_n=5)
                for m, b in BEACONS.items()}
        print(f"\n[{t}] per-60s-bin correlation r(sfo, noise_floor) "
              f"and r(sfo, resid):")
        for b, bb in bins.items():
            ks = np.array(sorted(k for k in bb if k < len(nf60)))
            if ks.size < 10:
                print(f"    {b}: too few bins")
                continue
            sf = np.array([bb[k][0] for k in ks])
            rd = np.array([bb[k][2] for k in ks])
            nfv = nf60[ks]
            ok = ~np.isnan(nfv) & ~np.isnan(rd)
            r_nf = (np.corrcoef(sf[ok], nfv[ok])[0, 1]
                    if np.std(nfv[ok]) > 0 else float("nan"))
            r_rd = np.corrcoef(sf[ok], rd[ok])[0, 1]
            print(f"    {b}: bins={ok.sum():4d}  r(sfo,nf)={r_nf:+.3f}  "
                  f"r(sfo,resid)={r_rd:+.3f}  "
                  f"sd(nf)={np.nanstd(nfv[ok]):.4f}")

    print()
    print("=" * 78)
    print("TABLE 4 — run integrity")
    print("=" * 78)
    for t in tags:
        s, z, o, pb = data[t]
        d = s["drops_total"]
        kept = s["n_rows"]
        print(f"\n[{t}]")
        print(f"  delivered rows              {kept:,}")
        print(f"  queue drops (wrap-safe,     {d:,}")
        print(f"    corrupt rows removed)")
        print(f"  endpoint cross-check        {s['drops_endpoint']:,}"
              f"  {'AGREES' if s['drops_endpoint']==d else 'DISAGREES'}")
        print(f"  u16 counter wraps           {s['drop_wraps']}")
        print(f"  loss = drops/(kept+drops)   "
              f"{100*d/(kept+d):.3f} %")
        print(f"  shipped one-wrap estimator  {s['naive_onewrap']:,} "
              f"(understates by {d/max(s['naive_onewrap'],1):.2f}x)")
        print(f"  positive-delta-only sum     {s['naive_positive']:,}")
        kps = z["kept_per_s"]; dps = z["drops_per_s"]
        print(f"  frames/s  mean {kps.mean():.2f}  median "
              f"{np.median(kps):.1f}  p1 {np.percentile(kps,1):.1f}  "
              f"p99 {np.percentile(kps,99):.1f}  min {kps.min()}  "
              f"max {kps.max()}")
        print(f"  seconds with 0 frames       {int((kps==0).sum())}")
        if (kps == 0).sum():
            zi = np.flatnonzero(kps == 0)
            runs = np.split(zi, np.flatnonzero(np.diff(zi) != 1) + 1)
            print(f"    longest zero-frame run    {max(len(r) for r in runs)} s"
                  f"  at t = {max(runs, key=len)[0]} s")
        print(f"  drops/s   mean {dps.mean():.2f}  median "
              f"{np.median(dps):.1f}  p90 {np.percentile(dps,90):.1f}  "
              f"p99 {np.percentile(dps,99):.1f}  max {dps.max():.0f}")
        print(f"  seconds with 0 drops        {int((dps==0).sum())} of "
              f"{dps.size}")
        srt = np.sort(dps)[::-1]
        cs = np.cumsum(srt) / max(srt.sum(), 1)
        for frac in (0.01, 0.05, 0.10, 0.25, 0.50):
            k = max(1, int(frac * dps.size))
            print(f"    share of drops in worst {frac*100:4.0f} % of seconds"
                  f"  {100*cs[k-1]:.1f} %")
        # rate by 30-min block
        nb = kps.size // 1800 + 1
        print("  frames/s and drops/s by 30-min block:")
        for k in range(nb):
            seg = kps[k * 1800:(k + 1) * 1800]
            segd = dps[k * 1800:(k + 1) * 1800]
            if seg.size < 60:
                continue
            print(f"    t = {k*0.5:5.2f}-{(k+1)*0.5:5.2f} h  "
                  f"kept {seg.mean():7.2f} fps   drops {segd.mean():7.2f}/s  "
                  f"offered {seg.mean()+segd.mean():7.2f} fps")
        print(f"  largest pc_time batch gap   {s['pc_gap_max_us']/1e6:.3f} s")
        print("  10 largest pc_time gaps (t, gap_s):")
        for tt, g in s["pc_gap_detail"]:
            print(f"    t = {tt:9.1f} s   {g/1e6:.4f} s")
        print(f"  esp_timestamp u32 wraps     {s['esp_wraps']} "
              f"(expected {s['span_s']/4294.967:.1f})")
        for tt, a, b in s["esp_neg_detail"]:
            print(f"    t = {tt:9.1f} s   {a} -> {b}"
                  f"   {'clean wrap' if a > 4_200_000_000 else 'NOT A WRAP'}")
        print(f"  largest esp gap             "
              f"{s['esp_gap_max_us']/1e6:.4f} s at t = {s['esp_gap_max_t']:.1f} s")

    print()
    print("=" * 78)
    print("TABLE 5 — MAC census, ghost screen")
    print("=" * 78)
    # sustained set = MACs with >= SUSTAIN frames on either node
    SUSTAIN = args.sustain
    sustained = set()
    for t in tags:
        s, z, o, pb = data[t]
        mc = np.array(s["mac_count"])
        for i in np.flatnonzero(mc >= SUSTAIN):
            sustained.add(s["mac_names"][i])
    print(f"\nsustained set (>= {SUSTAIN} frames on either node): "
          f"{len(sustained)}")
    for m in sorted(sustained):
        print(f"    {m}")

    seen = {t: dict(zip(data[t][0]["mac_names"], data[t][0]["mac_count"]))
            for t in tags}
    allmacs = sorted(set().union(*[set(v) for v in seen.values()]))
    print(f"\nunion of both nodes: {len(allmacs)} distinct MACs")

    hdr = (f"{'mac':19s} " + " ".join(f"{t+' n':>9s}" for t in tags) +
           f" {'bad%':>6s} {'span_s':>9s} {'bins':>5s} {'nn':>3s} "
           f"{'nearest sustained':19s} {'nb':>3s} {'nearest bigger':19s} "
           f"{'len':>5s} {'rssi med':>9s}")
    print("\n" + hdr)
    print("-" * len(hdr))
    total_n = {m: sum(seen[t].get(m, 0) for t in tags) for m in allmacs}
    rows = []
    for m in allmacs:
        ns = [seen[t].get(m, 0) for t in tags]
        # richest node for this MAC
        ti = int(np.argmax(ns))
        s, z, o, pb = data[tags[ti]]
        i = s["mac_names"].index(m)
        bad = s["mac_bad"][i]
        badp = 100 * bad / max(ns[ti], 1)
        spanm = s["mac_last"][i] - s["mac_first"][i]
        act = z["act"][i]
        nbins = int((act > 0).sum())
        rh = z["rs_hist"][i]
        vals = np.repeat(np.arange(129) - 128, rh)
        rmed = float(np.median(vals)) if vals.size else float("nan")
        lh = s["len_hist"].get(m, {})
        dom_len = max(lh, key=lh.get) if lh else "-"
        # nearest sustained MAC other than itself
        cands = [(mac_octet_distance(m, x), x) for x in sustained if x != m]
        d, nearest = min(cands) if cands else (6, "-")
        # nearest MAC that is at least 20x more frequent than this one
        big = [(mac_octet_distance(m, x), x) for x in allmacs
               if x != m and total_n[x] >= 20 * max(total_n[m], 1)]
        d2, near2 = min(big) if big else (6, "-")
        rows.append((m, ns, badp, spanm, nbins, d, nearest, d2, near2,
                     dom_len, rmed))
    rows.sort(key=lambda r: -sum(r[1]))
    for (m, ns, badp, spanm, nbins, d, nearest, d2, near2, dom_len,
         rmed) in rows:
        print(f"{m:19s} " + " ".join(f"{x:>9,}" for x in ns) +
              f" {badp:6.1f} {spanm:9.1f} {nbins:5d} {d:3d} "
              f"{nearest:19s} {d2:3d} {near2:19s} {str(dom_len):>5s} "
              f"{rmed:9.1f}")

    print()
    print("=" * 78)
    print("TABLE 5b — cross-receiver temporal coincidence")
    print("=" * 78)
    print("  Two receivers a few inches apart decode independently, so a")
    print("  bit error that invents a MAC on one cannot invent the same MAC")
    print("  on the other in the same 300 s bin.  Jaccard = |bins active on")
    print("  both| / |bins active on either|.  High J with n>1 on both is")
    print("  over-the-air traffic; J=0 with traffic on both is suspicious.")
    ta, tb = tags[0], tags[1]
    sa, za, _, _ = data[ta]
    sb, zb, _, _ = data[tb]
    print(f"\n{'mac':19s} {ta+' n':>9s} {tb+' n':>9s} {'binsA':>6s} "
          f"{'binsB':>6s} {'both':>5s} {'either':>6s} {'J':>6s}")
    both = [m for m in allmacs
            if seen[ta].get(m, 0) > 0 and seen[tb].get(m, 0) > 0]
    jrows = []
    for m in both:
        ia = sa["mac_names"].index(m)
        ib = sb["mac_names"].index(m)
        aa = za["act"][ia] > 0
        ab = zb["act"][ib] > 0
        k = min(aa.size, ab.size)
        aa, ab = aa[:k], ab[:k]
        inter = int((aa & ab).sum())
        union = int((aa | ab).sum())
        jrows.append((m, seen[ta][m], seen[tb][m], int(aa.sum()),
                      int(ab.sum()), inter, union,
                      inter / union if union else 0.0))
    jrows.sort(key=lambda r: -(r[1] + r[2]))
    for r in jrows:
        print(f"{r[0]:19s} {r[1]:>9,} {r[2]:>9,} {r[3]:>6d} {r[4]:>6d} "
              f"{r[5]:>5d} {r[6]:>6d} {r[7]:>6.3f}")
    print(f"\n  MACs on both nodes: {len(both)} of {len(allmacs)}")

    print()
    print("=" * 78)
    print("TABLE 5c — census classification")
    print("=" * 78)
    print("  Criteria, applied in order; first match wins.")
    print("  X  decode artefact: >= 50 % of its rows carry an out-of-range")
    print("     value in a field unrelated to the MAC (node_id, env_id,")
    print("     channel, csi_len, noise_floor, rssi), OR a dominant csi_len")
    print("     that is neither 128 nor 256, OR <= 4 frames and within 2")
    print("     octets of a MAC at least 20x more common.")
    print("  R  sustained: >= 1000 frames on at least one node, no flagged")
    print("     rows, active in >= 20 of the 300 s bins.")
    print("  P  intermittent but corroborated: >= 5 frames, no flagged rows,")
    print("     and seen on both nodes in at least one common 300 s bin.")
    print("  S  singleton / near-singleton, fields all clean, no near-miss:")
    print("     cannot be classified either way from these files.")
    jmap = {r[0]: r for r in jrows}
    cls = {}
    for (m, ns, badp, spanm, nbins, d, nearest, d2, near2, dom_len,
         rmed) in rows:
        tot = sum(ns)
        dl = int(dom_len) if str(dom_len).isdigit() else -1
        if badp >= 50 or dl not in VALID_LEN or (tot <= 4 and d2 <= 2):
            cls[m] = "X"
        elif max(ns) >= 1000 and badp < 1.0 and nbins >= 20:
            cls[m] = "R"
        elif (tot >= 5 and badp < 1.0 and m in jmap and jmap[m][5] >= 1):
            cls[m] = "P"
        else:
            cls[m] = "S"
    for c, label in (("R", "sustained"), ("P", "intermittent, corroborated"),
                     ("S", "unresolved"), ("X", "decode artefact")):
        ms = [m for m in cls if cls[m] == c]
        nf_tot = sum(sum(seen[t].get(m, 0) for t in tags) for m in ms)
        print(f"\n  {c}  {label}: {len(ms)} MACs, {nf_tot:,} frames")
        per = {t: sum(1 for m in ms if seen[t].get(m, 0) > 0) for t in tags}
        print(f"       present on: " +
              "  ".join(f"{t}={per[t]}" for t in tags))
        if c != "X":
            for m in sorted(ms, key=lambda x: -sum(seen[t].get(x, 0)
                                                   for t in tags)):
                la = "LAA" if int(m[:2], 16) & 0x02 else "OUI"
                print(f"       {m}  {la}  " +
                      "  ".join(f"{t}={seen[t].get(m,0):,}" for t in tags))
    # How many artefacts look like CSI sample bytes rather than like a
    # near-miss of a real MAC?  CSI values are int8 and small, so a resync
    # into the payload yields six octets that all read as roughly [-64,64].
    xs = [m for m in cls if cls[m] == "X"]
    sample_like = [m for m in xs
                   if all(int(o, 16) <= 0x40 or int(o, 16) >= 0xc0
                          for o in m.split(":"))]
    near_miss = [m for m in xs
                 if min((mac_octet_distance(m, y) for y in sustained),
                        default=6) <= 2]
    print(f"\n  of the {len(xs)} class-X MACs: {len(sample_like)} have all "
          f"six octets in the range an int8 CSI sample can take")
    print(f"  ([-64,+64], i.e. a resync into the payload), and "
          f"{len(near_miss)} are within 2 octets of a beacon.")

    print("\n  LAA = locally-administered bit set in the first octet, i.e. a")
    print("  randomised address; one physical device can present several")
    print("  over a night, so the LAA rows are an upper bound on devices.")
    print("\n  per node, after screening:")
    for t in tags:
        tot = len(seen[t])
        nx = sum(1 for m in seen[t] if cls[m] == "X")
        print(f"    {t}: {tot} distinct MACs in the file, {nx} class X, "
              f"{tot - nx} surviving")

    print()
    print("=" * 78)
    print("TABLE 4b — delivered frames per beacon, per 30-min block")
    print("=" * 78)
    for t in tags:
        s, z, o, pb = data[t]
        idx = {b: s["mac_names"].index(m) for m, b in BEACONS.items()
               if m in s["mac_names"]}
        print(f"\n[{t}]  t(h)   " +
              "   ".join(f"{b:>8s}" for b in idx) + "      total")
        a = z["act"]                      # per-MAC per-300 s counts
        nblk = a.shape[1] // 6 + 1
        for k in range(nblk):
            seg = slice(k * 6, (k + 1) * 6)
            secs = min(1800.0, max(0.0, s["span_s"] - k * 1800))
            if secs < 300:
                continue
            vals = [a[i, seg].sum() / secs for b, i in idx.items()]
            print(f"      {k*0.5:5.2f}   " +
                  "   ".join(f"{v:8.2f}" for v in vals) +
                  f"   {sum(vals):8.2f} fps")

    print()
    print("=" * 78)
    print("TABLE 6 — RSSI distribution per node (all frames)")
    print("=" * 78)
    for t in tags:
        s, z, o, pb = data[t]
        rh = z["rs_hist"].sum(axis=0)
        vals = np.repeat(np.arange(129) - 128, rh)
        print(f"\n[{t}] all frames  n={vals.size:,}  mean {vals.mean():.2f} "
              f"median {np.median(vals):.0f}  "
              f"p1 {np.percentile(vals,1):.0f} p5 {np.percentile(vals,5):.0f} "
              f"p95 {np.percentile(vals,95):.0f} "
              f"p99 {np.percentile(vals,99):.0f} "
              f"min {vals.min()} max {vals.max()}")
        # non-beacon frames only
        bi = [s["mac_names"].index(m) for m in BEACONS
              if m in s["mac_names"]]
        mask = np.ones(z["rs_hist"].shape[0], bool)
        mask[bi] = False
        rh2 = z["rs_hist"][mask].sum(axis=0)
        v2 = np.repeat(np.arange(129) - 128, rh2)
        if v2.size:
            print(f"       non-beacon n={v2.size:,}  mean {v2.mean():.2f} "
                  f"median {np.median(v2):.0f} "
                  f"p5 {np.percentile(v2,5):.0f} "
                  f"p95 {np.percentile(v2,95):.0f} "
                  f"min {v2.min()} max {v2.max()}")
        # MACs unique to this node
        others = set().union(*[set(seen[x]) for x in tags if x != t])
        uniq = [mm for mm in seen[t] if mm not in others]
        ui = [s["mac_names"].index(mm) for mm in uniq]
        if ui:
            rh3 = z["rs_hist"][ui].sum(axis=0)
            v3 = np.repeat(np.arange(129) - 128, rh3)
            print(f"       MACs unique to {t}: {len(uniq)} MACs, "
                  f"{v3.size:,} frames, mean rssi {v3.mean():.2f}, "
                  f"median {np.median(v3):.0f}, "
                  f"p5 {np.percentile(v3,5):.0f}, "
                  f"p95 {np.percentile(v3,95):.0f}")

    print()
    print("=" * 78)
    print("TABLE 7 — verbatim rows for rare MACs (forensics)")
    print("=" * 78)
    for t in tags:
        s, z, o, pb = data[t]
        det = s["detail"]
        keys = sorted(det, key=lambda m: len(det[m]))
        shown = 0
        for m in keys:
            if args.detail_macs and m not in args.detail_macs.split(","):
                continue
            print(f"\n[{t}] {m}  ({seen[t].get(m,0)} frames total)")
            for r in det[m][:6]:
                print(f"    t={r['t']:9.2f} rssi={r['rssi']:5d} "
                      f"nf={r['nf']:5d} ch={r['ch']:4d} len={r['ln']:4d} "
                      f"node={r['node']:4d} env={r['env']:3d} "
                      f"drop={r['drop']:6d} "
                      f"{'CORRUPT' if r['corrupt'] else 'clean'}")
            shown += 1
            if shown >= args.detail_limit:
                print(f"    ... ({len(keys)-shown} more rare MACs on {t})")
                break


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("part", help="parse one byte range of one capture")
    p.add_argument("path")
    p.add_argument("--tag", required=True)
    p.add_argument("--part", type=int, required=True)
    p.add_argument("--nparts", type=int, required=True)
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.set_defaults(func=cmd_part)

    p = sub.add_parser("merge", help="merge parts and derive everything")
    p.add_argument("path")
    p.add_argument("--tag", required=True)
    p.add_argument("--nparts", type=int, required=True)
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.add_argument("--expect-lines", type=int, default=0,
                   help="cross-check against an independent `wc -l`")
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("report")
    p.add_argument("--tags", required=True)
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.add_argument("--sustain", type=int, default=1000)
    p.add_argument("--detail-limit", type=int, default=12)
    p.add_argument("--detail-macs", default="")
    p.add_argument("--step-thresh", type=float, default=0.25,
                   help="dB move in the smoothed noise_floor to call a step")
    p.set_defaults(func=cmd_report)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
