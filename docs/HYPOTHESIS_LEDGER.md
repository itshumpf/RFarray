# HYPOTHESIS_LEDGER — what was tested, what died, and what it cost

**2026-08-28.** An inventory of every candidate explanation in `docs/` that was
stated, tested against data, and rejected on evidence.

Read-only pass over 46 documents. No git command run.

---

## 0. What this file is, and what it is not

**The verdict quotes are measurements.** Every one is copied verbatim from the
file and line cited beside it. Eight were re-verified by hand against the
source after the inventory was compiled — `KAPPA_SLOPE_FUSION.md:155`,
`IDENTITY_STABILITY.md:362`, `UL_BIT_GROUND_TRUTH.md:213`,
`REFERENCE_CHOICE.md:51`, `BLIND_CLUSTERING.md:472`, `IQ_IMBALANCE.md:955`,
`SEPARATION_SCALING.md:61`, `GATE_CALIBRATION.md:641` — and all eight matched.
The rest have not been re-verified. **Verify before quoting** (failure mode A).

**The §2 / §3 split is a judgement, not a measurement.** The documents record
verdicts; they do not record whether a verdict cost the project something. The
classification below was made by reading each entry and asking *was this a
working result or a live hope when the test began?* Reasonable people can move
items across that line. It is stated as an opinion because it is one.

**Counting convention.** 35 rejections at the level of *independent tests*,
collapsing to **29 distinct ideas** once six families of repeated kill are
merged (§5). Expanded fully — counting `S3_SFO_STEPS.md` §9's five candidates
and `OLED_AND_MARGINAL_CELL.md`'s seven covariates individually — it is 43.
**Quote 29 or 35 with the convention attached, or quote neither.**

---

## 1. The count

| | tests | distinct ideas |
|---|---:|---:|
| **Rejected — own positive result** (§2) | 18 | **13** |
| **Rejected — alternative explanation or bug cause** (§3) | 17 | **16** |
| **Total destroyed** | **35** | **29** |
| Mixed / unresolved, recorded as such (§4) | — | **16** |

**Fifteen of the 35 carry a threshold or decision rule frozen before the run.**
`GATE_CALIBRATION.md` §2 was frozen at 2026-08-23 19:30 UTC before any sweep.

---

## 2. Rejections that destroyed a positive result

Each of these was working, or was a live hope, at the moment the test started.

### 2.1 Fusing `κ` with the SFO slope carries information neither carries alone
> **FAIL on both arms. The SFO slope adds nothing to `κ` that a random number
> of the same variance would not also add. The fusion branch closes.**

`KAPPA_SLOPE_FUSION.md:155`. **Pre-registered rule and a variance-matched
control, both frozen before results.** The apparent gain was **+26 pp, winning
12 of 12 comparisons, CI excluding zero.** Substituting a random axis of
identical variance reproduced it: F3 +0.00 pp, CI [−1.80, +1.71].

**The single strongest item in this ledger.** The control existed only because
it was built to make the result fail, and it did.

### 2.2 The SFO slope carries transmitter identity
Killed three ways, from three directions. One idea, three independent attacks.

> **No. A device's SFO signature does not survive from one session to the next
> on a fixed receiver — and the reason is worse than a session boundary: it
> does not reliably survive from one hour to the next *inside* a single
> session either.**

`IDENTITY_STABILITY.md:362`. Pre-registered FATAL bar at `:260`, scored FATAL
on three blocks.

> | **C3** comparator — same test on the SFO slope | \|Δslope\| 0.000064,
> `S_slope` 0.000019, **ratio 3.40** | **slope FAILS** its own > 3.0 bar |

`UL_BIT_GROUND_TRUTH.md:213`. Against definitional ground truth — one radio's
two interfaces, differing by the U/L bit — **the slope resolves them as
different devices.** Four controls (C1 positive, C2 negative, C3 comparator,
C4 RSSI confound).

Plus §2.1 above.

### 2.3 A shared common-mode term can be subtracted away
Four documents, four different quantities, one idea.

> **No reference condition meaningfully reduces the receiver term. The one
> that appears to is a degeneracy, not common-mode rejection.**

`REFERENCE_CHOICE.md:51`. The correction *raises* the Allan-deviation floor in
**six of six** non-degenerate S3 cells — what subtracting an uncorrelated
series of comparable magnitude gives.

Also `IDENTITY_STABILITY.md:743` (NOT COMPENSABLE, every 3-device block),
`KAPPA_CROSS_SESSION.md:320` (H1 fails its 0.25 bar), and
`COLOCATED_TX_0828.md:152` — *"The correction is the entire source of the
disagreement."*

### 2.4 `κ` is transmitter-dominated with a removable additive receiver term
> **VERDICT: RECEIVER-DOMINATED, and the additive model does not hold.**

`IQ_IMBALANCE.md:955`. Pre-registered thresholds `frac_rx < 0.5` and
`R_disp < 2`; **measured 5.73 and 826.6.**

### 2.5 The receiver-pair disagreement is a fixed constant
> **H3 is FALSIFIED**, by four orders of magnitude on the pre-registered
> threshold

`RECEIVER_TERM_PREREG.md:703`. Bar `R_disp < 2`, measured **10,830**. Also
`DUAL_RX_2026-08-21.md:428` and `POSITIVE_CONTROL_0822.md:590`. Had it been
constant it would have been correctable.

### 2.6 Longer averaging windows buy separation
> **Longer windows buy almost nothing.**

`SEPARATION_SCALING.md:61`. **256× more averaging** moves minimum pairwise
separation 0.69σ → 0.83σ. The time-shuffle control reproduces the ideal factor
of 16 exactly on the same frames, so the plateau is temporal correlation and
not a broken estimator.

### 2.7 Tighter admission gates rescue the unseparable pair
> **Tighter gates do not rescue the pair that matters.**

`SEPARATION_SCALING.md:69`. **175 configurations swept; 174 hold the pair at
0.66σ–1.18σ.**

### 2.8 Loosening the gates recovers usable ambient sources
> **No, and the reason is not conservatism about changing a default.**

`GATE_CALIBRATION.md:641`. **Every one of the 13 fails the pre-registered gain
rule**, slope dispersion 9.6σ to 64.5σ. A beacon of known position moves 3.03σ
*in the pre-registered direction that rejects the setting.*

### 2.9 Blind clustering can re-link MAC-randomising devices
> **no multi-MAC cluster survived the pre-registered calibration on both
> receivers**

`BLIND_CLUSTERING.md:472`. Below the permutation null in **all eight** cut ×
receiver × window combinations — what a one-dimensional feature colliding by
pigeonhole looks like.

### 2.10 Relaxing the 20-frame floor is what would reveal ambient devices
> **Relaxing the 20-frame floor bought essentially nothing** — **+0**
> additional clusterable sources on the d0wd and **+1** on the S3

`BLIND_CLUSTERING.md:469`. Recorded because it was the operator's own
suspicion, tested and dropped.

### 2.11 CFO is a usable discriminator
`ROOM_OR_RADIO.md:242`, with `DUAL_RX_2026-08-21.md:433` and
`AMBIENT_SEPARATION.md:62`. Between-device medians **+0.3, −0.0, −0.0 Hz**
against within-device IQRs of **7.3, 7.3, 5.5 Hz** — measured under the most
favourable conditions the project could construct.

### 2.12 A constant offset ports a fingerprint library between receivers
> So: **the constant-offset hypothesis is refuted; the alternative is not
> established.**

`DUAL_RX_2026-08-21.md:428`. Three per-beacon differences separated by 3.9–7.8×
the between-unit spread, disjoint CIs, B3 opposite in sign.

### 2.13 Ambient hardware separates better than the beacons
The hoped-for reading: the repo's own figures are a worst case.
> **No. On the primary node, at a defensible gate, the ambient population is
> not meaningfully more separable than the three beacons, and on the reading
> that survives the most checks it is less so.**

`AMBIENT_SEPARATION.md:77`. Includes an n-artefact control.

### 2.14 The occupancy detector generalises to a short absence
> **a short absence from an otherwise-occupied room does not reproduce the
> 08:55 signature, and on the 08:55 detector it is not detectable at all.**

`OCCUPANCY_TEST_0822.md:53`. The detector was run **unchanged** from
`POSITIVE_CONTROL_0822.md` §2.1 — 23/24 series flagging before, 9/24 now.

### 2.15 Discarding the warm-up region recovers stability
> **Discarding warm-up does not reduce the wander.** It increases it by +1% to
> +20% and never separates from baseline.

`THERMAL_EVIDENCE.md:732`. Matched head/tail trims, 2000-session bootstrap;
every head-trim CI includes baseline.

*(2.2, 2.3, 2.5 each merge multiple tests — see §5. Thirteen distinct ideas
across eighteen tests.)*

---

## 3. Rejections that eliminated a cause, not a result

Ordinary and necessary; listed briefly. These do not carry the same weight and
should not be quoted as though they do.

| # | hypothesis | verdict | cite |
|---|---|---|---|
| 1 | Power-on warm-up transient drives the instability | ❌ not driving it | `THERMAL_EVIDENCE.md:726` |
| 2 | A real 1-hour outdoor→indoor step produces a detectable settle | no settle, six cells | `THERMAL_STEP.md:582` |
| 3 | All three beacons are clock twins from one lot (strong form) | **REFUTED** | `LOT_HYPOTHESIS.md:51` |
| 4 | `84:7b:57:cc:20:0e` is the twin reflashed | **No. Refuted, decisively.** | `TWIN_INVESTIGATION.md:269` |
| 5 | The clock twin caused the 99.7 → 95.7 drop | twin absent from both sets | `TWIN_INVESTIGATION.md:32` |
| 6 | Outdoor air temperature explains the drift | **Weather is not the mechanism.** | `WEATHER_COVARIATE.md:427` |
| 7 | Barometric pressure explains the drift | **explains nothing** — strong null | `WEATHER_COVARIATE.md:1118` |
| 8 | Unwrap defect caused by temporal pinning | **RULED OUT** — branch inert | `UNWRAP_DEFECT.md:355` |
| 9 | Unwrap defect triggered by low SNR | **It is not an SNR failure.** | `UNWRAP_DEFECT.md:397` |
| 10 | Cable length / mains-vs-battery counterpoise | **eliminated**, backwards from prediction | `ROTATION_PREREG.md:283` |
| 11 | B1's distinctness is a `reference.py` artifact | wrong; survives raw | `COLOCATED_TX_0828.md:98` |
| 12 | The S3 step is a periodic internal cycle | CV 1.311; eliminated | `OVERNIGHT_2026-08-22.md:79` |
| 13 | Seven covariates explain the marginal cell | none explains it | `OLED_AND_MARGINAL_CELL.md:70` |
| 14 | The OLED `display_task` delays frames by 23.5 ms | not close to it | `DISPLAY_LIVE_0822.md:48` |
| 15 | USB PHY workaround triggered t = 930 s | **Confirmed dead as a trigger.** | `S3_SFO_STEPS.md:425` |
| 16 | Five further t = 930 s candidates (reboot, calibration, channel, loss, desk-confined) | each named and killed | `S3_SFO_STEPS.md:437-442` |
| 17 | Transmitter boot state sets `κ` | **not set by transmitter boot state** | `LABELLED_EVENTS_0823.md:776` |

Two of these — **#10 and #11** — run the other way: eliminating them made a
finding *stronger*, not weaker.

Two verdict lines worth keeping for their own sake:
> A constant cannot explain a variable. — `OLED_AND_MARGINAL_CELL.md:683`
> Time of day is not it, and the hypothesis fails in the direction opposite to
> the one proposed. — `OLED_AND_MARGINAL_CELL.md:803`

---

## 4. Recorded as mixed or unresolved — 16

Not counted as destroyed. Listed because **a corpus with no unresolved
verdicts is a corpus that forced them.**

`KAPPA_CROSS_SESSION.md:384` (H2 FAIL must not be read as refutation —
underpowered, 66.7% bar inside both CIs) · `RIPPLE_TEST.md:580` (channel
hypothesis: null below the instrument's own detection floor) ·
`ROTATION_PREREG.md:342` (MIXED, both receivers) · `LOT_HYPOTHESIS.md:12`
(inconclusive on lot identity) · `RECEIVER_TERM_PREREG.md:727` (neither H1 nor
H2 supported, neither rejected) · `WEATHER_COVARIATE.md:1141` (humidity not
trustworthy at n = 15, **as pre-registered, whatever value it takes**) ·
`THERMAL_STEP.md:612` (κ neither shown thermally conditional nor robust) ·
`THERMAL_STEP.md:622` (reboot vs settle not separable, 12 of 18 cells) ·
`THERMAL_STEP.md:772` (CSMA contention — not a clean test) ·
`BLIND_CLUSTERING.md:455` (**the positive control did not pass**) ·
`S3_SFO_STEPS.md:443` (no ambient explanation found — *"weaker than
excluded"*) · `S3_SFO_STEPS.md:444` (room movement: not supported, not
excluded) · `OVERNIGHT_2026-08-22.md:93` (charge controller weakened, not
closed) · `OLED_AND_MARGINAL_CELL.md:952` (headless null carries no
information about a working panel) · `LABELLED_EVENTS_0823.md:1072`
(disagreement with `IQ_IMBALANCE.md` §15.1 unresolved) ·
`AMBIENT_SEPARATION.md:288` (19 and 13 MACs unresolved)

**`BLIND_CLUSTERING.md:455` is the one to point at.** The positive control
failed — scored MARGINAL in all four configurations, never within half of the
PASS threshold — and it was written down rather than quietly re-run.

---

## 5. Deduplication — do not double-count

| family | tests | cite once as |
|---|---|---|
| A shared common-mode term can be subtracted away | `REFERENCE_CHOICE.md:51`, `IDENTITY_STABILITY.md:743`, `KAPPA_CROSS_SESSION.md:320`, `COLOCATED_TX_0828.md:152` | §2.3 |
| The receiver-pair disagreement is constant | `RECEIVER_TERM_PREREG.md:703`, `DUAL_RX_2026-08-21.md:428`, `POSITIVE_CONTROL_0822.md:590` | §2.5 |
| The SFO slope carries transmitter identity | `IDENTITY_STABILITY.md:362`, `KAPPA_SLOPE_FUSION.md:155`, `UL_BIT_GROUND_TRUTH.md:213` | §2.2 |
| CFO is a usable discriminator | `ROOM_OR_RADIO.md:242`, `DUAL_RX_2026-08-21.md:433`, `AMBIENT_SEPARATION.md:62` | §2.11 |
| The unwrap defect's mechanism | `UNWRAP_DEFECT.md:355`, `:397` | §3 #8–9 |
| Thermal | **do not merge** — power-on transient, applied step, and outdoor temperature are three distinct sub-hypotheses | §3 #1, #2, #6 |

**Thermal-as-mechanism is not destroyed anywhere in this corpus.**
`LOT_HYPOTHESIS.md:580` rates it *"Moderate — plausible, not isolated."* Do not
claim it was ruled out.

**Scope flag.** `DISPLAY_LIVE_0822.md` (§3 #14) is the only capture in which a
panel actually ran. The OLED nulls in `OLED_AND_MARGINAL_CELL.md` are on
headless boards and are disclaimed there. Do not merge them.

---

## 6. Reproduce

```
cd docs
grep -inE '^\**(verdict|conclusion|result|outcome|answer|finding)\**[:*[:space:]]' *.md
```

Then read each hit in context. The grep is a pointer, not a source — several
verdicts in §2 sit under headings this pattern does not match, and several
matches are not verdicts.

---

# 7. ADDENDUM — 2026-09-05. Four pre-registrations since this file was written.

**§0–§6 above are dated 2026-08-28 and are left exactly as written.** Between
that date and 2026-09-05 the project ran four further pre-registered studies and
one full-corpus replay. **Nothing above is retracted; several items move.**

**The §1 count table is now stale and is not edited.** Use it as the
2026-08-28 figure. The additions below are counted separately and the §2/§3
classification of them is a judgement in exactly the way §0 says the original
was.

## 7.1 What was frozen, and what it returned

Sixteen predictions were written with thresholds before the data existed.
**Five held. Eleven failed. None was rescored after the fact.**

| study | prediction | verdict |
|---|---|---|
| `SEVEN_NIGHT_PREREG` | **P1** co-located B2–B3 < 1.0σ on ≥5 of 7 | **failed 7/7 → UNINTERPRETABLE** per §4's frozen cell |
| | **P2** reference correction ≥2× worse | **failed** every night it could run |
| | **P3** stationary night-to-night wander > 1.0σ | **HELD** |
| `SECOND_WINDOW_PREREG` | **Q1** signature frozen within a night | **HELD** — 38/40 cells < 1.0σ, median 0.07σ over 39 min |
| | **Q2** B2–B3 ≥ 3.0σ on ≥6 of 7, both rx | **failed** — 7/7 s3, 5/7 d0wd |
| | **Q3** blind identification survives | **HELD** — median 95.8%, min 61.8% |
| | **Q4** no collapse at the observed rate | **HELD** |
| | **Q5** same yield victims | **failed** — s3 degraded for the first time |
| `NIGHT_EIGHT_PREREG` | **R1** enrolment ≥ 90% both rx | **failed** — s3 81.7% |
| | **R2** ≥ 15-pt drop by +4 h both rx | **failed** — s3 rose |
| | **R3** wrong ≤10%, refuse > wrong, precision ≥85% | **failed** on s3 |
| | **R4** drift saturation | **failed** on (b), n = 4 |
| | **R5** 0.5–1 h wander < 0.35σ | **HELD** — 0.26 / 0.31 |
| `LINK_SIGNATURE_PREREGISTRATION` | **T1** held-out-night identification | **failed** — best 53.2 / 64.3% |
| | **T2** two-receiver fusion beats the better receiver | **failed** — 63.7%, 0.6 pt below s3 |
| | **T3** verification AUC ≥ 0.90, EER ≤ 15% | **failed** — best 0.700 / 30.9% |

**P3 is the one to understand.** It was written down *because it might
invalidate P1*, and it did. Without it, seven consecutive P1 failures would have
been reported as a refutation of the co-location result. **That is the single
clearest case in this project of a control earning its place.**

## 7.2 New rejections that destroyed a positive result — 5

Classified §2-style: each was working, or a live hope, when the test began.

**7.2.1 The SFO slope is a property of the transmitter.**
This is `2.2` finished. §2.2 established the signature does not survive a
session boundary or reliably an hour. The full-corpus replay establishes *why*:
the cross-receiver double difference `[(A−B) on s3] − [(A−B) on d0wd]` is
**6.79 SD at 10 s, 60 s and 300 s bins**, level correlation ≈ 0.00. A
transmitter-bound quantity cannot do that. **What is measured is the link —
transmitter, receiver and path as one object.**
`share/deep_dive/FULL_CORPUS_FINDINGS.md`. 69,510,186 frames, unwrap-free
estimator with an OLS cross-check agreeing to 0.02–0.06 SD.

**7.2.2 The 28 August co-location collapse reproduces.** P1, failed 7/7.
Scored UNINTERPRETABLE rather than refuted **only because P3 fired.** The
collapse is real and intermittent — three instances in eight nights (0.2σ on
28 Aug, 0.09σ night 5 held-out, 0.34σ night 8 s3) — with no mechanism found.

**7.2.3 Reference-beacon correction improves cross-receiver agreement.** P2,
failed on every runnable night. Night 4 gave the mechanism: correcting against a
degraded reference **exports its degradation** into the other beacons.

**7.2.4 A link state can serve as an authentication credential.** T1–T3, all
failed. Within a night the links are highly separable; across nights a template
averages **38.6–48.8%** with individual pairs ranging from near 0% to near 100%.
`LINK_SIGNATURE_FINDINGS.md`.

**7.2.5 Two receivers are better than one by concatenation.** T2. Fusion came in
**0.6 pt below the better single receiver** on channel features, 11.1 pt below on
slope. Naive concatenation adds unstable dimensions, not corroboration. **Does
not rule out a calibrated decision rule or challenge–response fusion.**

## 7.3 New rejections that eliminated a cause, not a result — 5

**7.3.1 The anomalies are an unwrap or RANSAC artifact.** Retired. An
unwrap-free circular-objective estimator and an all-bin OLS agree to
**0.02–0.06 SD** at minute scale across all six receiver-beacon cells.

**7.3.2 Ambient traffic inflated the pooled covariance P1 was scored in.**
Retired by measurement: across all fourteen night-receiver runs, **zero
non-beacon sources entered the pool.** A source needs ~576 accepted frames to
qualify and no corrupt-row ghost reaches it inside a scored window.
`SEVEN_NIGHT_REREAD.md` §3 correction and §9B.

**7.3.3 The CFO axis, never characterised, might carry the missing information.**
Retired. `BETWEEN_UNIT_SD_CFO = 0.053 Hz` against a median within-window IQR of
**5.97 Hz** — 112:1 noise to signal, where SFO's ratio is 0.39:1. CFO
contributes a **median −1.4%** to pairwise separations. It is carried through
every centroid and both χ² gates and does nothing. `SEVEN_NIGHT_REREAD.md` §9.

**7.3.4 `d0wd` is the sole locus of the anomalies** — i.e. the project is
downstream of the non-S3 CSI corruption warned about in
`github.com/nzqo/sensession` (Portner et al., arXiv:2605.26836).
**Retired.** Night 7's B1 is inflated on **both** receivers simultaneously —
IQR 0.02118 on d0wd and 0.00711 on s3, 19× and 8× their own medians. Night 7's
held-out window shows s3 at 77.1% yield; night 8's separability failure is on
s3. **A defect in one receiver's silicon cannot do that.** The corpus is
adjacent to that literature, not downstream of it.

**7.3.5 Battery life improved when the cells were charged.** Retired.
`SEVEN_NIGHT_REREAD.md` §1: night 4's B1 and B3 died at **21,300.2 s and
21,519.5 s** and returned at ~72,650 s when the operator swapped cells. The
"nothing died" claim was an artifact of a 12,225 s view of a 72,692 s file.
**Battery life is a constant, 19,300–21,520 s, not a variable the operator
improved.**

## 7.4 Moves within §4 — three resolved, five added

**Resolved out of §4:**

- **D2, "yield collapse and SFO disagreement are one phenomenon."** Still
  unresolved as scored, but `SEVEN_NIGHT_REREAD.md` §5 shows the check that
  dismissed it compared **two nights of the same class**. The victim/non-victim
  split across the series separates perfectly, 5.95×, no overlap. **Reopened
  rather than closed.**
- **The CFO question** — closed, §7.3.3.
- **Whether the unwrap defect drives the results** — closed, §7.3.1.

**Added to §4, unresolved:**

1. **What puts the bench into the collapse state.** Three occurrences, no
   mechanism, never both receivers on the same night.
2. **The effective sample size behind every accuracy figure.** Holdout windows
   are 64 consecutive frames from one continuous capture and are **not
   independent observations.** No autocorrelation length has ever been
   estimated. A block bootstrap over `data/cache/windows*/` would settle it.
3. **A 60–85 minute periodicity family.** `q = 0.090` after Benjamini-Hochberg
   over 45 series — below the 5% bar. Not a discovery. Untestable further
   because the recorder **decodes status telemetry and discards it**.
4. **Whether a link signature resists spoofing.** `summary.json` records
   `spoof_resistance_tested: false`. **There is no attacker in this corpus** —
   no cloned MAC, no displaced transmitter, no replay. *"A link signature is
   harder to spoof than a device signature"* is a prospective hypothesis and
   must never be quoted as a finding.
5. **The receiver swap.** Named as the most valuable next capture by
   `DUAL_RX_2026-08-21`, restated in `AMBIENT_SEPARATION` §9,
   `UL_BIT_GROUND_TRUTH` §8, `KAPPA_CROSS_SESSION` §10, and reached
   independently by the full-corpus deep dive. **Five documents. Never run.**

## 7.5 Two defects in the record, found by audit

Recorded here because a ledger that only tracks hypotheses and not its own
errors is half a ledger.

- **Two different σ, asserted to be one.** `SEVEN_NIGHT_PREREG` §2 states all σ
  are in `BETWEEN_UNIT_SD` units. P1's separations are 2-D (CFO, SFO)
  Mahalanobis distances under a *within-night pooled covariance* measured at
  **0.00049–0.00291 rad/sc**, a 5.9× swing against a fixed 0.00237. **P1's
  1.0σ bar was a different physical distance every night.**
- **R3 gated on the wrong statistic.** Population spread, not minimum pairwise
  separation. Night 8's s3 had a healthy 5.0σ spread carried entirely by B1
  sitting far away while **B2 and B3 sat 0.34σ apart**, and wrong-identity hit
  28.6%. The corrected gate is written in `NIGHT_EIGHT_PREREG` §9.1 and **not
  applied** — R3 stays failed as frozen.

## 7.6 Verification status of this addendum

Figures in §7 were read this session from `SEVEN_NIGHT_PREREG.md`,
`SEVEN_NIGHT_REREAD.md`, `SECOND_WINDOW_PREREG.md`, `NIGHT_EIGHT_PREREG.md`,
`FINGERPRINT_HALFLIFE.md`, `LINK_SIGNATURE_FINDINGS.md` and
`share/deep_dive/FULL_CORPUS_FINDINGS.md`, or computed directly from
`data/cache/`. **They have not been independently re-verified by a second pass.**
Verify before quoting — failure mode **A**, exactly as §0 says of the original.
