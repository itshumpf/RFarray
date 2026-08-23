# SEPARATION SCALING — does beacon separation improve when the room holds
# still and you average for longer?

One question asked of the 2026-08-22 overnight capture, over its empty-room
window only: if the noise in the SFO estimate were white, averaging longer
would buy separation without limit, and crystal fingerprinting in an
uncontrolled room would be an engineering problem. If the noise is
correlated, no amount of averaging helps and the limit is physical.

Read-only. Both CSVs were opened `"rb"` and never written; nothing in
`data/raw/` was modified, renamed or deleted; the two files still read
2,529,534,604 and 2,962,429,711 bytes. No serial port was opened, nothing was
flashed, nothing was staged, committed or pushed. Two files in the repo were
written by this pass: this one and `pc/exp_separation_scaling.py`. The frame
cache went to a directory outside the repo tree, named by `$SEPSCALE_CACHE`.
Running the script also left
`pc/__pycache__/exp_separation_scaling.cpython-310.pyc`, which this session
had no permission to delete; `__pycache__/` is in `.gitignore`, so it is not
a repo artefact, but it is there. The pre-existing
`pc/exp_poscontrol_0822.py.head` and `.tail`, which
`docs/POSITIVE_CONTROL_0822.md` records and asks to be deleted, were not
touched and are still present.

**Inputs and window**

| | `d0wd_20260822_023034.csv` | `s3_20260822_023034.csv` |
|---|---|---|
| `node_id`, every row | 68 | 108 |
| data rows | 2,983,560 | 3,564,005 |
| beacon frames inside the window | 2,905,126 | 3,481,255 |

**The window is `300 s <= t < 23,000 s`**, half-open, where `t` is seconds of
`pc_time_us` since each file's own first decodable row — the same clock and
the same per-file origin that `pc/rff_offline.py`'s `--after` / `--before`
use. It excludes the power-on settle at the head, and it ends **67 s before
the operator re-entered the room** at `t ≈ 23,067 s`
(`docs/POSITIVE_CONTROL_0822.md` §0, §2.1) and 267 s before the last row.
6 h 18 m 20 s of empty room.

**The S3 is primary.** `docs/OVERNIGHT_2026-08-22.md` establishes that it
has 0 corrupt rows against the d0wd's 142 (§1), and §3.1 that its B3 cell
rejects 58.8 % of its frames. Both nodes were run and both are reported; where
they disagree, §4 says which one the conclusion rests on and why.

B1 = `a4:f0:0f:77:91:20` (reference), B2 = `28:05:a5:2f:fa:48`,
B3 = `f4:2d:c9:70:72:30` (the clock twin, `docs/LOT_HYPOTHESIS.md`).

---

## 0. The question, answered

**The data is in a flicker / random-walk regime, and the knee is at
τ ≈ 10–30 s.** The Allan deviation of the SFO estimate falls as τ^−0.47 —
white noise, within 0.035 of the ideal −0.5 — in **all six** node×beacon
cells, but only out to about 10 s. Between τ ≈ 20 s and τ ≈ 1 h it is flat
or rising: the 60–600 s log-log slope is **+0.096 to +0.271 in five of six
cells**. Every cell has a minimum, at **τ = 21.5 to 186.5 s** in five of six,
and the floor sits at **2.7 × 10⁻⁴ to 6.6 × 10⁻⁴ rad/sc** (1.5 × 10⁻³ on the
one bad cell) — that is **0.11 to 0.28 × `BETWEEN_UNIT_SD`**.

**Longer windows buy almost nothing.** On the S3, going from the shipped
64-frame window (0.64 s) to 16,384 frames (164 s) — **256× more averaging** —
moves the minimum pairwise separation from **0.69σ to 0.83σ** and the median
from 2.93σ to 3.51σ. The pooled per-window SFO sd falls from 1.498 × 10⁻³ to
1.251 × 10⁻³, a factor of **1.20**, where uncorrelated frames would give 16.
The time-shuffle control (§2.4) reproduces the factor of 16 exactly on the
same frames, so the plateau is temporal correlation and nothing else.

**Tighter gates do not rescue the pair that matters.** On the S3 the shipped
`max_resid = 0.8` rejects **zero** of 3,481,252 fitted frames — the largest
`resid_std` anywhere in the window, either file, is **0.2202** — and tightening
`min_inlier` from 0.60 to 0.90 costs 21 % of the frames while moving the
worst pair from 0.69σ to 0.83σ. Tightening helps the pairs that already
separated and does not touch the one that did not.

**The honest number.** At the best configuration on the S3 that keeps all
three beacons on real data — window 16,384 frames, `max_resid 0.80`,
`min_inlier 0.90`, 78.6 % of frames kept, 30–72 windows per beacon — the
three pairwise separations are

| pair | separation |
|---|---|
| B1 vs B2 | 3.72σ |
| B2 vs B3 | 4.68σ |
| **B1 vs B3** (the clock twins) | **0.96σ** |

**B1 and B3 do not separate.** 0.69σ at the shipped configuration, 0.96σ
after 256× more averaging and a tightened gate, and **0.66σ to 1.18σ at 174
of the 175 configurations swept**. Only one configuration exceeds that, and it
keeps 0.25 % of the frames and trips the discriminator's own variance floor
(§4.2). The blind 60/40 chronological holdout at the best configuration calls
**25 of 29 B3 test windows "B1"**. Two of the three pairs
clear the codebase's >3σ line and one does not, and the one that does not is
the pair the security use case actually cares about — two identical boards.

**And the receiver term is bigger than the beacon term.** In this same
window, the largest beacon-to-beacon SFO difference measurable *within* the
S3 is 0.00542 rad/sc (B2 vs B3, 2.29 × `BETWEEN_UNIT_SD`), while the
*smallest* same-beacon difference *between* the two receivers is 0.00897
(B1, 3.79 ×). The rank order of B1 and B2 is not even the same on the two
boards: B1 < B2 on the d0wd (+0.02287 vs +0.02678), B1 > B2 on the S3
(+0.01390 vs +0.00956). This is arithmetic on `docs/OVERNIGHT_2026-08-22.md`
§3.1's own table, reproduced here on the trimmed window (§0c of `report`).

---

## 1. Method

One script, `pc/exp_separation_scaling.py`, from the repo root:

```
export SEPSCALE_CACHE=/some/dir/outside/the/repo
D=data/raw/d0wd_20260822_023034.csv
S=data/raw/s3_20260822_023034.csv
for p in 0 1 2 3 4 5; do
    python3 pc/exp_separation_scaling.py scan $D --tag d0wd --part $p --nparts 6
    python3 pc/exp_separation_scaling.py scan $S --tag s3   --part $p --nparts 6
done
python3 pc/exp_separation_scaling.py merge --tag d0wd --nparts 6 --expect-rows 2983560
python3 pc/exp_separation_scaling.py merge --tag s3   --nparts 6 --expect-rows 3564005

python3 pc/exp_separation_scaling.py report  --tags d0wd,s3
python3 pc/exp_separation_scaling.py detail  --tags d0wd,s3 --window 16384 --max-resid 0.80 --min-inlier 0.90
python3 pc/exp_separation_scaling.py detail  --tags d0wd    --window 16384 --max-resid 0.80 --min-inlier 0.60
python3 pc/exp_separation_scaling.py detail  --tags d0wd    --window 4096  --max-resid 0.80 --min-inlier 0.70
python3 pc/exp_separation_scaling.py control --tags d0wd,s3
```

Every figure below is from one of those five commands, named per section.

**Phase work is `pc/rff/dsp.py`'s `FrameEstimator` and `WindowAggregator`.**
`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` were
**not** used: `docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 establishes all three
have the DC/guard-band index wrong, and `pc/test_rff_synth.py` test 7 shows
`phase_skew`'s mask returns the opposite sign.

**The DSP runs once; the sweeps re-derive from a per-frame cache.** This is
not an approximation, and the reason it is not is worth stating because the
whole gate sweep depends on it:

- `FrameEstimator` state is the unwrap-continuity anchor and the previous
  intercept/timestamp for the CFO finite difference. Both depend only on the
  order of that source's own frames. **Neither depends on any gate** — the
  gates live in `WindowAggregator.feed` (`pc/rff/dsp.py:190-197`), strictly
  downstream. One pass therefore serves every gate setting exactly.
- A window is emitted every `window` *accepted* frames and the buffer is then
  cleared, so re-chunking the cached accepted-frame sequence into consecutive
  groups of `window` is the aggregator.

`report` §0b **checks** that rather than asserting it: it replays 20,000
cached frames per node through the real `WindowAggregator(64, 0.6, 0.8)` and
compares. Result: **300 and 311 windows, counts equal, SFO bit-identical,
CFO identical.**

**Reproduction against the published cell table.** `report` §0c, shipped
configuration, this window against `docs/OVERNIGHT_2026-08-22.md` §3.1's
whole-file numbers:

| node | b | this window: reject % / SFO median | §3.1 whole file: reject % / SFO median |
|---|---|---|---|
| d0wd | B1 | 7.371 % / +0.02287 | 7.422 % / +0.02277 |
| d0wd | B2 | 4.082 % / +0.02678 | 4.114 % / +0.02682 |
| d0wd | B3 | 59.477 % / +0.07218 | 58.814 % / +0.07195 |
| s3 | B1 | 0.566 % / +0.01390 | 0.664 % / +0.01392 |
| s3 | B2 | 0.712 % / +0.00956 | 0.794 % / +0.00959 |
| s3 | B3 | 0.311 % / +0.01468 | 0.314 % / +0.01466 |

Six of six agree to **2.3 × 10⁻⁴ rad/sc or better**, five of six to
1.0 × 10⁻⁴, and the outlier is B3/d0wd — the 59 %-reject cell. The reject
rates all fall slightly, which is the direction trimming the power-on settle
predicts. The window drops 300 s from the head and 267 s from the tail, 2.4 %
of each file.

**The `part`/`merge` split** exists only because this host caps a shell call
at ~178 s and a single pass over the two files takes about eleven minutes. It
is not an approximation: ranges are cut on line boundaries, each part asserts
that its first byte equals the previous part's last byte, the
`FrameEstimator` state and MAC table are pickled forward, and `merge`
re-checks rather than asserts — the parts' rows sum to **2,983,560 and
3,564,005**, matching `wc -l` minus the header exactly, with **0 `pc_time_us`
reversals** across the 5 seams per file.

### 1.1 The parse defect, and the check that it is not present here

`docs/POSITIVE_CONTROL_0822.md` §1.2 records that `cs.split(",", 128)` at
`pc/exp_overnight_0822.py:303` and `pc/exp_s3_sfo_steps.py:153,590` silently
discards every `csi_len = 128` row, because `maxsplit=128` returns **at most**
129 items and a 128-value row yields exactly 128. This script reads the field
with `np.fromstring(cs, sep=",")` — the same read as
`pc/rff_offline.py:203` — and counts what it sees (`report` §0):

| | d0wd | s3 |
|---|---|---|
| data rows | 2,983,560 | 3,564,005 |
| rows undecodable by line or field | 0 / 0 | 0 / 0 |
| parsed CSI vector length **128** | **2,222** | **2,444** |
| parsed CSI vector length **256** | **2,981,272** | **3,561,558** |
| other lengths | 384: 64, 241: 1, 0: 1 | 384: 3 |
| rows `split(",", 128)` would have dropped | 2,223 | 2,444 |
| `node_id` values | 68 (all rows) | 108 (all rows) |

The parsed-vector histogram equals the `csi_len` column histogram row for
row, in both files.

**The check with teeth** is that the 128-length sources produce fits, because
a parser carrying the defect returns zero for them. `scan` phase-estimates
every non-beacon source as well: **2,258 of 2,264 ambient frames on the d0wd
and 2,344 of 2,345 on the S3 obtained a RANSAC fit**, including
`1c:ce:51:f3:0d:fa` (947 and 932 frames, 100 % fitted) and
`ba:80:d5:0c:18:87` (253 and 899). Those are the sources
`docs/POSITIVE_CONTROL_0822.md` §3.1 lists at `len 128`.

The beacon population is untouched by any of this: `docs/OVERNIGHT_2026-08-22.md`
§3.1 and `docs/POSITIVE_CONTROL_0822.md` §3.1 both record all three beacons
at **100 % `csi_len = 256`**, and the three beacons' row counts in this
window sum to 2,905,126 and 3,481,255 — every one of which parsed.

**One screen was deliberately not reproduced.** The two-route corrupt-row
screen of `docs/OVERNIGHT_2026-08-22.md` §1 (a width-9 median filter on
`dropped`, plus six-column field plausibility) is not applied here; this pass
screens only on parseability. That screen finds 142 corrupt rows on the d0wd
and 0 on the S3, i.e. at most 142 of 2,905,126 d0wd beacon frames — 0.005 % —
could be corrupt rows this pass kept. Nothing below turns on 0.005 %.

---

## 2. ALLAN DEVIATION — the diagnostic that decides the rest

`report` §1. Per-frame slopes passing the shipped gates are binned into
**τ₀ = 0.5 s** bins (45,400 bins spanning the window; **100.0 % populated**
in five of six cells and 99.1 % in B3/d0wd), and the overlapping Allan
deviation is computed on the bin means. A block of m bins counts only if at
least 90 % of its bins carry data, so gaps drop pairs rather than biasing
them toward zero. `indep` is the number of non-overlapping pairs at that τ,
i.e. the honest confidence: the last three rows of each series rest on 3–5
independent samples and should not be read as precise.

### 2.1 The shape, in one table

Six cells, σ(τ) in rad/sc, at seven τ across the range:

| node/b | τ=0.5 s | 2 s | 9.5 s | 37 s | 186 s | 937 s | 3600 s |
|---|---|---|---|---|---|---|---|
| d0wd/B1 | 3.13e-3 | 1.59e-3 | 8.16e-4 | **6.57e-4** | 9.26e-4 | 1.46e-3 | 1.10e-3 |
| d0wd/B2 | 2.17e-3 | 1.11e-3 | 5.77e-4 | 4.00e-4 | 4.67e-4 | 4.23e-4 | 4.45e-4 |
| d0wd/B3 | 4.87e-3 | 2.48e-3 | 1.51e-3 | 1.58e-3 | 2.35e-3 | 3.01e-3 | 2.50e-3 |
| s3/B1 | 1.51e-3 | 7.71e-4 | 3.87e-4 | **3.23e-4** | 4.46e-4 | 6.88e-4 | 7.76e-4 |
| s3/B2 | 2.28e-3 | 1.14e-3 | 5.48e-4 | 3.38e-4 | **2.68e-4** | 3.27e-4 | 4.38e-4 |
| s3/B3 | 1.43e-3 | 7.35e-4 | 3.78e-4 | **3.02e-4** | 4.53e-4 | 5.41e-4 | 9.10e-4 |

### 2.2 Slopes, by regime

Log-log fits over four bands, from `report` §1:

| node/b | 0.5–5 s | 5–60 s | 60–600 s | 600–3600 s | minimum σ | at τ |
|---|---|---|---|---|---|---|
| d0wd/B1 | **−0.478** | −0.191 | **+0.271** | −0.161 | 6.57e-4 | 37.0 s |
| d0wd/B2 | **−0.470** | −0.281 | +0.096 | −0.007 | 3.88e-4 | 1226.5 s |
| d0wd/B3 | **−0.465** | −0.010 | **+0.249** | −0.145 | 1.49e-3 | 21.5 s |
| s3/B1 | **−0.479** | −0.175 | **+0.263** | +0.055 | 3.19e-4 | 28.5 s |
| s3/B2 | **−0.492** | −0.374 | −0.015 | +0.295 | 2.68e-4 | 186.5 s |
| s3/B3 | **−0.472** | −0.193 | **+0.222** | +0.350 | 3.01e-4 | 28.5 s |

**Read plainly:** the short-τ regime is white, unambiguously and identically
in all six cells (−0.465 to −0.492 against the ideal −0.5). It ends by about
5–10 s. From ~60 s out the slope is positive in five of six cells (+0.096 to
+0.271), which is random-walk-like; only s3/B2 stays flat (−0.015), which is
flicker-like. Nothing anywhere continues to fall.

**The τ at which it stops improving is 20–40 s** in four of six cells, 186 s
in s3/B2 and 1226 s in d0wd/B2. Past that, averaging longer makes the
estimate *worse*: s3/B3 goes from 3.02e-4 at 28.5 s to 9.10e-4 at 3600 s, a
factor of 3.0 in the wrong direction.

### 2.3 The floor, against the yardsticks

| quantity | value | source |
|---|---|---|
| best Allan floor, S3 cells | 2.68e-4 – 3.19e-4 rad/sc | `report` §1 |
| best Allan floor, d0wd cells | 3.88e-4 – 1.49e-3 | `report` §1 |
| `BETWEEN_UNIT_SD` | 2.37e-3 | `pc/exp_thermal_evidence.py:129` |
| twin ΔSFO | 8.0e-4 | `pc/exp_lot_hypothesis.py:85-86` |
| estimator floor, quantisation only | 1.8e-5 | `pc/test_rff_synth.py` test 6 |
| estimator floor, 20 dB SNR | 3.5e-4 | `pc/test_rff_synth.py` test 6 |

The S3's floors are **0.113 to 0.135 × `BETWEEN_UNIT_SD`** and **0.34 to
0.40 × the twin ΔSFO**. The beacon-to-beacon SFO differences measurable on
the S3 in this window are 0.00104 (B1−B3), 0.00439 (B1−B2) and 0.00542
(B2−B3), i.e. **3.5×, 15× and 18×** the floor.

So the floor is *not* what stops B1 and B3 separating. At τ ≈ 30 s the
estimator can tell 3 × 10⁻⁴ rad/sc apart and the twins differ by
1.04 × 10⁻³. What stops them is that the *drift between two measurements*
is much larger than the precision of either one — which is exactly what a
rising Allan deviation means, and what §3 measures directly.

**Two comparisons that must be made carefully.** The S3's floors, 2.7–3.2e-4,
sit near `test_rff_synth` test 6's 20 dB-SNR figure of 3.5e-4. These are
**not the same quantity** — test 6's number is the smallest ΔSFO separable at
3σ over 20 windows of 64 frames under one synthetic stationary channel, not
an Allan deviation — so the agreement is suggestive of the S3 running near a
~20 dB effective SNR and is not evidence of it. And test 6's own caveat
applies here with force: it measures precision under *one* stationary
multipath realisation, and records that a single smooth multipath
realisation biases the slope by ~1e-2 rad/sc. The floors above are what a
real room does to that.

### 2.4 The non-circular control: shuffle time, keep the frames

`control`. Each beacon's accepted frames are permuted in time and re-chunked.
Chunking a shuffled sequence averages exactly the same numbers, so any
difference is purely the correlation between neighbouring frames.

Per-window SFO sd, S3, real order against shuffled order:

| beacon | W=64 | W=256 | W=1024 | W=4096 | W=16384 | real ÷ | shuffled ÷ |
|---|---|---|---|---|---|---|---|
| B1 real | 1.36e-3 | 1.24e-3 | 1.19e-3 | 1.16e-3 | 1.11e-3 | **1.23** | |
| B1 shuffled | 6.68e-4 | 3.34e-4 | 1.72e-4 | 8.24e-5 | 4.25e-5 | | **15.7** |
| B2 real | 1.27e-3 | 9.57e-4 | 8.48e-4 | 7.93e-4 | 7.47e-4 | **1.70** | |
| B2 shuffled | 9.50e-4 | 4.74e-4 | 2.38e-4 | 1.15e-4 | 4.87e-5 | | **19.5** |
| B3 real | 1.72e-3 | 1.65e-3 | 1.62e-3 | 1.60e-3 | 1.56e-3 | **1.10** | |
| B3 shuffled | 6.35e-4 | 3.18e-4 | 1.57e-4 | 7.89e-5 | 3.65e-5 | | **17.4** |

√256 = 16. The shuffled series lands on 15.7, 19.5 and 17.4 — 1/√W, as
uncorrelated frames must. The real series lands on 1.10 to 1.70. The d0wd
shows the same thing (B3 real 6.41e-3 → 5.22e-3, factor 1.23; shuffled
1.70e-3 → 8.72e-5, factor 19.5).

**This is the whole answer in one table.** The averaging machinery works
perfectly; there is simply nothing left to average away after the first
second. The plateau is not the estimator, not the gate, not the aggregator,
not the window arithmetic. It is the room and the crystals moving together on
timescales of tens of seconds and longer.

---

## 3. WINDOW-LENGTH SWEEP

`report` §2. Windows of 64 / 256 / 1024 / 4096 / 16384 accepted frames at the
shipped gates, all windows entering the model (not the 60 % training split —
see the caveat at the end of this section). Separations are
`rff.discriminator.Discriminator.separation_matrix()`, pooled covariance,
returning d not d².

### 3.1 S3 — the primary node

| window | s at 100 fps | wins B1/B2/B3 | B1–B2 | **B1–B3** | B2–B3 | min | median |
|---|---|---|---|---|---|---|---|
| 64 *(shipped)* | 0.6 | 19506/12588/22029 | 2.93 | **0.69** | 3.62 | 0.69 | 2.93 |
| 256 | 2.6 | 4876/3147/5507 | 3.21 | **0.76** | 3.97 | 0.76 | 3.21 |
| 1024 | 10.2 | 1219/786/1376 | 3.32 | **0.79** | 4.10 | 0.79 | 3.32 |
| 4096 | 41.0 | 304/196/344 | 3.39 | **0.80** | 4.19 | 0.80 | 3.39 |
| 16384 | 163.8 | 76/49/86 | 3.51 | **0.83** | 4.34 | 0.83 | 3.51 |

Per-window SFO sd over the same windows: B1 0.00136 → 0.00111, B2 0.00127 →
0.00075, B3 0.00172 → 0.00156. Pooled: **1.498e-3 → 1.251e-3**.

**It improves, and the improvement is trivial.** 256× the averaging buys
**+20 %** on both the minimum and the median. Nothing plateaus in the sense
of stopping dead — the curve is still creeping upward at 16,384 frames.

**That creep must not be extrapolated.** Fitting a power law to it gives an
exponent of 0.033, i.e. 5.6 × 10¹⁶ × more averaging to carry the twin pair
from 0.83σ to 3σ, which is a number with no physical meaning. The reason it
has none is §2: σ(τ) is already *rising* past τ ≈ 200 s in four of the six
cells, and 16,384 frames is 164 s. The sweep stops one step short of the
turn, and beyond it the trend reverses.

### 3.2 d0wd — and why its big numbers are not separations

| window | wins B1/B2/B3 | B1–B2 | B1–B3 | B2–B3 | min | median |
|---|---|---|---|---|---|---|
| 64 *(shipped)* | 12451/13432/7272 | **1.14** | 13.50 | 12.36 | 1.14 | 12.36 |
| 256 | 3112/3358/1818 | **1.23** | 14.55 | 13.32 | 1.23 | 13.32 |
| 1024 | 778/839/454 | **1.28** | 15.19 | 13.90 | 1.28 | 13.90 |
| 4096 | 194/209/113 | **1.36** | 16.03 | 14.67 | 1.36 | 14.67 |
| 16384 | 48/52/28 | **1.48** | 17.37 | 15.89 | 1.48 | 15.89 |

Same shape: +30 % over 256×. But the 12–17σ figures are **not** crystal
separations. They are B3/d0wd, the cell that rejects 59.5 % of its frames and
reads **+0.07218** where the same beacon at the same time on the other
receiver reads **+0.01468** — a factor of 4.9.
`docs/S3_SFO_STEPS.md` §7.2 established that this offset is a function of fit
quality and collapses by 30× when the population is stratified by
`resid_std`, and `docs/OVERNIGHT_2026-08-22.md` §3.4 and §10 already say that
cell must not be quoted alone. **The d0wd's headline separation is an
estimator-bias artefact and is excluded from §5's answer.**

What the d0wd *does* contribute is B1–B2: **1.14σ → 1.48σ**, on a pair that
reads 2.93σ → 3.51σ on the S3. Same two boards, same six hours, same code,
**2.4–2.6× different answer** depending on window length.

### 3.3 CFO contributes nothing

The 2-D Mahalanobis figures above are equal to the SFO-axis-only figures to
two decimals in every row of every table. Measured directly (`detail`):
the CFO axis alone gives **0.01σ to 0.02σ** at the shipped configuration and
0.14σ to 0.21σ at 16,384 frames. The per-frame CFO medians are −0.040,
−0.007 and +0.016 Hz for the three beacons on the S3, with IQRs of 20 to
33 Hz.

That corroborates `docs/TWIN_INVESTIGATION.md` §3 ("the entire separation
lives in SFO; CFO contributes nothing, d = 0.03") on a different capture, a
different source pair and 6.4 M frames. Anything below that says "separation"
is SFO.

**Caveat on the protocol.** `pc/rff_offline.py:report()` builds its printed
separation matrix from the **first 60 %** of each source's windows; the sweep
above uses all of them, which is the right choice for a descriptive statistic
and is stated so the numbers are not compared to `rff_offline` output
carelessly. `docs/TWIN_INVESTIGATION.md` §3 measured the same gap in the
other direction on a different pair (2.54σ all-windows against 2.10σ at
train-60 %), so the two conventions can differ by ~20 %.

---

## 4. GATE SWEEP

`report` §3. `max_resid` ∈ {0.80, 0.30, 0.20, 0.16, 0.14, 0.12, 0.10} ×
`min_inlier` ∈ {0.60, 0.70, 0.80, 0.90, 0.95}, at window 64 and window 4096.
`nsrc` is how many of the three beacons still reached
`Discriminator.MIN_CHARACTERIZED = 5` windows; a `min` computed over two
sources is not comparable to one computed over three, which is why the column
is printed.

### 4.1 The residual gate is inoperative, measured on 6.4 M frames

`max_resid = 0.80`, `0.30` and `0.20` return **identical** frame counts on
the d0wd (2,122,014) and near-identical on the S3 (3,463,968 vs 3,463,890).
Directly: across all **6,386,119** frames in the window that produced a
RANSAC fit (259 on the d0wd and 3 on the S3 did not), the **maximum
`resid_std` is 0.2202 on the d0wd and 0.2188 on the S3**; p99 is 0.187 and
0.173. The shipped gate sits at **3.6× the worst residual in either file**.

That reproduces `docs/S3_SFO_STEPS.md` §7.3 ("on this data the residual gate
is inoperative") on 6.4 M frames instead of one session, and it is why the
`--max-resid` axis is nearly degenerate down to 0.16 in every table below.

### 4.2 S3, window 64 — the trade-off curve

| max_resid | min_inlier | frames kept | kept % | wins B1/B2/B3 | min | median |
|---|---|---|---|---|---|---|
| 0.80 | 0.60 *(shipped)* | 3,463,968 | 99.50 | 19506/12588/22029 | **0.69** | 2.93 |
| 0.80 | 0.70 | 3,416,881 | 98.15 | 19282/12308/21798 | **0.70** | 2.94 |
| 0.80 | 0.80 | 3,222,621 | 92.57 | 18630/10930/20791 | **0.73** | 2.97 |
| 0.80 | 0.90 | 2,735,463 | 78.58 | 16494/7722/18524 | **0.83** | 3.21 |
| 0.80 | 0.95 | 1,632,807 | 46.90 | 10712/2781/12018 | **0.73** | 4.64 |
| 0.16 | 0.60 | 3,249,024 | 93.33 | 18377/11236/21151 | 0.71 | 2.89 |
| 0.14 | 0.60 | 1,910,829 | 54.89 | 9069/6064/14723 | 0.76 | 2.47 |
| 0.12 | 0.60 | 283,575 | 8.15 | 330/955/3144 | 0.79 | 2.14 |
| 0.10 | 0.60 | 9,924 | 0.29 | 11/53/90 | 0.71 | 8.05 |

The minimum lives between **0.66σ and 0.92σ at every grid point where all
three beacons survive, bar one** (the last row, discussed below). The median
moves — 2.93 → 4.64 at
`min_inlier 0.95` — because tightening shrinks the pooled sd and the two
already-separated pairs ride that down. The worst pair does not move, because
the twins' centroids move together.

The one grid point above 2σ, `max_resid 0.10 / min_inlier 0.70` → 2.73σ,
retains **8,719 of 3,481,252 frames (0.25 %)**, gives 6 windows to the
sparsest beacon, and trips the discriminator's own variance floor (`report`
flags it `floor? YES`: `rff/discriminator.py:29` floors the SFO variance at
1e-8, so below a per-window sd of 1e-4 rad/sc the denominator is the floor
rather than the data). It is small-sample noise, not a configuration.

### 4.3 S3, window 4096 — same picture, one step better

| max_resid | min_inlier | kept % | wins B1/B2/B3 | min | median |
|---|---|---|---|---|---|
| 0.80 | 0.60 *(shipped)* | 99.50 | 304/196/344 | 0.80 | 3.39 |
| 0.80 | 0.80 | 92.57 | 291/170/324 | 0.84 | 3.39 |
| 0.80 | 0.90 | 78.58 | 257/120/289 | **0.93** | 3.60 |
| 0.80 | 0.95 | 46.90 | 167/43/187 | 0.84 | 5.31 |
| 0.14 | 0.90 | 49.56 | 132/76/211 | 0.91 | 2.99 |
| 0.12 | 0.60 | 8.15 | 5/14/49 | 1.03 | 2.50 |

**The cost curve is monotone and the benefit curve is flat.** Going from
99.5 % of frames to 46.9 % — throwing away 1.83 million frames — moves the
worst pair from 0.80σ to 0.84σ.

### 4.4 d0wd — where the gate does appear to buy separation, and why

| max_resid | min_inlier | kept % | wins B1/B2/B3 | nsrc | min | median |
|---|---|---|---|---|---|---|
| 0.80 | 0.60 *(shipped)*, W=64 | 73.05 | 12451/13432/7272 | 3 | 1.14 | 12.36 |
| 0.80 | 0.70, W=64 | 46.65 | 7921/12326/**924** | 3 | 2.34 | 19.53 |
| 0.80 | 0.80, W=64 | 17.79 | 1489/6577/**6** | 3 | 4.96 | 21.75 |
| 0.80 | 0.90, W=64 | 0.48 | 20/197/**0** | 2 | 7.89 | 7.89 |
| 0.80 | 0.70, W=4096 | 46.65 | 123/192/**14** | 3 | 3.09 | 25.79 |
| 0.16 | 0.70, W=4096 | 28.14 | 55/133/**10** | 3 | 3.49 | 27.43 |

This is the "properly tightened gate buys separation" case, and it does not
survive inspection. Look at the B3 column: 7,272 windows → 924 → 6 → 0. The
d0wd's inlier gate is not selecting good frames from a good cell, it is
**deleting the B3 cell**. At `min_inlier 0.70 / W=4096` B3 has 14 windows,
its SFO reads +0.06903 instead of +0.07202, and the pooled sd has collapsed
because the widest source is gone. The "3.09σ" minimum is B1–B2 measured
against a covariance pool that no longer contains B3.

The trade-off, stated as the brief asked: on the d0wd, moving `min_inlier`
0.60 → 0.70 costs **36 % of all frames and 87 % of B3's windows** and returns
a min of 2.34σ that is a denominator effect; 0.70 → 0.80 costs 62 % more and
returns 4.96σ on six B3 windows. There is no point on this curve where the
gate buys separation without buying it out of the sample size.

---

## 5. THE HONEST SUMMARY

### 5.1 The best achievable configuration, and its numbers

`detail --tags d0wd,s3 --window 16384 --max-resid 0.80 --min-inlier 0.90`.
This is the best configuration on the S3 that keeps all three beacons on a
substantial fraction of real data and does not trip the variance floor:
78.58 % of frames retained, 64 / 30 / 72 windows of 163.8 s each.

| beacon | windows | SFO mean | SFO sd | SFO sd within 30 min | CFO mean | CFO sd |
|---|---|---|---|---|---|---|
| B1 | 64 | +0.01386 | 0.00107 | 0.00084 | −0.058 Hz | 0.237 |
| B2 | 30 | +0.00928 | 0.00068 | 0.00055 | −0.024 Hz | 0.159 |
| B3 | 72 | +0.01503 | 0.00151 | 0.00076 | +0.016 Hz | 0.256 |

| pair | ΔSFO | × `BETWEEN_UNIT_SD` | separation | drift-removed |
|---|---|---|---|---|
| B1 vs B2 | 0.00458 | 1.93 | **3.72σ** | 5.93σ |
| B2 vs B3 | 0.00576 | 2.43 | **4.68σ** | 7.45σ |
| **B1 vs B3** | **0.00118** | **0.50** | **0.96σ** | **1.52σ** |

("drift-removed" is |Δμ| against the pooled *within-30-minute-block* sd,
7.723e-4, from the same `detail` output — what the separation would be if
every comparison were made inside half an hour and the slow drift between
blocks did not exist. It is a diagnostic, not an operating point; you cannot
enrol a device in one half hour and identify it in another.)

**Blind 60/40 chronological holdout at that configuration: 37/67 = 55.2 %**
on a 3-class problem where chance is 33 %, with **25 of 29 B3 test windows
classified as B1** and 0 strangers. At the shipped configuration on the same
node the holdout is 12,193/21,651 = **56.3 %**, with 6,241 B3→B1 and 2,081
B1→B3 confusions. The extra averaging did not change the accuracy either.

### 5.2 Stated directly

**These three beacons do not reliably separate in this room.** Two of the
three pairs do — B1 vs B2 at 3.72σ and B2 vs B3 at 4.68σ clear the
codebase's >3σ rule of thumb (`pc/rff_offline.py:322`) once you average
164 s. The third pair, **B1 vs B3, reaches 0.96σ and stays there**: 0.69σ at
the shipped configuration, 0.83σ at 256× the averaging, 0.96σ with a
tightened inlier gate as well, and **0.66σ to 1.18σ at 174 of the 175
configurations swept** — the 175th being the 0.25 %-of-frames,
variance-floor-tripping point of §4.2. A 3-class identifier built on this
data is a 2-class identifier with a coin flip inside it, which the 55 %
holdout says out loud.

**Longer averaging is not the missing ingredient.** §2 says why in advance of
§3 measuring it: the estimate stops improving at τ ≈ 20–40 s and then gets
worse, and §2.4's shuffle control shows the averaging arithmetic is working
perfectly and has simply run out of white noise to remove. The gain available
from here is +20 % per 256× of averaging.

**Tighter gates are not the missing ingredient either.** The shipped
`max_resid = 0.8` rejects zero frames out of 6.4 million, so there was a real
possibility that a working residual gate had never been tried — but it has
now been swept to 0.10, and on the S3 the worst pair sits between 0.66σ and
0.92σ everywhere the sample survives. On the d0wd tightening appears to buy
separation and does not: it deletes the B3 cell and shrinks the pooled
covariance.

**What this does not say.** It does not say crystal fingerprinting cannot
work. It says these three units, at these two receivers, in this room, over
these 6.3 hours, do not separate — and that B1 and B3 are a pair
`docs/LOT_HYPOTHESIS.md` already characterised as a genuine clock twin
(0.26σ, ΔSFO 0.00080 rad/sc on `rx_20260714_011619`). Finding that two clock
twins remain twins after six hours of averaging is a confirmation, not a
surprise. What is new is the *reason*, and the reason is general: the noise
stops being white at 10 s.

### 5.3 Against the separations already in the repo

| source | pair | figure | this pass, same pair |
|---|---|---|---|
| `docs/WINDOW_CONVERGENCE.md` §4.3 | B1 vs B3 (twins), `rx_20260714_011619`, 0.5–120 s windows | **0.32σ – 0.44σ** | **0.69σ – 0.96σ** |
| `docs/WINDOW_CONVERGENCE.md` §4.2 | B1 vs B2, `rx_20260714_011619`, 0.1–120 s windows | **1.68σ – 2.62σ** | **2.93σ – 3.72σ** (s3) |
| `docs/TWIN_INVESTIGATION.md` §3 | `84:7b:57:cc:20:0e` vs B1, ambient | 2.54σ all-windows / 2.10σ train-60 % | not in this population |
| `docs/LOT_HYPOTHESIS.md` | B1 vs B3 on `rx_20260714_011619` | 0.26σ, ΔSFO 0.00080 | ΔSFO **0.00118** here |
| `pc/rff_offline.py:322` | rule of thumb | >3σ reliably separable | 2 of 3 pairs clear it |

The two independent measurements of the twin pair — 0.32–0.44σ on
2026-07-14 and 0.69–0.96σ on 2026-08-22, different receiver, different
harness, 6 weeks apart — **agree in conclusion and differ by roughly 2× in
value.** Both are far below 3σ. `docs/WINDOW_CONVERGENCE.md` §4.3's second
finding — "window length is irrelevant to the twins, 0.33σ at 0.5 s and
0.44σ at 120 s, 240× more observation buys nothing" — is reproduced here at
256× on a 6.3-hour capture, and §2 of this document supplies the mechanism
it was missing.

`docs/WINDOW_CONVERGENCE.md` §4.2 reported the same-model non-twin pair
*rising* with window length (1.68σ at 0.1 s to 2.62σ at 120 s) and never
clearing 3σ. This pass sees the same rise on the S3 and it does clear 3σ, at
3.51σ (all-windows, shipped gates, 164 s) and 3.72σ (gate 0.90). **That is a
real difference between the two captures and it is not explained here** — it
is a different receiver, a different session and a different room state, and
this document cannot say which.

---

## 6. Established / permitted / unknown

**Established by this pass, from these files:**

- The SFO estimate's noise is white out to τ ≈ 5–10 s (log-log slope −0.465
  to −0.492 in 6 of 6 cells) and correlated beyond it (60–600 s slope +0.096
  to +0.271 in 5 of 6). §2.2.
- σ(τ) has a minimum at τ = 21.5–186.5 s in 5 of 6 cells, at 2.68e-4 to
  1.49e-3 rad/sc, and rises past it. §2.1–2.2.
- The plateau in per-window sd is temporal correlation and nothing else: the
  same frames shuffled in time give 1/√W (15.7–19.5 over √256 = 16) while
  the real order gives 1.10–1.70. §2.4.
- 256× more averaging (64 → 16384 frames) buys **+20 %** of separation on the
  S3 and **+30 %** on the d0wd. §3.1–3.2.
- On the S3, B1 vs B3 is **0.69σ** shipped and **0.96σ** at the best
  configuration, and stays in **0.66–1.18σ at 174 of the 175** swept
  configurations where all three beacons survive; the 175th (2.73σ) retains
  0.25 % of the frames and trips the variance floor. §4.2, §5.1.
- B1 vs B2 is **3.72σ** and B2 vs B3 **4.68σ** at that configuration; both
  clear the >3σ rule. §5.1.
- Blind 60/40 holdout: **55.2 %** (67 windows) at the best configuration,
  **56.3 %** (21,651 windows) shipped, both with the B1↔B3 confusion
  dominating. §5.1.
- The shipped `max_resid = 0.8` rejects **0** of 6,386,119 fitted frames;
  the largest `resid_std` anywhere in the window is **0.2202**. §4.1.
- CFO carries no discriminating information here: CFO-axis separation
  0.01–0.21σ, per-frame medians within 0.06 Hz of zero for all three
  beacons. §3.3.
- The `split(",", 128)` defect is not present in this pass: 2,222 and 2,444
  128-length rows parsed, 2,258/2,264 and 2,344/2,345 ambient frames fitted.
  §1.1.
- Same-beacon receiver-to-receiver SFO differences (0.00897, 0.01721,
  0.05750) exceed every within-receiver beacon-to-beacon difference on the S3
  (0.00104, 0.00439, 0.00542), and B1/B2's rank order reverses between the
  two receivers. §0, `detail`.

**Permitted but not established:**

- That the S3's Allan floor of ~3e-4 rad/sc reflects a ~20 dB effective SNR
  (it coincides with `test_rff_synth` test 6's 20 dB figure, but that figure
  is a different statistic under a synthetic stationary channel). §2.3.
- That the correlated component is thermal. `docs/THERMAL_EVIDENCE.md`
  exists and this pass did not test against it; nothing here records
  temperature, and `docs/OVERNIGHT_2026-08-22.md` §3.2 already found the
  available proxy (`noise_floor`) uninformative on the S3.
- That B1 vs B2 clearing 3σ here while `docs/WINDOW_CONVERGENCE.md` §4.2 has
  it below 3σ is a receiver or room-state effect rather than a session
  accident. §5.3.
- That the 30-minute drift-removed separations (5.93σ, 7.45σ, 1.52σ) would be
  achievable by any real enrolment protocol. They are computed by removing a
  drift no deployed system can remove. §5.1.

**Unknown, and not addressed by this capture:**

- Whether the twin pair separates at any averaging time at all. This pass
  reached τ = 3600 s and 16,384-frame windows; both got worse, not better,
  past ~200 s, so an experiment at longer τ has no reason to be run.
- Whether a *different* feature (amplitude-domain, per-subcarrier residual
  shape, transient turn-on) separates them. Only the (CFO, SFO) phase feature
  was measured, and §3.3 shows one of its two axes is dead.
- The receiver-versus-position confound. The operator states the nodes were
  deliberately not swapped, so this session cannot separate "the d0wd reads
  differently" from "that corner of the room reads differently";
  `docs/DUAL_RX_2026-08-21.md` §6's swap-and-repeat remains the outstanding
  experiment and §0's rank-order reversal is a fresh reason to run it.
- Whether the B3/d0wd 59.5 %-reject cell has a physical cause. This pass
  reproduces it and excludes it; it does not explain it.

---

## 7. Figures in this document that should not be quoted alone

- **12–17σ on the d0wd.** Those are B1–B3 and B2–B3 on the receiver whose B3
  cell rejects 59.5 % of its frames and reads 4.9× the other receiver's value
  for the same beacon. They are estimator bias, not crystal separation. §3.2.
- **2.73σ, 4.96σ, 7.89σ and the other tightened-gate minima.** Each is
  disqualified by something different, and each is named: 2.73σ keeps 8,719
  of 3,481,252 frames (0.25 %) and trips the variance floor; 4.96σ rests on
  six B3 windows; 7.89σ is computed over two beacons, not three. §4.2, §4.4.
- **5.93σ / 7.45σ / 1.52σ drift-removed.** Diagnostics computed with the
  between-block drift subtracted; no enrolment protocol can do that. §5.1.
- **"+20 % per 256×."** True on the S3 over the range swept. It is not a law
  and should not be extrapolated; §2's Allan curves say the next decade of
  averaging is worse, not merely flatter.
- **0.96σ.** It is the best configuration's number for one pair on one node
  over one night. The stable claim is the *range*: **0.66–1.18σ at 174 of
  the 175 swept configurations**, and 0.32–1.18σ across this capture and
  `rx_20260714_011619` together.
- **The `docs/WINDOW_CONVERGENCE.md` comparison in §5.3.** Different session,
  different receiver, different harness, and the windows are defined in
  seconds there and in frames here. It is a consistency check, not a matched
  comparison.

---

## 8. What would settle the rest

1. **Swap the two nodes' positions and repeat.** Still the outstanding
   experiment (`docs/DUAL_RX_2026-08-21.md` §6). §0's finding that B1 and B2
   change rank order between receivers makes it the single highest-value run:
   if the order follows the board, the receiver is the problem; if it follows
   the position, multipath is.
2. **A cross-manufacturer source, in the same six hours.**
   `docs/WINDOW_CONVERGENCE.md` §4.1 measures 3.4–4.1σ cross-manufacturer at
   0.4–30 s windows. Running that pair through this same Allan analysis would say
   whether the τ ≈ 30 s knee is universal or specific to identical crystals.
3. **Temperature logging.** The correlated component has a timescale of tens
   to hundreds of seconds. That is the right timescale for thermal, and
   nothing in this repo has ever recorded a temperature.
4. **An amplitude- or transient-domain feature, measured on this same cache.**
   The frame cache this pass builds already holds per-frame `resid_std`,
   `inlier_ratio` and RSSI for 6.4 M frames; §3.3 shows the CFO axis is dead,
   so the feature space is effectively one-dimensional and any second real
   axis would be worth more than more averaging on the first.
