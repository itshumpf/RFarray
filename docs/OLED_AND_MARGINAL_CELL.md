# OLED_AND_MARGINAL_CELL — `docs/V2_SPEC.md` §7(a)2 and §7(a)8

**Date:** 2026-08-22 · **Type:** measurement pass against files already on
disk. No hardware was touched, no serial port was opened, nothing in
`data/raw/` was written, renamed or deleted, and nothing was staged,
committed or pushed. Two files in the repo were written: this one and
`pc/exp_oled_marginal_0822.py`. A short note was appended to
`docs/V2_SPEC.md` §7(a) recording what moved.

Every number below is one of: (a) a line of code in this repo, cited by file
and line; (b) a measurement run in this session with the command shown; (c)
a figure from an existing document, named; or (d) explicitly labelled
**unknown**. Where the operator's stated facts are used they are labelled as
testimony, per `CLAUDE.md` failure mode **G**.

**Two operator facts were handed to this pass and are taken as given.**

1. **No node has ever been physically moved.** Receiver and beacon positions
   are identical across all three dual captures.
2. **The OLED never came up on the S3.** The display never initialised on
   that board.

B1 = `a4:f0:0f:77:91:20`, B2 = `28:05:a5:2f:fa:48`,
B3 = `f4:2d:c9:70:72:30`. d0wd = `node_id` 68, s3 = `node_id` 108. On
2026-08-21 the D0WD's file is named `desk_*`; it is the same board
(`docs/OCCUPANCY_TEST_0822.md` §9.1).

---

## 0. What this pass establishes, stated once

**§7(a)2 — the 250 ms fold is null on the file the spec names.** On
`s3_20260822_023034.csv` — 3,563,999 usable drop-delta pairs carrying
**624,290 drops**, 2.90× the other five files here put together —
the drop rate folded on 250 ms has a mean resultant
**R̄ = 0.002393** against a circular-rotation null whose 95th percentile is
**0.002645**; empirical **p = 0.094**. The effect size is
**m = 2R̄ = 0.0048**, i.e. a 4 Hz sinusoidal modulation of the drop rate of
**0.5 % of the mean rate**, and the null says an m above ≈ 0.0053 would have
been detected. A period scan over 200–300 ms puts no peak at 250 ms. The
same fold is null on four of the other five captures.

**The one capture that does carry structure carries it at 1 Hz, not 4 Hz.**
`s3_20260822_144424.csv` folds at 250 ms with R̄ = 0.042248 (m = 0.0845)
against a null p95 of 0.022945, **p = 0.00050**, and a 200–300 ms scan peaks
at **exactly 250.000 ms**. But the resultant is *larger* at 1000 ms
(**R̄ = 0.069208**) than at 500 ms (0.042513) or 250 ms (0.042248), and a
5 s fold in 50 ms bins repeats every twenty bins. A source at 250 ms would
leave the 1000 ms fundamental empty; a source at 1000 ms lands in the same
250 ms phase slot every cycle and produces exactly what is seen.
**Nothing in the firmware runs at 1 Hz** (§3.4). The frames themselves carry
no 1 Hz arrival structure (R̄ = 0.0017, Rayleigh p = 0.45), so this is in the
drop process, not the arrival process.

**§7(a)2 — what the code does when no panel is attached.**
`firmware/csi_rx/main/main.c:302-307` creates `display_task` **only if
`oled_init()` returns `ESP_OK`**. `oled_init()`
(`firmware/common/node_hal/ssd1306.c:56-110`) returns the first non-`ESP_OK`
result of 25 two-byte I²C transactions to address 0x3C
(`ssd1306.c:81-105`, `:50-54`). With no device acknowledging, it returns an
error, `main.c:304-306` logs `OLED not found … running headless`, and
**`display_task` is never created — it does not run, and it issues no I²C
transaction at all.** The concern that a timing-out transaction might block
*longer* than a successful one does not reach the steady state: the single
failing transaction happens at `main.c:302`, which is **before** `wifi_init()`
(`:309`), before the queue exists (`:314`), before `csi_drain_task` (`:318`)
and before `csi_init()` (`:321`). No CSI frame can arrive while it is
blocked. Its worst case is bounded at 100 ms (`ssd1306.c:53`), once, at boot.

**§7(a)8 — the marginal cell: seven candidates were measured and none
explains it.** All eighteen node × beacon × session cells were rebuilt from
one pipeline and reproduce every published figure (§5.1). Across those
eighteen, no covariate survives correction: the largest, cell RSSI, gives
ρ = −0.639 (p = 0.0054, Bonferroni threshold 0.0038) and **collapses inside
each board** (d0wd ρ = −0.367 p = 0.34; s3 ρ = −0.617 p = 0.088). Node-level
covariates have an effective n of 6, not 18, and at n = 6 none reaches
p < 0.35. Tracking each cell's *change* across session pairs, the best
correlate is band tilt at ρ = +0.542 (p = 0.021, threshold 0.0083). Each
candidate also has a direct counterexample inside the data (§6.3): on the S3
on 2026-08-22, a **9.74 dB** RSSI spread between two healthy cells moves
reject rate by **0.69 pp**, while the cell that is **2.69 dB** below the
better of them rejects **83 %**; the D0WD's B3 cell rejects **43.563 %** at a
band tilt of 1.57 and **6.250 %** at a *flatter* tilt of 1.45; and
`noise_floor` reads exactly −97.00 on all nine D0WD cells while D0WD reject
rate spans 1.34–58.75 %.

**Two findings this pass did not go looking for.**

- **The `resid_std <= 0.8` gate (`pc/rff/dsp.py:164,175`) rejected 0 of
  8,274,369 fitted frames, in 18 of 18 cells.** Every rejection in every cell
  is `inlier_ratio < 0.6` (`dsp.py:164,173`). "Reject rate" in this project
  is a RANSAC-consensus statistic and nothing else (§7).
- **A third candidate for the 154 fps ceiling, which
  `docs/CODE_INVENTORY.md` §1.3 does not list.** The S3's console is
  configured as **UART0 at 460,800 baud** (`firmware/csi_rx/sdkconfig:1298-1310`),
  which is 46,080 B/s 8N1, and `telemetry.c:37-40` writes every frame to
  `stdout`. The S3's measured on-wire delivered rate is **43,519 B/s
  (94.44 %)** on 08-21 and **43,489 B/s (94.38 %)** overnight — two sessions
  4,213 s and 23,267 s long, agreeing to 0.07 % of the budget. The D0WD never
  exceeds 84.00 %. This is **permitted, not established** (§4.3).

---

## 1. Method

One script, `pc/exp_oled_marginal_0822.py`, from the repo root. It is the
only script this pass added.

```
python3 pc/exp_oled_marginal_0822.py selftest
# then, per file, N = round(bytes / 120e6) byte-range parts:
python3 pc/exp_oled_marginal_0822.py part data/raw/<f>.csv --tag <f> \
        --index K --parts N [--t0-pc <pc_time_us of the session's row 1>]
python3 pc/exp_oled_marginal_0822.py merge --tag <f> --parts N
python3 pc/exp_oled_marginal_0822.py harmonics --tag <f> --parts N
python3 pc/exp_oled_marginal_0822.py report
```

Parts used: `desk_20260821_125017` 4, `s3_20260821_125017` 4,
`d0wd_20260822_023034` 21, `s3_20260822_023034` 25,
`d0wd_20260822_144424` 2, `s3_20260822_144424` 2.

**Phase work** is `pc/rff/dsp.py`'s `FrameEstimator(rng_seed=0)` with the
shipped gates `inlier_ratio >= 0.6` and `resid_std <= 0.8`
(`dsp.py:164,173,175`) and `WindowAggregator(window=64)`.
`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` were
**not** used (`docs/CODE_INVENTORY.md` §4.2 C1/C2/C3).

**The CSI field is read with a real CSV reader.** `csi_data` is a quoted
comma-separated list nested inside the CSV. `len(row)` is **13 on
8,297,372 of 8,297,372 data rows** across all six files, by `csv.reader`;
the `split(",", 128)` construction is not used anywhere in this script.

**Corrupt rows** are screened by the two independent routes of
`docs/OVERNIGHT_2026-08-22.md` §1, reused unchanged: route 1 is a width-9
edge-padded median filter on `dropped` with tolerance 100; route 2 is field
plausibility on `node_id`, `env_id == 0`, `channel`, `csi_len ∈ {128,256,384}`,
`noise_floor ∈ [−110,−70]`, `rssi ∈ [−100,−10]`. `node_id` and `channel`
modes are taken from the file's own first 20,000 rows.

### 1.1 Why the file is split into parts, and what that costs

The shell available to this pass caps a single command at ~180 s, and the two
overnight files are 2.5 and 3.0 GB. `part` seeks to a byte offset, backs up
16 KB, discards the partial line, and primes the 9-deep median window from
rows belonging to the previous part; it also reads four records past its
range end. A record is emitted by exactly one part — the one containing its
starting byte — so the corrupt-row screen is the same one a single pass
applies. `merge` concatenates parts in file order.

`FrameEstimator` carries one advancing RNG (`dsp.py:118`, used at `:132`), so
restarting it at a part boundary changes which random 2-point hypotheses
`ransac_line` draws. **Measured cost, same file, 1 part against 3 parts:**
row counts, the corrupt-row screen (14/15/14/15), the drop-delta accounting
and every Check-1 statistic were **identical to the printed precision**;
reject rates moved by at most **0.095 pp** (d0wd/B2, 11.469 → 11.374). That
is the noise floor on every reject figure in this document, and it is three
orders of magnitude below the effects discussed.

### 1.2 Self-tests, run before the data

`selftest` checks four things and all four pass:

- the streaming width-9 edge-padded median equals the reference loop of
  `pc/exp_occupancy_0822.py:81` for n ∈ {3, 9, 10, 37, 500};
- `chi2_sf` (a hand-written regularized incomplete gamma — this environment
  has no scipy) matches published critical values at (3.841, 1), (18.307, 10),
  (23.685, 14), (0, 4);
- `spearman` returns 0.8000 on the textbook case, −1.0 on a perfect
  anti-rank, and the tie-corrected value on a tied case;
- **the Check-1 statistic recovers a planted signal.** On 400,000 synthetic
  frames with a Poisson drop process modulated as
  `λ(θ) = 0.20 (1 + 0.30 cos θ)` at 250 ms, `fold_stats` returns
  **m = 0.2903** against the planted 0.300; on a flat control it returns
  **m = 0.00666** with a rotation-null R̄ p95 of 0.00596.

---

## 2. CHECK 1, part one — what the code does with no panel attached

### 2.1 `display_task` is created conditionally, and the condition fails

`firmware/csi_rx/main/main.c:300-307`:

```c
/* Display first so calibration progress shows during bring-up.
 * Headless-first: non-fatal if the OLED is missing. */
if (oled_init(OLED_SDA, OLED_SCL, OLED_ROTATE_180) == ESP_OK) {
    xTaskCreate(display_task, "display", 4096, NULL, 3, NULL);
} else {
    ESP_LOGW(TAG, "OLED not found on SDA=%d SCL=%d — running headless",
             OLED_SDA, OLED_SCL);
}
```

`oled_init()` (`ssd1306.c:56-110`) can fail at three points, and returns at
the first:

| line | call | returns on failure |
|---|---|---|
| `ssd1306.c:67-68` | `i2c_new_master_bus(&bus_cfg, &bus)` | `err` |
| `ssd1306.c:75-76` | `i2c_master_bus_add_device(bus, &dev_cfg, &s_dev)` | `err` |
| `ssd1306.c:99-105` | 25 × `cmd(init_seq[i])` | `err`, with `ESP_LOGE` |

`cmd()` is `i2c_master_transmit(s_dev, b, 2, 100)` (`ssd1306.c:50-54`) — a
two-byte write to address 0x3C (`:9`) with a **100 ms** timeout. Espressif's
own API reference for this IDF version and target
(https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32s3/api-reference/peripherals/i2c.html)
documents `i2c_master_transmit` as returning `ESP_OK`,
`ESP_ERR_INVALID_ARG`, or `ESP_ERR_TIMEOUT`, and notes on
`i2c_master_probe` that a device that does not answer on a pulled-up bus
yields `ESP_ERR_TIMEOUT`. The bus is pulled up here — `bus_cfg` sets
`flags.enable_internal_pullup = true` (`ssd1306.c:64`).

**Established:** with nothing answering at 0x3C on the configured pins,
`oled_init()` returns a non-`ESP_OK` value and `display_task` is never
created. It does not run. It issues no I²C transaction, ever.

### 2.2 The failing transaction cannot affect the steady state

This is the specific worry the brief raised — that a timing-out transaction
blocks longer than a succeeding one, so "no OLED" could make contention
*worse*. It cannot, because of ordering in `app_main`:

| main.c line | what happens |
|---|---|
| `:302` | `oled_init()` — the I²C transaction that fails |
| `:309` | `wifi_init()` — the radio is not even started yet |
| `:311-312` | `esp_now_init()`, `esp_now_register_recv_cb()` |
| `:314` | `s_csi_queue = xQueueCreate(64, …)` — the queue does not exist before this |
| `:318` | `csi_drain_task` created, priority 5 |
| `:319` | `status_task` created, priority 4 |
| `:321` | `csi_init()` — `esp_wifi_set_csi_rx_cb`, `esp_wifi_set_csi(true)` |

The failing I²C write completes before the queue that `s_dropped` counts
overflows exists (`:314`), and before the callback that increments
`s_dropped` is registered (`:321` → `csi_rx_cb`, `main.c:131-133`). Its cost
is bounded by one 100 ms timeout, once, at boot, with the radio off.
**`s_dropped` cannot have been incremented by it.**

### 2.3 What it would have cost if the panel had come up

Arithmetic, not measurement, and stated as such. `oled_flush()`
(`ssd1306.c:173-183`) issues six two-byte command writes and one
**1,025-byte** `i2c_master_transmit` at `I2C_FREQ_HZ` = 400,000
(`ssd1306.c:10`). With one ACK bit per byte, 1,026 bytes on the wire is
≈ 9,234 bit-times ≈ **23.1 ms**; at `pdMS_TO_TICKS(250)` (`main.c:247`)
that is ≈ **9.2 % of wall time** with the I²C peripheral busy. Whether that
would *cause drops* is a separate question that this pass cannot answer:
`display_task` is priority **3** (`main.c:303`) and `csi_drain_task` is
priority **5** (`main.c:318`), so a `display_task` waiting on an I²C
transaction cannot preempt the drain task. Whether it steals CPU, bus or
interrupt time from it anyway depends on `driver/i2c_master` internals that
no file in this repo carries. **Permitted, not established, and untestable
from these files.**

### 2.4 What the record does not carry, and should

The one line that would settle whether the S3 ran headless —
`ESP_LOGW(TAG, "OLED not found …")` at `main.c:305-306` — is written to
`stdout`, arrives in the serial stream, and is discarded by
`pc/rff/protocol.py`'s resync as non-frame bytes. It reaches no file in
`data/raw/`. This is the same complaint `docs/V2_SPEC.md` §2.7 makes about
STATUS, and it is why §2.7 part 2's `display_enabled u8` is the right fix:
the node knows the answer and never says it where anything records it.

**Unknown, and not resolvable from these files:** whether `oled_init` failed
on the bus, on the device add, or on the first command byte; and whether a
panel is physically wired to GPIO 21/22 at all.
`docs/S3_PORT_SCOPE.md:132-137` records that `OLED_SDA 21` / `OLED_SCL 22`
(`main.c:62-63`) are DevKit-convention pins, that the Heltec V3's own I²C
OLED wiring "is not recorded anywhere in this repo", and predicts exactly the
headless outcome measured here. Operator fact 2 is consistent with all three
failure points and distinguishes none of them.

---

## 3. CHECK 1, part two — the measurement

### 3.1 The statistic, and why it is not a chi-square

Per-frame `dropped` deltas are taken wrap-safe over u16, on clean rows only.
A pair is excluded if it straddles an `esp_timestamp_us` u32 wrap (2³² µs is
not a multiple of 250 ms, so the fold phase is undefined across such a step),
if the timestamp does not advance, or if `dt ≥ 1 s`. Each delta is given the
phase of the frame that observed it.

Frames are not uniform in phase, so the raw drop-weighted resultant is biased
by frame density. The statistic is built from the per-phase-bin drop **rate**
r_b = (drops in bin b) / (frames in bin b) over 25 bins of 10 ms:

    C = Σ_b r_b cos θ_b,  S = Σ_b r_b sin θ_b,  R̄ = √(C² + S²) / Σ_b r_b

For a rate law r(θ) = r₀(1 + m cos(θ − φ)), R̄ → m/2, so **m = 2R̄ is the
fractional amplitude of the sinusoidal modulation** — the effect size, in
units of the mean drop rate.

The null is **2,000 circular rotations of the drop-delta series against the
timestamp series**. Rotation preserves the frame phase distribution *and* the
burst autocorrelation of `dropped` exactly. That matters: drops are known to
be bursty (`docs/OVERNIGHT_2026-08-22.md` §4.2 — 18.9 % of the S3's drops in
the worst 10 % of seconds, 100 % for the D0WD), and a Pearson chi-square
against a uniform-rate expectation treats every drop as independent and
therefore over-rejects. Both are reported below; **the rotation null is the
test**, and the chi-square column is there to show the difference.

### 3.2 Result, both nodes, three captures

`report` R1.

| file | pairs | drops | R̄ | **m = 2R̄** | null p95 | **p** | χ²/24 dof | χ² p |
|---|---|---|---|---|---|---|---|---|
| `desk_20260821_125017` | 577,328 | 20,919 | 0.002702 | 0.00540 | 0.015970 | **0.915** | 37.4 | 0.040 |
| `s3_20260821_125017` | 649,070 | 164,503 | 0.001346 | 0.00269 | 0.005238 | **0.812** | 37.5 | 0.039 |
| `d0wd_20260822_023034` | 2,983,295 | 17,366 | 0.006465 | 0.01293 | 0.017120 | **0.658** | 35.4 | 0.062 |
| **`s3_20260822_023034`** | 3,563,999 | **624,290** | 0.002393 | **0.00479** | 0.002645 | **0.094** | 41.9 | 0.013 |
| `d0wd_20260822_144424` | 242,703 | 2,065 | 0.025151 | 0.05030 | 0.051099 | **0.482** | 22.4 | 0.558 |
| **`s3_20260822_144424`** | 280,620 | 10,498 | 0.042248 | **0.08450** | 0.022945 | **0.00050** | 54.8 | 3.3e-4 |

Note the chi-square column would have called three of these significant at
0.05 that the rotation null does not. That is burstiness, not periodicity.

Period scans, same run:

| file | fine 249–251 ms: peak R̄ at | coarse 200–300 ms: peak R̄ at |
|---|---|---|
| `desk_20260821_125017` | 0.019055 @ 250.470 ms | 0.020981 @ 261.000 ms |
| `s3_20260821_125017` | 0.012313 @ 250.200 ms | 0.007298 @ 256.000 ms |
| `d0wd_20260822_023034` | 0.021315 @ 250.820 ms | 0.025195 @ 277.000 ms |
| `s3_20260822_023034` | 0.003074 @ 249.560 ms | 0.003315 @ **300.000 ms** (range edge) |
| `d0wd_20260822_144424` | 0.064488 @ 249.405 ms | 0.062838 @ 256.500 ms |
| `s3_20260822_144424` | 0.043781 @ 250.005 ms | 0.042248 @ **250.000 ms** |

**On the file §7(a)2 names, the answer is null**, and the scan puts no peak
at 250 ms. The effect-size bound is the useful number: the null p95 of
0.002645 means an m above ≈ **0.0053** would have been detected, so **any
4 Hz sinusoidal modulation of the S3's overnight drop rate is under 0.5 % of
the mean rate** — against a mean rate of 0.17517 drops per delivered frame
and a per-bin range of 0.17261–0.17828.

### 3.3 The one positive, and why it is 1 Hz

`harmonics --tag s3_20260822_144424 --parts 2`:

| period | R̄ | m = 2R̄ | rotation-null p95 | p | frame-arrival R̄ | Rayleigh p |
|---|---|---|---|---|---|---|
| 250 ms | 0.042248 | 0.0845 | 0.022142 | 0.0033 | 0.001447 | 0.56 |
| 500 ms | 0.042513 | 0.0850 | 0.030209 | 0.0033 | 0.003137 | 0.063 |
| **1000 ms** | **0.069208** | **0.1384** | 0.040205 | **0.0033** | 0.001692 | 0.45 |
| 1250 ms | 0.006136 | 0.0123 | 0.031921 | 0.874 | 0.002813 | 0.11 |
| 2500 ms | 0.030247 | 0.0605 | 0.038252 | 0.193 | 0.004744 | 1.8e-3 |
| 5000 ms | 0.024153 | 0.0483 | 0.042631 | 0.445 | 0.003992 | 1.1e-2 |
| 10000 ms | 0.053917 | 0.1078 | 0.057774 | 0.090 | 0.006404 | 1.0e-5 |

(p is empirical over 300 rotations here, so its floor is 1/301 = 0.0033; the
2,000-rotation run in `merge` gives 0.00050 at 250 ms.)

**The resultant is largest at 1000 ms.** That is decisive on direction: a
source at 250 ms repeats four times inside a 1000 ms fold and leaves the
1000 ms *fundamental* near zero, whereas a source at 1000 ms lands in the
same 250 ms phase slot every cycle and shows at 250 and 500 ms as
subharmonics. Folding the same data at 5000 ms in 100 bins of 50 ms shows
the elevated bins recurring every **twenty** bins — a 1000 ms spacing.

The `frame-arrival R̄` column is the same resultant computed on the frame
arrival phases alone, with the classical Rayleigh p = exp(−nR̄²). At 250,
500 and 1000 ms it is flat, so **the periodicity is in the drop process, not
in when frames arrive.**

### 3.4 Nothing in the firmware runs at 1 Hz — and the 5 s sources are a trap

Every periodic source in the running node, from the code:

| source | period | file:line | note |
|---|---|---|---|
| `display_task` | **250 ms** | `main.c:247` | created only if `oled_init` returned `ESP_OK` (§2.1) |
| `status_task` | **5,000 ms** | `main.c:190` | writes a STATUS frame to the same `stdout` |
| `rf_liveness_check` | **5,000,000 µs** | `node_hal.c:256` | `esp_timer` periodic callback |
| `csi_drain_task` receive timeout | 250 ms | `main.c:171` | fires **only** when the queue is empty for 250 ms |

**5000 = 20 × 250 exactly.** Either 5 s source therefore lands in one and the
same 250 ms phase slot on every cycle and would masquerade as "250 ms
periodicity" in the fold §7(a)2 specifies. This is checked directly: folding
`s3_20260822_144424` at 5000 ms into 20 slots of 250 ms, the hottest slot
(slot 1, 250–500 ms into the cycle) carries **6.411 %** of all drops against
a **5.015 %** expectation from its frame share, and sits **+2.42 sd** above
the other nineteen. That is not the single dominant impulse a 5 s writer
would produce, and it does not account for the 1000 ms fundamental.

The 1 Hz source is **unknown**. It is not in `firmware/`. `pc/capture.py`'s
TUI redraws at 10 Hz (`capture.py:192`, `time.sleep(0.1)`) and `Node.rate()`
uses a 2 s window (`capture.py:75-78`), so the obvious host-side candidate
does not match either. The D0WD in the same session, sharing one
`pc/capture.py` process and one host clock, shows nothing at any period —
but see §3.5 before reading that as a control.

### 3.5 The D0WD is not a clean control in that session

`d0wd_20260822_144424` has **2,065 drops**, against the S3's 10,498. Its
rotation-null p95 for R̄ is **0.051099**, so it could not have detected the
S3's m = 0.0845 (R̄ = 0.0422) even if the same effect were present. Saying
"the D0WD shows nothing" is `CLAUDE.md` failure mode **C** unless the power
is stated with it. The D0WD's own arrivals do carry 1000 ms and 500 ms phase
structure (Rayleigh p = 2.1e-15 and 1.1e-10) while its drops do not, which
is a separate observation and not evidence about the S3.

The other four captures **are** clean negatives on this point. Detecting the
S3's R̄ = 0.0422 at p < 0.05 requires a rotation-null p95 below it, and
`desk_20260821_125017` (0.015970), `s3_20260821_125017` (0.005238),
`d0wd_20260822_023034` (0.017120) and `s3_20260822_023034` (0.002645) all
clear that bar by 2.5× to 16×. Whatever the 1 Hz source is, it was **not**
present at this amplitude in the S3's own 08-21 or overnight captures, on the
same board with the same firmware. That is the fact that makes it interesting
and is also why it cannot be a fixed periodic task.

### 3.6 A methodological point about the fold that would have bitten

`esp_timestamp_us` is `info->rx_ctrl.timestamp` (`main.c:127`), the WiFi MAC
receive clock, while `display_task` is scheduled off FreeRTOS ticks. If the
two drifted, a global fold over 6.5 h would smear a real 250 ms line away —
10 ppm of relative drift is 234 ms over 23,267 s, a full cycle. Two things
guard against reading a smeared signal as an absence: the fine period scan
(249–251 ms in 5 or 20 µs steps) would find a displaced line, and a
drift-robust 60 s-block fold is reported alongside. Both agree with the
global fold on all six files. Separately, `s3_20260822_144424`'s 1 Hz line
stays phase-coherent against `esp_timestamp_us` across the whole 1,945 s —
a coarse 0.5 ms-step scan resolves its 250 ms subharmonic to 250.000 ms —
so on that board at least, whatever generates it and the MAC receive clock
do not drift measurably against each other over half an hour. That is
evidence about the 1 Hz source, not about FreeRTOS ticks, which nothing here
exercises.

### 3.7 What this does and does not settle

- **Established:** the fold §7(a)2 specifies, run on the file §7(a)2 names,
  is null at p = 0.094 with an effect-size ceiling of m ≈ 0.005.
- **Established:** `display_task` is not created when `oled_init` fails, so
  on a headless board there is no 4 Hz I²C activity to find (§2.1). The null
  is therefore the *expected* result given operator fact 2, not evidence
  about what the OLED would do if present.
- **A null does not exonerate the display path.** It cannot: on the boards
  that produced these six files the display path was, per operator fact 2 and
  per `main.c:302`, not running. The experiment §7(a)2 describes has never
  been performed on a node with a working panel, and these files cannot
  perform it. That question passes to §2.7 part 3 — a run-time
  `display_task` disable plus `display_enabled` in STATUS — exactly as
  §7(a)2 says it should.
- **Unknown:** what runs at 1 Hz in `s3_20260822_144424`, and why it appears
  in that session and in no other.

---

## 4. The drain-path ceiling, measured in bytes

This is not what §7(a)2 asked for. It is here because the same pass produced
it and because it bears directly on the same question.

### 4.1 The arithmetic

`telemetry.c:21-41` writes 12 header bytes, `len` payload bytes and one XOR
byte per frame; `tlm_send_csi` (`:43-61`) sets `len = 15 + csi_len`. A
256-sample CSI frame is therefore **284 bytes on the wire**.

`firmware/csi_rx/sdkconfig` — target `esp32s3` (`:391`), mtime
**2026-08-21 12:20**, with `build/csi_rx.bin` built **12:22**, 28 minutes
before the 12:50:17 capture — configures the console as:

```
:1298  CONFIG_ESP_CONSOLE_UART_CUSTOM=y
:1301  CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=y
:1303  CONFIG_ESP_CONSOLE_UART=y
:1306  CONFIG_ESP_CONSOLE_UART_NUM=0
:1308  CONFIG_ESP_CONSOLE_UART_TX_GPIO=1
:1310  CONFIG_ESP_CONSOLE_UART_BAUDRATE=460800
```

460,800 baud, 8N1, is **46,080 B/s**, which at 284 B/frame is **162.25
fps**. `sdkconfig.old` (target `esp32`, `:1120-1127`) carries the same
UART0-at-460800 console with no secondary, so both builds write telemetry
into the same byte budget.

### 4.2 The measurement

`report` R2, mean on-wire bytes per second over the whole session:

| file | fps | mean B/s | **% of 46,080** |
|---|---|---|---|
| `desk_20260821_125017` | 137.05 | 38,708 | 84.00 |
| **`s3_20260821_125017`** | **154.08** | **43,519** | **94.44** |
| `d0wd_20260822_023034` | 128.22 | 36,404 | 79.00 |
| **`s3_20260822_023034`** | **153.18** | **43,489** | **94.38** |
| `d0wd_20260822_144424` | 124.81 | 35,438 | 76.91 |
| `s3_20260822_144424` | 144.30 | 40,971 | 88.91 |

The S3's two pinned sessions — 4,213 s and 23,267 s, a day apart, at
different offered loads — sit at **94.44 %** and **94.38 %** of the same
number. The D0WD never reaches 84 %. `docs/OVERNIGHT_2026-08-22.md` §4.3's
"153.2–153.7 fps in every 30-minute block while the drop rate moves by a
factor of 1.9" and `docs/DUAL_RX_2026-08-21.md` §2.5's "154.0–154.3 fps in
all ten deciles against an offered 175–204 fps" are, in bytes, one number
that does not move.

### 4.3 Grading this honestly

- **Established from files:** the byte arithmetic above; the sdkconfig
  console settings and their mtimes; the measured on-wire rates.
- **Permitted, not established:** that the console UART is what pins the
  ceiling. Three things are not settled by anything in this repo or by any
  page this pass could fetch. (i) Whether IDF duplicates `stdout` to both the
  primary UART and the secondary USB-Serial-JTAG when
  `CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=y` — the S3's data reaches
  the host over native USB, so the secondary certainly carries it, but
  whether the primary is *also* written is an IDF-internal behaviour this
  pass could not retrieve (`raw.githubusercontent.com` timed out). (ii)
  Whether that UART write blocks the calling task. (iii) What was actually
  flashed: `csi_rx.bin`'s mtime and the sdkconfig target are strong
  circumstantial evidence, no more. The 5.6 % shortfall from 100 % is also
  unexplained; three `fwrite`s plus an `fflush` per frame
  (`telemetry.c:37-40`) is a candidate and is not measured.
- **The check that settles it costs nothing new:** rebuild with
  `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` as the *primary* console and
  re-capture. If the ceiling moves, it was the UART; if it does not, §2.7's
  `emit_ns_accum` ÷ `emit_count` decides between the remaining candidates.
  Either way **`docs/CODE_INVENTORY.md` §1.3 should list three candidates,
  not two**, before an instrumented build is spent on the question.

---

## 5. CHECK 2 — the six cells, three sessions, one pipeline

### 5.1 The table, and the reproduction check

`report` R3, as accepted / **fed**. The denominator is `fed`, matching
`docs/OCCUPANCY_TEST_0822.md` §2.3 — a frame that fails to fit at all is a
reject too, and there are between 0 and 188 of those per cell.

| cell | 2026-08-21 12:50 | 2026-08-22 02:30 (overnight) | 2026-08-22 14:44 |
|---|---|---|---|
| d0wd/B1 | 3.697 % (154,947/160,896) | 7.439 % (817,091/882,760) | 8.180 % (58,259/63,449) |
| d0wd/B2 | 1.337 % (242,497/245,782) | 4.113 % (881,801/919,624) | 11.458 % (69,967/79,021) |
| d0wd/B3 | **43.563 %** (91,075/161,374) | **58.752 %** (486,198/1,178,713) | 6.250 % (93,866/100,124) |
| s3/B1 | 0.379 % (178,973/179,654) | 0.660 % (1,273,925/1,282,394) | 0.984 % (84,353/85,191) |
| s3/B2 | 1.034 % (211,080/213,286) | 0.795 % (823,413/830,010) | **83.037 %** (9,351/55,126) |
| s3/B3 | **12.545 %** (216,920/248,036) | 0.312 % (1,444,535/1,449,060) | 0.290 % (139,761/140,168) |

Every one of the eighteen reproduces its published figure to within
**0.064 pp** (largest disagreement: d0wd/B3 overnight, 58.752 against
58.814):

| source | published | this pass |
|---|---|---|
| `docs/S3_SFO_STEPS.md` §1 (via `OCCUPANCY_TEST_0822.md` §9.1) | 3.70 / 1.34 / 43.54 / 0.37 / 1.03 / 12.53 | 3.697 / 1.337 / 43.563 / 0.379 / 1.034 / 12.545 |
| `docs/OVERNIGHT_2026-08-22.md` §3.1 (via `POSITIVE_CONTROL_0822.md` §1.1) | 7.422 / 4.114 / 58.814 / 0.664 / 0.794 / 0.314 | 7.439 / 4.113 / 58.752 / 0.660 / 0.795 / 0.312 |
| `docs/OCCUPANCY_TEST_0822.md` §2.3 | 8.156 / 11.469 / 6.239 / 0.995 / 83.101 / 0.300 | 8.180 / 11.458 / 6.250 / 0.984 / 83.037 / 0.290 |

The residual is the RANSAC RNG-stream effect measured in §1.1 (bounded there
at 0.095 pp on the same file), not a disagreement about the data. Against the
one document that prints frame counts,
`docs/OCCUPANCY_TEST_0822.md` §2.3: **`fed` matches exactly in 6 of 6 cells**
(63,449 / 79,021 / 100,124 / 85,191 / 55,126 / 140,168); `fitted` differs by
at most 2 frames; 64-frame window counts differ by at most 1 (909 against
910, 1,092 against 1,093, exact in the other four). Those are the same
RNG-stream effect, at the frame level: whether `ransac_line` returns `None`
at all, and which side of a gate a borderline frame lands on, depends on
which 2-point hypotheses were drawn.

`docs/OCCUPANCY_TEST_0822.md` §9.1's statement stands unchanged: three
sessions, three different marginal cells; not a property of a board and not
a property of a beacon.

### 5.2 What operator fact 1 does to the interpretation

With positions identical across all three sessions, the between-session
changes in this table cannot be repositioning. That removes the benign
reading of the RSSI swings the earlier documents flagged:
`docs/OVERNIGHT_2026-08-22.md` §6 warned "do not read the between-session
RSSI change as a receiver-state change — this capture cannot separate the
two." Fact 1 separates them by testimony: on **s3/B1**, RSSI runs
−78.17 → −67.87 → −77.08 dBm across the three sessions, a **10.30 dB**
excursion and return with nothing moved; on **d0wd/B3** it runs
−83.38 → −79.06 → −77.33, a **6.05 dB** monotone improvement with nothing
moved.

So the remaining explanations are the room's contents, the propagation
environment, or the receiver itself — and only the last is instrumented by
V2. **This strengthens §2.5, it does not weaken it.** It is also testimony,
not measurement (`CLAUDE.md` **G**), and `docs/V2_SPEC.md` §2.9 exists
precisely so the next capture does not depend on it.

---

## 6. CHECK 2 — the seven candidates, measured

### 6.1 Per cell, per session

`report` R4. `|CSI|` columns exclude k = +1: the D0WD's k = +1 bin reads
exactly 3.0 counts on every source it hears
(`docs/UNWRAP_DEFECT.md` §2, reproduced here on all nine D0WD cells), so
leaving it in makes "min bin" and any max/min fade depth a measurement of
that dead bin rather than of the channel, and not comparable between boards.
`tilt` is max/min over the remaining 51 bins.

| session | cell | rej % | RSSI | RSSI sd | RSSI acc | RSSI rej | mean\|CSI\| | min | max | tilt | noise_floor | inlier med |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 08-21 | d0wd/B1 | 3.697 | −82.32 | 1.914 | −82.29 | −83.14 | 19.042 | 14.053 | 23.914 | 1.70 | −97.00 | 0.8654 |
| 08-21 | d0wd/B2 | 1.337 | −71.11 | 1.495 | −71.11 | −71.48 | 21.933 | 14.343 | 26.314 | 1.83 | −97.00 | 0.9615 |
| 08-21 | d0wd/B3 | **43.563** | −83.38 | 2.448 | −82.12 | −85.01 | 17.120 | 13.421 | 21.103 | **1.57** | −97.00 | 0.6346 |
| 08-21 | s3/B1 | 0.379 | −78.17 | 1.779 | −78.16 | −81.64 | 12.359 | 10.202 | 14.250 | 1.40 | −94.65 | 0.9231 |
| 08-21 | s3/B2 | 1.034 | −74.07 | 1.692 | −74.06 | −75.32 | 12.113 | 6.171 | 16.908 | 2.74 | −94.61 | 0.9038 |
| 08-21 | s3/B3 | **12.545** | −70.50 | 3.046 | −69.62 | −76.64 | 12.409 | 10.230 | 14.746 | 1.44 | −94.64 | 1.0000 |
| night | d0wd/B1 | 7.439 | −81.60 | 0.858 | −81.58 | −81.74 | 20.027 | 13.359 | 28.037 | 2.10 | −97.00 | 0.7115 |
| night | d0wd/B2 | 4.113 | −79.94 | 0.662 | −79.95 | −79.73 | 19.964 | 9.396 | 28.847 | 3.07 | −97.00 | 0.7885 |
| night | d0wd/B3 | **58.752** | −79.06 | 0.836 | −79.05 | −79.07 | 18.831 | 7.268 | 33.497 | 4.61 | −97.00 | 0.5962 |
| night | s3/B1 | 0.660 | −67.87 | 1.022 | −67.86 | −68.71 | 12.337 | 8.709 | 15.360 | 1.76 | −92.85 | 0.9615 |
| night | s3/B2 | 0.795 | −73.91 | 1.126 | −73.92 | −72.60 | 12.264 | 7.374 | 15.457 | 2.10 | −92.85 | 0.9231 |
| night | s3/B3 | 0.312 | −65.60 | 0.965 | −65.60 | −64.55 | 12.129 | 7.252 | 15.525 | 2.14 | −92.84 | 0.9615 |
| 14:44 | d0wd/B1 | 8.180 | −82.60 | 1.739 | −82.49 | −83.88 | 18.697 | 14.048 | 23.846 | 1.70 | −97.00 | 0.7692 |
| 14:44 | d0wd/B2 | 11.458 | −80.20 | 1.459 | −80.07 | −81.23 | 19.823 | 12.630 | 27.658 | 2.19 | −97.00 | 0.7500 |
| 14:44 | d0wd/B3 | 6.250 | −77.33 | 2.972 | −77.12 | −80.59 | 20.724 | 17.406 | 25.287 | 1.45 | −97.00 | 0.9231 |
| 14:44 | s3/B1 | 0.984 | −77.08 | 1.856 | −77.09 | −76.86 | 12.006 | 9.138 | 14.459 | 1.58 | −92.79 | 0.9038 |
| 14:44 | s3/B2 | **83.037** | −79.77 | 1.335 | −79.72 | −79.78 | 11.391 | 5.397 | 20.390 | **3.78** | −92.79 | **0.4808** |
| 14:44 | s3/B3 | 0.290 | −67.34 | 1.922 | −67.34 | −68.95 | 12.367 | 9.459 | 15.306 | 1.62 | −92.80 | 0.9808 |

Session-level covariates (constant across a node-session's three cells):

| session | node | local start | occupancy | ambient MACs | ambient fps | noise_floor | uptime at t0 (s) |
|---|---|---|---|---|---|---|---|
| 08-21 | d0wd | 12:50:17 | present throughout | 39 | 2.213 | −97.00 | 4,182.495 |
| 08-21 | s3 | 12:50:17 | present throughout | 13 | 1.922 | −94.63 | 1,536.472 |
| night | d0wd | 02:30:34 | empty throughout | 128 | 0.105 | −97.00 | 1,861.107 |
| night | s3 | 02:30:34 | empty throughout | 31 | 0.109 | −92.85 | 470.372 |
| 14:44 | d0wd | 14:44:24 | present except t ∈ [785,920) s | 24 | 0.070 | −97.00 | 2,939.017 |
| 14:44 | s3 | 14:44:24 | present except t ∈ [785,920) s | 12 | 0.070 | −92.79 | 1,548.005 |

"uptime at t0" is the first clean `esp_timestamp_us`, which is a u32 µs
counter wrapping every 4,294.967 s (`docs/V2_SPEC.md` §2.3). **It is uptime
modulo 71.6 minutes, not uptime**, and 4,182.495 s is 97 % of one wrap
period. It cannot distinguish a node up for 70 minutes from one up for
three days. `docs/HANDOFF.md` line 247 records that Heltec uptimes "lie"
because a USB unplug does not reboot the board with the LiPo attached. This
covariate is reported for completeness and should not be leaned on.

### 6.2 The correlations, at three levels

`report` R5, R5a, R5b, R5c. Spearman ρ with a 20,000-draw permutation p.

**Over all eighteen cells (R5), thirteen covariates, Bonferroni threshold
p < 0.003846:**

| covariate | ρ | p |
|---|---|---|
| RSSI mean (cell) | **−0.6388** | **0.00540** |
| RSSI sd (cell) | 0.0093 | 0.971 |
| RSSI variance (cell) | 0.0093 | 0.971 |
| mean \|CSI\| over 52 bins | 0.2900 | 0.244 |
| min bin \|CSI\| | −0.4471 | 0.064 |
| fade ratio mean/min | 0.4097 | 0.092 |
| noise_floor (cell) | −0.4465 | 0.066 |
| ambient MAC count | 0.2100 | 0.410 |
| ambient frames/s | −0.0846 | 0.749 |
| delivered fps (node) | −0.4922 | 0.041 |
| uptime at t0 | 0.5110 | 0.032 |
| hour of day | 0.1705 | 0.506 |
| operator present (1/0) | 0.1590 | 0.557 |

**Nothing clears the threshold.** RSSI comes closest and does not.

**Within each board (R5a).** A covariate that only separates the two boards
is a node-level confound, not a cell-level explanation:

| covariate | all 18 | p | d0wd (9) | p | s3 (9) | p |
|---|---|---|---|---|---|---|
| RSSI mean | −0.6388 | 0.0054 | **−0.3667** | **0.344** | **−0.6167** | **0.088** |
| RSSI sd | 0.0093 | 0.971 | −0.1000 | 0.812 | 0.1833 | 0.644 |
| mean \|CSI\| (excl k=+1) | 0.2900 | 0.244 | −0.6833 | 0.051 | −0.4167 | 0.269 |
| min \|CSI\| (excl k=+1) | 0.1600 | 0.530 | −0.5833 | 0.108 | −0.2833 | 0.460 |
| band tilt max/min | 0.2446 | 0.327 | 0.1667 | 0.678 | 0.2833 | 0.461 |
| noise_floor | −0.4465 | 0.066 | *no variance* | — | 0.0500 | 0.915 |

RSSI's whole-set significance does not survive being asked inside either
board. `noise_floor` on the D0WD has **zero variance** — it reads exactly
−97.00 on all nine cells across all three sessions — while D0WD reject rate
spans 1.337–58.752 %. A constant cannot explain a variable.

**Node-level covariates at the honest n (R5b).** Seven of the thirteen are
constant across a node-session's three cells, so treating eighteen cells as
independent is wrong for them; the effective n is **6**. Against each
node-session's worst and mean cell:

| covariate | ρ vs worst | p | ρ vs mean | p |
|---|---|---|---|---|
| ambient MAC count | −0.0857 | 0.922 | −0.0286 | 1.000 |
| ambient frames/s | −0.3143 | 0.562 | −0.4857 | 0.353 |
| delivered fps | −0.1429 | 0.811 | −0.4286 | 0.421 |
| noise_floor (node) | 0.0911 | 0.884 | −0.0304 | 1.000 |
| uptime at t0 | 0.3143 | 0.560 | 0.4857 | 0.355 |
| hour of day | 0.2390 | 0.713 | 0.3586 | 0.537 |
| operator present | 0.2070 | 0.800 | 0.2070 | 0.795 |

**Nothing is within reach of significance.** The apparent p = 0.032 for
uptime and p = 0.041 for delivered fps in R5 are artefacts of counting six
values eighteen times.

**Against the movement itself (R5c).** The question is not "which cells
reject" but "why the marginal cell moves". Each of the six cells is followed
across the three session pairs — eighteen changes — and the change in reject
rate is tested against the change in each covariate. Six covariates,
Bonferroni threshold p < 0.0083:

| change in | ρ | p |
|---|---|---|
| band tilt max/min | +0.5418 | 0.021 |
| mean \|CSI\| | −0.5377 | 0.022 |
| RSSI mean | −0.5191 | 0.028 |
| min \|CSI\| | −0.4840 | 0.044 |
| noise_floor | −0.1753 | 0.490 |
| RSSI sd | −0.1228 | 0.626 |

The top four are collinear — they are four ways of measuring how strong and
how flat the link is — and none clears the threshold. Selecting the largest
and presenting it would be `CLAUDE.md` failure mode **A**.

### 6.3 Each candidate has a counterexample inside the data

Correlation aside, each candidate can be killed by a pair of cells:

- **RSSI.** On the S3 on 2026-08-22 14:44, B3 at **−67.34 dBm** rejects
  0.290 % and B1 at **−77.08 dBm** rejects 0.984 % — a **9.74 dB** spread
  buys **0.69 pp**. In the same session on the same board, B2 at
  **−79.77 dBm**, only **2.69 dB** below B1, rejects **83.037 %**. On
  2026-08-21 the D0WD's B1 at −82.32 dBm rejects 3.697 % while its B3 at
  −83.38 dBm — **1.06 dB** lower, same board, same session — rejects
  **43.563 %**, 11.8× as much.
- **RSSI variance.** ρ = 0.009, p = 0.97 over eighteen cells — the flattest
  of all thirteen. The three marginal cells' RSSI sds are 2.448, 0.836 and
  1.335, spread across most of the range the whole table shows (0.662 to
  3.046). The cell holding the **largest** RSSI sd of all eighteen (s3/B3 on
  08-21, 3.046) also holds the **highest** median inlier ratio in the table,
  1.0000 — and still rejects 12.545 %, which is its own small puzzle and is
  noted rather than explained here.
- **Per-bin amplitude / fade.** Tilt does not order reject rate anywhere in
  the table. **d0wd/B3 rejects 43.563 % at tilt 1.57 and 6.250 % at a
  *flatter* tilt of 1.45** — the same cell, the same board, a 7× difference
  in the direction opposite to the hypothesis. Taking the four flattest cells
  in the whole table in order — tilt 1.40, 1.44, 1.45, 1.57 — their reject
  rates run **0.379 %, 12.545 %, 6.250 %, 43.563 %**: no order at all.
  d0wd/B2 overnight at tilt 3.07 rejects 4.113 % and s3/B3 overnight at tilt
  2.14 rejects 0.312 %. The 83 % cell *does* sit in
  the second-strongest tilt in the table (3.78: a monotone fall from ≈20
  counts at the low band edge to 5.4 at k = +5, then a partial recovery to
  11.9 at k = +26) — but the strongest tilt of all, d0wd/B3 overnight at
  4.61, rejects 58.752 %, and the same S3 cell a day earlier at tilt 2.74
  and min 6.171 produced **1.034 %**.
- **`noise_floor`.** Constant at −97.00 across every D0WD cell in every
  session (§6.2), which is also `docs/OCCUPANCY_TEST_0822.md` §2.2's finding
  of zero transitions on 242,718 clean rows. The D0WD's marginal cell moved
  anyway.
- **Operator presence.** §6.4.
- **Time of day.** §6.5.
- **Ambient MAC population and channel activity.** ρ = −0.086 to +0.210 over
  eighteen, ρ = −0.486 to −0.029 at n = 6. The overnight session has the
  **most** ambient MACs (128 on the D0WD) and the **least** ambient traffic
  (0.105 fps) — the two proxies point in opposite directions, and
  `docs/OVERNIGHT_2026-08-22.md` §5.3 establishes that 100 of the D0WD's 131
  overnight MACs are decode artefacts, so the count is partly a measure of
  corruption rather than of the air.
- **Receiver uptime at session start.** ρ = +0.314 (p = 0.56) at n = 6, on a
  quantity that is uptime modulo 71.6 minutes (§6.1).

### 6.4 Operator presence, tested inside one session

`report` R6. The 14:44 session contains a located 135 s absence,
t ∈ [785, 920) s (`docs/OCCUPANCY_TEST_0822.md` §0, §5.3). Reject rate
inside against outside:

| cell | rej % absent | n | rej % present | n | Δ pp |
|---|---|---|---|---|---|
| d0wd/B1 | 4.378 | 4,637 | 8.478 | 58,811 | −4.100 |
| d0wd/B2 | 3.561 | 6,122 | 12.118 | 72,897 | −8.558 |
| d0wd/B3 | 12.287 | 4,867 | 5.937 | 95,252 | +6.350 |
| s3/B1 | 0.888 | 6,303 | 0.991 | 78,888 | −0.103 |
| s3/B2 | **98.510** | 4,430 | **81.685** | 50,695 | **+16.826** |
| s3/B3 | 0.678 | 9,736 | 0.261 | 130,432 | +0.416 |

Three cells go up, three go down. There is no coherent presence effect, and
the marginal cell is not switched on or off by it: s3/B2 rejects 81.7 % with
the operator in the room. Its +16.8 pp is the largest single move and is
worth noting — the empty-room stretch is its worst — but three of six signs
disagree and the window is 135 s.

### 6.5 Time of day, and whether the afternoons resemble each other

`report` R7. L1 distance between the six-cell reject vectors:

| pair | L1 | rank corr |
|---|---|---|
| 08-21 12:50 ↔ 08-22 02:30 (afternoon ↔ overnight) | **34.460 pp** | +0.4286 |
| 08-21 12:50 ↔ 08-22 14:44 (afternoon ↔ afternoon) | **146.778 pp** | −0.3143 |
| 08-22 02:30 ↔ 08-22 14:44 (overnight ↔ afternoon) | 143.175 pp | +0.4286 |

**The two afternoon sessions are the most dissimilar pair of the three, by a
factor of 4.3.** The most similar pair is an afternoon session and the
overnight one. Time of day is not it, and the hypothesis fails in the
direction opposite to the one proposed.

---

## 7. What the marginal cell actually is, mechanically

`report` R9, per-frame over every fitted frame in all six files:

**Of 8,274,369 fitted frames across 18 cells, `resid_std > 0.8`
(`dsp.py:164,175`) rejected 0. Zero. In 18 of 18 cells.** Every rejection,
in every cell, in every session, is `inlier_ratio < 0.6`
(`dsp.py:164,173`), and the two gates never co-fire because one of them
never fires.

Two consequences, stated at the width the measurement supports.

- **`resid_std <= 0.8` is inert at this threshold on this hardware.** It has
  never rejected a frame in 8.27 M. If it is meant as a safety net it is not
  catching anything, and `docs/V2_SPEC.md` §5.5 ("anything that changes the
  SFO estimator" is out of scope) should be read knowing that one of the two
  shipped gates is currently a no-op.
- **"Reject rate went up" never means "`resid_std` crossed 0.8".** Where a
  document reports `resid_std` and reject rate moving together —
  `docs/S3_SFO_STEPS.md` §7 states the relation and
  `docs/OCCUPANCY_TEST_0822.md` §0 invokes it — reject rate is measuring
  `inlier_ratio` and only `inlier_ratio`. Whether the two continuous series
  are independent evidence is a separate question that this pass did not
  test; what it did establish is that the reject-rate series is not a
  restatement of the `resid_std` **gate**, because that gate never fires.

Mechanically, then, the marginal cell is a cell where RANSAC cannot gather
60 % of the 52 usable subcarriers onto one line within ±0.30 rad
(`dsp.py:71`), while the residual of whatever line it does find stays
normal — s3/B2 at 14:44 has median inlier ratio **0.4808**, below the gate,
with median `resid_std` **0.1568**, unremarkable against a 0.8 threshold and
against its siblings' 0.1453 and 0.1305. The phase is not noisy. It is not
*linear*.

This pass did not test what makes it non-linear. The obvious next
measurement is `docs/HANDOFF.md` open thread 2's residual-vector feature —
the per-subcarrier residual shape that the current pipeline discards — run
on the marginal cells specifically. It runs against data already on disk.

---

## 8. Established / permitted / unknown

**Established by this pass, from these files and this code.**

- `display_task` is created only when `oled_init()` returns `ESP_OK`
  (`main.c:302-307`); with nothing acknowledging at 0x3C it is never created
  and issues no I²C transaction (§2.1). The single failing transaction
  precedes the radio, the queue and the CSI callback, so it cannot
  contribute to `s_dropped` (§2.2).
- The 250 ms fold specified by §7(a)2, run on the file §7(a)2 names, is null:
  R̄ = 0.002393 against a rotation-null p95 of 0.002645, p = 0.094, over
  624,290 drops, with an effect-size ceiling of m ≈ 0.005 (§3.2).
- Four of the other five captures are also null (p = 0.48 to 0.92).
- `s3_20260822_144424` carries real periodic structure whose **fundamental is
  1000 ms**, with 250 and 500 ms as its subharmonics (§3.3), in the drop
  process and not in the arrival process.
- Nothing in `firmware/` runs at 1000 ms; the periods present are 250 ms
  (conditional), 5,000 ms (twice), and a 250 ms empty-queue timeout (§3.4).
- All eighteen node × beacon × session reject rates, from one pipeline,
  reproducing every published figure to ≤ 0.064 pp, with `fed` matching
  exactly in the 6 cells any document prints it for (§5.1).
- Over those eighteen, no covariate survives multiple-comparison correction;
  RSSI's whole-set ρ = −0.639 collapses within each board; node-level
  covariates at the honest n = 6 reach p ≥ 0.35; and against the movement
  itself the best correlate is band tilt at p = 0.021 against a 0.0083
  threshold (§6.2).
- Each of the seven candidates is either flatly null across all three tests
  or has a direct counterexample inside the data (§6.3).
- The two afternoon sessions are the **most dissimilar** pair of the three
  (§6.5).
- `resid_std > 0.8` rejected **0 of 8,274,369** fitted frames (§7).
- The S3's mean on-wire delivered rate is 94.44 % and 94.38 % of a
  460,800 baud 8N1 budget in its two pinned sessions; the D0WD never exceeds
  84.00 % (§4.2).

**Permitted, not established.**

- That the console UART at 460,800 baud is what pins the S3 at ~154 fps
  (§4.3). Consistent with every measurement here; three separate links in
  the chain are unverified.
- That the 1 Hz source in `s3_20260822_144424` is host-side. The D0WD in the
  same `pc/capture.py` process shows nothing, which argues against it, but
  that node lacks the power to have seen it (§3.5).
- That an unmeasured receiver-state change explains the between-session RSSI
  swings. Operator fact 1 removes repositioning, which strengthens
  `docs/V2_SPEC.md` §2.5's hypothesis without testing it (§5.2).
- That the marginal cell is a non-linearity in the phase-versus-subcarrier
  relation rather than noise. The gate attribution and the
  inlier-median-versus-`resid_std`-median split in §7 are consistent with it
  and with nothing else this pass measured, but no residual-shape statistic
  was computed.

**Unknown.**

- What runs at 1 Hz, and why it appears in that capture and not in the other
  five. Detecting R̄ = 0.0422 at p < 0.05 needs a rotation-null p95 below it,
  and **four of the five other captures clear that bar** (null p95 0.0026 to
  0.0171) and show nothing; only `d0wd_20260822_144424`, at 0.0511, could not
  have seen it (§3.5). So this is not simply a power story — but neither is
  the source named.
- Which of `oled_init`'s three failure points fired, and whether a panel is
  physically wired to GPIO 21/22 at all (§2.4).
- What was actually flashed to either board for any of these six captures.
  `csi_rx/build/csi_rx.bin` (2026-08-21 12:22, target `esp32s3`) and
  `sdkconfig` (12:20) are circumstantial.
- **What the display path costs when it runs.** No capture in `data/raw/`
  was taken on a node with a working panel, so §7(a)2's experiment has never
  been performed and cannot be performed on these files.
- Why the marginal cell moves.

---

## 9. What would settle the rest, in cost order

1. **A one-line rebuild for the ceiling.** Make USB-Serial-JTAG the primary
   console and re-capture 10 minutes. If the S3's delivered rate leaves
   154 fps, §4's candidate is the answer and no instrumented build is needed
   for §7(a)2's other half. Costs one flash.
2. **Residual-shape statistics on the marginal cells.** For each of the
   eighteen cells, the per-subcarrier RANSAC residual vector — mean shape,
   which k are outliers, whether the outliers are contiguous. Runs against
   data already on disk and would say whether the 83 % cell fails at the band
   edges, at one bin, or everywhere. This is `docs/HANDOFF.md` open thread 2
   pointed at a different question.
3. **`display_enabled` and the run-time disable** (`docs/V2_SPEC.md` §2.7
   part 3). Until a node exists that can be run with and without the display
   on otherwise identical conditions, §7(a)2 is unanswerable by any amount
   of reanalysis. This pass's null does not change that and should not be
   read as reducing the priority of §2.7.
4. **A capture with a panel actually attached**, on the pins the Heltec
   uses, which are still not recorded in this repo (§2.4,
   `docs/S3_PORT_SCOPE.md:132-137`).
5. **`agc_gain` per frame** (`docs/V2_SPEC.md` §2.5). §5.2 makes this more
   urgent, not less: with repositioning ruled out by testimony, a 10.30 dB
   RSSI excursion and return on one link has no measured explanation at all.

---

## 10. Figures in this document that should not be quoted alone

- **"m = 0.0845 at 250 ms on the S3"** — only with §3.3 attached. Its
  fundamental is 1000 ms; quoting the 250 ms number alone reproduces exactly
  the confusion §7(a)2 was written to avoid.
- **"p = 0.094, therefore the OLED is exonerated."** No. The board was
  headless (§2.1), so the null is the expected result and carries no
  information about a working display (§3.7).
- **"RSSI correlates with reject rate at ρ = −0.639, p = 0.005."** Only with
  §6.2's within-board collapse and §6.3's counterexamples. On its own it is
  a between-board difference wearing a cell-level label.
- **"reject rate"** — across these six captures it is `inlier_ratio < 0.6`
  and nothing else; the `resid_std` gate never fired (§7). That is measured
  on 8.27 M frames from these files, not proved for the pipeline in general.
- **"uptime at session start"** — it is uptime modulo 71.6 minutes (§6.1).
- **The 94.44 % / 94.38 % UART figures** — only with §4.3's three unverified
  links.
- **Anything in §5.2 that depends on operator fact 1** — it is testimony,
  recorded as testimony, and `docs/V2_SPEC.md` §2.9 exists because no file in
  `data/raw/` can check it.
