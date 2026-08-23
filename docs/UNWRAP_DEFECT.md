# UNWRAP DEFECT — can `pc/rff/dsp.py`'s phase unwrapping land a whole turn
# out on a weak signal, and stay there?

One question, asked of `pc/rff/dsp.py` and of the 2026-08-22 overnight
capture: `docs/AMBIENT_SEPARATION.md` §5 reports that `1c:ce:51:f3:0d:fa`'s
slope distribution on the d0wd is bimodal with its modes **0.195 rad/sc**
apart, against 2π/32 = 0.1963, and attributes it to "a one-turn RANSAC
mis-unwrap over 32 subcarriers". That is a mechanism claim with an arithmetic
coincidence behind it and nothing else. This pass tries to break it.

**Yes, the defect is real, and it is not what §5 says it is.** The trigger is
not weak signal and not RANSAC choosing a bad subset. It is one dead
subcarrier on one receiver.

Read-only on `data/raw/`. Both CSVs were read with `grep -a`, `tail -c`/`head
-n` and Python's `csv` module and never written; nothing in `data/raw/` was
modified, renamed or deleted; the two files still read **2,962,429,711**
(`s3_20260822_023034.csv`) and **2,529,534,604** (`d0wd_20260822_023034.csv`)
bytes, matching what `docs/SEPARATION_SCALING.md` and
`docs/AMBIENT_SEPARATION.md` record. No serial port was opened, nothing was
flashed, nothing was staged, committed or pushed (`git diff --cached
--name-only` is empty).

**Two files in the repo were written by this pass**: this one, and
`pc/test_rff_synth.py`, which gains a test 9 and nothing else — the printed
output of tests 0 through 8 is **byte-identical** to the pre-existing run
(`diff` clean, verified in §9.1). **`pc/rff/dsp.py` was deliberately not
changed**; §8 gives the five candidate repairs that were built and measured
and why none of them is clearly correct. `pc/rff/dsp.py`'s mtime is still
**2026-07-13 20:42:46** and `git status` does not list it.
`docs/AMBIENT_SEPARATION.md` reads 2026-08-22 13:03:44, before this session's
first write at 13:30, and was not touched here.

Running the tests left `pc/__pycache__/test_rff_synth.cpython-310.pyc`
(27,813 bytes), which **this session had no permission to delete** — `rm`
returns `Operation not permitted`, the same condition
`docs/SEPARATION_SCALING.md` and `docs/AMBIENT_SEPARATION.md` record for
their own `.pyc` files. `__pycache__/` is in `.gitignore`. The pre-existing
`pc/exp_poscontrol_0822.py.head` and `.tail` were not touched.

**The parse defect is not present here.** `csi_data` is a quoted
comma-separated list *inside* the CSV, so `cs.split(",", 128)` returns at
most 129 items and silently drops every 128-length row —
`pc/exp_overnight_0822.py:303` and `pc/exp_s3_sfo_steps.py:153,590` all do
this, and **all ambient traffic is 128-length**. Everything below reads the
field with Python's `csv.reader` plus `np.fromstring(cs, sep=",")`, the same
read as `pc/rff_offline.py:203`. The check with teeth is that the 128-length
sources produce fits: **954 of 954 and 972 of 972** `1c:ce:51:f3:0d:fa`
frames obtained a RANSAC fit on the two nodes.

B1 = `a4:f0:0f:77:91:20`, B2 = `28:05:a5:2f:fa:48`,
B3 = `f4:2d:c9:70:72:30`. d0wd = `node_id` 68, s3 = `node_id` 108.

---

## 0. The answer

**1. The mechanism, established.** `np.unwrap` (`pc/rff/dsp.py:64`) is a
serial, non-robust operation feeding a robust estimator, and the robust
estimator cannot undo it. One subcarrier whose phase is decorrelated from its
neighbours puts every bin after it onto the wrong 2π branch. RANSAC
(`dsp.py:71-103`) then does not reject the split: its winning consensus
*straddles* the break, taking inliers from both branches. A line that
straddles has to climb a whole turn between the two groups, so the fitted
slope is off by 2π ÷ (the separation of the two groups' inlier centroids).

Demonstrated causally, not argued. In the synthetic, where the answer is
known by construction, refitting the affected frames with the same RANSAC and
the same seed and **only** the branching forced onto one branch removes
**99.2 %** of the error, and removing the dead bin instead takes the failure
rate from 4.95 % to **0.00 %** (test 9.1, §5.3). On the real d0wd frames the
same substitution moves the fitted slope by **+0.20494 rad/sc, median, in the
same direction in 58 of 58 frames** (§4).

**2. The trigger is a dead subcarrier on the d0wd, not weak signal.** On
node 68, subcarrier **k = +1 has |CSI| = 3.0 counts in 100.0 % of frames**
against a band median of 20.0 — it is pinned at the quantisation floor and
carries no channel. Its phase is therefore uniform on (−π, π], which is
exactly what the data says: the wrapped phase step across the k = −1 → +1 gap
has median **1.57–1.61 rad** and exceeds 2.5 rad in **20.46–20.65 %** of
frames on all three beacons, against the (π − 2.5)/π = **20.4 %** a uniform
phase predicts. On the s3 the same bin is normal (14.3 counts, band median
12.6) and the same gap reads median 0.065–0.099 rad with **0.00 %** over
2.5. **This is a property of node 68, present on every source it hears.**

**3. Where 2π/32 comes from — measured, not inferred.** It is one turn over
the **separation between the two branch groups' inlier centroids inside the
winning consensus**. On the d0wd's `1c:ce:51:f3:0d:fa` frames that separation
is **32.00 subcarriers (IQR 31.50–32.50)**, the groups sitting at k = −10.25
and k = +19.00, and the measured slope offset across the 58 affected frames
has median **+0.20494 rad/sc = 2π/30.66** and is positive in **58 of 58**.

It is **not** a count of subcarriers in the fit, **not** any span of the
52-wide usable set (2π/52 = 0.1208), and **not a constant of the estimator**:
the same defect in the synthetic reproduction gives 2π/26.2. `2π/Δk where Δk
is the span of the subset`, as `docs/AMBIENT_SEPARATION.md` §5 puts it, is
the right algebra applied to the wrong Δk — the subset spans the whole band,
what matters is where its two halves sit.

**4. `docs/AMBIENT_SEPARATION.md` §5 has the two modes the wrong way round.**
An unwrap-free arbiter — the ramp that maximally aligns the *raw wrapped*
phases, which never unwraps and so cannot inherit an unwrap error — puts the
d0wd's median at **−0.14009** against `dsp.py`'s −0.14188. The d0wd's
dominant −0.14 mode is **genuine**: it is in the received phase and the
estimator reports it correctly. The **minority +0.06 mode is the artefact**,
and it is 6.58 % of frames, not the population. §5 assumed the reverse.

The arbiter also kills the coincidence: evaluated at the *other* receiver's
median slope, its objective is **0.251** of that frame's own peak on the d0wd
and **0.267** on the s3, and exceeds 0.9 in **0.0 %** of frames on either.
The 0.203 rad/sc cross-receiver disagreement for this device is a real
difference in the phase ramp the two boards received, not an estimator error
— which leaves `docs/AMBIENT_SEPARATION.md` §5's *conclusion* (large ambient
slopes are not reproducible across receivers) standing and its *explanation*
refuted.

**5. It does not touch any published beacon figure.** Over **479,705** beacon
frames and **6,515** 64-frame windows across both nodes, the number of
windows whose SFO sits within 10 % of 2π/32 of that beacon's own median is
**zero**. Per frame the turn-out rate is 0.0000–0.0160 % on the s3 and
0.0189–0.0350 % on d0wd/B1 and B2. The one cell where it is not negligible is
**d0wd/B3 at 4.58 %** — the 59 %-reject cell that `docs/SEPARATION_SCALING.md`
§3.2 and `docs/OVERNIGHT_2026-08-22.md` §3.4 already exclude — and even
there, 4.58 % of frames cannot move a 64-frame median. **Only the ambient
work is exposed.**

**6. There is a detector, and it is cheap and clean.** The branch-invariant
coherence of the fitted line,

```
C = | sum_k exp( j * ( phase_k - (slope*k + intercept) ) ) | / 52
```

taken over **all 52 usable bins** with the *un-unwrapped* phase.
`exp(j·2π) == 1`, so C is blind to which branch any bin was put on: it cannot
be measuring the unwrap, only the slope. A one-turn-out fit ramps through
several turns of residual and the sum cancels. Computed on the
*inliers only* it is useless (0.99 either way, by construction) — the 52-bin
version is the whole point. Measured: **C < 0.5 gives 100 % recall at 0.00 %
false positives** on the synthetic population and **92.2 % at 0.00 %** on the
d0wd's real `1c:ce` frames; across 479,705 real beacon frames it flags
0.000–0.023 % in five of six cells and **2.604 %** in d0wd/B3, the one cell
the repo already knew was broken.

**7. No fix was made, and §8 says exactly why.** Five repairs were built and
measured against the arbiter. Four are **worse** than doing nothing
(13.2 %, 83.1 %, 8.5 %, 63.3 % turn-outs against the current 6.07 %). The
fifth is better (1.03 %) but is not a repair: it never reaches zero, its
benefit depends on a tuning constant it does not have a principled value for
(10.80 % / 1.65 % / 1.03 % at FFT lengths 64 / 256 / 1024), and it is **not a
no-op on the frames the current code gets right** — it changes 9.7–19.7 % of
beacon frames and moves the emitted window count by −0.5 % to −11.3 %, so it
would move every published figure in the repo by an amount this session
cannot re-derive on 6.4 M frames.

---

## 1. Method, and the commands

Everything real-data below comes from one script. It is not added to the
repo — the brief permitted two files and this is not one of them — so it is
reproduced verbatim in §12 and is self-contained. From the repo root:

```
D=data/raw/d0wd_20260822_023034.csv
S=data/raw/s3_20260822_023034.csv

# the ambient source, both receivers
LC_ALL=C grep -a '1c:ce:51:f3:0d:fa' $S > /tmp/s3_1cce.csv
LC_ALL=C grep -a '1c:ce:51:f3:0d:fa' $D > /tmp/d0wd_1cce.csv

# six 40,000-row samples spread across each file, for the beacons
for f in $S $D; do sz=$(stat -c%s $f); for i in 1 2 3 4 5 6; do
    tail -c +$((sz*i/8)) $f | tail -n +2 | head -n 40000 \
        > /tmp/$(basename $f .csv)_c$i.txt
done; done

python3 /tmp/uwv/unwrap_defect_check.py      # the script in §12
python3 /tmp/uwv/candidates.py               # §8, the script in §12
python3 pc/test_rff_synth.py                 # test 9
```

**Sampling, stated plainly.** The beacon figures rest on 6 × 40,000 rows per
node — 479,705 fitted beacon frames against the 6,386,381 that
`docs/SEPARATION_SCALING.md` §1 counts in its window — cut at byte offsets
1/8 … 6/8 of each file, i.e. spread across the night rather than taken from
its head. **The 300 s ≤ t < 23,000 s window that the other documents use was
not applied**; the six offsets fall between roughly 12.5 % and 75 % of each
file, which is inside that window by construction, but nothing here re-checks
it row by row. That is enough to bound a per-frame rate to about ±0.03 % and
it is **not** the whole capture; §11 says so again.

**Why per-frame and not windowed.** The unit of the defect is one frame. The
64-frame median is the thing it has to get past, so both are reported: §6
gives the per-frame rate *and* the window count.

**The arbiter.** Every "is this answer right?" question below is settled by
the ramp that maximises `|Σ_k exp(j(φ_k − m·k))|` over m on a 0.0002 rad/sc
grid, using the **raw principal angles**. It never unwraps, so it cannot
inherit an unwrap error, and it is the natural estimator for a pure ramp
observed through unit-magnitude phases. It is **not** what `dsp.py` does and
it is not proposed as a replacement (§8, candidate E, is the cheap version of
it, and it is not clearly correct either).

**One methodological wrinkle that matters.** `FrameEstimator` carries a
single `np.random.default_rng` that advances frame to frame (`dsp.py:118`
used at `dsp.py:132`), so *which* frames turn out depends on where a frame
sits in the stream. The same 972 d0wd frames give a **6.07 %** turn-out rate
with a fresh `default_rng(3)` per frame and **6.58 %** through
`FrameEstimator`. Both are quoted below against the run that produced them;
neither should be read to three significant figures.

---

## 2. THE TRIGGER: node 68's subcarrier k = +1 is dead

`unwrap_defect_check.py`, section 2. 20,000 frames per node, all MACs,
from the first sample chunk.

| | s3 (node 108) | d0wd (node 68) |
|---|---|---|
| band median \|CSI\| | 12.6 counts | 20.0 counts |
| **k = +1 median \|CSI\|** | **14.3** | **3.0** |
| k = +1, 90th percentile | 16.3 | **3.0** |
| k = +1, fraction ≤ 4 counts | 2.6 % | **100.0 %** |
| bins below 40 % of the band median | **none** | **[+1]** |

**k = +1 on the d0wd is pinned at 3.0 counts in every frame examined**, on
every source, 6.7× below the band median. It is one bin out of 52 and it is
inside `dsp.py`'s static usable mask (`dsp.py:35`), which excludes DC and the
guard band because they are **exactly** zero (`dsp.py:26`). Three counts is
not exactly zero, so it survives the mask, and `np.angle` of it is noise.

What that does to the phase, same script, same chunks, beacons only:

| node / beacon | n | median \|Δφ\| across the k = −1 → +1 gap | fraction > 2.5 rad |
|---|---|---|---|
| s3 / B1 | 14,564 | 0.0918 | 0.00 % |
| s3 / B2 | 9,482 | 0.0991 | 0.00 % |
| s3 / B3 | 15,921 | 0.0647 | 0.00 % |
| **d0wd / B1** | 12,418 | **1.6065** | **20.63 %** |
| **d0wd / B2** | 12,243 | **1.6142** | **20.65 %** |
| **d0wd / B3** | 15,297 | **1.5708** | **20.46 %** |

A uniformly distributed phase difference exceeds 2.5 rad with probability
(π − 2.5)/π = **20.4 %**. Three cells measure 20.46, 20.63 and 20.65 %. The
k = +1 bin's phase is uniform, to within the precision of 12,000 frames, on
all three beacons. **It is the receiver, not the transmitter.**

### 2.1 Why the DC gap is where it hurts

`dsp.py:33-38` orders the 52 usable bins by physical k: −26 … −1, +1 … +26.
Adjacent entries are one subcarrier apart everywhere **except** across DC,
where they are two apart, so the model phase step there is twice as large and
`np.unwrap` has the least margin of any gap in the array. The dead bin sits
on the far side of exactly that gap.

All 58 breaks measured on the d0wd's `1c:ce` frames land in one of the two
gaps flanking k = +1 — **30 at k = −1 → +1 and 28 at k = +1 → +2**, none in
any of the other 49 gaps. On the s3, where that bin is healthy, the single
break in 954 frames lands at k = −16 → −15, nowhere near DC. That
distribution is what the dead bin predicts on
its own (a bad bin disturbs the gap on each side of it, roughly equally), so
the Δk = 2 geometry is **not needed** to explain where the break lands and
this pass did not separate the two effects. Test 9.2b shows a dead bin alone
on a flat channel needs the SNR down at **4 dB** before it fires at all,
which is the reason §5.2 calls the channel, not the gap and not the noise,
the thing that lets a straddling consensus win.

---

## 3. THE FAILURE PATH, IN ORDER

1. **`dsp.py:130`** takes `np.angle` of all 52 usable bins. Bin k = +1 on the
   d0wd returns a uniform random angle.
2. **`dsp.py:64`** runs `np.unwrap`. It corrects any adjacent difference
   exceeding π by ∓2π, cumulatively. An isolated bad bin usually produces a
   *spike* — a correction at the gap before it and the opposite correction at
   the gap after — which cancels. It fails to cancel when the true phase
   advance across the bad bin is large enough to push only one of the two
   gaps over π. A one-line model of that — the dead bin's phase is uniform,
   so exactly one gap wraps when it lands in a window of width equal to the
   phase advance across the bin — gives a rate of |slope| × Δk / 2π, i.e.
   **6.8 %** for `1c:ce` on the d0wd (slope −0.142, Δk = 3 across the dead
   bin). Measured: **6.07–6.58 %**. The model is a sanity check on the
   mechanism, not an independent measurement. When it fails to cancel, **every bin after
   the break sits 2π away from every bin before it.**
3. **`dsp.py:91-99`** draws 64 two-point hypotheses and keeps the one with
   the most inliers inside 0.30 rad. Two points drawn from *different*
   branches give a hypothesis slope offset by 2π/(their k separation). On a
   frequency-selective channel the correct branch does not have a large
   consensus to lose — RANSAC's 0.30 threshold captures only a locally
   straight arc of it — so a straddling line can win.
4. **`dsp.py:100-101`** refits least squares on the winning inliers. The
   inliers are on two branches, so the refit inherits the straddle.
5. **`dsp.py:103`** returns `resid_std` computed *on the inliers*, which are
   within 0.30 by construction, and `inlier_ratio`, which the straddle can
   make **larger** than the correct fit's. The estimate leaves the function
   looking clean.

Step 5 is why the failure is stable-wrong rather than noisy. On the d0wd's
`1c:ce` frames the turn-out fits carry median `inlier_ratio` **0.404**
against the correct fits' **0.365** — the wrong answer is the
*higher-quality* one by the pipeline's own measure. Tightening `min_inlier`
therefore enriches for it.

---

## 4. WHERE 2π/32 COMES FROM

`unwrap_defect_check.py`, section 3/4/5. `1c:ce:51:f3:0d:fa`, all frames that
`FrameEstimator` fitted, no gate.

| | s3 | d0wd |
|---|---|---|
| frames fitted | 954 | 972 |
| `dsp.py` median slope | +0.06152 | −0.14188 |
| median `inlier_ratio` | 0.577 | 0.365 |
| **arbiter** median slope | **+0.06401** | **−0.14009** |
| arbiter objective at the *other* node's median slope | 0.267 of peak | 0.251 of peak |
| … fraction of frames where that exceeds 0.9 | **0.0 %** | **0.0 %** |
| turn-outs (\|dsp − arbiter\| > 0.05) | 1 / 954 = **0.10 %** | 64 / 972 = **6.58 %** |
| frames where the branching changes the RANSAC slope | 1 | **58** |
| … median slope offset | −0.22058 | **+0.20494** |
| … sign | 0 up / 1 down | **58 up / 0 down** |
| … written as one turn | 2π/28.49 | **2π/30.66** |
| … **lever arm: separation of the two branch groups' inlier centroids** | 30.00 | **32.00 (IQR 31.50–32.50)** |
| `inlier_ratio`, correct frames → turn-out frames | 0.577 → 0.385 | **0.365 → 0.404** |

The two branch groups on the d0wd sit at k = −10.25 and k = +19.00. **32.00
is that separation**, and 2π/32 = 0.19635 against a measured +0.20494 (4.4 %
apart, which is what the difference between a two-group centroid and the full
least-squares weighting costs).

It is a per-frame geometric quantity and it varies:

| | lever arm | offset |
|---|---|---|
| d0wd, `1c:ce`, 58 real frames | 32.00 | 2π/30.66 |
| s3, `1c:ce`, 1 real frame | 30.00 | 2π/28.49 |
| synthetic, test 9.1, 73 frames | 30.5 | 2π/26.2 |
| **any span of the usable set** | ≤ 52 | ≥ 2π/52 = 0.1208 |

Nothing forces it to 32. It is 32 for this device on this receiver because
that is where the break lands and where the channel leaves RANSAC something
to lock onto on each side. **Quoting "2π/32" as the size of the defect is
quoting one draw.**

---

## 5. WHAT IT IS NOT — the candidates, ruled out by demonstration

The brief named three candidates. Two are ruled out and one is confirmed.

### 5.1 RULED OUT — `unwrap_continuity`'s temporal pinning (`dsp.py:65-67`)

`turns = round((ph.mean() − prev_mean) / 2π)` followed by `ph −= turns·2π` is
a **uniform additive shift** of the whole frame. `ransac_line`'s two-point
hypotheses shift their intercept and not their slope, every residual is
unchanged, the inlier set is identical, and the least-squares refit returns
the identical slope. `cfo_hz` is then computed through
`np.angle(np.exp(1j·Δ))` at `dsp.py:142`, which is 2π-invariant. So the
pinning cannot reach either published output.

Demonstrated on all 972 d0wd `1c:ce` frames by running the estimator three
ways — as shipped, with `_prev_mean` forced to `None` every frame, and with
it sabotaged by +17 turns every frame:

| quantity | shipped vs never pinned | shipped vs sabotaged by 17 turns/frame |
|---|---|---|
| max \|Δ slope\| | 2.08e-15 | 2.13e-12 |
| max \|Δ cfo_hz\| | 5.88e-13 | 7.84e-10 |
| max \|Δ intercept\| | 8.80e+01 | 1.04e+05 (= 16,524 turns) |

The intercept moves by sixteen thousand turns and the slope and CFO move by
float noise. **The entire `prev_mean` branch is inert for every value the
estimator returns.** (Script in §12.2. It is not a defect on its own — but
`dsp.py:56-62`'s docstring says the pinning exists "so the intercept
time-series is differentiable instead of saw-toothed", and no consumer of
`intercept` other than `dsp.py:142` exists in `pc/`, so the code does nothing
that anything reads.)

### 5.2 RULED OUT — noise, as the trigger

Test 4 already establishes that the estimator degrades gracefully and then
goes silent under AWGN. Test 9.2b sweeps SNR with the dead bin present and a
flat channel:

| band SNR | 25 | 15 | 10 | 8 | 6 | **4** | 2 | 0 dB |
|---|---|---|---|---|---|---|---|---|
| turn-out rate | 0.00 % | 0.00 % | 0.00 % | 0.00 % | 0.00 % | **0.25 %** | 2.17 % | 6.65 % |

**It starts at 4 dB and is still under 7 % at 0 dB.** Meanwhile test 9.1
fires at **4.95 % at 25 dB** with a frequency-selective channel. The real
source that produced this whole investigation sits at **RSSI −34 to −36 dBm**
— among the strongest signals in the capture — and fires at 6.58 %.
**It is not an SNR failure.** SNR is one way to weaken the correct branch's
consensus; a frequency-selective channel is a much more effective one, and
that is what the field supplies.

### 5.3 CONFIRMED — RANSAC building a consensus across the break

Test 9.1, with the injected slope as ground truth and a channel built with
two echoes at −τ and +τ so its mean group delay is zero and the injected
slope stays the right answer:

| dead bin at k = +1 | frames | median slope | \|err\| on the right frames | turn-outs |
|---|---|---|---|---|
| yes | 1,476 | +0.14188 | 0.00113 | **73 (4.95 %)** |
| no | 1,499 | +0.14194 | 0.00104 | **0 (0.00 %)** |

Same channel, same SNR, same seed. Refit those same 73 frames with the same
RANSAC and the same seed, changing only the branching — every bin forced onto
one branch around the known slope instead of `np.unwrap`'s serial choice —
and the median \|error\| falls from **0.23959 to 0.00192 rad/sc**, i.e. the
branching accounts for **99.2 %** of it. 73 of 73 have their winning
consensus split across two or more branches.

---

## 6. DOES IT TOUCH THE BEACONS? — no

`unwrap_defect_check.py`, section 3. Shipped configuration:
`FrameEstimator(rng_seed=0)` → `WindowAggregator(64, 0.6, 0.8)`.

| node / beacon | frames | windows | turn-outs (per frame) | **windows within 10 % of 2π/32 of that beacon's own median** |
|---|---|---|---|---|
| s3 / B1 | 85,354 | 1,325 | 1 (0.0012 %) | **0** |
| s3 / B2 | 56,238 | 872 | 9 (0.0160 %) | **0** |
| s3 / B3 | 98,306 | 1,530 | 0 (0.0000 %) | **0** |
| d0wd / B1 | 71,502 | 1,044 | 25 (0.0350 %) | **0** |
| d0wd / B2 | 73,918 | 1,109 | 14 (0.0189 %) | **0** |
| **d0wd / B3** | 94,387 | 635 | **4,326 (4.5833 %)** | **0** |
| total | **479,705** | **6,515** | 4,375 | **0** |

**Stated plainly: it never fires on the beacons in a way that reaches a
published number.** Not one of 6,515 windows sits a turn away from its own
source's median. The published beacon figures —
`docs/SEPARATION_SCALING.md`'s 0.69σ / 3.72σ / 4.68σ, its Allan curves,
`docs/AMBIENT_SEPARATION.md`'s 2.94 / 0.69 / 3.63σ reproduction, the twin
ΔSFO of 0.00080 and 0.00118 — **are unaffected by this defect.** What is
compromised is the ambient work, where the unit of observation is a single
frame (`docs/AMBIENT_SEPARATION.md` §1, forced by 20-to-932-frame sources)
and a 6 % contamination is a 6 % contamination.

**The one cell worth flagging is d0wd/B3 at 4.58 %.** That is the cell whose
59.5 % reject rate and +0.0707-against-+0.0150 offset
`docs/SEPARATION_SCALING.md` §3.2 and `docs/OVERNIGHT_2026-08-22.md` §3.4
both exclude as an unexplained "estimator-bias artefact". This pass supplies
part of an explanation — 4.58 % of its frames are genuinely a turn out — and
**does not supply enough of one**: 4.58 % of frames cannot move a median by
0.056 rad/sc, so most of that cell's offset is still unexplained.

---

## 7. DETECTION

The pipeline needs something it can compute per frame that says "this
estimate may be a turn out". Four candidates were measured.

| candidate | verdict |
|---|---|
| `resid_std` | **useless.** Computed on the inliers, which are inside 0.30 rad by construction. Test 9.2: worst turn-out `resid_std` **0.211** against `max_resid = 0.8`. It flags none of them, and `docs/SEPARATION_SCALING.md` §4.1 already records the gate rejecting 0 of 6,386,119 frames. |
| `inlier_ratio` | **useless, and worse than useless.** Its sign is not stable: turn-outs sit at 0.250 against 0.481 in the synthetic and at **0.404 against 0.365** on the d0wd's real frames. On real data, tightening the gate *enriches* for them. |
| inlier-set straddle test | **fails on real data.** Detecting whether the winning inliers span an `np.unwrap` correction gives 5.1 % recall at a 92.99 % false-positive rate on the d0wd, because an isolated bad bin produces two cancelling corrections in almost every frame. |
| **branch-invariant coherence C** | **works.** See below. |

```
C = | sum_k exp( j * ( phase_k - (slope*k + intercept) ) ) | / 52
```

over all 52 usable bins, `phase_k` being the raw principal angles — not the
unwrapped ones — and `slope`, `intercept` the values `ransac_line` already
returns. 52 complex exponentials per frame; no grid search, no FFT, no new
constant except the threshold.

It is branch-invariant by construction (`exp(j·2π) == 1`), so it cannot be
measuring the unwrap; a fit that is one turn out over the band leaves a
residual that ramps through several turns and the sum cancels.

| population | C, correct fits | C, turn-outs | **C < 0.5: recall** | **false-positive rate** |
|---|---|---|---|---|
| synthetic, test 9.3 (1,403 / 73) | 0.763 (p1 0.602) | 0.055 (p99 0.279) | **100.0 %** | **0.00 %** |
| s3, `1c:ce` (953 / 1) | 0.934 | 0.020 | 100.0 % | 0.00 % |
| d0wd, `1c:ce` (908 / 64) | 0.794 | 0.129 | **92.2 %** | **0.00 %** |

On the 479,705 real beacon frames, as a false-alarm test:

| node / beacon | flagged C < 0.5 | of which genuinely wrong |
|---|---|---|
| s3 / B1 | 0 (0.000 %) | 0 |
| s3 / B2 | 13 (0.023 %) | 7 |
| s3 / B3 | 0 (0.000 %) | 0 |
| d0wd / B1 | 15 (0.021 %) | 12 |
| d0wd / B2 | 13 (0.018 %) | 7 |
| d0wd / B3 | 2,458 (2.604 %) | 2,029 |

A healthy cell is flagged at 0.000–0.023 %. d0wd/B3 is flagged at 2.6 %, and
2,029 of those 2,458 are independently confirmed wrong by the arbiter. **The
detector is a cell-health monitor as much as a per-frame flag**, and it
identifies the one beacon cell the repo already knew was broken without being
told. Its **precision on the beacons is 54 % to 83 %**, not 100 %: 7 of 13 in
s3/B2, 12 of 15 in d0wd/B1, 7 of 13 in d0wd/B2, 2,029 of 2,458 in d0wd/B3.
It over-flags, on a population where over-flagging costs almost nothing.

**What it does not do.** It does not tell you the right answer, only that
this one is suspect. It is a *proposal*, validated on 480,000 real frames and
one synthetic population, and it has not been run on the whole 6.4 M-frame
capture. Nothing was added to `pc/rff/dsp.py` to compute it (§8).

---

## 8. THE FIX — why there isn't one

Five repairs were built and measured against the arbiter, on the same 954 and
972 `1c:ce` frames, with a fresh `default_rng(3)` per frame so the RANSAC
draws are identical across candidates (`candidates.py`, §12.3). Turn-out rate
is `|slope − arbiter| > 0.05`.

| | what it does | s3 | **d0wd** |
|---|---|---|---|
| — | **current `np.unwrap`** | 0.10 % | **6.07 %** |
| A | rebranch about a one-lag circular-mean anchor (phase only) | 0.10 % | **13.17 %** |
| B | rebranch about a one-lag anchor, amplitude-weighted | 8.91 % | **83.13 %** |
| C | drop bins under 25 % of the frame's median \|CSI\| | 0.10 % | **8.54 %** |
| D | fit only inside the longest run with no `np.unwrap` correction | 5.14 % | **63.27 %** |
| E | rebranch about a zero-padded-FFT anchor, length 64 | 0.00 % | 10.80 % (2 frames lose their fit) |
| E | … length 256 | 0.00 % | 1.65 % |
| E | … length 1024 | 0.00 % | **1.03 %** |

**A, B, C and D are all worse than doing nothing.** C is the one that looks
most obviously right — the trigger *is* a bin at 3 counts, so mask it — and
it makes things worse, because removing k = +1 widens the DC gap to Δk = 3
and the 0.25 threshold also deletes real bins in the channel's fades. D fails
because the "longest run with no correction" is median 33 of 52 bins on the
d0wd and 47 of 52 on the s3: throwing away a third of the band costs more
than the branch error does. B fails because the amplitude-weighted anchor is
dominated by the strong low-k half and lands far enough off that the rebranch
locks the fit onto the wrong ramp.

**E is a mitigation, not a repair, and it is not clearly correct.**

1. It never reaches zero: 1.03 % against 6.07 %, so five of six, not six of
   six.
2. Its benefit depends on a tuning constant it has no principled value for —
   10.80 %, 1.65 %, 1.03 % at FFT lengths 64, 256, 1024 — and at length 64 it
   is worse than doing nothing *and* loses two frames' fits entirely.
3. **It is not a no-op on the frames the current code gets right.** Measured
   on the beacon samples (`impact` run, FFT length 1024):

   | node / beacon | frames changed | windows before → after | window median SFO shift |
   |---|---|---|---|
   | s3 / B1 | 9.83 % | 1,325 → 1,304 | −2.1e-05 |
   | s3 / B2 | 10.45 % | 872 → 854 | +3.7e-06 |
   | s3 / B3 | 9.65 % | 1,530 → 1,508 | +4.1e-05 |
   | d0wd / B1 | 14.34 % | 1,046 → 1,026 | −3.1e-04 |
   | d0wd / B2 | 13.80 % | 1,108 → 1,102 | −1.4e-04 |
   | d0wd / B3 | **19.75 %** | 636 → **564** | −3.7e-04 |

   (Procedure: the same six sampled chunks, each frame fitted twice —
   `ransac_line` on `np.unwrap(phase)` and on the rebranched phase — and both
   results pushed through their own `WindowAggregator(64, 0.6, 0.8)`. The
   window counts differ by one or two from §6's because that run gives RANSAC
   a fresh `default_rng(3)` per frame instead of `FrameEstimator`'s advancing
   one; the before/after pairs in the table come from the same run and are
   internally consistent.)

   It moves ten to twenty per cent of frames, drops 0.5–11.3 % of emitted
   windows, and shifts d0wd/B3's window median by 0.16 × `BETWEEN_UNIT_SD`.
   Every SFO number in `docs/SEPARATION_SCALING.md`,
   `docs/AMBIENT_SEPARATION.md`, `docs/OVERNIGHT_2026-08-22.md` and
   `docs/S3_SFO_STEPS.md` would have to be re-derived on 6.39 M frames to
   know what it actually did, and this session sampled 480,000.
4. It introduces a failure mode the current code does not have. The anchor is
   the argmax of the zero-padded IDFT of the unit-magnitude phases — the
   strongest *delay tap* of the phase-only channel. On a channel where an
   echo is stronger than the direct path, the anchor is the echo, and RANSAC
   is then confined to ±π about it. This pass did not bound how often that
   happens. It did measure, on this very source, that the arbiter's objective
   has a **second peak 0.395 rad/sc away at 0.31 (s3) and 0.50 (d0wd) of the
   main peak's height** — i.e. the channel has a competing tap of comparable
   strength, and how often the wrong one wins was not established.
5. It is not a fix to a bug in a line of code. It replaces the estimator's
   definition of "which branch each subcarrier is on". That is a change to
   what `dsp.py` *is*, and the brief's standing instruction is not to make
   one speculatively.

**And the thing being fixed is a hardware fault.** §2 establishes that
node 68's k = +1 subcarrier is dead on every source it hears. A software
change that tolerates a dead bin also **hides** it, and this is the first
artifact in the repo that identifies it. The right first move is to find out
why that bin is at 3 counts — a board fault, a firmware CSI-buffer bug, or an
antenna/front-end problem — not to make the DSP robust to it.

**So `pc/rff/dsp.py` is unchanged, and test 9's last verdict FAILs against
it.** That is deliberate and it is the file's own convention (test 5's
smooth-multipath verdict already fails the same way). Fix `dsp.py` and it
turns green; §9.1 records the exact before-state so the change is measurable.

---

## 9. WHAT WAS ADDED TO `pc/test_rff_synth.py`

Test 9, `t9_one_turn`, and four helpers: `sym_two_ray`, `ransac_inliers` (a
verbatim copy of `dsp.ransac_line` that also returns the inlier mask, which
dsp does not expose), `fit_coherence` (the §7 detector) and `_t9_run`.

### 9.1 The suite before and after

| | before | after |
|---|---|---|
| verdicts `[ok]` | 21 | **25** |
| verdicts `[FAIL]` | 1 | **2** |
| runtime | 21.0 s | 21.7 s |
| printed output of tests 0–8 | — | **byte-identical** (`diff` clean) |

The pre-existing FAIL is test 5's `on smooth two-ray multipath RANSAC is
2.06x least squares`, unchanged. The new FAIL is test 9's last verdict, which
is the defect (§8).

### 9.2 A defect in the test file, found on the way, and not fixed

`two_ray` (`pc/test_rff_synth.py:148-154`) builds its channel indexed by `K`,
sorted −26 … +26. `make_frame` (`:119-121`) applies `channel` to `h`, which
is indexed in **FFT order**, +1 … +26, −26 … −1. **They are different
orders**, so the channel test 5(c)/(d) actually injects is a shuffled version
of the two-ray channel it writes down, and is not smooth.

Measured both ways, test 5(d)'s statistic (median |err| RANSAC ÷ polyfit,
ρ = 0.70, τ = 0.020, 400 trials):

| | RANSAC | polyfit | ratio |
|---|---|---|---|
| as shipped (channel on sorted K) | 3.659e-02 | 1.777e-02 | **2.06×** |
| channel built in the order it is applied | 4.155e-02 | 1.503e-02 | **2.76×** |

**Test 5's conclusion is unchanged** — RANSAC still loses to least squares on
a smooth channel, by more rather than less — so test 5 was left exactly as it
stands rather than silently re-baselined. Test 9 builds its own channel in
FFT order and says so in its output. **This should be fixed by whoever next
touches test 5, and doing so will change test 5(d)'s printed numbers.**

---

## 10. Established / permitted / unknown

**Established by this pass, from these files:**

- On node 68 (`d0wd`), subcarrier **k = +1 has |CSI| = 3.0 counts in 100.0 %
  of 20,000 frames** across all MACs, against a band median of 20.0; it is
  the only bin below 40 % of the band median. On node 108 (`s3`) the same bin
  reads 14.3 against a band median of 12.6 and no bin is below 40 %. §2.
- That bin's phase is uniform: the wrapped step across the k = −1 → +1 gap
  exceeds 2.5 rad in **20.46 %, 20.63 % and 20.65 %** of frames for the three
  beacons on the d0wd, against the **20.4 %** a uniform phase predicts, and
  in **0.00 %** on the s3. §2.
- `np.unwrap` at `dsp.py:64` fails to cancel that bin's disturbance in
  **6.07–6.58 %** of the d0wd's `1c:ce:51:f3:0d:fa` frames and **0.10 %** of
  the s3's; when it fails, RANSAC's winning consensus straddles the break in
  **58 of 58** cases and the fitted slope moves by **+0.20494 rad/sc,
  median, in the same direction every time**. §4.
- The two branch groups' inlier centroids in those 58 frames sit at
  k = −10.25 and k = +19.00, **32.00 subcarriers apart, IQR 31.50–32.50**.
  That is the whole source of `docs/AMBIENT_SEPARATION.md` §5's 2π/32. §4.
- The lever arm is not a constant: 32.00 here, 30.00 on the s3's one affected
  frame, 30.5 in the synthetic reproduction, whose offset is 2π/26.2. §4.
- The turn-out fits carry a **higher** `inlier_ratio` than the correct ones on
  real data (0.404 vs 0.365) and a **lower** one in the synthetic
  (0.250 vs 0.481). The residual gate flags **none** of them: worst turn-out
  `resid_std` 0.211 against `max_resid` 0.8. §7.
- An arbiter that never unwraps puts the d0wd's median for this source at
  **−0.14009** against `dsp.py`'s −0.14188, and its objective at the s3's
  median slope reaches 0.9 of that frame's own peak in **0.0 %** of frames
  (and symmetrically). **The cross-receiver disagreement is real, and
  §5's identification of which mode is the artefact is backwards.** §0, §4.
- Over **479,705** beacon frames and **6,515** windows on both nodes,
  **zero** windows sit within 10 % of 2π/32 of their own source's median.
  Per-frame turn-out rates: 0.0000–0.0160 % (s3), 0.0189 % and 0.0350 %
  (d0wd B1, B2), **4.5833 %** (d0wd B3). §6.
- `unwrap_continuity`'s `prev_mean` pinning (`dsp.py:65-67`) cannot affect
  `slope` or `cfo_hz`: sabotaging it by 17 turns every frame moves
  `intercept` by 16,524 turns and moves slope and CFO by 2.1e-12 and 7.8e-10.
  §5.1.
- With a flat channel and the dead bin present, the failure needs **4 dB**
  SNR before it fires at all (0.25 %, rising to 6.65 % at 0 dB); with a
  frequency-selective channel it fires at **4.95 % at 25 dB**. §5.2.
- In the synthetic case with ground truth, refitting the affected frames with
  the branching forced onto one branch and nothing else changed removes
  **99.2 %** of the error. §5.3.
- `C < 0.5` gives **100 % recall at 0.00 % false positives** on the synthetic
  population, **92.2 % at 0.00 %** on the d0wd's real frames, and flags
  0.000–0.023 % of frames in five of six beacon cells against **2.604 %** in
  d0wd/B3, where 2,029 of 2,458 flags are independently confirmed wrong. §7.
- Four of five candidate repairs are worse than doing nothing (13.17 %,
  83.13 %, 8.54 %, 63.27 % against 6.07 %); the fifth reaches 1.03 % but
  changes 9.7–19.7 % of beacon frames and drops 0.5–11.3 % of windows. §8.
- `pc/test_rff_synth.py`'s `two_ray` is built on a different subcarrier
  ordering than `make_frame` applies it in; correcting it moves test 5(d)'s
  ratio from 2.06× to 2.76× and does not change its conclusion. §9.2.

**Permitted but not established:**

- That the Δk = 2 DC gap (`dsp.py:33-38`) contributes to *where* the break
  lands, as distinct from the dead bin causing it. Every one of the 58 breaks
  on the d0wd's `1c:ce` frames lands in one of the two gaps flanking k = +1
  — **30 at the k = −1 → +1 gap and 28 at the k = +1 → +2 gap**, none
  anywhere else in the 51 gaps — which is what the dead bin predicts on its
  own, so the DC gap's extra width is not needed to explain it and was not
  separated from it.
- That the other large ambient cross-receiver disagreements
  (`docs/AMBIENT_SEPARATION.md` §5's `ba:80` at 27.2× and `bc:96` at 19.4×
  `BETWEEN_UNIT_SD`) have the same cause. Only `1c:ce:51:f3:0d:fa` was
  examined this way, exactly as §5 itself cautions.
- That node 68's dead k = +1 bin is a hardware fault rather than a firmware
  or CSI-buffer artefact. It is present on every source and in 100 % of
  frames sampled, which rules out the channel; nothing here rules between
  the remaining causes.
- That candidate E would be an improvement overall. It is better on the one
  ambient source measured and its effect on 6.39 M beacon frames was
  sampled, not computed.
- That d0wd/B3's +0.0707-against-+0.0150 offset is caused by this defect.
  4.58 % of its frames are turn-outs; that is 4.58 %, not 0.056 rad/sc.

**Unknown, and not addressed:**

- Whether the whole capture behaves like the 6 × 40,000-row samples. The
  beacon figures rest on 479,705 of 6.39 M frames.
- Whether the s3 has a dead bin at any other subcarrier, or the d0wd has more
  than one, outside the sampled chunks. §2 checked one chunk per node.
- Why the k = +1 bin reads exactly 3.0 counts. No firmware or hardware check
  was made; `docs/HANDOFF.md`'s gotchas were not exercised and no serial port
  was opened.
- Whether a branch-invariant estimator (the §1 arbiter, or candidate E at a
  sufficient FFT length) would change any published conclusion. It would
  change the numbers; nothing here says by how much on the full capture.
- What the correct SFO for `1c:ce:51:f3:0d:fa` is. Both receivers are
  reporting their own received phase ramp correctly and they disagree by
  0.203 rad/sc; `docs/AMBIENT_SEPARATION.md` §7's "whether the slope's
  timing-offset component can be separated from its sampling-frequency
  component" remains exactly as open as it was.

---

## 11. Figures in this document that should not be quoted alone

- **"6.07 %"** and **"6.58 %"**. Same 972 frames, same code; they differ
  because `FrameEstimator`'s RNG advances frame to frame (`dsp.py:118,132`),
  so which frames turn out depends on stream position. The stable claim is
  "about 6 %", and it is one source on one night.
- **"2π/32"**. It is a per-frame lever arm that measured 32.00 for this
  device on this receiver and 26–30 elsewhere. Do not treat 32 as a property
  of the estimator or of the 52-subcarrier band. §4.
- **"4.58 % on d0wd/B3"**. It is a real per-frame rate and it explains none
  of that cell's 0.056 rad/sc offset. §6.
- **The beacon rates generally.** Six 40,000-row samples per node, 479,705
  of 6.39 M frames. §1.
- **The candidate-repair table in §8.** One ambient source, 1,926 frames
  across two receivers. Candidate E's beacon impact is from the same six
  sampled chunks, not the capture.
- **The detector's "0.00 % false-positive rate".** Measured at a threshold of
  0.5 on three populations, one of which is synthetic. On the beacons its
  *precision* is **54 % to 83 %**, not 100 % — 7 of 13 flags in s3/B2, 2,029
  of 2,458 in d0wd/B3. It over-flags. §7.
- **Anything about node 68's k = +1 bin as a "hardware fault".** What is
  measured is 3.0 counts in 100 % of 20,000 frames. The cause is unknown.

---

## 12. What would settle the rest, and the scripts

1. **Look at node 68's k = +1 bin on the hardware.** It is the single
   highest-value action here and it is not a software task. If that bin is
   dead on the board, every ambient number the d0wd has ever contributed
   inherits a 6 %-ish contamination and the fix is a soldering iron or a
   firmware patch, not a DSP change.
2. **Run the §7 detector over the whole capture, both nodes, every source.**
   It is 52 complex exponentials per frame and it needs no new state. That
   turns "about 6 % on one source" into a census, and it answers
   `docs/AMBIENT_SEPARATION.md` §9.2's outstanding item directly.
3. **Re-run `docs/AMBIENT_SEPARATION.md`'s ambient matrices with C < 0.5
   frames dropped.** Its §5 conclusion is unaffected but its §4 numbers are
   built per-frame on sources whose median `inlier_ratio` is 0.365, i.e.
   exactly the population this defect lives in.
4. **Correct `two_ray`'s ordering in `pc/test_rff_synth.py` and re-baseline
   test 5.** §9.2.
5. **Decide candidate E on the full capture, not on samples.** §8 lists the
   four things that would have to be measured first.

### 12.1 `unwrap_defect_check.py` — every real-data figure above

Placed outside the repo (`/tmp/uwv/`), because the brief allowed two repo
files and this is not one of them. Setup commands are in §1.

```python
#!/usr/bin/env python3
"""Regenerates every real-data figure in docs/UNWRAP_DEFECT.md."""
import csv, glob, sys, numpy as np
sys.path.insert(0, 'pc')
from rff import dsp

K = dsp.K_USABLE.astype(np.float64)
IDX = dsp._USABLE_IDX
HDR = ("pc_time_us,label,seq,mac,rssi,noise_floor,channel,esp_timestamp_us,"
       "len,csi_data,node_id,env_id,dropped").split(",")
BE = {"a4:f0:0f:77:91:20": "B1", "28:05:a5:2f:fa:48": "B2",
      "f4:2d:c9:70:72:30": "B3"}
TURN32 = 2 * np.pi / 32
MG = np.arange(-np.pi, np.pi, 0.0002)          # the branch-invariant arbiter
EXP = np.exp(-1j * np.outer(MG, K))
MB = np.arange(-0.6, 0.6, 0.0005)              # coarse grid, beacon slopes
EXPB = np.exp(-1j * np.outer(MB, K))


def rows(path, macs=None):
    """A real CSV reader. `csi_data` is a quoted comma-separated list inside
    the CSV, so a 128-value row splits into 140 fields on a naive comma
    split -- which is why pc/exp_overnight_0822.py:303 and
    pc/exp_s3_sfo_steps.py:153,590 drop every 128-length row."""
    out = []
    with open(path, newline='') as f:
        for r in csv.reader(f):
            if len(r) != 13:
                continue
            d = dict(zip(HDR, r))
            if macs and d["mac"] not in macs:
                continue
            v = np.fromstring(d["csi_data"], sep=",")
            if v.size < 128:
                continue
            out.append((int(d["pc_time_us"]), d["mac"], int(d["rssi"]),
                        int(d["esp_timestamp_us"]), v))
    out.sort(key=lambda t: t[0])
    return out


def ph_of(v):
    return np.angle(dsp.csi_to_complex(v)[IDX])


def ransac_inl(x, y, rng):
    """dsp.ransac_line (pc/rff/dsp.py:71-103) verbatim + the inlier mask."""
    n = x.size
    i, j = rng.integers(0, n, 64), rng.integers(0, n, 64)
    ok = x[i] != x[j]
    i, j = i[ok], j[ok]
    m = (y[j] - y[i]) / (x[j] - x[i])
    b = y[i] - m * x[i]
    res = np.abs(y[None, :] - (m[:, None] * x[None, :] + b[:, None]))
    c = (res < 0.30).sum(1)
    best = int(np.argmax(c))
    bc = int(c[best])
    if bc < max(4, n // 4):
        return None
    inl = res[best] < 0.30
    A = np.column_stack([x[inl], np.ones(bc)])
    (mf, bf), *_ = np.linalg.lstsq(A, y[inl], rcond=None)
    r = y[inl] - (mf * x[inl] + bf)
    return float(mf), float(bf), bc / n, float(r.std()), inl


def arbiter(ph):
    """(slope, intercept, objective) of the branch-invariant best ramp."""
    z = np.exp(1j * ph)
    j = np.abs(EXP @ z)
    m = float(MG[int(np.argmax(j))])
    b = float(np.angle(np.sum(z * np.exp(-1j * m * K))))
    return m, b, j


def coherence(ph, m, b):
    return float(np.abs(np.sum(np.exp(1j * (ph - (m * K + b))))) / K.size)


print("SECTION 2 -- the hardware trigger: median |CSI| per subcarrier")
for tag in ("s3", "d0wd"):
    A = []
    for p in sorted(glob.glob(f"/tmp/{tag}_2026*_c1.txt")):
        for *_, v in rows(p):
            A.append(np.abs(dsp.csi_to_complex(v)[IDX]))
            if len(A) >= 20000:
                break
    A = np.array(A)
    med = np.median(A, axis=0)
    dead = [int(K[i]) for i in np.where(med < 0.4 * np.median(med))[0]]
    print(f"  {tag}: n={A.shape[0]} frames, all MACs.  band median |CSI| "
          f"{np.median(med):.1f} counts;  k=+1 median {med[26]:.1f}, "
          f"p90 {np.percentile(A[:, 26], 90):.1f}, "
          f"frac<=4 counts {100 * np.mean(A[:, 26] <= 4):.1f}%")
    print(f"        bins below 40% of the band median: {dead}")

print("SECTION 2 -- what that does to the phase step at the DC gap")
for tag in ("s3", "d0wd"):
    for p in sorted(glob.glob(f"/tmp/{tag}_2026*_c1.txt")):
        D = {m: [] for m in BE}
        for _, mac, _, _, v in rows(p, BE):
            a = ph_of(v)
            D[mac].append(np.angle(np.exp(1j * (a[26] - a[25]))))
        for m, name in BE.items():
            d = np.abs(np.array(D[m]))
            print(f"  {tag} {name}: n={d.size}  |dphi| across the k=-1 -> +1 "
                  f"gap: median {np.median(d):.4f} rad, frac>2.5 "
                  f"{100 * np.mean(d > 2.5):.2f}%   "
                  f"(a uniform phase gives (pi-2.5)/pi = 20.4%)")

print("SECTION 3/4/5 -- 1c:ce:51:f3:0d:fa, both receivers")
for tag, path in (("s3", "/tmp/s3_1cce.csv"), ("d0wd", "/tmp/d0wd_1cce.csv")):
    rr = [r for r in rows(path) if r[1] == "1c:ce:51:f3:0d:fa"]
    est = dsp.FrameEstimator(rng_seed=0)
    sl, ir, pk, ratio_other, C = [], [], [], [], []
    off, lev, ir_to, ir_ok = [], [], [], []
    other = 0.06152 if tag == "d0wd" else -0.14196
    io = int(round((other + np.pi) / 0.0002))
    for _, _, _, ets, v in rr:
        e = est.feed(v, ets)
        if e is None:
            continue
        ph = ph_of(v)
        m0, b0, j = arbiter(ph)
        sl.append(e["slope"])
        ir.append(e["inlier_ratio"])
        pk.append(m0)
        ratio_other.append(j[io - 300:io + 300].max() / j.max())
        f = ransac_inl(K, np.unwrap(ph), np.random.default_rng(3))
        C.append(coherence(ph, f[0], f[1]) if f else np.nan)
        ref = m0 * K + b0 + np.angle(np.exp(1j * (ph - (m0 * K + b0))))
        w = np.round((np.unwrap(ph) - ref) / (2 * np.pi)).astype(int)
        g = ransac_inl(K, ref, np.random.default_rng(3)) if f else None
        if g is not None and abs(f[0] - g[0]) > 1e-9:
            off.append(f[0] - g[0])
            wi = w[f[4]]
            if wi.max() != wi.min():
                lev.append(np.mean(K[f[4]][wi == wi.max()])
                           - np.mean(K[f[4]][wi == wi.min()]))
            ir_to.append(f[2])
        elif f:
            ir_ok.append(f[2])
    sl, ir, pk = np.array(sl), np.array(ir), np.array(pk)
    C, ro = np.array(C), np.array(ratio_other)
    C = np.where(np.isnan(C), 1.0, C)      # unfitted frames cannot be flagged
    d = np.abs(sl - pk)
    print(f"  {tag}: {sl.size} frames fitted")
    print(f"     dsp median slope {np.median(sl):+.5f}   median inlier_ratio "
          f"{np.median(ir):.3f}")
    print(f"     branch-invariant arbiter, median peak {np.median(pk):+.5f}; "
          f"its value at the OTHER receiver's median slope ({other:+.5f}) is "
          f"{np.median(ro):.3f} of this frame's own peak, frac>0.9 "
          f"{100 * np.mean(ro > 0.9):.1f}%")
    print(f"     turn-outs (|dsp - arbiter| > 0.05): {int((d > 0.05).sum())} "
          f"/ {sl.size} = {100 * np.mean(d > 0.05):.2f}%")
    off = np.array(off)
    if off.size:
        print(f"     frames where np.unwrap changes the RANSAC slope: "
              f"{off.size}; offset median {np.median(off):+.5f} rad/sc, "
              f"sign +{int((off > 0).sum())}/-{int((off < 0).sum())}, "
              f"= 2pi/{2 * np.pi / abs(np.median(off)):.2f}")
        lev = np.array(lev)
        print(f"     lever arm (separation of the two branch groups' inlier "
              f"centroids): median {np.median(np.abs(lev)):.2f}, IQR "
              f"{np.percentile(np.abs(lev), 25):.2f}"
              f"..{np.percentile(np.abs(lev), 75):.2f} subcarriers")
        print(f"     inlier_ratio: correct frames {np.median(ir_ok):.3f}, "
              f"turn-out frames {np.median(ir_to):.3f}")
    bad = d > 0.05
    print(f"     detector C: correct median {np.median(C[~bad]):.3f}, "
          f"turn-out median "
          f"{np.median(C[bad]) if bad.any() else float('nan'):.3f}"
          f";  C<0.5 recall "
          f"{100 * np.mean(C[bad] < 0.5) if bad.any() else 0:.1f}% "
          f"FPR {100 * np.mean(C[~bad] < 0.5):.2f}%")

print("SECTION 3 -- does it touch the beacons?")
for tag in ("s3", "d0wd"):
    est = {m: dsp.FrameEstimator(rng_seed=0) for m in BE}
    agg = {m: dsp.WindowAggregator(64, 0.6, 0.8) for m in BE}
    S = {m: [] for m in BE}
    P = {m: [] for m in BE}
    W = {m: [] for m in BE}
    Cs = {m: [] for m in BE}
    for p in sorted(glob.glob(f"/tmp/{tag}_2026*_c?.txt")):
        for pc, mac, rssi, ets, v in rows(p, BE):
            e = est[mac].feed(v, ets)
            if e is None:
                continue
            ph = ph_of(v)
            S[mac].append(e["slope"])
            P[mac].append(ph)
            f = ransac_inl(K, np.unwrap(ph), np.random.default_rng(3))
            Cs[mac].append(coherence(ph, f[0], f[1]) if f else np.nan)
            w = agg[mac].feed(e, pc, float(rssi))
            if w:
                W[mac].append(w["sfo"])
    for m, name in BE.items():
        s = np.array(S[m])
        ww = np.array(W[m])
        c = np.array(Cs[m])
        if not s.size:
            continue
        pkb = np.empty(s.size)
        A = np.array(P[m])
        for a in range(0, s.size, 4000):
            pkb[a:a + 4000] = MB[np.argmax(
                np.abs(np.exp(1j * A[a:a + 4000]) @ EXPB.T), axis=1)]
        d = np.abs(s - pkb)
        wn = (np.abs(np.abs(ww - np.median(ww)) - TURN32) < 0.1 * TURN32)
        print(f"  {tag} {name}: {s.size} frames, {ww.size} windows;  "
              f"turn-outs {int((d > 0.05).sum())} "
              f"({100 * np.mean(d > 0.05):.4f}%);"
              f"  windows within 10% of 2pi/32 of own median: {int(wn.sum())}"
              f";  detector C<0.5 flags {int((c < 0.5).sum())} "
              f"({100 * np.mean(c < 0.5):.3f}%), of which genuinely wrong "
              f"{int(((c < 0.5) & (d > 0.05)).sum())}")
```

### 12.2 §5.1's demonstration that `prev_mean` is inert

```python
import sys, numpy as np
sys.path.insert(0, 'pc')
from rff import dsp
exec(open('/tmp/uwv/unwrap_defect_check.py').read().split('print("SECTION')[0])

rr = [r for r in rows("/tmp/d0wd_1cce.csv") if r[1] == "1c:ce:51:f3:0d:fa"]
a = dsp.FrameEstimator(rng_seed=0)

class NoPin(dsp.FrameEstimator):
    def feed(self, v, ts):
        self._prev_mean = None                       # never pin
        return dsp.FrameEstimator.feed(self, v, ts)

class Sabotage(dsp.FrameEstimator):
    def feed(self, v, ts):
        self._prev_mean = (self._prev_mean or 0.0) + 17 * 2 * np.pi
        return dsp.FrameEstimator.feed(self, v, ts)

b, c = NoPin(rng_seed=0), Sabotage(rng_seed=0)
ds, dc, di = [], [], []
for _, _, _, ets, v in rr:
    ra, rb, rc = a.feed(v, ets), b.feed(v, ets), c.feed(v, ets)
    if not (ra and rb and rc):
        continue
    ds.append((ra["slope"] - rb["slope"], ra["slope"] - rc["slope"]))
    di.append((ra["intercept"] - rb["intercept"],
               ra["intercept"] - rc["intercept"]))
    if None not in (ra["cfo_hz"], rb["cfo_hz"], rc["cfo_hz"]):
        dc.append((ra["cfo_hz"] - rb["cfo_hz"], ra["cfo_hz"] - rc["cfo_hz"]))
ds, dc, di = np.array(ds), np.array(dc), np.array(di)
print("n=%d" % len(ds))
print("max |dslope|     %.3e / %.3e" % (np.abs(ds[:, 0]).max(),
                                        np.abs(ds[:, 1]).max()))
print("max |dcfo_hz|    %.3e / %.3e" % (np.abs(dc[:, 0]).max(),
                                        np.abs(dc[:, 1]).max()))
print("max |dintercept| %.3e / %.3e (= %.0f turns)"
      % (np.abs(di[:, 0]).max(), np.abs(di[:, 1]).max(),
         np.abs(di[:, 1]).max() / (2 * np.pi)))
```

### 12.3 §8's candidate-repair comparison

```python
import csv, sys, numpy as np
sys.path.insert(0, 'pc')
from rff import dsp
K = dsp.K_USABLE.astype(np.float64); IDX = dsp._USABLE_IDX
HDR = ("pc_time_us,label,seq,mac,rssi,noise_floor,channel,esp_timestamp_us,"
       "len,csi_data,node_id,env_id,dropped").split(",")
MG = np.arange(-np.pi, np.pi, 0.0002); EXP = np.exp(-1j * np.outer(MG, K))
UNIT = np.diff(K) == 1


def arb(ph):
    return float(MG[int(np.argmax(np.abs(EXP @ np.exp(1j * ph))))])


def rebr(ph, m0):
    return m0 * K + np.angle(np.exp(1j * (ph - m0 * K)))


def fft_coarse(ph, pad):
    z = np.zeros(pad, dtype=complex)
    z[np.rint(K).astype(int) % pad] = np.exp(1j * ph)
    m = 2 * np.pi * int(np.argmax(np.abs(np.fft.fft(z)))) / pad
    return m - 2 * np.pi if m > np.pi else m


def R(x, y):
    return dsp.ransac_line(x, y, rng=np.random.default_rng(3))


for tag, path in (("s3", "/tmp/s3_1cce.csv"), ("d0wd", "/tmp/d0wd_1cce.csv")):
    out = {k: [] for k in ("cur", "A", "B", "C", "D", "E64", "E256", "E1024")}
    ref = []
    with open(path, newline='') as fh:
        for r in csv.reader(fh):
            if len(r) != 13:
                continue
            d = dict(zip(HDR, r))
            if d["mac"] != "1c:ce:51:f3:0d:fa":
                continue
            v = np.fromstring(d["csi_data"], sep=",")
            if v.size < 128:
                continue
            csi = dsp.csi_to_complex(v)[IDX]
            ph = np.angle(csi); uw = np.unwrap(ph)
            f = R(K, uw)
            if f is None:
                continue
            ref.append(arb(ph)); out["cur"].append(f[0])
            mA = np.angle(np.sum(np.exp(1j * np.diff(ph)[UNIT])))
            g = R(K, rebr(ph, mA)); out["A"].append(g[0] if g else np.nan)
            mB = np.angle(np.sum((csi[1:] * np.conj(csi[:-1]))[UNIT]))
            g = R(K, rebr(ph, mB)); out["B"].append(g[0] if g else np.nan)
            keep = np.abs(csi) > 0.25 * np.median(np.abs(csi))
            g = R(K[keep], np.unwrap(ph[keep]))
            out["C"].append(g[0] if g else np.nan)
            s = np.nonzero(np.abs(np.diff(ph)) > np.pi)[0]
            b = [0] + [i + 1 for i in s] + [52]
            a, z = max([(b[i], b[i + 1]) for i in range(len(b) - 1)],
                       key=lambda t: t[1] - t[0])
            g = R(K[a:z], uw[a:z]); out["D"].append(g[0] if g else np.nan)
            for pad in (64, 256, 1024):
                g = R(K, rebr(ph, fft_coarse(ph, pad)))
                out[f"E{pad}"].append(g[0] if g else np.nan)
    ref = np.array(ref)
    print(f"--- {tag}  n={ref.size}  arbiter median {np.median(ref):+.5f}")
    for k in out:
        x = np.array(out[k]); d = np.abs(x - ref)
        print(f"    {k:6s} median {np.nanmedian(x):+.5f}   turn-outs "
              f"{int(np.nansum(d > 0.05)):4d} "
              f"({100 * np.nanmean(d > 0.05):5.2f}%)   "
              f"med|x-arbiter| {np.nanmedian(d):.5f}   "
              f"no-fit {int(np.isnan(x).sum())}")
```
