# B3_MOVED — the first deliberate manipulation, and what it actually measured

**Short version.** The beacon that was moved is **B3 (`f4:2d:c9:70:72:30`)**,
not B1. B3 delivered **0 admissible frames on the d0wd and 5 on the S3**
against a floor of 640, so **no slope comparison for the treated unit exists**
and the primary question is unanswerable from this capture. Separately, the
control failed: **B2, which did not move, shifted +3.96 `BETWEEN_UNIT_SD` on
the S3**, 9.4× its own overnight null band. Both facts are below with the
commands that produce them.

---

## 0.0 AMENDMENT — how the treated unit was identified, and why this file is not `B1_MOVED.md`

**This section is an amendment, added after the pre-registration in §0–§6 was
written and saved, and it is the only thing in this document that changes what
was frozen. It changes a *label*, not a prediction.**

Sequence of events, in order, with nothing reordered:

1. The pre-registration in §0–§6 below was written and saved as
   `docs/B1_MOVED.md` on the operator's initial report that **B1** had been
   moved. At that point **no** frame count, RSSI or slope had been computed
   from any file. That text is reproduced below unedited; where it says "B1"
   as the *treated unit* it should be read as "the treated unit", and the role
   assignment is resolved in step 3.
2. The operator then reported that he was **no longer certain which physical
   board was moved** — he had been unplugging transmitters to identify them and
   lost track of which board corresponds to which name. It may have been B3.
3. **The treated unit was then identified empirically, from RSSI and frame
   rate only** (§7). RSSI is not the outcome variable; the outcome variable is
   the `pc/rff/dsp.py` phase slope. At the moment of identification **no slope
   had been computed from any file** — the only outputs that existed were row
   counts and byte offsets from the replay's progress lines. The identification
   is therefore independent of the statistic the pre-registration is about, and
   the pre-registration's predictions were not adjusted to fit it: P1 is
   evaluated below as **falsified**, decisively, by the identified unit.
4. This file is named for what the data says happened. `docs/B1_MOVED.md`
   could not be deleted — `rm` on this mount returns `Operation not
   permitted`, the same restriction `docs/RIPPLE_TEST.md` §7 records — so it
   has been **overwritten with a short redirect stub** pointing here. That
   is disclosed rather than left to be discovered.

**Role reassignment, and its one consequence for the frozen text.** §1's
control design named B2 and B3 as the controls. With B3 identified as the
treated unit, **the controls are B1 and B2**. §1's decision table is applied
unchanged with that substitution; the *rule* was written about roles, and the
roles are now filled by the data instead of by recollection.

### 0.0.1 MACs are eFuse-burned. What is uncertain is boards, not addresses.

**The ESP32 base MAC is burned into eFuse and cannot change from a power
cycle, a re-flash, or being unplugged.** So the MAC→name mapping in
`pc/occ/__init__.py` — `a4:f0:0f:77:91:20 = B1`, `28:05:a5:2f:fa:48 = B2`,
`f4:2d:c9:70:72:30 = B3` — is **still valid and was never in question**. Every
number in this document is keyed to a MAC, and no number here depends on
anybody's recollection of which board is which.

**What is uncertain is only which *physical board on the bench* the operator
believes corresponds to each name.** That distinction matters directly for the
planned rotation experiment: a rotation is a mapping from *physical positions*
to *MACs*, and if the operator's position→name mental model is wrong, the
rotation will be recorded wrong even though every MAC in the CSV is correct.
**Before the rotation experiment, the position→MAC mapping needs to be
re-established from the data, not from memory** — the method in §7 (power one
board down, or move it, and watch which MAC's RSSI collapses) does exactly
that and takes one short capture per board.

A second, sharper consequence: **the repo's B1/B2/B3 labels have never been
tied to physical positions by anything but recollection.** Nothing in this
pass can say when the position→name mapping drifted, or whether it was ever
right. Documents that reason about *where* a beacon is — as opposed to which
MAC transmitted — inherit that uncertainty. This pass does not attempt to
audit them and does not claim any of them are wrong.

---

# PRE-REGISTRATION

*(Written and saved before any frame count, RSSI or slope was computed from
any file. Unedited below this line except for the §0.0 amendment above, which
is additive and is placed above rather than inside it. Where the frozen text
says "B1" as the treated unit, read "the treated unit"; §0.0 step 3 resolves
which MAC that is.)*

**What had been read at freeze time, and nothing else:** `CLAUDE.md`;
`pc/rff/dsp.py` in full; `docs/RIPPLE_TEST.md` in full (its §0 physics, §6
constraints and §5 outcome table are what motivated this pass);
`pc/exp_ripple_test.py` down to `_process()`; the beacon table in
`pc/occ/__init__.py`; the CSV header and first two data rows of
`data/raw/d0wd_20260823_141358.csv` and `data/raw/s3_20260823_141358.csv`;
`ls -l` on `data/raw/`; and the **first and last `pc_time_us` field** of each
of the six files named in §2, obtained by `sed -n 2p` and `tail -c`. No slope,
no per-beacon frame count, no RSSI distribution and no window statistic had
been computed from any file.

## 0. What was done to the hardware, as reported by the operator

The treated beacon was moved from its indoor position to a car park **roughly
100 ft away and three storeys down, outdoors**. **The other two beacons and
both receivers were not touched.** The capture was started **after** the move
was complete, so the whole file is one condition — there is no within-file
transition to find and none will be looked for.

This is the manipulation `docs/RIPPLE_TEST.md` §5 named as the required next
instrument: its own null was declared a null **only for delays large enough to
ripple the 16.25 MHz band** (τ ≳ 60 ns), and the outcome table says the
alternative instrument is "a wider band, or **a deliberate path-length
manipulation**". Every other pass in this repo has been observational.

### 0.1 The physics point that constrains the prediction — and its limit

The receiver **synchronises its FFT window to each packet**. Absolute
propagation delay is therefore removed by timing sync: moving a beacon ~30 m
does **not** inject ~100 ns of measurable delay into the phase ramp. There is
no "distance shows up as slope" prediction available here and none is being
made.

What does change is the **relative multipath structure** — which reflections
arrive, at what excess delay relative to the (re-synced) first arrival, and
with what amplitude. Indoors, the beacon sat in a room with a dense set of
short-excess reflections; outdoors beside a car and three storeys down, the
set is entirely different. `docs/RIPPLE_TEST.md` §0 establishes the
sensitivity: a **36 cm** change in the excess length of one dominant reflected
path moves the fitted slope by a full `BETWEEN_UNIT_SD`, because a single
delayed path contributes a **pure linear** ramp of `−2π·Δf·τ` rad/subcarrier
that RANSAC cannot reject.

**So the change in the relative multipath structure is real, but its magnitude
is not predictable from the distance moved.** The prediction below is
therefore **directional only**, and this document states explicitly, before the
result: **no magnitude was predicted.** A post-hoc statement that some observed
number "is about what you'd expect from a 30 m move" is not available to this
pass and will not be made.

### 0.2 Four variables changed at once — the result is asymmetric

The move confounds, irreducibly and by construction:

1. **distance and multipath structure** — the variable of interest;
2. **outdoor temperature on the crystal** — `docs/THERMAL_EVIDENCE.md`
   establishes crystal drift on this hardware is a thermal, minutes-scale
   process, and this file is a different thermal environment for 51 minutes;
3. **a car's worth of metal beside the antenna** — a near-field scatterer;
4. **roughly 20 dB less received signal** — three storeys of concrete.

Therefore:

- **A NULL IS STRONG.** If the treated beacon's slope distribution does not
  move despite four simultaneous large changes, that is substantial evidence
  the slope is a transmitter property and not a room property — much stronger
  than any observational null in this repo.
- **A POSITIVE IS AMBIGUOUS.** If it moves, this pass **cannot say which of
  the four did it**, and will not attribute the shift to geometry. Writing
  "the geometry changed the slope" would be failure mode **G** (assumed
  context stated as fact) on top of an uncontrolled design.

Both sentences are written here, before the result, so that neither outcome can
be re-narrated afterwards.

## 1. THE CONTROL IS THE WHOLE DESIGN

The two untouched beacons are measured by the same receivers, in the same
files, through the same code path, with the same screening. Their shift is the
**null band for everything that changed between the two captures that is not
the treated beacon's position** — receiver state, thermal drift of the
receivers, ambient channel occupancy, time of day.

Decision rule, frozen:

| observed | reading |
|---|---|
| **the treated beacon's slope distribution shifts and the two controls' do not** | the shift is attributable to **the move** — the whole intervention, not to geometry within it (§0.2) |
| **all three shift** | **something else changed between the two captures.** The treated beacon's number carries **no information about geometry** and will be reported as carrying none. |
| a control shifts and the treated beacon does not | the instrument is not measuring what this design assumes; reported as such, no treatment claim |
| nothing shifts | **null, and per §0.2 a strong one** |

`CLAUDE.md` failure mode **A** applies to the second row above: it is named as
**the more likely outcome** and burying it would be the worst available failure
of this pass. It gets the same prominence in the summary as any positive.

### 1.1 Every shift in `BETWEEN_UNIT_SD`

`σ ≡ BETWEEN_UNIT_SD = 0.00237 rad/sc` (`pc/exp_thermal_evidence.py:129`, from
`docs/LOT_HYPOTHESIS.md` §5). **Every** shift reported below — treated unit,
both controls, the temporal-block null band, the time-of-day control — is
divided by σ and quoted in those units, so it is directly comparable to every
other separation figure in the repo. Raw `rad/sc` is quoted alongside, never
instead.

### 1.2 The within-before null band — a second control, from the before file alone

The before capture is **6.70 h**; the after capture is **51.9 min**. Comparing
a 51.9-minute median against a 6.70-hour median would let ordinary slow drift
masquerade as an effect. So the before file is cut into **non-overlapping
3111 s blocks** (the after capture's exact duration), each block's median
window-slope computed, and the **full range of those block medians** reported
in σ, per beacon per receiver.

**Frozen threshold:** a beacon "shifted" only if `|Δ|` exceeds **both** 1.0 σ
**and** that beacon's own within-before block range on that receiver. A shift
smaller than the drift the before file already contains on its own is not a
shift, whatever its size in σ.

The **last 3111 s of the before file** is additionally reported as a
time-adjacent before-condition.

### 1.3 The time-of-day control — a third control, from a different day

The before capture runs **01:47–08:29 local**; the after capture runs
**14:13–15:05 local**. Time of day is confounded with the move. So a third
pair is analysed identically: **`data/raw/*_20260822_144424*`** — 32.4 min,
**14:44–15:16 local on the previous day**, i.e. the same clock hour as the
after capture with the manipulation absent.

**Frozen use:** if the treated beacon's before→after shift is reproduced in
magnitude and sign by before→TOD-control (where it did *not* move), **time of
day explains it and the move claim is dead.** This control is pre-committed
here so that it counts whichever way it falls; it is not a fallback to be
introduced only if the primary result is inconvenient. Caveat stated in
advance: it is a different day, so it is not a clean time-of-day isolate
either.

## 2. Files — identified by timestamp, not assumed

Identified by `ls -l data/raw/` and the first/last `pc_time_us` of each file.
`pc_time_us` is epoch microseconds; the filename stamps are local time and the
two agree to the second on every file below.

| role | files | first→last `pc_time_us` | local | duration |
|---|---|---|---|---|
| **AFTER** | `d0wd_20260823_141358.csv`, `s3_20260823_141358.csv` | 1787512438882281 → 1787515550187329 | 08-23 14:13:58→15:05:50 | **3111.3 s = 51.86 min** |
| **BEFORE** | `d0wd_20260823_014740.csv`, `s3_20260823_014740.csv` | 1787467661178922 → 1787491784301939 | 08-23 01:47:41→08:29:44 | **24123.1 s = 6.70 h** |
| **TOD CONTROL** | `d0wd_20260822_144424.csv`, `s3_20260822_144424.csv` | 1787427864814291 → 1787429809495553 | 08-22 14:44:24→15:16:49 | **1944.7 s = 32.4 min** |

The operator's "started at 14:13" and "about 51 minutes" match the after pair
to the second and to 0.9 min respectively. The before pair is the one
`docs/RIPPLE_TEST.md` §6 and `docs/COLOCATED_0823.md` also use, so its row
counts (3,344,351 d0wd / 4,330,849 s3) and screen counts (187 / 1) are
**independently predicted** by this pass and any disagreement is a bug in this
pass, reported as such.

**Both receivers are reported separately and are never pooled.** `d0wd` and
`s3` disagree with each other by up to **86 × σ** on ambient sources
(`docs/AMBIENT_SEPARATION.md` §5) and by **6.2 × σ** on the beacons
(`docs/DUAL_RX_2026-08-21.md`); pooling them would swamp any effect this pass
could see. A shift must appear on **both receivers with the same sign** to
count.

## 3. Method — every choice fixed here

**Replay.** Each file is read **from row 1** with a **fresh `FrameEstimator`
per (node, source-MAC) stream**, in file order, no window, filter or subsample
ahead of it. `FrameEstimator` owns a per-instance RNG (`dsp.py:118`) handed to
`ransac_line` every frame (`:132`), which draws two `rng.integers(..., size=64)`
per call (`:85-86`): the generator advances once per fitted frame, so a slope
depends on how many frames preceded it in that stream. The checkpoint pickles
estimator state **and** the exact byte offset, so an N-call run is
frame-for-frame what one uninterrupted pass would produce. `pc/rff/dsp.py` is
used **exactly as shipped and is not modified** (`docs/V2_SPEC.md` §5.5).

**CSV.** `csi_data` is a quoted comma-separated list nested inside the CSV.
Parsed with `csv.reader`. Never `line.split(",")`.

**Corrupt-row screen, before the estimator and before any delta arithmetic.**
Six-column field plausibility, identical to `docs/RIPPLE_TEST.md` §6 /
`docs/OVERNIGHT_2026-08-22.md` §1: `node_id` against the file's own mode,
`env_id == 0`, `channel` against the file's own mode, `csi_len ∈ {128,256,384}`,
`noise_floor ∈ [−110,−70]`, `rssi ∈ [−100,−10]`. Rows failing any test never
reach the estimator.

**The `0d:0a` framing screen (reported item 3).** `0d 0a` is CR/LF. A MAC
containing those bytes means **the framer lost sync and the address is a
framing artifact, not a device** — the operator saw `10:06:13:0d:0a:0b` live
on the d0wd. Every MAC whose text contains `0d:0a` is screened out and
**counted**, per file, and reported even if the count is zero. The weaker
screen — any MAC containing an `0d` or `0a` octet anywhere — is counted
separately and reported, but is **not** used to exclude, because `0a` and `0d`
are legal octets in a real address and excluding on them would silently drop
genuine devices. Both counts are reported; only the `0d:0a` **adjacency** is
treated as proof of a framing artifact.

**Gates.** The shipped ones and no others: `inlier_ratio ≥ 0.6`,
`resid_std ≤ 0.8` (`dsp.py:164`). Not tuned by this pass.

**Windows.** `W = 64` consecutive **accepted** frames from one (node, MAC)
stream — the same W as `docs/RIPPLE_TEST.md`, ≈1 s on a beacon. Window
statistic = **median slope over the 64 frames**. Windows spanning more than
**5.0 s** of `pc_time_us` are excluded from the primary and the excluded count
reported. **Robustness replicate at W = 256.** A sign flip between W=64 and
W=256 voids the claim.

**Central tendency:** median of the window-median slopes, per (receiver,
beacon, condition). **Δ = median(after) − median(before)**, reported in σ.

**Dispersion — reported alongside every shift, never omitted (item 2):**

- **between-window dispersion** = `1.4826 × MAD` of the window-median slopes;
- **within-window dispersion** = median over windows of the per-window
  `1.4826 × MAD` of the 64 frame slopes.

Both are reported for before and after, as a ratio after/before **and** in σ.
**Frozen reading:** if the treated beacon's slope moves *and* its dispersion
inflates, the low SNR of the outdoor link is doing part of the work and the
shift cannot be read as a clean relocation of a stable distribution. That
sentence is written before the result because it is the most likely way a
positive here would be overclaimed.

**No p-values.** n is in the millions of frames and the tens of thousands of
windows; everything would be "significant". Effect sizes in σ, and the
control, decide this.

## 4. Floors — checked and reported FIRST (item 1)

At ~20 dB less signal, the treated beacon may simply not deliver enough
admissible frames. **If it fails the floors, that is the headline and
everything else is moot** — and it will be reported that way rather than as a
shrunken but reportable effect.

Per (receiver, beacon, condition), reported before any slope: **raw rate**
(rows bearing that MAC ÷ file duration), **accepted rate** (frames passing
screen + `csi_to_complex` + RANSAC + both shipped gates ÷ duration),
**acceptance fraction**, **median and 10th-percentile RSSI**, median
`noise_floor`.

**Frame floor:** ≥ **640** accepted frames (≥ 10 windows at W=64), the same
floor as `docs/RIPPLE_TEST.md` §6.

**Window floor, frozen now:**

| windows at W=64 | status |
|---|---|
| ≥ 100 | primary comparison proceeds |
| 30–99 | comparison reported as **provisional**, dispersion untrustworthy |
| < 30 | **insufficient** — no shift is quoted for that stream, in either direction |

A stream below floor is reported as **below floor**, distinguishing (failure
mode **C**) *no admissible data exists* from *not asked for*: here it would be
the former, and the raw rate says whether the frames arrived at all or arrived
and were rejected.

## 5. Predictions — directional only, with confidence, frozen

**P1 — the treated beacon clears the floors on both receivers.** *Moderate
confidence.* **Sub-prediction:** its acceptance fraction after < before.

**P2 — its slope distribution shifts by more than its own within-before block
range and more than 1.0 σ.** *Low-to-moderate confidence.* **Direction not
predicted.** **Magnitude not predicted** — §0.1. Weakest-held prediction here.

**P3 — the two untouched beacons hold still: `|Δ| < 1.0 σ` and within their
own within-before block range, on both receivers.** *Moderate confidence, and
this is the prediction that decides whether P2 means anything.* The brief's
judgement that "all three shift" is the more likely outcome is recorded here as
a live and respected possibility; if it happens, §1's second row governs and
P2 is discarded regardless.

**P4 — the treated beacon's within-window dispersion inflates after the move.**
*Higher confidence than P2.*

**P5 — `0d:0a` MACs appear on the d0wd and not (or far less) on the s3.**
*Moderate confidence*, from the operator's live observation being on the d0wd
and from `docs/COLOCATED_0823.md` §2's 126-vs-1 asymmetry in corrupt rows.

**What would make this pass VOID:** `pc/rff/dsp.py` modified; any stream fed
anything other than its own file from row 1; any write to `data/raw/`; the
before pair's row counts disagreeing with `docs/COLOCATED_0823.md`; or the
W=256 replicate flipping the sign of a claimed shift.

## 6. Constraints obeyed

No sub-agents. No `git add` / commit / push / staging. `pc/rff/dsp.py` not
modified. `pc/capture.py:compute_cfo`, `pc/phase_skew.py`, `pc/fingerprint.py`
not used (`docs/CODE_INVENTORY.md` §4.2 C1/C2/C3). No serial port opened.
`data/raw/` opened `"rb"` and never written; three other tasks are reading
these files concurrently. One script. Host caps shell calls near 178 s, so the
script checkpoints and resumes; state lives outside the repo tree in
`$B1M_CACHE` and is deleted at the end.

---

# RESULTS

*(Everything above this rule, except the §0.0 amendment, was written and saved
before the first frame count or slope was computed. Nothing above it has been
edited since.)*

## 7. IDENTIFICATION — which beacon moved, from RSSI and frame rate only

Two independent derivations, deliberately not sharing code:

```
# (a) awk, streaming, on the fields that precede the quoted csi_data column
tail -n +2 data/raw/<file>.csv | cut -d, -f4,5,6,7,9 | awk -v CH=6 -f /tmp/rssi_id.awk
# (b) the full replay's own per-stream RSSI histograms
python3 pc/exp_b3_moved.py floors --tags b_d0wd,a_d0wd,t_d0wd,b_s3,a_s3,t_s3
```

They agree on every count below. (a) applies a four-column subset of the
screen (`channel`, `csi_len`, `noise_floor`, `rssi`, plus the `0d:0a`
exclusion) because `node_id` and `env_id` sit *after* the quoted `csi_data`
field and cannot be reached with `cut`; (b) applies the full six-column screen
via `csv.reader`. The residual difference is ≤ 1 row per file and moves no
median.

**Per-beacon median RSSI and raw frame rate, before vs after, both receivers.
All three beacons shown, so the identification is checkable and not asserted:**

| rx | beacon | RSSI p50 before | RSSI p50 after | **Δ dB** | raw fps before | raw fps after | fps ratio |
|---|---|---|---|---|---|---|---|
| d0wd | B1 `a4:f0:…:91:20` | −83 | −83 | **0** | 35.05 | 37.43 | 1.07 |
| d0wd | B2 `28:05:…:fa:48` | −79 | −73 | **+6** | 42.06 | 62.02 | 1.47 |
| d0wd | **B3 `f4:2d:…:72:30`** | −75 | **no frames at all** | **link gone** | 61.29 | **0.00** | **0.000** |
| s3 | B1 | −79 | −80 | **−1** | 52.25 | 49.84 | 0.95 |
| s3 | B2 | −75 | −71 | **+4** | 65.27 | 76.30 | 1.17 |
| s3 | **B3** | −78 | **−91** | **−13, and censored** | 61.60 | **0.0032** | **0.00005** |

**The identification is unambiguous: B3 is the beacon that moved.** B1's RSSI
is unchanged to within 1 dB on both receivers and its frame rate is unchanged;
B2's RSSI went *up*; B3's link collapsed to nothing on the d0wd and to ten
frames on the S3. Nothing else in the table is close.

**The −13 dB on the S3 is a floor, not the drop.** It is the median of the
**ten frames that got through**, which are by construction the top of the
fading distribution — everything below the receiver's detection threshold is
missing from the average. The true median path loss increase is larger than
13 dB and this pass cannot say how much larger. The d0wd, which heard B3 at
−75 dBm indoors, heard **zero** frames after, which is consistent with a drop
past its threshold. Reported as a **censored lower bound**, not as "13 dB".

### 7.1 Moved, or simply switched off? — the record was opened, not assumed

The operator had been unplugging boards. An unplugged board and a board three
storeys away both produce "no frames", so this needed checking rather than
assuming (failure mode **E**). The ten surviving S3 rows were opened:

```
LC_ALL=C grep -a ",f4:2d:c9:70:72:30," data/raw/s3_20260823_141358.csv
```

They are clean by every screen column (`node_id` 108 = the S3's mode,
`env_id` 0, `channel` 6, `csi_len` 256, `noise_floor` −95, `rssi` −89…−92) and
their arrival times, in seconds from the start of the 3111 s capture, are:

```
914.7  2073.8  2417.8  2455.7  2459.7  2654.0  2903.4  2925.0  3010.7  3047.3
```

**Spread across the last two-thirds of the capture, not clustered at the
start.** A board that was unplugged would stop and stay stopped; this one was
still transmitting at 3047 s, 8 seconds before the file ends. **B3 was powered
and transmitting throughout. It was far away.** The 915 s gap before the first
frame is unremarkable at this rate: at 10 frames per 3111 s, the chance of
seeing none in the first 915 s is about 5 %.

**One anomaly, flagged and not built on.** The `seq` column is monotonic in the
1.47M–1.69M range for eight of the ten rows but reads 378671 and 437850 for
rows 4 and 10. `seq` appears to be a host-side capture counter (the two
receivers' first rows carry 1386718 and 1386713 at the same `pc_time_us`), so
two out-of-range values suggest a second writer or a counter reset. Nothing in
this document depends on `seq`. Recorded as an open question.

### 7.2 Consequence for the frozen design

**Treated unit = B3. Controls = B1 and B2.** §1's table applies unchanged.

## 8. ITEM 1 — FLOORS. This is the headline, and B3 fails.

```
python3 pc/exp_b3_moved.py floors --tags b_d0wd,a_d0wd,t_d0wd,b_s3,a_s3,t_s3
```

| tag | beacon | raw | **accepted** | acc/raw | raw fps | acc fps | RSSI p50 | p10 | nf p50 | **win64** | span-dropped | **status** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| b_d0wd | B1 | 845583 | 784259 | 0.927 | 35.05 | 32.51 | −83 | −85 | −97 | 12247 | 3069 | ok |
| b_d0wd | B2 | 1014678 | 205169 | **0.202** | 42.06 | 8.51 | −79 | −80 | −97 | 2604 | 1343 | ok |
| b_d0wd | B3 | 1478531 | 1450598 | 0.981 | 61.29 | 60.13 | −75 | −75 | −97 | 22665 | 256 | ok |
| a_d0wd | B1 | 116464 | 107287 | 0.921 | 37.43 | 34.48 | −83 | −86 | −97 | 1671 | 417 | ok |
| a_d0wd | B2 | 192953 | 182016 | 0.943 | 62.02 | 58.50 | −73 | −75 | −97 | 2844 | 111 | ok |
| **a_d0wd** | **B3** | **0** | **0** | — | **0.00** | **0.00** | — | — | — | **0** | 0 | **ABSENT** |
| t_d0wd | B1 | 63449 | 58274 | 0.918 | 32.63 | 29.97 | −83 | −85 | −97 | 887 | 249 | ok |
| t_d0wd | B2 | 79021 | 69958 | 0.885 | 40.63 | 35.97 | −80 | −82 | −97 | 1089 | 269 | ok |
| t_d0wd | B3 | 100124 | 93877 | 0.938 | 51.49 | 48.27 | −76 | −82 | −97 | 1462 | 149 | ok |
| b_s3 | B1 | 1260401 | 1256700 | 0.997 | 52.25 | 52.10 | −79 | −80 | −95 | 19635 | 1786 | ok |
| b_s3 | B2 | 1574578 | 1555700 | 0.988 | 65.27 | 64.49 | −75 | −76 | −95 | 24291 | 100 | ok |
| b_s3 | B3 | 1485873 | 1470786 | 0.990 | 61.60 | 60.97 | −78 | −79 | −95 | 22978 | 353 | ok |
| a_s3 | B1 | 155080 | 154652 | 0.997 | 49.84 | 49.71 | −80 | −82 | −95 | 2416 | 303 | ok |
| a_s3 | B2 | 237402 | 236861 | 0.998 | 76.30 | 76.13 | −71 | −73 | −95 | 3700 | 6 | ok |
| **a_s3** | **B3** | **10** | **5** | 0.500 | **0.0032** | **0.0016** | −91 | −92 | −95 | **0** | 0 | **INSUFFICIENT** |
| t_s3 | B1 | 85191 | 84343 | 0.990 | 43.81 | 43.37 | −77 | −79 | −93 | 1317 | 277 | ok |
| t_s3 | B2 | 55126 | 9316 | **0.169** | 28.35 | 4.79 | −80 | −81 | −93 | **67** | 114 | **provisional** |
| t_s3 | B3 | 140168 | 139747 | 0.997 | 72.07 | 71.86 | −67 | −69 | −93 | 2183 | 9 | ok |

### 8.1 B3 did not clear the frame floor. It missed it by a factor of 128.

**The floor is 640 accepted frames. B3 delivered 0 on the d0wd and 5 on the
S3.** The window floor is 30 windows at W=64; B3 produced **zero windows on
both receivers**.

Per §4, distinguishing the three cases failure mode **C** requires: this is
**"no admissible data exists"**, not "not allowed to ask" and not "never
asked". Both files were read end to end, every row bearing B3's MAC was
counted before any screening (`grep -ac` gives 0 and 10, matching the screened
counts), and B3's stream was fed to a fresh estimator like every other. The
frames are not there because they did not arrive.

**Therefore: no slope, no dispersion and no shift can be computed for the
treated unit, and none is quoted below in either direction.** The primary
question this manipulation was designed to answer — does moving a transmitter
move its slope? — **is not answered by this capture.** Everything in §9 is
about the two beacons that did *not* move.

**P1 is FALSIFIED, decisively, and its sub-prediction is unevaluable** (an
acceptance fraction over 5 frames is not a number). **P2 and P4 are
unevaluable** — not null, not supported, simply without data. They are not
quietly dropped and they are not restated as nulls; a floor failure is not a
null, and calling it one would be failure mode **A**.

### 8.2 What the floor failure does tell us

It is a real measurement, just not of the slope. Moving one beacon ~30 m and
three storeys down took its link from **60–61 accepted frames/s on both
receivers** to **0.0016 frames/s on one and nothing on the other** — a
reduction of at least four and a half orders of magnitude in usable yield.
Any future design that assumes a beacon stays reachable after being moved out
of the building needs to budget for this: **the useful working range of this
bench, for RFF purposes, does not extend three storeys down.** A repeat needs
the beacon moved far enough to change geometry but near enough to stay above
the receiver's threshold — a same-floor move of a few metres, with the null
band from §1.2 as the yardstick, is the version of this experiment that could
actually return data.

## 9. ITEM 4 / THE CONTROL — did the two stationary beacons hold still? No.

```
python3 pc/exp_b3_moved.py report --before b_d0wd,b_s3 --after a_d0wd,a_s3 \
                                  --tod t_d0wd,t_s3 --rx d0wd,s3
python3 pc/exp_b3_moved.py report ... --robust     # the W=256 replicate
```

Receivers are reported separately throughout and are never pooled.

### 9.1 The within-before null band (§1.2), per beacon per receiver

Median window-slope of each non-overlapping 3111 s block of the 6.70 h before
file:

| rx | beacon | block medians (rad/sc) | **range** | **× σ** |
|---|---|---|---|---|
| d0wd | B1 | +0.013925 +0.013098 +0.016018 +0.013679 +0.019069 +0.017174 +0.017068 +0.018046 | 0.005972 | **2.52** |
| d0wd | B2 | +0.028475 +0.058391 +0.068612 +0.071111 *(4 qualifying blocks)* | 0.042635 | **17.99** |
| d0wd | B3 | +0.012124 +0.015509 +0.009681 +0.008964 +0.008985 +0.009063 +0.009824 +0.009258 | 0.006545 | 2.76 |
| s3 | B1 | +0.011352 +0.010095 +0.016326 +0.013316 +0.014621 +0.016545 +0.014593 +0.015023 | 0.006450 | **2.72** |
| s3 | B2 | +0.005809 +0.005606 +0.005319 +0.005134 +0.005114 +0.005584 +0.005720 +0.006107 | 0.000994 | **0.42** |
| s3 | B3 | +0.019567 +0.024837 +0.031208 +0.024746 +0.025117 +0.025375 +0.026233 +0.022812 | 0.011641 | 4.91 |

**This table is a result in its own right, independent of the manipulation.**
A beacon that is bolted to a wall and never touched wanders **2.5–4.9 σ across
one night** on four of the six (receiver, beacon) pairs — i.e. 2.5–4.9× the
between-unit standard deviation the repo uses to tell devices apart. Of the
other two, `s3`/B2 is genuinely tight (0.42 σ) and `d0wd`/B2 is degenerate
(17.99 σ, next paragraph). This is consistent with, and quantifies on a third file,
`docs/IDENTITY_STABILITY.md`'s within-session drift finding; it is not a new
claim and is not being fused with that document's numbers.

**Why d0wd/B2's band is 18 σ, opened rather than assumed** (failure mode
**E**): B2's link to the d0wd **died during the overnight capture**. Windows
per 3111 s block are `1424, 970, 15, 0, 3, 15, 60, 117` — it was heard
normally for the first ~1.7 h and then almost not at all. Its overnight
acceptance fraction of **0.202** is a consequence of that, not a property of
B2. **Any d0wd/B2 before→after comparison is therefore between a mostly-dead
link and a healthy one and is not a comparison at all.** It is reported for
completeness and carries no weight.

### 9.2 Slope distributions, W = 64

| rx | beacon | cond | n_win | median slope | betw MAD | with MAD | RSSI | resid | status |
|---|---|---|---|---|---|---|---|---|---|
| d0wd | B1 | before | 12247 | +0.015941 | 0.003647 | 0.010726 | −83.1 | 0.160 | ok |
| d0wd | B1 | after | 1671 | +0.015466 | 0.003246 | 0.010352 | −83.3 | 0.158 | ok |
| d0wd | B1 | tod | 887 | +0.013885 | 0.004464 | 0.010374 | −82.5 | 0.157 | ok |
| d0wd | B2 | before | 2604 | +0.045321 | 0.025829 | 0.009913 | −78.7 | 0.153 | ok *(see 9.1)* |
| d0wd | B2 | after | 2844 | +0.023982 | 0.007632 | 0.006111 | −73.3 | 0.140 | ok |
| d0wd | B2 | tod | 1089 | +0.027970 | 0.012207 | 0.008562 | −80.1 | 0.155 | ok |
| d0wd | B3 | before | 22665 | +0.009358 | 0.001249 | 0.003889 | −74.6 | 0.135 | ok |
| **d0wd** | **B3** | **after** | **0** | — | — | — | — | — | **ABSENT** |
| d0wd | B3 | tod | 1462 | +0.010876 | 0.004649 | 0.005663 | −76.3 | 0.133 | ok |
| s3 | B1 | before | 19635 | +0.014214 | 0.002601 | 0.005476 | −79.0 | 0.143 | ok |
| s3 | B1 | after | 2416 | +0.008599 | 0.001893 | 0.006582 | −80.3 | 0.143 | ok |
| s3 | B1 | tod | 1317 | +0.012943 | 0.003395 | 0.008045 | −77.2 | 0.146 | ok |
| s3 | B2 | before | 24291 | +0.005462 | 0.000777 | 0.003337 | −74.6 | 0.132 | ok |
| s3 | B2 | after | 3700 | +0.014851 | 0.002808 | 0.003035 | −70.8 | 0.140 | ok |
| s3 | B2 | tod | 67 | +0.009307 | 0.026426 | 0.011265 | −80.0 | 0.151 | provisional |
| s3 | B3 | before | 22978 | +0.025309 | 0.004082 | 0.006766 | −78.0 | 0.149 | ok |
| **s3** | **B3** | **after** | **0** | — | — | — | — | — | **ABSENT** |
| s3 | B3 | tod | 2183 | +0.009821 | 0.002563 | 0.003416 | −67.0 | 0.126 | ok |

### 9.3 Deltas in `BETWEEN_UNIT_SD`, with dispersion alongside (item 2)

| rx | beacon | comparison | Δ rad/sc | **× σ** | null band × σ | **exceeds both?** | betw-MAD ratio | with-MAD ratio |
|---|---|---|---|---|---|---|---|---|
| d0wd | B1 | before→after | −0.000475 | **−0.20** | 2.52 | no | 0.89× | 0.97× |
| d0wd | B1 | before→tod | −0.002056 | −0.87 | 2.52 | no | 1.22× | 0.97× |
| d0wd | B2 | before→after | −0.021339 | **−9.00** | 17.99 | no *(band is degenerate, §9.1)* | 0.30× | 0.62× |
| d0wd | B2 | before→tod | −0.017351 | −7.32 | 17.99 | no | 0.47× | 0.86× |
| d0wd | B3 | before→tod | +0.001517 | +0.64 | 2.76 | no | 3.72× | 1.46× |
| s3 | B1 | before→after | −0.005615 | **−2.37** | 2.72 | no *(just inside)* | 0.73× | 1.20× |
| s3 | B1 | before→tod | −0.001271 | −0.54 | 2.72 | no | 1.31× | 1.47× |
| **s3** | **B2** | **before→after** | **+0.009389** | **+3.96** | **0.42** | **YES — 9.4× its own band** | **3.62×** | 0.91× |
| s3 | B2 | before→tod | +0.003845 | +1.62 | 0.42 | yes, but *provisional* (67 win) | 34.03× | 3.38× |
| **s3** | **B3** | **before→tod** | **−0.015489** | **−6.54** | 4.91 | **YES** | 0.63× | 0.50× |

Time-adjacent before (last 3111 s of the before file), which removes the
duration mismatch entirely:

| rx | beacon | n_win | median | Δ to after × σ |
|---|---|---|---|---|
| d0wd | B1 | 1513 | +0.017513 | −0.86 |
| d0wd | B2 | 117 | +0.071111 | −19.89 *(degenerate, §9.1)* |
| s3 | B1 | 2459 | +0.014862 | **−2.64** |
| s3 | B2 | 3239 | +0.006000 | **+3.73** |

### 9.4 W = 256 robustness replicate

On the **S3 the replicate confirms every figure**, sign and magnitude:

| rx | beacon | comparison | W=64 × σ | **W=256 × σ** |
|---|---|---|---|---|
| s3 | B1 | before→after | −2.37 | **−2.27** |
| s3 | B2 | before→after | +3.96 | **+3.98** |
| s3 | B3 | before→tod | −6.54 | **−6.54** |

On the **d0wd the replicate is not informative for B1 and B2, and this is a
disagreement with the frozen §3, reported rather than smoothed over.** The
5.0 s window-span cap interacts with the d0wd's low accepted frame rates: 256
frames at B2's 8.51 accepted fps spans 30 s and is discarded, leaving 59
before-windows and 1 for B1. The d0wd W=256 B2 figure (+4.88 σ) has the
opposite sign to its W=64 figure (−9.00 σ). **Per §5 a sign flip voids a
claim — and there is no d0wd/B2 claim to void**, because §9.1 already
disqualified that comparison and §9.3 already records it as not exceeding its
band. The flip is reported as evidence that the d0wd/B2 comparison is
worthless, which is the same conclusion §9.1 reached by a different route.

### 9.5 Verdict on the control — §1's second row governs

**P3 is FALSIFIED.** The two beacons that did not move did not hold still:

- **B2 shifted +3.96 σ on the S3**, exceeding its own overnight null band
  (0.42 σ) by **9.4×**, confirmed at W=256 (+3.98 σ) and by the time-adjacent
  before (+3.73 σ). B2's **between-window dispersion inflated 3.62×**
  alongside the shift, while its within-window dispersion was flat (0.91×) —
  i.e. the individual windows are as tight as before, but they disagree with
  each other far more.
- **B1 shifted −2.37 σ on the S3** (−2.27 σ at W=256, −2.64 σ time-adjacent).
  That does **not** exceed B1's own 2.72 σ null band, so by the frozen rule B1
  did not "shift" — but its after-median (+0.008599) sits **below all eight**
  of its before-block medians (+0.0101…+0.0165), which the rule's range test
  is not designed to notice. Reported both ways.
- On the **d0wd**, B1 was flat (−0.20 σ) and B2's comparison is disqualified
  (§9.1). The d0wd therefore neither confirms nor contradicts the S3.

**The sign requirement of §2 — a shift must appear on both receivers — is not
met for either control**, because the d0wd cannot speak to B2 at all. What is
established is narrower and still decisive for this design: **on the receiver
where the comparison is clean, a stationary beacon moved several σ.** §1's
second row says what that means: **something other than the manipulation
changed between the two captures, and a treated-unit number from this pair
would not have been attributable to geometry even if B3 had delivered one.**

### 9.6 A fifth changed variable this pass found, and did not predict

§0.2 named four. There is a fifth, and it was **created by the manipulation
itself**:

**Removing B3 from the air changed the other beacons' reception.** With B3
transmitting at ~61 fps on both receivers, and then gone:

| | B2 RSSI d0wd | B2 RSSI s3 | B2 raw fps d0wd | B2 raw fps s3 | B2 acc/raw d0wd |
|---|---|---|---|---|---|
| before (B3 present, 61 fps) | −79 | −75 | 42.06 | 65.27 | 0.202 |
| after (B3 absent) | **−73** | **−71** | **62.02** | **76.30** | **0.943** |
| tod control (B3 present, 51–72 fps) | −80 | −80 | 40.63 | 28.35 | 0.885 |

B2 is louder and faster in exactly the file where B3 is off the air, and back
to its quiet values in the file where B3 is present. **A plausible mechanism is
that B3's traffic was contending for airtime and desensitising the receivers,
and its removal freed both** — the frame-rate rise follows straightforwardly
from CSMA, the 4–6 dB RSSI rise less so. **This is stated as a hypothesis
generated by three confounded files, not as a finding**, and it is not
diagnosed further here; a clean test is to power B3 down in place, on the
bench, and re-capture (failure mode **A**: this is not a number anyone should
quote yet).

Whether or not that mechanism is right, the design lesson stands and matters
for the rotation experiment: **you cannot move one beacon out of range without
changing the channel the other two are measured on.** The "controls" in a
single-beacon relocation are not untreated units. A rotation that keeps all
three transmitting, and only permutes positions, does not have this problem —
which is a point in its favour.

### 9.7 One more thing the TOD control revealed, which disqualifies it

**B3, stationary, shifted −6.54 σ between the 22 August afternoon and the
23 August overnight** on the S3 (2183 and 22978 windows, both well above
floor), exceeding its 4.91 σ band, with RSSI +11 dB different (−67 vs −78).
`docs/HANDOFF.md`-style bench stability cannot be assumed across those two
days, and in fact the operator's own account — that he was **unplugging boards
to identify them** — means boards may have been disturbed between them.

**So the §1.3 time-of-day control cannot do the job it was pre-registered
for.** It is reported in full above and then set aside: it is not a clean
time-of-day isolate, and this pass will not use it to argue either that time of
day does or does not explain the B2 shift. Stated as a limitation rather than
used selectively.

## 10. ITEM 3 — the `0d:0a` framing-artifact screen

```
python3 pc/exp_b3_moved.py floors --tags b_d0wd,a_d0wd,t_d0wd,b_s3,a_s3,t_s3
```

| tag | rows | **`0d:0a` adjacency (excluded)** | `0d`/`0a` octet anywhere (counted only) | bad_field | bad_parse | short_csi | ambient MACs |
|---|---|---|---|---|---|---|---|
| b_d0wd | 3,344,351 | **0** | 1563 | 187 | 0 | 0 | 37 |
| **a_d0wd** | 313,558 | **1** | 548 | 9 | 0 | 0 | 18 |
| t_d0wd | 242,733 | **0** | 80 | 15 | 0 | 0 | 12 |
| b_s3 | 4,330,849 | **0** | 1750 | 1 | 0 | 0 | 30 |
| a_s3 | 397,983 | **0** | 605 | 0 | 0 | 0 | 14 |
| t_s3 | 280,621 | **0** | 82 | 0 | 0 | 0 | 12 |

**Exactly one `0d:0a` address appears across all six files, and it is the one
the operator saw: `10:06:13:0d:0a:0b`, once, on the d0wd, in the 14:13
capture.** The operator's live observation is corroborated in the file. It was
screened out and never reached the estimator.

**P5 holds** in direction — the artifact is on the d0wd and not the S3 — but
on n = 1, which is far too thin to call the asymmetry confirmed. Reported as
"consistent with, not evidence for".

The weaker octet screen's 80–1750 rows per file are **not** framing artifacts
and were correctly not excluded: they are dominated by `1c:ce:51:f3:0d:fa`
(872/1005/76/79 rows) and `1e:ce:51:f3:0d:fa` (589/714/433/486), which are
genuine locally-administered ambient devices already known to
`docs/AMBIENT_SEPARATION.md`. Excluding on a lone `0d` or `0a` octet would
have silently deleted them. **`0d` next to `0a` is the signature; `0d` or
`0a` alone is not.**

## 11. What was run, and provenance

One script, `pc/exp_b3_moved.py`, from the repo root, `$B1M_CACHE=/tmp/b1moved`:

```
python3 pc/exp_b3_moved.py verify data/raw/d0wd_20260823_013537.csv --split-budget 1.2
python3 pc/exp_b3_moved.py run data/raw/d0wd_20260823_141358.csv --tag a_d0wd
python3 pc/exp_b3_moved.py run data/raw/s3_20260823_141358.csv   --tag a_s3
python3 pc/exp_b3_moved.py run data/raw/d0wd_20260823_014740.csv --tag b_d0wd   # x5
python3 pc/exp_b3_moved.py run data/raw/s3_20260823_014740.csv   --tag b_s3     # x6
python3 pc/exp_b3_moved.py run data/raw/d0wd_20260822_144424.csv --tag t_d0wd
python3 pc/exp_b3_moved.py run data/raw/s3_20260822_144424.csv   --tag t_s3
python3 pc/exp_b3_moved.py floors --tags b_d0wd,a_d0wd,t_d0wd,b_s3,a_s3,t_s3
python3 pc/exp_b3_moved.py report --before b_d0wd,b_s3 --after a_d0wd,a_s3 \
                                  --tod t_d0wd,t_s3 --rx d0wd,s3 [--robust]
```

**The script's name changed mid-pass, and nothing else did.** It was created
and run as `pc/exp_b1_moved.py`, then renamed to `pc/exp_b3_moved.py` after §7
identified the treated unit. **Byte-identical**: `md5sum` is
`16e54c161cf4a47785468f81bb748373` before and after the rename. Verified by
re-running the after-d0wd file from scratch under the new name into a separate
tag and comparing **every window record of every stream** against the original:
`rows 313558 vs 313558, streams 2 vs 2, differing-window-sets=0` — PASS.

**All six files were read end to end.** Final byte offsets equal the file sizes
exactly. **Independent confirmation of §2's frozen prediction:** the before
pair produced **3,344,351** (d0wd) and **4,330,849** (s3) rows with **187** and
**1** rows removed by the field screen — matching `docs/COLOCATED_0823.md` and
`docs/RIPPLE_TEST.md` §7 to the unit, on both counts, on both files. 0
unparseable rows and 0 short-CSI rows on every file.

**The checkpoint split was proved transparent, not asserted.** `verify` ran
`d0wd_20260823_013537.csv` as one uninterrupted pass and again as 6 resumed
parts, comparing every window record of every stream at both W=64 and W=256:
`rows 45012 vs 45012, streams 3 vs 3, differing-window-sets=0` — PASS. The
`docs/V2_SPEC.md` §5.5 replay-origin requirement therefore holds for the
5- and 6-part overnight runs.

**Integrity, checked before and after the pass:**

- `pc/rff/dsp.py` **not modified** — `md5 ebc56a2a82a3aaacf72cea71c6e27281`,
  mtime `2026-07-13 20:42:46.783015400 -0500`, identical before and after.
- All six raw CSVs **unchanged** — mtimes identical before and after
  (`2026-08-23 08:29:44`, `2026-08-23 15:05:50`, `2026-08-22 15:16:49`).
  Every file opened `"rb"`.
- **Nothing staged, committed or pushed.** `git diff --cached --name-only`
  empty before and after.
- No serial port opened. No sub-agents. `pc/capture.py:compute_cfo`,
  `pc/phase_skew.py`, `pc/fingerprint.py` not imported or used.
- All state in `/tmp/b1moved`, outside the repo tree, deleted at the end.

**Files this pass wrote in the repo:** this one, `pc/exp_b3_moved.py`, and the
redirect stub at `docs/B1_MOVED.md`. Two disclosed exceptions, both matching
what `docs/RIPPLE_TEST.md` §7 records for this mount: `docs/B1_MOVED.md` could
not be deleted (`rm` returns `Operation not permitted`) so it was overwritten
with a stub rather than removed; and `pc/__pycache__/` entries produced by the
verification helpers importing the module could not be deleted either. Both
are covered by `.gitignore`.

## 12. VERDICT

1. **The beacon that moved is B3 (`f4:2d:c9:70:72:30`), not B1.** Identified
   from RSSI and frame rate on both receivers, by two independent code paths,
   before any slope existed. B1's RSSI moved 0 and −1 dB; B2's went *up* 6 and
   4 dB; B3's link went to nothing on the d0wd and to ten frames at −91 dBm on
   the S3. **The MAC→name map in `pc/occ/__init__.py` was never in doubt** —
   MACs are eFuse-burned — **only the operator's position→board recollection
   was.** §0.0.1.

2. **B3 did not clear the floors, and this is the headline.** 0 accepted
   frames on the d0wd, 5 on the S3, against a floor of 640: short by a factor
   of 128. Zero windows on both receivers. **No slope, dispersion or shift
   exists for the treated unit, and none is quoted.** The manipulation's
   primary question is **not answered** by this capture. That is a floor
   failure, not a null, and it is not being written up as one.

3. **B3 was moved, not switched off.** The ten surviving frames are spread
   from 914.7 s to 3047.3 s of a 3111 s capture and are clean on every screen
   column. The record was opened rather than the absence assumed.

4. **The controls did not hold still. §1's second row governs.** B2, which
   never moved, shifted **+3.96 σ** on the S3 — **9.4× its own 0.42 σ
   overnight null band** — confirmed at W=256 (+3.98 σ) and by the
   time-adjacent before (+3.73 σ), with **between-window dispersion up 3.62×**
   while within-window dispersion stayed flat. B1 moved −2.37 σ on the S3,
   inside its own (much wider, 2.72 σ) band but below every one of its eight
   before-blocks. On the d0wd, B1 was flat and B2's comparison is disqualified
   because B2's link to that receiver died mid-overnight (windows per block
   `1424, 970, 15, 0, 3, 15, 60, 117`). **Even if B3 had delivered frames, its
   number would not have been attributable to geometry.**

5. **The four-variable ambiguity, stated rather than glossed — and it is now
   five.** Had B3 produced a shift, distance/multipath, outdoor temperature on
   the crystal, the car body beside the antenna, and ~20 dB of lost signal all
   changed at once and this pass could not have said which. §9.6 adds a fifth
   that the manipulation created rather than controlled: **taking B3 off the
   air changed how the receivers heard B2.** A null would have been strong; a
   positive would have been ambiguous; what actually happened is neither.

6. **A stationary beacon wanders 2.5–4.9 σ across a single night** on four of
   six (receiver, beacon) pairs (§9.1) — several times the between-unit
   standard deviation the repo uses to tell devices apart. Any future manipulation on this
   bench needs an effect larger than that to be visible at all, and this pass
   suggests the block-range null band as the yardstick to hold it to.

7. **`docs/RIPPLE_TEST.md` §5's requirement is still outstanding.** It asked
   for "a deliberate path-length manipulation" because its own instrument was
   blind below ~60 ns. This was that attempt, and it did not deliver the
   measurement — **not because the physics failed but because the beacon was
   moved out of radio range.** The experiment is still worth doing: it needs a
   **same-floor move of a few metres**, keeping all three beacons transmitting
   and above threshold, with the §9.1 null band as the significance yardstick.
   The planned rotation experiment is a better instrument than this one was,
   for the reason in §9.6 — but it requires the position→MAC mapping to be
   re-established from data first (§0.0.1).
