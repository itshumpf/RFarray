"""Binary serial frame decoder for the CSI array nodes.

Two generations on the wire, distinguished by magic:

v1 (magic C5 51) — original single-type frame:
  C5 51 | seq u32 | mac[6] | rssi i8 | noise i8 | chan u8 |
  tstamp u32 | len u16 | csi[len] i8 | xor u8

v2 (magic C5 52) — field telemetry, typed frames with node metadata:
  C5 52 | type u8 | node_id u8 | env_id u16 | boot_ts_us u32 | len u16 |
  payload[len] | xor u8            (xor covers all bytes after the magic)
  type 1 CSI    payload: seq u32 | mac[6] | rssi i8 | noise i8 | chan u8 |
                         dropped u16 | csi[...]
  type 2 STATUS payload: fw u8 | reset u8 | cal_state u8 | crash u16 |
                         cal_remaining u16 | uptime_s u32 | pkt u32 |
                         drop u32 | heap u32 | noise_cq8 i16 | rssi_cq8 i16

decode_stream() yields dicts; every record has "type" ("csi"|"status").
CSI records share the same keys across v1/v2 (v1 fills node_id/env_id/
dropped with None). boot_ts_us (v2 "ts") wraps every ~71.6 min — the
consumer unwraps (see unwrap_ts).

This is the single source of truth for frame parsing.
"""
import struct

MAGIC_V1 = b"\xc5\x51"
MAGIC_V2 = b"\xc5\x52"
HDR_V1 = 21
HDR_V2 = 12
CSI_MAX = 384

# Bytes of v2 CSI payload that precede the CSI vector itself:
# seq u32 | mac[6] | rssi i8 | noise i8 | chan u8 | dropped u16.
# _try_v2 derives rec["len"] as `length - CSI_PREFIX`; anything computing an
# on-wire size must use the same constant rather than repeating the 15.
CSI_PREFIX = 15


def frame_bytes(csi_len, v2=True):
    """On-wire bytes of one CSI frame carrying `csi_len` CSI bytes.

    Single source of truth for the frame size. It lives here, beside the
    parser that defines the layout, because two host tools previously each
    open-coded it — `pc/throughput_test.py` as a literal `12 + 15 + 256 + 1`
    and `pc/diagnose.py` as `HDR_V2 + (rec["len"] + 15) + 1`. Both are
    arithmetically correct today for a 256-byte frame. Both silently stop
    being correct when a header changes, and `throughput_test.py`'s is
    already wrong for the 128- and 384-byte CSI lengths this parser accepts
    (`CSI_MAX + 15`), which is every ambient source that is not a beacon.
    docs/V2_READY.md 1.5.
    """
    return (HDR_V2 + CSI_PREFIX if v2 else HDR_V1) + csi_len + 1
TYPE_CSI = 1
TYPE_STATUS = 2

_STATUS_FMT = "<BBBHHIIIIhh"          # 27 bytes
_STATUS_LEN = struct.calcsize(_STATUS_FMT)
TS_WRAP_US = 1 << 32

CAL_STATES = {0: "CALIBRATING", 1: "DONE", 2: "BYPASS"}
RESET_REASONS = {0: "UNKNOWN", 1: "POWERON", 3: "SW", 4: "PANIC",
                 5: "INT_WDT", 6: "TASK_WDT", 7: "WDT", 8: "DEEPSLEEP",
                 9: "BROWNOUT", 10: "SDIO", 11: "USB", 12: "JTAG",
                 13: "EFUSE", 14: "PWR_GLITCH", 15: "CPU_LOCKUP"}


def _mac_str(b):
    return ":".join(f"{x:02x}" for x in b)


def _i8(b):
    return b - 256 if b > 127 else b


def _try_v1(buf, j, n):
    """Return (record|None, next_consumed) for a v1 frame at offset j."""
    if j + HDR_V1 + 1 > n:
        return None, j                     # incomplete: wait for more
    length = buf[j + 19] | (buf[j + 20] << 8)
    if length == 0 or length > CSI_MAX:
        return None, j + 1
    total = HDR_V1 + length + 1
    if j + total > n:
        return None, j
    frame = bytes(buf[j:j + total])
    cks = 0
    for b in frame[2:HDR_V1 + length]:
        cks ^= b
    if cks != frame[HDR_V1 + length]:
        return None, j + 1
    rec = {
        "type": "csi",
        "node_id": None,
        "env_id": None,
        "seq": int.from_bytes(frame[2:6], "little"),
        "mac": _mac_str(frame[6:12]),
        "rssi": _i8(frame[12]),
        "noise": _i8(frame[13]),
        "channel": frame[14],
        "ts": int.from_bytes(frame[15:19], "little"),
        "len": length,
        "dropped": None,
        "csi": [_i8(b) for b in frame[HDR_V1:HDR_V1 + length]],
    }
    return rec, j + total


def _try_v2(buf, j, n):
    if j + HDR_V2 + 1 > n:
        return None, j
    ftype = buf[j + 2]
    length = buf[j + 10] | (buf[j + 11] << 8)
    if ftype not in (TYPE_CSI, TYPE_STATUS) or length == 0 \
            or length > CSI_MAX + 15:
        return None, j + 1
    total = HDR_V2 + length + 1
    if j + total > n:
        return None, j
    frame = bytes(buf[j:j + total])
    cks = 0
    for b in frame[2:HDR_V2 + length]:
        cks ^= b
    if cks != frame[HDR_V2 + length]:
        return None, j + 1

    node_id = frame[3]
    env_id = int.from_bytes(frame[4:6], "little")
    boot_ts = int.from_bytes(frame[6:10], "little")
    pl = frame[HDR_V2:HDR_V2 + length]

    if ftype == TYPE_CSI:
        if length < 15:
            return None, j + 1
        rec = {
            "type": "csi",
            "node_id": node_id,
            "env_id": env_id,
            "seq": int.from_bytes(pl[0:4], "little"),
            "mac": _mac_str(pl[4:10]),
            "rssi": _i8(pl[10]),
            "noise": _i8(pl[11]),
            "channel": pl[12],
            "ts": boot_ts,
            "len": length - 15,
            "dropped": int.from_bytes(pl[13:15], "little"),
            "csi": [_i8(b) for b in pl[15:]],
        }
        return rec, j + total

    if length < _STATUS_LEN:
        return None, j + 1
    (fw, reset, cal_state, crash, cal_rem, uptime, pkt, drop, heap,
     noise_cq8, rssi_cq8) = struct.unpack(_STATUS_FMT, pl[:_STATUS_LEN])
    rec = {
        "type": "status",
        "node_id": node_id,
        "env_id": env_id,
        "ts": boot_ts,
        "fw": fw,
        "reset_reason": reset,
        "cal_state": cal_state,
        "crash_count": crash,
        "cal_remaining_s": cal_rem,
        "uptime_s": uptime,
        "pkt_total": pkt,
        "drop_total": drop,
        "heap_free": heap,
        "noise_floor": noise_cq8 / 256.0,
        "rssi_avg": rssi_cq8 / 256.0,
    }
    return rec, j + total


def decode_stream(buf):
    """Consume complete frames from a bytearray, return list of dicts.

    Leaves any trailing partial frame in `buf`. Corrupt frames cost one
    byte of resync.
    """
    out = []
    consumed = 0
    n = len(buf)
    while True:
        j1 = buf.find(MAGIC_V1, consumed)
        j2 = buf.find(MAGIC_V2, consumed)
        if j1 < 0 and j2 < 0:
            consumed = max(consumed, n - 1)
            break
        if j2 < 0 or (0 <= j1 < j2):
            j, parser = j1, _try_v1
        else:
            j, parser = j2, _try_v2
        rec, nxt = parser(buf, j, n)
        if rec is not None:
            out.append(rec)
        if nxt == j:                       # incomplete frame: stop here
            consumed = j
            break
        consumed = nxt
    del buf[:consumed]
    return out


def unwrap_ts(ts, prev_ts, prev_unwrapped):
    """Unwrap a u32 microsecond boot timestamp into a monotonic int."""
    if prev_ts is None:
        return ts
    delta = ts - prev_ts
    if delta < -(TS_WRAP_US // 2):
        delta += TS_WRAP_US
    return prev_unwrapped + delta
