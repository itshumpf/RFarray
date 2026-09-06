#!/usr/bin/env python3
"""Dependency-free SVG heatmaps for the full-corpus state analysis."""

import argparse
import csv
from pathlib import Path


PAIRS=("B1-B2","B1-B3","B2-B3")


def read(p):
    with open(p,newline="",encoding="utf-8") as f:return list(csv.DictReader(f))


def color(v, vmax, hue):
    x=max(0,min(1,v/vmax)); base={"blue":(31,119,180),"orange":(255,127,14),
                                  "green":(44,160,44),"red":(214,39,40)}[hue]
    return "#%02x%02x%02x"%tuple(round(255-(255-c)*x) for c in base)


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--analysis",required=True);ap.add_argument("--out",required=True);a=ap.parse_args()
    root=Path(a.analysis); states=read(root/"state_duration_summary.csv"); dd=read(root/"double_difference_summary.csv")
    W,H=1180,780; svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">','<rect width="100%" height="100%" fill="white"/>','<style>text{font-family:Segoe UI,Arial,sans-serif;fill:#222}.title{font-size:24px;font-weight:600}.h{font-size:17px;font-weight:600}.a{font-size:12px}</style>','<text class="title" x="590" y="35" text-anchor="middle">Full-corpus unwrap-free pattern map</text>']
    def heat(x,y,title,data,vmax,hue,fmt):
        cw,ch=78,42; svg.append(f'<text class="h" x="{x}" y="{y-18}">{title}</text>')
        for j,p in enumerate(PAIRS):svg.append(f'<text class="a" x="{x+95+j*cw+cw/2}" y="{y-3}" text-anchor="middle">{p}</text>')
        for i in range(8):
            svg.append(f'<text class="a" x="{x+82}" y="{y+i*ch+27}" text-anchor="end">night {i+1}</text>')
            for j,p in enumerate(PAIRS):
                v=data.get((i+1,p),0); xx=x+95+j*cw; yy=y+i*ch
                svg.append(f'<rect x="{xx}" y="{yy}" width="{cw-3}" height="{ch-3}" fill="{color(v,vmax,hue)}" stroke="#ddd"/>')
                svg.append(f'<text class="a" x="{xx+(cw-3)/2}" y="{yy+25}" text-anchor="middle">{fmt(v)}</text>')
    for idx,(rx,title,hue) in enumerate((("d0wd","D0WD: time pair is below 1 SD","blue"),("s3","S3: time pair is below 1 SD","orange"),("both","Both receivers simultaneously","green"))):
        dat={(int(r["night"]),r["pair"]):100*float(r["below_frac"]) for r in states if int(r["scale_s"])==60 and r["receiver"]==rx}
        heat(25+(idx%2)*570,95+(idx//2)*385,title,dat,100,hue,lambda v:f"{v:.0f}%")
    dat={(int(r["night"]),r["pair"]):float(r["median_abs_double_diff_sd"]) for r in dd if int(r["scale_s"])==300}
    heat(595,480,"5-min median |double difference|",dat,25,"red",lambda v:f"{v:.1f} SD")
    svg.append('<text class="a" x="25" y="755">State panels use exact 1-minute medians. Dark color means larger value; double-difference color saturates at 25 SD.</text>')
    svg.append('</svg>');Path(a.out).write_text("\n".join(svg),encoding="utf-8")


if __name__=="__main__":main()
