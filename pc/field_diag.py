#!/usr/bin/env python3
"""Field diagnostics: connect to a node, summarize its health.

Listens on the serial port for a few seconds, collects STATUS and CSI
telemetry, and prints a clinical health report: identity, uptime, reset
history, calibration state, link statistics (rate, RSSI, SNR, sequence
gaps, queue drops). Exit code 0 = healthy, 1 = no telemetry, 2 = warnings
(crashes recorded, drops observed, or calibration bypassed).

Usage:
  python field_diag.py COM3
  python field_diag.py COM3 --seconds 15 --baud 460800
"""
import argparse
import statistics
import sys
import time

try:
    import serial
except ImportError:
    serial = None

from rff.protocol import decode_stream, CAL_STATES, RESET_REASONS
from rff.serialio import open_serial


def listen(port, baud, seconds):
    ser = open_serial(port, baud)
    buf = bytearray()
    csi, status = [], []
    t_end = time.time() + seconds
    t0 = None
    while time.time() < t_end:
        chunk = ser.read(8192)
        if not chunk:
            continue
        if t0 is None:
            t0 = time.time()
        buf.extend(chunk)
        for rec in decode_stream(buf):
            (csi if rec["type"] == "csi" else status).append(rec)
    ser.close()
    span = (time.time() - t0) if t0 else 0.0
    return csi, status, span


def fmt_uptime(s):
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def report(port, csi, status, span):
    print(f"=== FIELD DIAGNOSTICS - {port} ===")
    if not csi and not status:
        print("no telemetry received. Check baud (460800 default), "
              "wiring, or whether the node is in safe-boot.")
        return 1

    warns = []
    st = status[-1] if status else None
    if st:
        print(f"node_id      : {st['node_id']}   env_id: {st['env_id']}   "
              f"fw: v{st['fw']}")
        print(f"uptime       : {fmt_uptime(st['uptime_s'])}")
        rr = RESET_REASONS.get(st['reset_reason'], str(st['reset_reason']))
        print(f"last reset   : {rr}")
        print(f"crash count  : {st['crash_count']}")
        cal = CAL_STATES.get(st['cal_state'], str(st['cal_state']))
        if st['cal_state'] == 0:
            cal += f" ({st['cal_remaining_s']} s remaining)"
        print(f"calibration  : {cal}")
        print(f"noise floor  : {st['noise_floor']:+.2f} dBm (EMA)")
        print(f"rssi avg     : {st['rssi_avg']:+.2f} dBm (EMA)  ->  "
              f"SNR {st['rssi_avg'] - st['noise_floor']:.2f} dB")
        print(f"totals       : {st['pkt_total']} frames captured, "
              f"{st['drop_total']} queue drops")
        print(f"heap free    : {st['heap_free']:,} bytes")
        if st['crash_count']:
            warns.append(f"{st['crash_count']} crash(es) recorded "
                         "(CLEARCRASH in safe-boot to reset)")
        if st['cal_state'] == 2:
            warns.append("calibration bypassed (cal_seconds=0)")
    else:
        print("(no STATUS frame seen — v1 firmware or window too short)")

    if csi:
        rssis = [r["rssi"] for r in csi]
        noises = [r["noise"] for r in csi]
        macs = {r["mac"] for r in csi}
        rate = len(csi) / span if span > 0 else 0.0
        print(f"live capture : {len(csi)} CSI frames in {span:.1f} s "
              f"({rate:.1f}/s), {len(macs)} distinct MAC(s)")
        print(f"rssi         : mean {statistics.mean(rssis):+.1f} dBm  "
              f"min {min(rssis)}  max {max(rssis)}")
        print(f"snr (inst)   : {statistics.mean(rssis) - statistics.mean(noises):.1f} dB")

        # sequence gaps within the dominant (beacon) MAC
        dom = max(macs, key=lambda m: sum(1 for r in csi if r["mac"] == m))
        seqs = [r["seq"] for r in csi if r["mac"] == dom]
        gaps = sum(max(b - a - 1, 0) for a, b in zip(seqs, seqs[1:]))
        print(f"seq gaps     : {gaps} missing beacon frame(s) "
              f"across {len(seqs)} from {dom}")

        drops = [r["dropped"] for r in csi if r["dropped"] is not None]
        if len(drops) >= 2 and drops[-1] != drops[0]:
            d = (drops[-1] - drops[0]) & 0xFFFF
            warns.append(f"{d} queue drop(s) during the listen window")
    else:
        print("live capture : no CSI frames (calibrating, or channel silent)")

    if warns:
        print("\nwarnings:")
        for w in warns:
            print(f"  - {w}")
    print("=== end of report ===")
    return 2 if warns else 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--seconds", type=float, default=12.0,
                    help="listen window (default 12 — two STATUS periods)")
    args = ap.parse_args()

    if serial is None:
        print("pyserial not installed: pip install pyserial", file=sys.stderr)
        return 1
    csi, status, span = listen(args.port, args.baud, args.seconds)
    return report(args.port, csi, status, span)


if __name__ == "__main__":
    sys.exit(main())
