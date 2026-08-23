# S3_SFO_STEPS — what causes the within-session SFO steps on the Heltec S3

Follow-up to `docs/DUAL_RX_2026-08-21.md` §3.3, which found the S3's
per-beacon SFO non-stationary and recorded the cause as unknown.

Read-only. No serial port was opened. Nothing in `data/raw/` was modified,
renamed or deleted; both CSVs were opened `"r"` and never written. Nothing
was flashed, staged, committed or pushed. Two files in the repo were
written by this pass: this one and `pc/exp_s3_sfo_steps.py`. Caches went to
`../s3_sfo_steps_cache/`, outside the repo tree.

Inputs: `data/raw/desk_20260821_125017.csv` (D0WD, `node_id` 68) and
`data/raw/s3_20260821_125017.csv` (Heltec S3, `node_id` 108), the same
70 minutes, three beacons, promiscuous `csi_rx`.

---

## 0. Answer, stated once

**The steps are not a clock effect and not two events. They are one
receiver-side event on the S3 at t = 930 ± 10 s, and what steps at that
moment is the RANSAC fit residual, which the SFO estimate is a near-linear
function of.**

Two claims, with different strengths of evidence:

1. **Established.** On the S3, per-60 s-bin SFO median and per-60 s-bin
   mean `resid_std` correlate at **r = +0.948 / +0.942 / +0.970** for
   B1 / B2 / B3 over 70 bins (§7, M2). The B3 anomaly disappears when the
   residual gate is tightened: the pre-step-to-post-step difference in
   per-frame median slope falls from **0.0451 rad/sc at the shipped gate
   `resid_std <= 0.8` to 0.0015 at `resid_std <= 0.12`**, a 30x collapse
   (§7, M4). `+0.060` is not a property of B3's crystal, of the S3's
   crystal, or of the pair. It is what `ransac_line`
   (`pc/rff/dsp.py:71-103`) returns when the phase-vs-k curve on that link
   is not close to a line, and the shipped gates
   (`pc/rff/dsp.py:164`) do not screen it out.

2. **Not established.** What changed inside the S3 at t = 930 s. Something
   did — `noise_floor`, RSSI on all three links, detected-frame rate and
   fit residual all move inside one 20 s window, on the S3 only — but no
   field in these files names it, and `tlm_status_t`
   (`firmware/common/telemetry/include/telemetry.h:35-46`) carries no PHY,
   gain or calibration state. §10 lists what it is not, and §11 what would
   settle it.

Direct answers to the three questions asked:

- **Did `noise_floor` step?** On the S3, **yes**, at t = 930 s, and
  identically across all three beacons (it is a per-node quantity). On the
  desk it cannot step: it reads `-97` on **577,354 of 577,381 rows** and
  the 27 exceptions are the known corrupt-row artefact (§4).
- **What did B1 do?** **B1 stepped too, at the same instant, in the same
  direction as B3**: `+0.01691 [+0.01649, +0.01733]` → `+0.01227
  [+0.01209, +0.01251]`, CIs disjoint (§6). It was not flat. The 120 s
  bins in `docs/DUAL_RX_2026-08-21.md` §3.3 did not flag it.
- **Cause.** Proximate cause identified (residual-driven estimator bias,
  §7). Root cause of the t = 930 s receiver event **not identified** (§10).

---

## 1. Method

`pc/exp_s3_sfo_steps.py`, four passes. Run from the repo root.

```
python3 pc/exp_s3_sfo_steps.py scan data/raw/desk_20260821_125017.csv --tag desk
python3 pc/exp_s3_sfo_steps.py scan data/raw/s3_20260821_125017.csv   --tag s3
python3 pc/exp_s3_sfo_steps.py sfo  data/raw/desk_20260821_125017.csv --tag desk \
        --t0 1787334617609854 --t1 1787338830177969
python3 pc/exp_s3_sfo_steps.py sfo  data/raw/s3_20260821_125017.csv   --tag s3 \
        --t0 1787334617609854 --t1 1787338830177969
python3 pc/exp_s3_sfo_steps.py report --tags desk,s3 --bin-s 60
python3 pc/exp_s3_sfo_steps.py report --tags desk,s3 --bin-s 20 --lo 12 --hi 19
python3 pc/exp_s3_sfo_steps.py mech   --tags desk,s3
```

and, for the per-frame stratification in §7:

```
B=1787334617609854
python3 pc/exp_s3_sfo_steps.py frames data/raw/s3_20260821_125017.csv \
        --tag s3pre  --mac f4:2d:c9:70:72:30 --t0 $B --t1 $((B+900000000))
python3 pc/exp_s3_sfo_steps.py frames data/raw/s3_20260821_125017.csv \
        --tag s3post --mac f4:2d:c9:70:72:30 --t0 $((B+960000000)) --t1 $((B+1860000000))
python3 pc/exp_s3_sfo_steps.py frames data/raw/desk_20260821_125017.csv \
        --tag deskpre  --mac f4:2d:c9:70:72:30 --t0 $B --t1 $((B+900000000))
python3 pc/exp_s3_sfo_steps.py frames data/raw/desk_20260821_125017.csv \
        --tag deskpost --mac f4:2d:c9:70:72:30 --t0 $((B+960000000)) --t1 $((B+1860000000))
```

All phase work is `pc/rff/dsp.py`'s `FrameEstimator` +
`WindowAggregator(window=64)`, gates `inlier_ratio >= 0.6` and
`resid_std <= 0.8` — i.e. `pc/rff_offline.py:54-79` with a MAC restriction
and a `pc_time_us` window added, which is the pipeline
`docs/DUAL_RX_2026-08-21.md` Appendix B used. Two things were added:
per-window `resid_std` (the shipped `WindowAggregator` returns mean
`inlier_ratio` as `quality` and discards `resid_std`,
`pc/rff/dsp.py:185-195`) and a per-frame reject-reason code.

`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py`
were not used; `docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 establishes all three
have the DC/guard-band index wrong.

**Reproduction check.** The `sfo` pass returns, per cell, exactly the
window counts and reject rates `docs/DUAL_RX_2026-08-21.md` §3.2 reports:
B1 2,420 / 3.70 %, B2 3,788 / 1.34 %, B3 1,423 / 43.54 % on desk;
B1 2,796 / 0.37 %, B2 3,297 / 1.03 %, B3 3,389 / 12.53 % on s3. Six of six.
This pass is looking at the same numbers as the pass it is following up.

`pc_time_us` is a per-drain-batch host stamp
(`pc/node_census.py:30-35`, `docs/HANDOFF.md` trap #1). It is used here
only to place bins and define the common window, never to measure cadence.

---

## 2. It is one event, not two

`docs/DUAL_RX_2026-08-21.md` §3.3 reports B3 stepping "between t = 12 and
14 min" and B2 at "t = 16 min", and builds an argument on the two being
four minutes apart and opposite in sign. At 10 s resolution
(`mech`, M1) they are the same event:

```
t(s)    nf_mean  frac-94 | B1 rssi   sfo      inl   | B2 rssi   sfo      inl   | B3 rssi   sfo      inl
  900   -94.000   1.000  |  -79.10  +0.01584 0.886  |  -74.29  +0.01028 0.956  |  -75.53  +0.05360 0.688
  910   -94.000   1.000  |  -79.13  +0.01733 0.871  |  -74.13  +0.00856 0.959  |  -76.27     -       -
  920   -94.000   1.000  |  -78.92  +0.01616 0.881  |  -74.16  +0.01031 0.950  |  -76.03  +0.06830 0.667
  930   -94.429   0.571  |  -81.37  +0.01894 0.838  |  -77.67  +0.01177 0.895  |  -74.83  +0.01648 0.790
  940   -95.351   0.010  |  -82.00  +0.01367 0.855  |  -75.22  +0.01556 0.909  |  -72.12  +0.01160 0.950
  950   -94.424   0.576  |  -77.76  +0.01317 0.919  |  -72.82  +0.02456 0.866  |  -68.82  +0.00904 0.984
  960   -94.308   0.692  |  -77.78  +0.01444 0.906  |  -71.93  +0.02443 0.879  |  -68.39  +0.00916 0.985
  970   -95.000   0.000  |  -78.00  +0.01561 0.904  |  -72.08  +0.02489 0.884  |  -68.42  +0.00933 0.987
```

Everything crosses in the bins t = 930–950 s: `noise_floor` leaves its
pinned `-94`, B3's RSSI rises 7 dB, B3's `inlier_ratio` goes 0.67 → 0.98,
B2's goes 0.95 → 0.87, B1's goes 0.88 → 0.92. **t ≈ 930 s = 15.5 min.**

The apparent earlier onset of B3 is bistable flicker, not a separate step.
At 20 s bins (`report --bin-s 20 --lo 12 --hi 19`), B3/s3 reads
`+0.042` (t = 14.0), `+0.008` (14.3), `+0.007` (14.7), `+0.054` (15.0),
`+0.044` (15.3), `+0.009` (15.7) and never leaves `+0.009` again. It
alternates between the two values for ~90 s and then locks. A 120 s bin
straddling that flicker returns an intermediate value, which is what put
`docs/DUAL_RX_2026-08-21.md`'s B3 step in the 12–14 bin.

**Consequence for the argument in the brief.** "The steps go in opposite
directions, and a receiver-clock drift would move every beacon the same
way, so it is not a common receiver-clock drift" — the premise about
timing is wrong (one event, not two), the conclusion is right, and the
reason is stronger than the one given: it is not a *drift* of any kind. It
is a step, in a quantity that is not a clock (§7).

---

## 3. What moved at t = 930 s, per node

`report --bin-s 60`, windows 630–930 s (300 s before) and 960–1260 s
(300 s after), attributed per beacon:

| node | b | window | RSSI | `noise_floor` | frame reject % | inlier | resid_std |
|---|---|---|---|---|---|---|---|
| s3 | B1 | 630–930 | −81.15 | −93.9997 | 1.731 | 0.8299 | 0.1540 |
| s3 | B1 | 960–1260 | **−77.38** | **−94.6335** | **0.109** | **0.9282** | **0.1419** |
| s3 | B2 | 630–930 | −74.78 | −93.9994 | 0.380 | 0.9511 | 0.1333 |
| s3 | B2 | 960–1260 | **−73.20** | **−94.6393** | 0.494 | **0.8662** | **0.1497** |
| s3 | B3 | 630–930 | −75.72 | −94.0002 | 51.586 | 0.6984 | 0.1596 |
| s3 | B3 | 960–1260 | **−68.93** | **−94.6358** | **0.245** | **0.9835** | **0.1166** |
| desk | B1 | 630–930 | −83.63 | −97.0000 | 7.662 | 0.7847 | 0.1565 |
| desk | B1 | 960–1260 | −82.20 | −97.0000 | 3.147 | 0.8545 | 0.1489 |
| desk | B2 | 630–930 | −71.46 | −97.0000 | 1.373 | 0.9545 | 0.1348 |
| desk | B2 | 960–1260 | −70.73 | −97.0000 | 0.974 | 0.9603 | 0.1284 |
| desk | B3 | 630–930 | −83.26 | −97.0000 | 49.154 | 0.7461 | 0.1442 |
| desk | B3 | 960–1260 | −82.39 | −97.0000 | 21.998 | 0.7256 | 0.1408 |

The desk's columns move by ≤ 1.4 dB and its `noise_floor` not at all. The
desk's B3 reject rate does drop 49 % → 22 %, but it is 22 % everywhere
after and it is not a step (see §5 on B3/desk, which is a bad cell on its
own terms).

---

## 4. `noise_floor` — the requested discriminator

**On the desk it carries no information whatsoever.** Over all 577,381
rows the value is `-97` on **577,354**; the other 27 rows read
−48, −47, −45, −43, −22, −21, −20 ×2, −6, 0 ×4, 9, 11 ×2, 21, 22, 27, 30,
34, 37, 38, 44 ×2, 46, 51 — values that are not dBm at all. They are the
UART corrupt-row phenomenon (`docs/DUAL_RX_2026-08-21.md` §2.1: 34 corrupt
rows on desk, 0 on s3, from `pc/rff/protocol.py:153-180` resyncing one byte
at a time past a one-byte XOR check). The D0WD build never varies this
field. **"The desk's `noise_floor` held" is therefore not evidence of
anything** — it could not have stepped.

**On the S3 it varies, and it stepped.** Over 649,072 rows: `-95` ×408,126,
`-94` ×240,339, `-96` ×553, `-93` ×54. Per 60 s bin (`report --bin-s 60`,
table 1b), the fraction reading exactly `-94`:

```
t (min)   0     1     2     3-14  15    16    17    18    19    20    ...  67
frac -94  0.47  0.38  0.95  ~1.00 0.69  0.67  0.45  0.36  0.30  0.04  ...  0.00
```

From t ≈ 120 s to t ≈ 925 s the S3 reports exactly `-94` on essentially
every frame; from t ≈ 930 s it dithers and settles toward `-95`. It is
**identical across the three beacons in every bin** (table 1c: at t = 12
min all three read −94.0000; at t = 18 min they read −94.6261, −94.6490,
−94.6453) — it is a per-node quantity, as it should be.

**What this does and does not establish.** It establishes that a
receiver-side state on the S3 changed at t ≈ 930 s and that the desk was
in no equivalent state. It does **not** date the onset of the anomaly:
B3/s3 already reads `+0.06133` with `inlier_ratio` 0.68 in the very first
20 s window of the capture, while `noise_floor` is still dithering
(`frac -94` = 0.059 at t = 0–20 s). The pinning to `-94` begins around
t ≈ 120–160 s, after the B3 anomaly is already present. **`noise_floor`
marks the exit from the anomalous state, not the entry.** The entry is not
in this capture; the S3's `dropped` counter reads 30,391 on its first row,
so the board had been up long before the file opened.

---

## 5. RSSI

`report --bin-s 20 --lo 12 --hi 19`. S3, mean RSSI per 20 s bin:

```
t (min)   15.0    15.3    15.7    16.0    16.3
B1/s3    -79.11  -80.01  -79.60  -77.89  -77.57
B2/s3    -74.21  -75.80  -74.10  -72.00  -72.49
B3/s3    -75.90  -75.37  -70.53  -68.41  -68.25
```

All three rise, in the same bins, by different amounts: B3 ≈ +7 dB,
B1 ≈ +2.5 dB, B2 ≈ +2 dB. Over the same bins the desk reads
B1 −84.2 → −83.3, B2 −71.3 → −71.3, B3 −81.7 → −82.6 — no corresponding
move on any beacon.

**RSSI steps with the SFO, on the S3 only.** That is the answer the brief
asked for, and it is consistent with a receiver front-end state change.
But it does **not** by itself identify one: the RSSI moves are not a
common offset (7 / 2.5 / 2 dB), and `noise_floor` moves 1 dB in the
*opposite* sense to RSSI, so a single scalar gain-calibration shift does
not reproduce the pattern. Something changed about how the S3 receives;
these numbers do not say what.

---

## 6. Common-mode or per-beacon — B1 reported explicitly

`mech`, M3. Bootstrap medians (4,000 resamples of the window list,
`np.random.default_rng(0)`), 600 s either side of the transition:

| node | b | 330–930 s | 960–1560 s | Δ |
|---|---|---|---|---|
| s3 | B1 | **+0.01691** [+0.01649, +0.01733] | **+0.01227** [+0.01209, +0.01251] | **−0.00464** |
| s3 | B2 | +0.00926 [+0.00901, +0.00951] | +0.02712 [+0.02660, +0.02772] | **+0.01786** |
| s3 | B3 | +0.05915 [+0.05777, +0.06110] | +0.00842 [+0.00828, +0.00850] | **−0.05073** |
| desk | B1 | +0.00968 [+0.00936, +0.01022] | +0.00855 [+0.00825, +0.00887] | −0.00113 |
| desk | B2 | +0.00800 [+0.00792, +0.00811] | +0.00688 [+0.00682, +0.00697] | −0.00112 |
| desk | B3 | +0.01070 [+0.00974, +0.01217] | +0.00880 [+0.00723, +0.00966] | −0.00190 |

**B1/s3 stepped.** −0.00464 rad/sc, CIs disjoint, 2.0x `BETWEEN_UNIT_SD`
(0.00237, `pc/exp_thermal_evidence.py:129`), and in the **same direction as
B3** — down. Its reject rate fell 16x (1.73 % → 0.11 %) and its
`inlier_ratio` rose 0.83 → 0.93 in the same window. It was reported as
flat only because it is a small step next to B3's factor of seven.

So all three S3 beacons moved at one instant. Two down, one up. The desk's
three all moved −0.0011 to −0.0019, which is a common drift of the same
sign and roughly the same size on all three — the signature you would
expect from a slow shared effect, and nothing like the S3's pattern.

**Revised reading of the sign argument.** Two of three beacons stepped
down and one up, at one instant, on one receiver. That is not a receiver
clock — a receiver clock offset is common to all sources by construction,
so it cannot produce a −0.005 / +0.018 / −0.051 fan-out. §7 says what it
is instead, and the sign of each beacon's step follows from it: **B1 and
B3's fits improved and B2's degraded**, which is exactly the ordering of
the three signs.

---

## 7. The mechanism: SFO tracks the RANSAC residual

### 7.1 Correlation across the whole session

`mech`, M2. Per 60 s bin, SFO median against mean `resid_std`, all bins
with ≥ 5 windows:

| node | b | bins | r(sfo, resid_std) | r(sfo, inlier_ratio) | d sfo / d resid |
|---|---|---|---|---|---|
| s3 | B1 | 70 | **+0.948** | −0.917 | 0.47 |
| s3 | B2 | 70 | **+0.942** | −0.623 | 1.05 |
| s3 | B3 | 69 | **+0.970** | −0.968 | 1.11 |
| desk | B1 | 70 | +0.477 | −0.429 | 0.15 |
| desk | B2 | 70 | +0.583 | −0.767 | 0.19 |
| desk | B3 | 66 | +0.570 | +0.342 | 0.67 |

On the S3 the reported SFO is a near-linear function of the fit residual.
The sign is **positive in all six cells**, on both receivers, so it is not
an artefact of a shared time trend: B2/s3 moves *up* over t = 16–58 min
while B1/s3 and B3/s3 move *down*, and its residual moves up with it.

`resid_std` is the better predictor than `inlier_ratio`, and B2's return
after t = 58 min is where that shows. B2/s3, 60 s bins:

```
t (min)   56       57       58       59       60       61       62
sfo    +0.02147 +0.01988 +0.01288 +0.01113 +0.01171 +0.00886 +0.00750
resid    0.1451   0.1447   0.1376   0.1333   0.1341   0.1307   0.1331
inlier   0.8663   0.8002   0.8816   0.8298   0.8072   0.8558   0.8463
```

The SFO tracks `resid_std` down; `inlier_ratio` does not move
monotonically and would not have predicted the return. **B2/s3's "return
after t = 60 min" is a return of its fit residual to the value it held
before t = 930 s.**

### 7.2 The non-circular test: stratify the same frames by fit quality

The correlation above shares inputs with the quantity it explains, so on
its own it is suggestive rather than decisive. The test that is not
circular is to take **one fixed population of frames** and ask whether its
better-fitting members give a different slope than its worse-fitting ones.
If `+0.060` were a real timing offset on that link it would appear
identically at every quality level.

`mech`, M4, per-frame medians for B3 (`f4:2d:c9:70:72:30`), pre = 0–900 s,
post = 960–1860 s:

| set | gate `resid_std <=` | kept % | per-frame slope median |
|---|---|---|---|
| s3 pre | 0.80 *(shipped)* | 100.0 | **+0.05373** |
| s3 pre | 0.16 | 55.1 | +0.01968 |
| s3 pre | 0.14 | 22.1 | +0.01138 |
| s3 pre | 0.12 | 5.7 | **+0.00977** |
| s3 post | 0.80 *(shipped)* | 100.0 | +0.00866 |
| s3 post | 0.16 | 98.6 | +0.00866 |
| s3 post | 0.14 | 93.8 | +0.00864 |
| s3 post | 0.12 | 63.1 | +0.00830 |

**Pre-step and post-step differ by 0.0451 rad/sc at the shipped gate and by
0.0015 at `resid_std <= 0.12` — a 30x collapse.** The post-step population
is insensitive to the gate (0.00866 → 0.00830 across an 8x change in
retention); the pre-step population moves by a factor of 5.5. The same
holds on the desk's B3 (0.0099 → 0.0022 across the same two gates), which
is the same effect on the same beacon at the other receiver.

Stratifying by `inlier_ratio` instead gives the same picture and shows the
gradient directly. Per-frame slope median, B3, pre-step window:

```
inlier band   0.60-0.70  0.70-0.80  0.80-0.90  0.90-0.95   (>0.95: n=14)
slope med      +0.06483   +0.05640   +0.04091   +0.02553
n                 12,217      7,916      1,445         60
```

versus the post-step window, where it is flat:

```
inlier band   0.60-0.70  0.70-0.80  0.80-0.90  0.90-0.95  0.95-1.01
slope med      +0.01046   +0.01045   +0.01024   +0.01094   +0.00860
n                    221        477      1,471      3,550     46,576
```

Pre-step, the estimate walks monotonically toward the post-step value as
the fit improves, and essentially no frame reaches `inlier_ratio > 0.95`
(14 of 51,079). Post-step, the estimate is the same at every quality level
and 89 % of frames clear 0.95.

### 7.3 What this says about the shipped gates

`pc/rff/dsp.py:164` sets `min_inlier_ratio=0.6, max_resid=0.8`. On this
data the residual gate is **inoperative**: 100.0 % of B3 frames pass
`resid_std <= 0.8` in all four populations above. All the rejecting is done
by the inlier gate, and the bias is a smooth function of quality across the
entire *accepted* range — the median of 64 accepted frames
(`pc/rff/dsp.py:180-189`) inherits it rather than suppressing it.

**Caveat, stated because it limits how the gate sweep may be quoted.**
Tightening the gate also pulls the desk's post-step B3 down
(+0.00966 → +0.00364 from 0.80 to 0.12), so a tight gate is not free — it
has its own selection effect and the absolute value under it should not be
read as "the true SFO". What survives that objection is the *difference*
between two populations under one common gate, which is what §7.2 quotes,
and which collapses by 30x.

---

## 8. USB and throughput — tested and killed as the trigger

`firmware/csi_rx/sdkconfig:375` reads
`CONFIG_SOC_WIFI_PHY_NEEDS_USB_WORKAROUND=y` and `:1178`
`CONFIG_ESP_PHY_ENABLE_USB=y`; `:391` `CONFIG_IDF_TARGET="esp32s3"`. The
same flag is at `firmware/csi_tx/build_s3/sdkconfig:375`. So the S3's
receiver build does run the PHY with the USB workaround enabled and the
D0WD does not. That much is confirmed from the files.

It is not the trigger for this event, on three measurements:

1. **Delivered rate does not move across the step.** `report --bin-s 30`:
   the S3 delivers **153.56 fps over t = 630–930 s and 153.97 fps over
   t = 960–1260 s** (+0.27 %), and 150.9–155.0 fps in every 30 s bin
   between t = 10 and 23 min — a range that contains no edge at t = 930 s
   (its two lowest bins are at t = 11.0 and 11.5 min). `docs/DUAL_RX_2026-08-21.md` §2.5 finds the
   same 154 fps in all ten deciles.
2. **Bytes per frame do not move.** `report`, table 0: `csi_len` is 256 on
   **100.000 %** of beacon frames on both nodes, before and after
   (B1 34,645 pre / 142,389 post, B2 50,791 / 159,421,
   B3 51,089 / 193,452, zero `csi_len` 128 in any of the six). The 7,860
   `csi_len` 128 rows in the S3 file are all ambient MACs, and their
   5-minute histogram has no edge at t = 930 s.

   Delivered frames × bytes per frame is therefore constant across the
   step: **the host-side USB write load is the same before and after.**
3. **Queue drops rise, but downstream of the event, not upstream.** Drops
   go 20.27/s → 41.20/s, so *offered* load goes **173.83 → 195.18 fps**
   while *delivered* stays 154. The S3 started detecting ~21 more
   frames/s. That is the S3 hearing more, which is the same fact as the
   RSSI rise in §5 — a consequence of whatever happened, not a change in
   USB activity that could have caused it.

**Confirmed dead as a trigger.** What is *not* excluded is the USB
workaround as a standing condition — a PHY that is permanently in a
different configuration on this board than on the D0WD, and which may be
why the S3 has a bistable receive state at all when the desk does not.
Nothing here tests that; it needs a build comparison, not a data pass.

---

## 9. Everything else the data supports, checked

| candidate | check | result |
|---|---|---|
| reboot / uptime wrap | `report`, table 6 | one backward `esp_timestamp_us` step per node: desk at t = 112.3 s (`4294960368 → 4365`), s3 at t = 2758.4 s (`4294966145 → 2967`). Both clean u32 wraps, neither near t = 930 s. **Not a reboot.** |
| 300 s startup calibration | `calibration.c:64-67` gate; S3's `dropped` = 30,391 on its first row | board was up long before the file opened, frames flow from t = 0. **Not calibration.** |
| channel change | `report`, table 0 | s3: `channel` = 6 on every row. desk: 24 distinct values including 211, 220, 255 — the corrupt-row artefact again, not a channel hop. **Not channel.** |
| `env_id` | `report`, table 0 | 0 on every row of both files. **No change.** |
| frame loss | §8 item 3 and `docs/DUAL_RX_2026-08-21.md` §2.4 | drops are not source-selective (±3 % across beacons on s3) and rise *after* the event. **Not loss.** |
| corrupt rows | §4 | 27 rows on desk with impossible `noise_floor`, 0 on s3. Confirms `docs/DUAL_RX_2026-08-21.md` §2.1 via a third independent column. Confined to desk; **cannot explain an S3 event.** |
| ambient interferer arriving/leaving | per-MAC 5-minute histograms over both scan caches | the only ambient MACs with structure are `02:a7:34:41:c2:dd` (present t ≈ 600–1500 s) and `ba:80:d5:0c:18:87` (activity dips t ≈ 600–1500 s), and **both appear on both nodes**, with edges at ~600 s and ~1500 s, not 930 s. Nothing S3-only steps at t = 930 s. **No ambient explanation found** — which is weaker than "excluded": these files only see devices that transmit CSI-bearing frames the node decodes, so a non-802.11 or off-channel interferer would be invisible here. |
| room movement | operator statement; desk saw the same minutes | the desk's RSSI on all three beacons moves ≤ 1.4 dB across t = 930 s. A room change large enough to move the S3's B3 by 7 dB and not touch the desk is possible in principle (different positions) but would not change the S3's reported `noise_floor`, which is a receiver quantity. **Not supported, not formally excluded.** |

---

## 10. Established / permitted / unknown

**Established by this capture.**

- The S3's two reported SFO steps are one event at t = 930 ± 10 s, and all
  three beacons participate, including B1 (§2, §6).
- On the S3, SFO median is a near-linear function of `resid_std`
  (r = +0.94 to +0.97 over 70 bins per cell), and the direction of each
  beacon's step is the direction its fit quality moved (§7.1, §6).
- The `+0.060` figure is an estimator bias, not a link or clock property:
  under a common tight residual gate the pre/post difference collapses
  30x, and within the pre-step population the estimate is monotone in fit
  quality while within the post-step population it is flat (§7.2).
- The post-step value is the trustworthy one. B3/s3 post-step is
  `+0.00842` against B3/desk's `+0.01070`–`+0.00880` over the same
  minutes; pre-step it is `+0.05915`, which agrees with nothing.
- `noise_floor` stepped on the S3 and cannot step on the desk (§4).
- Delivered USB throughput and bytes/frame are unchanged across the event
  (§8).

**Permitted but not established.**

- That the t = 930 s event is an AGC or PHY gain-state change inside the
  S3. It is consistent with every observation (per-node `noise_floor`,
  all-links-simultaneous, more frames detected, different residual on each
  link) and inconsistent with none. But nothing measures it: no field in
  the CSV and no field in `tlm_status_t`
  (`firmware/common/telemetry/include/telemetry.h:35-46`) carries PHY,
  gain or calibration state, so this is a hypothesis with no contradicting
  evidence, which is not the same as support.
- That the S3's bistability is downstream of the USB PHY workaround being
  compiled in on this board and not on the D0WD (§8).
- That a change in multipath local to the S3 is responsible. Not favoured
  — it does not explain `noise_floor` — but not excluded.

**Unknown.**

- **What changed inside the S3 at t = 930 s.** Not identified. The event
  is real, sharp and receiver-local, and this capture contains no field
  that names it.
- **When the anomalous state began.** Before the capture opened (§4).
- **Whether it recurs, and on what timescale.** One event in 70 minutes is
  one event.
- Whether `B2/s3`'s elevated regime and `B3/s3`'s pre-step regime are the
  same phenomenon or two. They share the residual relationship; nothing
  here shows they share a cause.

---

## 11. What would settle it

| question | measurement |
|---|---|
| What is the S3's PHY doing at t = 930 s? | Add gain/AGC state and `esp_wifi_sta_get_rssi`-class PHY fields to `tlm_status_t` (`telemetry.h:35-46`) — it has no slot for any of them today — and re-capture. This is the single measurement that would convert §10's "permitted" into an answer, and it is a firmware change of a few lines. |
| Is the estimator bias avoidable? | Re-run `pc/rff_offline.py` with `max_resid` tightened from 0.8 to ~0.14 (`pc/rff/dsp.py:164`) and check whether the S3's steps survive. §7.2 predicts they do not. **Do not adopt the tighter gate on the strength of this document** — §7.3's caveat is that it has its own selection effect, and every historical figure in the project was computed at 0.8. |
| Receiver hardware or receiver position? | Swap the two nodes' physical positions and repeat, as `docs/DUAL_RX_2026-08-21.md` §6 already says. A bistable receive state follows the board; a multipath residual stays with the position. |
| Is the USB workaround implicated? | Build `csi_rx` for the S3 with `CONFIG_ESP_PHY_ENABLE_USB=n` (`firmware/csi_rx/sdkconfig:1178`), collect over the UART console rather than USB-Serial-JTAG, and look for the same bistability. |
| Does the desk have the same problem, hidden? | Its B3 cell shows the same residual/slope relationship (r = +0.570, and a 4.5x collapse of its own pre/post difference under the same tight gate — 0.0099 to 0.0022, §7.2) at a 43.5 % reject rate. Treat B3/desk as suspect for the reason `docs/DUAL_RX_2026-08-21.md` §4 already gives, plus this one. |

---

## 12. Consequences for figures already published

- `docs/DUAL_RX_2026-08-21.md` §3.3's framing — two steps, four minutes
  apart, opposite directions, B1 flat — should be read with §2 and §6 of
  this document. One event, all three beacons, at t = 930 s.
- Its §3.4 conclusion ("the constant-offset hypothesis is refuted") is
  **not affected**: it holds in the last 10 minutes, after the event, where
  all six cells are settled, and it does not depend on the pre-step
  regime.
- Its §4 warning that **B2/s3's whole-session `+0.01823` is a two-regime
  mixture** is confirmed and can now be stated more precisely: the
  regimes are `resid_std ≈ 0.133` and `resid_std ≈ 0.150`.
- **B3/s3's whole-session median `+0.00894` should not be quoted either.**
  It is a mixture of **343 pre-step windows at `+0.06066` and 3,046
  post-step windows at `+0.00878`** (split at t = 930 s). It lands near the
  trustworthy value only because the post-step windows outnumber the others
  8.9 : 1.
- Nothing in this document touches the occupancy pipeline (`pc/occ/`,
  amplitude domain). Device-ID and occupancy figures must not be combined.
