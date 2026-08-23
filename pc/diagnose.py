#!/usr/bin/env python3
r"""diagnose - pre-capture health check for the array (receiver + beacons).

Run this after powering the beacons and the collector and before any real
capture. It opens the collector's serial port via `rff.serialio.open_serial`
(so it does NOT toggle DTR/RTS and does NOT restart the node's baseline
calibration), listens for a fixed window, and prints one row per transmitter
actually heard.

Read-only. Writes no CSV and touches nothing in data/, pc/rff/, pc/occ/,
firmware/ or site/. Frames are decoded by `rff.protocol.decode_stream` - the
same decoder capture.py, occ_capture.py and field_diag.py use - and the
expected beacon set comes from `occ.BEACON_MACS`, so this tool learns about a
new beacon the moment that dict does.

Usage
-----
  python pc\diagnose.py COM3
  python pc\diagnose.py COM3 --seconds 120
  python pc\diagnose.py COM3 --seconds 0                 # until ctrl-c
  python pc\diagnose.py COM3 --expect a4:f0:0f:77:91:20=B1,28:05:a5:2f:fa:48=B2

Columns
-------
  frames      CSI frames decoded from this MAC inside the window
  fps         frames / elapsed window seconds. The denominator is the same
              for every row, so a beacon that joined late reads low; late
              joiners are named under SUMMARY rather than silently rescaled.
  rssi        median / min / max of rx_ctrl.rssi, dBm
  maxgap_ms   longest interval between two consecutive frames of this MAC,
              measured on the node's own boot_ts_us so host serial jitter is
              excluded. A row marked * had unusable node timestamps and fell
              back to the host clock.
  csi_len     modal CSI payload length for this MAC (beacons run 256; see
              node_census.py BEACON_MIN_LEN256)
  off-len     frames whose payload length differed from that mode
  ch          Wi-Fi channel(s) those frames arrived on

An expected beacon that produced nothing gets a row of zeros marked MISSING.
A row is never omitted because it was empty: no row at all means the MAC was
never in the expected set and never transmitted.

What this tool deliberately does not report
-------------------------------------------
Per-beacon lost-frame counts. `seq` is not a per-transmitter sequence
number: firmware/csi_rx/main/main.c stamps every CSI frame with
`s_latest_seq`, a single global updated by the ESP-NOW receive callback from
whichever beacon most recently transmitted. With more than one beacon on
air, seq gaps grouped by MAC measure nothing. Frame loss is therefore
reported once, at receiver level, from the node's own cumulative queue-drop
counter (`dropped`, v2 firmware only).

Exit codes - a scripting convenience, not a health grade
--------------------------------------------------------
  0  the window completed, every expected beacon was seen, no unknown MAC
     appeared, and no rate outlier tripped the stated rule. That is the
     whole claim; it is not a statement that the array is good.
  1  no telemetry at all, or the port could not be opened
  2  the window completed, and SUMMARY lists at least one finding
  3  the window did not complete: operator stop, serial error, or a receiver
     stall longer than --silence
"""
import argparse
import collections
import os
import statistics
import sys
import time

try:
    import serial
except ImportError:
    serial = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rff.protocol import (decode_stream, unwrap_ts, CAL_STATES,   # noqa: E402
                          RESET_REASONS, HDR_V1, HDR_V2)
from rff.serialio import open_serial                              # noqa: E402
from occ import BEACON_MACS                                       # noqa: E402
# node_census.py is import-safe (everything is behind its __main__ guard);
# borrowing the constant keeps one definition of "this is beacon cadence".
from node_census import BEACON_MIN_FPS                            # noqa: E402

# MACs we have already characterized as not-ours, so an operator does not
# spend the pre-capture minute chasing one. Still printed, never filtered.
KNOWN_AMBIENT = {
    "84:7b:57:cc:20:0e": "known ambient third-party device "
                         "(docs/TWIN_INVESTIGATION.md)",
}

# A beacon whose first frame lands this far into the window is called out
# rather than left to look slow in the fps column.
LATE_START_S = 5.0

# Rate-outlier rule, stated in the output so the number is never mysterious.
OUTLIER_FRACTION = 0.5


class Source:
    """Per-transmitter accumulator. One instance per MAC actually heard,
    plus one per expected MAC so a silent beacon still gets a row."""

    def __init__(self, mac, name="", expected=False):
        self.mac = mac
        self.name = name
        self.expected = expected
        self.n = 0
        self.rssi = []
        self.lens = collections.Counter()
        self.channels = set()
        self.t_first_host = None
        self.t_last_host = None
        self.host_max_gap = 0.0
        self._prev_ts = None
        self._prev_unwrapped = None
        self.ts_span_us = 0
        self.ts_max_gap_us = 0
        self.ts_backwards = 0

    def feed(self, rec, now):
        self.n += 1
        self.rssi.append(rec["rssi"])
        self.lens[rec["len"]] += 1
        self.channels.add(rec["channel"])
        if self.t_first_host is None:
            self.t_first_host = now
        elif now - self.t_last_host > self.host_max_gap:
            self.host_max_gap = now - self.t_last_host
        self.t_last_host = now

        u = unwrap_ts(rec["ts"], self._prev_ts, self._prev_unwrapped)
        if self._prev_unwrapped is not None:
            d = u - self._prev_unwrapped
            if d < 0:
                self.ts_backwards += 1
            else:
                self.ts_span_us += d
                if d > self.ts_max_gap_us:
                    self.ts_max_gap_us = d
        self._prev_ts = rec["ts"]
        self._prev_unwrapped = u

    @property
    def ts_usable(self):
        """Node timestamps are trusted only if they advanced and did so
        monotonically. Otherwise the gap column falls back to host time."""
        return (self.n > 1 and self.ts_span_us > 0
                and self.ts_backwards <= max(1, self.n // 100))

    def max_gap_ms(self):
        """(milliseconds, fell_back_to_host)"""
        if self.n < 2:
            return None, False
        if self.ts_usable:
            return self.ts_max_gap_us / 1000.0, False
        return self.host_max_gap * 1000.0, True

    def modal_len(self):
        return self.lens.most_common(1)[0][0] if self.lens else None

    def off_len(self):
        m = self.modal_len()
        return sum(c for L, c in self.lens.items() if L != m)


class Run:
    """Everything the listen window observed, including how it ended."""

    def __init__(self, port, baud, requested):
        self.port = port
        self.baud = baud
        self.requested = requested
        self.sources = {}
        self.order = []
        self.total_csi = 0
        self.total_status = 0
        self.t_open = None
        self.t_first_byte = None
        self.t_end = None
        self.ended = "completed"         # completed | operator | serial | stall
        self.error = ""
        self.stalls = []                 # (seconds_into_window, duration_s)
        self.last_status = None
        self.drop_first = None
        self.drop_last = None
        self.saw_v1 = False
        self.unaccounted_bytes = 0
        self.unaccounted_blind_batches = 0

    @property
    def span(self):
        if self.t_first_byte is None or self.t_end is None:
            return 0.0
        return max(0.0, self.t_end - self.t_first_byte)

    def source(self, mac, name="", expected=False):
        s = self.sources.get(mac)
        if s is None:
            s = Source(mac, name, expected)
            self.sources[mac] = s
            self.order.append(mac)
        return s


def frame_bytes(rec):
    """On-wire size of a decoded CSI record, or None if not derivable.

    Used only to total the bytes decode_stream() consumed that did not
    become a frame. STATUS records carry no payload length on the record,
    so any decode batch containing one is skipped rather than guessed at.
    """
    if rec["type"] != "csi":
        return None
    if rec["node_id"] is None:                    # v1 frame
        return HDR_V1 + rec["len"] + 1
    return HDR_V2 + (rec["len"] + 15) + 1         # v2 CSI payload prefix = 15


def parse_expect(spec):
    """--expect MAC[=NAME][,MAC[=NAME]...]; empty string means expect none."""
    if spec is None:
        return dict(BEACON_MACS)
    out = {}
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        mac, _, name = tok.partition("=")
        mac = mac.strip().lower()
        out[mac] = name.strip() or BEACON_MACS.get(mac, "?")
    return out


def listen(run, expect, silence, tick=0.5):
    try:
        ser = open_serial(run.port, run.baud)
    except Exception as e:                        # noqa: BLE001 - reported
        run.ended = "serial"
        run.error = f"could not open {run.port}: {e}"
        run.t_open = run.t_end = time.time()
        return run

    run.t_open = time.time()
    deadline = (run.t_open + run.requested) if run.requested > 0 else None
    buf = bytearray()
    last_byte_at = run.t_open
    last_tick = 0.0
    in_stall = False
    unknown_seen = set()
    cal_note = "no STATUS yet"

    try:
        while deadline is None or time.time() < deadline:
            try:
                chunk = ser.read(8192)
            except Exception as e:                # noqa: BLE001 - reported
                run.ended = "serial"
                run.error = f"read failed: {e}"
                break

            now = time.time()
            if chunk:
                if in_stall:                       # close the open stall
                    run.stalls[-1] = (run.stalls[-1][0], now - last_byte_at)
                    in_stall = False
                if run.t_first_byte is None:
                    run.t_first_byte = now
                last_byte_at = now

                buf.extend(chunk)
                before = len(buf)
                recs = decode_stream(buf)
                consumed = before - len(buf)
                accounted = 0
                blind = False
                for rec in recs:
                    fb = frame_bytes(rec)
                    if fb is None:
                        blind = True
                    else:
                        accounted += fb
                    if rec["type"] == "status":
                        run.total_status += 1
                        run.last_status = rec
                        cal = CAL_STATES.get(rec["cal_state"], "?")
                        cal_note = "cal:" + cal
                        if rec["cal_state"] == 0:
                            cal_note += f" {rec['cal_remaining_s']}s"
                        continue

                    run.total_csi += 1
                    if rec["node_id"] is None:
                        run.saw_v1 = True
                    if rec["dropped"] is not None:
                        if run.drop_first is None:
                            run.drop_first = rec["dropped"]
                        run.drop_last = rec["dropped"]

                    mac = rec["mac"].lower()
                    if mac in expect:
                        s = run.source(mac, expect[mac], True)
                    else:
                        s = run.source(mac, "", False)
                        unknown_seen.add(mac)
                    s.feed(rec, now)

                if blind:
                    run.unaccounted_blind_batches += 1
                elif consumed > accounted:
                    run.unaccounted_bytes += consumed - accounted
            elif run.t_first_byte is not None:
                # Silence only counts as a stall once the receiver has
                # spoken at least once; "never said anything" is a different
                # finding and is reported by print_integrity.
                quiet = now - last_byte_at
                if quiet > silence:
                    if in_stall:
                        run.stalls[-1] = (run.stalls[-1][0], quiet)
                    else:
                        in_stall = True
                        run.stalls.append((last_byte_at - run.t_open, quiet))

            if now - last_tick >= tick:
                last_tick = now
                el = int(now - run.t_open)
                counts = " ".join(
                    f"{expect[m]}:{run.sources[m].n if m in run.sources else 0:,}"
                    for m in expect)
                extra = f"  +{len(unknown_seen)} unknown" if unknown_seen else ""
                sys.stdout.write(
                    f"\r  listening {el // 60:02d}:{el % 60:02d}  "
                    f"{run.total_csi:,} fr  {counts}{extra}  {cal_note}"
                    "          ")
                sys.stdout.flush()
    except KeyboardInterrupt:
        run.ended = "operator"

    run.t_end = time.time()
    try:
        ser.close()
    except Exception:                             # noqa: BLE001
        pass
    sys.stdout.write("\n")
    sys.stdout.flush()
    return run


def fmt_uptime(s):
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def print_integrity(run):
    print(f"=== PRE-CAPTURE DIAGNOSTIC - {run.port} @ {run.baud} ===")
    req = f"{run.requested:g} s" if run.requested > 0 else "open-ended"
    print(f"requested window : {req}")

    if run.ended == "serial":
        print(f"RUN INCOMPLETE   : {run.error}")
    elif run.ended == "operator":
        print("RUN INCOMPLETE   : stopped by operator (ctrl-c) before the "
              "window ended")
    elif run.stalls:
        print("RUN INCOMPLETE   : the receiver went silent during the window "
              "(see below)")
    else:
        print("window           : ran to completion")

    if run.t_first_byte is None:
        print("elapsed          : no bytes ever arrived on this port")
    else:
        print(f"elapsed          : {run.span:.1f} s of serial traffic "
              f"(first byte {run.t_first_byte - run.t_open:.1f} s after open)")

    if run.stalls:
        longest = max(d for _, d in run.stalls)
        print(f"receiver stalls  : {len(run.stalls)}, longest {longest:.1f} s")
        for at, dur in run.stalls[:5]:
            print(f"                   - {dur:.1f} s of silence starting "
                  f"{at:.1f} s into the window")
        if len(run.stalls) > 5:
            print(f"                   - ... {len(run.stalls) - 5} more")

    st = run.last_status
    if st:
        cal = CAL_STATES.get(st["cal_state"], str(st["cal_state"]))
        if st["cal_state"] == 0:
            cal += f" ({st['cal_remaining_s']} s remaining)"
        print(f"receiver         : node_id {st['node_id']}  env_id "
              f"{st['env_id']}  fw v{st['fw']}  uptime "
              f"{fmt_uptime(st['uptime_s'])}")
        print(f"last reset       : "
              f"{RESET_REASONS.get(st['reset_reason'], st['reset_reason'])}"
              f"   crashes {st['crash_count']}   cal {cal}")
    elif run.t_first_byte is not None:
        print("receiver         : no STATUS frame in this window "
              "(v1 firmware, or window shorter than the STATUS period)")
    print()


def print_table(run, expect):
    rows = []
    for mac in expect:
        rows.append(run.sources.get(mac) or Source(mac, expect[mac], True))
    unknown = [run.sources[m] for m in run.order
               if not run.sources[m].expected]
    unknown.sort(key=lambda s: -s.n)
    rows.extend(unknown)

    span = run.span
    hdr = (f"{'name':<5} {'mac':<18} {'frames':>8} {'fps':>7} "
           f"{'rssi med':>9} {'min':>5} {'max':>5} {'maxgap_ms':>10} "
           f"{'csi_len':>8} {'off-len':>8}  {'ch':<8} note")
    print(hdr)
    print("-" * len(hdr))

    footnote_host = False
    for s in rows:
        name = s.name or ("?" if not s.expected else "")
        if s.n == 0:
            note = "MISSING - expected, zero frames received"
            print(f"{name:<5} {s.mac:<18} {0:>8} {'0.00':>7} "
                  f"{'-':>9} {'-':>5} {'-':>5} {'-':>10} "
                  f"{'-':>8} {'-':>8}  {'-':<8} {note}")
            continue

        fps = s.n / span if span > 0 else 0.0
        gap, host_fb = s.max_gap_ms()
        if host_fb:
            footnote_host = True
        gap_s = "-" if gap is None else f"{gap:.1f}{'*' if host_fb else ''}"
        chans = ",".join(str(c) for c in sorted(s.channels))
        note = ""
        if not s.expected:
            note = "UNEXPECTED - " + KNOWN_AMBIENT.get(
                s.mac, "not in the expected set")
        print(f"{name:<5} {s.mac:<18} {s.n:>8,} {fps:>7.2f} "
              f"{statistics.median(s.rssi):>9.1f} {min(s.rssi):>5} "
              f"{max(s.rssi):>5} {gap_s:>10} "
              f"{s.modal_len():>8} {s.off_len():>8}  {chans:<8} {note}")

    print()
    if footnote_host:
        print("  * node boot_ts_us was unusable for this source; maxgap_ms "
              "came from the host clock and includes serial jitter.")
    print("  A row of zeros means the beacon was expected and stayed silent. "
          "No row at all means")
    print("  the MAC was neither expected nor heard.")
    print()


def print_summary(run, expect):
    findings = []
    span = run.span
    print("=== SUMMARY ===")
    print(f"total CSI frames   : {run.total_csi:,}   "
          f"STATUS frames: {run.total_status}")
    req = (f"requested {run.requested:g} s" if run.requested > 0
           else "open-ended")
    print(f"window elapsed     : {span:.1f} s ({req})")

    seen = [m for m in expect if m in run.sources and run.sources[m].n > 0]
    missing = [m for m in expect if m not in seen]
    print(f"expected beacons   : {len(expect)} expected, {len(seen)} seen")
    if missing:
        for m in missing:
            print(f"  MISSING          : {expect[m]}  {m}  - zero frames")
        findings.append(f"{len(missing)} expected beacon(s) produced nothing")
    elif expect:
        print("  all expected beacons produced frames")

    unknown = [run.sources[m] for m in run.order
               if not run.sources[m].expected and run.sources[m].n > 0]
    if unknown:
        unknown.sort(key=lambda s: -s.n)
        print(f"unexpected MACs    : {len(unknown)}")
        for s in unknown:
            tag = KNOWN_AMBIENT.get(s.mac, "unknown transmitter")
            print(f"  {s.mac}  {s.n:>7,} frames  - {tag}")
        findings.append(f"{len(unknown)} MAC(s) outside the expected set")
    else:
        print("unexpected MACs    : none")

    live = [run.sources[m] for m in seen]
    if live and span > 0:
        # Absolute check first: it needs no peers and its threshold has a
        # source, so it still works when only one beacon is on air.
        slow = [s for s in live if s.n / span < BEACON_MIN_FPS]
        print(f"cadence floor      : {BEACON_MIN_FPS:g} fps "
              "(node_census.BEACON_MIN_FPS, per docs/LOT_HYPOTHESIS.md s.3)")
        for s in slow:
            print(f"  BELOW FLOOR      : {s.name} {s.mac}  "
                  f"{s.n / span:.2f}/s")
            findings.append(f"{s.name or s.mac} is below the cadence floor")
        if not slow:
            print("  every beacon seen is above it")

    if len(live) >= 2 and span > 0:
        med = statistics.median(s.n / span for s in live)
        thresh = OUTLIER_FRACTION * med
        print(f"rate outlier rule  : fps < {OUTLIER_FRACTION:g} x median fps "
              f"of the {len(live)} beacon(s) seen "
              f"(median {med:.2f}/s, threshold {thresh:.2f}/s)")
        low = []
        for s in sorted(live, key=lambda x: x.n):
            r = s.n / span
            ratio = r / med if med > 0 else 0.0
            mark = "  <-- LOW" if r < thresh else ""
            print(f"    {s.name or s.mac:<5} {r:8.2f}/s  "
                  f"{ratio:5.2f}x median{mark}")
            if r < thresh:
                low.append(s)
                findings.append(f"{s.name or s.mac} rate is a low outlier")
        if not low:
            print("  no beacon fell below the threshold - the ratios above "
                  "are printed anyway, so a")
            print("  beacon sitting just over the line is still visible.")
        if len(live) == 2:
            print("  (two sources only - the median is their mean; treat "
                  "this rule as weak here)")
    elif live:
        print("rate outlier rule  : not applied - fewer than two beacons "
              "were seen, so there is nothing")
        print("                     to compare against. The cadence floor "
              "above still applies.")

    late = [s for s in live
            if run.t_first_byte is not None
            and s.t_first_host - run.t_first_byte > LATE_START_S]
    for s in late:
        print(f"  LATE START       : {s.name} {s.mac} first heard "
              f"{s.t_first_host - run.t_first_byte:.1f} s into the window; "
              "its fps is diluted by the shared denominator")
        findings.append(f"{s.name or s.mac} started "
                        f"{s.t_first_host - run.t_first_byte:.0f} s late")

    print()
    print("frame loss (receiver level, not per beacon):")
    if run.drop_first is not None and run.drop_last is not None:
        d = (run.drop_last - run.drop_first) & 0xFFFF
        print(f"  queue drops      : {d} sample(s) dropped by the node's CSI "
              "queue during the window")
        if d:
            findings.append(f"{d} node-side queue drop(s)")
    elif run.saw_v1:
        print("  queue drops      : not reported by v1 firmware")
    else:
        print("  queue drops      : no CSI frame carried the counter")
    if run.unaccounted_blind_batches and not run.unaccounted_bytes:
        print("  decoder resync   : not measured - every decode batch in this "
              "run contained a STATUS frame, whose on-wire length the record "
              "does not carry")
    else:
        print(f"  decoder resync   : {run.unaccounted_bytes:,} serial byte(s) "
              "consumed without becoming a frame (checksum rejects, noise, "
              "truncation)")
        if run.unaccounted_blind_batches:
            print(f"                     {run.unaccounted_blind_batches} "
                  "batch(es) excluded from that total because they contained "
                  "a STATUS frame")
        if run.unaccounted_bytes:
            findings.append(f"{run.unaccounted_bytes:,} unaccounted serial "
                            "byte(s)")
    print("  per-beacon RF loss is NOT measurable here: seq is a node-global "
          "(firmware/csi_rx/main/main.c,")
    print("  s_latest_seq), so seq gaps grouped by MAC mean nothing with more "
          "than one beacon on air.")

    print()
    print("This tool checked presence, rate, RSSI, continuity and payload "
          "length, and nothing else.")
    print("It did not check CFO/SFO separability, channel occupancy, or that "
          "a beacon is the unit you")
    print("think it is - a MAC is not an identity. No overall verdict is "
          "printed on purpose.")
    return findings


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", help="collector COM port (e.g. COM3)")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--seconds", type=float, default=60.0,
                    help="listen window; 0 means run until ctrl-c "
                         "(default 60)")
    ap.add_argument("--expect", default=None,
                    help="comma-separated MAC[=NAME] list of beacons that "
                         "should be on air. Default: occ.BEACON_MACS "
                         f"({', '.join(BEACON_MACS.values())}). Pass an "
                         "empty string to expect none.")
    ap.add_argument("--silence", type=float, default=8.0,
                    help="seconds of serial silence that counts as a "
                         "receiver stall (default 8, above the ~6 s STATUS "
                         "cadence)")
    args = ap.parse_args()

    if serial is None:
        print("pyserial not installed: pip install pyserial", file=sys.stderr)
        return 1

    expect = parse_expect(args.expect)
    req = f"{args.seconds:g} s" if args.seconds > 0 else "until ctrl-c"
    print(f"diagnose: {args.port} @ {args.baud}, {req}, expecting "
          f"{len(expect)} beacon(s): "
          f"{', '.join(f'{n} {m}' for m, n in expect.items()) or '(none)'}")
    print("  ctrl-c stops early; the report will say that it did.\n")

    run = Run(args.port, args.baud, max(0.0, args.seconds))
    listen(run, expect, args.silence)

    print_integrity(run)
    if run.total_csi == 0 and run.total_status == 0:
        print("no telemetry received. Check the baud (460800 default), the "
              "cable, whether another")
        print("program holds the port, or whether the node is in safe-boot. "
              "If STATUS frames are")
        print("absent too, the problem is the link to the receiver, not the "
              "beacons.")
        return 1

    print_table(run, expect)
    findings = print_summary(run, expect)

    if run.ended in ("serial", "operator") or run.stalls:
        return 3
    return 2 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
