# UL_BIT_GROUND_TRUTH — is `κ` a hardware property? A definitional test.

**Stage 1 (everything above the `STAGE 2` banner) was written and saved
before any statistic in this document was computed.** The only thing run
first was the floor check in §3, which counts frames and cells and computes
no `κ`. Its output is reproduced there.

**Date:** 2026-08-27 · Read-only on `data/raw/`. Nothing in `pc/rff/` or
`pc/exp_iq_imbalance.py` is modified. No git command is run.

---

## 0. Why this test is better than every other one in this repo

Every identity result here rests on ground truth that is **inferred**. The
three beacons are "different devices" because they have different MACs and
were bought separately — `docs/LOT_HYPOTHESIS.md` §6.3 records that **no
purchase, serial or lot record exists for any board**. The clock twins are
"twins" because they measure close, which is circular.

`C:\dev\.astory\ERROR_LOG.md` **E41** found a pair that escapes this:

> `1c:ce:51:f3:0d:fa` and `1e:ce:51:f3:0d:fa` differ in the `0x02` bit of
> the first octet — the **IEEE locally-administered bit**. Clear means a
> vendor-assigned hardware address; set means a software-chosen one. The
> pair is **one physical radio presenting two interfaces**, which is how
> Wi-Fi Direct and SoftAP conventionally derive an address from the
> hardware MAC.

That entry states the consequence itself:

> *"the pair is a ground-truth positive control for the whole
> RF-fingerprinting thesis — two addresses, provably one oscillator.
> **If `κ` is a hardware property then κ(1c) must equal κ(1e).**
> Unlike the clock-twin question there is no ambiguity about ground truth,
> because the U/L relationship is definitional rather than inferred from
> similarity."*

E41 also establishes the direction is not reversed: the locally-administered
address carries **5.6× more frames** than the global one (40,699 vs 7,286
across all 85 files), and corruption is rarer than its source, never
commoner.

**The slope has already failed this test.** `docs/BLIND_CLUSTERING.md` §9.5
measures the pair's pooled window SFO sd at **0.05147 = 21.7 ×
`BETWEEN_UNIT_SD`**, and flags the cluster that does hold them as a
mis-unwrap artefact. One radio, two addresses, and the phase slope puts them
21.7 between-device widths apart.

**`κ` has never been run against it.** This document runs it.

---

## 1. Hypothesis

**H4 — `κ` is a property of the transmitting hardware.** If so, two
interfaces of one radio must produce the same `κ`, to within the
measurement's own noise, and must sit far closer together than two
physically distinct radios do.

---

## 2. Decision rule, frozen before the numbers exist

Per receiver, never pooled across receivers — `docs/IQ_IMBALANCE.md` §15
measures `frac_rx = 5.73` and `R_disp = 826.6` against a threshold of 2,
i.e. **RECEIVER-DOMINATED**, so a cross-receiver comparison would measure
the receivers.

Let **`Δ_UL` = |κ(1c) − κ(1e)|** on one receiver, and let **`S_dev`** be the
**median pairwise |Δκ| between the three beacons on that same receiver**,
computed from the same pooled cells by the same code path. `S_dev` is the
distance between genuinely different radios as this instrument measures it.

| `Δ_UL / S_dev` | verdict |
|---|---|
| **≤ 1.0** | **PASS.** One radio's two interfaces are no further apart than the instrument's own device-scale unit. Consistent with `κ` being a hardware property. |
| 1.0 – 3.0 | **MARGINAL.** Closer than the slope's 21.7×, but the two interfaces are resolvable as "different devices." |
| **> 3.0** | **FAIL.** Definitionally identical hardware reads as distinct. `κ` is not measuring the transmitter. |

### 2.1 The error bar is the estimator's own

`pc/exp_iq_imbalance.py::features()` returns `kh1` and `kh2` — `κ` computed
on **alternate frames**, two independent halves of the same data. `|kh1 −
kh2| / 2` is therefore a split-half noise estimate that requires no
assumption. `Δ_UL` is reported against it: a difference inside the noise is
not a difference.

### 2.2 What would void the test

- If `Δ_UL` is smaller than its own split-half noise on **both** receivers,
  the test is **underpowered**, not passed, and will be reported that way.
- If the two addresses' `κ` differ by less than the beacons differ but the
  beacons themselves do not separate on these pooled cells, the positive
  control has failed and no verdict is quotable (§4 C1).

---

## 3. The floor, and the pooling this test requires

**Checked before Stage 1 was frozen. Counted frames and cells only; no `κ`
was computed.** Across the nineteen August scans:

| MAC | frames | 600 s cells | cells passing `detected2` |
|---|---:|---:|---:|
| `1c:ce:51:f3:0d:fa` | 7,462 | 347 | **0** |
| `1e:ce:51:f3:0d:fa` | 15,508 | 148 | **2** |

**At 600 s chunking this pair is a floor failure**, exactly the shape
`docs/B3_MOVED.md` §12.2 records: ~21 frames per cell against a coherence
floor of `5 × 0.886 / √n`, which at n = 21 is 0.97 and unreachable.

**Pooling is the intended remedy, not a relaxed floor.** The `Cell` class
docstring in `exp_iq_imbalance.py` states it: *"Every field is a plain sum,
so chunk cells add to give the whole-source value,"* and `add_cells()` exists
for precisely this. Chunking at 600 s is a **stability**-analysis choice
(`RECEIVER_TERM_PREREG.md` §8.3); a single `κ` per source is what this test
needs, and it is what the accumulators were built to produce.

**Frozen floor:** a (MAC, receiver) cell enters only with **≥ 2,000 admitted
frames** — `FLOOR_CHUNK` in `exp_iq_imbalance.py`, taken unchanged — and only
if the pooled cell passes `detected2`. Any address failing that is reported
as a floor failure and no `κ` is quoted for it.

---

## 4. Controls

- **C1 — positive.** The three beacons must separate from each other on the
  same pooled cells. `IQ_IMBALANCE.md` §13 measures 4.35–6.66σ (d0wd) and
  8.39–11.21σ (s3) with blind purity 0.992/1.000, so a failure here means
  the pooling broke something and the pass stops.
- **C2 — negative.** `Δ` between `1c`/`1e` and each beacon must be large. If
  the ambient pair sits on top of a beacon, the measurement is not resolving
  devices at all.
- **C3 — the slope, same cells.** The identical comparison on `slope_med`,
  so this pass carries its own comparator rather than citing
  `BLIND_CLUSTERING.md` §9.5's 21.7× from a different corpus and chunking.
- **C4 — RSSI.** `IQ_IMBALANCE.md` §18 warns `|κ|` is diluted by additive
  noise and **not comparable across links of different strength**. Mean RSSI
  is printed for every cell. If `1c` and `1e` differ materially in RSSI, the
  comparison is confounded and that is reported, not adjusted away.

---

## 5. What this test cannot show

- **Nothing about whether `κ` identifies devices across sessions.**
  `docs/KAPPA_CROSS_SESSION.md` already answered that: 65.2 % against a
  66.7 % bar, FAIL. This asks a different and more basic question.
- **Nothing cross-receiver.** Per §2, single-receiver throughout.
- **A PASS would not make `κ` a working fingerprint.** It would establish
  that `κ` tracks hardware, which is the premise every identity claim needs
  and which nothing in this repo has yet tested against non-circular ground
  truth. A FAIL closes the feature.
- **The U/L relationship is definitional, but the inference "same base
  address ⇒ same radio" is a convention, not a law.** It is how Wi-Fi Direct
  and SoftAP derive addresses; a device could in principle do otherwise.
  Stated as the one assumption this test rests on.

---

## 6. Reproduce

```
python pc\exp_ul_ground_truth.py
```

Reads the same caches as `docs/KAPPA_CROSS_SESSION.md`. Floors, the bar and
the beacon list are module constants, not CLI flags.

---

## STAGE 2 — results

**Run 2026-08-27**, `python pc\exp_ul_ground_truth.py`. Two consecutive runs
**byte-identical**. Nothing above this banner was edited after the run.

### 7. Verdict

**`κ` PASSES on the s3 receiver at 0.21 against a 1.0 bar. The SFO slope
FAILS the same test, on the same cells, through the same code path, at
3.40. The d0wd is a floor failure and no verdict is quoted for it.**

This is the first non-circular evidence in this repo that `κ` tracks the
transmitter.

### 7.1 s3 — the scoreable receiver

| quantity | value |
|---|---:|
| `κ(1c:ce…)` | \|κ\| 0.01260, arg +48.7° — n = 4,010, RSSI −33.1 dBm |
| `κ(1e:ce…)` | \|κ\| 0.01134, arg +57.3° — n = 8,869, RSSI −31.7 dBm |
| **`Δ_UL` = \|κ(1c) − κ(1e)\|** | **0.00217** |
| split-half noise (§2.1) | **±0.00111** |
| beacon pairwise \|Δκ\| | 0.00846, 0.01050, 0.01353 |
| **`S_dev`** (median) | **0.01050** |
| **`Δ_UL / S_dev`** | **0.21** — bar ≤ 1.0 |

**One radio's two interfaces sit at a fifth of the distance between two
genuinely different radios.**

`Δ_UL` is **1.96× its own split-half noise**, so the difference is resolved
rather than absent — but only just. §2.2's underpowered condition does not
fire, and it was close to firing.

### 7.2 Controls

| control | result | verdict |
|---|---|---|
| **C1** positive — beacons separate on pooled cells | three pairs at 0.00846 / 0.01050 / 0.01353 | **PASS** |
| **C2** negative — pair vs nearest beacon | **0.01528 = 1.45 × `S_dev`** | **PASS** — the pair does not sit on a beacon |
| **C3** comparator — same test on the SFO slope | \|Δslope\| 0.000064, `S_slope` 0.000019, **ratio 3.40** | **slope FAILS** its own > 3.0 bar |
| **C4** RSSI confound | −33.1 vs −31.7 dBm, **Δ 1.3 dB** | not confounded (§4 C4) |

**C3 is the result that carries the weight.** It is not cited from
`BLIND_CLUSTERING.md` §9.5's 21.7× — that figure is from a different corpus,
chunking and estimator convention. This pass computed its own comparator on
the identical pooled cells, and the direction reproduces: the slope resolves
one radio's two interfaces as **different devices**; `κ` does not.

### 7.3 d0wd — floor failure, not a null

`1c:ce:51:f3:0d:fa` reaches 3,452 frames but fails `detected2` on
**coherence**: `coh` 0.0465 against a floor of 0.0754. Its alignment is fine
(0.5683 against a wrong-pairing 0.2149).

More striking: **`a4:f0:0f:77:91:20` also fails `detected2` on the d0wd with
3,044,110 frames** — and it fails on *alignment*, `align` 0.2817 against
`align_shift` 0.3350, i.e. the true subcarrier pairing scores **worse than a
deliberately wrong one**. The reference beacon has no detectable `κ` on that
receiver at three million frames.

That is consistent with everything else recorded about the d0wd —
`SEPARATION_SCALING.md` §7 measures a cell rejecting 59.5 % of frames,
`GATE_CALIBRATION.md` §3.2 puts its corrupt-row rate at 56.81 ppm against the
s3's 0.23 — and it means **every `κ` result in this repo is effectively
single-receiver.** That is a limitation of the bench, not of `κ`, and it is
not evidence either way about the hypothesis.

### 8. What this changes, and what it does not

**It does not make `κ` a working fingerprint.**
`docs/KAPPA_CROSS_SESSION.md` measured 65.2 % against a 66.7 % bar and that
stands unrevised.

**But it changes what that failure means.** If `κ` tracks hardware — which
this pass is the first evidence for — then a feature that identifies a
device within a session at 99.0 % and fails across sessions at 65.2 % is not
failing because the feature is noise. It is failing because **something
between the transmitter and the estimate is moving**, and the candidates are
the receiver and the room. That is a materially different conclusion from
"the signature does not exist," and it makes the receiver-swap capture the
experiment that matters.

**Stated plainly:** before this pass, "`κ` is a hardware property" was an
assumption every `κ` result rested on. It is now a measurement, on one
receiver, at 0.21, against ground truth that is definitional rather than
inferred.

### 9. What this pass does not establish

- **Nothing about the d0wd.** §7.3 is a floor failure.
- **Nothing cross-receiver.** Single-receiver by design (§2).
- **Nothing about other devices.** One pair, n = 2 addresses.
- **`Δ_UL` is 1.96× its own noise.** A replication on a second U/L pair, or
  a longer capture of this one, would tighten it. None exists in this corpus.
- **The one assumption**, restated from §5: that a locally-administered
  address sharing a base with a global one implies the same radio. That is
  the Wi-Fi Direct / SoftAP convention, not a law.
- **No revision** of 65.2 %, 42.2 %, 99.7 %/7,497 or 95.7 %/14,234.

### 9.1 Temptations recorded rather than acted on

1. **Reporting the d0wd's `Δ_UL` anyway.** Both addresses have numbers
   printed in the run output. Neither clears `detected2`, so neither is
   quoted, and the receiver is reported as a floor failure.
2. **Citing `BLIND_CLUSTERING.md`'s 21.7× as this pass's slope comparator.**
   Different corpus and chunking. C3 computes its own, gets 3.40, and reports
   that instead — the smaller, less flattering number.
3. **Calling 0.21 "κ is silicon."** It is one pair, one receiver, at twice
   the noise. It is evidence, not proof, and §8 says so.

### 10. Reproduce

```
python pc\exp_ul_ground_truth.py
```

Every figure above is printed by that command. The floor, the bars and the
beacon list are module constants, not CLI flags.
