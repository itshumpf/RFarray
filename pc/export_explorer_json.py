#!/usr/bin/env python3
"""export_explorer_json.py — build the portfolio CSI explorer's data file.

    python pc/export_explorer_json.py --out ..\portfolio\public\demo\csi\csi-explorer.json

Reads the two cached tables built from data/raw/:

  data/cache/sweep/*.parquet    one row per DSP window  (sfo, cfo, rssi, quality)
  data/cache/parquet/*.parquet  one row per frame       (rssi, noise_floor, label)

and emits a single small JSON for a client-side page. **No raw CSI leaves this
script** — only the derived per-window SFO, the fit quality, and the operator's
own labels. That matters: `ROOM_OR_RADIO.md` §8 refuses to publish the captures
because they are a log of when a home was occupied, and this keeps that promise.

Downsampling is by ntile median, not by decimation: each output point is the
median of an equal-count bucket, so a spike is attenuated rather than either
dropped or over-represented. The point count is stated in the payload so a
reader knows they are looking at a summary.
"""
import argparse
import json
import os
import sys

BEACONS = {"a4:f0:0f:77:91:20": "B1",
           "f4:2d:c9:70:72:30": "B3",
           "28:05:a5:2f:fa:48": "B2"}

# The four captures the case study actually argues about.
SESSIONS = [
    ("20260827_140642", "Rotation — beacons swapped between positions mid-capture"),
    ("20260828_022627", "Co-located — all three on one surface, room empty"),
    ("20260829_025355", "Night 1 of the eight-night replication"),
    ("20260829_122648", "Fan A/B — fan off, on, off, operator present"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", default="data/cache/sweep")
    ap.add_argument("--frames", default="data/cache/parquet")
    ap.add_argument("--out", required=True)
    ap.add_argument("--points", type=int, default=400,
                    help="output points per beacon per receiver")
    args = ap.parse_args()

    import duckdb
    con = duckdb.connect()
    out = {"points_per_series": args.points,
           "note": "Each point is the median of an equal-count bucket, not a raw window.",
           "beacons": ["B1", "B2", "B3"], "sessions": []}

    for sid, title in SESSIONS:
        entry = {"id": sid, "title": title, "nodes": [], "series": {}, "events": []}
        for node in ("s3", "d0wd"):
            p = os.path.join(args.sweep, f"{node}_{sid}.parquet")
            if not os.path.exists(p):
                print(f"  no sweep for {node}_{sid}", file=sys.stderr)
                continue
            entry["nodes"].append(node)
            t0 = con.execute(f"SELECT min(ts_pc) FROM read_parquet('{p}')").fetchone()[0]
            series = {}
            for mac, name in BEACONS.items():
                rows = con.execute(f"""
                  WITH d AS (SELECT ts_pc - {t0} AS t, sfo, quality
                             FROM read_parquet('{p}')
                             WHERE mac = '{mac}' AND sfo IS NOT NULL),
                       b AS (SELECT *, ntile({args.points}) OVER (ORDER BY t) g FROM d)
                  SELECT round(median(t), 1), round(median(sfo), 6),
                         round(median(quality), 3)
                  FROM b GROUP BY g ORDER BY 1""").fetchall()
                if rows:
                    series[name] = [[r[0], r[1], r[2]] for r in rows]
            entry["series"][node] = series

        # Labels live in the FRAME table, not the sweep table — the operator's
        # own event log, reconstructed from the captures.
        for node in ("d0wd", "s3"):
            fp = os.path.join(args.frames, f"{node}_{sid}.parquet")
            if not os.path.exists(fp):
                continue
            evs = con.execute(f"""SELECT round(min(t_rel), 1), label
                  FROM read_parquet('{fp}')
                  WHERE label IS NOT NULL AND label <> ''
                  GROUP BY label ORDER BY 1""").fetchall()
            if evs:
                entry["events"] = [{"t": t, "label": l} for t, l in evs]
                break
        if not entry["events"]:
            print(f"  {sid}: no labels found — frame parquet may predate the "
                  f"end of the capture; rebuild it to pick them up", file=sys.stderr)
        out["sessions"].append(entry)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"wrote {args.out}  ({os.path.getsize(args.out) / 1024:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
