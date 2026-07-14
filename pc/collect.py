#!/usr/bin/env python3
"""Serial -> CSV collector for a single CSI node (binary protocol).

Usage:
    python collect.py COM6 --out node1.csv
    python collect.py /dev/ttyUSB0 --out node1.csv --label walking

Run one instance per RX node. Adds a PC receive timestamp and optional
activity label to every row, so recordings are self-documenting. Decodes
the firmware's compact binary frames and writes the same CSV format the
analysis tools expect. Ctrl+C to stop.

For multiple nodes at once with a live console, use capture.py instead.
"""
import argparse
import csv
import sys
import time

import serial

from rff.protocol import decode_stream
from rff.serialio import open_serial

HEADER = [
    "pc_time_us", "label", "seq", "mac", "rssi", "noise_floor",
    "channel", "esp_timestamp_us", "len", "csi_data",
    "node_id", "env_id", "dropped",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="CSI serial collector (binary)")
    ap.add_argument("port", help="serial port (COM6, /dev/ttyUSB0, ...)")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--out", default=None, help="output CSV (default: auto-named)")
    ap.add_argument("--label", default="", help="activity label stored per row")
    args = ap.parse_args()

    out_path = args.out or time.strftime("csi_%Y%m%d_%H%M%S.csv")

    try:
        ser = open_serial(args.port, args.baud)
    except serial.SerialException as e:
        print(f"cannot open {args.port}: {e}", file=sys.stderr)
        return 1

    count = 0
    bytes_seen = 0
    warned = False
    t_start = time.time()
    buf = bytearray()
    print(f"logging {args.port} @ {args.baud} -> {out_path}  (Ctrl+C to stop)")

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        try:
            while True:
                chunk = ser.read(8192)
                # Diagnose a silent stall (the classic baud/port mismatch): no
                # frame ever decodes and the CSV stays empty. Warn once at ~3 s.
                if count == 0 and not warned and time.time() - t_start > 3:
                    if bytes_seen == 0:
                        print(f"\n[!] no bytes on {args.port} after 3 s — board "
                              f"not sending, wrong port, or unpowered.", file=sys.stderr)
                    else:
                        print(f"\n[!] {bytes_seen} bytes but 0 valid frames on "
                              f"{args.port} — likely baud mismatch (--baud "
                              f"{args.baud} != board) or OUTPUT_BINARY off in "
                              f"firmware.", file=sys.stderr)
                    warned = True
                if not chunk:
                    continue
                bytes_seen += len(chunk)
                buf.extend(chunk)
                for rec in decode_stream(buf):
                    if rec["type"] != "csi":
                        continue        # STATUS frames: use field_diag.py
                    writer.writerow([
                        int(time.time() * 1e6), args.label, rec["seq"], rec["mac"],
                        rec["rssi"], rec["noise"], rec["channel"], rec["ts"],
                        rec["len"], ",".join(str(v) for v in rec["csi"]),
                        rec["node_id"], rec["env_id"], rec["dropped"],
                    ])
                    count += 1
                    if count % 500 == 0:
                        rate = count / (time.time() - t_start)
                        print(f"\r{count} samples  ({rate:.0f}/s)",
                              end="", flush=True)
        except KeyboardInterrupt:
            pass
        finally:
            ser.close()

    dt = time.time() - t_start
    print(f"\ndone: {count} samples in {dt:.1f}s -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
