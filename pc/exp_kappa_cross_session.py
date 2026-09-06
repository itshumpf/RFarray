#!/usr/bin/env python3
"""Does `kappa` (transmitter IQ imbalance) survive the cross-session test
that killed the SFO slope?

Pre-registered design, thresholds and caveats: docs/KAPPA_CROSS_SESSION.md
(Stage 1 written and saved before this file was run).

Read-only on data/raw/. Opens no serial port. Modifies nothing in pc/rff/ and
nothing in pc/exp_iq_imbalance.py -- the kappa estimator is IMPORTED from it,
never reimplemented, so this pass cannot disagree with docs/IQ_IMBALANCE.md
about what kappa is.

  scan <csv> --tag T   run the imported estimator over one capture
  floors               how many sessions/devices clear MIN_WIN (run first)
  score                H1, H2, and the controls
  report               print the scored result
  verify               show this file's classifier == the shipped one

WHY A LOCAL CLASSIFIER EXISTS HERE (docs/KAPPA_CROSS_SESSION.md 4)
------------------------------------------------------------------
pc/rff/discriminator.py:27 sets _VAR_FLOOR = [1.0, 1e-8], in CFO Hz^2 and
SFO (rad/subcarrier)^2. Those are physical units of the SLOPE feature.
kappa is a dimensionless ratio of order 1e-2, so the shipped floor is about
1e6 times kappa's own scale on the first axis: every ellipse inflates until
every observation matches every model, and the resulting accuracy is an
artifact of a unit mismatch rather than a measurement.

So features are standardized (z-scored on the ENROLLMENT half only, never the
test half) and the floor is applied in that standardized space. `verify`
demonstrates that with shipped units and shipped floors this file's Mahal
class reproduces pc/rff/discriminator.py exactly, so the only difference
between the two is the standardization this document declares.

CONSEQUENCE, from the pre-registration: numbers here are NOT comparable to
any figure produced at the shipped floors, including 99.7%/7,497 and
95.7%/14,234. They are comparable only to the slope figure this same pass
computes on the same cells under the same standardization.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exp_iq_imbalance as iq                                  # noqa: E402
from rff.discriminator import Discriminator as ShippedDisc     # noqa: E402

CACHE = os.environ.get("KXS_CACHE", "/tmp/kxs")

# ---- frozen in docs/KAPPA_CROSS_SESSION.md 2-3, not tunable from the CLI
MIN_WIN = 10                     # cells per (session, device); 3
R_CM_COMMON = 0.25               # 2.1
R_CM_NONE = 1.00                 # 2.1
SEED = 20260827                  # 5, N1
MIN_CHARACTERIZED = 5            # matches Discriminator.MIN_CHARACTERIZED
CHI2 = {1: 6.635, 2: 9.210, 3: 11.345}   # 99th pct, df 1..3

# ---- docs/KAPPA_SLOPE_FUSION.md. NOISE occupies the slope's slot at the
# slope's variance and carries no information; whatever it buys is the
# dimensionality premium and is subtracted from the claim (that doc 2).
FUSE_ARMS = {
    "F3": dict(fused=("kre", "kim", "sfo"), noise=("kre", "kim", "NOISE"),
               comps={"kappa": ("kre", "kim"), "slope": ("sfo",)}),
    "F2": dict(fused=("karg", "sfo"), noise=("karg", "NOISE"),
               comps={"kappa": ("karg",), "slope": ("sfo",)}),
}

BEACONS = ("a4:f0:0f:77:91:20", "f4:2d:c9:70:72:30", "28:05:a5:2f:fa:48")


# ------------------------------------------------------------------ model

class Mahal:
    """Dimension-generic Gaussian model. Same Welford update, same chi2 gate
    and same MIN_CHARACTERIZED as pc/rff/discriminator.py; the only thing
    that differs is that the variance floor is a parameter instead of a
    module constant in CFO/SFO units. `verify` checks the equivalence."""

    def __init__(self, dim, floor):
        self.dim = dim
        self.floor = np.asarray(floor, dtype=np.float64)
        self.n = 0
        self.mean = np.zeros(dim)
        self._m2 = np.zeros((dim, dim))

    def update(self, x):
        x = np.asarray(x, dtype=np.float64)
        self.n += 1
        d = x - self.mean
        self.mean += d / self.n
        self._m2 += np.outer(d, x - self.mean)

    @property
    def cov(self):
        c = (np.diag(self.floor) if self.n < 2
             else (self._m2 / (self.n - 1)).copy())
        for i in range(self.dim):
            c[i, i] = max(c[i, i], self.floor[i])
        return c

    def d2(self, x):
        d = np.asarray(x, dtype=np.float64) - self.mean
        try:
            return float(d @ np.linalg.solve(self.cov, d))
        except np.linalg.LinAlgError:
            return float("inf")


class Library:
    def __init__(self, dim, floor):
        self.dim, self.floor = dim, floor
        self.models = {}

    def learn(self, sid, x):
        self.models.setdefault(sid, Mahal(self.dim, self.floor)).update(x)

    def usable(self):
        return [s for s, m in self.models.items() if m.n >= MIN_CHARACTERIZED]

    def classify(self, x):
        best, bd = None, float("inf")
        for sid, m in self.models.items():
            if m.n < MIN_CHARACTERIZED:
                continue
            d = m.d2(x)
            if d < bd:
                best, bd = sid, d
        if best is None:
            return None, float("inf"), "UNSCORED"
        return (best, bd,
                "STRANGER" if bd > CHI2[self.dim] else "MATCH")


# ------------------------------------------------------------------- data

def session_of(tag):
    """'d0wd_20260822_023034' -> ('d0wd', '20260822_023034')."""
    p = tag.split("_", 1)
    return (p[0], p[1]) if len(p) == 2 else (tag, "")


def cells_of(tag, svar="strue"):
    """-> {mac: [(t_lo, featdict)]} for cells passing the 3 admission rules.

    detected2 is docs/IQ_IMBALANCE.md 10.3's pre-registered alignment
    detection. A cell that does not clear it has no measured kappa, and a
    non-measurement is never scored as though it were one."""
    st = iq.load(tag, svar)
    out = defaultdict(list)
    kept = dropped = 0
    for (mac, chunk), cell in st.cells.items():
        f = iq.features(cell)
        if f is None:
            dropped += 1
            continue
        if not f.get("detected2"):
            dropped += 1
            continue
        if not np.isfinite(f["slope_med"]):
            dropped += 1
            continue
        out[mac].append((cell.t_lo if cell.t_lo is not None else chunk, f))
        kept += 1
    for m in out:
        out[m].sort(key=lambda r: r[0])
    return dict(out), kept, dropped


def vec(f, arm, which):
    """Feature vector. arm A/B/C x which 'kappa'|'slope'; see prereg 4.1."""
    k = f["kappa"]
    if which == "kappa":
        if arm == "A":
            return np.array([k.real, k.imag])
        if arm == "B":
            return np.array([math.atan2(k.imag, k.real)])
        return np.array([abs(k)])
    if arm == "A":
        # the shipped 2-D slope feature carries a dead CFO axis
        # (SEPARATION_SCALING 3.3: 0.01-0.21 sigma). Reproduced honestly:
        # the second axis is the slope, the first is what the pipeline has.
        return np.array([f.get("rssi", 0.0), f["slope_med"]])
    return np.array([f["slope_med"]])


# --------------------------------------------------------------- H1 tests

def circmean(a):
    return math.atan2(float(np.mean(np.sin(a))), float(np.mean(np.cos(a))))


def circspread(a):
    """Circular sd (Mardia): sqrt(-2 ln R). 0 = identical directions."""
    R = math.hypot(float(np.mean(np.sin(a))), float(np.mean(np.cos(a))))
    R = min(max(R, 1e-12), 1.0)
    return math.sqrt(max(-2.0 * math.log(R), 0.0))


def wrap(x):
    return (x + math.pi) % (2 * math.pi) - math.pi


def session_kappa(cells):
    """{mac: complex} coherent mean kappa per device for one session."""
    return {m: complex(np.mean([f["kappa"] for _, f in v]))
            for m, v in cells.items() if len(v) >= MIN_WIN}


def h1(sessions):
    """Per receiver, per ordered adjacent pair: is the rotation shared?"""
    rows = []
    for rx, tags in sessions.items():
        for a, b in zip(tags, tags[1:]):
            ka, kb = session_kappa(a[2]), session_kappa(b[2])
            common = [m for m in BEACONS if m in ka and m in kb]
            if len(common) < 3:
                rows.append(dict(rx=rx, a=a[1], b=b[1], n=len(common),
                                 verdict="FLOOR"))
                continue
            d = np.array([wrap(np.angle(kb[m]) - np.angle(ka[m]))
                          for m in common])
            mu, sp = circmean(d), circspread(d)
            R = sp / abs(mu) if abs(mu) > 1e-9 else float("inf")
            # fraction of rotation energy a single shared rotation removes,
            # directly comparable to IDENTITY_STABILITY 13's 7-46% for slope
            tot = float(np.sum(np.abs(d) ** 2))
            res = float(np.sum(np.abs(np.array([wrap(x - mu)
                                                for x in d])) ** 2))
            frac = 1.0 - res / tot if tot > 0 else float("nan")
            rows.append(dict(rx=rx, a=a[1], b=b[1], n=len(common),
                             deg=[math.degrees(x) for x in d],
                             mean_deg=math.degrees(mu),
                             spread_deg=math.degrees(sp), R_cm=R,
                             energy_removed=frac,
                             verdict=("COMMON-MODE" if R <= R_CM_COMMON else
                                      "NOT COMMON-MODE" if R > R_CM_NONE
                                      else "PARTIAL")))
    return rows


# --------------------------------------------------------------- H2 tests

def standardize(enroll, test):
    """z-score on the POOLED WITHIN-DEVICE covariance of enroll only.

    Within-device, so the scale is set by how much a device moves, not by
    how far apart the devices are -- standardizing on the between-device
    spread would hand the classifier the answer."""
    dim = len(next(iter(next(iter(enroll.values()))), np.zeros(1)))
    acc = []
    for xs in enroll.values():
        X = np.asarray(xs, dtype=np.float64)
        if len(X) >= 2:
            acc.append(X - X.mean(axis=0))
    if not acc:
        return None, None
    W = np.vstack(acc)
    sd = W.std(axis=0, ddof=1)
    sd = np.where(sd > 0, sd, 1.0)
    z = lambda D: {m: [np.asarray(x) / sd for x in xs] for m, xs in D.items()}
    return z(enroll), z(test)


def evaluate(enroll, test, dim):
    """Same shape as exp_identity_stability.evaluate: A_gated and A_nn, with
    N classes carried alongside every number (IDENTITY_STABILITY 1.3)."""
    e, t = standardize(enroll, test)
    if e is None:
        return None
    lib = Library(dim, np.full(dim, 1e-4))    # floor in standardized units
    for m, xs in e.items():
        for x in xs:
            lib.learn(m, x)
    ids = lib.usable()
    if len(ids) < 2:
        return None
    tot = cg = cn = st = 0
    conf = defaultdict(lambda: defaultdict(int))
    for m, xs in t.items():
        for x in xs:
            best, d2, verdict = lib.classify(x)
            if verdict == "UNSCORED":
                continue
            tot += 1
            if verdict == "STRANGER":
                st += 1
                conf[m]["<stranger>"] += 1
            else:
                conf[m][best] += 1
                cg += int(best == m)
            cn += int(best == m)
    if tot == 0:
        return None
    return dict(n_classes=len(ids), classes=sorted(ids), n_test=tot,
                A_gated=cg / tot, A_nn=cn / tot, strangers=st,
                conf={k: dict(v) for k, v in conf.items()})


def derot(cells, rot):
    """Remove a per-(receiver, session) common-mode rotation from kappa."""
    out = {}
    for m, v in cells.items():
        nv = []
        for t, f in v:
            g = dict(f)
            g["kappa"] = f["kappa"] * complex(math.cos(-rot), math.sin(-rot))
            nv.append((t, g))
        out[m] = nv
    return out


def feats(cells, arm, which, macs=None):
    d = {}
    for m, v in cells.items():
        if macs and m not in macs:
            continue
        if len(v) < MIN_WIN:
            continue
        d[m] = [vec(f, arm, which) for _, f in v]
    return d


def cross_session(sessions, arm, which, derotate, shuffle=False):
    """Ordered session pairs on ONE receiver. Never pooled across receivers
    (N2; BLIND_CLUSTERING 1)."""
    rng = np.random.default_rng(SEED)
    res = []
    for rx, tags in sessions.items():
        ref = tags[0][2]
        base = {}
        if derotate:
            k0 = session_kappa(ref)
            anchor = BEACONS[0]
            for _, name, c in tags:
                kk = session_kappa(c)
                if anchor in kk and anchor in k0:
                    base[name] = wrap(np.angle(kk[anchor])
                                      - np.angle(k0[anchor]))
                else:
                    base[name] = 0.0
        for i, (_, na, ca) in enumerate(tags):
            for j, (_, nb, cb) in enumerate(tags):
                if i == j:
                    continue
                A = derot(ca, base.get(na, 0.0)) if derotate else ca
                B = derot(cb, base.get(nb, 0.0)) if derotate else cb
                fa, fb = feats(A, arm, which), feats(B, arm, which)
                if shuffle:
                    ks = list(fb)
                    vs = [fb[k] for k in ks]
                    rng.shuffle(vs)
                    fb = dict(zip(ks, vs))
                common = set(fa) & set(fb)
                if len(common) < 2:
                    continue
                fa = {k: fa[k] for k in common}
                fb = {k: fb[k] for k in common}
                r = evaluate(fa, fb, 2 if arm == "A" else 1)
                if r:
                    r.update(rx=rx, a=na, b=nb)
                    res.append(r)
    return res


# ------------------------------------------- fusion (KAPPA_SLOPE_FUSION.md)

def comps_of(f):
    k = f["kappa"]
    return dict(kre=k.real, kim=k.imag, kabs=abs(k),
                karg=math.atan2(k.imag, k.real), sfo=f["slope_med"])


def build_comps(cells):
    return {m: [comps_of(f) for _, f in v]
            for m, v in cells.items() if len(v) >= MIN_WIN}


def assemble(D, spec, rng, sd_noise):
    """Component dicts -> feature vectors. NOISE is drawn at the slope's
    variance, measured on the ENROLLMENT half only (FUSION 2)."""
    out = {}
    for m, rows in D.items():
        out[m] = [np.array([(rng.normal(0.0, sd_noise) if c == "NOISE"
                             else r[c]) for c in spec], dtype=np.float64)
                  for r in rows]
    return out


def cross_session_spec(sessions, spec, derotate=True, shuffle=False,
                       seed=SEED):
    """Same pairing/standardization as cross_session, arbitrary components."""
    rng = np.random.default_rng(seed)
    res = []
    for rx, tags in sessions.items():
        base = {}
        if derotate:
            k0 = session_kappa(tags[0][2])
            anchor = BEACONS[0]
            for _, name, c in tags:
                kk = session_kappa(c)
                base[name] = (wrap(np.angle(kk[anchor]) - np.angle(k0[anchor]))
                              if anchor in kk and anchor in k0 else 0.0)
        for i, (_, na, ca) in enumerate(tags):
            for j, (_, nb, cb) in enumerate(tags):
                if i == j:
                    continue
                A = derot(ca, base.get(na, 0.0)) if derotate else ca
                B = derot(cb, base.get(nb, 0.0)) if derotate else cb
                da, db = build_comps(A), build_comps(B)
                common = sorted(set(da) & set(db))
                if len(common) < 2:
                    continue
                da = {k: da[k] for k in common}
                db = {k: db[k] for k in common}
                sd = float(np.std([r["sfo"] for rows in da.values()
                                   for r in rows], ddof=1))
                sd = sd if sd > 0 else 1.0
                fa = assemble(da, spec, rng, sd)
                fb = assemble(db, spec, rng, sd)
                if shuffle:
                    ks = list(fb)
                    vs = [fb[k] for k in ks]
                    rng.shuffle(vs)
                    fb = dict(zip(ks, vs))
                r = evaluate(fa, fb, len(spec))
                if r:
                    r.update(rx=rx, a=na, b=nb)
                    res.append(r)
    return res


def paired(a, b, rx="s3", n=3, B=4000, seed=SEED):
    """Paired bootstrap of median(a - b) over the pairs both share."""
    ka = {(r["a"], r["b"]): r["A_nn"] for r in a
          if r["rx"] == rx and r["n_classes"] == n}
    kb = {(r["a"], r["b"]): r["A_nn"] for r in b
          if r["rx"] == rx and r["n_classes"] == n}
    keys = sorted(set(ka) & set(kb))
    if len(keys) < 3:
        return None
    d = np.array([ka[k] - kb[k] for k in keys])
    rng = np.random.default_rng(seed)
    bs = np.array([np.median(rng.choice(d, len(d), replace=True))
                   for _ in range(B)])
    return dict(n=len(keys), med=float(np.median(d)),
                lo=float(np.percentile(bs, 2.5)),
                hi=float(np.percentile(bs, 97.5)),
                wins=int((d > 0).sum()))


def cmd_fuse(a):
    sessions, _ = load_all(a.tags) if getattr(a, "tags", None) else \
        load_all([t for t in _cached_tags()])
    out = {}
    print("\n" + "=" * 74)
    print("KAPPA + SLOPE FUSION -- docs/KAPPA_SLOPE_FUSION.md")
    print("s3 only, N=3.  NOISE = N(0, var(sfo)) from the ENROLL half, "
          f"seed {SEED}")
    print("=" * 74)
    for arm, cfg in FUSE_ARMS.items():
        runs = {"fused": cross_session_spec(sessions, cfg["fused"]),
                "noise": cross_session_spec(sessions, cfg["noise"])}
        for nm, sp in cfg["comps"].items():
            runs[nm] = cross_session_spec(sessions, sp)
        runs["p1_fused"] = within_spec(sessions, cfg["fused"])
        runs["n1_fused"] = cross_session_spec(sessions, cfg["fused"],
                                              shuffle=True)
        out[arm] = runs
        print(f"\n-- ARM {arm}   fused={'+'.join(cfg['fused'])}   "
              f"control={'+'.join(cfg['noise'])}")
        for nm in ("p1_fused", "fused", "noise", "kappa", "slope",
                   "n1_fused"):
            rs = [r for r in runs[nm] if r["rx"] == "s3"
                  and r["n_classes"] == 3]
            if not rs:
                print(f"   {nm:<10} no pair clears the floor")
                continue
            print(f"   {nm:<10} A_nn {100*med([r['A_nn'] for r in rs]):5.1f}%"
                  f"  A_gated {100*med([r['A_gated'] for r in rs]):5.1f}%"
                  f"  N=3  chance 33.3%  bar 66.7%"
                  f"  {len(rs)} pairs / {sum(r['n_test'] for r in rs)} tests")
        d = paired(runs["fused"], runs["noise"])
        out[arm + "_delta_info"] = d
        if d:
            verdict = ("INFORMATION" if d["lo"] > 0 else
                       "DIMENSIONALITY ONLY -- CI includes zero")
            print(f"\n   delta_info (fused - NOISE control): "
                  f"{100*d['med']:+.1f} pp  95% CI "
                  f"[{100*d['lo']:+.1f}, {100*d['hi']:+.1f}]  "
                  f"{d['wins']}/{d['n']} pairs  -> {verdict}")
        for nm in ("kappa", "slope"):
            p = paired(runs["fused"], runs[nm])
            out[f"{arm}_vs_{nm}"] = p
            if p:
                print(f"   fused - {nm:<6}: {100*p['med']:+.1f} pp  "
                      f"95% CI [{100*p['lo']:+.1f}, {100*p['hi']:+.1f}]  "
                      f"{p['wins']}/{p['n']}")
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, "fuse.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"\n  -> {os.path.join(CACHE, 'fuse.json')}\n")
    return 0


def within_spec(sessions, spec, seed=SEED):
    rng = np.random.default_rng(seed)
    res = []
    for rx, tags in sessions.items():
        for _, name, c in tags:
            d = build_comps(c)
            en, te = {}, {}
            for m, rows in d.items():
                cut = int(len(rows) * 0.6)
                if cut < MIN_CHARACTERIZED or len(rows) - cut < 1:
                    continue
                en[m], te[m] = rows[:cut], rows[cut:]
            if len(en) < 2:
                continue
            sd = float(np.std([r["sfo"] for rows in en.values()
                               for r in rows], ddof=1)) or 1.0
            r = evaluate(assemble(en, spec, rng, sd),
                         assemble(te, spec, rng, sd), len(spec))
            if r:
                r.update(rx=rx, a=name, b=name)
                res.append(r)
    return res


def _cached_tags():
    import glob
    return sorted(os.path.basename(p).replace("_strue_scan.pkl", "")
                  for p in glob.glob(os.path.join(CACHE, "*_strue_scan.pkl")))


def within_session(sessions, arm, which):
    """P1 positive control: first 60% enroll, last 40% test, chronological."""
    res = []
    for rx, tags in sessions.items():
        for _, name, c in tags:
            en, te = {}, {}
            for m, v in c.items():
                if len(v) < MIN_WIN:
                    continue
                cut = int(len(v) * 0.6)
                if cut < MIN_CHARACTERIZED or len(v) - cut < 1:
                    continue
                en[m] = [vec(f, arm, which) for _, f in v[:cut]]
                te[m] = [vec(f, arm, which) for _, f in v[cut:]]
            if len(en) < 2:
                continue
            r = evaluate(en, te, 2 if arm == "A" else 1)
            if r:
                r.update(rx=rx, a=name, b=name)
                res.append(r)
    return res


# ------------------------------------------------------------------- cmds

def load_all(tags):
    sessions = defaultdict(list)
    acct = []
    for t in tags:
        rx, when = session_of(t)
        try:
            c, kept, dropped = cells_of(t)
        except FileNotFoundError:
            print(f"  no scan cache for {t} -- run `scan` first",
                  file=sys.stderr)
            continue
        clears = {m: len(v) for m, v in c.items() if len(v) >= MIN_WIN}
        acct.append(dict(tag=t, rx=rx, when=when, cells_kept=kept,
                         cells_dropped=dropped, devices=len(c),
                         clearing=clears))
        if clears:
            sessions[rx].append((when, t, c))
    for rx in sessions:
        sessions[rx].sort(key=lambda r: r[0])
    return dict(sessions), acct


def cmd_scan(a):
    ns = argparse.Namespace(path=a.path, tag=a.tag, convention="divided",
                            svar="strue", max_rows=a.max_rows,
                            seconds=a.seconds, resume=a.resume)
    iq.run_scan(ns)


def cmd_floors(a):
    _, acct = load_all(a.tags)
    print(f"\nFLOOR ACCOUNTING  (MIN_WIN = {MIN_WIN} cells of "
          f"{iq.CHUNK_S:.0f} s per (session, device))\n")
    for r in acct:
        cl = r["clearing"]
        print(f"  {r['tag']:<28} kept={r['cells_kept']:>4} "
              f"dropped={r['cells_dropped']:>4} devices={r['devices']:>3} "
              f"clearing={len(cl)}")
        for m, n in sorted(cl.items(), key=lambda kv: -kv[1]):
            print(f"       {m}  {n:>4} cells"
                  f"{'   <-- beacon' if m in BEACONS else ''}")
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, "floors.json"), "w") as f:
        json.dump(acct, f, indent=1)
    print(f"\n  -> {os.path.join(CACHE, 'floors.json')}")


def cmd_score(a):
    sessions, acct = load_all(a.tags)
    if not sessions:
        print("no session clears the floor; nothing to score", file=sys.stderr)
        return 1
    out = dict(min_win=MIN_WIN, seed=SEED, chunk_s=iq.CHUNK_S,
               accounting=acct, h1=h1(sessions), arms={})
    common = all(r.get("verdict") == "COMMON-MODE"
                 for r in out["h1"] if r.get("verdict") != "FLOOR")
    out["h1_common"] = bool(common) and any(
        r.get("verdict") == "COMMON-MODE" for r in out["h1"])
    for arm in ("A", "B", "C"):
        out["arms"][arm] = dict(
            kappa_raw=cross_session(sessions, arm, "kappa", False),
            kappa_derot=cross_session(sessions, arm, "kappa", True),
            slope=cross_session(sessions, arm, "slope", False),
            p1_kappa=within_session(sessions, arm, "kappa"),
            p1_slope=within_session(sessions, arm, "slope"),
            n1_shuffle=cross_session(sessions, arm, "kappa", True,
                                     shuffle=True))
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, "score.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"scored -> {os.path.join(CACHE, 'score.json')}")
    return 0


def med(v):
    return float(np.median(v)) if v else float("nan")


def summarize(res):
    if not res:
        return None
    ns = sorted({r["n_classes"] for r in res})
    return dict(pairs=len(res), n_classes=ns,
                nmed=int(np.median([r["n_classes"] for r in res])),
                A_nn=med([r["A_nn"] for r in res]),
                A_gated=med([r["A_gated"] for r in res]),
                tests=int(sum(r["n_test"] for r in res)))


def cmd_report(a):
    with open(os.path.join(CACHE, "score.json")) as f:
        o = json.load(f)
    print("\n" + "=" * 72)
    print("KAPPA CROSS-SESSION -- docs/KAPPA_CROSS_SESSION.md")
    print(f"MIN_WIN={o['min_win']}  chunk={o['chunk_s']:.0f}s  "
          f"seed={o['seed']}")
    print("=" * 72)

    print("\n-- H1  is the per-session kappa rotation common-mode? "
          f"(bar: R_cm <= {R_CM_COMMON})")
    for r in o["h1"]:
        if r.get("verdict") == "FLOOR":
            print(f"  {r['rx']:<5} {r['a']} -> {r['b']}   "
                  f"only {r['n']} beacons clear the floor -- FLOOR")
            continue
        print(f"  {r['rx']:<5} {r['a']} -> {r['b']}")
        print(f"      per-beacon rotation: "
              f"{', '.join(f'{d:+.1f}deg' for d in r['deg'])}")
        print(f"      mean {r['mean_deg']:+.1f}deg   "
              f"spread {r['spread_deg']:.1f}deg   "
              f"R_cm {r['R_cm']:.3f}   "
              f"energy removed {100*r['energy_removed']:.1f}%   "
              f"{r['verdict']}")

    for arm, label in (("A", "PRIMARY  kappa=[Re,Im] 2-D vs slope 2-D"),
                       ("B", "FAIR 1-D  kappa=[arg] vs slope=[sfo]"),
                       ("C", "kappa=[|k|] -- not to be quoted alone (4.1)")):
        d = o["arms"][arm]
        print(f"\n-- ARM {arm}   {label}")
        for key, name in (("p1_kappa", "P1 within-session kappa"),
                          ("p1_slope", "P1 within-session slope"),
                          ("kappa_raw", "H2 cross-session kappa, raw"),
                          ("kappa_derot", "H2 cross-session kappa, derot"),
                          ("slope", "H2 cross-session slope"),
                          ("n1_shuffle", "N1 label-shuffle control")):
            s = summarize(d[key])
            if not s:
                print(f"   {name:<34} no pair clears the floor")
                continue
            n = s["nmed"]
            print(f"   {name:<34} A_nn {100*s['A_nn']:5.1f}%  "
                  f"A_gated {100*s['A_gated']:5.1f}%  "
                  f"N={s['n_classes']}  chance {100/n:4.1f}%  "
                  f"bar(2/N) {200/n:4.1f}%  "
                  f"{s['pairs']} pairs / {s['tests']} tests")

    # Stratified by (receiver, N). The pooled medians above mix N=2 and N=3
    # pairs into one number, which IDENTITY_STABILITY 1.3 forbids quoting.
    # docs/KAPPA_CROSS_SESSION.md 8.2-8.5 quote THIS block, not the one above.
    print("\n" + "=" * 72)
    print("STRATIFIED BY RECEIVER AND N  -- the figures docs/ 8.4 quotes")
    print("=" * 72)
    for arm in ("A", "B", "C"):
        print(f"\n-- ARM {arm}")
        for key, name in (("p1_kappa", "P1 within kappa"),
                          ("p1_slope", "P1 within slope"),
                          ("kappa_raw", "H2 kappa raw"),
                          ("kappa_derot", "H2 kappa DEROT"),
                          ("slope", "H2 slope"),
                          ("n1_shuffle", "N1 shuffle")):
            by = defaultdict(list)
            for r in o["arms"][arm][key]:
                by[(r["rx"], r["n_classes"])].append(r)
            for (rx, n), rs in sorted(by.items()):
                print(f"   {name:<16} rx={rx:<5} N={n}  "
                      f"A_nn {100*med([x['A_nn'] for x in rs]):5.1f}%  "
                      f"A_gated {100*med([x['A_gated'] for x in rs]):5.1f}%  "
                      f"chance {100/n:4.1f}%  bar {200/n:4.1f}%  "
                      f"{len(rs)} pairs / {sum(x['n_test'] for x in rs)} tests")
    print()
    return 0


def cmd_verify(a):
    """This file's Mahal, given shipped dim/floors, == pc/rff/discriminator."""
    rng = np.random.default_rng(0)
    mine = Library(2, np.array([1.0, 1e-8]))
    theirs = ShippedDisc()
    pts = {f"dev{i}": rng.normal(size=(40, 2)) * [3.0, 1e-3] + [i * 5.0, i * 2e-3]
           for i in range(3)}
    for sid, xs in pts.items():
        for x in xs:
            mine.learn(sid, x)
            theirs.learn(sid, x)
    bad = 0
    for _ in range(2000):
        x = rng.normal(size=2) * [4.0, 2e-3]
        a1, d1, _ = mine.classify(x)
        a2, d2, _ = theirs.classify(x)
        if a1 != a2 or abs(d1 - d2) > 1e-9 * max(1.0, abs(d2)):
            bad += 1
    print(f"\n  2,000 random observations, 3 models, shipped floors "
          f"[1.0, 1e-8]")
    print(f"  disagreements with pc/rff/discriminator.py: {bad}")
    print("  -> identical" if bad == 0 else "  -> DIFFERS, do not trust")
    print("\n  The only difference in the scored run is the standardization")
    print("  declared in docs/KAPPA_CROSS_SESSION.md 4.\n")
    return 0 if bad == 0 else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("path")
    s.add_argument("--tag", required=True)
    s.add_argument("--max-rows", type=int, default=0)
    s.add_argument("--seconds", type=float, default=0)
    s.add_argument("--resume", action="store_true")
    s.set_defaults(fn=cmd_scan)
    for name, fn in (("floors", cmd_floors), ("score", cmd_score)):
        p = sub.add_parser(name)
        p.add_argument("tags", nargs="+")
        p.set_defaults(fn=fn)
    for name, fn in (("report", cmd_report), ("verify", cmd_verify)):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
    p = sub.add_parser("fuse")
    p.add_argument("tags", nargs="*")
    p.set_defaults(fn=cmd_fuse)
    a = ap.parse_args()
    return a.fn(a) or 0


if __name__ == "__main__":
    raise SystemExit(main())
