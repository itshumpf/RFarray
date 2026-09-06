# RIPPLE_TEST — is the "SFO" slope contaminated by multipath delay?

**Pre-registration. Written 2026-08-23, before any amplitude statistic or any
slope was computed from the 2026-08-23 overnight files.** Everything above the
`RESULTS` rule is frozen. If the data disagrees with a prediction below, the
disagreement gets reported; the prediction does not get revised.

What had been read at freeze time, and nothing else: `pc/rff/dsp.py` in full,
`CLAUDE.md`, `PROJECT_NOTES.md`, `docs/COLOCATED_0823.md` §0–3, `docs/V2_SPEC.md`
§5.5, `pc/occ/__init__.py`, `pc/exp_colocated_0823.py`'s header, and the CSV
header plus the first four data rows of each of the two files. No slope, no
amplitude spectrum and no correlation had been computed from any file.

---

## 0. The physics the test is built from

For a 20 MHz non-HT frame `pc/rff/dsp.py` models the measured phase as

```
phase(k) = slope·k + intercept + channel(k) + noise
```

and attributes `slope` to the transmitter's sampling-frequency offset (SFO) —
a crystal property, i.e. an identity. The docstring at `dsp.py:17-20` already
concedes that `channel(k)` is "smooth but NOT linear", and justifies RANSAC as
the defence against it.

**That defence assumes the channel term is non-linear. For a single delayed
path it is exactly linear, and RANSAC cannot see it.** A reflection arriving
τ seconds after the direct path multiplies the channel by `exp(−j2πfτ)`. Each
subcarrier k sits at `f = k·Δf` with `Δf = 312.5 kHz` (`dsp.py:40`), so that
one delayed path contributes

```
Δphase(k) = −2π·Δf·τ·k          →  a pure slope of  −2π·Δf·τ  rad/subcarrier
```

which is *the same functional form* as SFO. **In a single frame the two are
mathematically indistinguishable.** No robust fit, no residual gate and no
inlier threshold can separate them, because the contaminant is not an outlier
— it is a perfect inlier.

**The scale of the problem, derived before looking at anything.** The repo's
standing yardstick for between-unit identity separation is
`BETWEEN_UNIT_SD = 0.00237 rad/sc` (`pc/exp_thermal_evidence.py:129`, from
`docs/LOT_HYPOTHESIS.md` §5), and the documented clock-twin separation is
`ΔSFO = 0.00080 rad/sc` (`CLAUDE.md`). Inverting the expression above:

| slope shift | equivalent change in effective path delay |
|---|---|
| `0.00080` rad/sc (the clock-twin separation) | **0.41 ns** = 12 cm of excess path |
| `0.00237` rad/sc (`BETWEEN_UNIT_SD`) | **1.21 ns** = 36 cm of excess path |
| `0.0196` rad/sc | 10 ns |
| `0.196` rad/sc | 100 ns |

**A 36 cm change in the length of one reflected path moves the slope by a full
between-unit standard deviation.** That is a room, not a crystal. This is the
reason the test exists, and it is arithmetic, not a result.

**The readout that makes the test possible.** The same delay τ also imposes
amplitude ripple on the channel with period `1/τ` in frequency, because the
direct and delayed paths alternately add and cancel across the band. The
*amplitude* spectrum therefore carries an independent readout of the delay
that is contaminating the *phase* slope. Amplitude and phase of the same
frames have never been used against each other in this repo — `pc/rff/`
(phase) and `pc/occ/` (amplitude) are separate pipelines and `CLAUDE.md`
forbids fusing their *numbers*. **This test fuses no numbers from either
pipeline.** It computes a new amplitude statistic and correlates it with a
`pc/rff/dsp.py` slope, which is new analysis, not a cross-citation.

### 0.1 The band's resolution limit — frozen as a scope limit, not discovered later

The usable band is `k = −26..−1, 1..26` (`dsp.py:37`), spanning 52·Δf =
**16.25 MHz**. A delay τ produces `16.25e6·τ` ripple cycles across it.

| | τ | why |
|---|---|---|
| one full ripple cycle across the band | **61.5 ns** | `1/(16.25 MHz)` |
| two cycles — a realistic floor for FFT detection | **123 ns** | |
| Nyquist across subcarrier index (period = 2 subcarriers) | **1.6 µs** | `1/(2·Δf)` |

**So the flatness statistic is only sensitive to τ in roughly [60 ns, 1.6 µs].**
Typical indoor RMS delay spread is tens of ns, i.e. *below* this window. And
the delays this test is least able to see are precisely the ones that
contaminate the slope most cleanly: a delay short enough to produce under one
ripple cycle across 16.25 MHz produces a near-perfectly linear phase ramp and
a nearly flat amplitude spectrum.

**Frozen consequence: a null on the primary test does not refute channel
contamination. It refutes it only for delays large enough to ripple the band.**
This is written here, before the result, so that a null cannot later be talked
up into a clean acquittal of the slope.

---

## 1. Hypotheses

**PRIMARY (H1).** IF the slope is channel-contaminated, THEN frames with
flatter amplitude spectra yield more stable slopes than frames with deep
spectral ripple, BECAUSE ripple depth indexes the delay spread leaking into
the fit.

Operational direction: **spectral flatness up ⇒ slope dispersion down**, i.e.
a **negative** correlation.

**H0.** Ripple depth carries no information about slope stability once
received power is controlled: the slope's instability is crystal noise and
receiver noise, and the channel term is either negligible or is already
absorbed by RANSAC.

**SECONDARY (H2, stretch).** For a dominant two-path channel the ripple
*period* gives τ, and that same τ predicts a slope offset of `−2π·Δf·τ`. If
the contamination is real and two-path-dominated, the observed per-frame slope
deviation should match that prediction **in magnitude**, not merely correlate
with it.

### 1.1 Two mechanisms this test cannot separate — stated now

If H1 is supported, the support is consistent with either of:

- **(a) delay leaks into the fit** — the intended mechanism; a varying
  composite delay moves the linear phase ramp frame to frame;
- **(b) spectral nulls starve subcarriers** — deep ripple means some
  subcarriers sit in a fade, their phase is noise-dominated, and the fit
  degrades.

Both are channel contamination and both falsify "the slope is a clock
property". Neither is an SNR artefact in the RSSI sense, because RSSI is
*total* power across the band and is held fixed by the strata (§3). The test
is not designed to separate (a) from (b) and will not claim to.

---

## 2. Statistics

**Amplitude per usable subcarrier.** From `csi_data`, parsed with a real CSV
reader (it is a quoted comma-separated list nested in the CSV). The buffer is
**imag,real interleaved**: `iq[1::2] + 1j*iq[0::2]`, exactly `csi_to_complex`
(`dsp.py:43-52`). The same 52-bin usable mask as `dsp.py:33-38`, DC and guards
excluded. `|H(k)|` is the magnitude, `P(k) = |H(k)|²` the power.

**Ripple statistic — spectral flatness (SF).**

```
SF = geometric_mean(P) / arithmetic_mean(P) = exp(mean(ln P)) / mean(P)
```

Chosen because it is (i) **bounded on (0,1]** with 1 = perfectly flat, so it
needs no scale normalisation and cannot be inflated by a single outlier bin;
(ii) **scale-free** — multiplying every subcarrier by a constant leaves SF
unchanged, which is exactly the property required when the confound under
control is total received power; (iii) **standard** (Wiener entropy), so it
has no tuning parameter for this pass to choose after seeing the data. A
frame with any exactly-zero usable bin has SF = 0 by definition; such frames
are counted and excluded rather than floored, and the count is reported.

**Robustness metric (second, pre-committed).** `ripple_db = std(20·log10|H(k)|)`
over the usable bins. Different functional form (spread of the log vs. gap
between mean-of-log and log-of-mean), same intent, unbounded. Expected to
correlate strongly with SF; if the two disagree on the sign of the primary
result, the result is reported as unstable and is not claimed.

**Slope.** `FrameEstimator.feed()` from `pc/rff/dsp.py`, **unmodified**
(`docs/V2_SPEC.md` §5.5), one fresh instance per (node, source-MAC) stream,
fed every screened frame of that stream **from the first row of the file**,
in file order, with no window, filter or subsample ahead of it — because the
RANSAC RNG is per-instance and advances once per fitted frame (`dsp.py:118`,
`:132`, `:85-86`), so a slope depends on how many frames preceded it.

**Stability.** Frames are grouped into windows of **W = 64 consecutive
accepted frames from one (node, MAC) stream** — accepted meaning it passes the
shipped gates `inlier_ratio ≥ 0.6` and `resid_std ≤ 0.8` (`dsp.py:164`).

```
slope_mad = 1.4826 × median(|slope − median(slope)|)   over the W frames
```

MAD rather than sd because a single RANSAC failure would otherwise dominate.

**Why W = 64, and why a duration cap.** The three beacons deliver on the order
of 60 frames/s per stream on these files (`docs/COLOCATED_0823.md` §2:
1.48M–0.85M frames over 24,123 s), so W = 64 spans **about one second**.
Crystal drift on this hardware is a thermal, minutes-scale process
(`docs/THERMAL_EVIDENCE.md`), so a one-second window cannot let drift
masquerade as instability — which is the failure the brief names. Slow ambient
sources would otherwise get windows spanning minutes, so **any window spanning
more than 5.0 s of `pc_time_us` is excluded from the primary** and the count is
reported. Robustness: the whole analysis is repeated at **W = 256** (≈4 s).

**Per-window predictors:** median SF, median `ripple_db`, mean RSSI, median
`resid_std`, span in seconds, n frames.

**Correlation.** **Spearman ρ** throughout — monotone, insensitive to the
heavy right tail of `slope_mad`, and it does not assume the linear-in-what
functional form that is itself under test. **p-values are not reported as
evidence.** n is in the millions of frames and the low tens of thousands of
windows; everything will be "significant" and significance carries no
information here.

---

## 3. The confound that would fake this result, and its controls

**Low SNR independently roughens the amplitude spectrum *and* noisens the
phase.** That alone produces the predicted negative correlation with no
multipath involved. Three controls, in increasing order of how much they
decide the question:

1. **Partial Spearman controlling RSSI** (rank-residualise both variables on
   window-mean RSSI, then correlate). Reported, but partialling assumes a
   monotone relation is fully removed by rank-residualising, which is an
   assumption.
2. **Within narrow RSSI strata — this is the test that decides it.** Windows
   are binned by mean RSSI into **1 dB bands**, and ρ is computed *inside each
   band*. Within a 1 dB band the received power is effectively constant, so a
   relationship that survives there is not an SNR artefact. **The pooled
   number is decoration; the strata number is the result.**
3. **Beyond `resid_std`.** `dsp.py:103` already computes the fit residual
   spread, which plausibly captures some of the same thing. Reported as a
   partial Spearman controlling RSSI **and** window-median `resid_std`
   jointly. If ripple adds nothing beyond `resid_std`, the honest reading is
   that the pipeline already had this information and the flatness statistic
   is redundant, not that the channel is innocent.

`ripple_db` is *not* scale-free the way SF is, which is precisely why SF is
primary: SF cannot mechanically track RSSI.

---

## 4. Minimum effect sizes — frozen. Anything smaller is a NULL.

n is in the millions. A tiny-but-significant result is a null for our purposes
and will be reported as one.

**E1 — PRIMARY, decides the test. Within-RSSI-stratum Spearman.**
Over strata holding ≥ 200 windows, on each of the three beacons on each
receiver:

- the **median across qualifying strata of ρ(SF, slope_mad)** must be
  **≤ −0.20**, and
- **≥ 70 % of qualifying strata** must show **ρ ≤ −0.10**, and
- the sign must hold on **both receivers**.

`|ρ| = 0.20` is ~4 % of rank variance. Below that, "the channel measurably
destabilises the identity slope" is not a statement this data supports at any
n, and the correct report is a null.

**E2 — PRACTICAL, within stratum.** median `slope_mad` of the **lowest-SF
quintile** ÷ median `slope_mad` of the **highest-SF quintile** must be
**≥ 1.5×**, pooled over qualifying strata.

**E3 — INCREMENTAL over `resid_std`.** partial ρ(SF, slope_mad | RSSI,
resid_std) must be **≤ −0.10**. If |ρ| < 0.10 here, the finding is reported as
"already captured by `resid_std`", whatever E1 says.

**E4 — ROBUSTNESS.** `ripple_db` must give the same sign as SF (its predicted
sign is **positive**: more ripple ⇒ more dispersion), and W = 256 must give
the same sign as W = 64. A sign flip on either voids the claim.

**E5 — SECONDARY / H2, quantitative.** Counted as tractable only if a τ̂ is
extractable on ≥ 20 % of frames of a stream. Then the match is judged by
regressing observed per-frame slope deviation on the predicted `−2π·Δf·τ̂`:

- **quantitative match** = fitted coefficient in **[0.5, 2.0]** (within a
  factor of two of unity) **and** ρ ≥ 0.3;
- **correlation only** = ρ ≥ 0.3 with the coefficient outside that range;
- **null** = ρ < 0.3.

A quantitative match is much stronger evidence than a correlation, because it
has a specific predicted magnitude and cannot easily arise by accident. If τ̂
is not extractable on enough frames — which §0.1 says is a live possibility on
physical grounds, not merely practical ones — **that will be stated as "not
tractable", not quietly dropped.**

**VOID conditions.** The test reports itself void, rather than reporting a
result, if: fewer than 5 RSSI strata qualify on a stream; or the SF
distribution within a stratum is so narrow that the top and bottom quintiles
overlap in SF; or `pc/rff/dsp.py` is modified; or any stream is fed anything
other than its file from row 1.

---

## 5. What each outcome means — decided in advance

| outcome | reading |
|---|---|
| E1 **and** E3 met, E4 consistent | **The channel hypothesis survives its first direct test.** The slope carries a room term the estimator cannot reject, over and above what `resid_std` already flags. Identity claims resting on the slope need a multipath control. |
| E1 met, E3 **not** met | Real relationship, but `resid_std` already had it. Not a new finding; a re-description of an existing gate. |
| E1 not met | **Null for resolvable delays.** Per §0.1 this does not acquit the slope — sub-60 ns delays are invisible to this statistic and contaminate the slope most linearly. A different instrument (wider band, or a deliberate path-length manipulation) is required. |
| ρ **positive** (rougher ⇒ *more* stable) | Report as-is and do not rationalise. Would indicate the flatness statistic is tracking something other than delay spread. |

**Failure modes this pass is exposed to, from `CLAUDE.md`.** **A** — every
number below must be re-derivable by a named command. **C** — an empty result
must say whether the data does not exist, was not asked for, or could not be
asked for. **E** — an anomaly is not assumed to be a defect until the record
that triggered it has been opened. **F** — the finished document gets read in
the form the recipient sees it.

---

## 6. Data and constraints

**Files.** `data/raw/d0wd_20260823_014740.csv` and
`data/raw/s3_20260823_014740.csv`. **Discrepancy against the brief, stated
not explained away:** the brief names `*_20260823_014741*`; no such file
exists. The only 2026-08-23 pairs on disk are `014740` (the 6.70 h overnight,
2,866,404,334 and 3,596,309,377 bytes) and `013537` (a separate 317 s run
twelve minutes earlier, per `docs/COLOCATED_0823.md` §0). The `014740` pair is
used, on the assumption that the brief means the overnight capture whose first
`pc_time_us` is 01:47:41 — the second, not the filename, is what reads 41.
The `013537` pair is not fused with it.

**Sources.** The three beacons (`pc/occ/__init__.py`): B1
`a4:f0:0f:77:91:20` (reference), B2 `28:05:a5:2f:fa:48`, B3
`f4:2d:c9:70:72:30`. Ambient sources clearing the floor are analysed and
**reported separately**, never pooled with the beacons. Floor for this test:
≥ 640 accepted frames, i.e. ≥ 10 windows at W = 64.

**Corrupt-row screen, before the estimator and before any delta arithmetic**
— the d0wd fabricates MACs from corrupt rows (126 of them on this file,
`docs/COLOCATED_0823.md` §2). Field plausibility on six columns: `node_id`
against the file's own mode, `env_id == 0`, `channel` against the file's own
mode, `csi_len ∈ {128, 256, 384}`, `noise_floor ∈ [−110, −70]`,
`rssi ∈ [−100, −10]`.

**Constraints obeyed.** No sub-agents. No `git add` / commit / push / staging.
`pc/rff/dsp.py` not modified — computing an amplitude is new analysis, not an
estimator change. `pc/capture.py:compute_cfo`, `pc/phase_skew.py` and
`pc/fingerprint.py` not used (`docs/CODE_INVENTORY.md` §4.2 C1/C2/C3: all
three have the DC/guard-band index wrong). No serial port opened; `data/raw/`
opened read-only and never written. One script, `pc/exp_ripple_test.py`. Host
caps shell calls near 178 s, so the script checkpoints its estimator state and
byte offset and resumes; scratch lives outside the repo tree and is removed.

---

# RESULTS

*(Everything above this rule was written and saved before the first slope or
amplitude statistic was computed. Nothing above it has been edited since.
Results follow. Two predictions were disagreed with and both are reported as
disagreements, not revised: §0.1's resolution limit turned out to be the
binding constraint on the whole test, and E5's instrument turned out not to
work at all.)*

## 7. What was run

One script, `pc/exp_ripple_test.py`, from the repo root:

```
export RIPPLE_CACHE=/tmp/ripple
python3 pc/exp_ripple_test.py verify data/raw/d0wd_20260823_013537.csv --split-budget 1.2
python3 pc/exp_ripple_test.py run data/raw/d0wd_20260823_014740.csv --tag d0wd   # x4
python3 pc/exp_ripple_test.py run data/raw/s3_20260823_014740.csv   --tag s3     # x5
python3 pc/exp_ripple_test.py report --tags d0wd,s3
python3 pc/exp_ripple_test.py checks --tags d0wd,s3
python3 pc/exp_ripple_test.py checks --tags d0wd --power-mode block \
        --spreads 30,40,50,60,80,120
```

**Both files were read end to end.** Final byte offsets equal the file sizes
exactly (2,866,404,334 and 3,596,309,377) and the row counts are
**3,344,351** and **4,330,849** — matching `docs/COLOCATED_0823.md` §0 to the
unit. The field-plausibility screen removed **187** rows on the d0wd and **1**
on the S3, matching that document's independent `awk` (`screened=187`,
`screened=1`) exactly. 0 unparseable rows, 0 short-CSI rows on either file.
Read-only throughout: both CSVs opened `"rb"`, never written; no serial port
opened; nothing staged or committed (`git diff --cached --name-only` empty,
before and after). `ls -l --time-style=full-iso` reports both raw files
unchanged at `2026-08-23 08:29:44` after the pass. `pc/rff/dsp.py` was **not
modified** — mtime still `2026-07-13 20:42:46`. All state went to
`$RIPPLE_CACHE = /tmp/ripple`, outside the repo tree, and was deleted.

**Two files in the repo were written by this pass: this one and
`pc/exp_ripple_test.py`.** One disclosed exception, identical to the one
`docs/COLOCATED_0823.md` §0 records:
`pc/__pycache__/exp_ripple_test.cpython-310.pyc` was produced when a
verification helper imported the module rather than running it, and **this
pass could not delete it** — `rm` on this mount returns `Operation not
permitted`. It is covered by `.gitignore` (`__pycache__/`) and matches the
`.pyc` already present for every other `pc/exp_*.py`.

**Disclosed for completeness:** before the overnight runs, the script's
`report` path was exercised once on the short `d0wd_20260823_013537.csv` file
to check it executed. That file produced 0 qualifying strata and so could not
have previewed any result, the pre-registration above was already written and
saved at that point, and nothing above the RESULTS rule was changed
afterwards. The 013537 figures are not fused with anything below.

**The checkpoint split was proved transparent, not asserted.** `verify` ran
the 013537 d0wd file as one uninterrupted pass and again as 5 resumed parts
and compared every window record of every stream: row counts and stream sets
identical, **0 streams with any differing window**. The `docs/V2_SPEC.md`
§5.5 replay-origin requirement therefore holds for the 9-part overnight runs.

**Scale.** 6,723,212 accepted beacon frames; 102,452 W=64 windows inside 37
qualifying 1 dB RSSI strata. As pre-registered, **no p-value is reported.**

## 8. Pooled result — the decoration, and why it was labelled that

| stream | pooled ρ(SF, slope_mad) | strata median ρ |
|---|---|---|
| d0wd / B3 | −0.187 | −0.070 |
| d0wd / B1 | **−0.537** | −0.201 |
| d0wd / B2 | −0.279 | *(void, 4 strata)* |
| s3 / B2 | −0.171 | −0.135 |
| s3 / B3 | **−0.505** | −0.255 |
| s3 / B1 | **−0.034** | −0.132 |

The pooled number ranges from −0.034 to −0.537 across six streams of the same
three transmitters heard by two receivers ten inches apart. **Roughly half of
every large pooled value is the RSSI confound**: B1 on the d0wd falls
−0.537 → −0.201 and B3 on the S3 falls −0.505 → −0.255 once the comparison is
made inside a 1 dB band. The pre-registration called the pooled figure
decoration before seeing it; it was right to.

## 9. Within-RSSI-strata — the result

37 strata qualified (≥ 200 windows each), spanning 102,452 windows.

- **34 of 37 carry the predicted negative sign**; 3 are positive.
- median ρ across all 37 = **−0.173**, range **−0.360 … +0.213**.
- **16 of 37** reach ρ ≤ −0.20.

Per beacon, against the frozen E1:

| stream | strata median ρ | frac(ρ ≤ −0.10) | MAD ratio (low-SF ÷ high-SF) | partial ρ \| RSSI, resid_std |
|---|---|---|---|---|
| d0wd / B3 | −0.070 | 0.43 | 1.025 | −0.239 |
| d0wd / B1 | −0.201 | 1.00 | 1.103 | −0.213 |
| s3 / B2 | −0.135 | 0.67 | 1.064 | −0.150 |
| s3 / B3 | −0.255 | 0.89 | 1.173 | −0.296 |
| s3 / B1 | −0.132 | 0.60 | 1.055 | +0.062 |

**E1 — NOT MET.** The median stratum ρ reaches −0.20 on 2 of 5 beacon
streams; the ≥ 70 % criterion is met on 2 of 5. Both were required on every
stream.

**E2 — NOT MET, and not close.** Median MAD ratio **1.099**; the largest of
any of the 37 strata is **1.300**; **zero of 37** reach the frozen 1.5.
Plainly: inside a 1 dB RSSI band, the windows with the deepest spectral
ripple have slopes about **10 % more dispersed** than the flattest windows.
Real, consistent in sign, and small.

**E3 — NOT MET by the frozen all-streams rule, though 4 of 5 pass.** Partial
ρ(SF, slope_mad | RSSI, resid_std) is −0.239, −0.213, −0.150 and −0.296 on
four streams, and **+0.062** on s3/B1. So on most streams ripple does carry
information `resid_std` does not — ρ(SF, resid_std) is itself unstable in sign
across streams (+0.201, −0.538, +0.032, +0.013, −0.464, −0.460), i.e. the two
statistics are not redundant — but the criterion required all five.

**E4 — sign robustness HOLDS.** `ripple_db` gives the predicted **positive**
sign on every stream (strata medians +0.053, +0.191, +0.128, +0.228, +0.128),
and W = 256 gives the predicted negative sign on every stream (strata medians
−0.032, −0.252, −0.157, −0.412, −0.107). No sign flip. The small effect is
not an artefact of one metric or one window length.

**The small effect is not residual SNR inside the stratum, and is not a
machine artefact.** Two controls from `checks`:

- removing the residual continuous within-stratum RSSI barely moves it, on
  all six beacon streams (the void d0wd/B2 included, since this control does
  not apply the 5-strata minimum): −0.201 → −0.161 (d0wd/B1), −0.108 →
  −0.117 (d0wd/B2), −0.070 → −0.084 (d0wd/B3), −0.132 → −0.100 (s3/B1),
  −0.135 → −0.117 (s3/B2), −0.255 → −0.238 (s3/B3);
- a shuffle placebo (SF permuted within stratum) returns strata medians of
  +0.006, −0.020, −0.007, −0.018, −0.005, −0.004 — the machinery does not
  manufacture correlation at this n.

**So: a real, SNR-independent, sign-consistent relationship exists, and it is
far below the size pre-registered as meaningful. By the frozen rule that is a
NULL, and it is reported as one.**

## 10. Secondary quantitative test — the instrument does not work

E5 asked for a match in magnitude. The numbers, at face value:

| stream | τ̂ detected | median τ̂ | ρ(pred, \|dev\|) | fitted coefficient |
|---|---|---|---|---|
| s3 / B2 | 98.59 % | 125.0 ns | +0.199 | 0.0018 |
| s3 / B3 | 97.59 % | 156.2 ns | −0.021 | 0.0005 |
| s3 / B1 | 96.51 % | 125.0 ns | +0.113 | 0.0008 |
| d0wd / B2 | 49.30 % | 125.0 ns | −0.303 | −0.0097 |
| d0wd / B1 | 37.18 % | 468.8 ns | +0.020 | 0.0009 |
| d0wd / B3 | 9.94 % — below the 20 % floor | — | (−0.108) | — |

Every ρ is below the frozen +0.30 and every coefficient is **three orders of
magnitude** below the frozen [0.5, 2.0]. On the frozen criteria: **null.**

**But the null carries no physical information, because the input is not a
delay estimate.** Failure mode **E** (`CLAUDE.md`) says open the record before
blaming the mechanism, so the estimator was calibrated against pure noise:
`_synth_tau_null` runs the identical FFT-argmax-and-prominence logic on 20,000
white-Gaussian log-amplitude spectra and the detector fires **94.84 % of the
time**, at a median τ̂ of 862.5 ns. A "detection rate" of 96–99 % on the S3
beacons is therefore **indistinguishable from what noise produces**, and the
near-quantised medians (125.0 ns = FFT bin 20, 468.8 ns = bin 75) are argmax
grid artefacts, not physics.

**E5 is reported as NOT TRACTABLE, not as evidence.** A dominant two-path
channel that resolves in 16.25 MHz was not measurable in this data with this
estimator, exactly as §0.1 warned was likely on physical grounds. What would
be required is a wider band or a deliberate path-length manipulation, not a
better peak-picker.

## 11. Power calibration — the finding that decides how to read the null

A null is worthless without knowing what the test could have seen. `checks`
step 4 injects a **known** second path into **real** screened frames —
`H'(k) = H(k)·(1 + 0.5·exp(−j2π·k·Δf·τ))`, re-quantised to the int8 grid so
the synthetic frame is no cleaner than a real one — then runs the identical
unmodified `FrameEstimator` and the identical statistics.

Two injection regimes, 18,000 frames of B2 on `d0wd_20260823_013537.csv`:

**(a) τ redrawn i.i.d. per frame.** Slope dispersion triples
(`slope_mad` median 3.19e−3 → 1.02e−2 at 60 ns) — **the channel-to-slope link
itself is confirmed, exactly as §0 predicts** — but ρ goes *positive*
(−0.116 → +0.189) and the MAD ratio never leaves 1.0. Every window receives
the same τ mixture, so within-window averaging destroys the between-window
contrast the hypothesis compares. **The test has no power in this regime at
all.**

**(b) delay spread redrawn per 64-frame block** — the realistic case, and the
one the hypothesis actually describes:

| injected delay spread | ρ(SF, slope_mad) | MAD ratio | slope_mad median |
|---|---|---|---|
| 0 ns (control, real channel only) | −0.116 | 1.002 | 3.19e−3 |
| 5 ns | −0.065 | 1.057 | 3.23e−3 |
| **20 ns** | **−0.092** | **1.111** | 4.08e−3 |
| 30 ns | −0.159 | 1.087 | 4.96e−3 |
| 40 ns | −0.223 | 1.225 | 6.05e−3 |
| 50 ns | −0.311 | **1.493** | 6.92e−3 |
| **60 ns** | **−0.406** | **1.666** | 7.87e−3 |
| 80 ns | −0.369 | 1.390 | 8.80e−3 |
| 120 ns | −0.349 | 1.412 | 8.92e−3 |

**The test crosses E1 (ρ ≤ −0.20) between 30 and 40 ns and E2 (ratio ≥ 1.5)
between 50 and 60 ns.** §0.1 predicted, from the band alone and before any
data, that one ripple cycle across 16.25 MHz requires **61.5 ns**. The
measured detection floor lands on that number. The frozen scope limit was
correct.

**And the real data sits where ~20–30 ns of injected delay spread puts it.**
Real strata medians are ρ = −0.070 … −0.255 with ratios 1.03–1.17; injected
20–30 ns gives ρ = −0.092 … −0.159 with ratios 1.09–1.11. The observed null is
quantitatively the signature of a delay spread in the low tens of
nanoseconds — the ordinary indoor value — seen by an instrument whose floor is
around 50 ns.

## 12. Ambient sources, reported separately

Never pooled with the beacons. Four cleared the 640-accepted-frame floor and
none produced a single qualifying stratum, so **none of them can test
anything** — they are reported for completeness only.

| stream | accepted | windows kept | pooled ρ | note |
|---|---|---|---|---|
| d0wd `7e:ed:82:d6:23:e8` | 1,202 | 16 | −0.476 | 0 strata — void |
| d0wd `62:45:b4:f0:e1:97` | 689 | 5 | nan | SF IQR is 0.0004 wide; degenerate |
| s3 `7e:ed:82:d6:23:e8` | 2,952 | 43 | −0.603 | 0 strata — void |
| s3 `62:45:b4:f0:e1:97` | 2,693 | 35 | −0.028 | RSSI −29 dBm, near-flat spectrum |
| d0wd `32:c8:46:83:87:d0` | 776 | **0** | — | 64 frames span a median 18.0 s |
| s3 `ba:80:d5:0c:18:87` | 1,354 | **0** | — | 64 frames span a median 34.9 s |

The last two are the pre-registered duration cap doing its job: a source that
slow cannot form a window short enough to exclude drift, so it was excluded
and **counted**, per failure mode **C** — this is "could not be asked", not
"no data".

**One beacon stream was also void:** d0wd/B2 accepted only 20.2 % of its
1,014,678 frames (against 92.7–99.7 % everywhere else) and produced just 4
qualifying strata, one short of the frozen minimum of 5. Its low acceptance
rate is not explained by this pass and was not investigated.

## 13. Verdict, against §5's table

**The channel hypothesis did not survive its first direct test as stated — and
it was not refuted either. The test returned a null that its own power
calibration places below the instrument's detection floor.**

Precisely what is and is not established:

1. **E1, E2 and E3 all NOT MET.** The pre-registered claim "frames with
   flatter amplitude spectra yield materially more stable slopes" is **not
   supported at the frozen effect size**, in the only comparison that decides
   it — inside a 1 dB RSSI band.
2. **A small, real, SNR-independent effect of the predicted sign does exist**
   (34/37 strata negative, median ρ −0.173, ~10 % dispersion difference),
   survives a residual-RSSI control and a shuffle placebo, and holds sign
   under both a second ripple metric and a 4× longer window. It is a fifth of
   the size that was pre-registered as meaningful, so per §4 it is a **null**.
3. **The null is bounded, not general.** Injection shows the test detects
   varying delay spread above ~40–60 ns and does not below it — matching
   §0.1's 61.5 ns prediction made before the data. The correct statement is
   therefore: *no evidence of frame-to-frame varying multipath with delay
   spread above roughly 50 ns.* Below that, this instrument is blind, and §0's
   arithmetic says **1.21 ns of delay change is already a full
   `BETWEEN_UNIT_SD` of slope**. The regime that matters for identity is
   entirely inside the blind spot.
4. **The channel-to-slope link is nonetheless demonstrated**, by injection
   rather than by correlation: a varying second path triples the slope
   dispersion of real frames through the unmodified estimator. What failed is
   the *amplitude readout* of that delay at short τ, not the physics of §0.
5. **The largest limitation, and it is structural.** This test measures
   **dispersion**, so a *static* multipath delay — which shifts the slope by a
   constant — is invisible to it **by construction**. That is exactly the
   route from geometry to slope that matters most for the receiver term in
   `docs/SEPARATION_SCALING.md` §0 / `docs/REFERENCE_CHOICE.md` §0 and for the
   cross-receiver generalization gap `CLAUDE.md` records. **Nothing in this
   document speaks to it.** A test of that needs a deliberate path-length
   manipulation with the transmitter held fixed, not an observational pass.

**Nothing here changes any published figure**, and no number in this document
may be fused with the device-ID or occupancy pipelines' numbers.
