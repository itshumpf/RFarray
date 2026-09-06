# IDENTITY_STABILITY — does an SFO signature survive across sessions on a fixed receiver?

**Stage 1 (this section) was written and saved before any scoring code was
run.** Section 8 onward is appended after the run. Nothing above the
`STAGE 2` banner was edited after results existed; if a Stage-1 statement
turns out to have been wrong, it is corrected *below* the banner with the
original left standing, not silently rewritten.

---

## 0. The question, and why it is the load-bearing one

The operator's goal is not to classify three beacons he owns. Those are a
signal source he controls. The goal is **identifying devices by their clock
signature on a receiver that stays put.**

Under that framing, cross-*receiver* transfer is an assumption the
application never needed. `docs/COLOCATED_0823.md` §5,
`docs/REFERENCE_CHOICE.md` §0 and `docs/SEPARATION_SCALING.md` §0 all
establish that which receiver heard a frame can dominate device identity —
and `CLAUDE.md` names that inversion as the mechanism behind the
99.7 % → 95.7 % device-ID drop. **Per-receiver enrollment is a legitimate
design response to that.** You enroll on the receiver you deployed.

What per-receiver enrollment **cannot** survive is cross-*session* drift on
the same receiver, because that would mean the enrollment expires and the
deployment needs continuous re-enrollment — which is the same as having no
enrollment at all.

**That has never been measured directly in this repo.** The two headline
numbers are both single-run, pooled-session, chronological-split figures
(`PROJECT_NOTES.md` §2 claim 2). `rff_offline.py` pools every input file
into one `by_mac` dict and then splits 60/40 by window index
(`rff_offline.py:333-337`), so its "holdout" test windows are drawn from
whatever session happens to sit last in the pooled sequence. It has no
notion of a session boundary. `docs/LOT_HYPOTHESIS.md` §5 and
`docs/THERMAL_EVIDENCE.md` §2.5 measure a *variance* decomposition of
session-to-session wander (within-unit across-session sd **0.00570** rad/sc
ref / **0.00618** raw, against a between-unit spread of **0.00237** ref /
**0.00213** raw) — but a variance ratio is not an identification rate, and
those figures are pooled across receivers.

This document measures the identification consequence, per receiver.

## 1. Design

### 1.1 Per receiver, never pooled

Every figure is reported for one receiver at a time. No receiver's windows
are ever mixed into another receiver's enrollment or test set, and no
accuracy is averaged across receivers. Pooling would reintroduce exactly
the confound the whole re-framing exists to avoid.

Receiver blocks analysed, and how each is identified:

| block | identity basis | sessions | caveat |
|---|---|---|---|
| **R1 `desk`** (era A) | **filename prefix only** | 2026-07-12 / 07-13 | Era A carries **no receiver identity in the data at all** (`docs/NODE_CENSUS.md` §1). `desk` is a string typed at `capture.py`'s command line. Two receivers provably existed (`NODE_CENSUS` P2); which was which is a **label, not a measurement** (I3). |
| **R2 `node3`** (era A) | filename prefix only | 2026-07-13, promiscuous era only | Same caveat. `node3` logged a **single-MAC** stream for its first seven sessions (`NODE_CENSUS` P5), so only sessions from 07-13 18:17 UTC onward have a class set at all. |
| **R3 node 68 / `rx_*`** (era B/C) | `node_id = 68` | 07-14 ×3, 07-15, 07-22 ×2 | `node_id` is a **compiled-in firmware constant** — it identifies a build, not a board (`NODE_CENSUS` I2). Spans 07-14 → 07-23: the longest inter-session intervals available, which is what the drift question needs. |
| **R4 node 68 / August** | `node_id = 68` | 08-21, 08-22 ×3, 08-23 ×2 | Same `node_id` as R3 but 39 days later; **treated as a separate block**, because nothing records what happened in between. Contains the 08-22 remount. |
| **R5 node 108 / `s3_*`** | `node_id = 108` | 08-21, 08-22 ×3, 08-23 ×2 | The second August receiver. Contains the 08-22 remount. |

**The 2026-08-22 remount.** `docs/COLOCATED_0823.md` §0 and §5.5 record that
both receivers were remounted onto the same wall on 2026-08-22, and that
the remount moved *both* position and separation at once. It falls between
`*_20260822_235739` (pre) and `*_20260823_013537` (post). **Any R4 or R5
session pair that straddles that boundary is not a fixed-receiver
comparison and is reported separately, never pooled into the headline.**
Within R4/R5 the pre-remount block is {0821_125017, 0822_023034,
0822_144424, 0822_235739} and the post-remount block is {0823_013537,
0823_014740}.

R3 and R4 share a `node_id` but are 39 days apart with no artifact recording
the receiver's position in between; they are not joined.

`occ_*` captures are **excluded** even though they are node-68 CSI. They are
in scope physically but `docs/NODE_CENSUS.md` §5 records an unlogged beacon
outage across five of them, and keeping the block to `rx_*` avoids any
appearance of fusing pipelines. **No `pc/occ/` number is read, produced or
combined with anything here.**

### 1.2 Within-session, cross-session, and the gap

For an **ordered pair (A → B)** of sessions on one receiver:

- **Test set is always the last 40 % of session B's windows, per device,
  chronologically.** Identical windows in both arms. Only the enrollment
  changes. This is the tightest available comparison: any difference is
  attributable to where the enrollment came from and to nothing else.
- **Within-session arm (the upper bound):** enroll on the **first 60 % of
  session B**. 60/40 is `rff_offline.TRAIN_FRACTION`, kept so the number is
  comparable to the repo's own convention.
- **Cross-session arm (the real number):** enroll on **all windows of
  session A**.
- **The gap = within − cross. That is the drift cost and it is the
  headline.**

Every ordered pair available on a receiver is run, both directions, not one
pair.

### 1.3 Class set

**Beacons and ambient devices on equal footing.** No device is excluded for
being third-party, and no device is given a privileged role in the class
set. The class set for a pair (A → B) is:

> every source MAC with **≥ 10 accepted 64-frame windows in session A AND
> ≥ 10 in session B**, after corrupt-row screening.

10 windows is the floor because `Discriminator.MIN_CHARACTERIZED = 5`
(`discriminator.py:79`) and the 60/40 within-session split of 10 windows
still leaves 6 to enroll and 4 to test. The class set is **identical in both
arms of a pair**, so the gap is not contaminated by a moving denominator.

**N classes is printed next to every single accuracy figure in this
document, without exception.** `CLAUDE.md` records that the ~77 % same-model
figure is permanently uninterpretable precisely because its class count was
never written down. This document will not create a second one.

Three breakdowns are reported for every pair: **combined**, **beacon-only**
(the ≤3 MACs meeting `docs/NODE_CENSUS.md` §2's proven beacon signature),
and **ambient-only** (everything else). Ambient-only is the number a real
deployment faces, so it is not an afterthought.

### 1.4 Feature space: raw is primary, ref is the mitigation arm

Both arms are run for every pair.

- **`raw`** = `(obs['cfo'], obs['sfo'])`. **Primary.** It is the direct
  measurement of the signature whose survival is the question.
- **`ref`** = `(obs['cfo_ref'], obs['sfo_ref'])`, the shipped
  reference-corrected space (`pc/rff/reference.py`, ref MAC
  `a4:f0:0f:77:91:20`). **This is the mitigation arm**, and it is the
  scientifically interesting one, because reference correction is designed
  to cancel exactly the receiver-side common-mode wander that is a prime
  drift candidate.

**Pre-registered warning about `ref`, so it cannot be enjoyed after the
fact:** for the reference beacon *itself*, `sfo_ref` is its own innovation
against its own Kalman track, and `ReferenceNormalizer` restarts per file
(`rff_offline.collect_observations`). So the reference beacon's `ref`
feature is **~0-centred in every session by construction**. That will make
the reference beacon look artificially stable across sessions in the `ref`
arm. `docs/THERMAL_EVIDENCE.md` §2.2 and §6 reading 2 flag the same
construction. **Any `ref`-arm improvement that is carried by the reference
beacon alone is an artifact and will be labelled one.** The `ref` arm is
credible only for non-reference devices.

### 1.5 Two accuracy definitions, both reported

- **`A_gated`** — the shipped χ² gate. `Discriminator.classify` returns
  STRANGER above `CHI2_99 = 9.21`; a STRANGER counts in the denominator and
  not in the numerator, matching `rff_offline.py:360-385`. **This is the
  deployment number.**
- **`A_nn`** — nearest centroid, gate ignored. **This is the science
  number**, and it is reported because the gate is the first thing drift
  breaks: a centroid that has moved makes *everything* a STRANGER, which
  collapses `A_gated` without necessarily meaning the signature stopped
  pointing at the right device.

Thresholds below apply to both. Where they disagree, that disagreement is
itself the finding and will be stated.

### 1.6 Pipeline, held fixed

- `pc/rff/dsp.py` is **not modified**. `FrameEstimator` and
  `WindowAggregator` are used as shipped, gates `min_inlier_ratio = 0.6` /
  `max_resid = 0.8` (`dsp.py:164`), window **64 frames** (the shipped
  default).
- The discriminator is `pc/rff/discriminator.py` as shipped.
- `pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py`
  are **not used** — `docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 establishes all
  three have the DC/guard-band index wrong.
- **Every stream is replayed from the start of its file with a fresh
  estimator**, one per (file, source-MAC), with no window, filter or
  subsample ahead of it. `ransac_line` draws from a per-instance RNG that
  advances once per fitted frame (`dsp.py:118,132`; `docs/V2_SPEC.md` §5.5),
  so a replay that does not start at byte one is not comparable to one that
  does.
- **Row cap: the first 300,000 data rows of each file**, chosen from a
  timing probe (≈ 8,000 rows/s on this host, so ≈ 38 s per file) and fixed
  before any scoring. A prefix is a legitimate truncation under the
  replay-from-start rule — the windows it yields are byte-identical to the
  ones a full replay would emit over the same rows — and it equalises
  exposure across sessions of very different length. It is a **subsample**
  and is labelled one everywhere. Files shorter than the cap are read whole.
- **Corrupt rows are screened before the estimator and before any delta
  arithmetic**, by both routes `docs/COLOCATED_0823.md` §1 requires: field
  plausibility, and a width-9 median filter on `dropped` compared circularly
  mod 65536. **Era A (10-column) files have no `dropped`, `node_id` or
  `env_id` column, so the median-filter route does not exist for R1 and R2.**
  That is a missing column, not an unrun check, and R1/R2 corrupt-row
  screening is therefore weaker than R3/R4/R5's. Stated here rather than
  discovered later.

### 1.7 Drift decomposition — common-mode vs per-device

For each ordered pair (A → B) on a receiver, the per-device shift is

> `Δ_d = median SFO of device d in B − median SFO of device d in A`

- **Total drift** = RMS of `Δ_d` over the pair's devices.
- **Common-mode** = the median of `Δ_d` across devices — the component every
  device in the room shares, which is receiver-side and, being shared, is
  removable by a reference-relative measurement (`pc/rff/reference.py`,
  `docs/REFERENCE_CHOICE.md`).
- **Per-device residual** = RMS of `Δ_d − common-mode`. **This is the number
  that limits deployment**, because it cannot be corrected without
  re-observing each device individually — which is re-enrollment.
- **Variance explained by the shared component** = `1 − Var(residual) /
  Var(Δ_d)`, with the device count n printed.

A large total with a large common-mode fraction is a **good** result: it is
compensable. A small total that is nearly all per-device residual is
**worse than it looks.**

### 1.8 Covariates

**Checked, in the columns that actually exist, before concluding anything.**
The full era-B/C/August schema is
`pc_time_us, label, seq, mac, rssi, noise_floor, channel, esp_timestamp_us,
len, csi_data, node_id, env_id, dropped`; era A is the first ten of those.
**There is no temperature column and no temperature was ever recorded
anywhere in this project** (`docs/THERMAL_EVIDENCE.md`, standing note above
its §1). No field is added and none is assumed. The covariates that do exist
and will be regressed against the common-mode component are:

- **elapsed wall-clock between the two sessions** (`pc_time_us`),
- **local time of day** of each session (`pc_time_us`, local = UTC−5),
- **mean `rssi`** and **modal `noise_floor`** per (session, device).

`esp_timestamp_us` is node-boot-relative and **wraps**
(`rff_offline.iter_frames` docstring), so it is not used as an uptime
covariate; saying "uptime" from it would be inventing a circumstance the
field does not carry (`CLAUDE.md` failure mode **G**).

`docs/THERMAL_EVIDENCE.md` has been read in full before writing this.
Its findings are **not** to be re-derived or contradicted here: no power-on
warm-up transient is detectable (§3, smallest p in the whole sweep 0.23 at
n = 25); head-trimming warm-up makes the wander **worse**, +1 % to +20 %
(§4); time of day is **underpowered, not measured** — 12 distinct sessions,
non-independent points, r flips sign with feature space (§5). **If a
time-of-day correlation appears here it will be reported against that prior
and will not be presented as a new discovery, and no thermal causation will
be asserted from it.**

## 2. Thresholds — committed now, before any result exists

These exist so the result cannot be rationalised afterwards. They are stated
as the median over the ordered pairs available on a given receiver, in the
**raw** arm, on the **combined** class set, unless a row says otherwise.

### 2.1 The headline gap (within − cross, same test windows)

| verdict | condition | what it means for the deployment |
|---|---|---|
| **STABLE — deployable** | median gap **≤ 10 pp** AND median cross-session accuracy **≥ 0.80 × within-session accuracy** | Enroll once per receiver. The enrollment holds across a session boundary at a cost of at most a tenth of the within-session rate. |
| **MARGINAL** | gap **10–30 pp**, and cross-session accuracy still **≥ 2 / N** (twice chance) | Usable with a re-enrollment schedule, if §2.3 gives an interval to quote. |
| **FATAL** | median gap **> 30 pp**, OR median cross-session accuracy **< 2 / N** | The signature does not survive a session boundary. Per-receiver enrollment does not rescue the design; it needs continuous re-enrollment, which is the same as having no enrollment. |

`2 / N` is written as a fraction of the pair's own class count, so it moves
with N and cannot be gamed by a convenient class set.

### 2.2 The reference device's honest headline pair

`a4:f0:0f:77:91:20`, per receiver, cross-session, with N and the pair count
attached. **Recall without its false-positive companion is not a result**,
so both are thresholded:

| verdict | condition |
|---|---|
| **usable** | recall **≥ 0.70** AND false-positive rate **≤ 0.30** (fraction of *other* devices' test windows misattributed to it) |
| **not usable** | either bound violated |

### 2.3 Does the gap grow with elapsed time?

Spearman ρ between |elapsed wall-clock between A and B| and the pair's gap.

| verdict | condition | consequence |
|---|---|---|
| **drift accumulates** | ρ **> 0**, p **< 0.05**, n **≥ 10** pairs | There is a re-enrollment interval that can actually be quoted. |
| **fixed session-to-session offset** | \|ρ\| **< 0.3** and p **> 0.05** | Different and more tractable problem: a per-session offset, not an accumulating one. |
| **inconclusive** | anything else, or n < 10 | Say so. Do not pick the reading that is more convenient. |

Ordered pairs come in (A→B, B→A) duplicates with the same |elapsed|, so ρ is
computed on **unordered** pairs for the primary figure and on ordered pairs
as a secondary, with both n values printed.

### 2.4 Drift decomposition

| verdict | condition |
|---|---|
| **compensable** | common-mode variance-explained **≥ 0.70** AND per-device residual **≤ 0.00237** rad/sc |
| **not compensable** | per-device residual **> 0.00237** rad/sc |

`0.00237` is `BETWEEN_UNIT_SD` — the entire between-unit spread of the three
beacons' grand means (`docs/LOT_HYPOTHESIS.md` §5, used as σ throughout
`docs/COLOCATED_0823.md` §5 and `pc/exp_thermal_evidence.py:129`). **If the
per-device residual between two sessions exceeds the whole spread between
devices, devices swap places and identity is destroyed regardless of what
the accuracy number says.** That is the fatal condition for this section,
and it is deliberately set at a value that already exists in the repo rather
than one chosen now.

### 2.5 The `84:7b:57:cc:20:0e` confusion

`CLAUDE.md` records the largest single error mode as **276 reference windows
landing on `84:7b:57:cc:20:0e`**, an ambient third-party device 2.54σ from
the reference, in the 95.7 % combined-receiver run.

| verdict | condition |
|---|---|
| **persistent** | reference → `84:7b` is the largest single confusion in **≥ 50 %** of the ordered pairs where both devices are in the class set |
| **one-session artefact** | it appears in **< 20 %** of those pairs |
| **intermediate** | reported as such, with the fraction and the denominator |

If `84:7b:57:cc:20:0e` fails the 10-window floor on a receiver, that is
reported as **"not in the class set on this receiver"** and explicitly
distinguished from "measured and absent" — `CLAUDE.md` failure mode **C**.

### 2.6 What would make this whole document not answer the question

Stated now so it is not discovered as an excuse later:

- Fewer than 3 sessions with a shared class set on any single receiver →
  cross-session is one pair and n is too small for §2.3. Say so.
- A class set that turns out to be beacons only on every receiver → the
  ambient-only breakdown does not exist and the "what a real deployment
  faces" claim cannot be made. Say so; do not substitute the beacon number.
- If the within-session upper bound is itself low (< 70 %), the gap is
  measured against a weak ceiling and the *ratio* becomes the honest
  statistic rather than the difference. Report both regardless.

## 3. Reproduce

One script, `pc/exp_identity_stability.py`, read-only on `data/raw/`, no
serial port opened, nothing staged or committed. Scratch state goes to
`$IDST_CACHE` outside the repo tree.

```
export IDST_CACHE=/tmp/idst
python3 pc/exp_identity_stability.py extract <csv> --cap 300000     # per file, checkpointed
python3 pc/exp_identity_stability.py score                          # all receivers, all ordered pairs
python3 pc/exp_identity_stability.py report
```

---
---

# STAGE 2 — results

Run 2026-08-23. **33 session files replayed, 6,279,715 data rows** through
`pc/rff/dsp.py` as shipped. `pc/rff/dsp.py` was not modified — its mtime is
still **2026-07-13 20:42:46**, the same value `docs/COLOCATED_0823.md` §1
records. No serial port opened, nothing under `data/raw/` written, nothing
staged (`git diff --cached --name-only` empty before and after), nothing
committed or pushed.

## 8. Verdict

**No. A device's SFO signature does not survive from one session to the next
on a fixed receiver — and the reason is worse than a session boundary: it
does not reliably survive from one hour to the next *inside* a single
session either.**

On the only receiver block with enough sessions to answer properly
(**R3**, `node_id 68`, six `rx_*` sessions, 07-14 → 07-23):

> **within-session 57.9 %, cross-session 29.7 %, gap 28.2 pp — against
> N = 3 classes, median over 30 ordered pairs, 108–1,843 test windows per
> pair.** Chance is 33.3 %. **Cross-session identification is at or below
> chance.**

That is **FATAL** on the §2.1 threshold (`cross < 2/N = 66.7 %`), and it is
FATAL on all three receiver blocks that have a class set larger than two.
The three-number drift decomposition (§13) says why, and it is the more
useful answer: the drift is **large and mostly NOT common-mode**, so it is
**not compensable** by a reference-relative measurement.

The one apparently-good result — **R1 `desk`, gap 6.4 pp** — is a **2-class
problem with a 45 : 1 class imbalance**, and is reported in full in §11
precisely so it is not quoted as a survival result. It is not one.

## 9. What was actually run

300,000-row prefix cap per file, as pre-registered. Corrupt-row screening
fired on the era-B/C/August files and had no column to fire on in era A:

| block | sessions | rows analysed | field-screened | median-filter-screened | median filter |
|---|---:|---:|---:|---:|---|
| R1 `desk` era A | 9 | 1,348,607 | 0 | — | **column absent** |
| R2 `node3` era A | 6 | 881,759 | 0 | — | **column absent** |
| R3 node 68 July | 6 | 1,260,871 | 59 | 0 | yes |
| R4 node 68 August | 6 | 1,395,913 | 81 | **1** | yes |
| R5 node 108 August | 6 | 1,392,565 | 0 | 0 | yes |

The single median-filter catch is on `d0wd_20260822_023034` — a row the
field screen passed and only the circular median filter rejected, the same
class `docs/COLOCATED_0823.md` §3.3 found three of. Era A's zero is **"no
`dropped`/`node_id`/`env_id` column exists"**, not "checked and clean"
(`CLAUDE.md` failure mode **C**).

## 10. The class set that actually materialised — §2.6 bullet 2 fired

**Pre-registered failure condition §2.6 bullet 2 is what happened, on every
receiver.** At the shipped 64-frame window, ambient traffic in this corpus
is too sparse to form a class:

| block | distinct MACs emitting ≥1 window | clear the 10-window floor in ≥1 session | clear it in **≥2** sessions (the only ones that can *be* a cross-session class) | **ambient devices eligible** |
|---|---:|---:|---:|---|
| R1 `desk` | 5 | 2 | 2 | **1** — `84:7b:57:cc:20:0e`, in 3 of 9 sessions |
| R2 `node3` | 4 | 1 | 1 | **0** |
| R3 node 68 July | 5 | 3 | 3 | **0** |
| R4 node 68 Aug | 9 | 6 | 3 | **0** |
| R5 node 108 Aug | 8 | 4 | 3 | **0** |

An ambient device at 1–3 fps needs ~640 accepted frames for 10 windows.
`84:7b:57:cc:20:0e` carries 6,707 frames across 17 files in the whole
project (`docs/NODE_CENSUS.md` §2.5) — a few hundred per file.

**Consequences, stated rather than worked around:**

- **The ambient-only breakdown does not exist on any receiver**, so the
  "what a real deployment faces" claim in §1.3 **cannot be made from this
  corpus**. The beacon-only number is **not** substituted for it. On
  R3/R4/R5 the combined and beacon-only figures are identical because the
  class set *is* the three beacons.
- **R2 `node3` is entirely unscorable.** In its promiscuous era it heard
  exactly one source above the floor — the reference beacon — so N = 1 and
  there is no cross-session identity question to ask on it. Six sessions,
  zero usable pairs.
- **The floor was not lowered after seeing this.** Lowering `MIN_WIN` from
  its pre-registered 10 is the exact post-hoc move §2 exists to prevent.

## 11. Within-session vs cross-session, per receiver

Same test windows in both arms (the last 40 % of session B, per device).
**N = class count, printed against every figure.**

### R3 — node 68, `rx_*`, 07-14 → 07-23 · the primary result

| | **N** | within | cross | **gap** | cross/within | chance 1/N |
|---|---:|---:|---:|---:|---:|---:|
| **raw, gated** (deployment) | **3** | 57.9 % | **29.7 %** | **28.2 pp** | 0.513 | 33.3 % |
| raw, nearest-centroid | 3 | 59.6 % | 30.9 % | 28.7 pp | 0.518 | 33.3 % |
| ref, gated | 3 | 58.7 % | 34.9 % | 23.8 pp | 0.595 | 33.3 % |
| ref, nearest-centroid | 3 | 61.1 % | 38.4 % | 22.7 pp | 0.629 | 33.3 % |

Median over **30 ordered pairs** (all of them controlled — no remount in
this block). Test-set sizes 108–1,843 windows. **Gated and
nearest-centroid agree to within 1.5 pp everywhere**, so the collapse is
*not* the χ² gate rejecting drifted centroids — the signature genuinely
stops pointing at the right device. Strangers are negligible (10–11 of
1,827 in the audited pair).

The `ref` arm improves the cross number by 5.2 pp and is **still below
2/N**. Per §1.4 that improvement is partly the reference beacon's own
construction artifact: its recall rises 18.1 % → 32.3 % in `ref`, which is
the unit whose `ref` feature is ~0-centred by design.

### R4 — node 68, August (14 controlled pairs; 16 straddling pairs excluded)

| | N | within | cross | gap |
|---|---:|---:|---:|---:|
| raw, gated | **3** | 60.7 % | **33.3 %** | 27.4 pp |
| ref, gated | 3 | 61.7 % | 33.1 % | 28.6 pp |

Cross-session **exactly at chance (33.3 % = 1/N)**.

### R5 — node 108, August (14 controlled pairs; 16 straddling excluded)

| | N | within | cross | gap |
|---|---:|---:|---:|---:|
| raw, gated | **3** | 53.2 % | **46.7 %** | 6.5 pp |
| ref, gated | 3 | 55.4 % | 38.8 % | 16.7 pp |

R5's raw gap of 6.5 pp is the smallest anywhere, and it is **not** a
stability result: it is 6.5 pp measured against a **53.2 % ceiling** on
N = 3, i.e. the within-session arm has already collapsed to within 20 pp of
chance, so there is little left for the session boundary to take. §2.6
bullet 3 applies — the **ratio** (0.878) is the honest statistic, and it is
high only because the numerator and denominator are both bad. R5 also
contains the single worst within-session cell in the whole run:
`s3_20260821_125017` scores **3.0 % within-session on N = 3**, below chance
by a factor of eleven.

### R4 / R5 straddling the 2026-08-22 remount — **not** a controlled comparison

16 pairs per block cross the remount (`docs/COLOCATED_0823.md` §5.5: it
moved position *and* separation at once, and nothing in the record labels
it). Reported separately and never pooled: R4 raw within 50.8 % / cross
39.4 % / gap 11.4 pp; R5 raw within 64.5 % / cross 39.2 % / gap 25.3 pp,
N = 3 both. **These are not evidence about drift.**

Between `desk_20260821_125017` and the 08-22 sessions **nothing records
whether the receivers moved**; those pairs are treated as controlled on the
absence of a recorded move, which is weaker than a recorded absence
(failure mode **G**).

### R1 `desk`, era A — the number that looks good and is not

| | N | within | cross | gap |
|---|---:|---:|---:|---:|
| raw, gated | **2** | 95.6 % | 89.2 % | **6.4 pp** |
| ref, gated | 2 | 96.3 % | 92.9 % | 3.5 pp |

6 ordered pairs, from the only 3 of 9 sessions where `84:7b:57:cc:20:0e`
clears the floor. **Four reasons this is not a survival result:**

1. **N = 2.** The pre-registered `2/N` arm evaluates to 100 % and is
   degenerate; only the gap arm is usable.
2. **Class imbalance 45 : 1** — median 268 reference test windows against 6
   for `84:7b`. 89.2 % accuracy is barely above simply always answering
   "reference".
3. The per-device split shows it: reference recall **89.7 %**, `84:7b`
   recall **55.0 %** at precision **43.6 %**.
4. Era A carries **no receiver identity in the data at all**; `desk` is a
   string typed at a command line (`docs/NODE_CENSUS.md` I3).

## 12. The finding that reframes the question: the within-session ceiling is itself broken

The within-session arm was pre-registered as the **upper bound**. On
R3/R4/R5 it is 53–61 % on N = 3 — barely above the 33 % chance line — and
individual sessions fall below chance. This was checked by an **independent
route that does not use the classifier at all**: per-device median SFO in
the first 60 % vs the last 40 % of a single session.

| session | device | first 60 % | last 40 % | within-session shift | × `BETWEEN_UNIT_SD` |
|---|---|---:|---:|---:|---:|
| `s3_20260821_125017` | `28:05:a5:2f:fa:48` | +0.00971 | +0.02453 | **+0.01482** | **6.3×** |
| `d0wd_20260822_023034` | `f4:2d:c9:70:72:30` | +0.05038 | +0.07263 | **+0.02225** | **9.4×** |
| `desk_20260713_172009` | `a4:f0:0f:77:91:20` | +0.00840 | +0.01240 | +0.00400 | 1.7× |
| `rx_20260714_031131` | `28:05:a5:2f:fa:48` | +0.00586 | +0.00347 | −0.00239 | 1.0× |

In `s3_20260821_125017` the first-60 % medians of `28:05` (**+0.00971**) and
`f4:2d` (**+0.00973**) are **identical to four decimal places** — the
enrollment cannot separate them at all — and by the last 40 % `28:05` has
moved to +0.02453. That is the entire explanation of its 3.0 % score, and it
is arithmetic, not a classifier artifact.

**So "cross-session drift" is the wrong name for this.** The signature
wanders continuously, by multiples of the whole between-device spread, on a
timescale of tens of minutes. A session boundary is not what breaks it; a
session boundary is just a long enough interval for the wander to finish the
job. This is consistent with, and sharpens, `docs/LOT_HYPOTHESIS.md` §5
(within-session pair separations ranging 0.05σ to 9.08σ across six
consecutive chunks of one 42-minute prefix) and with
`docs/THERMAL_EVIDENCE.md` §4's finding that the wander is "spread through
the session, not concentrated at its start."

## 13. Drift decomposition — total, common-mode, per-device residual

Per-device SFO shift between the two sessions of a pair; common-mode = the
median shift across devices; residual = what is left. **`var_explained` is
the fraction of total drift *energy* (mean-square about zero) removed by
subtracting one shared constant** — not `1 − Var(resid)/Var(Δ)`, which is
identically zero because variance is taken about the mean and is unchanged
by subtracting a constant. That error was in the first version of this
script and is recorded here rather than quietly fixed.

| block | space | n devices | **total RMS** | **\|common-mode\|** | **energy removed by the shared constant** | **per-device residual RMS** | × 0.00237 | verdict §2.4 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| **R3** node 68 Jul | raw | 3 | 0.00725 | 0.00321 | **29.3 %** | **0.00511** | **2.16×** | **NOT COMPENSABLE** |
| R3 | ref | 3 | 0.00743 | 0.00347 | 45.6 % | 0.00509 | 2.15× | NOT COMPENSABLE |
| **R4** node 68 Aug | raw | 3 | 0.01942 | 0.00498 | **31.1 %** | **0.01687** | **7.12×** | **NOT COMPENSABLE** |
| R4 | ref | 3 | 0.01695 | 0.00060 | 1.9 % | 0.01694 | 7.15× | NOT COMPENSABLE |
| **R5** node 108 Aug | raw | 3 | 0.00902 | 0.00204 | **7.5 %** | **0.00882** | **3.72×** | **NOT COMPENSABLE** |
| R5 | ref | 3 | 0.00955 | 0.00391 | 26.7 % | 0.00794 | 3.35× | NOT COMPENSABLE |
| R1 `desk` era A | raw | **2** | 0.00216 | 0.00192 | 78.6 % | 0.00100 | 0.42× | within the spread |
| R1 | ref | 2 | 0.00216 | 0.00130 | 65.5 % | 0.00136 | 0.57× | within the spread |

**This is the answer to "which kind of drift is it", and it is the bad
kind.** On every block with three devices, the common-mode component
removes only **7–46 %** of the drift energy, and the **per-device residual
is 2.2× to 7.1× the entire between-device spread**. A shift that large
cannot be corrected by any reference-relative measurement, because it is
not shared — it is per-device, and removing it requires re-observing each
device individually, which is re-enrollment. **A small total that is nearly
all per-device residual would be worse than it looks; here the total is
large *and* it is mostly per-device residual, which is worse still.**

**R1's 78.6 % common-mode fraction is the only compensable cell, and it
rests on n = 2 devices** — with two points a "median across devices" and a
"shared component" are nearly the same object, so the decomposition is close
to vacuous there. It is reported for completeness, not as a counterexample.

This does **not** contradict `docs/THERMAL_EVIDENCE.md` §6, which found that
raw within-session movement is not *shared between two receivers* hearing the
same beacon. That is a different quantity: §6 asks whether one device's
trajectory is common across receivers; §13 asks whether several devices'
shifts are common within one receiver. Both come back "not common", from
opposite directions, and together they say the movement is
per-(receiver, device) — which is also what `docs/COLOCATED_0823.md` §4.1
found for the estimator-bias pathology.

## 14. The reference device's honest headline pair

`a4:f0:0f:77:91:20`, cross-session, **raw**, gated — recall and its
false-positive companion, with N and pair count attached:

| block | N | pairs | **recall** | precision | **FPR** (other devices' windows called "reference") | median n_test | §2.2 |
|---|---:|---:|---:|---:|---:|---:|---|
| **R3** node 68 Jul | 3 | 30 | **18.1 %** | 33.9 % | **16.0 %** | 457 | **not usable** |
| R4 node 68 Aug | 3 | 14 | **2.4 %** | 36.4 % | 2.0 % | 421 | **not usable** |
| R5 node 108 Aug | 3 | 14 | **3.7 %** | 45.1 % | 1.7 % | 514 | **not usable** |
| R1 `desk` era A | **2** | 6 | 89.7 % | 99.0 % | **45.0 %** | 268 | **not usable** (FPR > 0.30) |

**Stated as one sentence, as asked:** on receiver node 68 across six `rx_*`
sessions, `a4:f0:0f:77:91:20` is **recognised at 18.1 %** and **16.0 % of
other devices' windows are misattributed to it**, against **N = 3 classes**
over **30 ordered session pairs**. Every block fails §2.2, R1 on its
false-positive arm despite a 89.7 % recall — which is exactly why the
threshold was written as a pair.

**Not one of the three beacons is recognised at even 50 % cross-session on
any three-class block.** The full per-device tables are in the run output;
the worst cells are `a4:f0` at 2.4 % recall on R4 and `28:05` at 0.0 %
recall / 0.0 % precision on R4-`ref`. The device that scores *highest* is
`f4:2d:c9:70:72:30` at 79.0 % recall on R4 — but at **69.1 % FPR**, i.e. it
is absorbing most of the other two beacons' windows. That pair is the
clearest illustration in the run of why recall alone is not a result.

## 15. Does the gap grow with elapsed time?

Spearman ρ, unordered pairs primary (ordered pairs duplicate each
\|elapsed\|), permutation p, 20,000 permutations:

| block | space | **unordered** ρ (p, n) | ordered ρ (p, n) | §2.3 verdict |
|---|---|---|---|---|
| **R3** node 68 Jul | raw | **+0.604 (p = 0.017, n = 15)** | +0.331 (p = 0.075, n = 30) | **drift accumulates** |
| R3 | ref | +0.489 (p = 0.065, n = 15) | +0.334 (p = 0.075, n = 30) | leans same way, misses p |
| R4 node 68 Aug | raw | +0.607 (p = 0.169, **n = 7**) | +0.585 (p = 0.033, n = 14) | **inconclusive — n < 10** |
| R5 node 108 Aug | raw | **−0.321** (p = 0.495, **n = 7**) | −0.248 (p = 0.403, n = 14) | **inconclusive — n < 10** |
| R1 `desk` era A | raw | +0.500 (p = 1.000, **n = 3**) | +0.359 (p = 0.540, n = 6) | **inconclusive — n < 10** |

**Answer: on the only block that meets the pre-registered n ≥ 10 bar (R3,
n = 15 unordered, elapsed 0.03 h → 211.6 h), the gap grows with elapsed
time — ρ = +0.604, p = 0.017.** The nearest-centroid gap agrees
(ρ = +0.550, p = 0.033). So this is drift that **accumulates**, not a fixed
session-to-session offset.

**But the re-enrollment interval that implies cannot be quoted, and saying
otherwise would be the whole point of §2.3 thrown away.** Cross-session
accuracy on R3 is already at or below chance at the *shortest* interval
available — `rx_20260714_030915 → rx_20260714_031131`, **136.8 s
start-to-start** and only **7.4 s between the end of one capture and the
start of the next** (`docs/NODE_CENSUS.md` §4): cross **38.6 %** against a
within-session **21.5 %** on N = 3, i.e. both arms are at chance a
*two-minute* boundary apart. There is no
interval on the accumulating curve at which performance is acceptable, so
there is no interval to re-enroll at. The correlation describes how a
already-failed number gets worse.

**The two August receivers point in opposite directions** (R4 +0.607, R5
−0.321), both at n = 7, both below the pre-registered bar. That
disagreement is reported, not resolved.

## 16. Covariates — only what the columns actually carry

**There is no temperature column anywhere in this dataset and no temperature
was ever recorded in this project** (`docs/THERMAL_EVIDENCE.md`, standing
note). No field was added and no thermal causation is asserted. `label` is
empty on every row. `esp_timestamp_us` is boot-relative and wraps, so it was
**not** used as an uptime proxy. What was available and was tested, against
the **common-mode** component:

| block | space | common-mode vs **elapsed** | common-mode vs **time of day** | residual vs elapsed |
|---|---|---|---|---|
| R3 | raw | +0.411 (p = 0.027, n = 30) | +0.163 (p = 0.397, n = 30) | +0.450 (p = 0.015) |
| R3 | ref | +0.254 (p = 0.175) | +0.181 (p = 0.341) | +0.679 (p < 0.001) |
| R4 | raw | +0.143 (p = 0.639, n = 14) | −0.280 (p = 0.331) | +0.429 (p = 0.129) |
| R4 | ref | **−0.714 (p = 0.007)** | −0.235 (p = 0.425) | +0.429 (p = 0.129) |
| R5 | raw | −0.107 (p = 0.727, n = 14) | +0.198 (p = 0.495) | **−0.679 (p = 0.010)** |
| R5 | ref | −0.321 (p = 0.266) | −0.108 (p = 0.720) | −0.679 (p = 0.010) |

- **Time of day: nothing, on any block, in any space** — every p ≥ 0.33 and
  the sign flips between receivers and between feature spaces. This
  **reproduces `docs/THERMAL_EVIDENCE.md` §5** ("underpowered, not
  measured"; r flips with feature space) and is reported as a reproduction,
  not a discovery. No thermal reading is offered.
- **Common-mode vs elapsed is not consistent**: R3-raw is positive and
  significant, R4-`ref` is *negative* and significant, R5 is null. Two
  significant results with opposite signs across receivers, at n = 14–30
  non-independent ordered pairs, is not a finding.
- **Residual vs elapsed flips sign between R3/R4 (positive) and R5
  (negative, p = 0.010).** Reported as the contradiction it is.
- **RSSI and `noise_floor` were collected per (session, device) but are not
  regressed here.** `docs/COLOCATED_0823.md` §4.1 already establishes the
  pathological-cell behaviour "is **not** an RSSI story", and re-deriving
  that was out of scope for this pass. The values are in the cached
  manifests if someone wants them.

## 17. `84:7b:57:cc:20:0e` — the §2.5 question, answered as far as it can be

`CLAUDE.md` records **276 reference windows landing on
`84:7b:57:cc:20:0e`** as the largest single error mode of the 95.7 %
combined-receiver run.

**It cannot be classified "persistent" or "one-session artefact" by the
pre-registered test, and here is exactly why:**

| block | in the class set? | basis |
|---|---|---|
| R1 `desk` era A | **yes**, 3 of 9 sessions → 6 eligible ordered pairs | clears the floor |
| R2 `node3` era A | no | never clears the floor |
| **R3** node 68 Jul | **no** | **whole-file `grep`, not a prefix artefact**: 0 frames in `rx_20260714_011619`, `rx_20260715_201703`, `rx_20260722_204658`; **1,114 frames in `rx_20260714_031131` only**. Present in 1 of 6 sessions — it can never be a *cross*-session class here at any row cap. |
| **R4 / R5** August | **no** | **whole-file `grep`**: 2,852 frames in `desk_20260821_125017` and 568 in `s3_20260821_125017`; **0 in every 08-22 and 08-23 file on both receivers.** It stopped transmitting after 08-21. Again 1 of 6 sessions, again not a cap artefact. |

This is "**not in the class set**", not "measured and absent" — failure
mode **C**, and the distinction is made by whole-file counts rather than by
the analysed prefix.

**On R1, where it is scorable, the result is:** it is the largest
non-self confusion in **6/6 pairs raw and 4/6 ref** — but **that statistic
is vacuous at N = 2**, because it is the only other class. The meaningful
number is the **rate: a median 1.4 % of reference test windows land on it
cross-session (raw), 51 windows over 6 pairs; 1.7 % and 203 windows in
`ref`.** So it **recurs on every pair of that receiver rather than being a
one-session accident** — but at ~1–2 %, nowhere near the dominant error
mode. On R3/R4/R5 the dominant error is **beacon-against-beacon**
confusion, and `84:7b` is not a participant.

**Reconciliation with the 95.7 % run, without contradicting it:** that run
pooled `desk` and `node3` and split 60/40 across the pooled window
sequence, so its reference test set came almost entirely from one receiver
while its model was trained 87.7 % on the other (`CLAUDE.md`;
`docs/TWIN_INVESTIGATION.md` §6–7). This pass never pools receivers, so it
is measuring a different error surface and its numbers are **not**
comparable to 276/95.7 % and are not offered as a correction to them.

## 18. Verdicts against the Stage-1 thresholds

| § | threshold | measured | **verdict** |
|---|---|---|---|
| 2.1 | gap ≤ 10 pp AND cross ≥ 0.80 × within | R3 gap 28.2 pp, ratio 0.513, cross 29.7 % < 2/N = 66.7 % | **FATAL** |
| 2.1 | " | R4 gap 27.4 pp, cross 33.3 % < 66.7 % | **FATAL** |
| 2.1 | " | R5 gap 6.5 pp but cross 46.7 % < 66.7 %, ceiling 53.2 % | **FATAL** (gap arm passes, `2/N` arm fails) |
| 2.1 | " | R1 gap 6.4 pp, N = 2 → `2/N` degenerate | **inconclusive by construction** (§11) |
| 2.2 | reference recall ≥ 0.70 AND FPR ≤ 0.30 | R3 18.1 % / 16.0 %; R1 89.7 % / **45.0 %** | **not usable, every block** |
| 2.3 | ρ > 0, p < 0.05, n ≥ 10 | R3 ρ = +0.604, p = 0.017, n = 15 | **drift accumulates** — but no quotable interval (§15) |
| 2.3 | " | R4, R5, R1 all n ≤ 7 | **inconclusive**, and R4/R5 disagree in sign |
| 2.4 | var-expl ≥ 0.70 AND residual ≤ 0.00237 | R3 29.3 % / 0.00511; R4 31.1 % / 0.01687; R5 7.5 % / 0.00882 | **NOT COMPENSABLE, every 3-device block** |
| 2.5 | `84:7b` persistence | in the class set on 1 of 5 blocks; vacuous at N = 2 there | **not classifiable**; rate 1.4 % on R1, absent elsewhere by whole-file count |
| 2.6 b2 | class set beacons-only → say so, don't substitute | ambient-eligible = 0 on 4 of 5 blocks | **fired; ambient claim withdrawn** |
| 2.6 b3 | within-session < 70 % → report the ratio too | within is 53–61 % on R3/R4/R5 | **fired; ratios reported throughout, and §12 shows the ceiling is itself broken** |

## 19. Limitations

- **Prefix subsample.** 300,000 rows per file. Windows are byte-identical to
  a full replay over the same rows, but the later hours of the long captures
  are not analysed. The `84:7b` conclusions in §17 are the exception — those
  were re-checked by whole-file `grep`.
- **N = 3 on every block that has a real class set**, and it is the same
  three beacons everywhere. This measures whether *these three units* stay
  separable, not whether an arbitrary device population does.
- **The drift decomposition rests on 3 devices** (2 on R1). A common-mode
  estimate from three points is weak, and §13's conclusion rests on the
  *residual magnitude* (2.2–7.1× the between-device spread), which is robust
  to that, more than on the exact common-mode percentage, which is not.
- **Era A receiver identity is a filename prefix** (`NODE_CENSUS` I3), and
  `node_id` is a compiled-in build constant, not a board (I2). "Fixed
  receiver" is therefore an inference from the absence of a recorded move in
  every block, not from a recorded absence of one — failure mode **G**.
- **Era A has no `dropped` column**, so R1/R2 got one screen where R3/R4/R5
  got two.
- **Ordered pairs are not independent.** Each unordered pair contributes two
  rows sharing an \|elapsed\| and a session; the unordered figure is the
  primary one for exactly that reason, and both n values are printed.
- **`desk_20260821_125017` vs the 08-22 sessions** is treated as controlled
  because no move is recorded between them. Nothing establishes there wasn't
  one.
- **Nothing here is fused with `pc/occ/`.** No occupancy number was read,
  produced or cited. `docs/DIRECTION.md` is not cited as capability
  anywhere.
- **This does not revise either headline accuracy figure.** 99.7 %/7,497 and
  95.7 %/14,234 are pooled-session, chronological-split numbers on a
  different corpus and a different split; this pass measures a quantity they
  do not measure and is not a correction to them.

## 20. What would settle it

1. **A capture designed as a re-enrollment trial**: the same devices, the
   same receiver, unmoved, sampled at 1 h / 6 h / 24 h / 7 d, with the
   geometry and antenna bearing written into the `label` column — which
   `docs/COLOCATED_0823.md` §8 item 1 already asks for and which is still
   empty on every row of every file.
2. **Ambient devices need a shorter window or a longer dwell** before the
   deployment framing is testable at all. At 64 frames and 1–3 fps the
   corpus cannot form an ambient class. Either is a design decision, not an
   analysis one.
3. **§12 is the thing to chase, not the session boundary.** The wander is
   sub-session and per-device. `docs/THERMAL_EVIDENCE.md` §8 item 1
   (temperature at *both* ends, per frame) remains the prerequisite, and
   §13 here adds a reason: the movement is not shared across devices at one
   receiver either, so a single environmental regressor may not explain it.

---

## Files added or written by this investigation

- `pc/exp_identity_stability.py` — the one script; source of every number above
- `docs/IDENTITY_STABILITY.md` — this file

`pc/rff/dsp.py`, `pc/rff/discriminator.py`, `pc/rff/reference.py`,
`pc/rff_offline.py` were **read and used unchanged**. Nothing under
`data/raw/`, `firmware/`, `pc/occ/` or `site/` was touched. All scratch
state went to `$IDST_CACHE` outside the repo tree. Nothing was staged,
committed or pushed.
