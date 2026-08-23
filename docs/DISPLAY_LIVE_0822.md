# DISPLAY_LIVE_0822 — the first capture taken with the S3's OLED running

`data/raw/s3_20260822_235739.csv` (node_id 108) and
`data/raw/d0wd_20260822_235739.csv` (node_id 68), started 2026-08-22
23:57:39. One thing is new about this pair and it is the reason the pass
exists: the Heltec ESP32-S3 has a working SSD1306 panel, so
`display_task` is created and runs. In every earlier capture in
`data/raw/` `oled_init()` failed and the task was never created
(`docs/OLED_AND_MARGINAL_CELL.md` §2.1), so no file in this repo has ever
contained its effect. The D0WD in the same session — same host process,
same host clock, no panel — is the control.

Read-only. Both CSVs were opened for reading only; nothing in `data/raw/`
was modified, renamed or deleted, and both files still read 125,449,502
and 180,762,568 bytes with mtime `2026-08-23 00:23:54`, unchanged across
the pass. No serial port was opened, nothing was flashed, nothing was
staged, committed or pushed (`git diff --cached --name-only` is empty).
Two files in the repo were written: this one and
`pc/exp_display_live_0822.py`. The frame cache went to a directory
outside the repo tree (`tempfile.gettempdir()/display_live_0822`).

Every number below was produced this session by a command named in §7.
`docs/DIRECTION.md` is not cited anywhere here; it describes nothing that
is built. Device-ID figures (`pc/rff/`, phase domain) and occupancy
figures (`pc/occ/`, amplitude domain) are kept apart per `CLAUDE.md`: §4
is amplitude-only, §5.3 is phase-only, and no figure in one is derived
from a figure in the other.

---

## 0. What this establishes, stated once

The display is **not** visible in frame arrival timing on either clock,
and the measurement had the power to see it if it were reaching the
drain. Folding the S3's host inter-frame arrival gaps onto a 250 ms
node-clock phase gives a rate-normalised resultant **R̄ = 0.002261,
m = 2R̄ = 0.00452, rotation-null p = 0.962** — the least significant
entry in the whole harmonic table. A fine period scan from 240 ms to
290 ms in 0.1 ms steps, which covers the `vTaskDelay`-inflated true
period as well as the nominal 250.000 ms, peaks at R̄ = 0.011212 at
240.3 ms against a scan-maximum rotation null of p95 = 0.0309
(**p = 1.000**).

The useful number is the ceiling, not the p. The 250 ms rotation null's
p95 of 0.020074 means **a drain stall larger than about 5.0 ms per
250 ms cycle would have been detected** (§2.6). The stall this pass was
sent to look for is 23.5 ms — 4.7× above that ceiling. So the null is
not a power failure: on the S3 the display is not delaying frame
delivery by anything close to 23.5 ms.

That is consistent with the firmware's own scheduling argument and does
not require a new one: `display_task` is priority 3
(`firmware/csi_rx/main/main.c:652`), `csi_drain_task` is priority 5
(`:667`), and the I²C write is a blocking wait rather than a spin, so a
preemptive scheduler puts the drain in front of it. The comment at
`main.c:422-426` says exactly this. This pass measured it rather than
asserting it, on a board where the panel was actually running.

Three things this does **not** establish are in §8.

---

## 1. The files, and the span actually analysed

The brief allowed for the capture still growing. It is not: both files
were polled three times over 36 s and neither size nor mtime moved, and
the final row of each parses to the full 13 fields. `read_capture()`
counts a short final row and skips it rather than truncating a column;
the count came back **0 on both files**.

| | s3 (108) | d0wd (68) |
|---|---|---|
| rows, `len()` of `csv.reader` output | **152,036** | **208,168** |
| short / truncated rows skipped | 0 | 0 |
| unparsable rows skipped | 0 | 0 |
| host span (`pc_time_us`) | 1,575.023 s | 1,575.006 s |
| node span (`esp_timestamp_us`, unwrapped) | 1,575.102 s | 1,575.434 s |
| `esp_timestamp_us` u32 wraps | 0 | 0 |
| delivered rate over the host span | 96.53 fps | 132.17 fps |

**The span analysed is 0 to 1,575.02 s — 26 min 15 s — i.e. wall clock
23:57:39 to 00:23:54.** Every `t = ...` in this document is seconds from
the first row of the corresponding file. The two files start 16 ms apart
on the host clock and are treated as one timeline; that 16 ms is far
below the 10 s binning used in §4.

`csi_data` is a quoted comma-separated list nested inside the CSV, so a
naive `line.split(",")` mis-splits every row. `read_capture()` uses
`csv.reader`; the row counts above are `len()` of what it yielded, not a
byte estimate and not a field-arithmetic estimate.

Both files span 26.25 min, well inside the 4,294.967 s u32 wrap of
`esp_timestamp_us`, so no timestamp unwrap was needed — but the code
does it anyway and reports the wrap count, because a fold phase is
undefined across a wrap (2³² µs is not a multiple of 250 ms).

---

## 2. Does the display show up in the data?

### 2.1 Which clock could carry it, and which cannot

With zero drops on the S3 (§3) there is nothing to fold in the drop
deltas that `docs/OLED_AND_MARGINAL_CELL.md` §3.1 used. Arrival timing
is the remaining channel, and the three clocks in play are not
interchangeable:

| clock | where it is stamped | can a `display_task` stall move it? |
|---|---|---|
| `esp_timestamp_us` | `info->rx_ctrl.timestamp`, in the CSI callback (`main.c:275`) | **No.** It is assigned before the frame is queued, upstream of `csi_drain_task` entirely. |
| `pc_time_us` | host, per decoded record inside the drain loop (`pc/capture.py:129`) | **Yes** — this is the only clock a drain stall can reach. |
| FreeRTOS ticks | what `vTaskDelay` at `main.c:578` counts | not in the CSV at all |

So the test folds a **host-time** quantity (the inter-frame arrival gap
`diff(pc_time_us)`) onto a **node-clock** phase (`esp_timestamp_us`).
The phase carrier has to be the node clock because that is the clock the
display's ticks live on; using the host clock for phase would fold
host-versus-node crystal drift into the answer.

The node-clock inter-frame gap is reported alongside as a **negative
control on the method, not on the display**: it is RF arrival cadence and
is blind to the drain by construction. It reads R̄ = 0.002914 (s3) and
0.004608 (d0wd) at 250 ms. That is stated so the reading is not
mistaken for evidence.

**One structure dominates the host clock and it is not on the node.**
`open_serial` sets `timeout=0.2` (`pc/rff/serialio.py:14`) and the
capture loop calls `ser.read(8192)` (`pc/capture.py:116`), so records
arrive in bursts separated by one long gap. On the S3, 7,354 gaps
exceed 100 ms and carry 1,542.1 s of the 1,575.1 s span (median
210.5 ms); on the d0wd, 8,612 gaps carry 1,521.6 s (median 176.4 ms).
A coarse period scan from 150 to 350 ms finds exactly this line:
**R̄ = 0.119215 at 213.0 ms on the S3 and 0.053274 at 177.5 ms on the
d0wd**. That is what a real periodicity in this quantity looks like at
this sample size — 5.9× the pointwise null p95 on the S3 — and it stands
52.7× (s3) and 14.6× (d0wd) above the same nodes' R̄ at 250 ms. It is
host-side, not a node task: the two nodes
share one `pc/capture.py` process and one host clock yet carry
*different* batch periods, tracking their different byte rates.

### 2.2 The statistic and the null

The statistic is the one `docs/OLED_AND_MARGINAL_CELL.md` §3.1
established, with the drop rate replaced by the mean arrival gap.
Frames are not uniform in phase, so a raw gap-weighted resultant is
biased by frame density; the statistic is built from the per-phase-bin
**mean gap** over 25 bins of 10 ms:

    r_b = (sum of gaps in bin b) / (frames in bin b)
    C = Σ_b r_b cos θ_b,  S = Σ_b r_b sin θ_b,  R̄ = √(C²+S²) / Σ_b r_b

For a law r(θ) = r₀(1 + m cos(θ − φ)), R̄ → m/2, so **m = 2R̄ is the
fractional sinusoidal modulation of the mean arrival gap** — the effect
size, in units of the mean itself.

The null is **2,000 circular rotations of the gap series against the
phase series**. Rotation preserves the frame phase distribution and the
autocorrelation of the gaps exactly. That matters more here than it did
for drops: the serial batching in §2.1 makes ~20 consecutive gaps
near-zero and then one ~200 ms, which any i.i.d. null — a Pearson
chi-square included — would treat as independent and massively
over-reject. The classical Rayleigh p in the last column is computed on
frame arrival *phases* alone and is reported for contrast only.

### 2.3 Result, both nodes

`phase`, 25 bins, 2,000 rotations.

**s3 (node 108, panel running), mean host arrival gap 10,360 µs:**

| period ms | R̄ | m = 2R̄ | null p95 | **p** | density R̄ | Rayleigh p |
|---|---|---|---|---|---|---|
| **250** | 0.002261 | **0.00452** | 0.020074 | **0.962** | 0.003555 | 0.146 |
| 500 | 0.000970 | 0.00194 | 0.006127 | 0.934 | 0.000358 | 0.981 |
| 1000 | 0.003553 | 0.00711 | 0.004571 | 0.156 | 0.003086 | 0.235 |
| 1250 | 0.003331 | 0.00666 | 0.004197 | 0.155 | 0.002935 | 0.270 |
| 2500 | 0.003950 | 0.00790 | 0.004416 | 0.093 | 0.003923 | 0.096 |
| **5000** | 0.007589 | 0.01518 | 0.005037 | **0.0065** | 0.007078 | 4.9e-4 |
| **10000** | 0.008146 | 0.01629 | 0.006166 | **0.0010** | 0.005546 | 9.3e-3 |

**d0wd (node 68, control, no panel), mean host arrival gap 7,566 µs:**

| period ms | R̄ | m = 2R̄ | null p95 | **p** | density R̄ | Rayleigh p |
|---|---|---|---|---|---|---|
| **250** | 0.003648 | **0.00730** | 0.011696 | **0.762** | 0.004667 | 0.011 |
| **500** | 0.007209 | 0.01442 | 0.004540 | **0.0030** | 0.004842 | 0.0076 |
| **1000** | 0.004619 | 0.00924 | 0.004495 | **0.0435** | 0.004045 | 0.033 |
| 1250 | 0.001659 | 0.00332 | 0.002835 | 0.392 | 0.000788 | 0.879 |
| 2500 | 0.002095 | 0.00419 | 0.002874 | 0.203 | 0.002732 | 0.212 |
| 5000 | 0.002391 | 0.00478 | 0.003197 | 0.208 | 0.006093 | 4.4e-4 |
| 10000 | 0.002224 | 0.00445 | 0.003884 | 0.489 | 0.002294 | 0.334 |

Both nodes are null at 250 ms. **The d0wd carries 500 ms and 1000 ms
structure of its own that the S3 does not**, which is not new —
`docs/OLED_AND_MARGINAL_CELL.md` §3.5 recorded the same thing on
`d0wd_20260822_144424` ("The D0WD's own arrivals do carry 1000 ms and
500 ms phase structure"). It is unexplained there and is unexplained
here; nothing in `firmware/` runs at 1 Hz. It is noted so that the
d0wd is not read as a featureless control.

### 2.4 The period scan, and why 250.000 ms is not the only period to try

`vTaskDelay(pdMS_TO_TICKS(250))` at `main.c:578` is a **relative** delay
placed at the end of the loop, not `vTaskDelayUntil`. The refresh period
is therefore 250 ms *plus* the loop's own execution time, so a 23.5 ms
blocking I²C write makes the true period ≈ 273.5 ms and the true rate
≈ 3.66 Hz, not 4.00 Hz. A fold at exactly 250.000 ms would smear such a
line away completely over 1,575 s. The scan is what protects against
reading that smear as an absence:

| node | fine 240–290 ms / 0.1 ms | scan-max null p95 | p | R̄ at 250.000 |
|---|---|---|---|---|
| s3 | 0.011212 @ **240.3 ms** | 0.030900 | **1.000** | 0.002261 |
| d0wd | 0.012277 @ **261.5 ms** | 0.018545 | **0.910** | 0.003648 |

The scan-max null is 200 rotations evaluated over the same grid, because
500 trial periods are 500 chances and the pointwise p95 is not the right
bar for a maximum. Neither node's best period in the whole 240–290 ms
window clears its own scan null. A **drift-robust 60 s-block fold** at
250 ms agrees: 27 blocks, mean per-block R̄ 0.02201 (s3) against a
blockwise rotation null of p95 0.06654, **p = 1.000**; d0wd 0.03154
against p95 0.04055, p = 0.726. (A per-block R̄ is positively biased —
27× fewer samples per fold — so it must be read against its own null,
which is why the null is computed the same blockwise way.)

### 2.5 The 1000 ms and 5000 ms aliases, checked rather than assumed

**5000 = 20 × 250 exactly**, so a 5 s source lands in the same 250 ms
phase slot on every cycle and can masquerade as 250 ms structure. Two
5 s sources are running: `status_task`, `STATUS_PERIOD_MS 5000`
(`main.c:62`, delay at `:339`), which writes a STATUS frame to the same
`stdout` the drain owns; and `rf_liveness_check`, an `esp_timer`
periodic at 5 × 10⁶ µs (`firmware/common/node_hal/node_hal.c:257`).
A third 250 ms source exists that is not the display: the drain's own
`xQueueReceive(..., pdMS_TO_TICKS(250))` bounded wait (`main.c:319`),
which fires only when the queue has been empty for 250 ms.

**The S3's 5 s line is real** — p = 0.0065 at 5000 ms and p = 0.0010 at
10000 ms in the gap fold, and Rayleigh p = 4.9e-4 in arrival density.
This is the trap the previous pass nearly fell into, so it is decomposed
rather than left as a caveat. Folding the S3 at 5000 ms into 20 slots of
250 ms:

```
slot z: -0.56 -1.46 +0.00 -0.55 -1.74 +1.55 -0.51 +0.83 +0.03 +0.21
        +1.84 +1.00 -0.64 -0.63 +1.09 -0.65 +0.37 -0.30 -1.32 +1.43
```

The hottest slot is slot 10 at **+1.84 sd**, carrying a frame share of
0.0480 against the 0.0500 its density predicts. That is not the single
dominant impulse a 5 s writer would produce, and — the point here — it
is not twenty equal peaks either, which is what a genuine 250 ms source
would look like folded at 5000 ms. The 250 ms fundamental is null
independently (§2.3), so no alias correction is needed to reach that
answer; this check only confirms the 250 ms null is not a cancelled
alias.

### 2.6 Effect size, and the ceiling that makes the null mean something

At 250 ms on the S3 the per-phase-bin mean gap is flat: bin mean
10,360 µs, **peak-to-peak 2,155 µs, bin sd 574 µs** across 25 bins, with
no bin standing out.

```
9789 11403 10350 10519 9933 10916 10029 10499 10458 9586 11096 10355
10247 10905 10020 10536 10146 10071 9466 11581 9941 10272 11374 9426 10084
```

The null p95 of R̄ = 0.020074 converts two ways.

- **As a modulation:** m ≥ 0.04015 would have been detected, i.e. a
  sinusoidal modulation of the mean arrival gap larger than
  0.04015 × 10,360 µs = **416 µs**.
- **As a stall.** A stall confined to one 10 ms phase bin lifts that
  bin's mean by H; the flat part of the fold contributes exactly zero to
  C and S, so R̄ = H / (25 r₀). The p95 gives **H ≤ 5,199 µs**. At 0.965
  frames per phase bin per 250 ms cycle, that is a per-cycle drain stall
  of **at most 5.02 ms**.

The stall this pass was sent to find is **23.5 ms**. It is 4.7× above
the ceiling. On the d0wd the same arithmetic gives H ≤ 2,212 µs and a
per-cycle stall ceiling of **2.92 ms** — the control is the *more*
sensitive of the two, because its higher frame rate puts 1.321 frames in
each phase bin per cycle against the S3's 0.965.

### 2.7 The control has the power, which is why its null counts

`CLAUDE.md` failure mode **C** applies to control arms as much as to
empty search results: "the D0WD shows nothing" is worth nothing unless
the power is stated with it, and `docs/OLED_AND_MARGINAL_CELL.md` §3.5
had to disqualify its own control for exactly this reason. Here the
control's ceiling (2.92 ms) is *below* the S3's (5.02 ms), so the d0wd
could have detected the S3's hypothesised effect nearly twice over. Its
250 ms null (p = 0.762) is a real null.

### 2.8 What §2 does and does not settle

- **Established:** on the S3, with `display_task` running, the host
  arrival-gap fold at 250 ms is null (p = 0.962), the 240–290 ms scan is
  null against its own scan-max null (p = 1.000), and the effect-size
  ceiling is a per-cycle drain stall of 5.02 ms.
- **Established:** the method has power on this data — it resolves the
  host serial batch line at R̄ = 0.119215 @ 213.0 ms and the S3's 5 s
  task line at p = 0.0065 — so the 250 ms null is a measurement, not an
  absence of sensitivity.
- **Not established:** that the panel was refreshing during this
  capture. Nothing in the CSV carries display state. The schema has no
  `display_enabled` field, `tlm_status_t` (`main.c:340-351`) does not
  include one, and STATUS frames are dropped by `pc/capture.py:122-128`
  before they reach the CSV. That the panel came up is an operator fact,
  not a fact in these files — the same gap `docs/OLED_AND_MARGINAL_CELL.md`
  §3.7 asked to be closed by "a run-time `display_task` disable plus
  `display_enabled` in STATUS", which is still not in the firmware.
- **Not established:** that the I²C write costs 23.5 ms per refresh, or
  9.4 % of wall time. Those figures came into this pass from outside it.
  Nothing in these files measures the write duration, and no artifact in
  the repo records it. §2.6 bounds the *drain stall*, which is what the
  arrival timing can see; it does not bound the I²C transaction itself,
  which can be 23.5 ms and still cost the drain nothing at priority 3.

---

## 3. Drop rates, properly screened

Corrupt rows are screened by **two independent routes** and both were
run: route 1 is the `dropped`-column median filter from
`docs/DUAL_RX_2026-08-21.md` Appendix A (width 9, tolerance 100); route 2
is field plausibility on six columns that have nothing to do with
`dropped` — `node_id` against the file's own mode, `env_id == 0`,
`channel` against the file's own mode, `csi_len` in {128, 256, 384},
`noise_floor` in [−110, −70], `rssi` in [−100, −10].
`csi_len = 384` is admitted deliberately: `pc/rff/protocol.py:31` sets
`CSI_MAX = 384` and `:59` rejects only what is longer. Excluding it
misclassified a real device once already
(`docs/OVERNIGHT_2026-08-22.md` §1).

| | s3 | d0wd |
|---|---|---|
| corrupt rows, route 1 (median filter) | 0 | **9** |
| corrupt rows, route 2 (field screen) | 0 | **9** |
| union | 0 | **9** |
| `dropped` first / last | 0 / 0 | 61,773 / 7,934 |
| u16 wraps after screening | 0 | **1** |
| **screened wrap-safe drops** | **0** | **11,697** |
| endpoint check `last − first + 65536×wraps` | 0 ✓ | 11,697 ✓ |
| delivered clean rows | 152,036 | 208,159 |
| **loss** | **0.0000 %** | **5.3203 %** |

**The d0wd's real figure is 11,697 drops, 5.3203 % of offered frames**
(11,697 / (208,159 + 11,697)). The nine screened rows and why each was
screened:

```
line  20057  t= 149.1 s  mac a4:f0:0f:77:91:20  rssi -83 nf -97 ch  32 len 256 dropped  9226  [channel,median-filter]
line  26539  t= 195.9 s  mac 00:00:00:00:00:00  rssi   0 nf   0 ch   0 len 256 dropped     0  [channel,noise_floor,rssi,median-filter]
line  27466  t= 203.0 s  mac d3:03:d3:08:d0:0c  rssi -43 nf  16 ch 208 len 256 dropped 54289  [channel,noise_floor,median-filter]
line  37472  t= 281.4 s  mac a4:f0:0f:77:16:28  rssi  24 nf  38 ch  26 len 256 dropped  6437  [channel,noise_floor,rssi,median-filter]
line  77538  t= 567.9 s  mac f5:11:03:18:06:16  rssi  -3 nf  22 ch 253 len 256 dropped 65048  [channel,noise_floor,rssi,median-filter]
line  91924  t= 671.5 s  mac 00:00:00:00:00:00  rssi   0 nf   0 ch   0 len 256 dropped     0  [channel,noise_floor,rssi,median-filter]
line 139205  t=1012.3 s  mac 28:05:a5:2f:04:14  rssi   2 nf  19 ch   6 len 256 dropped  1297  [noise_floor,rssi,median-filter]
line 146776  t=1073.1 s  mac f4:2d:c9:70:72:30  rssi -72 nf -97 ch   0 len 256 dropped     0  [channel,median-filter]
line 157805  t=1157.9 s  mac 00:00:00:00:00:00  rssi   0 nf   0 ch   0 len 256 dropped     0  [channel,noise_floor,rssi,median-filter]
```

**Nine rows screened, and the two routes agree row for row** — union 9,
not 10 or more. Two of the nine carry a plausible beacon MAC and a
plausible `noise_floor` and are caught only by `channel` (32 and 0
against a file mode of 6) plus the median filter; five are all-zero or
positive-RSSI rows that fail four fields at once, and one
(line 139,205) fails three.

**Without the screen the same wrap-safe accumulation returns 601,521
drops and 10 "wraps" — a 51.4× overstatement.** That is the number the
brief flagged, reproduced here only to show what it is: nine corrupt
rows produce nine spurious negative deltas, each of which a wrap-safe
accumulator credits with up to 65,536. The one genuine wrap is at clean
index 83,226 (t = 608.1 s), where the counter reads 65,534 for seven
consecutive rows and then 0 for the next five — a clean u16 rollover,
and the median filter flags neither side of it. This is the same failure
`docs/OVERNIGHT_2026-08-22.md` §4.2 records at 514× on the overnight
file; the mechanism is identical and only the multiplier differs.

**The S3's zero is confirmed, not re-derived on trust:** 0 corrupt rows
by either route, first and last `dropped` both 0, no negative delta
anywhere in 152,035 pairs, so the wrap-safe total is 0 by every route.

---

## 4. The two operator events

Amplitude domain only (`pc/occ/`). The statistic is the one
`docs/OCCUPANCY_TEST_0822.md` §5.1 found effective: per node×beacon
cell, the 10 s binned mean RSSI is differenced bin to bin (`|ΔRSSI|`),
each cell normalised by its own whole-run median, the six averaged. No
smoothing is applied before the index is formed. Clean rows only, six
cells, 157 boundaries.

Whole-run median `|ΔRSSI|` per cell (dB): s3/B1 0.4937, s3/B2 0.5853,
s3/B3 0.3523, d0wd/B1 0.3910, d0wd/B2 0.2779, d0wd/B3 0.3083. Index
median 1.3159, MAD 0.6502, so a 3 σ(MAD) gate sits at 4.208.

A second statistic is used alongside it, because a **permanent geometry
change** and a **body leaving** are supposed to look different and the
index alone cannot tell them apart: a coherent **level-step** scan. At
each 10 s boundary, each cell's mean RSSI over the following 120 s is
differenced against the preceding 120 s and divided by that cell's own
per-bin sd scaled by √(2/12); the six z-scores are combined as an RMS.
A third column reports the ratio of mean index after to before.

Top of the step scan over the whole run (non-maximum suppressed ±60 s):

| t (s) | rms z | cells \|z\|≥3 | s3/B1 | s3/B2 | s3/B3 | d0wd/B1 | d0wd/B2 | d0wd/B3 | var ratio |
|---|---|---|---|---|---|---|---|---|---|
| **1430** | **8.27** | 5 | −3.7 | +8.7 | +14.2 | +4.0 | −10.1 | −1.9 | **3.50** |
| 1310 | 6.60 | 4 | +5.0 | −2.1 | −11.5 | +8.2 | +4.9 | +2.7 | 0.27 |
| **450** | **6.30** | 3 | −8.4 | +1.3 | −0.6 | −2.2 | +5.1 | +11.6 | **0.37** |
| 980 | 6.27 | 4 | −5.3 | −0.7 | −0.8 | −3.5 | −11.2 | +8.3 | 1.28 |
| 1110 | 6.16 | 2 | +6.6 | −2.2 | +0.4 | −0.4 | +0.2 | −13.4 | 1.57 |
| 590 | 5.93 | 4 | +9.2 | +0.4 | +4.8 | +5.9 | +1.1 | −8.2 | 2.15 |
| 690 | 5.73 | 4 | +0.9 | −6.1 | −5.4 | −10.8 | −0.4 | +3.7 | 0.66 |
| 350 | 4.60 | 4 | +4.4 | +5.3 | +1.9 | +7.3 | +3.0 | −3.8 | 3.97 |

### 4.1 The antenna knock

Reported: "roughly 6–7 minutes", i.e. **360–420 s**, with the operator
unsure which antenna and whether it went back where it was.

The index is quiet through 310–370 s (0.33, 1.35, 0.93, 0.43, 1.22,
1.48, 1.60) and then breaks:

```
t=  380 idx= 4.474   <<<     t=  430 idx= 1.869
t=  390 idx= 2.539           t=  440 idx= 0.618
t=  400 idx= 4.728   <<<     t=  450 idx= 5.263   <<<
t=  410 idx= 3.384           t=  460 idx= 2.049
t=  420 idx= 4.105           t=  470 idx= 0.720
```

Two edges, 70 s apart. **The disturbance opens at t = 380 ± 10 s** —
the first bin over the 4.208 gate, against seven quiet bins before it —
and **closes with a level step at t = 450 ± 10 s** (rms z = 6.30, the
third largest in the run). The uncertainty is the bin grid, not a
confidence interval: a 10 s bin cannot resolve better than 10 s, and the
index differences adjacent bins so a transition inside a bin is smeared
across two.

**Against the reported window:** the opening edge at 380 s sits **inside
360–420 s**, 20 s from its lower edge. The closing step at 450 s is
**30 s past the upper edge**. The event as a whole is bracketed
[380, 450] s = 6 min 20 s to 7 min 30 s.

Mean index by stretch: **0.878** over [150, 370), **3.215** over
[380, 450) — a 3.66× rise — then **0.909** over [460, 580). The
disturbance closes completely, and closes to *below* the run's own
mid-run level of 1.666 over [700, 1300).

Level changes across it, in units of each cell's own per-bin sd:

```
pre[150,370) -> burst[380,450)    s3/B1 +3.57(z +9.5)  s3/B2 +1.72(z +4.7)  s3/B3 +0.40(z +1.1)
                                 d0wd/B1 +1.64(z +7.2) d0wd/B2 +0.24(z +1.3) d0wd/B3 -2.05(z -5.7)
pre[150,370) -> later[700,1300)   s3/B1 +1.48(z +6.9)  s3/B2 +1.16(z +5.6)  s3/B3 +1.07(z +5.1)
                                 d0wd/B1 +0.49(z +3.8) d0wd/B2 +0.31(z +2.9) d0wd/B3 -1.29(z -6.2)
```

**Mixed signs across cells — four up, one down, one flat — is a geometry
signature, not an absorption one**: a body between a link's endpoints
attenuates it, whereas moving one antenna helps some paths and hurts
others. That is consistent with the report. But the second row is the
one that matters for "permanent", and it is small: 0.3–1.5 dB, the same
order as the run's own drift over the same interval. **No level step at
6–7 minutes survives to the end of the capture at a size that separates
it from drift**, so this pass does not confirm a permanent geometry
change — only a bounded 70 s disturbance whose timing matches the
report.

### 4.2 The departure

Reported: "roughly 26 minutes", i.e. **~1,560 s**, near the end of the
visible window. The capture ends at 1,575.0 s.

```
t= 1390 idx= 0.303           t= 1440 idx= 3.865
t= 1400 idx= 0.146           t= 1450 idx= 1.135
t= 1410 idx= 0.152           t= 1460 idx= 1.585
t= 1420 idx= 0.237           t= 1470 idx= 1.738
t= 1430 idx= 2.737  <<<---   t= 1480 idx= 2.489
```

`[1390, 1430)` is the quietest stretch in the whole run — 0.146 and
0.152 against a run median of 1.3159 — and it ends abruptly.
**The edge is t = 1,430 ± 10 s**, and the coherent level step at that
same boundary is **rms z = 8.27, the largest in the run** with 5 of 6
cells past |z| = 3. The next largest anywhere is 6.60, so unlike the
antenna edge this one is uniquely distinguished by size.

**Against the reported time: 1,430 s is 24 min 50 s, which is 130 ± 10 s
earlier than the reported ~26 min.** The direction and rough size match
what `docs/OCCUPANCY_TEST_0822.md` §5.3 found on 08-22 afternoon, where
the recovered departure sat 120 ± 10 s from the operator's estimate.
That is a coincidence of magnitude worth noting and nothing more — two
observations of one operator's time estimation are not a calibration.

The level change persists to the end of the file:

```
pre[1300,1420) -> after[1490,end)  s3/B1 -1.10(z -2.8)  s3/B2 +2.97(z +7.8)  s3/B3 +4.04(z +10.5)
                                  d0wd/B1 +0.45(z +1.9) d0wd/B2 -2.93(z -14.6) d0wd/B3 -1.15(z -3.1)
```

### 4.3 Does the data distinguish the two events?

**Yes, but not on the axis the framing predicts.** The prediction was
permanent-step-versus-stillness. Neither half of that shows up: §4.1
finds no permanent step separable from drift, and no post-departure
stillness exists to find, because the file ends 145 s after the
departure edge and 15 s after the reported time — not enough room for a
quiet interval to accumulate. `docs/OCCUPANCY_TEST_0822.md` §5.1 needed
a 130 s quiet run to call its departure; there are only 145 s of file
left here and they are not quiet.

What does separate them is **whether the disturbance closes**:

| | antenna candidate | departure candidate |
|---|---|---|
| edge | t = 380 ± 10 s | t = 1,430 ± 10 s |
| step rms z at the closing edge | 6.30 (rank 3 of the run) | **8.27 (rank 1)** |
| index before | 0.878 over [150, 370) | 0.761 over [1300, 1420) |
| index during / after | 3.215 over [380, 450) | 2.000 over [1430, end) |
| variance ratio at the edge | **0.37** — collapses | **3.50** — triples |
| does it close? | **yes**, by t = 460 s, to 0.909 | **no**, still open at end of file |
| persistent level change | 0.3–1.5 dB, indistinguishable from drift | 1.1–4.0 dB, \|z\| up to 14.6 |

One is a 70 s transient the room recovers from; the other is a change
still in progress when the recording stops. That is a real distinction
and it is the one the data supports.

**Two cautions.** First, t = 450 s is rank 3 in a scan whose ranks 2, 4
and 5 (t = 1310, 980, 1110 — rms z 6.60, 6.27, 6.16) have no operator
report attached at all, so the antenna identification rests on the
coincidence with the reported window, not on the statistic's size.
Second, `CLAUDE.md` failure mode **G**: neither event is labelled in the
files. The `label` column is empty on all 360,204 rows in both captures.
Every attribution in §4 is inference from operator-stated times onto an
unlabelled timeline, and it is the times that are being tested, not the
identities.

---

## 5. Per-node census and health

### 5.1 Rates

| | s3 (108) | d0wd (68) |
|---|---|---|
| delivered fps, whole span | 96.53 | 132.17 |
| fps by 60 s bin: mean / min / max | 96.55 / 78.85 @1200 s / 110.73 @360 s | 132.43 / 103.58 @1200 s / 142.53 @120 s |
| B1 `a4:f0:0f:77:91:20` | **9.326** | 34.028 |
| B2 `28:05:a5:2f:fa:48` | 19.589 | 37.561 |
| B3 `f4:2d:c9:70:72:30` | 67.428 | 60.433 |
| mean RSSI B1 / B2 / B3 (dB) | −81.74 / −79.66 / −67.00 | −82.84 / −80.85 / −73.96 |
| RSSI sd B1 / B2 / B3 (dB) | 2.10 / 1.91 / 1.80 | 1.62 / 1.33 / 2.17 |

Two things are worth flagging rather than passing over.

**The S3 delivers fewer frames than the D0WD, 96.53 against 132.17 fps.**
The brief's premise for this session is that moving the S3's console
from UART0 to USB-Serial-JTAG removed a per-byte busy-wait that had been
capping the drain at 162 fps. The cap is indeed gone in the sense that
nothing here sits at 162, and the console move is real in the tree
(`firmware/csi_rx/sdkconfig.defaults.esp32s3:23`,
`CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`, against
`sdkconfig.defaults:9-12`'s UART0 console for the D0WD build). But the
S3 is not *faster* than the D0WD after it, and the difference is not a
drain limit: the S3 drops nothing (§3) while the D0WD drops 5.32 %, so
the S3's queue is never backing up. The S3 is simply hearing fewer
frames, concentrated in B1.

**The S3's B1 is below the firmware's own floor.** 9.326 fps against
`BEACON_MIN_FPS_X10 = 100`, i.e. 10.0 fps (`main.c:150`, mirroring
`pc/node_census.py`'s `BEACON_MIN_FPS`). B1 is the reference beacon.
Its per-300 s delivered rate on the S3 runs **8.13, 7.74, 9.62, 8.24,
11.51, 14.92** — under the floor in four of six blocks — so for the
first 20 minutes the panel was rendering a cadence warning for it on
page 3 (`main.c:117`; the row is written from `beacon_fps_x10[i] <
BEACON_MIN_FPS_X10` at `main.c:526-548`) if anyone was looking. The same
beacon on the D0WD reads 34.028 fps and never drops below 31.60 in any
block, so this is an S3-side reception problem, not the beacon failing.
The two blocks where the S3's B1 clears the floor are the last two —
11.51 and 14.92 — i.e. after the §4.2 edge at t = 1,430 s, which is a
correlation and not, on this evidence, more than that.

### 5.2 Fields

`noise_floor` on the s3: `{-93: 34,002, -92: 117,088, -91: 946}` over
the clean rows. On the d0wd: **`-97` on 208,159 of 208,159 clean rows —
100.000 %, zero row-to-row transitions in 26 minutes.** That reproduces
`docs/OVERNIGHT_2026-08-22.md` §2.1 exactly and carries the same
consequence: the D0WD build does not vary this field, so "the d0wd's
`noise_floor` held" remains evidence of nothing about receiver state.

`channel` mode 6 and `env_id` 0 on every clean row of both files.
`csi_len` is 256 on all beacon traffic on both nodes; every ambient
source except one is 128 (see §6). `label` is empty on all rows.

### 5.3 Phase-domain health, `rff.dsp.FrameEstimator`

One `FrameEstimator` per (node, source-MAC) stream, as its docstring
specifies, over every clean beacon frame — no subsampling. `nofit %` is
`ransac_line` returning `None` (`dsp.py:97`); `gate rej %` is the share
failing `WindowAggregator`'s own admission gate,
`min_inlier_ratio = 0.6` / `max_resid = 0.8` (`dsp.py:164`).

| node | b | frames | fitted | nofit % | med slope | med resid | med inlier | **gate rej %** |
|---|---|---|---|---|---|---|---|---|
| s3 | B1 | 14,688 | 14,688 | 0.000 | +0.02886 | 0.1592 | 0.6154 | **49.993** |
| s3 | B2 | 30,853 | 30,853 | 0.000 | +0.01016 | 0.1528 | 0.6731 | 32.020 |
| s3 | B3 | 106,201 | 106,201 | 0.000 | +0.01753 | 0.1470 | 0.9231 | 0.224 |
| d0wd | B1 | 53,595 | 53,595 | 0.000 | +0.01264 | 0.1565 | 0.7500 | 7.484 |
| d0wd | B2 | 59,159 | 59,158 | 0.002 | +0.04076 | 0.1599 | 0.6923 | 15.374 |
| d0wd | B3 | 95,182 | 95,182 | 0.000 | +0.01351 | 0.1430 | 0.9231 | 2.327 |

RANSAC finds a line on essentially every frame — one failure in 359,678
— but the *quality* gate is where the cells separate. **s3/B1 loses half
its frames at the aggregator gate (49.993 %)**, which compounds the rate
problem in §5.1: the S3's reference-beacon cell delivers 9.33 fps and
then half of that is inadmissible. The median inlier ratios are exact
fractions of the 52 usable subcarriers (0.6154 = 32/52, 0.6731 = 35/52,
0.75 = 39/52, 0.9231 = 48/52), which is what `K_USABLE`'s 52 bins
predict.

These are `pc/rff/` numbers and are reported as link health only. No
device-ID accuracy is claimed from them, and none of them is combined
with §4.

---

## 6. `64:fa:2b:6d:05:3b` — and it is not new

**The brief calls this a new MAC. It is not, and the correction belongs
at the top of this section** (`CLAUDE.md` failure mode **H**: check
whether a later artifact supersedes memory before asserting).
`grep -l` over `data/raw/*.csv` finds it in **seven files** spanning
2026-08-21 and 2026-08-22, on both receivers:

```
data/raw/desk_20260821_125017.csv      data/raw/s3_20260822_023034.csv
data/raw/s3_20260821_125017.csv        data/raw/s3_20260822_144424.csv
data/raw/d0wd_20260822_023034.csv      data/raw/s3_20260822_235739.csv
data/raw/d0wd_20260822_235739.csv
```

It is already classified and already phase-estimated:

- `docs/OVERNIGHT_2026-08-22.md` §5.3 puts it in class **P —
  intermittent, corroborated**, with 30 frames on the d0wd and 89 on the
  s3 over the 6.3 h overnight capture, active in 19 of 78 and 44 of 78
  300 s bins respectively (Jaccard 0.286).
- `docs/AMBIENT_SEPARATION.md` fits it: 89 frames on the S3, `csi_len`
  100 % at 256, RSSI −64.6 mean / −69 min / −60 max, duty 0.58 of the
  window. Its median SFO reads **+0.00168 rad/sc on the s3 against
  +0.00659 on the d0wd**, a cross-receiver disagreement of 2.1 ×
  `BETWEEN_UNIT_SD` — the second-best agreement of the eleven sources
  that doc could compare, behind only `62:45:b4:f0:e1:97`. That same doc
  names it, with 89 frames and a per-frame sd of 0.073, as one of the
  three weakest sources it characterised.

Tonight it is far sparser than it was overnight. What this capture adds:

| | s3 | d0wd |
|---|---|---|
| frames | **1** | **3** |
| rate over the 1,575 s span | 0.00063 fps | 0.00190 fps |
| times (s from file start) | 1,331.760 | 175.888, 1,148.807, 1,150.645 |
| RSSI | −69 | −71, −69, −70 |
| `csi_len` | 256 | 256, 256, 256 |
| `channel` | 6 | 6, 6, 6 |
| `noise_floor` | −92 | −97, −97, −97 |
| passes both corrupt-row screens | 1 / 1 | 3 / 3 |

**It looks like a real device, on five independent grounds.**

1. **The payloads are real LLTF buffers.** All four frames carry 256
   integers and **zero nonzero guard bins out of 11** (|k| = 27…32), the
   check `PROJECT_NOTES.md` §2 ran on 5,000 frames and found holding at
   99.88 %. A mis-decoded or bit-shifted frame does not respect the
   guard band. `FrameEstimator` fits all four
   (slopes +0.06763, +0.01054, +0.04306, +0.01297 rad/sc; inlier ratios
   0.673, 0.538, 0.462, 0.462; resid 0.1451, 0.1242, 0.1100, 0.0588).
2. **It is not a corruption of anything present.** Hamming distance to
   the three beacons is 16, 25 and 30 bits, over all six octets. A
   one-bit or one-octet corruption of a bulk source it is not.
3. **The address is globally administered and unicast.** First octet
   0x64: locally-administered bit 0, multicast bit 0. It is a real OUI,
   not a privacy-randomised address — unlike eight of the seventeen
   ambient addresses `docs/OVERNIGHT_2026-08-22.md` §5.3 lists.
4. **The OUI has independent, older corroboration in this repo.**
   `data/fingerprints/64fa2b708554.json`, written **2026-07-13** — six
   weeks before this capture — holds a Phase-1 amplitude template for a
   *different* device on the same 64:fa:2b prefix
   (`64:fa:2b:70:85:54`, 28 frames, `len_hist` 100 % at 256, `rssi_mean`
   −81.54, sd 1.78) built from a set of `desk_20260712_*` sessions
   nothing in this pass touched. Two distinct addresses under one OUI,
   both at `csi_len` 256, six weeks apart.
5. **RSSI is consistent across receivers and across time.** −69 on the
   s3 and −71/−69/−70 on the d0wd, a 2 dB spread across two radios and a
   975 s separation. `csi_len` 256 makes it the only non-beacon source
   in either file at that length; every other ambient MAC tonight is 128.

**Two things that do not support it, stated because they are the ones
that would matter.** The two receivers never caught the same
transmission: the nearest s3/d0wd pair is **181.098 s apart**, so tonight
there is no simultaneity evidence, only same-address-in-two-files
evidence — a weaker thing, and `pc/node_census.py`'s own docstring says
simultaneity is what separates two receivers from one. And four frames
is four frames: `docs/AMBIENT_SEPARATION.md` set a 20-accepted-frame
floor for treating a source as characterised, and tonight's sighting is
five times below it on both nodes. **The characterisation above rests on
the seven-file history and the fingerprint file, not on tonight's four
frames.** From tonight alone the honest statement is "four clean frames
of a previously-catalogued address", nothing stronger.

**What is unknown:** the vendor behind the OUI. No lookup was performed
this session and no vendor table exists in the repo. `CLAUDE.md` failure
mode **D** applies — a remembered OUI assignment is not a source — so it
is left open rather than guessed.

---

## 7. Commands

Everything above comes from one script, `pc/exp_display_live_0822.py`,
read-only, with the frame cache outside the repo tree.

```
python pc\exp_display_live_0822.py census
python pc\exp_display_live_0822.py newmac --mac 64:fa:2b:6d:05:3b
python pc\exp_display_live_0822.py phase  --rot 2000 --scanrot 200 --blockrot 200
python pc\exp_display_live_0822.py events --win 120 --top 12
python pc\exp_display_live_0822.py dsp
python pc\exp_display_live_0822.py report --rot 2000 --scanrot 200 --blockrot 200
```

Section to subcommand: §1 and §3 and §5.1-5.2 → `census`; §2 → `phase`;
§4 → `events`; §5.3 → `dsp`; §6 → `newmac` plus
`grep -l "64:fa:2b:6d:05:3b" data/raw/*.csv`. All randomised nulls use
`numpy.random.default_rng` with fixed seeds (0 for the harmonic and
ceiling nulls, 1 for the scan-max null, 2 for the block null), so every
p above re-derives to the digit.

Not used, per the brief: `pc/capture.py:compute_cfo` (which
`docs/S3_PORT_SCOPE.md:249` records as carrying the opposite I/Q
convention to `dsp.py:52` anyway), `pc/phase_skew.py`,
`pc/fingerprint.py`.

---

## 8. Established, permitted, unknown

**Established this session, each re-derivable by a named command:**

- 152,036 rows on the s3 and 208,168 on the d0wd, no truncated final
  row, 1,575.02 s analysed on both (§1).
- s3 drops 0 of 152,036 with 0 corrupt rows by either screen; d0wd drops
  **11,697** with 9 corrupt rows, 1 genuine u16 wrap, and a 5.3203 %
  loss rate. The unscreened figure is 601,521, a 51.4× overstatement
  (§3).
- The 250 ms arrival-gap fold is null on both nodes (s3 p = 0.962,
  d0wd p = 0.762), the 240–290 ms scan is null against its own scan-max
  null, and the s3's detection ceiling is a **5.02 ms per-cycle drain
  stall** (§2.3, §2.4, §2.6).
- The method has power on this data: the host serial batch line
  resolves at R̄ = 0.119215 @ 213.0 ms, and the s3's 5 s task line at
  p = 0.0065 (§2.1, §2.5).
- Two coherent disturbances, at t = 380 ± 10 s and t = 1,430 ± 10 s,
  the second being the largest coherent level step in the run
  (rms z = 8.27) (§4).
- s3/B1 delivers 9.326 fps, under the firmware's own 10.0 fps floor, and
  loses 49.993 % of its frames at the `WindowAggregator` gate (§5).
- `64:fa:2b:6d:05:3b` appears in seven files in `data/raw/` and has a
  same-OUI fingerprint in the repo dated 2026-07-13 (§6).

**Permitted by the data but not established:**

- That the t = 380–450 s disturbance is the reported antenna knock. The
  timing matches and the mixed-sign level pattern is a geometry
  signature, but the step's size is rank 3 among five comparable
  unlabelled steps, and no permanent level change separable from drift
  survives it (§4.1, §4.3).
- That the t = 1,430 s edge is the reported departure. It is the run's
  largest step and it is 130 s from the reported time, but the `label`
  column is empty on every row and the file ends before any
  post-departure stillness could confirm it (§4.2, §4.3).
- That `64:fa:2b:6d:05:3b` is one physical device rather than one
  address. Four frames tonight is five times below
  `docs/AMBIENT_SEPARATION.md`'s own 20-frame floor, and the two
  receivers never caught the same transmission (§6).

**Unknown:**

- **Whether the panel was refreshing during this capture.** No column,
  and no STATUS field, carries display state; STATUS frames never reach
  the CSV (`pc/capture.py:122-128`). The null in §2 is therefore a null
  about *arrival timing*, and it becomes a null about *the display* only
  by taking the operator's word that the panel was up. The
  `display_enabled` STATUS field `docs/OLED_AND_MARGINAL_CELL.md` §3.7
  asked for would close this and is still not in the firmware.
- **What the I²C write actually costs.** The 23.5 ms / 9.4 % figures
  entered this pass from outside it and no artifact in the repo
  measures them. §2.6 bounds the drain stall at 5.02 ms; it does not
  bound the transaction, which can be 23.5 ms and cost the drain nothing
  at priority 3 (`main.c:652` vs `:667`).
- **Why the d0wd's arrivals carry 500 ms (p = 0.0030) and 1000 ms
  (p = 0.0435) structure.** Nothing in `firmware/` runs at 1 Hz or 2 Hz.
  `docs/OLED_AND_MARGINAL_CELL.md` §3.4 reached the same dead end from
  the drop process on a different file and left it open; this pass finds
  it in a different quantity on a different night and leaves it open too.
- **Why the s3 hears B1 at 9.33 fps when the d0wd hears it at 34.03.**
  §5.1 establishes the asymmetry and rules out drain backpressure (zero
  drops); it does not explain it.
- **The vendor behind the 64:fa:2b OUI** (§6).
