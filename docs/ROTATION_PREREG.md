# ROTATION — is the "device signature" the device, or the position?

**Stage 1. Written and saved 2026-08-27, before the capture exists.**
Nothing below the `STAGE 2` banner will be written until the blocks are on
disk. Read-only on `data/raw/`. No git command is run.

---

## 0. The question, and why this instrument is better than the last one

Every between-device figure this project has ever produced was measured with
**the three beacons in three different rooms.** `RECEIVER_TERM_PREREG.md`
§639: *"the three beacons span the room."* `COLOCATED_0823.md` co-located the
two **receivers**; nothing has ever co-located or permuted the
**transmitters.**

So `BETWEEN_UNIT_SD = 0.00237`, every σ separation, and the `S_dev = 0.01050`
this project's own U/L test used as its yardstick this morning
(`docs/UL_BIT_GROUND_TRUTH.md`) all contain a **position term that has never
been separated from the silicon term.** "These three devices are
distinguishable" and "these three positions are distinguishable" are the same
measurement in this dataset, and always have been.

**A rotation separates them by construction.** Each device visits each
position; device and position are crossed rather than confounded.

`docs/B3_MOVED.md` §9.6 already established why a rotation beats the
relocation it attempted:

> *"you cannot move one beacon out of range without changing the channel the
> other two are measured on. **The 'controls' in a single-beacon relocation
> are not untreated units.** A rotation that keeps all three transmitting,
> and only permutes positions, does not have this problem — which is a point
> in its favour."*

**And the prerequisite that document set is already met.** §0.0.1 required the
position→MAC mapping be *"re-established from the data, not from memory"*
before a rotation. `*_20260823_180002.csv` contains all three units
power-cycled in place — B2 at t = 59 s for 58.3 s, B1 at t = 482 s for 59.3 s,
B3 at t = 1,140 s for 68.3 s — each on both receivers, agreeing to 0.1 s, each
landing on its logged minute. That anchor exists.

---

## 1. Design

**Amendment, 2026-08-27, before any capture exists.** The design below
originally specified one capture per block. It is changed to **a single
continuous capture spanning all three blocks**, with block boundaries defined
by wall-clock time and verified against the data afterwards. Reasons, both
methodological: a continuous capture holds receiver state, calibration and
serial session constant across the comparison instead of restarting them
twice, and the moves then appear as RSSI steps that can be **located
independently of the operator's log** — the method `LABELLED_EVENTS_0823.md`
§15 used to place four reboots to within 1.5–5.4 s of their logged minutes.
Recorded as an amendment rather than a silent edit; no data existed when it
was made.

Three blocks, **≥ 30 minutes each**, one continuous capture, all three beacons
transmitting throughout:

| block | arrangement |
|---|---|
| **A** | original — B1@P1, B2@P2, B3@P3 |
| **B** | rotated — every beacon moves one position |
| **A′** | returned to the original arrangement |

**A′ is not optional.** `LABELLED_EVENTS_0823.md` §20 measures the SFO slope
wandering **0.56–4.97 × the entire between-device spread over four untouched
minutes**, and `B3_MOVED.md` §9.1 puts stationary-beacon wander at 2.5–4.9σ
across one night. **A single before/after cannot distinguish a rotation from
the clock.** A→B→A′ can: a positional effect reverses when the rotation is
undone; drift does not.

### 1.1 One manipulation at a time

**The receivers must not move during these three blocks.** If the receivers
were repositioned before block A, that is fine — it is the *state*, held
constant — but nothing may change between A, B and A′ except which beacon sits
where. `COLOCATED_0823.md` §5.5 is the standing precedent: that file cannot
separate co-location from relocation to this day, because a remount moved both
receivers at once and no artefact records it.

### 1.1a Block A positions — recorded from photographs, 2026-08-27

**The first positional record this project has.** `NODE_CENSUS.md` I4
established that `heatmap.py`'s coordinates are defaults in an interactive
plotting tool, *"not a record of where hardware was"*; `COLOCATED_0823.md`
§0.0.1 that *"the repo's B1/B2/B3 labels have never been tied to physical
positions by anything but recollection."* Source here is four photographs
supplied by the operator and described by an assistant, labelled by the
operator as **pre-rotation**.

> **⚠ CORRECTED — annotated 2026-08-27, after the capture.** The HOME mapping
> recorded below (B2@POS1, B3@POS2, B1@POS3) did not reconcile with the
> arrangements described after the run, and an earlier version of this note
> declared the block→arrangement mapping **unrecoverable**. That was wrong,
> and it is replaced rather than deleted so the sequence stays visible.
>
> **It took four exchanges to establish, because the `label` column records
> *actions taken* and not *resulting arrangements*** — an action log cannot
> imply a layout without a known starting state. The analysing agent also
> twice asserted a layout inferred from photographs over one the operator had
> stated, which is `CLAUDE.md` failure mode **G**.
>
> **Block B arrangement, operator-confirmed:**
> **B1 @ POS1 · B2 @ POS4 · B3 @ POS3 (on the TV).** B3 was deliberately
> placed away from the main room for the empty-apartment window. B1 and B2
> were both in the main room. This is the arrangement every Stage 2 figure
> from block B describes.
>
> **Confirmed current state, operator, 2026-08-27 post-capture:**
> **B1 @ POS1 · B2 @ POS3 · B3 @ POS4.** POS4 is the bar in the main room and
> is battery-powered. B3 cannot return to POS2. This is the baseline the next
> capture starts from.
>
> **The fix, for the rerun:** the label column must carry the *resulting
> arrangement* at the start of every block — one line, `B1@Px B2@Py B3@Pz` —
> not only the action performed. `docs/B3_MOVED.md` §0.0.1 predicted exactly
> this: *"a rotation is a mapping from physical positions to MACs, and if the
> operator's position→name mental model is wrong, the rotation will be
> recorded wrong even though every MAC in the CSV is correct."*

**HOME arrangement as recorded before the run: B2 @ POS1, B3 @ POS2,
B1 @ POS3.** The position numbering is the operator's; the RF descriptions
are read off photographs. Retained as written rather than corrected, so the
discrepancy above stays visible.

**Positions, operator-confirmed 2026-08-27 after four exchanges. This table
replaces an earlier version that placed POS3 in the main room; it is in the
bedroom.**

| pos | where it is | RF character |
|---|---|---|
| **POS1** | "Christmas table", **main open space** | Mains, powered by a **long USB cable run across the floor** from a wall outlet — the shield is continuous with the board's ground plane, so the cable is part of the radiating structure. Under the running ceiling fan. |
| **POS2** | Side table beside a desktop PC tower — **a separate room, behind a wall** | A **PS5 DualSense sits inches away** — an active 2.4 GHz Bluetooth transmitter, in band. Power strip and mains adapters on the same surface. **Unavailable from 2026-08-27 onward.** |
| **POS3** | On a **Telly-brand television — BEDROOM, behind a wall** | The only position not in the main space. **Breadboard, and a long USB run — same cable topology as POS1.** A television panel is a **large conductive ground plane** directly beneath a PCB trace antenna whose module datasheet requires a keep-out zone. A Telly also runs a **permanently-lit second screen pulling content over WiFi**, so it is an active in-band neighbour, not a passive surface. |
| **POS4** | Kitchen bar, **main open space** | **Always battery**, connected by a **short USB cable** — corrected 2026-08-27; an earlier version of this table said "no cable", which was an assistant inference and wrong. Still the cleanest position electrically: a battery pack floats, where a mains adapter couples the shield toward building earth and a much larger counterpoise. |
| — | **RX** ×2 | On the wall above the PC tower, **main open space**, within a few feet of POS1, POS2 and POS4. |

**Topology, confirmed:** the TV wall, kitchen bar, desk and dining area are
**one open-plan space under a vaulted ceiling with a running ceiling fan.**
**Only POS1 and POS4 are in it, with the receivers. POS2 and POS3 are each
in a separate room, behind walls.**

### 1.1b The consequence for every prior figure in this project

The HOME arrangement recorded before this capture was **B2@POS1, B3@POS2,
B1@POS3** — which places **one beacon in the receivers' room and two behind
walls**, with the reference beacon among the latter.

**So no measurement in this repo has ever compared two beacons on comparable
paths.** Every pairwise σ, `BETWEEN_UNIT_SD = 0.00237`, every twin figure and
every same-model figure was taken with the units in different rooms. Device
identity and room identity have been perfectly confounded since July, not as
a subtlety but as the standing physical layout.

That is not a claim that the prior figures are wrong. They measure what they
measure. It is a statement that **"these devices are distinguishable" and
"these rooms are distinguishable" have never been separable in this dataset**,
and that block B of this capture is the first window in which two beacons
shared the receivers' space at all.
| **ceiling fan** | **Running.** Five blades, motion-blurred in the photograph, on a long downrod into the vaulted volume of the receiver room. |
| **AC** | Operator states it runs continuously and cycles ≈ every 30 min. Third floor, Kansas summer. |

**Not recorded, and therefore not claimed:** antenna orientation of any unit,
heights, distances better than the operator's pacing, and whether the TV or
the PS5 changed state during the capture. Photographs establish *what is
there*, not *what stayed constant*.

**Why this belongs in the pre-registration rather than the results:** the
three positions are not interchangeable neutral spots. They are a ground
plane, an in-band emitter, and a long counterpoise. A rotation across
environments this distinct is a **stronger** test than a rotation across
three similar corners would be — if the signature follows the board through
these, it is not the furniture. Written before any block is scored so that a
POSITION verdict cannot later be explained away by pointing at the clutter.

### 1.2 Recorded per block, before it starts

Position → MAC for all three. Block start time, local and UTC. AC state and
whether it cycled. Ceiling fans, on or off. Anything else that moved. If a
beacon has to be powered down to move it, note it — those gaps land in the
data to a tenth of a second and can be verified.

---

## 2. Decision rule, frozen before the numbers exist

Measured per receiver, never pooled across receivers
(`IQ_IMBALANCE.md` §15: `frac_rx = 5.73`, `R_disp = 826.6`, RECEIVER-DOMINATED).

For each feature **`κ`** (primary) and **SFO slope** (comparator), and each
beacon:

- **`D_dev`** = |feature(beacon X, block A) − feature(beacon X, block B)| —
  how much a *device* changes when it changes *position*.
- **`D_pos`** = |feature(position P, block A) − feature(position P, block B)| —
  how much a *position* changes when it changes *device*.
- **`R_drift`** = |feature(beacon X, block A) − feature(beacon X, block A′)| —
  the same device, same position, separated only by time. **This is the null
  band, measured in this experiment rather than imported.**

| outcome | reading |
|---|---|
| **`D_dev` ≤ `R_drift`** and **`D_pos` > 3 × `R_drift`** | **SILICON.** The signature travels with the board. |
| **`D_pos` ≤ `R_drift`** and **`D_dev` > 3 × `R_drift`** | **POSITION.** The signature stays with the room. The "device signature" is the floor plan. |
| both > 3 × `R_drift` | **MIXED** — report the ratio `D_pos / D_dev`, claim neither. |
| both ≤ `R_drift` | **UNDERPOWERED.** The blocks are too short or the drift too large. No verdict. |

**Stated now:** a large `D_pos` with a large `R_drift` is not evidence of
anything. Every comparison is against the drift band this experiment measures
for itself, not against `BETWEEN_UNIT_SD` — because §0 is the reason
`BETWEEN_UNIT_SD` is exactly the number in question.

---

## 3. Controls

- **C1 — the return block.** A′ vs A is the null. If `R_drift` is comparable
  to `D_pos`, nothing is claimed.
- **C2 — the comparator.** `κ` and the slope are scored identically. The slope
  fails the U/L ground-truth test at 3.40 and `κ` passes at 0.21
  (`UL_BIT_GROUND_TRUTH.md` §7), so a rotation result that disagrees between
  the two features is informative rather than contradictory.
- **C3 — RSSI.** Printed per beacon per block. A rotation changes path length,
  so RSSI *should* move; `|κ|` is diluted by link strength
  (`IQ_IMBALANCE.md` §18), so `arg κ` carries the primary claim and `|κ|` is
  reported beside it, not instead of it.
- **C4 — both receivers.** Two receivers see the same rotation. Agreement is
  evidence; disagreement bounds it.

---

## 4. What this cannot show

- **Nothing cross-receiver.** Per §2.
- **Nothing about ambient devices.** Beacons only.
- **It cannot separate position from orientation** unless orientation is held
  fixed. Set each beacon the same way up at every position, and say so.
- **It does not revise** 99.7 %/7,497, 95.7 %/14,234, 65.2 %, or the U/L
  result. It tests the yardstick those numbers are measured against.
- **A POSITION verdict would not mean the crystals are identical.** It would
  mean this instrument, in this apartment, cannot see past the room — which is
  a statement about the measurement, not about the silicon.
- Nothing is fused with `pc/occ/`. The ~77 % same-model figure is not quoted.
  `DIRECTION.md` is not cited as capability.

---

## 5. Reproduce

```
python pc\exp_kappa_cross_session.py scan data\raw\<blockfile>.csv --tag <tag>
python pc\exp_rotation.py            # written after the blocks exist
```

The analysis script does not exist yet and will not be written until the
capture does, so it cannot be shaped by the data.

---

## STAGE 2 — results

**Capture 2026-08-27 14:06:42, 2:07:29, both receivers.** Nothing above this
banner was edited after the run except the §1.1a correction block, which is
marked and dated.

### 6. The result that matters, and it is not the rotation

**In a 34-minute window with the apartment empty and nothing moved, the two
beacons sharing the receivers' open-plan space are 0.2σ apart, and the one
behind a wall on a television is 7.7–7.9σ from both.**

`pc/rff_offline.py`, block B (`--after 2531 --before 4579`), s3, N = 3:

| pair | separation | positions |
|---|---:|---|
| **B1 vs B2** | **0.2σ** | POS1 and POS4 — **both in the open space with the RX** |
| B1 vs B3 | **7.7σ** | open space vs **bedroom, on a Telly** |
| B2 vs B3 | **7.9σ** | open space vs **bedroom, on a Telly** |

**Cable topology is eliminated, and the elimination runs backwards from what
a cable effect would predict.**

| pair | cable topology | separation |
|---|---|---:|
| B1 (POS1, long USB) vs **B3** (POS3, long USB) | **matched** | **7.7σ** |
| B1 (POS1, long USB) vs **B2** (POS4, battery, no cable) | **mismatched** | **0.2σ** |

The two boards with the *same* radiating structure are the ones 7.7σ apart.
The two with *different* radiating structures are indistinguishable. A
counterpoise effect would produce exactly the opposite pattern, so cable
length and mains-versus-battery are **not** what this measurement is
responding to.

What remains as candidates for POS3's extremity: **the wall and its
propagation path, the television as a ground plane, and the Telly's active
second screen.** Three confounds, still stacked, but a real one has been
removed by measurement rather than by argument.

Blind chronological holdout: **85.0 %, 2121/2494**. But the accuracy is
carried entirely by B3: 674/677 correct, against B1's **514/860 with 344
windows landing on B2.** Two devices in one room are a coin flip; the third
is trivially separable because it is somewhere else.

**B3's reference-corrected SFO is +0.0419 rad/sc.** `BETWEEN_UNIT_SD` is
0.00237, so that is **17.7× the entire between-unit spread**, with an IQR of
0.0115 against B1 and B2's 0.0010 — twelve times wider. **No crystal
tolerance produces a 17× outlier.** B3 is not reading as a different
oscillator; it is reading as a different channel.

**And POS3 is the least neutral position in the apartment.** It is the top of
a powered, WiFi-associated television — a metre-wide conductive ground plane
directly beneath a PCB trace antenna whose module datasheet requires a
keep-out zone. `docs/GATE_CALIBRATION.md` §4.2 measured this estimator wrong
by **15–21σ under two-ray multipath at every inlier stratum**, and §8.3 that
neither gate statistic can detect channel bias at all. A beacon on a TV is
the condition that failure mode describes.

### 6.1 The rotation itself — MIXED, and one metric was measuring the wrong thing

`pc/exp_rotation.py`, κ, s3, drift band from the A→A′ return leg:

| quantity | value | vs R_drift |
|---|---:|---:|
| R_drift | 0.00108 | — |
| D_dev B1 | 0.00077 | 0.71× |
| D_dev B2 | 0.00189 | 1.74× |
| D_pos POS1 / POS3 | 0.01913 / 0.01772 | 17.66× / 16.36× |

**D_pos is not a position result.** |κ(B1) − κ(B2)| measured directly is
0.01892 / 0.01787 / 0.01708 across the three blocks — D_pos *is* the
between-device separation, restated. It is a sanity check, not evidence.

**And B1's channel barely changed across the swap** — RSSI −74.4 → −74.2,
**0.2 dB**. A position change that is not a channel change is not a test, so
B1's small D_dev is uninformative. Of the four cells, three are informative:
s3/B2 moved 5.1 dB and κ shifted 1.74× the band; d0wd/B1 and d0wd/B2 moved
7.5 and 4.5 dB and κ held at 0.91× and 0.76×.

**Verdict per §2: MIXED on both receivers.** Two of three informative cells
hold at the drift floor across real channel changes; one exceeds it.

### 6.2 Reproduced live, in the operator's own run output

> *"note: `--max-resid 0.8` rejected NOTHING — it passed 100 % of the 428,799
> fitted frames."*

`docs/GATE_CALIBRATION.md` §4.1's structural no-op, printed by the shipped
pipeline on a capture taken five days later.

### 7. What this pass does not establish

- **One 34-minute window, one session, three devices.**
- **Blocks A and A′ had a person in the room; block B did not.** The
  pre-registered §2 sign test returned **+0.888 — symmetric** — but with
  D_dev at the drift floor there is no positional effect for it to have a
  sign, so what it measured is that the residual drift is common-mode between
  units, not a swap.
- **Movement outside the labels is unbounded.** Guard windows remove the
  movement that was written down. The operator reports additional unlogged
  movement in blocks A and A′, so those two blocks carry an unknown human
  term. Block B does not.
- **The 0.2σ / 7.8σ contrast is one arrangement.** It is consistent with the
  room being the dominant variable and it is **not** a controlled test of
  that — no beacon was moved *within* the window.
- **Historical twin figures are not replaced.** B1/B3 at 0.26–0.96σ come from
  July captures on different receivers with B1 on the TV. Tonight B3 is on
  the TV. The pairs are not like-for-like and no revision is claimed.
- Nothing fused with `pc/occ/`. The ~77 % same-model figure is not quoted.

### 7.1 Temptations recorded rather than acted on

1. **Leading with "D_pos is 17× D_dev."** It was reported that way for
   nineteen minutes before the metric was checked, and it was measuring the
   between-device separation. Corrected in §6.1 rather than removed.
2. **Reading 85 % as an accuracy result.** It is one separable device and two
   indistinguishable ones. §6 reports the confusion counts instead.
3. **Attributing the twin inversion to "B1 and B2 share a room."** That
   layout was inferred from photographs and was wrong. See §1.1a.
4. **Calling B3's 17.7× a crystal result.** No tolerance produces it.

### 8. The experiment this points at

Two beacons, **both on battery**, same room, **one variable: separation X**.
Blocks at X ≈ touching → X ≈ several feet → back to touching, operator out of
the room throughout, B1 left untouched as reference. If separation grows with
X it is path; if it is flat, it is silicon. That is one capture and it
subsumes the rotation question this document set out to answer.
