# Seven-night re-read — audit, 2026-09-04

**This document does not edit `SEVEN_NIGHT_PREREG.md` and does not rescore
anything.** It is a post-series read of the whole record looking for structure
nobody scored and for claims the record makes about itself that its own data
does not support. Nothing here is pre-registered; nothing here carries a
verdict. Where a finding would change a verdict, that is said explicitly — and
in every case below, it does not.

No git command was run. `data/raw/` was read only.

## 0. Provenance — what is measured here and what is quoted

Two classes of number appear below and they are not equally strong.

**MEASURED THIS SESSION, from `data/raw/` or from source files:**

| item | how |
|---|---|
| night-4 capture duration, per-hour and per-MAC frame counts, beacon death and return times | single `awk` pass over `d0wd_20260901_035805.csv` (4.7 GB), streamed |
| file sizes, mtimes, CSV schema | `ls`, `head` |
| the σ-unit finding in §3 | read out of `pc/rff/discriminator.py`, `pc/rff_offline.py`, `pc/exp_lot_hypothesis.py` |

**QUOTED FROM `SEVEN_NIGHT_PREREG.md` §10–§11 AND NOT RE-RUN:** every SFO
centroid, every pairwise separation, every P3 step, every yield percentage,
every cross-receiver disagreement. `rff_offline.py` was **not** re-executed on
any night. Analyses in §2, §4 and §5 below are arithmetic on the document's own
published tables. If those tables are wrong, so are these.

That distinction is the point of this section. **§3 is the finding that would
survive the tables being wrong**, because it comes from the code.

---

## 1. Night 4's batteries did not last, and two "nothing died" claims are
artifacts of where the analysis stopped looking

### What the record says

`SEVEN_NIGHT_PREREG.md` §10.4:

> All three transmitted for the entire capture on both receivers. **This is the
> first night of the series where nothing died, and it is the direct result of
> the batteries being charged before the run** — a deliberate operator change
> from night 3.

§10.6, of night 6:

> the first night of the series on which **no beacon stops transmitting at
> all** — all three run to the last second on both receivers.

### What the file says

`d0wd_20260901_035805.csv`, first frame `1788253086170328`, last frame
`1788325778086578` → **72,691.9 s = 20.19 h**, not the 12,225 s §10.4 records.
That much is already known and reconciled in `UNPLANNED_20H_20260901.md`, which
states correctly that the prereg saw 3 h 24 m of a 20 h file.

Frames per hour, measured this session:

| hour | B1 `a4:f0` | B2 `28:05` | B3 `f4:2d` |
|---:|---:|---:|---:|
| 0 | 132,512 | 189,695 | 172,723 |
| 1 | 126,587 | 184,545 | 187,061 |
| 2 | 121,403 | 183,714 | 192,755 |
| 3 | 107,044 | 158,760 | 179,270 |
| 4 | 146,230 | 174,353 | 164,477 |
| 5 | 128,175 | 164,102 | 180,911 |
| **6–19** | **0** | 185,026 – 213,249 | **0** |
| 20 | 1,549 | 37,243 | 2,550 |

Exact transition times:

| beacon | last frame before the gap | returns at | gap |
|---|---:|---:|---:|
| B1 `a4:f0` | **21,300.2 s (5.92 h)** | 72,655.1 s (20.18 h) | 14.27 h |
| B3 `f4:2d` | **21,519.5 s (5.98 h)** | 72,644.9 s (20.18 h) | 14.20 h |
| B2 `28:05` | — runs 0 → 72,691.9 s continuously — | | |

The return at 20.18 h is 00:08:53. Night 5's capture starts at **00:09:49**.
That is the operator swapping batteries to set up the next night, recorded by a
capture that had not been stopped.

### Consequence

**Night 4's battery beacons died at 5.92 h and 5.98 h — squarely inside the
range every other night shows.**

| night | capture | B1 dies | B3 dies |
|---|---:|---:|---:|
| 1 | 26,644 s | 18,138 | 20,446 |
| 2 | 23,557 s | 22,047 | 21,081 |
| 3 | 16,821 s | **1,769** *(flat cell, §10.3)* | 9,059 |
| **4** | **72,692 s** | **21,300** | **21,520** |
| 5 | 29,479 s | 22,871 | 19,436 |
| 6 | **20,004 s** | *censored at capture end* | *censored at capture end* |
| 7 | 24,486 s | *censored at capture end* | 19,300 |

Setting aside night 3, which §10.3 already identifies as a flat cell: **B3 dies
between 19,300 s and 21,520 s on all five nights where it is observable — a
37-minute spread across five nights.** B1 spans 18,138–22,871 s. This is a
hardware constant, not a variable the operator improved.

Three statements in the record follow from not seeing it:

1. **§10.4's "first night where nothing died … the direct result of the
   batteries being charged."** Both battery beacons died on schedule. The claim
   is an artifact of a 12,225 s window on a 72,692 s file. **The causal
   attribution to charging has no support.**
2. **§10.6's "first night on which no beacon stops transmitting at all."**
   Night 6's capture ran 20,004 s. The batteries die at ~21,000 s. Nothing
   stopped transmitting because the recording stopped first.
3. **The death-order watch**, opened in §10.5 and continued in §10.7 ("B3 first
   again, as on night 5"). Across all seven nights: **B1 first on nights 1, 3
   and 4; B3 first on nights 2, 5 and 7. Three–three.** The watch compared only
   the two nights that agreed. There is no death order.

**No scored figure is affected.** Every scored window is 2,400–4,700 s, more
than four hours inside the intact stretch on every night. What is affected is
the causal story the document tells about its own bench.

---

## 2. Night 5 is the one night that partially reproduces the co-location
result, and P1's pair-only scoring could not see it

P1 scored one pair, B2–B3. Scoring instead the **spread of the whole
three-beacon population** — (max − min) of the raw SFO centroids, in
`BETWEEN_UNIT_SD` units — gives:

| night | s3 | d0wd |
|---:|---:|---:|
| 1 | 8.6 | 10.1 |
| 2 | 4.1 | 33.0 |
| 3 *(2 beacons only)* | 3.2 | 5.4 |
| 4 | 5.3 | 24.1 |
| **5** | **1.6** | **2.9** |
| 6 | 6.4 | 10.8 |
| 7 | 6.6 | 3.7 |

**Night 5 is the minimum on both receivers independently** — 3.9× below the
median on s3 and 3.8× below it on d0wd. On night 5 the three co-located
beacons came closer to being one population than on any other night of the
series, and both receivers agree that they did.

It is also where the only sub-bar pairs in the series live. Of 38
beacon-pair-nights, four fall below P1's 1.0σ line, and the two closest are
both night 5:

| | | |
|---|---|---:|
| night 5 | s3, B1–B2 | 0.25σ |
| night 5 | d0wd, B2–B3 | 0.84σ |
| night 6 | s3, B1–B2 | 0.84σ |
| night 7 | s3, B1–B2 | 0.97σ |

*(computed from the published centroids in `BETWEEN_UNIT_SD` units — see §3 for
why these do not match §10's tabulated σ.)*

Night 5 is also, independently: the night with the **smallest cross-receiver
disagreement** of the series (0.0030 / 0.0032 / 0.0049), the **first night with
no yield victim**, and the night with the **lowest blind classification
accuracy** reported anywhere in the series (s3 76.8%, d0wd 67.2%). §10.6 notes
that high accuracy and co-location collapse are the same measurement read in
two directions. Night 5 is that measurement read the other way, and the
document does not connect them.

**What this is not.** The per-night spreads on the two receivers do not
correlate across the series (Spearman ρ = −0.09, p = 0.87, n = 6 full nights),
so "tightness" is **not** a global property of a night that both receivers
inherit. Night 5 being the minimum on both is one coincidence in six, which is
not significant on its own. It is recorded as the most interesting unscored
observation in the series, not as a result.

**It does not rescue P1.** P1 failed on night 5 as scored, and night 5's 1.6σ
population spread is still far above the 0.2σ that 28 August produced.

---

## 3. The two σ in this series are different units, and §2 says they are the
same one

**This is the finding that does not depend on the document's tables.**

`SEVEN_NIGHT_PREREG.md` §2 states:

> `BETWEEN_UNIT_SD = 0.00237` (`pc/exp_ambient_separation.py:79`). **All σ
> figures in this document are in those units.**

That is true of §11's P3 table — 0.0166 / 0.00237 = 7.0σ reproduces exactly. It
is **not** true of any pairwise separation table in §10.

Read out of the source this session:

- `pc/rff/discriminator.py:2` — the feature space is **(CFO, SFO)**, two
  dimensions.
- `pc/rff/discriminator.py:116–140` — `separation_matrix()` returns *"pairwise
  centroid Mahalanobis distances under pooled covariance"*, where the pool is
  built from `m.cov * (m.n - 1)` summed over **every characterized source in the
  library**, `m.cov` being that source's own window-to-window covariance.
- `pc/rff_offline.py:340–341` — this is what §10's separation tables print.
- `pc/exp_lot_hypothesis.py:27–34`, written before this series:

  > `Discriminator.separation_matrix()` pools covariance over *every*
  > characterized source in the library. Run over a whole session that includes
  > ambient traffic, the three-beacon sigmas are therefore computed against a
  > pooled covariance that ambient devices helped set, **and are not the
  > three-beacon numbers the hypothesis is about.**

`exp_lot_hypothesis.py` exists *because of* this defect. §9's commands run
`rff_offline.py` with no `--only-macs`, so the series scored P1 on the path that
warning is about.

> #### CORRECTION, 2026-09-04, same day — the ambient half of this was wrong
>
> The paragraph above originally continued: *"Night 4's d0wd capture alone
> carries **~250 distinct MACs**, several with thousands of frames."* It was
> offered as evidence that ambient traffic had inflated P1's pooled covariance.
>
> **Two things are wrong with it and the operator caught both.**
>
> First, most of those ~250 MACs are not devices. `d0wd` fabricates MAC
> addresses from dropped characters in the serial stream — a phenomenon this
> corpus already documents (`COLOCATED_0823`'s 126 fabricated MACs, several one
> bit-flip from a real beacon; the night-4 listing contains
> `f4:2d:c9:70:06:ef`, `28:05:a5:2f:1c:f6`, `a4:f0:0f:77:0e:fd` and dozens more
> of the same shape). **Counting MAC strings is not counting transmitters.**
>
> Second, and decisively, it was never checked. **It has now been measured on
> all fourteen night-receiver runs** (§9's method): the number of non-beacon
> sources that entered the pooled covariance is **zero, on every night, on both
> receivers.** A source needs 4 windows to enter the analysis and 5 training
> windows to enter the pool — 256 and ~576 accepted frames respectively — and
> no corrupt-row ghost or ambient device ever gets there inside a 2,300 s
> window. Sources seen and dropped for having under 4 windows: 0 to 2 per run.
>
> This is failure mode **B** — a source characterised without being opened.
> `exp_lot_hypothesis.py`'s warning is real in general and does not apply here.
>
> **What survives is the rest of §3, and it survives measured rather than
> inferred** — see §9C. The pooled covariance really is the unit P1 is scored
> in, it really does swing 5.9× across the series, and the cause is simply the
> three beacons' own window-to-window scatter changing from night to night. No
> ambient device is needed to produce it.

### Back-solving the unit from the document's own numbers

Implied pooled SD = |ΔSFO between the two centroids| ÷ the σ §10 reports:

| night | rx | \|ΔSFO\| | §10 σ | implied SD | × 0.00237 |
|---:|---|---:|---:|---:|---:|
| 1 | s3 | 0.0081 | 9.2 | 0.00088 | 0.37 |
| 1 | d0wd | 0.0064 | 6.8 | 0.00094 | 0.40 |
| 2 | s3 | 0.0045 | 3.4 | 0.00132 | 0.56 |
| 2 | d0wd | 0.0730 | 60.6 | 0.00120 | 0.51 |
| 3 | s3 | 0.0077 | 14.6 | 0.00053 | 0.22 |
| 3 | d0wd | 0.0128 | 17.9 | 0.00072 | 0.30 |
| 4 | s3 | 0.0067 | 9.5 | 0.00071 | 0.30 |
| 4 | d0wd | 0.0422 | 14.9 | 0.00283 | 1.20 |
| 5 | s3 | 0.0039 | 4.4 | 0.00089 | 0.37 |
| 5 | d0wd | 0.0020 | 1.9 | 0.00105 | 0.44 |
| 6 | s3 | 0.0131 | 26.1 | 0.00050 | 0.21 |
| 6 | d0wd | 0.0257 | 46.4 | 0.00055 | 0.23 |
| 7 | s3 | 0.0157 | 30.8 | 0.00051 | 0.22 |
| 7 | d0wd | 0.0029 | 6.1 | 0.00048 | 0.20 |

Range **0.00048 – 0.00283 rad/sc, a 6.0× swing**, against a `BETWEEN_UNIT_SD`
that is fixed at 0.00237. Median 0.00088 = **0.37 ×** the stated unit.

The identification is corroborated by the document itself: §10.7 records
per-beacon-night window IQRs "near 0.0005–0.0011", which for a Gaussian implies
SD 0.00037–0.00082 — the same band the back-solve lands in. **The σ P1 was
scored in is the within-night, window-to-window scatter. The σ P3 was measured
in is the between-unit spread.**

### What follows, and what does not

**Three things follow.**

1. **P1's "1.0σ" bar stood for a different ΔSFO every night.** Nothing moved —
   the beacons stayed within an inch of their positions for the whole series
   (operator statement, and §2's arrangement clause was photograph-checked after
   night 2). What changed is the *threshold*: expressed in rad/subcarrier, the
   bar ranged from 0.20× to 1.20× `BETWEEN_UNIT_SD`, because it is defined by
   that night's own window-to-window scatter. A pair separated by a fixed
   physical ΔSFO would have been scored at 1.0σ on one night and 6σ on another.
2. **§11's headline magnitude is understated and in the wrong unit.** It reads
   *"a single stationary beacon wanders between three and thirty times further,
   night to night, than the bar P1 was asked to clear."* Putting both in
   `BETWEEN_UNIT_SD`: the floor is 3.5–30.5×, the bar is ~0.37×, so the true
   ratio is roughly **9× to 82×**.
3. **The drift floor of the CFO axis had never been measured.**
   `SEVEN_NIGHT_PREREG.md` contains the string "CFO" **zero times**, and P1's
   statistic is two-dimensional. P3 characterised one of the two axes P1's bar
   lives in. **This has now been closed — see §9, and the answer is that the
   gap cost nothing.**

**One thing does not follow: the verdict does not change.** §4's
UNINTERPRETABLE cell requires P1 to fail and P3 to show a floor ≥ 1.0σ. Both
hold, and correcting the units makes the gap between floor and bar *wider*, not
narrower. **P1 is still UNINTERPRETABLE and this strengthens the reading rather
than undermining it** — there are now two independent reasons the design could
not resolve its question, and this one is worse, because it is a defect in the
ruler rather than a limit on the subject.

---

## 4. The drift floor is a property of the receiver, and "max step" is the
least robust way to state it

§11 scores P3 on the **maximum** night-to-night step. Recomputing the same
published values as a **median absolute deviation of the nightly level** —
robust to a single anomalous night — gives a materially different picture:

| rx | beacon | MAD (σ) | §11 max step (σ) | inflation |
|---|---|---:|---:|---:|
| s3 | B2 | 1.48 | 5.8 | 3.9× |
| s3 | B3 | **0.34** | 7.0 | 20.7× |
| s3 | B1 | **0.95** | 7.0 | 7.4× |
| d0wd | B2 | **0.55** | 3.5 | 6.4× |
| d0wd | B3 | 4.56 | 30.5 | 6.7× |
| d0wd | B1 | 3.04 | 23.5 | 7.7× |

**Three of six cells have a robust floor below 1.0σ.** P3 as written asks
whether wander *exceeds* 1.0σ, and the maximum step does, so **P3 still HELD as
frozen** — this is not a rescoring. But the sentence that will get quoted out of
§11 — that the floor "is between three and thirty times" the bar — describes
the tail of the distribution, not its centre.

The stronger and more useful statement the same data supports:

> **The drift floor is not one number. It is ~0.3–1.5σ on s3 and ~0.6–4.6σ on
> d0wd, and which receiver you use matters more than which beacon you point
> at.**

`s3`'s B3 is the extreme case and is worth naming on its own: **+0.0197,
+0.0204, +0.0189, +0.0188, +0.0038, +0.0204, +0.0224** across seven nights. Six
of the seven sit inside a 0.0036 band — 1.5σ total — and night 5 is a single
6.3σ excursion. That cell is the most stable repeated measurement anywhere in
this corpus, and §11's table reports it as "7.0σ max" because one outlier night
produces two large consecutive steps. `RECEIVER_DIVERGENCE_PREREG.md`'s D3
failure is the same night-5 excursion seen from the other side.

---

## 5. Cross-receiver disagreement separates perfectly on yield-victim nights,
and the check that dismissed it compared two nights of the same class

Mean |s3 − d0wd| across beacons, by night, against whether d0wd had a beacon
below 90% yield:

| night | victim on d0wd? | mean \|s3−d0wd\| | max |
|---:|---|---:|---:|
| 2 | **yes** — B3 at 30.1% | **0.0305** | 0.0591 |
| 4 | **yes** — B1 53.0%, B3 84.7% | **0.0296** | 0.0534 |
| 3 | no | 0.0040 | 0.0066 |
| 5 | no | 0.0037 | 0.0049 |
| 6 | no | 0.0049 | 0.0078 |
| 7 | no | 0.0075 | 0.0162 |

**Perfect separation.** The smallest victim night (0.0296) is 3.9× the largest
non-victim night (0.0075); victim mean is 5.95× non-victim mean. Mann-Whitney
gives p = 0.067, which is the **smallest p-value obtainable** with 2 against 4,
so the test is saturated rather than weak. Night 1 is excluded because §10 does
not publish a per-beacon yield table for it.

§10.6a's advance consistency check — *"if no victim and small disagreement are
one phenomenon, a night with no victim should show small disagreement"* — was
scored by comparing **night 5 (0.0037) with night 6 (0.0049)**. Both are
non-victim nights. That is a within-class comparison used to argue against a
between-class distinction, and the 0.0012 difference between them is smaller
than the spread among the non-victim nights themselves.

**This is not a rescoring of D2** and it must not be treated as one: it is
post-hoc, the classes are 2 against 4, and the two quantities are not
independent — window-level fit quality drives both the inlier gate and the
centroid's reliability, so a mechanical coupling is expected. What is being
claimed is narrower and it is about method: **the evidence §10.6a read as
pointing against the pairing does not point either way, because it never
crossed the class boundary.**

---

## 6. B2 is the stable beacon on d0wd at two timescales, measured two
independent ways — and s3 shows no such split

`RECEIVER_DIVERGENCE_PREREG.md` records that the affected beacon changes night
to night and that B2 is never one. `UNPLANNED_20H_20260901.md` §4 separately
reports hour-to-hour stability within one 20-hour run. Nobody has put them
side by side:

| rx | beacon | §11 max nightly step (σ) | ratio to that rx's B2 | 20H hourly-median SD | ratio to B2 |
|---|---|---:|---:|---:|---:|
| s3 | B2 | 5.8 | 1.00 | 0.00305 | 1.00 |
| s3 | B3 | 7.0 | 1.21 | 0.00392 | 1.29 |
| s3 | B1 | 7.0 | 1.21 | 0.00295 | 0.97 |
| d0wd | B2 | 3.5 | 1.00 | 0.00430 | 1.00 |
| d0wd | B3 | 30.5 | **8.71** | 0.01250 | **2.91** |
| d0wd | B1 | 23.5 | **6.71** | 0.02172 | **5.05** |

Spread across beacons: **s3 1.21× nightly and 1.33× hourly; d0wd 8.71× nightly
and 5.05× hourly.**

Two different timescales (hours within one run; nights across seven runs), two
different sampling schemes (first 200 frames of each hour; full scored
windows), two documents written a day apart — **same ordering, same conclusion:
d0wd's instability is beacon-specific and s3's is not.** That is the closest
thing to an independent replication anywhere in the seven-night material.

**Confounds, stated rather than dismissed.** B2 `28:05` is the mains unit
(operator statement at the bench, 2026-08-31, §10.3) and it is also the beacon
with the highest frame rate — on night 4 hours 0–5 it delivers roughly 1.3×
B1's frames per hour. Higher yield means tighter window statistics
independently of any clock property. Power source and frame rate are not
separated by anything in this corpus. `ROTATION_PREREG.md` §0.0.1's labelling
caveat also still applies.

**The cheap test the corpus keeps naming and has never run** is one night with
the power assignment swapped. It is named in §10.4 and remains undone.

---

## 7. What to do with this

In rough order of value per hour:

1. ~~**Measure the CFO drift floor**~~ **— DONE, 2026-09-04. See §9.**
2. ~~**Rerun one night's separation with `--only-macs`**~~ **— superseded. The
   §9 runs measured the pool membership directly: no ambient source ever
   entered it, so there is nothing for `--only-macs` to remove.**
3. **Correct §10.4's battery claim and §10.6's "nothing died" claim in place**,
   in the corpus's own style — note alongside, original left visible.
4. **Restate §11's magnitude sentence in one unit**, and add the robust floor
   from §4 above beside the max-step figure.
5. Leave §5 and §2 alone as observations. Both are post-hoc, both are
   underpowered, and neither is worth a pre-registration on a bench that is
   being retired.

## 8. What this re-read did not do

- ~~`rff_offline.py` was **not** re-run on any night.~~ **Superseded by §9,
  added later the same day: the pipeline was re-run on all fourteen
  night-receiver cells, and §10's SFO table reproduces to within 0.0001 rad/sc
  (0.04σ) on all 40 cells. §2, §4 and §5 above therefore now rest on verified
  inputs.**
- Only `d0wd_20260901_035805.csv` was scanned frame by frame. The matching s3
  file was not, so the night-4 death times in §1 are **d0wd-only**;
  `UNPLANNED_20H` §2 reports the same six-hour shape on s3 and that is
  consistent, but it was not re-measured here.
- No pre-registration was scored, amended, or reopened.
- Nothing here has been tested for whether it survives the corpus's own
  multiple-comparison discipline. Five candidate patterns were looked for and
  five are reported; the s3-B2 monotone decline across nights (Spearman
  ρ = −0.821, p = 0.023) is **omitted from the findings above** precisely
  because it does not survive correction across the six cells tested.

---

# 9. The CFO axis, measured — added 2026-09-04, after §1–§8

§3 flagged that P1's statistic is a two-dimensional (CFO, SFO) Mahalanobis
distance while P3 characterised only SFO, and called closing that gap the
cheapest remaining experiment on the project. It has been run. **No new capture
was taken; every figure below comes from the seven nights already on disk.**

## 9A. Method, and why the numbers can be trusted

Each of the fourteen night-receiver captures was byte-sliced to its scored
window with a 500 s lead-in (bisection on file position; `pc_time_us` is
monotonic), and the project's own pipeline was run on the slice —
`rff_offline.collect_observations`, so `FrameEstimator`, `WindowAggregator`,
gates and window size are the shipped ones and no DSP is reimplemented. Only
the reporting is new: full-precision medians, the pooled covariance itself, and
the list of which sources entered it.

Windows 2,400–4,700 s absolute on nights 1 and 3–7; **5,520–7,820 s on night
2**, matching §10.2's T0 = 3,120 s. Raw, no `--ref-mac`, shipped gates.

**Reproduction check — this is what licenses everything else.** Against
`SEVEN_NIGHT_PREREG.md` §10's published SFO centroids, **40 of 40 cells agree,
largest discrepancy 0.0001 rad/sc = 0.04σ**, which is the document's own
rounding. The slice-with-lead-in method is therefore doing nothing to the
numbers, and §10's table is exactly reproducible fifteen days after it was
written.

## 9B. No ambient source ever entered the pooled covariance

| | sources in pool | non-beacon in pool | seen but under 4 windows |
|---|---|---|---|
| all 14 runs | 3 (2 on night 3, B1 off air) | **0** | 0–2 |

This is the measurement that retires the ambient half of §3 — see the
correction there.

## 9C. The unit P1 is scored in, measured rather than back-solved

| night | s3 pooled SD | × 0.00237 | d0wd pooled SD | × 0.00237 |
|---:|---:|---:|---:|---:|
| 1 | 0.00082 | 0.35 | 0.00095 | 0.40 |
| 2 | 0.00121 | 0.51 | 0.00122 | 0.52 |
| 3 | 0.00054 | 0.23 | 0.00068 | 0.29 |
| 4 | 0.00069 | 0.29 | **0.00291** | **1.23** |
| 5 | 0.00085 | 0.36 | 0.00124 | 0.52 |
| 6 | 0.00049 | 0.21 | 0.00055 | 0.23 |
| 7 | 0.00052 | 0.22 | 0.00049 | 0.21 |

**Measured range 0.00049 – 0.00291 rad/sc, a 5.9× swing; median 0.00076 =
0.32 × `BETWEEN_UNIT_SD`.** §3's back-solve from the published tables predicted
0.00048 – 0.00283, median 0.00088. **The prediction was right.**

Night 4 d0wd is the one cell above `BETWEEN_UNIT_SD`, and it is the night B1
ran at 53.0% yield — degraded windows inflate the pool, exactly as §10.2's
`--min-inlier` experiment showed. **The bar moves with the night's own noise.**

## 9D. CFO per beacon-night, Hz

| night | rx | B2 | B1 | B3 |
|---:|---|---:|---:|---:|
| 1 | s3 | +0.124 | −0.079 | +0.233 |
| 1 | d0wd | +0.153 | +0.028 | +0.056 |
| 2 | s3 | −0.123 | −0.023 | +0.075 |
| 2 | d0wd | +0.039 | −0.093 | −0.124 |
| 3 | s3 | −0.196 | *off air* | −0.289 |
| 3 | d0wd | +0.262 | *off air* | +0.151 |
| 4 | s3 | +0.208 | +0.205 | +0.503 |
| 4 | d0wd | +0.389 | −0.010 | +0.220 |
| 5 | s3 | −0.184 | +0.130 | +0.171 |
| 5 | d0wd | +0.187 | −0.130 | −0.095 |
| 6 | s3 | +0.249 | −0.050 | +0.508 |
| 6 | d0wd | +0.153 | −0.003 | −0.212 |
| 7 | s3 | +0.070 | +0.346 | +0.143 |
| 7 | d0wd | +0.210 | −0.031 | +0.372 |

Building the yardstick exactly as `BETWEEN_UNIT_SD` was built — *"sd over the
3 units of their grand means"*, `pc/exp_thermal_evidence.py:129` — over both
receivers and all seven nights:

> **`BETWEEN_UNIT_SD_CFO` = 0.053 Hz** (grand means B2 +0.110, B1 +0.024,
> B3 +0.122). Per receiver: 0.086 Hz on s3, 0.120 Hz on d0wd.

Raw rather than reference-corrected, unlike the published SFO constant.
Recorded as a limitation, not corrected for.

## 9E. The CFO drift floor, scored the way §11 scored SFO

Night-to-night |ΔCFO| in units of `BETWEEN_UNIT_SD_CFO`:

**s3**

| beacon | 1→2 | 2→3 | 3→4 | 4→5 | 5→6 | 6→7 | max | > 1.0σ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B2 | 4.6 | 1.4 | 7.6 | 7.3 | 8.1 | 3.4 | **8.1** | 6 / 6 |
| B3 | 3.0 | 6.8 | 14.8 | 6.2 | 6.3 | 6.8 | **14.8** | 6 / 6 |
| B1 | 1.0 | n/a | n/a | 1.4 | 3.4 | 7.4 | **7.4** | 4 / 4 |

**d0wd**

| beacon | 1→2 | 2→3 | 3→4 | 4→5 | 5→6 | 6→7 | max | > 1.0σ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B2 | 2.1 | 4.2 | 2.4 | 3.8 | 0.6 | 1.1 | **4.2** | 5 / 6 |
| B3 | 3.4 | 5.2 | 1.3 | 5.9 | 2.2 | 10.9 | **10.9** | 6 / 6 |
| B1 | 2.3 | n/a | n/a | 2.3 | 2.4 | 0.5 | **2.4** | 3 / 4 |

**Read naively this fires harder than P3 did** — 30 of 32 steps clear 1.0σ,
against P3's more mixed record. **Read naively it would be wrong**, and §9F is
why.

## 9F. The control that kills it: CFO cannot measure itself

Standard error of one night's median, from that night's own IQR and window
count (SE ≈ 1.2533 × σ / √n, σ = IQR / 1.349; median 2,418 windows per
beacon-night):

| feature | between-unit SD | median within-window IQR | IQR ÷ between-unit SD | **SE of one night's median** |
|---|---:|---:|---:|---:|
| **SFO** | 0.00237 rad/sc | 0.0009 | **0.39** | 0.000017 = **0.007σ** |
| **CFO** | 0.053 Hz | 5.97 Hz | **111.9** | 0.116 Hz = **2.2σ** |

**Measuring a beacon's SFO for one night is 140× more precise than the spread
it is trying to resolve. Measuring its CFO for one night is 2.2× less precise
than that spread.**

A difference of two such estimates carries SE ≈ 2.2 × √2 = **3.1σ**. The
observed CFO steps in §9E have a median near 3.4σ.

> #### CORRECTION, 2026-09-04 — this argument was not a control, and the
> operator said so
>
> The sentence that stood here read: *"The entire CFO drift floor is the
> standard error of estimating CFO. There is no drift to see, because there is
> no measurement."*
>
> **That was two numbers compared, not a measurement.** The SE above comes from
> `SE ≈ 1.2533σ/√n`, which assumes the windows are independent. Thirty-second
> windows in one room are almost certainly autocorrelated, so the formula is
> the wrong tool and the conclusion was asserted rather than tested. The
> operator's objection was exactly right: *seven nights in a row was the method
> for measuring drift — so why doesn't it work here?*
>
> §9I is the test that answers it, run on the data rather than derived from an
> assumption. **It reaches a similar destination by a legitimate route, and it
> corrects the claim: there is a small real between-night CFO component on s3,
> and none detectable on d0wd.** The blanket "there is no measurement" is
> withdrawn.

The same conclusion arrives independently from the separation side. Recomputing
every pairwise σ from the SFO axis alone, under the same pooled covariance:

> **CFO's contribution to P1's separations is a median of −1.4%** (range −18.7%
> to +11.7%, 38 pairs). It reduces the separation slightly more often than it
> increases it — the signature of an axis contributing variance and no signal.

This independently reproduces `AMBIENT_SEPARATION.md` §62's *"CFO is
established dead on this capture — 0.01σ to 0.21σ"*, on a different dataset,
seven nights instead of one, by a different route.

## 9G. What this settles

1. **The §3 gap cost nothing, and that is now a measurement rather than a
   hope.** P3 characterised the only axis of P1's statistic that carries
   information. **The UNINTERPRETABLE verdict stands, unchanged, and is now
   supported across the full feature space.**
2. **`BETWEEN_UNIT_SD_CFO` = 0.053 Hz is a new number this project did not
   have**, and its main use is to show that CFO's own estimation noise is 2.2×
   larger than it.
3. **The 2-D feature vector should be 1-D.** `rff/discriminator.py` carries CFO
   through every centroid, covariance and χ² threshold, and on this bench it
   contributes a median −1.4% to separation while consuming one of the two
   degrees of freedom the χ² gates are calibrated against (`CHI2_95 = 5.991`,
   `CHI2_99 = 9.210`, both 2-dof). **Dropping to SFO alone would need 1-dof
   thresholds (3.841 / 6.635) and would make every STRANGER/MARGINAL verdict in
   the corpus stricter.** Not a change to make on a bench being retired, but it
   is the honest description of the estimator.
4. **The retirement question is answered.** The cheapest remaining experiment
   has been run and it returned "nothing here." That is a reason to stop, not a
   reason to look for the next one.

## 9H. What §9 did not do

- CFO was measured **raw**; `BETWEEN_UNIT_SD` is published from
  reference-corrected data. The two yardsticks are not built on identical
  footing and 9D says so.
- The 500 s lead-in was validated only by the 40-cell reproduction in §9A, not
  by a lead-in sweep. §10.2 ran that sweep on night 2 d0wd (520 s vs 2,020 s,
  identical to every digit); this assumes it generalises.
- Nothing was pre-registered. §9E's floor was computed after §9D was seen. It
  is reported because §9I destroys it, not because it stands.

---

# 9I. The variogram — the test that actually settles it

§9F compared two numbers and called it a control. This is the measurement.

**Method.** Every accepted window's `(ts_pc, cfo, sfo)` was dumped to disk
(`pc/dump_windows.py`, results in `data/cache/windows/`) — 14 cells, ~1.8 MB,
so every follow-up below is free. Each night's 2,300 s scored window was cut
into **8 blocks of ~288 s**, a median taken per block, and the median
|difference| computed at increasing separations. Between-night points use the
full-window medians.

**If a quantity genuinely drifts, |difference| must grow with separation.** A
random walk cannot get closer to itself over time. Flat means noise; falling
means noise that averages down as more windows enter the estimate.

### SFO — the positive control

| separation | s3 | d0wd |
|---|---:|---:|
| ~5 min | 0.06 | 0.08 |
| ~10 min | 0.08 | 0.15 |
| ~19 min | 0.15 | 0.21 |
| ~34 min | 0.17 | 0.42 |
| **1 night** | **0.79** | **5.85** |
| 2 nights | 0.82 | 3.44 |
| 3 nights | 1.66 | 4.54 |

*(units of `BETWEEN_UNIT_SD` = 0.00237 rad/sc)*

**Monotone, and it jumps by an order of magnitude at the night boundary.** SFO
is nearly perfectly stable inside a night — 0.06σ over five minutes — and moves
0.8σ to 5.9σ across one. **This is what real drift looks like, and it is why
the seven-night design was the right instrument for SFO.** It also re-derives
§11's result by an independent route.

### CFO — flat, and then falling

| separation | s3 | d0wd |
|---|---:|---:|
| ~5 min | 9.41 | 7.30 |
| ~10 min | 12.10 | 7.89 |
| ~19 min | 10.46 | 7.17 |
| ~34 min | 10.51 | 7.14 |
| **1 night** | **6.31** | **2.34** |
| 2 nights | 4.80 | 2.07 |
| 3 nights | 2.88 | 2.78 |

*(units of `BETWEEN_UNIT_SD_CFO` = 0.053 Hz)*

Two things, and the second is the one that decides it.

**CFO moves ~7–12σ inside twenty minutes**, where SFO moves 0.15σ. In its own
between-unit units, CFO is two orders of magnitude noisier at every timescale.

**And the between-night values are *smaller* than the within-night ones.** A
drift process cannot do that. What can is estimation noise: the between-night
points are built from ~2,400 windows and the block points from ~300, an 8×
difference, so pure white noise predicts the between-night figure should be
**√8 = 2.83× smaller.**

| receiver | predicted drop (pure noise) | observed drop | reading |
|---|---:|---:|---|
| d0wd | 2.83× | **3.05×** (7.14 → 2.34) | indistinguishable from pure noise |
| s3 | 2.83× | **1.66×** (10.51 → 6.31) | drops less than noise alone would |

**So d0wd's CFO carries no between-night information at all, and s3's carries a
little.** The split-half decomposition agrees and localises it: of six
beacon-receiver cells, four show no detectable between-night drift, while
**s3/B3 shows a drift SD of 4.32σ_CFO and s3/B1 0.92σ_CFO.**

### What this means, stated at the strength the data supports

1. **The seven-night design did its job.** It is a sound instrument for
   measuring between-night drift — the SFO table proves that. The reason it
   returns an unusable answer for CFO is not the design.
2. **"The CFO drift floor" is not a well-defined quantity on this bench.**
   Drift is meaningful when a quantity is stable at short timescales and moves
   at long ones. CFO moves ~10σ in five minutes. There is no stable value for
   it to drift *from*.
3. **There is a small real between-night CFO component, on s3 only.** §9F's
   flat "there is no measurement" was too strong and is withdrawn. It is small
   relative to CFO's own five-minute scatter, it appears on one receiver, it
   survives no multiple-comparison correction across six cells, and it is
   **post-hoc**.
4. **None of this changes anything downstream**, because §9F's other, untouched
   result stands on its own: CFO contributes a **median −1.4%** to P1's
   pairwise separations. Whatever s3's B3 is doing between nights, it is not
   helping to tell the beacons apart.
5. **The verdict is unchanged.** P1 remains UNINTERPRETABLE, and it now rests
   on a floor measured on the axis that carries the information, with the other
   axis shown by two independent methods to carry almost none.
