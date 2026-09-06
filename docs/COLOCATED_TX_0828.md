# COLOCATED_TX — the first capture with all three beacons in one place

**2026-08-28.** This is a **measurement, not a pre-registered test.** The
capture was taken to co-locate the transmitters; the reference-correction
finding in §4 was not anticipated and no bar was frozen for it. It is written
up as an observation with its own limits attached, and §6 says what would have
to be pre-registered to make it a result.

Read-only on `data/raw/`. No git command run.

---

## 0. Why this capture exists

Every between-device figure this project has produced was measured with the
three beacons **in three different rooms** (`ROTATION_PREREG.md` §1.1a–1.1b).
`COLOCATED_0823.md` co-located the two *receivers*. Nothing had ever
co-located the *transmitters*, which means "these devices are distinguishable"
and "these positions are distinguishable" have never been separable in this
dataset.

**This is the first capture that separates them.**

---

## 1. The capture

`data/raw/s3_20260828_022627.csv` and `d0wd_20260828_022627.csv`.
Start 02:26:27, span **15,693 s (4 h 21 m)**, both receivers.

**Arrangement, operator-stated: all three beacons at POS4 (kitchen bar, main
open space), spread roughly 4 ft apart. B1 and B3 on battery; B2 on mains.**
Receivers untouched in their usual position. Operator present and moving for
the opening stretch, then asleep.

### 1.1 Battery deaths, located in the data

| beacon | last frame, s3 | last frame, d0wd | power |
|---|---:|---:|---|
| **B1** `a4:f0` | **t = 4,721 s** | t = 4,722 s | battery |
| **B3** `f4:2d` | **t = 8,974 s** | t = 8,974 s | battery |
| B2 `28:05` | t = 15,693 s | t = 15,692 s | **mains** |

**Both receivers agree to within one second on both deaths**, and there are no
gaps over 30 s anywhere before them — the units ran continuously and then
stopped. The two battery-powered beacons died; the mains one did not.

**Consequence: only t = 0 → 4,721 s carries all three transmitters.** Any
whole-file figure from this capture describes a population that changes twice.

### 1.2 The analysis window

**t = 2,400 → 4,700 s. 38 minutes, all three up, operator settled.**

s3: 544,255 frames to the DSP, 8,455 windows (2,894 / 3,245 / 2,315 per
source). d0wd: 327,497 frames, 5,039 windows (1,521 / 1,444 / 2,073).

```
python pc\rff_offline.py data\raw\s3_20260828_022627.csv --after 2400 --before 4700
python pc\rff_offline.py data\raw\d0wd_20260828_022627.csv --after 2400 --before 4700
```

---

## 2. Two boards four feet apart are indistinguishable

Pairwise centroid separation, both receivers, reference-corrected on B1:

| pair | s3 | d0wd |
|---|---:|---:|
| B1 – B3 | 5.3σ | 2.0σ |
| B2 – B1 | 4.7σ | 2.1σ |
| **B2 – B3** | **0.6σ** | **0.2σ** |

**And against the same pair the night before, with B3 in the bedroom:**

| B2 – B3 | separation |
|---|---:|
| `ROTATION_PREREG` block B — B3 behind a wall | **7.9σ** |
| here — B3 four feet from B2 | **0.6σ** |

**A 13× collapse from moving one board into the same room.**

Raw SFO for the pair: **−0.0042 and −0.0044** (s3), **−0.0026 and −0.0025**
(d0wd). Against `BETWEEN_UNIT_SD = 0.00237` those gaps are **0.08σ and 0.04σ**
in the feature itself. In classification, B3 scores 366 correct against **560
of its test windows landing on B2** (s3).

**Both receivers rank the three pairs identically** — B2–B3 far below the two
B1 pairs. Magnitudes differ by about 2.4×, which is the receiver term and is
not small; the *ordering* is the same.

---

## 3. B1 is genuinely distinct, and it is not a reference artifact

An earlier reading of §2 flagged that B1's separations might be structural,
since `reference.py` pins the reference near zero by construction. **That was
wrong, and removing the correction settles it.**

**Raw, no reference correction:**

| beacon | s3 | d0wd |
|---|---:|---:|
| B2 | +0.0090 | +0.0086 |
| **B1** | **+0.0131** | **+0.0112** |
| B3 | +0.0087 | +0.0086 |

B1 sits **0.0026–0.0044 rad/sc** away from the other two — roughly 1–2 ×
`BETWEEN_UNIT_SD` — on both receivers independently, with nothing pinned.

And the separations barely move when the correction is removed:

| pair | s3 corrected → raw | d0wd corrected → raw |
|---|---|---|
| B2 – B1 | 4.7 → **4.5σ** | 2.1 → **2.3σ** |
| B1 – B3 | 5.3 → **5.2σ** | 2.0 → **2.1σ** |
| **B2 – B3** | 0.6 → **0.7σ** | 0.2 → **0.2σ** |

**§2's finding is a raw measurement.** It does not depend on the correction.

---

## 4. Reference correction increases cross-receiver disagreement

The unanticipated result, and the one with the widest consequences.

**Uncorrected, the two receivers agree on the same transmitter almost exactly:**

| beacon | s3 raw | d0wd raw | disagreement |
|---|---:|---:|---:|
| B2 | +0.0090 | +0.0086 | **0.0004** |
| B3 | +0.0087 | +0.0086 | **0.0001** |
| B1 | +0.0131 | +0.0112 | 0.0019 |

**Corrected, they disagree far more:**

| beacon | s3 corrected | d0wd corrected | disagreement | change |
|---|---:|---:|---:|---:|
| B2 | −0.0042 | −0.0026 | **0.0016** | **4× worse** |
| B3 | −0.0044 | −0.0025 | **0.0019** | **19× worse** |
| B1 | −0.0000 | +0.0001 | 0.0001 | pinned by construction |

### 4.1 The mechanism, and it is not subtle

`reference.py` subtracts B1's Kalman-smoothed track from every other source.
**B1's own value differs between the two receivers by 0.0019.** Subtracting
B1's track therefore *hands that 0.0019 to B2 and B3*, which did not have it.

Before correction, B3 is measured at +0.0087 and +0.0086 by two independent
receivers — a disagreement of one ten-thousandth. After correction, the same
transmitter reads −0.0044 and −0.0025. **The correction is the entire source
of the disagreement.**

The stated purpose of reference-beacon subtraction is to cancel receiver-side
common-mode error. **On this capture it does the opposite, by an order of
magnitude.**

### 4.2 Relation to `REFERENCE_CHOICE.md`

That document (§0) found *"No reference condition meaningfully reduces the
receiver term. The one that appears to is a degeneracy, not common-mode
rejection."* This capture is consistent with it and goes one step further:
the term is not merely un-reduced, it is **increased**, and §4.1 gives the
mechanism.

**Caveat, and it matters.** `REFERENCE_CHOICE` tested five reference
conditions on a 2026-08-22 capture with the beacons in three different rooms.
This is one condition on one 38-minute co-located window. The two are not
like-for-like and this does not revise its figures.

---

## 5. The operator as a variable

The first ~10 minutes of this same capture were scored separately, while the
operator was awake and moving. Same beacons, same positions, same night — the
only difference is a person in the room.

| | s3 | d0wd |
|---|---|---|
| **moving, ~81k/104k frames** | most separable **B1–B3 (3.1σ)**, least **B2–B3 (1.2σ)** | most **B2–B1 (3.0σ)**, least **B1–B3 (0.9σ)** |
| **settled, t=2400–4700** | ordering **agrees** with d0wd | ordering **agrees** with s3 |

**With a person moving, the two receivers ranked the pairs in opposite orders.
With the room still, they agree.**

**This is suggestive and it is not established.** The moving windows are a
tenth the size of the settled one, so noise alone could produce a rank
reversal at those sample sizes. Recorded because the comparison is available
and because it points at the experiment in §6.

---

## 6. Limits, and what would make this a result

- **One 38-minute window, one night, three devices.** Everything here is a
  single observation.
- **Nothing was pre-registered.** §4 in particular was found by checking a
  caveat, not by testing a frozen hypothesis. The bar it would have to clear
  was never written down in advance.
- **B1 and B3 were on battery, B2 on mains.** Power source is confounded with
  device identity in this capture, and B1's distinctness in §3 has that
  confound sitting on it. B2 and B3's collapse does *not* — they differ in
  power source and still read 0.2–0.7σ apart, which is the harder direction
  for a confound to explain.
- **The 13× collapse in §2 compares two different nights.** The 7.9σ comes
  from `ROTATION_PREREG` block B on 27 August. Different session, different
  duration.
- **§5's inversion is underpowered** and is offered as a pointer only.
- Nothing here is fused with `pc/occ/`. No device-ID figure is revised. The
  ~77 % same-model figure is not quoted.

**To make §4 a result, pre-register it:** state in advance that
cross-receiver disagreement will be computed for each beacon with and without
reference correction, on a stated window, with the direction and factor
predicted before running. Then run it on a fresh capture. It would take one
overnight and it is the highest-value hour available, because **if it holds,
every reference-corrected figure in this repo carries an injected receiver
term.**
