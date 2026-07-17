#!/usr/bin/env python3
r"""Ground-truth capture: CSI recording with live keyboard labeling.

Same CSV format as capture.py, but the `label` column (empty since
Phase 1) is filled with the operator's current ground-truth state, so
occ_offline.py can score detectors honestly instead of assuming what a
session contained.

Usage:
  python pc\occ_capture.py COM3 --labels empty,walk,still,out
    keys 1..9  -> set the corresponding label
    0 or space -> clear label (unscored time)
    q          -> stop

A scripted session then looks like: start with the room empty, press 1;
walk a defined path, press 2 while walking; sit motionless, press 3;
leave, press 4 on the way out. Timestamps of every keypress land in the
CSV with the frames they describe.

Serial is opened via rff.serialio.open_serial (no DTR/RTS reset — a
plain pyserial open would restart the node's calibration cycle).
"""
import argparse
import csv as csvmod
import os
import sys
import time

from rff.protocol import decode_stream, CAL_STATES
from rff.serialio import open_serial
from occ import BEACON_MACS

HEADER = ["pc_time_us", "label", "seq", "mac", "rssi", "noise_floor",
          "channel", "esp_timestamp_us", "len", "csi_data",
          "node_id", "env_id", "dropped"]
RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "data", "raw")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", help="collector COM port (e.g. COM3)")
    ap.add_argument("--labels", default="empty,walk,still,out",
                    help="comma-separated label names bound to keys 1..9")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--out", help="output CSV (default data/raw/occ_*.csv)")
    args = ap.parse_args()

    labels = [s.strip() for s in args.labels.split(",") if s.strip()][:9]
    out = args.out
    if not out:
        os.makedirs(RAW_DIR, exist_ok=True)
        out = os.path.join(RAW_DIR,
                           f"occ_{time.strftime('%Y%m%d_%H%M%S')}.csv")

    if os.name == "nt":
        import msvcrt

        def poll_key():
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                return ch
            return None
    else:
        # POSIX fallback: line-buffered stdin (press key then Enter)
        import select

        def poll_key():
            r, _, _ = select.select([sys.stdin], [], [], 0)
            if r:
                s = sys.stdin.readline().strip()
                return s[:1] if s else None
            return None

    ser = open_serial(args.port, args.baud)
    buf = bytearray()
    label = ""
    n_frames = 0
    per_beacon = {m: 0 for m in BEACON_MACS}
    status = ""
    t_start = time.time()
    t_disp = 0.0

    key_help = "  ".join(f"[{i+1}]{s}" for i, s in enumerate(labels))
    print(f"recording -> {out}")
    print(f"{key_help}  [0/space]clear  [q]quit")

    with open(out, "w", newline="") as f:
        w = csvmod.writer(f)
        w.writerow(HEADER)
        try:
            while True:
                ch = poll_key()
                if ch is not None:
                    if ch.lower() == "q":
                        break
                    if ch in ("0", " "):
                        label = ""
                        print(f"\n  {time.strftime('%H:%M:%S')} "
                              f"label cleared")
                    elif ch.isdigit() and 1 <= int(ch) <= len(labels):
                        label = labels[int(ch) - 1]
                        print(f"\n  {time.strftime('%H:%M:%S')} "
                              f"label = '{label}'")
                chunk = ser.read(8192)
                if chunk:
                    buf.extend(chunk)
                    for rec in decode_stream(buf):
                        if rec["type"] == "status":
                            cal = CAL_STATES.get(rec["cal_state"], "?")
                            status = f"cal:{cal}"
                            continue
                        w.writerow([int(time.time() * 1e6), label,
                                    rec["seq"], rec["mac"], rec["rssi"],
                                    rec["noise"], rec["channel"], rec["ts"],
                                    rec["len"],
                                    ",".join(map(str, rec["csi"])),
                                    rec["node_id"], rec["env_id"],
                                    rec["dropped"]])
                        n_frames += 1
                        if rec["mac"] in per_beacon:
                            per_beacon[rec["mac"]] += 1
                now = time.time()
                if now - t_disp > 1.0:
                    t_disp = now
                    el = int(now - t_start)
                    rates = " ".join(
                        f"{BEACON_MACS[m]}:{c}" for m, c in
                        sorted(per_beacon.items(),
                               key=lambda kv: BEACON_MACS[kv[0]]))
                    sys.stdout.write(
                        f"\r  {el//60:02d}:{el%60:02d}  {n_frames:,} fr  "
                        f"{rates}  {status}  label='{label}'   ")
                    sys.stdout.flush()
        except KeyboardInterrupt:
            pass
    ser.close()
    print(f"\nwrote {n_frames:,} frames -> {out}")
    print(f"score it:  python pc\\occ_offline.py {out} "
          f"--calib <empty-room csv>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
