# FAN A/B PREREG — does the fan move the SFO separation?

> **STAGE 1. Written 2026-08-29, before the capture exists.** Nothing above the
> Stage 2 banner in §6 may be edited after the capture starts. If the bars in
> §3 are not met, §6 says they were not met.

---

## 1. Why

`SEVEN_NIGHT_PREREG` §10 night 1 read **B2–B3 at 6.8σ (d0wd) / 9.2σ (s3)**
against a bar of 1.0σ. The same pair on 2026-08-28 read **0.2σ / 0.7σ**.

The only controlled difference the operator can name between those two nights
is the **fan**: on throughout the 28th, off on the 29th. The AC cycles on a
thermostat and was running on both, so it is not the between-night variable.

This is a 45-minute direct test of that one thing.

## 2. Design — fixed before running

**One continuous capture. Three blocks of 15 minutes: ON → OFF → ON.**

- `A` fan **on**, 15 min
- `B` fan **off**, 15 min
- `A′` fan **on**, 15 min

**A→B→A′, not A→B**, for the reason `ROTATION_PREREG.md:71` already gives:
a single before/after cannot separate the treatment from drift. A fan effect
reverses when the fan comes back. Drift does not.

- **Beacons and receivers are not touched.** B1/B3/B2 left to right on the bar,
  B2 wrapped as it currently is, receivers on the wall. The fan switch is the
  only thing that moves.
- **Operator present for all three blocks, seated in one position.** Presence is
  an 8.7× IQR effect (`ROOM_OR_RADIO.md` §6.6), so it must be a *constant*, not
  a variable. Being in the room is fine. Getting up in one block and not another
  is not.
- **Label each transition** in the capture: `fan on A`, `fan off B`,
  `fan on Aprime`.
- **Score the last 12 minutes of each block, discard the first 3.** The flip
  requires standing up and walking; that movement must sit outside the scored
  data.
- Raw, no `--ref-mac`, both receivers, computed independently.

`BETWEEN_UNIT_SD = 0.00237` (`pc/exp_ambient_separation.py:79`).

## 3. Predictions, frozen

**P1 — direction.** B2–B3 centroid separation is **larger in B (fan off) than
in both A and A′ (fan on)**, on **both** receivers independently.

**P2 — reversal, the drift control.** A′ returns toward A rather than
continuing past B:

> **|A′ − A| < |B − A|**, on both receivers.

If B2–B3 slides monotonically A → B → A′, that is drift and **P1 is not
evidence about the fan even if it passes.**

**P3 — secondary, no bar.** RSSI IQR per beacon is recorded for each block. A
fan moving air through the propagation path plausibly widens it. No threshold
is set; this is recorded, not tested.

## 4. Verdict table — frozen

| outcome | condition |
|---|---|
| **FAN IMPLICATED** | P1 holds **and** P2 holds |
| **DRIFT, NOT FAN** | P1 holds but P2 fails — monotone slide |
| **FAN CLEARED** | B is not the largest block on either receiver |
| **MIXED** | receivers disagree, or one prediction holds and the other is unevaluable |

Anything not meeting a row is reported as **MIXED**, in that word.

## 5. What this cannot answer

- **It is 3 × 12 scored minutes.** `LABELLED_EVENTS_0823.md` §20 measures the
  slope wandering 0.56–4.97 × the between-device spread over **four untouched
  minutes**. A 12-minute block sits barely above that. **This test is
  underpowered by construction** and a null means "not detected here", never
  "no effect".
- **Operator present throughout**, so nothing here transfers to the empty-room
  overnight windows the seven-night series scores.
- It does not touch P1/P2/P3 of `SEVEN_NIGHT_PREREG`, revise night 1, or
  license any edit to `ROOM_OR_RADIO.md`.

## 6. Stage 2 — results

> **Nothing below this line existed when §1–§5 were written.**

`d0wd_20260829_122648.csv` / `s3_20260829_122648.csv`, 4,208 s total.

### 6.1 What was actually run, and how it differs from §2

**The executed design is the inverse of the frozen one: OFF → ON → OFF, not
ON → OFF → ON.** B3 died at t = 163.8 s, three minutes into the first attempt,
and stayed dead for 954.6 s. After it was revived on a fresh battery the
operator restarted from a fan-off state, so the three usable blocks run
off → on → off.

**P1 and P2 are evaluated on their substance, not their letters.** P1 predicts
larger separation with the fan off; P2 predicts the third block returns toward
the first rather than continuing past the second. Both survive the inversion
unchanged. The block *names* in §2 do not apply and are not used below.

**Power deviates from §2 as corrected:** B1 and B2 on mains, B3 alone on
battery. Mismatched, in the opposite direction to night 1.

**Scored windows** — last 720 s of each block, per §2:

| block | fan | window |
|---|---|---|
| OFF-1 | off | 1,527 – 2,247 s |
| ON | on | 2,554 – 3,274 s |
| OFF-2 | off | 3,487 – 4,207 s |

**Zero beacon gaps over 5 s after t = 1,243 s.** All three ran clean through
every scored window.

### 6.2 Result — B2–B3 raw centroid separation

| block | fan | d0wd | s3 |
|---|---|---:|---:|
| OFF-1 | off | **0.9σ** | **0.8σ** |
| ON | on | **0.2σ** | **0.2σ** |
| OFF-2 | off | **0.3σ** | **0.8σ** |

**P1 HOLDS on both receivers.** Both fan-off blocks exceed the fan-on block on
both receivers independently.

**P2 HOLDS on both receivers.**

| | \|OFF-2 − OFF-1\| | \|ON − OFF-1\| | verdict |
|---|---:|---:|---|
| d0wd | 0.6 | 0.7 | holds, marginally |
| s3 | **0.0** | 0.6 | holds cleanly |

On s3 the reversal is textbook: 0.8 → 0.2 → 0.8. Not a monotone slide, so this
is not drift.

### 6.3 Verdict per §4: **FAN IMPLICATED**

P1 and P2 both hold, on both receivers, against bars frozen before the capture.

### 6.4 And it does not explain night 1

**The effect is about 0.6σ. Night 1 was 6.8σ and 9.2σ.**

Every block today — fan on *and* fan off — sits below the 1.0σ bar that night 1
missed by a factor of seven. Whatever moved the pair on 2026-08-29 overnight,
**the fan is not big enough to be it.** The fan is implicated in a small effect
and cleared as the explanation for the large one.

### 6.5 Limits, and they are not small

- **§5 said this is underpowered and it is.** `LABELLED_EVENTS_0823.md` §20 puts
  the slope wandering 0.56–4.97 × the between-device spread over four untouched
  minutes. **A 0.6σ effect sits inside that band.** P1 and P2 both clearing is
  suggestive, not established.
- **The dab is confounded with the blocks.** Induction events at 1,636–1,716 s
  (inside OFF-1) and 2,880–2,952 s (inside ON). **None in OFF-2.** The one block
  with no induction event is the one whose d0wd value is lowest.
- **Text-message activity is clustered**, twelve labelled events between
  1,676 and 2,364 s — concentrated in OFF-1 and early ON, absent from OFF-2.
- **Operator present throughout**, so nothing here transfers to the empty-room
  overnight windows `SEVEN_NIGHT_PREREG` scores.
- **Nothing here revises night 1, `ROOM_OR_RADIO.md`, or the case study.**

### 6.6 Unpredicted observation

B1 is stably separated from both other beacons in every block, on both
receivers — 7.0σ to 9.5σ on s3, 3.7σ to 5.1σ on d0wd — while B2 and B3 sit on
top of each other. Its raw SFO barely moves across the three blocks
(+0.0200 / +0.0189 / +0.0189 on s3). No bar was frozen for this.

