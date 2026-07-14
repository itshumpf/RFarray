#!/usr/bin/env python3
"""Live RF signal discrimination: serial nodes -> DSP -> Kalman ->
Mahalanobis -> SQLite + TUI.

One reader thread per serial port decodes binary frames and runs the
per-frame DSP (unwrap + RANSAC) so a slow console can never back-pressure
a 100 Hz stream. The main thread aggregates windows, applies the
reference-beacon correction, updates each source's Kalman drift track and
Gaussian model, logs to SQLite, and renders the discrimination table.

Usage:
  python rff_live.py COM3:node1 COM12:node3 --ref-mac a4:f0:0f:77:91:20
  python rff_live.py COM12 --baud 460800 --window 64 --db ../data/rff.db

Verdicts per source (χ² thresholds on Mahalanobis² in (CFO, SFO) space):
  LEARNING   model still gathering observations
  STABLE     new windows fall inside own 95% ellipse
  DRIFTING   own-source d² between 95% and 99% — watch it
  ANOMALY    claimed MAC but signature rejects at 99% — investigate
"""
import argparse
import queue
import sys
import threading
import time
from collections import defaultdict

try:
    import serial
except ImportError:
    serial = None

from rich.console import Console
from rich.live import Live
from rich.table import Table

from rff.dsp import FrameEstimator, WindowAggregator
from rff.kalman import DriftTracker
from rff.discriminator import Discriminator, CHI2_95, CHI2_99
from rff.reference import ReferenceNormalizer
from rff.store import Store, DEFAULT_DB


class NodeReader(threading.Thread):
    """Serial port -> frames -> per-frame estimates -> window queue."""

    def __init__(self, name, port, baud, window, out_q, stop):
        super().__init__(daemon=True)
        self.name = name
        self.port = port
        self.baud = baud
        self.window = window
        self.out_q = out_q
        self.stop_evt = stop
        self.status = "opening"
        self.frames = 0

    def run(self):
        from rff.protocol import decode_stream
        from rff.serialio import open_serial
        try:
            ser = open_serial(self.port, self.baud)
        except Exception as e:
            self.status = f"ERR {e}"
            return
        self.status = "live"
        estimators = defaultdict(FrameEstimator)
        aggregators = defaultdict(lambda: WindowAggregator(window=self.window))
        buf = bytearray()
        while not self.stop_evt.is_set():
            try:
                chunk = ser.read(8192)
            except Exception:
                self.status = "ERR read"
                break
            if not chunk:
                continue
            buf.extend(chunk)
            for rec in decode_stream(buf):
                if rec["type"] != "csi":
                    continue                 # STATUS frames: health only
                self.frames += 1
                mac = rec["mac"]
                est = estimators[mac].feed(rec["csi"], rec["ts"])
                obs = aggregators[mac].feed(est, rec["ts"], rec["rssi"])
                if obs is not None:
                    self.out_q.put((self.name, mac, time.time(), obs))
        ser.close()


class SourceRow:
    """Live display + model state for one (source MAC)."""

    def __init__(self, mac):
        self.mac = mac
        self.tracker = DriftTracker()
        self.windows = 0
        self.last_seen = 0.0
        self.last_rssi = 0.0
        self.node = "-"
        self.d2_self = None
        self.verdict = "LEARNING"
        self.corrected = False


def feature(obs):
    cfo = obs.get("cfo_ref", obs.get("cfo"))
    sfo = obs.get("sfo_ref", obs.get("sfo"))
    if cfo is None or sfo is None:
        return None
    return [cfo, sfo]


def confidence(d2):
    """Map own-source Mahalanobis² to a rough stability confidence."""
    if d2 is None:
        return "-"
    if d2 <= CHI2_95:
        return f"{100 * (1 - d2 / CHI2_95) * 0.05 + 95:.0f}%"
    if d2 <= CHI2_99:
        return "marginal"
    return "reject"


def render(readers, rows, ref_mac, ref_ready):
    t = Table(title="RF SIGNAL DISCRIMINATION — live", title_justify="left")
    for col in ("source", "node", "wins", "rssi",
                "CFO Hz (KF)", "SFO rad/sc (KF)", "d² self", "conf",
                "verdict"):
        t.add_column(col, justify="right" if col not in
                     ("source", "node", "verdict") else "left")
    now = time.time()
    for mac in sorted(rows, key=lambda m: -rows[m].last_seen):
        r = rows[mac]
        stale = now - r.last_seen > 10
        cfo = f"{r.tracker.cfo.x:+.1f}" if r.tracker.cfo.initialized else "-"
        sfo = f"{r.tracker.sfo.x:+.4f}" if r.tracker.sfo.initialized else "-"
        if mac == (ref_mac or ""):
            label = f"[cyan]{mac} (REF)[/]"
        else:
            label = mac
        style = "dim" if stale else ("red" if r.verdict == "ANOMALY" else
                                     "yellow" if r.verdict == "DRIFTING"
                                     else "")
        mark = "*" if r.corrected else ""
        t.add_row(label, r.node, str(r.windows), f"{r.last_rssi:.0f}",
                  cfo + mark, sfo + mark,
                  f"{r.d2_self:.2f}" if r.d2_self is not None else "-",
                  confidence(r.d2_self), r.verdict, style=style or None)
    status = "  ".join(f"{rd.name}({rd.port}) {rd.status} {rd.frames}fr"
                       for rd in readers)
    ref_note = (f"  ref={ref_mac} [{'warm' if ref_ready else 'cold'}]"
                if ref_mac else "  (no reference beacon — raw drift)")
    t.caption = status + ref_note + "   * = reference-corrected"
    return t


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ports", nargs="+", help="PORT[:name] per node")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--window", type=int, default=64,
                    help="frames per observation window")
    ap.add_argument("--ref-mac", help="reference beacon MAC")
    ap.add_argument("--db", default=DEFAULT_DB, help="SQLite path")
    args = ap.parse_args()

    if serial is None:
        print("pyserial not installed: pip install pyserial", file=sys.stderr)
        return 1

    stop = threading.Event()
    obs_q = queue.Queue()
    readers = []
    for i, spec in enumerate(args.ports):
        port, _, name = spec.partition(":")
        readers.append(NodeReader(name or f"node{i}", port, args.baud,
                                  args.window, obs_q, stop))
    for r in readers:
        r.start()

    store = Store(args.db)                     # main thread only
    disc = Discriminator()
    # resume everything previously characterized
    for sid, model in store.load_models().items():
        mac_row = store.db.execute("SELECT mac FROM sources WHERE id=?",
                                   (sid,)).fetchone()
        if mac_row:
            model.source_id = mac_row[0]
            disc.models[mac_row[0]] = model
    if disc.models:
        print(f"resumed {len(disc.models)} source model(s) from {args.db}")

    ref = ReferenceNormalizer(args.ref_mac)
    rows = {}
    console = Console()
    last_commit = time.time()
    try:
        with Live(render(readers, rows, args.ref_mac, ref.ready),
                  console=console, refresh_per_second=4) as live:
            while True:
                try:
                    node, mac, ts_pc, obs = obs_q.get(timeout=0.25)
                except queue.Empty:
                    live.update(render(readers, rows, args.ref_mac,
                                       ref.ready))
                    continue

                obs, corrected = ref.feed(mac, obs)
                row = rows.setdefault(mac, SourceRow(mac))
                row.node = node
                row.windows += 1
                row.last_seen = ts_pc
                row.last_rssi = obs.get("rssi") or 0.0
                row.corrected = corrected
                row.tracker.update({
                    "cfo": obs.get("cfo_ref", obs.get("cfo")),
                    "cfo_iqr": obs.get("cfo_iqr"),
                    "sfo": obs.get("sfo_ref", obs.get("sfo")),
                    "sfo_iqr": obs.get("sfo_iqr")})

                f = feature(obs)
                verdict = "LEARNING"
                d2 = None
                if f is not None:
                    d2 = disc.self_consistency(mac, f)
                    if d2 is not None:
                        verdict = ("STABLE" if d2 <= CHI2_95 else
                                   "DRIFTING" if d2 <= CHI2_99 else
                                   "ANOMALY")
                    # anomalous windows must not poison the model
                    if verdict != "ANOMALY":
                        disc.learn(mac, f)
                row.d2_self = d2
                row.verdict = verdict

                sid = store.source_id(mac, now=ts_pc)
                store.add_observation(sid, node, ts_pc, obs,
                                      d2_self=d2, verdict=verdict)
                if mac in disc.models:
                    store.save_model(sid, disc.models[mac])
                if time.time() - last_commit > 2.0:
                    store.commit()
                    last_commit = time.time()

                live.update(render(readers, rows, args.ref_mac, ref.ready))
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        store.close()
        print("stopped; history saved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
