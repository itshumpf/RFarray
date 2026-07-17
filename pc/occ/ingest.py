#!/usr/bin/env python3
"""CSI amplitude ingestion: capture CSV -> per-link uniform time grids.

Physics
-------
Occupancy sensing lives in the *amplitude* domain. |H(f,t)| at each
subcarrier is the magnitude of a multipath sum; a body moving (or merely
breathing) in the space changes path lengths and re-weights that sum,
so |H| ripples. ESP32 phase carries an uncalibrated per-packet timing
offset (useless for absolute channel phase), which is why amplitude is
the trustworthy observable here — phase stays the fingerprinting domain.

Two nuisance effects are removed before |H| is comparable across frames:

1. AGC. The receiver applies an unknown gain step per frame, so absolute
   amplitude is meaningless. Each frame's 52-bin vector is normalized to
   unit mean: the spectral *shape* survives, the gain cancels. The
   pre-normalization RMS and the reported RSSI are kept as separate,
   coarser channels (they still carry body-shadowing information, mixed
   with AGC steps).
2. Irregular sampling. Beacon arrivals are collision-thinned (~35-60 fps
   per link, aperiodic), and spectral analysis needs an honest time
   axis. Frames are median-binned onto a uniform grid; empty bins stay
   NaN and downstream code decides how much gap-filling it tolerates.

Time axis: pc_time_us is stamped when the serial *drain batch* reaches
the PC, so frames arrive in bursts sharing one timestamp — useless for
spectral work. The node's own esp_timestamp_us is the true capture time
(u32 us, wraps every ~71.6 min; unwrapped here via rff.protocol). The
grid uses wall = first pc_time + esp-clock deltas, resyncing the anchor
if the two clocks diverge > 5 s (node reboot mid-capture).

Grids are cached as .npz next to data/cache/ keyed on file size+mtime,
because re-parsing a 2.4 GB CSV for every analysis iteration is silly.
"""
import os
import time

import numpy as np

from rff.dsp import K_USABLE, _USABLE_IDX   # frozen, validated LLTF mapping
from rff.protocol import unwrap_ts
from . import BEACON_MACS

N_SC = K_USABLE.size                        # 52 usable subcarriers
_LLTF_INTS = 128                            # 64 complex int8 pairs

CACHE_VERSION = 3
RESYNC_S = 5.0                # pc-vs-esp clock divergence forcing a resync


class LinkGrid:
    """One TX->RX link resampled onto a uniform grid.

    Attributes:
      mac       beacon MAC
      t0        wall-clock epoch seconds of bin 0
      dt        bin width in seconds
      shape     (n, 52) float32 — unit-mean |H| shape per bin (NaN = no data)
      rms       (n,) float32 — median pre-normalization frame RMS (AGC-mixed)
      rssi      (n,) float32 — median reported RSSI
      count     (n,) int16   — frames that landed in the bin
    """

    def __init__(self, mac, t0, dt, shape, rms, rssi, count):
        self.mac, self.t0, self.dt = mac, t0, dt
        self.shape, self.rms, self.rssi, self.count = shape, rms, rssi, count

    @property
    def n(self):
        return self.shape.shape[0]

    def times(self):
        return self.t0 + np.arange(self.n) * self.dt

    def coverage(self):
        """Fraction of bins that received at least one frame."""
        return float((self.count > 0).mean()) if self.n else 0.0

    def filled_shape(self, max_gap_s=2.0):
        """shape with NaN gaps <= max_gap_s linearly interpolated.

        Longer gaps stay NaN — inventing a minute of data would fabricate
        spectral content exactly where the respiration FFT looks.
        Returns (filled, valid_mask) where valid_mask marks bins that are
        real or short-gap-interpolated.
        """
        A = self.shape.copy()
        ok = self.count > 0
        if not ok.any():
            return A, ok
        max_gap = max(1, int(round(max_gap_s / self.dt)))
        idx = np.where(ok)[0]
        valid = ok.copy()
        # interpolate each column over short gaps only
        gaps = np.split(np.where(~ok)[0],
                        np.where(np.diff(np.where(~ok)[0]) != 1)[0] + 1) \
            if (~ok).any() else []
        fill_bins = []
        for g in gaps:
            if g.size == 0:
                continue
            if g.size <= max_gap and g[0] > idx[0] and g[-1] < idx[-1]:
                fill_bins.extend(g.tolist())
        if fill_bins:
            fill_bins = np.array(fill_bins)
            t = np.arange(self.n, dtype=np.float64)
            for k in range(A.shape[1]):
                A[fill_bins, k] = np.interp(t[fill_bins], t[idx],
                                            self.shape[idx, k])
            valid[fill_bins] = True
        return A, valid


def iter_amp_rows(path, macs=None):
    """Stream (t_wall_s, label, mac, rssi, amp52_unit_mean, rms) rows.

    Only rows whose MAC is in `macs` (default: the beacon fleet) pay the
    CSI-parse cost; ambient traffic is skipped after a cheap string split.

    t_wall_s is wall-clock epoch seconds built from the node's esp clock
    (true capture instants) anchored to the first frame's pc time; the
    anchor resyncs if pc and esp clocks diverge > RESYNC_S (node reboot).
    """
    if macs is None:
        macs = set(BEACON_MACS)
    usable = _USABLE_IDX
    prev_esp = prev_unwrapped = None
    anchor = None                 # wall seconds at esp_unwrapped == 0
    with open(path, "r", newline="") as f:
        header = f.readline().rstrip("\n").split(",")
        try:
            i_t = header.index("pc_time_us")
            i_lab = header.index("label")
            i_mac = header.index("mac")
            i_rssi = header.index("rssi")
            i_esp = header.index("esp_timestamp_us")
        except ValueError:
            raise ValueError(f"{path}: unrecognized CSV header")
        for line in f:
            parts = line.split(",", 9)
            if len(parts) < 10:
                continue
            mac = parts[i_mac].lower()
            if mac not in macs:
                continue
            csi_str = parts[9]
            q1 = csi_str.find('"')
            q2 = csi_str.rfind('"')
            if q1 < 0 or q2 <= q1:
                continue
            try:
                t_pc = int(parts[i_t]) * 1e-6
                rssi = int(parts[i_rssi])
                esp = int(parts[i_esp])
            except ValueError:
                continue
            u = unwrap_ts(esp, prev_esp, prev_unwrapped)
            prev_esp, prev_unwrapped = esp, u
            t_esp = u * 1e-6
            if anchor is None or abs((anchor + t_esp) - t_pc) > RESYNC_S:
                anchor = t_pc - t_esp
            t_s = anchor + t_esp
            v = np.fromstring(csi_str[q1 + 1:q2], dtype=np.float64, sep=",")
            if v.size < _LLTF_INTS:
                continue
            iq = v[:_LLTF_INTS]
            amp = np.hypot(iq[1::2], iq[0::2])[usable]   # |H| sorted by k
            m = amp.mean()
            if m <= 0:
                continue
            yield (t_s, parts[i_lab], mac,
                   rssi, (amp / m).astype(np.float32),
                   float(np.sqrt(np.mean(amp * amp))))


def _cache_path(csv_path, grid_hz):
    d = os.path.join(os.path.dirname(os.path.abspath(csv_path)),
                     "..", "cache")
    base = os.path.basename(csv_path)
    return os.path.join(d, f"{base}.occ{grid_hz:g}hz.npz")


def _cache_key(csv_path):
    st = os.stat(csv_path)
    return np.array([CACHE_VERSION, st.st_size, int(st.st_mtime)],
                    dtype=np.int64)


def build_link_grids(csv_path, grid_hz=10.0, macs=None, cache=True,
                     verbose=True):
    """Parse (or load cached) per-link grids for one capture CSV.

    Returns (grids: {mac: LinkGrid}, labels: [(t_s, label), ...]).
    labels holds label *transitions* (value changes only), so scripted
    ground-truth sessions survive the caching round trip.
    """
    if macs is None:
        macs = set(BEACON_MACS)
    cp = _cache_path(csv_path, grid_hz)
    key = _cache_key(csv_path)
    if cache and os.path.exists(cp):
        z = np.load(cp, allow_pickle=False)
        if "key" in z and np.array_equal(z["key"], key):
            grids = {}
            for mac in [m.decode() if isinstance(m, bytes) else str(m)
                        for m in z["macs"]]:
                p = mac.replace(":", "")
                grids[mac] = LinkGrid(
                    mac, float(z[f"{p}_t0"]), 1.0 / grid_hz,
                    z[f"{p}_shape"], z[f"{p}_rms"], z[f"{p}_rssi"],
                    z[f"{p}_count"])
            labels = [(float(t), s) for t, s in
                      zip(z["label_t"], z["label_s"])] \
                if "label_t" in z else []
            if verbose:
                print(f"  [cache] {os.path.basename(csv_path)}")
            return grids, labels

    dt = 1.0 / grid_hz
    acc = {m: {"bins": {}, "cur": None, "cur_bin": -1} for m in macs}
    t_min, t_max = None, None
    labels = []
    last_label = ""
    n_rows = 0
    t_start = time.time()

    def finalize(a):
        b = a["cur_bin"]
        cur = a["cur"]
        if cur is None or b < 0:
            return
        amps = np.stack([c[0] for c in cur])
        a["bins"][b] = (np.median(amps, axis=0).astype(np.float32),
                        float(np.median([c[1] for c in cur])),
                        float(np.median([c[2] for c in cur])),
                        len(cur))
        a["cur"] = None

    for t_s, label, mac, rssi, amp, rms in iter_amp_rows(csv_path, macs):
        n_rows += 1
        if t_min is None:
            t_min = t_s
        t_max = t_s
        if label != last_label:
            labels.append((t_s, label))
            last_label = label
        a = acc[mac]
        b = int((t_s - t_min) / dt)
        if b < 0:                      # clock resync stepped backwards
            continue
        if b != a["cur_bin"]:
            finalize(a)
            a["cur_bin"] = b
            a["cur"] = []
        a["cur"].append((amp, rms, rssi))
    for a in acc.values():
        finalize(a)

    if t_min is None:
        raise ValueError(f"{csv_path}: no beacon frames found")
    n_bins = int((t_max - t_min) / dt) + 1

    grids = {}
    for mac, a in acc.items():
        if not a["bins"]:
            continue
        shape = np.full((n_bins, N_SC), np.nan, dtype=np.float32)
        rms = np.full(n_bins, np.nan, dtype=np.float32)
        rssi = np.full(n_bins, np.nan, dtype=np.float32)
        count = np.zeros(n_bins, dtype=np.int16)
        for b, (s, r, rs, c) in a["bins"].items():
            shape[b], rms[b], rssi[b], count[b] = s, r, rs, min(c, 32767)
        grids[mac] = LinkGrid(mac, t_min, dt, shape, rms, rssi, count)

    if verbose:
        el = time.time() - t_start
        print(f"  parsed {os.path.basename(csv_path)}: {n_rows:,} beacon "
              f"frames -> {n_bins:,} bins x {len(grids)} links "
              f"({el:.0f}s)")

    if cache:
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        payload = {"key": key,
                   "macs": np.array(sorted(grids), dtype="U17"),
                   "label_t": np.array([t for t, _ in labels]),
                   "label_s": np.array([s for _, s in labels], dtype="U32")}
        for mac, g in grids.items():
            p = mac.replace(":", "")
            payload[f"{p}_t0"] = np.float64(g.t0)
            payload[f"{p}_shape"] = g.shape
            payload[f"{p}_rms"] = g.rms
            payload[f"{p}_rssi"] = g.rssi
            payload[f"{p}_count"] = g.count
        np.savez_compressed(cp, **payload)
    return grids, labels
