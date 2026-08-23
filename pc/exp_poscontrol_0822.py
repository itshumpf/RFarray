#!/usr/bin/env python3
"""Positive control (final minutes) + inter-receiver SFO across ambient
sources, on the 2026-08-22 02:30:34 -> 08:58 overnight pair. Read-only.

Two questions, one pass over the two captures.

ANALYSIS 1 — the positive control.
  The operator states he re-entered the room and sat at his desk about five
  minutes before the capture ended.  `docs/OVERNIGHT_2026-08-22.md` treated
  the whole file as a negative control and labelled the late excursions
  "final minutes"/shutdown.  This asks, at fine resolution over the last
  ~1800 s and per node and per beacon, whether the 2026-08-21 t = 930 s
  signature (`docs/S3_SFO_STEPS.md` §0, §3, §6) reappears:
  `noise_floor` departing a pinned value and NOT reverting, RSSI stepping on
  all three beacons at one instant, SFO moving on all three in different
  directions, and frame-reject/residual moving with it.

ANALYSIS 2 — is d0wd - s3 SFO a receiver-pair constant?
  `docs/DUAL_RX_2026-08-21.md` §3.4 refuted a constant offset on three
  beacons.  This capture has corroborated ambient sources seen by both
  receivers (`docs/OVERNIGHT_2026-08-22.md` §5.3), so the same test is run
  per source, with the spread of the per-source difference measured against
  `BETWEEN_UNIT_SD`.

Scope and safety
----------------
- `data/raw/*` is opened "rb" only.  Nothing there is written, renamed or
  deleted.  No serial port is opened.  Nothing is staged or committed.
- Caches go to `--cache`, which defaults OUTSIDE the repo tree.
- Repo files written by this pass: this one and
  `docs/POSITIVE_CONTROL_0822.md`.

Phase work
----------
`pc/rff/dsp.py`'s `FrameEstimator` and the shipped gates
(`inlier_ratio >= 0.6`, `resid_std <= 0.8`, `WindowAggregator(window=64)`).
`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` are
NOT used -- `docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 establishes all three
have the DC/guard-band index wrong and `pc/test_rff_synth.py` test 7 shows
`phase_skew` returns the opposite sign.

The per-frame `slope` is invariant to `unwrap_continuity`'s 2*pi shift (it
adds a constant to every subcarrier), so a slope does not depend on which
byte range it was computed in.  The RANSAC rng and the aggregator buffers
DO carry state, so they are pickled forward from part to part, which makes
the multi-part run frame-for-frame identical to one uninterrupted pass.

Corrupt-row screen -- reused unchanged from `docs/OVERNIGHT_2026-08-22.md`
§1 / `pc/exp_overnight_0822.py`: route 1 is a width-9 median filter on
`dropped` with tolerance 100, route 2 is field plausibility on six columns
unrelated to `dropped`.  Both are needed: the d0wd row at line 95,349 is
invisible to route 2 and inflates naive drop accounting 514x, and route 2
is what removes the ~100 artefact MACs.  `csi_len` 384 IS legal
(`pc/rff/protocol.py:31`).

Usage
-----
    D=data/raw/d0wd_20260822_023034.csv
    S=data/raw/s3_20260822_023034.csv
    for p in $(seq 0 7); do
        python3 pc/exp_poscontrol_0822.py part $D --tag d0wd --part $p --nparts 8
        python3 pc/exp_poscontrol_0822.py part $S --tag s3   --part $p --nparts 8
    done
    python3 pc/exp_poscontrol_0822.py merge $D --tag d0wd --nparts 8 --expect-lines 2983560
    python3 pc/exp_poscontrol_0822.py merge $S --tag s3   --nparts 8 --expect-lines 3564005
    python3 pc/exp_poscontrol_0822.py report --tags d0wd,s3
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

# corrupt-row screen, route 1
MF_W, MF_TOL = 9, 100
# corrupt-row screen, route 2
RSSI_LO, RSSI_HI = -100, -10
NF_LO, NF_HI = -110, -70
VALID_LEN = (128, 256, 384)      # pc/rff/protocol.py:31 admits 384

# yardsticks, quoted from the code that defines them
BETWEEN_UNIT_SD = 0.00237        # pc/exp_thermal_evidence.py:129
TWIN_DSFO = 0.00080              # pc/exp_lot_hypothesis.py:85-86

# per-frame phase records are kept for every non-beacon source (they are
# few) and, for every source, inside the tail region.
TAIL_KEEP_S = 1800.0

DEFAULT_CACHE = "/tmp/poscontrol_0822_cache"


def med_filt_chunked(x, w=MF_W, chunk=1_000_000):
    pad = w // 2
    out = np.empty(x.size, dtype=np.float64)
    xp = np.pad(x, pad, mode="edge")
    for s in range(0, x.size, chunk):
        e = min(s + chunk, x.size)
        sw = np.lib.stride_tricks.sliding_window_view(xp[s:e + 2 * pad], w)
        out[s:e] = np.median(sw, axis=1)
    return out


class TrackedAggregator(WindowAggregator):
    """WindowAggregator + reject accounting + per-window mean resid/inlier.

    Acceptance is read off the parent's own behaviour, never re-derived.
    """

    def __init__(self, *a, **kw):
        WindowAggregator.__init__(self, *a, **kw)
        self.n_fed = self.n_unusable = 0
        self.n_rej_inlier = self.n_rej_resid = self.n_rej_other = 0
        self.n_accepted = self.n_windows = 0
        self._resids = []
        self._inls = []

    def feed(self, est, ts_us, rssi):
        self.n_fed += 1
        n_before = len(self._buf)
        obs = WindowAggregator.feed(self, est, ts_us, rssi)
        grew = (obs is not None) or (len(self._buf) != n_before)
        if grew:
            self.n_accepted += 1
            self._resids.append(est["resid_std"])
            self._inls.append(est["inlier_ratio"])
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
            obs["inlier"] = float(np.mean(self._inls))
            self._resids = []
            self._inls = []
        return obs


def last_pc_time(path):
    """Read the file's final `pc_time_us` without loading the file."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        back = min(size, 1 << 16)
        f.seek(size - back)
        tailbytes = f.read(back)
    line = tailbytes.rsplit(b"\n", 2)[-2] if tailbytes.endswith(b"\n") \
        else tailbytes.rsplit(b"\n", 1)[-1]
    return int(line.split(b",", 1)[0])


def first_pc_time(path):
    with open(path, "rb") as f:
        f.readline()
        return int(f.readline().split(b",", 1)[0])


# ------------------------------------------------------- parse a byte range

def cmd_part(args):
    path, tag = args.path, args.tag
    part, nparts = args.part, args.nparts
    os.makedirs(args.cache, exist_ok=True)
    t_start = time.time()

    size = os.path.getsize(path)
    start = size * part // nparts
    end = size * (part + 1) // nparts
    statef = os.path.join(args.cache, f"{tag}_state.pkl")

    if part == 0:
        t0_us = first_pc_time(path)
        tend_us = last_pc_time(path)
        mac_ids, mac_names = {}, []
        est, agg = {}, {}
        pcbuf = {}
        n_short = {}
        header = None
    else:
        with open(statef, "rb") as fh:
            st = pickle.load(fh)
        if st["next_part"] != part:
            raise SystemExit(f"state is at part {st['next_part']}, "
                             f"asked for {part} - run parts in order")
        t0_us, tend_us = st["t0_us"], st["tend_us"]
        mac_ids, mac_names = st["mac_ids"], st["mac_names"]
        est, agg, pcbuf = st["est"], st["agg"], st["pcbuf"]
        n_short = st["n_short"]
        header = st["header"]

    tail_start_us = tend_us - int(TAIL_KEEP_S * 1e6)

    pc = array("q")
    rssi = array("h"); nf = array("h"); chan = array("h"); ln = array("h")
    node = array("h"); envid = array("h")
    drop = array("i"); midx = array("i")

    # per-frame phase records
    f_mid = array("i"); f_t = array("d"); f_rssi = array("h")
    f_slope = []; f_resid = []; f_inl = []
    obs = {}
    n_lines = n_badsplit = n_badint = 0

    with open(path, "rb") as f:
        if part == 0:
            header = f.readline().decode().strip()
        else:
            f.seek(start - 1)
            f.readline()
        pos = f.tell()
        for raw in f:
            pos += len(raw)
            n_lines += 1
            p = raw.decode("utf-8", "replace").split(",", 9)
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
                v_pc = int(p[0]); v_rssi = int(p[4]); v_nf = int(p[5])
                v_ch = int(p[6]); v_esp = int(p[7]); v_len = int(p[8])
                v_node = int(r[1]); v_env = int(r[2]); v_drop = int(r[3])
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
                est[m] = FrameEstimator()
                agg[m] = TrackedAggregator(window=WINDOW)
                pcbuf[m] = []
                n_short[m] = 0
                obs[m] = obs.get(m, [])

            pc.append(v_pc)
            rssi.append(max(-32768, min(32767, v_rssi)))
            nf.append(max(-32768, min(32767, v_nf)))
            chan.append(max(-32768, min(32767, v_ch)))
            ln.append(max(-32768, min(32767, v_len)))
            node.append(max(-32768, min(32767, v_node)))
            envid.append(max(-32768, min(32767, v_env)))
            drop.append(v_drop)
            midx.append(i)

            cs = r[0]
            if cs[:1] == '"':
                cs = cs[1:-1] if cs[-1:] == '"' else cs[1:]
            # NOTE `cs.split(",", 128)` returns at most 129 items, so a row
            # carrying exactly 128 CSI values yields 128 -- and the test
            # `len < 129` used by `pc/exp_overnight_0822.py` then discards
            # it.  Every `csi_len = 128` frame in these files is dropped by
            # that off-by-one, which is all of the ambient traffic (§ the
            # doc).  128 values is exactly one LLTF (64 complex int8 pairs)
            # and `pc/rff_offline.py:203` (`np.fromstring(..., sep=",")` ->
            # `csi_to_complex`, which needs `size >= 128`) accepts it.
            vals = cs.split(",", 128)
            if len(vals) < 128:
                n_short[m] += 1
                if pos >= end:
                    break
                continue
            try:
                vv = np.array(vals[:128], dtype=np.float64)
            except ValueError:
                n_short[m] += 1
                if pos >= end:
                    break
                continue
            e = est[m].feed(vv, v_esp)
            pcbuf[m].append(v_pc)
            o = agg[m].feed(e, v_esp, v_rssi)
            if o is not None:
                o["ts_pc"] = (float(np.median(pcbuf[m])) - t0_us) * 1e-6
                pcbuf[m] = []
                obs.setdefault(m, []).append(o)
            if e is not None and (m not in BEACONS or v_pc >= tail_start_us):
                f_mid.append(i)
                f_t.append((v_pc - t0_us) * 1e-6)
                f_rssi.append(max(-32768, min(32767, v_rssi)))
                f_slope.append(e["slope"])
                f_resid.append(e["resid_std"])
                f_inl.append(e["inlier_ratio"])
            if pos >= end:
                break

    np.savez(
        os.path.join(args.cache, f"{tag}_p{part:02d}.npz"),
        pc=np.frombuffer(pc, dtype=np.int64),
        rssi=np.frombuffer(rssi, dtype=np.int16),
        nf=np.frombuffer(nf, dtype=np.int16),
        chan=np.frombuffer(chan, dtype=np.int16),
        ln=np.frombuffer(ln, dtype=np.int16),
        node=np.frombuffer(node, dtype=np.int16),
        envid=np.frombuffer(envid, dtype=np.int16),
        drop=np.frombuffer(drop, dtype=np.int32),
        midx=np.frombuffer(midx, dtype=np.int32),
        f_mid=np.frombuffer(f_mid, dtype=np.int32),
        f_t=np.frombuffer(f_t, dtype=np.float64),
        f_rssi=np.frombuffer(f_rssi, dtype=np.int16),
        f_slope=np.array(f_slope, dtype=np.float32),
        f_resid=np.array(f_resid, dtype=np.float32),
        f_inl=np.array(f_inl, dtype=np.float32),
    )
    with open(os.path.join(args.cache, f"{tag}_obs_p{part:02d}.pkl"),
              "wb") as fh:
        pickle.dump(obs, fh)
    with open(statef, "wb") as fh:
        pickle.dump(dict(next_part=part + 1, t0_us=t0_us, tend_us=tend_us,
                         mac_ids=mac_ids, mac_names=mac_names, est=est,
                         agg=agg, pcbuf=pcbuf, n_short=n_short,
                         header=header), fh)
    with open(os.path.join(args.cache, f"{tag}_meta_p{part:02d}.json"),
              "w") as fh:
        json.dump(dict(part=part, nparts=nparts, start=start, end=end,
                       n_lines=n_lines, n_rows=len(pc),
                       n_badsplit=n_badsplit, n_badint=n_badint,
                       path=path, header=header), fh)
    print(f"[{tag} part {part}/{nparts}] bytes {start}..{end} "
          f"lines={n_lines} rows={len(pc)} phase_recs={len(f_slope)} "
          f"in {time.time()-t_start:.1f}s", flush=True)


# --------------------------------------------------- ambient sources only

def cmd_ambient(args):
    """Phase-estimate every non-beacon frame, from a pre-filtered CSV.

    Why this is exact and not a shortcut: `FrameEstimator` is one instance
    per source MAC, so the only state that matters is the order of that
    MAC's own frames, and `grep -v` preserves file order.  Feeding a MAC's
    frames from a file that contains only non-beacon rows therefore
    produces the identical estimator sequence to a full pass.  The
    per-frame `slope` is in any case invariant to the continuity unwrap.

    Ambient sources are ~5 k rows in 6.5 M, so this costs seconds where a
    second full pass costs eleven minutes.
    """
    with open(os.path.join(args.cache, f"{args.tag}_scan.json")) as fh:
        t0_us = json.load(fh)["t0_us"]
    est = {}
    rec = {}
    n_rows = n_short = n_none = 0
    t_start = time.time()
    with open(args.path, "rb") as f:
        first = f.readline()
        if not first.startswith(b"pc_time_us"):
            f.seek(0)
        for raw in f:
            p = raw.decode("utf-8", "replace").split(",", 9)
            if len(p) < 10:
                continue
            r = p[9].rsplit(",", 3)
            if len(r) != 4:
                continue
            try:
                v_pc = int(p[0]); v_rssi = int(p[4]); v_nf = int(p[5])
                v_ch = int(p[6]); v_esp = int(p[7]); v_len = int(p[8])
                v_node = int(r[1]); v_env = int(r[2])
            except ValueError:
                continue
            n_rows += 1
            m = p[3]
            cs = r[0]
            if cs[:1] == '"':
                cs = cs[1:-1] if cs[-1:] == '"' else cs[1:]
            vals = cs.split(",", 128)
            if len(vals) < 128:
                n_short += 1
                continue
            try:
                vv = np.array(vals[:128], dtype=np.float64)
            except ValueError:
                n_short += 1
                continue
            if m not in est:
                est[m] = FrameEstimator()
                rec[m] = []
            e = est[m].feed(vv, v_esp)
            if e is None:
                n_none += 1
                continue
            rec[m].append(((v_pc - t0_us) * 1e-6, e["slope"], e["resid_std"],
                           e["inlier_ratio"], v_rssi, v_len, v_nf, v_ch,
                           v_node, v_env))
    out = {}
    for m, v in rec.items():
        if not v:
            continue
        a = np.array(v, dtype=np.float64)
        out["t__" + m] = a[:, 0]
        out["sl__" + m] = a[:, 1]
        out["rd__" + m] = a[:, 2]
        out["il__" + m] = a[:, 3]
        out["rs__" + m] = a[:, 4]
        out["ln__" + m] = a[:, 5]
        out["nf__" + m] = a[:, 6]
        out["ch__" + m] = a[:, 7]
        out["nd__" + m] = a[:, 8]
        out["ev__" + m] = a[:, 9]
    np.savez_compressed(
        os.path.join(args.cache, f"{args.tag}_ambient.npz"),
        macs=np.array(sorted(rec), dtype=object), **out)
    print(f"[{args.tag} ambient] rows={n_rows:,} short={n_short} "
          f"no_fit={n_none} macs={len(rec)} "
          f"estimated={sum(len(v) for v in rec.values()):,} "
          f"in {time.time()-t_start:.1f}s", flush=True)


# ------------------------------------------------------------------- merge

def cmd_merge(args):
    path, tag = args.path, args.tag
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
    agg = st["agg"]
    t0_us, tend_us = st["t0_us"], st["tend_us"]

    names = ("pc", "rssi", "nf", "chan", "ln", "node", "envid", "drop",
             "midx", "f_mid", "f_t", "f_rssi", "f_slope", "f_resid", "f_inl")
    cols = {k: [] for k in names}
    seams = []
    for p in range(args.nparts):
        z = np.load(os.path.join(args.cache, f"{tag}_p{p:02d}.npz"))
        for k in names:
            cols[k].append(z[k])
        if p:
            seams.append((int(cols["pc"][p - 1][-1]), int(z["pc"][0])))
    pc = np.concatenate(cols["pc"])
    rssi = np.concatenate(cols["rssi"]).astype(np.int32)
    nf = np.concatenate(cols["nf"]).astype(np.int32)
    chan = np.concatenate(cols["chan"]).astype(np.int32)
    ln = np.concatenate(cols["ln"]).astype(np.int32)
    node = np.concatenate(cols["node"]).astype(np.int32)
    envid = np.concatenate(cols["envid"]).astype(np.int32)
    drop = np.concatenate(cols["drop"]).astype(np.int64)
    midx = np.concatenate(cols["midx"])
    f_mid = np.concatenate(cols["f_mid"])
    f_t = np.concatenate(cols["f_t"])
    f_rssi = np.concatenate(cols["f_rssi"]).astype(np.int32)
    f_slope = np.concatenate(cols["f_slope"]).astype(np.float64)
    f_resid = np.concatenate(cols["f_resid"]).astype(np.float64)
    f_inl = np.concatenate(cols["f_inl"]).astype(np.float64)
    del cols

    obs = {}
    for p in range(args.nparts):
        with open(os.path.join(args.cache,
                               f"{tag}_obs_p{p:02d}.pkl"), "rb") as fh:
            o = pickle.load(fh)
        for m, v in o.items():
            obs.setdefault(m, []).extend(v)

    n_lines = sum(m["n_lines"] for m in metas)
    seam_bad = sum(1 for a, b in seams if b < a)
    print(f"[{tag}] merged {args.nparts} parts: {n_lines:,} lines, "
          f"{pc.size:,} rows, {len(seams)} seams, {seam_bad} with "
          f"pc_time going backwards", flush=True)
    if args.expect_lines and n_lines != args.expect_lines:
        print(f"  !! line count {n_lines} != expected {args.expect_lines}")

    t = (pc - t0_us) * 1e-6
    span = float(t[-1])

    # ---- corrupt-row screens
    node_mode = int(np.bincount(node - node.min()).argmax() + node.min())
    ch_mode = int(np.bincount(np.clip(chan, 0, 300)).argmax())
    bad_field = ((node != node_mode) | (envid != 0) | (chan != ch_mode)
                 | ~np.isin(ln, VALID_LEN)
                 | (nf < NF_LO) | (nf > NF_HI)
                 | (rssi < RSSI_LO) | (rssi > RSSI_HI))
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

    sec = t.astype(np.int64)
    nsec = int(sec[-1]) + 1
    kept_per_s = np.bincount(sec, minlength=nsec)
    drops_per_s = np.bincount(sec[good][1:], weights=delta_uw,
                              minlength=nsec)

    # ---- noise_floor per 10 s bin, clean rows only
    BIN = 10
    tg = t[good]
    nfg = nf[good]
    b10 = (tg / BIN).astype(np.int64)
    nb10 = int(b10[-1]) + 1
    lo = int(nfg.min())
    spanv = int(nfg.max()) - lo + 1
    cnt10 = np.bincount(b10 * spanv + (nfg - lo),
                        minlength=nb10 * spanv).reshape(nb10, spanv)
    modal10 = cnt10.argmax(axis=1) + lo
    tot10 = cnt10.sum(1)
    mean10 = np.where(tot10 > 0,
                      (cnt10 * (np.arange(spanv) + lo)).sum(1)
                      / np.maximum(tot10, 1), np.nan)

    # ---- per-MAC census
    nmac = len(mac_names)
    mac_count = np.bincount(midx, minlength=nmac)
    mac_bad = np.bincount(midx[corrupt], minlength=nmac)
    mac_rssi_sum = np.bincount(midx[good], weights=rssi[good],
                               minlength=nmac)
    mac_count_good = np.bincount(midx[good], minlength=nmac)
    mac_first = np.full(nmac, np.inf)
    mac_last = np.full(nmac, -np.inf)
    np.minimum.at(mac_first, midx, t)
    np.maximum.at(mac_last, midx, t)
    BINA = 300
    ba = (t / BINA).astype(np.int64)
    nba = int(ba[-1]) + 1
    act = np.bincount(midx * nba + ba,
                      minlength=nmac * nba).reshape(nmac, nba)
    len_dom = {}
    for L in np.unique(ln):
        c = np.bincount(midx[ln == L], minlength=nmac)
        for i in np.flatnonzero(c):
            len_dom.setdefault(mac_names[i], {})[int(L)] = int(c[i])

    # ---- fine (per-10 s) per-beacon series over the tail
    TAILB = 10
    tail0 = span - TAIL_KEEP_S
    perb = {}
    for m, b in BEACONS.items():
        if m not in mac_names:
            continue
        i = mac_names.index(m)
        sel = (midx == i) & good
        tb = t[sel]
        bb = (tb / 60).astype(np.int64)
        nbb = int(bb.max()) + 1
        c60 = np.bincount(bb, minlength=nbb)
        perb[b] = dict(
            n60=c60.tolist(),
            nf60=(np.bincount(bb, weights=nf[sel], minlength=nbb)
                  / np.maximum(c60, 1)).tolist(),
            rssi60=(np.bincount(bb, weights=rssi[sel], minlength=nbb)
                    / np.maximum(c60, 1)).tolist(),
        )
        selt = sel & (t >= tail0)
        tt = t[selt]
        kb = ((tt - tail0) / TAILB).astype(np.int64)
        nkb = int(TAIL_KEEP_S // TAILB) + 1
        ck = np.bincount(kb, minlength=nkb)
        perb[b]["tail_n"] = ck.tolist()
        perb[b]["tail_rssi"] = (np.bincount(kb, weights=rssi[selt],
                                            minlength=nkb)
                                / np.maximum(ck, 1)).tolist()
        perb[b]["tail_nf"] = (np.bincount(kb, weights=nf[selt],
                                          minlength=nkb)
                              / np.maximum(ck, 1)).tolist()

    # node-level tail noise_floor at 10 s
    selt = good & (t >= tail0)
    kb = ((t[selt] - tail0) / TAILB).astype(np.int64)
    nkb = int(TAIL_KEEP_S // TAILB) + 1
    ckn = np.bincount(kb, minlength=nkb)
    tail_nf_mean = (np.bincount(kb, weights=nf[selt], minlength=nkb)
                    / np.maximum(ckn, 1))
    tail_nf_modal = []
    for k in range(nkb):
        v = nf[selt][kb == k]
        tail_nf_modal.append(int(Counter(v.tolist()).most_common(1)[0][0])
                             if v.size else 0)

    out = dict(
        tag=tag, path=path, header=st["header"], n_lines=n_lines,
        n_rows=int(pc.size), seams=seams, seam_bad=seam_bad,
        t0_us=t0_us, tend_us=tend_us, span_s=span,
        node_mode=node_mode, ch_mode=ch_mode,
        node_hist={int(k): int(v) for k, v in Counter(node.tolist()).items()},
        n_corrupt=int(corrupt.sum()), n_bad_field=int(bad_field.sum()),
        n_bad_drop=int(bad_drop.sum()),
        drops_total=drops_total, drops_endpoint=endpoint, drop_wraps=wraps,
        nf_hist={int(k): int(v) for k, v in Counter(nfg.tolist()).items()},
        mac_names=mac_names, mac_count=mac_count.tolist(),
        mac_count_good=mac_count_good.tolist(), mac_bad=mac_bad.tolist(),
        mac_rssi_mean=(mac_rssi_sum
                       / np.maximum(mac_count_good, 1)).tolist(),
        mac_first=mac_first.tolist(), mac_last=mac_last.tolist(),
        len_dom=len_dom, n_short=st["n_short"],
        tail0=tail0, tail_bin_s=TAILB,
        tail_nf_mean=tail_nf_mean.tolist(),
        tail_nf_modal=tail_nf_modal, tail_n=ckn.tolist(),
        agg_stats={m: dict(fed=a.n_fed, accepted=a.n_accepted,
                           unusable=a.n_unusable,
                           rej_inlier=a.n_rej_inlier,
                           rej_resid=a.n_rej_resid,
                           rej_other=a.n_rej_other,
                           windows=a.n_windows)
                   for m, a in agg.items() if a.n_fed > 0},
    )
    with open(os.path.join(args.cache, f"{tag}_scan.json"), "w") as f:
        json.dump(out, f)
    with open(os.path.join(args.cache, f"{tag}_perbeacon.json"), "w") as f:
        json.dump(perb, f)
    np.savez_compressed(
        os.path.join(args.cache, f"{tag}_series.npz"),
        kept_per_s=kept_per_s, drops_per_s=drops_per_s,
        modal10=modal10, mean10=mean10, act=act,
        f_mid=f_mid, f_t=f_t, f_rssi=f_rssi, f_slope=f_slope,
        f_resid=f_resid, f_inl=f_inl)
    with open(os.path.join(args.cache, f"{tag}_obs.pkl"), "wb") as f:
        pickle.dump(obs, f)
    print(f"[{tag}] rows={pc.size} span={span:.1f}s corrupt={int(corrupt.sum())} "
          f"drops={drops_total} wraps={wraps} macs={nmac} "
          f"phase_recs={f_slope.size}", flush=True)


# ------------------------------------------------------------------ report

def load(cache, tag):
    with open(os.path.join(cache, f"{tag}_scan.json")) as f:
        s = json.load(f)
    z = np.load(os.path.join(cache, f"{tag}_series.npz"))
    with open(os.path.join(cache, f"{tag}_obs.pkl"), "rb") as f:
        o = pickle.load(f)
    with open(os.path.join(cache, f"{tag}_perbeacon.json")) as f:
        pb = json.load(f)
    amb = None
    ap = os.path.join(cache, f"{tag}_ambient.npz")
    if os.path.exists(ap):
        amb = np.load(ap, allow_pickle=True)
    return s, z, o, pb, amb


def boot_med_ci(x, n=4000, seed=0):
    if x.size == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    bs = np.median(rng.choice(x, (n, x.size)), axis=1) if x.size <= 4000 \
        else np.array([np.median(rng.choice(x, x.size)) for _ in range(n)])
    return float(np.median(x)), float(np.percentile(bs, 2.5)), \
        float(np.percentile(bs, 97.5))


def boot_diff_ci(a, b, n=4000, seed=0):
    """median(a) - median(b), 95 % CI by bootstrap over windows."""
    rng = np.random.default_rng(seed)
    if a.size == 0 or b.size == 0:
        return float("nan"), float("nan"), float("nan")
    ds = np.empty(n)
    for k in range(n):
        ds[k] = np.median(rng.choice(a, a.size)) - \
            np.median(rng.choice(b, b.size))
    return float(np.median(a) - np.median(b)), \
        float(np.percentile(ds, 2.5)), float(np.percentile(ds, 97.5))


def windows_from_frames(slope, resid, inl, w, min_inl=0.6, max_resid=0.8):
    """Re-window a per-frame stream exactly as WindowAggregator would at a
    different window length: gate first, then chunk the surviving frames in
    arrival order and take the median of each full chunk."""
    ok = (inl >= min_inl) & (resid <= max_resid)
    s = slope[ok]
    nfull = s.size // w
    if nfull == 0:
        return np.empty(0), int(ok.sum())
    return np.median(s[:nfull * w].reshape(nfull, w), axis=1), int(ok.sum())


def cmd_report(args):
    tags = args.tags.split(",")
    D = {t: load(args.cache, t) for t in tags}
    ta, tb = tags[0], tags[1]

    print("=" * 78)
    print("TABLE 0 - the two captures, re-derived this pass")
    print("=" * 78)
    for t in tags:
        s, z, o, pb, amb = D[t]
        print(f"\n[{t}] {s['path']}")
        print(f"  lines {s['n_lines']:,}  rows {s['n_rows']:,}  "
              f"span {s['span_s']:.3f} s  seams {len(s['seams'])} "
              f"({s['seam_bad']} backwards)")
        print(f"  node_id mode {s['node_mode']}  channel mode {s['ch_mode']}"
              f"  node_id hist {s['node_hist']}")
        print(f"  corrupt rows {s['n_corrupt']} "
              f"(field {s['n_bad_field']}, dropped-median {s['n_bad_drop']})")
        print(f"  drops {s['drops_total']:,} (endpoint check "
              f"{s['drops_endpoint']:,} "
              f"{'AGREES' if s['drops_endpoint']==s['drops_total'] else 'DISAGREES'}"
              f", {s['drop_wraps']} u16 wraps)  "
              f"loss {100*s['drops_total']/(s['n_rows']+s['drops_total']):.3f} %")
        print(f"  distinct MACs {len(s['mac_names'])}   "
              f"noise_floor hist {dict(sorted(s['nf_hist'].items(), key=lambda kv:-kv[1])[:6])}")

    print()
    print("=" * 78)
    print("TABLE A1 - whole-night SFO per beacon (cross-check vs "
          "docs/OVERNIGHT_2026-08-22.md TABLE 2)")
    print("=" * 78)
    print(f"{'node':6s} {'b':3s} {'fed':>10s} {'acc':>10s} {'rej%':>7s} "
          f"{'windows':>8s} {'sfo med':>10s} {'IQR':>9s}")
    for t in tags:
        s, z, o, pb, amb = D[t]
        for m, b in BEACONS.items():
            st = s["agg_stats"].get(m)
            ob = o.get(m, [])
            if not st or not ob:
                continue
            sf = np.array([x["sfo"] for x in ob])
            rej = 100 * (st["fed"] - st["accepted"]) / max(st["fed"], 1)
            print(f"{t:6s} {b:3s} {st['fed']:>10,} {st['accepted']:>10,} "
                  f"{rej:7.3f} {st['windows']:>8,} {np.median(sf):+10.5f} "
                  f"{np.subtract(*np.percentile(sf,[75,25])):9.5f}")

    # ================================================== ANALYSIS 1
    print()
    print("=" * 78)
    print("ANALYSIS 1 - THE POSITIVE CONTROL (final minutes)")
    print("=" * 78)
    print("  The 2026-08-21 signature to be matched (docs/S3_SFO_STEPS.md")
    print("  §0/§3/§6, all inside one 20 s window at t = 930 s, on the S3):")
    print("    - noise_floor leaves a pinned value and does NOT revert")
    print("      (-94 -> -95, mean shift -0.63 dB over 55 further minutes)")
    print("    - RSSI steps UP on all three beacons: +3.8, +1.6, +6.8 dB")
    print("    - SFO moves on all three, in different directions:")
    print("      B1 -0.00464, B2 +0.01786, B3 -0.05073 rad/sc")
    print("    - frame reject % and resid_std move with it")
    print("    - the other receiver (desk) shows <= 1.4 dB and no nf move")

    print()
    print("-" * 78)
    print("A1.1 - noise_floor at 10 s over the final 1800 s, per node")
    print("-" * 78)
    for t in tags:
        s, z, o, pb, amb = D[t]
        modal = np.array(z["modal10"])
        base = int(np.bincount(modal - modal.min()).argmax() + modal.min())
        tm = np.array(s["tail_nf_mean"])
        tmod = np.array(s["tail_nf_modal"])
        tn = np.array(s["tail_n"])
        tail0 = s["tail0"]
        print(f"\n[{t}] all-night modal noise_floor {base:+d} dB "
              f"(from {modal.size} 10 s bins; "
              f"{100*(modal==base).mean():.2f} % of bins)")
        print(f"      t(s)   t_end-  mean_nf  modal  n    departure")
        first_dep = None
        for k in range(tm.size):
            tt = tail0 + k * s["tail_bin_s"]
            if tn[k] == 0:
                continue
            dep = tmod[k] != base
            if dep and first_dep is None:
                first_dep = tt
            if tt < s["span_s"] - args.tail_show and not dep:
                continue
            print(f"    {tt:8.0f} {s['span_s']-tt:8.0f} "
                  f"{tm[k]:+8.3f}  {tmod[k]:+5d} {tn[k]:5d}    "
                  f"{'AWAY' if dep else '.'}")
        # persistence: longest run away from base within the tail
        away = (tmod != base) & (tn > 0)
        runs, cur, curstart, best = [], 0, None, None
        for k, v in enumerate(away):
            if v:
                if cur == 0:
                    curstart = k
                cur += 1
            elif cur:
                runs.append((cur, curstart)); cur = 0
        if cur:
            runs.append((cur, curstart))
        print(f"    excursions away from {base:+d} in the tail: {len(runs)}")
        for n_, k0 in sorted(runs, key=lambda r: -r[0])[:6]:
            print(f"      {n_*s['tail_bin_s']:5.0f} s from t = "
                  f"{tail0 + k0*s['tail_bin_s']:.0f} s"
                  f"{'  (runs to end of file)' if k0+n_ >= tm.size or (tn[k0+n_:]>0).sum()==0 else ''}")

    print()
    print("-" * 78)
    print("A1.2 - per-beacon RSSI at 10 s over the final 900 s")
    print("-" * 78)
    for t in tags:
        s, z, o, pb, amb = D[t]
        tail0 = s["tail0"]
        bs = [b for b in ("B1", "B2", "B3") if b in pb]
        print(f"\n[{t}]  t(s)  t_end-   " +
              "   ".join(f"{b} rssi   {b} n" for b in bs))
        for k in range(len(pb[bs[0]]["tail_n"])):
            tt = tail0 + k * s["tail_bin_s"]
            if tt < s["span_s"] - args.tail_show:
                continue
            if all(pb[b]["tail_n"][k] == 0 for b in bs):
                continue
            row = "  ".join(
                f"{pb[b]['tail_rssi'][k]:+8.2f} {pb[b]['tail_n'][k]:5d}"
                for b in bs)
            print(f"    {tt:8.0f} {s['span_s']-tt:6.0f}   {row}")

    print()
    print("-" * 78)
    print("A1.3 - RSSI effect size: last 300 s vs the 1800 s before it")
    print("-" * 78)
    print("  (means over clean frames of that beacon, from the 10 s bins)")
    print(f"\n{'node':6s} {'b':3s} {'ref mean':>9s} {'last300':>9s} "
          f"{'delta dB':>9s} {'ref n':>8s} {'last n':>8s}")
    for t in tags:
        s, z, o, pb, amb = D[t]
        for b in ("B1", "B2", "B3"):
            if b not in pb:
                continue
            n60 = np.array(pb[b]["n60"], dtype=float)
            r60 = np.array(pb[b]["rssi60"], dtype=float)
            nb = n60.size
            # reference: minutes [nb-35, nb-5) ; test: last 5 min
            ref = slice(max(0, nb - 35), nb - 5)
            tst = slice(nb - 5, nb)
            rn, tn_ = n60[ref].sum(), n60[tst].sum()
            rm = (r60[ref] * n60[ref]).sum() / max(rn, 1)
            tm_ = (r60[tst] * n60[tst]).sum() / max(tn_, 1)
            print(f"{t:6s} {b:3s} {rm:+9.2f} {tm_:+9.2f} {tm_-rm:+9.2f} "
                  f"{rn:>8.0f} {tn_:>8.0f}")

    print()
    print("-" * 78)
    print("A1.4 - SFO per beacon per node, fine bins over the tail")
    print("-" * 78)
    for t in tags:
        s, z, o, pb, amb = D[t]
        print(f"\n[{t}] windows of {WINDOW} accepted frames, median SFO per "
              f"{args.sfo_bin:.0f} s bin, last {args.tail_show:.0f} s")
        bs = [b for m, b in BEACONS.items() if m in o]
        hdr = "  ".join(f"{b:>19s}" for b in bs)
        print(f"      t(s)  t_end-   {hdr}")
        series = {}
        for m, b in BEACONS.items():
            ob = o.get(m, [])
            if not ob:
                continue
            ts = np.array([x["ts_pc"] for x in ob])
            sf = np.array([x["sfo"] for x in ob])
            rd = np.array([x["resid"] for x in ob])
            series[b] = (ts, sf, rd)
        k0 = int((s["span_s"] - args.tail_show) // args.sfo_bin)
        k1 = int(s["span_s"] // args.sfo_bin)
        for k in range(k0, k1 + 1):
            lo_, hi_ = k * args.sfo_bin, (k + 1) * args.sfo_bin
            cells = []
            for b in bs:
                ts, sf, rd = series[b]
                sel = (ts >= lo_) & (ts < hi_)
                cells.append(f"{np.median(sf[sel]):+9.5f}/{sel.sum():3d}"
                             f"/{np.mean(rd[sel]):5.3f}"
                             if sel.sum() >= 3 else "        -        ")
            print(f"    {lo_:8.0f} {s['span_s']-lo_:6.0f}   " +
                  "  ".join(f"{c:>19s}" for c in cells))
        print("      (cell = median SFO / n windows / mean resid_std)")

    print()
    print("-" * 78)
    print("A1.5 - SFO effect size: last 300 s vs the 1800 s before it")
    print("-" * 78)
    print(f"  bootstrap over windows, 4000 resamples, "
          f"np.random.default_rng(0); BETWEEN_UNIT_SD = {BETWEEN_UNIT_SD}")
    print(f"\n{'node':6s} {'b':3s} {'ref med':>10s} {'ref n':>6s} "
          f"{'last med':>10s} {'n':>5s} {'delta':>10s} {'95% CI':>22s} "
          f"{'x SD':>6s}")
    a15 = {}
    for t in tags:
        s, z, o, pb, amb = D[t]
        for m, b in BEACONS.items():
            ob = o.get(m, [])
            if not ob:
                continue
            ts = np.array([x["ts_pc"] for x in ob])
            sf = np.array([x["sfo"] for x in ob])
            e = s["span_s"]
            ref = sf[(ts >= e - 2100) & (ts < e - 300)]
            tst = sf[ts >= e - 300]
            d, lo_, hi_ = boot_diff_ci(tst, ref)
            a15[(t, b)] = (d, lo_, hi_)
            print(f"{t:6s} {b:3s} {np.median(ref):+10.5f} {ref.size:>6d} "
                  f"{np.median(tst):+10.5f} {tst.size:>5d} {d:+10.5f} "
                  f"[{lo_:+8.5f},{hi_:+8.5f}] {abs(d)/BETWEEN_UNIT_SD:6.2f}")
    print("\n  signs, per node (08-21 had -, +, - on the S3):")
    for t in tags:
        sg = "".join("+" if a15[(t, b)][0] > 0 else "-"
                     for b in ("B1", "B2", "B3") if (t, b) in a15)
        print(f"    {t}: {sg}")

    print()
    print("-" * 78)
    print("A1.6 - frame rate and drop rate at 10 s over the final 900 s")
    print("-" * 78)
    for t in tags:
        s, z, o, pb, amb = D[t]
        kps = np.array(z["kept_per_s"], dtype=float)
        dps = np.array(z["drops_per_s"], dtype=float)
        e = int(s["span_s"])
        ref = slice(max(0, e - 2100), e - 300)
        print(f"\n[{t}] reference t = {ref.start}..{ref.stop} s: "
              f"kept {kps[ref].mean():.2f} fps  drops {dps[ref].mean():.2f}/s"
              f"  offered {kps[ref].mean()+dps[ref].mean():.2f} fps")
        print("      t(s)  t_end-   kept/s  drops/s  offered/s")
        for k in range(max(0, (e - int(args.tail_show)) // 10), e // 10 + 1):
            a, b2 = k * 10, min(k * 10 + 10, kps.size)
            if a >= kps.size:
                break
            print(f"    {a:8d} {e-a:6d}   {kps[a:b2].mean():7.2f} "
                  f"{dps[a:b2].mean():8.2f}  "
                  f"{kps[a:b2].mean()+dps[a:b2].mean():8.2f}")

    # ================================================== ANALYSIS 2
    print()
    print("=" * 78)
    print("-" * 78)
    print("A1.7 - change-point: WHEN does anything move, per node per beacon")
    print("-" * 78)
    print("  10 s bins from the per-frame stream (kept for every beacon over")
    print("  the final 1800 s).  Baseline = bins in [t_end-1800, t_end-600),")
    print("  chosen before looking so that a 5-minute-early entry cannot be")
    print("  inside it.  A bin is flagged when it leaves the baseline by more")
    print(f"  than {args.mad_k:.0f} x MAD; the first flagged bin at or after")
    print("  t_end-600 is reported, with the run of flagged bins that")
    print("  follows it.  MAD = 1.4826 x median|x - median|.")
    ev = {}
    for t in tags:
        s, z, o, pb, amb = D[t]
        span = s["span_s"]
        print(f"\n[{t}]  quantity        baseline   MAD    first move   "
              f"value there  bins flagged after / total")
        for m, b in BEACONS.items():
            if m not in s["mac_names"]:
                continue
            i = s["mac_names"].index(m)
            sel = z["f_mid"] == i
            tt = z["f_t"][sel]
            sl = z["f_slope"][sel]
            rd = z["f_resid"][sel]
            il = z["f_inl"][sel]
            rs = z["f_rssi"][sel].astype(float)
            acc = (il >= 0.6) & (rd <= 0.8)
            k = ((tt - (span - TAIL_KEEP_S)) / 10).astype(np.int64)
            nk = int(TAIL_KEEP_S // 10)
            k = np.clip(k, 0, nk - 1)
            tb_ = (span - TAIL_KEEP_S) + np.arange(nk) * 10
            n_ = np.bincount(k, minlength=nk).astype(float)
            with np.errstate(invalid="ignore", divide="ignore"):
                ser = {
                    "rssi (dB)": np.bincount(k, weights=rs, minlength=nk)
                    / np.maximum(n_, 1),
                    "accepted frac": np.bincount(k, weights=acc.astype(float),
                                                 minlength=nk)
                    / np.maximum(n_, 1),
                    "resid_std": np.bincount(k, weights=rd, minlength=nk)
                    / np.maximum(n_, 1),
                    "SFO (accepted)": np.array(
                        [np.median(sl[(k == j) & acc])
                         if ((k == j) & acc).sum() >= 5 else np.nan
                         for j in range(nk)]),
                }
            base = (tb_ >= span - 1800) & (tb_ < span - 600) & (n_ > 0)
            test = (tb_ >= span - 600) & (n_ > 0)
            for label, v in ser.items():
                bv = v[base]
                bv = bv[~np.isnan(bv)]
                if bv.size < 20:
                    continue
                med = np.median(bv)
                mad = 1.4826 * np.median(np.abs(bv - med))
                if mad <= 0:
                    mad = np.std(bv) if np.std(bv) > 0 else 1e-9
                flag = test & ~np.isnan(v) & (np.abs(v - med) > args.mad_k * mad)
                idx = np.flatnonzero(flag)
                if idx.size == 0:
                    print(f"   {b} {label:16s} {med:+9.4f} {mad:7.4f}   "
                          f"(never leaves baseline in the final 600 s)")
                    continue
                j0 = idx[0]
                nafter = int(flag[j0:].sum())
                ntot = int((test & ~np.isnan(v))[j0:].sum())
                print(f"   {b} {label:16s} {med:+9.4f} {mad:7.4f}  "
                      f"t={tb_[j0]:8.0f} (t_end-{span-tb_[j0]:3.0f})"
                      f" {v[j0]:+11.4f}   {nafter}/{ntot}")
                ev.setdefault((t, b, label), tb_[j0])

    print("\n  earliest flagged bin per node, over all beacons and "
          "quantities:")
    for t in tags:
        vs = [v for (tt_, b, l), v in ev.items() if tt_ == t]
        if vs:
            s = D[t][0]
            print(f"    {t}: t = {min(vs):.0f} s "
                  f"(t_end - {s['span_s']-min(vs):.0f} s)")
        else:
            print(f"    {t}: nothing flagged")

    print()
    print("-" * 78)
    print(f"A1.8 - effect sizes with the boundary at t = t_end - "
          f"{args.event_before:.0f} s")
    print("-" * 78)
    print("  after = [t_end-%.0f, t_end]; before = the 1800 s preceding it."
          % args.event_before)
    print(f"\n{'node':6s} {'b':3s} {'quantity':15s} {'before':>10s} "
          f"{'after':>10s} {'delta':>10s} {'95% CI':>22s} {'x SD':>6s}")
    for t in tags:
        s, z, o, pb, amb = D[t]
        span = s["span_s"]
        cut = span - args.event_before
        for m, b in BEACONS.items():
            if m not in s["mac_names"]:
                continue
            i = s["mac_names"].index(m)
            sel = z["f_mid"] == i
            tt = z["f_t"][sel]
            sl = z["f_slope"][sel]
            rd = z["f_resid"][sel]
            il = z["f_inl"][sel]
            rs = z["f_rssi"][sel].astype(float)
            acc = (il >= 0.6) & (rd <= 0.8)
            pre = (tt >= cut - 1800) & (tt < cut)
            post = tt >= cut
            print(f"{t:6s} {b:3s} {'rssi (dB)':15s} "
                  f"{rs[pre].mean():+10.2f} {rs[post].mean():+10.2f} "
                  f"{rs[post].mean()-rs[pre].mean():+10.2f} "
                  f"{'':>22s} {'':>6s}")
            print(f"{t:6s} {b:3s} {'reject %':15s} "
                  f"{100*(1-acc[pre].mean()):+10.3f} "
                  f"{100*(1-acc[post].mean()):+10.3f} "
                  f"{100*(acc[pre].mean()-acc[post].mean()):+10.3f}")
            print(f"{t:6s} {b:3s} {'resid_std':15s} "
                  f"{rd[pre].mean():+10.4f} {rd[post].mean():+10.4f} "
                  f"{rd[post].mean()-rd[pre].mean():+10.4f}")
            wpre, _ = windows_from_frames(sl[pre], rd[pre], il[pre], WINDOW)
            wpost, _ = windows_from_frames(sl[post], rd[post], il[post],
                                           WINDOW)
            d, lo_, hi_ = boot_diff_ci(wpost, wpre)
            print(f"{t:6s} {b:3s} {'SFO':15s} "
                  f"{np.median(wpre):+10.5f} {np.median(wpost):+10.5f} "
                  f"{d:+10.5f} [{lo_:+8.5f},{hi_:+8.5f}] "
                  f"{abs(d)/BETWEEN_UNIT_SD:6.2f}  "
                  f"(nw {wpre.size} -> {wpost.size})")
        # node-level noise_floor across the same boundary
        mean10 = np.array(s["nf_mean_10s_full"]) if \
            "nf_mean_10s_full" in s else np.array(z["mean10"])
        tb_ = np.arange(mean10.size) * 10
        pre = (tb_ >= cut - 1800) & (tb_ < cut)
        post = tb_ >= cut
        print(f"{t:6s} {'--':3s} {'noise_floor':15s} "
              f"{np.nanmean(mean10[pre]):+10.4f} "
              f"{np.nanmean(mean10[post]):+10.4f} "
              f"{np.nanmean(mean10[post])-np.nanmean(mean10[pre]):+10.4f}")
        # node-level delivery.  A host-side shutdown would show as frames
        # falling while queue drops RISE (the queue backs up); a fall in
        # what the node hears shows as both falling together.
        kps = np.array(z["kept_per_s"], dtype=float)
        dps = np.array(z["drops_per_s"], dtype=float)
        ts_ = np.arange(kps.size)
        pr = (ts_ >= cut - 1800) & (ts_ < cut)
        po = ts_ >= cut
        print(f"{t:6s} {'--':3s} {'kept fps':15s} "
              f"{kps[pr].mean():+10.2f} {kps[po].mean():+10.2f} "
              f"{kps[po].mean()-kps[pr].mean():+10.2f}")
        print(f"{t:6s} {'--':3s} {'queue drops/s':15s} "
              f"{dps[pr].mean():+10.2f} {dps[po].mean():+10.2f} "
              f"{dps[po].mean()-dps[pr].mean():+10.2f}")
        print(f"{t:6s} {'--':3s} {'offered fps':15s} "
              f"{(kps+dps)[pr].mean():+10.2f} {(kps+dps)[po].mean():+10.2f} "
              f"{(kps+dps)[po].mean()-(kps+dps)[pr].mean():+10.2f}")

    print()
    print("=" * 78)
    print("ANALYSIS 2 - IS d0wd - s3 SFO CONSTANT ACROSS SOURCES?")
    print("=" * 78)
    sa, za, oa, pba, amba = D[ta]
    sb, zb, ob_, pbb, ambb = D[tb]
    cnt = {t: dict(zip(D[t][0]["mac_names"], D[t][0]["mac_count"]))
           for t in tags}
    badf = {t: dict(zip(D[t][0]["mac_names"], D[t][0]["mac_bad"]))
            for t in tags}
    rmean = {t: dict(zip(D[t][0]["mac_names"], D[t][0]["mac_rssi_mean"]))
             for t in tags}
    # sort key includes the MAC so that sources with equal frame totals do
    # not swap places between runs: the input is a set, whose iteration
    # order varies with PYTHONHASHSEED, and `sorted` is only stable with
    # respect to that order.
    both = sorted(set(cnt[ta]) & set(cnt[tb]),
                  key=lambda m: (-(cnt[ta][m] + cnt[tb][m]), m))

    # per-source per-frame streams (non-beacons kept whole; beacons come
    # from the window observations, which cover the whole night)
    def frames_for(t, m):
        s, z, o, pb, amb = D[t]
        if amb is not None and ("sl__" + m) in amb:  # noqa: E501
            pass
        elif amb is not None and m not in BEACONS:
            e = np.empty(0)
            return (e, e, e, e, e)
        if amb is not None and ("sl__" + m) in amb:
            return (amb["sl__" + m], amb["rd__" + m], amb["il__" + m],
                    amb["t__" + m], amb["rs__" + m])
        if m not in s["mac_names"]:
            return None
        i = s["mac_names"].index(m)
        sel = z["f_mid"] == i
        return (z["f_slope"][sel], z["f_resid"][sel], z["f_inl"][sel],
                z["f_t"][sel], z["f_rssi"][sel])

    print("\n  Every source seen on BOTH nodes, and what it can support.")
    print("  `acc` = frames passing the shipped gates (inlier_ratio >= 0.6,")
    print("  resid_std <= 0.8).  A source can only be compared across the")
    print("  two receivers if BOTH receivers accept enough of its frames.")
    print(f"\n{'mac':19s} {'kind':5s} {'len':>4s} "
          f"{ta+' n':>9s} {'acc':>7s} {'acc%':>6s} {'rssi':>7s}  "
          f"{tb+' n':>9s} {'acc':>7s} {'acc%':>6s} {'rssi':>7s}  "
          f"{'bins A/B':>9s}")
    cand = []
    for m in both:
        na, nb = cnt[ta][m], cnt[tb][m]
        if na + nb < 5:
            continue
        bp = 100 * (badf[ta][m] + badf[tb][m]) / (na + nb)
        ia = sa["mac_names"].index(m)
        ib = sb["mac_names"].index(m)
        binsa = int((za["act"][ia] > 0).sum())
        binsb = int((zb["act"][ib] > 0).sum())
        try:
            kind = "beac" if m in BEACONS else ("LAA" if int(m[:2], 16) & 2
                                                else "OUI")
        except ValueError:
            kind = "?"
        acc = {}
        for t, tg_ in ((ta, "A"), (tb, "B")):
            if m in BEACONS:
                st = D[t][0]["agg_stats"][m]
                acc[tg_] = (st["accepted"], st["fed"])
            else:
                fr = frames_for(t, m)
                if fr is None or fr[0].size == 0:
                    acc[tg_] = (0, cnt[t][m])
                else:
                    ok = (fr[2] >= 0.6) & (fr[1] <= 0.8)
                    acc[tg_] = (int(ok.sum()), cnt[t][m])
        ld = D[ta][0]["len_dom"].get(m) or D[tb][0]["len_dom"].get(m) or {}
        dom = max(ld, key=ld.get) if ld else "-"
        print(f"{m:19s} {kind:5s} {str(dom):>4s} "
              f"{na:>9,} {acc['A'][0]:>7,} "
              f"{100*acc['A'][0]/max(na,1):6.1f} {rmean[ta][m]:7.2f}  "
              f"{nb:>9,} {acc['B'][0]:>7,} "
              f"{100*acc['B'][0]/max(nb,1):6.1f} {rmean[tb][m]:7.2f}  "
              f"{binsa:>4d}/{binsb:<4d}")
        cand.append(dict(mac=m, kind=kind, na=na, nb=nb, bp=bp,
                         binsa=binsa, binsb=binsb,
                         acca=acc["A"][0], accb=acc["B"][0]))

    print(f"\n  inclusion rule, stated before the answer: a source is "
          f"estimated only if")
    print(f"  BOTH receivers accept >= {args.min_acc} of its frames and "
          f"under 1 % of its rows")
    print(f"  are flagged corrupt.  {args.min_acc} accepted frames is far "
          f"above the two-frame")
    print(f"  convergence floor `docs/WINDOW_CONVERGENCE.md` §4.4 measures, "
          f"and at that")
    print(f"  section's own numbers the median |dSFO| at 16-31 accepted "
          f"frames is 0.00032")
    print(f"  for `62:45:b4:f0:e1:97`, an eighth of BETWEEN_UNIT_SD.  "
          f"Everything else is")
    print(f"  listed as excluded with the count that excluded it.")

    def frame_stream(t, m):
        """Accepted per-frame slopes for one source on one node."""
        if m in BEACONS:
            s, z, o, pb, amb = D[t]
            i = s["mac_names"].index(m)
            sel = z["f_mid"] == i          # tail only for beacons
            sl, rd, il = z["f_slope"][sel], z["f_resid"][sel], z["f_inl"][sel]
            ok = (il >= 0.6) & (rd <= 0.8)
            return sl[ok]
        fr = frames_for(t, m)
        if fr is None or fr[0].size == 0:
            return np.empty(0)
        ok = (fr[2] >= 0.6) & (fr[1] <= 0.8)
        return fr[0][ok]

    def point_and_ci(x, cap=20000, n=4000, seed=0):
        """Median + bootstrap 95 % CI, resampling at most `cap` values.

        Above `cap` the bootstrap is run on a without-replacement subsample,
        which widens the interval rather than narrowing it, so no CI here is
        optimistic.  Neither this nor a bootstrap over windows accounts for
        autocorrelation between frames, so both understate; the conclusion
        below does not rest on the width.
        """
        if x.size == 0:
            return float("nan"), float("nan"), float("nan")
        rng = np.random.default_rng(seed)
        y = x if x.size <= cap else rng.choice(x, cap, replace=False)
        bs = np.array([np.median(rng.choice(y, y.size)) for _ in range(n)])
        return (float(np.median(x)), float(np.percentile(bs, 2.5)),
                float(np.percentile(bs, 97.5)))

    print()
    print("-" * 78)
    print("A2.0 - does the per-frame estimator agree with the production "
          "window estimator?")
    print("-" * 78)
    print("  Ambient sources cannot fill a 64-frame window, so the estimate")
    print("  below is the median of accepted per-frame slopes.  On the three")
    print("  beacons, where both are available over the same frames (the")
    print("  final 1800 s, which is where per-frame records are kept), the")
    print("  two must agree or nothing else in this section is comparable.")
    print(f"\n{'node':6s} {'b':3s} {'per-frame med':>14s} {'n frames':>10s} "
          f"{'w=64 med':>10s} {'n win':>7s} {'difference':>11s}")
    for t in tags:
        s, z, o, pb, amb = D[t]
        for m, b in BEACONS.items():
            if m not in s["mac_names"]:
                continue
            i = s["mac_names"].index(m)
            sel = z["f_mid"] == i
            sl, rd, il = z["f_slope"][sel], z["f_resid"][sel], z["f_inl"][sel]
            ok = (il >= 0.6) & (rd <= 0.8)
            w64, _ = windows_from_frames(sl, rd, il, 64)
            pf = float(np.median(sl[ok]))
            wm = float(np.median(w64)) if w64.size else float("nan")
            print(f"{t:6s} {b:3s} {pf:+14.5f} {int(ok.sum()):>10,} "
                  f"{wm:+10.5f} {w64.size:>7,} {pf-wm:+11.5f}")

    print()
    print("-" * 78)
    print("A2.1 - per-source SFO on each node, and the d0wd - s3 difference")
    print("-" * 78)
    print("  estimator: median of accepted per-frame slopes; 95 % CI by")
    print("  bootstrap over frames (4000 resamples, "
          "np.random.default_rng(0)).")
    print("  Beacon rows use the final 1800 s, the stretch where per-frame")
    print("  records are kept; the whole-night window medians in TABLE A1")
    print("  are given beside them so the two can be compared.")
    print(f"\n{'mac':19s} {'kind':5s} "
          f"{ta+' med':>10s} {'nacc':>6s} {'rssi':>7s}  "
          f"{tb+' med':>10s} {'nacc':>6s} {'rssi':>7s}  "
          f"{'A-B':>9s} {'95% CI':>21s} {'xSD':>6s}")
    res, excl = [], []
    for c in cand:
        m = c["mac"]
        if c["acca"] < args.min_acc or c["accb"] < args.min_acc \
                or c["bp"] >= 1.0:
            excl.append(c)
            continue
        xa, xb = frame_stream(ta, m), frame_stream(tb, m)
        ma, la, ha = point_and_ci(xa)
        mb, lb, hb = point_and_ci(xb)
        rng = np.random.default_rng(0)
        ya = xa if xa.size <= 20000 else rng.choice(xa, 20000, replace=False)
        yb = xb if xb.size <= 20000 else rng.choice(xb, 20000, replace=False)
        ds = np.array([np.median(rng.choice(ya, ya.size))
                       - np.median(rng.choice(yb, yb.size))
                       for _ in range(4000)])
        d = ma - mb
        lo_, hi_ = np.percentile(ds, [2.5, 97.5])
        print(f"{m:19s} {c['kind']:5s} "
              f"{ma:+10.5f} {xa.size:>6,} {rmean[ta][m]:7.2f}  "
              f"{mb:+10.5f} {xb.size:>6,} {rmean[tb][m]:7.2f}  "
              f"{d:+9.5f} [{lo_:+8.5f},{hi_:+8.5f}] "
              f"{abs(d)/BETWEEN_UNIT_SD:6.2f}")
        res.append(dict(mac=m, kind=c["kind"], d=d, lo=lo_, hi=hi_,
                        na=c["na"], nb=c["nb"], wa=xa.size, wb=xb.size,
                        ra=rmean[ta][m], rb=rmean[tb][m],
                        binsa=c["binsa"], binsb=c["binsb"],
                        acca=c["acca"], accb=c["accb"]))

    print(f"\n  excluded: {len(excl)} of {len(cand)} sources seen on both "
          f"nodes")
    for c in excl:
        why = []
        if c["acca"] < args.min_acc:
            why.append(f"{ta} accepts {c['acca']} of {c['na']} frames")
        if c["accb"] < args.min_acc:
            why.append(f"{tb} accepts {c['accb']} of {c['nb']} frames")
        if c["bp"] >= 1.0:
            why.append(f"{c['bp']:.1f} % rows flagged")
        print(f"    {c['mac']:19s} {c['kind']:4s}  " + "; ".join(why))

    if len(res) >= 2:
        ds = np.array([r["d"] for r in res])
        print(f"\n  spread of (d0wd - s3) across the {len(res)} sources that "
              f"qualify:")
        for r in res:
            print(f"    {r['mac']:19s} {r['kind']:4s} {r['d']:+10.5f}  "
                  f"[{r['lo']:+.5f}, {r['hi']:+.5f}]")
        print(f"    min {ds.min():+.5f}  max {ds.max():+.5f}  "
              f"range {ds.max()-ds.min():.5f} = "
              f"{(ds.max()-ds.min())/BETWEEN_UNIT_SD:.2f} x BETWEEN_UNIT_SD"
              f" ({(ds.max()-ds.min())/TWIN_DSFO:.1f} x twin dSFO)")
        print(f"    sd {ds.std(ddof=1):.5f} = "
              f"{ds.std(ddof=1)/BETWEEN_UNIT_SD:.2f} x BETWEEN_UNIT_SD")
        print(f"    median {np.median(ds):+.5f}   "
              f"signs {''.join('+' if v > 0 else '-' for v in ds)}")
        nd = npair = 0
        for i in range(len(res)):
            for j in range(i + 1, len(res)):
                npair += 1
                if res[i]["hi"] < res[j]["lo"] or res[j]["hi"] < res[i]["lo"]:
                    nd += 1
        print(f"    pairs of sources with disjoint 95 % CIs: {nd} of {npair}")
        bo = [r for r in res if r["kind"] == "beac"]
        am = [r for r in res if r["kind"] != "beac"]
        if len(bo) >= 2:
            db = np.array([r["d"] for r in bo])
            print(f"    beacons only ({len(bo)}): range {db.max()-db.min():.5f}"
                  f" = {(db.max()-db.min())/BETWEEN_UNIT_SD:.2f} x SD "
                  f"(08-21 measured 6.2x on the same three)")
        if am:
            print(f"    ambient sources qualifying: {len(am)} "
                  f"({', '.join(r['mac'] for r in am)})")
        if len(res) >= 4:
            print("\n  does the difference correlate with anything "
                  "observable?")
            for label, v in (
                    ("rssi on d0wd", [r["ra"] for r in res]),
                    ("rssi on s3", [r["rb"] for r in res]),
                    ("rssi difference d0wd-s3",
                     [r["ra"] - r["rb"] for r in res]),
                    ("log10 frames on d0wd", [np.log10(r["na"]) for r in res]),
                    ("accept rate on d0wd",
                     [r["acca"] / max(r["na"], 1) for r in res]),
                    ("accept-rate difference",
                     [r["acca"] / max(r["na"], 1) - r["accb"] / max(r["nb"], 1)
                      for r in res]),
                    ("duty cycle: 300 s bins on d0wd",
                     [r["binsa"] for r in res])):
                v = np.array(v, dtype=float)
                if np.std(v) == 0:
                    continue
                r_ = np.corrcoef(ds, v)[0, 1]
                print(f"    r(delta, {label:32s}) = {r_:+.3f}"
                      f"   (n = {len(res)}, so this is descriptive only)")
        else:
            print(f"\n  {len(res)} sources is too few to correlate the "
                  f"difference against anything;")
            print(f"  no correlation is reported rather than one computed on "
                  f"{len(res)} points.")

    print()
    print("-" * 78)
    print("A2.2 - the reason most ambient sources cannot be used")
    print("-" * 78)
    print("  The gate that removes them is `inlier_ratio >= 0.6`")
    print("  (`pc/rff/dsp.py:164,173`), and it removes them at very")
    print("  different rates on the two receivers for the SAME device.")
    print(f"\n{'mac':19s} {'acc% d0wd':>10s} {'acc% s3':>9s} "
          f"{'med inlier A':>13s} {'med inlier B':>13s}")
    for c in cand:
        m = c["mac"]
        if m in BEACONS or c["na"] + c["nb"] < 40:
            continue
        ila = frames_for(ta, m)
        ilb = frames_for(tb, m)
        mia = float(np.median(ila[2])) if ila is not None and ila[2].size \
            else float("nan")
        mib = float(np.median(ilb[2])) if ilb is not None and ilb[2].size \
            else float("nan")
        print(f"{m:19s} {100*c['acca']/max(c['na'],1):10.1f} "
              f"{100*c['accb']/max(c['nb'],1):9.1f} {mia:13.3f} "
              f"{mib:13.3f}")

    print()
    print("-" * 78)
    print("A2.3 - sensitivity: the same estimate with the final 600 s removed")
    print("-" * 78)
    print("  Analysis 1 places a channel change at t_end - 170 s.  If that")
    print("  contaminated A2.1, dropping the last 600 s would move it.")
    print(f"{'mac':19s} {'A-B all':>10s} {'A-B excl tail':>14s} "
          f"{'shift':>9s} {'x SD':>6s}")
    for r in res:
        m = r["mac"]
        vals = {}
        for lbl, cut in (("all", False), ("cut", True)):
            mm = []
            for t in (ta, tb):
                s = D[t][0]
                if m in BEACONS:
                    z = D[t][1]
                    i = s["mac_names"].index(m)
                    sel = z["f_mid"] == i
                    sl, rd, il = (z["f_slope"][sel], z["f_resid"][sel],
                                  z["f_inl"][sel])
                    tt = z["f_t"][sel]
                else:
                    fr = frames_for(t, m)
                    sl, rd, il, tt = fr[0], fr[1], fr[2], fr[3]
                ok = (il >= 0.6) & (rd <= 0.8)
                if cut:
                    ok = ok & (tt < s["span_s"] - 600)
                mm.append(np.median(sl[ok]) if ok.sum() else np.nan)
            vals[lbl] = mm[0] - mm[1]
        print(f"{m:19s} {vals['all']:+10.5f} {vals['cut']:+14.5f} "
              f"{vals['cut']-vals['all']:+9.5f} "
              f"{abs(vals['cut']-vals['all'])/BETWEEN_UNIT_SD:6.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("part")
    p.add_argument("path"); p.add_argument("--tag", required=True)
    p.add_argument("--part", type=int, required=True)
    p.add_argument("--nparts", type=int, required=True)
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.set_defaults(func=cmd_part)

    p = sub.add_parser("ambient", help="phase-estimate non-beacon frames "
                                       "from a pre-filtered CSV")
    p.add_argument("path"); p.add_argument("--tag", required=True)
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.set_defaults(func=cmd_ambient)

    p = sub.add_parser("merge")
    p.add_argument("path"); p.add_argument("--tag", required=True)
    p.add_argument("--nparts", type=int, required=True)
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.add_argument("--expect-lines", type=int, default=0)
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("report")
    p.add_argument("--tags", required=True)
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.add_argument("--tail-show", type=float, default=900.0)
    p.add_argument("--sfo-bin", type=float, default=30.0)
    p.add_argument("--min-windows", type=int, default=8)
    p.add_argument("--min-w-sens", type=int, default=16)
    p.add_argument("--mad-k", type=float, default=6.0)
    p.add_argument("--min-acc", type=int, default=20,
                   help="accepted frames required on BOTH nodes")
    p.add_argument("--event-before", type=float, default=170.0,
                   help="seconds before the end of file to place the "
                        "before/after boundary in A1.8")
    p.set_defaults(func=cmd_report)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
