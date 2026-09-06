#!/usr/bin/env python3
"""Create a dependency-free SVG diagnostic from targeted replay summaries."""

import argparse
import csv
from pathlib import Path


def read(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--analysis", required=True)
    ap.add_argument("--out", required=True); args = ap.parse_args()
    root = Path(args.analysis); mins = read(root / "minute_medians.csv")
    pairs = read(root / "pair_minute_detail.csv")
    W, H = 1320, 860; pw, ph = 570, 300
    panels = [(80, 100), (710, 100), (80, 500), (710, 500)]
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<style>text{font-family:Segoe UI,Arial,sans-serif;fill:#222}.t{font-size:18px;font-weight:600}.a{font-size:12px}.g{stroke:#ddd;stroke-width:1}.axis{stroke:#555;stroke-width:1}.line{fill:none;stroke-width:2}</style>',
           '<text x="660" y="38" text-anchor="middle" font-size="24" font-weight="600">Exact full-frame targeted replay (common production gate)</text>']

    def panel(x, y, title, series, ylabel, threshold=None):
        vals = [(xx, yy) for _, _, pts in series for xx, yy in pts]
        xmin, xmax = min(v for v, _ in vals), max(v for v, _ in vals)
        ymin, ymax = min(v for _, v in vals), max(v for _, v in vals)
        if threshold is not None: ymin = 0; ymax = max(ymax, threshold * 1.4)
        pad = (ymax - ymin) * .08 or 1; ymax += pad
        if threshold is None: ymin -= pad
        X = lambda v: x + (v - xmin) / max(xmax - xmin, 1e-12) * pw
        Y = lambda v: y + ph - (v - ymin) / max(ymax - ymin, 1e-12) * ph
        svg.append(f'<text class="t" x="{x}" y="{y-22}">{esc(title)}</text>')
        for i in range(5):
            gy = y + i * ph / 4; val = ymax - i * (ymax-ymin)/4
            svg.append(f'<line class="g" x1="{x}" y1="{gy}" x2="{x+pw}" y2="{gy}"/>')
            svg.append(f'<text class="a" x="{x-8}" y="{gy+4}" text-anchor="end">{val:.2f}</text>')
        svg.append(f'<line class="axis" x1="{x}" y1="{y+ph}" x2="{x+pw}" y2="{y+ph}"/>')
        svg.append(f'<line class="axis" x1="{x}" y1="{y}" x2="{x}" y2="{y+ph}"/>')
        if threshold is not None:
            svg.append(f'<line x1="{x}" y1="{Y(threshold)}" x2="{x+pw}" y2="{Y(threshold)}" stroke="#111" stroke-dasharray="4 4"/>')
        for label, color, pts in series:
            dash = ' stroke-dasharray="7 5"' if "arbiter" in label else ""
            d = " ".join(("M" if i == 0 else "L") + f"{X(px):.1f},{Y(py):.1f}" for i, (px, py) in enumerate(pts))
            svg.append(f'<path class="line" stroke="{color}"{dash} d="{d}"/>')
        svg.append(f'<text class="a" x="{x+pw/2}" y="{y+ph+34}" text-anchor="middle">minutes from interval start</text>')
        svg.append(f'<text class="a" transform="translate({x-55},{y+ph/2}) rotate(-90)" text-anchor="middle">{esc(ylabel)}</text>')
        lx, ly = x + 8, y + 18
        for i, (label, color, _) in enumerate(series):
            yy = ly + 18*i; dash = ' stroke-dasharray="7 5"' if "arbiter" in label else ""
            svg.append(f'<line x1="{lx}" y1="{yy}" x2="{lx+24}" y2="{yy}" stroke="{color}" stroke-width="2"{dash}/><text class="a" x="{lx+30}" y="{yy+4}">{esc(label)}</text>')

    series = []
    for rx, color in (("d0wd", "#1f77b4"), ("s3", "#ff7f0e")):
        q = sorted((r for r in mins if r["stamp"] == "20260830_013943" and r["receiver"] == rx and r["beacon"] == "B3"), key=lambda r: int(r["absolute_minute"]))
        m0 = int(q[0]["absolute_minute"])
        series += [(f"{rx} production", color, [(int(r["absolute_minute"])-m0, float(r["prod"])) for r in q]),
                   (f"{rx} arbiter", color, [(int(r["absolute_minute"])-m0, float(r["arb"])) for r in q])]
    panel(*panels[0], "Night 2 — B3 label interval", series, "slope (rad/subcarrier)")

    def pair_series(stamp, pair):
        out = []
        for rx, color in (("d0wd", "#1f77b4"), ("s3", "#ff7f0e")):
            for est, name in (("prod", "production"), ("arb", "arbiter")):
                q = sorted((r for r in pairs if r["stamp"] == stamp and r["pair"] == pair and r["receiver"] == rx and r["estimator"] == est), key=lambda r: int(r["absolute_minute"]))
                m0 = int(q[0]["absolute_minute"])
                out.append((f"{rx} {name}", color, [(int(r["absolute_minute"])-m0, float(r["sigma"])) for r in q]))
        return out

    panel(*panels[1], "Night 6 — startup B1–B2", pair_series("20260903_013851", "B1-B2"), "pair distance / between-unit SD", 1)
    panel(*panels[2], "Night 5 — B2–B3", pair_series("20260902_000949", "B2-B3"), "pair distance / between-unit SD", 1)
    panel(*panels[3], "Night 8 — B2–B3", pair_series("20260905_025053", "B2-B3"), "pair distance / between-unit SD", 1)
    svg.append('</svg>')
    Path(args.out).write_text("\n".join(svg), encoding="utf-8")


if __name__ == "__main__":
    main()
