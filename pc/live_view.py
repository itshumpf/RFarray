#!/usr/bin/env python3
"""Live CSI amplitude waterfall — see motion in real time.

Usage:
    python live_view.py COM6

Top panel:    scrolling waterfall (time x subcarrier amplitude)
Bottom panel: motion metric (mean abs diff between consecutive frames)
Wave your hand near a node and watch it light up.
"""
import argparse
import collections
import sys
import threading

import numpy as np
import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation

HISTORY = 300          # frames shown in waterfall
N_SC = 64              # first 64 subcarriers (LLTF) for a stable-width view

# --- binary framing (matches firmware emit_binary) --------------------------
BIN_MAGIC = b"\xc5\x51"
BIN_HDR = 21


def decode_stream(buf):
    out = []
    consumed = 0
    n = len(buf)
    while True:
        j = buf.find(BIN_MAGIC, consumed)
        if j < 0:
            consumed = max(consumed, n - 1)
            break
        if j + BIN_HDR + 1 > n:
            consumed = j
            break
        length = buf[j + 19] | (buf[j + 20] << 8)
        if length == 0 or length > 384:
            consumed = j + 1
            continue
        total = BIN_HDR + length + 1
        if j + total > n:
            consumed = j
            break
        frame = bytes(buf[j:j + total])
        cks = 0
        for b in frame[2:BIN_HDR + length]:
            cks ^= b
        if cks != frame[BIN_HDR + length]:
            consumed = j + 1
            continue
        csi = np.frombuffer(frame[BIN_HDR:BIN_HDR + length], dtype=np.int8)
        out.append(csi)
        consumed = j + total
    del buf[:consumed]
    return out


class Reader(threading.Thread):
    def __init__(self, port: str, baud: int):
        super().__init__(daemon=True)
        self.ser = serial.Serial(port, baud, timeout=0.2)
        self.frames = collections.deque(maxlen=HISTORY)
        self.motion = collections.deque(maxlen=HISTORY)
        self._prev = None

    def run(self):
        buf = bytearray()
        while True:
            try:
                chunk = self.ser.read(8192)
            except serial.SerialException:
                break
            if not chunk:
                continue
            buf.extend(chunk)
            for vals in decode_stream(buf):
                if vals.size < N_SC * 2:
                    continue
                iq = vals[: N_SC * 2].astype(np.float32)
                amp = np.hypot(iq[0::2], iq[1::2])  # sqrt(i^2 + q^2)
                self.frames.append(amp)
                if self._prev is not None:
                    self.motion.append(float(np.mean(np.abs(amp - self._prev))))
                self._prev = amp


def main() -> int:
    ap = argparse.ArgumentParser(description="Live CSI waterfall")
    ap.add_argument("port")
    ap.add_argument("--baud", type=int, default=460800)
    args = ap.parse_args()

    reader = Reader(args.port, args.baud)
    reader.start()

    fig, (ax_w, ax_m) = plt.subplots(
        2, 1, figsize=(10, 7), gridspec_kw={"height_ratios": [3, 1]}
    )
    fig.suptitle(f"CSI live view — {args.port}")

    img = ax_w.imshow(
        np.zeros((N_SC, HISTORY)), aspect="auto", origin="lower",
        interpolation="nearest", cmap="viridis", vmin=0, vmax=40,
    )
    ax_w.set_ylabel("subcarrier")
    ax_w.set_xlabel("frame (newest right)")

    (line_m,) = ax_m.plot([], [], lw=1)
    ax_m.set_xlim(0, HISTORY)
    ax_m.set_ylim(0, 10)
    ax_m.set_ylabel("motion metric")
    ax_m.grid(True, alpha=0.3)

    def update(_):
        if reader.frames:
            data = np.array(reader.frames).T  # (subcarrier, time)
            padded = np.zeros((N_SC, HISTORY))
            padded[:, -data.shape[1]:] = data
            img.set_data(padded)
            img.set_clim(0, max(20, float(data.max())))
        if reader.motion:
            y = list(reader.motion)
            line_m.set_data(range(HISTORY - len(y), HISTORY), y)
            ax_m.set_ylim(0, max(5, max(y) * 1.2))
        return img, line_m

    _anim = animation.FuncAnimation(fig, update, interval=100, blit=False,
                                    cache_frame_data=False)
    plt.tight_layout()
    plt.show()
    return 0


if __name__ == "__main__":
    sys.exit(main())
