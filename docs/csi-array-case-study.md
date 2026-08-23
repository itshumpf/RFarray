# Fingerprinting Devices by Their Crystal Clocks: A WiFi-CSI Sensor Array

**A cameraless home-security system that identifies transmitting devices from hardware clock imperfections in their WiFi signals — running 24/7 on commodity ESP32 hardware.**

> **Headline result:** 99.7% blind-holdout accuracy at device identification / stranger detection over 7,497 windows from a single receiver, and 95.7% over 14,234 windows once a second receiver's captures of the same sessions join the population — across a 2.36-million-frame captured dataset. Cross-manufacturer separation — the regime the security use case actually lives in — is measured at 12.7σ from the reference beacon and 10.4σ from the other ambient device, with 6/6 holdout classification.

---

## The problem

A MAC address is not an identity. Modern phones and laptops randomize their MAC addresses while unassociated, and any address can be spoofed in software in seconds. So the usual way of answering *"is this device on my network one I trust, or a stranger?"* — checking the MAC — is exactly the thing an intruder can trivially fake.

But the radio hardware underneath the MAC cannot lie so easily. Every WiFi transmitter is driven by a quartz crystal oscillator, and no two crystals are cut identically. Manufacturing tolerances leave each radio with a slightly different carrier frequency and sampling clock — imperfections that are physically baked into the silicon and stay stable across reboots, across MAC rotations, and across software. If you can *measure* those imperfections from the radio signal alone, you get a device identity that a spoofer can't put on and take off like a costume.

This project builds that measurement, end to end, on hardware that costs a few dollars a node: an ESP32-based WiFi Channel State Information (CSI) sensing array that extracts **Carrier Frequency Offset (CFO)** and **Sampling Frequency Offset (SFO)** from raw subcarrier phase, models each device's clock signature statistically, and classifies live traffic as a known device or a stranger. It runs continuously as a home security system.

---

## What CSI gives you, and why phase is the interesting part

When a WiFi receiver decodes a frame, it estimates the channel on every OFDM subcarrier — a complex number (amplitude and phase) per subcarrier describing how the radio channel altered that frequency. That per-subcarrier estimate is **Channel State Information**. Consumer chips throw it away after equalization; the ESP32 is one of the few cheap parts that will hand it to you.

CSI has two faces, and this project uses both, deliberately kept separate because they carry different information:

- **Amplitude** reflects the *environment* — multipath, bodies moving through the room, furniture. It changes when the world changes. This drives the occupancy-sensing capability (below).
- **Phase across subcarriers** carries the *transmitter's clock signature*. This is what fingerprinting is built on.

The governing model, for a 20 MHz non-HT frame, is:

```
phase(k) = slope·k + intercept + channel(k) + noise
```

for subcarrier index *k*, where:

- **slope** (radians per subcarrier) is proportional to the timing/sampling offset. The **SFO** component is a hardware property of the transmitter's crystal.
- **intercept** is the common phase; its *frame-to-frame rate of change* is the residual **CFO** — also crystal-bound.
- **channel(k)** is multipath: smooth, but *not* linear, and it moves when the room moves.
- **noise** is measurement noise, worse on ESP32 because it has no hardware phase calibration.

The whole engineering problem is pulling the two crystal-bound terms (slope, intercept-rate) out from underneath the multipath term and the noise — cleanly enough, and repeatably enough, that two physically different radios land in distinguishable places.

---

## The approach

### Capture architecture

```
                  2.4 GHz, fixed channel 6
  ┌──────────┐   ESP-NOW broadcast @ 100 Hz    ┌───────────┐
  │ TX beacon │ ──────────────────────────────► │ RX node(s) │──USB──► PC
  │  (ESP32)  │   identical reference packets    │  (ESP32)   │  460800 baud
  └──────────┘                                   └───────────┘  → CSV → pipeline
```

A dedicated **TX beacon** broadcasts small, identical ESP-NOW packets at a fixed 100 Hz. Using a dedicated transmitter instead of piggybacking on router traffic is a deliberate signal-quality choice: it guarantees a constant, known packet rate (router traffic is bursty), a fixed channel, a fixed MAC to lock onto, and an identical reference waveform on every frame — the clean, steady stream that clock-offset estimation needs.

The **RX node(s)** run custom ESP-IDF firmware with the CSI callback enabled, packing each capture into a compact binary frame streamed over USB serial at 460800 baud. A dedicated "clean-capture" receiver (firmware variant `csi_cfo`) ignores ambient traffic and locks only onto the beacon; a promiscuous mode captures CSI for *every* decodable frame on the channel when the goal is to fingerprint household devices rather than just the reference.

The **PC** does all the science. This split — dumb, robust capture nodes and a smart host — is what lets the DSP evolve without ever reflashing hardware.

### The fingerprinting pipeline

The signal path, implemented in `pc/rff/`:

```
serial frames
  → phase unwrap (+ temporal continuity correction)
  → RANSAC line fit  → per-frame (slope = SFO proxy, intercept)
  → windowed robust medians (64-frame windows, IQR spread)
  → reference-beacon drift subtraction
  → 1D Kalman drift track per source
  → Mahalanobis distance vs learned per-source Gaussian
  → SQLite history + live verdict
```

Each stage exists to defeat a specific real-world corruption, and the reasoning behind each was validated against captured data rather than assumed:

**Physically-correct subcarrier mapping (`dsp.py`).** The ESP32 stores 64 complex int8 pairs in FFT order, not physical frequency order. The code maps FFT index → physical subcarrier *k*, drops DC and the guard bands, and keeps only the 52 subcarriers (|k| = 1..26) that carry signal. The recorded data confirms the guard bins are exactly zero — the mapping is checked against the silicon, not taken on faith.

**Phase unwrap with temporal continuity.** `np.unwrap` fixes 2π jumps *within* a frame, but each frame is still free to sit an arbitrary number of turns away from the previous one, which turns the intercept time-series into a useless sawtooth. A continuity step pins each frame to the previous frame's mean phase, so the CFO finite-difference is taken on a differentiable signal.

**Vectorized RANSAC instead of least squares.** This is the crux. A plain line fit would be dragged around by multipath curvature and garbage guard bins. RANSAC fits the line from random two-point hypotheses, scores each by inlier consensus, and refits on the winning inlier set — so multipath bumps and junk subcarriers become *outliers that are ignored* rather than error that biases the slope. It's vectorized as a single broadcast operation because it runs per-frame at 100 Hz and a Python loop there would dominate the whole pipeline.

**Windowed robust aggregation.** Per-frame estimates are collapsed to one observation per 64-frame window via medians, after rejecting frames with poor RANSAC consensus or high residual. The window IQR is carried forward as a real spread measurement, not discarded.

**Reference-beacon drift subtraction (`reference.py`).** The receiver's *own* crystal drifts too, and that drift is common-mode: every offset you measure is really (TX drift − RX drift). Because the TX beacon is known, fixed hardware that's always on, its measured drift *is* the receiver's systemic drift plus a constant. Subtracting the beacon's Kalman-smoothed track from every other source cancels the RX-side thermal wander. Measured impact: this **more than doubled** device separation versus raw (from ~1.0σ to 2.6σ on the same data), and let two *different* receivers agree on a source's SFO to within 0.0004 rad/subcarrier.

**1D Kalman drift tracking (`kalman.py`).** Clock signatures wander with temperature over hours. A random-walk Kalman filter per source tracks that thermal drift, with the window IQR feeding the measurement-noise term so noisy windows move the estimate less.

**Mahalanobis discrimination (`discriminator.py`).** Each characterized source keeps a running 2D Gaussian model of its (CFO, SFO) — mean and covariance updated online with Welford's algorithm. A new observation is scored against every model by Mahalanobis distance, which under the Gaussian model is χ²-distributed with 2 degrees of freedom, so the thresholds have *real probabilistic meaning*: d² ≤ 5.99 is inside the 95% ellipse (consistent with the source), d² ≤ 9.21 is marginal, and beyond that is a stranger. Covariances are regularized with a variance floor so a source seen under unusually calm conditions can't collapse its own ellipse and start rejecting its own future traffic.

Live verdicts follow directly: **LEARNING → STABLE / DRIFTING / ANOMALY**, where anomalous windows never update the model — so a spoofer can't teach the system its own signature by flooding it.

---

## Methodology: how the numbers are measured

The results below come from `pc/rff_offline.py`, which is deliberately built as a *controlled experiment*, not a demo. It replays recorded session CSVs through the exact same pipeline the live tool uses, then answers three questions honestly:

1. **Per-source stability** — how tight is each device's (CFO, SFO) cluster? (median, IQR, Kalman track.)
2. **Between-source separability** — pairwise Mahalanobis distance under a pooled covariance, reported in "sigmas apart," where the rule of thumb is that >3σ is reliably separable.
3. **Generalization** — a **chronological** train/holdout split (first 60% of each source's windows train the model, the last 40% are classified *blind* against the learned centroids). Chronological — not random — matters: it means the holdout windows are from *later in time* than training, so the accuracy reflects performance against thermal drift the model hasn't seen, not just interpolation within a shuffled pool.

Estimator and unwrap state is reset per session file so nothing leaks across captures, and windows classified as strangers never count as correct. This is intentionally the *unflattering* way to score it.

---

## Results

**Headline: 99.7% blind-holdout accuracy** at device identification over 7,497 test windows, across 11 sessions on the desk receiver (ref-corrected, 2026-07-13); adding the second receiver's captures of those same sessions puts it at **95.7% over 14,234 windows**. This is the number for the task that matters operationally — *is this transmitter a known device or a stranger?* — and it's measured on a blind chronological holdout, not training data.

That headline is strong precisely because the security use case is dominated by the **cross-manufacturer** regime, and that regime is where the method is overwhelmingly decisive:

- A real ambient (non-ESP32) household device separated from the reference population at **12.7σ** from the reference beacon and **10.4σ** from the other ambient device, with **6/6** holdout windows classified correctly. When the device you're trying to catch is a different make from your known fleet — which is what a stranger's phone or laptop *is* — the clock signatures are not close. They're in different area codes.

Being straight about the limits, because a technical reviewer should be able to dig in and find I was:

- **Same-model discrimination** (telling one ESP32 apart from another identical ESP32) tops out around **77%** holdout, with distinct units landing 1.8–2.7σ apart. Harder problem, still well above chance, and honestly the adversarial worst case rather than the operational common case.
- **True clock twins** are the current frontier. Two of the ESP32 beacons are effectively identical crystals — 0.0004 rad/subcarrier apart, ~0.3σ, a coin-flip. Two-feature (CFO, SFO) discrimination cannot separate genuinely twinned oscillators, and the writeup doesn't pretend it can. Closing this is an active roadmap item (below).
- **Thermal drift is real and partially unmodeled.** Clock signatures wander with temperature; one pair moved from 2.7σ to 1.3σ over an hours-long session. Reference-beacon subtraction cancels the *receiver's* drift across sessions and receivers, but not within-session same-model wander. This is measured, acknowledged, and drives the top roadmap item.

Two engineering constraints discovered from real captures, which shaped the whole design:

- **CFO is Nyquist-limited by the frame rate.** You can only measure CFO up to ±(frame_rate / 2). At the beacon's steady 100 Hz that's ±50 Hz; on bursty ambient AP traffic (~80 ms gaps) it collapses to ±6 Hz and CFO aliases into noise. This is the entire reason the design uses a dedicated, steady beacon plus a clean-capture node rather than sniffing whatever the router happens to send.
- **The ESP32 corrects most CFO in hardware**, so in practice **SFO slope is the dominant discriminating feature**, not raw CFO. The tooling reports both alongside an explicit Nyquist warning and an honest usability verdict rather than silently returning a confident-looking but aliased number.

---

## A second capability on the same capture stream: occupancy sensing

The fingerprinting track answers *"who is transmitting."* A second pipeline (`pc/occ/`) answers *"what is happening in the space,"* from the **amplitude** of the very same captured frames — cameraless presence, motion, and even respiration detection. The division of labor is principled: ESP32 phase is per-packet uncalibrated so amplitude owns occupancy, while phase owns fingerprinting.

It normalizes every frame's amplitude vector to unit mean (cancelling automatic-gain-control so only spectral *shape* is analyzed), builds its time axis on the node's own hardware timestamps rather than bursty host arrival times (so respiration FFTs see a true sampling grid), and requires consensus before it alarms — motion needs agreement across multiple links, and breathing detection needs several subcarriers agreeing on one frequency, so single-channel artifacts don't trigger false alarms. On recorded sessions it cleanly separated an occupied-but-still room (respiration detected at 7.0–16.0 bpm, 6.1–15.2 dB SNR across all 54 presence-verdict scans) from an empty-room night, with motion-detection edges matching the human narrative to the minute. It's a demonstration that one CSI capture stream supports both device identity and environmental sensing.

---

## Engineering for 24/7 autonomy

This is not a lab demo that runs while someone watches it — it runs continuously, so the firmware was hardened for autonomous field deployment. The HAL and processing were refactored into shared ESP-IDF components used by every node:

- **Watchdogs with real recovery.** A task watchdog hard-resets the node if the serial-drain task hangs; an RF-liveness monitor resets it if the WiFi stack delivers nothing for 120 s (recovering from stack lock-ups that would otherwise silently kill a sensor). Abnormal resets increment a persisted crash counter reported in health telemetry.
- **Honest timing.** The CSI callback only enqueues; one drain task owns stdout. Sampling cadence is set by RF arrivals, never by host serial latency, and every timestamp is node-boot-relative so the host can reconstruct true frame timing.
- **Baseline calibration on power-up** — a 300 s ambient noise-floor characterization, then continuous thermal tracking via EMA.
- **Binary telemetry protocol v2** with per-node/per-environment IDs (persisted in NVS), a queue-drop counter as a missing-frame indicator, and periodic STATUS health frames (firmware version, reset reason, crash count, uptime, heap, noise/RSSI).
- **Safe-boot recovery console** and a `field_diag.py` tool that plugs into any node and returns a full health report with a meaningful exit code.

A representative hard-won detail: pyserial asserts DTR/RTS on port open, which trips the ESP32 devkit's auto-reset circuit — so *every diagnostic connection used to silently power-cycle the node and restart its calibration window.* All host tools now open ports with those lines deasserted, so observing a node no longer disturbs it. The kind of bug you only find, and only fix, by running the thing for real.

---

## Tech stack

**Firmware:** C on ESP-IDF v5.5; custom ESP-IDF components (`node_hal`, `telemetry`, `calibration`); ESP-NOW transport; SSD1306 OLED status display; NVS-persisted identity; custom little-endian binary wire protocol with magic-byte resync and XOR checksums.

**Signal processing / host:** Python with NumPy — hand-rolled DSP (RANSAC, phase unwrap, Welford covariance, 1D Kalman) with no heavyweight ML dependency; pyserial for capture; SQLite for fingerprint history and persisted models; Matplotlib for analysis plots.

**Scale:** ~4,000 lines of Python across capture, fingerprinting, and occupancy tools; custom firmware across three node roles; 2.36 million CSI frames across the 2026-07-13 session set backing the reported results, out of ~15 million frames / 13 GB captured overall.

**Deliberately not used:** a deep-learning framework. The discrimination is a statistically interpretable Gaussian/Mahalanobis model with χ²-calibrated thresholds — every decision the system makes is explainable in terms of an ellipse and a probability, which for a security system is a feature, not a limitation.

---

## What's next

The roadmap is where the near-term work is landing, and it targets exactly the honest limitations above.

**Landing soon:**

- **2D spatial mapping.** Fusing sequence-aligned features across multiple receivers into coarse zone localization — moving from "who is transmitting" to "who is transmitting, and *where*." Cross-receiver drift agreement is already validated, which is the hard prerequisite.
- **Digital fingerprint matching at scale** — maturing the live match/library workflow so any capture is scored against the learned device library in real time, with the four operational verdicts (known device, same radio / rotated MAC, trusted MAC but wrong radio → investigate, stranger).

**Cracking the same-model / clock-twin frontier:**

- **Thermal compensation from the transmitter itself.** Every ESP32 has an internal die-temperature sensor; embedding TX die temperature in the beacon payload lets the host correlate and compensate the thermal drift that currently smears same-model centroids. Zero added hardware cost, and it's the single highest-value improvement.
- **Higher-dimensional features.** The current model uses two features (CFO, SFO) and throws away the per-subcarrier phase *residual* shape after the RANSAC fit — which carries multipath and hardware-nonlinearity signature, I/Q imbalance, and amplitude ripple. The literature indicates these separate near-identical radios; adding a residual-vector feature to a higher-dimensional Mahalanobis (or a small classifier) is the path to beating the ~77% same-model ceiling. Crucially, this can be validated by re-scoring the *existing* 2.36M-frame dataset — no new captures required.

**Hardware and deployment:**

- **Custom 3D-printed enclosures** for the nodes — turning the breadboard prototype into a finished, mountable sensor product.
- **Raspberry Pi host migration** — the collector is pure Python/pyserial and runs unchanged on a Pi, enabling a permanent headless deployment with home-automation (MQTT / Home Assistant) publishing.

---

## Why this project

It's a complete embedded-plus-DSP system built from first principles: custom firmware on constrained hardware, a signal-processing pipeline where every stage defeats a specific measured failure mode, statistically honest evaluation, and the operational discipline to run it 24/7 and fix the bugs that only autonomy surfaces. The headline number is strong — 99.7% at the task that matters — and the parts that aren't solved yet are named, measured, and on the roadmap rather than hidden. That's the combination the whole thing was built to demonstrate.

---

*Source code and captured datasets: [GitHub repository]. Hardware photos of the custom-enclosure nodes to follow.*
