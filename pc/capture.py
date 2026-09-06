#!/usr/bin/env python3
r"""Unified multi-node CSI capture with a live matrix-rain console."""
import argparse
import collections
import math
import os
import sys
import threading
import time
import numpy as np

# ---- optional serial -------------------------------------------------------
try:
    import serial
except ImportError:
    serial = None

from rff.protocol import decode_stream, CAL_STATES

HEADER = ["pc_time_us", "label", "seq", "mac", "rssi", "noise_floor",
          "channel", "esp_timestamp_us", "len", "csi_data",
          "node_id", "env_id", "dropped"]

def compute_cfo(csi_data):
    """Calculates phase slope (CFO) using linear regression on unwrapped phase."""
    iq = np.array(csi_data, dtype=np.float32)
    iq = iq[: len(iq) & ~1]          # drop a trailing odd byte: i/q must pair
    if iq.size < 4:
        return 0.0
    complex_csi = iq[0::2] + 1j * iq[1::2]
    phases = np.unwrap(np.angle(complex_csi))
    slope, _ = np.polyfit(np.arange(len(phases)), phases, 1)
    return slope

RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw")
N_SC = 32 
RAIN_ROWS = 8
SHADE = " .:-=+*#%@"

# ---- ANSI -------------------------------------------------------------------
CSI0 = "\x1b["
# Viridis, not a hue rainbow. A rainbow ramp is non-monotonic in perceived
# brightness — yellow reads brighter than blue at a lower value — so the eye
# invents boundaries that aren't in the data. Viridis is perceptually uniform:
# brighter always means more. Same reason matplotlib retired `jet`.
VIRIDIS = [(68, 1, 84), (72, 40, 120), (62, 74, 137), (49, 104, 142),
           (38, 130, 142), (31, 158, 137), (53, 183, 121), (109, 205, 89),
           (180, 222, 44), (253, 231, 37)]

def green(intensity):
    """Truecolor viridis ramp. Name kept so nothing else has to change."""
    i = min(len(VIRIDIS) - 1, max(0, int(intensity * (len(VIRIDIS) - 1))))
    r, g, b = VIRIDIS[i]
    return f"{CSI0}38;2;{r};{g};{b}m"

HIDE, SHOW = f"{CSI0}?25l", f"{CSI0}?25h"
HOME, CLEAR = f"{CSI0}H", f"{CSI0}2J"
RESET, BOLD = f"{CSI0}0m", f"{CSI0}1m"
GHEAD = f"{CSI0}38;5;46m"
GDIM = f"{CSI0}38;5;28m"

class Node:
    def __init__(self, name, port):
        self.name, self.port = name, port
        self.total = 0
        self.times = collections.deque(maxlen=200)
        self.last_rssi = 0
        self.macs = set()
        self.mac_cfo = {}
        self.rain = collections.deque(maxlen=RAIN_ROWS)
        self.status = "opening"
        self.lock = threading.Lock()
        self.baseline = None

    def get_differential(self, current_amps):
        amps_arr = np.array(current_amps)
        if len(amps_arr) > 64: amps_arr = amps_arr[:64]
        elif len(amps_arr) < 64: amps_arr = np.pad(amps_arr, (0, 64 - len(amps_arr)), 'constant')
        if self.baseline is None:
            self.baseline = amps_arr.copy()
            return np.zeros_like(amps_arr)
        self.baseline = 0.95 * self.baseline + 0.05 * amps_arr
        return amps_arr - self.baseline

    def rate(self):
        now = time.time()
        recent = [t for t in self.times if now - t < 2.0]
        return len(recent) / 2.0 if recent else 0.0

    def feed(self, seq, mac, rssi, amps, csi_raw):
        with self.lock:
            # Update CFO
            self.mac_cfo[mac] = 0.95 * self.mac_cfo.get(mac, 0) + 0.05 * compute_cfo(csi_raw)
            # Rain logic
            diff_amps = self.get_differential(amps)
            display_amps = np.abs(diff_amps)
            self.total += 1
            self.times.append(time.time())
            self.last_rssi = rssi
            self.macs.add(mac)
            row = []
            step = max(1, len(display_amps) // N_SC)
            for i in range(N_SC):
                seg = display_amps[i * step:(i + 1) * step]
                row.append(sum(seg) / len(seg) if len(seg) > 0 else 0.0)
            self.rain.append(row)
            self.status = "live"

# Current event label, written into every row until it changes. A one-element
# list rather than a bare global so the reader threads see updates without a
# lock — CPython list-item assignment is atomic, and a torn read here would
# cost one mislabelled row, not a capture.
#
# Why this exists: `label` has been in HEADER since v1 and nothing ever wrote
# to it. Every experiment so far was reconstructed from wall-clock times typed
# into a chat window afterwards, and on 2026-08-23 two of seven logged events
# turned out to be wrong when checked against the frames.
LABEL = [""]


def label_prompt():
    """Blocking prompt, called from the render loop when a key is pressed.

    Wrapped by its caller: if anything in here raises, labelling is skipped
    and the capture keeps running. Losing a label is an inconvenience.
    Losing a capture is an evening.
    """
    sys.stdout.write(SHOW + f"\n{CSI0}0m label (empty to clear): ")
    sys.stdout.flush()
    try:
        text = sys.stdin.readline().strip()
    finally:
        sys.stdout.write(HIDE + CLEAR)
        sys.stdout.flush()
    LABEL[0] = text[:60]


def key_pressed():
    """True if a key is waiting. Windows only; silently False elsewhere."""
    try:
        import msvcrt
        if msvcrt.kbhit():
            msvcrt.getwch()          # consume the keypress itself
            return True
    except Exception:
        pass
    return False


def reader_thread(node, stop, baud):
    import csv as csvmod
    os.makedirs(RAW_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = os.path.join(RAW_DIR, f"{node.name}_{ts}.csv")
    try:
        from rff.serialio import open_serial
        ser = open_serial(node.port, baud)
    except Exception as e:
        node.status = f"ERR {e}"
        return
    buf = bytearray()
    with open(out, "w", newline="") as f:
        w = csvmod.writer(f)
        w.writerow(HEADER)
        while not stop.is_set():
            try:
                chunk = ser.read(8192)
            except Exception:
                node.status = "ERR read"
                break
            if not chunk: continue
            buf.extend(chunk)
            for rec in decode_stream(buf):
                if rec["type"] == "status":
                    cal = CAL_STATES.get(rec["cal_state"], "?")
                    node.status = (f"live n{rec['node_id']} cal:{cal}"
                                   + (f" {rec['cal_remaining_s']}s"
                                      if rec["cal_state"] == 0 else ""))
                    continue
                w.writerow([int(time.time() * 1e6), LABEL[0], rec["seq"], rec["mac"],
                            rec["rssi"], rec["noise"], rec["channel"], rec["ts"],
                            rec["len"], ",".join(map(str, rec["csi"])),
                            rec["node_id"], rec["env_id"], rec["dropped"]])
                csi = rec["csi"]
                amps = [math.hypot(csi[i], csi[i + 1]) for i in range(0, len(csi) - 1, 2)]
                node.feed(rec["seq"], rec["mac"], rec["rssi"], amps, csi)
    ser.close()

def render(nodes, start):
    out = [HOME]
    el = int(time.time() - start)
    grand = sum(n.total for n in nodes)
    out.append(f"{GHEAD}{BOLD} CSI ARRAY // LIVE CAPTURE {RESET}"
               f"{GDIM}  up {el//3600:02d}:{(el%3600)//60:02d}:{el%60:02d}"
               f"   {grand:,} frames total{RESET}{CSI0}K\n")
    lab = LABEL[0]
    out.append(f"{GDIM} label: {RESET}"
               + (f"{GHEAD}{lab}{RESET}" if lab else f"{GDIM}(none){RESET}")
               + f"{GDIM}   — press any key to set{RESET}{CSI0}K\n")
    out.append(f"{GDIM} {'─'*58}{RESET}{CSI0}K\n")
    for n in nodes:
        with n.lock:
            rain = list(n.rain)
            rate, tot, rssi = n.rate(), n.total, n.last_rssi
            macs, status = len(n.macs), n.status
            dot = "●" if rate > 1 else "○"
            out.append(f"{GHEAD} {dot} {n.name:<7}{RESET}{GDIM}{n.port:<7}{RESET}"
                       f"  {GHEAD}{rate:4.0f}/s{RESET}{GDIM}  {tot:>7,} fr   "
                       f"rssi {rssi:>4}   {macs} mac  {status}{RESET}{CSI0}K\n")
            
            # CFO Reporting
            for mac in list(n.macs)[-2:]:
                out.append(f"{GDIM} -> {mac} CFO: {n.mac_cfo.get(mac, 0):.4f}{RESET}{CSI0}K\n")
            
            vmax = max((max(r) for r in rain if r), default=1.0) or 1.0
            for _ in range(RAIN_ROWS - len(rain)):
                out.append(f"   {GDIM}{' '*N_SC}{RESET}{CSI0}K\n")
            for row in rain:
                line = []
                for v in row:
                    inten = min(1.0, v / vmax)
                    ch = SHADE[min(len(SHADE) - 1, int(inten * (len(SHADE) - 1)))]
                    line.append(f"{green(inten)}{ch}")
                out.append(f"   {''.join(line)}{RESET}{CSI0}K\n")
        out.append(f"{CSI0}K\n")
    out.append(f"{GDIM} ctrl-c to stop{RESET}{CSI0}K")
    sys.stdout.write("".join(out))
    sys.stdout.flush()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ports", nargs="*", help="PORT[:name] per node")
    ap.add_argument("--baud", type=int, default=460800)
    args = ap.parse_args()
    nodes = [Node(spec.partition(":")[2] or f"node{i}", spec.partition(":")[0]) 
             for i, spec in enumerate(args.ports)]
    stop = threading.Event()
    threads = [threading.Thread(target=reader_thread, args=(n, stop, args.baud), daemon=True)
                for n in nodes]
    for t in threads: t.start()
    if os.name == "nt": os.system("")
    sys.stdout.write(HIDE + CLEAR)
    main.start = time.time()
    try:
        while True:
            render(nodes, start=main.start)
            if key_pressed():
                try:
                    label_prompt()
                except Exception:
                    pass          # never let labelling kill a capture
            time.sleep(0.1)
    except KeyboardInterrupt: pass
    finally:
        stop.set()
        sys.stdout.write(SHOW + RESET + "\n")
        sys.stdout.flush()

if __name__ == "__main__": main()