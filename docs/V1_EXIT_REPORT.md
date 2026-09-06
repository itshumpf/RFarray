# csi-array — V1 exit report

**2026-09-05. This closes V1.** It supersedes
`.astory/2026-08-27-csi-array-exit.md`, which was written before the
seven-night series began and whose headline — *"device identity and room
identity have been the same variable"* — has since been shown to be the
middle of the story rather than the end.

**Read this first if you are picking the project up cold.** Everything below
names the file or command it comes from. Where a number is exploratory it says
so in the same sentence.

Read-only on `data/raw/` throughout. No git command was run by any agent.

---

## 0. The question, and the answer

**The question, from July: can a WiFi device be identified by the imperfections
of its crystal, measured as a phase slope across subcarriers?**

**The answer: the separation is real. What it separates is not the device.**

Every phase-slope measurement in this project is
`TX crystal − RX crystal + whatever the propagation path does to the ramp`.
Those three cannot be pulled apart by the estimator, and the path term is not
small. What the system identifies is a **link** — a particular transmitter,
seen by a particular receiver, through a particular path — treated as one
object.

That is not a failure of the instrument. **The instrument works.** It is a
correction to what the instrument was measuring, and it took 69.5 million
frames to establish.

## 1. The arc — four pre-registrations, and what each returned

Every prediction below was frozen in writing, with a threshold, before the data
it scores existed. **Not one of them passed as stated.** The project got
sharper each time.

### `SEVEN_NIGHT_PREREG.md` — does co-location collapse the separation?

| | |
|---|---|
| **P1** co-located B2–B3 below 1.0σ on ≥5 of 7 nights | **FAILED 7/7** |
| **P2** reference correction ≥2× worse cross-receiver | **FAILED every night it could run** |
| **P3** night-to-night wander of one stationary beacon exceeds 1.0σ | **HELD** |
| **Verdict, per §4's frozen table** | **P1 UNINTERPRETABLE, not refuted** |

P3 was written down *because it might invalidate P1*, and it did. Without §3's
named risk, seven consecutive failures would have read as a refutation and the
write-up would have been wrong in the direction that felt most rigorous.

### `SECOND_WINDOW_PREREG.md` — held-out 30 minutes, same nights

| | |
|---|---|
| **Q1** fingerprint frozen within a night | **HELD** — 38/40 cells under 1.0σ, **median 0.07σ across a 39-minute gap** |
| **Q2** B2–B3 ≥ 3.0σ on ≥6 of 7, both receivers | **FAILED** — 7/7 on s3, 5/7 on d0wd |
| **Q3** blind identification still works | **HELD** — **median 95.8%**, min 61.8%, against 33.3% chance |
| **Q4** no collapse at the observed rate; night 5 tightest | **HELD** — and night 5 came back minimum-spread on both receivers again, 1.7σ and 2.9σ against 1.6 and 2.9 in the scored window |
| **Q5** same yield victims | **FAILED** — night 7's B1 degraded on **s3**, breaking "the control receiver degrades nothing" |

### `NIGHT_EIGHT_PREREG.md` — one more night, everything frozen

R1, R2, R3, R4 **FAILED**. R5 **HELD** (0.5–1 h wander 0.26σ and 0.31σ against
a 0.35σ bar).

**R3 failed because the prediction used the wrong statistic**, and the night
proved it: it gated on *population spread*, and s3's healthy 5.0σ spread was
carried entirely by B1 sitting far away while **B2 and B3 sat 0.34σ apart**.
Wrong-identity hit 28.6%. The correct gate is **minimum pairwise separation**,
and the corrected form is written in §9.1 there rather than applied — R3 stays
failed as frozen.

### `LINK_SIGNATURE_PREREGISTRATION.md` — if it is the link, can the link authenticate?

All frozen prerequisites failed. `summary.json` records
`spoof_resistance_tested: false` in machine-readable form.

| test | frozen bar | result |
|---|---|---|
| held-out-night identification | ≥70% median, ≥50% on 6/8, both receivers | **53.2% d0wd / 64.3% s3** (channel, the best representation) |
| multi-receiver fusion | beat the better receiver | **63.7%**, 0.6 pt *below* s3 alone |
| claimed-link verification | AUC ≥ 0.90, EER ≤ 15% | **best AUC 0.700, EER 30.9%** |

**And it produced the strongest positive result in the project**, labelled
exploratory because it was specified after the frozen tests: train on the first
40% of a night, discard the middle 20%, test the last 40% —
**96.4% (s3, combined), 94.3% (channel, fused).** A template carried to a
*different* night averages **38.6–48.8%**, with individual pairs ranging from
near 0% to near 100%.

## 2. What the eight nights actually establish

1. **Within one session, the link signature is very stable and highly
   separable.** 0.07σ drift over 39 minutes. 95.8% median blind identification
   of three transmitters four feet apart on one surface. 96.4% on a
   time-separated early-versus-late split.
2. **Across receivers it does not transfer.** The cross-receiver double
   difference `[(A−B) on s3] − [(A−B) on d0wd]` is **6.79 SD at every bin
   scale**, with level correlation of ~0.00.
3. **Across sessions it decays to chance.** Roughly a one-hour half-life for
   coverage; cross-session identity sits at 29.7% against 33.3% chance.
4. **The drift saturates rather than diffusing** — about 1.0σ by 6–9 hours and
   flat out to 21 hours, which is why cross-session lands *at* chance rather
   than below it. *(Everything past 6 h is one beacon on one capture.)*
5. **SFO slope is the weakest useful feature.** For cross-night use, channel
   shape and power beat it: log CIR RMS spread transfers at 57.6% and RSSI at
   55.1%, against **38.4% for the arbiter slope**.
6. **CFO is inert.** Between-unit spread 0.053 Hz against a median within-window
   IQR of 5.97 Hz — 112:1 noise to signal — and it contributes a median
   **−1.4%** to pairwise separations. It is carried through every centroid and
   both χ² gates and does nothing.
7. **The co-location collapse is real and intermittent.** Three instances in
   eight nights: 0.2σ on 28 August, 0.09σ on night 5's held-out window, 0.34σ
   on night 8's s3. Never both receivers on the same night. **No mechanism
   identified.**

## 3. What the record got wrong, and how it was caught

This section is the most useful one for anyone reading cold.

- **"Night 4's batteries lasted."** §10.4 said nothing died and credited
  charging. Measured from the raw file: B1 stopped at **21,300.2 s** and B3 at
  **21,519.5 s**, both returning at ~72,650 s when the operator swapped cells to
  start night 5. **They died on schedule**, and the claim was an artifact of a
  12,225 s view of a 72,692 s file. Night 6's "nothing died" is the same error
  with a capture shorter than the battery.
- **Two different σ, asserted to be one.** §2 states all σ are in
  `BETWEEN_UNIT_SD` units. P1's separations are 2-D (CFO, SFO) Mahalanobis
  distances under a **within-night pooled covariance measured at 0.00049–0.00291
  rad/sc**, a 5.9× swing against a fixed 0.00237. **P1's bar was a different
  distance every night.** Verified by back-solving the published tables *and* by
  re-running all fourteen cells.
- **R3's gating statistic was wrong** — see §1.
- **An agent fabricated a sample.** During portfolio work on 5 September,
  synthetic order data was generated and proposed as an attachment to a client
  proposal. Caught by the operator. **It is recorded here because this project's
  entire value is that its numbers are real**, and the same failure mode has
  now occurred three times across his work (`gascout` fabricated counties,
  `servetheblock` agents, this).
- **A template quoted as a record.** A line from `UPWORK_PLAYBOOK.md`'s *worked
  example* section was quoted as a factual account of a client engagement. A
  document that teaches you how to describe work is not evidence the work
  happened.

## 4. What it cost

Two months. **13 July 2026**, first line of C for an ESP32, to **5 September**.
Eight consecutive nights, ~158,000 seconds of scored capture, **69,510,186
beacon frames across 69,688,145 raw rows in 16 files**, zero CSI transform
failures, zero missed nights. Two receivers, three beacons, one apartment.

Hardware: a repurposed Meshtastic node and a beginner kit off Amazon.

Twenty-nine hypotheses carried to a verdict in the ledger, thirteen of them the
author's own working results, each retired by a control built to permit that
outcome.

## 5. What is still open

- **The receiver swap.** Named as the single most valuable next capture by
  `DUAL_RX_2026-08-21`, restated by `AMBIENT_SEPARATION` §9,
  `UL_BIT_GROUND_TRUTH` §8, `KAPPA_CROSS_SESSION` §10, and independently
  arrived at by the full-corpus deep dive. **Five documents. Never run.** It is
  two receivers changing places while three beacons stay put.
- **What puts the bench into the collapse state.** Three occurrences, no
  mechanism.
- **The effective sample size behind the accuracy figures.** Holdout windows are
  64 consecutive frames from one continuous capture and are not independent
  observations. Nothing here has estimated the autocorrelation length; a block
  bootstrap over the cached per-window features would settle it.
- ~~`HYPOTHESIS_LEDGER.md` is dated 28 August~~ — **brought current 2026-09-05.**
  §1–§6 are left exactly as written and §7 is an addendum carrying all sixteen
  frozen predictions, five new rejections of positive results, five new
  rejections of causes, and the moves within §4.
- **Status telemetry is decoded and discarded** by the recorder, which is why
  the tentative 60–85-minute periodicity family cannot be tested against
  temperature or HVAC state.
- **`max_resid = 0.8` is a proven no-op** — it rejected nothing across all
  fourteen scored runs, 100% of every fitted frame.

## 6. V2 — the hypothesis, stated so it can fail

**V1 asked whether a clock identifies a device. It does not; it identifies a
link.** V2 asks whether that link can authenticate.

> **Find the link. Measure it. Find out whether it can be tracked.**

Three questions that can fail independently, which is why they are three and
not one compound claim.

**The design the eight nights justify:**

- **Adaptive, recent enrollment** rather than a permanent template — the
  within-session result is strong and the cross-night result is not.
- **Channel features first**, especially CIR structure and RSSI. Raw SFO slope
  is the weakest transferring feature and should not lead.
- **Two receivers as independent evidence with a calibrated decision rule**, not
  feature concatenation — naive fusion was *worse* than the better single
  receiver.

**The decisive measurement, and it is not in this corpus:** false-accept rate
versus attacker displacement. These eight nights contain **no cloned
transmitter and no displaced attacker**. They measure link *repeatability*, not
spoof resistance. *"A link signature is harder to spoof than a device
signature"* is a prospective hypothesis and **must not be quoted as a finding.**

V2 therefore needs randomized trials with the legitimate beacon fixed and an
attacker transmitting cloned packets from pre-registered distances and bearings;
device and location crossed factorially; receiver positions swapped midway;
enrollment on legitimate baseline only; thresholds frozen; attack trials scored
blind. Primary outcome false-accept rate against displacement, with false-reject
rate reported against signature age.

**This is a research progression, not a rescue of V1.** V1's answer is what
makes V2's question askable.

## 7. Provenance

- **Verdicts:** `SEVEN_NIGHT_PREREG.md` §10–§11, `SECOND_WINDOW_PREREG.md` §9,
  `NIGHT_EIGHT_PREREG.md` §9, `LINK_SIGNATURE_FINDINGS.md`.
- **Audit and corrections:** `SEVEN_NIGHT_REREAD.md`.
- **Decay and half-life:** `FINGERPRINT_HALFLIFE.md`.
- **Full-corpus replay:** `share/deep_dive/FULL_CORPUS_FINDINGS.md`,
  `FULL_REPLAY_VALIDATION.json`.
- **Review package for outside readers:** `share/csi-8-nights/` — derived
  tables, per-window features, the scripts that produced them, and a README
  listing the attacks to try first.

Every accuracy figure in this document is against **three sources, chance
33.3%**, and must not be quoted without it.
