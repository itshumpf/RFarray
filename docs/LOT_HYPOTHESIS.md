# Are all three D0WD beacons clock twins from one manufacturing lot?

**Date:** 2026-08-15 · **Scope:** read-only re-analysis of `data/raw/`
· **Tool:** `pc/exp_lot_hypothesis.py` (new), driving `pc/twin_probe.py`
→ `pc/rff_offline.py` → `pc/rff/`. No DSP was reimplemented and no
existing file was modified.

---

## Verdict

**Refuted in its strong form. Inconclusive on lot identity. The
same-model figure does not need a "same-lot" relabel — it needs a
condition, and that condition is not the one the hypothesis proposed.**

The three pairwise separations, measured on the single capture both prior
investigations used (`rx_20260714_011619.csv`, all three beacons on air
together for 45.9 min):

| pair | σ | bootstrap 95% CI | ΔSFO (rad/sc) | × twin scale |
|---|---:|---|---:|---:|
| `a4:f0:0f:77:91:20` vs `f4:2d:c9:70:72:30` | **0.26** | [0.21, 0.30] | +0.00080 | 1.0× |
| `28:05:a5:2f:fa:48` vs `a4:f0:0f:77:91:20` | **1.99** | [1.89, 2.08] | +0.00618 | 7.7× |
| `28:05:a5:2f:fa:48` vs `f4:2d:c9:70:72:30` | **2.25** | [2.12, 2.35] | +0.00697 | 8.7× |

On that session alone the answer would read "one twin pair plus one unit
that is still below the 3σ line" — and that is exactly what
`docs/TWIN_INVESTIGATION.md` §3 already recorded. This investigation
reproduces those three numbers to the second decimal (§2), then does the
thing that had not been done: **repeats the measurement on all seven
captures in which the three beacons transmit concurrently.**

Repeated, it does not hold.

| pair | sessions <3σ | σ min | σ median | σ max | \|ΔSFO\| median | × twin scale |
|---|---:|---:|---:|---:|---:|---:|
| `77:91:20` vs `70:72:30` | 6 / 7 | 0.26 | 0.58 | **4.29** | 0.00314 | 3.9× |
| `2f:fa:48` vs `70:72:30` | 6 / 7 | 0.20 | 1.54 | 3.04 | 0.00697 | 8.7× |
| `77:91:20` vs `2f:fa:48` | 5 / 7 | 0.47 | 1.69 | 4.25 | 0.00502 | 6.3× |

Three findings, in decreasing order of confidence:

1. **All three are mutually inseparable — but not because they are
   twins.** Every pair sits below the project's own 3σ line in the
   majority of sessions, and every pair exceeds 3σ in at least one. No
   unit is separable and no pair is reliably closest: the closest pair is
   `77:91:20`/`70:72:30` in 3 of 7 sessions, `2f:fa:48`/`70:72:30` in 3,
   and `77:91:20`/`2f:fa:48` in 1. **The recorded twin pair is the
   *farthest* pair in `rx_20260722_204658.csv` (4.29σ).**

2. **The strong hypothesis — all three at clock-twin scale — is
   refuted.** In no session are all three pairs at twin scale. Median
   ΔSFO per pair is 3.9×, 6.3× and 8.7× the recorded twin scale of
   0.00080 rad/sc.

3. **The hypothesis cannot be tested on this data at all, because the
   measurement's own instability is larger than the effect it would have
   to resolve.** Each unit's session-to-session wander (mean across-unit
   sd **0.00570 rad/sc**) is **2.4×** the spread between the three units'
   grand means (**0.00237 rad/sc**). Within a single session the same
   pair's σ moves across the full range 0.05 → 9.08 (§5). A between-unit
   difference buried 2.4× under within-unit wander cannot distinguish
   "three crystals off one reel" from "three crystals off three reels
   whose differences are simply smaller than the drift."

**So the scoping correction the hypothesis proposed is not earned.**
Relabelling the ~77% figure "same-lot" would replace one unsupported
claim with another. What that figure actually needs is stated in §7.

Braeden was right that the published figure is under-conditioned and
right that the three units are mutually inseparable. He was wrong about
the mechanism: it is not that all three are twins, and the data cannot
support a lot-based reading.

**This is n=3, from what is believed to be one purchase — that belief is
Braeden's premise, not a finding, and nothing in the repo corroborates
it. Lot identity is inferred from nothing: there is no purchase record,
serial marking, or lot label anywhere in the repo (§6.3).**

---

## 1. What the hypothesis had to predict

Braeden's conjecture: the three D0WD beacons came from one order, so
their crystals plausibly came off one reel, and within-lot oscillator
variance is far tighter than across-lot. If true, the published
"same-model ESP32 discrimination tops out ≈77%, distinct units 1.8–2.7σ
apart" (`docs/HANDOFF.md`) would be a same-**lot** result, not a
same-**model** one.

Written as something the data can refuse, in this project's own units
(twin scale = 0.26σ / ΔSFO 0.00080 rad/sc, `docs/TWIN_INVESTIGATION.md`
§3; separability line = 3σ):

| form | prediction |
|---|---|
| **STRONG** | all three pairs at twin scale |
| **WEAK** | all three pairs below 3σ, not all at twin scale |
| **REFUTED** | at least one pair separates like genuinely different crystals |

These are encoded in `verdict_line()` in `pc/exp_lot_hypothesis.py`, so
the verdict prints from the numbers rather than being asserted over them.

## 2. Method, and why a new script was needed

`twin_probe.py` already drives the real pipeline correctly and is reused
unchanged for collection. The one thing it could not do is restrict the
covariance pool: `Discriminator.separation_matrix()` pools covariance
over **every** characterized source in the library, so a session
containing ambient traffic yields three-beacon σ values that ambient
devices helped set. `rff_offline.py --only-macs` drops sources after
reference correction but still pools over whatever survives, and has no
bootstrap. `exp_lot_hypothesis.py` adds selection, bootstrap and
reporting only. The chain to the production estimator is unbroken:

```
rff.dsp.FrameEstimator / WindowAggregator
  -> rff.reference.ReferenceNormalizer
    -> rff_offline.collect_observations
      -> twin_probe collect  (cache shard)
        -> twin_probe.load
          -> exp_lot_hypothesis.py   (selection, bootstrap, reporting)
```

**Equivalence check.** On `lot14a` only three sources clear the 5-window
gate, so the restricted pool *is* the full pool and the two tools must
agree. They do, and they agree with `docs/TWIN_INVESTIGATION.md` §3:

| pair | `twin_probe sep` | `exp_lot_hypothesis matrix` | TWIN_INVESTIGATION §3 |
|---|---:|---:|---:|
| `77:91:20` vs `70:72:30` | 0.26 | 0.26 [0.21, 0.30] | 0.26 [0.21, 0.30] |
| `2f:fa:48` vs `77:91:20` | 1.99 | 1.99 [1.89, 2.08] | 1.99 [1.90, 2.08] |
| `2f:fa:48` vs `70:72:30` | 2.25 | 2.25 [2.12, 2.35] | 2.25 [2.12, 2.36] |

ΔSFO agrees to all five decimals for the pair orderings as written above
(+0.00080 / +0.00618 / +0.00697). **ΔSFO is signed and its sign follows
the order the pair is written in** — the same quantity appears as
−0.00618 in §4.2, where the pair is written `77:91:20` vs `2f:fa:48`. A
second, independent cross-check: the 3-class blind holdout on the same
session gives **55.37%**, inside the 51–67% band
`docs/WINDOW_CONVERGENCE.md` §4.3 measured on the same capture through a
completely different harness.

**Both feature spaces are reported.** `ref` is reference-corrected — the
space the published 1.8–2.7σ figure lives in. `raw` is the uncorrected
estimator output from the same observation dicts, because
`docs/HANDOFF.md` records that reference subtraction does not help
within-session same-model separation. **Every conclusion below holds in
both** (§4.2), so none of it is an artifact of the correction.

Reproduce:

```
export TWIN_PROBE_CACHE=/scratch/lot_cache      # NOT data/cache — do not race other experiments
python pc/twin_probe.py collect --tag lot14a data/raw/rx_20260714_011619.csv
python pc/exp_lot_hypothesis.py overlap  data/raw/rx_20260714_011619.csv
python pc/exp_lot_hypothesis.py matrix   --tag lot14a --boot 400
python pc/exp_lot_hypothesis.py sessions --tags lot14a,lot14b,lot14cS,lot15S,lot22a,lot22b,lot22cS --boot 400
python pc/exp_lot_hypothesis.py stability --tags lot14a,lot14cS,lot15S,lot22cS --chunks 6
python pc/exp_lot_hypothesis.py variance  --tags lot14a,lot14b,lot14cS,lot15S,lot22a,lot22b,lot22cS
```

Three sessions were replayed as **300 MB prefix slices** (tags ending
`S`) rather than in full, because each full file is 1.7–5.2 GB. Each
slice is the first ~40–44 min of its session and is labelled as such
throughout. This is a subsample, not a summary: the DSP runs on every
frame in the slice.

## 3. The three beacons, and everything else on air

A per-(file, MAC) census of all 62 files in `data/raw/` — frames, span,
mean RSSI and the full CSI-buffer-length histogram — was built with an
independent `awk` pass (`census_full.csv`, 910 rows, 546 distinct MACs).
The row count reproduces the 910 that `docs/WINDOW_CONVERGENCE.md` §6
obtained by a different route.

Applying the beacon signature that `docs/TWIN_INVESTIGATION.md` §4
established — high frame rate, uniformly len-256 frames, sustained
presence — as **≥10 fps AND ≥1000 frames AND >99.9% len-256**:

| MAC | files passing filter | frames in those files | fps range | mean-RSSI range | len-256 | all files / all frames |
|---|---:|---:|---|---|---:|---|
| `a4:f0:0f:77:91:20` | 42 | 7,015,610 | 11.6 – 66.6 | −66.0 … −88.5 | 100% | 49 / 7,016,574 |
| `f4:2d:c9:70:72:30` | 12 | 4,639,517 | 37.0 – 82.5 | −63.8 … −76.9 | 100% | 12 / 4,639,517 |
| `28:05:a5:2f:fa:48` | 7 | 3,274,606 | 27.2 – 49.3 | −76.0 … −79.5 | 100% | 7 / 3,274,606 |

(The reference beacon appears in 7 further files below the ≥1000-frame or
≥10 fps thresholds — brief or nearly-empty sessions — accounting for the
964-frame difference between the two frame columns.)

**Exactly three sources in the entire 13 GB dataset match. There is no
fourth.** **The filter is not doing the work by luck — the gap is wide on every
axis at once, and no non-beacon source is close on more than one.** Every
row in the census that reaches ≥10 fps with ≥500 frames is one of the
three beacons. The nearest competitors, each on a different axis: by
frames in one file, `1e:ce:51:f3:0d:fa` with 20,913 (in
`rx_20260722_XXXXXX.csv`) — but 0% len-256; by rate,
`76:eb:b0:c0:68:4d` at 13.1 fps, inside the beacons' own 11.6–82.5 fps
band — but only 235 frames total and 0% len-256; by frame format,
`84:7b:57:cc:20:0e` at 84.4% len-256 — but ≤2.4 fps and mixed lengths,
which `docs/TWIN_INVESTIGATION.md` §4 already characterized as ambient
third-party traffic.

132 near-miss addresses share a beacon OUI (40 / 55 / 37 across the
three), of which 2 share a beacon's full upper five octets
(`f4:2d:c9:70:72:00`, `a4:f0:0f:77:91:00`).
Summed per OUI prefix they account for **42, 66 and 42 frames** against
`a4:f0:0f`, `f4:2d:c9` and `28:05:a5` respectively — **0.0006%–0.0014%**
of each beacon's traffic — and are bit-corrupted captures of the beacons
themselves, not devices.

### 3.1 The Heltec S3 never transmitted

`8c:fd:49:b7:b0:6c` appears **zero times in all 62 capture files.** So
does the collector `f4:2d:c9:6f:8b:44`, as expected for a receiver.

This confirms `docs/HANDOFF.md` open thread #3 (S3 WiFi-TX inaudible)
from the capture side and settles the control question: **the closest
thing to a different-lot control that exists in this project's hardware
inventory produced no data, so there is no natural control and none of
this analysis has one.**

## 4. Concurrency, and the full pairwise matrix

### 4.1 Seven concurrent sessions

Concurrency removes thermal and environmental drift as a confound in a
way cross-session comparison cannot, so it is required here, as
`docs/TWIN_INVESTIGATION.md` §5a required it. Measured by
`exp_lot_hypothesis.py overlap`, counting 10-second bins in the mutual
on-air window that contain a frame from **every** beacon:

| tag | capture | mutual window | 10 s bins with all three |
|---|---|---:|---:|
| `lot14a` | `rx_20260714_011619.csv` | 45.9 min | 275/275 = 100% |
| `lot14b` | `rx_20260714_030915.csv` | 0.9 min | 5/5 = 100% |
| `lot14cS` | `rx_20260714_031131.csv` (300 MB prefix) | 40.2 min | 241/241 = 100% |
| `lot15S` | `rx_20260715_201703.csv` (300 MB prefix) | 41.9 min | 251/251 = 100% |
| `lot22a` | `rx_20260722_204658.csv` | 5.3 min | 31/31 = 100% |
| `lot22b` | `occ_20260722_191220.csv` | 10.0 min | 58/59 = 98.3% |
| `lot22cS` | `rx_20260722_XXXXXX.csv` (300 MB prefix) | 44.2 min | 223/265 = 84.2% |

The tool also prints nearest-frame proximity (p50 0.03–0.82 ms). **That
number is not load-bearing and should not be quoted:** `pc_time_us` is
stamped per serial drain batch, not per frame (`docs/HANDOFF.md` trap
#1), so sub-millisecond proximity partly reflects batching. The 10 s bin
co-presence is coarse enough to be immune to that, and is what the
concurrency claim rests on.

### 4.2 The matrix, session by session

`exp_lot_hypothesis.py sessions`, reference-corrected, bootstrap 95% CI
over 400 per-source resamples:

| tag | pair | windows a/b | σ | 95% CI | ΔSFO (rad/sc) |
|---|---|---:|---:|---|---:|
| lot14a | `77:91:20` vs `70:72:30` | 2145/2445 | 0.26 | [0.21, 0.30] | +0.00080 |
| lot14a | `77:91:20` vs `2f:fa:48` | 2145/1302 | 1.99 | [1.89, 2.08] | −0.00618 |
| lot14a | `2f:fa:48` vs `70:72:30` | 1302/2445 | 2.25 | [2.12, 2.35] | +0.00697 |
| lot14b | `2f:fa:48` vs `70:72:30` | 21/113 | 0.20 | [0.06, 0.57] | +0.00050 |
| lot14b | `77:91:20` vs `2f:fa:48` | 131/21 | 0.47 | [0.24, 0.77] | +0.00264 |
| lot14b | `77:91:20` vs `70:72:30` | 131/113 | 0.58 | [0.30, 0.93] | +0.00314 |
| lot14cS | `2f:fa:48` vs `70:72:30` | 1361/2052 | 0.77 | [0.69, 0.85] | +0.00149 |
| lot14cS | `77:91:20` vs `2f:fa:48` | 1858/1361 | 1.39 | [1.23, 1.57] | +0.00269 |
| lot14cS | `77:91:20` vs `70:72:30` | 1858/2052 | 2.17 | [2.03, 2.34] | +0.00418 |
| lot15S | `77:91:20` vs `70:72:30` | 2359/1427 | 0.35 | [0.31, 0.40] | −0.00104 |
| lot15S | `2f:fa:48` vs `70:72:30` | 1495/1427 | **3.04** | [2.94, 3.16] | +0.00918 |
| lot15S | `77:91:20` vs `2f:fa:48` | 2359/1495 | **3.38** | [3.28, 3.51] | −0.01022 |
| lot22a | `77:91:20` vs `2f:fa:48` | 101/236 | 1.69 | [1.48, 1.91] | −0.00502 |
| lot22a | `2f:fa:48` vs `70:72:30` | 236/290 | 2.61 | [2.35, 2.89] | −0.00776 |
| lot22a | `77:91:20` vs `70:72:30` | 101/290 | **4.29** | [4.04, 4.63] | −0.01278 |
| lot22b | `2f:fa:48` vs `70:72:30` | 304/426 | 1.54 | [1.35, 1.73] | +0.00746 |
| lot22b | `77:91:20` vs `70:72:30` | 98/426 | 2.75 | [2.55, 2.95] | −0.01305 |
| lot22b | `77:91:20` vs `2f:fa:48` | 98/304 | **4.25** | [4.00, 4.52] | −0.02051 |
| lot22cS | `77:91:20` vs `70:72:30` | 819/2361 | 0.37 | [0.30, 0.43] | −0.00238 |
| lot22cS | `77:91:20` vs `2f:fa:48` | 819/1962 | 0.60 | [0.55, 0.66] | +0.00388 |
| lot22cS | `2f:fa:48` vs `70:72:30` | 1962/2361 | 0.97 | [0.91, 1.03] | −0.00627 |

Bootstrap CIs are tight — the *sampling* uncertainty within a session is
small. It is the **between-session** variation that is enormous, and no
bootstrap inside one session can see it. That is the whole point: the
0.26σ figure is a precise measurement of something that does not stay
put.

**σ is not comparable across sessions** (the pooled covariance changes
with the window counts and spreads of each run) — ΔSFO in rad/sc is the
comparable quantity, and it moves just as much: the recorded twin pair
spans +0.00080 to −0.01305, a **16× range that also changes sign.**

**The uncorrected space gives the same answer.** Repeating the whole
sweep with `--mode raw`:

| pair | ref: σ min/med/max | raw: σ min/med/max | ref \|ΔSFO\| med | raw \|ΔSFO\| med |
|---|---|---|---:|---:|
| `77:91:20` vs `70:72:30` | 0.26 / 0.58 / 4.29 | 0.25 / 0.58 / 3.94 | 0.00314 | 0.00293 |
| `2f:fa:48` vs `70:72:30` | 0.20 / 1.54 / 3.04 | 0.22 / 1.47 / 3.00 | 0.00697 | 0.00647 |
| `77:91:20` vs `2f:fa:48` | 0.47 / 1.69 / 4.25 | 0.66 / 1.58 / 3.69 | 0.00502 | 0.00527 |

Rank-1 (closest-pair) counts are identical in both spaces: 3 / 3 / 1.
Reference-beacon correction is not producing any of this.

### 4.3 Direct answer to "one twin pair, or all three?"

**Neither of the two options as posed.** All three are mutually
inseparable — no pair holds a reproducible ≥3σ separation — but they are
not all twins, and the pair the inventory calls a twin does not stay the
closest pair. Per-pair medians: **0.58σ, 1.54σ, 1.69σ**, all below the
3σ line; per-pair maxima: **4.29σ, 3.04σ, 4.25σ**, all above it.

The 3-class blind holdout over the same seven sessions (`twin_probe
holdout --only` the three beacons, chronological 60/40, chance = 33.3%):

| tag | accuracy | test windows |
|---|---:|---:|
| lot14a | 55.37% | 2357 |
| lot14b | 56.48% | 108 |
| lot14cS | 55.07% | 2110 |
| lot15S | 61.43% | 2113 |
| lot22a | 80.56% | 252 |
| lot22b | 80.78% | 333 |
| lot22cS | **16.81%** | 2058 |

Two sessions beat 80%; one falls **below chance** at 16.8%, with 301 of
its windows rejected as strangers. A classifier that lands below chance
on a 3-class problem is not measuring device identity in that session at
all — the chronological split is handing it a train set and a test set
from two different parts of the drift measured in §5. (What *causes* that
drift is not established here; no temperature was recorded. See §9.)

## 5. Why: the signature moves more than the units differ

Splitting each session's windows into six consecutive equal-count chunks
(`exp_lot_hypothesis.py stability`) and recomputing inside each:

`rx_20260714_011619.csv` (the 0.26σ session):

| pair | c0 | c1 | c2 | c3 | c4 | c5 | σ range |
|---|---:|---:|---:|---:|---:|---:|---:|
| `77:91:20` vs `2f:fa:48` | 0.75 | 3.64 | 5.48 | 4.30 | 1.35 | 1.36 | 4.73 |
| `77:91:20` vs `70:72:30` | 0.36 | 0.62 | 1.45 | 1.20 | 0.32 | 0.26 | 1.19 |
| `2f:fa:48` vs `70:72:30` | 0.39 | 4.21 | 6.92 | 5.50 | 1.03 | 1.62 | 6.53 |

`rx_20260714_031131.csv` prefix:

| pair | c0 | c1 | c2 | c3 | c4 | c5 | σ range |
|---|---:|---:|---:|---:|---:|---:|---:|
| `77:91:20` vs `2f:fa:48` | 0.05 | 0.40 | 2.34 | 8.41 | 8.61 | 8.17 | 8.56 |
| `77:91:20` vs `70:72:30` | 2.10 | 1.23 | 2.48 | 8.83 | 9.05 | 9.08 | 7.85 |
| `2f:fa:48` vs `70:72:30` | 2.06 | 1.33 | 0.34 | 0.44 | 0.45 | 0.92 | 1.72 |

`rx_20260722_XXXXXX.csv` prefix, in ΔSFO (rad/sc) — the comparable unit:

| pair | c0 | c1 | c2 | c3 | c4 | c5 | range |
|---|---:|---:|---:|---:|---:|---:|---:|
| `77:91:20` vs `2f:fa:48` | −0.00464 | −0.00054 | +0.00441 | +0.00464 | +0.00889 | +0.01054 | 0.01518 |
| `77:91:20` vs `70:72:30` | −0.00904 | −0.00933 | −0.00842 | +0.00084 | +0.00619 | +0.00546 | 0.01552 |
| `2f:fa:48` vs `70:72:30` | −0.00440 | −0.00880 | −0.01283 | −0.00380 | −0.00270 | −0.00508 | 0.01014 |

Inside a single 44-minute window, each pair's ΔSFO traverses ~0.015
rad/sc (0.01014, 0.01518, 0.01552) — **12.7× to 19× the twin scale** —
and two of the three change sign. Each chunk holds 136–408 windows per
source (136 is the smallest, in `lot22cS`), so this is centroid movement,
not small-n noise.

The variance decomposition makes it a single number
(`exp_lot_hypothesis.py variance`, per-session mean SFO over the seven
concurrent sessions):

| space | between-unit sd of grand means | mean within-unit across-session sd | ratio within/between |
|---|---:|---:|---:|
| reference-corrected | 0.00237 | 0.00570 | **2.40** |
| raw | 0.00213 | 0.00618 | **2.90** |

Per unit (reference-corrected): `a4:f0:0f:77:91:20` across-session sd
0.00124 (range 0.00353), `f4:2d:c9:70:72:30` 0.00734 (0.01761),
`28:05:a5:2f:fa:48` 0.00851 (0.02380).

This is not a new phenomenon — `docs/HANDOFF.md` already records "clock
signatures wander thermally: pairs moved 2.7σ→1.3σ over an hours-long
session," and lists embedding TX die temperature as open thread #1. What
is new is the magnitude relative to the between-unit spread, and the
consequence: **while within-unit wander is 2.4× the between-unit spread,
no single-session pairwise separation between these units generalizes,
and the lot question is not answerable.**

## 6. Where the third beacon was on 2026-07-13

**Absent. Not below quality gates, not under an unattributed address.**
Both other beacons were physically not on channel 6 during any 07-12 or
07-13 capture.

Three independent lines, all from the files:

1. **String search.** `28:05:a5:2f:fa:48` and `f4:2d:c9:70:72:30` occur
   **0 times** across every `desk_2026071[23]_*.csv` and
   `node3_2026071[23]_*.csv` (`grep -c`, both receivers).
   `a4:f0:0f:77:91:20` occurs 3,411,854 times in the same files. This
   reproduces `docs/TWIN_INVESTIGATION.md` §2's factual finding.

2. **Signature search — the test a string search cannot do.** A beacon
   under a different address would still transmit like a beacon. Across
   all 27 files dated 07-13, **66 distinct MACs** appear and **only
   `a4:f0:0f:77:91:20` has beacon character.** The runner-up by frame
   count is `1e:ce:51:f3:0d:fa` with 5,621 frames at ≤3.3 fps and **0%
   len-256**; `84:7b:57:cc:20:0e` has 5,582 frames at ≤1.6 fps and mixed
   frame lengths. The reference beacon out-transmits the busiest
   non-beacon source on 07-13 by **417×** (2,345,529 vs 5,621 frames),
   and that source carries no len-256 frames at all. The "present but
   below quality gates"
   branch is excluded at the census level, before the DSP is reached:
   these sources do not have enough frames to gate.

3. **First appearance.** Both beacons first appear at
   **2026-07-14 06:16:19 UTC, 0.18 s apart**, at the very start of
   `rx_20260714_011619.csv` — the first capture after the last 07-13
   session ended. Two units arriving on air within 180 ms of each other,
   at a file boundary, is a deployment event, not a gradual one.

**Caveat, stated because it is the only branch the data cannot close:**
all 07-13 captures are channel 6 only (verified on
`desk_20260713_172009.csv`: 588,009 frames, channel 6, no other value).
Absence is therefore established for channel 6. A beacon transmitting on
another channel would be invisible to these captures. Nothing in the
repo suggests that happened, but this analysis cannot exclude it.

### 6.1 What this means for the two headline numbers

Nothing changes. Both the 99.7%/7,497-window and 95.7%/14,234-window
runs are 07-13 captures, so **two of the three beacons are absent from
both**, exactly as `docs/TWIN_INVESTIGATION.md` §6 concluded. The
same-model and twin figures come from 07-14-onward data and are a
separate population.

**This contradicts `CLAUDE.md`, and the contradiction is deliberate —
flagging it here so nobody meets it cold.** `CLAUDE.md` attributes the
99.7% → 95.7% drop to "once the population includes the clock-twin pair."
The clock twin is not in either run. `docs/TWIN_INVESTIGATION.md` §7
already recommends the correction and supplies replacement wording; this
investigation independently confirms the absence by three routes (§6) and
adds nothing new to that recommendation. **The two accuracy numbers
themselves, and the instruction to quote them only with their condition
attached, are correct and are not in question — only the stated
condition is.**

### 6.2 The only lot-adjacent physical evidence in the data

The three beacons carry **three different OUIs** — `a4:f0:0f`,
`28:05:a5`, `f4:2d:c9` — while the collector (`f4:2d:c9:6f:8b:44`)
shares the third beacon's OUI.

Read this weakly or not at all. It is a fact about the ESP32 die's eFuse
MAC block, assigned by the silicon vendor; the crystal is a separate
component placed by the module maker, and the hypothesis is about the
crystal. Three distinct OUI blocks is *mildly* suggestive of chips from
different allocation windows, and therefore mildly against a single-lot
reading, but it is not evidence about crystals and no weight is placed
on it here. **The registrant behind each OUI was not looked up; that
would need an external IEEE query, which was not performed.**

### 6.3 No lot record exists

A repo-wide search for `lot`, `serial`, `batch`, `purchase`, `order`,
`invoice`, `reel`, `crystal`, `oscillator`, `xtal` across all `.md`,
`.txt`, `.py`, `.c`, `.h` and `.json` files returns **no purchase
record, no serial marking, and no lot label for any board.**
`docs/HARDWARE_BUY_NOTES.md` is forward-looking (a Pi and future ESP32
multipacks) and says nothing about the provenance of the boards already
in service. **Lot identity is therefore inferred from behaviour alone —
and §5 shows behaviour cannot currently carry that inference.**

## 7. What the published figure needs instead

`docs/HANDOFF.md` currently reads:

> Same-model ESP32 discrimination on (CFO, SFO) tops out ≈ **77%**
> holdout (distinct units 1.8–2.7σ apart). Two boards are true clock
> twins: 0.0004 rad/sc apart, 0.3σ, coin-flip.

- ❌ **Do not relabel it "same-lot."** That is not established and this
  analysis cannot establish it.
- ✅ **"Tops out" is doing real work and should be kept and
  strengthened.** Read at face value the line invites "1.8–2.7σ" and
  "≈77%" to be quoted as the result. Both are best cases. Two caveats on
  the comparison, and neither weakens the point:
  - σ **is not comparable across sessions** (§4.2), so "1.8–2.7 inside
    0.20–4.29" is not one distribution — it is a published pair of
    single-session values against a set of seven single-session values,
    each valid only for its own run. That is precisely the objection:
    the published band is quoted as if it were session-independent, and
    the seven sessions show it is not.
  - The class count behind ≈77% is not recorded anywhere in the repo, so
    it cannot be placed inside the 3-class 16.8–80.8% range measured
    here. `docs/WINDOW_CONVERGENCE.md` §5 caveat 2 makes exactly this
    point about class counts, and it applies to this comparison too. For
    a like-for-like anchor, that file's own *two*-class same-model run
    (chance 50%) spans 73–94% on `rx_20260714_011619.csv`. **Whichever
    class count ≈77% refers to, it is a single-session figure quoted
    without its session.**
- ✅ **The twin line needs its condition, exactly as `CLAUDE.md` already
  demands for the accuracy pair.** 0.26σ / 0.00080 rad/sc is a real,
  reproducible measurement of `rx_20260714_011619.csv` and only of it.
  The same pair reads 4.29σ / −0.01278 rad/sc on
  `rx_20260722_204658.csv`.

Suggested replacement:

> Same-model ESP32 discrimination on (CFO, SFO) is strongly
> session-dependent, and any figure must name its session. Across the
> seven captures in which all three D0WD beacons transmit concurrently,
> per-session pairwise separation ranges from 0.20σ to 4.29σ and 3-class
> blind holdout from 16.8% to 80.8% (chance 33.3%). The ≈77% figure is a
> single-session best case; its class count was never recorded, so it
> cannot be placed inside that range — but on no reading is it a typical
> value. (σ is not comparable across sessions; ΔSFO in rad/sc is.) Every pair
> is below the 3σ line in the majority of sessions and above it in at
> least one — no unit is reliably separable and no pair is reliably
> closest. `f4:2d:c9:70:72:30` and `a4:f0:0f:77:91:20` measure 0.26σ /
> ΔSFO 0.00080 rad/sc **on `rx_20260714_011619.csv`**; on
> `rx_20260722_204658.csv` the same pair measures 4.29σ / −0.01278. The
> limiting quantity is signature wander, not crystal similarity: a unit's
> across-session sd (0.0057 rad/sc) is 2.4× the spread between the three
> units' grand means (0.0024). The cause of that wander is unmeasured —
> no temperature is recorded — so it should be called wander, not
> thermal wander, until open thread #1 is done.

## 8. What capture would settle the lot question properly

In order. **The first item is a prerequisite, not an option** — without
it the rest inherits the confound that made this analysis inconclusive.

1. **Temperature. `docs/HANDOFF.md` open thread #1, already scoped and
   $0.** Extend the 8-byte beacon payload with the ESP32's internal die
   temperature; log it per frame. Until ΔSFO can be regressed on ΔT, the
   2.4× within/between ratio in §5 is unremovable and any lot comparison
   measures the room, not the reel.

2. **Different-lot same-model units.** Buy 3–4 more ESP32 D0WD boards
   from a **different vendor and a separate order**, ideally months
   apart. The comparison that decides the hypothesis is *within-group
   pairwise ΔSFO for the existing three* against *across-group pairwise
   ΔSFO*, after temperature correction. Note this is a **different
   purchase** from `docs/HANDOFF.md` open thread #6, which plans a
   *non-Espressif* board — that one answers the cross-manufacturer
   question, which is already the project's strongest result. For *this*
   question the informative buy is same-model, different-lot.

3. **Long concurrent captures with a temperature sweep.** All units on
   air simultaneously across a controlled thermal ramp, not just across
   the ambient day. §5's chunk tables show ~0.015 rad/sc of movement
   inside 44 minutes of ordinary room conditions; a deliberate ramp
   would let that be modelled instead of merely observed.

4. **Photograph the crystals.** Cheap, immediate, and the only thing
   here that touches lot identity directly rather than through
   behaviour: date codes and manufacturer markings on the XTAL packages
   of all four D0WD boards. If three carry one date code and one
   another, the hypothesis has physical evidence for the first time. If
   the markings are absent or identical across a multipack, that is also
   worth recording — it bounds what the inference can ever be.

A power analysis is not offered because it would be a prediction, not a
measurement: with within-unit wander 2.4× the between-unit spread, the
required n depends entirely on how much of that wander item 1 removes,
which is unknown until item 1 exists.

## 9. Confidence, and its basis

| claim | confidence | basis |
|---|---|---|
| Exactly three beacon-signature transmitters exist in `data/raw/`; no fourth | **Very high** | Full 62-file census, 910 rows / 546 MACs, independent `awk` pass reproducing `WINDOW_CONVERGENCE` §6's row count. Nearest competitor 3 orders of magnitude sparser. |
| The Heltec S3 never transmitted; no control exists | **Very high** | Zero occurrences of `8c:fd:49:b7:b0:6c` in all 62 files. Corroborates `HANDOFF` open thread #3. |
| Beacons 2 and 3 are absent from all 07-12/07-13 captures | **Very high** | Three independent lines (§6): `grep -c` = 0; no beacon-signature source among 66 MACs; simultaneous first appearance 0.18 s apart at a file boundary. Bounded to channel 6. |
| All three transmit concurrently in seven captures | **Very high** | 10 s co-presence 84–100% over mutual windows of 0.9–45.9 min. Coarse enough to be immune to the drain-batch timestamp trap. |
| The `lot14a` matrix (0.26 / 1.99 / 2.25σ) is correct | **Very high** | Reproduces `twin_probe sep`, `TWIN_INVESTIGATION` §3 and (holdout) `WINDOW_CONVERGENCE` §4.3, three independent routes. |
| No pair holds a reproducible ≥3σ separation; all three mutually inseparable | **High** | 7 concurrent sessions, both feature spaces, bootstrap CIs. Every pair below 3σ in 5–6 of 7. |
| The strong lot hypothesis (all three at twin scale) is refuted | **High** | Median ΔSFO 3.9–8.7× twin scale; no session has all three pairs at twin scale, in either space. |
| Within-unit wander exceeds between-unit spread by ~2.4× | **High** | Two spaces (2.40 / 2.90), 7 sessions, corroborated by within-session chunking on 4 sessions. |
| The lot hypothesis is untestable on this data | **High** | Follows from the ratio above; independent of any assumption about crystals. |
| The three units are or are not from one lot | **No confidence — not determined** | No purchase record, no serial, no lot label (§6.3). The only physical hint is three distinct OUIs (§6.2), which is about the die, not the crystal. |
| Thermal drift is *the* mechanism behind the instability | **Moderate — plausible, not isolated** | Consistent with `HANDOFF`'s recorded thermal wander and with the monotone chunk trends in §5, but no temperature was recorded, so RSSI/SNR changes, receiver placement and per-file Kalman warm-up are not excluded as contributors. |

### Limitations

- **n = 3 units, believed but not shown to be one purchase, lot inferred
  from nothing.** Even had the measurement been stable, three units from
  one order cannot establish a within-lot vs across-lot contrast on their
  own — and that they *are* one order is itself unevidenced (§6.3).
- **Three of seven sessions are 300 MB prefix slices**, i.e. the first
  ~40–44 min of long captures. The slices are contiguous and fully
  processed, but they sample session starts, which may over-represent
  warm-up. `lot14a`, `lot14b`, `lot22a` and `lot22b` are complete files
  and show the same instability, so this does not drive the conclusion.
- **Window counts are unequal within sessions** (e.g. 98 vs 426 in
  `lot22b`, 21 vs 131 in `lot14b`). The bootstrap resamples at each
  source's own n and so propagates this, but a 21-window model is
  poorly conditioned regardless — `lot14b`'s wide CIs [0.06, 0.57] say so.
- **No temperature data exists**, so the mechanism in §5 is characterized
  but not explained. See §8 item 1.
- **The per-file Kalman warm-up of `ReferenceNormalizer` was not ablated.**
  It is a candidate contributor to chunk-0 anomalies specifically. It
  cannot explain the c1→c5 swings (e.g. 3.64 → 5.48 → 1.35 in `lot14a`),
  and the `raw` sweep — which uses no reference track at all — reproduces
  every conclusion.
- **Channel 6 only.** Every claim of absence is bounded to the channel
  the collector captured.
- **No hardware was touched.** All findings are from `data/raw/` CSVs.

---

## Files added by this investigation

- `pc/exp_lot_hypothesis.py` — read-only analysis tool (source of every
  number above except the `awk` census and `grep` counts, which are
  quoted inline in §3 and §6)
- `docs/LOT_HYPOTHESIS.md` — this file

Nothing under `pc/rff/`, `pc/occ/`, `data/`, `site/`, `firmware/`, or any
existing entry point was modified. `pc/twin_probe.py` and
`pc/exp_window_convergence.py` were read and reused, not edited. Cache
shards were written to a scratch directory outside the repo via
`TWIN_PROBE_CACHE`, so neither `data/cache/expwin` nor the default
`twin_probe` cache was raced.
