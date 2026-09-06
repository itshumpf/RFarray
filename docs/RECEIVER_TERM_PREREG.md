# PRE-REGISTERED TEST — why does the inter-receiver SFO disagreement vary across sources?

**Stage 1 written 2026-08-23, before any analysis of this question was run.**
Nothing below §9 existed when the first row of the capture was read for this
pass. The predictions in §3 are **frozen**: if the data disagrees with one,
the results section reports the disagreement. No prediction is revised,
reworded, or joined by a new hypothesis after the fact. Where the temptation
arises it is recorded as a temptation in §14 rather than acted on.

---

## 0. The capture

| | `data/raw/d0wd_20260823_014740.csv` | `data/raw/s3_20260823_014740.csv` |
|---|---|---|
| `node_id` | 68 | 108 |
| data rows | 3,344,351 | 4,330,849 |
| span | 01:47:41 → 08:29:44 local, 24,123.12 s = 6.7009 h | same |

Both receivers are on the same wall, ~10 inches apart chip to chip
(`docs/COLOCATED_0823.md`). The shorter `013537` pair from the same night is
**not used** — not as input, not as corroboration.

Read-only on `data/raw/`: every input opened `"rb"`. No serial port is
opened. Nothing is staged, committed or pushed. `pc/rff/dsp.py` is not
modified and is used exactly as shipped (`docs/V2_SPEC.md` §5.5).
`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` are
not used — `docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 establishes all three have
the DC/guard-band index wrong. One script is written: `pc/exp_receiver_term_prereg.py`.

---

## 1. The question

For a source heard by both receivers, the two receivers disagree about that
source's SFO. `docs/COLOCATED_0823.md` §5.1 measures that disagreement on
three known beacons under co-location and finds it varies **23×**:

| beacon | d0wd−s3 SFO diff (rad/sc) | × `BETWEEN_UNIT_SD` |
|---|---|---|
| B1 `a4:f0:0f:77:91:20` | +0.00168 | 0.71 |
| B2 `28:05:a5:2f:fa:48` | +0.03870 | 16.33 |
| B3 `f4:2d:c9:70:72:30` | −0.01610 | 6.79 |

**Why does it vary?**

### 1.1 Framing — the transmitters are sources, not instruments

The receivers are the instrument under test. The three beacons have exactly
one privilege over every other transmitter in the room: **known position.**
In every other respect they are three sources among however many the room
holds.

Therefore **n is every source heard by both receivers with enough frames to
fit** (§4), beacons included on equal footing and not broken out as a
separate category. `docs/COLOCATED_0823.md` §2 establishes that the S3's
real population is a strict subset of the d0wd's — 14 and 18 sources at the
repo's 20-frame floor — so an n in the low teens is expected. That is
anticipated here, not discovered later, and §6 states the consequence.

---

## 2. The disagreement statistic, and why it is not the documented one

### 2.1 What prior documents used

`docs/SEPARATION_SCALING.md` §0, `docs/REFERENCE_CHOICE.md` §0/§1.3 and
`docs/COLOCATED_0823.md` §5 all use the same statistic: the **d0wd-minus-s3
same-source SFO median difference, no reference correction**, where each
receiver's SFO is the median over **16,384-frame `WindowAggregator` window
medians** with the shipped gates `min_inlier_ratio = 0.6` / `max_resid = 0.8`
(`pc/rff/dsp.py:164`). `docs/REFERENCE_CHOICE.md` §1.3 chose 16,384 as the
longest averaging that keeps all three beacons alive on both receivers.

### 2.2 Why it cannot be the statistic here

A 16,384-frame window needs 16,384 admissible frames to emit even one value.
An ambient source with 20–2,000 frames emits **zero** windows. So does it at
the shipped window of 64 if it has fewer than 64. The documented statistic is
defined only on the three beacons, which is precisely the population this
test is not allowed to restrict itself to (§1.1). Using it would answer the
question on n = 3.

### 2.3 The statistic used, defined

For each (receiver, source) cell, let the **admissible frame set** be every
frame that `FrameEstimator.feed` fits and that passes both shipped gates
(`inlier_ratio >= 0.6`, `resid_std <= 0.8`) — exactly the frames
`WindowAggregator` admits, with the windowing removed. Let

  `SFO(node, src) = median of the per-frame RANSAC slopes over that set`  (rad/sc)

  `Δ_signed(src) = SFO(d0wd, src) − SFO(s3, src)`

  `Δ(src) = |Δ_signed(src)|`

`Δ` is the per-source disagreement statistic. `Δ_signed` is used only in the
H3 test (§3.3), where sign is the point.

This is the documented statistic with the window collapsed to 1 and the
outer median removed — the same frames, the same gates, the same direction of
subtraction, the same absence of reference correction.

### 2.4 The check that the substitution is legitimate, pre-registered

The window-16,384 and window-64 statistics are computed **as well**, for
every source that emits at least three windows. On the three beacons all
three statistics are directly comparable to `docs/COLOCATED_0823.md` §5.1.

**Acceptance criterion, frozen:** the frame-level `Δ` is used as the primary
statistic if, on the three beacons, it (a) preserves the rank order
B2 > B3 > B1 and (b) agrees with the window-16,384 `Δ` within **25 %** on
each of the three.

**If it fails either condition,** the failure is reported, the frame-level
statistic is not promoted, and the analysis falls back to the window-64
statistic on whatever reduced n supports it — with the reduced n and the
worse detection floor stated. That fallback is a pre-registered branch, not a
revision.

### 2.5 Known hazard, stated now

`docs/SEPARATION_SCALING.md` §0 establishes the per-frame SFO series is **not
white** beyond τ ≈ 10–30 s — the Allan deviation is flat or rising from
τ ≈ 20 s to τ ≈ 1 h, and a time-shuffle control reproduces the white-noise
factor of 16 that the real data does not. Consequently **any uncertainty on a
per-source median that assumes independent frames is a lower bound.** All
per-source uncertainties below use a moving-block bootstrap (§3.3) for that
reason, and are still described as lower bounds.

---

## 3. The hypotheses, their predicted signs, and their statistics

The predictor is per-source RSSI. Two composite variables are defined per
source, both over clean rows only:

  `RSSI(src) = mean( mean_rssi(d0wd, src), mean_rssi(s3, src) )`   — primary
  `RSSI_min(src) = min( mean_rssi(d0wd, src), mean_rssi(s3, src) )` — sensitivity

The primary is the two-receiver mean because at 10 inches the two receivers
see nearly the same path and both hypotheses are about the source's link, not
one receiver's. `RSSI_min` is reported alongside because H1's mechanism, if
real, should be driven by the noisier of the two cells.

### 3.1 H1 — estimator noise

> IF the disagreement is fit noise, THEN it correlates **negatively** with
> RSSI, BECAUSE slope-fit variance scales inversely with SNR.

**Predicted sign: r(Δ, RSSI) < 0.** (RSSI is signed dB: higher = stronger.
A strong source has small Δ.)

### 3.2 H2 — relative baseline geometry

> IF it is the channel differing between the two receiver positions, THEN it
> correlates **positively** with RSSI, BECAUSE the 10-inch receiver
> separation is a larger fraction of a short path, and a dominant direct path
> carries structured channel phase that biases the slope differently at each
> position.

**Predicted sign: r(Δ, RSSI) > 0.**

H1 and H2 predict **opposite signs on the same measurement.** That is the
discriminating power of the test and the reason it is worth running on a
small n.

### 3.3 H3 — fixed receiver offset (the null)

> IF it is a property of the receiver pair rather than the link, THEN it is
> roughly constant across sources.

A fixed offset is a **signed** constant, so H3 is tested on `Δ_signed`, not
`Δ`. Two statistics, both frozen:

- **Dispersion ratio** `R_disp = Var_across-sources(Δ_signed) / median_src( Var_boot(Δ_signed(src)) )`,
  where `Var_boot` is from a **moving-block bootstrap** over each cell's
  per-frame slope series: B = 200 resamples, block length
  `L = max(1, min(1024, n_adm // 8))`, fixed seed 20260823, and
  `Var_boot(Δ_signed) = Var_boot(SFO_d0wd) + Var_boot(SFO_s3)`.
  Blocks rather than iid resampling because of §2.5.
- **Range ratio** `max(Δ) / min(Δ)` across the included sources.

**H3 survives only if `R_disp < 2`** — across-source spread no more than
twice the (lower-bound) sampling variance of a single source's estimate.
`R_disp >= 2` falsifies H3 regardless of what the correlation does.

### 3.4 The confound control

RSSI and frame count are collinear: a quiet source is also heard rarely, and
fewer frames means a noisier median. A raw correlation cannot separate H1
from "not enough frames".

**Control variable:** `logN(src) = log10( n_min(src) )`, where
`n_min(src) = min(n_adm(d0wd,src), n_adm(s3,src))` — the **lower** of the two
receivers' admissible frame counts, because the noisier cell sets the
disagreement. `log10` because n spans 20 to ~1.5 × 10⁶ and median noise
scales as n^(−1/2), so the effect is linear in log n, not in n.

**Primary test: partial Spearman correlation of `Δ` with `RSSI`, controlling
for `logN`.** Computed as the Pearson partial correlation on the
rank-transformed triple:

  `r_partial = (r_xy − r_xz · r_yz) / sqrt( (1 − r_xz²)(1 − r_yz²) )`

with `x = rank(Δ)`, `y = rank(RSSI)`, `z = rank(logN)`, `df = n − 3`.

Rank-based rather than Pearson-on-raw because `Δ` spans orders of magnitude
and one cell (B2/d0wd, 79.8 % gate rejection, `docs/COLOCATED_0823.md` §4.1)
is a known extreme that must not be allowed to set a Pearson slope by itself.

Also reported, without which the partial cannot be interpreted: the raw
`r_xy`, the collinearity `r_yz` between RSSI and logN, and `r_xz` between Δ
and logN.

### 3.5 Pre-registered sensitivity analyses

Run and reported whatever the primary shows; none can replace the primary.

1. `RSSI_min` substituted for `RSSI`.
2. Sources whose gate rejection exceeds **50 %** on either receiver excluded.
   `docs/POSITIVE_CONTROL_0822.md` §5 and `docs/REFERENCE_CHOICE.md` §0
   establish the standing rule that such a cell must not be rested on; B2/d0wd
   is one in this file. The primary includes it (excluding a source for having
   a large Δ would be circular); this sensitivity shows the reading without it.
3. Pearson on `log10(Δ)` vs `RSSI` controlling `logN`, as a parametric check
   that the rank result is not an artefact of ties.
4. The window-64 `Δ` substituted for the frame-level `Δ`, on the sources that
   support it.

---

## 4. Inclusion criteria, and the n reported at every step

Applied in this order, with the count surviving each step reported for both
receivers:

1. **Rows parsed.** 3,344,351 / 4,330,849 expected. Rows with ≠ 13 fields or
   unparseable ints are counted and dropped.
2. **Both corrupt-row screens, before any delta arithmetic.** Field
   plausibility on six columns (`node_id` vs the file's own mode, `env_id == 0`,
   `channel` vs the file's own mode, `csi_len ∈ {128,256,384}`,
   `noise_floor ∈ [−110,−70]`, `rssi ∈ [−100,−10]`) **and** a width-9 median
   filter on `dropped`, compared circularly mod 65536. Both are required:
   `docs/COLOCATED_0823.md` §3.3 shows three d0wd rows are invisible to the
   field screen and only the median filter catches them, and the d0wd
   fabricates MACs from corrupt rows — 126 of its 166 addresses were
   corruption (§2).
3. **Distinct source MACs on clean rows**, per receiver.
4. **Heard by both receivers** (intersection).
5. **≥ 20 admissible frames on both receivers**, where admissible is §2.3.
   Twenty is the repo's own floor — `pc/mac_census.py --min-frames 20`, the
   floor `docs/COLOCATED_0823.md` §2 uses to define the real population — here
   applied to admissible frames rather than clean rows, which is strictly
   tighter. Reported alongside: n at a 64-frame floor (one shipped window).

Every source dropped at step 4 or 5 is listed individually with its frame
count on each receiver and the reason.

**Not excluded, but flagged:** `docs/COLOCATED_0823.md` §2 identifies at
least three sparse d0wd addresses as single-frame byte-neighbours of beacon
MACs (`fa:1e:c9:70:72:30`, `e4:21:e3:20:72:30`, `d9:f4:a5:2f:fa:48`) and more
likely undetected corruption than real transmitters. They passed both screens,
so removing them here would be a post-hoc judgement; they are flagged in the
listing and, at 1 frame each, cannot reach the 20-frame floor anyway.

---

## 5. Replay discipline

`FrameEstimator` owns a per-instance generator (`pc/rff/dsp.py:118`) handed to
`ransac_line` on every frame (`:132`), which draws two
`rng.integers(0, n, size=64)` per call (`:85-86`). The generator advances once
per fitted frame, so the hypotheses tried at frame N depend on how many frames
preceded N **in that stream** (`docs/V2_SPEC.md` §5.5).

**Every stream is replayed from the start of its file with a fresh estimator**,
one per (node, source-MAC), with no window, filter or subsample applied ahead
of it. The `part`/`merge` split pickles estimator state forward and is
verified at merge against `wc -l` minus the header; `docs/COLOCATED_0823.md`
§1 establishes the split reproduces a single uninterrupted pass byte-identically.

---

## 6. The detection floor

**A null result here means "no effect above |r| = X", never "no effect".**
X is computed from the n actually obtained, not assumed.

For the partial correlation, `df = n − 3`, and the two-tailed p < 0.05
threshold is

  `r_crit = t_crit / sqrt( t_crit² + df )`,  `t_crit = t(0.975, df)`

For the raw correlation, `df = n − 2`. Both are computed and printed by the
script from `scipy`-free closed form (Student-t quantile by bisection on the
incomplete beta), for the exact n obtained, and both appear in the results.

Indicative values, so the frozen expectation is on the record: at n = 14
(df = 11) `r_crit ≈ 0.553`; at n = 12 (df = 9) `≈ 0.602`; at n = 10 (df = 7)
`≈ 0.666`; at n = 8 (df = 5) `≈ 0.754`. **The floor is bad and known to be
bad before the test is run.** This test can only detect a strong effect.

**Underpowered is declared, not inferred**, under either condition:

- `n < 6` (df ≤ 3) — no inference of any kind is drawn; the correlation is
  reported as uninterpretable.
- `r_crit > 0.70` — the test is declared underpowered for anything but a very
  strong effect, and a non-significant result is reported as such rather than
  as support for H3.

---

## 7. What each outcome will be taken to mean

Decided now, applied mechanically to whatever comes out.

| outcome | reading |
|---|---|
| `r_partial <= −r_crit` | **H1 supported, H2 rejected.** The disagreement is fit noise. |
| `r_partial >= +r_crit` | **H2 supported, H1 rejected.** The disagreement is relative baseline geometry. |
| `\|r_partial\| < r_crit` **and** `R_disp < 2` | **H3 survives.** Fixed receiver-pair offset, no effect on RSSI above `r_crit`. |
| `\|r_partial\| < r_crit` **and** `R_disp >= 2` | **Neither.** Δ varies far more than sampling noise but not along RSSI. H1, H2 and H3 are all unsupported and the driver is something not on this list. |
| raw `r_xy` clears its floor but `r_partial` does not | **Consistent with frame count, not RSSI.** The apparent RSSI effect is the collinear confound. Reported as such, not as H1. |
| `n < 6`, or `r_crit > 0.70` with a non-significant result | **Underpowered.** No hypothesis is supported or rejected. |

The `Neither` row exists because it is the outcome the 23× beacon spread at
fixed geometry already makes plausible, and it must have a name before the
data is seen so that it cannot be quietly re-described later.

---

## 8. The operator's hypothesis — are the sparse d0wd addresses passers-by?

Equal billing, same freezing rules.

> IF the 22 "clean but sparse" d0wd addresses are devices transiting the
> building, THEN their frames cluster in one short contiguous window and never
> recur, BECAUSE a phone in a passing car is in range once. A resident device
> recurs across the six hours.

`pc/mac_census.py` **counts frames only and never looks at arrival time**, so
nothing in the repo has tested this. The 22 are the d0wd addresses with ≥ 1
clean frame and < 20 clean frames (`docs/COLOCATED_0823.md` §2); the count is
re-derived here rather than taken on trust.

### 8.1 The statistic

Let a source have `k` clean frames at times `t_1 <= ... <= t_k`, seconds of
`pc_time_us` since the file's first decodable row, and let `T = 24,123.12 s`
be the capture span. Under a **uniform-arrival null** the `k` arrivals are iid
Uniform(0, T). The **sample range**

  `W = (t_k − t_1) / T`

is then distributed Beta(k − 1, 2), giving the **exact** one-sided p-value for
clustering

  `p(W) = P(range <= W) = k·W^(k−1) − (k−1)·W^k`

This is the named statistic: **the normalised sample range against its exact
Beta(k−1, 2) null.** It is chosen over a KS test because it tests the stated
prediction — *all* frames inside one short window — rather than
non-uniformity in general. The one-sample **Kolmogorov–Smirnov** statistic
against Uniform(0,1) is reported as a secondary for every source.

### 8.2 The timestamp hazard

`pc_time_us` is a per-serial-drain-batch host stamp
(`pc/node_census.py:30-35`, `docs/HANDOFF.md` trap #1), not per-frame cadence.
Frames drained in one batch carry identical stamps, so `W` is floored at batch
granularity. It is used here only to place arrivals at minute scale, which is
the scale the hypothesis is about. Any source whose whole span is **< 1.0 s**
is reported as **single-batch**, with its p-value labelled an upper bound.

### 8.3 The decision rule, frozen and mutually exclusive

Applied in order:

1. `k < 2` → **undecidable** (the range statistic is undefined at k = 1).
2. `p(W) < 0.05` → **transient**.
3. `p(W) >= 0.05` **and** `W >= 0.5` → **resident** (frames span at least half
   the 6.70 h capture, consistent with recurrence).
4. otherwise → **undecidable**.

Reported for each: `k`, `W`, span in seconds, `p(W)`, KS statistic, the
number of distinct 600 s bins occupied out of 41, and the largest
inter-arrival gap. For the transient set, additionally whether the span is
≤ 600 s — passer-by scale as opposed to merely-clustered.

### 8.4 The detection floor for this test too

The minimum attainable p at a given `k` is 0 as `W → 0`, so the floor is
expressed as the largest `W` that can still reject: `W_crit(k)` solving
`k·W^(k−1) − (k−1)·W^k = 0.05`. The script prints the table for every `k`
present. Indicatively, `k = 2` rejects only for `W <= 0.0253` (≈ 610 s),
`k = 3` for `W <= 0.135`, `k = 5` for `W <= 0.343`. **At k = 2 the test can
only see a genuinely tight burst**, and a k = 2 source that fails to reject is
undecidable, not resident.

### 8.5 Cross-receiver check

A real passer-by is a physical event and should look transient on **both**
receivers, ten inches apart. Every sparse d0wd address is therefore also
classified on the S3 where it has ≥ 2 clean frames, and agreement or
disagreement between the two classifications is reported. Disagreement is
evidence the address is an artefact of one receiver rather than a device.
This is a check on the classification, not a fourth class.

---

## 9. What this pass will not do

- Not fuse any `pc/rff/` (phase) number with any `pc/occ/` (amplitude) number.
- Not derive or quote a device-ID accuracy figure.
- Not cite `docs/DIRECTION.md` as capability.
- Not propagate `docs/COLOCATED_0823.md` §5.2's 0.71σ into any device-ID claim.
- Not treat a surviving H3 as evidence the receiver term is silicon; §7's
  reading is the only reading.

---
---

# STAGE 2 — RESULTS

*Appended after the run. **Nothing above this line was edited.** No
prediction was revised, reworded, or joined by a new hypothesis. The two
places where that temptation arose are recorded in §14 rather than acted on.*

---

## 10. What was run, and the integrity checks

One script, `pc/exp_receiver_term_prereg.py`, from the repo root:

```
export RXTERM_CACHE=/tmp/rxterm
D=data/raw/d0wd_20260823_014740.csv
S=data/raw/s3_20260823_014740.csv
for p in 0 1 2 3 4 5 6 7 8 9; do
  python3 pc/exp_receiver_term_prereg.py part $D --tag d0wd \
      --part $p --nparts 10 --total-rows 3344351
done
for p in 0 1 2 3 4 5 6 7 8 9 10 11; do
  python3 pc/exp_receiver_term_prereg.py part $S --tag s3 \
      --part $p --nparts 12 --total-rows 4330849
done
python3 pc/exp_receiver_term_prereg.py merge --tag d0wd --nparts 10 --expect-rows 3344351
python3 pc/exp_receiver_term_prereg.py merge --tag s3   --nparts 12 --expect-rows 4330849
python3 pc/exp_receiver_term_prereg.py report --tags d0wd,s3
```

Every number below is from `report` unless it names another command. The
part counts (10 and 12, against `docs/COLOCATED_0823.md`'s 5) are set only by
this host's ~178 s cap on a shell call; the split point does not enter any
figure, and `merge` re-checks that rather than asserting it.

**Whole file, both nodes, first row to last.** The `part` loop's final byte
position equals the file size exactly on both — **2,866,404,334** and
**3,596,309,377** — and `merge` reports **3,344,351** and **4,330,849** data
rows against `wc -l` minus the header, MATCH on both, with the 20,000-row
prescan's `node_id`/`channel` mode AGREEing with the whole-file histogram.
`0` rows on either node had ≠ 13 fields or unparseable ints.

**Read-only, verified before and after.** `stat` reports the two files
unchanged across the pass: 2,866,404,334 and 3,596,309,377 bytes, mtimes
`2026-08-23 08:29:44.302952100 −0500` and `08:29:44.213825100 −0500`. No
serial port was opened. `git diff --cached --name-only` is empty, before and
after; nothing was staged, committed or pushed. `pc/rff/dsp.py` was not
modified. `pc/capture.py:compute_cfo`, `pc/phase_skew.py` and
`pc/fingerprint.py` were not used.

**Two files in the repo were written by this pass:** this one and
`pc/exp_receiver_term_prereg.py`. All state and report text went to
`$RXTERM_CACHE = /tmp/rxterm`, outside the repo tree. **One disclosed
exception:** `pc/__pycache__/exp_receiver_term_prereg.cpython-310.pyc`,
produced when the verification helper of §10.2 imported the module rather
than running it. `rm` on this mount returns `Operation not permitted`, so
this pass could not delete it; it is covered by `.gitignore:14`, exactly as
`docs/COLOCATED_0823.md` records for its own `.pyc`.

### 10.1 Both corrupt-row screens fired, and reconcile with the prior pass

| | d0wd | s3 |
|---|---|---|
| field screen | 187 | 1 |
| width-9 median filter | 186 | 1 |
| both | 183 | 1 |
| **union (corrupt)** | **190** | **1** |
| rate | 56.81 ppm | 0.23 ppm |
| **caught by the median filter ONLY** | **3** | 0 |
| clean rows | 3,344,161 | 4,330,848 |

**190 and 1 reproduce `docs/COLOCATED_0823.md` §3.1/§3.2 exactly**, including
the three d0wd rows invisible to the field screen. This pass has no `dropped`
accounting to protect, but the screen still matters here for a different
reason: those 190 rows carry 126 fabricated d0wd MACs, and unscreened they
would have entered the source census as devices.

### 10.2 Independent re-derivation

An `awk` implementation sharing no code with the script, using `$(NF-2)` /
`$(NF-1)` for `node_id` / `env_id` because `csi_data` contains commas:

```
awk -F, -v ND=68 'NR>1{nd=$(NF-2);ev=$(NF-1);ch=$7;ln=$9;nf=$6;rs=$5;
  ok=(nd==ND&&ev==0&&ch==6&&(ln==128||ln==256||ln==384)
      &&nf<=-70&&nf>=-110&&rs<=-10&&rs>=-100);
  if(!ok){bad++;next} kept++; c[$4]++; if(!($4 in f0))f0[$4]=$1; f1[$4]=$1}
 END{...}' data/raw/d0wd_20260823_014740.csv
```

- **d0wd**: `kept=3,344,164 screened=187 distinctCleanMACs=40 sparse<20=22`
- **s3**: `kept=4,330,848 screened=1 distinctCleanMACs=33 sparse<20=19`

`screened` matches the script's field-screen count on both. `kept` differs
from the script's clean-row count by **exactly 3 on the d0wd and 0 on the
S3** — the three median-filter-only rows, again. **40 and 33 reconcile with
`docs/COLOCATED_0823.md` §2 to the unit**: 40 = 18 real + 22 sparse,
33 = 14 + 19. And the awk's per-address arrival spans match the script's on
all eight d0wd sparse addresses with k ≥ 2, to 0.1 s (§15).

The statistical machinery was checked against sources outside itself:
Student-t quantiles reproduce the published table to 4 dp
(df 3 → 3.1824, df 4 → 2.7764, df 9 → 2.2622, df 30 → 2.0423); the exact
Beta(k−1,2) range CDF reproduces a 10⁶-draw Monte Carlo to ~4 dp at every
k and w used; `pearson` matches `numpy.corrcoef`; and the partial-correlation
formula matches an explicit residual regression to 6 dp.

---

## 11. The funnel — n at every step, and why n is 6 and not 14

| step | d0wd | s3 |
|---|---|---|
| 1. distinct MACs, every row | 166 | 34 |
| 2. seen only on corrupt rows | −126 | −1 |
| 3. distinct MACs on clean rows | **40** | **33** |
| 3b. of which ≥ 20 clean frames | 18 | 14 |

| step | n |
|---|---|
| 4. heard by **both** receivers (≥ 1 clean frame each) | **29** |
| — heard only by d0wd / only by s3 | 11 / 4 |
| 4b. ≥ 20 **clean** frames on both (the census floor) | **14** |
| 5. ≥ 20 **admissible** frames on both — **n for the test** | **6** |
| sensitivity floor 64 admissible on both | 5 |

**The anticipated n was the low teens (§1.1) and the obtained n is 6.** Step
4b lands on exactly 14, so the anticipation was right about the *census*
floor; the pre-registered floor is on **admissible** frames — fitted and
through both shipped gates — and that costs eight more sources. The criterion
was applied exactly as frozen in §4.5; what follows is why it bites so hard,
not a reason to move it.

Admissible-over-clean ratio for the 14 sources at the census floor:

| mac | adm/clean d0wd | adm/clean s3 | kept |
|---|---|---|---|
| `f4:2d:c9:70:72:30` B3 | 0.981 | 0.990 | yes |
| `28:05:a5:2f:fa:48` B2 | 0.202 | 0.988 | yes |
| `a4:f0:0f:77:91:20` B1 | 0.927 | 0.997 | yes |
| `7e:ed:82:d6:23:e8` | 0.983 | 0.999 | yes |
| `62:45:b4:f0:e1:97` | 0.997 | 1.000 | yes |
| `32:c8:46:83:87:d0` | 0.573 | 0.065 | yes |
| `1c:ce:51:f3:0d:fa` | **0.008** | **0.002** | no |
| `1e:ce:51:f3:0d:fa` | **0.000** | 0.007 | no |
| `ba:80:d5:0c:18:87` | 0.026 | 0.790 | no |
| `ee:a0:3d:e2:e5:a0` | 0.042 | 0.275 | no |
| `64:fa:2b:6d:05:3b` | 0.125 | 0.368 | no |
| `d2:eb:b6:ca:31:24` | 0.758 | 0.312 | no |
| `7e:f2:52:b7:1e:1f` | 0.946 | **0.000** | no |
| `be:eb:63:2a:08:56` | 0.976 | **0.000** | no |

**Established, and not something this pass went looking for: the shipped
gates are near-total for several ambient sources.** `1c:ce:51:f3:0d:fa` has
872 and 1,005 clean frames and yields **7 and 2** admissible ones — 0.8 % and
0.2 %. `1e:ce:51:f3:0d:fa` yields **zero** on the d0wd from 589 clean frames.
`7e:f2:52:b7:1e:1f` and `be:eb:63:2a:08:56` clear 95 % on the d0wd and
**0.0 %** on the S3 from 26 and 23 clean frames. That is a per-(receiver,
source) property of the same kind `docs/COLOCATED_0823.md` §4.1 records for
B2/d0wd, now visible on ambient sources and asymmetric between two receivers
ten inches apart. **Why is unknown and was not investigated** — nothing in
this pre-registration asks the question.

Every source dropped at step 4 or 5 is listed individually with both frame
counts and its reason in the `report` output, as §4 requires.

The three byte-neighbour addresses `docs/COLOCATED_0823.md` §2 flags as
likely undetected corruption (`fa:1e:c9:70:72:30`, `e4:21:e3:20:72:30`,
`d9:f4:a5:2f:fa:48`) carry **1 clean frame each** and were dropped at step 4
for not being heard by the S3, as §4 anticipated. They were not removed by
hand.

---

## 12. The substituted statistic passes its pre-registered check

| beacon | frame-level Δ | window 16,384 | window 64 | `COLOCATED_0823` §5.1 | frame vs w16384 |
|---|---|---|---|---|---|
| B1 | **+0.00147** | **+0.00168** | +0.00175 | +0.00168 | 12.6 % |
| B2 | **+0.03858** | **+0.03870** | +0.04019 | +0.03870 | 0.3 % |
| B3 | **−0.01538** | **−0.01610** | −0.01595 | −0.01610 | 4.5 % |

Rank order by |Δ| at frame level: **B2 > B3 > B1**, as §2.4 required.
All three agree with the window-16,384 statistic within 25 %.
**ACCEPTANCE CRITERION: PASS** — the frame-level statistic is the primary,
and the fallback branch of §2.4 is not taken.

**A stronger result fell out of the check than the check needed.** The
window-16,384 column reproduces `docs/COLOCATED_0823.md` §5.1 to **five
decimal places on all three beacons** (+0.00168 / +0.03870 / −0.01610), and
the window-64 column reproduces that document's window-64 figures exactly
too (+0.00175 / +0.04019 / −0.01595). This is an independent reproduction by
a separately written script over a differently-parted replay of the same
files — the 0.71σ / 16.33σ / 6.79σ the question is built on is confirmed, not
assumed.

---

## 13. The measurement

### 13.1 The six sources

σ = `BETWEEN_UNIT_SD` = 0.00237 throughout, so |Δ|/σ is comparable to
`docs/COLOCATED_0823.md` §5.1.

| mac | role | adm d0wd | adm s3 | SFO d0wd | SFO s3 | **Δ_signed** | **\|Δ\|/σ** | RSSI | rej % d0wd | rej % s3 |
|---|---|---|---|---|---|---|---|---|---|---|
| `f4:2d:c9:70:72:30` | B3 | 1,450,600 | 1,470,786 | +0.00988 | +0.02525 | **−0.01538** | 6.49 | −76.21 | 1.89 | 1.01 |
| `a4:f0:0f:77:91:20` | B1 | 784,198 | 1,256,700 | +0.01551 | +0.01404 | **+0.00147** | 0.62 | −80.97 | 7.26 | 0.29 |
| `28:05:a5:2f:fa:48` | B2 | 205,095 | 1,555,700 | +0.04415 | +0.00558 | **+0.03858** | 16.28 | −76.90 | **79.79** | 1.20 |
| `7e:ed:82:d6:23:e8` | — | 1,202 | 2,952 | −0.00081 | +0.00086 | **−0.00167** | 0.70 | −65.90 | 1.72 | 0.10 |
| `62:45:b4:f0:e1:97` | — | 689 | 2,693 | +0.00355 | +0.00411 | **−0.00055** | 0.23 | **−27.95** | 0.29 | 0.00 |
| `32:c8:46:83:87:d0` | — | 776 | 38 | +0.01736 | +0.05129 | **−0.03393** | 14.32 | −79.06 | 42.69 | **93.48** |

Three ambient sources join the three beacons on equal footing, as §1.1
requires. `62:45:b4:f0:e1:97` at −27.95 dB is by far the strongest source in
the room and extends the RSSI range the test can work over: the three beacons span
4.76 dB, and this one source sits 48.26 dB above the strongest of them,
taking the full range to 53.02 dB — which is the whole reason for not restricting to
beacons.

### 13.2 The correlations, and the detection floor

**PRIMARY — partial Spearman, control = log₁₀ n_min, n = 6:**

| quantity | value | p | floor |
|---|---|---|---|
| raw `r(\|Δ\|, RSSI)` | **−0.3714** | 0.4685 | \|r\| > **0.8114** (df 4) |
| control `r(\|Δ\|, log₁₀ n_min)` | +0.0286 | 0.9572 | |
| collinearity `r(RSSI, log₁₀ n_min)` | −0.2000 | 0.7040 | |
| **PARTIAL `r(\|Δ\|, RSSI · log n)`** | **−0.3734** | 0.5359 | **\|r\| > 0.8783 (df 3)** |

Pre-registered sensitivities:

| # | variant | n | raw r | partial r | floor |
|---|---|---|---|---|---|
| 1 | `RSSI_min` substituted | 6 | −0.5429 | **−0.5441** | 0.8783 |
| 2 | > 50 % gate rejection excluded | — | — | — | **not runnable** |
| 3 | Pearson on log₁₀\|Δ\| | 6 | −0.6693 | **−0.6910** | 0.8783 |
| 4 | window-64 Δ substituted | 5 | −0.7000 | **−0.4118** | 0.9500 (df 2) |

Sensitivity 2 excluded two sources — B2 (79.79 % on the d0wd) and
`32:c8:46:83:87:d0` (93.48 % on the S3) — leaving 4, below the 5 the script
requires to correlate. It is reported as not runnable rather than run on 4.

**The detection floor, computed for the n obtained, not assumed.** At n = 6
the partial has **df = 3** and needs **|r| > 0.8783** to clear p < 0.05
two-tailed. The brief's reference point of |r| ≈ 0.53 at n ≈ 14 is confirmed
by the same code (n = 14 → 0.5324 raw, **0.5529 partial**) — the usable n is
smaller than 14, so the floor is worse, exactly as §6 warned it might be.
**A null here means "no RSSI effect above |r| = 0.878". It does not mean
"no effect".**

**The collinearity the control exists for did not materialise in this
sample.** `r(RSSI, log₁₀ n_min) = −0.2000`, p = 0.70 — RSSI and frame count
are essentially uncorrelated across these six sources, so the partial
(−0.3734) barely moves from the raw (−0.3714). The control was necessary to
pre-register and turned out not to bind. That is worth stating plainly: on
this sample the confound was not doing the work, and the correlation still
does not clear its floor.

### 13.3 H3 — falsified, and not by the underpowered arm

| mac | role | Δ_signed | block-bootstrap sd(Δ) |
|---|---|---|---|
| `f4:2d:c9:70:72:30` | B3 | −0.01538 | 0.000136 |
| `a4:f0:0f:77:91:20` | B1 | +0.00147 | 0.000149 |
| `28:05:a5:2f:fa:48` | B2 | +0.03858 | 0.001518 |
| `7e:ed:82:d6:23:e8` | — | −0.00167 | 0.000289 |
| `62:45:b4:f0:e1:97` | — | −0.00055 | 0.000071 |
| `32:c8:46:83:87:d0` | — | −0.03393 | 0.013620 |

| | value |
|---|---|
| Var across sources of Δ_signed | 5.719 × 10⁻⁴ |
| median block-bootstrap Var(Δ) | 5.281 × 10⁻⁸ (a **lower bound**, §2.5) |
| **`R_disp`** | **10,830** (H3 survives only if < 2) |
| range ratio max\|Δ\| / min\|Δ\| | **69.9** |
| signs of Δ_signed | **2 positive, 4 negative** |

**H3 is FALSIFIED**, by four orders of magnitude on the pre-registered
threshold, and it is falsified in a way that does not depend on the
correlation's power: `R_disp` is a dispersion comparison, not a significance
test. Even taking the bootstrap variance as the lower bound §2.5 says it is,
it would have to be understated by ~5,000× for `R_disp` to reach 2. The
mixed signs settle it independently — a fixed receiver-pair offset cannot be
+0.039 on one source and −0.034 on another.

The 23× spread the question started from is **69.9× once ambient sources
join the beacons.**

### 13.4 The verdict, applied mechanically from §7

> **NEITHER** — |r_partial| = 0.373 < 0.878, and `R_disp` = 10,830 ≥ 2, so
> H3 is falsified too.
>
> **UNDERPOWERED** — the floor 0.878 exceeds 0.70, so the non-significant
> partial is not support for H3.

Both rows of §7 fire, and they say different things about different arms, so
both are reported:

- **The H1-vs-H2 arm is underpowered and settles nothing.** At n = 6 with a
  floor of 0.878, this test could only have detected an almost perfectly
  monotone relationship. It did not detect one. **H1 is not supported, H2 is
  not supported, and neither is rejected.** The discriminating power the
  opposite-sign design was built for was not delivered by this sample.
- **The H3 arm is not underpowered and does reject.** Δ_signed varies far
  beyond sampling noise and changes sign. **The disagreement is not a
  property of the receiver pair.**

**So the question "why does it vary?" is not answered by this test.** What is
established is that it *does* vary, by 69.9× across six sources at fixed
geometry, and that the one hypothesis of the three that could be tested at
this n is wrong.

**The direction of the effect, stated as direction and not as a result.** All
four correlation variants come out negative — −0.3734, −0.5441, −0.6910,
−0.4118 — which is H1's predicted sign. **None of them reaches its floor**,
the largest (−0.691) is 0.79 of the way there, and four variants of one
underpowered test are not four tests. This is recorded so the sign is on the
record for a future pass to pre-register against, and for no other purpose.
It is **not** weak support for H1; see §14.

---

## 14. Temptations recorded, and not acted on

Per the preamble. Each of these was wanted while writing §13 and none was
done.

1. **To relax the floor from admissible frames to clean frames and recover
   n = 14.** Step 4b lands on exactly 14 and the temptation was strong. Not
   done: choosing an inclusion rule after seeing that the frozen one yields
   n = 6 is precisely the move this document exists to prevent, and the
   result at n = 14 would be uninterpretable because the rule would have been
   selected for its n. **This is the single most useful thing for the next
   pass to pre-register instead** — see §17.
2. **To promote the consistently negative sign into "weak support for H1".**
   Not done. Four variants of one underpowered test on six sources are one
   observation, and §7 has no "weak support" row.
3. **To add a fourth hypothesis to explain the `NEITHER` outcome.** The
   six-row table of §13.1 is suggestive: the two largest |Δ| (16.28σ and
   14.32σ) are the two cells with > 50 % gate rejection (79.79 % and
   93.48 %), and the four small ones all reject under 8 %. Not done, and not
   tested. `docs/POSITIVE_CONTROL_0822.md` §5 already lists "lowest
   acceptance ↔ largest inter-receiver difference" under **permitted, not
   established**, and `docs/COLOCATED_0823.md` §5.4 declines to promote it on
   the grounds that the middle of the range is not monotone. **This pass adds
   six data points to that standing question and promotes nothing.** It is
   named here as a candidate for the next pre-registration, not as a finding.
4. **To reword H2 so that `62:45:b4:f0:e1:97` — the −27.95 dB source with the
   smallest |Δ| of the six — reads as evidence against it.** Not done. H2's
   prediction is about a correlation, the correlation does not clear its
   floor, and one source is not a test.
5. **To classify the 14 single-frame sparse addresses as transient** on the
   reasoning that "heard once and never again" is what a passer-by looks
   like. Not done: at k = 1 the uniform-arrival null is unfalsifiable (W ≡ 0
   for every k = 1 source, resident or not), and k = 1 is exactly where
   `docs/COLOCATED_0823.md` §2's undetected corruption lives.

---

## 15. The operator's hypothesis — the sparse addresses

**Statistic:** the normalised sample range `W = (t_k − t_1)/T` against its
exact Beta(k−1, 2) uniform-arrival null, `p = k·W^(k−1) − (k−1)·W^k`, with
`T = 24,123.12 s`. Verified against a 10⁶-draw Monte Carlo (§10.2).
`pc/mac_census.py` counts frames only and never looks at arrival time.

**The 22 reproduce**, from clean rows and independently from `awk` (§10.2).

### 15.1 Detection floor, computed per k

Largest W that can still reject at α = 0.05:

| k | W_crit | in seconds |
|---|---|---|
| 2 | 0.0253 | 611 |
| 3 | 0.1354 | 3,265 |
| 4 | 0.2486 | 5,997 |
| 5 | 0.3426 | 8,264 |
| 9 | 0.5709 | 13,771 |
| 19 | 0.7736 | 18,662 |

**At k = 2 the test can only see a burst tighter than about ten minutes.** A
k = 2 source that fails to reject is undecidable, not resident.

### 15.2 The d0wd split

| mac | k | span s | W | p | KS | 600 s bins /41 | max gap s | class |
|---|---|---|---|---|---|---|---|---|
| `28:f5:2b:4f:7c:6b` | 9 | 22,251.1 | 0.9224 | 0.849 | 0.218 | **6** | 7,840.6 | **resident** |
| `f0:7b:65:5e:ec:2c` | 5 | 3,081.0 | 0.1277 | 0.0012 | 0.867 | 3 | 1,820.6 | **transient** |
| `92:95:4f:74:c5:49` | 4 | 10.6 | 0.0004 | <10⁻⁵ | 0.679 | 1 | 6.0 | **transient** ≤600 s |
| `72:90:a2:7d:6f:fb` | 2 | 0.3 | <10⁻⁴ | 3×10⁻⁵ | 0.940 | 1 | 0.3 | **transient** ≤600 s, single-batch |
| `62:45:b2:0c:fb:78` | 2 | 43.0 | 0.0018 | 0.0036 | 0.670 | 1 | 43.0 | **transient** ≤600 s |
| `56:96:75:ef:30:81` | 2 | 0.0 | 0.0000 | <10⁻⁵ | 0.626 | 1 | 0.0 | **transient** ≤600 s, single-batch |
| `10:38:1f:da:79:31` | 2 | 409.7 | 0.0170 | 0.0337 | 0.790 | 2 | 409.7 | **transient** ≤600 s |
| `26:ce:cf:10:34:26` | 2 | 0.0 | 0.0000 | <10⁻⁵ | 0.898 | 1 | 0.0 | **transient** ≤600 s, single-batch |
| 14 further addresses | **1** | 0.0 | — | undefined | — | 1 | — | **undecidable** |

> **d0wd SPLIT: 7 transient, 1 resident, 14 undecidable — of 22.**
> Six of the seven transients are at passer-by scale (span ≤ 600 s) — all but
> `f0:7b:65:5e:ec:2c` at 3,081 s; three of those six are single-batch, where
> p is an upper bound (§8.2).

**All 14 undecidables are k = 1**, i.e. undecidable by construction rather
than by weak evidence. Among them are all three byte-neighbour addresses
`docs/COLOCATED_0823.md` §2 flags as likely undetected corruption. **At k = 1
this test cannot separate "a device heard once" from "one corrupt row", and
that is the honest limit of the answer**, not a shortcoming of the decision
rule.

### 15.3 The S3, for comparison

> **s3 SPLIT: 14 transient, 2 resident, 3 undecidable — of 19.**

The S3's sparse population is far more decidable — only 3 of its 19 are
k = 1, against 14 of 22 on the d0wd — and overwhelmingly transient. Three of
its transients are striking: `9e:38:41:e0:97:0d` puts 19 frames into 74.3 s,
`6e:0a:30:1f:ed:21` 12 frames into 6.1 s, `32:a7:21:0b:32:85` 11 frames into
13.5 s. Each is one burst inside a 6.70 h file, each in a single 600 s bin,
p < 10⁻⁵.

### 15.4 The cross-receiver check

| mac | d0wd k / class | s3 k / class | agree |
|---|---|---|---|
| `28:f5:2b:4f:7c:6b` | 9 resident | 9 resident | yes |
| `f0:7b:65:5e:ec:2c` | 5 transient | 2 transient | yes |
| `56:96:75:ef:30:81` | 2 transient | 2 transient | yes |
| `10:38:1f:da:79:31` | 2 transient | 2 transient | yes |
| `26:ce:cf:10:34:26` | 2 transient | 7 transient | yes |

> **agree 5, disagree 0, not comparable 17.**

Every comparable pair agrees. That matters most for the three single-batch
d0wd transients, which on one receiver alone are indistinguishable from a
corruption burst: `56:96:75:ef:30:81` and `26:ce:cf:10:34:26` are classified
transient **independently on both receivers**, and two boards ten inches
apart do not corrupt the same fabricated address at the same instant. Those
two are real transmissions.

The 17 not-comparable pairs are **11** addresses the S3 never heard and **6**
where one side is k = 1.

### 15.5 The answer

**Of the 8 d0wd sparse addresses this test can decide, 7 are transient and 1
is resident.** The transients look like the hypothesis predicts — one
contiguous burst, one 600 s bin, no recurrence across the remaining 6.7 h —
and 6 of the 7 are at literal passer-by scale. The single resident,
`28:f5:2b:4f:7c:6b`, is the counter-example that shows the statistic
discriminates rather than always firing: 9 frames spread over 22,251 s in 6
separate 600 s bins with a 7,840 s maximum gap, and resident on both
receivers.

**But 14 of the 22 are single-frame and structurally undecidable**, so the
honest headline is **7 / 1 / 14**, not "7 of 8". The hypothesis is
**supported on the decidable subset and untested on two thirds of the
population.** Whether the k = 1 majority are one-frame passers-by or
undetected corruption is **unknown**, and `docs/COLOCATED_0823.md` §2's
byte-neighbour finding is a live reason to think at least some are the
latter.

---

## 16. Summary by evidential status

**Established by this pass** — re-derivable now by the commands in §10:

- The whole of both files was read, **3,344,351 + 4,330,849 = 7,675,200
  rows**, final byte position equal to file size on both, files unchanged.
  §10.
- **190 and 1 corrupt rows**, three of the d0wd's caught only by the median
  filter — `docs/COLOCATED_0823.md` §3.1/§3.2 reproduced exactly, and
  independently by `awk`. §10.1, §10.2.
- **The clean-row source census reconciles with `docs/COLOCATED_0823.md` §2
  to the unit**: 40 = 18 + 22 on the d0wd, 33 = 14 + 19 on the S3. §10.2.
- **`docs/COLOCATED_0823.md` §5.1 is independently reproduced to five decimal
  places** — +0.00168 / +0.03870 / −0.01610 at window 16,384 and
  +0.00175 / +0.04019 / −0.01595 at window 64 — by a separately written
  script over a differently-parted replay. §12.
- **n = 6.** 29 sources heard by both, 14 at the census floor, 6 at the
  pre-registered admissible-frame floor. §11.
- **The shipped gates admit under 1 % of the clean frames of some ambient
  sources**, asymmetrically between two receivers ten inches apart
  (`1c:ce:51:f3:0d:fa` 0.8 % / 0.2 %; `be:eb:63:2a:08:56` 97.6 % / 0.0 %).
  §11.
- **The disagreement spread is 69.9×, not 23×**, once ambient sources join
  the beacons on equal footing. §13.3.
- **H3 is falsified.** `R_disp` = 10,830 against a threshold of 2, and
  Δ_signed changes sign (2 positive, 4 negative). The disagreement is not a
  fixed property of the receiver pair. §13.3.
- **The H1-vs-H2 test is underpowered**: n = 6, df = 3, detection floor
  **|r| > 0.8783**, partial r = **−0.3734**. Neither hypothesis is supported
  or rejected. §13.2, §13.4.
- **RSSI and frame count were not collinear in this sample**
  (r = −0.20, p = 0.70), so the control did not bind and the partial is
  within 0.002 of the raw correlation. §13.2.
- **Sparse d0wd addresses: 7 transient, 1 resident, 14 undecidable of 22**,
  with every one of the 5 cross-receiver-comparable classifications
  agreeing. §15.

**Permitted by this pass, not established:**

- That the disagreement tracks estimator noise (H1). All four correlation
  variants carry H1's sign; none clears its floor. §13.4, §14.2.
- That gate rejection selects which cells carry a large disagreement. The
  two largest |Δ| are the two > 50 %-rejection cells. Not tested here, and
  already on the record as permitted-not-established in
  `docs/POSITIVE_CONTROL_0822.md` §5. §14.3.

**Unknown, and named as unknown:**

- **Why the disagreement varies.** This is the question the pass was run to
  answer and it is not answered. §13.4.
- Why the shipped gates reject ~100 % of some ambient sources on one
  receiver and ~0 % on the other. §11.
- Whether the 14 single-frame sparse addresses are passers-by or undetected
  corruption. §15.5.
- Whether `92:95:4f:74:c5:49` — 4 frames in 10.6 s on the d0wd, **never heard
  by the S3** ten inches away — is a passer-by or an artefact. It is counted
  transient because the frozen rule counts it transient. §15.2.

**Not claimed anywhere above:** no device-ID accuracy figure is derived; no
`pc/rff/` (phase) number is combined with any `pc/occ/` (amplitude) number;
`docs/DIRECTION.md` is not cited as capability; and
`docs/COLOCATED_0823.md` §5.2's 0.71σ is not propagated into any device-ID
claim.

---

## 17. For the next pass

1. **Pre-register the inclusion floor on clean frames, with admissibility as
   a reported covariate rather than a gate.** §14.1 records why this pass
   would not do it retroactively. Doing it prospectively takes n from 6 to
   14, and the floor from 0.878 to **0.553** — computed by the same code, and
   the only change on this list that fixes the actual problem.
2. **n = 14 is still not enough for a 3-way discrimination.** The floor at
   0.553 detects only a strong effect. Pooling sources across several
   co-located sessions is the cheap way to a usable n, and
   `docs/COLOCATED_0823.md` §8.2 already asks for alternating
   separated/co-located captures for a different reason.
3. **The gate-rejection hypothesis of §14.3 now has six points and a
   suggestive pattern.** It should be written down as a prediction with a
   sign before it is measured again, not after.
4. **The k = 1 problem in §15 is a capture-side problem, not an analysis-side
   one.** Nothing in a 6.7 h file can decide a single-frame address. If
   passers-by matter, the `label`/STATUS record of `docs/V2_SPEC.md` §2.7 and
   a longer baseline are what would decide them.
