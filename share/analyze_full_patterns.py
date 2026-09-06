#!/usr/bin/env python3
"""Cross-receiver, state, change-point, and periodicity analyses."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


UNIT = 0.00237
PAIRS = ((1, 2), (1, 3), (2, 3))


def write_csv(path, rows):
    if not rows: return
    fields = []
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


def load_scale(root, scale):
    pp = sorted(root.glob(f"*.{scale}s.npy"))
    return np.concatenate([np.load(p) for p in pp]) if pp else np.empty(0)


def corr(x, y):
    return float(np.corrcoef(x, y)[0, 1]) if len(x) >= 3 and np.std(x) and np.std(y) else np.nan


def pair_maps(a, night, scale):
    out = {}
    for rx in (0, 1):
        q = a[(a["night"] == night) & (a["receiver"] == rx)]
        byb = {b: {int(z["bin"]): float(z["arb"]) for z in q[q["beacon"] == b]}
               for b in (1, 2, 3)}
        for b1, b2 in PAIRS:
            bins = sorted(set(byb[b1]) & set(byb[b2]))
            out[(rx, b1, b2)] = {t: byb[b1][t] - byb[b2][t] for t in bins}
    return out


def runs(bins):
    if not bins: return []
    out = []; a = z = bins[0]
    for x in bins[1:]:
        if x == z + 1: z = x
        else: out.append((a, z, z-a+1)); a = z = x
    out.append((a, z, z-a+1)); return out


def cross_and_states(a, scale):
    detail = []; summary = []; states = []
    for night in range(1, 9):
        pm = pair_maps(a, night, scale)
        for b1, b2 in PAIRS:
            d0, s3 = pm[(0, b1, b2)], pm[(1, b1, b2)]
            common = sorted(set(d0) & set(s3))
            x = np.array([d0[t] for t in common]); y = np.array([s3[t] for t in common])
            dd = y-x
            summary.append({"night": night, "scale_s": scale, "pair": f"B{b1}-B{b2}",
                            "aligned_bins": len(common), "corr_level": corr(x, y),
                            "corr_first_diff": corr(np.diff(x), np.diff(y)),
                            "median_abs_double_diff": float(np.median(np.abs(dd))) if len(dd) else np.nan,
                            "median_abs_double_diff_sd": float(np.median(np.abs(dd))/UNIT) if len(dd) else np.nan,
                            "double_diff_below_1sd_frac": float(np.mean(np.abs(dd)<UNIT)) if len(dd) else np.nan})
            for t, xx, yy in zip(common, x, y):
                detail.append({"night": night, "scale_s": scale, "bin": t,
                               "pair": f"B{b1}-B{b2}", "d0wd_diff": xx,
                               "s3_diff": yy, "double_diff": yy-xx})
            for rx, d in (("d0wd", d0), ("s3", s3)):
                valid = sorted(d); low = [t for t in valid if abs(d[t]) < UNIT]
                rr = runs(low); longest = max(rr, key=lambda z: z[2]) if rr else (None,None,0)
                states.append({"night": night, "scale_s": scale, "receiver": rx,
                               "pair": f"B{b1}-B{b2}", "bins": len(valid),
                               "below_1sd": len(low), "below_frac": len(low)/len(valid) if valid else np.nan,
                               "longest_run_bins": longest[2], "longest_run_s": longest[2]*scale,
                               "longest_start_bin": longest[0]})
            both = [t for t in common if abs(d0[t]) < UNIT and abs(s3[t]) < UNIT]
            rr = runs(both); longest = max(rr, key=lambda z:z[2]) if rr else (None,None,0)
            states.append({"night": night, "scale_s": scale, "receiver": "both",
                           "pair": f"B{b1}-B{b2}", "bins": len(common),
                           "below_1sd": len(both), "below_frac": len(both)/len(common) if common else np.nan,
                           "longest_run_bins": longest[2], "longest_run_s": longest[2]*scale,
                           "longest_start_bin": longest[0]})
    return detail, summary, states


def change_points(a):
    cand = []
    for night in range(1, 9):
        for rx in (0, 1):
            for b in (1, 2, 3):
                q = a[(a["night"]==night)&(a["receiver"]==rx)&(a["beacon"]==b)]
                q = q[np.argsort(q["bin"])]
                t, y = q["bin"].astype(int), q["arb"].astype(float)
                for w in (5, 15, 30):
                    cc = []
                    for i in range(w, len(y)-w):
                        # Require one unbroken 2w-bin run, including adjacency
                        # across the candidate boundary.  Checking each side
                        # alone wrongly labels a beacon off/on gap as a step.
                        if t[i+w-1]-t[i-w] != 2*w-1: continue
                        left, right = y[i-w:i], y[i:i+w]
                        shift = float(np.median(right)-np.median(left))
                        noise = 1.4826*np.median(np.abs(np.diff(y[i-w:i+w])-np.median(np.diff(y[i-w:i+w]))))
                        cc.append((abs(shift), i, shift, noise))
                    chosen = []
                    for _, i, shift, noise in sorted(cc, reverse=True):
                        if any(abs(i-j) < w for j in chosen): continue
                        chosen.append(i)
                        cand.append({"night":night,"receiver":"s3" if rx else "d0wd",
                                     "beacon":f"B{b}","window_min":w,"boundary_abs_min":int(t[i]),
                                     "shift":shift,"shift_sd":shift/UNIT,
                                     "local_robust_score":abs(shift)/noise if noise>0 else np.nan})
                        if len(chosen)>=5: break
    # Cross-receiver replication within +/- 2 minutes and matching sign.
    for r in cand:
        other = [z for z in cand if z["night"]==r["night"] and z["beacon"]==r["beacon"]
                 and z["window_min"]==r["window_min"] and z["receiver"]!=r["receiver"]
                 and abs(z["boundary_abs_min"]-r["boundary_abs_min"])<=2
                 and np.sign(z["shift"])==np.sign(r["shift"])
                 and abs(z["shift"]) >= UNIT]
        other.sort(key=lambda z:(abs(z["boundary_abs_min"]-r["boundary_abs_min"]),
                                 -abs(z["shift"])))
        r["cross_receiver_match"] = bool(other) and abs(r["shift"]) >= UNIT
        r["other_shift_sd"] = other[0]["shift_sd"] if other else np.nan
    return cand


def change_controls(a, candidates):
    """Before/after controls for replicated candidate boundaries."""
    rows=[]; seen=set()
    for c in candidates:
        if not c.get("cross_receiver_match"): continue
        key=(c["night"],c["beacon"],c["window_min"],c["boundary_abs_min"])
        if key in seen: continue
        seen.add(key); target_b=int(c["beacon"][1:]); w=int(c["window_min"]); t=int(c["boundary_abs_min"])
        for rx in (0,1):
            for b in (1,2,3):
                q=a[(a["night"]==c["night"])&(a["receiver"]==rx)&(a["beacon"]==b)]
                pre=q[(q["bin"]>=t-w)&(q["bin"]<t)]; post=q[(q["bin"]>=t)&(q["bin"]<t+w)]
                if not len(pre) or not len(post): continue
                r={"night":c["night"],"target_beacon":c["beacon"],"window_min":w,
                   "boundary_abs_min":t,"receiver":"s3" if rx else "d0wd",
                   "control_beacon":f"B{b}","is_target":b==target_b,
                   "pre_bins":len(pre),"post_bins":len(post)}
                for field in ("arb","ols","coh_arb","rssi","amp_med","kp1_amp","cir_peak","cir_rms"):
                    r[f"{field}_shift"]=float(np.median(post[field])-np.median(pre[field]))
                r["arb_shift_sd"]=r["arb_shift"]/UNIT
                rows.append(r)
    return rows


def periodogram_tests(a, permutations=200, seed=20260905):
    rng = np.random.default_rng(seed); rows=[]
    for night in range(1,9):
        for rx in (0,1):
            for b in (1,2,3):
                q=a[(a["night"]==night)&(a["receiver"]==rx)&(a["beacon"]==b)]
                q=q[np.argsort(q["bin"])]
                if len(q)<32: continue
                # Longest contiguous five-minute segment.
                t=q["bin"].astype(int); cuts=np.r_[0,np.flatnonzero(np.diff(t)!=1)+1,len(t)]
                lo,hi=max(zip(cuts[:-1],cuts[1:]),key=lambda z:z[1]-z[0])
                y=q["arb"][lo:hi].astype(float); n=len(y)
                if n<32: continue
                x=np.arange(n); coef=np.polyfit(x,y,1); z=y-np.polyval(coef,x)
                win=np.hanning(n); power=np.abs(np.fft.rfft(z*win))**2
                freq=np.fft.rfftfreq(n,d=300.0)
                period=np.full_like(freq,np.inf); period[1:]=1/freq[1:]
                # A two-lobe trend can masquerade as a half-session period.
                # Require at least three observed cycles before calling a
                # spectral peak a periodicity candidate.
                ok=(freq>0)&(period>=600)&(period<=n*300/3)
                inds=np.flatnonzero(ok); best=inds[np.argmax(power[inds])]
                observed=float(power[best]/max(power[inds].sum(),1e-30))
                block=6; blocks=[z[i:i+block] for i in range(0,n,block)]
                null=[]
                for _ in range(permutations):
                    order=rng.permutation(len(blocks)); zz=np.concatenate([blocks[i] for i in order])[:n]
                    pp=np.abs(np.fft.rfft(zz*win))**2
                    null.append(float(np.max(pp[inds])/max(pp[inds].sum(),1e-30)))
                p=(1+sum(v>=observed for v in null))/(permutations+1)
                rows.append({"night":night,"receiver":"s3" if rx else "d0wd",
                             "beacon":f"B{b}","bins":n,"period_min":period[best]/60,
                             "power_fraction":observed,"block_shuffle_p":p})
    # Benjamini-Hochberg adjusted values over all tested series.
    order=sorted(range(len(rows)),key=lambda i:rows[i]["block_shuffle_p"])
    adj=1.0
    for rank_i in range(len(order)-1,-1,-1):
        idx=order[rank_i]; rank=rank_i+1
        adj=min(adj,rows[idx]["block_shuffle_p"]*len(rows)/rank)
        rows[idx]["bh_q"] = min(adj,1.0)
    return rows


def replicated_change_tests(a):
    """Session-max same-sign step test using exact circular-shift nulls.

    The longest jointly observed contiguous minute segment is used. Circularly
    shifting one receiver preserves both marginal series and its autocorrelation
    while destroying absolute-time alignment.
    """
    rows=[]
    for night in range(1,9):
        for b in (1,2,3):
            series=[]
            for rx in (0,1):
                q=a[(a["night"]==night)&(a["receiver"]==rx)&(a["beacon"]==b)]
                series.append({int(z["bin"]):float(z["arb"]) for z in q})
            common=sorted(set(series[0])&set(series[1]))
            if not common: continue
            cuts=np.r_[0,np.flatnonzero(np.diff(common)!=1)+1,len(common)]
            lo,hi=max(zip(cuts[:-1],cuts[1:]),key=lambda z:z[1]-z[0])
            tt=np.array(common[lo:hi]); x=np.array([series[0][t] for t in tt]); y=np.array([series[1][t] for t in tt])
            for w in (5,15,30):
                n=len(x)
                if n<2*w+5: continue
                def shifts(z):
                    windows=np.lib.stride_tricks.sliding_window_view(z,w)
                    med=np.median(windows,axis=1)
                    return med[w:]-med[:-w]
                sx=shifts(x); sy=shifts(y)
                score=np.where(np.sign(sx)==np.sign(sy),np.minimum(np.abs(sx),np.abs(sy))/UNIT,0)
                ib=int(np.argmax(score)); obs=float(score[ib]); boundary=int(tt[w+ib])
                null=[]
                for lag in range(1,n):
                    sy0=shifts(np.roll(y,lag))
                    sc=np.where(np.sign(sx)==np.sign(sy0),np.minimum(np.abs(sx),np.abs(sy0))/UNIT,0)
                    null.append(float(np.max(sc)))
                p=(1+sum(v>=obs for v in null))/(1+len(null))
                rows.append({"night":night,"beacon":f"B{b}","window_min":w,
                             "contiguous_bins":n,"boundary_abs_min":boundary,
                             "d0wd_shift_sd":float(sx[ib]/UNIT),"s3_shift_sd":float(sy[ib]/UNIT),
                             "min_same_sign_score_sd":obs,"circular_shift_max_p":p})
    order=sorted(range(len(rows)),key=lambda i:rows[i]["circular_shift_max_p"]); adj=1.0
    for ri in range(len(order)-1,-1,-1):
        idx=order[ri]; rank=ri+1
        adj=min(adj,rows[idx]["circular_shift_max_p"]*len(rows)/rank)
        rows[idx]["bh_q"]=min(adj,1.0)
    return rows


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--multiscale",required=True)
    ap.add_argument("--out",required=True); ap.add_argument("--permutations",type=int,default=200)
    args=ap.parse_args(); root=Path(args.multiscale); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    all_summary=[]; all_states=[]
    for scale in (10,60,300):
        a=load_scale(root,scale); detail,summary,states=cross_and_states(a,scale)
        if scale==60: write_csv(out/"double_difference_minute_detail.csv",detail)
        all_summary+=summary; all_states+=states
    write_csv(out/"double_difference_summary.csv",all_summary)
    write_csv(out/"state_duration_summary.csv",all_states)
    minute=load_scale(root,60)
    cp=change_points(minute); write_csv(out/"change_points.csv",cp)
    write_csv(out/"change_point_controls.csv",change_controls(minute,cp))
    write_csv(out/"replicated_change_tests.csv",replicated_change_tests(minute))
    per=periodogram_tests(load_scale(root,300),args.permutations); write_csv(out/"periodicity.csv",per)
    manifest={"unit_sd":UNIT,"change_windows_min":[5,15,30],
              "periodicity_block_min":30,"periodicity_permutations":args.permutations,
              "change_candidates":len(cp),"periodicity_series":len(per)}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(manifest))


if __name__=="__main__": main()
