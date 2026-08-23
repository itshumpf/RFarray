# OCCUPANCY TEST — the deliberate 2026-08-22 14:44:24 capture, 32.4 minutes,
# one departure and one return, both receivers

Follow-up to `docs/POSITIVE_CONTROL_0822.md`, which established that a person
entering an empty room produces a large, coherent, multi-series signature, and
asked for a repeat with a logged entry time and a longer tail. This is that
repeat, with one operator-reported timestamp and its uncertainty stated.

Read-only on `data/raw/`. Both CSVs were opened `"r"` through Python's `csv`
module and never written; nothing in `data/raw/` was modified, renamed or
deleted. `ls -l --time-style=full-iso` reports **210,066,333** and
**232,208,794** bytes, last modified **2026-08-22 15:16:49.496593900** and
**15:16:49.512218600 −0500**, unchanged before and after every pass
(the `run` command prints size and `mtime_ns` at entry and exit and asserts
equality; both printed `unchanged=True`). No serial port was opened, nothing
was flashed, nothing was staged, committed or pushed (`git status --porcelain`
lists no staged path; `git diff --cached --name-only` is empty).

**Files in the repo written by this pass:** this one, `pc/exp_occupancy_0822.py`,
and a short appended section in `docs/V2_SPEC.md`. Caches went to
`/tmp/occ0822_cache`, outside the repo tree.

B1 = `a4:f0:0f:77:91:20` (reference), B2 = `28:05:a5:2f:fa:48`,
B3 = `f4:2d:c9:70:72:30` (B1's characterised clock twin,
`docs/LOT_HYPOTHESIS.md`). d0wd = `node_id` 68 (ESP32-D0WD, UART bridge),
s3 = `node_id` 108 (Heltec ESP32-S3, native USB).

**Operator-stated conditions**, recorded as stated and not verified by these
files: he was seated at the desk from the start; he stood and left at a time he
did not record against the run clock; **he sat back down at approximately
t = 17:20 = 1040 s, his one firm timestamp, ±1 minute at best**; he remained at
the desk to the end. Receivers and beacons in the positions of the overnight
capture, nothing moved. The capture was intended to run 20 minutes and ran
32.4. Nothing in either file records any of this.

**Nothing in this document touches the occupancy pipeline (`pc/occ/`,
amplitude domain).** Everything below is the device-ID domain — `pc/rff/`
phase estimates and the raw `rssi` / `noise_floor` columns. Device-ID and
occupancy figures must not be combined (`CLAUDE.md`).

---

## 0. What this establishes, stated once

**The pre-registered test fails, and a different one succeeds.**

`docs/POSITIVE_CONTROL_0822.md` §2.1's detector — 24 series, 10 s bins,
6 × MAD departure from a pre-chosen baseline — found **23 of 24 series leaving
baseline at 08:55, 20 of them inside one 70 s band**. Run unchanged on this
capture it finds **9 of 24 series flagging anywhere at all, a maximum
concurrency of 3 of 24 in any bin, and 2 of 24 within ±30 s of the reported
arrival at t = 1040 s.** No coherent multi-series step occurs at 1040 s, or
anywhere else in the run. Said plainly: **a short absence from an
otherwise-occupied room does not reproduce the 08:55 signature, and on the
08:55 detector it is not detectable at all.** (The brief calls it a
four-minute absence; the data below makes it 135 s.)

What does detect it is **RSSI variability**, not RSSI level. The bin-to-bin
absolute change `|ΔRSSI|` of the 10 s mean, averaged over all six node×beacon
cells, collapses by **2.35× to 7.12×, in 6 of 6 cells**, over one contiguous
130 s interval and nowhere else in the run. That interval is
**t = [790, 920) s**, and its edges bound the two transitions:

| | data | wall clock |
|---|---|---|
| departure | **t = 785 ± 10 s** | 14:57:29 ± 10 s |
| return | **t = 920 ± 10 s** | 14:59:44 ± 10 s |
| room measurably still for | **135 ± 14 s** | 2 min 15 s |
| operator's reported sit-down | t = 1040 ± 60 s | 15:01:44 |

**The return edge sits 120 s before the reported sit-down — twice the
operator's own stated uncertainty.** The absence was 135 s, not four minutes.

The transitions are **not** undetectable in the phase pipeline; they are
undetectable *as level steps*. Measured at the departure edge with a
window-level bootstrap, SFO moves on **5 of 6 cells with 95 % CIs excluding
zero**, the largest being **d0wd/B3, +0.01836 rad/sc [+0.01621, +0.02199] =
7.75 × `BETWEEN_UNIT_SD`** — against 08:55's largest of −0.05410 = 22.83 ×.
**34 % of the 08:55 SFO effect**, and it moves with `resid_std` and reject rate
exactly as `docs/S3_SFO_STEPS.md` §7 says it must.

Three further results, none of them about occupancy:

- **The marginal cell has moved again, to a beacon that has never been
  marginal.** Reject rate: 08-21 B3/s3 43.5 %, overnight B3/d0wd 58.8 %, **this
  run B2/s3 83.1 %** — while B3/d0wd falls to 6.2 %. Three sessions, three
  different marginal cells (§9.1).
- **`docs/UNWRAP_DEFECT.md` §7's coherence detector is not measuring the branch
  defect here.** `C < 0.5` fires on **0.000–0.268 % of accepted frames and
  0.943–34.180 % of rejected frames** in 6 of 6 cells — it is very nearly
  redundant with the shipped `inlier_ratio >= 0.6` gate. Its highest rate,
  28.449 %, is on the **S3**, which `docs/V2_SPEC.md` §7(a)1 established has no
  dead subcarrier in 7 of 7 chunks (§8).
- **The S3's `noise_floor` produced a 310 s excursion at t = 990–1300 s**
  (+1.032 dB), longer than every one of the 129 excursions in the 6.5 h
  empty-room overnight (median 10 s, **maximum 220 s**), and it reverted. It
  begins 70 s after the return edge and 50 s before the reported sit-down.
  Nothing in the record says whether it is the receiver or the room (§7).

---

## 1. Pre-registration — written before either file was opened

The prediction below was written from `docs/POSITIVE_CONTROL_0822.md` alone,
before `pc/exp_occupancy_0822.py` was written and before any byte of
`data/raw/*_144424.csv` was read.

### 1.1 The 08:55 signature, as the source states it

`docs/POSITIVE_CONTROL_0822.md` §2.1, §2.2, §2.4, §2.5. The 08:55 arrival
(t = 23,067–23,137 s of `d0wd_20260822_023034.csv` /
`s3_20260822_023034.csv`) produced:

| quantity | d0wd B1 / B2 / B3 | s3 B1 / B2 / B3 |
|---|---|---|
| RSSI Δ, dB | **+0.28 / +0.43 / +1.68** | **−3.58 / −1.47 / −3.69** |
| SFO Δ, rad/sc | −0.00751 / +0.00383 / **−0.05410** | +0.00420 / +0.00945 / −0.00162 |
| … × `BETWEEN_UNIT_SD` | 3.17 / 1.61 / **22.83** | 1.77 / 3.99 / 0.68 |
| reject %, before → after | 14.5→16.2 / 4.3→7.2 / **57.2→22.5** | 0.6→7.1 / 0.9→9.3 / 0.3→0.7 |
| `resid_std` | .1612→.1559 / .1541→.1550 / .1583→.1442 | .1420→.1507 / .1411→.1506 / .1334→.1350 |

`noise_floor`: the d0wd cannot answer (−97 on 100.000 % of clean rows, zero
transitions); the S3 leaves its all-night modal −93 at t = 23,135.091 s and
does not return in the remaining 132.2 s, mean **+0.648 dB**. Frame rate: d0wd
offered +6 %, s3 offered −22 %, in opposite directions at the same instant.
Onset: a 70 s band across both nodes; **23 of 24 monitored series** leave a
pre-chosen baseline by > 6 × MAD and **20 of them inside that band**.

`BETWEEN_UNIT_SD = 0.00237` (`pc/exp_thermal_evidence.py:129`).

### 1.2 The prediction for t ≈ 1040 s

If the reported sit-down is the same class of event, then within roughly a 70 s
band around 1040 s:

- **P1** RSSI steps on all three beacons on both nodes, opposite sign per node,
  order 0.3–1.7 dB on the d0wd and 1.5–3.7 dB on the S3.
- **P2** SFO steps on all six cells with CIs excluding zero, the marginal cell
  moving by order 0.05 rad/sc ≈ 20 × `BETWEEN_UNIT_SD`.
- **P3** The marginal cell's reject rate collapses.
- **P4** The S3's `noise_floor` leaves its modal value and does not return; the
  d0wd's is silent by construction.
- **P5** ≥ 20 of 24 series flag beyond 6 × MAD inside a ~70 s band.
- **P6** Offered frame rate moves in opposite directions on the two nodes.

**Directional note, recorded in advance.** 08:55 was an *arrival*. A sit-down at
1040 s should carry the **same** signs if the mechanism is orientation-free;
the earlier *departure* should carry **mirrored** signs if arrival and
departure are reciprocal. `docs/POSITIVE_CONTROL_0822.md` §2.8 offers exactly
this as testable and does not assert it.

**Magnitude caveat, recorded in advance.** 08:55 followed 6.5 h of an empty
room. This is a short absence from an otherwise-occupied room. The perturbation
is smaller by construction, and a null result is a real finding about the
sensitivity limit and must not be dressed up.

### 1.3 The thresholds, and one amendment made before looking

Bin 10 s, threshold 6 × MAD, both from `docs/POSITIVE_CONTROL_0822.md` §2.1.

**Baseline A = [120, 720) s** — the run's own early occupied stretch, after
2 minutes of settling. My first choice was [120, 840); the brief's own
preliminary lead says d0wd/B3 drops across 780–960 s, which would put part of
the suspected *departure* inside the *arrival's* baseline. The amendment was
made before the files were opened and is recorded rather than hidden. Neither
window contains t = 1040 s. **Baseline B** = whole-run median/MAD, reported
alongside where it matters.

A second threshold was pre-registered because 6 × MAD on a 10 s series is tight
enough to fire on ordinary drift: the per-series flag *rate away from the
transitions* is reported alongside every flag, since
`docs/POSITIVE_CONTROL_0822.md` §2.1's force came from 20 of 23 series flagging
inside **one** band, not from any single flag.

---

## 2. Method

One script, `pc/exp_occupancy_0822.py`, from the repo root:

```
D=data/raw/d0wd_20260822_144424.csv
S=data/raw/s3_20260822_144424.csv
python3 pc/exp_occupancy_0822.py run $D --tag d0wd
python3 pc/exp_occupancy_0822.py run $S --tag s3
python3 pc/exp_occupancy_0822.py report --tags d0wd,s3
```

Every number below is from `report` unless it names another command. `report`
is deterministic: three runs under `PYTHONHASHSEED=1,2,3` give byte-identical
output, `md5sum` **`51e014ff0cfde39805fc4d6474f55c46`**. Every bootstrap uses
`np.random.default_rng(0)` and 4,000 resamples. `FrameEstimator` carries a
single advancing RNG (`dsp.py:118` used at `dsp.py:132`), so per-frame results
depend on stream position; the `run` pass is a single ordered pass over each
file, with no `part`/`merge` split, so there is no seam to check.

**Phase work** is `pc/rff/dsp.py`'s `FrameEstimator(rng_seed=0)` with the
shipped gates `inlier_ratio >= 0.6` (`dsp.py:164,173`) and `resid_std <= 0.8`
(`dsp.py:164,175`), and `WindowAggregator(window=64)` (`dsp.py:164`).
`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` were
**not** used: `docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 establishes all three have
the DC/guard-band index wrong, and `pc/test_rff_synth.py` test 7 shows
`phase_skew` returns the opposite sign.

**The CSI field is read with a real CSV reader.** `csi_data` is a quoted
comma-separated list nested inside the CSV (`pc/capture.py:129-132`), and the
row-length histogram is reported by `len(row)`:

| | d0wd | s3 |
|---|---|---|
| `csv.reader`, `len(row)` | **13 on 242,733 of 242,733** | **13 on 280,621 of 280,621** |
| naive `line.split(",")` | 140 × 124, 268 × 242,609 | 140 × 133, 268 × 280,488 |
| rows a naive split mis-parses | **242,733 of 242,733** | **280,621 of 280,621** |

The vector guard is `if vals.size < 128`, **not** `< 129` — the off-by-one at
`pc/exp_overnight_0822.py:303-304` and `pc/exp_s3_sfo_steps.py:153-155,590-592`
that `docs/POSITIVE_CONTROL_0822.md` §1.2 identifies. Row counts match
`wc -l` minus the header exactly on both files.

**Corrupt rows** are screened by the two independent routes of
`docs/OVERNIGHT_2026-08-22.md` §1, reused unchanged: route 1 is a width-9
median filter on `dropped` with tolerance 100; route 2 is field plausibility on
`node_id` against the file's own mode, `env_id == 0`, `channel` against the
file's own mode, `csi_len ∈ {128, 256, 384}`, `noise_floor ∈ [−110, −70]`,
`rssi ∈ [−100, −10]`.

### 2.1 The two files

| | d0wd | s3 |
|---|---|---|
| bytes | 210,066,333 | 232,208,794 |
| data rows (`wc -l` − 1, and by `len(row)`) | **242,733** | **280,621** |
| `pc_time_us` span | 1,944.681 s | 1,944.772 s |
| first row, local (UTC−5) | **14:44:24** | **14:44:24** |
| last row, local | **15:16:49** | **15:16:49** |
| `node_id`, mode | 68 | 108 |
| `channel`, mode | 6 | 6 |
| `csi_len` histogram | {128: 124, 256: 242,609} | {128: 133, 256: 280,488} |
| corrupt rows: route 1 / route 2 / both / union | 14 / 15 / 14 / **15** | 0 / 0 / 0 / **0** |
| distinct MACs | 27 | 15 |
| queue drops, wrap-safe | 2,065 (1.062 /s) | 10,498 (5.398 /s) |
| `dropped` u16 wraps | 0 | 0 |
| `esp_timestamp_us` negative steps / u32 wraps / true backward | 1 / 1 / **0** | 0 / 0 / **0** |
| node clock span vs host span | 1,944.818 vs 1,944.681 s | 1,944.890 vs 1,944.772 s |

The two `t0` stamps differ by **−0.074852 s**; both readers ran in one
`pc/capture.py` process, so `pc_time_us` is a shared host clock. The file's own
first stamp puts t = 0 at **14:44:24**, matching the filename, and its last row
at **15:16:49**, matching the `ls` mtime to under a second — an independent
check that `t` is the run clock the operator's 17:20 refers to.

`pc_time_us` is a per-serial-drain-batch host stamp (`pc/node_census.py:30-35`,
`docs/HANDOFF.md` trap #1). It is used here only to place bins and to measure
host-side delivered rate, never as per-frame cadence.

### 2.2 The corrupt rows, verified independently of the script

Straight down field 6 with `awk`, on the raw file:

```
awk -F, 'NR>1{h[$6]++; if($6!=p && NR>2) tr++; p=$6}
  END{for(x in h) printf "  nf %s x%d\n",x,h[x]
      printf "  row-to-row transitions: %d\n", tr+0}' \
  data/raw/d0wd_20260822_144424.csv
```

> `nf -97 x242721` · `nf 0 x3` · `nf -8 x1` · `nf 40 x1` · `nf -28 x1` ·
> `nf 3 x1` · `nf 6 x1` · `nf -36 x1` · `nf 29 x1` · `nf -33 x1` ·
> `nf 36 x1` · `row-to-row transitions: 24`

Twelve rows carry a `noise_floor` that is not dBm at all — the UART corrupt-row
family `docs/S3_SFO_STEPS.md` §4 and `docs/OVERNIGHT_2026-08-22.md` §5.4
already characterise. The screen removes 15 rows; on the remaining **242,718
clean rows `noise_floor` reads −97 with zero transitions** (§7).

### 2.3 Per-cell frame accounting

| node | b | fed | fitted | accepted | reject % | 64-frame windows |
|---|---|---|---|---|---|---|
| d0wd | B1 | 63,449 | 63,446 | 58,274 | 8.156 | 910 |
| d0wd | B2 | 79,021 | 79,019 | 69,958 | 11.469 | 1,093 |
| d0wd | B3 | 100,124 | 100,120 | 93,877 | 6.239 | 1,466 |
| s3 | B1 | 85,191 | 85,191 | 84,343 | 0.995 | 1,317 |
| s3 | B2 | 55,126 | 55,124 | **9,316** | **83.101** | **145** |
| s3 | B3 | 140,168 | 140,168 | 139,747 | 0.300 | 2,183 |

---

## 3. The 24 monitored series, on the pre-registered test

`report` R1. Baseline A = [120, 720) s, 10 s bins, 6 × MAD. 195 bins per
series.

| series | baseline | MAD | flagged bins | first | flag rate |
|---|---|---|---|---|---|
| d0wd B1 rssi | −81.8453 | 0.85252 | **0 / 195** | — | 0.0 % |
| d0wd B1 resid_std | +0.1550 | 0.00446 | **0 / 195** | — | 0.0 % |
| d0wd B1 SFO | +0.0137 | 0.00362 | **0 / 195** | — | 0.0 % |
| d0wd B1 accfrac | +0.9525 | 0.01804 | 25 / 195 | 570 | 12.8 % |
| d0wd B2 rssi | −79.7219 | 0.95328 | **0 / 195** | — | 0.0 % |
| d0wd B2 resid_std | +0.1535 | 0.00373 | **0 / 195** | — | 0.0 % |
| d0wd B2 SFO | +0.0261 | 0.00488 | 1 / 195 | 1460 | 0.5 % |
| d0wd B2 accfrac | +0.9542 | 0.01826 | 53 / 195 | 330 | 27.2 % |
| d0wd B3 rssi | −78.4754 | 1.83373 | **0 / 195** | — | 0.0 % |
| d0wd B3 resid_std | +0.1446 | 0.00531 | **0 / 195** | — | 0.0 % |
| d0wd B3 SFO | +0.0172 | 0.00526 | 1 / 195 | 40 | 0.5 % |
| d0wd B3 accfrac | +0.9588 | 0.01875 | 29 / 195 | 10 | 14.9 % |
| s3 B1 rssi | −77.1220 | 1.01353 | **0 / 195** | — | 0.0 % |
| s3 B1 resid_std | +0.1428 | 0.00402 | **0 / 195** | — | 0.0 % |
| s3 B1 SFO | +0.0102 | 0.00197 | 2 / 195 | 830 | 1.0 % |
| s3 B1 accfrac | +0.9898 | 0.00464 | 2 / 195 | 940 | 1.0 % |
| s3 B2 rssi | −79.6917 | 0.78230 | **0 / 195** | — | 0.0 % |
| s3 B2 resid_std | +0.1551 | 0.00502 | **0 / 173** | — | 0.0 % |
| s3 B2 SFO | +0.0504 | 0.03071 | **0 / 173** | — | 0.0 % |
| s3 B2 accfrac | +0.2654 | 0.22927 | **0 / 195** | — | 0.0 % |
| s3 B3 rssi | −67.3501 | 1.02197 | **0 / 195** | — | 0.0 % |
| s3 B3 resid_std | +0.1388 | 0.01130 | **0 / 195** | — | 0.0 % |
| s3 B3 SFO | +0.0119 | 0.00349 | 2 / 195 | 410 | 1.0 % |
| s3 B3 accfrac | +0.9987 | 0.00131 | 12 / 195 | 390 | 6.2 % |

**Not one of the six RSSI series and not one of the six `resid_std` series
leaves its baseline anywhere in the run.** Four of six SFO series flag once or
twice; five of six `accepted fraction` series flag. **Nine of 24 series flag at
all**, against 23 of 24 at 08:55.

### 3.1 Every excursion, with its timestamp

`report` R2. Contiguous runs of ≥ 2 flagged bins, all 24 series, whole run:

| t (s) | bins | series |
|---|---|---|
| 10 – 30 | 2 | d0wd B3 accfrac |
| 40 – 60 | 2 | d0wd B3 accfrac |
| 90 – 110 | 2 | d0wd B3 accfrac |
| 350 – 410 | 6 | d0wd B3 accfrac |
| 410 – 430 | 2 | s3 B3 accfrac |
| 450 – 520 | 7 | d0wd B3 accfrac |
| 570 – 670 | 10 | d0wd B1 accfrac |
| 650 – 670 | 2 | d0wd B2 accfrac |
| 710 – 740 | 3 | d0wd B2 accfrac |
| 710 – 750 | 4 | d0wd B1 accfrac |
| 760 – 780 | 2 | d0wd B1 accfrac |
| **900 – 970** | 7 | d0wd B3 accfrac |
| 960 – 980 | 2 | s3 B3 accfrac |
| **1010 – 1030** | 2 | s3 B3 accfrac |
| 1120 – 1140 | 2 | d0wd B2 accfrac |
| 1230 – 1260 | 3 | d0wd B1 accfrac |
| 1390 – 1530 | 14 | d0wd B2 accfrac |
| 1560 – 1580 | 2 | d0wd B2 accfrac |
| 1640 – 1690 | 5 | d0wd B2 accfrac |
| 1710 – 1830 | 12 | d0wd B2 accfrac |
| 1870 – 1910 | 4 | d0wd B1 accfrac |
| 1920 – 1940 | 2 | d0wd B2 accfrac |

**22 excursions, and every one of them is in `accepted fraction`.** They are
distributed across the whole run — seven of them after t = 1200 s, when the
operator states he was seated and still. They are not transitions; they are
what that quantity does on this hardware.

Concurrency — how many of the 24 series are simultaneously flagged:

| | value |
|---|---|
| bins with ≥ 6 of 24 flagged | **none** |
| maximum concurrency anywhere | **3 / 24, at t = 830 s** (inside the still interval) |
| peak within ±30 s of t = 1040 | **2 / 24** |
| peak within ±30 s of the departure edge | **1 / 24** |
| peak within ±30 s of the return edge | **2 / 24** |
| the same statistic at 08:55 | **23 / 24, 20 inside one 70 s band** |

**P5 fails.** Nothing in this capture approaches the concurrency 08:55
produced.

---

## 4. The reported arrival at t = 1040 s

### 4.1 The test as the brief asked for it, and why its windows are wrong

`report` R4. Boundary t = 1040 s, before = [740, 1040), after = [1040, 1340),
in `docs/POSITIVE_CONTROL_0822.md` §2.4/§2.5 units:

| node | b | rssi before | rssi after | Δ dB | Δ SFO | × SD | CI excl. 0 | reject % |
|---|---|---|---|---|---|---|---|---|
| d0wd | B1 | −82.48 | −82.56 | −0.09 | −0.00224 | 0.94 | yes | 7.66 → 6.20 |
| d0wd | B2 | −79.31 | −80.38 | −1.07 | +0.01508 | 6.36 | yes | 3.81 → 9.70 |
| d0wd | B3 | −81.62 | −75.78 | **+5.85** | −0.00930 | 3.92 | yes | 12.29 → 1.97 |
| s3 | B1 | −77.26 | −76.38 | +0.88 | −0.00560 | 2.36 | yes | 1.45 → 0.64 |
| s3 | B2 | −79.63 | −79.47 | +0.15 | +0.01309 | 5.52 | yes | 93.21 → 87.51 |
| s3 | B3 | −68.43 | −66.77 | +1.66 | −0.01453 | 6.13 | yes | 0.65 → 0.20 |

**These numbers must not be quoted as the sit-down.** The "before" window
[740, 1040) contains the entire 130 s still interval located in §5. The table
measures the absence, not the arrival — the same error
`docs/POSITIVE_CONTROL_0822.md` §2.5 records for its own A1.5 last-300 s
window, with the contamination in the other direction.

### 4.2 The same test with windows that do not straddle the gap

`report` R4b. Window-level bootstrap over 64-frame windows,
`np.random.default_rng(0)`, 4,000 resamples.

**Sit-down only**, [920, 1040) → [1040, 1160) — i.e. after the room is moving
again, across the reported timestamp:

| node | b | Δ rssi dB | Δ SFO | × SD | CI excl. 0 | reject % |
|---|---|---|---|---|---|---|
| d0wd | B1 | +0.45 | −0.00056 | 0.23 | **no** | 6.84 → 3.92 |
| d0wd | B2 | −1.12 | +0.00603 | 2.54 | yes | 3.70 → 7.95 |
| d0wd | B3 | **+4.02** | −0.01086 | 4.58 | yes | 16.16 → 2.19 |
| s3 | B1 | +1.89 | −0.00792 | 3.34 | yes | 1.95 → 0.50 |
| s3 | B2 | −0.07 | +0.00892 | 3.76 | yes | 86.73 → 81.19 |
| s3 | B3 | +1.03 | −0.00922 | 3.89 | yes | 0.72 → 0.24 |

Per-series step at t = 1040 in units of each series' own baseline-A MAD
(`report` R5): the largest of the 24 is d0wd B3 accfrac at +7.4, then d0wd B3
`resid_std` at −4.2 and s3 B1 SFO at −3.2. **Sixteen of the 24 are under
2 MAD.** RSSI moves **+0.93, −1.01, +3.33 on the d0wd and +2.29, −0.44, +1.19
on the S3** — the two nodes have the *identical* sign pattern, `+ − +` on both,
where 08:55 had `+ + +` on the d0wd against `− − −` on the S3. **P1's
opposite-direction-per-receiver requirement fails**, and it fails in the
strongest way available: the receivers agree instead of opposing.

**Node-level series at 1040 s** (`report` R3), against each series' own
baseline-A MAD:

| | d0wd | s3 |
|---|---|---|
| `noise_floor` | cannot move (−97, 0 transitions) | +0.422 dB (**2.86 ×** MAD 0.14768) |
| delivered fps | +9.00 (1.45 ×) | −0.45 (0.06 ×) |
| drop rate /s | 0.00 | +13.70 (1.70 ×) |

**P6 fails**: the two offered rates do not move in opposite directions at 1040
by any margin the baseline supports.

### 4.3 What is at 1040 s

Something is, and it is a **settling**, not a step. The 10 s series (`report`
R10) through this stretch reads, on d0wd/B3's RSSI: −83.5 pinned through
[790, 930), then −80.9, −81.4, −81.3, −81.3, −79.8, −80.2, −80.1, −80.1, −78.5
across [940, 1030), then −77.2 at 1040, −74.6 at 1120, and −74 to −76 for the
remaining 800 s. The motion index (§5) shows a burst at t = 1010–1030 and then
falls. The reading the data supports is: **the room begins moving again at
920 s; a period of movement runs to about 1030; the channel reaches its final
configuration between 1040 and 1200 and holds it to the end.** That is
consistent with a person entering at 920, moving about, and settling at a desk
around 1040 ± 60 — and it is consistent with several other stories, and this
file cannot choose between them.

**How far the observed step sits from the reported time.** The only sharp,
data-located transition near 1040 s is the return edge at **920 ± 10 s**,
which is **120 ± 10 s earlier** — outside the operator's stated ±60 s by a
factor of two.

---

## 5. The departure and the return, located from the data

The operator does not know when he left. Both edges are recovered here, from a
statistic that is not the pre-registered one.

### 5.1 The motion index

`report` R11. For each of the six node×beacon cells, the 10 s binned mean RSSI
is differenced bin to bin: `|Δ level|`. Each cell is normalised by its own
whole-run median and the six are averaged. **No smoothing window is applied
before the index is formed**, so the 10 s resolution survives. A 5-bin (50 s)
running *median* is applied only before contiguous runs are extracted, so one
quiet bin inside an occupied stretch cannot open an interval; the raw index is
reported alongside and gives the same edges.

Why this quantity and not the within-bin sd: the **within-bin sd of per-frame
RSSI does not separate the two states** — inside/outside ratios are 1.20, 1.23,
0.97, 1.35, 1.25, 1.37 across the six cells, i.e. one cell has it backwards.
It is dominated by fast fading that is present whether or not anything moves.
The bin-to-bin change of the *mean* is the occupancy-bearing quantity.

Baseline A median 1.5395, MAD 0.9238; running-median baseline 1.7165; quiet
threshold = half that = 0.8583. **A 6 × MAD one-sided gate is unusable here
because it lands below zero (−4.0032), which is stated rather than quietly
replaced.**

Contiguous quiet runs across the whole 1,944.7 s:

| t (s) | duration |
|---|---|
| 170 – 190 | 20 s |
| 200 – 210 | 10 s |
| 460 – 520 | 60 s |
| **790 – 920** | **130 s** |
| 1220 – 1240 | 20 s |
| 1410 – 1430 | 20 s |
| 1670 – 1690 | 20 s |
| 1700 – 1720 | 20 s |
| 1780 – 1830 | 50 s |

**One interval is 130 s; the next longest anywhere in the run is 60 s.**

### 5.2 The interval is coherent across all six cells

| node | b | \|ΔRSSI\| inside | outside | ratio | within-bin sd inside / outside |
|---|---|---|---|---|---|
| d0wd | B1 | 0.084 dB | 0.556 dB | **6.59** | 0.830 / 0.997 |
| d0wd | B2 | 0.149 | 0.349 | **2.35** | 0.675 / 0.828 |
| d0wd | B3 | 0.118 | 0.512 | **4.32** | 0.846 / 0.823 |
| s3 | B1 | 0.066 | 0.472 | **7.12** | 0.829 / 1.121 |
| s3 | B2 | 0.083 | 0.348 | **4.19** | 0.741 / 0.929 |
| s3 | B3 | 0.095 | 0.385 | **4.05** | 0.708 / 0.973 |

Six of six cells, two nodes, three beacons, every ratio ≥ 2.35. Nothing else
in the run does this.

### 5.3 The edges, and their uncertainty

Raw (unsmoothed) index around each edge, `report` R11:

```
departure   760:0.96  770:2.56  780:0.91  790:0.38  800:0.26  810:0.18  820:0.40
return      890:0.56  900:0.52  910:0.61  920:1.19  930:2.81  940:1.71  950:1.24
```

The last bin above the 0.8583 threshold before the interval is [780, 790)
(0.91, marginal); the first clearly below is [790, 800) (0.38). The last bin
below at the far end is [910, 920) (0.61); the first above is [920, 930)
(1.19). The smoothing does not move either edge.

| | estimate | uncertainty | wall clock |
|---|---|---|---|
| departure | **t = 785 s** | ±10 s (one bin) | **14:57:29** |
| return | **t = 920 s** | ±10 s (one bin) | **14:59:44** |
| stillness | **135 s** | ±14 s | 2 min 15 s |

**The uncertainty is the bin grid, not a confidence interval.** A 10 s bin
cannot resolve better than 10 s, and the index is a difference of adjacent
bins, so a transition inside a bin is smeared across two. Nothing here supports
a tighter figure.

A second, independent edge estimate from a different statistic — the 2 s-bin
RSSI level step on the single strongest series (`report` R5) — puts d0wd/B3's
falling edge at **t = 768.0 s** with a −6.81 dB step and a 90 %-of-maximum
band of [736, 796] s. It agrees with 785 ± 10 s to within its own ±30 s and is
the weaker of the two, because it rests on one cell.

### 5.4 What happens to the phase pipeline at the departure

`report` R13. Window-level bootstrap, 4,000 resamples, `default_rng(0)`,
[670, 790) vs [790, 910) s:

| node | b | n win before | after | Δ SFO | 95 % CI | × `BETWEEN_UNIT_SD` |
|---|---|---|---|---|---|---|
| d0wd | B1 | 48 | 62 | −0.00431 | [−0.00562, −0.00257] | 1.82 |
| d0wd | B2 | 70 | 83 | −0.00736 | [−0.00948, −0.00530] | 3.11 |
| d0wd | B3 | 100 | 60 | **+0.01836** | [+0.01621, +0.02199] | **7.75** |
| s3 | B1 | 82 | 87 | +0.00613 | [+0.00443, +0.00657] | 2.59 |
| s3 | B2 | 6 | **0** | — | — | — |
| s3 | B3 | 132 | 134 | +0.01224 | [+0.01077, +0.01371] | 5.16 |

**Five of six cells move with CIs excluding zero. The sixth emits zero windows
in the still interval and cannot be measured.** The largest is d0wd/B3 at
**7.75 × `BETWEEN_UNIT_SD`**.

And it is the `docs/S3_SFO_STEPS.md` §7 mechanism, seen a fourth time. At the
same instant on that cell (`report` R5, per-series steps at 790 s):
`resid_std` **+0.0191** (+3.6 MAD), `accepted fraction` **−0.0939** (−5.0 MAD),
RSSI **−6.66 dB** (−3.6 MAD). The fit degrades and the reported "clock" follows
it. **This is not a clock move and must not be quoted as one.**

---

## 6. Are the two transitions mirror images?

`report` R6. Step statistic at T_DEP = 790 s and T_RET = 920 s, w = 120 s,
each in its own units.

**Nineteen of 24 series step in opposite directions at the two edges.** The
five that do not are d0wd B1/B2 rssi, s3 B1/B3 rssi and d0wd B3 accfrac.

The magnitudes are **not** mirror images. Taking the four series with a step
larger than 2 MAD at both edges:

| series | @ T_DEP | @ T_RET | recovery |
|---|---|---|---|
| d0wd B3 rssi | −6.663 dB | +2.999 dB | **45 %** |
| d0wd B3 resid_std | +0.01913 | −0.01081 | 57 % |
| d0wd B3 SFO | +0.01853 | −0.01143 | 62 % |
| s3 B3 SFO | +0.01271 | −0.00760 | 60 % |

The return recovers roughly half of what the departure moved, because **the
room he came back to is not the room he left.** `report` R9, baseline A
[120, 720) against [1100, 1900):

| node | b | rssi before → after | Δ | SFO before → after | Δ |
|---|---|---|---|---|---|
| d0wd | B1 | −81.85 → −83.61 | −1.76 | +0.0137 → +0.0120 | −0.0017 |
| d0wd | B2 | −79.72 → −80.95 | −1.23 | +0.0261 → +0.0423 | +0.0162 |
| d0wd | B3 | −78.48 → **−75.06** | **+3.41** | +0.0172 → +0.0095 | −0.0077 |
| s3 | B1 | −77.12 → −77.68 | −0.56 | +0.0102 → +0.0138 | +0.0036 |
| s3 | B2 | −79.69 → −79.72 | −0.03 | +0.0504 → +0.0764 | +0.0261 |
| s3 | B3 | −67.35 → −66.61 | +0.74 | +0.0119 → +0.0089 | −0.0031 |

Verified independently of the script by `awk` on the raw files. The `awk`
windows are **not identical** to the table's — it uses the still interval
[790, 910) against [1200, 1900), where the table uses [120, 720) against
[1100, 1900) — so this is a cross-check on the levels, not a reproduction. The
two "occupied-after" columns agree to **0.17 dB on all six cells** (worst:
d0wd B1, −83.44 against −83.61):

```
for f in data/raw/d0wd_20260822_144424.csv data/raw/s3_20260822_144424.csv; do
  T0=$(awk -F, 'NR==2{print $1; exit}' $f)
  awk -F, -v T0=$T0 'NR>1{t=($1-T0)/1e6
      k=(t>=790&&t<910)?"quiet":((t>=1200&&t<1900)?"occ":"")
      if(k!=""){n[$4 FS k]++; r[$4 FS k]+=$5}}
    END{for(x in n) if(n[x]>100){split(x,a,FS)
        printf "  %-19s %-5s n=%-6d rssi=%.2f\n",a[1],a[2],n[x],r[x]/n[x]}}' $f
done
```

> d0wd: B1 quiet −82.51 / occ −83.44 · B2 −79.65 / −81.01 · **B3 −83.58 / −75.10**
> s3: B1 −77.35 / −77.68 · B2 −79.53 / −79.75 · B3 −68.48 / −66.48

**Sitting back down at the desk did not restore the pre-departure channel on
any cell.** d0wd/B3 ends 3.4 dB *above* where it started. Two sessions the
operator describes as identical are not identical to the instrument, which is
the same warning `docs/OVERNIGHT_2026-08-22.md` §6 gives across sessions, now
observed **inside** one session across 20 minutes and one chair.

---

## 7. `noise_floor`

**The d0wd cannot answer, for the third capture running.** It reads −97 on
**242,718 of 242,718 clean rows with zero row-to-row transitions** (§2.2,
`awk`-verified). "The d0wd's `noise_floor` held" remains evidence of nothing —
`docs/OVERNIGHT_2026-08-22.md` §2.1, `docs/S3_SFO_STEPS.md` §4 and
`docs/V2_SPEC.md` §4.4 all say the same, and this is a third file.

**The S3 does answer.** Raw values over 280,621 rows: −93 × 224,514,
−92 × 53,894, −91 × 2,156, −94 × 57. Modal 10 s value **−93**, held by
**83.08 %** of bins (overnight: 86.89 % of 2,327 bins). `report` R3b — every
excursion from the modal value:

| t (s) | duration | mean offset |
|---|---|---|
| **990 – 1300** | **310 s** | **+1.032 dB** |
| 300 – 310 | 10 s | +1.000 dB |
| 970 – 980 | 10 s | +1.000 dB |

**Three excursions in 1,944.7 s, and the longest is 310 s.**
`docs/OVERNIGHT_2026-08-22.md` §0 measures 129 excursions over 23,267 s with a
**median duration of 10 s and a maximum of 220 s**. This one is 90 s longer
than the longest of 129 draws from an empty room. Drawing three and getting a
310 s one has probability under 3/129 ≈ 2.3 % if the two distributions matched
— which is a suggestive number resting on **n = 3**, and is offered as that.

It begins at **t = 990 s**, which is 70 s after the return edge and 50 s before
the reported sit-down, and it **reverts** at t = 1300 s. That is the property
`docs/POSITIVE_CONTROL_0822.md` §2.3 uses to *separate* a `noise_floor`
excursion from the 08:55 signature: at 08:55 it left −93 and did not return.
Here it returns. **P4 fails.**

Step at the return edge: **+0.578 dB, 3.91 × its own baseline-A MAD (0.14768)**.
Step at t = 1040: +0.422 dB, 2.86 ×.

---

## 8. The branch-invariant coherence detector

`docs/UNWRAP_DEFECT.md` §7's detector, applied unchanged:

```
C = | sum_k exp( j ( phi_k - (m k + b) ) ) | / 52
```

over all 52 usable bins with the **raw principal angles** (`dsp.py:130` before
`dsp.py:64`), and `m`, `b` the slope and intercept `ransac_line`
(`dsp.py:71-103`) already returns through `FrameEstimator`. It is
branch-invariant by construction, so it is blind both to `np.unwrap`'s branch
choice and to `unwrap_continuity`'s integer-turn shift (`dsp.py:65-67`).

`report` R7, 523,068 fitted beacon frames:

| node | b | frames fitted | median C | flagged C < 0.5 | rate |
|---|---|---|---|---|---|
| d0wd | B1 | 63,446 | 0.9447 | 65 | 0.102 % |
| d0wd | B2 | 79,019 | 0.9373 | 89 | 0.113 % |
| d0wd | B3 | 100,120 | 0.9599 | 433 | **0.432 %** |
| s3 | B1 | 85,191 | 0.9818 | 8 | 0.009 % |
| s3 | B2 | 55,124 | **0.7922** | **15,682** | **28.449 %** |
| s3 | B3 | 140,168 | 0.9901 | 7 | 0.005 % |

### 8.1 Do flagged windows cluster around the transitions? No.

Flag rate within ±120 s of the departure edge, the return edge or t = 1040,
against the rest of the run:

| node | b | near | elsewhere | ratio | total flagged in the run |
|---|---|---|---|---|---|
| d0wd | B1 | 0.033 % | 0.150 % | 0.22 | 65 |
| d0wd | B2 | 0.042 % | 0.147 % | 0.29 | 89 |
| d0wd | B3 | 0.565 % | 0.520 % | 1.09 | 433 |
| s3 | B1 | 0.028 % | 0.003 % | 8.09 | **8** |
| s3 | B2 | 31.134 % | 26.264 % | 1.19 | 15,682 |
| s3 | B3 | 0.011 % | 0.003 % | 3.89 | **7** |

Two of the six cells move the *wrong* way, two are flat, and **the two large
ratios rest on 8 and 7 flagged frames in the entire capture** and are not a
result. **The detector does not localise the transitions.**

### 8.2 What it is actually measuring here

`report` R12, splitting each cell by whether the shipped gates accepted the
frame:

| node | b | C < 0.5 given **accepted** | C < 0.5 given **rejected** | median C accepted | median C rejected |
|---|---|---|---|---|---|
| d0wd | B1 | **0.000 %** | 1.257 % | 0.9468 | 0.8734 |
| d0wd | B2 | **0.000 %** | 0.982 % | 0.9406 | 0.8860 |
| d0wd | B3 | **0.004 %** | 6.872 % | 0.9617 | 0.8712 |
| s3 | B1 | **0.000 %** | 0.943 % | 0.9819 | 0.8877 |
| s3 | B2 | **0.268 %** | 34.180 % | 0.9227 | 0.7233 |
| s3 | B3 | **0.000 %** | 1.663 % | 0.9901 | 0.9012 |

**In 6 of 6 cells the detector fires on 0.000–0.268 % of the frames the
pipeline keeps and 0.943–34.180 % of the frames it already throws away.** On
this capture `C < 0.5` is very nearly redundant with `inlier_ratio >= 0.6`
(`dsp.py:164,173`). At worst it would remove 2.7 frames per thousand from an
accepted population, and in four of six cells it would remove none.

**And its largest rate is on the S3.** `docs/UNWRAP_DEFECT.md` §2 identifies
the trigger for the whole defect as node 68's dead `k = +1` subcarrier, and
`docs/V2_SPEC.md` §7(a)1 sweeps 140,000 frames across seven chunks per node and
finds **no dead bin on the S3 at any subcarrier, in 7 of 7 chunks**. So the
28.449 % rate on s3/B2 cannot be that defect. `C < 0.5` is a **fit-quality**
statistic; on the d0wd it happens to co-occur with a branch error, and here it
does not.

What it does do, unprompted, is track a cell's health over time. `report` R13,
s3/B2 by 200 s block:

| t (s) | frames | accepted | median C |
|---|---|---|---|
| 0 – 200 | 4,219 | 52.15 % | 0.8568 |
| 200 – 400 | 4,561 | 27.17 % | 0.8003 |
| 400 – 600 | 5,647 | 27.43 % | 0.8194 |
| 600 – 800 | 6,126 | 24.00 % | 0.8136 |
| 800 – 1000 | 6,601 | 5.15 % | 0.6610 |
| 1000 – 1200 | 6,012 | 17.20 % | 0.8505 |
| 1200 – 1400 | 6,011 | 9.02 % | 0.8178 |
| 1400 – 1600 | 6,098 | 7.71 % | 0.7872 |
| 1600 – 1800 | 6,031 | 6.42 % | 0.7311 |
| 1800 – 2000 | 3,820 | **2.23 %** | **0.4886** |

**s3/B2 is not stationary.** Its acceptance falls from 52 % to 2 % across one
32-minute capture while it continues to deliver ~6,000 frames per 200 s, and
its median coherence falls with it. That is a cell-health monitor working, and
it is the only thing in this document that the detector adds over the shipped
gate.

---

## 9. Magnitude, against 08:55, honestly

`report` R8. The 12 series `docs/POSITIVE_CONTROL_0822.md` §2.4/§2.5 quantifies,
against this run's steps at the departure edge, the return edge and the
reported time:

| series | 08:55 | @ T_DEP | @ T_RET | @ 1040 | \|DEP\|/\|08:55\| | \|RET\|/\|08:55\| |
|---|---|---|---|---|---|---|
| d0wd B1 rssi | +0.28000 | +1.36964 | +0.41035 | +0.93205 | 4.892 | 1.466 |
| d0wd B2 rssi | +0.43000 | +0.93724 | +0.85685 | −1.00534 | 2.180 | 1.993 |
| d0wd B3 rssi | +1.68000 | −6.66333 | +2.99862 | +3.32848 | 3.966 | 1.785 |
| s3 B1 rssi | −3.58000 | +0.29631 | +0.43351 | +2.28644 | 0.083 | 0.121 |
| s3 B2 rssi | −1.47000 | +0.18545 | −0.13409 | −0.44373 | 0.126 | 0.091 |
| s3 B3 rssi | −3.69000 | +1.12312 | +0.09684 | +1.18569 | 0.304 | 0.026 |
| d0wd B1 SFO | −0.00751 | −0.00432 | +0.00299 | −0.00068 | 0.576 | 0.399 |
| d0wd B2 SFO | +0.00383 | −0.00846 | +0.00084 | +0.00629 | 2.209 | 0.219 |
| d0wd B3 SFO | −0.05410 | +0.01853 | −0.01143 | −0.01167 | **0.342** | 0.211 |
| s3 B1 SFO | +0.00420 | +0.00563 | −0.00026 | −0.00635 | 1.340 | 0.062 |
| s3 B2 SFO | +0.00945 | +0.07314 | −0.02730 | +0.01351 | 7.740 | 2.889 |
| s3 B3 SFO | −0.00162 | +0.01271 | −0.00760 | −0.00949 | 7.843 | 4.691 |

Median ratio over the 12: **T_DEP 1.760, T_RET 0.309, t = 1040 1.471**. Those
medians are not a summary of anything — they are dominated by series whose
08:55 value was near zero (s3 B3 SFO's 08:55 move was 0.68 × SD, so a ratio of
7.8 against it means 5.4 × SD, not "eight times the event"). The comparison
that means something is the largest single effect:

| | 08:55 | this run |
|---|---|---|
| largest SFO move | **−0.05410 = 22.83 × SD** (d0wd B3) | **+0.01836 = 7.75 × SD** (d0wd B3, at T_DEP) |
| … as a fraction | — | **34 %** |
| largest RSSI move | +1.68 / −3.69 dB | **−6.66 dB** (d0wd B3, at T_DEP) |
| series leaving a 6 × MAD baseline | **23 of 24** | **9 of 24, never more than 3 at once** |
| onset band | 70 s, both nodes | no band; no coherent onset |
| `noise_floor` | leaves modal, does not return | leaves modal at 990 s, **returns at 1300 s** |
| offered rate | opposite directions on the two nodes | same direction, under 1.5 × MAD |

**Sign agreement** with the 08:55 arrival, over the 12 series: 5/12 at the
departure, 7/12 at the return, 8/12 at t = 1040. Chance is 6/12. **Nothing in
the sign pattern reproduces.**

The unqualified largest SFO move anywhere in this run is **−0.10240 rad/sc =
43.21 × SD, on s3/B2 at t = 1760 s**. It is **not quotable**: that cell rejects
83.101 % of its frames, emits 145 windows in 32 minutes, and carries a 28.449 %
coherence flag rate. Excluding it, the largest is the +0.01836 above.

**Stated plainly, because the brief asked for it plainly:** on the detector
that found the 08:55 event, **this run's transitions are not detectable above
baseline.** They are detectable on a different statistic, at roughly a third of
08:55's amplitude in the one axis where both can be compared. That is a real
result about the sensitivity limit and it is not dressed up.

### 9.1 The marginal cell has moved again

`report` R13. Whole-run reject rate per cell, against the two earlier dual
captures (overnight = `docs/OVERNIGHT_2026-08-22.md` §3.1 as reproduced in
`docs/POSITIVE_CONTROL_0822.md` §1.1; 08-21 = `docs/S3_SFO_STEPS.md` §1, where
this same D0WD board is called `desk`):

| cell | this run | overnight | 2026-08-21 |
|---|---|---|---|
| d0wd B1 | 8.156 % | 7.422 % | 3.70 % |
| d0wd B2 | 11.469 % | 4.114 % | 1.34 % |
| d0wd B3 | **6.239 %** | **58.814 %** | **43.54 %** |
| s3 B1 | 0.995 % | 0.664 % | 0.37 % |
| s3 B2 | **83.101 %** | **0.794 %** | 1.03 % |
| s3 B3 | 0.300 % | 0.314 % | **12.53 %** |

**Three sessions, three different marginal cells.** On 08-21 it was B3/s3; on
the overnight it was B3/d0wd; today it is **B2/s3, a cell that has never been
marginal before, at 83 %** — while B3/d0wd, the cell four documents warn
against quoting, falls to 6.2 %, its best figure on record.
`docs/POSITIVE_CONTROL_0822.md` §2.6 already noted that "the high-reject cell
has already moved boards once." This is the second move, and it moves to a
different beacon as well as a different board. Whatever the marginal cell is,
it is **not a property of a board and not a property of a beacon**, and it
changes on a timescale of hours.

---

## 10. Established / permitted / unknown

**Established by this pass, from these files.**

- The two files are 242,733 and 280,621 data rows spanning 1,944.681 and
  1,944.772 s, first row 14:44:24 and last 15:16:49 local, matching both
  filenames and both `ls` mtimes. 15 corrupt rows on the d0wd, **0** on the S3
  (§2.1, §2.2).
- **A naive `line.split(",")` mis-parses 100 % of the rows in both files** —
  140 fields on the 128-length rows, 268 on the 256-length rows, 13 on none of
  523,354 (§2).
- Run unchanged on this capture, `docs/POSITIVE_CONTROL_0822.md` §2.1's
  24-series 6 × MAD detector flags **9 of 24 series anywhere, never more than
  3 in one bin, and 2 of 24 within ±30 s of t = 1040 s** — against **23 of 24,
  20 inside one 70 s band** at 08:55. **Not one RSSI series and not one
  `resid_std` series leaves baseline anywhere in the run** (§3).
- All 22 excursions of ≥ 2 bins are in `accepted fraction`, and they are spread
  across the whole run including the stretch the operator states he was seated
  and still (§3.1).
- **The bin-to-bin |ΔRSSI| of the 10 s mean collapses by 2.35× to 7.12× in 6 of
  6 cells over exactly one contiguous 130 s interval, [790, 920) s**, and the
  next longest such interval in the run is 60 s (§5.1, §5.2).
- The transition edges are **t = 785 ± 10 s** and **t = 920 ± 10 s**
  (14:57:29 and 14:59:44 local), bounding **135 ± 14 s** of stillness. **The
  return edge is 120 ± 10 s earlier than the operator's reported 1040 s ± 60 s**
  (§5.3).
- **The within-bin sd of per-frame RSSI does not separate the two states**
  (inside/outside ratios 0.97–1.37, one of them inverted) (§5.1).
- At the departure edge, SFO moves on **5 of 6 cells with 95 % CIs excluding
  zero**; the largest is **d0wd/B3 +0.01836 rad/sc [+0.01621, +0.02199] =
  7.75 × `BETWEEN_UNIT_SD`**, accompanied on the same cell by `resid_std`
  +0.0191, `accepted fraction` −0.0939 and RSSI −6.66 dB (§5.4).
- **19 of 24 series step in opposite directions at the two edges**, but the
  return recovers only 45–62 % of the departure's magnitude on the four series
  large enough to compare, because the post-return channel differs from the
  pre-departure one on every cell — d0wd/B3 by **+3.41 dB**, `awk`-verified
  (§6).
- The d0wd's `noise_floor` reads −97 on **242,718 of 242,718 clean rows with
  zero transitions**, for a third capture (§7).
- The S3's `noise_floor` makes **3 excursions from its modal −93 in 1,944.7 s,
  the longest 310 s (t = 990–1300, +1.032 dB), and it reverts** — against 129
  excursions of median 10 s and maximum 220 s over the 6.5 h empty-room
  overnight (§7).
- `C < 0.5` fires on **0.000–0.268 % of accepted frames and 0.943–34.180 % of
  rejected frames in 6 of 6 cells**; its highest rate, **28.449 %, is on
  s3/B2**, a cell on the board `docs/V2_SPEC.md` §7(a)1 shows has no dead
  subcarrier in 7 of 7 chunks. Flagged frames do **not** cluster at the
  transitions (§8).
- **s3/B2 is non-stationary within the capture**: acceptance 52.15 % → 2.23 %
  and median C 0.8568 → 0.4886 across ten 200 s blocks, while frame delivery
  stays near 6,000 per block (§8.2).
- **The marginal cell has moved for the second time in three sessions**, to
  B2/s3 at 83.101 %, while B3/d0wd falls from 58.814 % to 6.239 % (§9.1).
- `esp_timestamp_us`: **1 u32 wrap on the d0wd, 0 on the S3, 0 true backward
  steps on either**, node clock agreeing with host clock to 0.137 s and 0.118 s
  over 1,944.7 s — reproducing `docs/V2_SPEC.md` §2.3's table on a third pair
  of files (§2.1).
- `grep -rn 'split(",", 128)' pc/` now matches **seven** files, not the two
  `docs/POSITIVE_CONTROL_0822.md` §1.2 and `docs/V2_SPEC.md` §2.10 record. The
  two defective sites are unchanged; `pc/exp_poscontrol_0822.py:290,400`
  carries the corrected `< 128`; and `pc/exp_ambient_separation.py:358`,
  `pc/exp_reference_choice.py:343` and `pc/exp_separation_scaling.py:232` use
  the broken form **deliberately**, as a `naive_dropped` counter of what it
  would have discarded. The substantive claim stands; the grep result does not
  (§13, §2.10 entry).

**Permitted but not established.**

- **That the 130 s still interval is the operator being out of the room.** What
  is measured is that no scatterer in the room moved enough to change any of
  six RSSI paths by more than ~0.1 dB per 10 s. A person standing motionless
  produces the same observation. Attributing it to his absence rests on his
  account, which is what is being tested.
- **That the return edge at 920 s is him walking back in.** It is a channel
  change at roughly the right time, of the right kind. No field in either file
  names a person.
- **That the S3's 310 s `noise_floor` excursion at t = 990 is caused by the
  operator.** It begins 70 s after the return edge, which is suggestive and is
  not a measurement. `docs/POSITIVE_CONTROL_0822.md` §2.3 establishes that a
  `noise_floor` excursion on its own is not the signature, and here it is on
  its own: RSSI on all six cells moves less at 990 s than at several other
  points in the run.
- **That the reported 1040 s is a misremembering rather than a distinct
  event.** A person can enter a room at 920 s and sit at 1040 s. The channel
  does reach its final configuration between 1040 and 1200. This file cannot
  choose.
- **That B2/s3's collapse to 83 % reject is the same phenomenon as B3/s3's on
  08-21 and B3/d0wd's on the overnight.** They share the reject/residual/slope
  relationship; nothing here shows they share a cause.
- **That the operator's presence is what makes the marginal cell marginal.**
  s3/B2's acceptance falls monotonically through the run in both occupancy
  states and its worst 200 s block (5.15 %) straddles the still interval.

**Unknown.**

- **When the operator actually left and returned in wall-clock terms he would
  recognise.** The data gives 14:57:29 and 14:59:44 ± 10 s. He recorded
  neither, and his one recorded time disagrees with the second by 120 s.
- **Why the marginal cell moves between sessions.** Three sessions, three
  cells, and the position swap that would separate board from position is
  still not run.
- **Why s3/B2 degrades within one capture.** Nothing in the record carries a
  receiver state that could explain it; `tlm_status_t`
  (`firmware/common/telemetry/include/telemetry.h:35-46`) has no slot for one,
  and STATUS is discarded at `pc/capture.py:123-128`.
- **What the S3's `noise_floor` excursion at t = 990–1300 is.** Same gap as
  `docs/S3_SFO_STEPS.md` §10 and `docs/POSITIVE_CONTROL_0822.md` §4.
- **Whether a longer or a more complete absence would reproduce 08:55.** This
  capture contains 135 s of stillness. 08:55 followed 6.5 h of it.
- **What the S3's delivered rate is limited by in this session.** Peak 10 s bin
  153.2 fps, matching the 153.2–153.7 the overnight holds in every 30-minute
  block, but the *mean* is 143.91 fps and offered load is 149.31 fps — below
  the ceiling most of the time, unlike either earlier session.

---

## 11. Figures in this document that should not be quoted alone

- **Anything from the s3/B2 cell.** 83.101 % reject, 145 windows in 32 minutes,
  28.449 % coherence flag rate, acceptance falling 52 % → 2 % within the
  capture. Its −0.10240 rad/sc "largest SFO move" is an estimator artefact of
  exactly the kind `docs/S3_SFO_STEPS.md` §7.2 characterises.
- **§4.1's table.** Its "before" window contains the whole still interval. Use
  §4.2.
- **The median ratios in §9 (1.760 / 0.309 / 1.471).** They are dominated by
  series whose 08:55 value was near zero. The comparable number is the largest
  single effect: 7.75 × SD against 22.83 ×.
- **"19 of 24 opposite" as evidence of reciprocity.** The signs mirror; the
  magnitudes recover only 45–62 %, and five series do not mirror at all (§6).
- **The 8.09× and 3.89× coherence ratios in §8.1.** They rest on 8 and 7
  flagged frames in the entire capture.
- **The 310 s `noise_floor` excursion as "longer than the empty room ever
  produced."** True as stated, and it is one draw of three against 129 (§7).
- **d0wd/B3's +0.01836 as a clock move.** It moves with `resid_std` and reject
  rate on the same cell in the same instant. It is fit quality
  (`docs/S3_SFO_STEPS.md` §7).
- **The ±10 s edge uncertainties.** They are the bin grid, not confidence
  intervals (§5.3).
- **Any statement that the room was empty.** What is measured is stillness.

---

## 12. V2 implications — requirement by requirement

Read against `docs/V2_SPEC.md` as it stands. A short section recording these is
appended to that file; nothing in it was restructured.

### 12.1 Strengthened

| requirement | what this run adds |
|---|---|
| **§2.5** `agc_gain` per CSI frame | Two things. (i) The S3 produced a **310 s `noise_floor` excursion at t = 990–1300 s**, longer than any of the 129 in the 6.5 h empty room, and it **reverted** — so it is neither the 08:55 class nor the reverting class cleanly, and nothing in the record names it. (ii) It begins 70 s after a transition this capture locates **independently, from RSSI variability**. That pairing — an externally-timed room event and a receiver-state excursion 70 s later — is exactly the control §7(b)1 lacks. Stays **Must**; (b)1 now has a candidate event with a known external cause. |
| **§2.7** STATUS to disk | ~389 STATUS records per node were emitted at 5 s (`csi_rx/main/main.c:59`) and discarded (`pc/capture.py:123-128`) during this capture. Every receiver-state question it raises — what the 310 s excursion is, why s3/B2 falls from 52 % to 2 % acceptance — is a question STATUS on disk would at least constrain. Stays **Must**. |
| **§2.9** provenance and markers | **The requirement this capture bears on hardest.** Three failures in one run: the operator's one firm timestamp is **120 s from the transition the data locates**, twice his own stated uncertainty; the departure time was never recorded at all and had to be recovered; and the capture ran **1,944.7 s when 1,200 were intended**, with nothing in either file recording either number. `env_id` reads 0 on every row of both files, and `label` is `""` on every row (`pc/capture.py:129`). Stays **Must**, and **part 3 should be widened**: the recorder needs an operator **event-marker channel usable during a capture**, not only a start sidecar and a stop marker. The `label` column already exists and costs **zero wire bytes**. |
| **§2.10** CSI must not be splittable wrong | Measured directly: a naive `line.split(",")` mis-parses **100 % of 523,354 rows** in these two files (140 or 268 fields, never 13). Stays **Must**. **Correction to §2.10's text**: `grep -rn 'split(",", 128)' pc/` now matches **seven** files, not "these two files and no others" — three later scripts use the broken form deliberately as a counter and one carries the fix. The substantive claim is unaffected; the grep result quoted in §2.10 is stale and should be replaced with the file list rather than the count. |
| **§4.4** a receiver-state control the D0WD can provide | Third capture, third confirmation: −97 on **242,718 of 242,718** clean rows, zero transitions. Stays a **Should** for the reason §4.4 gives — it is still not established that the D0WD exposes a varying gain index either. |
| **§5.3** no unwrap fix in V2 | §5.3's decisive point is that the defect reaches no published beacon figure. Here the d0wd's coherence flag rate is **0.432 %** on B3 (against 2.604 % overnight) and ≤ 0.113 % on B1/B2, and **0.004 % of accepted d0wd/B3 frames** are flagged. Stays **out of scope**. |
| **§2.1** CRC-16 | A third file pair with the same asymmetry: **15 corrupt rows on the d0wd, 0 on the S3**, 12 of the 15 carrying an impossible `noise_floor`. Per byte: 7.14 × 10⁻⁸ here against 5.61 × 10⁻⁸ overnight, a ratio of 1.27 — **one more data point for §7(a)7 and not a rate test**. Stays **Must**. |

### 12.2 Weakened

| requirement | what this run does to it |
|---|---|
| **§4.1** the coherence detector | **Weakened as a per-frame flag, strengthened as a cell-health monitor.** On 523,068 beacon frames it fires on **0.000–0.268 % of accepted frames and 0.943–34.180 % of rejected frames in 6 of 6 cells** — it is very nearly redundant with the shipped `inlier_ratio >= 0.6` gate and would remove at worst 2.7 accepted frames per thousand. Its **largest rate is 28.449 % on the S3**, which §7(a)1 shows has no dead subcarrier in 7 of 7 chunks, so **it is not measuring the branch defect**; §4.1's recall and false-positive figures must not be read as branch-defect-specific. What it does do is track a cell's degradation unprompted (median C 0.857 → 0.489 as s3/B2's acceptance falls 52 % → 2 %). It stays a **Should**, its "not a node requirement, the record carries nothing extra" conclusion is **confirmed**, and it should be described as a fit-quality / cell-health statistic rather than a defect detector. |
| **§4.3** adaptive window length | Not weakened — **sharpened, on a beacon rather than an ambient source**. s3/B2 emitted **145 windows from 55,124 frames**, and in its last 200 s accepted 2.23 % of ~3,800 frames, i.e. about one window per 200 s while the radio delivered 19 frames/s. A cell can go effectively silent under the 64-accepted-frame rule (`dsp.py:164,178`) while delivering frames normally. Stays a **Should**. |

### 12.3 Left untouched

`§2.2` (`dropped` u32 — 0 u16 wraps on either node in 1,944.7 s; at the S3's
5.398 drops/s a u16 wraps in 12,141 s, so this capture cannot exercise it),
`§2.3` (corroborated, not tested — 1 wrap, 0 backward steps),
`§2.4` (per-source `seq`), `§2.6` (`q_occupancy` — but see below),
`§2.8` (`first_word_invalid`), `§2.11` (`csi_truncated` — **no 384-length frame
exists in either file**, so the clamp cannot have fired), `§4.2` (temperature),
`§4.5` (safe-boot console), `§4.6` (MAC filter in STATUS), `§5.1`, `§5.2`,
`§5.4`, `§6`.

One observation that touches **§2.6 / §7(b)3** without testing either: the
S3 dropped **5.398 /s here against 26.83 /s overnight**, a loss fraction of
**3.6 % against 14.906 %**, between two sessions the operator states were
physically identical. §7(b)3's null is neither confirmed nor killed, and **the
overnight remains the file to test it on** — this one has five times less loss
to work with.

### 12.4 Does anything move out of §7 "unjustified but suspected"?

**No. Nothing in §7 moves to Must on this run's evidence.**

- **§7(a)1** (is the S3 clean on all 52 bins?) — its residue asks for a per-bin
  coherence-against-the-fitted-line statistic over the full population. This
  run computes frame-level coherence on 523,068 beacon frames and **not per
  bin**, and it produces the first S3 cell in the repo with a large coherence
  flag rate (28.449 %). **That is a reason to run (a)1's residue against this
  capture rather than the overnight**, and it stays in (a).
- **§7(a)7** (is the corrupt-row rate a link BER?) — gains one data point
  (7.14 × 10⁻⁸ per byte against 5.61 × 10⁻⁸). Two points is not a rate test.
  Stays in (a).
- **§7(b)1** (is the t = 930 s class an AGC/PHY gain change?) — gains a
  candidate event **and an independently timed external cause**, which is the
  half it was missing. It still has no instrument. Stays in (b).
- **§7(a)2, (a)3, (a)4, (a)5, (a)6, (b)2, (b)3, (b)4** — untouched.

**One item should be added to §7(a)**, because this run raises a question none
of the seven covers and it is answerable from data already on disk:

> **(a)8 — Does the marginal cell have a pattern, or does it move at random?**
> Three dual captures, three different marginal cells: B3/s3 at 43.5 % on
> 08-21, B3/d0wd at 58.8 % overnight, **B2/s3 at 83.1 % today**, with B3/d0wd
> falling to 6.2 % in the same 8 hours. Six documents' outstanding position
> swap is motivated by "the d0wd reads differently"; a cell that moves between
> boards *and* between beacons within 8 hours is not a board property and not a
> beacon property. **Check:** compute the per-cell reject rate and median
> `inlier_ratio` for every dual capture in `data/raw/` and test whether the
> marginal cell tracks RSSI, tracks the beacon, tracks the board, or tracks
> nothing. Runs against data already on disk; no new capture.

**And one caution that belongs in §1, not in a requirement.** V2 exists to make
instrument defects self-reporting. This capture measures how large a *room*
confound is on the quantities V2 will be read through: **a person leaving for
135 s moves a marginal cell's SFO by 7.75 × `BETWEEN_UNIT_SD` and one link's
RSSI by 6.7 dB.** Any V2 experiment that reads `agc_gain` against a step in
RSSI or SFO needs the room state recorded at better than one-minute
resolution, or the instrument and the occupant are the same observation. That
is an argument for §2.9's event-marker channel and for nothing else.

---

## 13. What would settle the rest

| question | measurement |
|---|---|
| When did he actually leave and return? | Ask him whether 14:57:29 and 14:59:44 match anything he remembers, and whether the room was empty or he was standing still. Then repeat with the `label` column filled from a keypress — §2.9's event-marker channel, zero wire bytes, and the only thing that would have made this capture unambiguous. |
| Is the 310 s `noise_floor` excursion the receiver or the room? | §2.5's `agc_gain` per frame, and a repeat with the operator leaving for 20 minutes rather than 2. If the excursion tracks occupancy it is the room; if it tracks a gain index it is §7(b)1's answer. |
| Would a longer absence reproduce 08:55? | The obvious next capture: 30 minutes occupied, 30 minutes empty with the door shut and a logged exit, 30 minutes occupied. It also gives the persistence measurement `docs/POSITIVE_CONTROL_0822.md` §2.2 could only make over 132 s. |
| Why does s3/B2 fall from 52 % to 2 % acceptance in 32 minutes? | §2.7's STATUS-to-disk plus §2.5's `agc_gain`. Failing that, stratify s3/B2's frames by `inlier_ratio` as `docs/S3_SFO_STEPS.md` §7.2 did and see whether its slope is a function of fit quality in the same way. Runs against this capture. |
| Does the marginal cell have a pattern? | §12.4's proposed (a)8. Runs against data already on disk. |
| Is `C < 0.5` worth shipping at all? | It removes 0.000–0.268 % of accepted frames in 6 of 6 cells here. Run it over the full 6.4 M-frame overnight, both nodes, every source — `docs/UNWRAP_DEFECT.md` §12 item 2 already asks for this — and decide on the census, not on two captures. |
| Is the S3's 154 fps ceiling real when the offered load is below it? | This run offers 149.31 fps mean and delivers 143.91 with a peak bin of 153.2. `docs/V2_SPEC.md` §7(a)2's 250 ms fold and §2.7's `emit_ns_accum` both remain the way in. |

---

Nothing in this document touches the occupancy pipeline (`pc/occ/`, amplitude
domain). Device-ID and occupancy figures must not be combined (`CLAUDE.md`).
