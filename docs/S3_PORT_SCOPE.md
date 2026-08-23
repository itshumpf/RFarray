# Scope — running `csi_rx` on an ESP32-S3 alongside the D0WD collector

**Date:** 2026-08-21 · **Type:** read-and-report scope study, no port started
· **Method:** read `firmware/`, `pc/`, `docs/`, and measured `data/raw/`
directly. No file outside this one was created or modified; no hardware was
touched; nothing was staged or committed.

Every figure below is either (a) a line of code in this repo, cited by file
and line; (b) a measurement I ran in this session against `data/raw/`, with
the command shown; or (c) explicitly labelled **UNKNOWN**. Where an existing
document is the source, it is named. Where nothing in the repo settles a
question, that is said rather than filled in.

---

## 0. Provenance of the premise, before anything else

Three facts were handed to me as established. Two of them I can locate in
the repo. One I cannot.

| premise | status in the repo |
|---|---|
| D0WD UART saturated at 460800 with 3 beacons; 1,014 samples dropped, 348,716 resync bytes in 60 s | **Not recorded in any file.** `pc/diagnose.py` (mtime 2026-08-21 10:42) computes resync-byte and drop accounting, so the tool exists; the result is not written down anywhere I can find. |
| Heltec S3 sustained **675 KB/s** over native USB-Serial-JTAG, link-bound, zero loss across 20.7 MB | **Not recorded, and the newest artifact in the repo contradicts it.** `firmware/s3_throughput/README.md` (mtime 2026-08-21 11:25 — the most recently modified file in the tree) is headed "**State: builds, not yet flashed, never run**" and states at line 26: "No byte of this has run on the board, and no number it produces has been checked against anything." |
| Bandwidth is therefore solved | Follows from the second premise, and inherits its status. |

I am treating all three as given, as instructed. But `CLAUDE.md` failure mode
**A** ("every number must be re-derivable right now by a command you can
name") and **H** ("check whether a later artifact supersedes memory") both
apply here in the unusual direction: the *later* artifact is the one that
says the run never happened. Either `README.md` is 20 minutes stale, or the
675 KB/s figure came from somewhere other than this repo. **Before this scope
is used to justify spending time, write the throughput result into
`firmware/s3_throughput/README.md` and correct the "never run" heading.**
Otherwise the next session will read that heading and correctly refuse to
believe the bandwidth premise.

One further piece of context that is *not* a premise and that bears on
everything below: the Heltec S3 in question, `8c:fd:49:b7:b0:6c`, has
**never contributed a frame to this project** — zero occurrences across all
62 files in `data/raw/` (`docs/NODE_CENSUS.md` §3.5, P8;
`docs/LOT_HYPOTHESIS.md` §3.1). `docs/HANDOFF.md` line 33 records "RX works;
WiFi TX inaudible", and open thread #3 (lines 209–222) elaborates "RX path
works (hears beacons at −71)". **That RX observation has no artifact.** No
CSV, log, or capture in this repo shows the S3 receiving anything. It is a
recollection, and it is the single load-bearing assumption of this whole
idea.

---

## 1. Chip-specific coupling in `firmware/csi_rx/`

`csi_rx` is four translation units: `main/main.c`, plus `common/telemetry`,
`common/calibration`, and `common/node_hal` (which carries `ssd1306.c`).
`firmware/csi_cfo/main/main.c` differs from `csi_rx/main/main.c` in exactly
three places — the header comment, `RFF_PROMISCUOUS 0`, and a non-zero
`TX_FILTER_MAC` — so everything in this section applies to both.

### 1.1 Portable as-is

**`common/telemetry`** — the entire output path is chip-agnostic.
`telemetry.c:37-40` writes the frame with `fwrite(...)`/`fflush(stdout)`.
It never names a UART, a baud rate, or a peripheral. Whatever `sdkconfig`
points `stdout` at is where the telemetry goes. On S3 that means
`CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` moves the whole stream to native USB
**with no source change** — this is exactly the line
`firmware/s3_throughput/sdkconfig.defaults:10` already uses. The header
builder (`telemetry.c:14-41`) is byte-oriented little-endian with an explicit
`put_u16`/`put_u32`, so it is endian- and packing-independent.

**`common/calibration`** — `calibration.c` uses only `esp_timer_get_time()`
and float EMAs. Nothing chip-specific.

**`main.c` CSI configuration** — `csi_init()` at `main.c:267-281` builds a
`wifi_csi_config_t` with seven designated initialisers (`lltf_en`,
`htltf_en`, `stbc_htltf2_en`, `ltf_merge_en`, `channel_filter_en`,
`manu_scale`, `shift`). I fetched Espressif's own header at the closest
published tag, `esp-idf v5.5.1`,
`components/esp_wifi/include/local/esp_wifi_types_native.h`: for every target
*without* `CONFIG_SOC_WIFI_HE_SUPPORT` — which includes ESP32, S2 and S3 —
`wifi_csi_config_t` is that same struct plus one extra field, `dump_ack_en`.
Targets *with* HE support (C5/C6/C61) get `wifi_csi_acquire_config_t`
instead, which is a different struct entirely.

`CONFIG_SOC_WIFI_HE_SUPPORT` does **not** appear in
`firmware/csi_tx/build_s3/sdkconfig` (a real, generated esp32s3 config in
this tree) while `CONFIG_SOC_WIFI_CSI_SUPPORT=y` does, at line 372.
**Conclusion: `csi_init()` compiles unchanged on esp32s3, and designated
initialisation zero-fills `dump_ack_en` to the correct default.** This is the
single largest thing that could have made the port a rewrite, and it does not.

**`main.c` metadata reads** — `main.c:124-127` reads `info->rx_ctrl.rssi`,
`.noise_floor`, `.channel`, `.timestamp`. All four field names exist in the
S3 branch of `wifi_pkt_rx_ctrl_t` in the same header; only their bit offsets
within the struct differ between ESP32 and S3, which the compiler handles.

**ESP-NOW** (`main.c:311-312`, `espnow_recv_cb` at `main.c:94-106`) — no
chip-specific API. The `esp_now_recv_info_t` signature is IDF-version-bound,
not target-bound, and both builds are on the same IDF (5.5.4;
`firmware/csi_rx/sdkconfig:253`, `firmware/csi_tx/build_s3/project_description.json` `"git_revision": "v5.5.4"`).

**Queue and drain** — `s_csi_queue` (`main.c:314`), `csi_sample_t`
(`main.c:72-81`, 384-byte `int8_t buf`), `csi_drain_task` (`main.c:165-184`).
Pure FreeRTOS. `QUEUE_DEPTH 64` × `sizeof(csi_sample_t)` ≈ 26 KB of internal
DRAM; the S3 has more, not less. **Portable.**

**`s_latest_seq`** (`main.c:84`, written at `main.c:103`, read at
`main.c:122`) — a `volatile uint32_t`, no chip coupling. It has a
*correctness* problem that is not a porting problem and is discussed in §5.3.

### 1.2 Assumes ESP32-D0WD, and will misbehave silently

**The safe-boot diagnostic console is the concrete breakage.**
`hal_diag_console()` (`node_hal.c:132-201`) hard-codes `UART_NUM_0`:
`uart_wait_tx_idle_polling(UART_NUM_0)` at line 136,
`uart_set_baudrate(UART_NUM_0, DIAG_BAUD)` at 137,
`uart_driver_install(UART_NUM_0, ...)` at 139, and
`uart_read_bytes(UART_NUM_0, ...)` at 160. If the console moves to
USB-Serial-JTAG, this code compiles and runs and talks to a UART peripheral
nobody is attached to. The node will appear to hang at boot with BOOT held
low, and there is **no way to set `node_id`/`env_id`/`cal_seconds` on that
board** (`hal_identity_save`, `node_hal.c:82-88`, is only reachable through
this console). Not fatal to capture; fatal to field configuration.

**`sdkconfig.defaults` pins D0WD console pins.**
`firmware/csi_rx/sdkconfig.defaults:11-12` sets
`CONFIG_ESP_CONSOLE_UART_TX_GPIO=1` / `RX_GPIO=3`. Those are the ESP32
DevKit UART0 pins. An S3 build needs its own defaults file — the
`build_s3/` + `sdkconfig.defaults.s3` split `csi_tx` already uses
(`docs/HANDOFF.md` lines 251-253), not an edit to the existing file.

**OLED pins.** `main.c:62-63` sets `OLED_SDA 21`, `OLED_SCL 22`. These are
DevKit-convention pins, not Heltec V3 pins; the Heltec's own I²C OLED wiring
is documented by Heltec and **is not recorded anywhere in this repo**.
Consequence is bounded: `oled_init()` returns an error rather than aborting
(`ssd1306.c` `oled_init` returns `err` from `i2c_new_master_bus`), and
`main.c:302-307` treats that as non-fatal and runs headless. So this is
cosmetic — but the S3 build will be headless until the pins are corrected,
and the on-board status display is how `docs/HANDOFF.md`'s working style
("flash → live census at the collector") normally gets its first signal.

**`SAFE_BOOT_PIN 0`** (`main.c:51`) — GPIO0 is the boot strap on both parts,
but the Heltec's BOOT/RST button behaviour is the subject of its own gotcha
list (`docs/HANDOFF.md` line 249-253: pull the LiPo, `--no-stub`, manual RST
after flash, manual download = hold BOOT + tap RST). Whether the 500 ms
sample window at `main.c:52` interacts sanely with that sequence is
**UNKNOWN** and only a flash will tell.

**Node identity derives from the WiFi MAC.** `node_hal.c:72-73` defaults
`node_id` to `mac[5]`. The D0WD collector's is `68` on all 10,342,823
era-B/C rows (`docs/NODE_CENSUS.md` §1, P10). The Heltec's MAC is
`8c:fd:49:b7:b0:6c`, so its default `node_id` would be `0x6c` = **108**.
That is a genuinely useful accident: the two receivers self-distinguish in
the `node_id` column with no configuration. It also means **the era-B/C
`node_id = 68` constant stops being a constant**, and anything that assumed
it is one should be re-checked.

### 1.3 Outright unavailable on S3

I found nothing in `csi_rx` that is unavailable on esp32s3. `driver/i2c_master`,
`driver/gpio`, `driver/uart`, `esp_task_wdt`, `esp_timer`, `nvs_flash`,
`esp_now`, `esp_wifi` promiscuous mode and `esp_wifi_set_csi*` are all
present for that target in IDF 5.5.4.

### 1.4 The two risks that are neither "portable" nor "broken"

**(a) `CONFIG_SOC_WIFI_PHY_NEEDS_USB_WORKAROUND=y`** —
`firmware/csi_tx/build_s3/sdkconfig:375`. This flag exists for esp32s3 and
does **not** appear in `firmware/csi_rx/sdkconfig` for esp32. Its presence is
IDF's own statement that the S3's WiFi PHY and its USB peripheral interact
and that a software workaround is applied. **What that workaround costs when
USB is running near link saturation while the radio is receiving at 140 fps
is exactly the question this whole plan turns on, and nothing in this repo or
in the vendor page I fetched quantifies it.** UNKNOWN, and only measurable on
hardware. It is also a plausible mechanism for open thread #3's "WiFi TX
inaudible" symptom, which is worth noting but is not evidence.

**(b) The watchdog vs. USB backpressure.** `csi_drain_task` feeds the task
watchdog (`main.c:170`, `hal_watchdog_feed`) and then blocks inside
`tlm_send_csi` → `fflush(stdout)` (`telemetry.c:40`). `WDT_TIMEOUT_MS` is
10,000 (`main.c:56`) and `trigger_panic = true` (`node_hal.c:213`), so a
10-second stall in the write path hard-resets the node. On the S3 the write
path is a USB endpoint whose backpressure behaviour is, per
`firmware/s3_throughput/README.md` lines 150-155, **still unverified** ("the
whole design rests on `usb_serial_jtag_write_bytes(..., 0)` returning 0 when
the ring is full, rather than discarding"). `s3_throughput/sdkconfig.defaults`
disables both idle-task WDT checks and its README line 139 says in terms:
"**Do not copy those two watchdog lines into `csi_rx`**". So the mitigation
that made the throughput test work is explicitly off-limits here, and no
replacement has been designed.

---

## 2. CSI format — what is measured, and what is not

### 2.1 What the D0WD emits today (measured this session)

I read `data/raw/desk_20260713_104513.csv` directly: 5,000 consecutive frames
from the reference beacon `a4:f0:0f:77:91:20`.

- **Beacon frames are 256 bytes**, uniformly. `len_hist` in
  `data/fingerprints/a4f00f779120.json` is `{"256": 1996729}` — 1,996,729
  frames, no other length. `docs/NODE_CENSUS.md` §2 reports 100% len-256 for
  all three beacons across 14,986,846 frames.
- 256 int8 = **128 complex pairs**, stored **imag, real** (`dsp.py:52`
  `iq[1::2] + 1j*iq[0::2]`; `main.c:147-148` reads the same order).
- **Pairs 0–63 are the LLTF.** Pairs **27–37** are zero in >90% of frames
  (measured; 0 in 4,994/5,000 per `PROJECT_NOTES.md` line 92, which I
  reproduced independently). Under `dsp.py`'s FFT-order map (`dsp.py:33`)
  that set is exactly `k = +27..+31, −32..−27` — the 20 MHz guard band.
  **The documented layout at `dsp.py:22-26` holds.**
- **Pairs 64–127 are a second field with a narrower null set**: mean |value|
  collapses at pairs 93–99 (1.31, 1.82, 1.97, 1.21, 0.50, 0.25, 0.92 against
  ~35–65 elsewhere), i.e. relative indices 29–35 = `k = ±29..31, −32`. A
  narrower guard band on the second field is what HT-LTF looks like next to
  LLTF, and 64 LLTF + 64 HT-LTF complex pairs = 256 bytes, which matches
  `csi_init()`'s `lltf_en` + `htltf_en` (`main.c:270-271`).
- **The first word of each field is not channel data.** Mean |value| is 99.0
  at pair 0 and 3.0 at pair 1, against ~32–36 for pairs 2–26; the same step
  appears at pair 64 (2.09) vs pair 65 (65.4). `wifi_csi_info_t` carries a
  `first_word_invalid` flag for exactly this, and **`csi_rx` never reads it**
  (`main.c:109-134`). `dsp.py` drops pair 0 as DC but **keeps pair 1**
  (`k = +1` is inside `_USABLE_MASK`, `dsp.py:35`). One bin in 52, fed to a
  RANSAC fit that exists to reject outliers — small, and pre-existing, but
  it is an untested assumption that would need re-testing on any new part.
- Ambient non-HT devices emit **128** bytes (LLTF only) and at least one
  device emits **384** (`data/fingerprints/f46942f2d2af.json`, `{"384": 129}`).
  `CSI_BUF_MAX` is 384 (`main.c:45`), so 384 is the truncation ceiling, not a
  measured maximum.

### 2.2 What the host assumes

The transport parser is **already length-agnostic**. `pc/rff/protocol.py`
carries the CSI payload as a variable-length list (`protocol.py:125`) with
`len = length - 15` (`protocol.py:123`) and a single ceiling
`CSI_MAX = 384` (`protocol.py:31`, checked at `protocol.py:92-93`). **No
change is needed in `protocol.py` for a different CSI length**, as long as it
stays ≤ 384.

Everything above the transport does assume the layout. The complete list:

| site | assumption |
|---|---|
| `pc/rff/dsp.py:30-40` | **The canonical map.** `N_CPLX = 64`; FFT-order `_K_OF_IDX`; usable = `1 ≤ |k| ≤ 26`; `SUBCARRIER_SPACING_HZ = 312500.0`. |
| `pc/rff/dsp.py:49-52` | Returns `None` for any frame shorter than 128 ints. |
| `pc/occ/ingest.py:41,45-46` | Imports `K_USABLE`/`_USABLE_IDX` from `rff.dsp` — comment calls it the "frozen, validated LLTF mapping". One place to change, two pipelines affected. |
| `pc/fingerprint.py:33,49-51` | `N_SC = 64`; truncates to `vals[:128]`; **the amplitude template is per-buffer-index**, so a layout change silently invalidates all 13 files in `data/fingerprints/`. |
| `pc/live_view.py:22,84` | `N_SC = 64`, `vals[:128]`. Display only. |
| `pc/capture.py:24-33` | `compute_cfo` builds complex as `iq[0::2] + 1j*iq[1::2]` — **the opposite I/Q convention to `dsp.py:52`**. Display only (`capture.py:83,158`), but it is a second, inconsistent convention in the tree. |
| `pc/phase_skew.py:29-31` | `USABLE = np.r_[6:32, 33:59]`, "skip DC(32)" — **assumes shifted/natural subcarrier order, not FFT order.** A third convention, inconsistent with `dsp.py`. Labelled experimental in its own docstring, but it is the file a future session is most likely to reach for. |
| `pc/node_census.py:55,90,222` | `BEACON_MIN_LEN256 = 0.999` and a literal `if ln == 256`. **A receiver emitting any other length stops classifying beacons as beacons.** `pc/diagnose.py:34-35` inherits this. |
| `pc/exp_window_convergence.py:125,136-139` | `CSI_KEEP = 128`, and raises if any value falls outside int8 — "assumes the documented int8 LLTF layout". |

### 2.3 What an S3 would emit — UNKNOWN

I will not state a byte count. Here is precisely what is and is not known:

**Known:** `CONFIG_SOC_WIFI_CSI_SUPPORT=y` for esp32s3 in this IDF
(`firmware/csi_tx/build_s3/sdkconfig:372`). The configuration struct is the
same (§1.1), so the same fields are being *requested*.

**Not known, and not inferable from this repo:** the number of bytes the S3
returns in `wifi_csi_info_t.len` for a 20 MHz HT frame; whether the buffer is
FFT-ordered the same way; whether the imag/real interleave order is the same;
whether `first_word_invalid` is set on S3 when it is not on ESP32; whether
`ltf_merge_en` behaves identically. The repo contains **zero bytes of S3 CSI**
(`docs/NODE_CENSUS.md` P8). Espressif's `esp32s3` WiFi API guide, which I
fetched, does not document the buffer layout.

**The measurement that settles it, completely, in one run:** flash an
S3 with `csi_rx` (or a stripped variant), point it at the running reference
beacon on channel 6, capture ~5,000 frames with `pc/capture.py`, and read the
`len` column and the per-index mean magnitude of `csi_data`. That single
capture answers all five sub-questions at once: the length, the null-bin
positions (which give the ordering *and* the guard band), the field boundary,
and the first-word artifact. It is the same analysis I ran against the D0WD
data above and it takes minutes. **Nothing else in this document should be
acted on before that capture exists.**

---

## 3. The CFO/SFO pipeline and its dependence on layout

### 3.1 Where the estimation lives

`pc/rff/dsp.py`, and nowhere else in the production path.
`FrameEstimator.feed` (`dsp.py:120-153`) does the whole job:

1. `csi_to_complex` (`dsp.py:43-52`) — first 128 ints → 64 complex, FFT order.
2. `np.angle(csi[_USABLE_IDX])` (`dsp.py:130`) — select and re-sort the 52
   usable bins by physical `k`.
3. `unwrap_continuity` (`dsp.py:55-68`) — unwrap across subcarriers, then pin
   to the previous frame's mean.
4. `ransac_line(K_USABLE, ph)` (`dsp.py:132`) — fit `phase = slope·k + intercept`
   against the **physical subcarrier index**.
5. **SFO** = `slope`, in rad per subcarrier.
6. **CFO** = `(intercept − prev_intercept) / (2π·dt)` (`dsp.py:138-143`), from
   the *time* derivative of the common phase.

`WindowAggregator` (`dsp.py:156-195`) takes medians over 64 frames.
`pc/twin_probe.py:62` and `pc/rff_live.py:41` both import this module rather
than reimplementing it, so there is one estimator, not several.

### 3.2 Does it depend on the subcarrier layout? Answer, split in two

**CFO: no.** It is a finite difference of the RANSAC *intercept* over time
(`dsp.py:139-143`). The intercept is the common phase; changing which bins
enter the fit changes its variance, not its meaning. `dt` comes from
`rx_ctrl.timestamp` (`main.c:127`), which is microseconds on both parts.
**A layout change re-points CFO. It does not need re-deriving.**

**SFO: yes, and this is the one that matters.** The slope's units are
*radians per subcarrier index*, and the index is `K_USABLE` — a hard-coded
array built at `dsp.py:33-37` from the ESP32's FFT ordering. Three distinct
ways an S3 layout change breaks it:

1. **Wrong `k` for a bin** — if the buffer is in a different order, `_USABLE_IDX`
   selects the wrong bins and `K_USABLE` labels them with the wrong `k`. The
   fit still returns a number. It is not the same physical quantity.
2. **Wrong span** — if the usable set is wider or narrower, the slope is fitted
   over a different lever arm. RANSAC's `inlier_thresh = 0.30` and the `n < 8`
   guard (`dsp.py:71,82`) are tuned to 52 bins.
3. **Scale, not just noise.** `docs/HANDOFF.md` lines 127-129 is explicit:
   "**CFO is aliased at 100 Hz beacon rate (Nyquist ±50 Hz) → SFO slope is the
   discriminating feature.**" The discriminator's variance floor is
   `[1.0, 1e-8]` (`discriminator.py:27`) — 1 Hz² for CFO, 1e-8 (rad/sc)² for
   SFO. Every separation figure this project quotes (0.26σ twins, 2.54σ for
   `84:7b`, 11–15σ cross-manufacturer) is essentially an SFO figure. **If the
   subcarrier index changes meaning, every one of those numbers changes with
   it, and none of them are comparable across the two receivers until the
   mapping is re-derived.**

### 3.3 So: re-derive or re-point?

**Re-point, *if and only if* the S3 buffer turns out to be 64 FFT-ordered
LLTF complex pairs with the same guard band.** In that case the change is a
target-conditional constant in `dsp.py:30-38` and nothing else — `occ/` picks
it up for free via its import at `ingest.py:41`.

**Re-derive if the ordering or the usable set differs.** That is not a
constant change: `unwrap_continuity`'s assumption that adjacent array
positions are adjacent subcarriers (`dsp.py:64`, `np.unwrap`) has to hold in
whatever order the bins are handed to it, and `ransac_line`'s thresholds are
tuned to the current span. It is still a contained change — one module — but
it invalidates the tuning, and re-tuning has to be validated against a
known-good D0WD stream before it is trusted on an S3 one.

**Which of the two it is, is decided entirely by the §2.3 capture.** There is
no way to know in advance and no point guessing.

---

## 4. Receiver-relative CFO

### 4.1 What the code actually assumes

The physics is stated correctly and prominently.
`pc/rff/reference.py:4-5`: "The receiver's own crystal drifts too, and its
drift is common-mode: **every CFO/SFO we measure is (TX drift − RX drift)**."
So no, the code does not naively treat CFO as a transmitter property — the
docstring names the pair explicitly.

**And the correction is structurally right.** `ReferenceNormalizer.feed`
(`reference.py:29-59`) subtracts the reference beacon's Kalman-smoothed track
from every other source: `out["cfo_ref"] = obs["cfo"] − self.tracker.cfo.x`
(`reference.py:48,56`), same for SFO at `:50,58`. Written out:

```
cfo_ref(device) = (TX_dev − RX) − (TX_ref − RX) = TX_dev − TX_ref
```

The receiver term cancels algebraically. **The reference-corrected feature
space is transmitter-relative-to-reference-beacon, and is in principle
receiver-independent.** That is a much better starting position for a
two-receiver system than the framing of the question assumes.

`pc/rff_offline.py:82-95` and `pc/rff_live.py:111-124` both prefer
`cfo_ref`/`sfo_ref` over raw and, when `--ref-mac` is set, **drop**
uncorrected windows entirely (`rff_offline.py:89-90`) precisely so that raw
and corrected values never mix in one centroid.

### 4.2 Where the D0WD assumption actually lives

Three places, none of them in `reference.py`:

**(a) Raw values are stored and are receiver-bound.** `store.py:30-31`
persists `cfo_hz` and `sfo_slope` as "raw residual" alongside the corrected
pair. Any analysis that reaches for the raw columns is reading a
(TX − D0WD) quantity with no marker saying so — `observations.node`
(`store.py:26`) is a free-text column that `rff_offline.py:207` fills with
the literal string `"offline"` for every row it ever writes.

**(b) The models are keyed by MAC alone.** `Discriminator.models` is
`{source_id: SourceModel}` (`discriminator.py:83`), and `source_id` is the
MAC (`rff_offline.py:148`, `disc.learn(mac, f)`). There is no receiver
dimension anywhere in the model, the schema, or the classification call. A
model learned on one receiver and scored on another is indistinguishable, in
the data structure, from a model learned and scored on the same one.

**(c) `reference.py` cancels the receiver only while the reference is
visible.** `ready` requires both Kalman tracks initialised
(`reference.py:24-27`); until then observations pass through **uncorrected
and flagged** (`reference.py:37-38,52-53`) — which is the honest behaviour,
and also means a second receiver that cannot hear the reference beacon
produces raw, receiver-bound features that `feature(require_ref=True)` will
silently discard.

**Note also which "fingerprint library" is which.** `data/fingerprints/*.json`
(13 files) is `pc/fingerprint.py`'s **amplitude** template library — per-buffer-index
normalised |H| (`fingerprint.py:74-80`). It is not the CFO/SFO library. The
clock library is the `models` table in `data/rff.db` (`store.py:41-44`). The
amplitude templates are receiver-bound in a much harder way — they encode the
channel between that TX and that antenna — and **nothing about a two-receiver
calibration helps them.** `CLAUDE.md`'s rule against fusing `pc/rff/` and
`pc/occ/` numbers applies here too.

### 4.3 The calibration a simultaneous capture would enable — and the evidence that it works

This has already been done once, between two D0WDs, and the result is
recorded. `docs/HANDOFF.md` lines 132-134:

> Reference-beacon subtraction cancels RX-side drift across
> sessions/receivers (**two RX agreed on a source's SFO to 0.0004 rad/sc**)
> but does NOT help within-session same-model separation.

And more precisely, from `docs/TWIN_INVESTIGATION.md` §6: the reference
beacon's reference-corrected SFO mean was **+0.00028 on desk vs +0.00032 on
node3** — a 4e-5 rad/sc offset — while node3's *spread* was wider (sd 0.00299
vs 0.00272). That asymmetry is the whole story of the 99.7% → 95.7% drop: the
centroids agree, the ellipses do not, and 2.57% of node3 windows fall outside
the desk-trained ellipse and are rejected as strangers.

So the calibration is not "measure an offset and add it". The shape of what a
simultaneous D0WD + S3 capture would buy is:

1. **Both receivers hear the same reference beacon in the same minutes.**
   That is what makes the two `cfo_ref`/`sfo_ref` spaces comparable at all,
   and it is the condition the era-A `desk`/`node3` pairs satisfied.
2. **Measure the residual inter-receiver offset** in the corrected space —
   the analogue of `+0.00028` vs `+0.00032`. If it is a constant, it is a
   two-scalar correction and the existing `data/rff.db` models map onto S3
   readings directly. If it drifts with temperature, it is not a calibration,
   it is a second tracker.
3. **Measure the variance ratio, not just the offset.** The 95.7% run failed
   on spread, not centre. The number that decides whether the existing library
   transfers is *what fraction of S3 windows land inside the D0WD-trained
   χ²₉₅ ellipse* — and that exact statistic is already computed by an existing
   tool: `pc/twin_probe.py match --tag-a <d0wd> --tag-b <s3>` prints "B wins
   in A 95% ellipse" as a percentage, per source pair
   (`twin_probe.py:477-498`).
4. **Do it against a reference beacon that is warm and stationary.** Thermal
   wander moved pairs 2.7σ → 1.3σ within one session (`docs/HANDOFF.md` line
   130-131; `docs/THERMAL_EVIDENCE.md`), which is larger than the effect being
   measured.

**What this cannot establish:** whether the D0WD-trained library transfers to
the S3 *in the raw feature space*. It will not, and nothing here proposes it
should. The claim under test is narrower — that in the reference-corrected
space the S3 lands close enough to the D0WD that the existing centroids
remain usable. Between two D0WDs the answer was "centres yes, tails no". Across
different silicon it is **UNKNOWN**, and the two receivers are no longer the
same part, which is a strictly harder case than the one that produced 95.7%.

---

## 5. Two-receiver mechanics — what exists and what does not

### 5.1 What already exists and works

**Simultaneous multi-port capture: exists, and shipped.** `pc/capture.py`
takes `PORT[:name]` specs (`capture.py:177,180`), starts one reader thread
per port (`capture.py:183`), and writes **one CSV per node**, named
`{node.name}_{ts}.csv` (`capture.py:103`). That is exactly how the two-day
two-receiver dataset was produced: `data/raw/` holds 15 `desk_*`/`node3_*`
file pairs with matching timestamps, longest overlap **148.45 minutes**
(`docs/NODE_CENSUS.md` §4). Same host, one process, two USB ports.

**Live multi-port: exists.** `pc/rff_live.py:12` documents
`rff_live.py COM3:node1 COM12:node3 --ref-mac ...`; `NodeReader`
(`rff_live.py:48`) is one thread per port and holds **its own**
`FrameEstimator`/`WindowAggregator` dict (`rff_live.py:71-72`), which is
correct — per-frame phase continuity must not cross receivers.

**Cross-epoch comparison: exists.** `pc/twin_probe.py`'s `collect --tag` /
`match --tag-a --tag-b` (`twin_probe.py:44-47`, `440-499`) is purpose-built to
score every source in one capture set against every model from another. It was
written for "same device, different MAC"; it works unmodified for "same
device, different receiver".

### 5.2 How the existing two-receiver data was aligned — it was not

This is the important negative finding.

- **No frame-level cross-receiver alignment exists anywhere in the repo.**
- `pc_time_us` is written by the host at parse time, `int(time.time() * 1e6)`
  (`capture.py:129`) — and it is **stamped per serial drain batch, not per
  frame** (`docs/HANDOFF.md` trap #1, lines 170-172; `docs/NODE_CENSUS.md`
  §2.4 and §8). It is safe at minutes-to-hours scale, which is all
  `node_census.py overlap` uses it for, and useless below that.
- `esp_timestamp_us` is the node's own WiFi clock (`main.c:127`). It is
  per-frame and precise, and it is **node-local with no shared epoch**. In
  the paired files I read, `desk` and `node3` report 16,888 µs and 49,011 µs
  for their first reference-beacon frame — different boots, different zeros.
- The 95.7% run did not align frames at all. `rff_offline.collect_observations`
  (`rff_offline.py:54-79`) replays `sorted(paths)` and appends to
  `by_mac[mac]` (`rff_offline.py:77`) — **keyed by transmitter MAC only.**
  `iter_frames` (`rff_offline.py:41-52`) does not even read the `node_id`
  column. The two receivers' windows are concatenated, not paired, and
  `sorted()` puts every `desk_*` window before every `node3_*` one, which is
  why the "chronological" 60/40 split split by *receiver*
  (`docs/TWIN_INVESTIGATION.md` §6). **The 95.7% figure is what you get when
  two receivers are pooled with no alignment and no receiver dimension.**

### 5.3 What would have to be built

| # | gap | current state |
|---|---|---|
| 1 | **A shared time base across receivers.** | Nothing. Neither clock is common. The one shared token is `seq` — a TX-side ESP-NOW counter both receivers see (`main.c:104`). I confirmed it is genuinely shared: over the same window `desk` runs to 7,905,900 and `node3` spans 7,898,270–7,909,699. **But it is broken by design for the current fleet**: `s_latest_seq` is a single global updated by *any* beacon (`main.c:84,103`), so with 3 beacons on air the column is cross-contaminated — this is `docs/HANDOFF.md` open thread #4 verbatim. It worked in era A because only one beacon existed. **Fixing seq to per-MAC is a prerequisite for any frame-level alignment, and it is a firmware change to both receivers.** |
| 2 | **A receiver dimension in the offline pipeline.** | Absent. `by_mac[mac]` (`rff_offline.py:77`); `node_id` unread (`rff_offline.py:41-52`). |
| 3 | **A receiver dimension in the model store.** | Absent. `models` is keyed by `source_id` only (`store.py:41-44`); `observations.node` is free text and is always `"offline"` (`rff_offline.py:207`). |
| 4 | **Per-receiver reference normalization in the live path.** | **Absent, and currently wrong for two receivers.** `rff_live.py:209` creates **one** `ReferenceNormalizer` for all node readers, and `rows`/`disc` are keyed by MAC alone (`rff_live.py:198,225`); `row.node` (`rff_live.py:226`) is overwritten by whichever reader spoke last and is display-only. Two receivers feeding one normalizer interleave two different (TX − RX) series into a single Kalman track. |
| 5 | **One `--baud` for all ports.** | `capture.py:178` and `rff_live.py:176` both take a single `--baud` applied to every reader. On a USB-Serial-JTAG endpoint the value is discarded by the device (`pc/throughput_test.py:26-32`), so a mixed D0WD-at-460800 + S3-on-USB pair happens to work — but by accident, not by design. |
| 6 | **`node_id` disambiguation.** | Works for free, see §1.2 — D0WD 68, Heltec 108 — *provided* both are era-B/C 13-column captures. |

---

## 6. Ordered work breakdown

Smallest first. Each step ends in something you can look at. The
cheap-and-informative steps are marked **[C]**; the ones that commit real time
or hardware state are marked **[X]**.

**The step where the whole idea dies, if it is going to, is step 3.** Steps 1
and 2 cost under an hour between them and one of them is pure reading.

| # | step | ends in | cost |
|---|---|---|---|
| 0 | **Write the 675 KB/s result into `firmware/s3_throughput/README.md`** and fix its "never run" heading (§0). | The repo stops contradicting the premise. | **[C]** minutes |
| 1 | **Read `wifi_csi_config_t` and `wifi_csi_info_t` out of the local IDF** — `grep -rn "wifi_csi_config_t\|first_word_invalid" C:\Espressif\frameworks\esp-idf-v5.5.4\components\esp_wifi\include\` — and confirm against §1.1. | A printed struct that either matches the fetched v5.5.1 header or does not. Settles "does `csi_init()` compile" with zero risk. | **[C]** minutes |
| 2 | **Build `csi_rx` for esp32s3.** New `sdkconfig.defaults.s3` (`CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`, `CONFIG_ESP_WIFI_CSI_ENABLED=y`, `CONFIG_LIBC_STDOUT_LINE_ENDING_LF=y`, drop the GPIO 1/3 lines), `-B build_s3` per `docs/HANDOFF.md` line 251-253. **Do not flash.** | Either a `.bin` or a compiler error naming exactly which API is missing. Every §1 claim about portability is confirmed or refuted here, on the bench, without touching a board. | **[C]** ~1 h |
| 3 | **Flash it and capture 5,000 beacon frames.** `--no-stub -b 115200`, pull the LiPo, expect a manual RST (`docs/HANDOFF.md` 249-253). Then `python pc\capture.py COM6:s3` for two minutes with the reference beacon running. | **A CSV.** Its `len` column and per-index mean magnitude answer §2.3 completely — length, ordering, guard band, field boundary, first-word artifact. **This is the go/no-go.** If the S3 produces no CSI rows at all, open thread #3's "RX works" was wrong and the plan stops here. | **[X]** ~2 h |
| 4 | **Re-point or re-derive `dsp.py`** per §3.3, guarded by a target check, and validate the unchanged D0WD path still reproduces a known number. | `rff_offline.py` on an existing `desk_*` file printing the same σ it printed before. Regression-proof before anything new is trusted. | **[C]** if re-point; **[X]** if re-derive |
| 5 | **Sustained solo run: S3 alone, 60 minutes, radio on, USB at rate.** | A `diagnose.py` report with drop count, resync bytes, and crash count. This is where `SOC_WIFI_PHY_NEEDS_USB_WORKAROUND` (§1.4a) and the WDT-vs-backpressure risk (§1.4b) either show up or do not. A single reset in 60 minutes means the drain-task/watchdog interaction needs redesigning before any dual work. | **[X]** ~1 h wall, mostly waiting |
| 6 | **Simultaneous capture, both receivers, ≥30 min.** `python pc\capture.py COM3:d0wd COM6:s3`. Nothing in `pc/` needs to change for this — §5.1. | Two CSVs with overlapping `pc_time_us` spans, provable by `node_census.py overlap`. | **[X]** ~1 h |
| 7 | **Cross-receiver comparison with the tool that already exists.** `twin_probe.py collect --tag d0wd21 ...`, same for `s3_21`, then `match --tag-a d0wd21 --tag-b s3_21 --a-only <ref-mac>`. | The number that decides everything downstream: **what fraction of S3 windows land inside the D0WD-trained χ²₉₅ ellipse.** Compare against the era-A D0WD↔D0WD baseline (centres 4e-5 rad/sc apart, ~2.6% tail loss). | **[C]** — the tool exists |
| 8 | **Only then**: per-MAC `seq` in firmware (open thread #4), receiver dimension in `rff_offline`/`store`/`rff_live` (§5.3 gaps 1–4). | A pipeline that can hold two receivers honestly. | **[X]** — real work, and premature before step 7 |

---

## 7. What could not be determined from this repo

Stated plainly rather than filled in.

1. **The S3 CSI buffer layout.** Zero S3 CSI bytes exist here. Only step 3
   settles it. (§2.3)
2. **Whether the Heltec S3 can receive CSI at all.** `docs/HANDOFF.md`'s "RX
   works" has no supporting artifact in this repo and `data/raw/` contains
   nothing from that board. (§0)
3. **What `SOC_WIFI_PHY_NEEDS_USB_WORKAROUND` costs under simultaneous
   WiFi-RX and saturated USB-TX.** The flag is real
   (`firmware/csi_tx/build_s3/sdkconfig:375`); its cost is documented nowhere
   I can reach. (§1.4a)
4. **Whether `usb_serial_jtag_write_bytes(..., 0)` backpressures or drops.**
   `firmware/s3_throughput/README.md:150-155` flags this as unverified, and
   the drain task's watchdog behaviour depends on the answer. (§1.4b)
5. **The Heltec V3's I²C OLED pins and BOOT-button timing.** Not recorded in
   this repo. (§1.2)
6. **Whether the D0WD↔S3 inter-receiver offset is constant or thermal.** Only
   a multi-hour dual capture answers it, and it determines whether §4.3 is a
   two-scalar calibration or a second Kalman track. (§4.3)
7. **The 675 KB/s and UART-saturation figures themselves.** Given to me;
   present in no file. (§0)

---

## Files this study touched

Created: `docs/S3_PORT_SCOPE.md` (this file). Nothing else. No existing file
was modified, no hardware was touched, nothing was staged or committed.
