#!/usr/bin/env python3
r"""throughput_test - how fast can the S3 push bytes to this PC over native USB?

Host side of `firmware/s3_throughput`. It answers one question and refuses
to answer any other: what is the SUSTAINED device->host byte rate of the
ESP32-S3's built-in USB-Serial-JTAG peripheral, with records shaped like a
real CSI frame (256-byte payload). The last section converts that into CSI
frames per second so the answer is in the units the decision needs.

It does NOT show that the S3 can capture CSI at that rate. This test never
turns the radio on. The S3's WiFi path is a separate open question
(docs/HANDOFF.md).

Read-only. Writes no file and touches nothing in data/, pc/rff/, pc/occ/,
firmware/ or site/.

Usage
-----
  python pc\throughput_test.py COM7
  python pc\throughput_test.py COM7 --seconds 120
  python pc\throughput_test.py COM7 --seconds 0            # until ctrl-c
  python pc\throughput_test.py COM7 --needed-fps 140 --today-bps 46080

Baud
----
There is no baud rate on this link. USB-Serial-JTAG is a USB CDC endpoint;
whatever number the host writes into the baud field is discarded by the
device. --baud exists only so the call site looks like diagnose.py's, and
its value cannot change the measurement. The port is still opened through
`rff.serialio.open_serial`, which leaves DTR/RTS deasserted - on the S3
those two lines are how esptool asks the USB-Serial-JTAG peripheral to
reset the chip into download mode, so a plain pyserial open can reboot the
board mid-run.

What is measured, and how
-------------------------
  sustained B/s   total bytes received divided by the seconds of serial
                  traffic. Every byte counts, including bytes that did not
                  become a record - a link that delivers garbage fast is
                  not delivering.
  trend           bytes per whole second, so a link that starts fast and
                  degrades cannot hide inside a mean. The trailing partial
                  second is excluded from the mean and said to be excluded.
  gaps            DATA records carry a u32 sequence number. A jump is data
                  the host never saw. Reported as records missing and as
                  the number of separate gap events, never averaged away.
  checksum fails  bytes that framed like a record but did not verify.
  resync bytes    bytes consumed that never became a record at all: boot
                  banner text, corruption, truncation. Same accounting
                  diagnose.py uses for the receiver link.
  device side     STATUS records carry the device's own attempted-vs-
                  accepted write counters, which is what separates "the
                  USB link is the ceiling" from "the firmware was slow".

What this tool deliberately does not report
-------------------------------------------
Latency, and any per-record timing distribution. The device stamps each
record with boot_ts_us, but the blast loop is backpressured by USB by
design, so those stamps measure when the driver had room, not when the
byte reached the host. Quoting them as latency would be a fiction.

Exit codes - a scripting convenience, not a health grade
--------------------------------------------------------
  0  the window ran to completion with no gaps, no checksum failures, no
     stalls, and no device-side completion timeouts. That is the whole
     claim.
  1  no data at all, or the port could not be opened
  2  the window completed and SUMMARY lists at least one finding
  3  the window did not complete: operator stop, serial error, or a link
     stall longer than --silence
"""
import argparse
import os
import statistics
import struct
import sys
import time

try:
    import serial
except ImportError:
    serial = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rff import protocol                                          # noqa: E402
from rff.serialio import open_serial                              # noqa: E402

# ---------------------------------------------------------------- protocol
# Mirrors firmware/s3_throughput/main/main.c. Magic C5 54 is distinct from
# the array's C5 51 (v1) and C5 52 (v2) telemetry, so this stream can never
# be confused with a capture.
MAGIC = b"\xc5\x54"
HDR = 12
PAYLOAD = 256
REC = HDR + PAYLOAD + 1                     # 269
TYPE_DATA = 1
TYPE_STATUS = 2
FW_EXPECTED = 1

# STATUS payload prefix; the rest of the 256 bytes is zero padding.
_STATUS_FMT = "<6I2Q5I"                     # 60 bytes
_STATUS_LEN = struct.calcsize(_STATUS_FMT)
_STATUS_FIELDS = ("uptime_ms", "data_seq", "attempted", "accepted_first_try",
                  "would_block", "partial", "bytes_committed", "block_us",
                  "completion_timeouts", "heap_free", "status_seq",
                  "tx_ring_bytes", "cpu_mhz")

SEQ_WRAP = 1 << 32

# payload[i] = (seq + 7*i) & 0xFF, so it depends on seq only through the low
# byte. Precomputing all 256 possibilities turns per-record verification into
# one C-level bytes compare instead of a 256-step Python loop; without it the
# host becomes the bottleneck and the tool measures itself.
_EXP_PAYLOAD = []
_EXP_XOR = []
for _s in range(256):
    _p = bytes((_s + 7 * _i) & 0xFF for _i in range(PAYLOAD))
    _x = 0
    for _b in _p:
        _x ^= _b
    _EXP_PAYLOAD.append(_p)
    _EXP_XOR.append(_x)

# ------------------------------------------------------------- conversions
# The one figure here that comes from a repo file rather than from the
# operator. It is now DERIVED from pc/rff/protocol.py rather than restated:
# a literal `12 + 15 + 256 + 1` here was a third copy of a layout defined in
# two other places, and it silently assumed every frame carries 256 CSI
# bytes. The parser accepts 128 and 384 too (CSI_MAX + 15), and while the
# three beacons are 100% len-256 (docs/NODE_CENSUS.md 2), ambient sources
# are not — so the assumption is wrong for exactly the population the
# ambient work cares about. docs/V2_READY.md 1.5.
DEFAULT_CSI_LEN = 256                       # beacon traffic; override below
CSI_FRAME_BYTES = protocol.frame_bytes(DEFAULT_CSI_LEN)      # 284

# These two are OPERATOR-SUPPLIED for this session and are not read out of
# any repo artifact. They are CLI-overridable and are labelled as such
# everywhere they are printed.
DEFAULT_TODAY_BPS = 46080                   # 460800 baud, 8N1 = 10 bits/byte
DEFAULT_NEEDED_FPS = 140.0                  # 3 beacons combined

# Trend rule, stated in the output so the call is never mysterious.
TREND_DEGRADE = 0.90
TREND_IMPROVE = 1.10
SAG_FRACTION = 0.5
MIN_TREND_BUCKETS = 6


class Decoder:
    """Fixed-size record decoder with explicit resync accounting.

    Records are all REC bytes, so once locked the decoder simply steps.
    A byte that does not fit that lock is counted, never quietly skipped.
    """

    def __init__(self):
        self.resync_bytes = 0
        self.checksum_fail = 0
        self.pattern_fail = 0
        self.bad_type = 0
        self.fw_seen = set()

    def feed(self, buf, out):
        """Consume whole records from bytearray `buf` into list `out`.

        Leaves any partial tail in buf. Returns nothing; counters update
        in place.
        """
        n = len(buf)
        if n < REC:
            return
        mv = memoryview(buf)
        j = 0
        try:
            while j + REC <= n:
                if mv[j] != 0xC5 or mv[j + 1] != 0x54:
                    k = buf.find(MAGIC, j + 1)
                    if k < 0:
                        # Nothing framable left. Keep one trailing byte in
                        # case a magic straddles the chunk boundary.
                        self.resync_bytes += max(0, n - j - 1)
                        j = max(j, n - 1)
                        break
                    self.resync_bytes += k - j
                    j = k
                    continue

                rec = self._parse(mv, j)
                if rec is None:
                    self.resync_bytes += 1
                    j += 1
                    continue
                out.append(rec)
                j += REC
        finally:
            mv.release()
        if j:
            del buf[:j]

    def _parse(self, mv, j):
        typ = mv[j + 2]
        if typ != TYPE_DATA and typ != TYPE_STATUS:
            self.bad_type += 1
            return None
        fw = mv[j + 3]
        seq = int.from_bytes(mv[j + 4:j + 8], "little")
        pay = mv[j + HDR:j + HDR + PAYLOAD]

        pattern_ok = True
        if typ == TYPE_DATA:
            exp = _EXP_PAYLOAD[seq & 0xFF]
            if pay == exp:
                pay_x = _EXP_XOR[seq & 0xFF]
            else:
                pattern_ok = False
                pay_x = 0
                for b in pay:
                    pay_x ^= b
        else:
            pay_x = 0
            for b in pay:
                pay_x ^= b

        cks = pay_x
        for i in range(j + 2, j + HDR):
            cks ^= mv[i]
        if cks != mv[j + HDR + PAYLOAD]:
            self.checksum_fail += 1
            return None

        # Checksum passed, so the bytes on the wire are intact. A pattern
        # miss here is therefore a firmware/host disagreement about the
        # generator, not link corruption - a different finding entirely.
        if not pattern_ok:
            self.pattern_fail += 1
        self.fw_seen.add(fw)

        rec = {
            "type": typ,
            "fw": fw,
            "seq": seq,
            "ts": int.from_bytes(mv[j + 8:j + 12], "little"),
        }
        if typ == TYPE_STATUS:
            vals = struct.unpack(_STATUS_FMT, bytes(pay[:_STATUS_LEN]))
            rec.update(dict(zip(_STATUS_FIELDS, vals)))
        return rec


class Run:
    """Everything the listen window observed, including how it ended."""

    def __init__(self, port, baud, requested):
        self.port = port
        self.baud = baud
        self.requested = requested
        self.dec = Decoder()

        self.t_open = None
        self.t_first_byte = None
        self.t_end = None
        self.ended = "completed"          # completed | operator | serial | stall
        self.error = ""
        self.stalls = []                  # (seconds_into_window, duration_s)

        self.bytes_total = 0
        self.data_recs = 0
        self.status_recs = 0

        self.prev_seq = None
        self.missing = 0                  # DATA records the host never saw
        self.gap_events = []              # (after_seq, missing_count)
        self.seq_backwards = 0            # device restart, or worse

        self.buckets = {}                 # second index -> [bytes, data_recs]
        self.first_status = None
        self.last_status = None
        self.max_in_waiting = 0
        self.rx_buffer_set = None         # True/False/None (not attempted)

    @property
    def span(self):
        if self.t_first_byte is None or self.t_end is None:
            return 0.0
        return max(0.0, self.t_end - self.t_first_byte)

    def full_buckets(self):
        """[(index, bytes, data_recs)] for whole seconds only.

        The trailing partial second is excluded here and said to be
        excluded wherever this is used. Its bytes still count in the total.
        """
        n_full = int(self.span)
        return [(i, self.buckets[i][0], self.buckets[i][1])
                for i in range(n_full) if i in self.buckets]

    def note_status(self, rec, host_bytes):
        entry = (rec, host_bytes)
        if self.first_status is None:
            self.first_status = entry
        self.last_status = entry


def listen(run, silence, tick=0.5):
    try:
        ser = open_serial(run.port, run.baud, timeout=0.05)
    except Exception as e:                            # noqa: BLE001 - reported
        run.ended = "serial"
        run.error = f"could not open {run.port}: {e}"
        run.t_open = run.t_end = time.time()
        return run

    # A small OS receive buffer shows up as gaps that look like link loss.
    # Windows-only API; whether it took is reported, never assumed.
    try:
        ser.set_buffer_size(rx_size=1 << 20)
        run.rx_buffer_set = True
    except Exception:                                 # noqa: BLE001
        run.rx_buffer_set = False

    run.t_open = time.time()
    deadline = (run.t_open + run.requested) if run.requested > 0 else None
    buf = bytearray()
    recs = []
    last_byte_at = run.t_open
    last_tick = 0.0
    in_stall = False

    try:
        while deadline is None or time.time() < deadline:
            try:
                waiting = ser.in_waiting
                if waiting > run.max_in_waiting:
                    run.max_in_waiting = waiting
                chunk = ser.read(waiting if waiting else 1)
            except Exception as e:                    # noqa: BLE001 - reported
                run.ended = "serial"
                run.error = f"read failed: {e}"
                break

            now = time.time()
            if chunk:
                if in_stall:
                    run.stalls[-1] = (run.stalls[-1][0], now - last_byte_at)
                    in_stall = False
                if run.t_first_byte is None:
                    run.t_first_byte = now
                last_byte_at = now

                run.bytes_total += len(chunk)
                bucket = run.buckets.setdefault(
                    int(now - run.t_first_byte), [0, 0])
                bucket[0] += len(chunk)

                buf.extend(chunk)
                del recs[:]
                run.dec.feed(buf, recs)
                for rec in recs:
                    if rec["type"] == TYPE_STATUS:
                        run.status_recs += 1
                        run.note_status(rec, run.bytes_total)
                        continue
                    run.data_recs += 1
                    bucket[1] += 1
                    seq = rec["seq"]
                    if run.prev_seq is not None:
                        d = (seq - run.prev_seq) % SEQ_WRAP
                        if d == 0 or d > SEQ_WRAP // 2:
                            run.seq_backwards += 1
                        elif d > 1:
                            run.missing += d - 1
                            run.gap_events.append((run.prev_seq, d - 1))
                    run.prev_seq = seq
            elif run.t_first_byte is not None:
                # Silence counts as a stall only once the device has spoken
                # at least once; "never said anything" is a different
                # finding and print_integrity reports it separately.
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
                el_rx = (now - run.t_first_byte) if run.t_first_byte else 0.0
                rate = run.bytes_total / el_rx if el_rx > 0 else 0.0
                sys.stdout.write(
                    f"\r  reading {el // 60:02d}:{el % 60:02d}  "
                    f"{run.bytes_total:,} B  {rate / 1024:,.1f} KB/s  "
                    f"{run.data_recs:,} rec  gaps {run.missing:,}"
                    "          ")
                sys.stdout.flush()
    except KeyboardInterrupt:
        run.ended = "operator"

    run.t_end = time.time()
    try:
        ser.close()
    except Exception:                                 # noqa: BLE001
        pass
    sys.stdout.write("\n")
    sys.stdout.flush()
    return run


def fmt_uptime(s):
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def slope(points):
    """Least-squares slope of y over x. None if undefined."""
    n = len(points)
    if n < 2:
        return None
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    den = sum((p[0] - mx) ** 2 for p in points)
    if den == 0:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in points) / den


def print_integrity(run):
    print(f"=== S3 USB THROUGHPUT - {run.port} ===")
    req = f"{run.requested:g} s" if run.requested > 0 else "open-ended"
    print(f"requested window : {req}")

    if run.ended == "serial":
        print(f"RUN INCOMPLETE   : {run.error}")
    elif run.ended == "operator":
        print("RUN INCOMPLETE   : stopped by operator (ctrl-c) before the "
              "window ended")
    elif run.stalls:
        print("RUN INCOMPLETE   : the link went silent during the window "
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
        print(f"link stalls      : {len(run.stalls)}, longest {longest:.1f} s")
        for at, dur in run.stalls[:5]:
            print(f"                   - {dur:.1f} s of silence starting "
                  f"{at:.1f} s into the window")
        if len(run.stalls) > 5:
            print(f"                   - ... {len(run.stalls) - 5} more")

    if run.rx_buffer_set is True:
        print("host rx buffer   : raised to 1 MiB (pyserial set_buffer_size)")
    elif run.rx_buffer_set is False:
        print("host rx buffer   : left at the driver default - "
              "set_buffer_size is Windows-only and did not apply here")

    if run.last_status:
        st = run.last_status[0]
        print(f"device           : fw v{st['fw']}  tx_ring "
              f"{st['tx_ring_bytes']:,} B  cpu {st['cpu_mhz']} MHz  uptime "
              f"{fmt_uptime(st['uptime_ms'] // 1000)}  "
              f"heap {st['heap_free']:,} B")
    elif run.t_first_byte is not None:
        print("device           : no STATUS record in this window (window "
              "shorter than the 1 s STATUS period, or the device is stuck "
              "in a blocked write)")
    print(f"record size      : {REC} B on the wire "
          f"({HDR} hdr + {PAYLOAD} payload + 1 xor)")
    print()


def print_rate(run):
    span = run.span
    print("=== SUSTAINED RATE ===")
    print(f"bytes received   : {run.bytes_total:,} B in {span:.1f} s")
    if span <= 0:
        print("sustained        : not computable - no measurable span")
        print()
        return None
    bps = run.bytes_total / span
    print(f"sustained        : {bps:,.0f} B/s = {bps / 1024:,.1f} KB/s "
          "(every byte received, including bytes that never became a record)")
    print(f"records          : {run.data_recs:,} DATA + {run.status_recs:,} "
          f"STATUS  ->  {run.data_recs / span:,.1f} DATA records/s")
    pay_bps = run.data_recs * PAYLOAD / span
    print(f"payload only     : {pay_bps:,.0f} B/s of {PAYLOAD}-byte payloads "
          f"(record overhead {REC - PAYLOAD}/{REC} = "
          f"{100.0 * (REC - PAYLOAD) / REC:.1f}%)")

    if run.last_status and run.first_status:
        a, b = run.first_status[0], run.last_status[0]
        dt_ms = b["uptime_ms"] - a["uptime_ms"]
        dbytes = b["bytes_committed"] - a["bytes_committed"]
        if dt_ms > 0:
            dev_bps = dbytes * 1000.0 / dt_ms
            print(f"device's own clock: {dev_bps:,.0f} B/s over {dt_ms / 1000:.1f} "
                  "s of device uptime - an independent check on the host "
                  "clock above")
    print()
    return bps


def print_trend(run):
    full = run.full_buckets()
    span = run.span
    n_full = len(full)
    trailing = max(0.0, span - int(span))
    print("=== TREND ===")
    print(f"buckets          : {n_full} whole second(s); the trailing "
          f"{trailing:.2f} s is excluded from every figure in this section "
          "but its bytes are in the total above")
    if n_full == 0:
        print("                   too short to say anything about trend")
        print()
        return []

    vals = [b for _, b, _ in full]
    med = statistics.median(vals)
    lo = min(vals)
    hi = max(vals)
    print(f"per-second bytes : min {lo:,}  median {med:,.0f}  max {hi:,}  "
          f"spread {100.0 * (hi - lo) / med if med else 0:.1f}% of median")

    # Bar chart, condensed to at most 30 rows so a long run stays readable.
    groups = min(30, n_full)
    per = n_full / groups
    print(f"shape            : {groups} row(s), each averaging "
          f"{per:.1f} second(s); bar is scaled to the max second")
    for g in range(groups):
        s0 = int(g * per)
        s1 = int((g + 1) * per) if g + 1 < groups else n_full
        seg = vals[s0:s1] or [0]
        v = sum(seg) / len(seg)
        bar = "#" * int(round(40.0 * v / hi)) if hi else ""
        label = f"{s0:>4}" if s1 - s0 <= 1 else f"{s0:>4}-{s1 - 1}"
        print(f"  s{label:<10} {v:>10,.0f} B/s  {bar}")

    findings = []
    if n_full >= MIN_TREND_BUCKETS:
        third = n_full // 3
        first = sum(vals[:third]) / third
        last = sum(vals[-third:]) / third
        ratio = last / first if first else 0.0
        print(f"first third      : {first:,.0f} B/s   "
              f"last third: {last:,.0f} B/s   ratio {ratio:.3f}")
        sl = slope(list(enumerate(vals)))
        if sl is not None:
            print(f"least squares    : {sl:+,.0f} B/s per second of run")
        if ratio < TREND_DEGRADE:
            call = "DEGRADING"
            findings.append(f"throughput degraded: last third is "
                            f"{ratio:.2f}x the first third")
        elif ratio > TREND_IMPROVE:
            call = "IMPROVING"
            findings.append(f"throughput was still ramping: last third is "
                            f"{ratio:.2f}x the first third")
        else:
            call = "STEADY"
        print(f"call             : {call}   (rule: DEGRADING below "
              f"{TREND_DEGRADE:g}x, IMPROVING above {TREND_IMPROVE:g}x, "
              "else STEADY)")
    else:
        print(f"call             : not stated - {n_full} whole second(s) is "
              f"below the {MIN_TREND_BUCKETS} this rule needs. Run "
              "--seconds 30 or more.")

    sag = [i for i, b, _ in full if med and b < SAG_FRACTION * med]
    print(f"sag seconds      : {len(sag)} second(s) below "
          f"{SAG_FRACTION:g}x the median second")
    if sag:
        shown = ", ".join(f"s{i}" for i in sag[:10])
        more = f" ... +{len(sag) - 10} more" if len(sag) > 10 else ""
        print(f"                   at {shown}{more}")
        findings.append(f"{len(sag)} second(s) fell below "
                        f"{SAG_FRACTION:g}x the median")
    print()
    return findings


def print_stream_integrity(run):
    d = run.dec
    findings = []
    print("=== STREAM INTEGRITY ===")
    expected = run.data_recs + run.missing
    print(f"DATA records     : {run.data_recs:,} received, {expected:,} "
          "expected from the sequence numbers "
          "(received + missing; the device's own count is under DEVICE SIDE)")
    if run.missing:
        pct = 100.0 * run.missing / expected if expected else 0.0
        print(f"  GAPS           : {run.missing:,} record(s) missing across "
              f"{len(run.gap_events):,} gap event(s) = {pct:.4f}% of expected")
        for after, cnt in run.gap_events[:5]:
            print(f"                   - {cnt:,} record(s) missing after "
                  f"seq {after:,}")
        if len(run.gap_events) > 5:
            print(f"                   - ... {len(run.gap_events) - 5} more "
                  "gap event(s)")
        findings.append(f"{run.missing:,} DATA record(s) lost in "
                        f"{len(run.gap_events):,} gap event(s)")
    else:
        print("  gaps           : none - every sequence number was accounted "
              "for")

    if run.seq_backwards:
        print(f"  SEQ BACKWARDS  : {run.seq_backwards:,} time(s). The device "
              "restarted mid-window, or the stream is not what this decoder "
              "thinks it is. Treat the rate above as unreliable.")
        findings.append(f"sequence went backwards {run.seq_backwards} time(s) "
                        "- likely a device restart inside the window")

    if d.checksum_fail:
        print(f"  CHECKSUM FAILS : {d.checksum_fail:,} record-shaped run(s) "
              "of bytes failed the xor")
        findings.append(f"{d.checksum_fail:,} checksum failure(s)")
    else:
        print("  checksum fails : 0")

    if d.pattern_fail:
        print(f"  PATTERN FAILS  : {d.pattern_fail:,} record(s) passed the "
              "checksum but their payload was not (seq + 7*i) & 0xFF. That "
              "is a firmware/host disagreement about the generator, NOT link "
              "corruption - check that both sides are the same version.")
        findings.append(f"{d.pattern_fail:,} payload pattern mismatch(es)")
    else:
        print("  pattern fails  : 0 - every payload matched its sequence "
              "number")

    print(f"  resync bytes   : {d.resync_bytes:,} byte(s) consumed without "
          "becoming a record")
    if d.resync_bytes:
        print("                   Expect a small non-zero count on the first "
              "run after reset: the firmware logs an ASCII banner before it "
              "starts blasting, and those bytes land here.")
        findings.append(f"{d.resync_bytes:,} unaccounted serial byte(s)")
    if d.bad_type:
        print(f"  bad type byte  : {d.bad_type:,} candidate(s) rejected on "
              "the type field")
    if d.fw_seen and d.fw_seen != {FW_EXPECTED}:
        print(f"  FW MISMATCH    : saw fw version(s) {sorted(d.fw_seen)}, "
              f"this host expects v{FW_EXPECTED}")
        findings.append("device firmware version is not the one this host "
                        "was written against")

    print(f"  host backlog   : {run.max_in_waiting:,} B was the most ever "
          "waiting unread in the OS buffer")
    print("                   If that approaches the driver buffer size, the "
          "host - not the link - is the limit, and gaps above may be this "
          "script losing data rather than the S3 failing to send it.")
    print()
    return findings


def print_device_side(run):
    findings = []
    print("=== DEVICE SIDE (from STATUS records) ===")
    if not run.first_status or not run.last_status:
        print("no STATUS record pair in this window, so nothing device-side "
              "can be said.")
        print("Without it this run cannot tell you WHERE the bottleneck is - "
              "only what rate came out.")
        print()
        findings.append("no device-side STATUS pair - bottleneck not located")
        return findings, None

    a, ha = run.first_status
    b, hb = run.last_status
    dt_ms = b["uptime_ms"] - a["uptime_ms"]
    d_att = b["attempted"] - a["attempted"]
    d_acc = b["accepted_first_try"] - a["accepted_first_try"]
    d_blk = b["would_block"] - a["would_block"]
    d_par = b["partial"] - a["partial"]
    d_to = b["completion_timeouts"] - a["completion_timeouts"]
    d_bytes = b["bytes_committed"] - a["bytes_committed"]
    d_block_us = b["block_us"] - a["block_us"]

    print(f"STATUS records   : {run.status_recs:,} received, spanning "
          f"{dt_ms / 1000.0:.1f} s of device uptime")
    print(f"write attempts   : {d_att:,} in that span")

    def pct(x):
        return 100.0 * x / d_att if d_att else 0.0

    print(f"  taken whole, no wait : {d_acc:,} ({pct(d_acc):.1f}%)")
    print(f"  driver took 0 bytes  : {d_blk:,} ({pct(d_blk):.1f}%)")
    print(f"  driver took a partial: {d_par:,} ({pct(d_par):.1f}%)")
    blocked_pct = 100.0 * (d_block_us / 1000.0) / dt_ms if dt_ms else 0.0
    print(f"  time spent waiting   : {d_block_us / 1e6:.1f} s of "
          f"{dt_ms / 1000.0:.1f} s = {blocked_pct:.1f}% of the run")
    if d_to:
        print(f"  COMPLETION TIMEOUTS  : {d_to:,}. The device had already "
              "committed part of a record and the host was not draining. "
              "It kept retrying rather than desync the stream.")
        findings.append(f"{d_to:,} device-side completion timeout(s) - the "
                        "host stopped reading mid-record")

    host_delta = hb - ha
    diff = d_bytes - host_delta
    print(f"bytes committed by device : {d_bytes:,}")
    print(f"bytes received by host    : {host_delta:,}   "
          f"(device minus host: {diff:+,})")
    print("  A small positive difference is expected - bytes still in the USB "
          "pipe when the")
    print("  last STATUS was decoded. A large or negative one means the two "
          "sides disagree and")
    print("  the rate figure should not be trusted.")

    # Where is the bottleneck? State the rule, then apply it.
    print()
    print("bottleneck       : rule - if the device spent most of the run "
          "waiting on the peripheral")
    print("                   and the ring was full on most writes, the "
          "measured rate is a LINK")
    print("                   ceiling. If instead most writes were taken "
          "immediately, the device")
    print("                   was never held back and the rate is a FLOOR, "
          "not a ceiling.")
    link_bound = blocked_pct >= 50.0 and pct(d_acc) <= 50.0
    if link_bound:
        print(f"                   -> LINK-BOUND. Device waited "
              f"{blocked_pct:.1f}% of the run; only {pct(d_acc):.1f}% of "
              "writes were taken")
        print("                      immediately. The number above is the "
              "USB peripheral's ceiling.")
    else:
        print(f"                   -> NOT LINK-BOUND. Device waited only "
              f"{blocked_pct:.1f}% of the run and {pct(d_acc):.1f}% of writes "
              "were taken")
        print("                      immediately, so something other than "
              "USB set the pace: the host")
        print("                      read loop, or the firmware itself. "
              "Treat the rate as a FLOOR.")
        findings.append("the run was not link-bound, so the measured rate is "
                        "a floor and not the USB ceiling")
    print()
    return findings, link_bound


def print_conversion(run, bps, link_bound, today_bps, needed_fps):
    print("=== WHAT THIS MEANS FOR CSI ===")
    print("Converted using the framing this repo already uses: 12 B header + "
          "15 B CSI prefix +")
    print(f"  256 B CSI + 1 B xor = {CSI_FRAME_BYTES} B per frame "
          "(firmware/common/telemetry/include/telemetry.h,")
    print("  pc/rff/protocol.py). Change the framing and these numbers "
          "change with it.")
    print()
    if bps is None:
        print("no measured rate, so no conversion.")
        print()
        return []

    fps = bps / CSI_FRAME_BYTES
    today_fps = today_bps / CSI_FRAME_BYTES
    print(f"measured link    : {bps:>10,.0f} B/s  ->  {fps:>9,.1f} CSI "
          "frames/s")
    print(f"today (UART)     : {today_bps:>10,.0f} B/s  ->  {today_fps:>9,.1f} "
          "CSI frames/s   [OPERATOR-SUPPLIED, not from a repo file]")
    print(f"needed           : {'':>10}       {needed_fps:>9,.1f} CSI "
          "frames/s   [OPERATOR-SUPPLIED: 3 beacons combined]")
    print()
    if today_bps > 0:
        print(f"headroom vs today  : {bps / today_bps:.1f}x the bytes/s the "
              "UART bridge can carry")
    if needed_fps > 0:
        print(f"headroom vs needed : {fps / needed_fps:.1f}x the "
              f"{needed_fps:g} fps requirement "
              f"({fps - needed_fps:,.0f} fps of spare capacity)")
    print()
    if link_bound is False:
        print("CAVEAT: this run was not link-bound (see DEVICE SIDE). The "
              "figures above are a")
        print("        lower bound on what the S3's USB can do, so they can "
              "only be used to argue")
        print("        FOR a port, never against one.")
        print()
    print("What this does NOT say:")
    print("  - that the S3 can CAPTURE CSI at that rate. The radio was never "
          "switched on in this")
    print("    test. The S3's WiFi path has its own open questions "
          "(docs/HANDOFF.md).")
    print("  - anything about the node-side CSI queue, which is a separate "
          "buffer from the USB")
    print("    TX ring measured here.")
    print("  - that USB will behave the same under a real capture load, "
          "where the WiFi task and")
    print("    the CSI callback compete for the same CPU.")
    return []


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", help="S3 USB serial port (e.g. COM7)")
    ap.add_argument("--baud", type=int, default=115200,
                    help="ignored - USB-Serial-JTAG is a USB endpoint and "
                         "has no baud rate. Present only so this call site "
                         "matches the other tools (default 115200)")
    ap.add_argument("--seconds", type=float, default=30.0,
                    help="read window; 0 means run until ctrl-c (default 30)")
    ap.add_argument("--silence", type=float, default=3.0,
                    help="seconds of serial silence that counts as a link "
                         "stall (default 3, well above the 1 s STATUS "
                         "period)")
    ap.add_argument("--today-bps", type=float, default=DEFAULT_TODAY_BPS,
                    help="bytes/s the current UART link carries, for the "
                         "comparison section. Default %(default)g = 460800 "
                         "baud 8N1. OPERATOR-SUPPLIED, not read from a repo "
                         "file")
    ap.add_argument("--needed-fps", type=float, default=DEFAULT_NEEDED_FPS,
                    help="CSI frames/s the array needs, for the comparison "
                         "section (default %(default)g). OPERATOR-SUPPLIED")
    args = ap.parse_args()

    if serial is None:
        print("pyserial not installed: pip install pyserial", file=sys.stderr)
        return 1

    req = f"{args.seconds:g} s" if args.seconds > 0 else "until ctrl-c"
    print(f"throughput_test: {args.port}, {req}")
    print("  baud is not set on this link - USB-Serial-JTAG ignores it.")
    print("  ctrl-c stops early; the report will say that it did.\n")

    run = Run(args.port, args.baud, max(0.0, args.seconds))
    listen(run, args.silence)

    print_integrity(run)
    if run.bytes_total == 0:
        print("no bytes received. Check that the cable is in the S3's USB-C "
              "port (not a UART")
        print("bridge), that no other program holds the port, and that "
              "s3_throughput is actually")
        print("flashed - a board sitting in the ROM bootloader enumerates "
              "but says nothing.")
        return 1

    findings = []
    bps = print_rate(run)
    findings += print_trend(run)
    findings += print_stream_integrity(run)
    dev_findings, link_bound = print_device_side(run)
    findings += dev_findings
    findings += print_conversion(run, bps, link_bound,
                                 args.today_bps, args.needed_fps)

    print()
    print("=== SUMMARY ===")
    if run.ended != "completed" or run.stalls:
        print("The window did NOT run to completion. Everything above "
              "describes a partial run.")
    if findings:
        print(f"{len(findings)} finding(s):")
        for f in findings:
            print(f"  - {f}")
    else:
        print("no findings: the window completed, every sequence number "
              "arrived, every checksum")
        print("passed, and the device reported no write timeouts.")
    print()
    print("This tool measured one thing: device-to-host bytes per second "
          "over USB, with no radio")
    print("running. No overall verdict on the port decision is printed on "
          "purpose.")

    if run.ended in ("serial", "operator") or run.stalls:
        return 3
    return 2 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
