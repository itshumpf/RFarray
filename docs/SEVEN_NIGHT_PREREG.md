# SEVEN NIGHT PREREG — replicating the co-location result

> **STAGE 1. Written 2026-08-28, before the first capture of this series
> exists.** Everything above the Stage 2 banner in §10 was fixed before any
> data was collected. Nothing above that banner may be edited after the first
> capture starts; corrections go below it, dated, with the original left
> visible. If the thresholds in §3 cannot be met, §10 reports that they were
> not met. They are not relaxed to manufacture a result.

Read-only on `data/raw/`. No git command run.

---

## 1. Why this capture exists

`COLOCATED_TX_0828.md` measured two physically distinct beacons four feet
apart on one surface and found them **0.2σ apart on d0wd and 0.7σ on s3**,
raw. That is the load-bearing result of the whole project: it is
**same-instant**, so it does not inherit the between-night drift that weakens
every other figure here.

**It is also n = 1.** One 38-minute window, one night. `ROTATION_PREREG.md:71`
already states the general problem in this project's own words — *"A single
before/after cannot distinguish a rotation from the clock."* The same applies
to a single co-location window.

This series exists to turn n = 1 into n = 7, and to settle two things the
28 August capture raised but could not answer.

---

## 2. Design — fixed before running

**Seven consecutive nights, 2026-08-28 through 2026-09-03.**

- All three beacons at **POS4**, on one surface, spread ~4 ft apart.
  Arrangement unchanged for the whole series. **If a beacon is moved for any
  reason, that night is excluded and the exclusion is recorded here with its
  reason** — not silently dropped.
- Both receivers (`s3`, `d0wd`) in their usual wall position, untouched.
- **Power: all three beacons on the same source.** Battery is fine — matched is
  what matters. The confound named in `COLOCATED_TX_0828.md` §6 is power source
  *differing between beacons*, so three on battery clears it exactly as well as
  three on mains, and three at one kitchen counter is achievable on battery and
  awkward on mains.

  Survival only has to reach the end of the scored window at t = 4,700 s, not
  the end of the capture. On 2026-08-28 the battery units ran 4,721 s and
  8,974 s; on 2026-08-29 they ran 18,138 s and 20,446 s. All clear 4,700 s
  comfortably.

  > **Edited 2026-08-29, after night 1 and before any night was scored.** The
  > original text read *"all three beacons on mains"* — a specification error,
  > written without checking it was physically achievable at POS4. **No
  > threshold, prediction or verdict in §3–§4 depends on power source**, and
  > none was changed. Recorded here rather than silently, because the rule
  > against editing above the Stage 2 banner exists precisely so that a change
  > like this has to be declared.
- Analysis window per night: **the first 2,400 s after the operator leaves the
  room, through +2,300 s.** 38 minutes, matching the 28 August window. Room
  unoccupied, all three transmitters live.
- **Raw. No `--ref-mac` on the primary arm**, so the headline figures do not
  depend on the reference correction that P2 is testing.

`BETWEEN_UNIT_SD = 0.00237` (`pc/exp_ambient_separation.py:79`). All σ figures
in this document are in those units.

---

## 3. Predictions, with thresholds frozen now

### P1 — the co-located pair stays collapsed

**Prediction: the B2–B3 raw centroid separation is below 1.0σ on at least
5 of 7 nights, on both receivers independently.**

Point estimate from 28 August: 0.7σ (s3), 0.2σ (d0wd).

### P2 — reference correction makes cross-receiver agreement worse

**Prediction: for at least 2 of 3 beacons, |s3 − d0wd| is larger after
reference-beacon correction than before it, by a factor of at least 2×, on at
least 5 of 7 nights.**

Point estimate from 28 August: B2 4× worse, B3 19× worse, B1 pinned by
construction. `COLOCATED_TX_0828.md` §4 records this as an unanticipated
observation with no frozen bar. This is that bar.

### P3 — the drift floor, and whether P1 is even interpretable

**Prediction: the night-to-night wander of a single co-located beacon's raw
SFO exceeds 1.0σ.**

`B3_MOVED.md:558` puts stationary-beacon wander at **2.5–4.9σ across a single
night**. If a beacon moves that much on its own, **P1's 1.0σ bar sits inside
the noise and P1 is uninterpretable as stated.**

This is the risk in this design and it is named before running rather than
discovered afterwards. The reason P1 may survive anyway: pair separation is a
*within-night, same-window* quantity, and drift shared between two beacons in
one room partially cancels in the difference. **That cancellation is an
assumption, not a measurement.** P3 is what tests it.

**If P3 fires and P1's separations also scatter above 1.0σ, the correct
reading is that this design cannot resolve the question — not that the room
conclusion is refuted.** Those are different outcomes and §4 keeps them apart.

---

## 4. Verdict table — frozen

| outcome | condition |
|---|---|
| **P1 HELD** | B2–B3 < 1.0σ on ≥ 5 of 7 nights, both receivers |
| **P1 REFUTED** | B2–B3 ≥ 1.0σ on ≥ 3 of 7 nights on either receiver, **and** P3 shows drift floor < 1.0σ |
| **P1 UNINTERPRETABLE** | P1 fails **and** P3 shows drift floor ≥ 1.0σ — the instrument cannot resolve the bar this design set |
| **P2 HELD** | ≥ 2 of 3 beacons worse by ≥ 2×, on ≥ 5 of 7 nights |
| **P2 REFUTED** | correction reduces or leaves unchanged the disagreement on ≥ 2 of 3 beacons, ≥ 5 of 7 nights |
| **P3 HELD** | single-beacon night-to-night raw SFO wander ≥ 1.0σ |

Any cell not meeting its condition and not meeting its opposite is reported as
**MIXED**, in those words, and is not resolved by choosing.

---

## 5. Controls

- **Both receivers, independently.** Every figure is computed twice. A result
  appearing on one receiver only is reported as receiver-specific, which
  `ROOM_OR_RADIO.md` §6.2 shows is a live failure mode here — B3 read +0.0552
  on s3 and +0.0048 on d0wd in the same window.
- **The third pair.** B2–B1 and B1–B3 are computed every night alongside
  B2–B3. If all three pairs collapse, the finding is about the room. If only
  the pair that collapsed before collapses again, that is a different and
  weaker claim.
- **Operator-present window.** The first ~10 minutes of each night are scored
  separately, as in `COLOCATED_TX_0828.md` §5. Not a prediction — a check that
  the unoccupied window is doing what it claims.

---

## 6. What would make me abandon the room conclusion

**If the co-located pair scatters above 1.0σ on most nights while the drift
floor stays below 1.0σ, the 28 August result was a coincidence** and the room
conclusion loses its load-bearing evidence. The 19.6σ and 7.9σ figures would
survive as observations but nothing same-instant would remain to support them.

Written here so it cannot be renegotiated later.

---

## 7. Temptations, recorded in advance

1. **Widening the 1.0σ bar** after seeing a night land at 1.1σ.
2. **Dropping a night** for a reason discovered after looking at its numbers.
   Exclusions must be for a stated physical cause — a beacon moved, a receiver
   rebooted — decided before the window is scored.
3. **Reporting P1 HELD when P3 fires**, which converts an uninterpretable
   result into a positive one. §4 separates these deliberately.
4. **Quoting the seven-night mean without the per-night spread.** The spread is
   the finding; the mean hides it.
5. **Letting P2 rescue the pass if P1 fails.** They are independent.

---

## 8. What this cannot answer

- **Thermal.** No temperature is measured — not outdoor, not indoor, not
  on-die. Seven more nights without a thermometer does not change that
  (`THERMAL_STEP.md:513`).
- **Whether device fingerprinting is possible on better hardware.** This is
  three ESP32s at 20 MHz in one apartment.
- **Anything about `pc/occ/`.** No occupancy figure is touched, computed, or
  cited here.
- **The cross-session identity result.** 29.7% against 33.3% chance stands and
  is not revisited.

---

## 9. Commands

Per night, both receivers, raw:

```
python pc\rff_offline.py data\raw\s3_<STAMP>.csv   --after <T0> --before <T0+2300>
python pc\rff_offline.py data\raw\d0wd_<STAMP>.csv --after <T0> --before <T0+2300>
```

P2 arm, same windows, adding `--ref-mac a4:f0:0f:77:91:20`.

`T0` is the first second after the operator leaves the room, read from the
capture log for that night and recorded in the §10 table before scoring.

---

## 10. Stage 2 — results

> **Nothing below this line existed when §1–§9 were written.**

### Night 1 — `20260829_025355`

**T0 recorded before scoring, per §9.** Operator statement: label set, then
straight to bed. **T0 = 0**, so the analysis window is **2,400 → 4,700 s
absolute** — identical to the 2026-08-28 window, which makes the two nights
directly comparable.

**Capture:** 26,644 s (7 h 24 m), both receivers. Single label at t = 23.8 s:
`"day 1 fan off ac starting on"`. Fan off and AC on is a **different airflow
and thermal condition** from the 28th, where the fan ran the whole capture.
Recorded, not corrected for.

**Protocol deviation — §2 as originally written was not met.** §2 has since been
corrected (see the note there): the requirement should have been *matched* power
across beacons, not mains. Night 1 still fails the corrected version, because B2
ran on mains while B1 and B3 ran on battery.

| beacon | frames (d0wd) | last frame | vs §2 |
|---|---:|---:|---|
| B2 `28:05` | 1,282,205 | **26,644 s** (full) | as specified |
| B3 `f4:2d` | 1,206,706 | **20,446 s** | died 6,198 s early |
| B1 `a4:f0` | 739,066 | **18,138 s** | died 8,506 s early |

§2 required all three on mains, both to survive the night and to clear the
power-source confound named in `COLOCATED_TX_0828.md` §6. Two beacons died,
same pattern as the 28th. **The confound §2 was written to remove is still
present on night 1.**

The window is unaffected — all three ran to 18,138 s, so 2,400–4,700 s sits
five hours inside the intact stretch and is scoreable as frozen. But P3's
between-night wander figure will carry the power confound until a night runs
with the condition actually met.

#### Night 1 scored — raw, no `--ref-mac`, window 2,400–4,700 s

| beacon | s3 | d0wd |
|---|---:|---:|
| B2 `28:05` | +0.0116 | +0.0009 |
| B3 `f4:2d` | +0.0197 | +0.0073 |
| B1 `a4:f0` | +0.0319 | +0.0248 |

Pairwise centroid separation:

| pair | s3 | d0wd |
|---|---:|---:|
| **B2 – B3** | **9.2σ** | **6.8σ** |
| B1 – B3 | 14.7σ | 18.2σ |
| B2 – B1 | 23.9σ | 25.0σ |

**P1 FAILS on night 1, on both receivers.** The bar was < 1.0σ; the pair reads
6.8σ and 9.2σ. On 2026-08-28 the same pair, same window length, same stated
arrangement, read **0.2σ and 0.7σ**.

**Per §4 this is one failing night, not a verdict.** REFUTED needs ≥ 3 of 7 and
requires P3 to show a drift floor below 1.0σ. Night 1 is recorded as a fail and
nothing is concluded from it.

#### Unpredicted, and it matters more than P1

Cross-receiver disagreement about the same transmitter, raw, co-located:

| beacon | 2026-08-28 | 2026-08-29 | change |
|---|---:|---:|---:|
| B2 | 0.0004 | **0.0107** | 27× worse |
| B3 | 0.0001 | **0.0124** | 124× worse |
| B1 | 0.0019 | 0.0071 | 3.7× worse |

**This is the result the case study leans on.** `ROOM_OR_RADIO.md` §6.3 reports
that co-locating the beacons made the two receivers agree to one part in ten
thousand, and it is presented there as same-instant and therefore drift-immune.
**On night 1 it did not reproduce.**

No bar was frozen for this, so it is an observation, not a scored prediction.
Three candidate explanations, none tested:

1. The beacons were not in the same arrangement as the 28th.
2. The environment differed — the operator logged `fan off ac starting on`,
   where the 28th ran with the fan on throughout.
3. **The 28 August agreement was n = 1 and may have been a coincidence** —
   which is the entire reason this series exists.

Nothing here is decided. Six nights remain.

---

### Night 2 — `20260830_013943`

> **§10.2a written before any separation for this night was computed.** T0, the
> window, the survival table and the §2 compliance note below were all fixed
> first, per §9. Scored figures follow in §10.2b.

**T0, per §9.** Single operator label in the capture, on **both** receivers
independently:

| receiver | first frame `pc_time_us` | label | t |
|---|---:|---|---:|
| d0wd | 1788071983261443 | `going to bed` | **3,120.4 s** |
| s3 | 1788071983195716 | `going to bed` | **3,120.5 s** |

The two receivers place the same event 0.1 s apart on their own per-file
origins, which is what should happen if they share a host clock and started
together. **T0 = 3,120 s.**

Night 1's T0 was 0 because the operator labelled and went straight to bed. Night
2 ran for 52 minutes with the operator up, so the window is **not** the same
absolute slice as nights 1 and the 28th:

**Analysis window: 5,520 → 7,820 s absolute** (T0 + 2,400 through T0 + 4,700),
same 2,300 s length as every other night in the series.

**Capture:** 23,557 s (6 h 32 m), both receivers.

| beacon | frames (d0wd) | frames (s3) | last frame | clears window? |
|---|---:|---:|---:|---|
| B2 `28:05` | 1,162,333 | 1,686,964 | **23,557 s** (full) | yes |
| B1 `a4:f0` | 980,760 | 1,878,581 | 22,047 s | yes |
| B3 `f4:2d` | 1,037,134 | 1,837,110 | 21,081 s | yes |

**All three clear the scored window by more than 13,000 s.** This is the first
night of the series where no beacon died anywhere near the window — on night 1
two died at 18,138 s and 20,446 s, still clear but by less.

**§2 compliance: not met, same as night 1.** §2 requires all three beacons on a
**matched** power source. The operator's stated arrangement for this night was
**one wired, two on battery** — three beacons, two sources. The confound named
in `COLOCATED_TX_0828.md` §6 is therefore still present, for the second night
running.

**Physical-vs-label caveat, recorded rather than resolved.** The operator states
the wired unit is B1. By last-frame survival the longest-running MAC is
`28:05` (B2), full capture, exactly as on night 1. Those disagree.
`ROTATION_PREREG.md` §0.0.1 already records that the repo's B1/B2/B3 labels have
never been tied to physical hardware, so this is the known labelling ambiguity
and not new evidence about anything. **Nothing was moved or relabelled to make
them agree.** Every figure below is keyed on MAC, which is unambiguous.

**Fan: on**, for the whole capture — the fan A/B result (`FAN_AB_PREREG.md`)
implicates the fan at ~0.6σ, so it is held constant across the series rather
than left to vary. Night 1 ran fan off with AC starting. **Nights 1 and 2 differ
in fan state**, which is a difference between them and is not corrected for.

#### Deviation from §9, declared — byte-sliced input, and the check that it is harmless

The two night-2 captures are 2.7 GB and 4.5 GB. Neither completes inside the
available run time, so each was **byte-sliced to a window with a 520 s lead-in**
(absolute 5,000 s → 7,820 s) and `rff_offline` run on the slice with `--after` /
`--before` shifted onto the slice's own origin. `QUALITY_GATE_PREREG.md` §7.0.3
records that slicing resets the phase-unwrap continuity anchor and cost 0.1σ
there, so this is a known hazard, not a free operation.

**It was tested rather than assumed.** d0wd was re-sliced with a **2,020 s
lead-in** — four times longer — and re-run:

| lead-in | B2 | B1 | B3 | B2–B3 |
|---|---:|---:|---:|---:|
| 520 s | +0.0065 | +0.0012 | +0.0795 | 60.6σ |
| 2,020 s | +0.0065 | +0.0012 | +0.0795 | 60.6σ |

Identical to every reported digit, and identical window counts. **On this
capture the anchor is fully converged well before the scored window and the
slice is not doing anything to the numbers.** This does not generalise to other
files; it is a check on these.

#### Night 2 scored — raw, no `--ref-mac`, window 5,520–7,820 s

| beacon | s3 | d0wd |
|---|---:|---:|
| B2 `28:05` | +0.0249 | +0.0065 |
| B3 `f4:2d` | +0.0204 | **+0.0795** |
| B1 `a4:f0` | +0.0152 | +0.0012 |

Pairwise centroid separation:

| pair | s3 | d0wd |
|---|---:|---:|
| **B2 – B3** | **3.4σ** | **60.6σ** |
| B1 – B3 | 4.2σ | 65.7σ |
| B2 – B1 | 7.6σ | 5.0σ |

**P1 FAILS on night 2, on both receivers.** The bar is < 1.0σ. The pair reads
3.4σ and 60.6σ. **That is two failing nights out of two.**

Per §4, REFUTED needs ≥ 3 of 7 on either receiver **and** a drift floor below
1.0σ from P3. Neither condition is met yet. Night 2 is recorded as a fail and
nothing is concluded from it.

**The closest pair is no longer the same pair, and the two receivers disagree
about which it is.** On 28 August the closest pair was B2–B3 (0.2σ / 0.7σ). On
night 1 it was still B2–B3 (6.8σ / 9.2σ). On night 2 it is **B2–B3 on s3
(3.4σ) but B2–B1 on d0wd (5.0σ)**. §5's third-pair control was written to catch
exactly this: the identity of the close pair is not stable across nights or
across receivers, which weakens any reading in which one specific pair of boards
is alike.

#### The d0wd B3 figure is a 30% remnant, and that is stated before it is used

`+0.0795` is roughly ten times any B3 value previously recorded on this receiver
(night 1 d0wd: +0.0073). Before treating it as a measurement, the frame yield:

| receiver | beacon | frames in window | windows | frames in windows | yield |
|---|---|---:|---:|---:|---:|
| d0wd | B2 | 112,920 | 1,741 | 111,424 | 98.7% |
| d0wd | B1 | 102,086 | 1,569 | 100,416 | 98.4% |
| d0wd | **B3** | **111,219** | **523** | **33,472** | **30.1%** |
| s3 | B2 | 169,998 | 2,624 | 167,936 | 98.8% |
| s3 | B1 | 200,738 | 3,111 | 199,104 | 99.2% |
| s3 | **B3** | **204,245** | **3,183** | **203,712** | **99.7%** |

**Roughly 70% of B3's frames on d0wd fail the shipped `--min-inlier 0.6` floor**
— 78,000 of the run's 80,913 total inlier rejections are B3's. The same
transmitter, in the same instants, yields 99.7% on s3.

**It is not a signal-strength effect.** B3 is the *strongest* of the three on
d0wd in this window at −73.3 dBm mean, against −75.2 (B2) and −77.8 (B1).

So the 60.6σ is **a 30% surviving remnant of B3 against near-complete
populations of B1 and B2** — structurally the same object as
`QUALITY_GATE_PREREG.md` §7.1a, where B2 lost 96% of its windows on this same
receiver and the resulting separation was ruled **UNEVALUABLE** rather than
reported. The beacon that gets destroyed has changed; the receiver has not.

**How this is scored.** P1 fails on night 2 regardless — s3's figure is a clean
99.7%-yield 3.4σ and it is already over the bar, so the verdict does not rest on
the d0wd remnant.

#### CORRECTION — the remnant was tested and it is representative

The paragraph originally written here read: *"The d0wd 60.6σ is recorded and is
not used as a magnitude for anything. Reporting it as 'sixty sigma apart' would
be quoting a number whose population is 30% of one beacon."*

**That was a reasonable suspicion and it is wrong.** It was written from the
shape of the yield table by analogy to `QUALITY_GATE_PREREG.md` §7.1a, without
running the test that distinguishes the two cases. The test is one flag.

Lowering `--min-inlier` admits the rejected frames. If the surviving 30% were an
unrepresentative branch, the centroid would move when the other 70% come back.
d0wd, chunk 9,700–10,900 s:

| `--min-inlier` | B3 windows | B3 SFO | B2 SFO | B1 SFO |
|---:|---:|---:|---:|---:|
| 0.2 | 702 | **+0.0764** | +0.0069 | +0.0014 |
| 0.4 | 701 | **+0.0766** | +0.0069 | +0.0014 |
| 0.6 *(shipped)* | 215 | **+0.0769** | +0.0069 | +0.0013 |
| 0.9 | **0** | — | +0.0068 | +0.0012 |

**Admitting 3.3× as many windows moves B3's centroid by 0.0005 — a fifth of one
σ.** The remnant is representative. This is the opposite of §7.1a, where B2's
centroid shifted and its spread tripled.

Repeated on the scored window itself, at `--min-inlier 0.4` (B3: 523 → 1,734
windows, full yield):

| quantity | shipped gate 0.60 | gate 0.40 |
|---|---:|---:|
| B3 centroid | +0.0795 | **+0.0797** |
| B2 – B3 | 60.6σ | **22.7σ** |
| B2 – B1 | 5.0σ | **1.9σ** |

**The centroids are robust; the σ figures are not.** Separations shrink by ~2.7×
because admitting noisier windows inflates the pooled covariance that σ is
measured in. Both readings are far over P1's 1.0σ bar, so the verdict is
unchanged either way — but **60.6σ should not be quoted as a magnitude, and the
reason is gate-sensitivity of the denominator, not an unrepresentative
population.** The corrected statement of the d0wd result is: *B2 and B3 are
separated by 0.073 rad/subcarrier, which is 22.7σ at a 0.40 inlier floor and
60.6σ at the shipped 0.60.*

#### The disagreement is stable all night, on both receivers, in opposite ways

Same beacon, same instants, both receivers, raw:

| absolute window | d0wd B3 | d0wd windows | s3 B3 | s3 windows |
|---|---:|---:|---:|---:|
| 1,200 – 2,100 s | +0.0423 *(IQR 0.0164)* | 663 | **+0.0204** | 1,187 |
| 5,520 – 7,820 s *(scored)* | +0.0795 | 523 | **+0.0204** | 3,183 |
| 10,000 – 10,900 s | +0.0769 | 215 | **+0.0201** | 1,243 |
| 14,000 – 14,900 s | +0.0786 | 236 | — | — |
| 18,000 – 18,900 s | +0.0781 | 238 | — | — |

**s3 reads B3 flat at +0.020 for the whole night. d0wd reads the same
transmitter climbing from +0.042 to +0.078 and then holding.** Neither is
noisy — d0wd's IQR after the first hour is 0.0017–0.0019.

Checked and ruled out as explanations: channel (both `ch=6`), CSI payload length
(both `len=256`), noise floor (both −96.00 dBm exactly), and RSSI — B3 is the
**strongest** of the three on d0wd at −73.3 dBm.

**This is the finding of night 2, and it is larger than P1.** A sampling-clock
offset is a property of a transmitter–receiver *pair*, so the two receivers are
not obliged to agree — but d0wd's own readings for B1 and B2 are flat and low
across the same night, so d0wd's clock is not wandering. Something specific to
the d0wd↔B3 path produced a 0.056 rad/subcarrier disagreement that persisted
for six hours.

**No explanation is offered here and none should be assumed.** It was B2 that
degraded on this receiver on 28 August and B3 on 30 August, which is a pattern
worth a prereg of its own rather than a guess in this one.

**The two receivers are ~12 inches apart** — operator statement, 2026-08-30.
Recorded here because it changes how surprising the paragraph above is, and
flagged because **no artifact in this repo records the receiver separation**.
`NODE_CENSUS.md` I3–I4 states plainly that the only coordinates in the codebase
are interactive defaults in `pc/heatmap.py` and are not a record of where
hardware sat, and that the RSSI evidence proves the antennas were in different
places while saying nothing about where. **A foot is an operator's memory, not a
measurement**, and nothing below depends on the exact figure — only on the two
receivers being close rather than in different rooms.

#### RSSI asymmetry between the receivers, scored window

Mean RSSI per beacon, same window, same frames:

| beacon | s3 | d0wd | s3 − d0wd |
|---|---:|---:|---:|
| B1 `a4:f0` | −66.9 | −77.8 | **+10.9 dB** |
| B3 `f4:2d` | −62.7 | −73.3 | **+10.6 dB** |
| B2 `28:05` | −72.1 | −75.2 | **+3.1 dB** |

**Absolute RSSI is not comparable across the two boards** — different silicon,
different calibration, and no cross-calibration exists. What survives a constant
per-receiver offset is the *shape*: whatever that offset is, it cancels in the
comparison between rows. **s3's advantage over d0wd is ~11 dB for two beacons
and 3 dB for the third.** That is a 7.8 dB spread in relative gain across three
transmitters that sit on one surface, seen by two receivers a foot apart.

`NODE_CENSUS.md` §4 already records up to **9.7 dB** between the two receivers
on a single transmitter, so the magnitude is in family with what this bench has
done before. What is new is that it is **not the same for all three beacons on
the same night**, which is not a property either receiver can have on its own.

Not scored, not predicted, and not explained. Recorded because it is the only
measured quantity that distinguishes the two receivers on the night they
disagreed by a factor of four.

#### §2 arrangement compliance — confirmed by photograph, 2026-08-30

A photograph was taken the morning after night 2 and inspected. Operator
statement accompanying it:

> *"2 rx on the wall in corner above my pc like they've always been. middle of
> room is the same fan that's always been there. left side of photo is 3 esps
> sitting on the bar in their same spots."*

**§2's arrangement requirement is met. Nothing moved between night 1 and night
2** — not the beacons, not the receivers, not the fan. This is the first
independent check on that clause in the series; every previous night rested on
recollection alone.

An earlier reading of the same photograph — that the beacons sat at differing
heights and the receivers were split between wall and desk — **was wrong and is
recorded as wrong.** It was inferred from LED positions and shadow in a dark
photograph and contradicted by the operator, who built the bench. It is written
down because it nearly became a physical explanation for §10.2's anomaly, and a
wrong explanation that feels physical is worse than none.

#### What actually changed between night 1 and night 2 — and what did not

> **CORRECTED 2026-08-30, after this section was first written.** The table
> below originally carried a column reading **"fan: on both"** for all three
> rows. **That is false, and it contradicted a paragraph forty lines above it in
> this same section**, which correctly records night 1 as `fan off ac starting
> on` and night 2 as fan on throughout. The error was caught by the operator
> asking whether the fan A/B data could explain nights 1 and 2 — a question that
> only makes sense if the fan differed between them. The original wording is
> quoted here rather than deleted.

Changes between night 1 and night 2:

| beacon | power night 1 | power night 2 | position | fan |
|---|---|---|---|---|
| B2 `28:05` | mains | battery | unchanged | **off → on** |
| B1 `a4:f0` | battery | mains | unchanged | **off → on** |
| **B3 `f4:2d`** | **battery** | **battery** | **unchanged** | **off → on** |

**B3's power and position did not change. The fan did, for all three.** B3 is
therefore a control on the power and position axes only — not, as first written,
on everything.

#### The fan is ruled out by measurement, not by assumption

The fan is the one environmental variable known to differ between the two
nights, so it is the first candidate for §10.2's divergence. It was tested
against the existing fan A/B capture (`20260829_122648`, `FAN_AB_PREREG.md`),
which contains a clean OFF → ON → OFF reversal with operator labels.

d0wd, raw, by fan segment:

| segment | window | B3 SFO | B3 windows | B2 | B1 |
|---|---|---:|---:|---:|---:|
| fan OFF | 1,350 – 2,240 s | **+0.0023** | 689 | +0.0027 | +0.0102 |
| fan ON | 2,310 – 3,270 s | **+0.0026** | 823 | +0.0025 | +0.0086 |
| fan OFF | 3,290 – 4,200 s | **+0.0025** | 838 | +0.0020 | +0.0096 |

**d0wd's B3 does not move with the fan — 0.0003 across a full reversal, against
the 0.0722 that needs explaining. Its yield stays healthy with the fan running**
(823 windows fan-on, the highest of the three segments), against the 30.1% seen
on night 2 with the fan also running.

s3 over the same fan-ON segment reads B3 at +0.0083, and the two receivers agree
to 0.0057 — a normal-sized disagreement for this bench, not a factor of four.

**Caveat, stated because it limits the conclusion:** the fan A/B capture was
recorded with the beacons *spread at the desk*, not at POS4 on the bar. The fan
state is exactly matched to night 2; the geometry is not. So this rules the fan
out **as a sufficient cause on its own** and does not exclude a fan-plus-geometry
interaction that only exists at POS4.

**What survives:** the fan changed between nights 1 and 2, and the fan does not
do this to d0wd's B3 when tested directly. The divergence still has no candidate
explanation.

#### Outside the scored window — the full night, both nights, to battery death

The scored window is 2,300 s of a six-hour capture. **Everything outside it was
already recorded and had never been looked at.** Operator's question, and the
right one: does the pattern hold until the batteries die?

d0wd, B3, raw. Windows are 900 s except the scored rows.

| night 1 (fan off) | B3 SFO | windows | | night 2 (fan on) | B3 SFO | windows |
|---|---:|---:|---|---|---:|---:|
| 1,000 – 1,900 s | +0.0063 | 810 | | 1,200 – 2,100 s | +0.0423 *(IQR 0.0164)* | 663 |
| 2,400 – 4,700 s *(scored)* | +0.0073 | — | | 5,520 – 7,820 s *(scored)* | +0.0795 | 523 |
| 5,000 – 5,900 s | +0.0073 | 779 | | 10,000 – 10,900 s | +0.0769 | 215 |
| 9,000 – 9,900 s | +0.0076 | 734 | | 14,000 – 14,900 s | +0.0786 | 236 |
| 13,000 – 13,900 s | +0.0077 | 823 | | 18,000 – 18,900 s | +0.0781 | 238 |
| 17,000 – 17,900 s | +0.0077 | 829 | | — | | |
| 19,500 – 20,400 s | +0.0068 | 1,090 | | 20,100 – 21,000 s | **+0.0805** | 212 |
| **B3 battery dies 20,446 s** | | | | **B3 battery dies 21,081 s** | | |

**Yes — it holds to the last frame.** Night 2's B3 reads +0.0805 in the final
900 s before its battery dies, with the same collapsed yield it had fifteen
thousand seconds earlier. There is no decay toward normal, no drift, and no sign
that a sagging battery is doing it.

**And night 1 never goes there at all.** +0.0063 to +0.0077 across 5.5 hours,
full yield throughout, right up to its own battery death. So night 2 is not
night 1 with a later onset that the scored window happened to catch — **night 1
had no onset.** The two nights are different in kind, not in phase.

The window after B3 dies on night 2 (21,100 – 22,300 s) shows B2 at +0.0059 and
B1 at +0.0005, both normal and both healthy — **the receiver is fine after the
affected transmitter goes off air**, which is one more thing a broken receiver
would not do.

#### Onset — and a hint about D2 that must not be allowed to score D2

Night 2's first sampled chunk, 1,200 – 2,100 s, is caught mid-transition:
**offset already elevated at +0.0423, IQR eight times its later value at 0.0164,
and yield still near-full at 663 windows.** By the scored window it is +0.0795
with yield collapsed.

**The offset moved before the yield collapsed.** That is direct evidence against
treating them as one phenomenon — which is exactly what `RECEIVER_DIVERGENCE_PREREG.md`
D2 was frozen to test.

**This is discovery data and it does not score D2.** It was found by looking
after the fact at a night whose numbers are already known, which is the thing
pre-registration exists to prevent counting. It is recorded here so that if
night 3 splits D2, nobody can claim the split was a surprise — and so that if
night 3 does *not* split it, this observation is on the record as having pointed
the wrong way.

Raw SFO for B3 across the two nights:

| receiver | night 1 | night 2 | change |
|---|---:|---:|---:|
| s3 | +0.0197 | +0.0204 | **+0.0007** |
| d0wd | +0.0073 | +0.0795 | **+0.0722** |

**s3 says the beacon that did not change did not change** — 0.3 raw SD units
across 27 hours, which is inside the drift floor and is what a stationary,
unmodified transmitter should look like. **d0wd says it moved by 30 SD units.**

This substantially weakens any reading in which d0wd's +0.0795 is a property of
B3. The one beacon with no altered variable is the one d0wd disagrees about
most, and the receiver that disagrees is the one with the anomalous frame yield.

**It is not proof that d0wd is wrong.** SFO is a pair quantity and a path can
change without hardware changing. But it inverts the burden: the claim now
needing evidence is that a physically untouched beacon shifted 30σ on one
receiver and 0.3σ on the other, in the same instants.

Separately, and not pursued here: **on both nights, on both receivers, the
mains-powered beacon has the lowest raw SFO** — d0wd +0.0009 (B2, night 1) and
+0.0012 (B1, night 2); s3 +0.0116 and +0.0152. Two nights is two points and the
pairwise separations do not follow the same rule, so this is logged as something
to look at, not a finding. It is exactly the confound `COLOCATED_TX_0828.md` §6
named and §2 has failed to remove twice.

#### P2 arm — reference correction, same windows

Reference-corrected SFO (`--ref-mac a4:f0:0f:77:91:20`):

| beacon | s3 | d0wd |
|---|---:|---:|
| B2 | +0.0096 | +0.0053 |
| B3 | +0.0052 | +0.0784 |
| B1 *(reference)* | −0.0000 | +0.0001 |

Cross-receiver disagreement, |s3 − d0wd|:

| beacon | raw | corrected | effect of correction |
|---|---:|---:|---|
| B2 | 0.0184 | 0.0043 | **4.3× better** |
| B3 | 0.0591 | 0.0732 | 1.24× worse |
| B1 | 0.0140 | 0.0001 | pinned to zero **by construction** — not evidence |

**P2 FAILS on night 2.** The bar is ≥ 2 of 3 beacons worse by ≥ 2×. B1 cannot
get worse — it is the reference and is forced to zero on both receivers by the
arithmetic — so the prediction effectively requires **both** B2 and B3. B2 got
4.3× *better* and B3 worsened by only 1.24×, short of the 2× bar.

This is the opposite of the 28 August point estimate (B2 4× worse, B3 19×
worse) and it goes on the record as such. **B1's pinning must not be counted
toward the REFUTED side either** — a quantity fixed at zero by construction is
not an observation, and §4's "≥ 2 of 3" wording does not exclude it. That is a
defect in §4's wording, noted now, and it is not silently used in either
direction.

#### The unpredicted observation from night 1 has continued, and got worse

Cross-receiver disagreement about the same transmitter, raw, co-located:

| beacon | 28 Aug | night 1 | night 2 | night 2 vs 28 Aug |
|---|---:|---:|---:|---:|
| B2 | 0.0004 | 0.0107 | **0.0184** | 46× worse |
| B3 | 0.0001 | 0.0124 | **0.0591** | 591× worse |
| B1 | 0.0019 | 0.0071 | **0.0140** | 7.4× worse |

**All three beacons, both nights, monotonically worse.** `ROOM_OR_RADIO.md` §6.3
presents the 28 August agreement — one part in ten thousand — as the
same-instant, drift-immune result. It has now failed to reproduce twice, and the
gap is widening rather than scattering.

Still no frozen bar for this, so it remains an observation. But it is no longer
a single non-replication: **it is a trend across every beacon on every night
since, and the 28 August figure is looking more like the outlier than the
baseline.** B3's night-2 number is contaminated by the 30% yield above; B1's and
B2's are not, and they move the same way.

---

### Night 3 — `20260831_020408`

> **§10.3a written before any figure for this night was computed. T0 is
> unresolved at the time of writing and is marked as such rather than
> chosen.**

**Capture:** started 02:04:08, ran **16,821 s (4 h 40 m)**, both receivers.
Two aborted starts at 02:03:37 and 02:03:50 (6 s and 12 s) precede it, plus a
zero-byte `s3_20260831_020350.csv`; these are the operator finding the right
COM ports and are not analysed.

**No operator label exists in either file.** Nights 1 and 2 each carried one
(`day 1 fan off ac starting on`, `going to bed`). §9 requires T0 to be read
from the capture log for that night and written here before scoring. **There
is no log entry to read.** T0 is therefore recorded as **UNRESOLVED — pending
operator statement**, and no window has been scored.

#### Survival — and the reason this night is degraded

| beacon | stated power | frames (d0wd) | last frame (d0wd) | last frame (s3) |
|---|---|---:|---:|---:|
| B2 `28:05` | battery | 1,059,568 | **16,821 s** (full) | 16,540 s |
| B3 `f4:2d` | battery | 610,195 | **9,059 s** | 8,779 s |
| **B1 `a4:f0`** | **mains** | 72,844 | **1,769 s** | **1,489 s** |

**B1 stopped transmitting after roughly 25 minutes**, on both receivers
independently, on the night it was stated to be the wired unit. A mains unit
does not run out of battery. This is a disconnection, a reset, or a power
assignment that differs from the one recorded — it is not characterised here
and must not be guessed at.

**The scored window is T0 + 2,400 through T0 + 4,700. For any T0 ≥ 0, B1 is
already off air before the window opens.** Consequences, fixed before any
figure was computed:

| item | night 3 status |
|---|---|
| **P1** — B2–B3 separation | **scoreable** (B3 lives to 9,059 s) |
| **P2** — reference correction | **UNRUNNABLE.** The reference beacon is `a4:f0:0f:77:91:20`. It is not transmitting during the window, so the arm cannot be computed at all. |
| §5 third-pair control (B2–B1, B1–B3) | **unavailable** |
| `RECEIVER_DIVERGENCE` D1–D3 | **scoreable** — all three concern B3 |
| `RECEIVER_DIVERGENCE` D4 (one victim at a time) | **degraded** — a three-beacon claim with two beacons |

**Per §7 temptation 2**, this is *not* an exclusion. The night is recorded, P1
is scored if T0 resolves, and P2 is reported as **UNRUNNABLE for night 3 for a
stated physical cause** — not as a fail, and not as a pass.

**A third consecutive night in which `28:05` outlives the others.** It ran the
full capture on all three nights while the beacon named as wired changed twice.
`ROTATION_PREREG.md` §0.0.1's labelling ambiguity remains open and this is now
three data points in the same direction. Still not resolved here; still keyed
on MAC everywhere.

#### RETRACTED — the "B1 was powered and hung" finding, withdrawn within the hour

**A section previously stood here claiming B1 ran the night powered but
silent, and that this invalidated the word "died" throughout §10.** It was
written from an ambiguous operator message — *"b1 is showing its on… but huh
look at that its frozen on the s3's screen"* — which was read as *B1's own LED
is lit.*

**On being asked directly, the operator's answer was: "b2 is powered, b1
showing dead."** B1 is a battery unit and it was flat. There was no hang.

The original text is not preserved because it asserted a physical state that
did not exist and would be quotable out of context. What it concluded —
that every "died" in this document was unsound, that the power inference was
withdrawn, that nights 1 and 2 needed re-reading — **is all withdrawn.**

**This is the failure `QUALITY_GATE_PREREG.md` §7.1b named this morning, three
hours before committing it: a correction inherits no authority from being a
correction.** A cascade of retractions was written across a whole document on
the strength of one ambiguous clause, without asking what it meant. Asking
took one message.

**Mode B** in `.astory/ERROR_LOG.md` — a source characterised without being
opened. The source here was the operator, and the fix was to ask him.

**What survives, and it is genuinely separate:** `record_source`
(`csi_rx/main/main.c:217-239`) updates a MAC's RSSI on every frame and
**never ages an entry out** — no `last_seen`, no timeout, no stale marking
anywhere in the file. A beacon that stopped transmitting at 02:30 still shows
its last RSSI on page 2 at 07:00. That is a real latent defect, verified in
the code, and it belongs on the pile with `TELEMETRY_SERIAL_RACE.md`. **It was
not the cause of what the operator saw**, and it is recorded here as a defect
rather than as an explanation.

#### The actual night-3 anomaly: a battery that lasted 25 minutes

B1 ran **1,769 s (d0wd) / 1,489 s (s3)** on night 3. The same unit ran
**18,138 s** on night 1 — a factor of ten.

That is the open question for this night, and it is a hardware-maintenance one
rather than a measurement one: flat cell, degraded cell, or not charged before
the run. **Nothing in the capture can distinguish those.** No power telemetry
is collected from the beacons; the only evidence a battery leaves in this
system is when it stops.

#### Power assignment — settled at the bench, 2026-08-31

**Operator statement, made at the hardware, with the nodes now physically
marked:** *"I didn't move anything. B2 is on power."* The powered node has
been the same node throughout.

This supersedes the night-2 statement recorded in §10.2 (*"b1 wired b2 battery
b3 battery"*), given at ~05:00 from memory. **The bench observation wins**: it
was made in front of the hardware, and the boards have since been labelled so
the question cannot recur.

**With that settled, the picture simplifies and improves:**

- Power assignment was **constant across all three nights** — `28:05` on mains,
  `a4:f0` and `f4:2d` on battery. Not a changing violation of §2, the same one
  three times.
- **The only variable that changed between nights 1 and 2 was the fan**, which
  was tested directly and eliminated (§10.2, OFF→ON→OFF moves d0wd's B3 by
  0.0003 against the 0.0722 needing explanation).
- **B3 becomes the clean accidental control it was first described as** — power,
  position and now everything but the fan held constant, and the fan ruled out.

**The night-2 "what changed" table in §10.2 is wrong on its power rows.** It
shows B2 mains→battery and B1 battery→mains between nights 1 and 2. Neither
swap happened. It is left in place with this note against it, per the rule
that corrections go alongside the original rather than over it.

**T0 for night 3, recorded before any figure was computed: T0 = 0, declared.**
No operator label exists in either file; §9's normal source does not exist for
this night. Capture began 02:04:08, the operator's last recorded activity was
~01:50, and night 1 set the precedent for a start-and-sleep capture. **Window:
2,400 → 4,700 s absolute.** Declared as a choice, not read from a log, and
marked as such so it is never quoted as though it were logged.

#### Did anything physically move? RSSI says: not answerable, but no swap signature

Mean RSSI per beacon, window 600–1,400 s, all three nights:

| receiver | night | B1 `a4:f0` | B2 `28:05` | B3 `f4:2d` |
|---|---|---:|---:|---:|
| d0wd | 1 | −74.2 | −74.0 | −66.7 |
| d0wd | 2 | −79.9 | −76.8 | −72.4 |
| d0wd | 3 | −77.8 | −73.8 | −68.0 |
| s3 | 1 | −73.9 | −66.6 | −66.2 |
| s3 | 2 | −67.6 | −71.8 | −64.3 |
| s3 | 3 | −66.9 | −66.1 | −62.9 |

**Night-to-night variation reaches 6 dB and is not uniform** across beacons or
receivers — on s3, B1 gains 6.3 dB from night 1 to night 2 while B2 loses
5.2 dB; on d0wd all three drop together by 3–6 dB over the same interval.

**This does not establish that anything moved, and it does not establish that
nothing did.** Multipath in an occupied apartment moves this much on its own,
and the fan state differs between night 1 and the others.

What it does rule out is the specific worry that prompted it: **there is no
clean exchange signature.** Two boards swapping physical positions would show
their RSSI values trading places on *both* receivers together. On s3 something
that shape appears between nights 1 and 2; on d0wd it does not. **MAC addresses
are burned into silicon and cannot change**, so the identity of each
transmitter in the data is not in question — only which physical object the
operator calls B1, B2 and B3, which is the ambiguity `ROTATION_PREREG.md`
§0.0.1 has recorded since before this series began.

**Recorded as unresolved. Every figure in this document is keyed on MAC and
none of them depend on it.**

#### Night 3 scored — raw, no `--ref-mac`, window 2,400–4,700 s

| beacon | s3 | d0wd |
|---|---:|---:|
| B2 `28:05` | +0.0112 | +0.0046 |
| B3 `f4:2d` | +0.0189 | +0.0174 |
| B1 `a4:f0` | *off air* | *off air* |

| pair | s3 | d0wd |
|---|---:|---:|
| **B2 – B3** | **14.6σ** | **17.9σ** |

**P1 FAILS on night 3, both receivers. That is three failures out of three.**

**P1 can no longer reach its threshold.** §3 requires B2–B3 below 1.0σ on
**5 of 7** nights. Three have failed and four remain, so the maximum
achievable is 4. **The bar is now arithmetically unreachable**, which §4 does
not have a name for. It is not REFUTED — §4 reserves that for a failure
accompanied by a drift floor below 1.0σ, and P3 has not been computed. The
correct statement is: **P1 has failed every night it was tested and cannot
now pass. The remaining nights characterise how, not whether.**

**P2 is UNRUNNABLE for night 3** — the reference beacon was off air. Not a
fail, not a pass.

#### The night-2 divergence has ended — D1 REVERTED

Scored against `RECEIVER_DIVERGENCE_PREREG.md`, bars frozen before this
capture existed:

| | bar | night 2 | night 3 | verdict |
|---|---|---:|---:|---|
| **D1** d0wd B3 offset | REVERTED ≤ +0.030 | +0.0795 | **+0.0174** | **REVERTED** |
| **D2** d0wd B3 yield | > 90% if reverted | 30.1% | **97.4%** | **HOLDS** |
| **D3** s3 B3 within ±0.0030 of +0.0204 | — | +0.0204 | **+0.0189** *(Δ 0.0015)* | **HOLDS** |
| **D4** ≤1 beacon under 50% yield on d0wd, none on s3 | — | — | **zero under 50%** | **holds, degraded** — two beacons, not three |

Full yields, window 2,400–4,700 s:

| receiver | beacon | frames | windows | yield |
|---|---|---:|---:|---:|
| d0wd | B3 | 167,573 | 2,551 | **97.4%** |
| d0wd | B2 | 147,599 | 2,280 | 98.9% |
| s3 | B3 | 206,801 | 3,218 | 99.6% |
| s3 | B2 | 201,153 | 3,143 | 100.0% |

**Per §5's verdict table this is the episodic outcome: the night-2 state had an
onset and an end.** Neither account in §2 is excluded — a path condition that
cleared and an estimator that recovered look identical from here — but the
effect is now known to be transient rather than a standing property of the
d0wd↔B3 pair. That is a handle neither account had before.

**D2 is the informative one.** §4 named a split — offset reverting while yield
stayed collapsed, or the reverse — as the outcome that would refute treating
them as one phenomenon. **They moved together**: 30.1% → 97.4% alongside
+0.0795 → +0.0174. The discovery-set hint recorded in §10.2, that the offset
moved *before* the yield collapsed on night 2, pointed the other way and is
not supported by the held-out night.

#### The "monotonically worse" trend is broken

§10.2 recorded cross-receiver disagreement worsening on every beacon on every
night, and said the 28 August agreement was "looking more like the outlier
than the baseline." Night 3 refutes that:

| beacon | 28 Aug | night 1 | night 2 | **night 3** |
|---|---:|---:|---:|---:|
| B2 | 0.0004 | 0.0107 | 0.0184 | **0.0066** |
| B3 | 0.0001 | 0.0124 | 0.0591 | **0.0015** |
| B1 | 0.0019 | 0.0071 | 0.0140 | *off air* |

**B3's disagreement fell 39× and is now within 15× of the 28 August figure
rather than 590×.** Two points do not make a trend and three did not either.
That reading is withdrawn.

---

### Night 4 — `20260901_035805`

> **§10.4a written before any figure for this night was computed.**

**Capture:** started 03:58:05, ran **12,225 s (3 h 24 m)**, both receivers. Shorter
than nights 1–3 (26,644 / 23,557 / 16,821 s) but more than twice the length
needed to cover the scored window.

**No operator label in either file**, as on night 3. **T0 = 0, declared** on the
same basis and recorded before scoring: no log entry exists to read, and the
night-3 precedent for a start-and-sleep capture applies. **Window: 2,400 →
4,700 s absolute.** Declared as a choice, not read from a log.

#### Survival — every beacon ran to the end

| beacon | frames (d0wd) | frames (s3) | last frame | clears window? |
|---|---:|---:|---:|---|
| B2 `28:05` | 626,709 | 956,380 | **12,225 s** | yes |
| B3 `f4:2d` | 628,233 | 1,007,470 | **12,225 s** | yes |
| B1 `a4:f0` | 425,233 | 1,024,358 | **12,225 s** | yes |

**All three transmitted for the entire capture on both receivers.** This is the
first night of the series where nothing died, and it is the direct result of
the batteries being charged before the run — a deliberate operator change from
night 3, where B1 stopped after 1,769 s.

**That change is recorded as restoring the intended condition rather than
introducing a new one.** §2 requires all three transmitting through the scored
window; nights 1, 2 and 3 each met that by margin or not at all, and night 4
meets it outright.

**Consequences, fixed before any figure was computed:**

| item | night 4 status |
|---|---|
| **P1** — B2–B3 separation | scoreable |
| **P2** — reference correction | **RUNNABLE — first time since night 2.** B1 `a4:f0` transmits throughout. |
| §5 third-pair control | **available** — all three pairs computable |
| `RECEIVER_DIVERGENCE` D1–D3 | scoreable |
| **D4** — one victim at a time | **fully scoreable** for the first time; night 3 was degraded to two beacons |

#### Night 4 scored — raw, no `--ref-mac`, window 2,400–4,700 s

| beacon | s3 | d0wd | \|s3 − d0wd\| |
|---|---:|---:|---:|
| B2 `28:05` | +0.0121 | +0.0025 | 0.0096 |
| B3 `f4:2d` | +0.0188 | **+0.0447** | 0.0259 |
| B1 `a4:f0` | +0.0063 | **+0.0597** | **0.0534** |

| pair | s3 | d0wd |
|---|---:|---:|
| **B2 – B3** | **9.5σ** | **14.9σ** |
| B2 – B1 | 8.4σ | 19.8σ |
| B1 – B3 | 17.9σ | 4.9σ |

**P1 FAILS on night 4, both receivers. Four failures out of four.**

### BOTH P1 AND P2 ARE NOW ARITHMETICALLY UNREACHABLE

**P1** needs B2–B3 below 1.0σ on **5 of 7** nights. Four have failed and three
remain. Maximum achievable is 3.

**P2** needs ≥2 of 3 beacons worse by ≥2× on **5 of 7** nights. Night 2 failed,
night 3 was unrunnable, night 4 failed (below). Even scoring night 1
retroactively and passing all three remaining nights gives a maximum of 4.

**Neither prediction can now reach its threshold.** §4 has no name for this
state. It is not REFUTED — that verdict requires P3's drift floor, which has
not been computed. The accurate statement is: **both predictions failed every
night they were tested and can no longer pass. Nights 5–7 characterise how,
not whether.**

This was flagged as the likely outcome after night 2 and it has arrived.

#### P2 arm — night 4

Reference-corrected (`--ref-mac a4:f0:0f:77:91:20`):

| beacon | s3 | d0wd |
|---|---:|---:|
| B2 | +0.0058 | −0.0576 |
| B3 | +0.0125 | −0.0154 |
| B1 *(reference)* | +0.0000 | −0.0003 |

Cross-receiver disagreement, |s3 − d0wd|:

| beacon | raw | corrected | effect |
|---|---:|---:|---|
| B2 | 0.0096 | 0.0634 | **6.6× worse** |
| B3 | 0.0259 | 0.0279 | 1.08× worse |
| B1 | 0.0534 | 0.0003 | pinned to zero **by construction** — not evidence |

**P2 FAILS.** The bar is ≥2 of 3 beacons worse by ≥2×. B2 qualifies; B3 does
not; B1 cannot, being the reference. One of two non-reference beacons.

**Note what the reference beacon was on this night.** B1 carried the *largest*
raw cross-receiver disagreement of the three (0.0534) — and correcting against
it forced that disagreement into B2, which is why B2's corrected figure is
worse than its raw one by a factor of six. **Using a degraded beacon as the
reference exports its degradation to everything else.** That is not a
prediction anyone froze, and it is the clearest argument yet that the reference
correction is unsafe on this bench.

#### THE VICTIM MOVED — and B2 has never been one

Per-beacon frame yield in the scored window, d0wd:

| night | B2 `28:05` | B3 `f4:2d` | B1 `a4:f0` |
|---|---:|---:|---:|
| 2 | 98.7% | **30.1%** | 98.4% |
| 3 | 98.9% | 97.4% | *off air* |
| **4** | **98.5%** | **84.7%** | **53.0%** |

s3, night 4: B1 99.3%, B3 99.8%, B2 99.9%. **The control receiver degrades
nothing, on any night.**

**On d0wd the affected beacon changes and B2 never is one.** Night 2 it was B3
alone. Night 3 nothing. Night 4 it is B1 worst and B3 second, with B2 clean at
98.5% for the third night running.

**A hypothesis this suggests, recorded and explicitly not adopted:** `28:05` is
the mains-powered unit — the one the operator confirmed at the bench on
2026-08-31 has been on power throughout. The two battery units are the two that
degrade, variably. **That is three nights of coincidence, not a finding.** No
mechanism is proposed, power was not varied deliberately, and
`ROTATION_PREREG.md` §0.0.1's labelling caveat still applies. It is written
down because it is the first thing to tie the pattern to a physical variable,
and because a night with the power assignment swapped would test it cheaply.

#### Series standing after 3 of 7

| prediction | nights scored | passing | standing |
|---|---:|---:|---|
| P1 — B2–B3 < 1.0σ | 2 | **0** | needs 5 of 7; **max achievable is now 5** |
| P2 — correction ≥ 2× worse | 2 | **0** | needs 5 of 7; **max achievable is now 5** |
| P3 — drift floor ≥ 1.0σ | — | — | not computable until the series ends |

**Both P1 and P2 now require every remaining night to pass.** One more failure
on either makes its threshold unreachable, which §4 does not have a name for.
It should be called what it is when it happens: the prediction failed, and the
remaining nights are being collected to characterise *how* rather than to
rescue it.

Nothing here is decided. Five nights remain.

---

### Night 5 — `20260902_000949`

> **§10.5a written before any figure for this night was computed.**
> T0 for the scoring session recorded as **2026-09-02 13:23 UTC**, before the
> capture was opened for anything other than the survival counts below.

**Capture:** started 00:09:49, ran **29,479 s (8 h 11 m)**, both receivers.
The longest night of the series (nights 1–4: 26,644 / 23,557 / 16,821 /
12,225 s), and more than six times the length needed to cover the scored
window.

**No operator label in either file**, as on nights 3 and 4. **T0 = 0,
declared** on the same basis and recorded before scoring: no log entry exists
to read, and the night-3 precedent for a start-and-sleep capture applies.
**Window: 2,400 → 4,700 s absolute.** Declared as a choice, not read from a
log.

#### Survival — every beacon clears the window by a wide margin

| beacon | frames (d0wd) | frames (s3) | first | last | clears 4,700 s? |
|---|---:|---:|---:|---:|---|
| B2 `28:05` | 1,349,509 | 2,308,908 | 0 s | **29,479 s** | yes |
| B1 `a4:f0` | 1,146,830 | 1,675,788 | 0 s | 22,871 s | yes |
| B3 `f4:2d` | 959,677 | 1,274,998 | 0 s | 19,436 s | yes |

All three transmit from t = 0 and run far past the scored window. **Second
consecutive night on which nothing died inside the window**, following the
battery change made before night 4.

B3 stops at 19,436 s and B1 at 22,871 s — both more than four hours after the
window closes, so neither affects scoring. Recorded because the order of
death (B3 first, then B1, B2 surviving) is the same order as the yield
degradation in the night-4 victim table, and that is worth watching rather
than noticing later.

**Consequences, fixed before any figure was computed:**

| item | night 5 status |
|---|---|
| **P1** — B2–B3 separation | scoreable |
| **P2** — reference correction | **runnable.** B1 `a4:f0` transmits throughout the window. |
| §5 third-pair control | available — all three pairs computable |
| `RECEIVER_DIVERGENCE` D1–D3 | scoreable |
| **D4** — one victim at a time | fully scoreable |

**P1 and P2 remain arithmetically unreachable** — that was settled at night 4
and nothing here changes it. Night 5 characterises how they fail, not whether.

#### Night 5 scored — raw, no `--ref-mac`, window 2,400–4,700 s

| beacon | s3 | d0wd | \|s3 − d0wd\| |
|---|---:|---:|---:|
| B2 `28:05` | +0.0077 | +0.0107 | 0.0030 |
| B1 `a4:f0` | +0.0071 | +0.0039 | 0.0032 |
| B3 `f4:2d` | +0.0038 | +0.0087 | 0.0049 |

| pair | s3 | d0wd |
|---|---:|---:|
| **B2 – B3** | **4.4σ** | **1.9σ** |
| B2 – B1 | **0.7σ** | 5.2σ |
| B1 – B3 | 3.7σ | 3.3σ |

**P1 FAILS on night 5, both receivers. Five failures out of five.**

**The collapsed pair is not the same pair on the two receivers.** On s3 the
closest pair is **B2–B1 at 0.7σ** — below P1's bar, but for the wrong pair. On
d0wd the closest is B2–B3 at 1.9σ. The two receivers, watching the same three
transmitters in the same window, disagree about which two are
indistinguishable.

The blind classification says the same thing independently. On s3, B1 is
misread as B2 in 510 of 1,054 test windows. On d0wd, B3 is misread as B2 in
626 of 719. Each receiver collapses a different beacon into B2. Accuracy s3
76.8%, d0wd 67.2%.

#### P2 arm — night 5

Reference-corrected (`--ref-mac a4:f0:0f:77:91:20`):

| beacon | s3 | d0wd |
|---|---:|---:|
| B2 | +0.0006 | +0.0068 |
| B3 | −0.0033 | +0.0048 |
| B1 *(reference)* | +0.0000 | +0.0000 |

| beacon | raw | corrected | effect |
|---|---:|---:|---|
| B2 | 0.0030 | 0.0062 | **2.07× worse** |
| B3 | 0.0049 | 0.0081 | 1.65× worse |
| B1 | 0.0032 | 0.0000 | pinned by construction — not evidence |

**P2 FAILS.** Bar is ≥2 of 3 beacons worse by ≥2×. B2 qualifies at 2.07×; B3
does not at 1.65×; B1 cannot. One of two non-reference beacons.

#### Frame yield — no victim, for the first time

| night | B2 `28:05` | B3 `f4:2d` | B1 `a4:f0` |
|---|---:|---:|---:|
| 2 | 98.7% | **30.1%** | 98.4% |
| 3 | 98.9% | 97.4% | *off air* |
| 4 | 98.5% | **84.7%** | **53.0%** |
| **5** | **98.0%** | **98.1%** | **98.1%** |

s3 night 5: B2 99.1%, B3 99.1%, B1 99.7%. **The control receiver degrades
nothing, on any night, still.**

**Night 5 is the first night with no victim on d0wd** — and it is also the
night with the smallest cross-receiver disagreement of the series (0.0030 /
0.0032 / 0.0049, against night 4's 0.0096 / 0.0534 / 0.0259). Those two facts
arriving together is consistent with yield collapse and SFO disagreement being
one phenomenon, which is exactly what `RECEIVER_DIVERGENCE_PREREG.md` D2 was
written to test. See §9.1c there.

**But see §9.1c before reading anything into the above.** D3 — the control
prediction that made the rest of the divergence work interpretable — **fails on
night 5**, and its frozen verdict is that the framing is wrong rather than a
branch being right.

---

### Night 6 — `20260903_013851`

> **§10.6a written before any SFO figure for this night was computed.** The
> only numbers read from the capture at the time of writing are the survival
> counts below, which are what fixes the scoring window.

**Capture:** started 01:38:51, ran **20,004 s (5 h 33 m)**, both receivers.
Series lengths for context: 26,644 / 23,557 / 16,821 / 12,225 / 29,479 /
**20,004 s**. More than four times the length needed to cover the scored
window.

Total frames: **5,039,118 (s3)** and **2,850,215 (d0wd)**.

**No operator label in either file**, as on nights 3, 4 and 5. **T0 = 0,
declared** on the same basis and recorded before scoring: no log entry exists
to read, and the night-3 precedent for a start-and-sleep capture applies.
**Window: 2,400 → 4,700 s absolute.** Declared as a choice, not read from a
log — identical to nights 3–5, so the window is not a free parameter being
re-picked each night.

#### Survival — all three beacons run the entire capture

| beacon | frames (d0wd) | frames (s3) | first | last | clears 4,700 s? |
|---|---:|---:|---:|---:|---|
| B2 `28:05` | 966,692 | 1,697,718 | 0 s | **20,004 s** | yes |
| B1 `a4:f0` | 952,285 | 1,570,932 | 0 s | **20,004 s** | yes |
| B3 `f4:2d` | 930,465 | 1,769,024 | 0 s | **20,004 s** | yes |

**Third consecutive night with nothing dying inside the window, and the first
night of the series on which no beacon stops transmitting at all** — all three
run to the last second on both receivers. Nights 5 and 4 cleared the window
but B3 and B1 still died hours later (19,436 s and 22,871 s on night 5). Here
none of them does.

That is a change in the bench, not a result: it follows the battery change made
before night 4 and a shorter capture than night 5's 8 h 11 m. Recorded so the
death-order watch opened at night 5 is not silently dropped — **there is no
death order this night to observe.**

**Consequences, fixed before any figure was computed:**

| item | night 6 status |
|---|---|
| **P1** — B2–B3 separation | scoreable |
| **P2** — reference correction | **runnable.** B1 `a4:f0` transmits throughout. |
| §5 third-pair control | available — all three pairs computable |
| `RECEIVER_DIVERGENCE` D1–D3 | scoreable |
| **D4** — one victim at a time | scoreable, and see the note below |

**P1 and P2 remain arithmetically unreachable.** Settled at night 4; nothing
here changes it. Five failures out of five stand, and at most two nights
remain. Night 6 characterises how they fail, not whether.

**Stated before scoring, so it cannot be claimed afterwards as a prediction:**
if the night-5 pairing of *no victim* with *smallest cross-receiver
disagreement* is one phenomenon, then a night on which every beacon survives
the whole capture should also show small disagreement. That is a consistency
check on the D2 framing, **not** a frozen prediction, and it carries no verdict
either way. It is written here only so that whichever way night 6 lands, the
expectation on record is the one held in advance.

#### Night 6 scored — raw, no `--ref-mac`, window 2,400–4,700 s

| beacon | s3 | d0wd | \|s3 − d0wd\| |
|---|---:|---:|---:|
| B2 `28:05` | +0.0073 | +0.0025 | 0.0048 |
| B1 `a4:f0` | +0.0053 | +0.0075 | 0.0022 |
| B3 `f4:2d` | +0.0204 | +0.0282 | 0.0078 |

| pair | s3 | d0wd |
|---|---:|---:|
| **B2 – B3** | **26.1σ** | **46.4σ** |
| B2 – B1 | 4.2σ | 9.0σ |
| B1 – B3 | 30.4σ | 37.4σ |

**P1 FAILS on night 6, both receivers. Six failures out of six** — and by the
widest margin of the series. No pair on either receiver is within the 1.0σ bar;
the *closest* pair anywhere tonight is B2–B1 at 4.2σ.

#### B3 moved 7–8σ overnight, and that is the night's actual result

Against `BETWEEN_UNIT_SD = 0.00237 rad/sc` (`pc/exp_ambient_separation.py:79`,
read this session):

| beacon | night 5 → 6, s3 | σ | night 5 → 6, d0wd | σ |
|---|---:|---:|---:|---:|
| **B3 `f4:2d`** | +0.0038 → **+0.0204** | **7.0σ** | +0.0087 → **+0.0282** | **8.2σ** |
| B2 `28:05` | +0.0077 → +0.0073 | 0.2σ | +0.0107 → +0.0025 | 3.5σ |
| B1 `a4:f0` | +0.0071 → +0.0053 | 0.8σ | +0.0039 → +0.0075 | 1.5σ |

**Both receivers see it, and they agree on its size and direction.** This is
not a receiver artifact — it is the transmitter.

This is a P3 quantity and **P3 is not scored here**; it is scored after night 7
as designed. Recorded now because it was measured now, and because a 7–8σ
overnight excursion by one stationary beacon is exactly the magnitude P3 was
written to detect. Nothing about the verdict is anticipated by saying so.

#### Blind classification — the most separable night of the series

s3 **97.7%** (3,508/3,592), d0wd **97.2%** (1,957/2,014). Against night 5's
76.8% and 67.2%.

**This is not a good result for the room conclusion — it is the opposite one.**
The beacons are easy to tell apart tonight *because* they are far apart. High
device-ID accuracy and co-location collapse are the same measurement read in
two directions, and tonight it reads all the way against collapse.

#### P2 arm — night 6

Reference-corrected (`--ref-mac a4:f0:0f:77:91:20`):

| beacon | s3 | d0wd |
|---|---:|---:|
| B2 | +0.0019 | −0.0050 |
| B3 | +0.0151 | +0.0207 |
| B1 *(reference)* | −0.0000 | +0.0000 |

| beacon | raw | corrected | effect |
|---|---:|---:|---|
| B2 | 0.0048 | 0.0069 | 1.44× worse |
| B3 | 0.0078 | 0.0056 | **1.39× BETTER** |
| B1 | 0.0022 | 0.0000 | pinned by construction — not evidence |

**P2 FAILS.** The bar is ≥2 of 3 beacons worse by ≥2×. **Zero of the two
non-reference beacons qualify** — B2 falls short at 1.44×, and B3 moves the
wrong way entirely.

**This is the first night on which the reference correction improved a
beacon.** On night 4 the opposite happened for a stated reason: B1 carried the
largest raw disagreement and exported it. Tonight B1 carries the *smallest*
(0.0022), and correcting against the cleanest beacon helped B3. That is
consistent with the night-4 note — the correction inherits whatever the
reference is doing — but one night each way is an observation, not a rule, and
no prediction was frozen on it.

#### Frame yield — no victim, and none anywhere

d0wd: 5,939 of 328,145 windowed frames rejected by `--min-inlier 0.6` (1.8%).
s3: 1,239 of 575,794 (0.2%). Per-beacon window counts are near-even on both
receivers (d0wd 1,700 / 1,742 / 1,591; s3 3,036 / 2,783 / 3,157).

Even if every rejection on d0wd fell on one beacon, that beacon would still
clear ~94%. **No beacon is below 90% on either receiver.** D4 holds; there is
no victim to identify.

#### The advance consistency check lands against the D2 framing

§10.6a recorded, before scoring, that if *no victim* and *small cross-receiver
disagreement* are one phenomenon, a night with no victim at all should show
small disagreement.


Night 6 is the cleanest yield night of the series — nothing died, nothing
degraded, on either receiver. Its cross-receiver disagreement is
**0.0048 / 0.0022 / 0.0078**, against night 5's **0.0030 / 0.0032 / 0.0049**.
**Larger on two of three beacons, and largest of the two nights overall.**

So the pairing seen at night 5 does not reproduce. This was not a frozen
prediction and carries no verdict, but it is evidence against treating yield
collapse and SFO disagreement as one mechanism, which is what
`RECEIVER_DIVERGENCE_PREREG.md` §4 says needs revisiting if D2 splits from D1.

---

### Night 7 — `20260904_010024`

> **§10.7a written before any SFO figure for this night was computed.** The
> only numbers read from the capture at the time of writing are the survival
> counts below, which are what fixes the scoring window.

**This is the last night of the series.** P3 becomes scoreable after it, and
P3 is the only prediction still live: P1 and P2 have been arithmetically
unreachable since night 4.

**Capture:** started 01:00:24, ran **24,486 s (6 h 48 m)**, both receivers.
Series lengths: 26,644 / 23,557 / 16,821 / 12,225 / 29,479 / 20,004 /
**24,486 s**. More than five times the length needed to cover the scored
window.

Total frames: **5,337,659 (s3)** and **3,272,773 (d0wd)**.

**No operator label in either file**, as on nights 3 through 6. **T0 = 0,
declared** on the same basis and recorded before scoring. **Window: 2,400 →
4,700 s absolute** — identical to nights 3–6, so the window is not a free
parameter being re-picked on the final night.

#### Survival — all three transmit from t = 0; B3 stops well after the window

| beacon | frames (d0wd) | frames (s3) | first | last | clears 4,700 s? |
|---|---:|---:|---:|---:|---|
| B2 `28:05` | 1,211,588 | 2,060,682 | 0 s | **24,486 s** | yes |
| B1 `a4:f0` | 823,903 | 1,644,176 | 0 s | **24,486 s** | yes |
| B3 `f4:2d` | 1,234,426 | 1,630,704 | 0 s | 19,300 s | yes |

**Fourth consecutive night with nothing dying inside the window.** B3 stops at
19,300 s — four hours after the window closes, so it cannot affect scoring.
Recorded because the death-order watch opened at night 5 now has a second
observation: B3 first again, as on night 5, with B2 and B1 surviving.

**Consequences, fixed before any figure was computed:**

| item | night 7 status |
|---|---|
| **P1** — B2–B3 separation | scoreable |
| **P2** — reference correction | **runnable.** B1 transmits throughout. |
| §5 third-pair control | available — all three pairs computable |
| `RECEIVER_DIVERGENCE` D1–D4 | scoreable |
| **P3** — the drift floor | **scoreable after this night, as designed** |

**P1 and P2 remain arithmetically unreachable.** Six failures out of six stand;
one night remains and the bar was five of seven. Night 7 closes the record, it
does not reopen it.

**Stated before scoring, so it cannot be claimed afterwards as a prediction.**
B3 moved 7.0σ (s3) and 8.2σ (d0wd) between nights 5 and 6 — the largest
single-beacon overnight excursion recorded in the series. If that was a
transition to a new operating point rather than free wander, night 7's B3
should sit near night 6's value rather than return toward night 5's. If it is
wander, it should land somewhere unrelated to both. This is a consistency
check on how P3's drift floor should be read, **not** a frozen prediction, and
it carries no verdict either way.



Night 6 is the cleanest yield night of the series — nothing died, nothing
degraded, on either receiver. Its cross-receiver disagreement is
**0.0048 / 0.0022 / 0.0078**, against night 5's **0.0030 / 0.0032 / 0.0049**.
**Larger on two of three beacons, and largest of the two nights overall.**

So the pairing seen at night 5 does not reproduce. This was not a frozen
prediction and carries no verdict, but it is evidence against treating yield
collapse and SFO disagreement as one mechanism, which is what
`RECEIVER_DIVERGENCE_PREREG.md` §4 says needs revisiting if D2 splits from D1.

#### Night 7 scored — raw, no `--ref-mac`, window 2,400–4,700 s

| beacon | s3 | d0wd | \|s3 − d0wd\| |
|---|---:|---:|---:|
| B2 `28:05` | +0.0067 | +0.0033 | 0.0034 |
| B1 `a4:f0` | +0.0090 | +0.0120 | 0.0030 |
| B3 `f4:2d` | +0.0224 | +0.0062 | **0.0162** |

| pair | s3 | d0wd |
|---|---:|---:|
| **B2 – B3** | **30.8σ** | **6.1σ** |
| B2 – B1 | 4.4σ | 17.2σ |
| B1 – B3 | 26.4σ | 11.1σ |

**P1 FAILS on night 7, both receivers. Seven failures out of seven.**

**The reference beacon had a bad night and it is visible in the spread, not
just the centroid.** B1 contributed **487 windows on d0wd and 1,070 on s3**,
against 1,899–3,037 for the other two, and its IQR is **0.0212 (d0wd)** and
0.0071 (s3) where every other beacon-night in the series sits near 0.0005–0.0011.
That is a twentyfold spread inflation on the one beacon the P2 arm corrects
against. Recorded here rather than used to exclude the night: the exclusion
rule in §7 requires a stated physical cause decided before scoring, and none
was.

Classification accuracy: s3 **87.2%**, d0wd **91.7%** — down from night 6's
97.7% and 97.2%.

#### P2 arm — night 7

Reference-corrected (`--ref-mac a4:f0:0f:77:91:20`):

| beacon | s3 | d0wd |
|---|---:|---:|
| B2 | −0.0023 | −0.0086 |
| B3 | +0.0134 | −0.0055 |
| B1 *(reference)* | +0.0002 | +0.0003 |

| beacon | raw | corrected | effect |
|---|---:|---:|---|
| B2 | 0.0034 | 0.0063 | 1.85× worse |
| B3 | 0.0162 | 0.0189 | 1.17× worse |
| B1 | 0.0030 | 0.0001 | pinned by construction — not evidence |

**P2 FAILS.** Bar is ≥2 of 3 beacons worse by ≥2×. B2 falls short at 1.85×,
B3 at 1.17×, B1 cannot count. Zero of two non-reference beacons qualify.

#### The advance check from §10.7a

Written before scoring: if B3's 7–8σ move between nights 5 and 6 was a
transition to a new operating point, night 7 should sit near night 6; if it was
wander, it should land somewhere unrelated.

**The two receivers disagree.** On s3, B3 went +0.0204 → **+0.0224**, a move of
0.8σ — it stayed. On d0wd, B3 went +0.0282 → **+0.0062**, a move of **9.3σ** —
it did not. The same transmitter in the same window looks settled to one
receiver and freely wandering to the other.

No verdict attaches to this; it was not a frozen prediction. It is recorded
because it is the cleanest single illustration in the series of why P1 could
not be resolved by this instrument.

---

## 11. P3 — scored, and the verdict table applied

**P3, frozen in §3:** *the night-to-night wander of a single co-located
beacon's raw SFO exceeds 1.0σ*, against
`BETWEEN_UNIT_SD = 0.00237 rad/sc` (`pc/exp_ambient_separation.py:79`).

Night-to-night |Δ| in σ, every beacon, both receivers, six steps across seven
nights. Night 3 is `n/a` for B1, which was off air.

**s3**

| beacon | 1→2 | 2→3 | 3→4 | 4→5 | 5→6 | 6→7 | max | steps > 1.0σ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B2 | 5.6 | 5.8 | 0.4 | 1.9 | 0.2 | 0.3 | **5.8** | 3 / 6 |
| B3 | 0.3 | 0.6 | 0.0 | 6.3 | 7.0 | 0.8 | **7.0** | 2 / 6 |
| B1 | 7.0 | n/a | n/a | 0.3 | 0.8 | 1.6 | **7.0** | 2 / 4 |

**d0wd**

| beacon | 1→2 | 2→3 | 3→4 | 4→5 | 5→6 | 6→7 | max | steps > 1.0σ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B2 | 2.4 | 0.8 | 0.9 | 3.5 | 3.5 | 0.3 | **3.5** | 3 / 6 |
| B3 | 30.5 | 26.2 | 11.5 | 15.2 | 8.2 | 9.3 | **30.5** | **6 / 6** |
| B1 | 10.0 | n/a | n/a | 23.5 | 1.5 | 1.9 | **23.5** | 4 / 4 |

**P3 HELD — decisively.** Every beacon on every receiver exceeds the 1.0σ bar,
most of them by a wide margin. On d0wd, B3 clears it on **all six** steps with
a median of 15.2σ. The stationary drift floor is not near 1.0σ — it is between
three and thirty times it.

### The frozen verdict

§4, written before the first capture:

> | **P1 UNINTERPRETABLE** | P1 fails **and** P3 shows drift floor ≥ 1.0σ — the instrument cannot resolve the bar this design set |

Both conditions are met. **P1 is UNINTERPRETABLE, not REFUTED.**

This is the outcome §3 named as the risk in this design, in writing, before any
data existed:

> *"If P3 fires and P1's separations also scatter above 1.0σ, the correct
> reading is that this design cannot resolve the question — not that the room
> conclusion is refuted."*

So the seven nights do **not** refute the co-location finding, and do not
support it either. They establish that **a single stationary beacon wanders
between three and thirty times further, night to night, than the bar P1 was
asked to clear.** A 1.0σ pair-separation test cannot mean anything against a
drift floor that size, and no amount of additional nights would change that —
the instrument, not the sample, is the limit.

**P2:** failed on every night it could be run — 2, 4, 5, 6, 7; night 3 was
unrunnable with B1 off air. It never reached the ≥2-of-3 bar on any night, and
its maximum achievable count fell below 5 of 7 at night 4. Not REFUTED under
§4's definition, which requires correction to *reduce* disagreement on ≥2 of 3
beacons across ≥5 nights; the honest statement is that **P2 failed every night
it was tested and can no longer pass.**

**What §6 said would happen if the pair scattered:** abandoning the room
conclusion was made conditional on the drift floor staying *below* 1.0σ. It did
not. The room conclusion therefore keeps its evidence and loses nothing here.

### What this series cost and bought

Seven nights, 158,000 seconds of capture, both receivers, zero missed nights.
Two predictions frozen in advance both failed. The third — the one written down
because it might invalidate the other two — held, and in holding it converted a
refutation into a statement about the instrument.

That is what a pre-registration is for. Without §3's named risk and §4's
separate UNINTERPRETABLE cell, seven consecutive P1 failures would have read as
a refutation of the co-location result, and the write-up would have been wrong
in the direction that felt most rigorous.

