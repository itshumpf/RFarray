# KAPPA_CROSS_SESSION — does `κ` survive the test that killed the slope?

**Stage 1 (everything above the `STAGE 2` banner) was written and saved
before any statistic in this document was computed.** Nothing was run before
it was written except `ls` on `data/raw/`, and reads of
`pc/exp_iq_imbalance.py`, `pc/exp_identity_stability.py` and
`pc/rff/discriminator.py` to establish the interfaces named in §4.

**Date:** 2026-08-27 · **Scope:** read-only on `data/raw/`. No serial port.
Nothing in `pc/rff/` is modified. No git command is run.

---

## 0. The question, and why it is the only one worth asking right now

`docs/IDENTITY_STABILITY.md` §8 and §12 established that the SFO slope does
not carry identity across a session boundary, and does not reliably carry it
across *tens of minutes inside* one session. §13 established why reference
subtraction cannot repair that: the drift is **not common-mode**. A shared
constant removes only **7–46 %** of the drift energy and leaves a per-device
residual of **2.2× to 7.1× the entire between-device spread**. You cannot
subtract away something that is not shared.

`docs/IQ_IMBALANCE.md` §14 then measured a second feature — the transmitter's
IQ imbalance `κ` — against that same standard, on identical data, identical
chunking, and an identical statistic:

| feature | d0wd | s3 | verdict |
|---|---:|---:|---|
| **`κ`** | **0.41×** | **0.20×** | STABLE |
| deterministic slope, same pass | 0.84× | 1.07× | comparator |
| SFO slope, published cross-session | 2.2–7.1× | | the thing that failed |

`κ` stays below 1.0 on both receivers **even for chunk pairs 6.5 hours
apart**. That document's own summary: *"the devices do not swap places."*

And then it stops, deliberately, at §14:

> **The published 2.2–7.1× is a harder, cross-session measurement and `κ` has
> not yet been put through it.**

This pass puts it through it.

### 0.1 The hazard, named in advance

`IQ_IMBALANCE.md` §15.1 records that on the d0wd **both** beacons rotated by
~155° between two captures — B1 by 158.5°, B2 by 153.2° — and that the cause
is unknown and was not investigated. §18 names it as the first thing to
settle and as *"a live hazard for any cross-session use of `κ`."*

That hazard is also the reason this pass might succeed. **158.5° and 153.2°
differ by 5.3°, which is 3.4 % of the rotation.** A disturbance that lands on
every source at one receiver to within a few percent is the definition of a
common mode — and a common mode is exactly what reference correction removes.
The slope's drift failed that test (7–46 % shared). `κ`'s rotation, on the one
observation available, looks like it would pass it.

**One observation of two beacons at one receiver across one capture pair is
not evidence.** It is the reason to run the test, and it is written here as a
hypothesis so that it cannot be presented afterwards as a finding.

---

## 1. Hypotheses, frozen

**H1 — the per-session `κ` rotation is common-mode across sources at a fixed
receiver**, and can therefore be removed by a single per-(receiver, session)
rotation.

**H2 — with the H1 rotation removed, `κ` identifies devices across session
boundaries on a fixed receiver**, on the same chronological protocol that
returned 29.7 % for the slope.

H2 is scored **whether or not H1 passes.** If H1 fails, H2 is run without
common-mode removal and reported as such; a feature could in principle
survive without needing the correction.

---

## 2. Decision rules, frozen before the numbers exist

### 2.1 H1 — common-mode

For each receiver and each ordered session pair, per beacon:
`Δ(m) = arg κ(session B, m) − arg κ(session A, m)`, wrapped to (−π, π].

Statistic: **`R_cm` = circular spread of `Δ` across beacons ÷ |circular mean
of `Δ`|**, computed only on pairs where **≥ 3 beacons** clear the §3 floor.

| `R_cm` | verdict |
|---|---|
| **≤ 0.25** | **COMMON-MODE.** The beacons rotate together; a single rotation removes it. |
| 0.25 – 1.00 | **PARTIAL.** Report the fraction of rotation energy removed, directly comparable to `IDENTITY_STABILITY.md` §13's 7–46 % for the slope. |
| **> 1.00** | **NOT COMMON-MODE.** The spread exceeds the mean; there is nothing shared to subtract. H1 fails. |

0.25 is chosen because the single observed case (§0.1) sits at 0.034. A bar
seven times looser than the observation it was motivated by is a bar the
observation cannot have been fitted to.

### 2.2 H2 — cross-session identification

Protocol identical to `pc/exp_identity_stability.py`: ordered session pairs on
one fixed receiver, enroll on A, test on B, chronological, never pooled across
receivers. **N classes is printed next to every accuracy figure in this
document, without exception** (`IDENTITY_STABILITY.md` §1.3 — the ~77 %
same-model figure is permanently uninterpretable because its class count was
never written down, and this document will not create a second one).

Both accuracy definitions are reported, as §1.5 of that document requires:
`A_gated` (STRANGER counts in the denominator, not the numerator) and `A_nn`
(nearest centroid, gate ignored).

Median across ordered pairs, against N classes:

| median `A_nn` | verdict |
|---|---|
| **≥ 2/N** and **> the slope's median on the same pairs** | **PASS.** `κ` carries cross-session identity where the slope does not. |
| ≥ 2/N but ≤ the slope | **MARGINAL.** Better than chance, not better than what already failed. |
| **< 2/N** | **FAIL. The branch closes.** |

2/N is the bar `pc/exp_identity_stability.py` already prints beside chance
(`threshold 2/N`, line 699). It is adopted here unchanged rather than chosen.

### 2.3 What would make the whole pass unreportable

If the **positive control fails** — if `κ` cannot identify devices *within* a
session on this corpus — then no cross-session number means anything and none
will be quoted. Stated now so it cannot be quietly dropped later.

---

## 3. Floors, frozen

- **`MIN_WIN = 10`** cells per (session, device), unchanged from
  `exp_identity_stability.py:48`.
- **Chunk = 600 s**, unchanged from `exp_iq_imbalance.py:CHUNK_S`, which took
  it from `RECEIVER_TERM_PREREG.md` §8.3.
- A cell enters only if `features(c)["detected2"]` is true — the alignment
  detection `IQ_IMBALANCE.md` §10.3 pre-registered — so that undetected `κ`
  is never scored as though it were a measurement.
- Corrupt-row screens are `exp_iq_imbalance.py`'s, unchanged. `LABELLED_EVENTS_0823.md`
  §14.1 found 19 fabricated byte-neighbour MACs on the d0wd; those screens
  caught all 19 and they are not relaxed here.

---

## 4. The estimator, and one place the shipped code cannot be used

`κ` comes from `pc/exp_iq_imbalance.py::features()["kappa"]`, imported, not
reimplemented. The session-pairing and scoring logic comes from
`pc/exp_identity_stability.py`. `pc/rff/dsp.py` is imported unmodified.

**The shipped `Discriminator` cannot be used on `κ` and this pass does not
pretend otherwise.** `pc/rff/discriminator.py:27` sets

```python
_VAR_FLOOR = np.array([1.0, 1e-8])      # CFO in Hz², SFO in (rad/subcarrier)²
```

Those floors are in physical units of the *slope* feature. `κ` is a
dimensionless ratio of order 10⁻². Feeding `[Re κ, Im κ]` to the shipped class
would apply a variance floor roughly **10⁶ times κ's own scale** on the first
axis, inflating every ellipse until every observation matches every model.
The resulting accuracy would be an artifact of a unit mismatch.

So this pass **standardizes both features identically** — z-scored on the
pooled within-device covariance of the **enrollment half only**, never the
test half — and applies a floor scaled to that standardized space. The
classifier is otherwise `Discriminator` as shipped, subclassed in the new
file. **Nothing in `pc/rff/` is edited.**

**Consequence, stated in advance:** the numbers this pass produces are
**not comparable to any figure produced at the shipped floors**, including
99.7 %/7,497 and 95.7 %/14,234. They are comparable only to the slope figure
this same pass computes on the same cells under the same standardization.
This is the same rule `GATE_CALIBRATION.md` §8.5 applied to its own loosened
gates.

### 4.1 Dimensionality is not symmetric, and the fix is pre-registered

`κ` is naturally 2-D (`Re`, `Im`). The slope is 1-D. The shipped 2-D slope
feature is `[cfo, sfo]`, and `SEPARATION_SCALING.md` §3.3 measured the CFO
axis at **0.01σ–0.21σ** — it contributes nothing, so `[cfo, sfo]` is a 1-D
feature carrying a dead axis. Scoring 2-D `κ` against that is not like-for-like:
a second real dimension is more room to separate, independent of physics.

So **three arms are run, all pre-registered here:**

| arm | `κ` feature | slope feature | purpose |
|---|---|---|---|
| **A (primary)** | `[Re κ, Im κ]` | `[cfo, sfo]` | as each feature is naturally used |
| **B (fair 1-D)** | `[arg κ]` | `[sfo]` | one real dimension each |
| **C** | `[\|κ\|]` | `[sfo]` | magnitude only; `IQ_IMBALANCE.md` §18 warns `\|κ\|` is diluted by additive noise and not comparable across links of different strength — arm C exists to show that, not to be quoted alone |

If A passes and B fails, the honest conclusion is that the gain came from
dimensionality and not from `κ`, and it will be reported that way.

---

## 5. Controls

- **P1 — positive control.** Within-session `κ` identification, same chunks,
  enroll on the first 60 % of a session's cells and test on the last 40 %.
  `IQ_IMBALANCE.md` §13 reports blind k-means purity 0.992 (d0wd) / 1.000
  (s3), so a within-session failure here would indicate a harness bug, not a
  physics result, and the pass would stop.
- **N1 — negative control.** Device labels permuted within each session, seed
  frozen at `20260827`. Accuracy must collapse to chance. `GATE_CALIBRATION.md`
  §4 records a run whose answer moved because it seeded from Python's salted
  `hash()`; this pass seeds explicitly and prints the seed with the result.
- **N2 — receiver control.** Every number is computed per receiver and never
  pooled. `BLIND_CLUSTERING.md` §1: pooling the two receivers *"would cluster
  the receivers, and the result would be worthless."*

---

## 6. What this pass cannot show, written before it is run

- **Nothing about cross-*receiver* `κ`.** `IQ_IMBALANCE.md` §15 measured
  `frac_rx = 5.73` (two receivers disagree about one transmitter by 5.7× the
  entire spread between transmitters) and `R_disp = 826.6` against a threshold
  of < 2 — **RECEIVER-DOMINATED, additive model does not hold.** This pass is
  single-receiver throughout and makes no cross-receiver claim.
- **No cause for the ~155° rotation.** If H1 passes, a common mode has been
  *removed*, not *explained*. Attributing it to a receiver reboot, reflash or
  reseat with nothing in the data recording one would be `CLAUDE.md` failure
  mode **G**, and `THERMAL_STEP.md` §1.4 already had to correct exactly that
  inference once.
- **Nothing fused with `pc/occ/`.** Device-ID and occupancy are separate
  pipelines and their numbers are never combined.
- **No revision of 99.7 %/7,497 or 95.7 %/14,234.** Different corpus,
  different feature, different standardization. Per §4, not comparable.
- **The ~77 % same-model figure is not quoted and not relabelled.**
- **`docs/DIRECTION.md` is not cited as capability.**

---

## 7. Reproduce

```
python pc\exp_kappa_cross_session.py scan   data\raw\<file>.csv --tag <tag>
python pc\exp_kappa_cross_session.py score
python pc\exp_kappa_cross_session.py report
```

Every figure in Stage 2 carries the command that regenerates it. A number
that cannot name its command is labelled a guess (`CLAUDE.md` failure mode A).

---

## STAGE 2 — results

**Run 2026-08-27.** 19 sessions scanned, ~31 GB, `pc/exp_kappa_cross_session.py`.
Nothing above this banner was edited after the run.

### 8. Verdict in one line

**Both hypotheses fail their frozen bars. `κ` is nonetheless 22–28 percentage
points better than the slope at cross-session identification on the same
pairs, in all three arms, with every confidence interval excluding zero — and
this test does not have the power to say whether that is enough.**

| | bar | measured | verdict |
|---|---|---|---|
| **H1** common-mode rotation | `R_cm` ≤ 0.25 | 0.392 / 0.758 / 5.532 | **FAIL** — partial, and highly variable |
| **H2** cross-session ID | median `A_nn` ≥ 2/N = 66.7 % | **65.2 %** | **FAIL** — by 1.5 pp, inside its own CI |

Per §2.2 the branch closes. §8.4 records why that verdict should be read as
*underpowered*, not as *refuted*.

### 8.1 Two things checked before anything was believed

- **The classifier bridge.** `python pc\exp_kappa_cross_session.py verify` —
  2,000 random observations against 3 models at the shipped floors
  `[1.0, 1e-8]`: **0 disagreements** with `pc/rff/discriminator.py`. The only
  difference between this file's classifier and the shipped one is the
  standardization declared in §4.
- **The reader agrees with a script written by someone else.** This pass's
  scan independently returned **3,344,351 rows / 190 corrupt** on
  `d0wd_20260823_014740` and **4,330,849 / 1** on `s3_20260823_014740` —
  both matching `GATE_CALIBRATION.md` §3.2 exactly. Different script, same
  bytes, same answer.

### 8.2 Floor accounting — and the d0wd receiver fails it

`python pc\exp_kappa_cross_session.py floors <tags>`

A cell enters only if it clears `detected2` (§3). Sessions reaching
`MIN_WIN = 10` cells for a device:

| receiver | sessions with **3** beacons clearing | sessions with 2 | with 1 |
|---|---|---|---|
| **s3** | **4** — `20260822_023034`, `20260823_014740`, `20260823_180002`, `20260823_224914` | 0 | 0 |
| **d0wd** | **0** | 3 | 1 |

**The d0wd receiver never gets all three beacons over the floor in a single
session.** That is a floor failure, not a null — it is not evidence that `κ`
behaves differently there, because the measurement was never available. It is
consistent with what the corpus already records about that receiver:
`SEPARATION_SCALING.md` §7 measures a d0wd cell rejecting **59.5 %** of
frames, and `GATE_CALIBRATION.md` §3.2 puts its corrupt-row rate at **56.81
ppm** against the s3's **0.23 ppm**.

**Consequence: every H2 number below is single-receiver, s3 only, N = 3.** The
two scoreable d0wd pairs (N = 2, 107 tests) return **49.0 %** for `κ` and
between **57.6 % and 94.8 %** for the slope depending on which arm is asked —
a 37-point disagreement between arms on the same two pairs. **Nothing from the
d0wd block is quoted here**, in either direction.

### 8.3 H1 — the rotation is partial, not common

`s3`, three ordered adjacent session pairs, all three beacons:

| pair | per-beacon rotation | mean | spread | `R_cm` | rotation energy removed | verdict |
|---|---|---:|---:|---:|---:|---|
| `023034 → 014740` | −16.5°, −17.0°, +0.8° | −10.9° | 8.3° | 0.758 | **63.5 %** | PARTIAL |
| `014740 → 180002` | −6.5°, −8.3°, +10.3° | −1.5° | 8.4° | 5.532 | **3.1 %** | NOT COMMON-MODE |
| `180002 → 224914` | +20.2°, +42.1°, +19.1° | +27.1° | 10.6° | 0.392 | **86.8 %** | PARTIAL |

**No pair reaches the 0.25 bar. H1 fails.**

The §0.1 hypothesis — that the ~155° rotation `IQ_IMBALANCE.md` §15.1 observed
is a clean receiver-side common mode — **is not supported at this scale.** Two
of three pairs remove 63.5 % and 86.8 % of the rotation energy with a single
shared angle, which is *better* than the 7–46 % `IDENTITY_STABILITY.md` §13
measured for the slope's drift; one pair removes 3.1 %, which is worse than
the slope's floor. A correction that works twice and fails once is not a
correction.

**⚠ Annotated 2026-08-27, after this pass was written.** The
`180002 → 224914` row above — the best of the three, at 86.8 % — uses a
session that contains an **undocumented 25-minute beacon outage**. In
`*_20260823_224914.csv`, B3 (`f4:2d:c9:70:72:30`) is off air from
t = 3,699 s to t = 5,201 s, **1,501.8 s**, on both receivers simultaneously.
This pass pooled B3's `κ` across that gap without knowing it was there.

Checked after the fact: B3 returns at **−66 → −67 dBm (s3)** and **−71 → −70
dBm (d0wd)**, i.e. **powered down in place, not moved** — and on the d0wd its
+1.0 dB is *smaller* than the +2.0 dB that untouched B1 and B2 drift over the
same window. So the pooled `κ` is probably not corrupted by it. **Probably is
not measured**, and the row is annotated rather than silently kept, because a
figure whose input contained an unknown event should say so.

**Comparability caveat.** §13's 7–46 % is the fraction of *slope drift* energy
removed by a shared constant. The figure above is the fraction of *`κ`
rotation* energy removed by a shared rotation. They are analogous statistics
on different quantities and are **not the same measurement**; the comparison
is offered as an order-of-magnitude orientation, not as a like-for-like.

### 8.4 H2 — better than the slope, still under the bar

`s3` only, **N = 3**, 12 ordered pairs, **1,293 scored tests**. `A_nn` =
nearest centroid, `A_gated` = STRANGER counted in the denominator
(`IDENTITY_STABILITY.md` §1.5). Chance 33.3 %, bar 2/N = 66.7 %.

| arm | `κ` raw | **`κ` derotated** | slope | N1 shuffle |
|---|---:|---:|---:|---:|
| **A** — `κ`=[Re,Im] 2-D vs slope 2-D | 59.2 % | **65.2 %** | 42.2 % | 17.0 % |
| **B** — fair 1-D, `κ`=[arg] vs [sfo] | 62.5 % | **62.5 %** | 35.9 % | 29.9 % |
| **C** — `κ`=[\|κ\|] vs [sfo] | 61.8 % | 61.8 % | 35.9 % | 33.3 % |

**The pre-registered dimensionality check of §4.1 comes out clean.** Arm A
does not pass while arm B fails; both show the same gain. **The advantage is
attributable to `κ` and not to the extra real dimension.**

**Paired difference on the same 12 pairs** (post-hoc bootstrap, 4,000
resamples, seed 20260827 — *not* in Stage 1, labelled accordingly):

| arm | `κ` derot − slope | 95 % CI | pairs `κ` wins |
|---|---:|---|---:|
| A | **+21.8 pp** | [+3.1, +36.5] | **10 / 12** |
| B | **+27.8 pp** | [+19.9, +38.3] | **11 / 12** |
| C | **+23.7 pp** | [+4.7, +30.7] | **10 / 12** |

**All three intervals exclude zero.** On this corpus, at this receiver, `κ`
carries more cross-session identity than the SFO slope does.

**Derotation earns its place in the gate, not in the ranking.** Arm A `A_gated`
rises **4.4 % → 18.4 %** and arm B **33.4 % → 53.9 %** when the §8.3 rotation
is removed, while `A_nn` moves +6.0 pp and 0.0 pp. That is the signature of
centroid displacement being corrected rather than separation being created —
the reading `IDENTITY_STABILITY.md` §1.5 gives an elevated STRANGER rate.

**Why the H2 FAIL must not be reported as a refutation.** The bootstrap CI on
the headline is **[39.3, 79.8]** (arm A) and **[59.6, 70.1]** (arm B, the
tightest). **The 66.7 % bar sits inside both.** Twelve pairs, one receiver,
three devices cannot resolve 65.2 % from 66.7 %. The pre-registered verdict is
FAIL because the point estimate is below the bar and the rule was frozen; the
measurement does not distinguish the two, and no claim is made that it does.

### 8.5 Controls

| control | result | verdict |
|---|---|---|
| **P1** within-session `κ`, s3, N=3 | **99.0 %** `A_nn` (arm A), 88.5 % (B), 77.0 % (C) | **PASS** — reproduces `IQ_IMBALANCE.md` §13's purity 1.000 in a different statistic |
| **P1** within-session slope, s3, N=3 | 97.0 % (A), 54.0 % (B/C) | context: `κ` beats it on the fair 1-D arm within-session too |
| **N1** label shuffle, seed 20260827 | 17.0 % (A), 29.9 % (B), 33.3 % (C) vs chance 33.3 % | **PASS** — collapses to or below chance |
| **N2** receiver pooling | never pooled; §8.2 reports each receiver separately | **HELD** |

§2.3's stop condition did not fire: the positive control passes, so the
cross-session numbers are interpretable.

### 9. What this pass does not establish

- **Nothing about cross-receiver `κ`.** Not measured here, and
  `IQ_IMBALANCE.md` §15's `frac_rx = 5.73` / `R_disp = 826.6` stand unchallenged.
- **Nothing about the d0wd receiver.** §8.2 is a floor failure. The 49.0 % and
  94.8 % figures in that block are recorded in `/tmp/kxs/score.json` and are
  **not quoted as results.**
- **No cause for the rotation.** §8.3 removes part of it and explains none of
  it. `IQ_IMBALANCE.md` §18 item 1 stays open.
- **No revision of 99.7 %/7,497 or 95.7 %/14,234.** Different corpus, feature
  and standardization; per §4 these numbers are not comparable to those.
- **`κ` is not a working cross-session fingerprint.** 65.2 % on three classes
  is not identification. It is a feature that fails less badly than the one
  before it.
- **The ~77 % same-model figure is not quoted or relabelled.** `DIRECTION.md`
  is not cited as capability. Nothing is fused with `pc/occ/`.

### 9.1 Temptations recorded rather than acted on

1. **Lowering `MIN_WIN` to bring d0wd in.** Dropping it to 5 would admit
   several d0wd sessions. The floor was frozen in §3 before the corpus was
   counted and it stays. The d0wd block is reported as a floor failure.
2. **Quoting 65.2 % as "essentially at the bar".** It is 1.5 pp under a bar
   that was frozen. It is reported as FAIL with the CI attached.
3. **Reporting arm A alone.** Arm A is the friendliest number in the table.
   §4.1 required arm B and arm B is reported beside it every time.
4. **Calling the §8.3 rotation removal "reference correction for `κ`".** It
   works on two pairs of three. It is called partial.
5. **Reading the arm-B slope figure of 35.9 % as a reproduction of
   `IDENTITY_STABILITY.md`'s 29.7 %.** Different corpus, chunking,
   standardization and receiver block. The resemblance is not evidence and the
   two are not compared.

### 10. What to run next, in order

1. **Get three beacons over the floor on the d0wd**, or establish that its
   frame rejection makes that impossible. Until then every `κ` cross-session
   number this project has is single-receiver.
2. **More sessions.** Twelve pairs is the reason §8.4 cannot resolve its own
   headline. The CI narrows as √pairs.
3. **The position swap** — exchange the two receivers on the wall and re-run.
   `DUAL_RX_2026-08-21.md` §3.6 cannot separate receiver from position, and
   twelve inches is 2.4 wavelengths at 2.4 GHz. If the disagreement follows
   the board it is silicon; if it follows the wall it is geometry.

### 11. Reproduce, exactly

```
python pc\exp_kappa_cross_session.py verify
python pc\exp_kappa_cross_session.py scan data\raw\<file>.csv --tag <tag>
python pc\exp_kappa_cross_session.py floors <tags...>
python pc\exp_kappa_cross_session.py score  <tags...>
python pc\exp_kappa_cross_session.py report
```

Scan tags are the CSV stems. `MIN_WIN`, `R_cm` bars, the chunk length and the
seed are module constants, not CLI flags, so a run cannot be tuned from the
command line. The bootstrap in §8.4 is post-hoc and is the only figure in this
document not produced by `report`.
