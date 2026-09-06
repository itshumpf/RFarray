import numpy as np, statistics as st, glob, os
import os, sys
W=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "cache", "windows")
B={"28:05:a5:2f:fa:48":"B2","a4:f0:0f:77:91:20":"B1","f4:2d:c9:70:72:30":"B3"}
STAMP={"20260829_025355":1,"20260830_013943":2,"20260831_020408":3,"20260901_035805":4,
       "20260902_000949":5,"20260903_013851":6,"20260904_010024":7}
SDC=0.053; SDS=0.00237
data={}
for f in glob.glob(W+"/*.npz"):
    tag=os.path.basename(f)[:-4]; rx,s=tag.split("_",1); n=STAMP[s]
    z=np.load(f)
    for m in z.files:
        if m in B: data[(n,rx,B[m])]=z[m][np.argsort(z[m][:,0])]

NB=8   # blocks per 2300 s window -> ~288 s each
def blocks(a,col):
    out=[]
    for i in range(NB):
        seg=a[len(a)*i//NB:len(a)*(i+1)//NB]
        if len(seg)>=15: out.append(float(np.median(seg[:,col])))
        else: out.append(None)
    return out

for col,name,SD,u in ((1,"CFO",SDC,"Hz"),(2,"SFO",SDS,"rad/sc")):
    print("="*92)
    print(f"{name} VARIOGRAM — median |difference| vs time separation, in units of {SD} {u}")
    print("="*92)
    print(f"  {'separation':<22}{'s3':>10}{'d0wd':>10}   n pairs (s3/d0wd)")
    lags=[(1,"~5 min  (1 block)"),(2,"~10 min (2 blocks)"),(4,"~19 min (4 blocks)"),
          (7,"~34 min (7 blocks)")]
    for k,lab in lags:
        row={}
        for rx in ('s3','d0wd'):
            ds=[]
            for b in ('B2','B1','B3'):
                for n in range(1,8):
                    a=data.get((n,rx,b))
                    if a is None: continue
                    bl=blocks(a,col)
                    for i in range(NB-k):
                        if bl[i] is not None and bl[i+k] is not None:
                            ds.append(abs(bl[i+k]-bl[i])/SD)
            row[rx]=(st.median(ds),len(ds)) if ds else (float('nan'),0)
        print(f"  {lab:<22}{row['s3'][0]:>10.2f}{row['d0wd'][0]:>10.2f}   "
              f"{row['s3'][1]}/{row['d0wd'][1]}")
    # between-night, full-window medians
    for k in (1,2,3):
        row={}
        for rx in ('s3','d0wd'):
            ds=[]
            for b in ('B2','B1','B3'):
                for n in range(1,8-k):
                    a1,a2=data.get((n,rx,b)),data.get((n+k,rx,b))
                    if a1 is None or a2 is None: continue
                    ds.append(abs(np.median(a2[:,col])-np.median(a1[:,col]))/SD)
            row[rx]=(st.median(ds),len(ds)) if ds else (float('nan'),0)
        lab = f"{k} night apart" if k==1 else f"{k} nights apart"
        print(f"  {lab:<22}{row['s3'][0]:>10.2f}"
              f"{row['d0wd'][0]:>10.2f}   {row['s3'][1]}/{row['d0wd'][1]}")
    print()
