import json, statistics as st, itertools, math
import os
B={"28:05:a5:2f:fa:48":"B2","a4:f0:0f:77:91:20":"B1","f4:2d:c9:70:72:30":"B3"}
SD=0.00237
P={}
for l in open("os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","data","cache","decay","decay.jsonl")"):
    d=json.loads(l[5:])
    for m,v in d["src"].items():
        if m in B: P.setdefault((d["tag"],B[m]),{})[d["t"]]=v["sfo"]
pairs=[]
for (tag,b),s in P.items():
    rx=tag.split("_")[0]
    for x,y in itertools.combinations(sorted(s),2):
        pairs.append(((y-x)/3600.0, abs(s[y]-s[x])/SD, rx, b, tag))
caps=sorted({t for _,_,_,_,t in pairs})
print(f"{len(pairs)} within-session pairs from {len(caps)} captures, "
      f"{len({(t,b) for _,_,_,b,t in pairs})} capture-beacon streams")

BINS=[(0,.25),(.25,.5),(.5,1),(1,1.5),(1.5,2),(2,3),(3,4),(4,6),(6,9),(9,13),(13,21)]
def med(f):
    v=[d for l,d,rx,b,t in pairs if f(l,rx,b)]
    return (st.median(v),len(v)) if v else (float('nan'),0)
print("\n"+"="*94)
print("THE DECAY CURVE — median |dSFO| within one continuous power-on, in BETWEEN_UNIT_SD")
print("="*94)
print(f"  {'lag':<12}{'all':>8}{'n':>6}{'s3':>8}{'n':>5}{'d0wd':>8}{'n':>5}   {'sqrt-t model':>13}")
ref=None
for lo,hi in BINS:
    a,na=med(lambda l,rx,b,lo=lo,hi=hi: lo<=l<hi)
    s,ns=med(lambda l,rx,b,lo=lo,hi=hi: lo<=l<hi and rx=='s3')
    d,nd=med(lambda l,rx,b,lo=lo,hi=hi: lo<=l<hi and rx=='d0wd')
    mid=(lo+hi)/2
    if ref is None and na>0 and not math.isnan(a): ref=(mid,a)
    if ref is None:
        print(f"  {f'{lo:g}-{hi:g} h':<12}{'--':>8}{na:>6}"); continue
    proj=ref[1]*math.sqrt(mid/ref[0])
    print(f"  {f'{lo:g}-{hi:g} h':<12}{a:>8.2f}{na:>6}{s:>8.2f}{ns:>5}{d:>8.2f}{nd:>5}   {proj:>13.2f}")
print("\n  'sqrt-t model' = what an unbounded random walk anchored at the first bin predicts.")
print("  The curve leaving that column behind means the wander is BOUNDED, not diffusive.")

print("\n"+"="*94); print("PER BEACON"); print("="*94)
print(f"  {'lag':<12}" + "".join(f"{b:>17}" for b in ('B2','B1','B3')))
for lo,hi in BINS:
    row=[]
    for b in ('B2','B1','B3'):
        v,n=med(lambda l,rx,bb,b=b,lo=lo,hi=hi: lo<=l<hi and bb==b)
        row.append(f"{v:>11.2f}({n:>3})" if n else f"{'--':>17}")
    print(f"  {f'{lo:g}-{hi:g} h':<12}" + "".join(row))

print("\n"+"="*94)
print("CROSSINGS — first lag at which the median wander reaches each threshold")
print("="*94)
for thr in (0.25,0.5,1.0,2.0,3.0):
    hit=None
    for lo,hi in BINS:
        a,n=med(lambda l,rx,b,lo=lo,hi=hi: lo<=l<hi)
        if n and a>=thr: hit=(lo,hi); break
    print(f"  {thr:>4} sig : " + (f"{hit[0]:g}-{hit[1]:g} h" if hit else "never, inside 21 h"))

print("\n"+"="*94)
print("IS THE BOUNDARY TIME, OR THE POWER CYCLE?")
print("="*94)
lat=[d for l,d,rx,b,t in pairs if l>=6]
print(f"  within ONE power-on, lag >= 6 h : median {st.median(lat):.2f} sig   (n={len(lat)})")
n11={'s3':{'B2':[5.6,5.8,0.4,1.9,0.2,0.3],'B3':[0.3,0.6,0.0,6.3,7.0,0.8],'B1':[7.0,0.3,0.8,1.6]},
     'd0wd':{'B2':[2.4,0.8,0.9,3.5,3.5,0.3],'B3':[30.5,26.2,11.5,15.2,8.2,9.3],'B1':[10.0,23.5,1.5,1.9]}}
allb=[x for rx in n11 for b in n11[rx] for x in n11[rx][b]]
print(f"  ACROSS a power cycle (~24 h, sec.11) : median {st.median(allb):.2f} sig   (n={len(allb)})")
for b in ('B2','B1','B3'):
    w=[d for l,d,rx,bb,t in pairs if l>=6 and bb==b]
    a=[x for rx in n11 for x in n11[rx][b]]
    ws=f"{st.median(w):.2f} (n={len(w)})" if w else "--"
    print(f"    {b}: within one power-on >=6 h {ws:<16} across a power cycle {st.median(a):.2f} (n={len(a)})")
