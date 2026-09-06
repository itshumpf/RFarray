# SECOND WINDOW PREREG — a held-out 30 minutes from the same seven nights

> **STAGE 1. Written 2026-09-04, before any SFO, κ, separation, yield or
> accuracy figure has been computed inside the window this document defines.**
> The only numbers read from the window so far are raw frame counts per MAC
> (§3), which is what fixes feasibility, exactly as §10.Na blocks did in
> `SEVEN_NIGHT_PREREG.md`. Nothing above the Stage 2 banner in §8 may be edited
> after the first figure is computed. Corrections go below it, dated, with the
> original left visible.
>
> Read-only on `data/raw/`. No git command run.

---

## 1. Why this exists

`SEVEN_NIGHT_PREREG.md` scored one 2,300 s window per night and returned
P1 UNINTERPRETABLE, P2 failed, P3 held. `SEVEN_NIGHT_REREAD.md` then audited
the record and found five things nobody had scored.

**Both of those documents read the series as an audit.** This one does not. It
takes a specific, optimistic reading of what the seven nights showed, states it
as predictions with numbers attached, and freezes them before looking.

### The reading being tested

P1 predicted that co-located beacons would become **indistinguishable**. It
failed seven times out of seven. Scored against the room hypothesis that is a
failure. Read as a capability claim it is the opposite:

> **Three ESP32s, four feet apart, on one surface, in one room, on a shared
> propagation path, watched by two receivers — and the system told them apart.
> Every night. Both receivers. 3.4σ to 60.6σ. Blind classification 87.2% to
> 97.7% on the three nights where it was reported.**

The obvious objection is that between-night drift manufactured those gaps.
**It cannot have.** `SEVEN_NIGHT_REREAD.md` §9I measured the SFO variogram:
within a night, SFO moves **0.06σ over five minutes and 0.15–0.21σ over
nineteen**. The separations above are same-window, same-instant, between
beacons. A signature that stationary cannot generate a 9σ gap between two
transmitters measured in the same seconds.

What P3 established, in this reading, is not that the instrument is broken. It
is that **the fingerprint is session-scoped**: frozen inside a night, moved by
0.79–5.85σ across one. That is a precise, useful characterisation, and it
independently explains `IDENTITY_STABILITY.md`'s cross-session collapse
(29.7% against 33.3% chance) with a measured timescale rather than a shrug.

**This document tests whether that reading survives contact with data it has
never seen.**

## 2. What would make this reading wrong

Stated before running, per the corpus's own convention:

- If separations in a fresh window come in **below 3.0σ** on most nights, the
  seven scored windows were not showing a stable capability and the reading is
  wrong.
- If SFO in the new window does **not** track the scored window's value, then
  the "frozen within a night" claim from §9I does not generalise past the
  34-minute lag it was measured over, and Q1 below carries that.
- If blind accuracy collapses toward chance (33.3%), the capability claim
  fails outright regardless of what the σ figures do.

**None of these outcomes would be rescued by reinterpretation here.** They
would be reported as written.

---

## 3. The window — fixed, and why this one

**T0 + 5,000 s through T0 + 6,800 s. 1,800 s = 30 minutes.**

`T0` is per-night and is **not re-derived**; it is taken from
`SEVEN_NIGHT_PREREG.md` §10 exactly as recorded there: T0 = 3,120 s on night 2,
T0 = 0 on all others. So the window is absolute **5,000–6,800 s** on nights
1 and 3–7, and **8,120–9,920 s** on night 2.

**It is disjoint from everything already scored.** The scored windows are
T0+2,400 through T0+4,700. This one opens 300 s after that closes and its
centre sits 2,350 s — 39 minutes — later.

**Constraints it had to satisfy, and the one that bound:**

| constraint | binding? |
|---|---|
| present on all seven nights | night 3's capture is shortest at 16,821 s — not binding here |
| outside every scored window | pushes the start past T0+4,700 |
| **B3 alive on night 3** | **binding** — B3's last frame on night 3 is 8,779 s (s3) / 9,059 s (d0wd), so the window must close before 8,779 s. It closes at 6,800 s, with 1,979 s of margin. |
| room unoccupied | satisfied — deeper into the night than the scored window on every night |

**Feasibility, measured 2026-09-04. Frame counts only; no estimator was run.**

| night | receiver | B2 `28:05` | B1 `a4:f0` | B3 `f4:2d` | total rows |
|---:|---|---:|---:|---:|---:|
| 1 | s3 | 157,536 | 120,960 | 152,996 | 431,768 |
| 1 | d0wd | 82,041 | 76,403 | 97,898 | 256,411 |
| 2 | s3 | 130,670 | 156,646 | 158,890 | 447,058 |
| 2 | d0wd | 88,276 | 79,947 | 86,803 | 255,636 |
| 3 | s3 | 157,893 | **0** | 162,315 | 320,796 |
| 3 | d0wd | 115,368 | **0** | 128,219 | 244,293 |
| 4 | s3 | 143,319 | 152,600 | 150,859 | 447,345 |
| 4 | d0wd | 89,686 | 62,438 | 96,568 | 249,146 |
| 5 | s3 | 142,018 | 134,282 | 122,516 | 398,943 |
| 5 | d0wd | 78,165 | 85,333 | 86,851 | 250,441 |
| 6 | s3 | 154,948 | 143,697 | 159,385 | 458,096 |
| 6 | d0wd | 86,912 | 87,138 | 82,797 | 256,895 |
| 7 | s3 | 152,392 | 126,345 | 153,526 | 432,528 |
| 7 | d0wd | 85,005 | 57,280 | 114,217 | 256,691 |

All fourteen cells span the full 1,800 s. **Night 3 has no B1**, which is the
already-documented off-air event at 1,769 s (§10.3) and not a new fact. So the
window carries **40 beacon-night-receiver cells** and **38 pairs**, matching
the scored set exactly.

## 4. Yardsticks — fixed here, not chosen later

- `BETWEEN_UNIT_SD = 0.00237 rad/sc` (`pc/exp_ambient_separation.py:79`).
  **Every σ in Q1, Q5 and Q6 below is in these units and nothing else.**
- **Separation σ** in Q2 and Q4 is the pooled-covariance Mahalanobis distance
  `pc/rff_offline.py` prints. `SEVEN_NIGHT_REREAD.md` §3 establishes that this
  is a *different unit* — the within-night window scatter, median 0.32 ×
  `BETWEEN_UNIT_SD`. It is used here because the scored-window figures it is
  being compared against are in it. **The two are never mixed in one
  comparison.**
- **κ yardstick** is computed from the *scored* window, not this one: the SD
  over the three units of their grand mean κ, pooled across nights, exactly as
  `BETWEEN_UNIT_SD` was built (`pc/exp_thermal_evidence.py:129`). It is
  computed before the new window is touched and recorded in §8 when it is.

## 5. Predictions, with thresholds frozen now

Every threshold below is set from figures already published in
`SEVEN_NIGHT_PREREG.md` §10 or measured in `SEVEN_NIGHT_REREAD.md` §9I. The
source of each is named so none can be claimed afterwards to have been chosen
to fit.

### Q1 — the fingerprint is frozen inside a night

**Prediction: |SFO(new window) − SFO(scored window)| is below 1.0σ on at least
36 of the 40 cells, and the median across all 40 is below 0.5σ.**

Basis: §9I's variogram gives median |Δ| of **0.17σ (s3)** and **0.42σ (d0wd)**
at a 34-minute separation. The two window centres here are 39 minutes apart —
just past the longest lag measured, so this is an extrapolation of one lag step
and is the weakest-supported prediction in the set.

### Q2 — separability survives in unseen data

**Prediction: B2–B3 separation is at or above 3.0σ — the repo's own
"reliably separable" line (`pc/rff_offline.py:353`) — on at least 6 of 7
nights, on both receivers independently.**

Basis: the scored windows gave **7 of 7** on s3 (minimum 3.4σ, night 2) and
**6 of 7** on d0wd (night 5's 1.9σ the sole miss). Predicting 6 of 7 on both
allows one more miss per receiver than was observed.

### Q3 — blind identification still works

**Prediction: median blind-holdout accuracy across the 14 cells is at or above
85%, and no cell falls below 60%.**

Basis: the six published cells are s3 76.8 / 97.7 / 87.2 and d0wd 67.2 / 97.2 /
91.7 (nights 5, 6, 7), median 89.5%, minimum 67.2%. The 60% floor sits below
the worst observed and far above the 33.3% three-class chance line.

**This is the load-bearing prediction of the document.** If it holds, three
co-located transmitters on a shared path were identified blind in thirty
minutes of data nobody had looked at.

### Q4 — no collapse, at the rate already seen

**Prediction: at most 6 of the 38 pairs fall below 1.0σ in `BETWEEN_UNIT_SD`
units, and night 5 remains the night with the smallest population spread
(max − min across beacons) on both receivers independently.**

Basis: `SEVEN_NIGHT_REREAD.md` §2 — 4 of 38 pairs were below 1.0σ in the scored
windows, and night 5 was the minimum-spread night on both receivers (1.6σ on
s3, 2.9σ on d0wd, each ~3.8× below its receiver's median).

The night-5 half is the sharper claim: §2 explicitly recorded that the two
receivers' spreads **do not correlate across nights** (ρ = −0.09), so night 5
landing minimum on both again would be a 1-in-6 coincidence repeating, or it
would mean something about night 5.

### Q5 — the yield victims are the same nights

**Prediction: (a) night 2, d0wd, B3 yields below 50%; (b) night 4, d0wd, B1
yields below 90%; (c) at most 2 of the 7 nights show any d0wd beacon below 90%;
(d) s3 shows no beacon below 90% on any night.**

Basis: §10.2's out-of-window sampling showed night-2 d0wd B3 still at 215–238
windows per 900 s out to 18,900 s — the collapse held all night, so it should
still be there at 8,120–9,920 s. Night 4's B1 was 53.0% in the scored window.
And across the whole series *"the control receiver degrades nothing, on any
night"* (§10.4, §10.5).

### Q6 — κ is the steadier feature

**Prediction: across the 40 cells, the median |Δκ| between the two windows,
expressed in κ's own between-unit units (§4), is smaller than the median |ΔSFO|
expressed in `BETWEEN_UNIT_SD` — and κ beats SFO on at least 4 of the 6
receiver-beacon cells.**

Basis: `LABELLED_EVENTS_0823.md` §20 measured κ's wander floor at **0.27–1.54×**
the between-device spread against SFO's **0.56–4.97×**, over four untouched
minutes. This extends that head-to-head from four minutes to thirty-nine.

**Recorded against this:** `IQ_IMBALANCE.md` §15.1 and `LABELLED_EVENTS_0823.md`
§20 disagree about κ's position-invariance, and `HYPOTHESIS_LEDGER.md` §4 lists
that as unresolved (item 15). Q6 does not resolve it and is not offered as
doing so.

## 6. Verdict table — frozen

| outcome | condition |
|---|---|
| **Q1 HELD** | ≥ 36 of 40 cells under 1.0σ **and** median < 0.5σ |
| **Q1 FAILED** | either half missed |
| **Q2 HELD** | B2–B3 ≥ 3.0σ on ≥ 6 of 7 nights, both receivers |
| **Q3 HELD** | median accuracy ≥ 85% **and** no cell below 60% |
| **Q4 HELD** | ≤ 6 of 38 pairs under 1.0σ **and** night 5 minimum-spread on both receivers |
| **Q5 HELD** | all four of (a)–(d) |
| **Q6 HELD** | κ median below SFO median **and** κ better on ≥ 4 of 6 cells |

Any prediction meeting neither its condition nor its opposite is reported as
**MIXED**, in those words, and is not resolved by choosing. A prediction whose
threshold becomes arithmetically unreachable is reported as **failed and
unreachable**, which is the state `SEVEN_NIGHT_PREREG.md` §4 had no name for.

## 7. Temptations, recorded in advance

1. **Reading Q2 or Q3 holding as evidence that the room conclusion is wrong.**
   It is not. This window shares all seven nights and the whole bench with the
   scored one; it is a *held-out window*, not an independent replication. It
   can show the capability is stable in time. It cannot show it generalises to
   another room, another apartment, or other hardware.
2. **Quoting Q3's accuracy without the class count.** Three sources, 33.3%
   chance. `CLAUDE.md` records that a same-model figure was once quoted without
   its class count and became unusable.
3. **Letting Q1 rescue Q3, or vice versa.** They are independent.
4. **Treating night 3 as a two-beacon success.** With B1 off air its pair set is
   one, not three, and it is weaker evidence than the other six nights.
5. **Widening the 3.0σ bar in Q2** if a night lands at 2.8σ.
6. **Re-deriving T0.** It is copied from §10 and stays copied, even if a better
   value could be argued for now.

## 8. Stage 2 — results

> **Nothing below this line existed when §1–§7 were written.**

Run 2026-09-04 on the operator's go-ahead. All fourteen cells, one pass each,
`pc/rff_offline.collect_observations` and `pc/rff_offline.report` imported
unmodified — DSP, gates, window size, pooled covariance and the chronological
60/40 holdout split are the shipped ones. Per-window values dumped to
`data/cache/windows2/`.

### Summary

| | verdict |
|---|---|
| **Q1** — fingerprint frozen inside a night | **HELD** |
| **Q2** — B2–B3 ≥ 3.0σ on ≥ 6 of 7, both receivers | **FAILED** |
| **Q3** — blind identification still works | **HELD** |
| **Q4** — no collapse at the observed rate; night 5 tightest | **HELD** |
| **Q5** — same yield victims | **FAILED** (a and b passed, c and d failed) |
| Q6 — κ vs SFO | not yet run |

**Both failures point at the same two objects**, and neither was chosen after
the fact: night 7's B1, and night 5's d0wd.

### Q1 — HELD

|ΔSFO| between the held-out and scored windows, in `BETWEEN_UNIT_SD`:

| night | rx | B2 | B1 | B3 |
|---:|---|---:|---:|---:|
| 1 | s3 | 0.00 | 0.44 | 0.74 |
| 1 | d0wd | 0.04 | 0.08 | 0.02 |
| 2 | s3 | 0.03 | 0.07 | 0.07 |
| 2 | d0wd | 0.00 | 0.13 | 0.03 |
| 3 | s3 | 0.14 | *off air* | 0.25 |
| 3 | d0wd | 0.14 | *off air* | 0.40 |
| 4 | s3 | 0.12 | 0.04 | 0.30 |
| 4 | d0wd | 0.06 | 0.23 | 0.82 |
| 5 | s3 | 0.16 | 0.04 | 0.05 |
| 5 | d0wd | 0.06 | 0.05 | 0.72 |
| 6 | s3 | 0.10 | 0.10 | 0.05 |
| 6 | d0wd | 0.03 | 0.06 | 0.01 |
| 7 | s3 | 0.03 | **4.06** | 0.23 |
| 7 | d0wd | 0.23 | **10.36** | 0.07 |

**38 of 40 under 1.0σ (bar ≥ 36). Median 0.07σ (bar < 0.5). Both halves met.**

0.07σ is **0.00017 rad/sc** across a thirty-nine-minute gap. §9I's variogram
predicted 0.17σ (s3) / 0.42σ (d0wd) at 34 minutes; the outcome is **tighter
than the extrapolation**, which §5 called the weakest-supported prediction in
the set.

**The two failures are the same beacon-night.** `SEVEN_NIGHT_PREREG.md` §10.7
recorded, before this document existed, that night 7's B1 contributed 487
windows on d0wd against 1,899–3,037 for the others, with an IQR of 0.0212
where every other beacon-night sits near 0.0005–0.0011 — *"a twentyfold spread
inflation on the one beacon the P2 arm corrects against."* **Q1 failed on
exactly the cell the record had already flagged, and nowhere else.**

### Q2 — FAILED

B2–B3 separation, pooled Mahalanobis, against the 3.0σ line
(`pc/rff_offline.py:353`):

| night | s3 | d0wd |
|---:|---:|---:|
| 1 | 11.1 | 11.0 |
| 2 | 7.8 | 76.3 |
| 3 | 15.8 | 25.2 |
| 4 | 11.1 | 29.4 |
| 5 | 6.7 | **0.6** |
| 6 | 29.0 | 47.3 |
| 7 | 29.8 | **2.8** |

**s3 7 of 7. d0wd 5 of 7. The bar was 6 of 7 on both, so Q2 fails.**

**Night 7's d0wd figure is 2.8σ against a 3.0σ bar.** §7 temptation 5 was
written to cover precisely this and it is not being widened. **Q2 is failed as
frozen.**

Night 5's 0.6σ is not a near-miss — see below.

### Q3 — HELD

| night | s3 | d0wd |
|---:|---:|---:|
| 1 | 95.4% (2,562/2,685) | 90.6% (1,431/1,580) |
| 2 | 97.7% (2,704/2,769) | 97.4% (1,143/1,173) |
| 3 | 89.8% (1,793/1,997) | 76.8% (1,148/1,494) |
| 4 | 94.9% (2,644/2,787) | 96.1% (1,249/1,300) |
| 5 | 80.5% (1,988/2,471) | **61.8%** (948/1,535) |
| 6 | 98.1% (2,804/2,857) | 98.7% (1,557/1,578) |
| 7 | 97.7% (2,463/2,520) | 98.1% (1,426/1,454) |

**Median 95.8% (bar ≥ 85). Minimum 61.8% (bar ≥ 60). Both halves met.**

**Three sources. Chance is 33.3%**, and night 3 carries two sources, where
chance is 50.0% — its 89.8% / 76.8% must be read against that, not against
33.3%.

Eleven of fourteen cells are above 89%. Nights 1–4 had **no published accuracy
figure anywhere in the corpus** before this run; they are new.

**This is the load-bearing prediction and it held on data that had never been
looked at.**

### Q4 — HELD

Pairs below 1.0σ in `BETWEEN_UNIT_SD` units: **4 of 38** (bar ≤ 6).

| night | rx | pair | σ |
|---:|---|---|---:|
| 5 | d0wd | B2–B3 | **0.09** |
| 5 | s3 | B1–B2 | 0.45 |
| 6 | s3 | B1–B2 | 0.82 |
| 7 | d0wd | B2–B3 | 0.94 |

> **DEFECT IN §4's WORDING, recorded now rather than resolved by choosing.**
> §4 assigns Q2 *and Q4* to the pooled-Mahalanobis unit, while Q5's text in §5
> says Q4 is in `BETWEEN_UNIT_SD`, and the basis it cites
> (`SEVEN_NIGHT_REREAD.md` §2, "4 of 38") is a `BETWEEN_UNIT_SD` figure. The
> two clauses contradict. **Scored both ways rather than picking the
> convenient one: 4 of 38 in `BETWEEN_UNIT_SD`, 1 of 38 in pooled units. The
> bar is ≤ 6 and Q4's first half holds under either reading**, so nothing
> turns on the ambiguity — but the wording is defective and any future
> document reusing this table must state its unit.

Population spread, max − min across beacons, in `BETWEEN_UNIT_SD`:

| night | s3 | d0wd |
|---:|---:|---:|
| 1 | 8.1 | 10.0 |
| 2 | 4.1 | 33.1 |
| 3 | 2.8 | 5.7 |
| 4 | 5.0 | 24.5 |
| **5** | **1.7** | **2.9** |
| 6 | 6.5 | 10.8 |
| 7 | 6.4 | 13.8 |

**Minimum on night 5, on both receivers independently. Predicted 5 and 5; got
5 and 5.**

The scored window gave 1.6 and 2.9 for the same night. **The held-out window
gives 1.7 and 2.9.** `SEVEN_NIGHT_REREAD.md` §2 recorded that the two
receivers' spreads do not correlate across nights (ρ = −0.09), so this was
offered there as possibly a 1-in-6 coincidence. **It has now repeated on a
disjoint window, to one decimal place, on both receivers.**

### Q5 — FAILED

Frame yield, windows × 64 ÷ the frame counts fixed in §3 before any estimator
ran:

| night | rx | B2 | B1 | B3 |
|---:|---|---:|---:|---:|
| 1 | s3 | 99.8% | 98.9% | 99.8% |
| 1 | d0wd | 98.9% | 98.3% | 98.4% |
| 2 | s3 | 98.6% | 99.2% | 99.8% |
| 2 | d0wd | 98.6% | 98.3% | **25.1%** |
| 3 | s3 | 100.0% | *off air* | 99.6% |
| 3 | d0wd | 98.9% | *off air* | 97.4% |
| 4 | s3 | 99.9% | 99.4% | 99.9% |
| 4 | d0wd | 98.4% | **50.1%** | 91.5% |
| 5 | s3 | 98.6% | 99.7% | 98.9% |
| 5 | d0wd | 98.1% | 98.0% | 97.9% |
| 6 | s3 | 99.9% | 99.9% | 99.4% |
| 6 | d0wd | 98.7% | 98.6% | 97.3% |
| 7 | s3 | 100.0% | **77.1%** | 99.9% |
| 7 | d0wd | 98.2% | **63.2%** | 98.7% |

- **(a) night 2 d0wd B3 below 50% — PASS at 25.1%.** The night-2 collapse is
  still running at 8,120–9,920 s, deeper than §10.2 sampled it. Predicted
  because §10.2 found it holding to 18,900 s.
- **(b) night 4 d0wd B1 below 90% — PASS at 50.1%**, against 53.0% in the
  scored window.
- **(c) at most 2 victim nights on d0wd — FAIL. Three: nights 2, 4 and 7.**
- **(d) s3 shows no beacon below 90% — FAIL. Night 7 B1 at 77.1%.**

**Q5 fails, and (d) is the informative half.** *"The control receiver degrades
nothing, on any night"* held across all seven scored windows (§10.4, §10.5,
§10.6). **In the held-out window it breaks — on s3, on night 7, on B1.**

## 8.1 What the two failures are actually saying

**Night 7's B1 is a sick transmitter, and the two-receiver design is what
proves it.** It is the only Q1 failure (4.06σ on s3, 10.36σ on d0wd), and it is
the only s3 yield victim in the series (77.1%). **Degradation appearing on both
receivers at once cannot be a receiver artifact.** Every previous victim in
this series appeared on d0wd alone, which is why §10.4's *"the control receiver
degrades nothing"* was worth writing down — and why its breaking here means
something different. `SEVEN_NIGHT_PREREG.md` §10.7 saw the d0wd half of this
and could not tell whether it was the receiver or the beacon; the held-out
window answers it. **B1 was failing on night 7 and the scored window caught
only part of it.**

This is also the beacon the P2 arm corrects against, which is one more entry on
the pile of reasons the reference correction is unsafe on this bench.

**Night 5 is a real, repeatable state of the bench, and it is the one thing in
this project that reproduces the 28 August collapse.** On night 5, d0wd,
**B2–B3 read 0.09σ** in `BETWEEN_UNIT_SD` units. `COLOCATED_TX_0828.md`'s
founding measurement was **0.2σ on the same receiver**. This is a window nobody
had scored, on a night whose scored window already carried the smallest spread
of the series on both receivers, and it comes in *tighter than the result the
whole project was built to replicate.*

**This must not be read as P1 rescued.** P1 required B2–B3 below 1.0σ on five
of seven nights and it got one, in a window that was not the pre-registered
one. §7 temptation 1 applies in full. What it does say is narrower and it is
new:

> **The co-location collapse is real and it is intermittent.** It is not the
> n = 1 coincidence §10.2 feared, and it is not the every-night property P1
> assumed. It is a state the bench enters on some nights and not others, and
> **night 5 is that state, now observed twice on disjoint windows.**

Nothing here identifies what puts the bench into it. Night 5 was the longest
capture (29,479 s), the first with no yield victim, and the night s3's B3 made
its only excursion away from +0.020. Those are three facts about the same
night, not a mechanism.

## 8.2 What held, stated plainly

Across seven nights, two receivers and thirty minutes per night that had never
been analysed:

- **The clock fingerprint is frozen inside a night** — median drift of 0.07σ
  over thirty-nine minutes, 38 of 40 cells under 1.0σ, and the two exceptions
  are one beacon the record had already flagged as failing.
- **Three transmitters four feet apart on one surface, sharing a propagation
  path, were identified blind at a median of 95.8%** against 33.3% chance,
  with eleven of fourteen cells above 89%.

Neither of those was scored anywhere before today.

## 9. Commands

Slicing (`pc/slice_window.py`, bisection on file position; the 500 s lead-in is
the method §9A of `SEVEN_NIGHT_REREAD.md` validated against §10's table on 40
of 40 cells):

```
python pc/slice_window.py data/raw/<RX>_<STAMP>.csv /tmp/w2.csv <T0+4500> <T0+6800>
python pc/rff_offline.py /tmp/w2.csv --after <500> --before <2300>
```

κ and the paired shipped-SFO come from the project's own pre-registered tool,
which imports the IQ estimator unmodified:

```
python pc/exp_labelled_events_0823.py scan --tag <RX>_<NIGHT> --path /tmp/w2.csv
```

Per-window values for any later timescale question are dumped by
`pc/dump_windows.py` into `data/cache/windows/`, as in §9I.
