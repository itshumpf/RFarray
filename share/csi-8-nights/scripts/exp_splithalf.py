import numpy as np, statistics as st, glob, os, math
import os, sys
W=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".." , "per_window_features", "windows")
B={"28:05:a5:2f:fa:48":"B2","a4:f0:0f:77:91:20":"B1","f4:2d:c9:70:72:30":"B3"}
STAMP={"20260829_025355":1,"20260830_013943":2,"20260831_020408":3,"20260901_035805":4,
       "20260902_000949":5,"20260903_013851":6,"20260904_010024":7}
SDC=0.053; SDS=0.00237
data={}
for f in glob.glob(W+"/*.npz"):
    tag=os.path.basename(f)[:-4]; rx,s=tag.split("_",1); n=STAMP[s]
    z=np.load(f)
    for m in z.files:
        if m in B: data[(n,rx,B[m])]=z[m]          # cols: ts, cfo, sfo

def halves(a, col):
    a=a[np.argsort(a[:,0])]
    k=len(a)//2
    return float(np.median(a[:k,col])), float(np.median(a[k:,col])), float(np.median(a[:,col]))

for col,name,SD,unit,fmt in ((1,"CFO",SDC,"Hz","{:+.3f}"),(2,"SFO",SDS,"rad/sc","{:+.4f}")):
    print("="*100)
    print(f"{name}  —  split-half within one night  vs  night-to-night   (yardstick {SD} {unit})")
    print("="*100)
    print(f"  {'rx':<5}{'bcn':<4}{'nights':>7}{'med |h1-h2|':>13}{'in sig':>8}"
          f"{'med |n->n+1|':>14}{'in sig':>8}   ratio  verdict")
    for rx in ('s3','d0wd'):
        for b in ('B2','B1','B3'):
            wi=[]; full={}
            for n in range(1,8):
                a=data.get((n,rx,b))
                if a is None or len(a)<40: continue
                h1,h2,fu=halves(a,col); wi.append(abs(h1-h2)); full[n]=fu
            if len(full)<3: continue
            be=[abs(full[n+1]-full[n]) for n in range(1,7) if n in full and n+1 in full]
            mw,mb=st.median(wi),st.median(be)
            # variance decomposition: Var(h1-h2)=4*Var(full median) under exchangeability
            var_meas=st.mean([d*d for d in wi])/4.0
            var_tot=st.variance(list(full.values()))
            var_drift=var_tot-var_meas
            sd_drift=math.sqrt(var_drift) if var_drift>0 else 0.0
            v=("no detectable drift" if var_drift<=0 else
               f"drift SD {fmt.format(sd_drift)} = {sd_drift/SD:.2f} sig")
            print(f"  {rx:<5}{b:<4}{len(full):>7}{mw:>13.4g}{mw/SD:>8.2f}"
                  f"{mb:>14.4g}{mb/SD:>8.2f}{mb/mw:>8.2f}   {v}")
    print(f"\n  Under pure measurement noise the split-half gap should be ~1.41x LARGER than the")
    print(f"  night-to-night gap (each half has half the windows). Ratio column is night/half:")
    print(f"    ratio ~0.7 = pure noise, no between-night drift")
    print(f"    ratio >>1 = real between-night drift on top of the noise\n")
