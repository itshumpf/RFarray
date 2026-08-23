# Mission Prompt — WiFi-CSI Sensing Array, Phase 3: Occupancy Science

Paste this whole file as the first message of a new chat.

---

You are joining an established WiFi-CSI (Channel State Information)
sensing research project at `C:\dev\csi-array` (git, branch `main`,
Windows, ESP-IDF v5.5.4). Read `README.md` and `docs/HANDOFF.md` in that
repo first — they carry the architecture, protocol, hardware inventory
(every node MAC), and a list of hard-won operational gotchas that cost
real hours to learn. Treat both as authoritative.

This is a **science-first project**. The standard is measured evidence,
not plausible-sounding claims. Prior sessions repeatedly found that the
honest number beat the flattering one, and that hardware misbehavior was
usually the test setup's fault, not the silicon's.

## What the instrument is

One ESP32 collector (`csi_rx` firmware, COM3, 460800 baud) sits
promiscuous on **WiFi channel 6** and captures per-frame CSI — the
complex channel response H(f) across 52 usable LLTF subcarriers — for
every decodable frame on the channel. Three ESP32 beacons (`csi_tx`)
broadcast identical ESP-NOW packets at 100 Hz as a controlled RF
stimulus. The PC does all signal processing (`pc/rff/`). Frames land as
CSV via `pc/capture.py`; `data/raw/` already holds a ~2.8M-frame
multi-hour session.

## Phase 1-2 victories (established results — do not re-derive; only
## challenge them with new measurements)

The completed work is **transmitter fingerprinting via clock physics**:

- Every radio's crystal is imperfect. Across subcarriers k, frame phase
  is `phase(k) = slope*k + intercept + channel(k) + noise`, where the
  slope carries **SFO** (sampling frequency offset) and the intercept's
  frame-to-frame rate of change carries **CFO** (carrier frequency
  offset). Both are hardware properties — they survive MAC
  randomization, which is what makes them a security primitive.
- `rff/dsp.py` does the physically-correct thing: FFT-order → physical
  subcarrier mapping (guards/DC excluded), phase unwrap with temporal
  continuity correction, then **RANSAC** line fitting so multipath
  curvature becomes outliers instead of slope bias. Windowed medians →
  robust per-observation estimates.
- `rff/kalman.py`: per-source 1D random-walk Kalman filters track
  thermal clock drift. `rff/discriminator.py`: per-source 2D Gaussians
  (Welford) + **Mahalanobis distance** with real chi-square thresholds
  (95%/99% ellipses). `rff/reference.py`: subtracting a reference
  beacon's drift cancels receiver-side common-mode drift.
  `rff/store.py`: SQLite history + persisted centroids.

**Measured results:**
- **CFO is aliased** at the 100 Hz beacon rate (Nyquist ±50 Hz) → all
  CFO medians sit near 0. **SFO slope is the discriminating feature.**
- Reference-beacon correction cancels RX drift across
  sessions/receivers — two independent receivers agreed on one source's
  SFO to **0.0004 rad/subcarrier**. It does NOT help within-session
  same-model separation (verified: raw vs corrected both 0.3σ).
- **Same-model ESP32 discrimination tops out ≈77%** (distinct units
  1.8–2.7σ apart under pooled covariance). Two boards are true clock
  twins: 0.0004 rad/sc apart, **0.3σ**, coin-flip — and this is
  physical, not a bug (their mean gap is 3-6× smaller than their
  per-window spread).
- A **cross-manufacturer ambient device separated at 11–15σ, 7/7 blind
  holdout.** That regime — foreign hardware vs. known fleet — is where
  the method genuinely works.
- Clock signatures **wander thermally**: pairs drifted 2.7σ → 1.3σ over
  one multi-hour session. Drift-vs-temperature is currently unmodeled.

## Phase 3 mission: build the occupancy-sensing science

The fingerprinting track answers *"who is transmitting."* Phase 3
answers a different question from the **same captured frames**: *"what
is happening in the physical space."* When a person moves through a
room, they perturb the multipath field; CSI amplitude ripples in
characteristic ways. None of this is built yet — the only motion code is
a toy metric on the collector's OLED.

Deliverables, in order:

1. **Motion detection.** Per-link sliding-window statistics on
   per-subcarrier amplitude |H(f,t)| — variance / MAD against the
   calibrated empty-room baseline (firmware already runs a 300 s
   baseline cycle on boot). Report an honest detection rate, not a demo.
2. **Presence of a *still* person.** The hard, valuable one. A
   motionless human still modulates the channel by **breathing**:
   0.2–0.33 Hz (12–20 breaths/min) periodic micro-motion. At 30–60
   frames/s per link you have ~100× the Nyquist headroom needed — an FFT
   of a subcarrier's amplitude time series should show a respiratory
   peak. This is what separates real occupancy sensing from a PIR
   sensor.
3. **Coarse zone localization.** You have **three independent TX→RX
   links** (three geometric paths through the space). A perturbation's
   *relative* signature across the three links carries spatial
   information. Differential response across links → coarse zones. This
   is the payoff of the existing fleet.
4. **Occupancy report.** Time-series presence/motion per zone — the
   deliverable an office-utilization audit would actually contain.

**Relevant physics/method notes:** ESP32 phase is uncalibrated per
packet, so occupancy work should lean on **amplitude** (and possibly
phase *differences* between subcarriers), while fingerprinting owns the
phase-slope domain — the two tracks are complementary and can share the
same raw captures. Consider: PCA/eigen-decomposition of the CSI
covariance matrix (the dominant eigenvector tracks the static path;
subordinate ones carry motion), Doppler spectra via FFT of subcarrier
time series, and per-subcarrier sensitivity weighting (subcarriers are
not equally informative).

## Hard constraints

1. **Do not regress the CFO/SFO pipeline.** `rff/dsp.py`,
   `rff/kalman.py`, `rff/discriminator.py`, `rff/reference.py`,
   `rff/store.py`, `rff/protocol.py`, `rff_offline.py`, `rff_live.py`
   are validated and produce the measured results above. Occupancy work
   is **additive** — new modules, new tools. If you must touch shared
   code, re-run `python pc\rff_offline.py "data\raw\rx_*.csv" --ref-mac
   a4:f0:0f:77:91:20` and confirm the separation matrix and holdout
   accuracy still match the numbers above.
2. **Do not change the beacon rate or frame format casually.** 100 Hz
   sets the CFO Nyquist limit (±50 Hz) AND the occupancy Doppler
   bandwidth. The MCS0/HT20 lock keeps CSI format consistent. Changing
   these invalidates prior data and prior results.
3. **Use the existing fleet — adding nodes is allowed but should not be
   necessary, and is not free.** All beacons share channel-6 airtime:
   with three beacons, per-beacon capture rates are ~58/46/34 fps (~140
   fps aggregate). A fourth beacon adds a spatial link but *dilutes
   per-link sample rate*, degrading both Doppler resolution and CFO
   headroom. Three links is near the sweet spot. Justify with
   measurements before adding hardware.
4. **Verify end-to-end, not just "it builds."** After any firmware
   change: flash, then take a live census at the collector. After any
   analysis change: run it on real captured data and report real
   numbers.
5. **Report failures plainly.** If a detector achieves 60%, say 60%.
   The prior session's honest 55% was more scientifically useful than a
   flattering 99.5% would have been.

## Known open threads (from `docs/HANDOFF.md`, ranked)

1. **Embed TX die temperature in beacon payloads** — no weather
   hardware exists, but every ESP32 has an internal temperature sensor.
   Stamping temp into the 8-byte beacon (`magic|seq`) turns the observed
   thermal drift from noise into a modeled variable. Costs $0. (Classic
   ESP32 needs ROM `temprature_sens_read()`; S3/C3 have a driver.)
   NOTE: changing the beacon payload touches constraint 2 — the CSI
   frame *format* must stay identical; only payload bytes change.
2. **v3 fingerprint features** — the RANSAC fit discards the
   per-subcarrier phase *residual shape*, I/Q imbalance, amplitude
   ripple. Literature says these crack near-identical radios. The
   existing 2.8M-frame dataset can validate this with no new captures.
3. **Benched Heltec ESP32-S3** (`8c:fd:49:b7:b0:6c`): MAC layer reports
   100% TX success (ch 6, 20 dBm, fresh RF cal, two antennas, 1M+MCS0)
   but a collector 1 m away hears zero frames; its RX path works fine.
   Not required for Phase 3.
4. **Per-MAC sequence tracking**: `csi_rx` tags every CSI record with
   the latest ESP-NOW seq from *any* beacon (one global var) — with 3
   beacons the `seq` column is cross-contaminated. Fix before relying on
   seq gaps.

## Working style that fits this project

Explain the physics before the code. Prefer a measured σ over a
confident adjective. Distrust the test setup before the silicon. Keep
tool output ASCII (Windows console is cp1252). Never open a node's COM
port with plain pyserial — DTR/RTS resets the board and restarts its
calibration; always use `rff/serialio.py::open_serial`. Check a capture
CSV's mtime before trusting it (a dead capture process once caused 14
hours of false conclusions).
