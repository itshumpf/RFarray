#!/usr/bin/env python3
"""Streaming integrity census for the eight-night CSI corpus.

This pass deliberately does not fit CSI phase.  It accounts for every CSV
row, validates every CSI vector's declared width, and retains one-second
telemetry for the three beacons.  Results are independent per input file, so
an interrupted corpus run resumes by skipping completed, size-matched files.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path


COLS = [
    "pc_time_us", "label", "seq", "mac", "rssi", "noise_floor",
    "channel", "esp_timestamp_us", "len", "csi_data", "node_id",
    "env_id", "dropped",
]
BEACONS = {
    "a4:f0:0f:77:91:20": "B1",
    "28:05:a5:2f:fa:48": "B2",
    "f4:2d:c9:70:72:30": "B3",
}
CSI_LEN_OK = {128, 256, 384}
DT_EDGES_US = [0, 1_000, 2_000, 5_000, 10_000, 20_000, 50_000,
               100_000, 200_000, 500_000, 1_000_000]


def counter_dict(c: Counter) -> dict[str, int]:
    return {str(k): int(v) for k, v in sorted(c.items(), key=lambda x: str(x[0]))}


def dt_bucket(dt: int) -> str:
    if dt <= 0:
        return "<=0"
    for edge in DT_EDGES_US[1:]:
        if dt <= edge:
            return f"<={edge}"
    return ">1000000"


def valid_mac(mac: str) -> bool:
    parts = mac.split(":")
    if len(parts) != 6:
        return False
    try:
        return all(len(p) == 2 and 0 <= int(p, 16) <= 255 for p in parts)
    except ValueError:
        return False


def new_series_cell() -> dict:
    return {
        "n": 0, "rssi_sum": 0, "rssi_min": 127, "rssi_max": -128,
        "noise_sum": 0, "seq_first": None, "seq_last": None,
        "drop_first": None, "drop_last": None,
    }


def scan(path: Path, progress_rows: int = 1_000_000) -> dict:
    started = time.time()
    size = path.stat().st_size
    out = {
        "schema_version": 1,
        "path": str(path.resolve()),
        "file": path.name,
        "size_bytes": size,
        "mtime_ns": path.stat().st_mtime_ns,
        "rows": 0,
        "bad_column_count": 0,
        "bad_integer_parse": 0,
        "bad_mac": 0,
        "csi_width_mismatch": 0,
        "field_implausible": 0,
        "pc_first_us": None,
        "pc_last_us": None,
        "pc_backsteps": 0,
        "pc_dt_max_us": 0,
        "pc_dt_hist": Counter(),
        "esp_wraps": 0,
        "esp_backsteps_nonwrap": 0,
        "esp_dt_max_us": 0,
        "mac_counts": Counter(),
        "label_counts": Counter(),
        "length_counts": Counter(),
        "channel_counts": Counter(),
        "node_counts": Counter(),
        "env_counts": Counter(),
        "noise_counts": Counter(),
        "rssi_counts": Counter(),
        "drop_change_rows": 0,
        "drop_positive_total_mod_u16": 0,
        "drop_large_jumps_gt100": 0,
        "sequence": defaultdict(lambda: {
            "first": None, "last": None, "same": 0, "forward_one": 0,
            "forward_other": 0, "back_or_large": 0, "max_forward": 0,
        }),
        "beacon_seconds": defaultdict(new_series_cell),
    }
    if size == 0:
        out["empty"] = True
        out["elapsed_s"] = time.time() - started
        return out

    csv.field_size_limit(10 ** 7)
    prev_pc = None
    prev_esp = None
    prev_drop = None
    origin_pc = None
    with path.open("r", newline="", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        out["header"] = header
        out["header_exact"] = header == COLS
        if not header or any(c not in header for c in COLS):
            out["fatal"] = "missing required columns"
            out["elapsed_s"] = time.time() - started
            return out
        idx = {name: header.index(name) for name in COLS}
        for row in reader:
            out["rows"] += 1
            nrow = out["rows"]
            if len(row) != len(header):
                out["bad_column_count"] += 1
                continue
            try:
                pc = int(row[idx["pc_time_us"]])
                seq = int(row[idx["seq"]])
                mac = row[idx["mac"]].lower()
                rssi = int(row[idx["rssi"]])
                noise = int(row[idx["noise_floor"]])
                channel = int(row[idx["channel"]])
                esp = int(row[idx["esp_timestamp_us"]])
                declared_len = int(row[idx["len"]])
                node = int(row[idx["node_id"]])
                env = int(row[idx["env_id"]])
                drop = int(row[idx["dropped"]])
            except (ValueError, IndexError):
                out["bad_integer_parse"] += 1
                continue

            if origin_pc is None:
                origin_pc = pc
                out["pc_first_us"] = pc
            out["pc_last_us"] = pc
            if prev_pc is not None:
                dt = pc - prev_pc
                out["pc_dt_hist"][dt_bucket(dt)] += 1
                out["pc_dt_max_us"] = max(out["pc_dt_max_us"], dt)
                if dt < 0:
                    out["pc_backsteps"] += 1
            prev_pc = pc

            if prev_esp is not None:
                raw_delta = esp - prev_esp
                if raw_delta < -(1 << 31):
                    out["esp_wraps"] += 1
                    edt = raw_delta + (1 << 32)
                else:
                    edt = raw_delta
                    if raw_delta < 0:
                        out["esp_backsteps_nonwrap"] += 1
                out["esp_dt_max_us"] = max(out["esp_dt_max_us"], edt)
            prev_esp = esp

            if prev_drop is not None:
                dd = (drop - prev_drop) % 65536
                if dd:
                    out["drop_change_rows"] += 1
                    out["drop_positive_total_mod_u16"] += dd
                    if dd > 100:
                        out["drop_large_jumps_gt100"] += 1
            prev_drop = drop

            out["mac_counts"][mac] += 1
            out["label_counts"][row[idx["label"]]] += 1
            out["length_counts"][declared_len] += 1
            out["channel_counts"][channel] += 1
            out["node_counts"][node] += 1
            out["env_counts"][env] += 1
            out["noise_counts"][noise] += 1
            out["rssi_counts"][rssi] += 1
            if not valid_mac(mac):
                out["bad_mac"] += 1

            csi_text = row[idx["csi_data"]]
            actual_len = 0 if not csi_text else csi_text.count(",") + 1
            if actual_len != declared_len:
                out["csi_width_mismatch"] += 1
            if not (declared_len in CSI_LEN_OK and -110 <= noise <= -70
                    and -100 <= rssi <= -10 and 0 <= drop <= 65535):
                out["field_implausible"] += 1

            sq = out["sequence"][mac]
            if sq["first"] is None:
                sq["first"] = seq
            if sq["last"] is not None:
                ds = (seq - sq["last"]) % (1 << 32)
                if ds == 0:
                    sq["same"] += 1
                elif ds == 1:
                    sq["forward_one"] += 1
                elif ds < (1 << 31):
                    sq["forward_other"] += 1
                    sq["max_forward"] = max(sq["max_forward"], ds)
                else:
                    sq["back_or_large"] += 1
            sq["last"] = seq

            beacon = BEACONS.get(mac)
            if beacon is not None:
                sec = (pc - origin_pc) // 1_000_000
                key = f"{beacon}:{sec}"
                cell = out["beacon_seconds"][key]
                cell["n"] += 1
                cell["rssi_sum"] += rssi
                cell["rssi_min"] = min(cell["rssi_min"], rssi)
                cell["rssi_max"] = max(cell["rssi_max"], rssi)
                cell["noise_sum"] += noise
                if cell["seq_first"] is None:
                    cell["seq_first"] = seq
                    cell["drop_first"] = drop
                cell["seq_last"] = seq
                cell["drop_last"] = drop

            if progress_rows and nrow % progress_rows == 0:
                rate = nrow / max(time.time() - started, 1e-9)
                print(f"{path.name}: {nrow:,} rows, {rate:,.0f} rows/s",
                      file=sys.stderr, flush=True)

    out["duration_s"] = ((out["pc_last_us"] - out["pc_first_us"]) / 1e6
                         if out["pc_first_us"] is not None else None)
    out["elapsed_s"] = time.time() - started
    for name in ("mac_counts", "label_counts", "length_counts",
                 "channel_counts", "node_counts", "env_counts",
                 "noise_counts", "rssi_counts", "pc_dt_hist"):
        out[name] = counter_dict(out[name])
    out["sequence"] = dict(out["sequence"])
    out["beacon_seconds"] = dict(out["beacon_seconds"])
    return out


def save(result: dict, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(result, f, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, dest)


def completed_matches(dest: Path, source: Path) -> bool:
    if not dest.exists():
        return False
    try:
        with gzip.open(dest, "rt", encoding="utf-8") as f:
            old = json.load(f)
        st = source.stat()
        return old.get("size_bytes") == st.st_size and old.get("mtime_ns") == st.st_mtime_ns
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--progress-rows", type=int, default=1_000_000)
    args = ap.parse_args()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    for raw in args.paths:
        path = Path(raw)
        dest = outdir / f"{path.stem}.census.json.gz"
        if not args.force and completed_matches(dest, path):
            print(f"skip completed {path.name}", file=sys.stderr)
            continue
        print(f"scan {path}", file=sys.stderr, flush=True)
        result = scan(path, args.progress_rows)
        save(result, dest)
        print(f"done {path.name}: {result['rows']:,} rows in "
              f"{result['elapsed_s']:.1f}s -> {dest}", file=sys.stderr,
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
