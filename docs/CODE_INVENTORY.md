# CODE_INVENTORY — read-only audit of `pc/` and `firmware/`

Date of this pass: **2026-08-21**. Read-only. Nothing in the repo was
modified, staged, committed or deleted; no serial port was opened; nothing
in `data/raw/` was touched except by reading.

## 0. Scope, method, and what is not covered

**What was read in full:** every file under `pc/` (including `pc/rff/` and
`pc/occ/`) and every source file under `firmware/` (including
`firmware/common/`), read as text, not skimmed from names or docstrings.
Docstrings in this repo have been caught being wrong before, so where a
docstring and the code below it disagree, this file records the code.

Files read in full, by directory:

- `pc/` top level: `capture.py` (198), `collect.py` (102),
  `device_correlate.py` (205), `diagnose.py` (632),
  `exp_lot_hypothesis.py` (573), `exp_occ_ground_truth.py` (499),
  `exp_thermal_evidence.py` (1081), `exp_window_convergence.py` (922),
  `field_diag.py` (137), `fingerprint.py` (206), `heatmap.py` (232),
  `live_view.py` (140), `mac_census.py` (103), `node_census.py` (327),
  `occ_capture.py` (147), `occ_offline.py` (361), `occ_survey.py` (111),
  `phase_skew.py` (149), `rff_live.py` (285), `rff_offline.py` (261),
  `test_occ_synth.py` (92), `throughput_test.py` (873),
  `twin_probe.py` (602), `zone_calib.py` (306), `requirements.txt` (4).
- `pc/rff/`: `__init__.py`, `discriminator.py`, `dsp.py`, `kalman.py`,
  `protocol.py`, `reference.py`, `serialio.py`, `store.py`.
- `pc/occ/`: `__init__.py`, `breathing.py`, `ingest.py`, `motion.py`,
  `zones.py`.
- `firmware/`: `csi_rx/main/main.c` (328), `csi_cfo/main/main.c` (340),
  `csi_tx/main/main.c` (70, working tree) and its git-HEAD version (79),
  `s3_throughput/main/main.c` (283), `common/telemetry/{telemetry.c,
  include/telemetry.h}`, `common/calibration/{calibration.c,
  include/calibration.h}`, `common/node_hal/{node_hal.c, ssd1306.c,
  include/node_hal.h, include/ssd1306.h}`, and every `CMakeLists.txt` and
  `sdkconfig.defaults*` in the tree.

**Read partially, and stated as such:** the generated `sdkconfig` files
(`firmware/csi_rx/sdkconfig` 2469 lines, `firmware/csi_cfo/sdkconfig`
2260, `firmware/csi_tx/sdkconfig` 2260, `firmware/s3_throughput/sdkconfig`
2456, `firmware/csi_rx/sdkconfig.old` 2260). These are ESP-IDF output, not
authored source. They were queried by grep for target, console, CSI,
watchdog and line-ending settings only. Any claim below about them names
the exact line queried. Nothing else in them was read.

**Not read at all:** `firmware/csi_tx/build_s3/` and every other
`build*/` tree (compiler output, gitignored), `pc/__pycache__/`,
`site/`, `git-guard/`, `data/`. `docs/*.md` was read only where a specific
claim needed checking; the line references to `docs/` below are all
verified individually, but this is not a full audit of `docs/`.

**Measurements taken during this pass**, all read-only, all on files that
were open for writing by a live capture at the time (so they describe the
first ~26 minutes of that capture, not a finished session):

| what | how |
|---|---|
| frame counts, per-MAC counts, `csi_len` histogram, `node_id` | streaming pass over `data/raw/s3_20260821_125017.csv` and `data/raw/desk_20260821_125017.csv`, prefix-split on the first 100 chars plus a 3-way `rsplit` for the trailing columns |
| queue-drop share | sum of per-frame deltas of the `dropped` column, mod 2^16, ignoring backward steps |
| guard-bin positions | `np.hypot` over the first 128 CSI values of five `len=256` reference-beacon frames |
| SFO slope comparison | `rff.dsp.csi_to_complex` + `rff.dsp.ransac_line` against a transcription of `pc/capture.py`'s `compute_cfo`, same frame |

No hardware was contacted. Nothing here measures the radio.

---

## 1. Established today, recorded here so it is not rediscovered

1. **`firmware/csi_tx/main/main.c` in the working tree is not the beacon.**
   It is a standalone NimBLE advertiser named `CSI-S3-ALIVE`
   (`firmware/csi_tx/main/main.c:19`), 70 lines, no ESP-NOW anywhere in
   it. The production beacon is git HEAD
   (`git show HEAD:firmware/csi_tx/main/main.c`, 79 lines, magic
   `0xC51C51C5` at `:65`, `SEND_INTERVAL_MS 10` at `:17`). Uncommitted;
   mtime `2026-07-22 18:50:49`. It was written to diagnose the S3
   WiFi-TX fault (`docs/HANDOFF.md:209-215`).

2. **`csi_rx` compiles clean for `esp32s3` and runs on the Heltec.**
   `firmware/csi_rx/sdkconfig:391` now reads
   `CONFIG_IDF_TARGET="esp32s3"`; `firmware/csi_rx/build/project_description.json`
   records `"target": "esp32s3"`, `"project_name": "csi_rx"`, built
   2026-08-21 12:20–12:22. Measured on the running capture:
   `data/raw/s3_20260821_125017.csv` carries **241,656 CSI rows over
   1,557 s = 154.0 fps**, `node_id` = `108` on every row (= `0x6c`, the
   last byte of the Heltec's MAC `8c:fd:49:b7:b0:6c`, which is what
   `firmware/common/node_hal/node_hal.c:73` uses as the default), all
   three beacons present, and **237,214 of 239,828 sampled rows have
   `csi_len` 256** — matching the D0WD collector, which reports 214,671
   of 216,502 at 256. 154 fps × 60 s = 9,240, consistent with the
   separately reported 9,313 frames in 60 s.

   Precision note: the Heltec's MAC still appears **zero times as a
   source MAC** in today's captures (`grep -c` on the first 100 chars of
   both files = 0). That is expected — it is receiving, not
   transmitting — but it means `docs/NODE_CENSUS.md:288`'s "0
   occurrences" is still literally true, and what changed today is that
   the *receive* side moved from inference (`docs/NODE_CENSUS.md:470`,
   inference I1, "Plausible, unverified") to measurement.

3. **Both receivers drop frames in the node-side CSI queue, and it is not
   serial saturation.** Measured over the same live window, by summing
   per-frame deltas of the `dropped` column:

   | file | receiver | kept | queue drops | loss |
   |---|---|---|---|---|
   | `s3_20260821_125017.csv` | Heltec S3, native USB | 241,656 | 49,511 | **17.00 %** |
   | `desk_20260821_125017.csv` | D0WD, UART bridge | 218,016 | 8,660 | **3.82 %** |

   The separately reported figure is ~14 % on both from a 60 s test; the
   26-minute figures above are what the running capture shows. Both are
   node-side: `firmware/csi_rx/main/main.c:131-133` increments `s_dropped`
   only when `xQueueSend(s_csi_queue, &s, 0)` fails, i.e. when the
   64-deep queue (`:46 QUEUE_DEPTH 64`) is full because the drain task
   (`:165-184`) has not kept up. The S3 in the reported test ran at ~6 %
   of its measured 675 KB/s link with 290 resync bytes and still dropped
   1,535 samples, so the USB link is not the constraint there.

   **Unknown, and not established by anything read here:** why the drain
   task falls behind. `tlm_send_csi` → `emit()`
   (`firmware/common/telemetry/telemetry.c:37-40`) does three `fwrite`s
   and an `fflush` per frame; whether that, the OLED `display_task`
   (`csi_rx/main/main.c:208-249`, 4 Hz, full 1 KB I²C framebuffer blast
   at `ssd1306.c:114-123`), or something else dominates is not measured
   anywhere in this repo.

   Caveat on the S3 number, which matters for how it is quoted: the S3's
   `dropped` counter is a `uint16_t` (`csi_rx/main/main.c:85`) and it
   **wrapped once inside this 26-minute window**. Summing per-frame
   deltas is wrap-safe; the two shipped tools that report this number are
   not (see §5, S6).

4. **Two receivers are logging right now**, `desk_20260821_125017.csv`
   (`node_id` 68) and `s3_20260821_125017.csv` (`node_id` 108), same
   start timestamp, same three beacons, both still growing. This is the
   first simultaneous two-receiver session since 2026-07-13
   (`docs/HANDOFF.md:60-63`).

---

## 2. File inventory — `pc/`

Status vocabulary: **current** = on a live path some tool uses today;
**superseded** = a later implementation of the same thing exists;
**dead** = cannot work against the committed firmware, or has no
reachable caller and no working entry point; **orphan CLI** = works, has
no importer, run by hand.

### 2.1 `pc/rff/` — the phase-domain pipeline (all current)

| file | what it actually does | called by | status |
|---|---|---|---|
| `rff/__init__.py` | docstring only; no code | — | current |
| `rff/protocol.py` | v1 (`C5 51`, 21-byte header) and v2 (`C5 52`, 12-byte header) frame decoder, XOR-checked, one-byte resync on failure (`:153-180`); `unwrap_ts` for the u32 µs boot clock (`:183-189`). Calls itself "the single source of truth for frame parsing" (`:23`) — see §4.2 C8 | `capture.py:18`, `collect.py:22`, `diagnose.py:77`, `field_diag.py:24`, `occ_capture.py:29`, `rff_live.py:63`, `occ/ingest.py:42` | current |
| `rff/serialio.py` | opens a port with DTR/RTS deasserted **before** `open()` so the node is not reset (`:15-23`) | `collect.py:23`, `diagnose.py:79`, `field_diag.py:25`, `occ_capture.py:30`, `throughput_test.py:86`, `rff_live.py:64`, `capture.py:105` | current |
| `rff/dsp.py` | the LLTF mapping (`:30-38`): 64 complex bins in FFT order, usable = \|k\| in 1..26 → 52 bins. `csi_to_complex` reads `iq[1::2] + 1j*iq[0::2]`, i.e. the buffer is imag-first (`:52`). `FrameEstimator.feed` (`:120-153`) unwraps with a one-frame continuity anchor, RANSAC-fits slope+intercept over `K_USABLE`, and derives `cfo_hz` from the **frame-to-frame intercept delta**, not from the slope. `WindowAggregator` (`:156-195`) medians 64 accepted frames per observation, gated on `inlier_ratio >= 0.6` and `resid_std <= 0.8` | `rff_live.py:41`, `rff_offline.py:32`, `exp_window_convergence.py:83`, `occ/ingest.py:41` | current |
| `rff/kalman.py` | scalar random-walk KF (`:14-43`) plus a paired CFO/SFO `DriftTracker` (`:46-67`) whose measurement noise comes from the window IQR / 1.35 | `rff_live.py:42`, `rff_offline.py:33`, `rff/reference.py:16`, `exp_window_convergence.py:85` | current |
| `rff/discriminator.py` | Welford 2-D Gaussian per source, χ² thresholds 5.991 / 9.210 (`:23-24`), variance floors `[1.0, 1e-8]` (`:27`), `MIN_CHARACTERIZED = 5` (`:80`), pooled-covariance pairwise separation matrix returning **d, not d²** (`:116-139`) | `rff_live.py:43`, `rff_offline.py:34`, `twin_probe.py:63`, `exp_lot_hypothesis.py:76`, `exp_window_convergence.py:84` | current |
| `rff/reference.py` | subtracts the reference beacon's Kalman track from every source; passes observations through **unmodified and flagged uncorrected** when the reference is cold (`:52-53`) | `rff_live.py:44`, `rff_offline.py:35` | current |
| `rff/store.py` | SQLite schema + insert/upsert (`:15-45`, `:86-90`). `load_models()` returns models keyed by integer `source_id`, not MAC (`:92-97`) | `rff_live.py:45`, `rff_offline.py:36` | current |

### 2.2 `pc/occ/` — the amplitude-domain pipeline (all current)

| file | what it actually does | called by | status |
|---|---|---|---|
| `occ/__init__.py` | `BEACON_MACS`, three MACs → `B1`/`B2`/`B3` (`:19-23`). No code | `occ_offline.py:32`, `occ_capture.py:31`, `device_correlate.py:35`, `mac_census.py:29`, `diagnose.py:80`, `exp_occ_ground_truth.py:38`, `zone_calib.py:194`, `occ/ingest.py:43` | current |
| `occ/ingest.py` | CSV → per-link uniform grids. Streams with `line.split(",", 9)` and locates `csi_data` inside the quotes (`:141-151`); builds the wall clock from the **unwrapped ESP clock anchored to the first pc time**, resyncing on >5 s divergence (`:158-163`); unit-mean-normalises each 52-bin amplitude vector (`:168-173`); caches to `.npz` keyed on `(CACHE_VERSION, size, mtime)` (`:184-187`) | `occ_offline.py:33`, `device_correlate.py:36`, `zone_calib.py:54`, `exp_occ_ground_truth.py:39` | current |
| `occ/motion.py` | NaN-aware trailing rolling std via cumsum (`:26-50`), median-across-subcarriers metric (`:53-61`), `CountConditionedFloor` that learns (median, MAD) per windowed frame-count level and interpolates (`:74-122`), `FusedDetector` 2-of-3 + solo with hysteresis (`:141-183`) | `occ_offline.py:34`, `device_correlate.py:37`, `exp_occ_ground_truth.py:40`, `test_occ_synth.py:13` | current |
| `occ/breathing.py` | hand-rolled Welch PSD, no scipy (`:34-61`); respiration-band SNR vs a 0.7–2.5 Hz noise floor, **rejecting band-edge peaks as 1/f leakage** (`:104-105`); consensus over the top-10 subcarriers (`:111-120`); `presence_verdict` ≥6 dB and ≥5 agreeing (`:130-138`) | `occ_offline.py:36`, `exp_occ_ground_truth.py:41`, `test_occ_synth.py:12` | current |
| `occ/zones.py` | per-event cross-link energy profiles (`:21-44`), spread about the centroid (`:47-64`), 30-line k-means (`:67-89`). Produces **unlabeled** clusters and says so | `occ_offline.py:37` | current |

### 2.3 `pc/` top level

| file | what it actually does | called by | status |
|---|---|---|---|
| `capture.py` | multi-port recorder + ANSI "matrix rain" TUI. One reader thread per port, writes `data/raw/<name>_<ts>.csv` (`:99-136`). Contains its own `compute_cfo` (`:24-33`) that is **not** the pipeline's estimator — see §4.2 C1 | orphan CLI (produced both of today's files) | current |
| `collect.py` | single-port recorder, same CSV schema. Has the best wrong-baud diagnostic in the tree (`:63-72`) | orphan CLI | current |
| `rff_live.py` | live TUI: thread-per-port → DSP → window → reference → Kalman → Mahalanobis → SQLite. `REBASELINE_STREAK = 20` resets a model after 20 consecutive anomalies (`:24`, `:251-258`). Resumes models from the DB (`:200-205`) | orphan CLI | current |
| `rff_offline.py` | the science run: replay CSVs, per-source stability table, pooled separation matrix, chronological 60/40 blind holdout (`:38`, `:139-196`). Estimator state resets per file, deliberately (`:54-79`) | `twin_probe.py:62`, `exp_lot_hypothesis.py:77`, `exp_window_convergence.py:86` | current |
| `diagnose.py` | pre-capture health check. The most careful tool in `pc/`: refuses per-beacon loss because `seq` is node-global (`:44-51`), separates "expected and silent" from "never heard" (`:401-449`), accounts for bytes that never became a frame (`:308-311`), and prints no overall verdict on purpose | orphan CLI | current |
| `field_diag.py` | shorter node health report over a fixed listen window | orphan CLI | current, partly superseded by `diagnose.py` |
| `occ_capture.py` | recorder with keyboard ground-truth labelling; `msvcrt` on Windows, line-buffered stdin elsewhere (`:58-75`) | orphan CLI | current |
| `occ_offline.py` | the occupancy science run: grids → count-conditioned z → fused detection → respiration scan of quiet runs → zone profiles → label scoring → ASCII timeline. `RSSI_GUARD_DB = 5.0` invalidates a transferred floor (`:41`, `:100-104`) | `exp_occ_ground_truth.py:42` | current |
| `occ_survey.py` | cheap per-session MAC/rate/gap survey, no CSI parse | orphan CLI | current |
| `mac_census.py` | cross-session distinct-MAC census with locally-administered flag (`:32-37`) | orphan CLI | current |
| `node_census.py` | the tool behind `docs/NODE_CENSUS.md`: per-(file, MAC) census, wall-clock overlap test, beacon-signature role filter, esp-clock cadence. Truncates each line to 100 chars before splitting (`:52`, `:70`) — safe because `csi_data` is field 10 | `diagnose.py:83` (constant `BEACON_MIN_FPS`) | current |
| `zone_calib.py` | labelled-walk zone classifier; trailing rolling-mean detrend, chronological visit split, nearest-centroid, honest confusion matrix | `device_correlate.py:38` (`labels_to_bins`, `label_runs`) | current |
| `device_correlate.py` | correlates ambient-MAC presence with motion-flagged bins, reports a lift ratio; explicitly refuses to call it ownership (`:196-200`) | orphan CLI | current |
| `twin_probe.py` | cached-shard replay wrapper over `rff_offline.collect_observations`; `sep` / `holdout` / `timing` / `match` / `drift`. Cache lives **outside the repo** at `../../twin_probe_cache` (`:69-72`) | `exp_lot_hypothesis.py:75`, `exp_thermal_evidence.py:122` | current |
| `exp_lot_hypothesis.py` | restricted-pool pairwise separation with bootstrap CIs, replication across tags, within-vs-between variance | orphan CLI | current |
| `exp_thermal_evidence.py` | warm-up trajectory / time-of-day / wander tests with matched-later and tail-drop controls; `paired` compares two receivers on one session | orphan CLI | current, but `paired` is unreachable — §5, S11 |
| `exp_window_convergence.py` | window-length truncation experiment; caches raw CSI to `.npz`, re-runs the **real** estimator per tile | orphan CLI | current |
| `exp_occ_ground_truth.py` | scores the 2026-07-22 labelled session under four calibration configs, with an interval-interior guard the committed scorer lacks (`:19-20`, `:116-124`) | orphan CLI | current |
| `throughput_test.py` | host side of `firmware/s3_throughput`; measures device→host B/s and converts to CSI fps at 284 B/frame (`:129`). Its own protocol, magic `C5 54` | orphan CLI | current |
| `test_occ_synth.py` | four synthetic assertions over `occ/breathing` and `occ/motion`, no hardware | orphan CLI | current |
| `fingerprint.py` | amplitude-template fingerprints, cosine distance, `data/fingerprints/*.json`. Phase-1 approach; `pc/rff/` replaced it | orphan CLI | **superseded** (and see §4.2 C3) |
| `phase_skew.py` | the RFF-v2 *probe* that preceded `rff/dsp.py`; prints an honest "is the phase usable" verdict | orphan CLI | **superseded**, and its subcarrier mask is wrong — §4.2 C2 |
| `live_view.py` | real-time waterfall. Carries a **private v1-only decoder** (`:25-60`) and opens the port with plain `serial.Serial` (`:66`) | orphan CLI | **dead** against committed firmware — §5, S2/S3 |
| `heatmap.py` | Fresnel-ellipse room heatmap, click-to-place nodes. Only Python file importing pandas (`:17`) | orphan CLI | **dead** against today's filenames — §5, S4 |
| `requirements.txt` | `pyserial`, `numpy`, `matplotlib`, `rich`. **Omits pandas**, which `heatmap.py:17` imports. scipy is correctly absent — nothing imports it | — | current |

## 3. File inventory — `firmware/`

| file | what it actually does | status |
|---|---|---|
| `common/telemetry/include/telemetry.h` | v2 wire format: `C5 52 \| type \| node_id \| env_id \| boot_ts_us \| len`, XOR over everything after the magic. `TLM_FW_VERSION 2` (`:33`). STATUS payload documented at `:19-23` as 27 bytes; `pc/rff/protocol.py:35` parses `"<BBBHHIIIIhh"` = 27. **They match.** | current |
| `common/telemetry/telemetry.c` | manual little-endian packing, three `fwrite`s + `fflush` per frame (`:37-40`); static 399-byte payload buffer on a one-caller contract (`:47-49`); clamps `csi_len` to 384 (`:51-52`) | current |
| `common/calibration/*` | 300 s startup gate with a fast EMA (α 0.05) then slow thermal tracking (α 0.002); `cal_gate_open()` suppresses **all** CSI emission while running (`calibration.c:64-67`) | current |
| `common/node_hal/node_hal.c` | NVS identity (`node_id` defaults to MAC byte 5, `:73`), crash accounting on abnormal reset (`:44-51`), safe-boot console at 115200 with `SHOW/NODE/ENV/CAL/CLEARCRASH/REBOOT` (`:132-201`), task WDT with `trigger_panic = true` and an already-running retune path (`:208-220`), RF-liveness timer that `esp_restart()`s after N seconds of silence (`:235-257`) | current |
| `common/node_hal/ssd1306.c` | 128×64 I²C driver, 5×7 font, `oled_flush` blasts the whole 1025-byte framebuffer per call (`:114-123`) | current |
| `csi_rx/main/main.c` | production collector. `RFF_PROMISCUOUS 1` (`:44`), `TX_FILTER_MAC` all-zero = **no filter** (`:68`), channel 6 (`:39`), queue depth 64 (`:46`), STATUS every 5 s (`:59`), CSI config enables LLTF + HT-LTF + merge (`:269-277`) which is why `csi_len` is 256 not 128 | current |
| `csi_cfo/main/main.c` | identical to `csi_rx` at git HEAD; the working tree differs — `RFF_PROMISCUOUS 0` (`:51`), `TX_FILTER_MAC = A4 F0 0F 77 91 20` (`:80`), `TAG = "csi_cfo"` (`:82`). Uncommitted, mtime 2026-08-02 23:11 | **uncommitted divergence** — §6, U4 |
| `csi_tx/main/main.c` | working tree: NimBLE advertiser `CSI-S3-ALIVE`, no ESP-NOW. HEAD: the 100 Hz ESP-NOW beacon | **uncommitted divergence** — §6, U1 |
| `s3_throughput/main/main.c` | fixed 269-byte records, magic `C5 54`, verifiable payload `(seq + 7*i) & 0xFF`, non-blocking first write so backpressure is measured rather than assumed (`:171-203`). Deliberately shares nothing with `../common` | current |
| `s3_throughput/README.md` | headed "**State: builds, not yet flashed, never run**" (`:18`) and "No byte of this has run on the board" (`:26`). mtime 2026-08-21 11:25 | **stale as of today** — see §4.1 note |
| `*/CMakeLists.txt`, `*/sdkconfig.defaults*` | `csi_rx`/`csi_cfo` pull `EXTRA_COMPONENT_DIRS ../common`; `csi_tx` does not. `csi_rx`'s `sdkconfig.defaults` has one comment line `csi_cfo`'s lacks; otherwise identical content | current |

---

## 4. Discrepancies

### 4.1 Code that contradicts the docs — 9 found

**D1. `docs/HANDOFF.md:33` — the Heltec's row is now wrong in both columns.**
It reads `| Heltec S3 (HTIT-WB32LAF) | 8c:fd:49:b7:b0:6c | benched | RX works; WiFi TX inaudible |`.
At the time it was written "RX works" was an inference, and
`docs/NODE_CENSUS.md:470` says so in its own words ("Nothing in any CSV
names it… **Plausible, unverified**"). As of 2026-08-21 it is measured:
`firmware/csi_rx/build/project_description.json` records an `esp32s3`
build of `csi_rx`, and `data/raw/s3_20260821_125017.csv` carries 241,656
CSI rows at `node_id` 108 (= `0x6c`) with all three beacons and
`csi_len` 256. "Benched" is now false. Separately,
`docs/S3_PORT_SCOPE.md:24` records the 675 KB/s USB figure as "Not
recorded, and the newest artifact in the repo contradicts it", pointing
at `firmware/s3_throughput/README.md:18` — that README is now stale too.

**D2. `README.md:17` says the receivers filter on the TX MAC. The committed receiver filters nothing.**
`README.md:17`: "N RX nodes … CSI callback enabled, **filtering on the TX
node's MAC**." `firmware/csi_rx/main/main.c:68`:
`static const uint8_t TX_FILTER_MAC[6] = {0, 0, 0, 0, 0, 0};` and `:44`
`#define RFF_PROMISCUOUS 1`. The guard at `:114-119` is an OR of the six
bytes, so an all-zero filter accepts everything. The only filtered build
in the tree is the uncommitted `csi_cfo` change (§6, U4).
`docs/HANDOFF.md:112-114` reaches the same conclusion independently.

**D3. `README.md:76` and `pc/collect.py:70` both tell you to flip a firmware switch that does not exist.**
`README.md:76`: "set `OUTPUT_BINARY 0` in the firmware and reflash".
`pc/collect.py:70`: "…or OUTPUT_BINARY off in firmware".
`grep -rn OUTPUT_BINARY firmware/` over every `.c`, `.h` and
`CMakeLists.txt` returns **nothing**. There is no CSV fallback in any
committed firmware; `tlm_send_csi` is unconditional
(`firmware/csi_rx/main/main.c:179-182`).

**D4. `README.md:76`'s serial-headroom argument is contradicted by today's data.**
It states the node "captures ~50 CSI frames/s of this payload size (~15
KB/s), only about a third of the ~46 KB/s the link can carry", and
concludes "**going higher than 460800 buys nothing**". Measured on the
D0WD/UART collector right now: 218,016 frames / 1,559 s = **139.8 fps**,
at 284 B on the wire per v2 frame (`pc/throughput_test.py:129`,
`pc/diagnose.py:217`) = **39.7 KB/s = 86 % of the 46,080 B/s** that
460800 8N1 carries — with 8,660 node-side queue drops in the same window.
The "~50 fps / a third" premise is off by roughly 2.6×.

**D5. `firmware/csi_cfo/main/main.c:7` calls the reference stream "the clean, steady 100 Hz reference".**
The beacon does transmit at 100 Hz (`git show HEAD:firmware/csi_tx/main/main.c:17`,
`SEND_INTERVAL_MS 10`). What arrives is not that: measured today,
`a4:f0:0f:77:91:20` reaches the desk collector at 57,649 / 1,559 s =
**37.0 fps** and the S3 at 63,511 / 1,557 s = **40.8 fps**. Anything that
reads "100 Hz" as the observation rate — including
`pc/rff/dsp.py:73-74`'s "this runs per frame at 100 Hz" and the Nyquist
reasoning in `docs/HANDOFF.md:128` — is reasoning about the transmit
cadence, not the sample rate the estimator actually sees.

**D6. `PROJECT_NOTES.md:89` describes a `csi_cfo` that no longer exists in the working tree.**
It states the file is "byte-for-byte identical to
`firmware/csi_rx/main/main.c`" with "the `TAG` string inside … still
reads `"csi_rx"`". Verified: that is **true of git HEAD** (`diff` of the
two HEAD blobs is empty) and **false of the working tree**
(`firmware/csi_cfo/main/main.c:51,80,82`). `PROJECT_NOTES.md` is dated
2026-08-02 22:45 and the `csi_cfo` change is dated 2026-08-02 23:11 — 26
minutes later. `CLAUDE.md:60-67` already records this; `PROJECT_NOTES.md`
itself does not, and `PROJECT_NOTES.md:120,158,182` still recommend
deleting or implementing `csi_cfo` on the strength of the stale reading.

**D7. `docs/OCC_PROTOCOL.md:35` credits the scorer with a guard band it does not have.**
"first ~15 s of `empty` will contain your exit — that's fine, **the
scorer uses interval interiors**". `pc/occ_offline.py:268-282`
(`score_against_labels`) does no trimming: it takes `lab_arr == val` and
averages `active` over every bin of it, transition included. The
interval-interior guard exists only in `pc/exp_occ_ground_truth.py:116-124`
(`trim()`, `GUARD_S = 15.0` at `:61`), whose own docstring at `:19-20`
says "the committed scorer does not actually do that".

**D8. STATUS cadence: firmware says 5 s, two host tools say otherwise.**
`firmware/csi_rx/main/main.c:59` and `firmware/csi_cfo/main/main.c:66`:
`#define STATUS_PERIOD_MS 5000`. `README.md:313` agrees ("STATUS frames
every 5 s"). But `pc/diagnose.py:595` justifies its 8 s stall threshold
as "above the **~6 s** STATUS cadence", and `pc/field_diag.py:126`
justifies a 12 s listen window as "**two STATUS periods**" (2 × 5 = 10).
Neither default is wrong in effect; both rationales are.

**D9. `README.md:31` lists `pc/live_view.py` as a working tool.**
"`pc/live_view.py`    real-time subcarrier amplitude waterfall". Its
decoder accepts only magic `\xc5\x51` with a 21-byte header
(`pc/live_view.py:25-26`), i.e. protocol v1. Every committed firmware
emits v2, `\xc5\x52` (`firmware/common/telemetry/include/telemetry.h:28-29`).
Against any current node it decodes zero frames and renders a blank
waterfall — see §5, S2.

### 4.2 Code that contradicts other code — 10 found

**C1. `pc/capture.py`'s `compute_cfo` disagrees with `pc/rff/dsp.py` in four independent ways, and the number it prints is mislabelled.**
`pc/capture.py:24-33` vs `pc/rff/dsp.py:43-52, 71-103, 120-153`:

| | `capture.py:24-33` | `rff/dsp.py` |
|---|---|---|
| I/Q assembly | `iq[0::2] + 1j*iq[1::2]` (`:30`) | `iq[1::2] + 1j*iq[0::2]` (`:52`) — buffer is imag-first |
| subcarrier mask | none; fits every value in the frame (`:31-32`) | `_USABLE_IDX`, DC and guards excluded (`:35-38`, `:130`) |
| fit | `np.polyfit` least squares (`:32`) | `ransac_line`, 64 hypotheses, ≥25 % consensus, LS refit on inliers (`:71-103`) |
| x-axis | `np.arange(len(phases))` — buffer index (`:32`) | `K_USABLE`, physical subcarrier k, sorted (`:132`) |
| what it names the result | "CFO" (`:25`, and the TUI prints `CFO:` at `:158`) | slope = **SFO**; CFO is the *intercept delta over time* (`:138-143`) |

Measured on one `len=256` reference-beacon frame from
`desk_20260821_125017.csv`: `rff/dsp` returns a slope of **−0.00040
rad/subcarrier**; `capture.py`'s `compute_cfo` returns **+0.0578
rad/index** — two orders of magnitude apart and opposite in sign. It also
fits across the LLTF→HT-LTF boundary, since `len(iq)` is 256 for these
frames and `rff/dsp.py:49-51` deliberately stops at 128. The value is
EMA-smoothed into `Node.mac_cfo` (`:83`) and shown on screen (`:158`);
nothing else consumes it.

**C2. `pc/phase_skew.py`'s subcarrier mask fits the phase of the zero vector.**
`pc/phase_skew.py:31`: `USABLE = np.r_[np.arange(6,32), np.arange(33,59)]`,
commented "skip DC(32) + edges" — i.e. it treats the buffer index as a
linear subcarrier axis with DC in the middle. `pc/rff/dsp.py:22-26,33-38`
documents the real ESP32 layout: FFT order, DC at index **0**, guard band
at indices **27–37**. Measured on today's data (five `len=256` reference
frames): the exact-zero complex bins are indices **27–37**, exactly as
`rff/dsp.py` says. `phase_skew`'s mask therefore **includes 10 of those
11 null bins** and **excludes indices 1–5 and 59–63**, which carry
k = ±1..5 and are real signal. `np.angle(0+0j)` is 0, so those bins
contribute a hard zero to the unwrap and the least-squares fit at
`:66-71`. The "SFO slope" and "residual after slope removal" it prints,
and the VERDICT text at `:98-108`, are computed on that mixture.

**C3. `pc/fingerprint.py` builds 64-bin templates of which 11 bins are always exactly zero.**
`pc/fingerprint.py:33` `N_SC = 64`, `:49-52` takes `iq[:128]` and
`np.hypot` over all 64 bins with no usable mask. Verified on today's
data: bins 27–37 are exactly 0 in every frame checked, and the stored
templates confirm it — `data/fingerprints/*.json` `template` arrays are
length 64. So ~17 % of every fingerprint is a constant zero, and the
cosine distance at `:88-93` — compared against `MATCH_THRESHOLD = 0.15`
(`:35`) — is diluted by that constant in both operands.
`pc/rff/dsp.py:35` and `pc/occ/ingest.py:45` both use 52.

**C4. Transmit cadence is measured from two different clocks, and one of the two tools says the other's clock is wrong.**
`pc/node_census.py:30-35` states it plainly: `pc_time_us` is "stamped per
serial DRAIN BATCH, not per frame… **WRONG for cadence**", and
`cmd_cadence` (`:260-293`) uses `esp_timestamp_us` for exactly that
reason. `pc/diagnose.py:31-35` and `:132` use the node's `boot_ts_us` for
the same reason. `docs/HANDOFF.md:171` records it as methodological trap
#1. But `pc/twin_probe.py:389-426` (`cmd_timing`, whose stated job is "is
this a configured beacon or a passing consumer device?") builds its entire
gap distribution from `pc_time_us` (`:389`), sorts it (`:399`), and
reports median/p5/p95 gaps, a coefficient of variation, seven percentiles,
and "fraction of inter-frame gaps within ±20 % of the median" (`:424-426`)
— all on the batch clock.

**C5. `seq` is a node-global, and two tools group it by MAC anyway.**
`firmware/csi_rx/main/main.c:84,122`: `s_latest_seq` is a single global
written by the ESP-NOW receive callback from whichever beacon transmitted
most recently, and stamped onto every CSI frame regardless of source.
`pc/diagnose.py:44-51` documents this and **refuses** to report per-beacon
loss because of it. Nonetheless: `pc/field_diag.py:98-102` computes "seq
gaps: N missing beacon frame(s)" grouped by the dominant MAC, and
`pc/twin_probe.py:406` reports `np.mean(np.diff(sorted(seqs)) == 1)` per
source in its transmit profile. `firmware/common/telemetry/include/telemetry.h:16-17`
also asserts "seq gaps give the same for RF loss". With three beacons on
air — which is the state in every capture since 2026-07-14 — none of
those three numbers means anything.

**C6. Two beacon tables.** `pc/occ/__init__.py:19-23` `BEACON_MACS` maps
the three MACs to `B1`/`B2`/`B3`. `pc/occ_survey.py:20-24` defines its own
`BEACONS` with the same three MACs and different labels
(`B1(ref/wall)`), and does not import the shared one. Every other consumer
does import it (`diagnose.py:80`, `mac_census.py:29`,
`device_correlate.py:35`, `exp_occ_ground_truth.py:38`,
`zone_calib.py:194`, `occ/ingest.py:43`). A fourth beacon added to
`occ/__init__.py` would appear everywhere except `occ_survey.py`.

**C7. Two census tools normalise MACs differently.**
`pc/mac_census.py:52`: `m = row[i_mac].lower()`. `pc/node_census.py:72`:
`mac = p[3]`, no case folding. `pc/rff/protocol.py:47` emits lowercase, so
the two agree on every file that exists today; the divergence is latent
and would surface the moment any writer emitted an uppercase MAC.

**C8. Two decoders for the same wire format.** `pc/rff/protocol.py:23`
declares itself "the single source of truth for frame parsing".
`pc/live_view.py:29-60` is a private, v1-only copy of it that also drops
the resync/reject accounting `rff/protocol.py` keeps.

**C9. Two `labels_to_bins`, with different rounding.**
`pc/occ_offline.py:253-265` truncates (`int((t - t0) / dt)`), does not
clip the upper bound, and returns `None` when no label is non-empty.
`pc/zone_calib.py:77-88` rounds (`int(round(...))`), clips to `[0, n]`,
and always returns an array. `pc/device_correlate.py:38` imports
`zone_calib`'s; `pc/exp_occ_ground_truth.py:76` uses `occ_offline`'s. The
same labelled session bins up to half a bin differently depending on which
tool is run.

**C10. Two definitions of "our hardware".**
`pc/exp_window_convergence.py:794-795` defaults `--known-macs` to four
MACs (the three beacons plus the collector `f4:2d:c9:6f:8b:44`).
`pc/occ/__init__.py:19-23`, `pc/exp_lot_hypothesis.py:81` and
`pc/exp_thermal_evidence.py:125` all list three. Neither list includes
the Heltec `8c:fd:49:b7:b0:6c`.

*Noted, not a defect:* `pc/occ/ingest.py:168`, `pc/fingerprint.py:52`,
`pc/live_view.py:85` and `firmware/csi_rx/main/main.c:147-149` all compute
amplitude with the I and Q operands in orders that disagree with each
other and, in two cases, with `pc/rff/dsp.py:52`'s stated imag-first
layout. `hypot` is symmetric so there is **no numeric consequence** — but
it is the same confusion that produced C1, preserved in four places.

### 4.3 Numbers hard-coded in code that also appear in docs

Where they agree, that is worth recording too, because it is the reason a
change to one of them is dangerous. Disagreements are marked **≠**.

| quantity | in code | in docs | |
|---|---|---|---|
| WiFi channel 6 | `csi_rx:39`, `csi_cfo:44`, `csi_tx`(HEAD)`:16` | `HANDOFF.md:10` | agree |
| beacon interval 10 ms = 100 Hz | `csi_tx`(HEAD)`:17` | `HANDOFF.md:10`, `csi_cfo:7` | agree as **transmitted**; **≠** as received — D5 |
| console baud 460800 | `csi_rx/sdkconfig.defaults:2`, `csi_cfo:2`, `csi_tx:2`; PC defaults at `capture.py:178`, `collect.py:35`, `rff_live.py:176`, `field_diag.py:124`, `diagnose.py:584`, `occ_capture.py:47` | `README.md:76,83,346` | agree |
| UART ceiling 46,080 B/s | `throughput_test.py:134` (`DEFAULT_TODAY_BPS`, labelled operator-supplied) | `README.md:76` "~46 KB/s" | agree |
| v2 frame = 284 B on the wire | `throughput_test.py:129`, `diagnose.py:217` | `README.md:310-313` framing | agree |
| `CSI_MAX` / `CSI_BUF_MAX` 384 | `csi_rx:45`, `csi_cfo:52`, `telemetry.c:49,51`, `rff/protocol.py:31` | — | agree |
| calibration window 300 s | `node_hal.c:22` | `README.md:304,350`, `rff/serialio.py:5-6` | agree |
| STATUS period 5 s | `csi_rx:59`, `csi_cfo:66` | `README.md:313` | **≠** `diagnose.py:595` "~6 s", `field_diag.py:126` "two STATUS periods" = 12 s — D8 |
| queue depth 64 samples | `csi_rx:46`, `csi_cfo:53` | not in any doc | the constant behind today's 17 % / 3.8 % loss |
| reference MAC `a4:f0:0f:77:91:20` | `csi_cfo:80` (uncommitted), `twin_probe.py:65`, `occ/__init__.py:20`, `occ_survey.py:21`, `exp_lot_hypothesis.py:81`, `exp_thermal_evidence.py:125`, `exp_window_convergence.py:757,794` | `HANDOFF.md:30`, `README.md:210` | agree — 8 independent hard-codings |
| clock twin `f4:2d:c9:70:72:30` | `occ/__init__.py:22` (as plain link `B3`), `exp_window_convergence.py:757` (`--twin-macs`) | `CLAUDE.md:31-37`, `TWIN_INVESTIGATION.md:471` | agree; note `occ/__init__.py` carries no marker that `B3` is the twin |
| known ambient `84:7b:57:cc:20:0e` | `diagnose.py:88` | `CLAUDE.md:26`, `TWIN_INVESTIGATION.md` | agree |
| **twin yardstick** | `exp_lot_hypothesis.py:85-86` `TWIN_SIGMA 0.26`, `TWIN_DSFO 0.00080` | `TWIN_INVESTIGATION.md:206,471`, `LOT_HYPOTHESIS.md:22,92`, `CLAUDE.md:33` | agree |
| **the same yardstick, other value** | `twin_probe.py:313-314` prints "HANDOFF's stated true-twin scale for reference: **0.0004 rad/sc apart, 0.3 sigma**" | `HANDOFF.md:125` | **≠** — see below |
| separability line 3σ | `exp_lot_hypothesis.py:87`, `rff_offline.py:163`, `twin_probe.py:281`, `rff/discriminator.py:120`, `exp_window_convergence.py:700` | `LOT_HYPOTHESIS.md:92`, `HANDOFF.md` | agree — 5 independent hard-codings, none shared |
| χ² 5.991 / 9.210 | `rff/discriminator.py:23-24` | `README.md:225` | agree |
| thermal yardsticks 0.00237 / 0.00570 | `exp_thermal_evidence.py:129-130` | `LOT_HYPOTHESIS.md:59-60,371` | agree |
| beacon signature: ≥10 fps, ≥1000 frames, >99.9 % len-256 | `node_census.py:53-55`; `BEACON_MIN_FPS` re-used by `diagnose.py:83,488` | `LOT_HYPOTHESIS.md:179` | agree |
| `csi_len == 256` as the beacon marker | `node_census.py:90`, `diagnose.py:36` | `LOT_HYPOTHESIS.md:179` | agree; confirmed today (237,214 / 239,828 sampled S3 rows) |
| observation window = 64 frames | `rff/dsp.py:164`, `rff_live.py:177`, `rff_offline.py:223`, `twin_probe.py:552`, `exp_window_convergence.py:747` | `README.md:187` | agree |
| train fraction 0.6 | `rff_offline.py:38` | `README.md:213`, `LOT_HYPOTHESIS.md` | agree |
| **usable subcarrier count** | `rff/dsp.py:35-37` → 52; `occ/ingest.py:45` → 52 | `README.md:250` "52-bin" | agree — **but** `fingerprint.py:33`, `live_view.py:22`, `phase_skew.py:29` all use 64, `capture.py:36` uses 32 (display only), `csi_rx:65 MOTION_SC` uses 64. **Five different counts in one tree** |
| occupancy thresholds 10 Hz grid, 2 s window, z 5/12/3, RSSI guard 5 dB | `occ_offline.py:41,322-327`; **duplicated** as module constants at `exp_occ_ground_truth.py:58-60` rather than imported | `HANDOFF.md:180-183`, `OCC_PROTOCOL.md` | agree today; nothing keeps the duplicate in step |
| respiration ≥6 dB, ≥5 agreeing, bands 0.10–0.55 / 0.70–2.50 Hz | `occ/breathing.py:30-31,130` | `HANDOFF.md:157-159`, `OCC_PROTOCOL.md` | agree |
| local UTC offset −5.0 h | `exp_thermal_evidence.py:136` | `TWIN_INVESTIGATION.md` §4 | agree; hard-coded, so it is wrong on the other side of a DST boundary |
| `REBASELINE_STREAK` 20 | `rff_live.py:24` | `README.md` REBASE section | agree |
| cosine `MATCH_THRESHOLD` 0.15, `MIN_FRAMES` 25 | `fingerprint.py:34-35` | **nowhere** | orphan constants; no doc records where 0.15 came from |

**On the twin yardstick specifically** — this is the one worth acting on.
`docs/HANDOFF.md:125` says "0.0004 rad/sc apart, 0.3σ".
`docs/TWIN_INVESTIGATION.md:206` measures 0.26σ / +0.00080, and `:210`
and `:451` explicitly record that this **is** the reproduction of
HANDOFF's figure ("0.0004 rad/sc / 0.3σ reproduces as 0.00080 rad/sc /
0.26σ"). So the ΔSFO differs by a factor of two between the two docs, and
each figure has been hard-coded into a different script:
`pc/exp_lot_hypothesis.py:85-86` uses the reproduced pair and drives its
STRONG/WEAK/REFUTED verdict off it (`:311-322`), while
`pc/twin_probe.py:313-314` prints the HANDOFF pair as a reference line
directly beneath its own per-axis ΔSFO table. Run both tools on the same
session and they print different yardsticks for the same pair of boards,
neither labelled as disputed.

### 4.4 Silent-failure paths — 12 found

**S1. `firmware/csi_cfo` captures nothing, forever, if the reference beacon's MAC changes — and then reboots in a loop.**
`csi_cfo/main/main.c:126-131` compares `info->mac` against the compiled-in
`TX_FILTER_MAC` (`:80`) and returns early on any mismatch. Nothing is
queued, so `s_dropped` (`:143-145`) does not increment either — the node
reports zero frames *and* zero drops, which reads as a quiet channel.
Worse: `hal_rf_liveness_start(RF_SILENCE_RESTART_S)` at `:334` with
`RF_SILENCE_RESTART_S 120` (`:64`) arms a timer that calls `esp_restart()`
after 120 s with no frame drained (`node_hal.c:235-243`), so the node
enters a reboot cycle, and each reboot restarts the 300 s calibration gate
(`:307`, `calibration.c:64-67`). The OLED would read `WAITING FOR TX...`
(`:244`). **No STATUS field carries the filter value** — `tlm_status_t`
(`telemetry.h:35-46`) has no slot for it — so no host tool can tell this
apart from an off-air beacon. The filter is also uncommitted (§6, U4), so
git does not record which MAC any given flashed node is locked to.

**S2. `pc/live_view.py` shows a blank waterfall instead of an error against v2 firmware.**
`:25-26` `BIN_MAGIC = b"\xc5\x51"`, `BIN_HDR = 21` — v1 only. Against a v2
stream `decode_stream` (`:29-60`) finds no magic, sets
`consumed = n - 1` and returns `[]` every time. `reader.frames` stays
empty, `update()` (`:119-130`) skips both branches, and the window renders
the zero-filled image created at `:106-109` forever. `pc/collect.py:63-72`
has precisely the right warning for this class of failure; `live_view.py`
has none.

**S3. `pc/live_view.py` power-cycles the node it connects to.**
`:66` `self.ser = serial.Serial(port, baud, timeout=0.2)` — the one place
in `pc/` that bypasses `rff/serialio.open_serial`.
`pc/rff/serialio.py:1-11` documents exactly what that costs: pyserial
asserts DTR/RTS on open, which drives EN/GPIO0 and resets the board,
restarting the 300 s baseline calibration during which
`cal_gate_open()` suppresses **all** CSI output
(`firmware/csi_rx/main/main.c:179`, `calibration.c:64-67`). Opening
`live_view` on a running collector therefore takes it off the air for five
minutes and presents as "no signal" — compounding S2.

**S4. `pc/heatmap.py` renders a confident single-node field when two of its three nodes are missing, and re-reads 13 GB to do it.**
`:64` `node_name = filename.split('_')[0]`; `:66` `if node_name not in NODE_POS: continue`.
`NODE_POS` keys are `tx`, `desk`, `node3` (`:31-35`). In `data/raw/`
today: `desk_*` matches; `node3_*` has not been written since 2026-07-13;
`rx_*`, `occ_*`, `s3_*`, `csi_*` and `harvest_afternoon.csv` are all
silently skipped, and there has never been a `tx_*` file. `:82`
`except Exception: continue` swallows every parse error on top. The
Fresnel sum at `:100-120` then runs over whatever survived and
`calculate_spatial_frame` returns a plausible-looking heatmap. Separately,
`:70` `pd.read_csv(filepath)` reads each matched file **in full** on every
animation frame, at `interval=100` ms (`:232`); `data/raw/` currently
holds 13 GB including a 5.2 GB and a 2.4 GB file. (`pandas` is also not in
`pc/requirements.txt`.)

**S5. A wrong `--baud` produces a header-only CSV in `data/raw/`, with no error.**
`pc/rff/protocol.py:153-180`: `_try_v1`/`_try_v2` reject on checksum and
advance one byte, so garbage decodes to silence rather than to an
exception. `pc/collect.py:63-72` and `pc/diagnose.py:614-621` detect this
and say so. `pc/capture.py`, `pc/occ_capture.py` and `pc/rff_live.py` do
not: `capture.py:111-113` writes the header row before the read loop, so a
misconfigured run leaves a valid-looking, empty capture file in
`data/raw/` and the TUI shows `live` with `0 fr`.

**S6. The `dropped` counter wraps at 65,535 and two tools assume it does so at most once.**
`firmware/csi_rx/main/main.c:85` `static volatile uint16_t s_dropped`.
`pc/field_diag.py:106` `d = (drops[-1] - drops[0]) & 0xFFFF` and
`pc/diagnose.py:540` `d = (run.drop_last - run.drop_first) & 0xFFFF` both
compute the loss as one masked difference between the first and last frame
of the window. Measured today, the S3's counter **crossed 65,535 once
inside a 26-minute capture** (49,511 drops when summed frame-to-frame). At
~32 drops/s, any `diagnose --seconds 0` run longer than ~34 minutes
reports a plausible small number instead of the real one — and it is
reported as a "finding", so it looks authoritative. Summing per-frame
deltas is wrap-safe; neither tool does it.

**S7. `data/cache/rx_20260722_XXXXXX.csv.occ10hz.npz` is a cached analysis of a file whose provenance is unrecorded.**
`data/raw/rx_20260722_XXXXXX.csv` is 5.2 GB with a literal `XXXXXX` where
a timestamp belongs. Nothing in `pc/` can produce that name:
`capture.py:102`, `collect.py:40` and `occ_capture.py:56` all build the
name from `time.strftime`. `pc/occ/ingest.py:184-187` keys its cache on
`(CACHE_VERSION, st_size, int(st_mtime))` only, so the `.npz` will be
served for that file indefinitely regardless of what it is. Not a bug in
the cache; a hole in the record. `pc/occ_offline.py:351-354` — which warns
when a file was modified in the last 3 minutes — is the only
running-capture guard anywhere in `pc/`.

**S8. Rejecting a calibration floor silently substitutes a self-calibration on the file under test.**
`pc/occ_offline.py:100-113`: if the transferred floor's RSSI moved more
than `RSSI_GUARD_DB` (5 dB), `fl` is set to `None` and the code falls
through to fitting a floor on "the quietest half" of the *analysed*
session. Same construction at `pc/device_correlate.py:96-103` and
`pc/exp_occ_ground_truth.py:177-190`. All three do print a note
(`occ_offline.py:117-118`, `device_correlate.py:109-111`,
`exp_occ_ground_truth.py:182-191`), so this is honest — but the substituted
result is a percentage in the same table and format as a properly
calibrated one, and `device_correlate.py:50-54` records what it can cost:
84.9 % "active" on an overnight file against an expected sub-1 %.

**S9. `rff_offline --db` silently overwrites models learned by `rff_live`.**
`pc/rff_live.py:200-205` loads existing models out of the DB and resumes
them. `pc/rff_offline.py:199-212` (`persist`) does **not** load first: it
builds a `Discriminator` from this run only (`:140-148`) and then calls
`store.save_model` for each source, which is an
`ON CONFLICT(source_id) DO UPDATE` (`pc/rff/store.py:88-89`). The
`models` table has one row per source and no run identifier, so after an
offline run the live tool resumes from the offline centroid with nothing
recording the swap.

**S10. A link that stops delivering frames reads as "definitely not moving".**
`pc/occ/motion.py:49` correctly sets the metric to `NaN` where a window
holds too few valid samples ("absence of data must not read as absence of
motion", `:30-31`). But `FusedDetector.detect` at `:159-160` does
`Z = np.where(np.isfinite(Z), Z, -np.inf)` before sorting, so those NaNs
become the smallest possible value. With the 2-of-3 rule at `:163-164`
(`second = Zs[-2]`), losing one link is handled; losing two silently
degrades the detector to `top > z_solo` on a single link, with no message.
The coverage percentages are printed (`occ_offline.py:130`) but nothing
connects them to the voting rule.

**S11. `exp_thermal_evidence paired` — the two-receiver test — cannot see today's two-receiver session.**
`pc/exp_thermal_evidence.py:943-944` selects sessions by filename prefix:
`{s[5:] for s in ser if s.startswith("desk_")} & {s[6:] for s in ser if s.startswith("node3_")}`.
No `node3_*` file has been written since 2026-07-13, and today's second
receiver writes `s3_*`. Against any tag built from post-07-13 captures
`bases` is empty, the loop body never runs, and `cmd_paired` prints its
header (`:937-939`) followed by nothing, with no explanation. Today's
`desk_20260821_125017.csv` / `s3_20260821_125017.csv` pair — one
transmitter, two receivers, the same minutes, which is exactly the input
this test was written for — is skipped.

**S12. `firmware/csi_rx/sdkconfig` now targets `esp32s3`, and it is gitignored.**
`firmware/csi_rx/sdkconfig:391` `CONFIG_IDF_TARGET="esp32s3"`, mtime
2026-08-21 12:20; the previous `esp32` config is preserved as
`sdkconfig.old:252`. `.gitignore:3-4` excludes both, so `git status` is
clean and no artifact records the switch. `README.md:85` warns that "a
stale `build/` cache or a leftover `sdkconfig` will re-assert the old
value" and prescribes `idf.py set-target esp32` — that warning now cuts
the other way: a plain `idf.py build` in `firmware/csi_rx/` produces an
S3 image, and flashing it to a D0WD collector will not run. Related and
**unknown**: the S3 config keeps `CONFIG_ESP_CONSOLE_UART_CUSTOM=y` on
GPIO1/GPIO3 (`:1298,1308-1310`) alongside
`CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=y` (`:1301`). Telemetry
plainly reaches the host — 241,656 rows today — but which of the two
consoles carries `stdout`, and whether the binary stream is also being
mirrored onto the UART pins, is recorded nowhere in this repo and was not
tested here.

### 4.5 Uncommitted or diverged from git HEAD — 9 tracked items, plus untracked

Reported only. Nothing was staged, committed, stashed or reverted.
Last commit: `9780351`, 2026-07-17 00:30. Last commit touching
`firmware/csi_tx/`: `2d2b0c2`, 2026-07-14.

| # | path | difference | mtime |
|---|---|---|---|
| U1 | `firmware/csi_tx/main/main.c` | **replaced, not extended.** HEAD is the ESP-NOW beacon (79 lines, `esp_now_send` loop at `:68-78`); the working tree is a standalone NimBLE advertiser `CSI-S3-ALIVE` (70 lines) with no ESP-NOW at all. Flashing it to a beacon takes that beacon off air | 2026-07-22 18:50 |
| U2 | `firmware/csi_tx/main/CMakeLists.txt` | `+PRIV_REQUIRES bt nvs_flash` | 2026-07-22 18:50 |
| U3 | `firmware/csi_tx/sdkconfig.defaults.s3` | `+CONFIG_BT_ENABLED=y`, `+CONFIG_BT_NIMBLE_ENABLED=y`. The diff shows 3 removed / 6 added because the file was also converted to CRLF; `git diff --ignore-all-space` shows the real change is those two lines plus a comment | 2026-07-22 18:50 |
| U4 | `firmware/csi_cfo/main/main.c` | `RFF_PROMISCUOUS 1→0` (`:51`), `TX_FILTER_MAC` all-zero → `A4 F0 0F 77 91 20` (`:80`), `TAG "csi_rx"→"csi_cfo"` (`:82`), header comment rewritten. **No artifact records this being flashed or verified**, and it postdates `PROJECT_NOTES.md` by 26 minutes — which is why that file still calls `csi_cfo` a duplicate (D6) | 2026-08-02 23:11 |
| U5 | `README.md` | two hunks: a new **Privacy** section (+18 lines after `:95`), and the headline accuracy figures changed from "99.6% over 10k windows" to the split "99.7% over 7,497 (desk alone) / 95.7% over 14,234 (with node3)" at `:210-216` | — |
| U6 | `docs/HANDOFF.md` | +145 lines: two "Correction — 15 August 2026" blocks, one on the hardware inventory, one on the BLE-as-scaffolding characterisation | 2026-08-15 19:48 |
| U7 | `pc/heatmap.py` | shows as **232 insertions / 232 deletions** in `git diff --stat`, but `git diff --ignore-all-space` is **empty**. The file was converted LF → CRLF and nothing else changed | — |
| U8 | `data/fingerprints/*.json` (13 files) | shows as **2,433 insertions / 2,433 deletions**, and `git diff --ignore-all-space` is likewise **empty**. LF → CRLF only. mtimes are still 2026-07-13 15:46 — **nothing was re-derived** | 2026-07-13 15:46 |
| U9 | gitignored but diverged | `firmware/csi_rx/sdkconfig` retargeted to `esp32s3` today (S12); `firmware/csi_rx/build/` rebuilt 12:20–12:22. `.gitignore:3-4` hides both | 2026-08-21 12:20 |

**Untracked, never committed** (`git status --porcelain`): `CLAUDE.md`,
`PROJECT_NOTES.md`, `.claude/`, `git-guard/`, `site/`, `docs/img/`, 11 of
the 13 files in `docs/` (only `HANDOFF.md` and `OCC_PROTOCOL.md` are
tracked), the whole of `firmware/s3_throughput/`, and 11 `pc/` scripts:
`device_correlate.py`, `diagnose.py`, `exp_lot_hypothesis.py`,
`exp_occ_ground_truth.py`, `exp_thermal_evidence.py`,
`exp_window_convergence.py`, `mac_census.py`, `node_census.py`,
`throughput_test.py`, `twin_probe.py`, `zone_calib.py`. That is roughly
5,900 lines of Python and 283 lines of C that exist only in the working
tree.

Also worth knowing: `.gitignore:24` is an unanchored `*.csv`. Every CSV
any tool writes anywhere in the tree is invisible to git — including
`pc/node_census.py`'s `--cache census_full.csv` default (`:303`) and
`pc/exp_window_convergence.py`'s `--dump-trials` output (`:759-762`). A
clean `git status` is not evidence that no analysis output exists.

---

## 5. Counts

| category | found |
|---|---|
| 4.1 code contradicts docs | 9 |
| 4.2 code contradicts other code | 10 |
| 4.3 numbers hard-coded in code that also appear in docs — disagreements | 4 (twin yardstick, STATUS cadence, subcarrier count, 100 Hz as-received) out of 27 quantities checked |
| 4.4 silent-failure paths | 12 |
| 4.5 uncommitted or diverged | 9 tracked items + 3 untracked groups |
| **total** | **44** |

## 6. What this pass did not check

- Whether any of the science results are correct. Nothing here re-ran a
  pipeline, re-derived a σ, or checked an accuracy figure. The
  §4.3 table records where numbers live, not whether they are right.
- Any behaviour of `firmware/` on hardware, beyond what today's two live
  capture files show. Nothing was flashed, no port was opened.
- `site/`, `git-guard/`, `docs/*.md` as a whole, and all `build*/` trees.
- The generated `sdkconfig` files beyond the specific lines cited in D8,
  S12 and §3.
- Whether the drain task's ~32 drops/s on the S3 is `fwrite`+`fflush`
  cost, OLED I²C contention, or something else. That needs an
  instrumented build, and no artifact in the repo measures it.
