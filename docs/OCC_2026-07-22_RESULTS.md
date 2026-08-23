# Scoring the 2026-07-22 labeled occupancy session

**Date:** 2026-08-20 · **Scope:** the six `data/raw/occ_20260722_*.csv`
captures, scored against their own `label` column · **Tool:**
`pc/exp_occ_ground_truth.py` (new, read-only). No file under `data/raw/`,
`pc/occ/`, `pc/rff/` or any existing entry point was modified. No hardware was
touched, no capture was taken, no serial port was opened.

This is the session `docs/HANDOFF.md` open thread #0 asks for, and
`PROJECT_NOTES.md` §2 flags as captured-but-never-scored. It has now been
scored. The result is mostly negative, and the largest finding is about the
session, not the detectors.

---

## 0. The one-paragraph answer

**The session that was captured is not the session `docs/OCC_PROTOCOL.md`
describes.** The protocol's labels are `empty,walk,still,out,cat`. The labels
actually in the CSVs are `empty` and `zone1`–`zone4`. There is no `walk`
segment, no `still` segment, no `out` segment and no `cat` segment anywhere in
the six files. The labels match the `zone1`..`zoneN` + `empty` convention documented in
`pc/zone_calib.py` — whose mtime is `2026-07-22 19:38`, sixteen minutes after
the last capture in the set closed — rather than the detection protocol's.
(They are *close* to `OCC_PROTOCOL.md`'s zone-calibration variant, but not it:
that variant specifies `walk-door,walk-window,still-desk,...`, labels that
encode the activity as well as the place. Bare `zoneN` does not.) Consequently
the four numbers the protocol says matter —
`walk` motion-detection rate, `still` breathing-detection rate, and the two
`cat` pet-immunity numbers — **cannot be computed from this session at all.**
What can be computed is a false-alarm rate on `empty`, and a presence rate on
occupied-at-a-named-location time. Both are reported below, both rest on small
denominators, and the occupied-time number is **not stable** across legitimate
choices of calibration source.

---

## 1. Method

### 1.1 What was run

```
cd pc
python exp_occ_ground_truth.py --report <path> --json <path>
```

`exp_occ_ground_truth.py` imports `pc/occ/` and `pc/occ_offline.py` and calls
their committed functions. Every detector, threshold and floor model is the
committed one:

| knob | value | source |
|---|---|---|
| grid | 10 Hz | `occ_offline.py` default |
| motion window | 2.0 s | `occ_offline.py` default |
| `z_on` / `z_solo` / `z_off` | 5.0 / 12.0 / 3.0 | `occ_offline.py` defaults |
| presence verdict | ≥ 6.0 dB SNR **and** ≥ 5 of top-10 subcarriers agreeing | `occ/breathing.py::presence_verdict` defaults |
| RSSI operating-point guard | 5.0 dB | `occ_offline.RSSI_GUARD_DB` |

**Nothing was tuned.** No threshold was moved to improve any number in this
document. Where detection is poor, that is reported as the finding.

### 1.2 Cross-check against the committed tool

`python occ_offline.py "../data/raw/occ_20260722_*.csv" --calib
../data/raw/rx_20260714_031131.csv` prints thirteen per-label motion
percentages (25.2 / 20.8 / 1.9 / 85.9 / 4.2 / 15.3 / 100.0 / 4.2 / 22.2 /
46.4 / 100.0 / 100.0 / 100.0 %). The new script's config-A **untrimmed**
per-label rows reproduce all thirteen exactly. Those untrimmed rows are not
what this document tabulates — §3.1 and §3.3 report interval interiors (§1.3.2)
— so the cross-check lives in the raw report, not in the tables below. It
establishes that the new script is a scorer wrapped around the committed
pipeline, not a reimplementation of it.

### 1.3 Four things this scorer does that `occ_offline.py` does not

1. **Per-label results split by run, by block, and by calibration source.**
   `occ_offline.py` does print a seconds count per label per file
   (`'zone1': 130s  motion-flagged  20.8%`). What it does not do is separate
   the two-link and three-link blocks, show the per-run breakdown behind a
   pooled label, or print the denominator that survives interval trimming —
   so a label whose 130 s is a 60 s run plus a 70 s run reads as one number.
2. **Interval interiors.** `OCC_PROTOCOL.md` step 1 says "the scorer uses
   interval interiors" — the operator is still walking out of the room during
   the first seconds of an `empty` interval. **The committed scorer does not
   actually do this.** Both the untrimmed and the 15-s-trimmed numbers are
   reported here; the trimmed ones are used for the pooled summary.
3. **Label-confined respiration scans.** `occ_offline.py` scans motion-quiet
   runs that may straddle several labels, then credits the whole scan range to
   every label it touches. In `occ_20260722_152849` the single stock quiet run
   is bins 1265–3868 (t = 126.5 → 386.8 s), which **starts in `zone1` and
   crosses `zone2` and `zone4`**; stock output consequently credits it to all
   three, giving `zone4` breathing-flagged 58.5%. Scans here are confined to a
   single label so the result is attributable to a condition.
4. **Held-out empty calibration.** A false-alarm rate measured on the same
   bins that set the threshold is not a false-alarm rate. Config B fits the
   motion floor on one file's labeled `empty` bins and scores the *other*
   file's.

### 1.4 The respiration window had to be shortened, and it matters

`occ_offline.MIN_BREATH_S` is 120 s. The contiguous labeled runs in this
session are 3–171 s long; eleven of the nineteen are 60–90 s and only three
exceed 120 s (`..._152849` `zone2` 171.0 s, `..._155622` `empty` 140.7 s,
`..._191220` `empty` 120.2 s). **At stock settings the
committed tool produces two respiration link-scans across the entire
session** — both from `occ_20260722_152849`; the other five files report "no
quiet runs long enough."

The *segment-selection* length was therefore lowered from 120 s to 60 s, which
is `respiration_scan`'s own floor (`seg_s=60.0`). The `presence_verdict`
thresholds were **not** changed. To be precise about what this buys: at 120 s,
label-confined scanning still works, but it reaches only **`zone2`** (config A,
2 scans, both below threshold) or **`zone2` and `empty`** (config B, 4 scans,
2 above threshold) — `zone1`, `zone3` and `zone4` are not scannable at 120 s in
any configuration, and `empty` is scannable in only one (`..._155622`) of the
four files that carry the label, because the other three `empty` runs lose bins
to motion flags or invalid data before reaching 120 s.
Lowering to 60 s widens coverage from two conditions to four (`empty`, `zone1`,
`zone2`, `zone3`; `zone4` yields no scan at any setting). It does not
create the analysis; it broadens it, and it is not free: at exactly 60 s there
is one Welch segment and therefore no averaging, so the SNR estimate has no
variance reduction and the false-peak rate rises. Every respiration number
below carries that caveat. The 120 s results are consistent with the 60 s ones
and are noted where they differ.

### 1.5 Calibration configurations

| cfg | motion floor from | applies to | held out? |
|---|---|---|---|
| **A** | `rx_20260714_031131.csv` (overnight, *assumed* empty, 8 days earlier) — the *kind* of source `occ_offline.py`'s docstring asks for ("a session … believed to be an empty room"); it names no actual file | all six files | yes, but the truth is assumed, not scripted |
| **B** | labeled `empty` bins of the *other* afternoon file | the two-link afternoon files | **yes** |
| **C** | the evening file's own labeled `empty` bins | the evening three-link file | **no — in-sample for the `empty` row** |
| **D** | same as C, with beacon B2 discarded | the evening file | ablation, see §3 |

Config A degrades badly and the pipeline says so out loud: B1's median RSSI on
07-22 is −83 to −89 dBm against −68 dBm at calibration, a 15–21 dB shift, so
the RSSI guard invalidates B1's transferred floor in **all six files** and the
link self-recalibrates on the file's own quietest half. In files 79–605 s long
that are mostly occupied, "quietest half" is not empty. Config A's occupied
numbers are contaminated by that circularity and are shown for completeness,
not relied on.

---

## 2. What is actually in the files

### 2.1 Link census — five of six files are two-link

| file | UTC span | links on air | missing |
|---|---|---|---|
| `occ_20260722_151807` | 20:22:26 → 20:23:44 | B1, B3 | **B2** |
| `occ_20260722_152849` | 20:28:49 → 20:38:55 | B1, B3 | **B2** |
| `occ_20260722_154312` | 20:43:12 → 20:44:59 | B1, B3 | **B2** |
| `occ_20260722_154716` | 20:47:16 → 20:52:03 | B1, B3 | **B2** |
| `occ_20260722_155622` | 20:56:22 → 20:59:02 | B1, B3 | **B2** |
| `occ_20260722_191220` | 07-23 00:12:20 → 00:22:21 | B1, B2, B3 | — |

`grep -c 28:05:a5:2f:fa:48` returns **0** in all five afternoon files and
**25,748** in the evening file, where B2 is present in row 1 (offset +0.00 s).
This re-derives `docs/NODE_CENSUS.md` P7 independently.

**Precision on the outage length.** `docs/NODE_CENSUS.md` §5 calls this a
"~37-minute block"; `docs/HANDOFF.md`'s correction block states the window
(20:22–20:59 UTC) without naming a duration. 36.6 minutes is the wall-clock
span of the five afternoon
captures (20:22:26 → 20:59:02 UTC), and B2 is provably absent throughout it.
It is *not* a measured outage duration: the previous B2 sighting is
`rx_20260715_201703.csv`, ending 2026-07-16 05:10 UTC, six days earlier. The
outage could have begun at any point in those six days. What is proven is
absence during 36.6 minutes of capture and presence again by 07-23 00:12:20
UTC.

**Why two links is materially harder, not just "one fewer."**
`occ/motion.py::FusedDetector` fires when the *second-largest* link z exceeds
`z_on`, or any single link exceeds `z_solo`. With three links that is a 2-of-3
vote. With two links `Zs[-2]` is the *minimum* of the two, so the rule becomes
**2-of-2** — both links must independently clear z=5. The afternoon block is
running a strictly stricter detector than the evening block, on top of having
one less geometric path. Any afternoon detection rate presented as comparable
to a three-link rate would be wrong twice over.

Per-link operating points, all six files:

| file | B1 fps / RSSI / cov | B2 fps / RSSI / cov | B3 fps / RSSI / cov |
|---|---|---|---|
| `..._151807` | 43.4 / −83 / 99.4% | — | 82.4 / −65 / 100.0% |
| `..._152849` | 26.2 / −86 / 95.1% | — | 81.1 / −65 / 100.0% |
| `..._154312` | 33.6 / −84 / 97.2% | — | 74.3 / −64 / 99.9% |
| `..._154716` | 35.0 / −85 / 97.6% | — | 81.0 / −66 / 100.0% |
| `..._155622` | 34.8 / −83 / 97.7% | — | 78.4 / −64 / 100.0% |
| `..._191220` | **15.9 / −89 / 63.7%** | 42.9 / −80 / 99.3% | 59.4 / −75 / 99.8% |

B1 in the evening file is a degraded link: 63.7% bin coverage and 15.9 fps.
It contributes to the fused vote anyway.

### 2.2 Label inventory — the ground truth as recorded

| file | label | seconds | runs |
|---|---|---:|---|
| `..._151807` | `zone4` | 41.3 | 41 s |
| `..._151807` | *(unlabeled)* | 37.3 | |
| `..._152849` | `zone1` | 130.3 | 60 s, 70 s |
| `..._152849` | `zone2` | 222.1 | 171 s, 51 s |
| `..._152849` | `zone3` | 61.1 | 61 s |
| `..._152849` | `zone4` | 87.2 | 55 s, 32 s |
| `..._152849` | *(unlabeled)* | 104.7 | |
| `..._154312` | `empty` | 87.1 | 87 s |
| `..._154312` | *(unlabeled)* | 20.6 | |
| `..._154716` | `empty` | **3.1** | 3 s |
| `..._154716` | `zone3` | 80.4 | 80 s |
| `..._154716` | *(unlabeled)* | 202.9 | |
| `..._155622` | `empty` | 140.7 | 141 s |
| `..._155622` | *(unlabeled)* | 19.6 | |
| `..._191220` | `empty` | 120.2 | 120 s |
| `..._191220` | `zone1` | 155.3 | 80 s, 75 s |
| `..._191220` | `zone2` | 155.4 | 81 s, 74 s |
| `..._191220` | `zone3` | 166.4 | 79 s, 87 s |
| `..._191220` | *(unlabeled)* | 3.4 | |

Totals: **1,450.6 s labeled** (24.2 min), 388.5 s unlabeled, 1,839.1 s of
capture across six files. Per condition: `empty` 351.1 s, `zone1` 285.6 s,
`zone2` 377.5 s, `zone3` 307.9 s, `zone4` 128.5 s.

The 3.1-second `empty` in `occ_20260722_154716`, immediately followed by a
clear-to-blank, is a mis-key. It is excluded from the pooled `empty` figures
and shown separately where it appears.

The evening file is two clean cycles of `zone1 → zone2 → zone3`, which is the
protocol's "repeat the whole cycle a second time" instruction followed.

### 2.3 What the labels do not record — say it plainly

These are unknowns, not inferences to be filled in:

- **What `zone1`–`zone4` are.** No session-notes file exists anywhere in the
  repo; `grep` across `docs/`, `README.md`, `PROJECT_NOTES.md` and `CLAUDE.md`
  finds no mention of the 07-22 zone labels. `pc/zone_calib.py` documents the
  *convention* (`zone1`..`zoneN`, `empty`) but names no physical location.
- **Whether the subject was walking or still at each zone.** The
  zone-calibration variant of the protocol asks for *walk* segments per
  location; the operator recorded bare `zoneN`. Motion state is not in the
  data. This is the single reason no `walk` rate and no `still` rate can be
  produced.
- **Whether the room was genuinely vacant during `empty`.** `OCC_PROTOCOL.md`
  §Setup warns that if you start and stop at the PC, *you are the test
  subject* and keyboard time is `still` at best. Every `empty` interval in
  this session begins seconds after a keypress and — in `..._154312` and
  `..._155622` — runs to the end of file, which is also a keypress (`q`). The
  first 15 s of each interval is trimmed here; the tail is not trimmable
  without knowing when he came back.
- **Cat state.** The protocol requires both cats out of the room for `empty`
  and `still`. Nothing records whether they were.
- **Appliance / HVAC state**, which the protocol asks for by name because an
  in-band mechanical modulation is a real detection, not a bug.
- **Household truth notes** — where the family was, neighbour activity. Not
  recorded.

The unlabeled stretches are suggestive but not evidence: the pre-`empty`
prefixes of `..._154312` (20.6 s labeled blank, **19.7 s of it covered**) and
`..._155622` (19.6 s blank, **18.7 s covered**) are motion-flagged **79.7%**
and **72.2%** under config B (config A: 79.2% and 72.2%), consistent with the
operator at the keyboard about to leave. That is a plausible story, not a
label, and it is not scored.

---

## 3. Results

All percentages below are of **covered** seconds (bins where at least one link
has finite data), over **interval interiors** (first 15 s of each labeled run
dropped). "either" = motion-flagged OR breathing-flagged, i.e. the pipeline's
overall occupied verdict.

### 3.1 Pooled per condition, per configuration

| cfg | condition | files | seconds | motion % | breathing % | either % |
|---|---|---:|---:|---:|---:|---:|
| A | `empty` | 3 | 303.0 | 18.81 | 81.16 | **99.97** |
| A | `zone1` | 2 | 225.6 | 58.56 | 24.47 | 83.02 |
| A | `zone2` | 2 | 317.5 | 40.85 | 0.00 | 40.85 |
| A | `zone3` | 3 | 247.9 | 70.15 | 0.00 | 70.15 |
| A | `zone4` | 2 | 83.5 | 7.19 | 0.00 | 7.19 |
| **B** | `empty` | 2 | 197.8 | **1.97** | 98.03 | **100.00** |
| **B** | `zone1` | 1 | 100.3 | 100.00 | 0.00 | 100.00 |
| **B** | `zone2` | 1 | 192.1 | 0.00 | 81.21 | 81.21 |
| **B** | `zone3` | 2 | 111.5 | **0.63** | 0.00 | **0.63** |
| **B** | `zone4` | 2 | 83.5 | 35.45 | 0.00 | 35.45 |
| C | `empty` (in-sample) | 1 | 105.2 | 2.19 | 97.81 | **100.00** |
| C | `zone1` | 1 | 125.3 | 47.25 | 0.00 | 47.25 |
| C | `zone2` | 1 | 125.4 | 5.98 | 94.02 | 100.00 |
| C | `zone3` | 1 | 136.4 | 100.00 | 0.00 | 100.00 |
| D | `empty` (in-sample) | 1 | 105.2 | 2.19 | 97.81 | 100.00 |
| D | `zone1` | 1 | 125.3 | 41.82 | 0.00 | 41.82 |
| D | `zone2` | 1 | 125.4 | 5.98 | 94.02 | 100.00 |
| D | `zone3` | 1 | 136.4 | 100.00 | 0.00 | 100.00 |

Config B covers only the two-link afternoon block; configs C and D only the
evening three-link file. Config A is the only one spanning both, and is the
one whose floors are least trustworthy (§1.5).

### 3.2 Motion false-alarm rate on `empty` — the one usable number

| basis | seconds | motion-flagged | note |
|---|---:|---:|---|
| **B — two-link, held-out in-session empty** | 197.8 | **1.97%** | the cleanest estimate in this session |
| ↳ `..._154312` scored on `..._155622`'s floor | 72.1 | 0.00% | |
| ↳ `..._155622` scored on `..._154312`'s floor | 125.7 | 3.10% | |
| C — three-link, own empty | 105.2 | 2.19% | **in-sample**, biased low |
| A — cross-session overnight floor | 303.0 | 18.81% | B1 self-recalibrated in every file |

Untrimmed (whole interval, including the operator's exit): config B pools to
**12.64%** over 227.8 s (`..._154312` 11.37%, `..._155622` 13.43%); config C
is 1.91%. The 15-second trim moves the two-link afternoon figure from 12.6% to
2.0%, which is itself worth knowing: most flagged "empty" time is the operator
walking out, exactly as `OCC_PROTOCOL.md` step 1 anticipates — and exactly what
the committed scorer, which does not trim, currently counts as a false alarm.

**~2% of labeled-empty time motion-flagged, over ~198 seconds of held-out
two-link empty.** That is a real measurement and it is a small one. Two files,
one afternoon, one link pair, no cat exclusion recorded. It should be quoted
with all of that attached or not quoted. It is also not a diffuse noise rate:
§3.6 shows the entire 1.97% is **3.9 seconds in two runs**, one B3 excursion
in `..._155622`, cause unknown.

For context and not as a comparison: `docs/HANDOFF.md` reports 0.50%
activity-flagged over the assumed-empty overnight interior. These are not the
same quantity — different link count, different fusion arity, different
calibration, 8 days apart, 198 s versus 4.6 h.

### 3.3 Motion on occupied time — no rate can be quoted

The same label, the same file, the same untuned thresholds, differing only in
which empty data set the floor:

| file | label | seconds | config A | config B |
|---|---|---:|---:|---:|
| `..._152849` | `zone1` | 100.3 | 6.78% | **100.00%** |
| `..._152849` | `zone2` | 192.1 | 2.24% | **0.00%** |
| `..._152849` | `zone3` | 46.1 | **81.34%** | **0.00%** |
| `..._152849` | `zone4` | 57.2 | 6.47% | 5.77% |
| `..._151807` | `zone4` | 26.3 | 8.75% | **100.00%** |
| `..._154716` | `zone3` | 65.4 | 0.00% | 1.07% |

Over 26–192 seconds of interval interior per row, the same ground truth reads
6.78% or 100.00% (`zone1`), 81.34% or 0.00% (`zone3` in `..._152849`), 8.75%
or 100.00% (`zone4` in `..._151807`). Both floors are legitimate, neither was
tuned, and the disagreement is not noise — it is
the count-conditioned floor for B1 being fitted on different data in a session
where B1 sits 15–21 dB below its reference operating point. **This session
cannot pin a motion detection rate.** Any single number drawn from it would be
a choice of calibration file presented as a measurement.

The evening three-link file is more internally consistent (`zone3` 100%,
`zone1` 47%, `zone2` 6%) but that is one 10-minute file, in-sample, and it
also spans 6%–100% across three labels that are, as far as anything recorded
says, the same activity at three different places.

### 3.4 The B2 ablation — measuring the two-link caveat instead of asserting it

Config D is the evening file with B2 discarded, so the *identical* ground
truth is scored against the afternoon's link set:

| condition | seconds | three-link (C) | two-link (D) | Δ |
|---|---:|---:|---:|---:|
| `empty` | 105.2 | 2.19% | 2.19% | 0.00 |
| `zone1` | 125.3 | 47.25% | 41.82% | **−5.43** |
| `zone2` | 125.4 | 5.98% | 5.98% | 0.00 |
| `zone3` | 136.4 | 100.00% | 100.00% | 0.00 |

Losing B2 costs 5.4 points of motion-flagged time on `zone1` and nothing
measurable on the other three conditions, on this one file. That is a small
effect, and it is a **lower bound** on the real cost, for two reasons: the
evening geometry may not resemble the afternoon's, and B2's absence in the
afternoon also degrades the *fusion arity* (2-of-3 → 2-of-2, §2.1) in a way
this ablation reproduces but the small Δ here does not isolate. The honest
statement remains: the five afternoon files are a two-link result and must be
labeled as such wherever they are cited.

### 3.5 Respiration — the full observed range, and a clear negative

The four configurations produce **33 scan instances** (A 12, B 10, C 7, D 4).
Config D re-scans the same segments as config C with B2 removed, so its 4 are
exact repeats; deduplicating on `(file, label, link, bin range)` leaves **29
distinct link-scans, 16 of them PRESENCE at stock thresholds**. The dedup is
imperfect and in one direction: `..._154716` `zone3` is scanned under both A
(bins 2094–2863 / 2094–2864) and B (2088–2857 / 2088–2857) — the same physical
segment offset by six bins, on both links — so it contributes **two excess
entries** inside the 29. Treat 29 as an upper bound on distinct
segment×link scans and 33 as the raw instance count; no conclusion below turns
on which is used.

| set | n | SNR dB | bpm | subcarrier agreement |
|---|---:|---|---|---|
| **all scans** | 29 | **4.90 – 14.66** (median 9.54) | **7.0 – 27.5** (median 13.5) | 2 – 9 of 10 |
| **PRESENCE only** | 16 | **7.58 – 14.66** (median 9.97) | **7.0 – 19.0** (median 11.0) | 5 – 9 of 10 |
| below threshold | 13 | 4.90 – 9.95 | 9.5 – 27.5 | |

This is the full set, not the strongest handful. For the record of how the
published figure has moved: `docs/HANDOFF.md:158` says **7–12 bpm at 10–14 dB**
(and 10/10 subcarrier consensus); `PROJECT_NOTES.md` §2 reran the cited evening
session and got **7.0–16.0 bpm, 6.1–15.2 dB** over the full set of
presence-verdict scans (it gives no count; `docs/csi-array-case-study.md:135`
carries the same range and puts the count at 54); this session gives
**7.0–19.0 bpm, 7.58–14.66 dB** over its 16, on a different session with a
different link set. HANDOFF's narrow figure is the one still uncorrected.

**Where the PRESENCE verdicts land is the finding.** By condition:

| condition | scans | PRESENCE | observed bpm values |
|---|---:|---:|---|
| `empty` | 12 | **9** | 19.0, 11.0, 13.5, 7.0, 10.0, 19.0, 18.0, 11.0, 13.5, 7.0, 9.0, 13.5 |
| `zone1` | 2 | 1 | 16.0, 13.0 |
| `zone2` | 9 | 6 | 15.0, 9.5, 20.0, 9.0, 19.0, 12.0, 10.5, 11.0, 15.0 |
| `zone3` | 6 | 0 | 15.0, 15.5, 27.5, 16.5, 15.0, 15.5 |
| `zone4` | 0 | 0 | — |

**Nine of the sixteen PRESENCE verdicts occur while the room is labeled
empty.** Pooled, the respiration detector flags 81–98% of labeled-empty
interior seconds depending on configuration, 0% of `zone3` and `zone4` time in
every configuration, and 0–24.47% of `zone1`. Its one high occupied-time score
is `zone2` — 0.00% under config A, 81–94% under B, C and D — and `zone2` is
also the condition whose scans disagree most on rate (see below). It is not
discriminating presence on this session; on `empty` it is close to always-on.

**Cross-link rate consensus — the detector's own stated discriminator — is
absent.** `occ/breathing.py` says a real breather produces subcarriers that
agree on the rate; the same argument applies across links looking at the same
room. All fourteen file/label groups with two or more scanned links, none
omitted:

| config | file | label | per-link bpm | spread |
|---|---|---|---|---:|
| A | `..._152849` | `zone1` | B1=16.0, B3=13.0 | 3.0 |
| A | `..._152849` | `zone2` | B1=15.0, B3=9.5 | 5.5 |
| A | `..._154312` | `empty` | B1=19.0, B3=11.0 | **8.0** |
| A | `..._154716` | `zone3` | B1=15.0, B3=15.5 | 0.5 |
| A | `..._155622` | `empty` | B1=13.5, B3=7.0 | 6.5 |
| A | `..._191220` | `empty` | B2=10.0, B3=19.0 | **9.0** |
| B | `..._152849` | `zone2` | B1=20.0, B3=9.0 | **11.0** |
| B | `..._152849` | `zone3` | B1=27.5, B3=16.5 | **11.0** |
| B | `..._154312` | `empty` | B1=18.0, B3=11.0 | 7.0 |
| B | `..._154716` | `zone3` | B1=15.0, B3=15.5 | **0.5** |
| B | `..._155622` | `empty` | B1=13.5, B3=7.0 | 6.5 |
| C | `..._191220` | `empty` | B2=9.0, B3=13.5 | 4.5 |
| C | `..._191220` | `zone2` | B1=10.5, B2=11.0/19.0, B3=12.0/15.0 | **8.5** |
| D | `..._191220` | `zone2` | B1=10.5, B3=12.0/15.0 | 4.5 |

Spreads of 0.5 to 11.0 bpm on simultaneous observations of the same room. Two
of the fourteen agree closely — `..._154716` `zone3` at 0.5 bpm, under both A
and B, which is the same segment scored twice and so is one observation, not
two; notably **neither of its scans clears the presence threshold**. Of the
twelve remaining groups, eleven spread by more than 3 bpm; the twelfth
(`[A] ..._152849` `zone1`) spreads by exactly 3.0. A single breather
cannot breathe at 20 and 9 breaths per minute at once. The PRESENCE calls in
this session are, on the available evidence, in-band spectral content that
clears a 6 dB threshold on a 60-second window with no Welch averaging — not a
measured respiration rate.

Note also that the 27.5 bpm scan (`..._152849` `zone3`, B1, below threshold)
lands in the 20–30 bpm band the protocol nominates as the *cat* discriminator.
With no cat label and no session note, that is an unexplained observation, not
a cat detection.

### 3.6 Per-label motion z-score distributions

Distributions rather than point estimates, interval interiors, config B for
the two-link block and config C for the evening file:

| file | label | link | n bins | p50 | p90 | p99 | max |
|---|---|---|---:|---:|---:|---:|---:|
| `..._154312` | `empty` | B1 | 721 | 0.58 | 1.55 | 2.42 | 3.02 |
| `..._154312` | `empty` | B3 | 721 | 0.58 | 4.27 | 11.18 | 13.94 |
| `..._155622` | `empty` | B1 | 1257 | −1.15 | 1.12 | 3.68 | 6.38 |
| `..._155622` | `empty` | B3 | 1257 | −0.33 | 1.77 | 32.97 | **36.07** |
| `..._151807` | `zone4` | B1 | 263 | −1.18 | 0.31 | 3.46 | 3.86 |
| `..._151807` | `zone4` | B3 | 263 | 4.11 | 12.14 | 23.03 | 23.65 |
| `..._152849` | `zone1` | B1 | 1003 | 3.22 | 4.63 | 5.91 | 6.39 |
| `..._152849` | `zone1` | B3 | 1003 | 0.79 | 6.38 | 15.85 | 16.78 |
| `..._152849` | `zone2` | B1 | 1921 | 3.06 | 4.47 | 5.81 | 6.68 |
| `..._152849` | `zone2` | B3 | 1921 | 0.09 | 2.68 | 8.44 | 11.76 |
| `..._152849` | `zone3` | B1 | 461 | 3.03 | 4.12 | 5.51 | 5.79 |
| `..._152849` | `zone3` | B3 | 461 | 0.86 | 2.40 | 3.67 | 4.22 |
| `..._152849` | `zone4` | B1 | 572 | 3.65 | 4.78 | 6.23 | 7.65 |
| `..._152849` | `zone4` | B3 | 572 | −0.13 | 3.14 | 15.78 | 17.05 |
| `..._154716` | `zone3` | B1 | 654 | 1.86 | 3.50 | 4.66 | 5.02 |
| `..._154716` | `zone3` | B3 | 654 | 0.81 | 2.39 | 17.35 | 22.82 |
| `..._191220` | `empty` | B1 | **39** | 10.50 | 12.74 | 13.17 | 13.25 |
| `..._191220` | `empty` | B2 | 1052 | −0.03 | 1.52 | 8.06 | 8.55 |
| `..._191220` | `empty` | B3 | 1052 | 0.08 | 2.30 | 10.14 | 11.10 |
| `..._191220` | `zone1` | B1 | 813 | 1.89 | 9.07 | 12.99 | 15.13 |
| `..._191220` | `zone1` | B2 | 1253 | 1.06 | 3.52 | 6.78 | 7.98 |
| `..._191220` | `zone1` | B3 | 1253 | 0.46 | 4.13 | 9.34 | 11.62 |
| `..._191220` | `zone2` | B1 | 963 | 0.98 | 8.55 | 12.31 | 13.84 |
| `..._191220` | `zone2` | B2 | 1254 | 0.68 | 1.70 | 2.54 | 2.93 |
| `..._191220` | `zone2` | B3 | 1254 | −0.79 | 2.34 | 48.50 | **54.51** |
| `..._191220` | `zone3` | B1 | 1364 | 1.41 | 4.67 | 7.13 | 8.55 |
| `..._191220` | `zone3` | B2 | 1364 | 0.40 | 1.68 | 4.24 | 4.93 |
| `..._191220` | `zone3` | B3 | 1364 | 7.76 | 42.40 | 58.74 | **64.80** |

Three things to read off this table:

- **B3 carries the signal; B1 barely moves.** Across the two-link block B1's
  p99 clears z=5 only in `occ_20260722_152849` and only marginally (5.51–6.23);
  in the other four files its p99 is 2.42–4.66. Under the 2-of-2 fusion rule
  (§2.1) B1 is the binding constraint on nearly every detection, and B1 is the
  link running 15–21 dB below its reference operating point.
- **The largest excursion in the two-link block is on `empty`, not on an
  occupied label**: `..._155622` `empty` B3 reaches z=36.07 with p99 = 32.97
  during 125.7 s of labeled-vacant time — 67 of 1,257 bins above z=5 and 35
  above z=12, against 4 and 0 for B1. The fused detector fires on 3.9 s of it
  in two runs (1.3 s and 2.6 s), via the `z_solo`=12 single-link gate. **That
  3.9 s is the entire two-link false-alarm figure in §3.2**: the pooled 1.97%
  is one B3 excursion in one file, not a diffuse noise rate. Whether it is a
  real event (a cat, a person elsewhere in the house, an appliance) or a link
  artifact is **unknown**, and there are no session notes to settle it. It is
  exactly the kind of blip `OCC_PROTOCOL.md` §Setup asks the household truth
  notes to resolve.
- **`..._191220` `empty` B1 has 39 finite bins out of 1,052** — 3.7% coverage
  on that link during the evening empty interval — and its median z there is
  +10.5. Any statement about B1's behaviour during the evening `empty` rests
  on 3.9 seconds of data.

---

## 4. Verdict

### 4.1 What this session establishes

1. **The 07-22 capture does not carry the occupancy protocol's labels.**
   `empty` and `zone1`–`zone4` are the only values in the `label` column of any
   of the six files. Those match `pc/zone_calib.py`'s documented convention
   (mtime `2026-07-22 19:38`, sixteen minutes after the last capture closed),
   which makes zone calibration the likely intent — but that is an inference
   from a filename convention and an mtime, not a record. No session notes
   exist. The only trace of the tool ever running is a bytecode cache
   (`pc/__pycache__/zone_calib.cpython-314.pyc`, mtime `2026-07-22 19:54:05`),
   which shows it was executed that evening but records nothing about what
   input it was given or what it produced.
2. **Five of the six files are two-link.** B2 (`28:05:a5:2f:fa:48`) is absent
   from all five afternoon captures and present from row 1 of the evening one.
   Independently re-derived here; consistent with `docs/NODE_CENSUS.md` P7.
3. **A motion false-alarm rate on scripted-vacant time: ~2%** (1.97% over
   197.8 s, two-link, held-out in-session empty floors; 0.00% and 3.10% on the
   two constituent files). This is the only detection figure in this session
   that survives held-out calibration, and it is 3.3 minutes of evidence
   containing 3.9 seconds of flagged time in two runs, from a single
   unexplained B3 excursion.
4. **The respiration/still-presence arm does not discriminate on this
   session.** It returns PRESENCE on 81–98% of labeled-empty seconds, 9 of its
   16 PRESENCE verdicts fall on `empty`, and cross-link rate agreement — its
   own stated discriminator — spreads 0.5–11.0 bpm on simultaneous views of
   the same room.
5. **Full observed respiration ranges, all verdicts, not the strong tail:**
   4.90–14.66 dB SNR and 7.0–27.5 bpm across 29 link-scans; 7.58–14.66 dB and
   7.0–19.0 bpm across the 16 PRESENCE verdicts.
6. **Motion detection rate on occupied time is not determined by this data.**
   The same label, same file, same untuned thresholds give 0% or 100%
   depending on which empty data fits the floor.
7. **The committed scorer has two defects this exposed**, both listed in §1.3:
   `occ_offline.py` does not trim interval interiors despite the protocol
   saying it does, and it attributes a straddling respiration scan to every
   label it touches. Neither is fixed here — `pc/occ/` and `pc/occ_offline.py`
   were not modified — and both are worth a separate change.

### 4.2 What this session does not establish

- **Motion detection rate.** No `walk` label exists. §3.3 shows the data
  cannot substitute for one.
- **Still-presence detection rate.** No `still` label exists. Only three
  labeled runs (171.0 s, 140.7 s, 120.2 s) exceed the detector's committed
  120 s window and two of the three are `empty`, so no *occupied* condition has
  a run long enough to score at stock settings. At those settings
  `occ_offline.py`'s label-blind quiet-run search yields
  **two** respiration link-scans for the whole session. Even with the window at
  60 s (§1.4), `zone3` and `zone4` produce no PRESENCE verdict at all and
  `zone1` produces one — there is no still-presence condition here to score.
- **Pet immunity.** No `cat` label. Not measured, at all.
- **The through-wall sleeper.** No `wall-sleeper` label.
- **Any three-link occupancy result beyond one 10-minute file**, in which B1
  ran at 63.7% coverage.
- **That the room was empty during `empty`.** The operator started and stopped
  at the PC; cat state, appliance state and household location are unrecorded.
  The false-alarm number in §3.2 is conditional on a vacancy that nothing
  independently confirms.
- **What any zone is, or whether the subject was moving in it.**

### 4.3 What to do next, in order of value

1. **Run the session `OCC_PROTOCOL.md` actually describes** — `--labels
   empty,walk,still,out,cat`, 3-minute `still` and `empty` segments, cats
   excluded and *written down*, appliance state written down, two cycles.
   Confirm all three beacons are on air first (`python pc\field_diag.py COM3`);
   the 07-22 session lost a third of its array and nobody noticed for four
   weeks. Everything in §4.2 becomes measurable and nothing in §4.1 needs
   redoing.
2. **Write the session notes the protocol asks for**, at capture time. Half
   the unknowns in §2.3 are unknowns only because nobody typed three lines.
3. **Fix B1's operating point or drop it.** At −83 to −89 dBm it is the
   binding constraint on a 2-of-2 vote and it self-recalibrates out of every
   cross-session calibration. Find out what moved. (`docs/HANDOFF.md` open
   thread #0 asks the same question about B3's −13 dB shift on Jul-15; this is
   the same class of problem, unresolved, now on a different link.)
4. **The respiration detector needs an empty-room false-alarm calibration
   before it is quoted again**, which is what §3.5 says it does not have. The
   6 dB / 5-agree thresholds are described in the code as "starting points"
   that "get calibrated against real empty-room segments." They never were.
5. **Run `pc/zone_calib.py` on this session and write the output down.** The
   zone labels are the convention that tool expects and this analysis is
   independent of everything above. Its bytecode cache says it was executed on
   2026-07-22 19:54; no result was ever recorded, so as far as the repo is
   concerned that run did not happen.

### 4.4 Effect on existing claims

`PROJECT_NOTES.md` §3 says to "flag [occupancy detection] as based on assumed,
not scripted-ground-truth, labels until `occ_20260722_*.csv` gets scored."
It has now been scored, and **the flag should stay on.** This session does not
convert the assumed-label occupancy results into honest labeled rates. It
produces one small false-alarm number under stated conditions, a clear
negative on the respiration arm, and a documented reason why the rest is not
computable from this data.

---

## 5. Reproduce

```
cd pc
python exp_occ_ground_truth.py --report ..\occ_scoring.txt --json ..\occ_scoring.json

# cross-check against the committed tool (config A motion column)
python occ_offline.py "..\data\raw\occ_20260722_*.csv" ^
    --calib ..\data\raw\rx_20260714_031131.csv

# link census
findstr /R /C:"28:05:a5:2f:fa:48" ..\data\raw\occ_20260722_151807.csv

# synthetic DSP checks still pass
python test_occ_synth.py
```

`python pc\test_occ_synth.py` was run at the end of this work and reports
`ALL OK` (4/4: injected 15 bpm → 15.0 bpm at 12.7 dB with 10/10 agreement;
0/10 false presence on noise; Welch tone 0.300 → 0.300 Hz; motion burst 100%
detected at 0.00% false alarm on the floor). It is a synthetic suite and needs
no dataset; it confirms the DSP is intact and says nothing about the results
above.

## Files added by this work

- `pc/exp_occ_ground_truth.py` — read-only scorer; source of every number here
- `docs/OCC_2026-07-22_RESULTS.md` — this file

Nothing else was created, modified or deleted by this work. Verified with
`find . -type f -newermt 2026-08-20`, which returns only the two files above
plus `pc/__pycache__/exp_occ_ground_truth.cpython-310.pyc` (gitignored); the
`docs/`, `pc/` and `pc/__pycache__/` directory mtimes moved as a consequence of
those writes. Every file under `data/raw/`, `pc/occ/` and `pc/rff/` carries a
July mtime; every pre-existing `pc/*.py` carries a mtime of 2026-08-15 or
earlier. Nothing outside the two new files was touched.

**Note on `git status`, so this is not misread.** `git status --porcelain`
lists modifications and untracked files that predate this session and were not
made here. Modified (` M`): `README.md`, `docs/HANDOFF.md`, four `firmware/`
files, thirteen `data/fingerprints/*.json`, `pc/heatmap.py`. Untracked (`??`):
roughly 25 entries including `PROJECT_NOTES.md`, `CLAUDE.md`,
`docs/NODE_CENSUS.md`, `docs/csi-array-case-study.md`, `pc/zone_calib.py` — and
now the two files this work added. The `pc/heatmap.py` diff is line-ending
churn only (232 insertions / 232 deletions), as are the fingerprint JSONs
(187/187, two at 188/188); all fourteen are empty under
`git diff --ignore-all-space`. The `README`/`HANDOFF`/`firmware` diffs are real
prior content, including the uncommitted BLE groundwork `docs/HANDOFF.md` warns
must not be discarded. **Nothing was staged, committed or pushed.**
