# THERMAL_STEP — a controlled thermal step on B3, and what it does to the SFO slope and to κ

**Date:** 2026-08-23 · **Scope:** read-only re-analysis of one capture pair in
`data/raw/` · **Tool:** `pc/exp_thermal_step.py` (new, one script).

> **STAGE 1 — everything above the `STAGE 2` banner was written and saved
> before any feature value existed.** The only things run before it was
> written were: `ls`/`head`/`tail`/`awk` row, MAC, timestamp and `label`-column
> counts on the two input files (§1), and reading `CLAUDE.md`,
> `PROJECT_NOTES.md`, `pc/rff/dsp.py` in full, `pc/exp_iq_imbalance.py`
> §§constants–`run_scan`, `docs/IQ_IMBALANCE.md`, `docs/THERMAL_EVIDENCE.md`
> §§verdict–2, `docs/WEATHER_COVARIATE.md` verdict rows, `docs/B3_MOVED.md`
> §§0–0.0.1 / 9.1 / 9.6 / 9.7, and `docs/COLOCATED_0823.md` §2. **No estimator
> had been run and no κ, no slope and no σ existed.**
>
> **Stage 1 is frozen.** A Stage-1 statement that turns out to be wrong is
> corrected *below* the banner with the original left standing, not rewritten.

---

## 0. The manipulation, as reported by the operator

Beacon **B3 `f4:2d:c9:70:72:30`** spent roughly one hour outdoors on a car,
then was carried back indoors to **approximately — not exactly — its previous
position**. A capture was started immediately on return. **B1
`a4:f0:0f:77:91:20`, B2 `28:05:a5:2f:fa:48` and both receivers were not
touched.** So the early minutes of the file contain B3's crystal and RF front
end equilibrating from outdoor to indoor temperature, and the tail is settled.

**This is the first temperature manipulation this project has run.**
`docs/WEATHER_COVARIATE.md` §11 and §7.1 excluded outdoor air temperature,
pressure and humidity as explanations for the drift but stated in those words
that a null there "does **not** exclude an indoor or on-die thermal
mechanism", and named per-frame die temperature as the only remaining route.
**There is still no temperature column anywhere in this data and none is
created here.** What this capture supplies is not a sensor but a *known,
large, one-directional* temperature step whose covariate is supplied by
physics and by the operator's account. Everything below is about the **shape
of a feature over time**, never about heat.

### 0.1 What is being inferred from an operator report, named as such

Per `CLAUDE.md` failure mode **G**: the claim "B3 was outdoors for an hour and
came back warm/cold" is **not carried by any field in the CSV**. There is no
temperature column, and §1.3 below establishes that the `label` column of both
files is empty on every row, so the manipulation is not written into the data
either. The treatment assignment is **the operator's account, taken as given**.
The one thing the data can check independently is that B3 is on the air and at
what rate, which §1 does. `docs/B3_MOVED.md` §0.0 is the standing warning here:
on the previous manipulation the operator's own identification of which board
was treated turned out to be wrong, and had to be re-derived from RSSI. This
pass does not re-derive it — B3 is the only MAC that could have been off the
bench, since it is the one `docs/B3_MOVED.md` established was already the
travelling unit — but the dependence is recorded.

---

## 1. The capture, identified from timestamps not from the brief

The operator described the file as "started around 16:00 local, the one after
the 14:13 capture, the most recent `*_20260823_*` pair". Two of those three
are right and one is not, so the identification is recorded explicitly:

| | `data/raw/d0wd_20260823_151725.csv` | `data/raw/s3_20260823_151725.csv` |
|---|---|---|
| bytes | 508,094,028 | 609,580,644 |
| first `pc_time_us` | 1787516245722011 | 1787516245619672 |
| last `pc_time_us` | 1787520463045502 | 1787520463072970 |
| UTC span | 20:17:25 → 21:27:43 | 20:17:25 → 21:27:43 |
| **local span (UTC−5)** | **15:17:25 → 16:27:43** | **15:17:25 → 16:27:43** |
| duration | **4217.45 s = 70.29 min** | **4217.45 s = 70.29 min** |

**It is the most recent `20260823` pair and it is the one immediately after
the 14:13:58 capture, but it started at 15:17:25 local, not "around 16:00".**
The 70-minute duration in the brief is right to the minute. The two receivers
opened 102 ms apart and closed 27 ms apart, so they cover the same interval
and no time alignment is needed beyond `pc_time_us`, which is the *host* clock
and common to both files.

**Nothing in this pass touches the 14:13 pair, the 01:47 pair or any other
file.** The 14:13 pair is the "B3 absent" file of `docs/B3_MOVED.md` §9.6 and
is referred to only through numbers already published there.

### 1.1 B3 is on the air, and this is not a repeat of `B3_MOVED`

Raw row counts over the first 400,000 rows of each file, before any screen:

| MAC | role | s3 | d0wd |
|---|---|---:|---:|
| `f4:2d:c9:70:72:30` | **B3 (treated)** | **122,474** | **152,662** |
| `a4:f0:0f:77:91:20` | B1 (control) | 103,261 | 95,828 |
| `28:05:a5:2f:fa:48` | B2 (control) | 172,154 | 149,633 |

**B3 delivered 0 admissible frames on the d0wd and 5 on the S3 in
`docs/B3_MOVED.md`, which is why that pass could not answer its own primary
question.** Here it is the *most* numerous source on the d0wd. Whatever else
this file does or does not show, the treated unit is measurable in it, on both
receivers. That is the precondition `B3_MOVED` lacked.

### 1.2 `seq` is not a boot-age indicator, and is not used as one

The obvious way to date B3's power cycle from the data is its transmit
sequence number. **It does not work and the reason is in the firmware.**
`firmware/csi_rx/main/main.c:241-251` stores the ESP-NOW sequence number into
a single global `s_latest_seq` in the receive callback, and line 270 attaches
*that* global to whatever CSI record is being emitted, regardless of which MAC
sent it. The recorded values confirm the cross-talk: over the first 400k s3
rows B1 and B3 both open at `seq` 1,767,403 and 1,767,405 while B2 opens at
513,792. **`seq` on a row is the last sequence number the receiver saw from
anybody, not that row's transmitter's counter.** It is therefore not used
here, in any form, to date a reboot or anything else. §5 states what *is* used.

### 1.3 The reboot is not in the `label` column

`docs/IQ_IMBALANCE.md` §19 item 2 asks for exactly this experiment — "a
capture pair straddling a deliberate receiver reboot, with the reboot written
into the `label` column" — as the thing that would decide whether κ survives
across sessions. **This is not that capture.** The `label` column is empty on
all 200,000 rows sampled from the s3 file, the reboot here is a *transmitter*
power cycle rather than a receiver one, and its time is unrecorded. §5 tests
for a reboot signature blindly instead, and that is a weaker test.

### 1.4 A prior attribution the brief asserts, which this repo does not contain

The brief states that `docs/IQ_IMBALANCE.md`'s ~155° d0wd rotation "is now
attributed to boot-time RF recalibration." **It is not, anywhere in this
repo.** `IQ_IMBALANCE.md` §15.1 says in bold: *"What caused it is unknown and
was not investigated"*, and explicitly names inferring a power-cycle from it as
`CLAUDE.md` failure mode **G**. §19 item 2 offers "a boot-time sign
convention" as one of **two** hypotheses in an `if`-clause, alongside "silicon
state that wanders", and asks for a capture to decide between them. §18 lists
it as an unexplained live hazard. A `grep` across `docs/` finds no other
document that mentions it at all.

**So the rotation is an open question, not a settled attribution, and this
pass treats it as one.** It matters because the brief's framing would let a
reboot signature here be read as *confirming* a prior finding when it would
actually be the first evidence for one of two standing hypotheses. §5 is
written to be reportable either way. This is `CLAUDE.md` failure mode **H**
caught at the input rather than the output.

---

## 2. The two features, and why the comparison is the point

### 2.1 SFO slope — the shipped estimator, unmodified

`pc/rff/dsp.py`'s `FrameEstimator` (RANSAC phase-slope fit) and
`WindowAggregator` (W = 64, `min_inlier_ratio` 0.60, `max_resid` 0.80),
imported and used **as-is**. `pc/rff/dsp.py` is not modified.
`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` are
not used — `docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 record all three as having
the DC/guard-band index wrong.

`ransac_line` draws from a per-instance RNG that advances once per fitted
frame (`dsp.py:118,132`), so its output depends on how many frames preceded it
*in that stream*. **Each (file, MAC) stream is therefore replayed from the
first data row of the file with one fresh `FrameEstimator`, in file order,
with no subsampling and no seeking.** This is the constraint that forces a
full sequential replay of both files.

### 2.2 κ — `pc/exp_iq_imbalance.py`'s estimator, imported not reimplemented

κ = `A/(2P)` with `A = Σ_f Σ_k s(k)·G̃_f(k)·G̃_f(−k)`, exactly as
`docs/IQ_IMBALANCE.md` §1.6 defines it. `pc/exp_thermal_step.py` **imports**
`pc/exp_iq_imbalance.py` and calls its `Cell`, `process_batch`, `features`,
`add_cells`, `frames_to_H`, `deslope`, `field_ok`, `med_flag` and its
`S_TRUE`/`S_NULL`/`SHIFTS` constants unchanged. No estimator is rewritten. The
convention branch is `--convention raw` (`H → H·L(k)`), which is what
`IQ_IMBALANCE.md` §10.2 resolved for these files, and the `s1` variant is run
as a robustness arm.

The controls `ν`, `κ₀`, `ν₀`, the 64 random even ±1 patterns and the four
wrong-pairing shifts come along with `features()` and are reported for every
cell **without exception**, per §1.6 of that document: *if κ and ν move
together, the statistic is measuring the channel and not the silicon.* A
thermal result on κ that is matched by ν is a channel result, and this capture
— which moved a beacon and put it back only approximately — is precisely the
situation where that could happen.

### 2.3 Why κ is the one that matters

`docs/IQ_IMBALANCE.md` §14 measured κ at **0.41× (d0wd) and 0.20× (s3)** of
the between-device spread against the deterministic slope's 0.84× / 1.07× on
identical data — **2.1× and 5.4× more stable** — and proposed it as a second
identity axis. But mixer gain and phase mismatch are analog silicon, and analog
silicon drifts with temperature; §0 of that document says so in as many words
("It drifts with temperature, slowly"). **If κ moves with the crystal settling,
then its measured stability is conditional on thermal quiet, and that needs
saying before anyone builds an identity axis on it.** If κ holds flat while
the slope drifts, that is a strong result for κ and the first evidence that
its stability is not merely an artifact of a thermally uneventful session.

### 2.4 The interleave convention, checked not assumed

`pc/rff/dsp.py:43-52` is `iq = v[:128]; return iq[1::2] + 1j*iq[0::2]` — the
buffer is **imag,real** interleaved and the complex value is
`iq[1::2] + 1j*iq[0::2]`. Read from the file this session, quoted above.
Getting it backwards conjugates every subcarrier and inverts exactly the
conjugate relation κ is built on. Both features here reach the buffer through
`dsp.csi_to_complex`'s convention: the slope arm through `dsp` itself, the κ
arm through `exp_iq_imbalance.frames_to_H`, which is that convention verbatim.
`pc/exp_thermal_step.py` asserts at import that both agree, on real frames.

---

## 3. THE PREDICTION IS A SHAPE, NOT A DIRECTION

A crystal and a die equilibrating from an outdoor to an indoor temperature
follow a first-order thermal settle with a time constant of **minutes** for a
small unenclosed board. So the treated beacon's feature should show
**monotonic drift that decays and flattens**.

**Direction is not predicted and must not be scored.** AT-cut crystals are
cubic-with-a-turnover in temperature; the turnover point for these boards is
recorded nowhere in this repo, `docs/HARDWARE_BUY_NOTES.md` and
`docs/NODE_CENSUS.md` say nothing about crystal cut or specification, and the
sign of df/dT therefore depends on which side of turnover the board sits and
on which direction the step went. A *direction* prediction here would be
unfalsifiable dressing. This is the one place where this document deliberately
departs from `docs/THERMAL_EVIDENCE.md` §1, whose STRONG form made shared
direction load-bearing — and it does so because that document was pooling
*many* captures where a shared sign was meaningful, whereas this is **n = 1
treated unit in n = 1 trial** and there is no population to share a sign with.

### 3.1 The model comparison, frozen

Per (receiver × beacon × feature), the feature is binned into **60 s bins over
the 4217.45 s span (70 bins)**, giving a series `y_i` at bin centres `t_i`.
Three nested models are fit by least squares:

| model | form | free params |
|---|---|---|
| **M0 — the no-trend null** | `y = a` | 1 |
| **M1 — linear** | `y = a + c·t` | 2 |
| **M2 — decaying settle** | `y = a + b·exp(−t/τ)` | 3 (τ on a grid, 0.5–35 min) |

Scored by **ΔBIC** against M0 and against M1, plus:

- **`R_shape`** — the fraction of M0's residual variance explained by M2.
- **A block permutation test.** The bins are shuffled in contiguous blocks of
  5 (to preserve short-range autocorrelation, which is what makes a naive
  F-test lie here) and M2 refit, 2,000 times. `p_perm` = the fraction of
  shuffles reaching the observed ΔBIC. **This, not the BIC, is the test**,
  because the bins are not independent and every feature in this project is
  known to autocorrelate.
- **`ρ_decay`** — Spearman ρ between bin index and `|y_{i+1} − y_i|`. A
  settle's *increments shrink*; a random walk's do not. Negative and
  significant is the shape signature that a monotone trend alone cannot fake.

### 3.2 The pre-registered decision table

| verdict | condition |
|---|---|
| **SETTLE** | M2 beats both M0 and M1 by ΔBIC ≥ 10, `p_perm` ≤ 0.01, fitted **τ ∈ [1, 30] min**, and `ρ_decay < 0` |
| **DRIFT, NOT SETTLE** | M1 beats M0 by ΔBIC ≥ 10 but M2 does not beat M1 by ≥ 10, or τ falls outside [1, 30] min |
| **NO STRUCTURE** | M2 does not beat M0 by ΔBIC ≥ 10, or `p_perm` > 0.01 |

A τ pinned at a grid edge is reported as **at the edge** and read as "the
window is the wrong length to see this", never as a fitted time constant.

### 3.3 What would falsify the thermal reading — stated now

1. **The controls do it too.** If B1 and B2 — indoors, untouched, at room
   temperature for the whole hour — return **SETTLE** on the same feature and
   receiver as B3, **the effect is not thermal.** It is then a property of the
   start of a capture, and this document reports *that* instead, as its
   primary finding, with the thermal reading withdrawn. §4 is written to make
   that outcome as visible as the positive one.
2. **The magnitude is inside ordinary wander.** §3.4.
3. **κ and ν move together.** §2.2 — then the κ arm is measuring the channel,
   which the approximate repositioning makes a live possibility, and the κ
   result is withdrawn.
4. **The step is a step.** If B3's series is a one-bin discontinuity with flat
   behaviour on both sides, that is a reboot, not a settle (§5).
5. **τ outside [1, 30] min.** A 90-second board equilibrating over 3 hours, or
   over 20 seconds, is not the mechanism claimed.
6. **The effect is present only under one convention branch** (`raw` vs `s1`)
   or only at one bin width. Both are run.

### 3.4 The bar. `docs/B3_MOVED.md` §9.1, adopted unchanged

`docs/B3_MOVED.md` §9.1 measured, on the *previous* night's 6.70 h file, the
range of block-median SFO across non-overlapping 3111 s blocks for beacons
that were **bolted to a wall and never touched**:

| rx | beacon | range (rad/sc) | **× BETWEEN_UNIT_SD (0.00237)** |
|---|---|---:|---:|
| d0wd | B1 | 0.005972 | **2.52** |
| d0wd | B3 | 0.006545 | **2.76** |
| s3 | B1 | 0.006450 | **2.72** |
| s3 | **B3** | **0.011641** | **4.91** |
| s3 | B2 | 0.000994 | 0.42 |
| d0wd | B2 | 0.042635 | 17.99 — degenerate, dead link, carries no weight |

**A stationary beacon wanders 2.5–4.9 σ across one night on four of the six
pairs. That is the bar.** An SFO excursion on B3 smaller than **4.91 σ on the
s3** and **2.76 σ on the d0wd** — B3's own bands — is **not distinguishable
from ordinary wander and will be reported as not distinguishable**, however
good its ΔBIC is. A shape can be statistically real and physically
uninformative at the same time, and that is the likely outcome here.

**Two honesties about the bar.** It is a *between-block range over 6.7 h*, and
this capture is 70 min — so comparing a 70-minute excursion to it is
conservative in one direction (less time to wander) and generous in the other
(the bar was measured on blocks 3111 s long, not 60 s bins, so it is smoothed
where these bins are not). Both the range-of-block-medians statistic in B3's
own units **and** the 60 s-bin version are computed on this file's controls, so
this file supplies its own contemporaneous null as well as importing B3_MOVED's.

**κ has no such published bar.** `docs/IQ_IMBALANCE.md` §14's stability
numbers are *ratios* to a between-device spread, not a wander band in κ's own
units. So the κ arm's bar is built here, from **this file's own untouched
controls**: B3's κ excursion is compared to the larger of B1's and B2's over
the same 70 minutes and the same bins. That is a weaker bar than an
independent one and is labelled as such wherever it is used.

### 3.5 The head-to-head, in the only units that make it fair

"Did κ or the slope move more" is meaningless in raw units — one is rad/sc and
one is dimensionless. Both are normalised **by their own between-device
spread on this file** (the sd of the three beacons' whole-file means, per
receiver), which is the construction `docs/IQ_IMBALANCE.md` §14 used and the
only one under which the two are comparable. Reported as
`excursion / S_bd` for each feature, and as the **ratio of those ratios**.

**Pre-registered expectation, and it cuts against κ:** if the mechanism is
thermal and κ is analog mixer mismatch, κ *should* move. `IQ_IMBALANCE.md` §0
proposed κ precisely because it "drifts with temperature, slowly". A κ that
holds flat through a large thermal step is therefore the *surprising* outcome
and the strong one; a κ that moves is the expected one and is a real
qualification on §14.

---

## 4. THE CONTROLS ARE THE WHOLE DESIGN

B1 and B2 stayed indoors, at room temperature, untouched, for the whole 70
minutes. They are run through **every** step of §3 identically and reported in
the same table as B3, never in an appendix. Three outcomes and what each means,
decided now:

| B3 | B1 & B2 | reading |
|---|---|---|
| SETTLE | NO STRUCTURE | consistent with a thermal settle on the treated unit |
| SETTLE | SETTLE | **not thermal.** A start-of-capture artifact. Reported as the primary finding, thermal reading withdrawn |
| NO STRUCTURE | NO STRUCTURE | the step is not resolvable in this feature at this bin width; reported as a bounded null with the bound printed |
| NO STRUCTURE | SETTLE | incoherent; the estimator or the binning is at fault and nothing is reportable until it is found |

### 4.1 Against `docs/THERMAL_EVIDENCE.md` — reproduce or contradict

`docs/THERMAL_EVIDENCE.md` (2026-08-15) already ran a warm-up analysis and
**found no power-on transient**: across 25 trials from 17 captures and 3 units
the first-10-minute drift had median magnitude **0.00061 rad/sc — 0.26× the
between-unit spread** — with no consistent direction (15/25 positive, exact
binomial **p = 0.42**), and head-trimming the warm-up region made the wander
figure **worse by +1% to +20%**. Its §3.1 control is the load-bearing part:
captures that begin seconds after the previous one ended, where the
transmitter was provably still on and still warm, show opening excursions of
the *same* order as captures following hours of silence.

**These two documents are asking different questions and the difference must
not be blurred.** `THERMAL_EVIDENCE` asked whether an *ordinary capture start*
carries a warm-up transient, on captures where **no temperature manipulation
was applied at all** and where §3.1 shows the transmitter was often already
warm. This document asks whether a **deliberate, large, known temperature
step** produces one. A null there does not predict a null here, and a positive
here does not overturn it.

Where they *do* meet is the control arm, and it is a real reproduction test:

- **B1 and B2 here are `THERMAL_EVIDENCE`'s question exactly** — untouched
  units at an ordinary capture start. **If they show opening structure, this
  contradicts `THERMAL_EVIDENCE` §3 and the contradiction is the headline.**
  If they are flat, it reproduces it on a fourth file and a finer bin width.
- **B3's excursion is compared to that document's 0.00061 rad/sc median**
  as well as to §3.4's bar, so the two are on one scale.

Pre-registered: **B1 and B2 will show NO STRUCTURE**, reproducing
`THERMAL_EVIDENCE` §3. Stated as a number so it can be scored.

### 4.2 The channel-reversal control, which is a control on the controls

`docs/B3_MOVED.md` §9.6 recorded that taking B3 off air **changed the channel
the other two beacons sit in**: B2's RSSI rose from −79 to −73 (d0wd) and −75
to −71 (s3), its raw frame rate from 42.06 to 62.02 fps (d0wd) and 65.27 to
76.30 (s3), and its d0wd acceptance from 0.202 to 0.943 — with the caveat, in
that document, that the 0.202 is itself an artifact of B2's d0wd link dying
mid-capture and "carries no weight".

**B3 is back on air in this file, so that should reverse.** Pre-registered:
B2's RSSI returns toward −79 (d0wd) / −75 (s3) and its raw fps toward
42 / 65, i.e. **within a few dB and a few fps of the "B3 present" column**,
not the "B3 absent" one. **If it does not reverse, the bench changed in some
way nobody recorded**, and every control in §4 is weakened — that would be
reported before any thermal result, not after it. The frame-rate half of this
follows from CSMA; `B3_MOVED` §9.6 explicitly declines to explain the RSSI
half and this pass does not either.

---

## 5. The reboot, and why it must not be conflated with the settle

B3 was power-cycled recently — the operator unplugged and replugged everything
while mapping node positions. A power cycle and a thermal settle are **both**
"something changes near the start of the file", and they are separable only by
shape:

| | reboot | thermal settle |
|---|---|---|
| shape | **step** — a discontinuity, flat on both sides | **exponential decay** — smooth, monotone, decaying increments |
| onset | at the boot instant, which may precede the file | at the moment the board changes environment |
| features affected | any feature carrying an RF-calibration state; a π rotation of κ is a sign flip of β/α | anything temperature-dependent |

**The discriminator, frozen.** Alongside M0/M1/M2 of §3.1, a fourth model is
fit to every series:

> **M3 — step at unknown time:** `y = a + d·1[t > t_s]`, `t_s` scanned over
> every bin boundary, 2 free params + 1 scanned.

and **M2 vs M3 is scored by ΔBIC and by the same block-permutation test**.
Additionally, κ's *argument* is tracked separately from its magnitude, because
`docs/IQ_IMBALANCE.md` §15.1's unexplained ~155° event was a rotation, and a
half-turn in `arg κ` is a sign flip of β/α — a categorically different object
from a smooth drift in |κ|. Reported for every cell:

- `arg κ` per bin, unwrapped, and the largest single-bin jump in it;
- whether that jump is confined to ≤ 1 bin (step-like) or spread over ≥ 3
  (settle-like);
- whether it appears on **B3 only** (transmitter-side, consistent with B3's
  power cycle) or on **all three beacons at one receiver** (receiver-side,
  the §15.1 signature, and *not* attributable to B3's reboot).

**Three outcomes, decided now:**

| finding | reading |
|---|---|
| M3 ≫ M2 on B3, with `t_s` in the first bins | a reboot discontinuity. **The thermal claim is not made.** |
| M2 ≫ M3 on B3 | a settle, separable from a reboot |
| M2 ≈ M3, ΔBIC < 10 either way | **not separable in this capture.** Reported as such. **This is the honest expected outcome** for a reboot that happened at an unknown time possibly before the file opened, and it will not be dressed up |

**The one thing this capture genuinely cannot do:** B3's boot instant is not
recorded anywhere (§1.2, §1.3). If B3 was powered up before the capture
started, the reboot transient may be entirely outside the file, in which case
M3 finds nothing and its absence is **not** evidence that a settle is what is
being seen. That asymmetry is stated here rather than discovered in §12.

---

## 6. Corrupt-row screening, and the fabricated near-misses

Both screens `docs/COLOCATED_0823.md` §1 requires, applied **before any MAC
enters a census and before any delta arithmetic**:

1. **Field plausibility** on six columns: `node_id` vs the file's own mode,
   `env_id == 0`, `channel` vs the file's own mode, `len ∈ {128,256,384}`,
   `noise_floor ∈ [−110,−70]`, `rssi ∈ [−100,−10]`.
2. **Width-9 median filter on `dropped`**, compared circularly mod 65536.
   Both are required: `COLOCATED_0823.md` §2 records three d0wd rows invisible
   to the field screen and caught only by the median filter.

`csi_data` is a quoted comma-separated list nested inside the CSV, so it is
read with `csv.reader`, never `line.split(',')`.

### 6.1 The near-miss census the standard screen under-counts

`docs/COLOCATED_0823.md` §2 flagged that the screen **under-counts**
corruption: at least three "clean but sparse" d0wd addresses are single-frame
byte-neighbours of beacon MACs — `fa:1e:c9:70:72:30` and `e4:21:e3:20:72:30`
against B3, `d9:f4:a5:2f:fa:48` against B2 — and are more likely undetected
corruption than real transmitters. The operator separately watched the d0wd
fabricate `f4:2d:c9:70:0d:1b` and `f4:2d:c9:70:00:00` live, both corrupted
variants of B3's own address.

Two screens are run over the **whole** MAC census of both files, and their
counts reported:

- **`0d:0a` screen** — any address containing the octet pair `0d:0a`
  adjacent, or any address containing an octet equal to `0d` or `0a` (the
  CR/LF bytes a line-oriented corruption injects). Both counts given
  separately, since the second is much looser and will catch innocents.
- **Byte-neighbour screen** — Hamming distance **in octets** from each of the
  three beacon MACs, reported at **d ≤ 1**, **d ≤ 2** and **d ≤ 3**, with the
  differing positions listed. Both of the operator's live sightings are d = 2
  at positions 4–5; `fa:1e:c9:70:72:30` is d = 2 at positions 0–1;
  `e4:21:e3:20:72:30` is d = 4. So **d ≤ 3 is the reportable screen and d = 4
  is shown too**, since a real fabrication already exceeded 3.

**These addresses are counted and reported. None of them enters any feature
computation** — only the three beacon MACs do — so this section cannot change
a κ or a slope. It exists to quantify how badly the standard screen
under-counts, which is what `COLOCATED_0823.md` §2 asked for.

**No mechanism other than corruption is claimed for any of them.** A
fabricated address is indistinguishable from a real one-frame transmitter on
one frame, and the census says only that these are byte-neighbours of
addresses known to be present in volume.

---

## 7. CRITICAL CAVEATS, stated before the numbers

1. **B3 was returned to approximately, not exactly, its previous position.**
   Multipath decorrelates over roughly **6 cm at 2.4 GHz** (a quarter
   wavelength; λ ≈ 12.5 cm at 2.437 GHz). A hand-placed board is not
   repositioned to 6 cm. **The tail of this file is therefore a *near*
   reproduction of the 08:29 baseline, not a reproduction**, and any
   comparison to that baseline carries a channel change of unknown size that
   is confounded with everything else. This is why the primary analysis is
   **entirely within this one file** — early bins against late bins of the
   same capture, same position, same channel — and why the cross-file
   comparison to the 08:29 pair appears only as a labelled secondary.
2. **No temperature was measured.** Not outdoor, not indoor, not on-die. The
   temperature step is an inference from the operator's account of an hour
   outdoors. Its magnitude, and even its sign, are unknown to this pass.
3. **The crystal turnover point is recorded nowhere**, so the direction of
   df/dT is unknown and direction is deliberately not scored (§3).
4. **n = 1.** One treated unit, one trial, one capture. No replication exists
   and none is claimed. A single exponential fit to a single 70-minute series
   is a weak instrument, which is why §3.1's permutation test and §3.4's
   wander bar both have to be cleared before anything is called an effect.
5. **B3's power cycle is a confound, not a nuisance** (§5), and it may be
   unresolvable here.
6. **B3's own removal changed the channel the controls sit in** (§4.2), so
   "untouched" means "not physically moved", not "measured under identical
   conditions".
7. **κ is receiver-dominated.** `docs/IQ_IMBALANCE.md` §15 measured
   `frac_rx = 5.73` — a lower bound — and concluded the model "does not
   decompose cleanly". **A large part of κ is receiver silicon, and the
   receivers were not treated.** So a *null* on κ has a boring explanation
   available — the transmitter's share of κ may simply be too small to see the
   step — and a null will be reported with that alternative stated, not as
   evidence of thermal robustness. This is the single most important caveat on
   the κ arm and it is written before the arm is run.
8. **`|κ|` is diluted by additive noise** (`IQ_IMBALANCE.md` §18), so a change
   in link strength changes `|κ|` without any silicon changing. B3's RSSI is
   tracked per bin alongside its κ for exactly this reason, and any `|κ|`
   excursion that tracks RSSI is reported as a link-strength artifact.
9. **This is `pc/rff/` phase-domain work only.** No `pc/occ/` number is read,
   produced or combined with anything here. No device-ID accuracy figure is
   derived or revised. `docs/DIRECTION.md` is not cited as capability. The
   ~77% same-model figure is not quoted and not relabelled.

---

## 8. Constraints held

Read-only on `data/raw/`; every input opened `"rb"`. No serial port is opened.
`pc/rff/dsp.py` is **not** modified; `FrameEstimator` is used as-is.
`pc/capture.py:compute_cfo`, `pc/phase_skew.py`, `pc/fingerprint.py` are not
used. Each stream is replayed from the start of its file with a fresh
estimator. The CSI buffer convention is `iq[1::2] + 1j*iq[0::2]`, verified
against `dsp.py:43-52` this session. Corrupt rows are screened before any
delta arithmetic. No sub-agents. Nothing is staged, committed or pushed. One
script is written: `pc/exp_thermal_step.py`. Scratch goes to `$TSTEP_CACHE`
outside the repo tree and is removed at the end; `PYTHONDONTWRITEBYTECODE=1`
is set so that importing `exp_iq_imbalance` leaves no `.pyc` behind (the
artifact `docs/IQ_IMBALANCE.md` §18 could not remove). The host caps shell
calls near 178 s, so the scan checkpoints and resumes.

## 9. Reproduce

```bash
export TSTEP_CACHE=/tmp/tstep PYTHONDONTWRITEBYTECODE=1
# scan each file; repeat until DONE (checkpoints under the host's time cap)
python3 pc/exp_thermal_step.py scan --tag s3   --path data/raw/s3_20260823_151725.csv   --resume --seconds 150
python3 pc/exp_thermal_step.py scan --tag d0wd --path data/raw/d0wd_20260823_151725.csv --resume --seconds 150
# fit, controls, wander bar, reboot discriminator, census
python3 pc/exp_thermal_step.py report
```

---
---

# STAGE 2 — RESULTS

*(Everything below this banner was written after the analysis ran. Nothing
above it has been edited.)*

## 10. Verdict

**No settle was detected on the treated beacon, in either feature, on either
receiver, at any of the three bin widths tried. B3 returns NO STRUCTURE on all
six of its primary cells. The two untouched beacons did *not* stay uniformly
flat — and that is the finding, because every SETTLE verdict this pass
produced landed on a beacon that was never touched, and none landed on the one
that spent an hour outdoors.**

**The magnitude result is the one that should be quoted.** B3's SFO excursion
between its first 5 minutes and its last 20 is **2.31 σ on the s3 and 0.43 σ
on the d0wd**, against its own stationary-wander bars of **4.91 σ and 2.76 σ**
from `docs/B3_MOVED.md` §9.1. **It clears neither.** On this file's own
contemporaneous version of that statistic — the range of block medians over
six 703 s blocks — the treated unit sits at **1.91 σ (s3) / 0.91 σ (d0wd)**
while **untouched** B2 on the d0wd reaches **3.33 σ** and **untouched** B1 on
the d0wd reaches **2.58 σ**. **The beacon that was carried outdoors for an
hour moved less than two of the four untouched (receiver, beacon) cells
measured in the same minutes.**

So: whatever an hour outdoors did to B3's crystal, it is **not distinguishable
from ordinary wander in this capture**, and §3.4 committed in advance to
reporting exactly that rather than reporting a shape.

**κ vs the slope.** κ moved *less* than the slope on the s3 (0.30× in
own-spread units) and *more* on the d0wd (5.45×) — but the d0wd ratio is not
trustworthy and §11.4 says why. The statement that survives on both receivers
is the absolute one: **`|κ|`'s excursion is 3–40× smaller than its own channel
control `|ν|`'s in every one of the six cells**, and on the treated unit's
strongest cell (s3/B3) `|κ|` moved by **0.00027 against a level of 0.01719 —
1.6% — across the whole 70 minutes.** κ was, by every measure here, quiet.

**But κ being quiet does not clear it, and this is the plain verdict the brief
asked for: κ's stability was NOT shown to be thermally conditional, and it was
NOT shown to be thermally robust either.** The slope did not move above its
wander floor in this capture, so there is no detected thermal effect for κ to
have either tracked or resisted. A feature that holds still in a session where
nothing else moved has not been tested. §11.7 gives the second, independent
reason this capture could not have answered it even in principle:
`docs/IQ_IMBALANCE.md` §15 measured κ as **receiver-dominated** (`frac_rx`
5.73, a lower bound), and **the receivers were never treated.**

**Reboot vs settle: not separable, on 12 of 18 cells, and the reason is a
missing record rather than a close call.** B3's boot instant is not in the
data — §1.2 shows `seq` is receiver-global and cannot date it, §1.3 shows the
`label` column is empty on every row — so a reboot transient that finished
before the capture opened would leave nothing to find, and its absence is not
evidence of a settle. **§5 pre-registered this as the honest expected outcome
and it is what happened.**

**One pre-registered prediction failed outright and is reported before
anything else that depends on it: the channel-reversal control (§4.2) did not
reverse.** §11.3.

---

## 11. The results, with the numbers

Command log in §9 above; every figure below is from
`$TSTEP_CACHE/report_strue.txt`, produced by `pc/exp_thermal_step.py report`.

### 11.0 Two Stage-1 statements were wrong. Corrected here, left standing above

1. **§2.2 states the convention branch backwards.** It says the analysis runs
   `--convention raw (H → H·L(k))`, "which is what `IQ_IMBALANCE.md` §10.2
   resolved". §10.2 resolved the **opposite**: `ROUGH(V₀)` is 19× and 38×
   smaller than `ROUGH(V₁)`, so the ESP32 LLTF buffer is **already a channel
   estimate divided by `L(k)`** and must **not** be multiplied by it.
   `exp_iq_imbalance.py:498` spells that branch `"divided"` and multiplies by
   `_L` only when `variant_div` is **False**. **The script ran the correct
   branch** — `--convention divided`, which is also `exp_iq_imbalance`'s own
   default — so no number is affected. Only the Stage-1 prose was wrong.
2. **§1 predicted the capture would be the file the operator described as
   starting "around 16:00".** It starts at **15:17:25** local. §1 recorded the
   discrepancy at freeze time rather than adopting the brief's time, which is
   why this is a correction to the brief and not to this document.

### 11.1 Scan provenance

| tag | rows | EOF | corrupt | field | median-only | bad-parse | span |
|---|---:|---|---:|---:|---:|---:|---:|
| s3 | 742,016 | yes | **0** | 0 | 0 | 0 | 4217.5 s |
| d0wd | 593,682 | yes | **22** | 22 | 0 | 0 | 4217.3 s |

Both files ran to EOF with byte position equal to file size. **The
median-filter screen caught nothing the field screen did not** on this pair —
all 21 median flags are also field flags. That is *not* a reproduction of
`docs/RECEIVER_TERM_PREREG.md` §10.1's "3 caught by the median filter only",
and it is not meant to be: that number is a pre-registered check on the
**`014740`** pair and this is a different file. The screen is run in full
regardless, because dropping it would be assuming this file resembles that one.

**Equivalence check on the shipped SFO estimator — run, and it comes out
mixed, which is reported rather than smoothed.** Whole-file median slope per
cell here, against `docs/B3_MOVED.md` §9.1's overnight block-median range for
the same (receiver, beacon) pair on the `014740` file 13.5 h earlier:

| rx | unit | windows | **here** | B3_MOVED §9.1 range | inside? |
|---|---|---:|---:|---|---|
| s3 | B3 | 3,225 | 0.01760 | 0.01957–0.03121 | no, 10% below |
| s3 | B1 | 3,040 | 0.00831 | 0.01010–0.01655 | no, 18% below |
| s3 | B2 | 5,000 | 0.01592 | 0.00511–0.00611 | **no, 2.6× above** |
| d0wd | B3 | 3,478 | 0.00767 | 0.00896–0.01551 | no, 14% below |
| d0wd | B1 | 1,997 | 0.01650 | 0.01310–0.01907 | **yes** |
| d0wd | B2 | 3,161 | 0.02877 | (degenerate, dead link) | n/a |

**One of five lands inside.** Two are within 10–18% of the bottom of their
published range — the same order and nearly the same value — and s3/B2 is
2.6× above its overnight range, which was `B3_MOVED.md` §9.1's single
*tightest* cell at 0.42 σ.

**This is not read as an estimator problem, and it is not read as a result
either.** The pipeline chain is the shipped one (`dsp.FrameEstimator` →
`WindowAggregator`, imported unmodified), the values are all in the right
decade, and the direction of the misses is not shared. What it does is
**quantify, on a sixth file, exactly the cross-session wander that
`docs/IDENTITY_STABILITY.md` §13 and `docs/B3_MOVED.md` §9.1 already
established** — and it is a standing reminder that the between-session drift
of this feature is larger than anything this document measures within a
session. It is recorded here so that no reader mistakes §11.5's within-file
figures for cross-file stability. **`CLAUDE.md` failure mode A: this was
checked because it was checkable, and it did not come out the way the check
was expected to.**

### 11.2 The near-miss census — and the standard screen did *not* under-count here

| | s3 | d0wd |
|---|---:|---:|
| distinct MACs, every row | 21 | 37 |
| clean rows & ≥ 20 frames | 13 | 12 |
| seen **only** on corrupt rows | **0** | **15** |
| `0d:0a` **adjacent-pair** screen | **0** | **0** |
| any octet equal to `0d` or `0a` | 3 | 4 |
| **byte-neighbours of a beacon MAC, d ≤ 3** | **0** | **7** |

All seven d0wd near-misses are at **Hamming distance 2 in octets, and all
seven differ in positions 4–5** — the last two bytes, exactly the corruption
signature the operator watched live:

| fabricated address | ~beacon | raw | **clean** | corrupt |
|---|---|---:|---:|---:|
| **`f4:2d:c9:70:0d:1b`** | B3 | 1 | **0** | 1 |
| **`f4:2d:c9:70:00:00`** | B3 | 1 | **0** | 1 |
| `f4:2d:c9:70:14:cc` | B3 | 1 | **0** | 1 |
| `f4:2d:c9:70:19:de` | B3 | 1 | **0** | 1 |
| `f4:2d:c9:70:e9:31` | B3 | 1 | **0** | 1 |
| `a4:f0:0f:77:e2:02` | B1 | 2 | **0** | 2 |
| `28:05:a5:2f:ee:29` | B2 | 1 | **0** | 1 |

> **The two addresses the operator reported watching the d0wd fabricate live —
> `f4:2d:c9:70:0d:1b` and `f4:2d:c9:70:00:00` — are both present, both once,
> and both on corrupt rows.** The operator's report is confirmed to the
> address.

**And the answer to `COLOCATED_0823.md` §2's concern is: on this file the
screen does not under-count.** Every one of the seven has `clean = 0`, i.e.
the corrupt-row screen caught all of them; none survived to contaminate a
census the way `fa:1e:c9:70:72:30`, `e4:21:e3:20:72:30` and
`d9:f4:a5:2f:fa:48` did on the `014740` file. **So §2's under-count is a
property of that file, not a general property of the screen** — which is a
narrower and better-supported statement than the one the brief assumed, and it
is the opposite of what this pass expected to find.

Five of the seven are B3 variants against two for B1 and B2 combined; B3 is
also the d0wd's most numerous source (226,432 raw rows), so the fabrication
count tracks traffic share and nothing more is claimed from it. **None of
these addresses entered any feature computation.**

### 11.3 THE CHANNEL-REVERSAL CONTROL FAILED — reported first, as §4.2 required

B3 is on air throughout this file at 52.75 fps (s3) / 53.69 fps (d0wd). §4.2
predicted B2 would therefore return to `docs/B3_MOVED.md` §9.6's **"B3
present"** column. It did not:

| rx | B2 measured here | B3_MOVED "B3 present" | B3_MOVED "B3 absent" |
|---|---|---|---|
| s3 | **−70.9 dBm, 76.16 fps** | −75, 65.27 | **−71, 76.30** |
| d0wd | **−74.4 dBm, 53.30 fps** | −79, 42.06 | −73, 62.02 |

**On the s3, B2 reproduces the "B3 ABSENT" column almost exactly — −70.9
against −71 dBm and 76.16 against 76.30 fps — while B3 is present and
transmitting at 52.75 fps.** On the d0wd it sits nearer "absent" on RSSI and
between the two on frame rate.

Two consequences, both stated before any thermal reading is taken from this
file:

1. **`B3_MOVED.md` §9.6's CSMA-contention hypothesis is not supported here.**
   That document offered — explicitly "as a hypothesis generated by three
   confounded files, not as a finding" — that B3's traffic was contending for
   airtime and desensitising the receivers. In this file B3 is transmitting and
   B2 is at its uncontended values anyway. That hypothesis should not be
   promoted, and this is a fourth file saying so. It is **not** thereby refuted:
   B3 is at 52.75 fps here against "~61 fps" there, so the contention load is
   not matched and this is not a clean test either.
2. **Something about the bench differs from both of the files §9.6 compared,
   and nothing recorded says what.** Per §4.2 this weakens every control in
   §4. The controls are still *contemporaneous* — B1, B2 and B3 are measured
   in the same minutes on the same receivers, which is what the within-file
   design needs — but "the bench is in the same state it was in on 23 August
   at 14:13" is now known to be false, and no cross-file comparison in this
   document leans on it.

### 11.4 THE SHAPE TEST — 60 s bins, primary arm

ΔBIC20 = BIC(M0) − BIC(M2); positive favours the settle. Verdicts by §3.2,
applied unchanged.

| rx | unit | feature | bins | ΔBIC20 | ΔBIC21 | τ min | ρ_decay | p_perm | R²shape | **verdict** |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| s3 | **B3** | sfo | 71 | −1.0 | 2.3 | 1.23 | −0.21 | 1.000 | 0.101 | **NO STRUCTURE** |
| s3 | **B3** | \|κ\| | 70 | −8.3 | −5.1 | 1.03 | +0.03 | 1.000 | 0.003 | **NO STRUCTURE** |
| s3 | **B3** | arg κ | 70 | 11.8 | 15.9 | 1.94 | −0.17 | **0.0285** | 0.251 | **NO STRUCTURE** |
| s3 | B1 | sfo | 71 | −5.2 | −4.6 | 35.0\* | −0.17 | 1.000 | 0.046 | NO STRUCTURE |
| s3 | B1 | \|κ\| | 70 | −3.7 | −4.1 | 35.0\* | +0.07 | 1.000 | 0.067 | NO STRUCTURE |
| s3 | B1 | arg κ | 70 | −7.7 | −4.3 | 35.0\* | −0.05 | 1.000 | 0.011 | NO STRUCTURE |
| s3 | B2 | sfo | 71 | 0.4 | 3.4 | 1.23 | −0.11 | 1.000 | 0.118 | NO STRUCTURE |
| s3 | B2 | \|κ\| | 70 | −6.0 | −2.7 | 8.24 | +0.08 | 1.000 | 0.035 | NO STRUCTURE |
| s3 | **B2** | **arg κ** | 70 | **69.8** | **39.8** | 10.81 | +0.16 | **0.0015** | **0.673** | **DRIFT, NOT SETTLE** |
| d0wd | **B3** | sfo | 71 | −1.9 | 2.2 | 8.24 | +0.14 | 1.000 | 0.089 | **NO STRUCTURE** |
| d0wd | **B3** | \|κ\| | 70 | −7.9 | −4.0 | 0.50\* | +0.11 | 1.000 | 0.008 | **NO STRUCTURE** |
| d0wd | **B3** | arg κ | 70 | −6.8 | −3.8 | 12.95 | −0.07 | 1.000 | 0.025 | **NO STRUCTURE** |
| d0wd | B1 | sfo | 71 | −6.4 | −2.8 | 0.79 | −0.06 | 1.000 | 0.029 | NO STRUCTURE |
| d0wd | B1 | \|κ\| | 35 | −5.4 | −3.6 | 35.0\* | +0.01 | 1.000 | 0.046 | NO STRUCTURE |
| d0wd | B1 | arg κ | 35 | −5.9 | −2.8 | 5.74 | +0.35 | 1.000 | 0.034 | NO STRUCTURE |
| d0wd | B2 | sfo | 71 | −5.4 | −1.3 | 5.74 | −0.14 | 1.000 | 0.043 | NO STRUCTURE |
| d0wd | B2 | \|κ\| | 70 | −6.5 | −4.5 | 1.48 | −0.35 | 1.000 | 0.028 | NO STRUCTURE |
| d0wd | B2 | arg κ | 70 | −8.0 | −3.7 | 4.79 | −0.09 | 1.000 | 0.007 | NO STRUCTURE |

\* τ pinned at a grid edge — read as "the window is the wrong length", never
as a fitted time constant (§3.2).

**B3 is NO STRUCTURE on all six cells.** Its best cell, s3/arg κ, reaches
ΔBIC20 = 11.8 and clears the ΔBIC gate, then **fails the block-permutation
test at p = 0.0285 against the pre-registered p ≤ 0.01.** That is the
permutation test doing exactly the job §3.1 said it was there for: ΔBIC on
autocorrelated bins overstates, and the pre-registration set the gate before
the number existed.

**The two cells with real structure belong to untouched beacons.** s3/B2's
arg κ carries R² = 0.673 at p = 0.0015 — but M2 also beats M1 by 39.8, and its
`ρ_decay` is **+0.16**, i.e. its increments *grow*. A settle's increments
shrink; §3.2 makes `ρ_decay < 0` a requirement, so it is scored **DRIFT, NOT
SETTLE** and not as a settle with an inconvenient sign.

**d0wd/B1's `|κ|` and `arg κ` rows carry 35 bins rather than 70** because B1
delivers 140,271 admissible frames over 70 bins ≈ 2,004 per bin, straddling the
2,000-frame floor of `IQ_IMBALANCE.md` §1.11. Half its bins were dropped by the
floor. That cell is the weakest in the table and no weight is put on it.

#### Bin-width robustness (§3.3 falsifier 6)

Re-run at 30 s and 120 s. **B3 is NO STRUCTURE in all six cells at all three
widths.** The only movement in the matrix is among the controls:

| cell | 30 s | 60 s | 120 s |
|---|---|---|---|
| **s3 / B3 / all three features** | NO STRUCTURE | NO STRUCTURE | NO STRUCTURE |
| **d0wd / B3 / all three features** | NO STRUCTURE | NO STRUCTURE | NO STRUCTURE |
| s3 / B2 / arg κ | — | DRIFT | **SETTLE** (τ 10.8 min, R² 0.735, p 0.008) |
| d0wd / B1 / arg κ | — | NO STRUCTURE | **DRIFT** (ΔBIC 81.6, p 0.001) |

> **The single SETTLE verdict at 60/120 s bins in this entire pass belongs to
> B2 — a beacon that sat indoors on the bench and was never touched.**

**This is a useful positive control on the machinery.** §3.3 falsifier 1 was
written for the case where the controls reproduce the treated unit's shape;
what happened is stronger and simpler — the fit *can* return SETTLE on this
data, it did so, and it did so on the wrong unit. B3's NO STRUCTURE is
therefore not a dead test.

#### s-variant robustness (§3.3 falsifier 6)

The whole pass was re-scanned under `--svar s1` (s(k) ≡ 1). Under that arm
**d0wd/B3/arg κ flips to SETTLE** (τ = 24.4 min, R² = 0.938, p = 0.0005) —
and it is the only B3 SETTLE anywhere in this document.

**It is not reportable, on the falsifier that was written for it.** §3.3 item 6
says in advance that an effect present under only one variant branch falsifies
the reading. Three independent reasons it should not be believed:

1. It is **absent under the primary `strue` arm** on the same cell (ΔBIC20
   = −6.8, i.e. M2 is *worse* than a constant).
2. The `s1` arm is the **undemodulated** conjugate statistic, which
   `IQ_IMBALANCE.md` §1.6 identifies as dominated by the pure-channel term
   `Σ_k H̃(k)H̃(−k)` — it is essentially `κ₀`, that document's **control 2**,
   the version of the measurement "with the confound left in".
3. Under `s1` the **controls light up too** — s3/B1/arg κ goes to ΔBIC 133.8
   and s3/B2/arg κ to 60.3, both DRIFT. An arm that finds strong structure on
   two untouched beacons is measuring the room.

### 11.5 MAGNITUDE against the wander bar (§3.4) — the decisive table

Excursion = |mean of first 5 min − mean of last 20 min| of the 60 s bin
series, in `BETWEEN_UNIT_SD = 0.00237` rad/sc.

| rx | unit | excursion rad/sc | **× σ** | bar (B3_MOVED §9.1) | **clears?** | × THERMAL_EVIDENCE median |
|---|---|---:|---:|---:|---|---:|
| s3 | **B3** | 0.005477 | **2.31** | **4.91** | **no** | 8.98× |
| s3 | B1 | 0.000308 | 0.13 | 2.72 | no | 0.51× |
| s3 | B2 | 0.002912 | 1.23 | 0.42 | *yes* | 4.77× |
| d0wd | **B3** | 0.001025 | **0.43** | **2.76** | **no** | 1.68× |
| d0wd | B1 | 0.002321 | 0.98 | 2.52 | no | 3.81× |
| d0wd | B2 | 0.006009 | 2.54 | 17.99 (degenerate) | no | 9.85× |

**B3 clears its bar on neither receiver.** The one "yes" in the table is
**untouched B2 on the s3**, and it is a yes only because that pair's bar is
0.42 σ — `B3_MOVED.md` §9.1's single genuinely tight cell — so it is a
statement about how quiet that link normally is, not about a treatment.

**And this file's own contemporaneous null says the same thing more directly.**
`B3_MOVED.md` §9.1's bar is a range of block medians over 3111 s blocks of a
6.70 h file; only one such block fits in 70 minutes, so the identical
*statistic* was recomputed on six 703 s blocks of this file:

| rx | unit | SFO block range | **× σ** | κ block range | × S_bd(κ) |
|---|---|---:|---:|---:|---:|
| s3 | **B3 (treated)** | 0.004533 | **1.91** | 0.002625 | **0.36** |
| s3 | B1 | 0.001257 | 0.53 | 0.001769 | 0.24 |
| s3 | B2 | 0.002327 | 0.98 | 0.007043 | **0.95** |
| d0wd | **B3 (treated)** | 0.002167 | **0.91** | 0.002037 | 0.84 |
| d0wd | B1 | 0.006116 | **2.58** | 0.001553 | 0.64 |
| d0wd | B2 | 0.007881 | **3.33** | 0.000601 | 0.25 |

> **The treated beacon is not the biggest mover on either feature.** On the
> SFO slope, untouched d0wd/B2 (3.33 σ) and untouched d0wd/B1 (2.58 σ) both
> exceed treated s3/B3 (1.91 σ) and treated d0wd/B3 (0.91 σ). On κ, untouched
> s3/B2 (0.95 S) exceeds both treated cells (0.36 S, 0.84 S).

That is the whole result in one table, and it does not need a model fit.

### 11.6 Head-to-head — did κ or the slope move more?

Both normalised by their own between-device spread computed on this file
(§3.5), so the two are comparable:

| rx | S_bd(sfo) | S_bd(κ) | unit | sfo exc/S | κ exc/S | **ratio κ/sfo** |
|---|---:|---:|---|---:|---:|---:|
| s3 | 0.005059 | 0.007375 | **B3** | 1.083 | 0.324 | **0.300** |
| s3 | | | B1 | 0.061 | 0.200 | 3.291 |
| s3 | | | B2 | 0.576 | 0.885 | 1.538 |
| d0wd | 0.010635 | 0.002416 | **B3** | 0.096 | 0.525 | **5.454** |
| d0wd | | | B1 | 0.218 | 0.454 | 2.080 |
| d0wd | | | B2 | 0.565 | 0.314 | 0.556 |

**The two receivers disagree and the disagreement has a known cause, so no
single ratio is quoted.** The d0wd's `S_bd(κ) = 0.002416` is set by
d0wd/B1's whole-file `|κ| = 0.00020` — the one cell `IQ_IMBALANCE.md` §12
classified **AT NOISE FLOOR** on this hardware. A between-device spread whose
smallest member is noise is not a valid normaliser, so **the d0wd's 5.454 is
an artifact of the denominator, not a measurement that κ moved more.** The s3,
where all three beacons are well above the floor (|κ| = 0.0069 / 0.0184 /
0.0172), gives **0.300 — κ moved less than the slope**.

The statement that does not depend on a normaliser at all: on the treated
unit's strongest cell, **`|κ|` moved 0.00027 on a level of 0.01719 — 1.6% —
over 70 minutes.**

### 11.7 κ's own controls: ν, and the RSSI dilution hazard

| rx | unit | \|κ\| | \|ν\| | arg κ | **exc\|κ\|** | **exc\|ν\|** | r(\|κ\|,RSSI) | Δrssi dB |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| s3 | **B3** | 0.01719 | 0.05221 | −1.833 | **0.00027** | 0.00802 | +0.29 | 0.58 |
| s3 | B1 | 0.00688 | 0.04546 | −1.097 | 0.00091 | 0.00604 | +0.25 | 0.33 |
| s3 | B2 | 0.01840 | 0.06823 | −2.215 | 0.00070 | 0.00304 | −0.24 | 0.18 |
| d0wd | **B3** | 0.00438 | 0.12824 | +1.890 | **0.00013** | 0.00525 | +0.14 | 0.71 |
| d0wd | B1 | 0.00020 | 0.04374 | +3.015 | 0.00058 | 0.00102 | −0.06 | 0.51 |
| d0wd | B2 | 0.00256 | 0.07597 | −2.710 | 0.00023 | 0.00176 | +0.32 | 0.01 |

**`exc|ν|` exceeds `exc|κ|` by 3× to 40× in all six cells.** §2.2 and
§3.3 falsifier 3 made "κ and ν move together" the condition under which the κ
arm would be withdrawn. **They do not move together — ν moves and κ does
not** — so the κ arm stands, and the approximate repositioning of §7.1 did
what one would expect: it perturbed the channel (which ν reads) without
perturbing the conjugate coefficient (which κ reads). That is a small
independent point in κ's favour and it is the only positive result in this
document.

RSSI moved by ≤ 0.71 dB between the early and late windows on every beacon, and
`r(|κ|, RSSI)` never exceeds 0.32, so §7.8's dilution hazard is not driving
anything here.

**§7.7's caveat is now the binding one.** κ held flat. But `IQ_IMBALANCE.md`
§15 puts `frac_rx` at **5.73, a lower bound** — most of κ is receiver silicon,
and **the receivers were not treated**. So "κ did not move when a transmitter
was heated" is consistent with κ being thermally robust *and* with the
transmitter's share of κ being too small to see the step. **This capture
cannot distinguish those, and the null on κ is reported as bounded, not as
robustness.** The bound: no `|κ|` change larger than 0.00027 (1.6% of level)
and no `arg κ` structure clearing p ≤ 0.01, on a transmitter that spent an
hour outdoors.

### 11.8 REBOOT vs SETTLE — not separable, and the reason is a missing record

M2 (settle) vs M3 (step at an unknown bin), ΔBIC = BIC(M3) − BIC(M2); positive
favours the settle.

| verdict | cells | which |
|---|---:|---|
| **NOT SEPARABLE** (\|ΔBIC\| < 10) | **12 of 18** | including **5 of B3's 6** |
| STEP beats settle | 4 | s3/B3/\|κ\| (step at **65.5 min** — the file's tail, not a boot), s3/B2/arg κ (11.5 min), d0wd/B1/sfo (11.5 min), d0wd/B1/arg κ (55.5 min) |
| settle beats step | 0 | — |

**No B3 cell shows an early step.** The one B3 cell where a step wins places it
at 65.5 minutes — four minutes before the end of the capture — which is not a
power-on transient by any reading. Of the three cells with steps in the first
15 minutes, **two are untouched B1/B2**.

`arg κ` at 20 s resolution, the finer check §5 asked for:

| rx | unit | max single-bin \|Δarg κ\| | at | bins ≥ half that size | shape |
|---|---|---:|---:|---:|---|
| s3 | B3 | 36.5° | 25.2 min | 8 | spread |
| s3 | B1 | 94.3° | 3.2 min | 20 | spread |
| s3 | B2 | 25.3° | 10.5 min | 18 | spread |
| d0wd | B3 | 177.5° | 49.8 min | 33 | spread |
| d0wd | B1 | 179.9° | 28.5 min | 76 | spread |
| d0wd | B2 | 178.9° | 17.8 min | 37 | spread |

**No cell shows a one-bin discontinuity.** The d0wd's ~178–180° maxima are
**not** a reproduction of `IQ_IMBALANCE.md` §15.1's ~155° common rotation and
must not be read as one: they occur at three different times (17.8, 28.5, 49.8
min), each is matched by 33–76 other bins of comparable size, and the d0wd's
`|κ|` is 0.0002–0.0044 — the receiver where §12 of that document put B1 **at
the noise floor**. Near-180° hops in the argument of a near-zero complex vector
are what phase noise looks like. **§15.1's rotation remains unexplained and
this capture does not touch it** — which is consistent with §1.4: it was never
attributed in the first place.

**What cannot be concluded.** B3's boot instant is unrecorded (§1.2, §1.3), so
a reboot transient that completed before 15:17:25 would leave no trace and
"NOT SEPARABLE" would be the result either way. §5 stated this asymmetry in
advance. **`IQ_IMBALANCE.md` §19 item 2's experiment — a capture straddling a
*deliberate* reboot with the reboot time written into the `label` column — has
still not been run**, and this file is not a substitute for it.

### 11.9 Against `docs/THERMAL_EVIDENCE.md` — reproduced, not contradicted

§4.1 pre-registered that B1 and B2 would show NO STRUCTURE, reproducing that
document's no-warm-up-transient finding. **They do, on the SFO slope, on both
receivers, at all three bin widths — twelve of twelve control cells return NO
STRUCTURE** (four control-SFO cells × 30 / 60 / 120 s). The treated unit does
too, on six of six. That is a fourth file, at a much finer bin width than that
document's 5–30 min opening intervals, agreeing with `THERMAL_EVIDENCE` §3.

**This document therefore does not contradict `THERMAL_EVIDENCE`. It extends
it in one specific way:** that pass could only show that an *ordinary capture
start* carries no transient, and its §3.1 control showed the transmitter was
often already warm at those starts. This pass adds a start where the
transmitter was provably **not** in thermal equilibrium with the room, and
still finds nothing above the wander floor.

Two of the controls' `arg κ` cells *do* carry structure (§11.4), and κ is a
feature `THERMAL_EVIDENCE` never examined, so that finding neither reproduces
nor contradicts anything there. **What it does mean is that arg κ carries
slow session-internal structure on untouched beacons**, which is a caution for
`IQ_IMBALANCE.md` §13 — where `arg κ` is the quantity carrying the 8.4–11.2 σ
separation — and it is flagged here rather than resolved.

---

## 12. Limitations

- **n = 1.** One treated unit, one trial, one capture, no replication. Every
  statement above is about this 70 minutes.
- **No temperature was measured.** Not outdoor, not indoor, not on-die. The
  size of the step, and its sign, are unknown. **A null here does not exclude
  a thermal mechanism; it bounds one.** The bound is §11.5's: nothing above
  1.91 σ on the slope or 0.36 S on κ over six 703 s blocks.
- **The treatment is an operator report** (§0.1), not a recorded field. On the
  previous manipulation that report was wrong about which board was treated
  (`B3_MOVED.md` §0.0), and it was corrected from data. It was not
  independently re-derived here.
- **B3 was returned to approximately, not exactly, its previous position**
  (§7.1). The entire primary analysis is within-file to avoid this, but it
  means the tail of this file is a *near* reproduction of any earlier baseline
  and no cross-file comparison here carries weight.
- **The channel-reversal control failed** (§11.3). The bench differs from the
  14:13 file in a way nothing recorded explains.
- **d0wd/B1 lost half its κ bins to the 2,000-frame floor**, and its
  whole-file `|κ| = 0.00020` is at the noise floor `IQ_IMBALANCE.md` §12
  identified. That cell is unreliable and it also corrupts the d0wd's
  between-device spread, which is why §11.6 quotes no pooled ratio.
- **κ is receiver-dominated and the receivers were untreated** (§7.7,
  §11.7). This is the reason the κ verdict is "not determined" rather than
  "robust", and it is a property of the design, not of the analysis.
- **A reboot preceding the capture is unexcludable** (§11.8), because B3's
  boot instant is in no field of this data.
- **The 70-minute window may simply be too short**, or the settle may have
  completed during the walk indoors and the file-open. §3.2's τ grid ran to
  35 min and no B3 cell placed a credible τ inside [1, 30]; that is evidence
  against a settle *in this window*, not against a settle.
- **`ρ_decay` and the permutation test share the same 70 bins**, so they are
  not independent evidence; they are two different ways of refusing the same
  overfit.
- **No `pc/occ/` number was read, produced or combined with anything here.**
  No device-ID accuracy figure is derived or revised. `docs/DIRECTION.md` is
  not cited as capability. The ~77 % same-model figure is not quoted and not
  relabelled. Nothing was staged, committed or pushed.

## 13. What would settle it

1. **Instrument the temperature.** `THERMAL_EVIDENCE.md` §8 item 1 and
   `WEATHER_COVARIATE.md` §21 item 1 both already ask for per-frame die
   temperature at both ends, and this pass is the third document to arrive at
   the same request from a different direction. A one-dollar indoor
   thermometer at the bench, logged, would also do most of the job.
2. **Make the step bigger and log its time.** An hour outdoors in August is a
   small ΔT. A board taken from a freezer to the bench, with the *moment of
   return* written into the `label` column, gives a known t = 0 — which is the
   single thing this capture most lacked.
3. **Treat a receiver, not a transmitter.** κ is receiver-dominated by a
   factor of ≥ 5.73. **The experiment that actually tests κ's thermal
   conditionality is heating or cooling a receiver**, and it was not run here.
   This is the most important item on this list for anyone intending to build
   on κ.
4. **Run `IQ_IMBALANCE.md` §19 item 2 as written** — a deliberate reboot with
   the time in the `label` column. §11.8 could not substitute for it.
5. **Explain `arg κ`'s session-internal structure on untouched beacons**
   (§11.4, §11.9). Two control cells reached R² = 0.67–0.92 with no treatment.
   `arg κ` is the quantity `IQ_IMBALANCE.md` §13's separation rests on, and
   this is the first sign it moves within a session.

---

## Files added or written by this investigation

- `pc/exp_thermal_step.py` — the one script; source of every number above.
- `docs/THERMAL_STEP.md` — this file.

Nothing else in the repo was modified. `pc/rff/dsp.py` was read, not changed.
`data/raw/` was opened `"rb"` only. Scratch was written to `$TSTEP_CACHE`
outside the repo tree and removed; `PYTHONDONTWRITEBYTECODE=1` was set for
every invocation, so importing `pc/exp_iq_imbalance.py` left no `.pyc` behind
(the one artifact `IQ_IMBALANCE.md` §18 was unable to remove). Nothing was
staged, committed or pushed.
