# LABELLED_EVENTS_0823 — the first capture with known event times, and what a power cycle does to a fingerprint

**Date:** 2026-08-23 · **Scope:** read-only re-analysis of one capture pair in
`data/raw/` · **Tool:** `pc/exp_labelled_events_0823.py` (new, one script).

> **STAGE 1 — everything above the `STAGE 2` banner was written and saved
> before any feature value existed.** The only things run before it was written
> were `ls`, `head`, `tail`, `stat`, `date` and a single `awk` census pass over
> the two input files (row counts, `label`-column counts, first/last
> `pc_time_us`, per-MAC raw row counts — all of §1 below), plus reading
> `CLAUDE.md`, `pc/rff/dsp.py` in full, `pc/exp_iq_imbalance.py`
> §§constants–`run_scan`, `docs/IQ_IMBALANCE.md` §§0–5 / 10 / 12–19,
> `docs/B3_MOVED.md` §§0–2 / 9.1, and `docs/THERMAL_STEP.md` §§0–1 / 6 / 11.2
> / 11.4. **No estimator had been run. No κ, no slope, no σ and no event time
> existed.**
>
> **Stage 1 is frozen.** A Stage-1 statement that turns out to be wrong is
> corrected *below* the banner with the original left standing, not rewritten.
> Temptations to revise are recorded in §12 rather than acted on.

---

## 0. The manipulation, as reported by the operator

The operator supplied a wall-clock log. **He states that the minutes are
reliable and the seconds are not.** Reproduced verbatim:

```
18:00  capture start. B3 in a car outdoors, at outdoor temperature
18:01  B2 power-cycled — brief, seconds off, in place
18:08  B1 power-cycled — brief, seconds off, in place
18:11  B3 carried indoors, placed in interior room, running on BATTERY (no reboot)
18:19  B3 unplugged from battery → wall power  (REBOOT 1, in place)
18:35  B3 wall → battery                        (REBOOT 2, in place)
18:40  B3 moved to kitchen, on top of the fridge, line of sight to receivers
19:10  B3 moved to the oven, ~3 ft west and 2 ft lower, LOS BLOCKED, still
       visible through a half-wall pass-through
~20:06 capture ends
```

Receivers were not touched at any point. B1 and B2 did not move after their
18:01 / 18:08 cycles.

### 0.1 The log is a hypothesis about the data, not ground truth — and it is
### not in the data

`CLAUDE.md` failure mode **G** applies with unusual force here. **§1 records
that the `label` column of both files is empty on every one of the 2,529,555
data rows.** The "written log" is a text the operator typed into the brief; it
is *not* a field in the CSV, and no column of this capture carries the
treatment assignment. So this file is **not** the labelled capture the project
has been waiting for in the sense of `docs/IQ_IMBALANCE.md` §19 item 2 ("with
the reboot written into the `label` column"). It is an *externally* labelled
capture, and the label's only anchor to the data is the shared wall clock.

That is why **§3 verifies every logged event against the data before any
event is used**, and why an event that cannot be located independently is
reported as not located rather than assumed to have happened at the logged
minute. `docs/B3_MOVED.md` §0.0 is the standing precedent: on the previous
manipulation the operator's identification of the treated unit was wrong and
had to be re-derived from RSSI.

**A second `CLAUDE.md`-**G** disclosure, stated now.** "B3 was in a car at
outdoor temperature", "B3 ran on battery", "B3 was on top of the fridge",
"line of sight was blocked" and "the fridge compressor cycles" are **all**
operator account. No column carries temperature, power source, position or
line of sight. What the data can check is: gaps in a MAC's frame stream,
frame rate, RSSI level and RSSI step times. That is the whole of the
independent evidence and §3 is limited to it.

### 0.2 What would make this pass worth having, and the outcome that would be
### most valuable

The load-bearing question is **§6, the power cycle**, and it is load-bearing
because of a specific live hazard, not because it is interesting:

`docs/IQ_IMBALANCE.md` §14 found `κ` to be the first feature this project has
measured that is stable within a session (0.41× / 0.20× against the SFO
slope's 2.2–7.1× cross-session and 0.84× / 1.07× like-for-like). But §15.1
found `arg(κ)` on the d0wd rotating **~155° for two beacons at once** between
two captures six hours apart, cause unknown, and §19 item 2 names explaining
that rotation as the first thing to settle: *"If it is a boot-time sign
convention it is trivially correctable and `κ` survives cross-session; if it
is silicon state that wanders, `κ` fails the same way the slope did."*

A transmitter power cycle is the cheapest available probe of the boot-state
hypothesis. **If a TX reboot moves `κ` by more than ordinary wander, then `κ`
carries boot-set state and cannot be a device fingerprint across power
cycles** — which is a hard negative for the only promising feature in the
repo, and it would be the most valuable single result this pass could produce.
It gets the same prominence in the summary as any positive. Per failure mode
**A**, it is named here, in advance, as an outcome that would close a branch.

The reverse null — a TX reboot moving nothing — is **also** informative, and
is what §5's frozen prediction expects, because `docs/IQ_IMBALANCE.md` §1.3
derives that the conjugate coefficient is *receiver* silicon by construction
and §15 measures it as receiver-dominated by ≥ 5.73×. **Neither outcome is a
surprise that gets promoted after the fact; both are written down here.**

---

## 1. The capture, identified from timestamps not from the brief

Identified by `ls -l data/raw/` and by the first and last `pc_time_us` of each
file. `pc_time_us` is epoch microseconds.

| | `data/raw/d0wd_20260823_180002.csv` | `data/raw/s3_20260823_180002.csv` |
|---|---|---|
| bytes at read | 902,906,747 | 1,235,397,467 |
| mtime | 2026-08-23 20:06:28.939 −0500 | 2026-08-23 20:06:28.983 −0500 |
| data rows | **1,044,694** | **1,484,861** |
| `label` non-empty rows | **0** | **0** |
| first `pc_time_us` | 1787526002588517 | 1787526002549991 |
| last `pc_time_us` | 1787533588936020 | 1787533588981858 |
| span | **7586.348 s** | **7586.432 s** |
| distinct MACs, every row | **61** | **24** |

Local start **18:00:02**, local end **20:06:28**, duration **2 h 06 m 26 s**.
The previous capture pair is `*_20260823_151725.csv` (15:17), which is
`docs/THERMAL_STEP.md`'s input; it is **not used here**, not as input and not
as corroboration.

**Three counts in the brief do not reproduce and this is recorded, not
smoothed over.** The brief states 2,529,587 frames (d0wd 1,044,711 / s3
1,484,876). Measured here: **2,529,555** (d0wd 1,044,694 / s3 1,484,861),
i.e. 17 and 15 fewer. The difference is 0.0016 % and does not affect any
statistic, but the brief's numbers are not re-derivable from these files by
the command in §11 and the measured ones are used throughout. Both files
stopped growing before this pass began (mtime 20:06:28, first read 20:10),
unlike `docs/IQ_IMBALANCE.md` §15.1's live inputs.

**61 MACs against 24 is exactly the asymmetry the brief flags**, and it
reproduces `docs/THERMAL_STEP.md` §11.2's 37-vs-21 on the previous file. The
raw census already shows the fabrication signature: `f4:2d:c9:70:72:00`
(Hamming distance **1** from B3), `f4:2d:c9:70:00:00` and
`f4:2d:c9:70:0d:1b`-style variants, eight `28:05:a5:2f:xx:xx` near-misses,
three `a4:f0:0f:77:xx:xx` near-misses, and **`07:d1:0a:d0:0a:ce`, present
once, containing `0a` twice — the address the brief predicted would appear.**
§4 screens all of them.

### 1.1 Event times converted to seconds from capture start, frozen

`t = 0` is each file's own first `pc_time_us`. The two files differ by 38 µs
at t = 0 and are treated as a common clock.

| logged | event | code | t (s) |
|---|---|---|---:|
| 18:01 | B2 power cycle, in place | `PC-B2` | 57.4 |
| 18:08 | B1 power cycle, in place | `PC-B1` | 477.4 |
| 18:11 | B3 car → interior room, battery, no reboot | `MOVE-IN` | 657.4 |
| 18:19 | B3 battery → wall, in place | `RB1` | 1137.4 |
| 18:35 | B3 wall → battery, in place | `RB2` | 2097.4 |
| 18:40 | B3 → kitchen, top of fridge, LOS | `POS-FRIDGE` | 2397.4 |
| 19:10 | B3 → oven, LOS blocked | `POS-OVEN` | 4197.4 |

---

## 2. The two features, and where each one comes from

Both features are run on **every** test. The comparison between them is the
point of the exercise and neither is allowed to be reported alone.

### 2.1 Feature 1 — the SFO slope, shipped estimator, unmodified

`pc/rff/dsp.py` `FrameEstimator` + `WindowAggregator(window=64,
min_inlier_ratio=0.6, max_resid=0.8)`, imported and **not modified**. One
`FrameEstimator` per (file, source MAC) stream, constructed once and fed
**every screened frame of that MAC in file order from the first row**, because
`ransac_line` draws from a per-instance RNG that advances once per fitted
frame (`dsp.py:118,132`). The observation is the window `sfo` (median of 64
frame slopes). Units rad/subcarrier.

**Checkpoint/resume equivalence, declared in advance.** The host caps a shell
call near 178 s and this replay will not fit in one. State is checkpointed by
pickling the estimator objects, which carries `numpy.random.Generator`'s
internal state exactly, so a resumed replay is bit-identical to an
uninterrupted one. **§11 verifies that claim by re-running one stream's first
N windows in a single pass and comparing to the checkpointed run**, rather
than asserting it.

`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` are
**not used** (`docs/CODE_INVENTORY.md` §4.2 C1/C2/C3). `pc/rff/dsp.py` is not
modified.

### 2.2 Feature 2 — `κ`, reusing `pc/exp_iq_imbalance.py`'s estimator

Imported, **not rewritten**: `frames_to_H`, `deslope`, `process_batch`,
`features`, `add_cells`, `Cell`, and the constants `S_TRUE`, `CSI_LEN_OK`,
`NF_LO/HI`, `RSSI_LO/HI`, `MED_W`, `MED_TOL`, `FLOOR_CHUNK`. Convention
`divided` and `s_vec = S_TRUE`, per `docs/IQ_IMBALANCE.md` §10.2's decisive
19×/38× roughness result — the ESP32 LLTF buffer is already a channel
estimate. The `s1` variant is not re-run; §10.2 settled it on the same
hardware.

`κ = A/(2P)` is complex. **Three derived quantities are reported for every
test**:

- **`arg κ`** (degrees) — **primary.** `docs/IQ_IMBALANCE.md` §13: additive
  noise dilutes `|κ|` but cannot rotate it, so `arg κ` is the SNR-robust
  component and is the one the separation results rest on.
- **`|κ|`** — reported, and **explicitly discounted for any test in which
  RSSI changes**, i.e. every position test. Stated now so it cannot be
  promoted later.
- **`|Δκ|`** — the complex-plane distance, the single scalar used for scoring.

### 2.3 Time binning

Both features are accumulated into **10 s bins** per (receiver, MAC).
`Cell` accumulators are plain sums, so bins add exactly (`add_cells`) and any
analysis window is formed by summing its bins — no re-read. At the observed
rates a 10 s bin holds roughly 550–750 frames; **the 2,000-admissible-frame
floor of `docs/IQ_IMBALANCE.md` §1.11 is applied to the summed analysis
window, never to a single bin**, and every window's admissible count is
printed so an under-powered window is visible rather than silent.

The deterministic per-frame slope `m_f` from `deslope` is retained per bin as
a free byproduct and reported as an internal robustness check only. Per
`docs/IQ_IMBALANCE.md` §1.5 it is **not** the shipped SFO estimator, no SFO
figure is re-derived from it, and it is **never** compared to
`BETWEEN_UNIT_SD`.

### 2.4 The σ units, and the two of them are never mixed

- **SFO:** `σ_sfo ≡ BETWEEN_UNIT_SD = 0.00237 rad/sc`
  (`pc/exp_thermal_evidence.py:129`, from `docs/LOT_HYPOTHESIS.md` §5), the
  repo's standing unit. Used unchanged.
- **`κ`:** `BETWEEN_UNIT_SD` is an SFO quantity and applying it to `κ` would
  be a units error. **`σ_κ(rx)` is computed on this file**, per receiver, as
  `docs/IQ_IMBALANCE.md` §4.1 defines `S_bd`: the RMS over the three beacons
  of `|μ_d − μ̄|`, `μ_d` the beacon's mean `κ` over the bins of the quiet
  stretch **Q2** (§4.3) and `μ̄` their centroid. Quiet Q2 is used rather than
  the whole file because B3 changes position twice inside the file and a
  whole-file mean would be a mixture.
  `docs/IQ_IMBALANCE.md` §14's 0.00318 (d0wd) / 0.00848 (s3) are quoted
  alongside **for reference on a different session and are not fused with
  anything measured here.**

Every shift below is quoted **both** raw and in its own feature's σ. A shift
in `σ_sfo` and a shift in `σ_κ` are never added, averaged or compared as if
they were the same unit.

---

## 3. FIRST: verifying the log against the data

**No event is used by §§5–9 until it has been located here.** Each event is
searched for independently, with the search run over the *whole file* rather
than only near the logged minute, so that the procedure could in principle
place an event somewhere the log does not mention — or fail to find one.

### 3.1 Power cycles → a seconds-long gap in that MAC's own frame stream

Per (receiver, beacon), the sorted inter-frame `pc_time_us` differences over
screened rows. A brief power cycle is "seconds off" plus ESP32 boot, so the
signature is a gap of roughly **1–20 s** in exactly one MAC while the other
two continue. A minute-long gap is a different event and is reported as such.

Frozen procedure:

1. Print the whole-file gap distribution per stream (median, p99, max) so
   "unusual" has a measured meaning rather than an assumed one.
2. List **every** gap ≥ 1.0 s per stream, with its time, whether the other
   two beacons gap at the same moment, and on which receivers it appears.
3. A gap is **an event** only if it appears on **both** receivers at the same
   time (±2 s) for the same MAC and **not** for the other MACs. A gap on one
   receiver only is a link dropout, not a transmitter reboot, and is scored
   as such.
4. Report **measured time and offset from the logged time** for each located
   event; report **NOT LOCATED** otherwise.

**Pre-registered ambiguity, named now:** a power cycle and a deep link
dropout can look identical on one receiver. Rule 3 is what separates them and
it is committed before any gap has been seen.

### 3.2 Moves → an RSSI step

Per (receiver, beacon), median RSSI in 10 s bins. Changepoint statistic:
`|median(next 120 s) − median(previous 120 s)|` evaluated at every bin
boundary, over the whole file. The **five largest** per stream are printed
with their times, before any comparison to the log. An event is located if a
local maximum of this statistic falls within **±90 s** of a logged move.

Also printed per beacon: mean RSSI and frame rate in each inter-event
interval, so a claimed move that produces no level change is visible.

### 3.3 Verdict vocabulary, fixed now

| verdict | condition |
|---|---|
| **LOCATED** | independent signature found, offset from log reported |
| **LOCATED, LOG TIME WRONG** | signature found > 90 s from the logged time |
| **NOT LOCATED** | no signature; the event is dropped from §§5–9 and the tests that needed it are reported as not runnable |
| **UNVERIFIABLE BY DESIGN** | the manipulation has no signature this data could carry (e.g. battery vs wall at constant position) — stated, not silently assumed present |

`RB1` and `RB2` are expected to be **UNVERIFIABLE except through the reboot
gap itself**: a power-source swap at a fixed position changes nothing the CSV
records other than the interruption. `MOVE-IN`'s temperature claim is
likewise unverifiable; only its position component (car → interior room) can
show up, in RSSI.

---

## 4. Screening, and the bar everything is scored against

### 4.1 Corrupt-row screens — both, before anything else

Identical constants to `pc/exp_iq_imbalance.py` and
`pc/exp_receiver_term_prereg.py`:

1. **Field plausibility**: `node_id` == file mode, `env_id == 0`, `channel` ==
   file mode, `len ∈ {128,256,384}`, `noise_floor ∈ [−110,−70]`,
   `rssi ∈ [−100,−10]`.
2. **Width-9 median filter on `dropped`**, compared circularly mod 65536.

`csi_data` is a quoted list nested in the CSV and is read with `csv.reader`,
never `line.split(',')`. Admissibility on top of the screens: guard bins
exactly zero, ≤ 4 zero-magnitude usable subcarriers.

### 4.2 Byte-neighbour census — reported, and none of them enters a feature

Over the whole MAC census of both files: Hamming distance **in octets** from
each beacon MAC at d ≤ 1, d ≤ 2, d ≤ 3, with differing positions listed; the
`0d:0a` adjacent-pair screen and the looser "any octet is `0d` or `0a`"
screen, counted separately. `07:d1:0a:d0:0a:ce` is expected to fall in the
second. For each near-miss: raw rows, rows surviving both screens, corrupt
rows.

**Only `a4:f0:0f:77:91:20` (B1), `28:05:a5:2f:fa:48` (B2) and
`f4:2d:c9:70:72:30` (B3) enter any feature computation.** The census cannot
change a κ or a slope; it exists to measure how much the screen misses.

### 4.3 THE BAR — this file's own contemporaneous wander

`docs/B3_MOVED.md` §9.1 measured a stationary, untouched beacon wandering
**2.5–4.9 σ_sfo across a single night** on four of six (receiver, beacon)
pairs. That is an overnight figure on a different file. **This pass scores
everything against a floor computed from this file's own quiet stretches**,
matched in length to the event statistic, which is the stricter and more
honest comparison. The overnight 2.5–4.9 σ is quoted once, for context, and
nothing is scored against it.

Two quiet stretches:

| code | window | t (s) | duration | who is quiet |
|---|---|---|---|---|
| **Q1** | 18:02 → 18:08 | 117.4 → 477.4 | 6.0 min | all three (B2 post-cycle, B1 pre-cycle, B3 untouched in the car) |
| **Q2** | 19:10 → 20:06 | 4197.4 → 7586.3 | 56.5 min | **B1 and B2 fully**; B3 stationary at the oven but in a kitchen |

**The floor statistic, matched to the event statistic.** Every event test in
§§5–9 is a difference between two adjacent windows of length `W`. So the
floor is the same difference, taken where nothing happened:

- Cut Q2 into non-overlapping blocks of length `W = 240 s` (14 blocks).
- Compute the feature per block.
- **`FLOOR_adj(rx, beacon, feature)` = the maximum |difference between
  adjacent blocks|**, and the 95th percentile alongside.
- **`FLOOR_range`** = full range of block values (the `docs/B3_MOVED.md` §1.2
  construction), reported alongside for comparability with that document.

Q1 is 360 s and yields one 240 s block, so it is additionally cut at
`W = 90 s` (4 blocks) and reported separately as a short-timescale sanity
check. **Q1's B1 and B2 values are post- and pre-cycle respectively and Q1 is
therefore not a clean floor for §6; Q2 is the floor of record.** Stated now.

**Scoring rule, frozen.** An effect is **ABOVE THE FLOOR** only if
`|Δ| > FLOOR_adj` for that exact (receiver, beacon, feature) cell **and**
`|Δ| > 1.0 σ`. Both conditions, on the cell's own floor, not a pooled one.
An effect below either is **NOT DISTINGUISHABLE FROM WANDER** and is reported
in those words.

### 4.4 Analysis windows and the guard band

`W = 240 s` before and after each event, with a guard band:

- Guard **±30 s** around the *logged* time by default, because the operator
  states the minutes are reliable and the seconds are not.
- If §3 locates the event to better than ±5 s (a gap has a measured start and
  end), the guard shrinks to **±5 s around the measured time** and the reboot
  gap itself is excluded.

**`PC-B2` is structurally under-powered and this is stated before it is run.**
The capture starts at 18:00:02 and B2 is cycled at 18:01, so at most ~58 s of
pre-event data exists — under a quarter of `W`. Its before-window is whatever
is available from t = 0 to the guard, its admissible-frame count is printed,
and if it falls under the 2,000-frame floor for `κ` the `κ` arm of `PC-B2` is
reported as **not runnable**, not as a null.

Where a 240 s window would cross another event it is truncated at that
event's guard and the truncation is printed. Known collisions: `RB2`'s
after-window ends at `POS-FRIDGE`'s guard (≈ 270 s available — fits);
`MOVE-IN`'s after-window ends at `RB1`'s guard (≈ 450 s — fits, but see §9).

---

## 5. PREDICTIONS — frozen

Recorded so that the outcomes are scoreable and cannot be re-narrated. Each
is a claim about a number that does not yet exist.

### 5.1 On locating the events (§3)

| # | prediction | confidence |
|---|---|---|
| L1 | `PC-B1` and `PC-B2` are **LOCATED** as gaps of 1–20 s in exactly one beacon's stream, on **both** receivers | high |
| L2 | `RB1` and `RB2` are **LOCATED** as gaps of the same character in B3's stream | high |
| L3 | The four gap times land within **±60 s** of their logged minutes | moderate |
| L4 | `POS-FRIDGE` and `POS-OVEN` are **LOCATED** as RSSI steps; `POS-OVEN` (losing LOS) is the larger of the two | moderate |
| L5 | `MOVE-IN` is **LOCATED** as a large RSSI step — a beacon in a car outdoors should be much weaker than one in an interior room | high |
| L6 | The whole-file gap census turns up **at least one gap ≥ 1 s that the log does not mention**, on at least one stream | moderate |

### 5.2 On the power cycle (§6) — the load-bearing prediction

**Primary prediction: a transmitter power cycle does NOT move `κ` above this
file's floor.** `|Δκ| < FLOOR_adj` for B1 and B2 on both receivers.

The reasoning, so that being wrong is informative: `docs/IQ_IMBALANCE.md`
§1.3 derives that with a real-valued L-LTF the transmitter's image is absorbed
into the direct term and the conjugate coefficient is **receiver** silicon;
§15 measures `frac_rx ≥ 5.73` and calls it receiver-dominated. Boot-time RF
calibration in the *transmitter* therefore has little of `κ` to set. **If this
prediction fails — if a TX reboot moves `κ` by multiples of the floor — then
either §1.3's derivation is wrong or `κ` carries transmitter boot state, and
in both cases `κ` is unusable as a fingerprint across power cycles. That is
the more valuable outcome and it will be reported first if it occurs.**

| # | prediction | confidence |
|---|---|---|
| P1a | `\|Δκ\|` for the cycled beacon < `FLOOR_adj`, all four (beacon, receiver) cells | moderate |
| P1b | `Δ arg κ` for the cycled beacon < 20° on every cell | moderate |
| P1c | The SFO slope shift for the cycled beacon is **also** below its floor — a power cycle does not move the crystal | moderate |
| P1d | Whatever moves, moves **coherently on both receivers for the cycled beacon and not for the other two** if it is transmitter-side; a shift shared by all three beacons at one receiver is receiver-side and will be called that | high (this is a rule, not a value) |
| P1e | **Two instances agree**: B1's shift and B2's shift are within 3× of each other in magnitude | low — n = 2 |

### 5.3 On B3's two reboots (§7)

| # | prediction | confidence |
|---|---|---|
| P2a | Both reboots produce `\|Δκ\|` below the floor, consistent with P1a | moderate |
| P2b | **Replication criterion, frozen:** the two reboots *replicate* only if both `\|Δ\|` exceed the floor, their magnitudes are within 3×, and (for `κ`) their directions in the complex plane agree within 90°. With n = 2 a direction agreement is 50 % likely by chance and will be labelled as such | — |
| P2c | The wall-vs-battery **level** difference is confounded beyond rescue: the battery-before window (18:11–18:19) sits inside the thermal transient and the battery-after window (18:35–18:40) is 5 min long. It will be reported as **not a clean comparison**, not as a null | high |

### 5.4 On position (§8)

| # | prediction | confidence |
|---|---|---|
| P3a | RSSI moves clearly at both position events; the SFO slope moves **above** its floor on at least one cell at `POS-OVEN` | moderate |
| P3b | `arg κ` moves **less** than the SFO slope, in floor units, at both position events — this is the `docs/IQ_IMBALANCE.md` §15.1 result (4.1° across a 100 ft, three-storey move) tested on a much smaller move | moderate |
| P3c | `\|κ\|` moves with RSSI and is **discounted in advance** as dilution (§2.2), not read as an effect | high |
| P3d | **The fridge-compressor confound is real and is looked for, not assumed away.** A Lomb–Scargle / autocorrelation scan of the Q2 residual for periods in **20–40 min** is run on both features. If power is found in that band, every "settle-shaped" claim in that stretch is void, including any that would flatter this pass | — |

### 5.5 On the thermal step (§9)

| # | prediction | confidence |
|---|---|---|
| P4a | **Under-powered and will be reported as such.** `MOVE-IN` at 18:11 has 8.0 min before `RB1` lands in it, against the **τ = 10.8 min** settle constant `docs/THERMAL_STEP.md` §11.4 measured (on `s3/B2/arg κ`, an *untouched* beacon, at 120 s bins). Under a first-order settle, 8.0 min is 0.74 τ and observes 52 % of the step; the post-reboot remainder is not attributable | high |
| P4b | No SETTLE verdict is claimed for `MOVE-IN` on either feature. If a settle shape appears it is reported with the power limitation attached and **not** promoted | high |

### 5.6 Stop conditions

| condition | consequence |
|---|---|
| a logged event is **NOT LOCATED** | its test is reported as not runnable; no substitute time is chosen to make a test possible |
| an event window falls under 2,000 admissible frames for `κ` | that arm is **not runnable**, reported, not scored as a null |
| a floor cell cannot be computed (beacon absent from Q2) | every effect on that cell is **unscoreable** and is printed raw with no verdict |
| `κ` is at the noise floor on a cell (`align` below all four wrong-pairing nulls, `docs/IQ_IMBALANCE.md` §10.3) | that cell's `κ` deltas are **noise deltas** and carry no weight; the `align` test is run per analysis window, not once per file |
| the two features disagree about whether an event happened | both are reported; neither is chosen because it is tidier |

---

## 6. Test 1 — does a transmitter power cycle shift the fingerprint?

`PC-B2` (18:01) and `PC-B1` (18:08). **Two independent instances of the
cleanest manipulation in the file**: one device, in place, nothing else
changed, seven minutes apart, with the other two beacons serving as
contemporaneous controls in the same minutes on the same receivers.

Reported per (receiver, beacon, feature): before/after values, `Δ`, `Δ` in σ,
the cell's `FLOOR_adj` and `FLOOR_range`, the verdict from §4.3, admissible
frame counts, and RSSI before/after (a power cycle in place should not move
RSSI; if it does, the "in place" claim is in question and that is reported).

**The control arm is not optional.** B1 and B3 are measured across `PC-B2`'s
boundary and B2 and B3 across `PC-B1`'s, on the same windows. A shift that
appears on all three beacons at one receiver is receiver-side or
environmental and is called that (§5.2 P1d).

## 7. Test 2 — do B3's two reboots replicate?

`RB1` (18:19) and `RB2` (18:35), same device, same position, 16 min apart,
differing only in which power source they land on. Same table as §6, plus the
§5.3 P2b replication verdict, plus the wall-vs-battery level comparison with
its §5.3 P2c caveat attached in the same table row rather than in a footnote.

## 8. Test 3 — position

`POS-FRIDGE` (18:40, LOS) and `POS-OVEN` (19:10, LOS blocked). Same table.
Plus §5.4 P3d's periodicity scan of Q2 in the 20–40 min band, run **before**
any structure in that stretch is interpreted.

## 9. Test 4 — the thermal step

`MOVE-IN` (18:11). Run, reported with §5.5's power limitation stated in the
result rather than after it.

## 10. What this pass will not do

- No `pc/occ/` number is read, produced or combined with anything here. The
  device-ID and occupancy pipelines stay separate (`CLAUDE.md`).
- No device-ID accuracy figure (99.7 % / 95.7 %) is derived, revised or
  quoted without its condition. The ~77 % same-model figure is not quoted and
  not relabelled "same-lot".
- `docs/DIRECTION.md` is not cited as capability.
- No firmware is touched, no serial port is opened, nothing under `data/raw/`
  is written. Every input is opened `"rb"`.
- Nothing is staged, committed or pushed. No sub-agents.
- No claim is made about temperature, power source or line of sight beyond
  what §0.1 admits is operator account.

## 11. Reproduce

```
IQ_CACHE=/tmp/lab0823 python3 pc/exp_labelled_events_0823.py scan  --tag d0wd --path data/raw/d0wd_20260823_180002.csv --resume
IQ_CACHE=/tmp/lab0823 python3 pc/exp_labelled_events_0823.py scan  --tag s3   --path data/raw/s3_20260823_180002.csv   --resume
IQ_CACHE=/tmp/lab0823 python3 pc/exp_labelled_events_0823.py census
IQ_CACHE=/tmp/lab0823 python3 pc/exp_labelled_events_0823.py verify
IQ_CACHE=/tmp/lab0823 python3 pc/exp_labelled_events_0823.py report
IQ_CACHE=/tmp/lab0823 python3 pc/exp_labelled_events_0823.py selfcheck
```

Row and MAC counts of §1:

```
awk -F, 'NR>1{n++; if($2!="")lab++; m[$4]++} END{print n, lab+0, length(m)}' data/raw/d0wd_20260823_180002.csv
```

`selfcheck` verifies: the `dsp.py` sha256 and mtime are unchanged; the
imported `csi_to_complex` is byte-identical to the one on disk; the
checkpoint/resume equivalence of §2.1; and that `pc/exp_iq_imbalance.py`'s
estimator functions are imported rather than reimplemented.

## 12. Temptations recorded rather than acted on

*(filled in below the banner — see §24)*

---

# STAGE 2 — RESULTS

*(everything below this line was written after the numbers existed)*

## 13. THE ANSWER IN ONE PARAGRAPH

**A transmitter power cycle does not move `κ`.** Four transmitter reboots were
located in the data. On every cell where `κ` is measurable, the cycled
beacon's `κ` moved *less* than this file's own contemporaneous wander floor,
and the rotation it did show was the **same rotation the two untouched beacons
showed in the same minutes on the same receiver** — `arg κ` moved **+8.76°**
for the beacon that was power-cycled, against **+7.51°** and **+8.86°** for
the two that were not touched. After removing that common mode the treated
residual is **0.25 σ_κ** and **0.46 σ_κ** for the two instances. **`κ` is not
set by transmitter boot-time RF calibration**, and the
`docs/IQ_IMBALANCE.md` §19 item 2 hazard is narrowed — but not closed, because
it points at the *receiver*, and no receiver was rebooted in this capture.
The two B3 reboots **do not replicate**: neither clears the floor, and their
`arg κ` shifts have **opposite signs on both receivers**. What did move `κ`
is **position** — a whole-room relocation moved `arg κ` by **34.3°, 5.6× its
own floor**, on the receiver where the controls moved 2.4–6.4°. And on the
comparison the exercise exists for: **`κ`'s 4-minute wander floor is
0.27–1.54 × its between-device spread while the SFO slope's is
0.56–4.97 ×** — the slope's floor is a *multiple* of the whole between-device
spread on 5 of 6 cells, `κ`'s is a *fraction* of it on 5 of 6.

---

## 14. What was run

| | `d0wd_20260823_180002.csv` | `s3_20260823_180002.csv` |
|---|---|---|
| rows parsed | **1,044,694** | **1,484,861** |
| bytes consumed | 902,906,747 (= file size) | 1,235,397,467 (= file size) |
| malformed rows (`len != 13` or unparseable) | **0** | **0** |
| corrupt rows (field screen ∪ median filter) | **52** (field 51, median 52, both 51) | **0** |
| checkpoint/resume boundaries | 1 (at row 940,000) | 1 (at row 1,060,000) |

`selfcheck` output, run after the scans:

```
dsp.py sha256 f8ef124ac4f4ecfdbbdbe977b3492058ba9cd2afe94ebd10c24ab5a7b143dea2
interleave convention on disk: iq[1::2] + 1j*iq[0::2]  (imag,real)  OK
kappa estimator functions imported from exp_iq_imbalance.py  OK
FrameEstimator imported from rff.dsp, unmodified  OK
pickle round-trip preserves numpy Generator state  OK
```

The last line discharges §2.1's checkpoint claim: 50 successive
`ransac_line` draws from a pickled-and-restored `FrameEstimator._rng` are
identical to 50 from the original, so the two-part replay of each file is the
single continuous replay the RNG requires.

### 14.1 The screen, and the fabricated addresses

**19 byte-neighbours of a beacon MAC at Hamming distance ≤ 3 in octets on the
d0wd; 0 on the s3.** One is at **distance 1** — `f4:2d:c9:70:72:00`, B3's
address with the last octet zeroed. The other 18 are all at distance 2 and
**all differ in positions 4–5**, the same last-two-bytes signature
`docs/THERMAL_STEP.md` §11.2 found. Counts: 8 B2-variants, 7 B3-variants
(plus the d=1), 3 B1-variants.

> **Every one of the 19 has `clean = 0`.** The two screens caught all of them.

`07:d1:0a:d0:0a:ce` **is present, once, on the d0wd**, exactly as the brief
predicted. It contains `0a` twice, is **not** a byte-neighbour of any beacon,
and is one of 36 d0wd addresses seen **only** on corrupt rows. The `0d:0a`
*adjacent-pair* screen returns **0** on both files; the looser "any octet is
`0d` or `0a`" screen returns 6 (d0wd) and 4 (s3).

**Only the three beacon MACs entered any feature computation.**

### 14.2 The `label` column, and what "labelled" means here

**`label` is empty on all 2,529,555 data rows of both files.** The event log
is operator text supplied in the brief, not a field in the capture. This is
still the first capture in the project with known event *times* — but it is
**not** the `label`-column capture `docs/IQ_IMBALANCE.md` §19 item 2 asks for,
and §21 keeps that ask open.

---

## 15. VERIFYING THE LOG — all seven events located, two log claims wrong

Search run over the whole file, per §3, before any event was used.

| event | logged | **measured** | **offset** | signature | on both rx? |
|---|---:|---|---:|---|---|
| `PC-B2` | 57.4 s | **gap 58.9 → 117.2 s** | **+1.5 s** | 58.30 s (d0wd) / 58.16 s (s3) off air | **yes** |
| `PC-B1` | 477.4 s | **gap 481.6 → 541.0 s** | **+4.2 s** | 59.25 s / 59.27 s off air | **yes** |
| `MOVE-IN` | 657.4 s | **645.3 → 656.6 s** | **−12.1 s** | 11.28 s s3 dropout; RSSI step **10.0 dB** (d0wd, t=630) / 4.5 dB (s3, t=650) | RSSI yes, dropout s3 only |
| `RB1` | 1137.4 s | **gap 1139.8 → 1208.1 s** | **+2.4 s** | 68.29 s / 68.24 s off air | **yes** |
| `RB2` | 2097.4 s | **gap 2102.7 → 2108.2 s** | **+5.4 s** | 5.43 s / 5.47 s off air | **yes** |
| `POS-FRIDGE` | 2397.4 s | RSSI step **2360 s** (d0wd) / **2440 s** (s3) | **−37 s / +43 s** | 3.0 dB / **10.0 dB** | **yes** |
| `POS-OVEN` | 4197.4 s | RSSI step **4180 s** (d0wd) / **4200 s** (s3) | **−17 s / +3 s** | **8.0 dB** / 2.5 dB | **yes** |

**All seven are LOCATED. None is NOT LOCATED.** Every gap-located event
appears on **both** receivers within 0.1 s for the same MAC and for no other
MAC, which is §3.1 rule 3's transmitter-reboot signature rather than a link
dropout. The gap-located offsets are **+1.5 s to +5.4 s**: the operator's
statement that the minutes are reliable and the seconds are not is confirmed
to better than 6 seconds. Predictions **L1, L2, L3, L4, L5** all hold, with
one correction to L4 below.

### 15.1 Two things the log says that the data contradicts

**(1) "brief, seconds off" is wrong for three of the four cycles.** The
measured off-air durations are **58.3 s, 59.3 s, 68.3 s and 5.4 s**. Only
`RB2` is "seconds"; the other three are about a minute. The distribution
makes this unambiguous rather than a judgement call: the median inter-frame
gap on every beacon stream is **1.0 ms** and the 99th percentile is
**183–204 ms**, so a 58-second hole is five orders of magnitude out of the
body of the distribution and there are only **1–3 gaps ≥ 1 s per stream on the
d0wd and 1–9 on the s3 across 2 h 06 m.**

This matters for §17: **`RB1` (68.3 s) and `RB2` (5.4 s) are not the same
manipulation in the data.** The log presents them as a matched pair differing
only in power source; the capture says one board was off air for over a minute
and the other for five seconds.

**(2) "LOS BLOCKED" at the oven is contradicted — the link got better.** L4
predicted `POS-OVEN` would be the larger RSSI step because it loses the direct
path. It is the larger step on the d0wd (8.0 vs 3.0 dB) but **in the wrong
direction**, and it is the smaller one on the s3 (2.5 vs 10.0 dB). Interval
medians for B3:

| interval | d0wd RSSI | d0wd fps | s3 RSSI | s3 fps |
|---|---:|---:|---:|---:|
| fridge top (2437–4197 s) | −72 | 54.02 | −72 | 71.05 |
| **oven (4237–7586 s)** | **−63** | **63.53** | **−69** | **78.50** |

**B3 is 9 dB stronger on the d0wd and 3 dB stronger on the s3 at the oven than
on the fridge top, and its frame rate rises on both.** Either the fridge top
was the shadowed position — it is a large grounded metal surface immediately
under the antenna, which the brief itself flags — or the half-wall
pass-through carries the path well. **The sharper manipulation §8 was designed
around did not occur**, and §18 scores `POS-OVEN` accordingly instead of
calling it a line-of-sight test.

### 15.2 L6 holds: gaps the log does not mention

- **d0wd / B1, t = 7331.9 s, 1.28 s** — 20:02 local, no logged event, d0wd
  only. A link dropout by rule 3.
- **s3 / B3, eight further gaps of 1.21–11.28 s** at t = 645.3, 665.3, 1122.8,
  1138.1, 2075.5, 2078.3, 2079.5 s — **s3 only**, so link dropouts, not
  reboots. They cluster tightly around the three moments the log says B3 was
  being physically handled (18:11 carry, 18:19 replug, 18:35 replug), which is
  corroboration of the log rather than a contradiction of it. The 11.28 s one
  at t = 645.3 s is the tightest independent anchor for `MOVE-IN` and is what
  §15's table uses.

### 15.3 What remains UNVERIFIABLE BY DESIGN

Per §3.3, and stated rather than assumed: **temperature** (no column, no
sensor — `MOVE-IN`'s "car → indoors at outdoor temperature" is operator
account only), **which power source a reboot landed on** (a wall/battery swap
at a fixed position changes nothing the CSV records beyond the interruption
itself), and **"in place"** for the two power cycles — see §16.3, where one of
them moved the link by 4 dB.

---

## 16. TEST 1 — DOES A TRANSMITTER POWER CYCLE SHIFT THE FINGERPRINT?

**No.** Two independent instances, both in the same direction, on the receiver
where `κ` is measurable for all three beacons.

`σ_sfo = 0.00237` (`BETWEEN_UNIT_SD`). `σ_κ` computed on this file from Q2:
**0.00294 (d0wd), 0.00829 (s3)**. For reference and not fused with anything:
`docs/IQ_IMBALANCE.md` §14 measured 0.00318 / 0.00848 for the same quantity on
the `014740` session — **8 % and 2 % from these, on a different day.**

### 16.1 `PC-B1` — B1 power-cycled at 18:08, 59.3 s off air

**s3**, 240 s before / 94 s after (the after-window is truncated by
`MOVE-IN`'s guard):

| beacon | role | `arg κ` before → after | **Δ arg** | \|Δκ\| /σ_κ | floor /σ_κ | ΔSFO /σ_sfo | floor /σ_sfo |
|---|---|---|---:|---:|---:|---:|---:|
| **B1** | **TREATED** | −77.26° → −68.50° | **+8.76°** | 0.40 | 0.28 | +0.97 | 0.56 |
| B2 | untouched | −115.03° → −107.51° | **+7.51°** | 0.31 | 0.37 | +0.30 | 1.74 |
| B3 | untouched | −114.40° → −105.54° | **+8.86°** | 0.35 | 0.27 | +1.32 | 4.97 |

> **The beacon that was power-cycled rotated by 8.76°. The two beacons that
> were not touched rotated by 7.51° and 8.86°, in the same direction, in the
> same minutes.** The treatment is invisible inside a receiver-side common
> mode. This is §5.2 prediction **P1d** — written as a rule before any value
> existed — firing exactly as written.

Common-mode removed (componentwise median of the two control Δκ, the
`docs/IQ_IMBALANCE.md` §4.1 construction): **treated residual = 0.25 σ_κ.**

**d0wd:** `κ` on d0wd/B1 is **AT NOISE FLOOR** in both windows — `align`
below its wrong-pairing nulls, `|κ|` 0.0007 → 0.0014 — reproducing
`docs/IQ_IMBALANCE.md` §12's whole-session finding for that exact cell. Per
§5.6 it is **unscoreable** and carries no weight. Its SFO is +2.36 σ against a
2.69 σ floor → wander.

### 16.2 `PC-B2` — B2 power-cycled at 18:01, 58.3 s off air

**s3**, 54 s before / 240 s after. The before-window is short because the
capture started 56 s before the cycle — §4.4 named this in advance. It
nevertheless carries **2,986 admissible frames**, above the 2,000 floor, so
the `κ` arm **is** runnable on s3 and on d0wd (3,144).

| beacon | role | `arg κ` before → after | **Δ arg** | \|Δκ\| /σ_κ | floor /σ_κ | ΔSFO /σ_sfo | floor /σ_sfo |
|---|---|---|---:|---:|---:|---:|---:|
| **B2** | **TREATED** | −125.23° → −115.59° | **+9.63°** | 0.37 | 0.37 | +1.13 | 1.74 |
| B1 | untouched | −85.06° → −76.78° | **+8.29°** | 0.11 | 0.28 | −0.12 | 0.56 |
| B3 | untouched | −111.64° → −115.15° | −3.51° | 0.31 | 0.27 | −1.82 | 4.97 |

Common-mode removed: **treated residual = 0.46 σ_κ.**
**d0wd**, B2 treated: Δ arg = **+5.45°**, \|Δκ\| = 0.71 σ_κ against a 1.00 σ_κ
floor, ΔSFO = +1.63 σ against a 3.49 σ floor. **Below the floor on both
features.**

### 16.3 The verdict, and the one thing that did change

| prediction | outcome |
|---|---|
| **P1a** `\|Δκ\|` < floor on the treated cells | **HOLDS.** 0.37 and 0.40 σ_κ (s3), 0.71 σ_κ (d0wd/B2); floors 0.37, 0.28, 1.00. s3/B2 is *below* its floor by a hair (0.003057 against 0.003073); s3/B1 exceeds its floor (0.40 vs 0.28) but is far under the 1.0 σ_κ half of the §4.3 rule. d0wd/B1 unscoreable. |
| **P1b** `Δ arg κ` < 20° on every cell | **HOLDS.** +5.45°, +8.76°, +9.63°. |
| **P1c** the SFO also below its floor | **HOLDS on 3 of 4.** The fourth, s3/B1 at +0.97 σ against a 0.56 σ floor, exceeds its floor but not the 1.0 σ half of the rule. |
| **P1d** transmitter-side ⇒ confined to the cycled beacon on both receivers | **The discriminator says receiver-side.** All three beacons rotate together, +7.5° to +8.9°. |
| **P1e** the two instances agree within 3× | **HOLDS.** Common-mode-corrected residuals 0.25 and 0.46 σ_κ — 1.8× apart. |

> ### `κ` survives a transmitter power cycle. Two instances, both receivers, both features below this file's own floor.
>
> This is the answer to the question `docs/IQ_IMBALANCE.md` §19 item 2 raised
> about boot-time RF calibration, for the **transmitter** half of it: **`κ` is
> not set by transmitter boot state.** That is consistent with §1.3's
> derivation — with a real-valued L-LTF the conjugate coefficient is receiver
> silicon — and with §15's `frac_rx ≥ 5.73`.
>
> **It does not close §19 item 2.** The unexplained ~155° d0wd rotation is a
> *receiver*-side common mode, and **no receiver was rebooted in this
> capture.** Four transmitter reboots produce ≤ 10° on the s3; a receiver
> reboot is still untested and is still the first thing to settle. §21 carries
> it forward unchanged.

**One thing did change across a power cycle, and it is reported rather than
buried: B1's link.** Its s3 RSSI went **−80 → −76 dB** across `PC-B1` and
stayed at −76/−77 for the remaining 1.8 h, while its d0wd RSSI moved only
−82 → −81. A change in transmit power at boot would move both receivers
equally; a 4 dB / 1 dB split is geometric. **The most likely reading is that
the board was nudged while being unplugged, i.e. "in place" is approximate** —
which is a `CLAUDE.md`-**G** correction to the log, not to the result: `arg κ`
moved 8.76° across a reboot *and* a 4 dB link change, still inside the
controls' band. `|κ|` did move — 0.00529 → 0.00840, **+59 %** — and that is
the SNR dilution §2.2 committed in advance to discounting: B2, whose RSSI
moved −1 dB across its own cycle, moved `|κ|` by **+1.7 %**.

---

## 17. TEST 2 — DO B3'S TWO REBOOTS REPLICATE? No.

**They are not the same manipulation in the data.** `RB1` is **68.3 s** off
air, `RB2` is **5.4 s** (§15.1). The log presents them as a matched pair.

| | rx | Δ arg κ | arg floor | \|Δκ\|/σ_κ | floor/σ_κ | ΔSFO/σ_sfo | floor/σ_sfo | verdict |
|---|---|---:|---:|---:|---:|---:|---:|---|
| **RB1** | s3 | **+5.89°** | 6.08° | 0.21 | 0.27 | −0.50 | 4.97 | wander |
| **RB1** | d0wd | **−34.10°** | 25.83° | 0.85 | 1.54 | +2.02 | 2.12 | wander |
| **RB2** | s3 | **−8.09°** | 6.08° | 0.61 | 0.27 | +0.33 | 4.97 | wander |
| **RB2** | d0wd | **+53.44°** | 25.83° | 1.36 | 1.54 | −3.21 | 2.12 | see below |

**The §5.3 P2b replication criterion, applied as frozen:** replication
requires *both* `|Δ|` above the floor, magnitudes within 3×, and directions
within 90°.

- **Neither reboot clears the floor** on `|Δκ|` on any cell (0.21, 0.85, 0.61,
  1.36 against floors 0.27, 1.54, 0.27, 1.54 — the two that exceed their floor
  are both under the 1.0 σ_κ half of the rule).
- **The directions oppose on both receivers**: +5.89° vs −8.09° on the s3,
  −34.10° vs +53.44° on the d0wd. A sign flip is the opposite of replication,
  and it happens independently on two receivers.

> **NOT REPLICATED, and consistent with no effect.** Both reboots sit inside
> ordinary wander and point opposite ways. Combined with §16 that is **four
> transmitter reboots, none of which moves `κ` above this file's floor.**

**The d0wd SFO cannot be used for `RB1`/`RB2`, and this is a control failure
reported as one.** In `RB1`'s windows the two **untouched** beacons moved
**more** than the treated one — B1 −3.69 σ and B2 −9.07 σ, both above their
floors, against B3's +2.02 σ below its floor. The same at `RB2`: B1 −4.98 σ,
B2 −5.21 σ, B3 −3.21 σ, **all three above floor together**. A receiver-wide
excursion in the SFO between 18:19 and 18:40 on the d0wd swamps the
manipulation. **Nothing about `RB2`'s d0wd "ABOVE FLOOR" SFO row can be
attributed to B3.** `κ` on the same windows shows no such common excursion —
the d0wd controls sit at 0.27–0.91 σ_κ.

### 17.1 Wall versus battery — not a clean comparison, as §5.3 P2c committed

B3's interval medians, with the caveat in the same table rather than a
footnote:

| period | source (operator) | d0wd RSSI | s3 RSSI | d0wd SFO | s3 SFO |
|---|---|---:|---:|---:|---:|
| 18:11–18:19 (697–1137 s) | battery | −77 | −83 | +0.016165 | +0.020240 |
| 18:19–18:35 (1177–2097 s) | **wall** | −76 | −81 | +0.022143 | +0.014189 |
| 18:35–18:40 (2137–2397 s) | battery | −75 | −85 | +0.024914 | +0.016321 |

**No consistent wall-versus-battery level difference exists in this data and
none is claimed.** RSSI moves +1/−1 on the d0wd and +2/−4 on the s3 — opposite
signs on the two receivers. The design cannot support the comparison anyway:
the first battery period **is the thermal transient** of §19, the second is
**4.3 minutes long**, and the two are separated by 16 minutes of ordinary
drift. This is reported as **not a clean comparison**, not as a null.

---

## 18. TEST 3 — POSITION. The only manipulation that moved either feature.

### 18.1 `POS-FRIDGE` (18:40) — interior room → kitchen, fridge top

This is a **whole-room relocation**, not the 3-foot move; §18.2 is the small
one.

| beacon | rx | role | `arg κ` before → after | **Δ arg** | **/floor** | \|Δκ\|/σ_κ | floor | ΔRSSI |
|---|---|---|---|---:|---:|---:|---:|---:|
| **B3** | **s3** | **TREATED** | −128.62° → −94.34° | **+34.28°** | **5.64×** | **1.59** | 0.27 | **+12 dB** |
| B1 | s3 | control | | +6.42° | 0.37× | 0.12 | 0.28 | 0 |
| B2 | s3 | control | | +2.35° | 0.46× | 0.11 | 0.37 | +2 |
| **B3** | **d0wd** | **TREATED** | | **−70.06°** | **2.71×** | **2.03** | 1.54 | +4 dB |
| B1 | d0wd | control | | +88.0° | 0.28× | 0.44 | 0.78 | −1 |
| B2 | d0wd | control | | +4.14° | 0.16× | 0.35 | 1.00 | 0 |

*(d0wd/B1's 88° is a noise-floor cell — its own arg floor is 316.8°, so 0.28×.)*

> **`κ` is ABOVE THE FLOOR on both receivers**, by 5.9× and 1.3× on `|Δκ|` and
> by **5.64× and 2.71× on `arg κ`**, while every control on both receivers
> stays at 0.16–0.46× of its own floor. Common-mode removed, the treated
> residual is **1.51 σ_κ (s3)** and **2.40 σ_κ (d0wd)** — the effect survives
> common-mode removal, is transmitter-specific, and appears on both receivers.

**`|κ|` is discounted here exactly as §2.2 committed in advance** — it went
0.01421 → 0.02224 on the s3 alongside a +12 dB RSSI change, which is textbook
noise dilution. **The claim rests on `arg κ`, which SNR cannot rotate**, and
`arg κ` moved 5.64× its floor.

**The SFO detects this on one receiver only**: d0wd −2.76 σ against a 2.12 σ
floor (**ABOVE**), s3 +1.46 σ against a **4.97 σ** floor (wander). The s3/B3
SFO floor is so wide that a whole-room relocation disappears into it.

### 18.2 `POS-OVEN` (19:10) — fridge top → oven, ~3 ft west, 2 ft lower

Remember §15.1: **the link improved.** This is a 3-foot move that made things
better, not a line-of-sight test.

| rx | Δ arg κ | /floor | \|Δκ\|/σ_κ | floor | ΔSFO/σ_sfo | floor | ΔRSSI |
|---|---:|---:|---:|---:|---:|---:|---:|
| s3 | **+7.66°** | 1.26× | 0.34 | 0.27 | −1.02 | 4.97 | +4 dB |
| d0wd | **+38.63°** | 1.49× | 1.42 | 1.54 | −2.19 | 2.12 | +8 dB |

**Neither feature clears the two-part bar on either receiver.** Both are
marginally above their own floors (1.26–1.49× on `arg κ`, 1.03× on the d0wd
SFO) and below it elsewhere. A 3-foot repositioning is at the edge of what
either feature resolves against this file's wander — reported as marginal,
not promoted to an effect.

### 18.3 The fridge compressor — looked for, and it is there

§5.4 **P3d** required this scan whichever way it fell. Q2 (56.5 min) in 60 s
blocks, linearly detrended first, best least-squares sinusoid in the
20–40 minute band:

| rx / beacon | SFO | `arg κ` | RSSI |
|---|---|---|---|
| **d0wd / B3** (at the oven, beside the fridge) | **T = 23.5 min, R² = 0.445** | **T = 24.0 min, R² = 0.222** | **T = 23.5 min, R² = 0.216** |
| d0wd / B1 (bench) | 25.0 min, 0.151 | 26.5 min, 0.058 | 39.0 min, 0.219 |
| d0wd / B2 (bench) | 40.0 min, 0.242 | 38.0 min, 0.053 | 30.5 min, 0.095 |
| s3 / B3 | 40.0 min, 0.258 | 20.0 min, 0.040 | 22.5 min, 0.133 |

**B3 on the d0wd locks three independent quantities to the same ~23.5-minute
period; the two bench beacons on the same receiver do not.** With 56.5 minutes
the band holds only **1.4–2.8 cycles**, so this is **not** a compressor
detection and is not offered as one. What it does establish, which is what
matters:

1. **B3's quiet stretch contains real 20–40 minute structure**, so **B3's floor
   is inflated by it and every score against that floor in §§16–19 is
   conservative** — the confound works against this pass's positives, not for
   them.
2. **No settle-shaped claim inside Q2 would be safe.** None is made anywhere in
   this document.
3. `arg κ` carries **half** the periodic R² the SFO does on the affected cell
   (0.222 vs 0.445) — a third, independent sense in which `κ` is the quieter
   feature.

---

## 19. TEST 4 — THE THERMAL STEP AT 18:11. Under-powered, and reported as such.

**§5.5 P4a predicted this and it is what happened.** `MOVE-IN`'s clean window
is bounded by `PC-B1` on one side and `RB1` on the other:

- **before-window: 94 s**, not 240 s — truncated by `PC-B1`'s guard.
- **after-window: 240 s**, and the reboot lands **483 s = 8.05 min** after the
  move, confirming the brief's arithmetic to the second.
- 8.05 min against `docs/THERMAL_STEP.md` §11.4's **τ = 10.8 min** is
  **0.75 τ**, which observes **53 %** of a first-order step.

| rx | Δ arg κ | arg floor | \|Δκ\|/σ_κ | floor | ΔSFO/σ_sfo | floor | ΔRSSI | status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| s3 | **+4.81°** | 6.08° | 0.18 | 0.27 | −0.65 | 4.97 | +4 dB | below floor on both features |
| d0wd | −104.93° | 25.83° | 1.13 | 1.54 | +0.39 | 2.12 | +10 dB | **`κ` AT NOISE FLOOR — unscoreable** |

The d0wd row is unscoreable for the reason §5.6 named in advance: B3 sat at
**−87 dBm** on the d0wd while it was in the car, `align` falls below its
wrong-pairing nulls in the before-window, and a rotation computed from a
noise-floor `κ` is a rotation of noise.

> **No SETTLE verdict is claimed for `MOVE-IN` on either feature, and no
> attempt is made to fit one.** The window is half a time constant, the
> before-side is 94 s, one receiver is unscoreable and a 68-second reboot lands
> in the middle of the transient. **P4b honoured.**

---

## 20. WHICH FEATURE HELD UP BETTER — the floors decide it

The comparison the exercise exists for, and it does not depend on any single
event. **This file's own 4-minute wander floor in Q2, per cell, in each
feature's own between-device units:**

| rx | beacon | **SFO floor** (× σ_sfo) | **`κ` floor** (× σ_κ) | `arg κ` floor |
|---|---|---:|---:|---:|
| d0wd | B1 | 2.69 | 0.78 | 316.8° *(noise-floor cell)* |
| d0wd | B2 | 3.49 | 1.00 | 25.2° |
| d0wd | B3 | 2.12 | 1.54 | 25.8° |
| s3 | B1 | **0.56** | 0.28 | 17.3° |
| s3 | B2 | 1.74 | 0.37 | 5.2° |
| s3 | B3 | **4.97** | 0.27 | 6.1° |

> ### The SFO slope's wander floor is **0.56–4.97 × the entire between-device spread**. `κ`'s is **0.27–1.54 ×**.
>
> Over **four minutes**, in a stretch where nothing was touched, the shipped
> phase slope moves by a **multiple** of the whole between-device spread on
> **5 of 6** cells. `κ` moves by a **fraction** of it on **5 of 6**.
>
> For scale: `docs/B3_MOVED.md` §9.1 measured a stationary beacon wandering
> **2.5–4.9 σ across a single night**. On `s3/B3` this file's slope reaches
> **4.97 σ between two adjacent four-minute blocks.** That is not a revision
> of §9.1 — different file, different block length, different statistic — but
> it is the same phenomenon measured on a third capture and it is why §4.3
> insisted on a contemporaneous floor.

Then, event by event:

| manipulation | what a device fingerprint **should** do | SFO | `κ` |
|---|---|---|---|
| 4 × transmitter reboot | not move | strictly below floor on **6 of 8** cells. Of the two exceptions, `RB2`/d0wd is a receiver-wide excursion that moved the **untouched** controls further (§17), and `PC-B1`/s3 (0.97 σ against a 0.56 σ floor) is the cell whose link also moved 4 dB (§16.3) | **below floor on every scoreable cell** except s3/B1 at 0.40 vs a 0.28 floor — and that one is 0.40 σ_κ, a fifth of a between-device spread, and matches the two untouched controls' rotation (§16) |
| whole-room relocation | (a channel effect either may show) | above floor on **1 of 2** receivers | above floor on **2 of 2**, `arg κ` at 5.64× and 2.71× floor, controls at 0.16–0.46× |
| 3 ft relocation | — | marginal on 1 of 2 | marginal on 2 of 2 |
| ~23.5 min ambient periodicity | not track it | R² = 0.445 | R² = 0.222 |

> **`κ` held up better on every axis measured here**: a tighter floor, silence
> under four reboots, cleaner control behaviour, and half the coupling to
> ambient periodicity.
>
> **And the finding that cuts against `κ`, stated with the same prominence:
> `κ` is not position-invariant.** A whole-room relocation moved `arg κ` by
> **34.3°, 5.6× its own floor, on both receivers, with contemporaneous
> controls quiet.** A feature that moves five floors when the transmitter
> changes rooms is measuring something about the link, not only about the
> silicon. **This disagrees with `docs/IQ_IMBALANCE.md` §15.1**, which found
> `arg κ` moving **4.1°** across a 100 ft, three-storey, indoor-to-outdoor
> relocation and called it "the strongest single piece of evidence in this
> pass that `κ` is analog silicon." Both measurements are reported; neither is
> chosen because it is tidier. The differences are named in §22, and the
> present one is the better-controlled of the two — within-session, two
> receivers, two contemporaneous untouched controls, and a floor computed from
> the same file — while §15.1 was a two-capture comparison on a link that had
> weakened.

---

## 21. VERDICTS AGAINST THE STAGE-1 THRESHOLDS

| # | prediction | outcome |
|---|---|---|
| L1 | `PC-B1`/`PC-B2` located as 1–20 s gaps on both receivers | **partly wrong.** Located on both receivers, but the gaps are **58–59 s**, outside the predicted range |
| L2 | `RB1`/`RB2` located as gaps | **HOLDS** (68.3 s, 5.4 s) |
| L3 | gap times within ±60 s of the log | **HOLDS**, and far better: +1.5 to +5.4 s |
| L4 | both positions located; `POS-OVEN` the larger step | **half wrong.** Both located; `POS-OVEN` is larger on the d0wd but **in the wrong direction**, and smaller on the s3 |
| L5 | `MOVE-IN` a large RSSI step | **HOLDS** (10.0 dB d0wd) |
| L6 | ≥ 1 unlogged gap ≥ 1 s | **HOLDS** (9 of them) |
| P1a–e | power cycle does not move `κ` | **ALL HOLD** (§16.3) |
| P2a | both B3 reboots below floor | **HOLDS** |
| P2b | replication criterion | **NOT REPLICATED** — neither clears the floor and the signs oppose on both receivers |
| P2c | wall-vs-battery confounded beyond rescue | **HOLDS** — reported as not a clean comparison |
| P3a | SFO above floor on ≥ 1 cell at `POS-OVEN` | **marginal** — d0wd 1.03× floor, s3 0.21× |
| P3b | `arg κ` moves **less** than the SFO in floor units at both position events | **WRONG, and it is the most consequential thing this pass got wrong.** At `POS-FRIDGE` `arg κ` moves **5.64×** its floor on the s3 where the SFO moves **0.29×**; at `POS-OVEN` 1.26×/1.49× against 0.21×/1.03× |
| P3c | `\|κ\|` tracks RSSI, discounted in advance | **HOLDS** (+59 % on a +4 dB link, +1.7 % on a −1 dB link) |
| P3d | compressor band scanned whichever way it falls | **RUN.** Structure found at ~23.5 min on the affected cell; it inflates B3's floor, making every score conservative |
| P4a/b | thermal step under-powered, no settle claimed | **HOLD** |

---

## 22. LIMITATIONS

- **n = 4 transmitter reboots, n = 3 devices, n = 2 receivers, n = 1 session.**
  §16 is two instances on one beacon each. It is the cleanest available test
  of the boot-state hypothesis, not a powerful one.
- **No receiver was rebooted.** §16 excludes *transmitter* boot state as the
  cause of `docs/IQ_IMBALANCE.md` §15.1's ~155° d0wd rotation. It says nothing
  about receiver boot state, which is where that rotation's common-mode
  signature points, and which §19 item 2 of that document asked for.
- **`label` is empty on every row** (§14.2). The treatment assignment reaches
  the data only through the wall clock; §15 anchors it to ±6 s for the four
  gap-located events and to ±43 s for the two RSSI-located ones.
- **d0wd/B1 is at the `κ` noise floor throughout**, as in
  `docs/IQ_IMBALANCE.md` §12, so one of the two `PC-B1` cells is unscoreable
  and `PC-B1`'s `κ` result rests on the s3 alone.
- **`PC-B2`'s before-window is 54 s** because the capture started 56 s before
  the event. It clears the 2,000-frame floor on both receivers but it is not a
  240 s window and is not equivalent to one.
- **`MOVE-IN`'s before-window is 94 s** and its temperature claim is
  unverifiable from this data (§15.3).
- **The d0wd SFO shows a receiver-wide excursion between 18:19 and 18:40** that
  moves untouched beacons by 3.7–9.1 σ (§17). Its cause is not known and was
  not investigated; no d0wd SFO figure from that stretch is used.
- **§18.3's periodicity scan cannot resolve the 20–40 min band** — 1.4–2.8
  cycles — and is used only to establish that structure exists there, not to
  identify the compressor.
- **§20's disagreement with `docs/IQ_IMBALANCE.md` §15.1 is unresolved.** The
  two measurements differ in design (within-session vs cross-capture),
  controls (two contemporaneous untouched beacons vs one), receivers (both vs
  one usable) and link quality. This pass does **not** revise any §15.1 number;
  it reports a contradiction and §23 names what would settle it.
- **`σ_κ` is a within-file quantity** computed on Q2 from three devices. It is
  not `BETWEEN_UNIT_SD`, was never compared to it, and the two are never added.
- **The deterministic slope `m_f`** was accumulated as a byproduct and is not
  reported; no SFO figure here comes from it. Every SFO number is the shipped
  `FrameEstimator` + `WindowAggregator(64, 0.6, 0.8)`.
- **Sensitivity check, and it argues for §3's design.** Re-running §§16–19 with
  the **logged** times and the ±30 s guard instead of the measured ones flips
  `PC-B2`'s d0wd SFO to −6.00 σ ("ABOVE FLOOR") — because a ±30 s guard does
  not clear a **58 s** outage and the windows straddle the hole. Every
  `κ` conclusion is unchanged by the substitution. This is the concrete cost
  of trusting a log instead of locating the event.
- **No `pc/occ/` number** was read, produced or combined with anything here. No
  device-ID accuracy figure is derived or revised. The ~77 % same-model figure
  is not quoted and not relabelled. `docs/DIRECTION.md` is not cited as
  capability.

---

## 23. WHAT WOULD SETTLE IT

1. **Reboot a receiver, with the reboot written into the `label` column.**
   §16 removed the transmitter half of `docs/IQ_IMBALANCE.md` §19 item 2. The
   receiver half is untouched and is now the single highest-value experiment
   available: it is one capture, it costs nothing, and it decides whether `κ`
   is usable across sessions.
2. **Resolve §20's contradiction with `docs/IQ_IMBALANCE.md` §15.1.** Move one
   beacon between three known positions inside one session, with the moves
   logged and the other two beacons untouched, and measure `arg κ` against a
   contemporaneous floor at each. Distance is evidently not the right axis —
   4.1° over 100 ft and 34.3° over one room change are not on the same curve.
3. **A power cycle with the board clamped.** §16.3's 4 dB RSSI change on the
   s3 means "in place" was approximate. A reboot that provably does not move
   the antenna would make §16 a clean isolate instead of a well-controlled one.
4. **More than two reboots per device.** §17's non-replication rests on n = 2
   with a 68 s / 5.4 s mismatch. Ten scripted reboots in one capture would give
   the question a real answer.
5. **Longer quiet stretches.** Q2 is 56.5 min, which is why §18.3 cannot
   resolve the compressor band and why the floors rest on 14 blocks.

---

## 24. Temptations recorded rather than acted on

- **Dropping `POS-FRIDGE` from the `κ` story.** It is the one result that
  weakens `κ` as an identity feature, and §5.4's P3b predicted the opposite. It
  is in §18.1 and §20 with the same prominence as §16.
- **Calling `RB2`'s d0wd SFO row an effect.** It is above its floor — and so
  are both untouched controls, by more. §17 says so.
- **Rescoring `POS-OVEN` as a line-of-sight test.** The link improved (§15.1);
  the frozen text calls it "LOS blocked" and the correction is made below the
  banner with the original left standing, per the Stage-1 rule.
- **Re-fitting a settle at `MOVE-IN` with a shorter τ.** The window is 0.75 τ
  with a reboot in it. §19 declines.
- **Widening `σ_κ` to the whole file** rather than Q2, which would have shrunk
  every `κ` score. §2.4 fixed Q2 in advance and Q2 was used.
- **Quoting `docs/IQ_IMBALANCE.md` §14's 0.00318/0.00848 as this file's σ_κ.**
  They are close (8 % / 2 %) and it would have saved a step. They are a
  different session's numbers and appear only as a comparison.

---

## Files added or written by this investigation

- `pc/exp_labelled_events_0823.py` — the one script; source of every number above
- `docs/LABELLED_EVENTS_0823.md` — this file

`pc/rff/dsp.py` was **read and imported unchanged** (sha256 verified after the
run). `pc/exp_iq_imbalance.py` was **imported, not modified**, and `selfcheck`
asserts that `frames_to_H`, `deslope`, `process_batch`, `features` and
`add_cells` resolve to that file. Nothing under `data/raw/`, `firmware/`,
`pc/occ/` or `site/` was touched; every input was opened `"rb"`. No serial
port was opened. All scratch went to `$IQ_CACHE = /tmp/lab0823`, outside the
repo tree. Nothing was staged, committed or pushed. No sub-agents.
