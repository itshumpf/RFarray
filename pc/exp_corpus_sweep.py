#!/usr/bin/env python3
"""exp_corpus_sweep.py — run the shipped DSP over every capture, once.

    python pc/exp_corpus_sweep.py --out data/cache/sweep --budget 140
    python pc/exp_corpus_sweep.py --out data/cache/sweep --only-beacons

EXPLORATORY. Nothing this produces is a test of anything. It exists to
generate hypotheses that then get pre-registered and tested on captures that
have not happened yet. Never quote a number out of this table as a finding —
`.astory/ERROR_LOG.md` mode K is exactly that mistake.

It reuses `rff_offline.collect_observations` unmodified, so every value here is
the number `rff_offline.py` would print for the same file. No estimator, gate
or aggregator is reimplemented. The only thing this adds is that it keeps the
provenance (`node`, `session`) that `rff_offline.persist()` throws away by
hardcoding node="offline".

One parquet per input file, resumable: files already written are skipped, so
it can be run repeatedly under a wall-clock budget.
"""
import argparse
import os
import sys
import time
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rff_offline import collect_observations, DEFAULT_MAX_RESID, DEFAULT_MIN_INLIER

BEACONS = ("a4:f0:0f:77:91:20", "f4:2d:c9:70:72:30", "28:05:a5:2f:fa:48")


def sweep_file(path, window, min_inlier, max_resid):
    """-> list of row dicts, one per accepted window."""
    by_mac = collect_observations([path], window=window, ref_mac=None,
                                  max_resid=max_resid, min_inlier=min_inlier)
    base = os.path.basename(path)[:-4]
    node, _, session = base.partition("_")
    rows = []
    for mac, obs_list in by_mac.items():
        for i, o in enumerate(obs_list):
            row = {"node": node, "session": session, "mac": mac,
                   "win_idx": i, "ts_pc": o.get("ts_pc")}
            # carry every scalar the aggregator produced, whatever it is named
            for k, v in o.items():
                if k in ("ts_pc", "session"):
                    continue
                if isinstance(v, (int, float, str, bool)) or v is None:
                    row[k] = v
            rows.append(row)
    return rows


COLUMNS = ("node", "session", "mac", "win_idx", "ts_pc", "ts_us",
           "sfo", "sfo_iqr", "cfo", "cfo_iqr", "rssi", "n_frames", "quality")


def write_parquet(duckdb, rows, out):
    """Write rows to parquet via duckdb. A file with no accepted windows still
    gets an empty parquet, so 'analysed and found nothing' is distinguishable
    from 'never analysed' — ERROR_LOG mode C."""
    con = duckdb.connect()
    con.execute("CREATE TABLE t (" + ", ".join(
        f'"{c}" ' + ("VARCHAR" if c in ("node", "session", "mac") else
                     "BIGINT" if c in ("win_idx", "n_frames", "ts_us") else "DOUBLE")
        for c in COLUMNS) + ")")
    if rows:
        con.executemany(
            "INSERT INTO t VALUES (" + ",".join("?" * len(COLUMNS)) + ")",
            [[r.get(c) for c in COLUMNS] for r in rows])
    con.execute(f"COPY t TO '{out}' (FORMAT parquet, COMPRESSION zstd)")
    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw", help="capture directory")
    ap.add_argument("--out", default="data/cache/sweep", help="parquet output dir")
    ap.add_argument("--window", type=int, default=64)
    ap.add_argument("--min-inlier", type=float, default=DEFAULT_MIN_INLIER)
    ap.add_argument("--max-resid", type=float, default=DEFAULT_MAX_RESID)
    ap.add_argument("--budget", type=float, default=0,
                    help="stop starting new files after this many seconds")
    ap.add_argument("--only-beacons", action="store_true",
                    help="keep only the three known beacons (much smaller)")
    ap.add_argument("--min-bytes", type=int, default=200,
                    help="skip files at or below this size (13 captures are 0 bytes)")
    args = ap.parse_args()

    # duckdb rather than pandas.to_parquet: no pyarrow in this environment,
    # and duckdb is already the project's query engine.
    import duckdb

    os.makedirs(args.out, exist_ok=True)
    files = [f for f in sorted(glob.glob(os.path.join(args.raw, "*.csv")))
             if os.path.getsize(f) > args.min_bytes]
    todo = [f for f in files
            if not os.path.exists(os.path.join(
                args.out, os.path.basename(f)[:-4] + ".parquet"))]
    print(f"{len(files)} non-empty captures, {len(todo)} remaining", file=sys.stderr)

    t0 = time.time()
    done = 0
    for path in todo:
        if args.budget and time.time() - t0 > args.budget:
            print("budget reached", file=sys.stderr)
            break
        base = os.path.basename(path)[:-4]
        try:
            rows = sweep_file(path, args.window, args.min_inlier, args.max_resid)
        except Exception as exc:
            print(f"  SKIP {base}: {exc}", file=sys.stderr)
            continue
        if args.only_beacons:
            rows = [r for r in rows if r["mac"] in BEACONS]
        out = os.path.join(args.out, base + ".parquet")
        write_parquet(duckdb, rows, out)
        done += 1
        print(f"  {base}: {len(rows)} windows -> {out}", file=sys.stderr)
    print(f"wrote {done} files in {time.time() - t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
