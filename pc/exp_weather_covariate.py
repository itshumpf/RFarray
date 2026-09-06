#!/usr/bin/env python3
"""Does outdoor temperature explain the cross-session SFO drift?

Pre-registered design, predictions, detection floor and scope limits:
docs/WEATHER_COVARIATE.md (Stage 1 written and saved before this file ran,
before any weather byte was fetched and before any capture was replayed).

Read-only on data/raw/. Opens no serial port. Modifies nothing in pc/rff/.
Scratch state goes to $WXC_CACHE (default /tmp/wxc), outside the repo tree.

  fetch                     expand data/weather_ojc_tmpf_hourly.txt ->
                            data/weather_ojc_tmpf.csv, and run the feed check
  extract <csv> [--cap N]   replay one capture from byte one with a fresh
                            estimator per (file, mac); checkpoint to cache
  analyze                   primary + secondary tests

The DSP is pc/rff/dsp.py as shipped: FrameEstimator + WindowAggregator at
window 64, min_inlier 0.6, max_resid 0.8. The classifier is
pc/rff/discriminator.py as shipped. pc/capture.py's compute_cfo,
pc/phase_skew.py and pc/fingerprint.py are not used (docs/CODE_INVENTORY.md
4.2 C1/C2/C3). scipy is deliberately not imported (CLAUDE.md: nothing in
the repo imports it); all p-values are permutation p-values.

PRIVACY: the weather station is referenced as OJC and nothing else. No
location, distance or rationale for the station appears in this file.
"""
import argparse
import csv as csvmod
import datetime as dt
import itertools
import os
import pickle
import sys
from collections import defaultdict, deque

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rff.dsp import FrameEstimator, WindowAggregator            # noqa: E402
from rff.discriminator import Discriminator                      # noqa: E402
from rff.reference import ReferenceNormalizer                    # noqa: E402

csvmod.field_size_limit(10 ** 7)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RAW = os.path.join(REPO, "data", "raw")
CACHE = os.environ.get("WXC_CACHE", "/tmp/wxc")

# Stage 3 (docs/WEATHER_COVARIATE.md 22): three covariates, one family.
# tmpf was Stage 1/2; relh and mslp are Stage 3/4.
COVARS = ["tmpf", "relh", "mslp"]
COV_UNIT = {"tmpf": "F", "relh": "%", "mslp": "hPa"}


def wx_src(var):
    return os.path.join(REPO, "data", f"weather_ojc_{var}_hourly.txt")


def wx_csv(var):
    return os.path.join(REPO, "data", f"weather_ojc_{var}.csv")

REF_MAC = "a4:f0:0f:77:91:20"
BEACONS = ["a4:f0:0f:77:91:20", "f4:2d:c9:70:72:30", "28:05:a5:2f:fa:48"]

WINDOW = 64                 # dsp.py shipped default
TRAIN_FRACTION = 0.6        # rff_offline.TRAIN_FRACTION
MIN_WIN = 10                # pre-registered, WEATHER_COVARIATE 2
DEFAULT_CAP = 300000        # pre-registered, same as IDENTITY_STABILITY 1.6
N_PERM = 20000
SEED = 20260823

# WEATHER_COVARIATE 1.2 -- taken verbatim from IDENTITY_STABILITY 1.1.
BLOCKS = {
    "R3_node68_july": ["rx_20260714_011619", "rx_20260714_030915",
                       "rx_20260714_031131", "rx_20260715_201703",
                       "rx_20260722_204658", "rx_20260722_XXXXXX"],
    "R4_node68_august": ["desk_20260821_125017", "d0wd_20260822_023034",
                         "d0wd_20260822_144424", "d0wd_20260822_235739",
                         "d0wd_20260823_013537", "d0wd_20260823_014740"],
    "R5_node108_august": ["s3_20260821_125017", "s3_20260822_023034",
                          "s3_20260822_144424", "s3_20260822_235739",
                          "s3_20260823_013537", "s3_20260823_014740"],
}
# COLOCATED_0823 0/5.5, via IDENTITY_STABILITY 1.1.
REMOUNT_KEY = "20260823_013537"


def session_key(stem):
    parts = stem.split("_")
    for i, p in enumerate(parts):
        if len(p) == 8 and p.isdigit() and i + 1 < len(parts):
            return p + "_" + parts[i + 1]
    return ""


def straddles_remount(a, b):
    ka, kb = session_key(a), session_key(b)
    if not ka or not kb:
        return True
    if max(ka, kb) < "20260800_000000":
        return False
    return (ka < REMOUNT_KEY) != (kb < REMOUNT_KEY)


# --------------------------------------------------------------- weather
def wx_fetch(var):
    """Expand the compact hourly source to a CSV the analysis re-reads.

    The source file holds the routine hourly METAR values as fetched. The
    5-minute grid rows between them are 'M' in the raw feed and were
    dropped, never interpolated (WEATHER_COVARIATE 1.1). mslp additionally
    carries its own M inside routine reports; dropped per-variable.
    """
    rows = []
    n_missing = 0
    with open(wx_src(var)) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            date, vals = line.split()
            y, m, d = (int(x) for x in date.split("-"))
            for hour, tok in enumerate(vals.split(",")):
                if tok == "-":
                    n_missing += 1
                    continue
                minute = 53
                if tok.startswith("@"):
                    mm, tok = tok[1:].split("=")
                    minute = int(mm)
                rows.append((dt.datetime(y, m, d, hour, minute,
                                         tzinfo=dt.timezone.utc),
                             float(tok)))
    rows.sort()
    with open(wx_csv(var), "w", newline="") as f:
        w = csvmod.writer(f)
        w.writerow(["station", "valid_utc", var])
        for t, v in rows:
            w.writerow(["OJC", t.strftime("%Y-%m-%d %H:%M"), f"{v:.2f}"])
    print(f"[fetch:{var}] wrote {len(rows)} hourly readings")
    print(f"[fetch:{var}] hours with no usable routine report "
          f"(dropped, not filled): {n_missing}")
    print(f"[fetch:{var}] span {rows[0][0]} .. {rows[-1][0]} UTC")
    print(f"[fetch:{var}] range {min(v for _, v in rows):.2f} .. "
          f"{max(v for _, v in rows):.2f} {COV_UNIT[var]}")
    if var == "tmpf":
        feed_check(rows)
    else:
        diurnal_note(var, rows)
    return rows


def diurnal_note(var, rows):
    """Descriptive UTC sanity note for the non-temperature covariates.

    The pre-registered feed check (WEATHER_COVARIATE 1.3) is defined on
    tmpf and is NOT redefined here for relh/mslp -- inventing a new pass/fail
    criterion after Stage 3 was frozen would be exactly the move Stage 1
    exists to prevent. This prints where the 2026-08-22 extremes fall so the
    reader can see whether they are consistent with the tmpf check, and it
    decides nothing.
    """
    day = [(t, v) for t, v in rows if t.date() == dt.date(2026, 8, 22)]
    if not day:
        return
    vs = [v for _, v in day]
    lo, hi = min(vs), max(vs)
    t_lo = [t for t, v in day if v == lo][0]
    t_hi = [t for t, v in day if v == hi][0]
    print(f"[note:{var}] 2026-08-22 min {lo:.2f} at {t_lo:%H:%M} UTC, "
          f"max {hi:.2f} at {t_hi:%H:%M} UTC "
          f"(descriptive only; the pre-registered check is on tmpf)")


def feed_check(rows):
    """WEATHER_COVARIATE 1.3 check 1 -- the UTC assumption, on 2026-08-22.

    Pre-registered: coolest reading of that day must land at 10:53 UTC and
    warmest at 20:53 UTC (= 05:53 / 15:53 local, UTC-5). Ties are reported
    rather than hidden -- argmin/argmax take the first occurrence.
    """
    day = [(t, v) for t, v in rows if t.date() == dt.date(2026, 8, 22)]
    vs = [v for _, v in day]
    lo, hi = min(vs), max(vs)
    t_lo = [t for t, v in day if v == lo]
    t_hi = [t for t, v in day if v == hi]
    ok = (t_lo[0].strftime("%H:%M") == "10:53"
          and t_hi[0].strftime("%H:%M") == "20:53")
    print(f"[feed-check] 2026-08-22 min {lo:.0f}F first at "
          f"{t_lo[0].strftime('%H:%M')} UTC "
          f"(ties: {[t.strftime('%H:%M') for t in t_lo]})")
    print(f"[feed-check] 2026-08-22 max {hi:.0f}F first at "
          f"{t_hi[0].strftime('%H:%M')} UTC "
          f"(ties: {[t.strftime('%H:%M') for t in t_hi]})")
    print(f"[feed-check] UTC assumption: {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("[feed-check] STOPPING per WEATHER_COVARIATE 1.3.")
        sys.exit(2)
    return ok


def wx_load(var):
    out = []
    with open(wx_csv(var), newline="") as f:
        r = csvmod.reader(f)
        next(r)
        for row in r:
            t = dt.datetime.strptime(row[1], "%Y-%m-%d %H:%M")
            out.append((t.replace(tzinfo=dt.timezone.utc).timestamp(),
                        float(row[2])))
    out.sort()
    return out


def wx_load_all():
    return {v: wx_load(v) for v in COVARS}


def wx_session(wx, t0_us, t1_us):
    """WEATHER_COVARIATE 3: mean/span/n_obs of readings inside the session.

    Falls back to the single nearest reading when none lands inside, and
    says so, per 3's `n_obs = 0 (nearest)` rule.
    """
    a, b = t0_us / 1e6, t1_us / 1e6
    inside = [v for t, v in wx if a <= t <= b]
    if inside:
        return (float(np.mean(inside)), float(max(inside) - min(inside)),
                len(inside), None)
    mid = 0.5 * (a + b)
    t, v = min(wx, key=lambda tv: abs(tv[0] - mid))
    return float(v), 0.0, 0, abs(t - mid) / 60.0


# --------------------------------------------------------------- extract
def circdiff(a, b):
    d = (a - b) % 65536
    return d - 65536 if d > 32768 else d


class Screen:
    """Corrupt-row screen, both routes docs/COLOCATED_0823.md 1 requires.

    Route 1: field plausibility on the columns that exist.
    Route 2: width-9 median filter on `dropped`, tolerance 100, compared
             CIRCULARLY mod 65536 so genuine u16 wraps are not flagged.
             The d0wd fabricates MACs from corrupt rows and three of them
             are invisible to the field screen (COLOCATED_0823 3.3).

    All three blocks analysed here are 13-column, so both routes exist for
    every file -- unlike era A, which is not analysed here.
    """

    def __init__(self, wide, node_mode, chan_mode, tol=100, width=9):
        self.wide, self.node_mode, self.chan_mode = wide, node_mode, chan_mode
        self.tol, self.width, self.half = tol, width, width // 2
        self.buf = deque()
        self.n_field = 0
        self.n_median = 0

    def field_ok(self, rec):
        if rec["chan"] != self.chan_mode:
            return False
        if rec["clen"] not in (128, 256, 384):
            return False
        if not (-110 <= rec["nf"] <= -70):
            return False
        if not (-100 <= rec["rssi"] <= -10):
            return False
        if self.wide and (rec["node"] != self.node_mode or rec["env"] != 0):
            return False
        return True

    def push(self, rec):
        if not self.wide:
            yield rec
            return
        self.buf.append(rec)
        if len(self.buf) < self.width:
            return
        c = self.buf[self.half]
        offs = sorted(circdiff(r["dropped"], c["dropped"]) for r in self.buf)
        med = offs[len(offs) // 2]
        if abs(med) > self.tol:
            self.n_median += 1
        else:
            yield c
        self.buf.popleft()

    def drain(self):
        if not self.wide:
            return
        while self.buf:
            yield self.buf.popleft()


def prescan(path, n=20000):
    node, chan = defaultdict(int), defaultdict(int)
    with open(path, newline="") as f:
        r = csvmod.reader(f)
        hdr = next(r)
        wide = len(hdr) >= 13
        for i, row in enumerate(r):
            if i >= n:
                break
            if len(row) != len(hdr):
                continue
            try:
                chan[int(row[6])] += 1
                if wide:
                    node[int(row[10])] += 1
            except ValueError:
                continue
    return (wide,
            max(node, key=node.get) if node else None,
            max(chan, key=chan.get) if chan else 6)


def extract(stem, cap):
    """Replay one capture FROM BYTE ONE with a fresh estimator per stream.

    ransac_line draws from a per-instance RNG that advances once per fitted
    frame (dsp.py:118,132; V2_SPEC 5.5), so a replay that does not start at
    the first row is not comparable to one that does. No window, filter or
    subsample runs ahead of the estimator; the row cap truncates the tail.
    """
    out = os.path.join(CACHE, stem + ".pkl")
    if os.path.exists(out):
        return out, True
    path = os.path.join(RAW, stem + ".csv")
    wide, node_mode, chan_mode = prescan(path)
    scr = Screen(wide, node_mode, chan_mode)
    ests, aggs = {}, {}
    ref = ReferenceNormalizer(REF_MAC)
    wins = defaultdict(list)
    frames = defaultdict(int)
    rows = unparse = 0
    t0 = tlast = None

    def handle(rec):
        nonlocal t0, tlast
        mac = rec["mac"]
        if t0 is None:
            t0 = rec["pc"]
        tlast = rec["pc"]
        frames[mac] += 1
        if mac not in ests:
            ests[mac] = FrameEstimator()
            aggs[mac] = WindowAggregator(window=WINDOW)
        est = ests[mac].feed(rec["vals"], rec["esp"])
        obs = aggs[mac].feed(est, rec["esp"], rec["rssi"])
        if obs is None:
            return
        obs, _ = ref.feed(mac, obs)
        wins[mac].append((rec["pc"], obs.get("cfo"), obs.get("sfo"),
                          obs.get("cfo_ref"), obs.get("sfo_ref")))

    with open(path, newline="") as f:
        r = csvmod.reader(f)
        hdr = next(r)
        ncol = len(hdr)
        for row in r:
            rows += 1
            if rows > cap:
                rows -= 1
                break
            if len(row) != ncol:
                unparse += 1
                continue
            try:
                rec = {"pc": int(row[0]), "mac": row[3].lower(),
                       "rssi": int(row[4]), "nf": int(row[5]),
                       "chan": int(row[6]), "esp": int(row[7]),
                       "clen": int(row[8])}
                if wide:
                    rec["node"] = int(row[10])
                    rec["env"] = int(row[11])
                    rec["dropped"] = int(row[12])
            except (ValueError, IndexError):
                unparse += 1
                continue
            if not scr.field_ok(rec):
                scr.n_field += 1
                continue
            rec["vals"] = np.fromstring(row[9], dtype=np.float64, sep=",")
            for ok in scr.push(rec):
                handle(ok)
        for ok in scr.drain():
            handle(ok)

    meta = dict(stem=stem, wide=wide, node_mode=node_mode, cap=cap, rows=rows,
                unparseable=unparse, n_field=scr.n_field,
                n_median=scr.n_median, t0=t0, tlast=tlast,
                frames=dict(frames))
    os.makedirs(CACHE, exist_ok=True)
    with open(out, "wb") as fh:
        pickle.dump(dict(meta=meta, wins=dict(wins)), fh)
    return out, False


# ----------------------------------------------------------- statistics
def _rank(a):
    a = np.asarray(a, dtype=np.float64)
    order = np.argsort(a, kind="mergesort")
    r = np.empty(a.size, dtype=np.float64)
    r[order] = np.arange(a.size, dtype=np.float64)
    # average ties
    i = 0
    s = a[order]
    while i < a.size:
        j = i
        while j + 1 < a.size and s[j + 1] == s[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = np.mean(r[order[i:j + 1]])
        i = j + 1
    return r


def _pearson(x, y):
    x = x - x.mean()
    y = y - y.mean()
    d = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / d) if d > 0 else float("nan")


def spearman(a, b, n_perm=N_PERM, seed=SEED):
    """Spearman rho with a permutation p (two-tailed). Returns (rho, p, n)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    n = a.size
    if n < 3:
        return float("nan"), float("nan"), n
    ra, rb = _rank(a), _rank(b)
    rho = _pearson(ra, rb)
    if not np.isfinite(rho):
        return rho, float("nan"), n
    rng = np.random.default_rng(seed)
    ca = ra - ra.mean()
    cb = rb - rb.mean()
    perm = np.argsort(rng.random((n_perm, n)), axis=1)
    num = (ca[perm] * cb[None, :]).sum(axis=1)
    den = np.sqrt((ca * ca).sum() * (cb * cb).sum())
    null = np.abs(num / den)
    p = (1 + int((null >= abs(rho) - 1e-12).sum())) / (n_perm + 1)
    return float(rho), float(p), n


def _resid(y, Xs):
    """Residual of y after regressing out every column in Xs (centred)."""
    y = y - y.mean()
    for _ in range(2):                       # two Gram-Schmidt passes
        for x in Xs:
            x0 = x - x.mean()
            ss = (x0 * x0).sum()
            if ss > 1e-12:
                y = y - ((x0 * y).sum() / ss) * x0
    return y


def partial_spearman(d, e, ts, n_perm=N_PERM, seed=SEED):
    """rho(d, e | ts) on ranks; ts is a LIST of control variables.

    WEATHER_COVARIATE 4.2 (one control) and 23 (the joint three-control
    form). Ranks first, then residualise both d and e on the controls and
    correlate the residuals; p by permuting the residualised d ranks.
    Returns (rho, p, n, zero_order_rho).
    """
    n = len(d)
    k = len(ts)
    if n < k + 4:
        return float("nan"), float("nan"), n, float("nan")
    rd, re_ = _rank(d), _rank(e)
    zero = _pearson(rd, re_)
    Xs = []
    for t in ts:
        Xs.append(_resid(_rank(t), Xs))      # orthogonalise the controls
    yd, ye = _resid(rd, Xs), _resid(re_, Xs)
    den = np.sqrt((yd * yd).sum() * (ye * ye).sum())
    if den <= 1e-12:
        return float("nan"), float("nan"), n, float(zero)
    rho = float((yd * ye).sum() / den)
    rng = np.random.default_rng(seed)
    perm = np.argsort(rng.random((n_perm, n)), axis=1)
    num = (yd[perm] * ye[None, :]).sum(axis=1)
    null = np.abs(num / den)
    p = (1 + int((null >= abs(rho) - 1e-12).sum())) / (n_perm + 1)
    return rho, float(p), n, float(zero)


def holm(pvals, alpha=0.05):
    """Holm-Bonferroni. Returns per-test (adjusted p, reject?) in input order.

    WEATHER_COVARIATE 24.1: applied to Family A at m = len(pvals).
    """
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    running = 0.0
    for rank_i, i in enumerate(order):
        a = min(1.0, (m - rank_i) * pvals[i])
        running = max(running, a)            # enforce monotonicity
        adj[i] = running
    return [(adj[i], adj[i] < alpha) for i in range(m)]


def m_eff(corr):
    """Cheverud-Nyholt / Li-Ji effective number of independent tests.

    WEATHER_COVARIATE 24.2. REPORTED FOR INTERPRETATION ONLY -- it does not
    govern the correction, because it is derived from the data and using a
    data-derived quantity to relax a threshold is the move Stage 1 exists
    to prevent.
    """
    lam = np.linalg.eigvalsh(np.asarray(corr, float))
    M = len(lam)
    return 1.0 + (M - 1.0) * (1.0 - float(np.var(lam, ddof=1)) / M)


def sidak(alpha, m):
    return 1.0 - (1.0 - alpha) ** (1.0 / max(m, 1e-9))


def floor_for(n, n_perm=200000, seed=SEED):
    """|rho| exceeded by 5% of random permutations at this n (two-tailed)."""
    if n < 3:
        return float("nan")
    rng = np.random.default_rng(seed)
    base = np.arange(n, dtype=np.float64)
    ca = base - base.mean()
    perm = np.argsort(rng.random((n_perm, n)), axis=1).astype(np.float64)
    cb = perm - perm.mean(axis=1, keepdims=True)
    num = (ca[None, :] * cb).sum(axis=1)
    den = np.sqrt((ca * ca).sum() * (cb * cb).sum(axis=1))
    return float(np.percentile(np.abs(num / den), 95))


# -------------------------------------------------------------- analyze
def floor_for_partial(n, k, n_draw=100000, seed=SEED):
    """Detection floor for a k-control partial rank correlation at this n.

    WEATHER_COVARIATE 25. Null: all k+2 variables mutually independent.
    Validated against floor_for(): at k = 0 this reproduces the Stage-1 6
    table (0.518 at n = 15, 0.750 at n = 7).
    """
    if n < k + 4:
        return float("nan")
    rng = np.random.default_rng(seed)

    def rk(a):
        o = np.argsort(a, axis=-1, kind="mergesort")
        r = np.empty_like(o, dtype=float)
        np.put_along_axis(r, o, np.arange(n, dtype=float), axis=-1)
        return r

    def res(y, Xs):
        y = y - y.mean(axis=1, keepdims=True)
        for _ in range(2):
            for x in Xs:
                x0 = x - x.mean(axis=1, keepdims=True)
                ss = (x0 * x0).sum(1, keepdims=True)
                b = np.divide((x0 * y).sum(1, keepdims=True), ss,
                              out=np.zeros_like(ss), where=ss > 1e-12)
                y = y - b * x0
        return y

    d = rk(rng.normal(size=(n_draw, n)))
    e = rk(rng.normal(size=(n_draw, n)))
    Xs = []
    for _ in range(k):
        Xs.append(res(rk(rng.normal(size=(n_draw, n))), Xs))
    yd, ye = res(d, Xs), res(e, Xs)
    num = (yd * ye).sum(1)
    den = np.sqrt((yd * yd).sum(1) * (ye * ye).sum(1))
    r = np.abs(np.divide(num, den, out=np.zeros_like(num), where=den > 1e-12))
    r = r[np.isfinite(r)]
    return float(np.percentile(r, 95))


def feats(wins, space):
    """[(ts, [cfo, sfo])]; BOTH components must exist (IDENTITY_STABILITY)."""
    i, j = (1, 2) if space == "raw" else (3, 4)
    return [(w[0], np.array([w[i], w[j]], float))
            for w in wins if w[i] is not None and w[j] is not None]


def sfos(wins, space):
    k = 2 if space == "raw" else 4
    return [w[k] for w in wins if w[k] is not None]


def gap_one_way(A, B, space):
    """within - cross accuracy on the SAME test windows (IDENTITY_STABILITY
    1.2): test = last 40% of B per device; enroll = first 60% of B (within)
    or all of A (cross). Shipped Discriminator, chi2 gate."""
    classes = [m for m in BEACONS if m in A and m in B]
    if len(classes) < 2:
        return None
    test, enr_w, enr_c = {}, {}, {}
    for m in classes:
        fb = sorted(feats(B[m], space))
        fa = sorted(feats(A[m], space))
        if len(fb) < MIN_WIN or len(fa) < MIN_WIN:
            return None
        cut = int(len(fb) * TRAIN_FRACTION)
        enr_w[m] = [f for _, f in fb[:cut]]
        test[m] = [f for _, f in fb[cut:]]
        enr_c[m] = [f for _, f in fa]
        if not test[m] or not enr_w[m]:
            return None

    def acc(enroll):
        d = Discriminator()
        for m, fs in enroll.items():
            for f in fs:
                d.learn(m, f)
        ok = tot = 0
        for m, fs in test.items():
            for f in fs:
                sid, _, verdict = d.classify(f)
                tot += 1
                if verdict in ("MATCH", "MARGINAL") and sid == m:
                    ok += 1
        return ok / tot if tot else float("nan")

    return acc(enr_w) - acc(enr_c), len(classes), sum(len(v) for v in test.values())


def gap_for_pair(A, B, space):
    """The UNORDERED-pair gap: mean of the two ordered gaps.

    WEATHER_COVARIATE 4.2 makes unordered pairs primary because the two
    ordered pairs of an unordered pair share one |elapsed|; that only works
    if both directions are actually collapsed into one value. The first
    version of this function returned the A->B direction alone, which is an
    ordered statistic wearing an unordered label. Recorded here rather than
    quietly fixed.
    """
    fwd = gap_one_way(A, B, space)
    rev = gap_one_way(B, A, space)
    if fwd is None or rev is None:
        return None
    return (0.5 * (fwd[0] + rev[0]), fwd[1], fwd[2] + rev[2])


def analyze():
    wx = wx_load_all()
    cells = {}      # (block, stem) -> dict
    for block, stems in BLOCKS.items():
        for stem in stems:
            p = os.path.join(CACHE, stem + ".pkl")
            if not os.path.exists(p):
                print(f"  !! missing cache for {stem}")
                continue
            with open(p, "rb") as fh:
                d = pickle.load(fh)
            meta = d["meta"]
            cov, nobs, near = {}, {}, {}
            for v in COVARS:
                cov[v], _, nobs[v], near[v] = wx_session(
                    wx[v], meta["t0"], meta["tlast"])
            cells[(block, stem)] = dict(meta=meta, wins=d["wins"],
                                        cov=cov, nobs=nobs, near=near)
    return cells, wx


def fmt(rho, p, n):
    if not np.isfinite(rho):
        return f"  n/a (n={n})"
    return f"{rho:+.3f} (p={p:.3f}, n={n})"




def cov_label(v):
    return {"tmpf": "|dT|", "relh": "|dRH|", "mslp": "|dP|"}[v]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "extract", "analyze", "status"])
    ap.add_argument("stem", nargs="?")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP)
    ap.add_argument("--space", default="raw", choices=["raw", "ref"])
    ap.add_argument("--budget", type=float, default=0.0,
                    help="seconds; extract files until exhausted then stop")
    ap.add_argument("--section", default="all",
                    choices=["all", "sessions", "primary", "secondary",
                             "collin"])
    a = ap.parse_args()

    if a.cmd == "fetch":
        for v in COVARS:
            wx_fetch(v)
            print()
        return

    if a.cmd == "status":
        for block, stems in BLOCKS.items():
            for s in stems:
                ok = os.path.exists(os.path.join(CACHE, s + ".pkl"))
                print(f"{'OK ' if ok else '.. '} {block:20s} {s}")
        return

    if a.cmd == "extract":
        import time
        todo = [a.stem] if a.stem else [s for v in BLOCKS.values() for s in v]
        t_start = time.time()
        for s in todo:
            if a.budget and time.time() - t_start > a.budget:
                print("[extract] budget exhausted; resume with the same cmd")
                break
            t0 = time.time()
            out, cached = extract(s, a.cap)
            with open(out, "rb") as fh:
                m = pickle.load(fh)["meta"]
            print(f"[extract] {s:24s} {'cached' if cached else 'ran'} "
                  f"rows={m['rows']} field={m['n_field']} "
                  f"median={m['n_median']} unparse={m['unparseable']} "
                  f"{time.time() - t0:.0f}s")
        return

    # ------------------------------------------------------------ analyze
    cells, wx = analyze()
    space = a.space
    sec = a.section
    print(f"\n### feature space: {space}\n")

    if sec in ("all", "sessions"):
        print("--- sessions and their OJC covariates -------------------------")
        print(f"{'block':18s} {'session':22s} {'start UTC':17s} {'h':>5s} "
              f"{'tmpf':>7s} {'relh':>7s} {'mslp':>9s}   n_obs(t/rh/p)")
        for (block, stem), c in sorted(cells.items()):
            m = c["meta"]
            t0 = dt.datetime.fromtimestamp(m["t0"] / 1e6, dt.timezone.utc)
            dur = (m["tlast"] - m["t0"]) / 1e6 / 3600
            nb = "/".join(str(c["nobs"][v]) for v in COVARS)
            print(f"{block:18s} {stem:22s} {t0:%Y-%m-%d %H:%M} {dur:5.2f} "
                  f"{c['cov']['tmpf']:7.2f} {c['cov']['relh']:7.2f} "
                  f"{c['cov']['mslp']:9.2f}   {nb}")
        nf = sum(1 for c in cells.values() for v in COVARS if c["nobs"][v] == 0)
        print(f"  cells using the nearest-reading fallback (WEATHER_COVARIATE 3): "
              f"{nf} of {len(cells) * len(COVARS)} (session, covariate) pairs")

    # ---------------------------------------------------- COLLINEARITY
    if sec in ("all", "collin", "secondary"):
        print("\n=== COLLINEARITY among the three covariates (24.2) ============")
        sess = {}
        for (block, stem), c in cells.items():
            sess.setdefault(session_key(stem), c["cov"])
        print(f"-- session level, n = {len(sess)} distinct wall-clock sessions --")
        keys = sorted(sess)
        lev = {v: [sess[k][v] for k in keys] for v in COVARS}
        C1 = np.eye(3)
        for i, vi in enumerate(COVARS):
            for j, vj in enumerate(COVARS):
                if i < j:
                    r = spearman(lev[vi], lev[vj])[0]
                    C1[i, j] = C1[j, i] = r
                    print(f"   rho({vi}, {vj}) = {r:+.3f}")
        print(f"   M_eff (session level) = {m_eff(C1):.3f}  "
              f"[interpretation only; Holm at m=3 governs]")

        print("\n-- R3 pair level (the deltas actually used), n = 15 --")
        r3 = [s for s in BLOCKS["R3_node68_july"] if ("R3_node68_july", s) in cells]
        dl = {v: [] for v in COVARS}
        for A, B in itertools.combinations(sorted(r3, key=session_key), 2):
            ca, cb = cells[("R3_node68_july", A)], cells[("R3_node68_july", B)]
            for v in COVARS:
                dl[v].append(abs(cb["cov"][v] - ca["cov"][v]))
        C2 = np.eye(3)
        for i, vi in enumerate(COVARS):
            for j, vj in enumerate(COVARS):
                if i < j:
                    r = spearman(dl[vi], dl[vj])[0]
                    C2[i, j] = C2[j, i] = r
                    print(f"   rho({cov_label(vi)}, {cov_label(vj)}) = {r:+.3f}")
        me = m_eff(C2)
        print(f"   M_eff (R3 delta level) = {me:.3f}")
        print(f"   Holm at m=3 governs. Sidak threshold at M_eff would be "
              f"alpha = {sidak(0.05, me):.4f} (vs Bonferroni 0.0167).")

    # ---------------------------------------------------- PRIMARY (Stage 3)
    if sec in ("all", "secondary"):
        print("\n=== STAGE-3 PRIMARY: does elapsed survive each control? =======")
        # M_eff on R3's deltas, for the descriptive Sidak column only (24.2).
        m_eff_r3 = []
        r3s = [s for s in BLOCKS["R3_node68_july"]
               if ("R3_node68_july", s) in cells]
        _dl = {v: [] for v in COVARS}
        for A, B in itertools.combinations(sorted(r3s, key=session_key), 2):
            ca, cb = cells[("R3_node68_july", A)], cells[("R3_node68_july", B)]
            for v in COVARS:
                _dl[v].append(abs(cb["cov"][v] - ca["cov"][v]))
        _C = np.eye(3)
        for i, vi in enumerate(COVARS):
            for j, vj in enumerate(COVARS):
                if i < j:
                    _C[i, j] = _C[j, i] = spearman(_dl[vi], _dl[vj])[0]
        m_eff_r3.append(m_eff(_C))
        for block, stems in BLOCKS.items():
            have = [s for s in stems if (block, s) in cells]
            pairs = []
            excl = 0
            for A, B in itertools.combinations(sorted(have, key=session_key), 2):
                if straddles_remount(A, B):
                    excl += 1
                    continue
                ca, cb = cells[(block, A)], cells[(block, B)]
                common = [m for m in BEACONS
                          if len(sfos(ca["wins"].get(m, []), space)) >= MIN_WIN
                          and len(sfos(cb["wins"].get(m, []), space)) >= MIN_WIN]
                if len(common) < 2:
                    continue
                deltas = [float(np.median(sfos(cb["wins"][m], space)))
                          - float(np.median(sfos(ca["wins"][m], space)))
                          for m in common]
                g = gap_for_pair(ca["wins"], cb["wins"], space)
                pairs.append(dict(
                    A=A, B=B,
                    d1=float(np.sqrt(np.mean(np.square(deltas)))),
                    d2=(g[0] if g else None),
                    elapsed=abs(cb["meta"]["t0"] - ca["meta"]["t0"]) / 1e6 / 3600,
                    dcov={v: abs(cb["cov"][v] - ca["cov"][v]) for v in COVARS}))
            n = len(pairs)
            print(f"\n-- {block}: {n} controlled unordered pairs "
                  f"({excl} straddling the remount, excluded) --")
            if n < 4:
                print("   too few pairs.")
                continue
            el = [q["elapsed"] for q in pairs]
            for name, key in (("D1", "d1"), ("D2", "d2")):
                famA = []       # WEATHER_COVARIATE 24.1: m = 3 covariates
                vals = [q[key] for q in pairs]
                if any(v is None for v in vals):
                    print(f"   {name}: not computable on every pair; skipped")
                    continue
                r_de, p_de, _ = spearman(vals, el)
                print(f"\n   {name}  zero-order vs elapsed: {fmt(r_de, p_de, n)}"
                      f"   [floor k=0: {floor_for(n):.3f}]")
                for v in COVARS:
                    dc = [q["dcov"][v] for q in pairs]
                    r_dt, p_dt, _ = spearman(vals, dc)
                    r_et, p_et, _ = spearman(el, dc)
                    pr, pp, pn, _ = partial_spearman(vals, el, [dc])
                    cond = "ILL-CONDITIONED" if abs(r_et) > 0.50 else "ok"
                    famA.append((v, p_dt, r_dt))
                    print(f"     control {cov_label(v):6s} | "
                          f"assoc {r_dt:+.3f} (p={p_dt:.3f}) | "
                          f"partial {pr:+.3f} (p={pp:.3f}) "
                          f"shift {pr - r_de:+.3f} | "
                          f"cond rho(elapsed,{cov_label(v)})={r_et:+.3f} {cond}")
                    # NOT PRE-REGISTERED. The symmetric completion of the
                    # pre-registered partial: does the covariate survive
                    # controlling for ELAPSED? Exploratory, labelled as such,
                    # counted in no family, and it changes no verdict (32).
                    rv, rvp, _, _ = partial_spearman(vals, dc, [el])
                    print(f"       [post-hoc, not pre-registered] "
                          f"rho(D,{cov_label(v)} | elapsed) = {rv:+.3f} "
                          f"(p={rvp:.3f}), was {r_dt:+.3f}")
                allc = [[q["dcov"][v] for q in pairs] for v in COVARS]
                pj, ppj, _, _ = partial_spearman(vals, el, allc)
                fl3 = floor_for_partial(n, 3)
                note = ("  UNINTERPRETABLE BY CONSTRUCTION (25)"
                        if fl3 > 0.90 else "")
                print(f"     JOINT control (all three): {pj:+.3f} "
                      f"(p={ppj:.3f}) shift {pj - r_de:+.3f} "
                      f"[floor k=3: {fl3:.3f}]{note}")
                if famA:
                    ps = [p for _, p, _ in famA]
                    hh = holm(ps)                 # m = 3, as pre-registered
                    sid = sidak(0.05, m_eff_r3[0]) if m_eff_r3 else None
                    print(f"     Family A for {name}: Holm at m={len(ps)} "
                          f"(pre-registered):")
                    for (nm, p, r), (adj, rej) in zip(famA, hh):
                        star = "  <-- NOMINAL HIT" if p < 0.05 else ""
                        extra = ""
                        if sid is not None and p < 0.05:
                            extra = (f"  [Sidak@M_eff a={sid:.4f}: "
                                     f"{'sig' if p < sid else 'ns'}]")
                        print(f"       {nm:5s} rho={r:+.3f} p={p:.3f} "
                              f"holm={adj:.3f} "
                              f"{'REJECT' if rej else 'retain'}{star}{extra}")

    # ---------------------------------------------------- SECONDARY
    if sec in ("all", "primary"):
        print("\n=== STAGE-3 SECONDARY: median SFO vs each covariate ===========")
        rows = []
        for (block, stem), c in sorted(cells.items()):
            for mac in BEACONS:
                s = sfos(c["wins"].get(mac, []), space)
                if len(s) < MIN_WIN:
                    continue
                rows.append(dict(block=block, mac=mac, stem=stem,
                                 sfo=float(np.median(s)), cov=c["cov"]))
        means = defaultdict(list)
        for r in rows:
            means[(r["block"], r["mac"])].append(r["sfo"])
        means = {k: float(np.mean(v)) for k, v in means.items()}
        dm = [r["sfo"] - means[(r["block"], r["mac"])] for r in rows]
        n_sess = len({session_key(r["stem"]) for r in rows})
        print(f"  n = {len(rows)} cells; {n_sess} distinct wall-clock sessions")
        print(f"  nominal floor n={len(rows)}: {floor_for(len(rows)):.3f}   "
              f"EFFECTIVE floor n={n_sess}: {floor_for(n_sess):.3f}")
        for v in COVARS:
            rho, p, n = spearman(dm, [r["cov"][v] for r in rows])
            print(f"   pooled de-meaned vs {v:5s}: {fmt(rho, p, n)}")
        for block in BLOCKS:
            idx = [i for i, r in enumerate(rows) if r["block"] == block]
            if len(idx) < 3:
                continue
            out = []
            for v in COVARS:
                rb, pb, nb_ = spearman([dm[i] for i in idx],
                                       [rows[i]["cov"][v] for i in idx])
                out.append(f"{v}={rb:+.3f}(p={pb:.3f})")
            print(f"   {block:18s} n={len(idx)} floor={floor_for(len(idx)):.3f}  "
                  + "  ".join(out))


if __name__ == "__main__":
    main()
