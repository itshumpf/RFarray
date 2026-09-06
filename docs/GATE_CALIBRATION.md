# GATE CALIBRATION — deriving the frame-admission thresholds from ground truth

**§1 and §2 of this file were written 2026-08-23 19:30 UTC, before any sweep
was run and before any real-data distribution was measured for this pass.**
The criterion in §2 is frozen. If the sweep says the criterion cannot be met
anywhere in the swept range, §5 reports that it cannot be met; the criterion
is not relaxed to manufacture a threshold. Where the temptation to relax it
arises it is recorded in §9 as a temptation rather than acted on.

Read-only on `data/raw/`. No serial port opened. **`pc/rff/dsp.py` is not
modified and no shipped default is changed anywhere** (`docs/V2_SPEC.md`
§5.5). Every loosened figure in this document is produced by passing
`--max-resid` / `--min-inlier` as arguments on a **parallel, explicitly
labelled branch**; the shipped-gate branch is run in the same pass, from the
same files, and reported beside it. Neither overwrites the other.
`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` are
not used (`docs/CODE_INVENTORY.md` §4.2 C1/C2/C3).

---

## 1. Why a calibration is needed, and what is actually being calibrated

### 1.1 The complaint

The pre-registered receiver-term test (`docs/RECEIVER_TERM_PREREG.md` §11)
found that of **29 sources heard by both receivers, 14 clear the census
floor and 6 clear the 20-admissible-frame floor**. One source produced
**7 admissible frames out of 872 clean ones — 99.2 % rejection**
(`docs/RECEIVER_TERM_PREREG.md`:577). `docs/IDENTITY_STABILITY.md` finds no
ambient device has ever cleared the 10-window floor in two sessions on any
receiver. The V2 readiness audit records that `min_inlier 0.6` "deletes
ambient sources entirely and inconsistently — the same device is accepted at
0.0 % on one receiver and 37.5–81 % on the other", and that `max_resid = 0.8`
rejects **zero of 6,386,119** fitted frames
(`docs/SEPARATION_SCALING.md`:631, `docs/V2_SPEC.md`:872).

### 1.2 What the two gates are

`pc/rff/dsp.py:164` — `WindowAggregator(window=64, min_inlier_ratio=0.6,
max_resid=0.8)`. Both are **per-frame** predicates applied at `:173-176`
before a frame may enter a window. They act on the two quality numbers
`ransac_line` returns at `:103`:

- `inlier_ratio = best_count / n` — the fraction of the 52 usable
  subcarriers within `inlier_thresh = 0.30` rad of the winning 2-point
  hypothesis (`dsp.py:94, 99`).
- `resid_std` — the standard deviation of the least-squares residual
  **computed on the inlier set only** (`dsp.py:100-103`).

### 1.3 A structural fact that bounds the max_resid half of this exercise

`resid_std` is computed over `y[inl]`, and membership in `inl` requires
residual `< inlier_thresh = 0.30` rad against the *hypothesis* line
(`dsp.py:99`). The least-squares refit then reduces that residual further.
So **`resid_std` is bounded above by roughly 0.30 by construction**, and any
`max_resid` above ~0.30 is a structural no-op — not an empirical accident.
That is why the shipped 0.8 rejected 0 of 6,386,119 frames and 0 of
8,274,369 in a second population (`docs/V2_SPEC.md`:1173), and why
`docs/UNWRAP_DEFECT.md` §7 rates `resid_std` "useless" as a quality signal.

**Consequence, stated in advance:** `max_resid` cannot be *loosened*. It is
already fully open. The only thing a sweep can find for it is whether
*tightening* it below 0.30 buys accuracy. The sweep therefore covers
(0, 0.30] plus the shipped 0.8 as a control, and the loosening question
reduces almost entirely to `min_inlier`. If that is what the sweep shows,
this document says so rather than reporting a loosened `max_resid` that does
nothing.

### 1.4 What "trustworthy" has to mean here

The quantity the analysis consumes is the **per-frame slope** — the SFO
proxy in rad/subcarrier. Ambient sources are frame-limited: they contribute
20 to 932 frames (`docs/AMBIENT_SEPARATION.md` §1), so many never form even
one 64-frame window and frame-level error is what actually reaches the
analysis. Window-median averaging therefore **cannot be assumed** to shrink
the error, and the criterion below is set at the frame level. This is also
the conservative direction: a frame-level criterion is stricter than a
window-level one whenever averaging does help.

---

## 2. THE CRITERION — frozen before the sweep

Let `σ = BETWEEN_UNIT_SD = 0.00237 rad/sc` (`pc/exp_thermal_evidence.py:129`,
via `docs/LOT_HYPOTHESIS.md` §5) — the standard deviation, over the three
known units, of their grand-mean SFO. It is the entire spread of the signal
this project is trying to measure.

A gate setting `g = (min_inlier, max_resid)` is **trustworthy** if, over
synthetic frames generated at a *known* slope under conditions matched to
the range ambient devices actually occupy, and considering **only the frames
`g` admits**:

> **C1.** median │slope_hat − slope_true│ ≤ **0.50 σ = 0.001185 rad/sc**
>
> **C2.** p90 │slope_hat − slope_true│ ≤ **1.00 σ = 0.00237 rad/sc**

The calibrated gate is the **loosest** setting on the swept grid that
satisfies C1 and C2 simultaneously.

### 2.1 Justification of the fraction 0.50 for C1

Identity claims in this project are made by **differencing** two SFO
estimates — the same device on two receivers, or two devices on one
receiver. Every headline in the week's documents is a Δ: the twin ΔSFO of
0.00080, the receiver-term Δ of 0.00147 to 0.03870, the ambient pairwise
separations. Two estimates each carrying independent error `e` produce a
difference carrying error `√2·e`.

At `e = 0.707 σ` the differencing error is exactly `1.00 σ` — the
measurement error on a Δ equals the entire between-unit spread, and the
instrument can manufacture a typical between-device difference out of
nothing, or erase a real one, with equal ease. That is the point at which
the measurement is self-defeating, and it is a property of the arithmetic,
not a taste.

**0.50 σ sits below that with ~30 % margin**, giving a differencing error of
`0.71 σ`. It is chosen to be the loosest value that still leaves the
instrument able to resolve a typical between-unit difference at better than
1:1 signal-to-error. A stricter 0.25 σ would be defensible and is reported
as a secondary column in §5 so a reader who wants it can adopt it; a looser
1.00 σ is not defensible, because at `e = σ` the differencing error is
`1.41 σ` and two typical units cannot be told apart by construction.

### 2.2 Justification of C2, the tail rider

A median-only criterion is blind to a bimodal error distribution, and the
documented failure mode of this estimator is **exactly bimodal**: `np.unwrap`
puts one subcarrier on the wrong 2π branch and the returned slope is off by
one whole turn over the lever arm, while the frame looks healthy
(`docs/UNWRAP_DEFECT.md`). `resid_std` does not flag it (worst turn-out
0.211 against `max_resid = 0.8`) and `inlier_ratio`'s sign is not stable
against it — on real d0wd frames turn-outs sit at 0.404 against 0.365 for
clean ones, so **tightening `min_inlier` enriches for them**
(`docs/UNWRAP_DEFECT.md` §7). A median could therefore sit comfortably
inside C1 while 20 % of admitted frames are wrong by ten times the signal.

C2 requires the 90th percentile of │error│ to stay inside **one whole
between-unit spread**: at most 10 % of admitted frames may be wrong by more
than the entire signal. This is deliberately a weak bound on a strong
failure — it does not certify the tail is clean, only that it is not
dominant.

### 2.3 The gain rule, also frozen

Loosening admits noisier fits, so a source that appears at a looser gate is
not automatically a gain. Frozen in advance:

> **C3.** A newly-admitted source counts as a **gain** only if the
> dispersion of its own slope estimates — IQR of its per-frame slopes, and
> of its window medians where it has ≥ 2 windows — is **below σ**.
>
> A source whose slope dispersion is **≥ σ** is reported as **"noise wearing
> a MAC"**: its own internal scatter covers the entire between-device
> spread, so it cannot be placed relative to any other device and its
> appearance in the census is not information. It is counted separately and
> never added to the gain total.

### 2.4 The swept grid, fixed in advance

- `min_inlier` ∈ {0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55,
  **0.60**, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90} (shipped value in bold)
- `max_resid` ∈ {0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, **0.80**}
- Synthetic conditions: per-subcarrier SNR and multipath severity chosen in
  §3 to bracket the range real ambient sources occupy, measured from real
  data *after* this section was written. The conditions are matched to the
  data; **the criterion is not.**

### 2.5 What would falsify the whole exercise

Stated now so it cannot be quietly avoided later:

1. If no setting on the grid meets C1 and C2, the answer is **"the data does
   not support looking at these devices"**, and this document says that
   rather than reporting the least-bad setting as a recommendation.
2. If the calibrated setting moves the three known beacons' SFO medians by
   more than **0.10 σ**, the setting is admitting material garbage and is
   rejected regardless of what C1/C2 say about synthetic frames — the
   beacons are the only sources with known ground truth in the real data,
   and `docs/AMBIENT_SEPARATION.md` §3.2 establishes they move by 0.004 σ
   across a 0.6→0.2 sweep, so any material movement is new and is a fault.
3. If the sources gained at the looser gate are predominantly MACs that fail
   the corrupt-row screen (§4), the gain is fabrication and is reported as
   fabrication.

---

*(§3 onward written after the above, in the order the work was done.
`docs/GATE_CALIBRATION.md` mtime after §1–§2 was written: 2026-08-23
14:29:47 −0500 = 19:29:47 UTC. The first sweep ran after that.)*

---

## 3. What was run

One new script, `pc/exp_gate_calibration.py`. Read-only on `data/raw/`; every
input opened `"rb"`. No serial port opened — **a capture was running on COM6
and COM12 throughout** and another task was reading the same tree, so
nothing was written anywhere near `data/raw/`. Nothing staged, committed or
pushed. `pc/rff/dsp.py` mtime is still **2026-07-13 20:42:46**, md5
`ebc56a2a82a3aaacf72cea71c6e27281`, and `git diff` over `pc/rff/dsp.py`,
`pc/rff_offline.py`, `pc/mac_census.py` and `pc/test_rff_synth.py` is empty.

```
python3 pc/exp_gate_calibration.py calib --frames 1500 --reps 2 \
        --rs-lo 0.07 --rs-hi 0.23 --ir-lo 0.30 --ir-hi 1.01
G=0.60/0.80,0.20/0.80,0.85/0.10,0.80/0.10
python3 pc/exp_gate_calibration.py scan data/raw/d0wd_20260823_014740.csv \
        --tag d0wd --part N --nparts 12 --total-rows 3344351 --gates $G
python3 pc/exp_gate_calibration.py scan data/raw/s3_20260823_014740.csv \
        --tag s3   --part N --nparts 16 --total-rows 4330849 --gates $G
python3 pc/exp_gate_calibration.py merge  --tag d0wd --nparts 12
python3 pc/exp_gate_calibration.py merge  --tag s3   --nparts 16
python3 pc/exp_gate_calibration.py report --tags d0wd,s3 --min-frames 20
```

The `0.85/0.10` gate is the §4.3 result, so the scan above is the *second*
pass over the two files; an earlier one used
`--gates 0.60/0.80,0.40/0.80,0.20/0.80,0.80/0.10,0.15/0.05` at
`--nparts 10`/`14`. Both are reported, and both reproduce every shared-gate
figure exactly.

**Data.** `data/raw/d0wd_20260823_014740.csv` and
`s3_20260823_014740.csv` only — the 6.70 h co-located overnight pair, both
receivers on the same wall ~10 in apart. **The receivers moved on
2026-08-22, and both of these files are entirely after the move**, so this
pass is internally controlled and nothing in it spans the move. No earlier
session is used, as input or as corroboration; where an earlier document is
cited it is cited for a figure that document itself printed, never fused
with one measured here.

**The part/merge split is exact, not an approximation.** The estimator state
is pickled forward, so an N-part run is frame-for-frame one uninterrupted
pass. Checked directly: the d0wd was run at `--nparts` 8, 10 and 12 and the
s3 at 12, 14 and 16; every split gives **3,344,351 / 4,330,849 rows, 190 / 1
corrupt rows, 166 / 34 distinct MACs** and identical per-source
admitted-frame counts at every shared gate.

### 3.1 Reproduction of the shipped branch, before anything is loosened

The shipped-gate column of this pass must reproduce documents written by
other scripts, or nothing else in it means anything.

| quantity | `docs/RECEIVER_TERM_PREREG.md` | this pass |
|---|---|---|
| d0wd data rows | 3,344,351 (§0) | **3,344,351** |
| s3 data rows | 4,330,849 (§0) | **4,330,849** |
| B1 `a4:f0:0f:77:91:20` admitted frames, d0wd / s3 | 784,198 / 1,256,700 (:631) | **784,198 / 1,256,700** |
| B1 SFO, d0wd / s3 | +0.01551 / +0.01404 (:631) | **+0.01551 / +0.01404** |
| `62:45:b4:f0:e1:97` admitted, d0wd / s3 | 689 / 2,693 (:634) | **689 / 2,693** |
| `1c:ce:51:f3:0d:fa` clean frames, d0wd / s3 | 872 / 1,005 (:577) | **872 / 1,005** |
| … of which admissible at the shipped gate | 7 / 2 (:577) | **7 / 2** |
| sources heard by both receivers | 29 (§11) | **29** |
| … clearing the 20-admissible floor on both | 6 (§11) | **6** |

Every one to the printed digit, from an independently written script. The
99.2 % rejection figure in the brief is this row: 872 clean frames, 7
admissible, **99.20 % rejected**.

### 3.2 The corrupt-row screen, run first

Two independent routes (`docs/OVERNIGHT_2026-08-22.md` §1): field
plausibility on six columns, and a width-9 circular median filter on
`dropped`.

| node | rows | unparseable | field-screen rejects | median-filter rejects | union | ppm | distinct MACs | **MACs existing only on rejected rows** | real MACs |
|---|---|---|---|---|---|---|---|---|---|
| d0wd | 3,344,351 | 0 | 187 | 186 | **190** | 56.81 | 166 | **126** | **40** |
| s3 | 4,330,849 | 0 | 1 | 1 | **1** | 0.23 | 34 | **1** | **33** |

**126 of the d0wd's 166 addresses are fabrications** — reproducing the
figure in `CLAUDE.md` and `docs/COLOCATED_0823.md` exactly. Every census
number in §5 onward is over the 40 and 33 screened MACs only. Had the screen
been skipped, loosening the gate would have appeared to "discover" up to 126
new devices on the d0wd alone, every one of them a parse artefact. This
mattered more than anywhere: the loosened gate's whole selling point is that
it admits weak, short-lived sources, and a corrupt row is exactly a weak,
short-lived source.

### 3.3 The operating point real sources occupy (measured after §2 was frozen)

Per-frame `inlier_ratio` and `resid_std` over every fitted frame of every
screened source, §5 of the report:

| node | source | kind | fitted frames | `ir` p10 | p50 | p90 | `rs` p50 | `rs` max |
|---|---|---|---|---|---|---|---|---|
| d0wd | `f4:2d:c9:70:72:30` B3 | beacon | 1,478,508 | 0.865 | 0.965 | 0.985 | 0.135 | 0.210 |
| d0wd | `28:05:a5:2f:fa:48` B2 | beacon | 1,014,661 | 0.445 | **0.515** | 0.715 | 0.155 | 0.230 |
| d0wd | `a4:f0:0f:77:91:20` B1 | beacon | 845,565 | 0.635 | 0.755 | 0.865 | 0.155 | 0.220 |
| d0wd | `62:45:b4:f0:e1:97` | private | 691 | 0.985 | 0.985 | 1.005 | 0.075 | 0.110 |
| d0wd | `7e:ed:82:d6:23:e8` | private | 1,223 | 0.865 | 0.985 | 0.985 | 0.095 | 0.190 |
| d0wd | `1c:ce:51:f3:0d:fa` | real-OUI | 872 | 0.365 | 0.405 | 0.465 | 0.165 | 0.210 |
| d0wd | `1e:ce:51:f3:0d:fa` | private | 589 | 0.345 | 0.425 | 0.505 | 0.165 | 0.210 |
| s3 | `28:05:a5:2f:fa:48` B2 | beacon | 1,574,576 | 0.905 | 0.965 | 1.005 | 0.135 | 0.220 |
| s3 | `1c:ce:51:f3:0d:fa` | real-OUI | 1,005 | 0.325 | 0.345 | 0.405 | 0.165 | 0.210 |

(full table in the report; 18 d0wd and 14 s3 sources with ≥ 20 fitted frames.)

**Two facts fix the sweep.**

1. **`resid_std` never leaves the band 0.07–0.23 anywhere in 7.67 M frames.**
   The median for every real source is between 0.075 and 0.165; the largest
   value seen on any source is 0.230. This is §1.3's structural bound
   showing up in the data: the shipped `max_resid = 0.8` is nowhere near the
   population, which is why it has rejected 0 of 6,386,119 and 0 of
   8,274,369 fitted frames in two prior passes.
2. **`inlier_ratio` medians run 0.345 to 1.005**, and the shipped 0.6 cuts
   straight through the middle of that range — including through a *beacon*:
   d0wd B2's median is **0.515**, the only beacon below the gate. That fact
   is what §7 turns on.

The real operating box is therefore `inlier_ratio ∈ [0.30, 1.01]`,
`resid_std ∈ [0.07, 0.23]`. §4 restricts the synthetic pool to it.

---

## 4. The synthetic sweep

Ground truth from `pc/test_rff_synth.py`'s generator, imported rather than
re-implemented so the frame layout cannot drift. Its own checks were re-run
this session: phase round-trip max │err│ **0.01495 rad**, and noiseless SFO
recovery worst median error **2.440e-05 rad/sc = 0.010 × σ** over injected
slopes from 0 to 0.2. The instrument is trustworthy when the channel is
clean; the question is what happens when it is not.

True slope +0.00237 rad/sc, 20 condition families × 1,500 frames × 2 seeds,
each stream replayed from its start with a fresh `FrameEstimator`; 59,567
frames fitted.

**Seeds are `zlib.crc32`, not `hash()`.** The first draft of this sweep
seeded from `hash((label, rep))`, and Python salts `str` hashing per process
(`PYTHONHASHSEED`), so two runs of the same command disagreed in the fourth
significant figure and — at one grid point — in the pass/fail verdict.
That is Rule A: a number must be re-derivable *now*, by a command that can
be named. Fixed and checked: two consecutive runs of the command in §3 are
**byte-identical**. Every figure below is from that command.

### 4.1 `max_resid` is bounded, exactly as §1.3 predicted

Largest `resid_std` produced anywhere in 59,567 synthetic frames: **0.215**.
Largest seen on real data across 7.67 M frames: **0.230**. So every grid
value at or above 0.30 — including the shipped 0.8 — is a **no-op by
construction, not by luck**. `max_resid` cannot be loosened. It is already
fully open.

### 4.2 `inlier_ratio` does not predict slope error

Pooled over all 20 conditions, median │err│ / σ by `inlier_ratio` bin:

| bin | n | med │err│ / σ | p90 / σ |
|---|---|---|---|
| [0.30,0.35) | 708 | 5.17 | 14.65 |
| [0.40,0.45) | 3,191 | 4.20 | 12.93 |
| [0.50,0.55) | 2,200 | 5.99 | 20.74 |
| [0.55,0.60) | 2,176 | **7.59** | 21.24 |
| [0.60,0.65) | 1,645 | 6.58 | 20.44 |
| [0.70,0.75) | 2,996 | 4.17 | 18.24 |
| [0.80,0.85) | 5,184 | 1.73 | 16.80 |
| [0.90,0.95) | 5,087 | 1.16 | 15.69 |
| [0.95,1.00) | 21,197 | 0.32 | 1.84 |

**The relation is not monotone.** The [0.55,0.60) bin is worse than
[0.30,0.35) and than [0.40,0.45). The per-condition breakdown shows why: the
error is set by the *channel*, not by the gate statistic, and the pooled
column is the mixture weights talking. Median │err│ / σ per (condition, bin),
frame counts in parentheses:

| condition | [0.30,0.45) | [0.45,0.60) | [0.60,0.75) | [0.75,0.90) | [0.90,1.00) |
|---|---|---|---|---|---|
| clean 20 dB | – | – | – | – | **0.18** (3000) |
| clean 12 dB | – | – | – | 0.65 (697) | 0.54 (2303) |
| clean 4 dB | 3.29 (284) | 2.33 (2335) | 1.78 (351) | – | – |
| mp ρ.3 τ.010 20 dB | – | – | – | 3.78 (604) | 2.20 (2396) |
| mp ρ.7 τ.020 20 dB | – | 13.79 (830) | 15.85 (750) | 16.13 (924) | **15.47** (480) |
| mp ρ.9 τ.020 15 dB | 23.31 (109) | 21.75 (780) | 20.98 (744) | 20.91 (1004) | **20.82** (363) |

Under two-ray multipath the estimator is wrong by 15–21 σ **at every inlier
stratum including [0.90,1.00)**. A frame at `inlier_ratio` 0.95 under ρ = 0.9
is confidently, quietly wrong by twenty times the entire between-device
spread. This is `pc/test_rff_synth.py` test 5(d) — RANSAC locks onto one
locally-straight arc of the channel ripple and inherits its tilt — measured
across the whole gate range instead of at one point.

### 4.3 The frozen grid inside the real operating box

Restricting the synthetic pool to §3.3's box — 54,337 of 59,567 frames,
**91.2 %**, land in it — and applying C1 and C2 unchanged:

| min_inlier | max_resid | admit % | med / σ | p90 / σ | C1 | C2 |
|---|---|---|---|---|---|---|
| 0.20 | 0.80 | 99.89 | 1.705 | 16.360 | FAIL | FAIL |
| 0.40 | 0.80 | 96.16 | 1.629 | 16.393 | FAIL | FAIL |
| **0.60** | **0.80** *(shipped)* | 79.57 | **1.253** | **15.918** | FAIL | FAIL |
| 0.75 | 0.20 | 64.43 | 0.908 | 14.510 | FAIL | FAIL |
| 0.80 | 0.15 | 43.83 | 0.636 | 4.582 | FAIL | FAIL |
| 0.80 | 0.10 | 9.51 | 0.250 | **1.157** | ok | **FAIL** |
| **0.85** | **0.10** | 9.19 | **0.239** | **0.736** | **ok** | **ok** |
| 0.90 | 0.10 | 8.93 | 0.231 | 0.637 | ok | ok |

**Exactly two settings on the frozen grid meet C1 and C2 inside the real
operating box, and both are TIGHTER than shipped on both axes.** The loosest
is:

> ### min_inlier = 0.85, max_resid = 0.10

It also meets the stricter 0.25 σ secondary column. Note `0.80/0.10`, one
grid step looser: it passes C1 at 0.250 σ and **fails C2 at 1.157 σ**. That
is the C2 rider from §2.2 doing exactly the job it was frozen for — the
median says the setting is fine and the tail says it is not. (In the
first, non-reproducible draft of this sweep `0.80/0.10` passed C2 at
0.943 σ. It is the one verdict the `hash()` seeding flipped, and the reason
§4's determinism note exists.)

The shipped gate admits frames whose median error is **1.25 σ** and whose p90
is **15.9 σ** — at the shipped setting more than half of admitted frames are
already wrong by more than half the between-device spread, and a tenth are
wrong by sixteen times it. Loosening to 0.20/0.80 moves the median to
1.71 σ.

### 4.4 Why the criterion is met, and what that is worth

Per condition, inside the box:

| condition | n in box | `ir` med | `rs` med | med / σ | p90 / σ | C1 |
|---|---|---|---|---|---|---|
| clean 20 dB | 1,372 | 1.000 | 0.075 | 0.18 | 0.45 | ok |
| clean 18 dB | 2,935 | 1.000 | 0.088 | 0.23 | 0.56 | ok |
| clean 16 dB | 3,000 | 1.000 | 0.109 | 0.30 | 0.72 | ok |
| clean 14 dB | 3,000 | 0.981 | 0.129 | 0.40 | 0.97 | ok |
| clean 12 dB | 3,000 | 0.923 | 0.145 | 0.55 | 1.39 | FAIL |
| clean 10 dB | 3,000 | 0.846 | 0.155 | 0.86 | 2.10 | FAIL |
| **mp ρ.15 τ.010 16 dB** | 3,000 | **0.981** | **0.125** | **1.21** | 2.07 | **FAIL** |
| mp ρ.15 τ.010 10 dB | 3,000 | 0.808 | 0.157 | 1.30 | 3.15 | FAIL |
| mp ρ.5 τ.005 16 dB | 3,000 | 0.962 | 0.137 | 1.93 | 4.08 | FAIL |
| mp ρ.5 τ.015 16 dB | 3,000 | 0.692 | 0.156 | 9.27 | 14.22 | FAIL |
| mp ρ.7 τ.020 10 dB | 3,000 | 0.635 | 0.146 | 16.52 | 19.85 | FAIL |
| mp ρ.9 τ.020 15 dB | 2,997 | 0.712 | 0.116 | 21.06 | 23.08 | FAIL |

**C1 is met by clean AWGN at ≥ 14 dB and by nothing else.** Every multipath
family fails, and the mild one is the point: `mp ρ.15 τ.010 16 dB` has
`ir` 0.981 and `rs` 0.125 — statistically indistinguishable from `clean
14 dB` at `ir` 0.981, `rs` 0.129 — and its error is **1.21 σ against 0.40 σ,
three times larger**. The two gate statistics cannot tell those two frames
apart.

So `min_inlier 0.85 / max_resid 0.10` does not work by identifying good
fits. **It works by selecting for high SNR**, and in a room with any
multipath at all it admits biased frames it cannot see. Its number is
defensible as *the place the criterion stops being met on this grid*; it is
not defensible as a gate that certifies a frame.

This is the same conclusion `docs/UNWRAP_DEFECT.md` §7 reached for the
one-turn defect by a different route — `resid_std` "useless", `inlier_ratio`
"useless, and worse than useless" — arrived at here for channel bias, and
now with a number attached.

---

## 5. The census, re-run at every gate as a parallel branch

Sources = screened MACs with ≥ 20 **admitted** frames on that node
(`docs/RECEIVER_TERM_PREREG.md` §2.3's floor, not the raw-frame floor
`pc/mac_census.py --min-frames 20` applies).

| node | gate (`min_inlier`/`max_resid`) | sources ≥ 20 | admitted frames | windows (w = 64) |
|---|---|---|---|---|
| d0wd | **0.60 / 0.80 — shipped** | **11** | 2,442,799 | 38,162 |
| d0wd | 0.20 / 0.80 — loosened | 18 | 3,344,104 | 52,243 |
| d0wd | **0.85 / 0.10 — calibrated** | **3** | 6,165 | 95 |
| d0wd | 0.80 / 0.10 | 3 | 6,188 | 95 |
| s3 | **0.60 / 0.80 — shipped** | **8** | 4,290,334 | 67,032 |
| s3 | 0.20 / 0.80 — loosened | 14 | 4,330,837 | 67,661 |
| s3 | **0.85 / 0.10 — calibrated** | **5** | 7,947 | 122 |
| s3 | 0.80 / 0.10 | 5 | 8,288 | 127 |

An earlier invocation of the same script with
`--gates 0.60/0.80,0.40/0.80,0.20/0.80,0.80/0.10,0.15/0.05` additionally
measured the intermediate and extreme settings: **0.40/0.80** gives d0wd 18
sources / 3,330,195 frames and s3 12 / 4,326,237; **0.15/0.05** gives d0wd 1
source / 269 frames and s3 3 / 2,163. That invocation reproduced every
shared-gate figure in this table exactly, as did runs at `--nparts` 8, 10 and
12 on the d0wd and 12, 14 and 16 on the s3.

Sources heard by **both** receivers at ≥ 20 admitted frames:

| gate | n on both |
|---|---|
| **0.60 / 0.80 — shipped** | **6** *(reproduces `docs/RECEIVER_TERM_PREREG.md` §11)* |
| 0.40 / 0.80 | 12 |
| **0.20 / 0.80 — loosened** | **14** |
| 0.85 / 0.10 — calibrated | 3 |
| 0.15 / 0.05 | 0 |

**The gain the brief predicted is real and large.** Loosening `min_inlier`
to 0.20 takes the both-receiver population from **6 to 14**, d0wd from 11 to
18, s3 from 8 to 14. Nothing is lost. The frames gained per source are
dramatic: `1c:ce:51:f3:0d:fa` goes from 7 admitted frames to 872 on the
d0wd (**124 ×**) and 2 to 1,005 on the s3 (**502 ×**); `1e:ce:51:f3:0d:fa`
goes from 0 to 589 and 5 to 714.

**The calibrated gate does the opposite.** At 0.85/0.10 the d0wd keeps 3
sources of 11 and the s3 5 of 8; the both-receiver population falls from 6
to 3. It admits 6,165 of 3.34 M frames on the d0wd (**0.18 %**) and 7,947 of
4.33 M on the s3 (0.18 %). The three it keeps on the d0wd are B3 and the two
strongest ambient sources in the room, `62:45:b4:f0:e1:97` and
`7e:ed:82:d6:23:e8` — precisely the two whose `resid_std` medians (0.075 and
0.095) are the only ones in the whole population below 0.10. That is §4.4's
"it selects for high SNR" showing up on real data.

---

## 6. Estimate quality of what was gained — every newly-admitted source

C3, frozen in §2.3: a source counts as a gain only if the IQR of its own
per-frame slope estimates is **below σ = 0.00237**. All 7.67 M frames of each
source enter the dispersion (a sparse slope histogram at 1e-5 resolution,
not a first-N reservoir, because different gates admit frames from different
stretches of the session and a reservoir would confound gate with time).

**d0wd, shipped 0.60/0.80 → 0.20/0.80:**

| mac | kind | clean | adm @ ship | adm @ 0.20 | med SFO | slope IQR | IQR / σ | verdict |
|---|---|---|---|---|---|---|---|---|
| `1c:ce:51:f3:0d:fa` | real-OUI | 872 | 7 | 872 | −0.11205 | 0.04257 | **17.96** | noise wearing a MAC |
| `1e:ce:51:f3:0d:fa` | private | 589 | 0 | 589 | −0.10821 | 0.04863 | **20.52** | noise wearing a MAC |
| `64:fa:2b:6d:05:3b` | real-OUI | 32 | 4 | 32 | +0.01509 | 0.03968 | **16.74** | noise wearing a MAC |
| `6e:0a:30:1f:ed:21` | private | 22 | 13 | 22 | +0.01208 | 0.02285 | **9.64** | noise wearing a MAC |
| `6e:34:6f:7b:3f:81` | private | 46 | 18 | 46 | −0.04151 | 0.08637 | **36.44** | noise wearing a MAC |
| `ba:80:d5:0c:18:87` | private | 229 | 6 | 229 | +0.04545 | 0.03045 | **12.85** | noise wearing a MAC |
| `ee:a0:3d:e2:e5:a0` | private | 71 | 3 | 70 | +0.06230 | 0.14483 | **61.11** | noise wearing a MAC |

**s3, shipped 0.60/0.80 → 0.20/0.80:**

| mac | kind | clean | adm @ ship | adm @ 0.20 | med SFO | slope IQR | IQR / σ | verdict |
|---|---|---|---|---|---|---|---|---|
| `1c:ce:51:f3:0d:fa` | real-OUI | 1,005 | 2 | 1,005 | −0.14731 | 0.03898 | **16.45** | noise wearing a MAC |
| `1e:ce:51:f3:0d:fa` | private | 714 | 5 | 714 | −0.14270 | 0.04356 | **18.38** | noise wearing a MAC |
| `7e:f2:52:b7:1e:1f` | private | 26 | 0 | 26 | −0.13695 | 0.04479 | **18.90** | noise wearing a MAC |
| `be:eb:63:2a:08:56` | private | 23 | 0 | 23 | −0.11359 | 0.15293 | **64.53** | noise wearing a MAC |
| `d2:eb:b6:ca:31:24` | private | 32 | 10 | 32 | −0.05073 | 0.02524 | **10.65** | noise wearing a MAC |
| `ee:a0:3d:e2:e5:a0` | private | 40 | 11 | 40 | −0.00816 | 0.08446 | **35.64** | noise wearing a MAC |

> **13 sources gained across the two receivers. Zero of them are gains.**
> Not one has an internal slope dispersion below the entire between-device
> spread. The *smallest* dispersion among them is **9.64 σ**; the largest is
> **64.53 σ**. Each of these devices scatters, by itself, across ten to
> sixty-five times the range that separates one ESP32 from another.

The same table at `0.40/0.80`, from the earlier invocation, gives the same
verdict on 7 sources (d0wd) and 4 (s3) — **0 gains**, IQR/σ from 7.55 to
60.88 — so this is not an artefact of going all the way to
0.20. And `1c:ce` / `1e:ce` are worth a note: they are the pair
`docs/AMBIENT_SEPARATION.md` §3.2 already found moving 6.4 σ when the gate
went 0.6 → 0.4. That movement is now explained. Their estimates were never
converging on a value; the gate was selecting which part of a 17–20 σ-wide
cloud got averaged.

---

## 7. Do the beacons move? — falsifier 2 fires, on one receiver

Per §2.5(2), set in advance: any beacon median moving more than **0.10 σ**
rejects the setting.

Beacon median SFO (rad/sc) at each gate:

| node | beacon | 0.60/0.80 *(shipped)* | 0.20/0.80 *(loosened)* | 0.85/0.10 *(calibrated)* | 0.80/0.10 |
|---|---|---|---|---|---|
| d0wd | B1 `a4:f0:0f:77:91:20` | +0.01551 | +0.01524 | +0.01595 | +0.01595 |
| d0wd | B2 `28:05:a5:2f:fa:48` | **+0.04416** | **+0.03697** | +0.02555 | +0.02655 |
| d0wd | B3 `f4:2d:c9:70:72:30` | +0.00988 | +0.00981 | +0.00407 | +0.00408 |
| s3 | B1 | +0.01404 | +0.01405 | +0.00711 | +0.00001 |
| s3 | B2 | +0.00558 | +0.00559 | +0.00566 | +0.00564 |
| s3 | B3 | +0.02526 | +0.02531 | +0.00827 | +0.00815 |

Largest movement across all four gates: **0.01861 rad/sc = 7.85 σ** (d0wd
B2). The calibrated gate is as guilty as the loosened one — d0wd B3 moves
from +0.00988 to +0.00407 and s3 B3 from +0.02526 to +0.00827.

**Loosening branch only** (0.60 → 0.20, i.e. the question actually asked;
the intermediate 0.40/0.80 column from the earlier invocation reads +0.01526
/ +0.03712 / +0.00981 / +0.01405 / +0.00559 / +0.02531 and does not change
any figure below):

| node | beacon | move (rad/sc) | × σ | verdict |
|---|---|---|---|---|
| d0wd | B1 | 0.00027 | 0.114 | moves |
| d0wd | **B2** | **0.00719** | **3.034** | **moves** |
| d0wd | B3 | 0.00007 | 0.030 | ok |
| s3 | B1 | 0.00001 | 0.004 | ok |
| s3 | B2 | 0.00001 | 0.004 | ok |
| s3 | B3 | 0.00005 | 0.021 | ok |

**On the s3 the beacons do not move** — largest 0.021 σ, reproducing
`docs/AMBIENT_SEPARATION.md` §3.2's "the beacons do not move … largest
change 0.004 × `BETWEEN_UNIT_SD`" on an independent capture. That is the good
case, and it is exactly half the answer.

**On the d0wd, B2 moves 3.03 σ**, and B1 moves 0.114 σ, past the
pre-registered line. **Falsifier 2 fires.** The mechanism is visible in
§3.3: d0wd/B2's `inlier_ratio` median is **0.515**, the only beacon anywhere
below the shipped gate. At 0.60 only its best ~20 % of frames survive; at
0.40 the bulk enters and drags the median by three times the entire
between-device spread. It is the `docs/AMBIENT_SEPARATION.md` §3.3 stratum
bias — [0.5,0.6) frames carrying 2.5–3.8 σ of offset — now measured on a
*beacon of known position under co-location*, where it cannot be blamed on
the source being unknown.

That is the load-bearing result. **The population loosening is meant to
rescue is precisely the population on which loosening is demonstrably
biased.** A marginal cell is marginal because its frames are in the
low-inlier strata, and those strata carry multiple σ of bias. B2 on the d0wd
is the control that proves it, because for B2 we can compare against the same
transmitter measured through a receiver where it is *not* marginal: the s3
reads B2 at +0.00558 and does not move at all.

The calibrated 0.85/0.10 gate fails the same falsifier from the other
direction — d0wd/B3 moves 2.45 σ, s3/B3 7.17 σ, s3/B1 2.92 σ, on 167–272
surviving frames. `0.15/0.05`, from the earlier invocation, is worse still:
269 frames on the d0wd and every beacon median at ±0.00001, i.e. it selects
near-flat degenerate frames rather than good ones. **Neither direction
leaves the beacons where the shipped gate leaves them.** The only setting
under which all six beacon cells sit still is the shipped one — which is not
evidence that 0.6/0.8 is correct, only that it is the point the week's
figures were measured at.

---

## 8. Verdict and recommendation

### 8.1 The calibration produced a threshold, and it is not a loosening

`min_inlier 0.85 / max_resid 0.10`, from §4.3: the loosest point on the
pre-registered grid at which admitted-frame slope error, inside the operating
box real sources occupy, stays under 0.50 σ median and 1.00 σ p90 (measured
0.239 σ and 0.736 σ). It is tighter than shipped on both axes and it keeps 3
of 11 sources on the d0wd and 5 of 8 on the s3, admitting 0.18 % of frames.

### 8.2 Should the loosened gates become the standard for ambient work?

**No, and the reason is not conservatism about changing a default.**

- Loosening to 0.20/0.80 gains 8 both-receiver sources (6 → 14), 7 on the
  d0wd, 6 on the s3, with frame gains up to 502 ×. **Every one of the 13
  fails the pre-registered gain rule.** Slope dispersion 9.6 σ to 64.5 σ.
  A device whose own estimates scatter across ten to sixty-five times the
  between-device spread cannot be placed relative to any other device; its
  appearance in a census is a row, not a measurement.
- Loosening moves a **known beacon of known position by 3.03 σ** on one of
  the two receivers, in the pre-registered direction that rejects the
  setting.
- The synthetic ground truth says the shipped gate is *already* admitting
  frames at 1.25 σ median error; loosening takes that to 1.71 σ. Neither is
  inside the criterion, and the two settings that are cost 99.8 % of the
  frames.

### 8.3 Does the data support looking at those devices at all?

**Not with this estimator and not with these two gate statistics.** §4.4 is
the reason and it is structural, not a threshold problem: `inlier_ratio` and
`resid_std` cannot separate a clean fit from a channel-biased one — a mild
two-ray channel produces frames at `ir` 0.981 / `rs` 0.125, indistinguishable
from clean 14 dB, carrying three times the error. Moving a cut point on a
statistic that does not carry the signal cannot fix that, in either
direction. The eight sources the shipped gate "kills" are not being hidden
by a bad threshold; they are being measured by an estimator whose error, in
their conditions, is larger than the thing being measured.

### 8.4 What would actually change this, and what is already in the tree

`docs/UNWRAP_DEFECT.md` §7 already identified and validated a per-frame
statistic that is *not* useless — **branch-invariant coherence**
`C = |Σ_k exp(j(φ_k − (m·k+b)))| / 52` over the raw principal angles. 52
complex exponentials per frame, no new constant but a threshold, and it uses
values `ransac_line` already returns. It was validated there against the
turn defect. Whether it also separates channel bias is **not established by
this pass and is not claimed here** — but it is the obvious next
calibration, and it can be run through exactly the machinery in §4 with the
criterion in §2 unchanged. That is the recommendation: calibrate a gate on a
statistic that carries the signal, rather than re-cutting two that do not.

### 8.5 What stands, unchanged

Nothing in this document changes any default anywhere. `pc/rff/dsp.py` is
byte-identical (md5 `ebc56a2a82a3aaacf72cea71c6e27281`, mtime 2026-07-13
20:42:46). Every 21–23 August figure produced at the shipped gate is
untouched and, where it was checkable, was reproduced here to the printed
digit (§3.1). The loosened numbers live only in this document, each carrying
its gate setting, and none of them is comparable to a figure produced at the
shipped gate.

---

## 9. Temptations recorded rather than acted on

1. **Relax C1 from 0.50 σ to 1.00 σ.** At 1.00 σ the setting `0.70/0.20`
   passes on the median (1.014 σ, just over) and `0.75/0.20` passes outright
   at 0.908 σ, and the story becomes "a modest tightening recovers
   accuracy on two thirds of the frames". §2.1 forbids it in advance and the
   arithmetic reason still holds: at e = σ the differencing error is 1.41 σ
   and two typical units cannot be distinguished. Not done.
2. **Drop C2 and report medians only.** `0.85/0.15`, `0.85/0.20`,
   `0.90/0.15` and `0.90/0.20` all pass C1 alone (0.523–0.622 σ) while their
   p90 runs **2.30–2.84 σ**, and `0.80/0.10` passes C1 at 0.250 σ while
   failing C2 at 1.157 σ. §2.2 anticipated this exactly and it is the single
   place in the pass where the rider changed an answer. Not done.
3. **Report the 0.20/0.80 census as "+8 sources" and put the dispersion in
   an appendix.** The gain is the headline the brief predicted and it is
   real as a count. C3 was frozen precisely so the count could not be
   reported without the dispersion beside it. Not done.
4. **Exclude d0wd/B2 from §7 as an anomalous cell.** It has form —
   `docs/SEPARATION_SCALING.md` §3.2 and `docs/OVERNIGHT_2026-08-22.md` §3.4
   both set aside a d0wd/B3 cell as an "estimator-bias artefact". Excluding
   it would let the loosening branch pass falsifier 2 on 5 of 6 beacons.
   It is the single most informative cell in the pass and it is reported.
   Not done.
5. **Call `min_inlier 0.85 / max_resid 0.10` "the calibrated gate" without
   §4.4.** It meets the frozen criterion and the sentence would be true. It
   would also imply the gate certifies frames, which §4.4 measures it does
   not. The caveat stays attached wherever the number appears.
6. **Quote a same-receiver "improvement" for `1c:ce` between gates.** Its
   d0wd median moves −0.11446 → −0.11205 between 0.40 and 0.20 and the
   temptation is to read convergence. Its IQR is 0.042 — the move is 6 % of
   its own scatter and means nothing. Not quoted as a trend.
7. **Report the first, `hash()`-seeded sweep and not mention it.** It gave
   `0.80/0.10` as the calibrated gate, which is a rounder story and one grid
   step looser. It was not reproducible between two runs of the same
   command. The seed was fixed, the sweep re-run, the answer moved to
   `0.85/0.10`, and the flip is recorded in §4 and §4.3 rather than
   quietly overwritten.

---

## 10. One-line summary

The gates were calibrated against synthetic ground truth to a criterion
frozen beforehand; the criterion put them at **`min_inlier 0.85 /
max_resid 0.10`**, *tighter* than shipped on both axes, because in the
conditions real frames actually occupy the shipped gate already admits
1.25 σ of median slope error. Loosening to `0.20/0.80` does gain **8
both-receiver sources (6 → 14)** and up to **502 ×** more frames per
source — and **all 13 gained sources have slope dispersion of 9.6 σ to
64.5 σ, none is a gain under the pre-registered rule, and loosening moves a
co-located beacon of known position by 3.03 σ on the d0wd.**
Recommendation: **do not adopt the loosened gates as standard for ambient
work, and do not adopt the calibrated one either** — it keeps 0.18 % of
frames and moves two beacons by more than 2 σ. The limit is not the
threshold value but that `inlier_ratio` and `resid_std` do not carry fit
quality, and the next move is to calibrate `docs/UNWRAP_DEFECT.md` §7's
branch-invariant coherence through this same machinery.
