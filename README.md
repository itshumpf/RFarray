# ESP32 WiFi CSI Sensing Array — v1: Raw Data Collection

Cameraless home security via WiFi Channel State Information (CSI). When a person moves through a room, they perturb the multipath RF environment; CSI captures per-subcarrier amplitude/phase of every received WiFi frame, so movement shows up as characteristic ripples in the data.

## Architecture

```
                    2.4 GHz, fixed channel (default 6)
  ┌─────────┐   ESP-NOW broadcast @ 100 Hz   ┌─────────┐
  │  TX node │ ─────────────────────────────► │ RX node 1│──USB──┐
  │ (1x ESP32)│ ────────────────────────────► │ RX node 2│──USB──┤►  PC (later: Pi)
  └─────────┘  ─────────────────────────────► │ RX node N│──USB──┘   collect.py → CSV
                                              └─────────┘            live_view.py
```

- **1 TX node** broadcasts small ESP-NOW packets at a fixed rate (100 Hz default). One transmitter, many listeners — every RX node hears the *same* packets, which makes multi-node data time-alignable via the sequence number embedded in each packet.
- **N RX nodes** sit in different rooms/corners, CSI callback enabled, filtering on the TX node's MAC. Each CSI capture is streamed as one compact binary frame over USB serial at 460800 baud; the PC decodes and logs it as CSV.
- **PC** runs `collect.py` (one instance per RX node / COM port) writing timestamped CSV files, and `live_view.py` for a real-time amplitude waterfall so you can *see* motion immediately.

Why a dedicated TX instead of the router: constant, known packet rate (router traffic is bursty), fixed channel, fixed MAC to filter on, and identical reference signal across all RX nodes. You can still add router-ping mode later.

### RFF note
Your project mentions RF fingerprinting. The same CSI stream (plus `rssi`, `noise_floor`, and raw LLTF) is the input you'd use to fingerprint *transmitters* — the collector stores everything needed, so v1 data is reusable for that.

## Repo layout

```
firmware/csi_tx/   ESP-IDF project — broadcaster
firmware/csi_rx/   ESP-IDF project — CSI receiver / serial dumper
pc/collect.py      serial → CSV logger
pc/live_view.py    real-time subcarrier amplitude waterfall
pc/requirements.txt
```

## Deployment (3 boards)

| Board | Role | Power | Firmware |
|---|---|---|---|
| Desk unit (COM12, 0.96" OLED) | RX + status display → PC | USB (PC) | `csi_rx` |
| Outlet unit #1 | TX beacon | wall outlet | `csi_tx` |
| Outlet unit #2 | spare / future 2nd RX | wall outlet | — |

The desk unit's OLED (SDA=21, SCL=22, flipped 180° for upside-down mounting; see defines at top of `csi_rx/main/main.c`) shows: packet rate, RSSI, latest seq, a smoothed motion metric, and a live motion bar. It shows "WAITING FOR TX..." until the beacon node is powered. The OLED is optional — the firmware runs headless if none is detected.

## Setup (Windows)

1. Install ESP-IDF v5.x via the ESP-IDF Windows installer (docs.espressif.com → ESP-IDF Get Started → Windows). Open the "ESP-IDF PowerShell" it creates.
2. Flash the TX node (plug in one board, note its COM port in Device Manager):
   ```
   cd firmware/csi_tx
   idf.py set-target esp32
   idf.py -p COM5 flash monitor
   ```
3. Flash each RX node the same way from `firmware/csi_rx`.
4. PC side:
   ```
   pip install -r pc/requirements.txt
   python pc/collect.py COM6 --out node1.csv        # one per RX node
   python pc/live_view.py COM6                      # or watch live
   ```

## Serial data format (RX → PC)

One line per CSI capture:

```
CSI,<seq>,<mac>,<rssi>,<noise_floor>,<channel>,<timestamp_us>,<len>,"[i0,q0,i1,q1,...]"
```

`buf` is int8 imaginary/real pairs per subcarrier (LLTF first; HT-LTF follows if present). Amplitude of subcarrier k = `sqrt(i^2 + q^2)`.

## Tuning knobs

- Channel: `CSI_WIFI_CHANNEL` define in both `main.c` files — keep TX and RX identical; pick one away from your busiest home WiFi if possible.
- TX rate: `SEND_INTERVAL_MS` in `csi_tx/main/main.c` (10 ms = 100 Hz). 50–100 Hz is plenty for human motion (<10 Hz Doppler).
- Baud: **460800** in firmware and all PC scripts. At 460800 the UART is *not* the bottleneck — the RX node captures ~50 CSI frames/s of this payload size (~15 KB/s), only about a third of the ~46 KB/s the link can carry. The frame rate is limited by the RF link (how many of the 100 Hz beacons actually survive the trip to the node), not the serial speed, so **going higher than 460800 buys nothing** and only risks corruption on cheap USB bridges. That rate is plenty for human motion (<10 Hz Doppler) and usable for SFO/CFO — `phase_skew.py` prints an honest Nyquist verdict for the effective rate. To fall back to human-readable CSV for debugging, set `OUTPUT_BINARY 0` in the firmware and reflash (then pass matching `--baud`).
  - **The baud is gated behind the console channel choice — this is the trap that cost us hours.** `CONFIG_ESP_CONSOLE_UART_BAUDRATE` has its Kconfig prompt `if ESP_CONSOLE_UART_CUSTOM`. With the default `Channel for console output = Default: UART0`, the symbol has *no prompt*: it is not user-settable and silently forces `default 115200`, ignoring any value you put in `sdkconfig` or `sdkconfig.defaults` (and the menuconfig field is non-interactive). To change the baud you **must** select `Custom UART` — which on ESP32 defaults to the *same* UART0/GPIO1/GPIO3 as Default, so it's the identical USB path, just with the baud field unlocked. The `sdkconfig.defaults` here do exactly that:
    ```
    CONFIG_ESP_CONSOLE_UART_CUSTOM=y
    CONFIG_ESP_CONSOLE_UART_CUSTOM_NUM_0=y
    CONFIG_ESP_CONSOLE_UART_TX_GPIO=1
    CONFIG_ESP_CONSOLE_UART_RX_GPIO=3
    CONFIG_ESP_CONSOLE_UART_BAUDRATE=460800
    ```
  - **Regenerate cleanly after changing baud:** `idf.py set-target esp32` (moves the old `sdkconfig` aside and rebuilds it from `sdkconfig.defaults`), then `idf.py -p COMxx flash` every RX board, then capture (PC tools default to 460800 now). Confirm it took with `grep ESP_CONSOLE_UART_BAUDRATE sdkconfig`. A stale `build/` cache or a leftover `sdkconfig` will re-assert the old value, so `set-target` (or `fullclean`) is what forces the defaults to win. There is no runtime baud switch on ESP32 — console baud is compile-time only. `collect.py`/`capture.py` warn "bytes/no frames (baud?)" if the PC `--baud` ever disagrees with the board, instead of silently writing 0-byte CSVs.
  - **Keep this project OUT of OneDrive/synced folders.** ESP-IDF's `build/` churns thousands of files; cloud sync racing the build corrupts caches and makes edits appear not to stick. Use a local path like `C:\dev\csi-array`.
- Wire format: `C5 51 | seq u32 | mac[6] | rssi i8 | noise i8 | chan u8 | tstamp u32 | len u16 | csi[len] i8 | xor-checksum u8`, little-endian. The PC decoders resync on the magic bytes and validate the checksum, so interleaved boot logs and split reads are handled automatically.

## Data pipeline & RF fingerprinting

```
serial ──► pc/collect.py ──► data/raw/*.csv ──► pc/fingerprint.py ──► data/fingerprints/*.json
```

- **data/raw/** — session recordings. Name them descriptively: `python pc\collect.py COM12 --out data\raw\baseline_night.csv`. Raw CSI at 100 Hz is ~250 MB/hour, so record deliberate sessions rather than 24/7; zip old ones.
- **data/fingerprints/** — one JSON per device: normalized CSI amplitude template, template stability, RSSI stats, frame-length histogram.

**Capturing from all nodes at once:** `capture.py` reads every node in one window with a live green CSI waterfall, writing one CSV per node into `data/raw/`:

```
python pc\capture.py COM12:desk COM7:node3      # PORT:name per node
python pc\capture.py --demo                     # no hardware, synthetic rain
```

`collect.py` is still there for logging a single port to a named file. Both write the identical CSV format.

Workflow:

```
# 1. record a session while a known device is active near the node
python pc\collect.py COM12 --out data\raw\phone_session.csv

# 2. learn its signature
python pc\fingerprint.py build data\raw\phone_session.csv --mac aa:bb:cc:dd:ee:ff --name phone

# 3. later, score any capture against the library
python pc\fingerprint.py match data\raw\overnight.csv
```

`match` verdicts: KNOWN (MAC + signature agree), SIGNATURE MATCH NEW MAC (same radio, rotated/spoofed MAC), MAC KNOWN BUT SIGNATURE OFF (someone imitating a trusted MAC — investigate), STRANGER (unknown radio).

For fingerprint-hunting sessions, set `RFF_PROMISCUOUS 1` in `csi_rx/main/main.c` and reflash — the node then captures CSI for *every* decodable frame on the channel, catching far more household-device traffic. Set it back to 0 for clean motion sensing (either mode keeps the display working). Note: modern phones randomize MACs while unassociated; fingerprint devices while they're on your network for stable identities.

## CFO / SFO fingerprinting (RFF v2) — node 3

Amplitude fingerprints mix in *where* a device is; clock-based fingerprints (carrier + sampling frequency offset) come from the transmitter's crystal and don't move with the device. `pc/phase_skew.py` estimates them from CSI phase:

```
python pc\phase_skew.py data\raw\node3_cfo.csv           # busiest MAC
python pc\phase_skew.py data\raw\node3_cfo.csv --mac aa:bb:cc:dd:ee:ff
```

**Node 3 is a dedicated clean-capture receiver.** Flash `firmware/csi_cfo` to it and wire it to the PC on its own COM port (yes — a second ESP32 on the PC is the right move; each RX needs its own host until the Pi arrives). It ignores promiscuous traffic and auto-locks onto the TX beacon, capturing only that steady 100 Hz identical-packet stream — the clean reference SFO/CFO estimation needs.

```
cd firmware\csi_cfo
idf.py set-target esp32
idf.py -p COMyy flash                     # COM port of the 2nd ESP32
python pc\collect.py COMyy --out data\raw\node3_cfo.csv
python pc\phase_skew.py data\raw\node3_cfo.csv
```

**Hard limits, learned from real captures:**
- CFO is only measurable up to ±(frame_rate / 2) — the Nyquist limit. At the beacon's 100 Hz that's ±50 Hz; on bursty ambient AP traffic (≈80 ms gaps) it collapses to ±6 Hz and CFO aliases to noise. This is why the steady beacon + node 3 matters.
- The ESP32 corrects most CFO in hardware, so **SFO slope is the realistic fingerprint**, not raw CFO. `phase_skew.py` reports both plus a Nyquist warning and an honest usability verdict.
- ESP32 phase carries an unknown per-packet timing offset; single-packet recovery is unreliable, so the tool works over many frames.

## Roadmap after raw collection works

1. **Sanity check**: record 60 s empty room, 60 s walking. The waterfall difference should be obvious.
2. **Motion metric**: moving variance of subcarrier amplitudes → threshold → presence flag.
3. **Multi-node**: seq-aligned features from all nodes → coarse zone localization.
4. **Pi migration**: collector is pure Python/pyserial — runs unchanged on a Pi; add MQTT/Home Assistant publishing.

## Known plain-ESP32 CSI quirks

- Subcarrier count varies with packet format (LLTF 64, +HT-LTF up to 128+); the code logs `len` so parsing is self-describing.
- ESP32 CSI phase is noisy (no phase calibration in hardware) — use amplitude-based features first.
- Keep `esp_wifi_set_ps(WIFI_PS_NONE)`; power save mangles timing.
- Reference: Espressif's esp-csi repo (github.com/espressif/esp-csi) has more advanced examples once v1 works.

## RFF v2 — scientific CFO/SFO discrimination pipeline (`pc/rff/`)

The `phase_skew.py` probe grew into a full discrimination system. Signal
path, per the v2 spec:

```
serial frames -> phase unwrap (+ temporal continuity) -> RANSAC line fit
  -> per-frame (slope=SFO proxy, intercept) -> windowed robust medians
  -> reference-beacon drift subtraction -> 1D Kalman per source
  -> Mahalanobis vs learned centroids -> SQLite + TUI
```

- `rff/dsp.py` — physically correct LLTF mapping (FFT order -> subcarrier
  k, guards/DC dropped), unwrap with continuity correction, vectorized
  RANSAC (multipath curvature and junk bins become outliers instead of
  biasing the slope).
- `rff/kalman.py` — random-walk 1D Kalman per source tracks thermal
  clock drift; window IQR feeds the measurement noise.
- `rff/discriminator.py` — running Gaussian model per source (Welford),
  Mahalanobis distance with chi-square thresholds (95% / 99% ellipses).
- `rff/reference.py` — the TX beacon's own track is subtracted from every
  other source, cancelling the receiver's systemic drift.
- `rff/store.py` — SQLite history [source, CFO, SFO, timestamp, RSSI] +
  persisted centroids in `data/rff.db`; live runs resume what they learned.

**Offline science run** (replays recorded sessions, reports per-source
stability, pairwise sigma-separation, blind train/holdout accuracy):

```
python pc\rff_offline.py data\raw\desk_*.csv --ref-mac a4:f0:0f:77:91:20 --db
```

First measured result (11 sessions, 2026-07-13, ref-corrected): pairwise
separation 2.6 sigma, holdout accuracy 99.6% over 10k windows. Reference
correction more than doubled the separation vs raw (1.0 sigma).

**Live discrimination TUI** (one thread per node, same pipeline):

```
python pc\rff_live.py COM3:node1 COM12:node3 --ref-mac a4:f0:0f:77:91:20
```

Verdicts: LEARNING -> STABLE / DRIFTING / ANOMALY (chi-square on the
source's own ellipse). Anomalous windows never update the model, so a
spoofer can't teach the system its own signature.

**Safe-Boot (recovery) mode**: hold the BOOT button while the app starts
(release EN first — GPIO0 low during reset enters the ROM downloader
instead) and the node drops its console to 115200 baud, shows SAFE BOOT
on the OLED, keeps RF off, and idles for reflash/diagnostics.

## Field-hardened firmware (fw v2) — site-audit infrastructure

The desk prototype firmware was refactored for autonomous field
deployment. HAL and processing are now separate ESP-IDF components shared
by every node project:

```
firmware/
  common/
    node_hal/      identity (NVS), crash accounting, safe-boot diagnostic
                   console, task watchdog + RF-liveness watchdog, SSD1306
    telemetry/     binary protocol v2 (node/env IDs, boot-relative time,
                   drop indicator, periodic STATUS health frames)
    calibration/   startup baseline noise-floor cycle + thermal EMA
  csi_rx/          field node — main.c is wiring only
  csi_cfo/         clean-capture node — same components, own sdkconfig
```

**Autonomy features**
- Task watchdog (panic -> hardware reset) guards the serial drain task;
  an RF-liveness monitor hard-resets the node if the WiFi stack delivers
  nothing for 120 s (stack-lock recovery). Abnormal resets increment a
  persisted crash counter reported in every STATUS frame.
- The CSI callback only copies into a queue; one drain task owns stdout.
  Sampling cadence is set by RF arrivals, never host serial latency, and
  all frame timestamps are node-boot-relative (u32 us; host unwraps).
- Safe-boot (BOOT held during app start) is now a 115200-baud
  configuration console: SHOW / NODE n / ENV n / CAL n / CLEARCRASH /
  REBOOT. Node and environment IDs persist in NVS and stamp every frame.

**Audit protocol** — on power-up the node runs a Baseline Calibration
cycle (default 300 s, `CAL n` to change, `CAL 0` for bench bypass):
ambient noise floor is averaged (fast EMA) while CSI reporting is held;
after the window the estimate keeps tracking thermal drift with a slow
EMA. The OLED shows the countdown; STATUS frames carry state, remaining
seconds, and the noise-floor/RSSI estimates.

**Protocol v2** (magic C5 52; v1 C5 51 still parsed by all host tools):
`type u8 | node_id u8 | env_id u16 | boot_ts_us u32 | len u16 | payload |
xor`. CSI payloads add a cumulative queue-drop counter (missing-frame
indicator; seq gaps cover RF loss). STATUS frames every 5 s carry fw
version, reset reason, crash count, cal state, uptime, totals, heap, and
noise/RSSI EMAs.

**Field diagnostics** — plug into any node and get a health report:

```
python pc\field_diag.py COM3
```

prints identity, uptime, last reset reason, crash count, calibration
state, noise floor / SNR, frame rate, sequence gaps, and queue drops.
Exit code: 0 healthy, 1 no telemetry, 2 warnings.

**Serial-connect gotcha (fixed):** pyserial asserts DTR/RTS on open,
which trips the devkit auto-reset circuit — every host connection used
to power-cycle the node and silently restart the calibration window.
All pc tools now open ports through `rff/serialio.py::open_serial`
(DTR/RTS deasserted before open); a diagnostics or capture connection no
longer disturbs the node. Flashing still resets, by design.

## Deployment quick reference

Flash (from an ESP-IDF PowerShell, or bootstrap one):

```powershell
$env:IDF_TOOLS_PATH = "C:\Espressif"
$env:IDF_PYTHON_ENV_PATH = "C:\Espressif\python_env\idf5.5_py3.11_env"
. "C:\Espressif\frameworks\esp-idf-v5.5.4\export.ps1"
cd firmware\csi_rx        # receiver; csi_cfo for the clean-capture node
idf.py -p COMxx flash
```

- All nodes: 460800 baud runtime, protocol v2, decoded by `pc/rff/protocol.py`.
- If a flash fails with "Invalid head of packet" / serial corruption
  (seen on COM3): retry with `idf.py -p COMxx -b 115200 flash`, or move
  the board to a known-good port (COM12).
- After flashing, the node runs its 300 s baseline calibration (OLED
  shows the countdown; STATUS frames carry the state). Verify with
  `python pc\field_diag.py COMxx` — expect fw v2, POWERON, CALIBRATING,
  then DONE + CSI frames after the window.
- Node identity: node_id defaults to the last MAC byte; assign survey
  IDs via the safe-boot console (hold BOOT at app start, 115200:
  `NODE n`, `ENV n`).
