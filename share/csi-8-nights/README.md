# Eight nights of WiFi CSI clock fingerprinting — review package

Built 2026-09-05 for independent review. **Everything in `data/` was computed
from the files in `per_window_features/` by `scripts/`, not transcribed from
any write-up.** Spot-checked against the project's own pre-registration on 40
of 40 cells to within 0.0001 rad/subcarrier.

**If you find something wrong, that is the point of sending it.** §7 is a list
of the attacks I would run first, including one I think is a genuine hole.

---

## 1. The bench, in one paragraph

Three ESP32 boards ("beacons" B1, B2, B3) transmit WiFi frames. Two other
ESP32s ("receivers" `s3` and `d0wd`) capture Channel State Information from
those frames. From each frame you can fit a line to the phase across
subcarriers; the **slope** of that line estimates **SFO** — sampling frequency
offset, a property of the transmitter's crystal — and the **intercept-ish**
term gives **CFO**. Sixty-four accepted frames are aggregated into one
*window*, and a window is the atomic observation everywhere in this package.

The question the project has been asking for four months: **can you identify a
device by its clock?** The complication discovered in August: for most of the
corpus, *which device* and *which room* were perfectly confounded, because the
beacons sat in different rooms. Every night here has all three beacons
**co-located, ~4 ft apart on one surface**, specifically to break that
confound.

Hardware: 3 × ESP32 transmitting, 2 × ESP32 receiving, 20 MHz channel, one
apartment, one week. **Three sources, so classifier chance is 33.3%.**

## 2. Chronology

| night | date | capture stamp |
|---:|---|---|
| 1 | 2026-08-29 | `20260829_025355` |
| 2 | 2026-08-30 | `20260830_013943` |
| 3 | 2026-08-31 | `20260831_020408` |
| 4 | 2026-09-01 | `20260901_035805` |
| 5 | 2026-09-02 | `20260902_000949` |
| 6 | 2026-09-03 | `20260903_013851` |
| 7 | 2026-09-04 | `20260904_010024` |
| 8 | 2026-09-05 | `20260905_025053` |

Nights 1–7 were a pre-registered series; night 8 was a separate
pre-registration written after 1–7 were scored. **B1 is off air from 1,769 s on
night 3** (flat cell) and appears nowhere in that night's data.

## 3. What is in the package

### `data/` — derived tables, all computed by `scripts/`

**`per_beacon_window_stats.csv`** (156 rows) — one row per
(source, night, receiver, beacon).

| column | meaning |
|---|---|
| `source` | which window this is: `scored_window`, `heldout_window`, `night8_block_T0+<n>` |
| `night`, `stamp`, `receiver`, `beacon`, `mac` | identity |
| `window` | the time span, in seconds after that capture's T0 |
| `n_windows` | number of 64-frame windows that survived the gates |
| `sfo_median`, `sfo_iqr`, `sfo_sd` | rad/subcarrier |
| `cfo_median`, `cfo_iqr`, `cfo_sd` | Hz |

**`pairwise_separation.csv`** (82 rows) — **read §4 before using this file.**
Carries the same separation in *two different units*, deliberately.

**`night_to_night_steps.csv`** (64 rows) — |Δ SFO| between consecutive nights,
per receiver and beacon, for both windows.

**`within_session_drift_pairs.csv`** (1,517 rows) — every pair of sample points
inside a single continuous power-on, with the lag in hours. This is the file
behind the drift-versus-timescale result. Lags run from 0.5 h to 19.7 h;
**everything past 6 h is B2 on night 4 only**, because B1 and B3 are dead by
then on every night.

**`enrol_then_identify.csv`** (60 rows) — enrol a classifier on one 300 s block,
then ask it to name the transmitter 1–5 hours later. Splits every outcome into
**correct / wrong-identity / refused**, which turns out to matter more than
accuracy does.

**`constants.csv`** — every hard-coded number, with the file and line it comes
from.

### `per_window_features/` — the underlying observations

`.npz` per capture-receiver (or per block), one array per MAC.
**Two shapes exist**: `(ts_pc, cfo, sfo)` from `dump_windows.py`, and
`(cfo, sfo)` from `exp_night_eight.py`. `scripts/` normalises both; if you load
them yourself, check `shape[1]`.

~4.8 MB total, against ~100 GB of raw captures that are not included. **If you
want to re-derive these from raw CSVs, ask** — the DSP chain is in
`scripts/rff/` and is unmodified project code.

### `scripts/` — everything that produced the above

`rff_offline.py` and `rff/` are the project's production pipeline, imported
unmodified by every analysis. Nothing in this package reimplements the DSP.

## 4. THE UNIT TRAP — read this before comparing any two σ

**There are two different "sigma" in this corpus and they are not the same
size.** A previous audit found the project's own pre-registration asserting
they were.

**`BETWEEN_UNIT_SD = 0.00237 rad/sc`** — the spread *between the three units*,
built as "sd over the 3 units of their grand means". This is the unit for
`sigma_between_unit_sd`, all night-to-night steps, and all drift figures.

**Pooled 2-D Mahalanobis** — what `rff_offline.py` prints as "sigmas apart". It
is a distance in **(CFO, SFO)** space under a covariance pooled across every
characterised source *in that run*. That covariance is the **within-night,
window-to-window scatter**, and it was measured across these nights at
**0.00049 – 0.00291 rad/sc, a 5.9× swing** — median **0.32 ×
`BETWEEN_UNIT_SD`**.

**So a "1.0σ" bar in the pooled unit is roughly a 0.3σ bar in between-unit
terms, and it moves every night.** Both are given in
`pairwise_separation.csv` so you can see the discrepancy directly.

**CFO is inert.** Between-unit spread 0.053 Hz against a median within-window
IQR of 5.97 Hz — 112:1 noise to signal, where SFO's ratio is 0.39:1. Removing
the CFO axis changes pairwise separations by a median of **−1.4%**. It is
carried through every centroid and both χ² gates and contributes nothing.

## 5. What was pre-registered, and what it returned

Three documents, each frozen before the data it scores existed.

**Seven-night series (nights 1–7).**
- **P1** — co-located B2–B3 stays below 1.0σ on ≥5 of 7 nights, both receivers.
  **Failed 7/7.**
- **P2** — reference-beacon correction makes cross-receiver agreement ≥2×
  worse. **Failed every night it could run.**
- **P3** — night-to-night wander of one stationary beacon exceeds 1.0σ.
  **Held.** Written in advance as the risk that would make P1 uninterpretable.
- **Verdict, per the frozen table: P1 UNINTERPRETABLE, not refuted.** The
  instrument cannot resolve the bar the design set.

**Held-out second window (same seven nights, disjoint 30 minutes).**
Q1 fingerprint frozen within a night **HELD** (38/40 cells under 1.0σ, median
0.07σ across a 39-minute gap). Q2 separation ≥3.0σ **FAILED** (5/7 on d0wd).
Q3 blind identification **HELD** (median 95.8%, min 61.8%, chance 33.3%). Q4
**HELD**. Q5 yield **FAILED**.

**Night 8.** R1 **FAILED**, R2 **FAILED**, R3 **FAILED**, R4 **FAILED**,
R5 **HELD**. Four of five. R3's gate was population spread, which this package
shows to be the wrong statistic — see §6.

## 6. The findings, ranked by how much I trust them

**Strong — the fingerprint is frozen inside a session.** Median |ΔSFO| across a
39-minute gap, 40 cells, two receivers, seven nights: **0.07σ**. The variogram
in `within_session_drift_pairs.csv` gives 0.06σ at 5 min and 0.15–0.21σ at
19 min. Pre-registered as Q1 and held.

**Strong — the failure mode is refusal, not confusion, *when the devices are
separable*.** On night 8's d0wd, where the closest pair is 1.43σ:
wrong-identity **0.2–2.8%**, precision **95.5–99.7%**, refusals climbing 38% →
50%. The system stops answering rather than answering wrongly.

**Strong — and this is the correction.** That behaviour inverts when two
devices genuinely share a signature. Night 8's s3 had a healthy 5.0σ
*population* spread carried entirely by B1 sitting far away, while **B2 and B3
sat 0.34σ apart** — and wrong-identity hit **28.6%**. Minimum *pairwise*
separation predicts confusion; population spread does not. The night-8
pre-registration gated on the wrong one and failed accordingly.

| night / receiver | min pair (σ) | worst wrong-identity |
|---|---:|---:|
| night 5 d0wd | 0.09 | 30–41% |
| night 5 s3 | 0.45 | 31–38% |
| night 8 s3 | 0.34 | 28.6% |
| night 8 d0wd | 1.43 | 2.8% |
| nights 4, 7 | wide | 0.0–7.8% |

**Moderate — identification has a half-life near one hour.** 97.5% at
enrolment, 69.3% at +1 h, 53.6% at +5 h, against 33.3% chance. **The spread is
enormous** — one cell held 99% for three hours, another fell to 42% in one.
Exploratory, not pre-registered.

**Moderate — the drift saturates rather than diffusing.** ~1.0σ by 6–9 h and
flat to 21 h. That shape is what makes cross-session identity land *at* chance
rather than below it. **Everything past 6 h is one beacon on one night.**

**Weak but repeated — the co-location collapse is real and intermittent.**
Three instances in eight nights: 0.2σ (28 Aug), 0.09σ (night 5 held-out
window), 0.34σ (night 8 s3). Never both receivers on the same night. **No
mechanism identified.**

## 7. What I would attack first

**7.1 — The classifier's effective sample size, and I think this is a genuine
hole.** Accuracies are quoted over thousands of holdout windows, but those
windows are 64 consecutive frames from a single continuous capture. **Adjacent
windows are not independent observations.** A chronological 60/40 split reduces
leakage but does not make the test set i.i.d., so an accuracy of "95.8% over
2,685 windows" has an effective *n* far below 2,685 and its confidence interval
is wider than it looks. Nothing in this corpus has ever estimated the
autocorrelation length. **A block bootstrap over the per-window features would
settle it, and the data to do it is in `per_window_features/`.**

**7.2 — Multiple comparisons.** Almost nothing here is corrected. The
pre-registered predictions are fine, but every "observation" in §6 was found by
looking. The night-5-is-tightest-on-both-receivers result is a 1-in-6
coincidence that repeated once; that is suggestive and it is not a p-value.

**7.3 — Saturation is one beacon.** §6's plateau rests on B2 alone, on the
2026-09-01 capture, past 6 h. If you can show the flattening is an artifact of
that single stream, the "bounded, not diffusive" claim goes with it.

**7.4 — Is the min-pair threshold real, or fitted?** The 1.43σ-versus-0.34σ
split in §6 is six cells. I picked minimum pairwise separation *after* seeing
night 8 fail. **Treat it as a hypothesis, not a result** — the honest test is a
fresh night.

**7.5 — The 500 s lead-in.** Every block here is byte-sliced out of a large
capture with a 500 s lead-in before the measured span, because the phase-unwrap
anchor needs to converge. That was validated once (520 s vs 2,020 s, identical
to every digit) and then assumed to generalise. If the anchor behaves
differently on some captures, slices are not comparable.

**7.6 — Two receivers, not two experiments.** `s3` and `d0wd` share a host
clock and sit ~12 inches apart. They agree and disagree in ways this corpus
still cannot fully explain, and treating them as independent replicates is
probably too generous.

**7.7 — Everything is one apartment, three boards, one week.** No claim here
generalises past that, and several of the strongest effects are per-unit
(B3 is markedly less stable than B2 on d0wd; B2 is the mains-powered unit,
which is confounded with being the most stable).

## 8. Reproducing

```
python scripts/exp_variogram.py          # drift vs timescale
python scripts/exp_splithalf.py          # within-night vs between-night
python scripts/exp_decay_accuracy.py     # enrol-then-identify
```

They expect the `per_window_features/` layout; adjust the path constant at the
top of each. `scripts/rff/` must be importable.

## 9. What is deliberately not here

Raw captures (~100 GB), firmware, the occupancy pipeline (`pc/occ/`, a separate
amplitude-domain project whose numbers must never be combined with these), and
the project's write-ups. **The write-ups are excluded on purpose** — I would
rather you read the numbers before you read anyone's conclusions about them.
