# REFERENCE CHOICE — does the choice of reference beacon change how much of
# the receiver-and-environment term gets absorbed?

`docs/SEPARATION_SCALING.md` §0 established an inversion: on the 2026-08-22
overnight capture the same-beacon **receiver-to-receiver** SFO differences
(0.00897, 0.01721, 0.05750 rad/sc) all exceed every within-receiver
**beacon-to-beacon** difference on the S3 (0.00104, 0.00439, 0.00542). That
inversion is why a fingerprint enrolled on one receiver does not transfer to
the other. Reference normalisation exists to absorb the shared
receiver-and-environment term. This pass measures whether it does, and
whether the choice of reference matters.

Read-only. Both CSVs were opened `"rb"` and never written; nothing in
`data/raw/` was modified, renamed or deleted. `ls -l --time-style=full-iso`
before and after reports **2,529,534,604** and **2,962,429,711** bytes, last
modified `2026-08-22 08:58:22.552711700 -0500` and `08:58:22.412160000
-0500`. No serial port was opened, nothing was flashed, nothing was staged,
committed or pushed (`git diff --cached --name-only` is empty). Two files in
the repo were written by this pass: **this one** and
**`pc/exp_reference_choice.py`**. The frame cache went to
`$REFCHOICE_CACHE = /tmp/refchoice_cache`, outside the repo tree, as did the
report text. **No scratch file was left in the repo tree by this pass**, and
no `pc/__pycache__/exp_reference_choice.*.pyc` was produced. The
pre-existing `pc/exp_poscontrol_0822.py.head` and `.tail`, which
`docs/POSITIVE_CONTROL_0822.md` asks to be deleted, were **not touched and
are still present**.

**Inputs and window**

| | `d0wd_20260822_023034.csv` | `s3_20260822_023034.csv` |
|---|---|---|
| `node_id`, every row | 68 | 108 |
| data rows | 2,983,560 | 3,564,005 |
| rows flagged corrupt (§1.2) | **142** | **0** |
| beacon frames inside the window, post-screen | 2,905,096 | 3,481,255 |
| ambient frames inside the window, post-screen | 2,158 | 2,345 |

**The window is `300 s <= t < 23,000 s`**, half-open, `t` in seconds of
`pc_time_us` since each file's own first decodable row — the window
`docs/SEPARATION_SCALING.md` established, ending 67 s before the operator
re-entered at `t ≈ 23,067 s` (`docs/POSITIVE_CONTROL_0822.md` §0, §2.1).

B1 = `a4:f0:0f:77:91:20` (the current default reference),
B2 = `28:05:a5:2f:fa:48`, B3 = `f4:2d:c9:70:72:30` (B1's documented clock
twin, `docs/LOT_HYPOTHESIS.md`).

---

## 0. The answer

**No reference condition meaningfully reduces the receiver term. The one
that appears to is a degeneracy, not common-mode rejection.**

Stated as the primary metric asks — the d0wd-minus-s3 SFO difference per
beacon, at 16,384-frame windows with `min_inlier 0.60` / `max_resid 0.80`,
which is the longest-averaging configuration that keeps all three beacons on
**both** receivers (§1.3):

| condition | B1 | B2 | B3 | best shrink on any beacon |
|---|---|---|---|---|
| **none** (raw) | **0.00900** | **0.01713** | **0.05786** | — |
| B1 as reference | *(self)* | 0.00813 | 0.04949 | **2.11×** (B2) |
| B2 as reference | 0.00823 | *(self)* | 0.04124 | 1.40× (B3) |
| B3 as reference | 0.04977 | 0.04083 | *(self)* | **0.18×** — 5.5× *worse* |
| population median | 0.00410 † | 0.00379 † | 0.04610 | 4.52× † (degenerate) |
| population, leave-one-out | 0.02905 | 0.01616 | 0.04533 | 1.28× (B3) |

† **degenerate — see §3.** With three sources the population median *is* one
of the sources. On the d0wd the middle beacon is B2 and on the S3 it is B1,
so under this condition the two receivers are normalised against **different
references**, and on each receiver one beacon is subtracted from itself and
reads identically `+0.00000`. That is the whole of its apparent advantage.

**Best condition, and by what factor.** On the like-for-like mean over each
condition's own beacon set, the population median scores 1.56× and every
other condition scores between 0.29× and 1.37×. Once the degenerate
condition is set aside, **the best is B2 as reference at 1.35×** (mean over
B1 and B3), with B1 as reference at 1.30×. The largest reduction on any
single beacon by any non-degenerate condition is **B1-as-reference on B2,
0.01713 → 0.00813, a factor of 2.11**.

**Does any condition bring the receiver term below the device term? No.**
The ratio that matters is the smallest receiver term against the largest
within-receiver beacon-to-beacon difference on the S3, measured under the
*same* condition — because reference correction shrinks the device term too:

| condition | smallest receiver term | largest S3 device term | ratio |
|---|---|---|---|
| none | 0.00900 | 0.00505 (B2−B3) | **1.78** |
| B1 as reference | 0.00813 | 0.00459 (B2−B3) | **1.77** |
| population, leave-one-out | 0.01616 | 0.00750 (B2−B3) | **2.15** |
| population median | 0.00379 † | 0.00418 † (B2−B3) | 0.91 † |

1.78 with no reference and 1.77 with the default reference. **Reference
correction shrinks the receiver term and the device term by nearly the same
factor, so the inversion survives untouched.** (B2- and B3-as-reference
score 7.35 and 7.93 on this ratio, but those rows are confounded: the only
pair each leaves is the B1/B3 clock twins and the B1/B2 pair respectively —
see §5.)

**The mechanism, measured directly.** Subtracting a reference *raises* the
Allan-deviation floor of the corrected series in **six of six**
non-degenerate S3 cells, by a factor of **1.40 to 1.69** — which is what
subtracting an **uncorrelated** series of comparable magnitude gives
(1.31–1.55 predicted from the two uncorrected floors), and the measured
ratios exceed even that by 2–9 %. If a shared receiver-and-environment term
existed at these timescales, the difference of two sources would have a
*lower* floor than either. It has a higher one. **There is no measurable
common short-term component for a reference to cancel.** (§4.2.)

**And B3 must never be the reference on this capture.** B3/d0wd is the
58.8 %-reject cell that `docs/OVERNIGHT_2026-08-22.md` §10 and
`docs/POSITIVE_CONTROL_0822.md` §5 both say must not be quoted alone. Its
SFO is an estimator-bias artefact, and using it as a reference **injects
that artefact into every other source**: B1's receiver term goes 0.00900 →
0.04977 (5.5× worse) and B2's 0.01713 → 0.04083 (2.4× worse). The same
contamination is why the leave-one-out population reference makes B1 worse
(0.00900 → 0.02905): on the d0wd, `median(B2, B3)` is half B3.

**Two facts about what a reference cannot fix.** No condition brings B3's
own receiver term below 0.04124 — because that difference is not a receiver
term at all but a per-source, per-receiver estimator bias, and reference
correction removes only what is *common* to the sources on a receiver.
And no condition improves the twin pair: on the S3 at the best
configuration, B1 vs B3 is **0.95σ** uncorrected and **0.89σ** under the
population reference (§5).

---

## 1. Method

One script, `pc/exp_reference_choice.py`, from the repo root. The
`scan`/`merge` split exists only because this host caps a shell call at
~178 s (measured: a `sleep 400` returns `Command timed out after
177999ms`) and a single pass over the two files takes about thirteen
minutes:

```
export REFCHOICE_CACHE=/tmp/refchoice_cache
D=data/raw/d0wd_20260822_023034.csv
S=data/raw/s3_20260822_023034.csv
for p in $(seq 0 11); do
    python3 pc/exp_reference_choice.py scan $D --tag d0wd --part $p --nparts 12
done
for p in $(seq 0 13); do
    python3 pc/exp_reference_choice.py scan $S --tag s3   --part $p --nparts 14
done
python3 pc/exp_reference_choice.py merge --tag d0wd --nparts 12 --expect-rows 2983560
python3 pc/exp_reference_choice.py merge --tag s3   --nparts 14 --expect-rows 3564005
python3 pc/exp_reference_choice.py report --tags d0wd,s3
```

Every figure below is from `report` unless it names another command. The
split is not an approximation: byte ranges are cut on line boundaries, each
part asserts that its first byte equals the previous part's last byte, the
`FrameEstimator` state, the MAC table and the in-flight median-filter buffer
are pickled forward, and `merge` re-checks rather than asserts — the parts'
rows sum to **2,983,560 and 3,564,005**, matching `wc -l` minus the header
exactly, with **0 `pc_time_us` reversals** across the 11 and 13 seams.

**Phase work is `pc/rff/dsp.py`'s `FrameEstimator` and `WindowAggregator`.**
`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` were
**not** used: `docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 establishes all three
have the DC/guard-band index wrong, and `pc/test_rff_synth.py` test 7 shows
`phase_skew`'s mask returns the opposite sign.

**The DSP runs once and the conditions are re-derived from a per-frame
cache**, for the reason `pc/exp_separation_scaling.py` states: `FrameEstimator`
state depends only on the order of a source's own frames and on nothing the
gates do, and `WindowAggregator` gating is strictly downstream
(`pc/rff/dsp.py:173-177`), emitting a window every `window` accepted frames
with the buffer then cleared. `report` §0b **checks** that rather than
asserting it, replaying 20,000 cached frames per node through the real
`WindowAggregator(64, 0.6, 0.8)`: **300 and 311 windows, counts equal, SFO
bit-identical**.

### 1.1 The parse defect, and the check that it is not present here

`docs/POSITIVE_CONTROL_0822.md` §1.2 records that `cs.split(",", 128)` at
`pc/exp_overnight_0822.py:303` and `pc/exp_s3_sfo_steps.py:153,590` silently
discards every `csi_len = 128` row, because `maxsplit=128` returns **at
most** 129 items and a 128-value row yields exactly 128. This script reads
the field with `np.fromstring(cs, sep=",")` — the same read as
`pc/rff_offline.py:203` — and counts what it sees (`report` §0):

| | d0wd | s3 |
|---|---|---|
| data rows | 2,983,560 | 3,564,005 |
| rows undecodable by line / field | 0 / 0 | 0 / 0 |
| parsed CSI vector length **128** | **2,222** | **2,444** |
| parsed CSI vector length **256** | **2,981,272** | **3,561,558** |
| other lengths | 384: 64, 241: 1, 0: 1 | 384: 3 |
| rows `split(",", 128)` would have dropped | 2,223 | 2,444 |

The parsed-vector histogram equals the `csi_len` column histogram row for
row in both files, and an independent `awk` reproduces it without using the
script at all:

```
awk -F, 'NR>1{n++; h[$9]++} END{print "rows",n; for(k in h) print "  len",k,h[k]}' \
    data/raw/d0wd_20260822_023034.csv
```
> `rows 2983560` · `len 0 1` · `len 128 2222` · `len 241 1` · `len 256 2981272` · `len 384 64`

**The check with teeth** is that the 128-length sources produce fits,
because a parser carrying the defect returns zero for them. `scan`
phase-estimates every non-beacon source as well: **2,153 of 2,158 ambient
frames on the d0wd and 2,344 of 2,345 on the S3 obtained a RANSAC fit**,
including `1c:ce:51:f3:0d:fa` (947 and 932 frames, 100 % fitted) — a source
`docs/POSITIVE_CONTROL_0822.md` §3.1 lists at `len 128`.

### 1.2 The corrupt-row screen, reproduced

Both routes of `docs/OVERNIGHT_2026-08-22.md` §1 are applied here, unlike
`docs/SEPARATION_SCALING.md`, which screened only on parseability:

- **field plausibility** on six columns — `node_id` against the file's own
  mode, `env_id == 0`, `channel` against the file's own mode, `csi_len` in
  {128, 256, 384}, `noise_floor` in [−110, −70], `rssi` in [−100, −10];
- **a width-9 median filter on `dropped`**, tolerance 100. The comparison is
  made **circularly, mod 65536**, so the u16 counter's 0 and 9 wraps
  (§4.2 of that document) are not false positives.

Result: **142 flagged on the d0wd, 0 on the S3** — the same counts that
document reports. The decomposition names the row it already named: **141 by
field plausibility, 140 by the median filter, 139 by both**, i.e. exactly
**one row is caught only by the median filter** — line 95,349, `dropped 15`
between neighbours reading 9,743, with every other field plausible
(`docs/OVERNIGHT_2026-08-22.md` §4.2). The field-plausibility count is
reproduced by an `awk` that shares no code with the script:

```
awk -F, 'NR>1{ nd=$(NF-2); ev=$(NF-1); ch=$7; ln=$9; nf=$6; rs=$5;
   ok = (nd==68 && ev==0 && ch==6 && (ln==128||ln==256||ln==384)
         && nf<=-70 && nf>=-110 && rs<=-10 && rs>=-100);
   if(!ok) bad++ } END{print "field-screen flagged:", bad+0}' \
   data/raw/d0wd_20260822_023034.csv
```
> `field-screen flagged: 141` — and `0` for the S3 with `nd==108`.

The screen mode is not hard-coded: it is taken from a pre-scan of the first
20,000 rows (`node_id` 68 / 108, `channel` 6) and `merge` re-checks it
against the whole-file histogram — **both AGREE**.

### 1.3 What "reference" means here, and why the configuration is not `min_inlier 0.90`

**Correction is within a receiver and simultaneous.** The term being
cancelled is a *receiver's*, so a window's reference is the median of the
reference source's gated frames lying inside **that same window's own time
span on that same node**. Windows are per-source, defined the established
way — a chunk of `window` consecutively-accepted frames — so their spans
differ in length between beacons (164 s to 766 s at 16,384 frames); the
reference is re-measured over each window's own span rather than assumed
constant. A window is dropped if the reference has fewer than 8 accepted
frames in its span; at 16,384 frames the *minimum* reference coverage
anywhere is **2,559 frames**, so nothing is resting on a thin reference.

**The brief asked for `docs/SEPARATION_SCALING.md` §5.1's best
configuration — window 16,384, `min_inlier 0.90`, `max_resid 0.80`. At that
configuration the primary metric does not exist**, and this is a fact about
the d0wd rather than a choice made here:

| node | beacon | frames kept at `min_inlier 0.90` | windows at 16,384 |
|---|---|---|---|
| d0wd | B1 | 1,298 of 860,321 (0.15 %) | **0** |
| d0wd | B2 | 12,792 of 896,267 (1.43 %) | **0** |
| d0wd | B3 | **0** of 1,148,508 (0.00 %) | **0** |
| s3 | B1 | 1,055,628 of 1,255,513 (84.08 %) | 64 |
| s3 | B2 | 494,247 of 811,474 (60.91 %) | 30 |
| s3 | B3 | 1,185,588 of 1,414,268 (83.83 %) | 72 |

`min_inlier 0.90` deletes **every frame** of B3/d0wd and leaves the d0wd
14,090 frames in total — under one 16,384-frame window. A d0wd-minus-s3
difference cannot be formed. This is the same collapse
`docs/SEPARATION_SCALING.md` §4.4 documents at window 64 ("the d0wd's inlier
gate is not selecting good frames from a good cell, it is **deleting the B3
cell**").

**Every figure in §0 and §2 is therefore at window 16,384, `min_inlier
0.60`, `max_resid 0.80`** — the same 164 s-plus of averaging, the same
residual gate, all three beacons alive on both receivers. The shipped
configuration (window 64) is reported alongside because its window counts
are 12,448–22,029 rather than 28–86 and its confidence intervals are
correspondingly tight; **the two agree on every conclusion**. The
`min_inlier 0.90` results are reported for the S3 alone, where they are
measurable, and they agree too.

### 1.4 Reproduction against `docs/SEPARATION_SCALING.md`

`report` §0c, shipped configuration, this window:

| node | b | this pass: reject % / SFO median / windows | SEPSCALE §0c, §3.1 |
|---|---|---|---|
| d0wd | B1 | 7.393 % / +0.02284 / 12,448 | 7.371 % / +0.02287 / 12,451 |
| d0wd | B2 | 4.069 % / +0.02680 / 13,434 | 4.082 % / +0.02678 / 13,432 |
| d0wd | B3 | 59.445 % / +0.07226 / 7,277 | 59.477 % / +0.07218 / 7,272 |
| s3 | B1 | 0.566 % / +0.01390 / **19,506** | 0.566 % / +0.01390 / **19,506** |
| s3 | B2 | 0.712 % / +0.00956 / **12,588** | 0.712 % / +0.00956 / **12,588** |
| s3 | B3 | 0.311 % / +0.01468 / **22,029** | 0.311 % / +0.01468 / **22,029** |

**The three S3 cells are identical in every printed digit and every window
count**, and so are its gate-sweep totals (3,463,968 frames at
`min_inlier 0.60`, 2,735,463 at 0.90, 3 frames with no RANSAC fit, largest
`resid_std` 0.2188 — all four exactly `docs/SEPARATION_SCALING.md` §4.1–4.2).
The d0wd differs in the fifth decimal, and the reason is stated rather than
waved at: **this pass screens 142 corrupt rows before the estimator and that
pass did not.** Removing 30 beacon rows shifts each source's RANSAC RNG
stream, so per-frame values downstream are not bit-identical. The
consequences are 3–5 windows per cell and ≤ 8 × 10⁻⁵ rad/sc on a median —
0.03 × `BETWEEN_UNIT_SD`. On the S3, where the screen removes nothing, the
agreement is exact, which is what makes the attribution safe. One knock-on:
the largest `resid_std` on the d0wd reads **0.2261** here against 0.2202
there — still **3.5× below the shipped `max_resid = 0.8`**, so that gate is
inoperative on this data either way.

The raw receiver-to-receiver differences reproduce directly:

| beacon | this pass, shipped | SEPSCALE §0 |
|---|---|---|
| B1 | **+0.00894** | +0.00897 |
| B2 | **+0.01724** | +0.01721 |
| B3 | **+0.05758** | +0.05750 |

**One figure of that document did not reproduce, and it is small.** §0 and
§2.3 give the within-S3 beacon-to-beacon differences as 0.00104 (B1−B3),
0.00439 (B1−B2), 0.00542 (B2−B3). This pass measures **0.00078, 0.00434,
0.00512** at the same configuration — and those are also what that
document's *own* §0c medians imply (0.01390 − 0.01468 = −0.00078). The two
sets agree to 2.6 × 10⁻⁴ or better and the discrepancy is not explained
here; every within-receiver figure below is this pass's own.

### 1.5 An independent re-derivation of the primary metric

The primary table was recomputed from the cached per-frame arrays by a
separate, plain-loop implementation that reuses none of
`exp_reference_choice.py`'s windowing or reference functions. **All 15
condition × beacon cells at window 16,384 / `min_inlier 0.60` agree to the
printed digit** (five decimal places), on both nodes and on the difference.

---

## 2. THE PRIMARY METRIC — d0wd minus s3, per beacon, per condition

`report` §1. Window 16,384 accepted frames (164 s to 766 s of wall clock,
depending on the cell's accept rate), `max_resid 0.80`, `min_inlier 0.60`.
Medians over windows; 95 % CI by bootstrap over windows, 4,000 resamples,
`np.random.default_rng(0)`, each node resampled independently.

| cond | beacon | d0wd med | n | s3 med | n | **d0wd − s3** | 95 % CI | × BU_SD | shrink |
|---|---|---|---|---|---|---|---|---|---|
| none | B1 | +0.02293 | 48 | +0.01393 | 76 | **+0.00900** | [+0.00787, +0.00985] | 3.80 | 1.00 |
| none | B2 | +0.02674 | 52 | +0.00961 | 49 | **+0.01713** | [+0.01684, +0.01755] | 7.23 | 1.00 |
| none | B3 | +0.07252 | 28 | +0.01466 | 86 | **+0.05786** | [+0.05551, +0.05990] | 24.41 | 1.00 |
| B1 | B2 | +0.00394 | 52 | −0.00420 | 49 | **+0.00813** | [+0.00734, +0.00909] | 3.43 | **2.11** |
| B1 | B3 | +0.04988 | 28 | +0.00039 | 86 | **+0.04949** | [+0.04651, +0.05167] | 20.88 | 1.17 |
| B2 | B1 | −0.00410 | 48 | +0.00413 | 76 | **−0.00823** | [−0.00876, −0.00739] | 3.47 | 1.09 |
| B2 | B3 | +0.04649 | 28 | +0.00525 | 86 | **+0.04124** | [+0.03799, +0.04269] | 17.40 | 1.40 |
| B3 | B1 | −0.05024 | 48 | −0.00047 | 76 | **−0.04977** | [−0.05227, −0.04813] | 21.00 | **0.18** |
| B3 | B2 | −0.04645 | 52 | −0.00561 | 49 | **−0.04083** | [−0.04246, −0.03971] | 17.23 | **0.42** |
| pop † | B1 | −0.00410 | 48 | **+0.00000** | 76 | **−0.00410** | [−0.00451, −0.00339] | 1.73 | 2.20 † |
| pop † | B2 | **+0.00000** | 52 | −0.00379 | 49 | **+0.00379** | [+0.00360, +0.00421] | 1.60 | 4.52 † |
| pop | B3 | +0.04649 | 28 | +0.00039 | 86 | **+0.04610** | [+0.04274, +0.04729] | 19.45 | 1.26 |
| popLOO | B1 | −0.02750 | 48 | +0.00154 | 76 | **−0.02905** | [−0.02979, −0.02767] | 12.26 | 0.31 |
| popLOO | B2 | −0.02110 | 52 | −0.00494 | 49 | **−0.01616** | [−0.01703, −0.01523] | 6.82 | 1.06 |
| popLOO | B3 | +0.04789 | 28 | +0.00256 | 86 | **+0.04533** | [+0.04321, +0.04733] | 19.13 | 1.28 |

`BU_SD` = `BETWEEN_UNIT_SD` = 0.00237 (`pc/exp_thermal_evidence.py:129`).
"shrink" is `|diff| under none ÷ |diff| under this condition`; > 1 is an
improvement. A beacon used as its own reference is excluded from its own
condition rather than reported as a meaningless zero. **The `pop` rows
marked † are degenerate — §3.**

**The same table at the shipped configuration** (window 64, 12,448–22,029
windows per cell, so the CIs are an order of magnitude tighter) reaches the
same numbers and the same conclusions:

| cond | B1 | B2 | B3 |
|---|---|---|---|
| none | +0.00894 | +0.01724 | +0.05758 |
| B1 | *(self)* | +0.00821 | +0.04870 |
| B2 | −0.00829 | *(self)* | +0.04028 |
| B3 | −0.04930 | −0.04086 | *(self)* |
| pop | −0.00398 † | +0.00388 † | +0.04479 |
| popLOO | −0.02838 | −0.01613 | +0.04467 |

Every CI at that configuration is narrower than ±0.0001 and every one
excludes zero. **No condition puts any beacon's receiver-to-receiver
difference below 0.0037 rad/sc, and only the degenerate condition gets under
0.0081.**

**A necessary caveat on all the CIs.** They resample windows independently.
`docs/SEPARATION_SCALING.md` §2 establishes that the per-frame SFO series is
correlated beyond τ ≈ 10 s and that its Allan deviation *rises* past
τ ≈ 200 s, so consecutive windows are not independent draws and every
interval above is **too narrow**. Nothing in §0 rests on an interval width;
the conclusions rest on ratios of 2× to 30× between point estimates.

---

## 3. Why the population reference looks best, and why that is not a result

**With three sources, the median across the population *is* one of the
sources.** Subtracting it means, on each receiver, subtracting whichever
beacon happens to sit in the middle. From the uncorrected medians:

```
d0wd:  B1 +0.02293   B2 +0.02674   B3 +0.07252    -> the median is B2
s3:    B1 +0.01393   B2 +0.00961   B3 +0.01466    -> the median is B1
```

Three consequences follow, and all three are visible in the §2 table:

1. **One beacon per receiver is normalised against itself** and reads
   identically `+0.00000` — d0wd/B2 and s3/B1 in the table. That is not a
   measurement.
2. **The two receivers are normalised against different references.** The
   d0wd's B1 is corrected against B2 and the S3's B1 is corrected against
   B1. A cross-receiver difference formed from those two is a comparison of
   two different quantities. `pop`'s B1 row (−0.00410) is in fact just
   `B2-as-reference`'s d0wd value (−0.00410) with the S3 side zeroed out —
   the same number, and the S3 contributes nothing to it.
3. **The apparent advantage is exactly that zeroing.** Under
   `B2-as-reference`, where both nodes use the same reference, B1's receiver
   term is 0.00823. Under `pop` it is 0.00410 — half, because one of the two
   terms in the subtraction has been replaced by zero.

**`popLOO`, the non-degenerate form** — subtract the median of the *other*
sources, which for three beacons is the mean of the two others — is the
honest version of common-mode rejection by the population, and it is the
condition that comes out **worst but one**: 0.31×, 1.06×, 1.28×, a
like-for-like mean of **0.93×**, i.e. slightly worse than doing nothing.

The reason `popLOO` is so bad on B1 is worth naming because it generalises:
on the d0wd, `median(B2, B3) = mean(+0.02674, +0.07252) = +0.04963`, and
B3/d0wd's +0.07252 is the 58.8 %-reject estimator-bias cell. **Any reference
built from B3 on the d0wd imports that bias into whatever it corrects.**
That is one mechanism; §4.2 gives the other, which applies even to clean
cells.

---

## 4. Secondary metrics

### 4.1 Within-source spread of the corrected per-window SFO

`report` §2, window 16,384 / `min_inlier 0.60`. IQR of the corrected
per-window SFO, rad/sc. A reference that absorbed a shared term would
*reduce* this.

**S3 (the primary node):**

| cond | B1 IQR | B2 IQR | B3 IQR |
|---|---|---|---|
| none | **0.00134** | **0.00126** | **0.00226** |
| B1 | *(self)* | 0.00162 | 0.00327 |
| B2 | 0.00166 | *(self)* | 0.00255 |
| B3 | 0.00312 | 0.00244 | *(self)* |
| pop | 0.00060 † | 0.00128 | 0.00261 |
| popLOO | 0.00211 | 0.00177 | 0.00264 |

**d0wd:**

| cond | B1 IQR | B2 IQR | B3 IQR |
|---|---|---|---|
| none | **0.00281** | **0.00097** | **0.00464** |
| B1 | *(self)* | 0.00292 | 0.00706 |
| B2 | 0.00229 | *(self)* | 0.00446 |
| B3 | 0.00715 | 0.00589 | *(self)* |
| pop | 0.00229 | 0.00000 † | 0.00446 |
| popLOO | 0.00464 | 0.00286 | 0.00614 |

**Reference correction increases the within-source spread in 10 of the 12
single-beacon-reference cells** — all six on the S3, four of six on the
d0wd. Both exceptions are on the d0wd and both are B2-as-reference: B1
(0.00281 → 0.00229) and B3 (0.00464 → 0.00446). `popLOO` increases it in
**six of six**. The two `0.00000` entries are the self-subtraction of §3.

### 4.2 The Allan floor — the mechanism behind the null

`report` §2b. Per-frame accepted slopes are binned into τ₀ = 0.5 s bins on a
common grid, the correction is applied bin by bin, and the overlapping Allan
deviation is taken on the corrected bin series. The floor is its minimum
over τ ∈ [0.5 s, 3600 s]. Same machinery as
`docs/SEPARATION_SCALING.md` §2, on the corrected series.

**S3, floor in rad/sc (τ of the minimum in brackets):**

| cond | B1 | B2 | B3 |
|---|---|---|---|
| none | **3.197e-4** (26 s) | **2.686e-4** (186 s) | **3.016e-4** (36 s) |
| B1 | *(self)* | 4.530e-4 (50 s) | 4.468e-4 (26 s) |
| B2 | 4.530e-4 (50 s) | *(self)* | 4.377e-4 (70 s) |
| B3 | 4.468e-4 (26 s) | 4.377e-4 (70 s) | *(self)* |
| pop | 2.405e-4 † (26 s) | 3.172e-4 (96 s) | 2.868e-4 (36 s) |
| popLOO | 3.921e-4 (36 s) | 3.692e-4 (70 s) | 3.929e-4 (36 s) |

Read the six single-beacon-reference cells against the "none" row:

| corrected series | uncorrected floor | corrected floor | measured ratio | ratio if the two series were **independent** |
|---|---|---|---|---|
| B2 − B1 | 2.686e-4 | 4.530e-4 | **1.687** | 1.554 |
| B1 − B2 | 3.197e-4 | 4.530e-4 | **1.417** | 1.306 |
| B3 − B1 | 3.016e-4 | 4.468e-4 | **1.481** | 1.457 |
| B1 − B3 | 3.197e-4 | 4.468e-4 | **1.398** | 1.375 |
| B3 − B2 | 3.016e-4 | 4.377e-4 | **1.451** | 1.339 |
| B2 − B3 | 2.686e-4 | 4.377e-4 | **1.630** | 1.503 |

The last column is `sqrt(σa² + σb²) / σa` — what differencing two
*uncorrelated* series with those floors would give. **Six of six measured
ratios are at or above that prediction**, by 2 % to 9 %. Differencing two
sources on the same receiver behaves as if the two carried no shared
component at all.

That is the whole null result in one table, and it is the same shape of
argument as `docs/SEPARATION_SCALING.md` §2.4's shuffle control: the
correction arithmetic works perfectly; there is simply nothing common to
remove. Whatever drives the SFO estimate on the 10–200 s timescale — and §2
of that document establishes it is correlated, not white — it is **not
shared between beacons at one receiver**, so no beacon can act as its proxy.

The d0wd shows the same thing (B1: 6.597e-4 → 7.809e-4 under B2, →
1.682e-3 under B3; B2: 3.804e-4 → 7.809e-4 under B1, → 1.595e-3 under B3).
Note the size of the B3 column there: a reference drawn from the
58.8 %-reject cell raises the corrected floor by **2.5× and 4.2×**.

**Two limits on this table.** The minima are taken at different τ in
different rows, so the ratios are minimum-to-minimum rather than
τ-matched. And the prediction column assumes the reference's own noise is
of the same character as the target's; §2 of `docs/SEPARATION_SCALING.md`
shows both are flicker-like over most of the range, but nothing here
verifies that the *shapes* match. The claim the table supports is "no
measurable common component", not a precise correlation coefficient.

---

## 5. Pairwise separation, and the confound in reading it

`report` §3, SFO axis, `|Δμ| / pooled sd`, no variance floor. The
uncorrected S3 row reproduces `docs/SEPARATION_SCALING.md` §3.1 and §5.1 to
two decimals (3.51/0.83/4.34 at `min_inlier 0.60`; 3.72/0.95/4.67 at 0.90
against that document's 3.72/0.96/4.68), which is the check that this
statistic is the same one.

**S3, window 16,384, `min_inlier 0.60`:**

| cond | sources left | pooled sd | B1–B2 | B1–B3 | B2–B3 | min |
|---|---|---|---|---|---|---|
| none | all three | 0.00125 | 3.51σ | **0.83σ** | 4.33σ | 0.83σ |
| B1 | B2, B3 | 0.00194 | — | — | 2.78σ | 2.78σ |
| B2 | B1, B3 | 0.00169 | — | **0.61σ** | — | 0.61σ |
| B3 | B1, B2 | 0.00212 | 2.07σ | — | — | 2.07σ |
| pop | all three | 0.00131 | 3.36σ | **0.77σ** | 4.12σ | 0.77σ |
| popLOO | all three | 0.00168 | 3.92σ | **0.92σ** | 4.84σ | 0.92σ |

**The confound, stated explicitly.** With three beacons, each single-beacon
reference leaves a *different* pair, so those three rows are not comparable
with each other or with "none". In particular **B2-as-reference leaves the
B1/B3 clock twins** — a pair `docs/LOT_HYPOTHESIS.md` characterises as a
genuine twin (0.26σ, ΔSFO 0.00080 on `rx_20260714_011619`) and
`docs/SEPARATION_SCALING.md` §5.2 measures at 0.66–1.18σ across 174 of 175
configurations. **Its 0.61σ minimum is the twins being twins and says
nothing about B2 as a reference.** Symmetrically, B1-as-reference's 2.78σ
and B3-as-reference's 2.07σ look better only because neither leaves the twin
pair. **Only "none", "pop" and "popLOO" leave all three**, and among those
the twin pair reads 0.83σ, 0.77σ and 0.92σ — a ±0.09σ band around doing
nothing. At `min_inlier 0.90` on the S3 the same three read 0.95σ, 0.89σ and
1.07σ.

The d0wd's separations (B1–B2 1.49σ, B1–B3 17.38σ, B2–B3 15.90σ under
"none") are not quoted as separations for the reason
`docs/SEPARATION_SCALING.md` §3.2 gives: the two large figures are B3/d0wd,
the 59 %-reject estimator-bias cell.

---

## 6. Ambient MACs — which can support an estimate, and which cannot

`report` §4, over the empty-room window, at the shipped gates. The inclusion
rule is `docs/POSITIVE_CONTROL_0822.md` §3.1's, stated before the answer:
**both** receivers must accept ≥ 20 of the source's frames.

**One ambient source qualifies: `62:45:b4:f0:e1:97`** — 20 frames on the
d0wd and 20 on the S3, **100 % accepted on both**, RSSI −26.25 and −34.05.
Everything else fails, and the reason is worth separating into two kinds:

| mac | d0wd n / acc | s3 n / acc | why not |
|---|---|---|---|
| `1c:ce:51:f3:0d:fa` | 947 / **0** | 932 / 330 | one receiver accepts none |
| `ba:80:d5:0c:18:87` | 253 / 8 | 899 / **0** | one receiver accepts none |
| `bc:96:e5:af:e5:7a` | 291 / 236 | 175 / **0** | one receiver accepts none |
| `1e:ce:51:f3:0d:fa` | 88 / **0** | 76 / 50 | one receiver accepts none |
| `76:eb:b0:c0:68:4d` | 220 / 82 | 32 / 10 | S3 below 20 |
| `54:6c:eb:15:e3:f7` | 28 / 16 | 43 / 43 | d0wd below 20 |
| `9a:9a:4a:6a:74:f1` | 167 / 0 | 1 / 0 | no acceptance either side |
| `28:f5:2b:4f:7c:6b` | 11 / 11 | 8 / 8 | too sparse, 100 % accepted |
| `a8:6d:aa:55:0d:1b` | 8 / 7 | 6 / 5 | too sparse, ~90 % accepted |
| `6e:0a:30:1f:ed:21` | 6 / 6 | 7 / 1 | too sparse |
| `10:38:1f:da:79:31` | 3 / 3 | 2 / 2 | too sparse, 100 % accepted |
| `64:fa:2b:6d:05:3b`, `f4:69:42:f2:d2:af`, `a6:11:ed:a5:b5:75`, `fe:8f:93:36:1a:b1`, `a8:b1:3b:00:b3:14`, `7e:6d:8c:69:13:0f` | — | — | too sparse and/or no acceptance |

The four largest ambient sources fail for the worst possible reason —
**one receiver accepts essentially none of their frames, and which receiver
that is changes per device**. This reproduces
`docs/POSITIVE_CONTROL_0822.md` §3.4 on the empty-room window: the
`inlier_ratio >= 0.6` gate straddles most ambient traffic, so a small
per-receiver difference in fit quality flips a source from fully accepted to
fully rejected.

**No ambient source can serve as a reference in this analysis**, and the
reason is arithmetic rather than judgement: the qualifying source has **20
accepted frames in 6.3 hours**, about one per 19 minutes. It cannot fill a
single 16,384-frame window, cannot supply 8 frames inside any window's span,
and is 5 orders of magnitude short of the beacons' traffic. The "population"
of §0 is therefore a population of **three**, which is exactly what makes it
degenerate (§3).

---

## 7. Established / permitted / unknown

**Established by this pass, from these files:**

- **No reference condition meaningfully reduces the receiver-to-receiver SFO
  difference.** At window 16,384 / `min_inlier 0.60` the like-for-like mean
  shrink is 1.30× (B1), 1.35× (B2), 0.29× (B3), 1.56× (pop, degenerate) and
  0.93× (popLOO). §0, §2.
- **The best single-beacon result is B1-as-reference on B2, 0.01713 →
  0.00813, 2.11×**, and the best non-degenerate condition overall is
  B2-as-reference at a 1.35× mean. §2.
- **The ratio of the smallest receiver term to the largest S3 device term is
  1.78 with no reference and 1.77 with B1 as reference.** The inversion of
  `docs/SEPARATION_SCALING.md` §0 survives every condition. §0, §5.
- **The three-source population median is degenerate**: the median *is* one
  of the sources, it is B2 on the d0wd and B1 on the S3, and one beacon per
  receiver reads identically +0.00000. `pop`'s advantage is that zeroing.
  §3.
- **The non-degenerate population reference (`popLOO`) is slightly worse
  than no reference**, 0.93× like-for-like. §2, §3.
- **B3 must not be used as a reference on this capture.** It makes B1's
  receiver term 5.5× worse and B2's 2.4× worse, because B3/d0wd is the
  58.8 %-reject estimator-bias cell. Any reference containing B3 on the
  d0wd imports that bias. §0, §3.
- **Reference correction increases the within-source spread** in 10 of 12
  single-beacon-reference cells (six of six on the S3) and in 6 of 6
  `popLOO` cells. §4.1.
- **Reference correction raises the Allan floor by 1.40–1.69× in six of six
  non-degenerate S3 cells**, at or above the 1.31–1.55 that differencing two
  *uncorrelated* series would give. There is no measurable common short-term
  component for a reference to cancel. §4.2.
- **Reference correction does not move the twin pair.** Among the conditions
  that leave all three beacons, B1 vs B3 on the S3 reads 0.83σ (none),
  0.77σ (pop) and 0.92σ (popLOO) at `min_inlier 0.60`, and 0.95σ / 0.89σ /
  1.07σ at 0.90. §5.
- **`docs/SEPARATION_SCALING.md` §5.1's best configuration cannot support
  the primary metric**: `min_inlier 0.90` keeps 0 of 1,148,508 B3/d0wd
  frames and 14,090 of 2,904,844 d0wd frames overall — under one
  16,384-frame window. §1.3.
- **The corrupt-row screen reproduces `docs/OVERNIGHT_2026-08-22.md` §1
  exactly**: 142 on the d0wd, 0 on the S3, with exactly one row caught only
  by the median filter; the field-plausibility count of 141 is confirmed by
  an independent `awk`. §1.2.
- **The `split(",", 128)` defect is not present in this pass**: 2,222 and
  2,444 128-length rows parsed, 2,153/2,158 and 2,344/2,345 ambient frames
  fitted. §1.1.
- **One ambient source of 18 qualifies for a cross-receiver estimate**
  (`62:45:b4:f0:e1:97`, 20 accepted frames per node), and none can act as a
  reference. §6.
- **The three S3 cells reproduce `docs/SEPARATION_SCALING.md` in every
  printed digit and window count**; the d0wd differs in the fifth decimal
  because this pass screens 142 corrupt rows before the estimator, which
  shifts each source's RANSAC RNG stream. §1.4.

**Permitted but not established:**

- That a reference *would* work with a larger population. The population
  here is three, which is why it degenerates; nothing measured says what
  five or ten sources on one receiver would do. §3, §6.
- That the absence of a common component is a property of this room rather
  than of the estimator. §4.2 measures the absence; it does not locate its
  cause. `docs/SEPARATION_SCALING.md` §6 already lists "that the correlated
  component is thermal" as permitted-but-unestablished, and if it *is*
  thermal it is per-crystal, which would explain why no beacon proxies for
  another — but this pass tests none of that.
- That B2 is a better reference than B1 in any general sense. Its 1.35× vs
  B1's 1.30× rests on two beacons each, one of which is B3, and the
  difference is inside what a different night could move.
- That `pop`'s degeneracy is the *only* reason it scores 1.56×. §3 shows the
  B1 and B2 rows are wholly explained by it; the B3 row (1.26×) is not
  degenerate and is a real, small improvement.

**Unknown, and not addressed by this capture:**

- **Whether the d0wd−s3 difference is a receiver property or a position
  property.** The operator states the nodes were deliberately not swapped.
  `docs/DUAL_RX_2026-08-21.md` §6's swap-and-repeat is still the outstanding
  experiment, and this pass adds a reason to run it: if the receiver term is
  not common-mode across beacons at one receiver, it may not be a "receiver
  term" at all.
- **Why B3/d0wd rejects 58.8 % of its frames** at the strongest RSSI on that
  node. Unchanged from `docs/OVERNIGHT_2026-08-22.md` §8. It dominates every
  B3 row above and no reference removes it.
- **Whether reference correction helps across *sessions* rather than across
  receivers.** Only the cross-receiver question was asked here.
- **Whether a reference measured on a different axis** (RSSI,
  `resid_std`, `noise_floor`) would absorb what an SFO reference does not.
  Only SFO-on-SFO correction was tested.
- The 2.6 × 10⁻⁴ discrepancy between this pass's within-S3 beacon-to-beacon
  differences and the ones `docs/SEPARATION_SCALING.md` §0/§2.3 quotes.
  §1.4.

---

## 8. Figures in this document that should not be quoted alone

- **`pop`'s 1.56× and its 0.00410 / 0.00379.** Degenerate: one beacon per
  receiver is subtracted from itself and the two receivers use different
  references. §3.
- **Anything in a B3 row, in either direction.** B3/d0wd is the
  58.8 %-reject cell that `docs/OVERNIGHT_2026-08-22.md` §10 and
  `docs/POSITIVE_CONTROL_0822.md` §5 both say must not be quoted alone. Its
  raw receiver difference (0.05786) and the damage it does as a reference
  (0.18×) are both driven by an estimator-bias artefact, not by a clock.
- **The 0.61σ under B2-as-reference and the 2.78σ / 2.07σ under B1 and B3.**
  Each single-beacon reference leaves a different pair; 0.61σ is the B1/B3
  clock twins and the other two are pairs that do not contain them. §5.
- **The 7.35 and 7.93 receiver-to-device ratios for B2 and B3 as
  reference.** Same confound: the denominator is whichever pair that
  condition happens to leave.
- **Every 95 % CI in §2.** Bootstrap over windows, which are correlated;
  all of them are too narrow. §2, and `docs/SEPARATION_SCALING.md` §2.
- **The Allan ratios in §4.2 as a correlation measurement.** They are
  minimum-to-minimum at different τ and rest on an equal-character
  assumption for the two noise processes. They support "no measurable common
  component", not a coefficient. §4.2.
- **"2.11×" as the value of a reference.** It is one beacon (B2) under one
  reference (B1) on one night, and it still leaves 0.00813 rad/sc — 3.4 ×
  `BETWEEN_UNIT_SD` and 10.2 × the twin ΔSFO.
- **The d0wd's 1.49σ / 17.38σ / 15.90σ.** Estimator bias, per
  `docs/SEPARATION_SCALING.md` §3.2.

Nothing in this document touches the occupancy pipeline (`pc/occ/`,
amplitude domain). Device-ID and occupancy figures must not be combined.

---

## 9. What would settle the rest

1. **Swap the two nodes' positions and repeat.** Still the outstanding
   experiment (`docs/DUAL_RX_2026-08-21.md` §6,
   `docs/SEPARATION_SCALING.md` §8.1, `docs/POSITIVE_CONTROL_0822.md` §6).
   §4.2's finding that nothing is common-mode between beacons at one
   receiver makes "receiver term" itself a hypothesis worth testing rather
   than a label to assume.
2. **A larger simultaneous population on one receiver.** The population
   reference degenerates at three sources and cannot be evaluated properly
   below about five. That needs either more beacons or ambient traffic the
   `inlier_ratio >= 0.6` gate does not delete — and
   `docs/POSITIVE_CONTROL_0822.md` §6 already proposes the gate-stratified
   study of `1c:ce:51:f3:0d:fa` that would say whether the second is
   available.
3. **Stratify B3/d0wd by `inlier_ratio`**, as `docs/S3_SFO_STEPS.md` §7.2
   did for B3/s3. Every B3 row above is dominated by that cell, and until it
   is explained the largest number in this document is uninterpretable.
4. **Temperature logging.** If the correlated component is thermal and
   per-crystal, that is a mechanism for §4.2's null — a shared *room*
   temperature would show as common mode and does not. Nothing in this repo
   has ever recorded a temperature.
5. **A reference on a different axis.** The frame cache this pass builds
   holds per-frame `resid_std`, `inlier_ratio` and RSSI alongside the slope
   for 6.4 M frames. `docs/OVERNIGHT_2026-08-22.md` §3.2 measures
   r(SFO, `resid_std`) at +0.63 to +0.84 in six of six cells — a stronger
   relationship than any beacon has with any other beacon here, and the
   obvious thing to try correcting against next.
