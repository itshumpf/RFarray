#!/usr/bin/env python3
r"""Evidence-based node census over data/raw/ -- who was on air, when, and
in what role.

This is the tool behind every number in docs/NODE_CENSUS.md. It is
read-only: it opens capture CSVs and writes nothing but stdout (and an
optional cache CSV).

It answers three questions the existing tools do not:

  1. census   -- per (file, MAC): frames, wall-clock span, mean RSSI,
                 CSI-buffer-length histogram, channel set. This is the
                 raw material; 910 rows over 62 files as of 2026-08-15.
  2. overlap  -- which capture files were on air AT THE SAME TIME.
                 Simultaneity is the only evidence that separates
                 "two receivers" from "one receiver, two file names",
                 because a single radio cannot produce two independent
                 receptions of the same instant.
  3. roles    -- applies the beacon signature (sustained high frame
                 rate + uniform len-256 frames + bulk presence) that
                 docs/TWIN_INVESTIGATION.md section 4 established, and
                 reports first/last appearance per source.

Why the parsing looks the way it does: csi_data is a quoted field full
of commas, and the files total ~13 GB. Fields 1..9 all precede it, so
each line is truncated to its first 100 characters before splitting.
That is ~50x faster than a real CSV parse and cannot mis-split, because
the truncation point is always inside csi_data.

Two clocks appear in these files and they are not interchangeable:
  * pc_time_us       -- PC wall clock, stamped per serial DRAIN BATCH,
                        not per frame (docs/HANDOFF.md trap #1). Correct
                        for "which files overlap"; WRONG for cadence.
  * esp_timestamp_us -- receiver clock, per frame. Correct for cadence.
`cadence` uses esp_timestamp_us for exactly this reason.

Usage:
  python pc\node_census.py census  "data\raw\*.csv" --cache census_full.csv
  python pc\node_census.py overlap --cache census_full.csv
  python pc\node_census.py roles   --cache census_full.csv
  python pc\node_census.py cadence data\raw\rx_20260714_031131.csv --mac a4:f0:0f:77:91:20
"""
import argparse
import datetime
import glob
import itertools
import os
import statistics
import sys
from collections import defaultdict

PREFIX_CHARS = 100          # fields 1..9 always fit; field 10 is csi_data
BEACON_MIN_FPS = 10.0       # per docs/LOT_HYPOTHESIS.md section 3
BEACON_MIN_FRAMES = 1000
BEACON_MIN_LEN256 = 0.999


def utc(us):
    return datetime.datetime.utcfromtimestamp(us / 1e6).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- census ----

def census_file(path):
    """-> list of dicts, one per (file, MAC)."""
    acc = {}
    with open(path, errors="replace") as fh:
        fh.readline()                                   # header
        for line in fh:
            p = line[:PREFIX_CHARS].split(",")
            if len(p) < 9:
                continue
            mac = p[3]
            if not mac:
                continue
            a = acc.get(mac)
            if a is None:
                a = acc[mac] = dict(n=0, t0=None, t1=None, rs=0.0,
                                    l256=0, lother=0, ch=set())
            try:
                t, rssi, ln = int(p[0]), int(p[4]), int(p[8])
            except ValueError:
                continue
            a["n"] += 1
            a["rs"] += rssi
            if a["t0"] is None or t < a["t0"]:
                a["t0"] = t
            if a["t1"] is None or t > a["t1"]:
                a["t1"] = t
            if ln == 256:
                a["l256"] += 1
            else:
                a["lother"] += 1
            a["ch"].add(p[6])
    base = os.path.basename(path)
    return [dict(file=base, mac=m, n=a["n"], t0=a["t0"], t1=a["t1"],
                 rssi=a["rs"] / a["n"], l256=a["l256"], lother=a["lother"],
                 ch="|".join(sorted(a["ch"])))
            for m, a in acc.items()]


def write_cache(rows, path):
    with open(path, "w") as fh:
        fh.write("file,mac,frames,t0_us,t1_us,mean_rssi,len256,len_other,channels\n")
        for r in rows:
            fh.write("%s,%s,%d,%d,%d,%.2f,%d,%d,%s\n" % (
                r["file"], r["mac"], r["n"], r["t0"], r["t1"],
                r["rssi"], r["l256"], r["lother"], r["ch"]))


def read_cache(path):
    rows = []
    with open(path) as fh:
        fh.readline()
        for line in fh:
            p = line.rstrip("\n").split(",")
            rows.append(dict(file=p[0], mac=p[1], n=int(p[2]), t0=int(p[3]),
                             t1=int(p[4]), rssi=float(p[5]), l256=int(p[6]),
                             lother=int(p[7]), ch=p[8]))
    return rows


def fps(r):
    d = (r["t1"] - r["t0"]) / 1e6
    return r["n"] / d if d > 0 else 0.0


# ------------------------------------------------------------- reporting ----

def cmd_census(args):
    paths = sorted({p for pat in args.csvs for p in glob.glob(pat)})
    paths = [p for p in paths if os.path.getsize(p) > 0]
    print("scanning %d non-empty file(s)..." % len(paths), file=sys.stderr)
    rows = []
    for i, p in enumerate(paths):
        got = census_file(p)
        rows.extend(got)
        print("  [%d/%d] %s: %d MAC(s)" % (i + 1, len(paths),
                                           os.path.basename(p), len(got)),
              file=sys.stderr)
    macs = {r["mac"] for r in rows}
    total = sum(r["n"] for r in rows)
    print("\n%d (file, MAC) rows | %d distinct MACs | %d frames | %d files"
          % (len(rows), len(macs), total, len(paths)))
    if args.cache:
        write_cache(rows, args.cache)
        print("cache -> %s" % args.cache)


def spans(rows):
    """Per-file wall-clock span over all MACs in it."""
    s = {}
    for r in rows:
        a = s.setdefault(r["file"], dict(n=0, t0=r["t0"], t1=r["t1"]))
        a["n"] += r["n"]
        a["t0"] = min(a["t0"], r["t0"])
        a["t1"] = max(a["t1"], r["t1"])
    return s


def cmd_overlap(args):
    rows = read_cache(args.cache)
    s = spans(rows)
    items = sorted(s.items(), key=lambda kv: kv[1]["t0"])

    print("=== capture files in wall-clock order ===")
    print("%-28s %10s  %-19s %-19s %9s %8s" %
          ("file", "frames", "start UTC", "end UTC", "dur_s", "fps"))
    for f, a in items:
        d = (a["t1"] - a["t0"]) / 1e6
        print("%-28s %10d  %-19s %-19s %9.1f %8.1f" %
              (f, a["n"], utc(a["t0"]), utc(a["t1"]), d,
               a["n"] / d if d > 0 else 0))

    print("\n=== SIMULTANEOUS files (spans intersect by more than %.0f s) ==="
          % args.min_overlap)
    print("A single radio cannot produce two independent receptions of the")
    print("same instant, so every row here is two physical receivers.\n")
    ov = []
    for (f1, a1), (f2, a2) in itertools.combinations(items, 2):
        lo, hi = max(a1["t0"], a2["t0"]), min(a1["t1"], a2["t1"])
        if (hi - lo) / 1e6 > args.min_overlap:
            ov.append(((hi - lo) / 6e7, f1, f2, lo, hi, a1["n"], a2["n"]))
    ov.sort(reverse=True)
    print("%11s  %-27s %-27s %10s %10s" %
          ("overlap_min", "file A", "file B", "framesA", "framesB"))
    for d, f1, f2, lo, hi, n1, n2 in ov:
        print("%11.2f  %-27s %-27s %10d %10d" % (d, f1, f2, n1, n2))
    print("\n%d overlapping pair(s)." % len(ov))
    if not ov:
        print("No simultaneity anywhere -> single receiver throughout.")


def cmd_roles(args):
    rows = read_cache(args.cache)
    s = spans(rows)
    order = {f: a["t0"] for f, a in s.items()}

    agg = defaultdict(lambda: dict(n=0, files=0, rs=0.0, l256=0,
                                   t0=None, t1=None, first=None, last=None,
                                   fps=[]))
    for r in rows:
        a = agg[r["mac"]]
        a["n"] += r["n"]
        a["files"] += 1
        a["rs"] += r["rssi"] * r["n"]
        a["l256"] += r["l256"]
        if a["t0"] is None or r["t0"] < a["t0"]:
            a["t0"], a["first"] = r["t0"], r["file"]
        if a["t1"] is None or r["t1"] > a["t1"]:
            a["t1"], a["last"] = r["t1"], r["file"]
        f = fps(r)
        if f:
            a["fps"].append(f)

    print("=== BEACON SIGNATURE FILTER ===")
    print("per file: fps >= %.0f AND frames >= %d AND len-256 > %.1f%%\n"
          % (BEACON_MIN_FPS, BEACON_MIN_FRAMES, 100 * BEACON_MIN_LEN256))
    hits = defaultdict(lambda: dict(files=0, n=0, fps=[], rs=[]))
    for r in rows:
        if (fps(r) >= BEACON_MIN_FPS and r["n"] >= BEACON_MIN_FRAMES
                and r["l256"] / r["n"] > BEACON_MIN_LEN256):
            h = hits[r["mac"]]
            h["files"] += 1
            h["n"] += r["n"]
            h["fps"].append(fps(r))
            h["rs"].append(r["rssi"])
    for m, h in sorted(hits.items(), key=lambda kv: -kv[1]["n"]):
        print("  %-18s files=%-3d frames=%-10d fps %.1f-%.1f  RSSI %.1f..%.1f"
              "  (all files=%d, all frames=%d)"
              % (m, h["files"], h["n"], min(h["fps"]), max(h["fps"]),
                 min(h["rs"]), max(h["rs"]), agg[m]["files"], agg[m]["n"]))
    print("\n  %d source(s) pass. Everything else is ambient traffic." % len(hits))

    print("\n=== TOP SOURCES BY FRAME COUNT ===")
    print("%-18s %10s %6s %7s %8s %8s  %-19s %-26s %-19s %s"
          % ("MAC", "frames", "files", "len256", "RSSI", "fps_max",
             "first seen UTC", "first file", "last seen UTC", "last file"))
    for m, a in sorted(agg.items(), key=lambda kv: -kv[1]["n"])[:args.top]:
        print("%-18s %10d %6d %6.1f%% %8.1f %8.1f  %-19s %-26s %-19s %s"
              % (m, a["n"], a["files"], 100 * a["l256"] / a["n"],
                 a["rs"] / a["n"], max(a["fps"]) if a["fps"] else 0,
                 utc(a["t0"]), a["first"], utc(a["t1"]), a["last"]))

    print("\n=== PER-BEACON PRESENCE BY FILE (chronological) ===")
    beacons = sorted(hits, key=lambda m: -agg[m]["n"])
    per = defaultdict(dict)
    for r in rows:
        if r["mac"] in beacons:
            per[r["file"]][r["mac"]] = r
    print("%-28s" % "file" + "".join("%22s" % m[:17] for m in beacons))
    for f in sorted(per, key=lambda f: order[f]):
        cells = []
        for m in beacons:
            r = per[f].get(m)
            cells.append("%9d %6.1ff/s" % (r["n"], fps(r)) if r else "%16s" % "-")
        print("%-28s" % f + "".join("%22s" % c for c in cells))


def cmd_cadence(args):
    """Per-frame cadence from esp_timestamp_us (NOT pc_time_us -- see module
    docstring). Reports the gap distribution that separates a configured
    beacon from ambient traffic."""
    t = []
    with open(args.csv, errors="replace") as fh:
        fh.readline()
        for line in fh:
            p = line[:PREFIX_CHARS].split(",")
            if len(p) < 9 or p[3] != args.mac:
                continue
            try:
                t.append(int(p[7]))
            except ValueError:
                pass
            if args.limit and len(t) >= args.limit:
                break
    gaps = [b - a for a, b in zip(t, t[1:]) if 0 < b - a < 5_000_000]
    if len(gaps) < 20:
        print("%s: only %d usable gaps -- too few" % (args.mac, len(gaps)))
        return
    med = statistics.median(gaps)
    sd = statistics.pstdev(gaps)
    mean = statistics.mean(gaps)
    g = sorted(gaps)
    within = sum(1 for x in gaps if abs(x - med) <= 0.2 * med) / len(gaps)
    print("%s in %s" % (args.mac, os.path.basename(args.csv)))
    print("  frames=%d  gaps=%d" % (len(t), len(gaps)))
    print("  fps(median gap)=%.1f  gap_med=%.5f s  CV=%.2f" %
          (1e6 / med, med / 1e6, sd / mean))
    print("  within +/-20%% of median = %.1f%%" % (100 * within))
    print("  p5=%.5f s  p50=%.5f s  p95=%.5f s  p99=%.5f s" %
          (g[len(g) // 20] / 1e6, med / 1e6,
           g[19 * len(g) // 20] / 1e6, g[99 * len(g) // 100] / 1e6))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("census", help="build the per-(file, MAC) table")
    c.add_argument("csvs", nargs="+")
    c.add_argument("--cache", default="census_full.csv")
    c.set_defaults(fn=cmd_census)

    o = sub.add_parser("overlap", help="which files were on air simultaneously")
    o.add_argument("--cache", default="census_full.csv")
    o.add_argument("--min-overlap", type=float, default=1.0, help="seconds")
    o.set_defaults(fn=cmd_overlap)

    r = sub.add_parser("roles", help="beacon filter + first/last appearance")
    r.add_argument("--cache", default="census_full.csv")
    r.add_argument("--top", type=int, default=25)
    r.set_defaults(fn=cmd_roles)

    d = sub.add_parser("cadence", help="per-frame gap stats from esp_timestamp_us")
    d.add_argument("csv")
    d.add_argument("--mac", required=True)
    d.add_argument("--limit", type=int, default=200000)
    d.set_defaults(fn=cmd_cadence)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
