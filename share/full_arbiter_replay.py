#!/usr/bin/env python3
"""Batch-vectorized unwrap-free replay for every clean canonical beacon frame.

The raw CSVs are read-only.  Rows are screened in file order by field
plausibility and the width-9 circular dropped-counter filter.  Clean beacon
frames are transformed in batches and written as compact .npy chunks.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, r"C:\dev\csi-array\pc")
from rff import dsp  # noqa: E402


BEACONS = {"a4:f0:0f:77:91:20": 1, "28:05:a5:2f:fa:48": 2,
           "f4:2d:c9:70:72:30": 3}
K = dsp.K_USABLE.astype(np.float64)
IDX = dsp._USABLE_IDX
KDEN = float(np.sum(K * K))
KP1 = int(np.flatnonzero(K == 1)[0])
PAD = 1024
STEP = 0.0002
RADIUS = 2 * np.pi / PAD
OFFSETS = np.arange(-RADIUS, RADIUS + STEP / 2, STEP)
OFFSET_EXP = np.exp(-1j * np.outer(OFFSETS, K)).astype(np.complex64)
KMOD = np.rint(K).astype(int) % PAD

CSI_LEN_OK = (128, 256, 384)
MED_W, MED_TOL, U16 = 9, 100, 65536

FRAME_DTYPE = np.dtype([
    ("pc_us", "<i8"), ("beacon", "u1"), ("rssi", "i1"), ("noise", "i1"),
    ("length", "<u2"), ("arb", "<f4"), ("coh_arb", "<f4"),
    ("ols", "<f4"), ("coh_ols", "<f4"), ("amp_med", "<f4"),
    ("kp1_amp", "<f4"), ("sat_frac", "<f4"), ("cir_peak", "<f4"),
    ("cir_rms", "<f4"),
])


def circ(a, b):
    return ((a - b + 32768) % U16) - 32768


def med_flag(vals, ci):
    c = vals[ci]
    offsets = sorted(circ(v, c) for v in vals)
    return abs(offsets[len(offsets) // 2]) > MED_TOL


def field_ok(row, node):
    return (int(row["node_id"]) == node and int(row["env_id"]) == 0
            and int(row["channel"]) == 6 and int(row["len"]) in CSI_LEN_OK
            and -110 <= int(row["noise_floor"]) <= -70
            and -100 <= int(row["rssi"]) <= -10)


def transform(records):
    """Return one structured vector for a clean-record batch."""
    n = len(records)
    raw = np.empty((n, 128), dtype=np.float32)
    keep = np.ones(n, dtype=bool)
    for i, rec in enumerate(records):
        v = np.fromstring(rec[5], dtype=np.float32, sep=",")
        if v.size < 128:
            keep[i] = False
        else:
            raw[i] = v[:128]
    if not keep.all():
        records = [r for r, ok in zip(records, keep) if ok]
        raw = raw[keep]; n = len(records)
    if not n:
        return np.empty(0, dtype=FRAME_DTYPE), int((~keep).sum())

    h = raw[:, 1::2] + 1j * raw[:, 0::2]
    hu = h[:, IDX]
    amp = np.abs(hu)
    z = np.ones_like(hu, dtype=np.complex64)
    np.divide(hu, amp, out=z, where=amp > 0)

    grid = np.zeros((n, PAD), dtype=np.complex64)
    grid[:, KMOD] = z
    coarse_i = np.argmax(np.abs(np.fft.fft(grid, axis=1)), axis=1)
    coarse = 2 * np.pi * coarse_i / PAD
    coarse = np.where(coarse > np.pi, coarse - 2 * np.pi, coarse)
    base = z * np.exp(-1j * coarse[:, None] * K[None, :])
    scores = np.abs(base @ OFFSET_EXP.T)
    oi = np.argmax(scores, axis=1)
    slope = coarse + OFFSETS[oi]
    slope = (slope + np.pi) % (2 * np.pi) - np.pi
    ramp = np.exp(-1j * slope[:, None] * K[None, :])
    arb_sum = np.sum(z * ramp, axis=1)
    intercept = np.angle(arb_sum)
    coh_arb = np.abs(arb_sum) / K.size

    ph = np.unwrap(np.angle(hu), axis=1)
    ols = np.sum(ph * K[None, :], axis=1) / KDEN
    ols_b = np.mean(ph, axis=1)
    coh_ols = np.abs(np.mean(np.exp(1j * (np.angle(hu)
        - (ols[:, None] * K[None, :] + ols_b[:, None]))), axis=1))

    cir = np.fft.ifft(h, axis=1)
    power = np.abs(cir) ** 2
    peak_i = np.argmax(power, axis=1)
    psum = np.sum(power, axis=1)
    cir_peak = power[np.arange(n), peak_i] / np.where(psum > 0, psum, 1)
    idx = np.arange(64)[None, :]
    dist = np.minimum((idx - peak_i[:, None]) % 64,
                      (peak_i[:, None] - idx) % 64)
    cir_rms = np.sqrt(np.sum(power * dist ** 2, axis=1)
                      / np.where(psum > 0, psum, 1))

    out = np.empty(n, dtype=FRAME_DTYPE)
    out["pc_us"] = [r[0] for r in records]
    out["beacon"] = [r[1] for r in records]
    out["rssi"] = [r[2] for r in records]
    out["noise"] = [r[3] for r in records]
    out["length"] = [r[4] for r in records]
    out["arb"] = slope; out["coh_arb"] = coh_arb
    out["ols"] = ols; out["coh_ols"] = coh_ols
    out["amp_med"] = np.median(amp, axis=1); out["kp1_amp"] = amp[:, KP1]
    out["sat_frac"] = np.mean(np.abs(raw) >= 127, axis=1)
    out["cir_peak"] = cir_peak; out["cir_rms"] = cir_rms
    return out, int((~keep).sum())


class ChunkSink:
    def __init__(self, outdir, stem, cap):
        self.outdir, self.stem, self.cap = outdir, stem, cap
        self.parts = []; self.n = 0; self.index = 0; self.files = []

    def add(self, arr):
        if arr.size:
            self.parts.append(arr); self.n += len(arr)
        if self.n >= self.cap:
            self.flush()

    def flush(self):
        if not self.parts: return
        arr = np.concatenate(self.parts)
        name = f"{self.stem}.part{self.index:03d}.npy"
        final = self.outdir / name; tmp = self.outdir / f"{name}.tmp.npy"
        np.save(tmp, arr, allow_pickle=False); os.replace(tmp, final)
        self.files.append({"name": name, "frames": len(arr),
                           "bytes": final.stat().st_size})
        self.parts = []; self.n = 0; self.index += 1


def replay(path, outdir, batch_size, chunk_size, progress_rows, max_seconds):
    stem = path.stem; meta_path = outdir / f"{stem}.meta.json"
    stat = path.stat()
    if meta_path.exists():
        old = json.loads(meta_path.read_text(encoding="utf-8"))
        if old.get("complete") and old.get("source_size") == stat.st_size \
                and old.get("source_mtime_ns") == stat.st_mtime_ns:
            print(f"skip complete {path.name}", file=sys.stderr); return
    outdir.mkdir(parents=True, exist_ok=True)
    start = time.time(); rows = parsed = clean = corrupt = 0
    field_bad = median_bad = both_bad = bad_csi = 0
    origin = last_pc = None; pend = []; hist = 0; batch = []
    node = 108 if path.name.startswith("s3_") else 68
    counts = Counter(); sink = ChunkSink(outdir, stem, chunk_size)

    def process_batch():
        nonlocal batch, bad_csi
        if not batch: return
        arr, bad = transform(batch); bad_csi += bad; sink.add(arr)
        for b in arr["beacon"]: counts[int(b)] += 1
        batch = []

    def emit(rec, mbad):
        nonlocal clean, corrupt, field_bad, median_bad, both_bad, batch
        row, fbad = rec
        field_bad += int(fbad); median_bad += int(mbad); both_bad += int(fbad and mbad)
        if fbad or mbad:
            corrupt += 1; return
        mac = row["mac"].lower()
        if mac not in BEACONS: return
        clean += 1
        batch.append((int(row["pc_time_us"]), BEACONS[mac], int(row["rssi"]),
                      int(row["noise_floor"]), int(row["len"]), row["csi_data"]))
        if len(batch) >= batch_size: process_batch()

    with path.open("r", newline="", errors="replace") as fh:
        for row in csv.DictReader(fh):
            rows += 1
            try:
                pc = int(row["pc_time_us"]); drop = int(row["dropped"])
                if origin is None: origin = pc
                last_pc = pc; fbad = not field_ok(row, node)
            except (KeyError, ValueError):
                continue
            parsed += 1; pend.append((row, fbad, drop))
            while hist < len(pend) and len(pend) - 1 - hist >= MED_W // 2:
                lo = max(0, hist - MED_W // 2); hi = min(len(pend), hist + MED_W // 2 + 1)
                vals = [pend[k][2] for k in range(lo, hi)]
                emit(pend[hist][:2], med_flag(vals, hist-lo) if len(vals) >= 3 else False)
                hist += 1
                while hist > MED_W // 2:
                    del pend[0]; hist -= 1
            if progress_rows and rows % progress_rows == 0:
                done = sum(counts.values())
                print(f"{path.name}: rows={rows:,} frames={done:,} "
                      f"rate={rows/max(time.time()-start,1e-9):,.0f} rows/s",
                      file=sys.stderr, flush=True)
            if max_seconds and origin is not None and pc-origin >= max_seconds*1e6:
                break
        while hist < len(pend):
            lo = max(0, hist-MED_W//2); hi = min(len(pend), hist+MED_W//2+1)
            vals = [pend[k][2] for k in range(lo, hi)]
            emit(pend[hist][:2], med_flag(vals, hist-lo) if len(vals) >= 3 else False)
            hist += 1
    process_batch(); sink.flush()
    complete = not max_seconds
    meta = {"complete": complete, "source": str(path.resolve()),
            "source_size": stat.st_size, "source_mtime_ns": stat.st_mtime_ns,
            "rows": rows, "parsed": parsed, "origin_pc_us": origin,
            "last_pc_us": last_pc, "span_s": (last_pc-origin)/1e6,
            "clean_beacon_rows": clean, "written_frames": sum(counts.values()),
            "beacon_counts": {f"B{k}": counts[k] for k in sorted(counts)},
            "corrupt_union": corrupt, "field_bad": field_bad,
            "median_bad": median_bad, "both_bad": both_bad,
            "bad_csi": bad_csi, "chunks": sink.files,
            "batch_size": batch_size, "chunk_size": chunk_size,
            "wall_s": time.time()-start}
    suffix = "meta.json" if complete else "partial.meta.json"
    (outdir / f"{stem}.{suffix}").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"done {path.name}: {rows:,} rows, {sum(counts.values()):,} frames, "
          f"{meta['wall_s']:.1f}s", file=sys.stderr, flush=True)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", required=True); ap.add_argument("--batch", type=int, default=2048)
    ap.add_argument("--chunk", type=int, default=250_000)
    ap.add_argument("--progress-rows", type=int, default=250_000)
    ap.add_argument("--max-seconds", type=float, default=0)
    a = ap.parse_args(); out = Path(a.out)
    for p in a.paths:
        replay(Path(p), out, a.batch, a.chunk, a.progress_rows, a.max_seconds)


if __name__ == "__main__": main()
