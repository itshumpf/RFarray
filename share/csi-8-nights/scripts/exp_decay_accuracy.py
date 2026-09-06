import numpy as np, glob, os, sys, statistics as st
import os
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from rff.discriminator import Discriminator
B={"28:05:a5:2f:fa:48":"B2","a4:f0:0f:77:91:20":"B1","f4:2d:c9:70:72:30":"B3"}
E=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","per_window_features","decay","enr")
NIGHT={"20260901_035805":4,"20260902_000949":5,"20260904_010024":7}
TS=[600,4200,7800,11400,15000,18600]
def load(tag,t):
    p=f"{E}/{tag}@{t}.npz"
    if not os.path.exists(p): return {}
    z=np.load(p)
    return {m: z[m][:,1:3] for m in z.files if m in B and len(z[m])>=10}  # cols cfo,sfo
caps=sorted({os.path.basename(f).split("@")[0] for f in glob.glob(E+"/*.npz")})
print(f"captures: {len(caps)}   enrollment t=600 s, tests at +1..+5 h\n")
rows={}
for cap in caps:
    rx=cap.split("_")[0]; night=NIGHT[cap.split("_",1)[1]]
    tr=load(cap,600)
    if len(tr)<2: continue
    d=Discriminator()
    for m,a in tr.items():
        for f in a: d.learn(m,f)
    for t in TS:
        te=load(cap,t)
        if t==600:   # honest self point: 60/40 chronological, like rff_offline
            d2=Discriminator(); ok=tot=0
            for m,a in tr.items():
                cut=max(int(len(a)*0.6),1)
                for f in a[:cut]: d2.learn(m,f)
            for m,a in tr.items():
                for f in a[int(len(a)*0.6):]:
                    b,_,v=d2.classify(f)
                    if v=="UNSCORED": continue
                    tot+=1; ok+= (v!="STRANGER" and b==m)
        else:
            ok=tot=0
            for m,a in te.items():
                if m not in tr: continue
                for f in a:
                    b,_,v=d.classify(f)
                    if v=="UNSCORED": continue
                    tot+=1; ok+= (v!="STRANGER" and b==m)
        if tot: rows.setdefault((t-600)/3600.0,[]).append((night,rx,100*ok/tot,tot,len(te or tr)))
print("="*88)
print("IDENTIFICATION ACCURACY vs HOURS SINCE ENROLLMENT")
print("  enrolled once on a 300 s block, then asked to name the transmitter later")
print("="*88)
print(f"  {'hours':>6}{'median acc':>12}{'min':>8}{'max':>8}{'cells':>7}{'classes':>9}   chance")
for h in sorted(rows):
    v=[a for _,_,a,_,_ in rows[h]]; k=st.median([c for _,_,_,_,c in rows[h]])
    print(f"  {h:>6.1f}{st.median(v):>11.1f}%{min(v):>7.1f}%{max(v):>7.1f}%{len(v):>7}"
          f"{k:>9.0f}   {100/k:>5.1f}%")
print("\nper capture:")
print(f"  {'night':>5} {'rx':<5}" + "".join(f"{f'+{h:.0f}h':>9}" for h in sorted(rows)))
for night in (4,5,7):
    for rx in ('s3','d0wd'):
        cells=[]
        for h in sorted(rows):
            m=[a for n,r,a,_,_ in rows[h] if n==night and r==rx]
            cells.append(f"{m[0]:>8.1f}%" if m else f"{'--':>9}")
        print(f"  {night:>5} {rx:<5}" + "".join(cells))
