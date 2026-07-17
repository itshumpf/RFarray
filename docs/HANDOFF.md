# RF Clock-Fingerprinting Array — Session Handoff

Paste this into a new chat to continue work on this system. Everything
below is measured fact from the repo at `C:\dev\csi-array` (git,
branch `main`) unless marked as an open question.

## What this system is

A WiFi-CSI sensing array for home security. ESP32 beacon nodes transmit
100 Hz reference packets on **channel 6**; one PC-connected collector
(`csi_rx` fw, COM3, 460800 baud) captures per-frame CSI (channel state
information) promiscuously — beacons AND every ambient device. The PC
does all the science (`pc/rff/`): RANSAC line fits on LLTF subcarrier
phase yield per-frame **SFO** (slope = sampling clock offset) and CFO
proxies; windowed medians → per-source 1D Kalman drift tracks →
Mahalanobis discrimination against per-source Gaussian models (Welford)
→ SQLite history (`data/rff.db`). Device identity = crystal-oscillator
imperfections, which survive MAC randomization.

Read `README.md` for architecture/protocol/calibration details. Key
tools: `pc/capture.py` (raw CSI recorder), `pc/rff_offline.py` (model
builder + honest holdout scoring; `--only-macs`, `--ref-mac`),
`pc/rff_live.py` (live TUI), `pc/field_diag.py` (node health).

## Hardware inventory (2026-07-15)

| board | MAC | role | state |
|---|---|---|---|
| ESP32 D0WD | f4:2d:c9:6f:8b:44 | collector, COM3 | healthy |
| ESP32 D0WD | a4:f0:0f:77:91:20 | TX beacon (reference) | on-air |
| ESP32 D0WD | 28:05:a5:2f:fa:48 | TX beacon | on-air |
| ESP32 D0WD | f4:2d:c9:70:72:30 | TX beacon | on-air; clock-twin of a4:f0 |
| Heltec S3 (HTIT-WB32LAF) | 8c:fd:49:b7:b0:6c | benched | RX works; WiFi TX inaudible (open bug, below) |
| Heltec S3 sibling | ? | unused | likely still runs Meshtastic |

## Measured results (don't re-derive; challenge with new data only)

- Same-model ESP32 discrimination on (CFO, SFO) tops out ≈ **77%**
  holdout (distinct units 1.8–2.7σ apart). Two boards are true clock
  twins: 0.0004 rad/sc apart, 0.3σ, coin-flip.
- A real ambient device separated at **11–15σ**, 7/7 holdout — the
  cross-manufacturer regime is where the security use case lives.
- CFO is aliased at 100 Hz beacon rate (Nyquist ±50 Hz) → **SFO slope is
  the discriminating feature.**
- Clock signatures **wander thermally**: pairs moved 2.7σ→1.3σ over an
  hours-long session. Drift-vs-temperature is unmodeled (see below).
- Reference-beacon subtraction cancels RX-side drift across
  sessions/receivers (two RX agreed on a source's SFO to 0.0004 rad/sc)
  but does NOT help within-session same-model separation.

## Phase 3: occupancy sensing (2026-07-17) — `pc/occ/`

Amplitude-domain occupancy pipeline, additive to rff/ (imports only the
LLTF mapping). Tools: `occ_survey.py`, `occ_offline.py` (calibrated
motion + respiration + zones + label scoring), `occ_capture.py`
(keyboard-labeled ground truth), `test_occ_synth.py` (synthetic DSP
checks, all passing). Protocol for honest rates: `docs/OCC_PROTOCOL.md`.

**Measured (assumed labels: overnight 03:11-08:40 Jul-14 = no known
occupant in the sensed room, evening 20:17-00:10 Jul-15 = user at
desk; scripted labeled session still pending). Household context that
bounds the claims: 2 cats roam freely, family (incl. son) sleeps in
other rooms, and neighbors are close — the overnight null is NOT a
guaranteed-empty house:**

- Motion: overnight interior (03:45-08:20) flagged 0.50% of time —
  8 events of 5-27 s. With free-roaming cats these may be TRUE
  detections, so 0.5% is activity-flagged time, not a false-alarm
  rate; the controlled empty segment in the protocol measures that.
  Evening: 53% active, 97 events. Detection edges match the human
  narrative to the minute (to-bed 03:11-03:26, wake 08:36).
- Respiration (still person): evening quiet segments 35/45 link-scans
  flagged presence, 7-12 bpm at 10-14 dB SNR, 10/10 subcarrier
  frequency consensus. Overnight: 0/24 above threshold. The separation
  between an occupied-but-still sensed room and a nobody-in-the-room
  night is unambiguous on this data. One overnight near-hit (B1
  03:52-04:08, 4.9 dB, 10 bpm, 8/10 agree) is a candidate through-wall
  sleeper — most plausibly the son in an adjacent room; the protocol
  has a `wall-sleeper` test to confirm.
- Zones: evening events cluster into 3 stable cross-link profiles
  (e.g. B3-dominant vs B2/B1-dominant); geometry is resolvable, but
  naming clusters needs a labeled calibration walk.

**Methodological traps found and fixed (both cost real signal):**

1. `pc_time_us` is stamped per serial *drain batch*, not per frame —
   bursty, useless for spectra. Grids are built on unwrapped
   `esp_timestamp_us` (reboot-resynced against pc time).
2. The motion metric's noise floor scales ~1/sqrt(frames-per-bin) and
   per-link rates shift between sessions; an unconditioned floor turned
   B3's 55->37 fps change into a fake permanent +19.6 sigma. Floors are
   count-conditioned now.
3. Respiration band-edge peaks are 1/f drift leakage and fake perfect
   subcarrier consensus; interior-local-max required now.
4. Cross-session calibration transfer is guarded: a link whose RSSI
   moved > 5 dB from calibration self-recalibrates (B3 physically
   changed -64 -> -77 dBm sometime before the Jul-15 evening session —
   worth asking what moved near it during the S3 bench work).

## Open threads, highest value first

0. **Run the scripted occupancy session** (`docs/OCC_PROTOCOL.md`,
   ~25 min) — converts the assumed-label results above into honest
   labeled detection/false-alarm rates (cats excluded during `empty`),
   measures pet immunity with labeled cat segments (rate band 20-30 vs
   12-20 bpm is a human/cat discriminator), and optionally confirms
   the through-wall sleeper. A per-zone labeled walk names the three
   cross-link clusters. Also: find out what changed B3's path (-13 dB)
   on Jul-15.
1. **Embed TX die temperature in beacon payloads.** No weather hardware
   exists yet — but every ESP32 has an internal temp sensor. Extend the
   8-byte beacon (`magic|seq`) with temp; collector logs it per frame;
   correlate/compensate the thermal drift that currently smears
   centroids. Classic ESP32 needs the ROM `temprature_sens_read()`
   (sic); S2/S3/C3 have a proper driver. This is the top improvement
   and costs $0.
2. **v3 features to crack same-model/twin discrimination:** the RANSAC
   fit currently throws away the per-subcarrier phase RESIDUAL shape
   (multipath + hardware nonlinearity signature), I/Q imbalance,
   amplitude ripple. Literature says these separate near-identical
   radios. Add residual-vector features → higher-dim Mahalanobis (or a
   small classifier), re-score the existing 2.8M-frame dataset in
   `data/raw/` — no new captures needed to validate.
3. **S3 WiFi-TX bug (benched Heltec):** transmits per MAC layer
   (air_ok 100%, ch 6, 20 dBm, fresh RF cal, 2 antennas, 1M + MCS0
   rates) yet a live collector 1 m away hears zero. RX path works
   (hears beacons at −71). Board previously paired with a phone via
   BLE under Meshtastic (2.4G TX radiated then). A NimBLE advertiser
   diagnostic was flashed; phone saw a Meshtastic-named BLE device but
   the unplug-disambiguation (was it this board or the sibling?) was
   never confirmed. If BLE provably radiates from THIS board, the
   fault is S3 WiFi-TX software — compare esp-csi project's S3 TX
   examples, try esp_now_set_peer_rate_config, try plain 802.11 data
   frames, check IDF 5.5.4 S3 errata.
4. **Per-MAC sequence tracking:** csi_rx tags every CSI record with the
   latest ESP-NOW seq from ANY beacon (single global var) — with 3
   beacons the seq column is cross-contaminated. Move to per-MAC seq or
   drop seq-gap analysis for multi-beacon fleets (`field_diag.py` gap
   stats are affected too).
5. **Multi-receiver deployment** (2nd RX exists in firmware as
   `csi_cfo`): cross-RX drift agreement already validated; a Pi host is
   planned. Enables spatial features + redundancy.
6. **Purchases planned:** a non-Espressif-D0WD board to replace one
   clock-twin beacon; a BME280-class environment node (until then, #1
   covers temperature).

## Hard-won gotchas (violate at your peril)

- Work at `C:\dev\csi-array`, NOT the OneDrive copy. IDF env bootstrap:
  set `IDF_TOOLS_PATH=C:\Espressif`,
  `IDF_PYTHON_ENV_PATH=C:\Espressif\python_env\idf5.5_py3.11_env`, then
  dot-source `C:\Espressif\frameworks\esp-idf-v5.5.4\export.ps1`
  (export.ps1 mis-detects system Python 3.14 otherwise).
- **Never open a node's COM port with plain pyserial** — DTR/RTS
  resets the board and restarts its 300 s calibration. Always
  `rff/serialio.py::open_serial`.
- **Check a capture CSV's mtime before trusting tail reads** — a dead
  capture.py once produced 14 h of stale-data false conclusions.
- Heltec boards: pull the **LiPo battery** when debugging (USB unplug
  doesn't reboot otherwise; uptimes lie). S3 flashing: `--no-stub`
  (stub dies over ROM USB-CDC); `erase_region 0x9000 0x6000` wipes NVS
  (PHY cal) stublessly; may need manual RST after flash; manual
  download mode = hold BOOT, tap RST. S3 builds live in `build_s3/`
  (`-B build_s3 -D SDKCONFIG=build_s3/sdkconfig -D
  SDKCONFIG_DEFAULTS=sdkconfig.defaults.s3`).
- COM3 flashing is flaky at 460800 — retry at `-b 115200`. Arduino IDE
  steals COM ports; close its serial monitor.
- `firmware/csi_tx/main/main.c` currently holds the BLE diagnostic;
  production beacon = git HEAD (a no-rate-config-on-S3 variant is in
  the session scratchpad). `sdkconfig.defaults.s3` has BT enabled for
  the diagnostic — remove those two lines for production beacon builds.
- Windows console is cp1252 — keep tool output ASCII.

## Working style that fit this project

Verify end-to-end after every change (flash → live census at the
collector, not just build success). Prefer measured σ over theory.
Report failures plainly — the honest 55% was more useful than the
flattering 99.5%. When hardware misbehaves, distrust the test setup
before the silicon (the battery, the stale CSV, and the cached BLE
name each burned an hour).
