#!/usr/bin/env python3
"""Byte-slice a capture CSV to an absolute time window, without reading it all.

pc_time_us is monotonic in these files (host clock, append order), so the byte
offset of a target timestamp can be found by bisection on file position. Emits
header + the byte range, so the slice is a valid CSV whose OWN origin is the
first row it contains.

Usage: slice_window.py IN OUT ABS_START_S ABS_END_S
Prints the slice's own origin offset so --after/--before can be shifted.
"""
import sys, os

def first_ts_at(f, pos, size):
    """Timestamp of the first complete row at or after byte `pos`."""
    f.seek(pos)
    if pos: f.readline()                 # discard partial line
    while True:
        p = f.tell()
        line = f.readline()
        if not line: return None, size
        if line.startswith(b"pc_time_us"): continue
        head = line.split(b",", 1)[0]
        try: return int(head), p
        except ValueError: continue      # corrupt row, take the next

def find(f, size, target_us, lo, hi):
    """Lowest byte offset whose row timestamp >= target_us."""
    best = hi
    while lo < hi:
        mid = (lo + hi) // 2
        ts, p = first_ts_at(f, mid, size)
        if ts is None or ts >= target_us:
            hi = mid; best = min(best, p if ts is not None else hi)
        else:
            lo = mid + 1
    ts, p = first_ts_at(f, max(lo - 1, 0), size)
    return p if ts is not None and ts >= target_us else lo

def main():
    src, dst, a, b = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
    size = os.path.getsize(src)
    with open(src, "rb") as f:
        header = f.readline()
        assert header.startswith(b"pc_time_us"), header[:40]
        t0, _ = first_ts_at(f, len(header), size)
        s = find(f, size, t0 + int(a * 1e6), len(header), size)
        e = find(f, size, t0 + int(b * 1e6), s, size)
        f.seek(s)
        data = f.read(e - s)
    with open(dst, "wb") as g:
        g.write(header); g.write(data)
        if data and not data.endswith(b"\n"): g.write(b"\n")
    with open(dst, "rb") as g:
        g.readline(); first, _ = first_ts_at(g, len(header), os.path.getsize(dst))
    print(f"{os.path.basename(src)}: bytes {s}..{e} ({(e-s)/1e6:.1f} MB) "
          f"slice_origin_abs={(first - t0)/1e6:.1f}s")

main()
