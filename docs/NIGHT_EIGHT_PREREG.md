# NIGHT EIGHT PREREG — freezing the fingerprint half-life

> **STAGE 1. Written 2026-09-04, before the capture it scores exists.**
> Nothing above the Stage 2 banner in §9 may be edited once the capture starts.
> Corrections go below it, dated, with the original left visible. If a
> threshold in §6 is not met, §9 reports that it was not met. Thresholds are
> not relaxed to manufacture a result.
>
> Read-only on `data/raw/`. No git command will be run.

**This document is written so that tomorrow requires no judgement.** Point at
the capture stamp, run §8's single command, and §9 fills itself in against
§6's frozen table. Everything that could be argued about is argued about here,
today, before the data exists.

---

## 1. What is being replicated

`docs/FINGERPRINT_HALFLIFE.md` (2026-09-04, exploratory, **not**
pre-registered) measured how long a clock fingerprint stays usable. Three
findings, all from the seven nights already on disk:

1. **Drift saturates.** Within one continuous power-on, |ΔSFO| climbs from
   0.06σ at five minutes to ~1.0σ at 6–9 hours **and then stops** — it does not
   keep growing out to 21 h. A beacon wanders about as far as the gap between
   two different beacons, and no further.
2. **Identification has a half-life near one hour.** Enrol on one 300 s block:
   97.5% median accuracy at enrolment, 69.3% an hour later, 53.6% at five
   hours, against 33.3% chance.
3. **The failure is refusal, not confusion — but only when the beacons are
   actually apart.** See §2; this is the finding that changed shape once it was
   looked at per-cell, and it is the most important thing this night tests.

None of it was pre-registered. **This document freezes it.**

## 2. The correction that shapes this pre-registration

`FINGERPRINT_HALFLIFE.md` §6 reports median wrong-identity of 1.2–3.9% across
six capture-receivers and concludes the system "does not become wrong, it
becomes silent."

**The median hid a bimodal distribution.** Per cell:

| night | rx | population spread at enrolment | wrong-identity, +1 h → +5 h | precision |
|---:|---|---:|---|---:|
| 4 | d0wd | 24.5σ | 0.0 / 0.0 / 0.0 / 0.0 / 0.0% | 100% |
| 4 | s3 | 5.0σ | 0.0 / 0.0 / 0.0 / 0.0 / 0.1% | 99.9–100% |
| 7 | d0wd | 13.8σ | 3.9 / 3.7 / 7.8 / 6.2 / 2.2% | 90.6–98.9% |
| 7 | s3 | 6.4σ | 0.6 / 0.0 / 0.0 / 0.0 / 0.0% | 98.7–100% |
| **5** | **d0wd** | **2.9σ** | **40.8 / 38.6 / 31.0 / 30.9 / 37.4%** | **57–67%** |
| **5** | **s3** | **1.7σ** | **31.5 / 35.2 / 35.0 / 34.2 / 38.3%** | **55–66%** |

**Four of six cells are at or near zero wrong. Both night-5 cells are at
30–40%.** Reporting the median as though it described the population was a
mistake, and it is corrected here rather than quietly.

**And the split is not random — it is exactly the collapse night.**
`SECOND_WINDOW_PREREG.md` Q4 independently identified night 5 as the
minimum-spread night on both receivers, twice, on disjoint windows, with B2–B3
at 0.09σ. **When two devices genuinely share a fingerprint, the classifier
confuses them. When they do not, it refuses rather than guesses.**

Every cell with spread ≥ 5.0σ has wrong-identity ≤ 7.8%. Both cells below 3.0σ
are above 30%. **On this data a 3.0σ threshold separates the two regimes
perfectly**, which is what R3 below is built on and what night eight tests.

## 3. What the capture must be

**Change nothing.** This is a replication. No variable is deliberately varied,
and any temptation to "also test X" is refused — see §7.

| item | requirement |
|---|---|
| beacons | all three at **POS4**, same surface, ~4 ft apart, arrangement unchanged from nights 1–7 |
| power | **batteries charged before the run**, as before nights 4–7. B2 `28:05` stays on mains, as it has been since the bench was labelled on 2026-08-31 |
| receivers | `s3` and `d0wd` in their usual wall position, **untouched** |
| fan | **on**, for the whole capture — held constant across the series since night 2 |
| duration | **≥ 19,800 s (5.5 h) with all three beacons live.** B3 has died at 19,300–21,520 s on every night it was observed, so this is at the edge. Longer is better; let the receivers run as long as they will |
| occupancy | operator out of the room from T0 onward |

**On T0, and a correction to how this document first framed it.**

This section originally opened by asking the operator to log a label because
nights 3–7 had none, *"which forced `T0 = 0, declared` every time"*, and stated
that an absent label would be recorded as a deviation.

> **OPERATOR STATEMENT, 2026-09-05, before this capture exists.** Asked why
> nights 3–7 carried no label: *"the other nights had none because i started and
> went straight to bed."*
>
> **That changes what `T0 = 0` means on those nights, and it is an upgrade.**
> `SEVEN_NIGHT_PREREG.md` records T0 = 0 for nights 3–7 as **declared** — a
> choice made because §9's normal source did not exist. It is now
> **operator-attested**: the value was right, and the missing label reflected the
> operator leaving immediately, not a measurement that was never taken. Night 1
> is the identical behaviour *with* a label attached — §10.1, *"label set, then
> straight to bed. T0 = 0"* — which is why the two agree.
>
> **No figure changes anywhere.** T0 = 0 was already the value used on all five
> nights. What changes is its provenance, from *declared* to *attested*.
> `SEVEN_NIGHT_PREREG.md` §10.3–§10.7 should carry a note to that effect.
>
> **Dated because the statement was made after those nights were scored.** It is
> not contemporaneous and must never be quoted as though it were. It supplies
> provenance for a value already in use — it moves no threshold, no window and no
> verdict — so §7 temptation 2 does not apply.

**Consequence for night eight: the label is optional.** If the operator starts
the capture and leaves immediately, **`T0 = 0` is correct and attested** and
`--t0 0` is the right invocation. A label is still worth adding if it costs
nothing, because it timestamps the departure independently rather than resting
on recollection. **Its absence is no longer a deviation.**

## 4. Sample grid — fixed now

Six enrolment/test blocks, each **300 s measured with a 500 s lead-in**, at:

| block | offset from T0 | role |
|---|---:|---|
| E | **T0 + 600 s** | **enrolment** |
| +1 | T0 + 4,200 s | test |
| +2 | T0 + 7,800 s | test |
| +3 | T0 + 11,400 s | test |
| +4 | T0 + 15,000 s | test — **last block in the scored core** |
| +5 | T0 + 18,600 s | test — reported, and scored only if all three beacons are live through T0 + 18,900 s |

**Scored core is E through +4**, which needs 15,300 s (4.25 h) of all three
beacons. **+5 is a bonus tier** because it needs 18,900 s and the battery
constant makes that uncertain. This split is fixed now precisely so that a
normal battery night still scores the pre-registration.

For §5's drift curve only, sampling continues every 1,800 s for as long as the
capture runs, on whatever beacons survive.

The 500 s lead-in is the method validated in `SEVEN_NIGHT_REREAD.md` §9A, which
reproduced `SEVEN_NIGHT_PREREG.md` §10's SFO table on 40 of 40 cells.

## 5. Yardsticks — fixed now, not chosen later

- `BETWEEN_UNIT_SD = 0.00237 rad/sc` (`pc/exp_ambient_separation.py:79`).
  **Every σ in R3, R4 and R5 is in these units.**
- **Population spread** of a receiver on this night = (max − min) of the three
  beacons' median SFO **in the enrolment block E**, in `BETWEEN_UNIT_SD`. It is
  computed from block E alone, before any test block is classified, and written
  into §9 before R3 is scored.
- **Chance is 33.3%** — three sources. No accuracy figure below may be quoted
  without it (`CLAUDE.md`).
- **Precision** = correct ÷ (correct + wrong-identity). Refusals are excluded
  from the denominator; that is what makes it precision rather than accuracy.
- **Wrong-identity rate** and **refusal rate** are both fractions of all scored
  windows, so accuracy + wrong + refusal = 100% within a cell.

## 6. Predictions, with thresholds frozen now

Each threshold's source is named. All are per receiver, so each prediction is
tested twice, independently.

### R1 — enrolment works

**Both receivers score ≥ 90% accuracy in the enrolment block** (60/40
chronological split within E, exactly as `rff_offline` does it).

*Basis: 6 of 6 cells were 91.8–100%. Bar is set below the observed minimum.*

### R2 — it decays

**On both receivers, accuracy at +4 h is at least 15 points below the enrolment
block's accuracy.**

*Basis: observed drops were 17, 23, 37, 49, 66 and 71 points. Bar is below the
observed minimum.*

### R3 — refusal, not confusion — conditional on separability

**This is the load-bearing prediction and it is stated as a conditional so it
can fail either way.**

**For each receiver whose population spread in block E is ≥ 3.0σ:**

- **(a) wrong-identity ≤ 10% at every scored lag**, and
- **(b) refusal rate exceeds wrong-identity rate at every lag from +2 h on**,
  and
- **(c) precision ≥ 85% at every scored lag.**

**For any receiver whose spread is < 3.0σ**, R3 makes **no prediction** and the
cell is recorded as a collapse cell with its figures reported.

*Basis: every cell observed with spread ≥ 5.0σ had wrong-identity ≤ 7.8% and
precision ≥ 90.6%; both cells below 3.0σ had wrong-identity above 30% and
precision below 67%. The 3.0σ line is the repo's own reliably-separable
threshold (`pc/rff_offline.py:353`) and it is not moved.*

**If both receivers come in below 3.0σ, R3 is UNTESTABLE on this night** — not
failed, not held — and that is reported in those words.

### R4 — drift saturates

**(a) Median |ΔSFO| in the 4–6 h lag bin is at least 2.5× the value in the
0.5–1 h bin.** *(Observed 0.83 against 0.18 = 4.6×.)*

**(b) If any beacon survives past 6 h**, the median in the 6–9 h bin is **no
more than 1.5×** the 4–6 h value. *(Observed 1.09 against 0.83 = 1.3×.)* If
nothing survives to 6 h, (b) is **NOT RUNNABLE** and (a) alone scores R4.

### R5 — frozen at short lag

**Median |ΔSFO| in the 0.5–1 h bin is below 0.35σ, on both receivers.**

*Basis: observed 0.18σ overall, 0.15σ (s3) and 0.25σ (d0wd); per beacon
0.15 / 0.20 / 0.24σ.*

### Verdict table — frozen

| outcome | condition |
|---|---|
| **R1 HELD** | ≥ 90% enrolment accuracy on **both** receivers |
| **R2 HELD** | ≥ 15-point drop by +4 h on **both** receivers |
| **R3 HELD** | (a), (b) and (c) all met on **every** receiver with spread ≥ 3.0σ |
| **R3 UNTESTABLE** | both receivers below 3.0σ |
| **R4 HELD** | (a) met, and (b) met or NOT RUNNABLE |
| **R5 HELD** | < 0.35σ on **both** receivers |

Any prediction meeting neither its condition nor its opposite is reported as
**MIXED**, in those words, and is not resolved by choosing. A prediction whose
threshold becomes arithmetically unreachable is reported as **failed and
unreachable**.

## 7. Temptations, recorded in advance

1. **Varying something "while we're at it."** Swapping the power assignment,
   moving a beacon, changing the fan. Every one of those is a good experiment
   and every one of them destroys this one. **Night eight changes nothing.**
2. **Moving the 3.0σ line in R3** after seeing a receiver land at 2.8σ or 3.2σ.
   The line is the repo's own and it stays.
3. **Reporting the median of the six-cell wrong-identity distribution.** §2 is
   what that mistake looks like. Report per cell, always.
4. **Excluding a beacon or a lag for a reason discovered after scoring.**
   Exclusions require a stated physical cause — a beacon dead, a receiver
   rebooted — decided before the block is scored, per `SEVEN_NIGHT_PREREG.md`
   §7.
5. **Reading R3 HELD as "the system is never wrong."** It would mean *this
   night's beacons were separable and the classifier declined rather than
   guessed.* On a collapse night it confuses, and §2 already shows that.
6. **Letting R1 or R5 rescue R3.** They are independent.
7. **Quoting any accuracy without the class count.** Three sources, 33.3%.
8. **Treating night eight as an independent replication of the room
   conclusion.** Same apartment, same bench, same hardware. It replicates a
   *timescale*, nothing else.

## 8. Tomorrow, in one command

```
python pc/exp_night_eight.py --stamp <YYYYMMDD_HHMMSS> [--t0 <SECONDS>]
```

It slices, runs the shipped pipeline on each block, computes every figure in
§6, prints the frozen verdict table filled in, and writes
`data/cache/night8/`. `--t0` defaults to 0 and should be given the value read
from the operator label if one exists.

Nothing else needs to be decided. **If the script and this document disagree,
this document wins and the script is wrong.**

It is resumable — every 300 s block is cached in `data/cache/night8/`, so an
interrupted run costs nothing already computed. It writes no scratch into the
repo. It never runs git.

### The script was dry-run before this document was frozen

`exp_night_eight.py` was executed end to end against **night 7
(`20260904_010024`)** on 2026-09-04, purely to prove it runs and that its
branches fire. That run is a **software test, not a result**, and its output is
not a Stage 2 figure for anything. It is recorded here because the script
existing and working before the capture is part of what makes tomorrow
mechanical, and because its cache files sit in `data/cache/night8/` under night
7's stamp.

Two things the dry run established, both worth knowing in advance:

- **The collapse-cell branch fires in practice.** Night 7's d0wd enrolment
  block reads a population spread of **2.8σ**, so R3 correctly declined to
  predict on it while still applying to s3. Note this is a different figure
  from the 13.8σ `SECOND_WINDOW_PREREG.md` Q4 reports for night 7 d0wd — that
  is measured on the 30-minute held-out window, this on the 300 s enrolment
  block at T0+600. **Spread is not constant within a night**, and §5 fixes
  block E as the one that decides R3. Expect R3 to be untestable on a receiver
  reasonably often.
- **An empty lag bin now reports NOT RUNNABLE, not FAILED.** The first dry run
  used `--drift-step 5400`, which leaves the 0.5–1 h bin empty, and the script
  called R4 and R5 failed. That is `ERROR_LOG` **mode C** — a capability
  failure read as a negative result — and it was fixed before freezing. **Use
  the default `--drift-step 1800`;** anything larger cannot fill the bin R5
  needs.

## 8.1 Deviations — decided now, so they are not decided under pressure

| if this happens | do this |
|---|---|
| no operator label | `--t0 0`, recorded as **operator-attested** per §3 — start-and-leave is the actual protocol, not a gap. Not a deviation |
| a beacon dies before T0 + 15,300 s | score the blocks it survives; the lost blocks are **NOT RUNNABLE**, not failures. R1/R2 need E and +4 on both receivers, so a death before +4 makes them **unscoreable on that receiver** |
| B1 `a4:f0` dies early, as on night 3 | two-class night. **Chance becomes 50%, not 33.3%**, and every accuracy figure must be quoted against 50%. R3's spread is then a single pair |
| a receiver drops out | score the other one and report the night as single-receiver; every prediction is per receiver, so this degrades rather than voids it |
| capture is shorter than T0 + 15,300 s | R1 and R2 unscoreable; R5 still scoreable if the capture reaches ~1 h; report what ran |
| something was moved or changed | **the night is excluded**, per `SEVEN_NIGHT_PREREG.md` §7 temptation 2, with the physical cause stated. Recorded, not silently dropped |
| the numbers look wrong | they are reported as they are. §6's table is frozen |

## 9. Stage 2 — results

> **Nothing below this line existed when §1–§8 were written.**

Capture `20260905_025053`, scored 2026-09-05 with
`python pc/exp_night_eight.py --stamp 20260905_025053 --t0 0`.

### Pre-scoring block, fixed before any figure was computed

**Capture ran 22,311 s (6 h 12 m)** — the longest all-three-beacon stretch of
the series.

| beacon | frames (d0wd) | first | last |
|---|---:|---:|---:|
| B2 `28:05` | 972,830 | 0.0 s | **22,311.3 s** (full) |
| B1 `a4:f0` | 1,094,934 | 0.0 s | **22,311.3 s** (full) |
| B3 `f4:2d` | 1,086,367 | 17.6 s | **21,668.0 s** |

B3's death at 21,668 s is the ninth observation of that constant and sits just
above the 19,300–21,520 s band, consistent with charged cells. **All six blocks
clear**, the last closing at 18,900 s — **the +5 h bonus tier is scoreable for
the first time.**

**Operator labels, four of them:** *"woke up about 10 min ago"* (20,695 s),
*"bathroom"* (21,588 s), *"back"* (21,859 s), *"battery died"* (22,303 s).
**Nothing at the start**, which is the start-and-leave protocol, so **T0 = 0,
operator-attested** per §3. *(The script's header prints "declared, no label";
that string predates §3's correction and is cosmetic.)*

**This is the best-documented night of the series.** The first label puts the
operator awake at roughly 20,100 s and every scored block closes at 18,900 s, so
**the entire scored window is provably unoccupied from the operator's own log**
rather than from recollection — which nights 3–7 could not say.

### Verdicts — applied as frozen

| | verdict |
|---|---|
| **R1** enrolment ≥ 90% both receivers | **FAILED** — s3 81.7%, d0wd 99.6% |
| **R2** ≥ 15-point drop by +4 h both | **FAILED** — s3 **−4** pt (it rose), d0wd 51 pt |
| **R3** wrong ≤ 10%, refuse > wrong, precision ≥ 85% | **FAILED** — clean on d0wd, violated on s3 at +1, +2, +3, +5 |
| **R4** 4–6 h ≥ 2.5× 0.5–1 h; 6–9 h ≤ 1.5× 4–6 h | **FAILED** — (a) 2.74× passes, (b) **4.09×** fails |
| **R5** 0.5–1 h wander < 0.35σ both | **HELD** — s3 0.26, d0wd 0.31 |

**Four of five failed. That is the result and it is reported as it landed.**

### The blocks

**s3** — enrolment SFO: B1 +0.0222, B2 +0.0102, B3 +0.0110. Population spread
5.0σ, so R3 applied.

| block | n | acc | wrong | refuse | precision |
|---|---:|---:|---:|---:|---:|
| E | 383 | 81.7% | **16.2%** | 2.1% | 83.5% |
| +1 | 969 | 70.4% | **28.6%** | 1.0% | 71.1% |
| +2 | 959 | 80.1% | **18.8%** | 1.1% | 81.0% |
| +3 | 912 | 86.7% | 10.9% | 2.4% | 88.9% |
| +4 | 928 | 85.9% | 3.8% | 10.3% | 95.8% |
| +5 | 943 | 64.4% | 12.5% | 23.1% | 83.7% |

**d0wd** — enrolment SFO: B1 +0.0059, B2 +0.0093, B3 +0.0363. Population spread
12.8σ.

| block | n | acc | wrong | refuse | precision |
|---|---:|---:|---:|---:|---:|
| E | 260 | 99.6% | 0.4% | 0.0% | 99.6% |
| +1 | 651 | 58.8% | 2.8% | 38.4% | 95.5% |
| +2 | 651 | 59.8% | 2.6% | 37.6% | 95.8% |
| +3 | 647 | 57.8% | **0.2%** | 42.0% | **99.7%** |
| +4 | 648 | 48.8% | 1.1% | 50.2% | 97.8% |
| +5 | 653 | 61.4% | 0.8% | 37.8% | 98.8% |

Drift: 0.5–1 h **0.27σ** (n=70), 4–6 h **0.74σ** (n=76), 6–9 h **3.02σ** (n=4).

## 9.1 Why R3 failed, and it is a defect in the prediction rather than in the bench

**R3 gated on population spread — (max − min) across the three beacons. That is
the wrong statistic, and this night is what proves it.**

Minimum *pairwise* separation in the enrolment block, in `BETWEEN_UNIT_SD`:

| receiver | B1–B2 | B2–B3 | B1–B3 | **minimum** | worst wrong-identity |
|---|---:|---:|---:|---:|---:|
| s3 | 5.06 | **0.34** | 4.73 | **0.34σ** | **28.6%** |
| d0wd | 1.43 | 11.39 | 12.83 | **1.43σ** | 2.8% |

**s3's population spread is a healthy 5.0σ — carried entirely by B1 sitting far
away — while B2 and B3 are 0.34σ apart, which is collapsed.** The classifier
confuses the two of them constantly, exactly as §2 said it would when devices
genuinely share a signature. R3 waved that cell through because the *spread*
looked fine.

Against the earlier evidence, minimum pair predicts wrong-identity and
population spread does not:

| night / receiver | min pair | wrong-identity |
|---|---:|---:|
| night 5 d0wd | 0.09σ | 30–41% |
| night 5 s3 | 0.45σ | 31–38% |
| **night 8 s3** | **0.34σ** | **10.9–28.6%** |
| **night 8 d0wd** | **1.43σ** | **0.2–2.8%** |
| nights 4, 7 | (wide) | 0.0–7.8% |

**The refusal-not-confusion behaviour is not refuted — it is confirmed and its
condition is corrected.** On d0wd, where the closest pair is 1.43σ, the failure
mode is textbook: wrong-identity **0.2–2.8%**, precision **95.5–99.7%**, and
refusals climbing 38% → 50%. On s3, where two beacons are 0.34σ apart, it
inverts. **The gate should have been minimum pairwise separation with a bar
near 1.0σ, not population spread at 3.0σ.**

That correction is written here rather than applied — **R3 is FAILED as frozen**
and is not being rescored under a better statistic. §7 temptation 2 exists for
exactly this.

## 9.2 What the other failures say

**R1 and R2 failed for the same reason, and it is s3's enrolment block.** At
81.7% accuracy and 16.2% wrong-identity, s3's baseline was already broken at
t = 600 s. **A decay measurement needs a clean starting point**, and R2's
"15-point drop" is meaningless from a baseline that was never up — which is why
s3 *rose* four points instead of falling. d0wd, enrolling at 99.6%, dropped 51
points exactly as predicted.

**R4(b) failed on n = 4.** The 6–9 h bin holds four pairs, from a 6.2-hour
capture that barely reaches the bin at all. **3.02σ against a 0.74σ four-to-six
hour figure is not evidence of anything** at that sample size; the bin should
not have been scored on a capture this length and §4 should have said so.
R4(a) passed at 2.74×.

**R5 held on both receivers** — 0.26σ and 0.31σ against a 0.35σ bar. **The
fingerprint is still frozen at the one-hour scale**, which is the finding the
whole series rests on, and it is the one prediction that survived.

## 9.3 A third co-location collapse

**s3's B2–B3 at 0.34σ is the third recorded instance** of the collapse this
project was built to replicate — after `COLOCATED_TX_0828`'s 0.2σ and night 5's
0.09σ on the held-out window. Three occurrences on eight nights, on both
receivers at different times, never both receivers on the same night.

**It is intermittent, it is real, and it is now observed often enough that
"n = 1 coincidence" is dead.** What still has no explanation is what puts the
bench into that state.

## 10. What night eight cannot do

- **It is one night.** R3's conditional is built on a 6-cell split with 2 cells
  on one side. One more night gives at most 2 more cells.
- **It is the same apartment, the same three ESP32s, the same two receivers.**
  Nothing here generalises to other hardware, other rooms, or more than three
  classes.
- **It cannot test the saturation plateau past ~6 h** unless the capture runs
  much longer than a night, because B1 and B3 die at 19,300–21,520 s. Only the
  2026-09-01 twenty-hour capture reaches further, and only on B2.
- **It does not revisit P1, P2, P3, D1–D4 or Q1–Q6.** Those verdicts are
  closed.
