#!/usr/bin/env python3
"""RF fingerprinting over collected CSI data.

Every transmitter's radio has tiny hardware imperfections that shape its
frames. We profile each device (per MAC) from collected CSVs:
  - CSI amplitude template (mean per-subcarrier amplitude, normalized)
  - template stability (per-subcarrier std dev)
  - RSSI distribution (mean/std)
  - frame length histogram (packet formats the device emits)

Commands:
  build     Learn/refresh fingerprints from one or more session CSVs
            python fingerprint.py build data/raw/*.csv --name phone --mac aa:bb:..
            (omit --mac/--name to profile every MAC seen)
  list      Show the fingerprint library
            python fingerprint.py list
  match     Score a new capture against the library, flag strangers
            python fingerprint.py match data/raw/unknown_session.csv

Fingerprints are JSON files in data/fingerprints/, one per device.
"""
import argparse
import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np

FP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "data", "fingerprints")
N_SC = 64                  # LLTF subcarriers used for the template
MIN_FRAMES = 25            # below this, refuse to fingerprint
MATCH_THRESHOLD = 0.15     # cosine distance above this = "does not match"


def load_rows(csv_paths):
    """Yield (mac, rssi, amps[N_SC]) per usable row across the given CSVs."""
    import csv as csvmod
    for path in csv_paths:
        with open(path, newline="") as f:
            reader = csvmod.DictReader(f)
            for row in reader:
                try:
                    vals = np.array(row["csi_data"].split(","), dtype=np.float32)
                except (KeyError, ValueError):
                    continue
                if vals.size < N_SC * 2:
                    continue
                iq = vals[: N_SC * 2]
                amps = np.hypot(iq[0::2], iq[1::2])
                yield row["mac"].lower(), int(row["rssi"]), int(row["len"]), amps


def collect_stats(csv_paths, only_mac=None):
    """Group rows by MAC and compute per-device stats."""
    frames = defaultdict(list)
    rssis = defaultdict(list)
    lens = defaultdict(lambda: defaultdict(int))
    for mac, rssi, flen, amps in load_rows(csv_paths):
        if only_mac and mac != only_mac:
            continue
        frames[mac].append(amps)
        rssis[mac].append(rssi)
        lens[mac][str(flen)] += 1

    stats = {}
    for mac, amp_list in frames.items():
        if len(amp_list) < MIN_FRAMES:
            continue
        a = np.array(amp_list)
        # normalize each frame so distance ignores overall power/AGC
        norms = np.linalg.norm(a, axis=1, keepdims=True)
        norms[norms == 0] = 1
        a = a / norms
        stats[mac] = {
            "frames": len(amp_list),
            "template": a.mean(axis=0).tolist(),
            "template_std": a.std(axis=0).tolist(),
            "rssi_mean": float(np.mean(rssis[mac])),
            "rssi_std": float(np.std(rssis[mac])),
            "len_hist": dict(lens[mac]),
        }
    return stats


def cosine_distance(u, v):
    u, v = np.asarray(u), np.asarray(v)
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    if nu == 0 or nv == 0:
        return 1.0
    return float(1.0 - np.dot(u, v) / (nu * nv))


def fp_path(mac):
    return os.path.join(FP_DIR, mac.replace(":", "") + ".json")


def cmd_build(args):
    paths = []
    for pat in args.csvs:
        paths.extend(glob.glob(pat))
    if not paths:
        print("no CSV files matched", file=sys.stderr)
        return 1
    os.makedirs(FP_DIR, exist_ok=True)
    only = args.mac.lower() if args.mac else None
    stats = collect_stats(paths, only_mac=only)
    if not stats:
        print(f"no MAC had >= {MIN_FRAMES} usable frames", file=sys.stderr)
        return 1
    for mac, st in stats.items():
        st["mac"] = mac
        st["name"] = args.name if (args.name and (only or len(stats) == 1)) else mac
        st["sources"] = [os.path.basename(p) for p in paths]
        with open(fp_path(mac), "w") as f:
            json.dump(st, f, indent=1)
        print(f"saved {st['name']}  ({mac})  {st['frames']} frames "
              f"rssi {st['rssi_mean']:.0f}±{st['rssi_std']:.0f}")
    return 0


def load_library():
    lib = {}
    for p in glob.glob(os.path.join(FP_DIR, "*.json")):
        with open(p) as f:
            fp = json.load(f)
        lib[fp["mac"]] = fp
    return lib


def cmd_list(_args):
    lib = load_library()
    if not lib:
        print("library is empty — run `build` first")
        return 0
    for mac, fp in sorted(lib.items()):
        print(f"{fp.get('name', mac):20s} {mac}  {fp['frames']:6d} frames  "
              f"rssi {fp['rssi_mean']:.0f}±{fp['rssi_std']:.0f}")
    return 0


def cmd_match(args):
    lib = load_library()
    if not lib:
        print("library is empty — run `build` first", file=sys.stderr)
        return 1
    paths = []
    for pat in args.csvs:
        paths.extend(glob.glob(pat))
    if not paths:
        print("no CSV files matched", file=sys.stderr)
        return 1
    stats = collect_stats(paths)
    if not stats:
        print(f"no MAC had >= {MIN_FRAMES} usable frames", file=sys.stderr)
        return 1

    print(f"{'observed MAC':20s} {'frames':>6s}  best match           "
          f"{'dist':>6s}  verdict")
    for mac, st in sorted(stats.items()):
        best_name, best_d = None, 2.0
        for kmac, fp in lib.items():
            d = cosine_distance(st["template"], fp["template"])
            if d < best_d:
                best_d, best_name = d, fp.get("name", kmac)
        known_mac = mac in lib
        ok = best_d <= MATCH_THRESHOLD
        if known_mac and ok:
            verdict = "KNOWN"
        elif ok and not known_mac:
            verdict = "SIGNATURE MATCH, NEW MAC (possible spoof/rotation)"
        elif known_mac and not ok:
            verdict = "MAC KNOWN BUT SIGNATURE OFF (investigate!)"
        else:
            verdict = "STRANGER"
        print(f"{mac:20s} {st['frames']:6d}  {best_name or '-':20s} "
              f"{best_d:6.3f}  {verdict}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="learn fingerprints from session CSVs")
    b.add_argument("csvs", nargs="+", help="CSV files or globs")
    b.add_argument("--mac", help="only fingerprint this MAC")
    b.add_argument("--name", help="friendly device name")
    b.set_defaults(fn=cmd_build)

    l = sub.add_parser("list", help="show fingerprint library")
    l.set_defaults(fn=cmd_list)

    m = sub.add_parser("match", help="score a capture against the library")
    m.add_argument("csvs", nargs="+", help="CSV files or globs")
    m.set_defaults(fn=cmd_match)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
