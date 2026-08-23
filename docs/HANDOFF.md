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

> **Correction — 15 August 2026.** The inventory above is dated
> 2026-07-15 and is accurate for that date, but it is routinely read as a
> description of the bench throughout the captured dataset, and for most
> of that dataset it is wrong. The original table is left in place
> unchanged. Full evidence and method: `docs/NODE_CENSUS.md`.
>
> **What was claimed:** implicitly, that this table describes the array
> that produced `data/raw/` — one collector on COM3, three TX beacons
> on-air, one Heltec benched.
>
> **What is actually true:** the array's composition changed twice during
> July, and this table describes only its final state.
>
> 1. **Two receivers were logging simultaneously on 07-12 and 07-13, and
>    the inventory has no row for the second one.** Fifteen `desk_*` /
>    `node3_*` file pairs overlap in wall-clock time, the longest by
>    **148.45 minutes** (`desk_20260713_172009` / `node3_20260713_172009`,
>    07-13 22:20:10 → 07-14 00:48:37 UTC). Over the same minutes the two
>    files record the same beacon at up to **9.7 dB** different RSSI and a
>    **5.5×** different frame count, so this is two antennas in two
>    places, not one radio writing two files. The second node produced 16
>    files and 1,717,532 frames.
> 2. **Only `a4:f0:0f:77:91:20` was transmitting for the first two days.**
>    `f4:2d:c9:70:72:30` and `28:05:a5:2f:fa:48` occur **zero times** in
>    every 07-12 and 07-13 capture on either receiver. They first transmit
>    on **2026-07-14 at 06:16:19.189 and 06:16:19.367 UTC** — 0.177 s
>    apart, at rows 1 and 32 of `rx_20260714_011619.csv`. A deployment
>    event, not a gradual one.
> 3. **From 07-14 onward there has been exactly one receiver.** Among all
>    twelve `rx_*` and `occ_*` files there is **not one microsecond of
>    overlap**; they run strictly sequentially with gaps of 7.4 s to
>    573,118 s. The rename from `desk_*`/`node3_*` to `rx_*` happened on
>    the same day and marks the *loss* of the second receiver, not the
>    arrival of anything.
> 4. **`28:05:a5:2f:fa:48` was off air during the five afternoon `occ_*`
>    captures of 07-22** (20:22–20:59 UTC; `grep -c` = 0 in all five) and
>    back on air that evening. `pc/occ/BEACON_MACS` calls it **B2**, so
>    any occupancy result computed from those five files is a **two-link**
>    result, not three. This is not noted in `docs/OCC_PROTOCOL.md`.
> 5. **The reference beacon was itself off air for ~11 minutes** on 07-13
>    (17:12:47–17:23:39 UTC): `desk_20260713_121242.csv` holds 939 frames
>    and none of them are `a4:f0:0f:77:91:20`.
>
> **What this does NOT establish — and it is the important part.** The
> census proves how many receivers there were. It proves nothing about
> *which boards they were.*
>
> - **The 10-column CSVs carry no receiver identity whatsoever.** The
>   strings `desk` and `node3` are filename prefixes typed at
>   `pc/capture.py`'s command line, nothing more.
> - **That the benched Heltec S3 `8c:fd:49:b7:b0:6c` was the second
>   collector is an inference**, from this file's "RX works; WiFi TX
>   inaudible" plus role and timing. **No CSV names it.** Its zero
>   transmit frames are consistent with it collecting and equally
>   consistent with it sitting idle.
> - **The 13-column captures carry `node_id`, and it is `68` on every one
>   of 10,342,823 rows** — but `node_id` is compiled into the firmware, so
>   it identifies a *build*, not a board. That the era-B/C collector is
>   the same physical board as era-A `desk` is also an inference.
> - **`pc/heatmap.py`'s `NODE_POS` coordinates and its "Desk PC Receiver"
>   / "Hallway/Door Receiver" strings are not evidence of physical
>   placement.** They are defaults in an interactive plotting script that
>   binds keys `1` and `3` to click-and-drag the markers elsewhere. The
>   RSSI divergence in point 1 proves the two antennas were in *different*
>   places; nothing in the data says *where*, and the hallway placement is
>   unverified.
>
> **Also unrecorded: the second receiver changed behaviour mid-07-13.**
> In its first seven sessions `node3` logged exactly one source MAC — the
> reference beacon — while `desk` logged up to 18 in the same minutes.
> From `node3_20260713_131746.csv` onward it logs 6–23 in every session
> long enough to carry ambient traffic. The change falls
> between 07-13 17:08 and 18:17 UTC. That is what a MAC-filtered build
> reflashed to a promiscuous one looks like, but **both committed
> firmwares are promiscuous with an all-zero `TX_FILTER_MAC`**, and the
> only filtered `csi_cfo` variant in the tree is an uncommitted 2026-08-02
> change. Whatever ran on 07-12 is preserved in no commit.
>
> **What does NOT change.** Every measured result in the next section
> stands; nothing here challenges a σ, an accuracy, or a rate. Open thread
> #5's *plan* (a Pi host, spatial features) is still the right plan — but
> its parenthetical, "2nd RX exists in firmware as `csi_cfo`," understates
> the position. A second RX did not merely exist in firmware; it ran for
> two days and then stopped, and no artifact records why.

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
   frames, check IDF 5.5.4 S3 errata. (**The BLE advertiser referred to
   here is not throwaway diagnostic code — see "Correction — 15 August
   2026" under *Hard-won gotchas*, and `docs/DIRECTION.md`.** The
   diagnostic *use* described in this bullet is still valid.)
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
  (**The word "diagnostic" is corrected below — see "Correction — 15
  August 2026". The build advice in this bullet still stands.**)
- Windows console is cp1252 — keep tool output ASCII.

> **Correction — 15 August 2026.** The characterization of the BLE work
> as diagnostic scaffolding is wrong. The original wording is left in
> place above, and in open thread #3, only as a record of what was
> believed on 22 July.
>
> **What was claimed:** that the BLE code in
> `firmware/csi_tx/main/main.c` and the `CONFIG_BT_ENABLED` /
> `CONFIG_BT_NIMBLE_ENABLED` lines in `firmware/csi_tx/sdkconfig.defaults.s3`
> exist solely to answer the S3 WiFi-TX question ("does the 2.4 GHz PA
> radiate at all?"), and are therefore debris to be stripped once that
> question is settled.
>
> **What is actually true:** per Braeden, 15 August 2026 — he always
> wanted BLE on this platform and knew it would be needed. A
> miscommunication on the day led him to table it, and it got written up
> as scaffolding. It is deliberate groundwork toward **BLE as a third
> identification channel** alongside WiFi CFO fingerprinting and CSI
> occupancy. See `docs/DIRECTION.md`. The S3 radiation test was a real
> and useful side-benefit of code that was going to be written anyway —
> not the reason it exists.
>
> **What does NOT change — the build advice above is still correct.**
> Whatever the intent, a production beacon build should not ship with
> the BT stack enabled: it costs flash and RAM and it is not the beacon.
> Strip the two `sdkconfig` lines for production beacon builds exactly
> as the bullet says. Correcting the intent does not promote the current
> working-tree file to production code.
>
> **Two details this file got wrong on the facts, found 15 August 2026
> by reading the working tree:**
>
> 1. **Three files are modified, not two.**
>    `firmware/csi_tx/main/CMakeLists.txt` also carries an uncommitted
>    change (`PRIV_REQUIRES bt nvs_flash`). A build that strips only the
>    two `sdkconfig` lines and leaves this will still pull in `bt`.
> 2. **The working-tree `main.c` is not "BLE additions" to the beacon —
>    it replaces it.** The file is a standalone NimBLE advertiser
>    (`CSI-S3-ALIVE`); the ESP-NOW beacon TX is gone from it entirely
>    (`git diff`: 70 insertions, 79 deletions). Flashing it to a beacon
>    node takes that node off the air. This is consistent with the
>    "production beacon = git HEAD" advice, but the word *additions*
>    understates it.
>
> **This work is uncommitted and has been sitting in the working tree
> since 2026-07-22.** The three files above show mtime
> `2026-07-22 18:50`; the last commit touching `firmware/csi_tx/` is
> `2d2b0c2`, dated 2026-07-14. Nothing in git preserves any of it. A
> careless `git checkout -- firmware/`, `git stash`, `git reset --hard`,
> or a clean-clone-and-copy loses the only copy of the BLE groundwork.
> **Braeden stages and commits himself — do not commit it for him — but
> do not destroy it either, and say so before running anything that
> discards working-tree state.**

## Working style that fit this project

Verify end-to-end after every change (flash → live census at the
collector, not just build success). Prefer measured σ over theory.
Report failures plainly — the honest 55% was more useful than the
flattering 99.5%. When hardware misbehaves, distrust the test setup
before the silicon (the battery, the stale CSV, and the cached BLE
name each burned an hour).
