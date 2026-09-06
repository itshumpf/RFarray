> ## Superseded — read this first
>
> **This README is the project as it stood on 23 August 2026.** It was already
> reporting the negative result — the signature does not survive an hour — but it
> did not yet know *why*.
>
> Eight paired overnight captures answered that in September. The separation is
> real and it is **not a property of the transmitter**. Two receivers watching the
> same beacon pair in the same instants disagree by a median of **6.79 between-unit
> SD** at every bin scale, which a property of one crystal cannot do. Co-located
> boards read **0.2σ** apart; the same board moved between rooms read **19.6σ**.
>
> What is being measured is the **link** — transmitter, receiver, and the path
> between them, as one object. Fresh within-session enrollment identifies three
> co-located transmitters at **88–96%**; a template carried to another night falls
> to **38–49%** against 33.3% chance. That is not an authentication system, and no
> spoof-resistance claim is made: the corpus contains no cloned MAC, no substitute
> board, no relay and no replay.
>
> **Current findings, with the controls and the limitations:**
> **https://braedenkeena.pages.dev/csi**
>
> **What is reproducible from this repo.** `share/csi-8-nights/` is the review
> package for the eight-night work: every table in `data/` was computed from the
> files in `per_window_features/` by the code in `scripts/`, not transcribed from
> any write-up. `share/LINK_SIGNATURE_PREREGISTRATION.md` is the frozen decision
> rules, written before that run. The raw captures are **not** published — they are
> promiscuous and contain third-party radios and household activity — so the replay
> from raw serial cannot be independently rerun here. Everything downstream of the
> per-window features can.
>
> Everything below this line is development history, accurate for its date.

---

# ESP32 WiFi CSI Array — RF fingerprinting, and why it doesn't work

An ESP32 bench that captures WiFi Channel State Information, and a month of
pre-registered experiments trying to identify individual radios from it.

**The short version: it identifies devices within a session at 99% and fails
completely across sessions.** The signature does not survive an hour. That
result, its controls, and the measurements behind it are the contribution
here — not a working sensor.

Everything below either traces to a file in `docs/` or to a command you can
run yourself. Figures are quoted with the condition that produced them, or
not quoted.

---

## The results, with their conditions

**Device identification (`pc/rff/`, phase domain)**

| measurement | value | condition |
|---|---:|---|
| Blind holdout accuracy | **99.7%** over 7,497 windows | desk receiver alone, 2026-07-13 |
| Same sessions, second receiver added | **95.7%** over 14,234 windows | cross-receiver generalization gap |
| **Cross-session, fixed receiver** | **29.7%** | against 33.3% chance, N=3 |
| Reference beacon, cross-session recall | **18.1%** | the beacon everything else is calibrated against |

The drop from 99.7 to 95.7 is not a harder device population. In the combined
run the reference beacon's entire test set comes from the second receiver
while its model trained 87.7% on the first. Quote both numbers with that
condition attached, or quote neither. (`docs/TWIN_INVESTIGATION.md` §6–7.)

**Why it fails**

- The SFO slope wanders **0.56 to 4.97× the entire between-device spread over
  four untouched minutes**, on 5 of 6 receiver-beacon cells
  (`docs/LABELLED_EVENTS_0823.md` §20).
- Reference-beacon subtraction cannot repair it. A shared constant removes
  **7–46%** of the drift energy and leaves a per-device residual **2.2× to
  7.1×** the between-device spread — it isn't common-mode, so it can't be
  subtracted (`docs/IDENTITY_STABILITY.md` §13).
- Averaging cannot reach it. Allan deviation falls as **τ^−0.47** out to
  τ ≈ 10 s and then *rises*; 256× more averaging buys 20%
  (`docs/SEPARATION_SCALING.md` §2). Shuffle the same frames in time and they
  recover 1/√W exactly — 15.7, 19.5, 17.4 against √256 = 16. The averaging
  machinery is fine; there is nothing left to average after the first second.
- **The receiver term is larger than the device term.** Two receivers twelve
  inches apart disagree about the same transmitter by **5.7×** the entire
  spread between transmitters, with a dispersion ratio of 826.6 against a
  threshold of 2 (`docs/IQ_IMBALANCE.md` §15). At 2.4 GHz twelve inches is
  2.4 wavelengths, so that measurement cannot yet separate the hardware from
  where it is sitting.

**A second feature, and it isn't enough either**

Transmitter IQ imbalance (`κ`) is extractable from stock ESP32 CSI — a
conjugate image at −34 to −48 dB, with 98.2% of the coherent mirror product
on a single complex axis and sign agreement on 52 of 52 subcarriers
(`docs/IQ_IMBALANCE.md` §12). It is **2.1× to 5.4× more stable** than the
phase slope on identical data.

Put through the same cross-session test (`docs/KAPPA_CROSS_SESSION.md`):
**65.2%** against a pre-registered bar of 2/N = 66.7%, N=3, 12 ordered pairs,
1,293 tests. It beats the slope by **+22 to +28 pp** with every CI excluding
zero — and still fails. Fusing the two adds nothing: against a random axis of
matched variance the gain is **+0.00 pp, CI [−1.80, +1.71]**
(`docs/KAPPA_SLOPE_FUSION.md`).

**Occupancy (`pc/occ/`, amplitude domain) — a separate pipeline, and weaker**

Motion and respiration run on frame *amplitude* and share no discrimination
logic with the device-ID pipeline. **Their numbers are never combined.**

The scripted ground-truth session was finally scored on 2026-08-20
(`docs/OCC_2026-07-22_RESULTS.md`) and it does not support the claims that
preceded it:

- **No motion detection rate can be quoted.** Same label, same file, changing
  only which empty file sets the floor gives 6.78% or 100.00%.
- **The respiration detector flags 81–98% of labeled-empty seconds**, and 9 of
  its 16 PRESENCE verdicts occur in an empty room. Simultaneous observations
  of the same room disagree by 0.5 to 11.0 bpm. These are in-band spectral
  peaks clearing a threshold, not a measured respiration rate.
- The one usable figure is a **1.97%** motion false-alarm rate on held-out
  scripted-vacant time — which is 3.9 seconds of flagged time in 3.3 minutes
  of evidence, and should be quoted with that attached or not at all.

**This array is not a home security system and this repo does not claim it
is.** That framing was in earlier versions of this README and the ground-truth
session removed it.

---

## What is actually solid

- **Within-session identification: 99.0%** on N=3. You can tell three
  transmitters apart right now. You cannot recognise them tomorrow.
- **`κ` is measurable from commodity CSI at all**, and is more stable than the
  clock slope. Whether it is *measurable* is a different question from whether
  it *identifies*, and the first one is answered yes.
- **126 of 166 MAC addresses seen by one receiver were parse artifacts.**
  19 sit at Hamming distance ≤ 3 from a real beacon MAC, one at distance 1.
  Corrupt-row screening caught all of them; without it, relaxing a gate would
  appear to "discover" up to 126 new devices, every one a bit-flip
  (`docs/GATE_CALIBRATION.md` §3.2). Anyone doing ambient WiFi census work is
  probably counting ghosts.
- **The methodology.** Every experiment in `docs/` is Stage-1 pre-registered:
  hypotheses, decision bars and controls written and saved to disk before any
  statistic was computed, with a "temptations recorded rather than acted on"
  section at the end. Several of those nulls were caught by their own controls
  — most recently a **+26 pp, 12-of-12-pairs** fusion result that a
  variance-matched random axis reproduced exactly.

---

## Architecture

```
                    2.4 GHz, fixed channel (default 6)
  ┌──────────┐   ESP-NOW broadcast @ 100 Hz   ┌──────────┐
  │ TX beacon │ ─────────────────────────────► │ RX node  │──USB──► PC
  │ (ESP32)   │                                │ (ESP32)  │   capture.py → CSV
  └──────────┘                                └──────────┘
```

A dedicated beacon rather than router traffic: constant known packet rate,
fixed channel, fixed MAC, identical reference signal at every receiver.

**"100 Hz" is the transmit cadence, not the sample rate.** The reference
beacon arrives at the collector at **37.0 fps** (d0wd) and **40.8 fps** (s3).
Anything quoting 100 Hz as an observation rate — including the Nyquist
reasoning in older docs — is wrong (`docs/CODE_INVENTORY.md` §4.1 D5).

**Node-side queue drops are the loss mechanism, not the link.** Measured over
a 26-minute capture: Heltec S3 native USB **17.00%**, D0WD UART bridge
**3.82%**, both from `QUEUE_DEPTH 64` overflow while running at a fraction of
link capacity. Why the drain task falls behind is **unknown**.

**The UART runs at 86% of capacity, not a third.** 218,016 frames / 1,559 s ×
284 B = 39.7 KB/s against the 46,080 B/s that 460800 8N1 carries. Earlier
versions of this file said "about a third" and "going higher buys nothing" —
that was off by roughly 2.6×.

---

## Repo layout

```
firmware/                 2,631 lines of C/ESP-IDF across 13 files
  common/node_hal/          identity (NVS), crash counter, safe-boot console,
                            task + RF-liveness watchdogs, SSD1306 OLED
  common/telemetry/         binary protocol v1/v2 (CSI + STATUS frames)
  common/calibration/       startup noise-floor baseline (dual-rate EMA)
  csi_tx/                   beacon — 100 Hz ESP-NOW broadcast
  csi_rx/    (677 lines)    promiscuous field node, RFF_PROMISCUOUS 1
  csi_cfo/   (340 lines)    clean-capture node — see hazard below

pc/                       33,508 lines of Python across 61 files
  rff/                      device ID: phase unwrap → RANSAC (dsp.py) →
                            Kalman drift (kalman.py) → reference subtraction
                            (reference.py) → Mahalanobis/χ² (discriminator.py)
  occ/                      occupancy: motion z-score, respiration Welch-PSD,
                            cross-link zones. Amplitude domain, separate.
  rff_offline.py            offline science run: per-source stats, pairwise σ,
                            chronological train/holdout
  exp_*.py                  one read-only script per docs/ experiment
  capture.py / collect.py   serial → CSV

data/raw/                 118 session files, 99.5 GiB — counted from disk
                          2026-09-06. The sixteen canonical eight-night files
                          hold exactly 69,688,145 rows in 54.92 GiB; at the same
                          bytes-per-row the full corpus is in the region of 126
                          million rows, which is an extrapolation and not a count.
                          GITIGNORED — see Data availability
docs/                     59 pre-registered experiment writeups
```

Line counts re-measured 2026-08-27 and include this repo's own experiment
scripts. Method: `find firmware -type d -name 'build*' -prune -o -type f
\( -name '*.c' -o -name '*.h' \) -print | xargs wc -l`, and the equivalent
over `pc/`. `PROJECT_NOTES.md` §2 records a "~15K lines of firmware" claim as
contradicted, but no such sentence has been found in this README, in `site/`,
or in the portfolio repo — the figure appears to have originated in
conversation rather than in any published file, and is noted here only so the
next reader of `PROJECT_NOTES.md` does not go looking for it.

---

## Restart hazards

- **`firmware/csi_cfo/main/main.c` is uncommitted and unverified.** It is now
  a genuinely distinct clean-capture firmware — `RFF_PROMISCUOUS 0` and
  `TX_FILTER_MAC` hard-coded to `a4:f0:0f:77:91:20` — but no artifact in this
  repo records it being flashed or its output checked. **It fails silently if
  the reference beacon's MAC changes:** the filter is compiled in and the node
  simply captures nothing.
- **`firmware/csi_tx/main/main.c` in the working tree is a BLE diagnostic**
  ("CSI-S3-ALIVE"), not the production beacon. Production beacon = git HEAD.
- **`pc/requirements.txt` omits pandas**, which `pc/heatmap.py` imports.
- **`pc/live_view.py` does not work.** It is a v1-protocol decoder running
  against v2 firmware; it decodes zero frames and renders a blank waterfall.
- **`OUTPUT_BINARY` does not exist.** Earlier versions of this file described
  it as a firmware switch for human-readable CSV. It appears in no `main.c`.
- **Receivers do not filter on the TX MAC.** `csi_rx` ships
  `RFF_PROMISCUOUS 1` with an all-zero `TX_FILTER_MAC`. Only `csi_cfo`
  filters.
- **Five different usable-subcarrier counts exist in this tree** — 52 in
  `dsp.py`/`ingest.py`, 64 in `fingerprint.py`/`live_view.py`/`phase_skew.py`,
  32 in `capture.py`. **Only 52 is correct.** `capture.py:compute_cfo`,
  `phase_skew.py` and `fingerprint.py` all have the DC/guard-band index wrong;
  nothing derived from them is quotable.
- **Keep this repo out of OneDrive or any synced folder.** ESP-IDF's `build/`
  churns thousands of files and cloud sync racing it corrupts caches and makes
  edits appear not to stick.

---

## Setup (Windows)

1. Install ESP-IDF v5.x via the Windows installer. Open the "ESP-IDF
   PowerShell" it creates.
2. Flash the beacon and a receiver:
   ```
   cd firmware/csi_tx   && idf.py set-target esp32 && idf.py -p COM5 flash
   cd firmware/csi_rx   && idf.py set-target esp32 && idf.py -p COM12 flash
   ```
3. PC side:
   ```
   pip install -r pc/requirements.txt        # note: pandas is missing from it
   python pc\capture.py COM12:desk COM7:node3     # PORT:name per node
   python pc\capture.py --demo                    # no hardware, synthetic
   ```

### The baud trap that cost us hours

Serial runs at **460800**. `CONFIG_ESP_CONSOLE_UART_BAUDRATE` has its Kconfig
prompt gated behind `if ESP_CONSOLE_UART_CUSTOM`. With the default
`Channel for console output = Default: UART0` the symbol has *no prompt*: it
is not user-settable and silently forces 115200, ignoring anything in
`sdkconfig` or `sdkconfig.defaults`. You **must** select `Custom UART` — which
on ESP32 defaults to the same UART0/GPIO1/GPIO3, so it is the identical USB
path with the baud field unlocked:

```
CONFIG_ESP_CONSOLE_UART_CUSTOM=y
CONFIG_ESP_CONSOLE_UART_CUSTOM_NUM_0=y
CONFIG_ESP_CONSOLE_UART_TX_GPIO=1
CONFIG_ESP_CONSOLE_UART_RX_GPIO=3
CONFIG_ESP_CONSOLE_UART_BAUDRATE=460800
```

After changing it run `idf.py set-target esp32` (moves the old `sdkconfig`
aside and rebuilds from defaults), reflash, and confirm with
`grep ESP_CONSOLE_UART_BAUDRATE sdkconfig`. A stale `build/` re-asserts the old
value. There is no runtime baud switch on ESP32.

### Wire format

`C5 52 | type u8 | node_id u8 | env_id u16 | boot_ts_us u32 | len u16 |
payload | xor`, little-endian. v1 (`C5 51`) is still parsed by all host tools.
Decoders resync on the magic bytes and validate the checksum, so interleaved
boot logs and split reads are handled. Amplitude of subcarrier k =
`sqrt(i² + q²)` over int8 I/Q pairs.

---

## Reproducing the experiments

Each writeup in `docs/` names the command that regenerates its figures. The
newest ones:

```
python pc\exp_identity_stability.py    extract <csv> ; score ; report
python pc\exp_kappa_cross_session.py   verify ; scan <csv> --tag T ; floors ; score ; report
python pc\exp_kappa_cross_session.py   fuse
python pc\exp_gate_calibration.py
python pc\exp_occ_ground_truth.py
```

Start with `docs/CODE_INVENTORY.md` (what is where, and 44 findings where the
code and docs disagree) and `docs/IDENTITY_STABILITY.md` (the result that
closed the project's original premise).

## Data availability

**`data/raw/` is not published, and that is a privacy decision before it is a
reproducibility one.** Running promiscuously, this array captured every WiFi
transmitter in range — a neighbour's router and other nearby hardware, none of
whom agreed to be recorded. The captures are also, unavoidably, a log of a
home: when rooms were occupied, when people were asleep, and what a still
person's breathing looks like in CSI.

**The practical consequence: you can read this pipeline but you cannot rerun
it against the data behind any number above.** Every figure names the file and
the command that produced it, and the `exp_*.py` scripts are read-only and
complete, but independent verification from a clone alone is not possible.
That is stated rather than worked around.
