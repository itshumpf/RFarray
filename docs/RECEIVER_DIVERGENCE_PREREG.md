# RECEIVER DIVERGENCE PREREG — is d0wd's B3 reading a state or an artifact?

> **STAGE 1. Written 2026-08-30, ~09:15, before the night-3 capture exists.**
>
> Nights 1 and 2 are the discovery set and their numbers are already known.
> **Night 3 has not been recorded.** Everything in §1–§8 is fixed before it
> exists. Corrections go below the Stage 2 banner in §9, dated, with the
> original left visible.
>
> Read-only on `data/raw/`. No git command run.

---

## 1. The observation this exists to test

On night 2 (`20260830_013943`, `SEVEN_NIGHT_PREREG.md` §10) the two receivers
disagreed about one transmitter by a factor of four, all night:

| absolute window | d0wd B3 | s3 B3 |
|---|---:|---:|
| 1,200 – 2,100 s | +0.0423 | +0.0204 |
| 5,520 – 7,820 s | +0.0795 | +0.0204 |
| 10,000 – 10,900 s | +0.0769 | +0.0201 |
| 14,000 – 14,900 s | +0.0786 | — |
| 18,000 – 18,900 s | +0.0781 | — |

Alongside it, **B3's frame-to-window yield on d0wd was 30.1%** at the shipped
`--min-inlier 0.6` floor, against 98.7% (B2) and 98.4% (B1) on the same
receiver and 99.7% for B3 itself on s3.

Three things are already ruled out and are not re-tested here: channel (both
`ch=6`), CSI payload length (both `len=256`), noise floor (both −96.00 dBm), and
signal strength — B3 was the **strongest** of the three on d0wd at −73.3 dBm.
Lowering the inlier floor to 0.2 restores full yield and moves B3's centroid by
0.0005, so **the value is not an artifact of the surviving subset.**

**The beacon is a partial control.** B3's power source (battery) and position
were identical on nights 1 and 2. Across those nights s3 moved it +0.0007 and
d0wd moved it +0.0722.

> **CORRECTED 2026-08-30, ~09:40 — before the night-3 capture exists and before
> any figure in §9 was computed.** This paragraph originally read *"B3's power
> source (battery), position **and the fan state** were identical on nights 1 and
> 2."* **The fan clause is false.** Night 1 ran fan off (`day 1 fan off ac
> starting on`); night 2 ran fan on throughout. Corrected in place rather than
> below the banner, following the precedent of `SEVEN_NIGHT_PREREG.md` §2, and
> declared here because the rule against editing sealed text exists so that a
> change like this has to be visible. **No threshold in §4 depended on it and
> none was changed.**

**The fan was then ruled out by measurement.** The existing fan A/B capture
(`20260829_122648`) contains an OFF → ON → OFF reversal. d0wd reads B3 at
**+0.0023 / +0.0026 / +0.0025** across it, with full window yield throughout
(689 / 823 / 838) — including during fan-on, where night 2 showed 30.1%. A fan
reversal moves d0wd's B3 by 0.0003; the effect under test is 0.0722.

That capture was recorded with the beacons spread at the desk rather than at
POS4, so the fan state matches night 2 but the geometry does not. **The fan is
excluded as a sufficient cause on its own, not as a component of a
fan-plus-geometry interaction.** Full working in `SEVEN_NIGHT_PREREG.md` §10.

---

## 2. The two accounts, stated before the test

**A — PATH STATE.** The d0wd↔B3 propagation path genuinely entered a different
condition, and d0wd's estimate is correct for that path. SFO is a
transmitter–receiver *pair* quantity; two receivers are not obliged to agree.
Under A the condition is physical, has a cause, and will either persist or end.

**B — ESTIMATOR ARTIFACT.** d0wd's phase-slope estimate for B3 has settled on a
wrong branch or a biased solution. Under B the number is stable and tight
because the estimator is stably wrong, not because anything in the room is.

**These make different predictions about night 3 and that is the point.**

---

## 3. Night 3 conditions — required, and fixed now

**Change nothing.** Same beacon positions on the bar. Same receivers on the wall.
Fan on. **Same power assignment as night 2: B1 mains, B2 battery, B3 battery.**

Night 3 must differ from night 2 in nothing the operator controls. If anything
is changed for any reason, **that is recorded in §9 before scoring and this
prereg is scored as UNRUNNABLE for that night**, not adjusted.

Analysis window: **T0 + 2,400 through T0 + 4,700**, T0 read from the capture's
own label per `SEVEN_NIGHT_PREREG.md` §9 and written into §9 below before any
figure is computed.

Raw, no `--ref-mac`, shipped defaults, both receivers independently.

---

## 4. Predictions, thresholds frozen now

### D1 — does the d0wd B3 offset persist?

Night 2 point value: **+0.0795**.

| outcome | condition on night 3, d0wd, scored window |
|---|---|
| **PERSISTS** | B3 raw SFO ≥ **+0.060** |
| **REVERTED** | B3 raw SFO ≤ **+0.030** |
| **INTERMEDIATE** | anything between — reported in those words, not resolved by choosing |

The gap between the bars is deliberate and wide. +0.030 is comfortably above
every d0wd B3 reading before night 2 (night 1: +0.0073); +0.060 is comfortably
below night 2's. A value landing between them is a real outcome and is reported
as one.

### D2 — is the yield collapse coupled to the offset?

Night 2: B3 yield on d0wd **30.1%**, B1 and B2 both ~98%.

**Prediction: yield and offset move together.** If D1 PERSISTS, B3's d0wd yield
is below 50%. If D1 REVERTED, B3's d0wd yield is above 90%.

**A split result — offset persists with healthy yield, or offset reverts with
collapsed yield — refutes the assumption that these are one phenomenon**, which
this document has been treating them as. That is the most informative outcome
available and it is named here so it cannot be waved through.

### D3 — does s3 stay flat?

**Prediction: s3's B3 raw SFO is within ±0.0030 of +0.0204.**

This is the load-bearing control. Under both A and B, s3 is measuring an
untouched beacon on an untouched path. **If s3 also moves, neither account in §2
is adequate** and the framing is wrong rather than one branch being right.

### D4 — is there one victim at a time?

**Prediction: on d0wd, at most one of the three beacons has yield below 50%; on
s3, none does.**

**This has exactly one supporting observation at the shipped floor** — night 2 —
and is the weakest prediction here. It is stated because it is the version of
the "receiver picks a victim" idea that can actually be scored, and because
stating it now stops it being asserted later from memory.

**Explicitly out of scope:** anything about the 0.90 inlier gate. The per-beacon
window counts in `QUALITY_GATE_PREREG.md` §7.1a do not reproduce (see §7 below),
and no prediction here is allowed to lean on them.

---

## 5. Verdict table — frozen

| result | reading |
|---|---|
| D1 PERSISTS + D2 low yield + D3 flat | consistent with **either** A or B; one night cannot separate them. Report as **PERSISTENT DIVERGENCE**, mechanism open. |
| D1 REVERTED + D2 high yield + D3 flat | the night-2 state was **episodic**. Neither A nor B is excluded, but the effect has an onset and an end, which is a handle. |
| D3 fails (s3 moves too) | **FRAMING WRONG.** §2's two accounts are both inadequate. Stop and rewrite before scoring anything else. |
| D2 splits from D1 | offset and yield are **separate phenomena**. Every document that has treated them as one — including `SEVEN_NIGHT_PREREG.md` §10 — needs revisiting. |
| INTERMEDIATE on D1 | reported as INTERMEDIATE. **Not rounded to the nearer bar.** |

One night does not decide A vs B and this document does not claim it will. It
decides whether the thing is still there, which is the question that has to be
answered first and which every further test depends on.

---

## 6. Controls

- **Both receivers, every figure, independently.**
- **B1 and B2 reported every night alongside B3**, whether or not they are
  interesting. A receiver-side effect that moves all three is a different object
  from one that moves one.
- **The inlier sweep repeated** — 0.2 / 0.4 / 0.6 on d0wd's B3 — since the
  night-2 finding that the centroid is gate-invariant is itself n = 1.
- **Frame counts, RSSI, channel, `len` and noise floor per beacon per receiver**,
  reported even when unchanged, so "checked and identical" is distinguishable
  from "never looked."

---

## 7. What this cannot answer, and one thing it must not touch

- **No mechanism.** No temperature is measured, no antenna orientation is
  recorded, no spectrum analyser exists. This series can establish *whether* and
  *when*, never *why*.
- **Nothing about P1, P2 or P3** in `SEVEN_NIGHT_PREREG.md`. Those bars are
  frozen separately and are not affected by any outcome here.
- **`QUALITY_GATE_PREREG.md` §7.1a is under a live discrepancy.** Its per-beacon
  table (B2 1,521 → 61 at gate 0.90) does not reproduce on either a sliced or a
  full-file run, both of which give **646**; B3 gives 2,005, not 2,074. §7.1's
  separations reproduce exactly. **That discrepancy is unresolved and belongs to
  its own document.** Nothing in this prereg cites §7.1a in either direction.

---

## 8. Temptations, recorded in advance

1. **Reading INTERMEDIATE as PERSISTS** because night 2 was dramatic and a
   dramatic result is more interesting to write up.
2. **Explaining a revert by something remembered afterwards** — a door left
   open, a phone on the counter. Any physical cause must be recorded in §9
   before the window is scored or it does not count.
3. **Letting D4 rescue the night** if D1 comes back INTERMEDIATE. They are
   independent.
4. **Treating "d0wd is just wrong" as the safe default.** It is the account that
   requires no new physics and is therefore the one most likely to be adopted
   without evidence. Under §2 it is account B, and it needs support like A does.
5. **Quoting +0.0795 as a magnitude.** Its σ depends on the inlier floor
   (60.6σ at 0.60, 22.7σ at 0.40). Quote the offset in rad/subcarrier.

---

## 9. Stage 2 — results

> **Nothing below this line existed when §1–§8 were written.**

### 9.1 Night 3 — `20260831_020408`, scored 2026-08-31

**T0 = 0, declared** (no operator label existed in either file; see
`SEVEN_NIGHT_PREREG.md` §10.3a). Window **2,400 – 4,700 s**, raw, shipped
defaults, both receivers.

**§3's conditions were not fully met.** B1 `a4:f0` stopped transmitting at
1,769 s (d0wd) / 1,489 s (s3), before the window opened. Per §3 that is
recorded before scoring, not adjusted for. D1–D3 concern B3 only and are
unaffected; D4 is scored on two beacons instead of three and is marked
degraded.

| | frozen bar | night 2 | night 3 | verdict |
|---|---|---:|---:|---|
| **D1** d0wd B3 raw SFO | ≥ +0.060 persists / ≤ +0.030 reverted | +0.0795 | **+0.0174** | **REVERTED** |
| **D2** d0wd B3 yield | > 90% if D1 reverted | 30.1% | **97.4%** | **HOLDS** |
| **D3** s3 B3 within ±0.0030 of +0.0204 | — | +0.0204 | **+0.0189** (Δ 0.0015) | **HOLDS** |
| **D4** ≤ 1 beacon < 50% yield on d0wd, 0 on s3 | — | — | **0 and 0** | **holds, degraded** |

**Per §5: the PERSISTENT branch is excluded. The night-2 state was episodic —
it had an onset and an end.**

**D3 is what makes the rest readable.** The control receiver moved 0.0015
across 27 hours while d0wd moved 0.0621 back the other way. Both receivers
wandering together would have voided the comparison; they did not.

**D2 contradicts the discovery-set hint and that is the point.**
`SEVEN_NIGHT_PREREG.md` §10.2 recorded that on night 2 the offset appeared to
move *before* the yield collapsed, which suggested two phenomena. §4 named a
split as the informative outcome. **On held-out data they moved together** —
30.1% → 97.4% alongside +0.0795 → +0.0174. The hint pointed the wrong way, and
it was written down in advance as pointing that way, which is the only reason
that statement can be made now.

**Cross-receiver disagreement for B3 fell from 0.0591 to 0.0015 — 39×.**

### 9.1b Night 4 — `20260901_035805`, scored 2026-09-01

T0 = 0 declared (no label; see `SEVEN_NIGHT_PREREG.md` §10.4a). Window
2,400–4,700 s. **All three beacons transmitted throughout**, so §3's conditions
were met for the first time and D4 is fully scoreable.

| | frozen bar | night 2 | night 3 | **night 4** | verdict |
|---|---|---:|---:|---:|---|
| **D1** d0wd B3 SFO | ≥+0.060 persists / ≤+0.030 reverted | +0.0795 | +0.0174 | **+0.0447** | **INTERMEDIATE** |
| **D2** d0wd B3 yield | >90% if reverted, <50% if persists | 30.1% | 97.4% | **84.7%** | **UNEVALUABLE** |
| **D3** s3 B3 within ±0.0030 of +0.0204 | — | +0.0204 | +0.0189 | **+0.0188** (Δ 0.0016) | **HOLDS** |
| **D4** ≤1 beacon <50% on d0wd, 0 on s3 | — | — | — | **0 and 0** | **HOLDS — and uninformative** |

**D1 lands between the bars.** §4 required this be reported as INTERMEDIATE and
**not rounded to the nearer bar**. It is 0.0147 above the reverted ceiling and
0.0153 below the persists floor — almost exactly in the middle of the gap that
was deliberately left wide.

**D2 cannot be scored.** Its wording is conditional on D1 being one thing or
the other: *"if D1 PERSISTS, yield below 50%; if D1 REVERTED, yield above 90%."*
D1 is neither, and 84.7% satisfies neither branch. **The bar failed to
anticipate its own INTERMEDIATE case**, which §4 had explicitly named as
possible. That is a defect in D2, not a result.

**D3 holds for a third consecutive night**, and this is now the strongest thing
in the document. s3's B3 across three nights: **+0.0204, +0.0189, +0.0188** —
a total spread of 0.0016 over 48 hours. d0wd's B3 over the same nights:
+0.0795, +0.0174, +0.0447. **The control receiver does not move. The other one
does, by up to fifty times as much, on the same frames.**

**D4 holds and tells us nothing.** The 50% threshold was set from night 2's
30.1%. Night 4's worst beacon is B1 at **53.0%** — degraded, clearly, and
sitting three points above a bar chosen before anyone knew what a mild case
looked like. The verdict is HOLDS and it should not be quoted as evidence of
anything.

**And the phenomenon is no longer "one victim."** Two of three beacons are
degraded on d0wd this night — B1 at 53.0% and +0.0597, B3 at 84.7% and +0.0447
— while B2 sits at 98.5% and +0.0025. D4's wording measures the wrong thing:
it counts beacons past a severity threshold rather than asking whether the
affected set changes. **The set changed.** Night 2 it was B3. Night 4 it is B1
and B3. B2 has never been affected on any night.

Full working, including the power-source coincidence that this raises and which
is **not adopted**, in `SEVEN_NIGHT_PREREG.md` §10.4.

### 9.1c Night 5 — `20260902_000949`, scored 2026-09-02

Window 2,400–4,700 s, T0 = 0 declared (no operator label, as nights 3 and 4).
Full pre-scoring block in `SEVEN_NIGHT_PREREG.md` §10.5a, written before any
figure below was computed. All three beacons transmit from t = 0 and run
hours past the window.

| | night 2 | night 3 | night 4 | **night 5** |
|---|---:|---:|---:|---:|
| d0wd B3 raw SFO | +0.0795 | reverted | +0.0447 | **+0.0087** |
| s3 B3 raw SFO | +0.0204 | +0.0189 | +0.0188 | **+0.0038** |
| d0wd B3 yield | 30.1% | 97.4% | 84.7% | **98.1%** |

**D1 — REVERTED.** Bar was ≤ +0.030. d0wd B3 reads **+0.0087**, comfortably
below it and the lowest of the series.

**D2 — HOLDS.** D1 REVERTED requires d0wd B3 yield above 90%. It is **98.1%**.
Offset and yield moved together, in the direction the coupling predicts. This
is the first night that scores D2 cleanly — night 3 scored it, night 4 could
not because D1 landed between the bars.

**D4 — HOLDS, and again tells us nothing.** No beacon on either receiver is
below 50%; the lowest figure anywhere on night 5 is 98.0%. A prediction about
which beacon is the victim is uninformative on a night with no victim.

#### D3 — FAILS. The control moved.

**Prediction: s3's B3 raw SFO within ±0.0030 of +0.0204**, i.e. inside
[+0.0174, +0.0234].

**Night 5 s3 B3 = +0.0038.** Outside the band by **0.0136**, which is 4.5×
the tolerance. For three consecutive nights s3's B3 sat at +0.0204, +0.0189,
+0.0188 — a spread of 0.0016, inside a band 0.0060 wide. §9.1b called that
"the strongest thing this document has." On night 5 it drops by 0.015.

**§5's frozen verdict for this outcome, quoted rather than paraphrased:**

> **D3 fails (s3 moves too)** — **FRAMING WRONG.** §2's two accounts are both
> inadequate. Stop and rewrite before scoring anything else.

That is the verdict. It was frozen before the data existed and it is being
applied as written.

**What it does and does not mean.** §2's accounts were **A** a real path state
on d0wd and **B** an estimator artifact on d0wd. Both locate the phenomenon on
one receiver and treat s3 as a fixed rule against which d0wd's movement is
measured. If s3 moves too, that ruler is not fixed, and neither account is
adequate as stated. **It does not mean d0wd's night-2 excursion was unreal** —
+0.0795 against +0.0204 is not explained by a control that later moves 0.015.
It means the frame the excursion was measured in is not stable, and the size
of every divergence figure in this document depends on a baseline that has now
been shown to drift.

**Account C is not rescued by this either.** C locates corruption on non-S3
silicon; s3 is the S3 board and s3 is what moved.

**One measurement bearing directly on this, from outside the series.** The
20-hour tail of the night-4 capture (`UNPLANNED_20H_20260901.md` §3) puts a
single beacon's hour-to-hour wander on s3 at **0.00305 rad/sc — 1.29 ×
`BETWEEN_UNIT_SD`** across fourteen hours. That is a within-night figure, not
the night-to-night quantity P3 asks for, and it must not be scored as P3. But
it establishes that s3 is not a fixed point on the scale of the D3 band, which
is 0.0060 wide. **A control tolerance narrower than the control's own measured
wander was never going to hold**, and the fact that it held for three nights
was luck rather than stability.

**What must not happen now:** D3's band must not be widened, and nights 1–4
must not be rescored against a looser bar. The prediction failed as written.
§5 says rewrite the framing, not the threshold.

#### 9.1c.1 — checked whether this is a reading error. It is not.

Three ways the night-5 figure could have been an artifact, each tested:

**Window placement.** s3's B3 was scored across three separate windows on
night 5: **+0.0028** (100–2,400 s), **+0.0038** (2,400–4,700 s, scored),
**+0.0043** (7,000–9,300 s). Spread 0.0015, all far below the band. It sat
there all night; the scored window did not catch a dip.

**Receiver alignment.** The two night-5 files' first frames are **104 ms**
apart (s3 `1788325789885148`, d0wd `1788325789989090`). The same relative
window is the same absolute period on both receivers.

**Historical values.** +0.0204 / +0.0189 / +0.0188 are written in §9.1a,
§9.1b and `SEVEN_NIGHT_PREREG.md` §10, not carried from memory.

#### 9.1c.2 — B3 moved on BOTH receivers, and the band was never justified

Night 4 → night 5, raw SFO:

| | s3 | d0wd |
|---|---:|---:|
| B3 `f4:2d` | +0.0188 → **+0.0038** (−0.0150) | +0.0447 → **+0.0087** (−0.0360) |
| B2 `28:05` | +0.0121 → +0.0077 (−0.0044) | +0.0025 → +0.0107 (**+**0.0082) |
| B1 `a4:f0` | +0.0063 → +0.0071 (+0.0008) | +0.0597 → +0.0039 (−0.0558) |

**Both receivers move B3 in the same direction on the same night.** B2 moves
in opposite directions on the two receivers. Two independent receivers
agreeing that one transmitter shifted is more consistent with **B3 changing**
than with s3 drifting — and a beacon-side change fails D3 while leaving both
receivers healthy, which is a different conclusion from the one §5 names.

**And the band was set from a quantity that was never stable.** s3's B3 raw
SFO in the same 2,400–4,700 s window across the corpus:

| capture | s3 B3 |
|---|---:|
| `20260823_014740` | +0.0280 |
| `20260827_140642` | +0.0394 |
| `20260828_022627` | +0.0088 |
| `20260829_025355` *(night 1)* | +0.0200 |
| `20260830_013943` *(night 2)* | +0.0204 |
| `20260831_020408` *(night 3)* | +0.0191 |
| `20260901_035805` *(night 4)* | +0.0190 |
| `20260902_000949` *(night 5)* | **+0.0028** |

Computed with `rff.dsp.FrameEstimator` at shipped gates, 4,000 frames per
capture. It reproduces the scored figures — night 2 +0.0204 against §9.1a's
+0.0204, night 3 +0.0191 against +0.0189, night 4 +0.0190 against +0.0188 —
so the method agrees with `rff_offline` to about 0.0002.

**In the week before the series, this same beacon on this same receiver ranged
+0.0088 to +0.0394 — a spread of 0.0306, five times the width of the D3 band.**
Even inside the series window, 28 August reads +0.0088 and 29 August +0.0200,
a jump of 0.011 between consecutive nights.

**D3's ±0.0030 was set from one night's value on a quantity that had moved
0.03 in the preceding week.** Four consecutive nights inside the band was the
unusual event, not the fifth night outside it.

**Caveat, stated rather than assumed:** the 23 and 27 August captures predate
§2's fixed POS4 arrangement, so they are not the same experimental condition
and are shown as context for the quantity's range, not as comparable nights.
The 28 → 29 August jump is inside the series window and does not need that
caveat.

**What this does to the verdict.** D3 still failed as written and §5's
instruction still stands. But the honest reading of *why* is no longer "the
control receiver moved." It is that **D3 was a tolerance narrower than the
natural variation of the thing it was measuring**, and that on night 5 the
beacon it was measuring moved on both receivers at once. Neither of those is
in §2's two accounts, which is what "rewrite the framing" now has to fix.

### 9.2 A third account, from outside — opened 2026-08-31

§2 framed two accounts: **A** a real path state, **B** an estimator artifact.
A third was not considered and comes from the authors of the receiver-effects
literature themselves.

`github.com/nzqo/sensession`, the code release for Portner et al.
(arXiv:2605.26836), gives this instruction for its ESP32 collection path,
verbatim:

> **"Make sure to use only the ESP32-S3 model for now. We found others to
> yield corrupted data occasionally."**

**`s3` is an ESP32-S3. `d0wd` is not** — it is the original ESP32 D0WD die.
Every anomaly in this document is on `d0wd`: the +0.0795 offset, the 30% frame
yield, and the 0.90-gate window collapse in `QUALITY_GATE_PREREG.md` §7.1b.

**Account C: occasional CSI corruption on non-S3 ESP32 silicon, known
informally to another group, episodic by their description.**

**This is not established and it is not adopted here.** It is a one-line
setup note in a README, not a result — no mechanism, no rate, no conditions,
and "occasionally" is not a measurement. It is recorded because it is the
first external evidence bearing on any of the three accounts, because it fits
the episodic shape night 3 just demonstrated, and because **it would be
dishonest to send anyone an email about a novel receiver effect without
having read the sentence in their own repository that may already explain
it.**

**What it changes about the plan:** nothing in §3–§5, which are frozen and
were scored before this was found. What it changes is priority — establishing
whether `d0wd` is the sole locus is now cheaper and more informative than
another night. The corpus already holds 14 capture days across both receivers
and that question can be asked of data already on disk.

**Counter-evidence already in hand, stated so it is not forgotten:** the
19.6σ excursion in `ROOM_OR_RADIO.md` §6.2 appeared on **s3**, not d0wd. Not
every anomaly in this project is on the non-S3 board.
