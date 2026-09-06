#!/usr/bin/env python3
"""Dependency-free SVG summary of link-signature results."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path("deep_dive/link_signature")
COLORS = {"d0wd": "#3264a8", "s3": "#e0802d", "fused": "#3a9d72"}
REPS = ("slope", "channel", "combined")


def read(name):
    with (ROOT / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    summary = json.loads((ROOT / "summary.json").read_text(encoding="utf-8"))
    ident = read("same_receiver_identification.csv")
    fusion = read("paired_receiver_fusion.csv")
    temporal = read("exploratory_early_late.csv")
    width, height = 1200, 820
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Segoe UI,Arial,sans-serif;fill:#222}.title{font-size:23px;font-weight:600}.h{font-size:16px;font-weight:600}.a{font-size:12px}.small{font-size:10px}</style>',
        '<text class="title" x="600" y="32" text-anchor="middle">Eight-night link signatures: strong within-night, weak across-night</text>',
    ]

    def axes(x, y, w, h, title, ylabel):
        svg.append(f'<text class="h" x="{x}" y="{y-14}">{title}</text>')
        svg.append(f'<line x1="{x}" y1="{y+h}" x2="{x+w}" y2="{y+h}" stroke="#555"/>')
        svg.append(f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y+h}" stroke="#555"/>')
        for value in (0, .25, .5, .75, 1):
            yy = y + h * (1-value)
            svg.append(f'<line x1="{x}" y1="{yy:.1f}" x2="{x+w}" y2="{yy:.1f}" stroke="#e6e6e6"/>')
            svg.append(f'<text class="small" x="{x-7}" y="{yy+4:.1f}" text-anchor="end">{value:.2f}</text>')
        svg.append(f'<text class="small" transform="translate({x-42},{y+h/2}) rotate(-90)" text-anchor="middle">{ylabel}</text>')

    x, y, w, h = 75, 85, 490, 275
    axes(x, y, w, h, "A. Channel signature by held-out night", "Balanced accuracy")
    series = {}
    for name in ("d0wd", "s3"):
        q = [r for r in ident if r["scale_s"] == "300" and
             r["representation"] == "channel" and r["receiver"] == name]
        series[name] = [float(r["balanced_accuracy"])
                        for r in sorted(q, key=lambda r: int(r["test_night"]))]
    q = [r for r in fusion if r["scale_s"] == "300" and
         r["representation"] == "channel" and r["model"] == "fused"]
    series["fused"] = [float(r["balanced_accuracy"])
                       for r in sorted(q, key=lambda r: int(r["test_night"]))]
    for i in range(8):
        xx = x + (i+.5)*w/8
        svg.append(f'<text class="small" x="{xx:.1f}" y="{y+h+17}" text-anchor="middle">N{i+1}</text>')
    chance_y = y+h*(1-1/3)
    svg.append(f'<line x1="{x}" y1="{chance_y:.1f}" x2="{x+w}" y2="{chance_y:.1f}" stroke="#555" stroke-dasharray="5 4"/>')
    for name, values in series.items():
        points = []
        for i, value in enumerate(values):
            xx, yy = x+(i+.5)*w/8, y+h*(1-value)
            points.append(f"{xx:.1f},{yy:.1f}")
            svg.append(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="3.5" fill="{COLORS[name]}"/>')
        svg.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{COLORS[name]}" stroke-width="2"/>')
    for j, name in enumerate(("d0wd", "s3", "fused")):
        svg.append(f'<rect x="{x+255+j*75}" y="{y-28}" width="12" height="4" fill="{COLORS[name]}"/>')
        svg.append(f'<text class="small" x="{x+271+j*75}" y="{y-22}">{name.upper()}</text>')

    def grouped_bars(x, y, w, h, title, values, target=None, target_label=""):
        axes(x, y, w, h, title, "Score")
        bar_width, gap = 32, w/3
        for i, rep in enumerate(REPS):
            base = x + (i+.5)*gap
            svg.append(f'<text class="small" x="{base:.1f}" y="{y+h+17}" text-anchor="middle">{rep.title()}</text>')
            names = list(values[rep])
            for j, name in enumerate(names):
                value = values[rep][name]
                xx = base + (j-(len(names)-1)/2)*(bar_width+4)-bar_width/2
                yy = y+h*(1-value)
                svg.append(f'<rect x="{xx:.1f}" y="{yy:.1f}" width="{bar_width}" height="{y+h-yy:.1f}" fill="{COLORS[name]}"/>')
        if target is not None:
            yy = y+h*(1-target)
            svg.append(f'<line x1="{x}" y1="{yy:.1f}" x2="{x+w}" y2="{yy:.1f}" stroke="#9b2f2f" stroke-dasharray="2 3"/>')
            svg.append(f'<text class="small" x="{x+w-3}" y="{yy-4:.1f}" text-anchor="end" fill="#9b2f2f">{target_label}</text>')

    values = {rep: {rx: next(r["macro_accuracy"] for r in summary["t1"] if
              r["scale_s"] == 300 and r["representation"] == rep and r["receiver"] == rx)
              for rx in ("d0wd", "s3")} for rep in REPS}
    grouped_bars(675, 85, 450, 275, "B. Cross-night identification", values, .70, "frozen target")

    values = {}
    for rep in REPS:
        values[rep] = {}
        for model in ("d0wd", "s3", "fused"):
            q = [float(r["balanced_accuracy"]) for r in temporal if
                 r["representation"] == rep and r["model"] == model]
            values[rep][model] = sum(q)/len(q)
    grouped_bars(75, 470, 490, 275, "C. Exploratory: early 40% to late 40%", values)

    values = {rep: {rx: next(r["macro_auc"] for r in summary["t3"] if
              r["representation"] == rep and r["receiver"] == rx)
              for rx in ("d0wd", "s3")} for rep in REPS}
    grouped_bars(675, 470, 450, 275, "D. Claimed-link verification (ROC AUC)", values, .90, "frozen target")
    svg.append('<text class="small" x="75" y="797">Whole nights are held out in A, B, and D. Panel C is explicitly post-hoc and uses a 20% within-night time gap.</text>')
    svg.append("</svg>")
    dest = ROOT / "link_signature_results.svg"
    dest.write_text("\n".join(svg), encoding="utf-8")
    print(dest)


if __name__ == "__main__":
    main()
