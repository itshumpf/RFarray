# BLIND CLUSTERING — can the fingerprint space group transmitters with no
# MAC address anywhere in the features or the grouping?

**Written 2026-08-23, before any clustering was run. Part I (§0–§8) is the
frozen design; it was committed to disk in full before the first replay
command was issued and is not edited afterwards. Part II (§9 onward) is the
result, appended after the fact.** If a criterion in Part I reads as though
it were written to fit the answer, check the mtimes: Part I predates every
number in Part II.

---

## 0. Why this exists

Every analysis in this repo groups by MAC first. `pc/rff_offline.py:239`
keys its estimators and aggregators on `mac`; `pc/rff/discriminator.py`
learns one model per MAC; `pc/mac_census.py` counts frames per MAC;
`docs/AMBIENT_SEPARATION.md` §2 and `docs/IDENTITY_STABILITY.md` both take
the MAC as the identity and ask how well the signal tracks it.

The operator's objection, which is the whole motivation for this pass:

> Modern devices randomise their addresses. One physical device therefore
> appears as many short-lived MACs. Each fragment falls under the 20-frame
> floor, and **every fragment gets discarded while the device was
> transmitting plenty.** The near-total ambient rejection rate may be an
> artefact of fragmenting one device across many labels rather than a
> property of the signal.

That objection is not speculative here. `docs/AMBIENT_SEPARATION.md` §2
already records `1e:ce:51:f3:0d:fa` as `1c:ce:51:f3:0d:fa` **with exactly
the locally-administered bit flipped and nothing else changed**, counted as
two sources by every tool in the repo. So the repo has already seen one
device split in two by its own labelling and did not have a technique that
could put it back together. This pass builds that technique and — before
using it — tests whether it works at all.

**Nothing in this document is a device-ID capability claim.** It is an
analysis of `data/raw/`, in the phase domain (`pc/rff/`) only. No occupancy
(`pc/occ/`, amplitude domain) figure appears here and none may be fused with
one.

---

## 1. Scope, and what is deliberately out of scope

**One session, two receivers, never pooled.**

| | `d0wd_20260823_014740.csv` | `s3_20260823_014740.csv` |
|---|---|---|
| `node_id` | 68 | 108 |
| data rows | 3,344,351 | 4,330,849 |
| span | 24,123.123 s = 6.7009 h | 24,123.100 s = 6.7009 h |

Row counts and span are `docs/COLOCATED_0823.md` §0's, and this pass
re-derives them rather than trusting them (§8, check 1).

**Single session only.** `docs/IDENTITY_STABILITY.md` established that
signatures do not survive across sessions, so a cross-session clustering
would fail for reasons that have nothing to do with the question being
asked. Anything cross-session is out of scope and no cross-session number
will be quoted.

**Each receiver clustered separately, never pooled.**
`docs/COLOCATED_0823.md` §5.1 measures the same-beacon receiver-to-receiver
SFO difference at 0.71σ / 16.33σ / 6.79σ, and §5.4 shows it is not
common-mode across beacons. `docs/AMBIENT_SEPARATION.md` §5 measures two
receivers disagreeing about a single ambient source by **86.1 ×
`BETWEEN_UNIT_SD`**. Which receiver heard a frame dominates identity in this
feature space. Pooling the two files would cluster the receivers, and the
result would be worthless.

**The 013537 pair is not used.** It is a separate 317 s run that ended
twelve minutes before this one started (`docs/COLOCATED_0823.md` §0). It is
used in this pass only as a throughput probe for feasibility, never fused.

---

## 2. Corrupt-row screening — first, and by both routes

This matters more here than in any previous pass. **A fabricated MAC becomes
a spurious singleton cluster, and spurious singletons are exactly the
evidence this pass is looking for.** `docs/COLOCATED_0823.md` §2 establishes
that on the d0wd, **126 of its 166 addresses exist only on corrupt rows**;
unscreened, this analysis would report 126 fake devices.

Both independent routes that `docs/OVERNIGHT_2026-08-22.md` §1 requires are
used, because `docs/COLOCATED_0823.md` §3.3 shows **neither alone is
sufficient** — the field screen alone leaves three corrupt rows in on this
very file:

1. **Field plausibility on six columns** — `node_id` equal to the file's own
   mode, `env_id == 0`, `channel` equal to the file's own mode, `csi_len` in
   {128, 256, 384}, `noise_floor` in [−110, −70], `rssi` in [−100, −10].
   Modes taken from a 20,000-row prescan and re-checked against the
   whole-file histogram at merge.
2. **Width-9 median filter on `dropped`**, tolerance 100, compared
   **circularly mod 65536** so that genuine u16 wraps are not false
   positives.

A row failing either screen is dropped before the estimator sees it, and
before any per-MAC counting.

**`csi_data` is parsed with `csv.reader`**, never `line.split(",")` — it is
a quoted comma-separated list nested inside the CSV.

---

## 3. Features — the decision that settles the outcome

### 3.1 What goes in

`pc/rff/dsp.py` is used **exactly as shipped and is not modified**
(`docs/V2_SPEC.md` §5.5). `pc/capture.py:compute_cfo`, `pc/phase_skew.py`
and `pc/fingerprint.py` are **not used** — `docs/CODE_INVENTORY.md` §4.2
C1/C2/C3 establishes all three have the DC/guard-band index wrong.

`FrameEstimator.feed` returns exactly five fields (`dsp.py:147-153`):
`slope`, `intercept`, `cfo_hz`, `inlier_ratio`, `resid_std`. That is the
entire raw supply. Per **window** (see §4), the candidate features are:

| # | feature | from | what it is |
|---|---|---|---|
| F1 | `sfo_med` | median `slope` | the SFO / TX-crystal term. The identity axis. |
| F2 | `sfo_iqr` | IQR of `slope` | within-window slope dispersion |
| F3 | `resid_med` | median `resid_std` | RANSAC fit residual |
| F4 | `inlier_med` | median `inlier_ratio` | RANSAC consensus fraction |
| F5 | `cfo_med` | median `cfo_hz` | intercept rate of change |

`intercept` enters only through F5. Its absolute value is a wrapped common
phase set by the channel and the frame's arrival phase; it is not a device
constant and is not used as a feature on its own.

### 3.2 RSSI is excluded, and this is not negotiable

**RSSI is not a feature, is not standardised into the feature vector, and is
not used to weight, gate or order anything.** RSSI encodes distance and
position. Include it and the clustering will group by *where a transmitter
is*, and the result will look like identity while being geometry.
`docs/COLOCATED_0823.md` §4 gives the mechanism directly: the three beacons
sit at −79.08 / −74.74 / −77.99 dB on the S3 with sds under 1.4 dB — they are
trivially separable by RSSI alone, so an RSSI-bearing feature space would
"pass" the positive control in §5 while proving nothing about the clock.

RSSI is carried through the pipeline for **reporting only** (per-cluster
mean RSSI is printed, so a reader can see whether a cluster happens to be
position-aligned) and is never seen by the clustering.

### 3.3 F3 and F4 are link-quality, not identity, and are treated as suspect

`resid_std` and `inlier_ratio` describe how well RANSAC fitted a frame. That
is a link-budget property, and link budget is a function of position — so F3
and F4 are a **back door for exactly the confound §3.2 closes the front door
on**. `docs/COLOCATED_0823.md` §4 shows median inlier ratios ranging from
2.2 % ≥0.90 (B2/d0wd) to 91.5 % (B2/s3) for the same beacon on two boards ten
inches apart.

Therefore, pre-registered:

- **Feature set A (primary, quoted):** F1, F2. Clock-derived only.
- **Feature set B (secondary, reported alongside):** F1, F2, F3, F4, F5.

**Every headline score in Part II is set A.** If set B scores materially
higher than set A, that is reported as *a warning*, not as a better result:
it means the grouping is being carried by fit quality, and fit quality is
positional.

### 3.4 Effective dimensionality will be measured, not assumed

`docs/AMBIENT_SEPARATION.md` §0 establishes that on the comparable
2026-08-22 capture **the CFO axis is dead** — 0.01σ to 0.21σ, all three
per-frame medians within 0.06 Hz of zero — so the repo's nominal 2-D
(CFO, SFO) feature space is in practice one-dimensional. This pass will
report:

- the correlation-matrix eigenvalue spectrum of the standardised features;
- the **participation ratio** `(Σλ)² / Σλ²`, an effective-dimension count;
- the fraction of windows for which `cfo_hz` is even defined (it is `None`
  on the first frame of a stream and after any gap ≥ 1 s, `dsp.py:141` — for
  a sparse ambient source that may be most frames).

**If the honest answer is "one and a half dimensions", Part II says so in
those words.** A single scalar cannot carry identity for thirty-odd sources
and that finding, if it lands, is the finding.

---

## 4. Windows, and the gate

**Per-window aggregates, not per-frame.** `docs/AMBIENT_SEPARATION.md` §4.2
measures per-frame beacon separations of 0.09σ / 0.46σ / 0.55σ — per-frame
slope is far too noisy to carry identity, and the repo's own pipeline
(`WindowAggregator`, `dsp.py:156`) has always aggregated. Windows are
**non-overlapping, in file order, over accepted frames, per (receiver, MAC)
stream** — the same construction `WindowAggregator` uses, reimplemented only
so the same frames can be re-windowed at two lengths without a second
replay.

**Two window lengths, both reported throughout:**

- **W = 64** — the shipped configuration (`dsp.py:164`). The repo's existing
  separation figures (2.94 / 0.69 / 3.63σ, `docs/AMBIENT_SEPARATION.md`
  §4.4) describe this window, so it is the window the positive control is
  *fairest* on. **The headline positive-control score is W = 64.**
- **W = 16** — the relaxed window. A source with 20 accepted frames yields
  **zero** windows at W = 64 and **one** at W = 16, so W = 16 is what makes
  the floor relaxation of §6 mean anything. Reported for every result.

**Gate: `min_inlier_ratio = 0.3`, `max_resid = 0.8`.** Both fixed now.

- `max_resid = 0.8` is the shipped value and is **inoperative on this data** —
  the largest `resid_std` anywhere in this file is 0.2233
  (`docs/COLOCATED_0823.md` §4), 3.6× below the gate. It is left at the
  shipped value precisely so that it changes nothing.
- `min_inlier = 0.3` rather than the shipped 0.6 because
  `docs/AMBIENT_SEPARATION.md` §3.1/§3.2 establishes that at 0.6 the gate,
  not sparsity, is what destroys ambient sources (`ba:80:d5:0c:18:87` gets
  **0 of 899**), that the beacon medians move by ≤ 1 × 10⁻⁵ rad/sc between
  0.6 and 0.2, and that ambient medians are converged by 0.4. 0.3 is above
  the estimator's own hard consensus floor of exactly 0.2500 (§3.4 there),
  below which the gate is degenerate.

**Replay from the start of each file with a fresh estimator.**
`FrameEstimator` owns a per-instance generator (`dsp.py:118`) handed to
`ransac_line` every frame (`:132`), which draws two `rng.integers(...,
size=64)` per call (`:85-86`). The generator advances once per fitted frame,
so a slope depends on how many frames preceded it in that stream. One fresh
estimator per (node, source-MAC), from byte 0 of the file, no window, filter
or subsample ahead of it. The host caps a shell call near 178 s and a full
pass is ~14 min, so the replay is split into parts that **pickle the
estimator state forward**; §8 check 2 proves the split reproduces one
uninterrupted pass rather than asserting it.

---

## 5. THE POSITIVE CONTROL — first, and decisive

The three beacons have fixed, factory MACs and transmit constantly:
`a4:f0:0f:77:91:20` (B1, the reference), `28:05:a5:2f:fa:48` (B2),
`f4:2d:c9:70:72:30` (B3). On this file they deliver 35–65 fps each on both
nodes for 6.7 h (`docs/COLOCATED_0823.md` §4). They are the loudest, longest,
cleanest, most-characterised signals this project has.

**Procedure.** Take only the three beacons' windows on one receiver. Strip
the MAC labels. Cluster with **k fixed at 3** — the clusterer is told how
many groups to find and nothing else. Score the recovered partition against
the withheld MAC truth with the **adjusted Rand index**.

**Pre-registered thresholds, on set A, at W = 64, per receiver:**

| ARI | verdict |
|---|---|
| **≥ 0.80** | **PASS** — the feature space recovers known devices unaided. Downstream results are worth reading. |
| 0.30 – 0.80 | **MARGINAL** — partial structure. Downstream results are reported but every one is explicitly qualified by this score. |
| **< 0.30** | **FAIL** — the feature space is too thin. |

Chance level is ARI ≈ 0 by construction (the index is adjusted for chance).

**What FAIL means, stated now so it cannot be softened later.** If blind
clustering cannot recover three known, loud, constantly-transmitting devices
on either receiver, then **nothing downstream in this document is worth
reading**, any multi-MAC cluster found in §7 is a coincidence of a
one-dimensional feature colliding, and this route is not viable. That
outcome will be reported plainly, in the summary, as the headline — it is
the most valuable possible negative result here and it stops a large amount
of wasted effort. It will not be buried under the §7 tables and it will not
be described as "promising".

**Secondary, reported but not decisive:** the same score at W = 16, on
feature set B, and with B2/d0wd excluded (below).

**B2/d0wd stays in.** `docs/COLOCATED_0823.md` §4.1 establishes that a
pathological cell — 79.787 % gate rejection, IQR 7–18× the healthy cells —
sits on B2/d0wd in this file, and that it has moved between receivers *and*
beacons across sessions, so it cannot be predicted away. Excluding it would
be choosing the easy cell. It stays in the primary number, and the
without-B2 number is reported next to it so the reading can be judged both
ways. The pre-existing rule that B2/d0wd must not be *rested on* is obeyed:
no conclusion here depends on that cell alone.

---

## 6. Relaxing the 20-frame floor — the thing under suspicion

The repo's floor is **≥ 20 frames per MAC** (`pc/mac_census.py --min-frames`
default 5 in code, 20 in every analysis that used it;
`docs/POSITIVE_CONTROL_0822.md` §3.1, `docs/AMBIENT_SEPARATION.md` §2). It
is exactly what the operator suspects of manufacturing the ambient rejection
rate, so **this pass does not apply it.**

**Inclusion rule for the open-set run: any screened MAC with ≥ 1 complete
window** (≥ 16 accepted frames at W = 16; ≥ 64 at W = 64). Part II reports:

- sources at the repo's ≥ 20-frame floor, per receiver — the baseline;
- sources clusterable at W = 16 with no floor — the relaxed count;
- **the difference, stated as "how many additional sources become
  clusterable when the label requirement is dropped"**;
- and the sources that still cannot be clustered, with the reason
  distinguished as `docs/AMBIENT_SEPARATION.md` §2 requires: **genuine
  sparsity** (fitted ≈ rows, the device simply did not transmit) versus
  **gate exclusion** (fitted but rejected) versus **parse failure**.

`docs/COLOCATED_0823.md` §2 gives the baseline to beat: 18 real sources on
the d0wd and 14 on the S3 at ≥ 20 frames, with 22 and 19 more clean but
below the floor.

---

## 7. THE REAL QUESTION, and how a false positive is prevented

**After the control passes — and only then — does any cluster contain
windows from more than one MAC?**

For each multi-MAC cluster, Part II reports: the addresses involved; each
one's window count and time span; whether the spans are **sequential**
(disjoint — one address stops, the next starts, which is what an address
rotation looks like) or **interleaved** (concurrent, which is what two
different devices look like); and the **locally-administered bit** of each
address.

The LAA test is the bit `first_octet & 0x02`, which is
`pc/mac_census.py:32-37`'s `is_locally_administered()`. That function is
**re-implemented inline rather than imported**, for one reason stated
plainly: importing `pc/mac_census.py` writes
`pc/__pycache__/mac_census.cpython-310.pyc`, and this session cannot delete
files it creates under the repo (`rm` returns `Operation not permitted`).
The inline copy is five lines and byte-equivalent in behaviour; it is
checked against the source in §8.

**A multi-MAC cluster whose members are all locally-administered is the
strongest available signature of one device randomising its address.**

### 7.1 The false positive this design is most likely to produce

With an effectively one-dimensional feature (§3.4) and thirty-odd sources,
**multi-MAC clusters are the expected outcome by pigeonhole and prove
nothing on their own.** Two unrelated devices will share a cluster simply
because a scalar has nowhere to put them. Reporting the co-occurrence
without calibrating it would be `CLAUDE.md` failure mode **A** — a
prediction printed as a measurement.

So, pre-registered: a multi-MAC cluster is reportable **as evidence of
randomisation** only if it clears all three:

1. **Permutation-calibrated.** Permute the MAC labels across windows within
   the receiver, preserving each MAC's window count and the cluster
   assignment; 1,000 permutations, fixed seed. The pair's co-clustering
   fraction must exceed the 95th percentile of that null.
2. **Tight.** The two addresses' pooled window spread must be no wider than
   `BETWEEN_UNIT_SD = 0.00237` (`pc/exp_thermal_evidence.py:129`, from
   `docs/LOT_HYPOTHESIS.md` §5) — i.e. no wider than two genuinely different
   units are apart.
3. **Not a mis-unwrap artefact** (§7.2).

A multi-MAC cluster that fails any of these is still listed, and labelled
**not evidence**.

### 7.2 The mis-unwrap confound, pre-registered

`docs/AMBIENT_SEPARATION.md` §5 established that a RANSAC consensus subset
sitting one turn away from the rest shifts the fitted slope by exactly
**2π/Δk**, and caught `1c:ce:51:f3:0d:fa` doing it: bimodal slopes
**0.195 rad/sc** apart against 2π/32 = **0.1963**. At `min_inlier 0.3` this
pass deliberately admits the low-consensus frames where that happens.

So Part II will check every cluster-centroid separation against the
2π/Δk ladder — 0.1208 (Δk=52), 0.1571 (40), 0.1963 (32), 0.2417 (26) — and
any cluster split or merge landing within 5 % of a rung is reported as **a
candidate estimator artefact, not a device boundary.**

### 7.3 The inverse question

**Does any single MAC split across clusters?** A fixed factory MAC whose
windows land in two or more clusters means the feature is tracking something
other than the device — drift, temperature, link quality, or the mis-unwrap
of §7.2. Part II reports, per MAC, the number of clusters its windows occupy
and the share in the largest one, for the beacons first (where the truth is
known) and then for every source.

---

## 8. Method, controls, and the checks that must pass

**The negative control.** Pool every accepted frame in one receiver,
randomly permute the assignment of frames to windows (fixed seed, window
sizes and window count preserved exactly), recompute the window aggregates,
re-cluster with the identical pipeline, and re-score. Structure must vanish.

- **Pre-registered criterion: ARI(shuffled) < 0.05 and the mean silhouette
  must fall materially toward 0.** If it does not, the clustering is finding
  something about the windowing rather than about the devices, and every
  positive result in Part II is void.
- **A stated limitation of this control:** it is only informative if the
  positive control passes. If the real run already scores ARI ≈ 0, a shuffle
  cannot lower it, and the negative control is vacuous rather than clean.
  Part II says which of the two it is.

**Clustering, and why this algorithm.** Neither `scipy` nor `scikit-learn`
is installed on this host (checked; `pc/requirements.txt` does not list
them, and `CLAUDE.md` notes nothing in the repo imports scipy). Everything
is implemented in the one script in plain numpy, which also means every
number is re-derivable from code in this repo:

- **k-means**, k-means++ init, 50 restarts, fixed seed, best inertia — used
  wherever k is known (the positive control, k = 3).
- **Average-linkage agglomerative** on standardised Euclidean distance —
  used for the open set, where k is not known. Two cuts, both reported:
  the threshold **maximising mean silhouette** over a swept range, and a
  fixed physically-anchored cut at within-cluster SFO spread ≤
  `BETWEEN_UNIT_SD`.
- **Robust standardisation** (median / MAD, per feature, per receiver), not
  mean/sd — the `1c:ce` mis-unwrap outliers would otherwise set the scale.
- **Silhouette** on a fixed-seed random subsample of 5,000 windows, because
  it is O(n²) and the beacon runs have >10⁵ windows.
- **ARI** by the standard pair-counting formula, implemented directly.

**Checks that must pass before any result in Part II is quoted:**

1. Screened row counts, per-node MAC census and corrupt-row totals
   re-derived here must reproduce `docs/COLOCATED_0823.md` §0/§2/§3 —
   **3,344,351 / 4,330,849 rows, 190 / 1 corrupt rows, 166 / 34 raw MACs,
   18 / 14 at the 20-frame floor**. A mismatch means the screen is wrong and
   the pass stops.
2. The part/merge split must be shown to reproduce a single uninterrupted
   pass: row counts equal `wc -l` − 1, `pc_time_us` monotone across every
   seam, prescan mode agreeing with the whole-file histogram.
3. The inline `is_locally_administered` must agree with
   `pc/mac_census.py`'s on every address in the census.
4. `pc/rff/dsp.py` mtime unchanged.

**Read-only and repo hygiene.** Both CSVs opened `"rb"`, never written. No
serial port opened — a capture is running on COM6/COM12 right now and
nothing here touches it. Nothing staged, committed or pushed. One script,
`pc/exp_blind_clustering_0823.py`. All state and scratch go to
`$BLIND_CACHE`, outside the repo tree, and are deleted at the end.

**Disclosed now rather than found later:** a 0-byte file
`pc/__pycache__/_probe_del.tmp` was created early in this session by a probe
testing whether this mount permits deletion. It does not — `rm` returns
`Operation not permitted` — so the probe could not remove its own test file.
It is 0 bytes, it is inside `__pycache__/` which is `.gitignore:14`, and it
is not staged. Running the script will also refresh
`pc/rff/__pycache__/*.cpython-310.pyc`, which already exist.

---

*Part I ends here. Everything below was written after the run.*

---

# PART II — RESULT

## 9. The answer, up front

**The positive control did not pass. It scored MARGINAL on both receivers,
in all four configurations, and never came within half of the PASS
threshold.** Best set-A score, on the window the control is fairest on:
**ARI 0.4200** (S3, W = 64), against a PASS bar of 0.80.

**Blind clustering is not a viable route on this feature space as it stands,
and the reason is specific and measurable: there is one usable dimension,
not two.** The participation ratio of the standardised clock features is
**1.38 – 1.55** across the four runs. "One and a half dimensions" is not a
figure of speech here; it is the measured number.

The controls behaved. The negative control was **clean** (|ARI| ≤ 0.0003 on
every run, silhouette falling toward the shuffled floor), so the partial
structure the clustering does find is about the devices and not about the
windowing. **Relaxing the 20-frame floor bought essentially nothing** —
**+0** additional clusterable sources on the d0wd and **+1** on the S3 — so
on this session the floor is *not* what is hiding ambient devices. And
**no multi-MAC cluster survived the pre-registered calibration on both
receivers**: the count of multi-MAC clusters was *below* the permutation
null in all eight cut × receiver × window combinations, which is what a
one-dimensional feature colliding by pigeonhole looks like.

One pair cleared all three of §7.1's criteria, on one receiver, and §9.5
explains why it should not be believed anyway.

---

## 9.1 The checks in §8 passed

| check | required | measured |
|---|---|---|
| d0wd rows | 3,344,351 | **3,344,351** ✓ |
| s3 rows | 4,330,849 | **4,330,849** ✓ |
| d0wd corrupt rows | 190 | **190** (field 187, median 186, both 183) ✓ |
| s3 corrupt rows | 1 | **1** (field 1, median 1, both 1) ✓ |
| d0wd distinct MACs, any row | 166 | **166** ✓ |
| s3 distinct MACs, any row | 34 | **34** ✓ |
| d0wd MACs ≥ 20 clean frames | 18 | **18** ✓ |
| s3 MACs ≥ 20 clean frames | 14 | **14** ✓ |
| d0wd MACs only on corrupt rows | 126 | **126** ✓ |
| s3 MACs only on corrupt rows | 1 | **1** ✓ |
| span, both nodes | 6.7009 h | **24,123.123 s / 24,123.100 s** ✓ |

The field screen alone flags **187** on the d0wd, exactly reproducing the
independent `awk` count in `docs/COLOCATED_0823.md` §3.3, and the median
filter catches three more — the same "neither screen alone is sufficient"
result, re-derived by code that shares nothing with that pass.

**Part/merge reproduces one uninterrupted pass.** Final byte position equals
file size exactly on both inputs (2,866,404,334 and 3,596,309,377),
`pc_time_us` is monotone across all 7 and 9 seams, and the 20,000-row
prescan modes agree with the whole-file histograms (node 68 / 108, channel
6). Proved rather than asserted on the small `013537` S3 file (59,908 rows,
not part of the analysis): a **2-part** replay and a **1-part** replay
produce **byte-identical** frame arrays under `np.array_equal` on the raw
bytes.

`is_locally_administered()` agrees with `pc/mac_census.py:32-37` on **all
166 addresses, 0 disagreements**. `pc/rff/dsp.py` mtime is still
2026-07-13 20:42:46 — unmodified. Both inputs still read 2,866,404,334 and
3,596,309,377 bytes at 2026-08-23 08:29:44, unchanged across the pass. No
serial port was opened. Nothing was staged or committed.

---

## 9.2 The positive control — MARGINAL, four times

Three beacons, labels withheld, k fixed at 3, scored by adjusted Rand index
against the withheld truth.

| receiver | W | set A (clock only) | verdict | set B (+ quality) | negative control, set A |
|---|---|---|---|---|---|
| d0wd | 64 | **0.4072** | MARGINAL | 0.7700 | ARI **+0.0002**, silhouette 0.677 → 0.335 |
| S3 | 64 | **0.4200** | MARGINAL | 0.4408 | ARI **−0.0000**, silhouette 0.540 → 0.331 |
| d0wd | 16 | **0.3860** | MARGINAL | 0.6847 | ARI **−0.0003**, silhouette 0.616 → 0.376 |
| S3 | 16 | **0.3596** | MARGINAL | 0.4184 | ARI **+0.0000**, silhouette 0.489 → 0.354 |

PASS was 0.80, FAIL was 0.30. Every run landed between: real structure is
present and it is nowhere near enough to recover three known devices.

**What the failure actually looks like.** The confusion matrices show the
clusterer is not confused evenly — it merges two beacons and splits the
third. S3, W = 64, set A:

| true | cluster 0 | cluster 1 | cluster 2 |
|---|---|---|---|
| B1 `a4:f0:0f:77:91:20` | 10,009 | 9,680 | 4 |
| B2 `28:05:a5:2f:fa:48` | 34 | **24,355** | 213 |
| B3 `f4:2d:c9:70:72:30` | **20,794** | 1,647 | 775 |

B1 — the reference beacon every device-ID figure in this repo is anchored
to — is **split almost exactly in half between B3's cluster and B2's**. It
does not get a cluster of its own. On the d0wd the same picture with a
different victim: B3 and B1 collapse into one cluster (22,877 and 12,920
windows) while B2, the 79.8 %-reject cell, splits three ways.

**B2/d0wd is not the whole story, but it is a large part of it.** Removing
that cell and asking for k = 2 lifts the d0wd score from 0.4072 to
**0.7524** at W = 64 and from 0.3860 to **0.5887** at W = 16 — a real
improvement that still does not reach PASS, on the *easier* two-class
problem. `docs/COLOCATED_0823.md` §4.1's rule holds: nothing here rests on
that cell alone.

**Set B is a warning, not a better answer, exactly as §3.3 pre-registered.**
On the d0wd, adding `resid_std` and `inlier_ratio` nearly doubles the score
(0.4072 → 0.7700 at W = 64). Those are link-quality features, link quality
is positional, and the d0wd is the receiver whose three beacon cells reject
7.3 % / 79.8 % / 1.9 % of their frames — so a "quality" feature there is very
nearly a beacon name tag. On the S3, whose cells are all healthy
(0.294 / 1.199 / 1.015 % rejection), the same features add almost nothing:
0.4200 → 0.4408. **The set-B gain appears exactly where fit quality happens
to be a label and vanishes where it does not.** That is the confound §3.2
and §3.3 were written to catch, and it is caught.

---

## 9.3 How many usable dimensions there actually are: one and a half

| receiver | W | set A eigenvalues | **participation ratio** | set B eigenvalues | PR |
|---|---|---|---|---|---|
| d0wd | 64 | 1.670, 0.330 | **1.38** | 3.060, 1.001, 0.484, 0.362, 0.094 | 2.33 |
| S3 | 64 | 1.630, 0.370 | **1.43** | 3.231, 0.997, 0.458, 0.197, 0.117 | 2.14 |
| d0wd | 16 | 1.599, 0.401 | **1.47** | 2.923, 1.000, 0.517, 0.422, 0.138 | 2.50 |
| S3 | 16 | 1.539, 0.461 | **1.55** | 3.003, 0.999, 0.532, 0.266, 0.200 | 2.40 |

Two nominal clock dimensions collapse to **1.38 – 1.55** effective ones,
because `sfo_iqr` is largely a noisy function of `sfo_med`. Set B's five
nominal dimensions reach only 2.14 – 2.50, and the axes it adds are the
quality axes §9.2 just disqualified.

**The CFO axis is defined but empty.** `cfo_hz` is available on **100.0 %**
of windows on both receivers at both window lengths — the sparse-source
worry in §3.4 did not materialise, because `dsp.py:141` only needs
consecutive frames under 1 s apart and even the ambient sources here arrive
in bursts. Its presence does not help: it is one of the five set-B axes and
set B on the healthy receiver gains 0.02 ARI.

**So the honest answer is the one §3.4 said to state in those words: one and
a half dimensions.** A single scalar — SFO — has to separate 10 to 18
sources per receiver. It cannot, and no clustering algorithm can rescue a
feature that does not carry the information.

---

## 9.4 The floor was not the problem on this session

| | d0wd | S3 |
|---|---|---|
| sources at the repo's ≥ 20-frame floor | 18 | 14 |
| **clusterable at W = 16, no floor** | **18** | **15** |
| **additional sources made clusterable** | **+0** | **+1** |
| clusterable at W = 64, no floor | 10 | 10 |
| additional at W = 64 | **−8** | **−4** |

The single source the relaxation adds is `9e:38:41:e0:97:0d` on the S3: 19
clean frames — one under the floor — of which 18 pass the gate, enough for
exactly one 16-frame window.

Everything else that fails is genuinely sparse, and the accounting says so
in the terms `docs/AMBIENT_SEPARATION.md` §2 requires. Not clusterable at
W = 16: **148 on the d0wd** — 126 corrupt-only artefacts, 21 sparsity, 1
parse/nofit — and **19 on the S3** — 1 corrupt-only, 18 sparsity. **Gate
exclusion accounts for zero of them** at `min_inlier 0.3`, which is the
gate `docs/AMBIENT_SEPARATION.md` §3 argued for and this pass adopted.

**This is a direct answer to the motivating hypothesis, and it is a
negative one for this session.** The 22 clean-but-sparse d0wd addresses and
19 on the S3 — the fragments the hypothesis is about — are not being
discarded by a floor that could be lowered. They carry 5 to 19 frames each.
Sixteen accepted frames is already close to the smallest window from which
a median SFO means anything, and at W = 16 the floor and the window
requirement coincide almost exactly. **To recover those fragments you would
have to pool their frames *before* estimating, which requires already
knowing which fragments belong together — the circularity this technique
was supposed to break.**

At W = 64 the picture is worse and worth stating plainly: **the shipped
64-frame window is a stricter floor than the 20-frame rule it sits behind**,
cutting the clusterable population from 18 to 10 on the d0wd and 14 to 10 on
the S3.

---

## 9.5 Multi-MAC clusters — and the one that cleared the bar

**Every multi-MAC count sat inside or below its permutation null.**

| receiver | W | cut | clusters | multi-MAC | null mean | null p95 | reading |
|---|---|---|---|---|---|---|---|
| d0wd | 64 | silhouette | 3 | 2 | 11.7 | 12 | within |
| d0wd | 64 | physical | 291 | 51 | 426.0 | 437 | **below** |
| S3 | 64 | silhouette | 3 | 3 | 13.2 | 14 | within |
| S3 | 64 | physical | 278 | 130 | 372.4 | 384 | **below** |
| d0wd | 16 | silhouette | 3 | 2 | 20.2 | 21 | within |
| d0wd | 16 | physical | 571 | 138 | 938.2 | 955 | **below** |
| S3 | 16 | silhouette | 3 | 3 | 18.5 | 20 | within |
| S3 | 16 | physical | 558 | 280 | 804.1 | 819 | **below** |

Fewer addresses share a cluster than chance would put together — which is
the signature of a feature that is *sorting* windows, just not by device.

### The candidate: `62:45:b4:f0:e1:97` and `7e:ed:82:d6:23:e8`, both LAA

On the S3's physical cut this pair co-clusters far more than permuted labels
would, at both window lengths, and it clears all three of §7.1's criteria:

| | W = 64 | W = 16 |
|---|---|---|
| shared clusters | 9 | 43 |
| co-cluster fraction (obs) | **0.1957** | **0.2323** |
| permutation null mean / p95 | 0.0944 / 0.1212 | 0.0512 / 0.0587 |
| p | **0.000** | **0.000** |
| **criterion 1** | **PASS** | **PASS** |
| pooled window SFO sd | **0.00174** | **0.00180** |
| **criterion 2** (≤ 0.00237) | **PASS** | **PASS** |
| median SFO gap | 0.00350 (1.48 σ) | 0.00322 (1.36 σ) |
| nearest 2π/Δk rung | 2π/52, **97 % away** | 2π/52, **97 % away** |
| **criterion 3** | **PASS** | **PASS** |

Both addresses have the locally-administered bit set. On the pre-registered
criteria alone this is the strongest possible signature of one device
randomising, and it is the only pair in the pass that reaches it.

**It should not be believed, for three reasons, and the third is decisive.**

1. **RSSI. `62:45:b4:f0:e1:97` averages −29.0 dB; `7e:ed:82:d6:23:e8`
   averages −65.1 dB.** A 36 dB gap. RSSI was kept out of the features
   precisely so it could be used this way (§3.2), and one stationary device
   does not swing 36 dB between its own addresses.
2. **They transmit at the same time.** Their raw frames share **2 of the 60 s
   bins** either is active in (24 bins and 11 bins respectively), and the
   same 2 at the window level. An address rotation stops one address when it
   starts the next; it does not run both concurrently.
3. **It does not reproduce on the other receiver.** On the d0wd, ten inches
   away on the same wall in the same six hours, the same pair scores
   obs 0.2105 against a p95 of 0.2253 — **criterion 1 FAIL, p = 0.083** —
   and at W = 64 they never share a cluster at all. A crystal property must
   read the same on both boards; `docs/AMBIENT_SEPARATION.md` §5 is the
   standing precedent for exactly this test, and this pair fails it.

**Reported as: not evidence.** Two LAA addresses whose SFO medians happen to
sit 1.4 σ apart on one receiver is what a one-dimensional feature does when
handed fifteen sources.

### The repo's own best candidate fails outright

`1c:ce:51:f3:0d:fa` and `1e:ce:51:f3:0d:fa` — the pair
`docs/AMBIENT_SEPARATION.md` §2 identified as **the same address with only
the LAA bit flipped**, and "almost certainly one device counted twice" — are
present on both receivers in this session, and blind clustering does **not**
put them together:

- **criterion 1 FAIL everywhere**: S3 W = 16 obs 0.0088 vs p95 0.0675
  (p = 1.000); S3 W = 64 obs 0.0467 vs p95 0.1600 (p = 0.927); d0wd W = 16
  obs 0.0170 vs p95 0.2234 (p = 1.000).
- **criterion 2 FAIL**: pooled window SFO sd **0.05147** on the S3, 21.7×
  `BETWEEN_UNIT_SD`. Their individual sds are 0.048 and 0.055 — each address
  is, on its own, more than twenty times wider than two different units are
  apart.
- and they are **concurrent in 12 of the 60 s bins** `1e:ce` appears in
  (14 bins), on raw frames, so even the ground truth this repo believes in
  is not a clean sequential rotation in this capture.

They do land in a cluster together at the coarse silhouette cut — and that
cluster is exactly the one the mis-unwrap check flags. **On the d0wd at
W = 16 the adjacent centroid gap separating it from everything else is
0.12596 rad/sc against 2π/52 = 0.12083 — 4.2 % away, inside the 5 % window,
CANDIDATE ESTIMATOR ARTEFACT**; on the S3 at both window lengths the flagged
gap is 0.16401 / 0.16365 against 2π/40 = 0.15708. Their SFO medians are
−0.108 to −0.115 on the d0wd and −0.142 to −0.151 on the S3 — the same
runaway values
`docs/AMBIENT_SEPARATION.md` §5 diagnosed as a one-turn mis-unwrap over
~32–52 subcarriers. **The one place blind clustering appears to catch
address randomisation in the act, it is instead catching the estimator
falling off a branch — which is what §7.2 was written to detect, and it
detected it.**

---

## 9.6 The inverse question: single MACs shatter

This is the loudest result in the pass. At the physical cut, fixed factory
MACs transmitting continuously for 6.7 h do not stay in one cluster:

| receiver | W | source | clusters occupied | largest holds |
|---|---|---|---|---|
| d0wd | 64 | B2 `28:05:a5:2f:fa:48` | **271** | **9.5 %** of 15,852 windows |
| d0wd | 64 | B1 `a4:f0:0f:77:91:20` | 30 | 28.0 % of 13,210 |
| d0wd | 64 | B3 `f4:2d:c9:70:72:30` | 30 | 85.3 % of 23,100 |
| S3 | 64 | B3 `f4:2d:c9:70:72:30` | **201** | **23.9 %** of 23,216 |
| S3 | 64 | B2 `28:05:a5:2f:fa:48` | 137 | 52.9 % of 24,602 |
| S3 | 64 | B1 `a4:f0:0f:77:91:20` | 36 | 34.3 % of 19,693 |
| d0wd | 16 | B2 `28:05:a5:2f:fa:48` | **517** | **4.3 %** of 63,409 |
| S3 | 16 | B3 `f4:2d:c9:70:72:30` | **355** | **11.3 %** of 92,865 |

**A device whose windows spread over 271 clusters with no cluster holding a
tenth of them is not being tracked by this feature.** The physical cut is
defined so that no cluster is wider in SFO than two genuinely different
units are apart (`BETWEEN_UNIT_SD`) — and at that resolution a single ESP32
wanders across hundreds of them over one night. Whatever the SFO window
median is following at that scale — drift, temperature, link quality,
RANSAC consensus composition — it moves the estimate further within one
device than it separates two devices.

The best case in the table, B3 on the d0wd at 85.3 %, is also the cell with
the lowest gate rejection in the file (1.888 %,
`docs/COLOCATED_0823.md` §4). The worst, B2 on the d0wd, is the 79.8 %-reject
cell. That ordering is consistent with the acceptance-quality story, and it
is **not evidence for it** — three beacon cells is the same thin evidence
`docs/POSITIVE_CONTROL_0822.md` §5 already filed under *permitted, not
established*, and this pass leaves it there.

---

## 9.7 Deviations from Part I, all forced and all disclosed

1. **Grid pre-aggregation before average linkage.** Average linkage is
   O(m²) in memory and the open-set runs have 52,237 – 270,660 windows.
   The window cloud is first collapsed, **label-blind**, onto a grid in
   standardised feature space (cell width coarsened until ≤ ~1,800 cells are
   occupied: 0.13 – 0.34 MAD-units here), and UPGMA runs on the weighted
   cells. Rare points keep their own cell exactly; the approximation is that
   distances *within* one cell are treated as zero. This is a change to how
   the pre-registered algorithm is computed, not to which algorithm.
2. **k-means restarts thinned from 50 to 12 above 50,000 points**, to keep
   one invocation inside the host's ~178 s shell cap.
3. **The per-pair co-clustering test is skipped on cuts with fewer than 10
   clusters.** With 3 clusters the permutation null sits at ~0.999 and the
   test has no power; it is reported on the physical cut, which has 278–571.
4. **`analyze` was split by window length across shell calls** for the same
   cap. Both cuts come from one linkage; nothing about the analysis changes.
5. **Window aggregation and silhouette were vectorised mid-pass** for speed.
   Verified numerically identical: the S3 W = 64 run before and after
   reproduces ARI 0.4200 / 0.4408, k = 278, and every figure quoted here.
6. **The mis-unwrap ladder check is reported on adjacent cluster centroids
   and, in `focus`, on the specific pair gap** — Part I specified centroid
   separations, and the pair-level version is an addition, not a
   substitute.

Nothing in §5's thresholds, §7.1's criteria, §3.2's RSSI exclusion or §4's
gates was changed after the first number appeared.

---

## 9.8 Established / permitted / unknown

**Established by this pass, from these two files:**

- Blind k-means on clock-only window features, k fixed at 3, recovers the
  three fixed-MAC beacons at **ARI 0.3596 – 0.4200**. MARGINAL on the
  pre-registered scale; never PASS on either receiver at either window.
  §9.2.
- The effective dimensionality of the clock feature space is **1.38 – 1.55**
  by participation ratio; `cfo_hz` is defined on 100.0 % of windows and
  contributes nothing on the receiver whose cells are healthy. §9.3.
- The negative control is **clean**: shuffling frames between windows drives
  ARI to |≤ 0.0003| and collapses the silhouette. The partial structure is
  about devices, not windowing. §9.2.
- Adding fit-quality features roughly doubles the score on the receiver with
  a 79.8 %-reject cell (0.4072 → 0.7700) and adds 0.02 on the receiver
  without one (0.4200 → 0.4408). §9.2.
- Dropping the 20-frame floor makes **+0** additional d0wd sources and
  **+1** additional S3 source clusterable at W = 16. Gate exclusion accounts
  for **zero** unclusterable sources at `min_inlier 0.3`. §9.4.
- The shipped W = 64 window is a **stricter** floor than the 20-frame rule:
  18 → 10 and 14 → 10 sources. §9.4.
- The number of multi-MAC clusters is **below the permutation null in all
  four physical-cut runs** and within it in all four silhouette-cut runs.
  §9.5.
- `62:45:b4:f0:e1:97` / `7e:ed:82:d6:23:e8` (both LAA) clear all three
  §7.1 criteria on the S3 at both windows, and are contradicted by a 36 dB
  RSSI gap, by 2 concurrent 60 s bins, and by criterion-1 FAIL on the d0wd
  (p = 0.083). §9.5.
- `1c:ce:51:f3:0d:fa` / `1e:ce:51:f3:0d:fa`, the repo's own LAA-bit-flip
  pair, **fail** criteria 1 and 2 on both receivers (pooled sd 0.05147 =
  21.7 × `BETWEEN_UNIT_SD`), and the cluster that does hold them is flagged
  by the 2π/Δk check at 4.2 % from 2π/52. §9.5.
- At a cut where no cluster is wider than `BETWEEN_UNIT_SD`, single fixed
  MACs occupy **30 – 517 clusters**, with the largest holding as little as
  **4.3 %** of one beacon's windows. §9.6.

**Permitted by this pass, not established:**

- That the whole shortfall is dimensionality rather than algorithm. A
  richer feature — per-subcarrier residual shape, IQ imbalance, transient
  onset — might separate where a scalar cannot. Nothing here tested one.
- That fit-quality ordering explains which beacon shatters worst. Three
  cells, consistent direction, same thin evidence as
  `docs/POSITIVE_CONTROL_0822.md` §5.

**Unknown:**

- What the SFO window median is actually tracking within one device over
  6.7 h to spread it across hundreds of `BETWEEN_UNIT_SD`-wide clusters.
  This pass measured the spread and did not investigate its cause.
- Whether any of this generalises past one night, one room, one channel and
  one pair of co-located receivers. `docs/IDENTITY_STABILITY.md` says not
  across sessions; that was the reason for the single-session scope and it
  is untouched.

**What would change the answer.** Not a better clusterer — the negative
control shows the clusterer is honest and the participation ratio shows the
input is thin. A second genuinely independent axis is the requirement. Until
one exists, the reasonable reading is the one in §9.4: on this session the
20-frame floor is not what makes ambient devices look unmeasurable;
**the ambient devices really do only transmit 5 to 19 frames, and the one
axis available cannot tell those fragments apart even when they are loud.**

---

## 9.9 Reproduction

```
export BLIND_CACHE=/tmp/blind
D=data/raw/d0wd_20260823_014740.csv
S=data/raw/s3_20260823_014740.csv
for p in 0 1 2 3 4 5 6 7; do
  python3 pc/exp_blind_clustering_0823.py replay $D --tag d0wd \
      --part $p --nparts 8 --total-rows 3344351
done
for p in 0 1 2 3 4 5 6 7 8 9; do
  python3 pc/exp_blind_clustering_0823.py replay $S --tag s3 \
      --part $p --nparts 10 --total-rows 4330849
done
python3 pc/exp_blind_clustering_0823.py merge --tag d0wd --nparts 8  --expect-rows 3344351
python3 pc/exp_blind_clustering_0823.py merge --tag s3   --nparts 10 --expect-rows 4330849
for t in d0wd s3; do for W in 64 16; do
  python3 pc/exp_blind_clustering_0823.py analyze --tags $t --windows $W
done; done
python3 pc/exp_blind_clustering_0823.py focus --tag s3 \
    --a 62:45:b4:f0:e1:97 --b 7e:ed:82:d6:23:e8
python3 pc/exp_blind_clustering_0823.py focus --tag s3 \
    --a 1c:ce:51:f3:0d:fa --b 1e:ce:51:f3:0d:fa --windows 16
```

Two files in the repo were written by this pass: **this one** and
**`pc/exp_blind_clustering_0823.py`**. All state and scratch went to
`$BLIND_CACHE` outside the repo tree and was deleted afterwards. The
0-byte `pc/__pycache__/_probe_del.tmp` disclosed in §8 is still there and
still undeletable from this session; `pc/rff/__pycache__` holds the same 24
`.pyc` files it held before.

**Two further `pc/__pycache__` disclosures, since this session cannot delete
what it creates under the repo.**

- **`pc/__pycache__/exp_blind_clustering_0823.cpython-310.pyc`** exists. It
  was **not** produced by running the analysis — the script is executed,
  never imported — but by a final `python3 -m py_compile` syntax check on
  the finished file. It matches the `.pyc` already present for every other
  `pc/exp_*.py` and is covered by `.gitignore:14`.
- **No `.pyc` was created for `pc/mac_census.py`.** The §8 check 3
  cross-comparison `exec`s that file's source text rather than importing the
  module, precisely to avoid one. `ls pc/__pycache__/ | grep mac_census`
  is empty.
