# Clock-twin investigation — 2026-07-13 captures

**Date:** 2026-08-15 · **Scope:** read-only re-analysis of `data/raw/`
· **Tool:** `pc/twin_probe.py` (new, read-only) driving `pc/rff/` through
`pc/rff_offline.py`

---

## Verdict

**Yes — a sub-3σ transmitter pair is present in the desk-only 2026-07-13
data, before node3 enters the analysis. No — it is not the clock twin.**

Three findings, in decreasing order of confidence:

1. **The desk-only 07-13 population contains exactly two characterizable
   transmitters, and they sit at 2.54σ** (bootstrap 95% CI 2.23–2.84),
   below the project's own >3σ reliable-separation line. The pair is the
   reference beacon `a4:f0:0f:77:91:20` and `84:7b:57:cc:20:0e`. So the
   claim that a hard transmitter pair predates node3 is **correct**, and
   the previous investigation's conclusion — that the difficulty was
   introduced by adding node3 — is **wrong**.

2. **`84:7b:57:cc:20:0e` is not the twin unit under a different address,
   and is not one of Braeden's boards at all.** The two transmit
   *simultaneously*: in `rx_20260714_031131.csv` all 1,114 frames of
   `84:7b:57:cc:20:0e` have an `f4:2d:c9:70:72:30` frame within **3.82 ms**,
   over **111.6 minutes** of shared airtime. One radio cannot be two
   addresses at once. The reflash hypothesis is refuted on evidence, not
   on plausibility.

3. **The 99.7% → 95.7% drop is not caused by a clock twin.** The twin is
   absent from *both* datasets — both are 07-13, and `f4:2d:c9:70:72:30`
   does not appear anywhere until 07-14. The drop is produced jointly by
   the second receiver and by the marginal `84:7b` pair, with the second
   receiver as the trigger. Mechanism in §6.

The `CLAUDE.md` line attributing the drop to the clock twin **should be
corrected** (§7).

Braeden was right about the important thing — the previous check was
invalid and the difficulty is transmitter-side and predates node3. He was
wrong about the specific mechanism: the pre-node3 hard pair is a piece of
ambient traffic, not the twin beacon.

---

## 1. Why the previous check was invalid, and what replaced it

The earlier investigation searched the 07-13 captures for the string
`f4:2d:c9:70:72:30`, found zero occurrences, and concluded the twin was
absent. That test cannot support its conclusion on this project's own
premise: a MAC is not an identity, and the inventory naming that MAC
(`docs/HANDOFF.md`, dated 2026-07-15) postdates the captures (07-13) by
two days.

This investigation searched for the **phenomenon** instead: are there two
or more sources in the desk-only 07-13 data whose (CFO, SFO) clock
signatures are statistically inseparable?

The DSP is not reimplemented. `pc/twin_probe.py` imports
`collect_observations` and `feature` directly from `pc/rff_offline.py`, so
every figure below comes out of the same `FrameEstimator` →
`WindowAggregator` → `ReferenceNormalizer` → `Discriminator` path the
project's own science run uses. `twin_probe.py` adds only bookkeeping:
per-file cache shards, pair ranking, bootstrap spreads, transmit-cadence
statistics, and cross-epoch matching.

**Equivalence check.** On the subset
`desk_20260713_{112617,131746,133556}.csv`, `rff_offline.py` and
`twin_probe.py` agree exactly:

| quantity | `rff_offline.py` | `twin_probe.py` |
|---|---|---|
| windows, `84:7b:57:cc:20:0e` | 30 | 30 |
| windows, `a4:f0:0f:77:91:20` | 1623 | 1623 |
| separation (train-60% models) | 1.6σ | 1.59σ |
| holdout accuracy | 615/662 = 92.9% | 615/662 = 92.90% |
| confusions ref → `84:7b` | 41 | 41 |

Reproduce:

```
python pc/rff_offline.py data/raw/desk_20260713_112617.csv data/raw/desk_20260713_131746.csv data/raw/desk_20260713_133556.csv --ref-mac a4:f0:0f:77:91:20 --min-windows 4
python pc/twin_probe.py collect --tag verify data/raw/desk_20260713_112617.csv data/raw/desk_20260713_131746.csv data/raw/desk_20260713_133556.csv
python pc/twin_probe.py sep --tag verify --min-windows 4 --boot 0 --train-frac 0.6
python pc/twin_probe.py holdout --tag verify --min-windows 4
```

Cache shards default to `../twin_probe_cache` (a sibling of the repo, so
it cannot race `data/cache/expwin`); override with `TWIN_PROBE_CACHE`.

---

## 2. Source census — desk-only 07-13

14 files, **1,235,088 frames, 59 distinct source MACs.**

| frames | source | note |
|---:|---|---|
| 1,223,567 | `a4:f0:0f:77:91:20` | reference beacon (99.07% of all frames) |
| 5,245 | `84:7b:57:cc:20:0e` | globally-administered OUI; see §4 |
| 3,599 | `1e:ce:51:f3:0d:fa` | private/randomized; frame-level mean RSSI −40.6 over these files — a close-in client |
| 379 | `a0:55:1f:10:c0:a7` | |
| 378 | `1c:ce:51:f3:0d:fa` | same base address as `1e:ce…` with the locally-administered bit cleared |
| 313 | `64:fa:2b:70:85:54` | |
| 306 | `5a:ad:4d:7c:b0:d3` | |
| 227 | `76:eb:b0:c0:68:4d` | |
| 199 | `f4:69:42:f2:d2:af` | |
| 166 | `06:74:95:e9:bc:40` | |
| 112 | `a6:0d:a5:a1:4f:b6` | |
| 109 | `06:f1:55:b3:34:ba` | |
| <64 | 47 further MACs | below one 64-frame window |

**`f4:2d:c9:70:72:30` and `28:05:a5:2f:fa:48` appear zero times in the
07-13 captures — on either receiver.** Both first appear on 07-14. This
part of the previous investigation's factual finding is confirmed; only
its interpretation was unsupported.

Only **2 sources survive to characterization** at the pipeline's default
64-frame window with reference correction:

| source | windows | with CFO | ref-corrected features |
|---|---:|---:|---:|
| `a4:f0:0f:77:91:20` | 18,670 | 18,670 | 18,670 |
| `84:7b:57:cc:20:0e` | 78 | 78 | 66 |
| `1e:ce:51:f3:0d:fa` | 4 | 4 | 3 |
| `76:eb:b0:c0:68:4d` | 1 | 1 | 1 |
| `06:f1:55:b3:34:ba` | 1 | 1 | 1 |

Everything else is ambient chatter too sparse, or too low-quality, to
clear the aggregator's inlier/residual gates. **The desk-only 07-13
"population" is a two-source problem.** That is worth stating plainly: the
99.7% headline is measured against a library of two devices, one of which
supplies 99.6% of the test windows.

---

## 3. Pairwise separation matrix

```
python pc/twin_probe.py sep --tag desk0713 --min-windows 4 --boot 400
```

### Per-source clock signature (reference-corrected)

| source | wins | sess | CFO med (Hz) | CFO IQR | CFO p5..p95 | SFO med (rad/sc) | SFO IQR | RSSI |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| `1e:ce:51:f3:0d:fa` | 3 | 3 | +0.89 | 0.48 | +0.0..+0.9 | −0.03739 | 0.00490 | −38.1 |
| `84:7b:57:cc:20:0e` | 66 | 8 | +0.08 | 0.34 | −0.4..+0.7 | −0.00625 | 0.00587 | −77.2 |
| `a4:f0:0f:77:91:20` | 18670 | 11 | −0.02 | 5.23 | −6.5..+6.4 | +0.00005 | 0.00173 | −75.6 |

### Matrix (σ, pooled covariance, all windows)

|  | `cc:20:0e` | `77:91:20` |
|---|---:|---:|
| `cc:20:0e` | — | **2.54** |
| `77:91:20` | **2.54** | — |

`1e:ce:51:f3:0d:fa` has 3 ref-corrected features — below
`Discriminator.MIN_CHARACTERIZED = 5` — so it cannot enter the matrix.
The matrix is 2×2 because the data supports nothing larger.

### Closest pair

| σ | bootstrap 95% CI (400 resamples) | pair |
|---:|---|---|
| **2.54** | [2.23, 2.84] | `84:7b:57:cc:20:0e` vs `a4:f0:0f:77:91:20` |

`min 2.54σ, median 2.54σ, max 2.54σ; 1 of 1 pairs below 3σ.`

Under `--train-frac 0.6` (the convention `rff_offline.report()` uses, which
builds the matrix from training windows only) the same pair reads
**2.10σ [1.85, 2.38]**. `README.md`'s "2.6 sigma" is the all-windows
figure and is consistent with 2.54σ.

### Per-axis decomposition

| pair | CFO d | SFO d | ΔCFO (Hz) | ΔSFO (rad/sc) |
|---|---:|---:|---:|---:|
| `cc:20:0e` vs `77:91:20` | 0.03 | **2.54** | +0.10 | −0.00692 |

pooled sd: CFO 3.914 Hz, SFO 0.00273 rad/sc.

**The entire separation lives in SFO; CFO contributes nothing (d = 0.03).**
That corroborates `HANDOFF.md`'s existing finding that CFO is aliased at
the beacon rate and SFO is the discriminating feature — and it matters
here, because `84:7b` transmits at ~2.4 fps against the reference's ~100
fps, so their CFO estimates are not even aliased into the same band and
could not have been compared meaningfully.

### Is 2.54σ a "clock twin"?

**No.** ΔSFO = 0.0069 rad/sc, seventeen times `HANDOFF.md`'s recorded
true-twin scale of 0.0004 rad/sc. The pair is close in σ not because the
crystals are alike but because `84:7b`'s own model is wide and poorly
conditioned (66 windows, SFO IQR 0.00587 vs the reference's 0.00173). It
is a **marginal, badly-estimated pair**, not a physical near-collision.
§4 shows part of that width is a measurement artifact.

For contrast, the genuine twin pair measured on 07-14
(`python pc/twin_probe.py sep --tag rx0714a --boot 200`):

| σ | 95% CI | pair | ΔSFO |
|---:|---|---|---:|
| **0.26** | [0.21, 0.30] | `a4:f0:0f:77:91:20` vs `f4:2d:c9:70:72:30` | +0.00080 |
| 1.99 | [1.90, 2.08] | `28:05:a5:2f:fa:48` vs `a4:f0:0f:77:91:20` | +0.00618 |
| 2.25 | [2.12, 2.36] | `28:05:a5:2f:fa:48` vs `f4:2d:c9:70:72:30` | +0.00697 |

0.26σ / 0.0008 rad/sc reproduces `HANDOFF.md`'s "0.0004 rad/sc apart, 0.3σ,
coin-flip" independently. **The clock twin is real. It is a 07-14-onward
phenomenon and has nothing to do with either headline accuracy number.**

---

## 4. What `84:7b:57:cc:20:0e` actually is

```
python pc/twin_probe.py timing --tag desk0713 --mac 84:7b:57:cc:20:0e
```

**Verdict: ambient traffic from a stationary third-party 802.11n device.
Not one of Braeden's boards.**

| property | `84:7b:57:cc:20:0e` | the three known ESP32 beacons |
|---|---|---|
| frame rate | ~2.4 fps (gap median 0.418 s) | 32–58 fps (gap median 0.0007–0.0013 s) |
| cadence regularity | CV 3.96; only **12.8%** of gaps within ±20% of median; p5 gap 0.000 s, p95 3.28 s, p99 7.83 s | tight, sub-2 ms |
| CSI buffer length | **mixed**: 4,448 × len-256, 795 × len-128 | **100% len-256**, all three units |
| frames per 2,754 s capture | 1,114 (07-14) | 88,010 – 158,537 |
| RSSI | −77.2, sd 0.7–2.8 within session | −64 to −79 |
| address type | globally administered (0x84 & 0x02 = 0) — a real vendor OUI, not randomized | vendor OUI |

A board flashed with this project's beacon firmware emits one frame format
at a fixed high rate. `84:7b` does neither. Its bursty pattern (sub-ms
bursts separated by multi-second silences) and mixed legacy/HT frame
formats are what a real Wi-Fi station's data traffic looks like. RSSI
stable to ±2 dB across six hours says it is stationary and not close by.

Its appearance history: 4 frames on 07-12, heavy on 07-13 (10 sessions,
15:45–21:06 UTC = 10:45–16:06 local, both receivers), 1,114 frames on
07-14, then absent from
`rx_20260714_030915`, `rx_20260715_201703`, `rx_20260722_204658`,
`occ_20260722_151807` and `harvest_afternoon`. Consistent with a
neighbouring or household device that was active on channel 6 that
weekend.

**Measurement caveat — this source's SFO is frame-format-dependent.**
Splitting its per-frame RANSAC slopes by CSI buffer length:

| capture | len=128 | len=256 |
|---|---|---|
| 07-14 20-min slice | n=62, median +0.00092 | n=774, median **+0.02926** |
| `desk_20260713_145302` | n=281, median +0.00248 | n=1545, median **+0.00599** |

The two formats give systematically different slopes for this source, so
its windowed SFO median depends on the format mix in each window. Whether
that is a PHY effect (HT vs non-HT LLTF conditioning) or an artifact of
the unwrap continuity anchor jumping between interleaved formats is **not
established here** — but it does mean `84:7b`'s wide SFO spread is partly
instrumental, and its 2.54σ proximity to the reference should not be read
as a statement about crystals. The reference and all three ESP32 beacons
are 100% len-256 and are unaffected.

---

## 5. Cross-epoch test — is any 07-13 source the twin under another address?

**No. Refuted, decisively.**

### 5a. The two addresses are on air at the same time

`rx_20260714_031131.csv` contains both:

| source | frames | span (UTC) |
|---|---:|---|
| `f4:2d:c9:70:72:30` | 1,089,773 | 07-14 08:11:32 – 13:40:43 |
| `84:7b:57:cc:20:0e` | 1,114 | 07-14 11:49:06 – 13:40:40 |

Nearest `f4:2d` frame to each `84:7b` frame: **p50 0.52 ms, p90 1.61 ms,
p99 3.02 ms, max 3.82 ms.** 1,114 of 1,114 (100%) within 100 ms.
Overlapping on-air window: **111.6 minutes.**

The reference `a4:f0:0f:77:91:20` likewise transmits alongside
`f4:2d:c9:70:72:30` throughout `rx_20260714_011619.csv` (138,939 and
158,537 frames in the same 2,754 s). Since the desk-only 07-13 population
is exactly `{a4:f0:0f:77:91:20, 84:7b:57:cc:20:0e}`, and **both** are shown
to be physically distinct from `f4:2d:c9:70:72:30` by simultaneous
transmission, no 07-13 source can be the twin unit under a different
address. This holds regardless of any oscillator statistic.

### 5b. Oscillator signatures agree — same capture, same receiver, same 20 minutes

Extracting the four transmitters from a 20-minute slice of
`rx_20260714_031131.csv` inside the overlap removes every drift and
receiver confound:

| source | wins | CFO med | SFO med | SFO IQR | RSSI |
|---|---:|---:|---:|---:|---:|
| `28:05:a5:2f:fa:48` | 697 | +0.23 | −0.00181 | 0.00134 | −77.7 |
| `84:7b:57:cc:20:0e` | 13 | +0.15 | **+0.02175** | 0.00202 | −77.8 |
| `a4:f0:0f:77:91:20` | 981 | +0.01 | +0.00005 | 0.00063 | −68.0 |
| `f4:2d:c9:70:72:30` | 945 | +0.02 | −0.00386 | 0.00056 | −63.9 |

|  | `2f:fa:48` | `cc:20:0e` | `77:91:20` | `70:72:30` |
|---|---:|---:|---:|---:|
| `2f:fa:48` | — | 24.38 | 1.93 | 2.33 |
| `cc:20:0e` | 24.38 | — | 22.45 | **26.71** |
| `77:91:20` | 1.93 | 22.45 | — | 4.26 |
| `70:72:30` | 2.33 | 26.71 | 4.26 | — |

`84:7b:57:cc:20:0e` vs `f4:2d:c9:70:72:30` = **26.71σ [22.67, 32.03]**,
ΔSFO 0.0245 rad/sc — sixty-one times the true-twin scale. It sits 22–27σ
from *all three* ESP32 units while they sit 1.9–4.3σ from each other.

*(σ is not comparable across runs: the pooled covariance shrinks in a
short capture, inflating every σ. ΔSFO in rad/sc is the comparable
quantity.)*

### 5c. The drift caveat, and why it does not change the verdict

A cross-**epoch** comparison alone would have been inconclusive.
`84:7b`'s own session-to-session SFO median wanders by **0.01064 rad/sc
(sd 0.00365 over 7 sessions)** on 07-13 —

```
python pc/twin_probe.py drift --tag desk0713 --macs 84:7b:57:cc:20:0e,a4:f0:0f:77:91:20
```

— which is *larger* than the 0.0058 rad/sc gap between its 07-13 centroid
and `f4:2d`'s 07-14 centroid. (The reference, by contrast, wanders only
0.00351 range / 0.00088 sd over 11 sessions.) So an SFO mismatch across
two days would not by itself have excluded a reflash. §5a is what settles
it, and §5b confirms it inside a single capture where no drift argument
applies.

Honest statement of what §5c means: **had the simultaneity evidence not
existed, this investigation would have returned "inconclusive," not
"refuted."** The strength of the verdict rests on §5a.

---

## 6. Attribution of the 99.7% → 95.7% drop

Both headline runs reproduce exactly.

```
python pc/twin_probe.py holdout --tag desk0713          --min-windows 4
python pc/twin_probe.py holdout --tag desk0713,node30713 --min-windows 4
```

| condition | test windows | accuracy | strangers | confusions |
|---|---:|---:|---:|---|
| desk only, all sources | **7,497** | **99.67%** | 17 | `84:7b` → ref ×8 |
| desk only, `84:7b` excluded | 7,470 | 99.77% | 17 | — |
| node3 only | 6,737 | 99.27% | 49 | — |
| **desk + node3, all sources** | **14,234** | **95.66%** | 329 | **ref → `84:7b` ×276**, ref → `1e:ce` ×4, `84:7b` → ref ×9 |
| desk + node3, `84:7b` excluded | 14,206 | 97.43% | 344 | ref → `1e:ce` ×21 |

The window counts (7,497 and 14,234) and the 276 confusions match the
recorded figures exactly, so these are the same two runs.

### Mechanism

`rff_offline` replays `sorted(paths)`, which places **every** `desk_*`
window before **every** `node3_*` window for a given source. The
"chronological" 60/40 split therefore splits by *receiver*, not by time —
both nodes recorded the same sessions simultaneously:

| source | windows | train (desk, node3) | test (desk, node3) |
|---|---:|---|---|
| `a4:f0:0f:77:91:20` | 35,498 | (18,670, 2,628) | **(0, 14,200)** |
| `84:7b:57:cc:20:0e` | 69 | (41, 0) | (25, 3) |

**In the 14,234-window run the reference's entire test set is node3
windows, scored against a model trained 87.7% on desk windows.** The
95.7% figure is measuring cross-receiver generalization, not a harder
device-identification population.

Reference normalization does its job on the centroid — the reference's
SFO mean is +0.00028 (desk) vs +0.00032 (node3) — but node3's spread is
wider (sd 0.00299 vs 0.00272), so a fraction of node3 reference windows
fall outside the desk-trained ellipse.

Splitting that fraction two ways:

| combined run | reference errors / 14,200 | rate |
|---|---:|---:|
| all sources | 276 confusions + 329 strangers + 4 = **609** | 4.29% |
| `84:7b` excluded | 21 confusions + 344 strangers = **365** | 2.57% |

So `84:7b` is not merely relabelling errors that would have happened
anyway. **2.57% is the pure cross-receiver gap** — node3 windows that miss
the desk-trained reference ellipse and are rejected as strangers. The
remaining **244 errors (1.72 points) are caused by `84:7b`'s presence**:
those windows are inside the reference's χ²₉₉ ellipse and would have been
classified correctly, but `84:7b`'s wide, low-n ellipse 2.4σ away is a
*closer* centroid, so they are handed to it instead. A marginal source
with a badly-conditioned model acts as a decoy for a well-modelled
source's tail.

### Answer to "inseparable transmitters, the second receiver, or both?"

**Both, and neither alone is sufficient.** Removing `84:7b` from the
combined run recovers only 97.43%, not 99.7%; running either receiver
alone gives 99.3–99.7% even with `84:7b` present. The second receiver
creates the generalization gap; the marginal 2.54σ pair converts it from
stranger-rejections into misidentifications.

**And the clock twin is in neither run.** Both datasets are 07-13;
`f4:2d:c9:70:72:30` first transmits on 07-14.

### Calibration note

`Discriminator` rejects as STRANGER beyond χ²₉₉, so ~1% of a source's own
windows should be rejected by construction. Desk-only gives 0.2% (17/7,497)
— optimistic, train and test windows come from the same receiver and the
same sessions. Combined gives 2.3% (329/14,234). Both are within a factor
of ~2 of the theoretical rate. **95.7% is closer to what a correctly
calibrated χ² gate predicts than 99.7% is**; the desk-only number is the
one flattered by its evaluation design.

---

## 7. What `CLAUDE.md` should say

The current text reads:

> Device-ID accuracy is **99.7% over 7,497 windows**, falling to **95.7%
> over 14,234 windows** once the population includes the clock-twin pair —
> `f4:2d:c9:70:72:30` is a clock twin of the reference beacon
> `a4:f0:0f:77:91:20`.
> […] That degradation is a result the project set out to characterize — a
> named, physically explained collision between two near-identical
> crystals.

**Recommendation: correct it. Two claims in it are false and one is
sound.**

- ❌ "once the population includes the clock-twin pair" — **false.**
  `f4:2d:c9:70:72:30` appears in neither run. Both are 07-13 captures;
  it first transmits on 07-14.
- ❌ "a named, physically explained collision between two near-identical
  crystals" — **false as an explanation of this drop.** The drop is a
  receiver-generalization gap (§6) landing on a marginal, partly
  instrumental 2.54σ pair whose closer member is ambient traffic.
- ✅ The two numbers themselves, and the instruction to quote both with
  their condition attached, are **correct and reproduce exactly**. The
  condition is just misstated.
- ✅ The clock twin **exists** and is correctly named — `HANDOFF.md`'s
  0.0004 rad/sc / 0.3σ reproduces as 0.00080 rad/sc / 0.26σ. It simply
  belongs to the 07-14-onward captures, not to these two numbers.

Suggested replacement for the condition clause:

> Device-ID accuracy is **99.7% over 7,497 windows** (desk receiver alone,
> 2026-07-13), falling to **95.7% over 14,234 windows** once node3's
> captures of those same sessions join the population. The drop is a
> cross-receiver generalization gap, not a harder device population: in the
> combined run the reference beacon's entire test set comes from node3
> while its model is trained 87.7% on desk windows. The single largest
> error mode is 276 reference windows landing on `84:7b:57:cc:20:0e`, an
> ambient third-party device that sits 2.54σ from the reference. **The
> clock twin `f4:2d:c9:70:72:30` is not present in either run** — it first
> transmits on 2026-07-14. Quote both numbers with the condition attached,
> or quote neither.

The clock-twin fact belongs in its own line, sourced to the 07-14 data:

> `f4:2d:c9:70:72:30` is a genuine clock twin of `a4:f0:0f:77:91:20`:
> 0.26σ apart, ΔSFO 0.00080 rad/sc, measured on `rx_20260714_011619.csv`.
> This is a characterized result, not a defect — but it is **not** the
> cause of the 99.7% → 95.7% drop.

---

## 8. Confidence, and its basis

| claim | confidence | basis |
|---|---|---|
| No 07-13 source is `f4:2d:c9:70:72:30` under another address | **Very high** | Simultaneous transmission, 111.6 min, max 3.82 ms inter-frame proximity, 1,114/1,114 frames. Physical impossibility, not a statistical inference. |
| The clock twin is absent from both headline runs | **Very high** | Zero string occurrences across all 07-13 files on both receivers, plus first-appearance 07-14 in the census. |
| Both headline numbers are the runs described | **Very high** | Window counts (7,497 / 14,234) and confusion count (276) reproduce exactly. |
| The drop is a cross-receiver generalization gap | **High** | Train/test receiver composition measured directly; ablations (±`84:7b`, per-receiver runs) bracket the effect. |
| `84:7b:57:cc:20:0e` is third-party ambient traffic | **High** | Rate 20× lower, cadence CV 3.96 vs tight, mixed frame formats vs 100% len-256 for all three known units, 22–27σ from all of them in a single shared capture. |
| The closest desk-only pair is 2.54σ | **Moderate–high** | Bootstrap CI [2.23, 2.84] over 400 resamples; `rff_offline`-convention variant 2.10σ. Point estimate is stable; interpretation is limited by `84:7b`'s 66 windows. |
| 2.54σ reflects a physical crystal proximity | **Low — do not assert** | `84:7b`'s SFO is frame-format-dependent (§4) and session-wandering (§5c). The pair is a real discriminator failure but its physical reading is unsupported. |

### Limitations

- The desk-only 07-13 analysis rests on **66 windows** for `84:7b`
  against 18,670 for the reference. Nothing here escapes that asymmetry.
- Only 2 of 59 source MACs are characterizable at the default 64-frame
  window. A smaller window would admit more sources at the cost of noisier
  per-window estimates; not attempted here.
- The 20-minute overlap slice (§5b) gives `84:7b` only 13 windows. Its
  ΔSFO to `f4:2d` is enormous (0.0245 rad/sc) so the conclusion is not
  marginal, but the σ figures from that slice are inflated by the short
  capture's small pooled covariance and should not be compared to §3's.
- Thermal drift remains unmodeled, as `HANDOFF.md` already records. §5c
  quantifies it for these two sources only.
- No hardware was touched and no existing file was modified. Findings are
  from `data/raw/` CSVs alone.

---

## Files added by this investigation

- `pc/twin_probe.py` — read-only analysis tool (this document's source of
  every number)
- `docs/TWIN_INVESTIGATION.md` — this file

Nothing under `pc/rff/`, `pc/occ/`, `data/`, `site/`, or any existing
entry point was modified.
