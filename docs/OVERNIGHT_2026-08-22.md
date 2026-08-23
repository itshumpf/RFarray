# OVERNIGHT — d0wd + s3, 2026-08-22 02:30:34 → 08:58, empty room

Controlled follow-up to `docs/S3_SFO_STEPS.md`, which found one receiver-side
event on the Heltec S3 at t = 930 s in a 70-minute daytime session and could
not say what it was or whether it recurs. This capture was taken to answer
one question stated in advance.

Read-only. Both CSVs were opened `"r"` and never written; nothing in
`data/raw/` was modified, renamed or deleted. No serial port was opened,
nothing was flashed, nothing was staged, committed or pushed. Two files in
the repo were written by this pass: this one and
`pc/exp_overnight_0822.py`. Caches went to `../overnight_0822_cache/`,
outside the repo tree.

**Inputs**

| | `d0wd_20260822_023034.csv` | `s3_20260822_023034.csv` |
|---|---|---|
| board / link | ESP32-D0WD, UART bridge | Heltec ESP32-S3, native USB |
| `node_id`, every row | 68 | 108 |
| bytes | 2,529,534,604 | 2,962,429,711 |
| data rows | 2,983,560 | 3,564,005 |
| `pc_time_us` span | 23,267.365 s | 23,267.252 s |
| first / last `pc_time_us` | 1787383835186933 / 1787407102551712 | 1787383835158318 / 1787407102410606 |

The two start stamps differ by 28.6 ms and the two end stamps by 141.1 ms;
both readers ran in one `pc/capture.py` process, so `pc_time_us` is a shared
host clock and the overlap is 99.999 % of either file. Everything below is
computed over each file in full — with a 6.5 h common window there is nothing
to gain from trimming to the intersection, and the two are aligned to within
0.14 s at both ends.

**Both captures were finished before any of this ran.** `ls --time-style` at
09:50 CDT reported both files last modified **08:58:22**, 52 minutes
quiescent, and unchanged in size across the whole analysis. This matters
because `pc/occ_offline.py:351-354` is the only running-capture guard
anywhere in `pc/`, and nothing used here has one.

**Operator-stated conditions**, recorded here as stated and not verified by
these files: nobody was in the room for the whole capture; receiver positions
unchanged from 2026-08-21 and **not** swapped; beacons unmoved; the S3 had a
battery attached while on USB, so its charge circuit was live throughout and
its charge LED stayed lit. Where a conclusion below leans on one of these,
it says so.

---

## 0. The pre-registered question, answered

Three outcomes were named in advance. **The data supports `Absent`.**

Over 6.5 h the S3's `noise_floor` never changes regime. It takes only four
values all night — `-93` on 84.95 % of rows, `-92` on 14.64 %, `-91` on
0.39 %, `-94` on 0.017 % — and its modal value per 10 s bin is **−93 dB in
86.89 % of the
2,327 bins**, and the 129 excursions away from it have a **median duration of
10 s and a maximum of 220 s** — every one of them reverts. Excluding the
first and last five minutes, the peak-to-peak of the 5-minute-smoothed series
is **1.0 dB**, entirely between −93 and −92, with no level held long enough
to be a regime. Nothing resembling the 2026-08-21 event — a persistent
departure from a pinned value, simultaneous with an RSSI step on all three
beacons and an SFO step on all three — occurs at any point in the night.
(`report`, TABLE 1 / TABLE 1c.)

The other two outcomes are ruled out on their own terms:

- **Not periodic.** A 0.25 dB threshold on the smoothed series flags 12
  excursions. Their inter-event intervals are 90, 2955, 220, 9560, 2270,
  1375, 4935, 60, 395, 1235, 125 s — mean 2110.9 s, **sd 2767.8 s, CV
  1.311**. A periodic process has CV near 0. Four of the twelve are the
  power-on settle (t < 150 s) and the shutdown minutes (t > 23,100 s).
- **Not once at a random time.** There is no single event; there are 129
  short reverting excursions and no persistent change.

**The strongest thing this establishes** is negative and about the S3's own
hardware: whatever happened at t = 930 s on 2026-08-21 is **not a
free-running receiver-internal cycle on a timescale of tens of minutes**,
because the same board in the same position ran 6.5 h without producing one.
That eliminates the `Periodic` hypothesis as stated. One thing this pass
cannot check: **whether the S3 was powered the same way on 2026-08-21.** The
battery is a stated condition of *this* capture only; nothing in either CSV
records a power configuration, and `docs/S3_SFO_STEPS.md` does not state one.
If the battery was absent yesterday, the two sessions differ in exactly the
variable the `Periodic` hypothesis is about.

**What it does not establish, and must not be read as.** "The operator moving
in the room caused yesterday's step" is *consistent* with this result and is
not demonstrated by it. Three gaps:

1. This capture cannot show that a person entering the room produces that
   signature; it can only show that an empty room does not produce it. The
   positive control was not run.
2. The charge-controller hypothesis is weakened, not closed. The operator
   states the charge LED stayed lit for the whole capture, i.e. the charger
   was in one state throughout. A controller that cycles only around a
   full-charge threshold, or only on a battery that is actually charging,
   would have had no opportunity to cycle here. **An absent stimulus and an
   absent effect are not distinguishable in this file.**
3. The S3's `noise_floor` sits about 2 dB higher tonight than on 2026-08-21,
   so the two sessions are not the same standing state (§2.3). A negative
   result in state A does not fully transfer to state B.

---

## 1. Method, and the reproduction check

One script, `pc/exp_overnight_0822.py`, run from the repo root:

```
D=data/raw/d0wd_20260822_023034.csv
S=data/raw/s3_20260822_023034.csv
for p in 0 1 2 3 4 5; do
    python3 pc/exp_overnight_0822.py part $D --tag d0wd --part $p --nparts 6
    python3 pc/exp_overnight_0822.py part $S --tag s3   --part $p --nparts 6
done
python3 pc/exp_overnight_0822.py merge $D --tag d0wd --nparts 6 --expect-lines 2983560
python3 pc/exp_overnight_0822.py merge $S --tag s3   --nparts 6 --expect-lines 3564005
python3 pc/exp_overnight_0822.py report --tags d0wd,s3
```

Every number in this document is from `report` unless it names another
command. The `part`/`merge` split exists only because the host used for this
pass kills any process when the shell call that spawned it returns, and a
single pass over these two files takes about eleven minutes. It is not an
approximation: ranges are cut on line boundaries with neither loss nor
duplication, and each part pickles the `FrameEstimator`, `WindowAggregator`
and MAC table forward to the next, so the six-part run is frame-for-frame
what one uninterrupted pass would have produced. `merge` re-checks this
rather than asserting it — the parts' row counts sum to **2,983,560 and
3,564,005**, matching `wc -l` minus the header exactly, and **0 of the 5
seams per file** has `pc_time_us` going backwards.

**Phase work** is `pc/rff/dsp.py`'s `FrameEstimator` +
`WindowAggregator(window=64)` with the shipped gates `inlier_ratio >= 0.6`
and `resid_std <= 0.8` — `pc/rff_offline.py:54-79` with a MAC restriction
added. `pc/capture.py:compute_cfo`, `pc/phase_skew.py` and
`pc/fingerprint.py` were **not** used: `docs/CODE_INVENTORY.md` §4.2 C1/C2/C3
establishes all three have the DC/guard-band index wrong, and
`pc/test_rff_synth.py` test 7 shows `phase_skew`'s mask returns the opposite
sign.

**Reproduction check against the unmodified shipped tool.** The first 80,000
rows of each file were copied to `/tmp` and replayed through
`pc/rff_offline.py` as shipped:

```
head -80001 data/raw/d0wd_20260822_023034.csv > /tmp/hd/d0wd_head.csv
head -80001 data/raw/s3_20260822_023034.csv   > /tmp/hd/s3_head.csv
python3 pc/rff_offline.py /tmp/hd/d0wd_head.csv --min-windows 20
python3 pc/rff_offline.py /tmp/hd/s3_head.csv   --min-windows 20
```

| cell | shipped `rff_offline` | this pass, same slice |
|---|---|---|
| B1 / d0wd | 367 windows, +0.0210 | 367, +0.02104 |
| B2 / d0wd | 359 windows, +0.0278 | 359, +0.02782 |
| B3 / d0wd | 242 windows, +0.0453 | 242, +0.04533 |
| B1 / s3 | 417 windows, +0.0144 | 417, +0.01441 |
| B2 / s3 | 306 windows, +0.0104 | 306, +0.01038 |
| B3 / s3 | 501 windows, +0.0136 | 501, +0.01363 |

Six of six window counts identical, six of six medians agreeing to the
shipped tool's printed precision. The MAC restriction is inert, as
`docs/DUAL_RX_2026-08-21.md` §3.1 also found.

**`pc_time_us` is a per-serial-drain-batch host stamp**
(`pc/node_census.py:30-35`, `docs/HANDOFF.md` trap #1). It is used here to
place bins and to measure *host-side delivered* rate, never as per-frame
cadence. Per-frame node-side timing is `esp_timestamp_us`, a u32 in µs that
wraps every 4294.967 s.

**Corrupt rows are screened by two independent routes**, and the difference
between them matters (§4.2): route 1 is the `dropped`-column median filter
from `docs/DUAL_RX_2026-08-21.md` Appendix A (width 9, tolerance 100); route
2 is field plausibility on six columns that have nothing to do with
`dropped` — `node_id` against the file's own mode, `env_id == 0`, `channel`
against the file's own mode, `csi_len` in {128, 256, 384}, `noise_floor` in
[−110, −70], `rssi` in [−100, −10].

**One correction made during this pass, recorded because it changed an
answer.** The first version of that screen listed `csi_len` in {128, 256}
only. That is wrong: `pc/rff/protocol.py:31` sets **`CSI_MAX = 384`** and
`:59` rejects anything longer, so 384 is a length the decoder accepts by
design. `data/fingerprints/f46942f2d2af.json` — written 2026-07-13, from 44
source sessions — records `f4:69:42:f2:d2:af` with **129 frames, `len_hist`
100 % at 384, `rssi_mean` −78.12 with sd 1.46 dB**, which is a stationary
real transmitter, not a decode artefact. The narrow screen flagged all 64 of
that device's frames tonight and classified it as a ghost. With 384 admitted:
the d0wd's corrupt-row count falls **206 → 142**, the S3's falls **3 → 0**,
and one MAC moves from artefact to device. **The drop totals in §4.2 are
unchanged by the correction** (17,366 and 624,291 both ways), because the
`dropped` values on those rows were never wrong.

---

## 2. `noise_floor` over the night

### 2.1 The d0wd is still useless as a control

Independently of the script, by `awk` straight down field 6:

```
awk -F, 'NR>1{h[$6]++} END{n=0; for(v in h){n++; if(h[v]>10) print v,h[v]}
                           print "distinct values:", n}' \
    data/raw/d0wd_20260822_023034.csv
```

**`-97` on 2,983,445 of 2,983,560 rows — 99.9961 %.** The other 115 rows are
spread over 61 distinct values, 26 of them reading `0`. **All 115 are
independently flagged corrupt by the field screen** — re-running the same
`awk` with the six-field plausibility test in front and counting survivors
returns `rows with nf != -97: 115, passing the full field screen: 0`.
Once the 142 corrupt rows are removed, the remaining **2,983,418 clean rows
carry `-97` without exception — 100.000 %, zero row-to-row transitions in 6.5
hours.**

This reproduces `docs/S3_SFO_STEPS.md` §4 exactly (there: −97 on 577,354 of
577,381 rows on 2026-08-21, re-derived here by the same `awk` on
`desk_20260821_125017.csv` and confirmed). **The D0WD build does not vary
this field, so "the d0wd's `noise_floor` held" remains evidence of nothing.**
It could not have stepped. Anything that wants the d0wd as a control for a
receiver-state change needs a different column, and no column in this CSV
carries one.

### 2.2 The S3 varies, and does not step

`awk` again, same command against the S3 file — **exactly four distinct
values, all plausible dBm, and the S3 file contains no corrupt rows at all,
so the clean-row histogram and the raw histogram are the same numbers:**

```
-93  3,027,708      -92  521,651      -91  14,041      -94  605
```

Per-10 s-bin modal value, night's mode −93, held by 86.89 % of 2,327 bins.
Mean `noise_floor` by 30-minute block spans **−92.62 to −92.98** across the
whole night — a total range of 0.36 dB, with no trend:

```
t (h)   0.0    0.5    1.0    1.5    2.0    2.5    3.0    3.5    4.0    4.5    5.0    5.5    6.0
mean  -92.84 -92.81 -92.98 -92.95 -92.86 -92.93 -92.89 -92.82 -92.62 -92.86 -92.95 -92.76 -92.68
```

The 12 excursions ≥ 0.25 dB found by the step detector, with times:

```
t =     0 ->    50 s   -91.000 -> -92.000   -1.000   power-on settle
t =    80 ->   150 s   -92.000 -> -92.889   -0.889   power-on settle
t =  2990 ->  3150 s   -92.888 -> -92.436   +0.453   reverts at t = 3270
t =  3270 ->  3310 s   -92.473 -> -92.872   -0.399
t = 12820 -> 12880 s   -92.568 -> -93.000   -0.432
t = 15050 -> 15190 s   -92.959 -> -92.240   +0.719   reverts at t = 16470
t = 16470 -> 16520 s   -92.402 -> -93.000   -0.598
t = 21400 -> 21460 s   -92.865 -> -92.397   +0.468
t = 21480 -> 21500 s   -92.397 -> -92.000   +0.397
t = 21800 -> 21970 s   -92.000 -> -92.617   -0.617   reverts
t = 23100 -> 23140 s   -93.000 -> -92.000   +1.000   final minutes
t = 23230 -> 23260 s   -92.000 -> -91.000   +1.000   final minutes
```

Every interior excursion is followed by a return. The longest stay away from
the night's modal value is **220 s**; the median is **10 s**. Compare
2026-08-21, where the S3 left a value pinned on essentially every frame for
13 minutes and **never returned to it** for the remaining 55 (`docs/S3_SFO_STEPS.md` §4).

It is a per-node quantity here as it was there: at t = 64 min all three
beacons read exactly −93.0000, at t = 128 min they read −92.4656, −92.4571,
−92.4609, and at t = 256 min −92.3253, −92.3427, −92.3351 (TABLE 1b). The
beacons agree to within 0.02 dB in every bin, which is what a receiver-side
scalar should do.

### 2.3 The S3's standing level differs between the two sessions

Re-derived from the files, not quoted from the earlier document:

| session | −91 | −92 | −93 | −94 | −95 | −96 |
|---|---|---|---|---|---|---|
| `s3_20260821_125017.csv` (649,072 rows) | — | — | 54 | 240,339 | 408,126 | 553 |
| `s3_20260822_023034.csv` (3,564,005 rows) | 14,041 | 521,651 | 3,027,708 | 605 | — | — |

The two distributions do not overlap in their modes. Tonight the S3 reports a
`noise_floor` about **2 dB higher** than yesterday and never once reads −95.
Whatever sets this field on the S3 is not fixed from session to session.

Both boards were restarted shortly before this capture, which is different
from 2026-08-21 and is worth recording because it changes what the file can
see. The S3's first row carries `esp_timestamp_us = 470,372,388` (470 s of
uptime) and **`dropped = 0`**, against `dropped = 30,391` on the first row of
`s3_20260821_125017.csv`, which is what `docs/S3_SFO_STEPS.md` §4 used to
argue that the board "had been up long before the file opened". Tonight it
had not: the capture begins **170 s after the 300 s calibration gate
(`firmware/common/calibration/calibration.c:64-67`) opened**, so unlike
yesterday's file this one does contain the minutes just after calibration.
The d0wd's first row reads `esp_timestamp_us = 1,861,107,159` (31 min) and
`dropped = 3,358`.

This is an observation from the two files; nothing here says what changed,
and §0 point 3 is why it limits how far the null result transfers.

---

## 3. SFO per beacon per node

### 3.1 Whole night

B1 = `a4:f0:0f:77:91:20` (reference), B2 = `28:05:a5:2f:fa:48`,
B3 = `f4:2d:c9:70:72:30` (the clock twin, `docs/LOT_HYPOTHESIS.md`).

| node | b | frames fed | accepted | reject % | windows | SFO median | IQR | mean `resid_std` | RSSI, all frames |
|---|---|---|---|---|---|---|---|---|---|
| d0wd | B1 | 882,769 | 817,246 | 7.422 | 12,769 | **+0.02277** | 0.00396 | 0.1616 | −81.60 |
| d0wd | B2 | 919,632 | 881,797 | 4.114 | 13,778 | **+0.02682** | 0.00207 | 0.1546 | −79.94 |
| d0wd | B3 | 1,178,726 | 485,472 | **58.814** | 7,585 | **+0.07195** | 0.00668 | 0.1559 | −79.06 |
| s3 | B1 | 1,282,394 | 1,273,873 | 0.664 | 19,904 | **+0.01392** | 0.00178 | 0.1416 | −67.87 |
| s3 | B2 | 830,010 | 823,420 | 0.794 | 12,865 | **+0.00959** | 0.00172 | 0.1409 | −73.91 |
| s3 | B3 | 1,449,060 | 1,444,508 | 0.314 | 22,570 | **+0.01466** | 0.00233 | 0.1345 | −65.60 |

**The anomalous cell has changed receivers.** On 2026-08-21 it was B3/s3
(+0.060 at 51.6 % reject before the event) and B3/desk (43.5 % reject). This
session the S3 is clean on all three beacons — **0.314 % to 0.794 % reject**,
lower than any of the six cells in the 2026-08-21 dual-receiver session,
whose best was 0.37 % — and it is **B3/d0wd that rejects 58.8 % of its frames
and returns +0.07195**, 4.9× the same beacon's value at the other receiver
over the same six and a half hours.

That is a stronger statement than it first looks, because it removes the
obvious explanation. B3/d0wd is **not** a weak link: at −79.06 dB over all
frames it is the *strongest* of the d0wd's three beacons, ahead of B2
(−79.94) and B1 (−81.60), and it rejects an order of magnitude more of them.
`docs/DUAL_RX_2026-08-21.md` §6 asks whether B3/desk's 43.5 % reject rate is
"an SNR floor or something else". On this capture it is not an SNR floor.

### 3.2 Do the SFO estimates track the `noise_floor`?

They do not, and that is the expected answer given §2 — the `noise_floor`
never steps, so there is nothing to track. Stated as measured, per-60 s-bin
correlations over 387 bins per cell:

| node | b | r(SFO, `noise_floor`) | r(SFO, `resid_std`) | sd(`noise_floor`) |
|---|---|---|---|---|
| d0wd | B1 | — (`noise_floor` constant) | **+0.813** | 0.0000 |
| d0wd | B2 | — | **+0.628** | 0.0000 |
| d0wd | B3 | — | **+0.757** | 0.0000 |
| s3 | B1 | +0.309 | **+0.820** | 0.2410 |
| s3 | B2 | +0.419 | **+0.816** | 0.2410 |
| s3 | B3 | −0.283 | **+0.844** | 0.2410 |

The three S3 correlations against `noise_floor` **do not agree in sign**
(+0.31, +0.42, −0.28) for a quantity that is common to all three beacons by
construction, so they describe no coherent relationship — they are what you
get correlating three noisy series against a fourth that is 87 % constant.

The residual relationship, by contrast, reproduces at **+0.63 to +0.84 in all
six cells**, on both boards. `docs/S3_SFO_STEPS.md` §7.1 measured +0.94 to
+0.97 on the S3 and only +0.48 to +0.58 on the desk, and read the strong
version as an S3 property. On this capture the D0WD shows +0.63 to +0.81
while the S3's `noise_floor` is quiet and its own reject rates are under 1 %.
**The estimator-bias mechanism follows the link, not the board** — which is
what §7.2 of that document argued from the gate sweep, now seen from the
other direction.

### 3.3 Stationarity — nothing steps, on either node

30-minute block medians, the full night:

```
t (h)   B1/d0wd   B2/d0wd   B3/d0wd    B1/s3     B2/s3     B3/s3
 0.0   +0.02262  +0.02716  +0.06163  +0.01366  +0.01028  +0.01565
 0.5   +0.02429  +0.02804  +0.07160  +0.01252  +0.00933  +0.01670
 1.0   +0.02421  +0.02818  +0.06835  +0.01239  +0.00870  +0.01715
 1.5   +0.02457  +0.02721  +0.06950  +0.01403  +0.00917  +0.01813
 2.0   +0.02067  +0.02668  +0.07111  +0.01480  +0.00979  +0.01541
 2.5   +0.02235  +0.02666  +0.07305  +0.01578  +0.00883  +0.01480
 3.0   +0.02274  +0.02699  +0.07420  +0.01534  +0.00868  +0.01406
 3.5   +0.02178  +0.02624  +0.08070  +0.01382  +0.00946  +0.01365
 4.0   +0.02204  +0.02664  +0.07501  +0.01406  +0.00990  +0.01423
 4.5   +0.01688  +0.02649  +0.07538  +0.01402  +0.00940  +0.01372
 5.0   +0.02267  +0.02596  +0.07530  +0.01349  +0.01026  +0.01422
 5.5   +0.02339  +0.02564  +0.07360  +0.01440  +0.01074  +0.01375
 6.0   +0.02460  +0.02619  +0.06860  +0.01384  +0.01094  +0.01416
```

Against the project's yardsticks `BETWEEN_UNIT_SD = 0.00237`
(`pc/exp_thermal_evidence.py:129`) and twin ΔSFO `0.00080`
(`pc/exp_lot_hypothesis.py:85-86`):

| node | b | 1st half | 2nd half | Δ | Δ 95 % CI | max adjacent block step | × SD |
|---|---|---|---|---|---|---|---|
| d0wd | B1 | +0.02335 | +0.02202 | −0.00133 | [−0.00144, −0.00121] | 0.00579 | 2.44 |
| d0wd | B2 | +0.02730 | +0.02626 | −0.00104 | [−0.00109, −0.00098] | 0.00097 | 0.41 |
| d0wd | B3 | +0.07096 | +0.07449 | +0.00353 | [+0.00321, +0.00384] | 0.00997 | 4.21 |
| s3 | B1 | +0.01374 | +0.01406 | +0.00032 | [+0.00027, +0.00036] | 0.00164 | 0.69 |
| s3 | B2 | +0.00924 | +0.00997 | +0.00073 | [+0.00067, +0.00079] | 0.00096 | 0.41 |
| s3 | B3 | +0.01601 | +0.01388 | −0.00213 | [−0.00218, −0.00208] | 0.00272 | 1.15 |

(2,000 bootstrap resamples of the window list, `np.random.default_rng(0)`.)

**No cell steps.** The largest movement between adjacent 30-minute blocks
anywhere in the night is 0.00997 rad/sc, on B3/d0wd — the 58.8 %-reject cell
— against the factor-of-6.7 step inside two 120 s bins that
`docs/DUAL_RX_2026-08-21.md` §3.3 reported. Every S3 cell holds to within
1.2 × `BETWEEN_UNIT_SD` all night.

The split-half CIs exclude zero in all six cells, and that should not be read
as instability: with 12,769 to 22,570 windows per cell the CI on a median is
narrow enough to resolve drifts of 0.0003 rad/sc, which is below the twin
yardstick. The honest summary is **slow drift of order 0.001–0.004 rad/sc
over 6.5 h, no steps**, and the two largest drifts are on the d0wd.

### 3.4 What this does not settle

The three per-beacon inter-receiver differences are again not one constant —
d0wd − s3 is +0.00885, +0.01723, +0.05729 for B1, B2, B3 — but **B3's is
dominated by the 58.8 %-reject cell**, so this capture adds nothing to
`docs/DUAL_RX_2026-08-21.md` §3.4 beyond not contradicting it. The
constant-offset hypothesis was already refuted there; nothing here rehabilitates
it and nothing here establishes the alternative. **The receiver-versus-position
confound is untouched** — the operator states the nodes were deliberately not
swapped, so this session cannot separate them, and `docs/DUAL_RX_2026-08-21.md`
§6's "swap the two nodes and repeat" remains the outstanding experiment.

---

## 4. Run integrity

### 4.1 Rates, gaps and stalls

| | d0wd | s3 |
|---|---|---|
| delivered rows | 2,983,560 | 3,564,005 |
| delivered rate | **128.23 fps** | **153.18 fps** |
| seconds with zero frames | **0 of 23,268** | **0 of 23,268** |
| largest `pc_time_us` batch gap | 0.4153 s (t = 16,321 s) | 0.2275 s (t = 23,226 s) |
| largest `esp_timestamp_us` gap | 0.4232 s (t = 16,321 s) | 0.2590 s (t = 11,705 s) |
| `esp_timestamp_us` u32 wraps | 5 | 5 |
| unwrapped node-side span | 23,268.077 s | 23,267.639 s |
| host-side span | 23,267.365 s | 23,267.252 s |

**No gap, no stall, no reboot on either node.** Not one second of the 23,268
is empty on either receiver. All five negative `esp_timestamp_us` steps per
node are clean u32 wraps — d0wd `4294957378 → 8749`, `4294964486 → 16976`,
`4294966761 → 13399`, `4294965850 → 6720`, `4294959167 → 1960`; s3
`4294957860 → 272`, `4294963099 → 2304`, `4294964965 → 5966`,
`4294961873 → 7630`, `4294960527 → 3449` — spaced 4294.9 s apart, against 5.4
expected for the span. The largest interruption anywhere is 0.4232 s on the
d0wd at t = 16,321 s, and both nodes' next nine largest gaps sit between
0.215 and 0.33 s, so nothing in either file is more than a fraction of a
second of missing wall-clock.

Node clock against host clock: the d0wd's unwrapped `esp_timestamp_us` runs
**+0.712 s over 6.5 h (+30.6 ppm)** relative to `pc_time_us` and the S3's
**+0.387 s (+16.6 ppm)**. Both are ordinary crystal offsets and neither
accumulates in steps.

### 4.2 Real drop rates — and the correction that matters is not the same one on both nodes

`dropped` is a `uint16_t` (`firmware/csi_rx/main/main.c:85`) counting failed
`xQueueSend` into a 64-deep queue (`:46`, `:131-133`).

| | d0wd | s3 |
|---|---|---|
| queue drops, wrap-safe, corrupt rows removed | **17,366** | **624,291** |
| endpoint cross-check `last − first + 65536×wraps` | 17,366 ✓ | 624,291 ✓ |
| u16 counter wraps in the session | **0** | **9** |
| **loss = drops / (delivered + drops)** | **0.579 %** | **14.906 %** |
| what `field_diag.py:106` / `diagnose.py:540` would report | 17,366 (correct — no wrap) | **34,467** |
| error of the shipped one-wrap estimator | none | **understates by 18.11×** |
| naive wrap-safe accumulation with no corrupt-row screen | **8,930,262 — overstates by 514×** | 624,291 (nothing to screen) |

Both figures were re-derived by an independent `awk` implementation that
shares no code with the script:

```
awk -F, 'NR>1{d=$NF; if(NR==2){first=d;prev=d;next}
              delta=d-prev; if(delta<0){neg++; delta+=65536}
              tot+=delta; prev=d}
         END{print "first="first" last="prev" neg="neg" total="tot}' \
    data/raw/s3_20260822_023034.csv
```

returns `first=0 last=34467 neg=9 total=624291` for the S3 — **identical**,
and `last - first = 34,467` is exactly the shipped one-wrap figure, so the
18.11× is arithmetic, not estimation. The same `awk` on the d0wd returns
`neg=136 total=8,930,262`, and re-running it with the field-plausibility
screen in front leaves `screened_out=141, wraps=1, drops=82,902` — from which
subtracting the one remaining false wrap gives **82,902 − 65,536 = 17,366**,
the script's figure to the unit. The same screened `awk` on the S3 returns
`screened_out=0, wraps=9, drops=624,291`.

**The two nodes fail in opposite directions, and each needs a correction the
other does not.**

- On the **S3** the counter genuinely wrapped nine times and there are **zero
  corrupt rows in 3,564,005** — both screens return empty, as they did on
  2026-08-21. Wrap-safety is everything; corrupt-row screening has nothing to
  do.
- On the **d0wd** the counter never wrapped, so the shipped estimator is
  accidentally right — but **136 negative deltas** appear anyway, all of them
  corrupt rows, and treating them as wraps inflates the total 514×. This is
  `docs/DUAL_RX_2026-08-21.md` §2.1 correction 2, five times larger than the
  101× it saw there.

**One corrupt row is invisible to the field screen and only the median filter
catches it.** At line 95,349 of the d0wd file:

```
line 95347   dropped 9743   mac a4:f0:0f:77:91:20  rssi -82  nf -97  ch 6  len 256
line 95348   dropped 9743   mac a4:f0:0f:77:91:20  rssi -81  nf -97  ch 6  len 256
line 95349   dropped   15   mac f4:2d:c9:70:72:30  rssi -79  nf -97  ch 6  len 256   <-- corrupt
line 95350   dropped 9743   mac f4:2d:c9:70:72:30  rssi -78  nf -97  ch 6  len 256
line 95351   dropped 9743   mac f4:2d:c9:70:72:30  rssi -79  nf -97  ch 6  len 256
```

Every other field on that row is plausible and the neighbours resume the true
trajectory immediately. That single row accounts for the entire 65,536
difference between 82,902 and 17,366. **Neither screen alone is sufficient;
this pass used both, and the field screen is what makes the census in §5
possible.**

Burstiness, per-second bins, 23,268 seconds:

| | d0wd | s3 |
|---|---|---|
| median drops/s | 0 | 27 |
| mean drops/s | 0.75 | 26.83 |
| p90 / p99 / max | 0 / 21 / 60 | 44 / 58 / 87 |
| seconds with zero drops | **21,794 (93.7 %)** | 1,183 (5.1 %) |
| share of all drops in the worst 10 % of seconds | **100.0 %** | 18.9 % |

The d0wd's loss is entirely confined to 6.3 % of the seconds — 100 % of its
drops fall in the worst 10 % — while the S3's 18.9 % is close to the 10 % a
uniform process would give. This is the same qualitative split as
`docs/DUAL_RX_2026-08-21.md` §2.3 (desk bursty, S3 near-continuous), now at
an order of magnitude lower absolute loss on the d0wd.

### 4.3 The delivered rate is falling on the d0wd, and offered load on both

Per 30-minute block:

```
t (h)          0.0   0.5   1.0   1.5   2.0   2.5   3.0   3.5   4.0   4.5   5.0   5.5   6.0
d0wd kept    140.2 132.0 139.1 133.6 130.1 128.3 128.5 123.8 126.8 120.7 124.4 117.5 121.5
d0wd offered 146.0 132.4 141.6 134.1 130.5 128.3 128.6 123.8 126.8 120.7 124.4 117.5 121.6
s3   kept    151.8 153.6 153.5 153.3 153.5 153.7 153.5 153.4 153.5 153.5 153.4 153.4 151.1
s3   offered 187.8 184.3 185.7 183.1 179.9 180.9 181.4 179.1 180.1 175.8 178.8 172.4 170.0
```

**The S3's 154 fps ceiling from `docs/DUAL_RX_2026-08-21.md` §2.5 reproduces
exactly** — 153.2 to 153.7 fps in every full block of a 6.5 h run while its
drop rate moves by a factor of 1.9. Its *delivered* rate cannot show a change
in what it hears; its *offered* rate can, and that falls 187.8 → 170.0 fps
(−9.5 %).

The d0wd is not against a ceiling and its delivered rate falls 140.2 → 121.5
fps, on all three beacons in proportion (B1 42.4 → 34.6, B2 43.1 → 38.1,
B3 54.6 → 48.8 fps). **Both receivers detect fewer frames as the night goes
on**, which points at the transmitters or the channel rather than at either
receiver — but nothing here identifies which, and §7 says why this file
cannot even measure the transmit cadence to check.

---

## 5. The MAC census, screened for ghosts

### 5.1 The raw counts, confirmed

```
awk -F, 'NR>1{m[$4]++} END{print length(m)}' data/raw/d0wd_20260822_023034.csv   ->  131
awk -F, 'NR>1{m[$4]++} END{print length(m)}' data/raw/s3_20260822_023034.csv     ->   34
```

**131 and 34**, matching the live console exactly, and matching the script.
The union across both nodes is **137** distinct MACs; only **28** appear on
both.

### 5.2 The criteria, stated before the answer

Applied in order, first match wins. `report`, TABLE 5c.

**X — decode artefact.** Any one of:
- ≥ 50 % of the MAC's rows carry an out-of-range value in a field that has
  nothing to do with the MAC (`node_id`, `env_id`, `channel`, `csi_len`,
  `noise_floor`, `rssi`); or
- a dominant `csi_len` outside {128, 256, 384}, the three lengths
  `pc/rff/protocol.py:31` admits; or
- ≤ 4 frames total **and** within 2 octets of a MAC at least 20× more common.

**R — sustained.** ≥ 1000 frames on at least one node, under 1 % of its rows
flagged, and active in ≥ 20 of the 78 five-minute bins.

**P — intermittent but corroborated.** ≥ 5 frames, under 1 % flagged, and
seen **on both receivers inside at least one common five-minute bin**.

**S — unresolved.** Fields all clean, no near-miss, but too little traffic to
place. Reported as unknown, not as a device.

The load-bearing criterion is the cross-receiver one. Two boards inches apart
run independent decoders over independent serial links; a bit error that
invents a MAC on one cannot invent the same MAC on the other inside the same
five minutes. TABLE 5b gives the Jaccard overlap of active 300 s bins for
every MAC seen on both:

```
mac                    d0wd n      s3 n  binsA binsB  both either      J
f4:2d:c9:70:72:30   1,178,726 1,449,060    78    78     78     78  1.000
a4:f0:0f:77:91:20     882,769 1,282,394    78    78     78     78  1.000
28:05:a5:2f:fa:48     919,632   830,010    78    78     78     78  1.000
1c:ce:51:f3:0d:fa         972       954    78    78     78     78  1.000
ba:80:d5:0c:18:87         276       971    27    29     27     29  0.931
bc:96:e5:af:e5:7a         315       196    19    19     19     19  1.000
1e:ce:51:f3:0d:fa         165       154     4     4      4      4  1.000
62:45:b4:f0:e1:97          21        21    21    21     19     23  0.826
54:6c:eb:15:e3:f7          28        43    24    31     18     37  0.486
64:fa:2b:6d:05:3b          30        89    19    44     14     49  0.286
```

### 5.3 The result

| class | MACs | frames | on d0wd | on s3 |
|---|---|---|---|---|
| **R** sustained | **3** | 6,542,591 | 3 | 3 |
| **P** intermittent, corroborated | **17** | 4,816 | 17 | 17 |
| **S** unresolved | 17 | 46 | 11 | 14 |
| **X** decode artefact | **100** | 112 | 100 | **0** |

The columns reconcile with the raw census exactly: d0wd 3 + 17 + 11 + 100 =
**131**, s3 3 + 17 + 14 + 0 = **34**. **Not one MAC in the S3 file is
classified as an artefact.**

R is exactly the three beacons. The 17 in P, with the locally-administered
bit of the first octet marked:

```
1c:ce:51:f3:0d:fa  OUI  d0wd=972  s3=954        f4:69:42:f2:d2:af  OUI  d0wd=64  s3=3
ba:80:d5:0c:18:87  LAA  d0wd=276  s3=971        62:45:b4:f0:e1:97  LAA  d0wd=21  s3=21
bc:96:e5:af:e5:7a  OUI  d0wd=315  s3=196        28:f5:2b:4f:7c:6b  OUI  d0wd=12  s3=9
1e:ce:51:f3:0d:fa  LAA  d0wd=165  s3=154        a6:11:ed:a5:b5:75  LAA  d0wd=1   s3=17
76:eb:b0:c0:68:4d  LAA  d0wd=220  s3=32         a8:6d:aa:55:0d:1b  OUI  d0wd=8   s3=6
9a:9a:4a:6a:74:f1  LAA  d0wd=168  s3=1          6e:0a:30:1f:ed:21  LAA  d0wd=6   s3=7
64:fa:2b:6d:05:3b  OUI  d0wd=30   s3=89         fe:8f:93:36:1a:b1  LAA  d0wd=12  s3=1
54:6c:eb:15:e3:f7  OUI  d0wd=28   s3=43         a8:b1:3b:00:b3:14  OUI  d0wd=6   s3=3
                                                10:38:1f:da:79:31  OUI  d0wd=3   s3=2
```

**The defensible count is 20 MAC addresses carrying real over-the-air
traffic — 3 beacons and 17 ambient — against a raw census of 131 and 34.**

Four of the 17 have an independent, pre-existing corroboration this pass did
not create: `data/fingerprints/` holds templates built on 2026-07-13 from 44
source sessions for `1c:ce:51:f3:0d:fa` (420 frames), `1e:ce:51:f3:0d:fa`
(6,581), `62:45:b4:f0:e1:97` (31) and `f4:69:42:f2:d2:af` (129). All four are
in P tonight. Nothing in this pass fed those files, and they are five weeks
older than this capture.

That is a count of *addresses*, not of *devices*, and the gap is not small.
Eight of the 17 have the locally-administered bit set, i.e. they are
randomised addresses, and one physical device rotates through several of them
over six hours. `1e:ce:51:f3:0d:fa` is `1c:ce:51:f3:0d:fa` with exactly that
bit flipped and nothing else changed, which is what a randomised address
derived from a hardware address looks like — and also, precisely, what a
one-bit corruption looks like. What separates them here is that the pair
appears on **both** receivers in the **same four five-minute bins** (J =
1.000) out of 78, which a per-receiver bit error cannot do, and that `1e`'s
165 and 154 frames are clustered into 4 bins rather than spread in proportion
to `1c`'s traffic. The 2026-07-13 fingerprint files settle it further: `1e`
has **6,581** stored frames against `1c`'s **420**, so historically the
supposed corruption is 15× more common than the address it would be a
corruption of, which is the wrong way round. Similarly `62:45:b4:f0:e1:97`,
`62:45:ba:3a:3c:61` and `62:45:b8:7d:71:26` share a prefix and are all
locally administered.

So: **20 addresses with traffic; somewhere between 13 and 20 physical
devices** — 3 beacons plus 9 universally-administered ambient addresses,
plus the 8 randomised ones which could in principle be as few as one device.
This file cannot narrow that further. No OUI database was consulted, so no
vendor is named here and none should be inferred.

### 5.4 The specific MACs the brief asked about

- **`f4:2d:c9:70:d9:10`** — 1 frame, d0wd only, class **X**, 2 octets from
  B3. Line 1,133,991 verbatim: `rssi = -45`, **`noise_floor = 19`**,
  **`channel = 211`**. Three impossible fields on one row.
- **`f4:2d:c9:70:07:d3`** — 1 frame, d0wd only, class **X**, 2 octets from
  B3. Line 1,422,946: **`rssi = -2`**, which is not a receivable level,
  `noise_floor = -52`, `channel = 7`.
- **`f4:2d:c9:70:72:00`** — 2 frames, d0wd only, class **X**, both rows
  flagged, 1 octet from B3. This is the same near-miss
  `docs/DUAL_RX_2026-08-21.md` §2.1 named.
- **`28:05:a5:2f:00:00`** — 1 frame, d0wd only, class **X**, 2 octets from
  B2, also as named there. Line 1,719,695 reads `rssi = 0, noise_floor = 0,
  channel = 0` and 256 zero CSI values — the row is null, not a device.
- Five more of the same family appear tonight: `28:05:a5:00:00:00`,
  `28:05:00:00:00:00`, `a4:f0:0f:00:00:00`, `f4:00:00:00:00:00`,
  `a4:f0:0f:77:19:20` (1 octet from B1). All singletons, all flagged.

**The dominant artefact family is not near-misses at all.** Of the 100
X-class MACs, **23 are within 2 octets of a beacon** and **74 have all six
octets in the range an `int8` CSI sample can take** (TABLE 5c). The second
group looks like `e2:04:e1:05:e3:08`, `f1:1d:f2:1e:f2:1d`,
`0d:ee:0b:ec:0b:eb` — six bytes that are small signed values near 0 or near
0xff, i.e. **CSI sample bytes being read as a MAC** after
`pc/rff/protocol.py:153-180` resynced into the middle of a payload and the
one-byte XOR check passed by chance. Their companion fields give them away:
`rssi = 0`, `noise_floor = 30`, `channel = 244`, `csi_len = 0` or `241`. One,
`16:fd:15:2f:fa:48`, carries B2's last three octets with the first three
replaced by sample bytes — a resync landing exactly three bytes early.

**A rule that was wrong, and what caught it.** `f4:69:42:f2:d2:af` was
classified X in the first run of this analysis, on the strength of its
`csi_len = 384` alone. It is a real device: 64 frames on the d0wd and 3 on
the S3 tonight, spread over 37 of the 78 five-minute bins, and a fingerprint
template built five weeks ago from 44 sessions with 129 frames all at length
384 and an RSSI spread of 1.46 dB. `pc/rff/protocol.py:31` admits 384. **The
screen was wrong, not the data** — see §1. It is in P.

### 5.5 What is unknown here

- **The 17 class-S MACs.** 46 frames between them, fields all clean, no
  near-miss, but **1 to 6 frames each — under the five-frame floor the
  corroboration rule needs**. Eight of the seventeen appear on both nodes and
  seven of those eight share a five-minute bin, so some of them are probably
  real; the rule was written before the answer and is not being relaxed after
  seeing it. They are not claimed as devices and not dismissed as artefacts.
  A real phone that
  transmitted twice all night and a corrupt row that happened to land on a
  plausible MAC are indistinguishable at n = 2. One deserves a specific
  flag: **`f9:c9:f0:ca:91:20`** ends in B1's last two octets and is 4 octets
  away otherwise, with clean fields and `rssi = -83`; the X rule did not
  catch it because 4 octets is not a near-miss, but it should not be counted
  as a device.
- **Whether any P-class MAC is a beacon under a different address.** Nothing
  was checked for this.
- **What any of the 17 ambient devices are.** No OUI lookup was performed
  and no traffic content is in these files.

---

## 6. Why the receivers disagree — 131 against 34

**Almost the entire gap is decode artefact, not sensitivity, and the residual
sensitivity difference runs the other way.**

| | d0wd | s3 |
|---|---|---|
| distinct MACs in the file | 131 | 34 |
| of those, class X | **100** | **0** |
| surviving the screen | **31** | **34** |
| corrupt rows | 142 of 2,983,560 = 4.8 × 10⁻⁵ | **0 of 3,564,005** |
| MACs seen exactly once | 102 | 5 |

After screening, the two receivers agree closely — **31 against 34** — and
the S3 sees three *more*, not 97 fewer. The 131 : 34 ratio in the raw census
is a statement about the two serial links, not about the two radios: **every
one of the 100 artefact MACs is on the d0wd and none is on the S3**, and the
S3's file contains no corrupt row of any kind. This is the same result
`docs/DUAL_RX_2026-08-21.md` §2.1 reached from three counts (34 corrupt rows
against 0, 42 MACs against 16, 25 singletons against 1), now on files five
times larger and with the artefact side of the S3's ledger at exactly zero.

The RSSI distributions settle whether the d0wd's extra MACs are weak
signals:

| | all frames | non-beacon frames | MACs unique to that node |
|---|---|---|---|
| **d0wd** | n = 2,983,560, mean **−80.07**, median −80, p1 −83, p95 −78, min −95, max **0** | n = 2,433, mean −56.69, median −39 | **103 MACs, 116 frames, mean rssi −13.59, median 0**, p5 −54 |
| **s3** | n = 3,564,005, mean **−68.34**, median −67, p1 −75, p95 −64, min −92, max −32 | n = 2,541, mean −55.88, median −68 | **6 MACs, 17 frames, mean rssi −83.47, median −84**, p5 −87 |

The 103 MACs that only the d0wd reports have a **median RSSI of 0 dBm**, and
a maximum of 0 dBm. That is not a weak signal; it is not a signal.

The check that makes this non-circular — the RSSI bound is itself one of the
six screen tests, so it cannot be used to justify the screen — is to drop the
RSSI test and keep the other five, then ask what the strongest surviving row
reads:

```
awk -F, 'NR>1{ nd=$(NF-2); ev=$(NF-1); ch=$7; ln=$9; nf=$6; rs=$5;
               if(!(nd==68 && ev==0 && ch==6 && (ln==128||ln==256)
                    && nf<=-70 && nf>=-110)) next;
               n++; if(mx==""||rs>mx) mx=rs }
         END{print "rows:", n, " max rssi:", mx}' \
    data/raw/d0wd_20260822_023034.csv
```

**`rows: 2,983,355  max rssi: -22`** — and the S3 by the same test reads
`-32`. Across 2.98 M structurally sound rows the d0wd never once reports
better than −22 dBm. An RSSI of 0 dBm is therefore 22 dB above anything this
receiver produces on a row whose other five fields are intact: it is a byte
from somewhere else in the payload, not a very close transmitter.
**The d0wd's extra MACs are artefact, not sensitivity** — the answer to the
question as asked.

The 6 MACs only the S3 reports are the opposite case: 17 frames at a mean of
−83.47 dBm, below the d0wd's own p1 of −83, i.e. exactly where a receiver
hearing 12 dB more would pick up devices the other cannot. The S3 hears the
whole population 11.7 dB stronger (mean −68.34 against −80.07), and every one
of the three beacons more strongly than the d0wd does (B1 +13.7, B2 +6.0,
B3 +13.5 dB).

**A caveat on comparing tonight's RSSI to yesterday's.** The operator states
the receivers were not moved and the beacons were not moved, yet the
per-beacon RSSI differs substantially from `docs/DUAL_RX_2026-08-21.md` §3.6:
B2/d0wd −71.11 → −79.94, B1/s3 −78.17 → −67.87, B3/s3 −70.50 → −65.60. The
positions being unchanged is a stated condition, not something these files
measure; an empty room at 03:00 and an occupied one at 13:00 are different
channels, and multipath is what `pc/rff/dsp.py:17-20` says it is. **Do not
read the between-session RSSI change as a receiver-state change** — this
capture cannot separate the two.

---

## 7. Turned up on the way, recorded so it is not rediscovered

**`seq` cannot be attributed to the MAC on the same row, and one shipped tool
does exactly that.** `firmware/csi_rx/main/main.c:84,101-103` keeps a single
node-global `s_latest_seq`, written by the ESP-NOW receive callback from
whichever beacon transmitted most recently, and `:122` copies it into every
CSI sample regardless of that sample's source. Directly visible in the file —
the first 59 rows of the d0wd capture carry `seq` values from three
interleaved counters (≈5,682,3xx, ≈5,686,2xx, ≈129,766,2xx) with **no
correspondence to the row's MAC**:

```
129766269 28:05:a5:2f:fa:48      5686258 f4:2d:c9:70:72:30      5682311 a4:f0:0f:77:91:20
  5686259 a4:f0:0f:77:91:20    129766271 28:05:a5:2f:fa:48      5686260 f4:2d:c9:70:72:30
```

Over the first 200,000 rows, all three beacon MACs carry the same full
`seq` range (min ≈ 5,682,311, max ≈ 129,908,5xx). `pc/diagnose.py:45-49` and
`:564-566` already state this correctly and refuse to compute per-beacon RF
loss. **`pc/field_diag.py:99-101` does not**: it selects the dominant MAC's
rows, differences their `seq`, and prints "`seq gaps: N missing beacon
frame(s)`". With three beacons on air that number is meaningless. The header
comment in `firmware/common/telemetry/include/telemetry.h:17-18` ("seq gaps
give the same for RF loss") is what invites the error.

This also closes off the obvious way to test §4.3: **per-beacon transmit
cadence is not recoverable from these files**, so whether the falling frame
rate is transmitter-side cannot be answered here.

---

## 8. Established / permitted / unknown

**Established by this capture.**

- The S3's `noise_floor` does not step in 6.5 h in an empty room. Modal −93
  in 86.89 % of 2,327 10 s bins; 129 excursions, median 10 s, longest 220 s,
  all reverting; interior peak-to-peak 1.0 dB (§2.2). The `Periodic`
  hypothesis as stated — a receiver-internal cycle on a tens-of-minutes
  timescale — is eliminated.
- The d0wd's `noise_floor` is `-97` on 99.9961 % of rows and on 100.000 % of
  clean rows, with zero transitions. It remains incapable of being a control
  (§2.1), reproducing `docs/S3_SFO_STEPS.md` §4 on a file 5× larger.
- No SFO cell steps on either node. Largest adjacent-30-minute-block movement
  anywhere is 0.00997 rad/sc, on the 58.8 %-reject cell; every S3 cell holds
  within 1.2 × `BETWEEN_UNIT_SD` all night (§3.3).
- Real loss: **d0wd 0.579 % (17,366 drops, 0 wraps), s3 14.906 % (624,291
  drops, 9 wraps)**, each confirmed by an independent `awk` implementation and
  by endpoint arithmetic (§4.2).
- The shipped one-wrap estimator understates the S3 by **18.11×**; naive
  wrap-safe accumulation without a corrupt-row screen overstates the d0wd by
  **514×**, and a *single* row (line 95,349) accounts for the whole error.
- Neither node stalled: 0 empty seconds of 23,268, largest gap 0.42 s, five
  clean u32 timestamp wraps each (§4.1).
- The S3's ~154 fps service ceiling reproduces over 6.5 h (§4.3).
- Of 137 distinct MACs across both files, **100 are decode artefacts and all
  100 are on the d0wd**; 31 of the d0wd's 131 and **34 of the S3's 34**
  survive screening; **20 addresses carry corroborated traffic**, four of
  them with fingerprint templates written five weeks earlier (§5.3).
- The S3 file contains **zero corrupt rows** by either screen, against 142
  on the d0wd (§4.2, §6).
- The d0wd's 103 unique MACs have a median RSSI of **0 dBm**, against a
  maximum of **−22 dBm** over 2.98 M structurally sound rows — artefact, not
  weak signal. The S3's 6 unique MACs sit at a mean of **−83.47 dBm** —
  genuine weak signal (§6).
- The SFO/`resid_std` relationship from `docs/S3_SFO_STEPS.md` §7 reproduces
  on **both** boards (+0.63 to +0.84 in six of six cells), including on the
  D0WD, which showed only +0.48 to +0.58 yesterday (§3.2).
- `seq` is node-global and cannot be attributed per source;
  `pc/field_diag.py:99-101` does so anyway (§7).

**Permitted but not established.**

- That yesterday's t = 930 s event was the operator moving in the room. This
  capture is consistent with it and provides no positive evidence for it
  (§0).
- That the charge controller is not involved. The charge LED was lit
  throughout by the operator's account, so the mechanism may simply have had
  no opportunity to act; absence of stimulus and absence of effect are not
  separated here (§0).
- That B3/d0wd's 58.8 % reject rate and yesterday's B3/s3 anomaly are the
  same phenomenon following the link. They share the residual signature and
  the magnitude, and it is now on the other board — but nothing measures the
  mechanism.
- That the falling frame rate on both nodes is transmitter-side. It is
  common to both receivers and to all three beacons, which is where a shared
  cause would show; the file carries no usable transmit cadence (§7).

**Unknown.**

- **What produced the 2026-08-21 event.** Still not identified. This capture
  narrows the class it can belong to and nothing more.
- **Whether the S3 event recurs on any timescale longer than 6.5 h.** One
  quiet night is one quiet night.
- **Why the S3's `noise_floor` sits ~2 dB higher tonight than yesterday**
  (§2.3), and therefore whether the null result transfers to yesterday's
  state.
- **Why B3/d0wd rejects 58.8 % of frames** while being the strongest of that
  node's three links. Not an SNR floor on this evidence (§3.1).
- **How many physical devices the 20 corroborated addresses represent.**
  Between 13 and 20; eight are randomised addresses (§5.3).
- **What the 17 class-S MACs are** (§5.5).
- **Whether tail-drop biases the surviving frames on the S3.** Untested here
  as in `docs/DUAL_RX_2026-08-21.md` §2.6; at 14.9 % loss it still matters.

---

## 9. What would settle the rest

| question | measurement |
|---|---|
| Does a person in the room reproduce the t = 930 s signature? | The positive control this session lacks: an otherwise identical capture in which the operator enters at a logged wall-clock time, walks the room, and leaves. One hour is enough. Without it, §0 stays a negative result. |
| Is the charge controller implicated at all? | Repeat with the S3 battery at ~50 % so the charger is actually cycling, and separately with the battery disconnected. The lit-LED condition made this session unable to test it. |
| Receiver hardware or receiver position? | Swap the two nodes' physical positions and repeat — still the outstanding experiment from `docs/DUAL_RX_2026-08-21.md` §6 and `docs/S3_SFO_STEPS.md` §11, and this session deliberately did not do it. B3/d0wd's 58.8 % reject rate makes it more valuable than it was: the anomalous cell has moved boards, so there is now something concrete for a swap to discriminate. |
| Why is B3/d0wd rejecting 58.8 % at the strongest RSSI on that node? | Stratify B3/d0wd's frames by `inlier_ratio` as `docs/S3_SFO_STEPS.md` §7.2 did for B3/s3 — the machinery is there and the cell is far larger (1.18 M frames). |
| Is the falling frame rate transmitter-side? | Give the beacon a per-transmitter sequence number the receiver preserves. `s_latest_seq` (`csi_rx/main/main.c:84`) would need to become a small per-MAC table; `tlm_send_csi`'s signature already carries `seq` per frame, so the CSV format does not change. |
| Does tail-drop bias survivors? | Emit queue occupancy in the STATUS frame — `tlm_status_t` (`telemetry.h:35-46`) has no slot for it — and test survivor SFO against occupancy. |
| Are the 17 unresolved MACs real? | Nothing offline can settle them. A longer capture, or a second night, would move the corroborated ones into P. |

---

## 10. Figures in this document that should not be quoted alone

- **B3/d0wd's +0.07195**, and any inter-receiver difference built on it.
  58.8 % of its frames are rejected at the quality gates and
  `docs/S3_SFO_STEPS.md` §7.2 establishes that in this regime the reported
  slope is a function of fit quality rather than of the link.
- **The split-half Δ confidence intervals in §3.3.** They exclude zero in all
  six cells because the window counts are enormous, not because anything is
  unstable. Quote the "no steps" conclusion with the max-adjacent-block
  column beside it.
- **"20 devices."** It is 20 *addresses*; eight are randomised (§5.3).
- **Any earlier draft's corrupt-row counts (206 / 3) or class counts
  (101 X, 19 addresses).** They came from a `csi_len` screen that excluded
  384; the corrected figures are 142 / 0 and 100 X, 20 addresses (§1).
- **Any between-session RSSI comparison** (§6, final paragraph).
- **The class-S count of 17.** It is an explicit unknown, not a device count,
  and not a bound on one either.

Not affected: the loss totals in §4.2 (three independent routes agree), the
row/rate/span census in §1 and §4.1, the `noise_floor` result in §2 (the
central claim is an absence, and it is measured on 3.56 M rows), the
artefact/real split in §5.3 and §6 (the cross-receiver criterion is
independent of the field-plausibility one and they agree), and §7 (read off
the firmware source and visible in the raw file).

Nothing in this document touches the occupancy pipeline (`pc/occ/`, amplitude
domain). Device-ID and occupancy figures must not be combined.
