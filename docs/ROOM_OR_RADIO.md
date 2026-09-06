# Room or radio?

**Whether a WiFi device can be identified by its crystal oscillator, or
whether the measurement is dominated by where the device is standing.**

Braeden Keena · August 2026 · `C:\dev\csi-array`

---

## Summary

Every radio is driven by a quartz crystal, and no two crystals are cut
identically. The resulting frequency offsets are properties of the silicon, so
in principle they identify a transmitter in a way that survives changing its
MAC address. This project built an instrument to measure them from commodity
ESP32 hardware and reported **99.7% blind-holdout accuracy** at telling three
transmitters apart.

That number was real and it was not measuring what it was named after.

Across a month of further testing the accuracy fell to **at or below chance
across sessions**, and the cause turned out to be an experimental design flaw
rather than a limit of the algorithm: **the three transmitters had always been
in three different rooms.** Device identity and position had never been
separable in the dataset.

A direct test settles it. With all three transmitters moved onto one surface
four feet apart, **two of them become statistically indistinguishable (0.2σ
and 0.6σ on two independent receivers)** where the same pair had read **7.9σ**
apart the night before with one of them behind a wall. The same physical board
reads **+0.0552 rad/subcarrier** in one room and **+0.0087** in another — a
**19.6σ** displacement of the quantity being used as its hardware signature,
for an oscillator that never changed.

**Conclusion: on this hardware, with this estimator, in a domestic multipath
environment, what is being measured is predominantly the propagation path, not
the transmitter.**

---

## 1. The physics, and why the idea is reasonable

When a WiFi receiver decodes a frame it estimates the channel on every OFDM
subcarrier — a complex number per subcarrier describing how the radio path
altered that frequency. That estimate is **Channel State Information**.
Consumer chipsets discard it after equalisation; the ESP32 is one of the few
inexpensive parts that will hand it over.

For a 20 MHz non-HT frame the per-subcarrier phase behaves as

```
phase(k) = slope·k + intercept + channel(k) + noise
```

for subcarrier index *k*, where:

- **slope** (radians per subcarrier) is proportional to the sampling timing
  error. Its stable component is **Sampling Frequency Offset (SFO)**, a
  property of the transmitter's crystal.
- **the intercept's frame-to-frame rate of change** carries residual **Carrier
  Frequency Offset (CFO)**, also crystal-bound.
- **channel(k)** is multipath — smooth, but not linear, and it changes when the
  room changes.
- **noise** is measurement error, worse on ESP32 because it has no hardware
  phase calibration.

Two of those terms are properties of the radio and two are properties of the
room. **The entire engineering problem is separating them**, and the entire
finding of this study is that the separation was not achieved.

---

## 2. The instrument

Three ESP32 beacons broadcasting identical ESP-NOW packets at a nominal 100 Hz
on a fixed channel, and one or two ESP32 receivers running promiscuous capture,
streaming binary telemetry over USB to a host that does all the signal
processing. **1,471 → 2,631 lines of C on ESP-IDF; 33,508 lines of Python
across 61 files.** Roughly **45 million captured frames** over ~44 GB.

The processing chain, per frame:

1. Map FFT index to physical subcarrier, drop DC and the guard bands, keep the
   52 that carry signal. *(Verified against the silicon: guard bins read
   exactly zero in 4,994 of 5,000 sampled frames.)*
2. Unwrap phase with a temporal continuity correction, so the intercept series
   is differentiable rather than a sawtooth.
3. Fit the phase-versus-subcarrier line by **RANSAC** rather than least
   squares, so multipath curvature becomes outliers to be ignored instead of
   error that biases the slope.
4. Collapse frames to one observation per 64-frame window by robust median.
5. Optionally subtract a known reference beacon's smoothed track, intended to
   cancel receiver-side drift.
6. Score observations by **Mahalanobis distance** against a per-source Gaussian,
   which under the model is χ²-distributed — so the accept/reject thresholds
   correspond to real confidence levels rather than tuned constants.

Evaluation uses a **chronological** train/test split: the first 60% of each
source's windows train, the last 40% are classified blind. Chronological rather
than random matters — it means the test windows are later in time than the
training ones, so the score reflects performance against drift the model has
not seen.

---

## 3. The original result, and its erosion

**99.7% over 7,497 test windows**, one receiver, 2026-07-13.

Then a second receiver's captures of the same sessions were added, and it fell
to **95.7% over 14,234 windows**. That drop is a cross-receiver generalisation
gap: in the combined run the reference beacon's entire test set comes from the
second receiver while its model trained 87.7% on the first.

Further tests, each making it worse:

| test | result |
|---|---|
| Identify a device in a *later session* on a fixed receiver | **29.7%**, against **33.3% chance** on three classes |
| Recognise the reference beacon itself across sessions | **18.1%** |
| How far does the signature wander over four untouched minutes? | **0.56 to 4.97 × the entire between-device spread**, on 5 of 6 cells |
| Can averaging recover it? | Allan deviation falls as **τ^−0.47** out to τ ≈ 10 s, then **rises**. 256× more averaging buys 20%. |
| Does reference subtraction repair the drift? | Removes **7–46%** of the drift energy; the residual is **2.2–7.1×** the between-device spread. The drift is not common-mode, so it cannot be subtracted. |

**One control deserves separate mention**, because it rules out the obvious
explanation. If the averaging machinery were broken, more averaging would not
help. Shuffling the same frames in time and re-averaging recovers the ideal
**1/√W** exactly — measured **15.7, 19.5, 17.4** against a predicted **16** for
W = 256. In true temporal order the same operation yields **1.10–1.70**. The
averaging is working perfectly. **There is simply nothing left to average away
after the first second.**

At this point the fair conclusion was that the feature does not carry identity.
It was the wrong conclusion, or rather an incomplete one, and finding out why
required leaving the data entirely.

---

## 4. The confound

The three beacons live where they live. One on a side table in an open-plan
living space, one on a television in a bedroom, one beside a desktop PC in a
third room. The receivers are on the living-room wall.

**Every between-device measurement this project has ever produced was taken
with the transmitters on non-comparable propagation paths.** "These devices are
distinguishable" and "these positions are distinguishable" are the same
measurement in this dataset, and have been since July.

Nothing in 45 million rows records where any hardware was. The layout was
established by drawing a floor plan on paper.

This is the whole finding, and it is worth being precise about what kind of
error it is. **It is not a bug and no figure was computed incorrectly.** It is a
design flaw: a variable that was never varied, and therefore never separated
from the variable of interest.

---

## 5. The experiment

**Move the transmitters onto one surface and repeat the measurement.**

Capture `*_20260828_022627.csv`, both receivers, 4 h 21 m. All three beacons
placed at one position roughly four feet apart. Two on battery, one on mains.
Operator present and moving at the start, then absent.

**The analysis window is t = 2,400 → 4,700 s** — 38 minutes, all three
transmitters up, room unoccupied. The window ends where it does because two
beacons were on battery and the batteries died: **B1 at t = 4,721 s and B3 at
t = 8,974 s, both receivers agreeing to within one second.**

The comparison case is the previous night's capture with the same three
beacons in three different rooms, windowed to 34 unoccupied minutes.

---

## 6. Results

### 6.1 Co-location collapses the separation

Pairwise centroid separation, both receivers, **no reference correction**:

| pair | s3 | d0wd |
|---|---:|---:|
| B1 – B3 | 5.2σ | 2.1σ |
| B2 – B1 | 4.5σ | 2.3σ |
| **B2 – B3** | **0.7σ** | **0.2σ** |

Against the same pair the night before, with B3 behind a wall: **7.9σ.**

**A 13× collapse from moving one board into the same room.** The raw SFO
values for that pair are **+0.0090 and +0.0087** on one receiver and **+0.0086
and +0.0086** on the other. The population standard deviation between units is
0.00237, so those gaps are **0.13σ and 0.00σ** in the feature itself.

### 6.2 The same board changes by 19.6σ when it changes rooms

| B3, raw SFO | value |
|---|---:|
| bedroom, on a television | **+0.0552** |
| kitchen bar, 4 ft from the next board | **+0.0087** |

**Same board, same firmware, adjacent nights.** In between-unit terms that is a
**19.6σ** displacement of the quantity being used as its hardware identity.

Over the same interval, B1 moved between two positions **within the same
room** and read **+0.0132 → +0.0131** — a displacement of **0.04σ.** Unchanged.

**Re-derived 2026-08-28.** Both values come from these two commands, and the
bedroom figure is **receiver-specific — it appears on `s3` and not on `d0wd`**:

```
python pc\rff_offline.py data\raw\s3_20260827_140642.csv --after 2531 --before 4579
python pc\rff_offline.py data\raw\s3_20260828_022627.csv --after 2400 --before 4700
```

The first prints `f4:2d:c9:70:72:30  +0.0552` and `a4:f0:0f:77:91:20  +0.0132`;
the second prints B3 at `+0.0087` and B1 at `+0.0131`. Neither command takes
`--ref-mac`, so these are raw. `BETWEEN_UNIT_SD = 0.00237`
(`pc/exp_ambient_separation.py:79`), giving 0.0465 / 0.00237 = **19.62σ**.

**The same window on `d0wd` gives B3 = +0.0048**, and blocks A and A′ give
+0.0144 and +0.0094. An earlier pass searched `d0wd` first, found nothing near
+0.0552, and came close to reporting the figure as unsupported. **That
disagreement between receivers is §6.3, not an error** — but it means any
future check of this number must name the receiver before concluding anything.

### 6.3 Two receivers agree only when the transmitters are together

Disagreement between the two receivers about **the same transmitter at the same
instant**, raw:

| beacon | beacons in three rooms | beacons co-located | change |
|---|---:|---:|---:|
| B1 | 0.0055 | 0.0019 | 2.9× |
| B2 | 0.0241 | 0.0004 | **60×** |
| B3 | **0.0504** | **0.0001** | **504×** |

With the beacons separated, the two receivers measured B2 at **+0.0120 and
−0.0121** — *opposite signs* for one transmitter at one moment. Co-located,
they agree on B3 to one part in ten thousand.

The pairwise *ordering* also inverts when the beacons are separated: B2–B1 is
the smallest separation on one receiver (0.2σ) and the largest on the other
(8.8σ). Co-located, both receivers produce the same ordering.

**A property of a crystal cannot depend on which receiver is listening.**

### 6.4 The reference correction makes it worse

The pipeline subtracts a designated reference beacon's smoothed track from
every other source, intending to cancel receiver-side error. On the co-located
capture, this **increases** cross-receiver disagreement — 4× on one beacon,
**19×** on another.

The mechanism is direct: the reference beacon's own value differs between the
two receivers by 0.0019. Subtracting its track hands that difference to every
other source, which did not previously have it.

### 6.5 Carrier frequency offset contributes nothing

Under the most favourable conditions available — co-located, unoccupied,
uncorrected — the three beacons' CFO medians are **+0.3, −0.0 and −0.0 Hz**
against within-device IQRs of **7.3, 7.3 and 5.5 Hz**. The entire between-device
signal is about **4% of the within-device spread**.

This is expected: the ESP32 corrects most CFO in hardware, and what remains is
aliased at the observed frame arrival rate. **SFO slope is the only candidate
feature, and §6.1–6.3 is what it does.**

### 6.6 An incidental result: the instrument detects people

The same window, split by whether the operator was in the room:

| | operator present | room empty | change |
|---|---:|---:|---:|
| B2 SFO IQR | 0.0052 | 0.0006 | **8.7× tighter** |
| B3 SFO IQR | 0.0045 | 0.0012 | 3.8× tighter |
| B1 SFO IQR | 0.0021 | 0.0006 | 3.5× tighter |

The medians barely move; the spread collapses. A human body in the room appears
as **variance on every link simultaneously**, which is what a moving scatterer
in a multipath field should produce. Noted because it is the same phenomenon
seen from the other side, and because it is a cleaner presence detector than
the amplitude-domain pipeline built for that purpose.

---

## 7. Conclusion

**The measured quantity is dominated by the propagation path.**

Two physically distinct boards four feet apart are indistinguishable at 0.2σ.
One board carried across an apartment moves 19.6σ. Two receivers observing the
same transmitter disagree by 500× more when the transmitters are separated than
when they are together, and invert each other's rankings entirely. None of
those are behaviours of a crystal.

**This does not show that RF fingerprinting is impossible.** Published successes
in the field generally use software-defined radios with far greater bandwidth,
transient turn-on analysis, and controlled channels. It shows that **this
instrument** — ESP32 CSI at 20 MHz, phase-slope estimation, domestic multipath —
cannot separate the transmitter from the room, and that the original 99.7%
was measuring a room.

---

## 8. Limits

- **One 38-minute window per condition, on two adjacent nights.** The central
  comparison is between captures, not within one.
- **Nothing in §6.3–6.4 was pre-registered.** It was found by checking a
  caveat. The direction and magnitude should be predicted in advance and
  re-tested before either is treated as established.
- **Power source is confounded with device identity** in the co-located
  capture — two beacons on battery, one on mains. The B2–B3 collapse survives
  this (they differ in power source and collapse anyway); B1's distinctness
  does not, and is not relied on.
- **Three devices.** Every accuracy figure here is against N = 3, chance 33.3%,
  and the class count is printed beside each one for that reason.
- **The dataset is not published.** Running promiscuously, the array captured
  every transmitter in range including third-party hardware whose owners did
  not consent, and the captures are a log of when a home was occupied. The
  pipeline can be read; the results cannot be independently re-derived from it.

---

## 9. Method notes

Every experiment in this project is written in two stages: **hypotheses,
decision thresholds and controls are written to disk and dated before the
analysis is run**, and results are appended below a banner afterwards. Several
of the nulls here were produced by controls designed specifically to kill the
author's own result — in one case a variance-matched random variable
reproduced a +26 percentage-point finding exactly, which retired it.

A running error log accompanies the project, currently **57 entries**. Its
load-bearing field is not what the error was but **how it was caught**, because
only the detection method transfers to the next one. Four of the errors in this
document's own analysis are recorded there, including a statistic that was
reported as a positional result and turned out to be the between-device
separation wearing a different label.

### Reproduce

```
python pc\rff_offline.py data\raw\s3_20260828_022627.csv --after 2400 --before 4700
python pc\rff_offline.py data\raw\d0wd_20260828_022627.csv --after 2400 --before 4700
python pc\rff_offline.py data\raw\s3_20260827_140642.csv --after 2531 --before 4579
```

Omitting `--ref-mac` disables reference correction. Every figure in §6 comes
from one of those three commands with and without it.
