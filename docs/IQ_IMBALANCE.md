# IQ_IMBALANCE — is transmitter IQ imbalance extractable from existing CSI, and is it more stable than the SFO slope?

**Stage 1 (everything above the `STAGE 2` banner) was written and saved
before any statistic in this document was computed.** The only things run
before it was written were: `head`/`awk` row and MAC counts on the two input
files (§0), and reading `pc/rff/dsp.py`, `docs/IDENTITY_STABILITY.md`,
`docs/RECEIVER_TERM_PREREG.md`, `docs/NODE_CENSUS.md` and `PROJECT_NOTES.md`.
No estimator was written and no feature value existed.

**Stage 1 is frozen.** If a Stage-1 statement turns out to be wrong it is
corrected *below* the banner with the original left standing, not rewritten.
Temptations to revise are recorded in §14 rather than acted on.

---

## 0. Why this question, and what would make it worth answering

`docs/IDENTITY_STABILITY.md` §13 established that the per-device residual
drift in the SFO slope is **2.2× to 7.1× the entire between-device spread**
(`BETWEEN_UNIT_SD = 0.00237` rad/sc), on every receiver block with three
devices, and §12 showed the same wander happens *inside* a single session on
a timescale of tens of minutes. A feature that moves by multiples of the
whole between-device spread cannot carry identity, and no amount of
classifier work fixes it.

**Adding a second feature only helps if the new one is more stable, not
merely different.** A second unstable dimension is a second way to be wrong.
So the load-bearing test in this document is **§2 stability**, not §1
separation. Separation is the positive control: if the beacons do not
separate on the feature at all, there is nothing to test for stability. If
they separate but drift as badly as the slope, the branch closes.

IQ imbalance is the candidate because it is **analog silicon, not a timing
quantity**. A gain or phase mismatch between the I and Q paths of a
direct-conversion transceiver is set by component tolerances on the die and
the board. It drifts with temperature, slowly, and — unlike a phase slope —
it has no reason to care where the antenna is or what the room is doing.

### 0.1 The capture

| | `data/raw/d0wd_20260823_014740.csv` | `data/raw/s3_20260823_014740.csv` |
|---|---|---|
| `node_id` | 68 | 108 |
| data rows | 3,344,351 | 4,330,849 |
| span | 01:47:41 → 08:29:44 local, 24,123.12 s = **6.7009 h** | same |

These are the two receivers of `docs/COLOCATED_0823.md`, ~10 inches apart on
the same wall, and **this is the same 6.70 h session in which
`docs/IDENTITY_STABILITY.md` measured the slope falling apart.** Using the
same session is the point: it removes "different data" as an explanation for
any difference in stability between the two features.

The shorter `013537` pair from the same night is **not used** — not as input,
not as corroboration.

### 0.2 Constraints held

Read-only on `data/raw/`; every input opened `"rb"`. No serial port is
opened (a capture is live on COM6 and COM12). `pc/rff/dsp.py` is **not
modified** — it is read, and `csi_to_complex`'s interleave convention is
checked against it byte for byte (§1.1). `pc/capture.py:compute_cfo`,
`pc/phase_skew.py` and `pc/fingerprint.py` are **not used**
(`docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 — all three have the DC/guard-band
index wrong). One script is written: `pc/exp_iq_imbalance.py`. Nothing is
staged, committed or pushed. No sub-agents. Scratch goes to `$IQ_CACHE`
outside the repo tree.

---

## 1. The physics, and the estimator built from it

### 1.1 The interleave convention, checked not assumed

`pc/rff/dsp.py:43-52` defines

```
iq = v[: N_CPLX * 2]
return iq[1::2] + 1j * iq[0::2]
```

i.e. the CSI buffer is **imag,real** interleaved and the complex value is
`real + j·imag` = `iq[1::2] + 1j*iq[0::2]`. **Getting this backwards
conjugates every subcarrier, which turns the conjugate relationship this
document is looking for into the non-conjugate one and vice versa.** This
pass uses `dsp.py`'s own `csi_to_complex`, imported unmodified, so the
convention cannot drift from it. §10 records a byte-level re-check that the
imported function is the one on disk.

Physical subcarrier mapping is also `dsp.py`'s: `_K_OF_IDX`, `_USABLE_MASK`,
`K_USABLE` = −26..−1, 1..26; DC and guards excluded (`dsp.py:33-38`).

### 1.2 What imbalance does, and what multipath cannot do

A direct-conversion transceiver whose I and Q paths differ in gain or phase
applies, in the time domain, `x(t) → α·x(t) + β·x*(t)`. In the frequency
domain that is **conjugate image leakage between mirrored subcarriers**:

> `X(k) → α·X(k) + β·X*(−k)`

**A multipath channel cannot produce this.** Multipath is linear and
time-invariant: it multiplies each subcarrier by its own complex gain `H(k)`
and never couples `k` to `−k`. That asymmetry is the whole reason the feature
is worth testing, and it is also the reason the estimator must be built to
respond to the *conjugate* relation and not to the plain mirror relation.

### 1.3 The consequence of a real-valued training sequence — stated up front

The ESP32 CSI is a channel estimate derived from the L-LTF, which is a
**known real-valued ±1 sequence** `L(k)` on k = −26..26 (IEEE 802.11-2020
§17.3.3). Carrying the imbalance model through a preamble-based channel
estimate gives, with `ε_t = β_t/α_t` (transmitter) and `ε_r = β_r/α_r`
(receiver), both small:

- transmitted spectrum `T(k) = α_t L(k) + β_t L(−k)`
- through the channel: `Y(k) = H(k) T(k)`
- receiver imbalance: `R(k) = α_r Y(k) + β_r Y*(−k)`
- channel estimate `Ĥ(k) = R(k)/L(k)`

which expands, to first order in ε, to

> **`Ĥ(k) ≈ α_rα_t · { H(k)·(1 + ε_t·s(k)) + ε_r·s(k)·H*(−k) }`**,
> where **`s(k) = L(−k)/L(k) = L(k)·L(−k) ∈ {±1}`**, an even function of k.

**This is a Stage-1 prediction with a consequence that cuts against the
premise of the investigation, and it is written here before any data is
touched:**

- **The conjugate term `H*(−k)` carries the RECEIVER imbalance `ε_r`, not the
  transmitter's.** The transmitter's image lands on the training sequence's
  own image — which is the same known real sequence — and is therefore
  absorbed into the direct term.
- **The transmitter imbalance `ε_t` appears instead as an `s(k)`-patterned
  ripple riding on the channel estimate itself.**

Both are analog-silicon quantities and both are estimated below. But it means
**§3 (TX/RX decomposition) is not a hygiene check appended to this pass — it
is the pass.** If the derivation above is right, the conjugate coefficient is
receiver silicon by construction and the answer to "how much of the measured
imbalance is receiver rather than transmitter" is "nearly all of it", with
the transmitter's contribution living in a different statistic.

**If the derivation is wrong, §3 will say so**: `κ` (defined below) would then
vary across transmitters at a fixed receiver by more than it varies across
receivers for a fixed transmitter, and §3's dispersion test measures exactly
that. Either outcome is reported; neither is chosen after the fact.

### 1.4 Step 0 — which convention the ESP32 buffer is in, decided by a test

It is **not established anywhere in this repo** whether the ESP32's LLTF CSI
buffer is the raw received training symbol (`∝ L(k)·H(k)·…`) or a channel
estimate already divided by `L(k)`. `s(k)` is a ±1 demodulation, so the two
hypotheses differ by a known ±1 pattern and getting it wrong costs the
matched filter its gain.

**Decision rule, frozen.** Let `V₀(k) = Ĥ_buf(k)` and `V₁(k) = Ĥ_buf(k)·L(k)`.
For each, compute the mean over frames of the normalised roughness

  `ROUGH(V) = Σ |V(k+1) − V(k)|² / Σ |V(k)|²`,

summed over adjacent k **within** each contiguous block (−26..−1 and 1..26)
only, never across DC. A true channel estimate is smooth in k; a
±1-scrambled one is not.

- If `ROUGH(V₀) < ROUGH(V₁)/2` → the buffer is **already divided**; take
  `H_meas = V₀` and use `s(k)` from the standard sequence.
- If `ROUGH(V₁) < ROUGH(V₀)/2` → the buffer is the **raw training symbol**;
  take `H_meas = V₁`. This outcome additionally **validates the `L(k)`
  sequence used here empirically**, since a wrong `L` could not smooth it.
- Otherwise → **inconclusive**; both branches are carried through the entire
  analysis and every headline number is reported twice.

The `L(k)` sequence used is written into `pc/exp_iq_imbalance.py` as a
literal and printed by the script so it is auditable. **If the check comes
out "already divided", the correctness of `L(k)` is not independently
verifiable from this data**; that limitation is stated in §19 and the whole
analysis is additionally run with `s(k) ≡ 1` as a variant so no conclusion
rests on it alone.

### 1.5 De-rotation, and why not `dsp.py`'s RANSAC

The dominant structure in a raw CSI vector is a linear phase ramp
`e^{−j(m·k + b)}` from sampling/timing offset and common phase. A pure ramp
is *exactly* the pathological case for a conjugate statistic: `H(k) = a·e^{−jθk}`
gives `H*(−k) = a*·e^{−jθk} ∝ H(k)`, i.e. **perfect apparent conjugate
coupling produced by no imbalance at all.** It must be removed before
anything is measured.

Per frame, deterministically:

  `m_f = arg( Σ_{adjacent k, within block} H_meas(k+1)·H_meas*(k) )`
  `b_f = arg( Σ_k H_meas(k)·e^{−j m_f k} )`
  **`G_f(k) = H_meas(k) · e^{−j(m_f·k + b_f)}`**

then the flat component is removed, `G̃_f(k) = G_f(k) − mean_k G_f(k)`,
because a perfectly flat channel makes imbalance **unidentifiable in
principle** (if `H` is constant, `α·H + β·H*` is also constant and no
statistic can separate the two). That is a property of the physics, not a
shortcoming of the estimator, and it is stated here rather than discovered
later.

**Why not `FrameEstimator`/`ransac_line`.** `ransac_line` draws from a
per-instance RNG that advances once per fitted frame (`dsp.py:118,132`;
`docs/V2_SPEC.md` §5.5), so its output depends on how many frames preceded it
*in that stream*. That forbids subsampling, part-splitting and per-chunk
analysis, all of which this pass needs. The de-rotation above is
deterministic and order-independent.

**Consequence, stated now: `m_f` is NOT the shipped SFO estimator and no SFO
figure in this repo is re-derived from it.** Where `m_f` appears (§2's
comparator) it is labelled "this pass's deterministic slope" and is never
compared against `BETWEEN_UNIT_SD = 0.00237` or against any published σ.

### 1.6 The primary statistic, and the controls it is separated from

All sums run over the 52 usable k and over the admissible frames of one cell
(= one receiver × one source MAC × one 600 s time chunk).

| symbol | definition | what it responds to |
|---|---|---|
| `P` | `Σ_f Σ_k \|G̃_f(k)\|²` | power, the normaliser |
| **`A`** | `Σ_f Σ_k s(k)·G̃_f(k)·G̃_f(−k)` | **conjugate coupling, s-demodulated — PRIMARY** |
| `B` | `Σ_f Σ_k s(k)·G̃_f(k)·G̃_f*(−k)` | **non-conjugate mirror relation — CONTROL 1** |
| `A₀` | `Σ_f Σ_k G̃_f(k)·G̃_f(−k)` | conjugate, **not** demodulated — CONTROL 2 |
| `B₀` | `Σ_f Σ_k G̃_f(k)·G̃_f*(−k)` | non-conjugate, not demodulated |
| `A_j` | `A` recomputed with a random even ±1 pattern `s_j`, j = 1..64 | **the noise floor — CONTROL 3** |

and the derived features

> **`κ = A / (2P)`** — complex. `\|κ\| ≈ \|ε\|` is the image ratio;
> `IRR_dB = 20·log₁₀\|κ\|`. **This is the feature under test.**
>
> `ν = B / (2P)`, `κ₀ = A₀/(2P)`, `ν₀ = B₀/(2P)` — the controls, in the
> same units, so they are directly comparable.

**Why `A` and not `A₀` is primary, and why this is the confound control the
brief demands.** Write the model of §1.3 with the ramp removed:
`G̃(k) ≈ H̃(k)(1 + ε_t s(k)) + ε_r s(k) H̃*(−k)`. Then

  `A ≈ Σ_k s(k)H̃(k)H̃(−k) + 2ε_t Σ_k H̃(k)H̃(−k) + 2ε_r Σ_k |H̃(k)|²`

The imbalance term `2ε_r Σ|H̃|²` is the **only** term that is a coherent sum
of non-negative quantities. The two channel terms are sums of a smooth
complex sequence against a fast-alternating ±1 pattern and against itself,
and both average toward zero across k and across frames. In `A₀` the channel
term `Σ_k H̃(k)H̃(−k)` is **not** demodulated and is the dominant term — which
is precisely why `A₀` is reported as a control rather than used: it is what
this measurement looks like when the confound is left in.

`B` responds to `H̃(k)` correlating with `H̃(−k)` — the *non*-conjugate mirror
relation a flat or slowly-varying channel produces — and carries **no**
imbalance term at first order. **`κ` and `ν` are reported side by side for
every cell in this document, without exception.** If they move together, the
statistic is measuring the channel and not the silicon.

### 1.7 The injection test — the explicit demonstration that they separate

Statistics are not taken on trust. On real measured frames drawn from this
corpus, two perturbations are injected and `κ` and `ν` are recomputed:

1. **Conjugate injection.** `G(k) → G(k) + β·s(k)·G*(−k)` for
   β ∈ {0, 0.005, 0.01, 0.02, 0.05, 0.10}, real and imaginary.
   **Prediction: `κ` recovers β linearly with slope 1 ± 0.15 and correct
   phase; `ν` moves by less than 0.2 × the change in `κ`.**
2. **Non-conjugate injection.** `G(k) → G(k) + γ·G(−k)` for the same γ grid —
   a mirror-symmetric channel perturbation, the confound made concrete.
   **Prediction: `ν` recovers γ; `κ` moves by less than 0.2 × the change in
   `ν`.**

**If either prediction fails, the estimator is not separating the two
relations and no result in §§1–4 is reportable.** That is a stop condition,
not a caveat.

### 1.8 The transmitter-ripple statistic (secondary)

From §1.3, `ε_t` rides on the direct term as an `s(k)`-patterned ripple. With
`Ḡ_f` = a 5-point moving average of `G̃_f` within each contiguous block,

> **`τ = ( Σ_f Σ_k s(k)·G̃_f(k)·Ḡ_f*(k) ) / ( Σ_f Σ_k |Ḡ_f(k)|² )`** ≈ `ε_t`

with its own 64-pattern random null. `τ` is **secondary**: it is reported and
thresholded the same way as `κ`, but the brief's question is about the
conjugate term and `κ` is the answer to it. `τ` exists so that a
"conjugate term is receiver-side" finding in §3 does not leave the
transmitter question unmeasured.

### 1.9 Admissibility, defined without `dsp.py`'s gates

`dsp.py`'s gates (`min_inlier_ratio 0.6`, `max_resid 0.8`) are properties of
the RANSAC fit, which is not used here.
`docs/RECEIVER_TERM_PREREG.md` §11 records that those gates admit under 1 % of
some ambient sources' clean frames, asymmetrically between the two receivers —
a known hazard for any ambient claim. This pass therefore defines its own
frame gate, and states it:

A frame is **admissible** iff (a) `csi_data` yields ≥ 128 int8 values;
(b) every guard bin (|k| ∈ 27..31 and k = −32) is **exactly zero** — the
check `PROJECT_NOTES.md` §2 verified holds on 99.88 % of frames; (c) at most
4 of the 52 usable bins have `|H| = 0`; (d) `Σ|G̃|² > 0` and finite.

The admissible/clean ratio is reported per (receiver, source) so this gate's
severity is visible and comparable to the shipped gates' 79.8 % / 93.5 %
outliers.

### 1.10 Corrupt rows, screened before anything

Both screens `docs/COLOCATED_0823.md` §1 requires, applied before any MAC
enters a census and before any arithmetic:

1. **Field plausibility** on six columns: `node_id` vs the file's own mode,
   `env_id == 0`, `channel` vs the file's own mode, `len ∈ {128,256,384}`,
   `noise_floor ∈ [−110,−70]`, `rssi ∈ [−100,−10]`.
2. **Width-9 median filter on `dropped`**, compared circularly mod 65536.

Both are required: the d0wd **fabricates MACs from corrupt rows** — 126 of
its 166 addresses were corruption (`docs/COLOCATED_0823.md` §2) — and three
d0wd rows are invisible to the field screen and caught only by the median
filter.

**Pre-registered reproduction check:** `docs/RECEIVER_TERM_PREREG.md` §10.1
puts the corrupt-row union at **190 (d0wd) and 1 (s3)**, with **3** caught by
the median filter only. If this pass does not reproduce those three numbers
exactly, its parser is wrong and no result is reportable until that is
resolved. `csi_data` is a quoted, comma-separated list nested inside the CSV,
so it is read with a real CSV reader (`csv.reader`), never a naive
`line.split(',')`.

### 1.11 Chunking

**600 s bins, 41 of them over the 24,123.12 s span** — the same binning
`docs/RECEIVER_TERM_PREREG.md` §8.3 uses on this exact file, reused rather
than invented. A cell enters chunk-level statistics iff it has **≥ 2,000
admissible frames in that chunk** (§4.2).

---

## 2. Does a conjugate term exist at all? — the branch that closes cheaply

**This is established before anything is interpreted.** The ESP32 may already
apply IQ correction internally, in which case the residual conjugate term is
tiny or absent. `docs/HARDWARE_BUY_NOTES.md` and `docs/NODE_CENSUS.md` record
nothing about the RF front end's calibration, and **no artifact in this repo
establishes whether ESP32 IQ correction is on, off, or present at all.** It
is an unknown, and it is treated as one.

### 2.1 The detection rule, frozen

A conjugate term is **DETECTED** in a cell iff **all three** hold:

| # | condition | why |
|---|---|---|
| i | `\|κ\| > max_j \|κ_j\|` over the 64 random even ±1 patterns | the matched filter beats every wrong pattern |
| ii | split-half (alternate frames) agreement: `\|κ_h1 − κ_h2\| < \|κ_h1 + κ_h2\|/2` | the complex value is reproducible, not noise |
| iii | frame coherence `coh = \|A\| / Σ_f \|A^{(f)}\| ≥ 5 × 0.886/√N` | the per-frame terms add coherently rather than as random phases (`E\|Σz\|≈√(πN)/2` for N random-phase unit terms) |

Otherwise the cell is **AT NOISE FLOOR**.

### 2.2 What each outcome means, decided now

| outcome | reading |
|---|---|
| DETECTED on the beacon cells, `\|κ\|` well above `\|κ_j\|` | a residual conjugate term exists; proceed to §§3–5 |
| AT NOISE FLOOR on every beacon cell | **clean negative.** The ESP32 either corrects internally or the residual is below what 52 subcarriers of int8 CSI can resolve. **The branch closes and this is stated plainly as a valuable negative, not padded out.** §§3–5 are then reported as "not runnable, and why", not quietly dropped. |
| DETECTED but `κ` tracks `ν` cell for cell | the statistic is reading the channel. Reported as an estimator failure, and §1.7's injection test is the arbiter. |

**A null here means "no conjugate term above `\|κ\| = X`", with X the measured
null, never "no conjugate term".** X is printed for every cell.

---

## 3. Test 1 — do the three beacons separate, labels withheld?

The three beacons are the proven-signature transmitters of
`docs/NODE_CENSUS.md` §2: `a4:f0:0f:77:91:20` (B1), `28:05:a5:2f:fa:48` (B2),
`f4:2d:c9:70:72:30` (B3).

`κ` is computed per cell with **no reference to which MAC the cell belongs
to**; the estimator never sees a label. Labels are attached only at the
reporting step. Two statistics:

- **Pairwise separation, in the repo's own σ terms.** With `μ_d` = the mean of
  `κ` over device d's chunk cells and `σ_d` = the RMS distance of those cells
  from `μ_d` (a 2-D dispersion in the complex plane),
  `σ_sep(d1,d2) = |μ_1 − μ_2| / √((σ_1² + σ_2²)/2)`.
  `pc/rff_offline.py:353` states the repo's rule of thumb: **> 3σ reliably
  separable.** That threshold is adopted unchanged.
- **Blind 3-cluster check.** k-means (k = 3, fixed seed, 50 restarts) on the
  chunk-level `κ` values with labels withheld, scored by purity and adjusted
  Rand index against the true MACs — the same shape of check
  `docs/BLIND_CLUSTERING.md` runs on the slope.

| verdict | condition |
|---|---|
| **separates** | all three pairwise `σ_sep ≥ 3.0` AND blind purity ≥ 0.90 |
| **partially separates** | at least one pair ≥ 3.0 |
| **does not separate** | no pair reaches 3.0 |

Reported per receiver, never pooled across receivers — pooling is the
confound `docs/IDENTITY_STABILITY.md` §1.1 exists to avoid.

**Pre-registered warning, given §1.3:** if the conjugate term is receiver
silicon, the three beacons at one receiver should **NOT** separate on `κ`, and
a null here is the *expected* result of the physics rather than a failure of
the feature. It would still be a negative for the brief's question, and it
would be reported as one. `τ` (§1.8) is where transmitter separation would
live, and Test 1 is run on `τ` as well, with the same thresholds.

---

## 4. Test 2 — the test that decides it: stability across the 6.70 h session

### 4.1 The statistic, matched to how the slope was scored

`docs/IDENTITY_STABILITY.md` §13's decomposition is reproduced in the
feature's own units, within one session instead of between two:

For each unordered pair of chunks (a, b) on one receiver, and each device d
present in both:

- `Δ_d = κ_d(b) − κ_d(a)` (complex)
- **common-mode** = componentwise median of `Δ_d` across the devices of that
  pair — the part every device shares, which is receiver-side and removable
  by a reference-relative measurement
- **per-device residual** = `Δ_d − common-mode`
- **per-device residual RMS** = RMS of `|residual|` over devices and pairs
- **between-device spread `S_bd`** = RMS over devices of `|μ_d − μ̄|`, `μ̄` the
  centroid of the three device means — the exact analogue of
  `BETWEEN_UNIT_SD`, computed for this feature on this session
- **energy removed by the shared constant** = the §13 quantity, mean-square
  about zero before minus after, **not** `1 − Var(resid)/Var(Δ)`
  (`docs/IDENTITY_STABILITY.md` §13 records why that form is identically zero)

> **THE HEADLINE NUMBER: `ratio = per-device residual RMS / S_bd`.**
>
> For the SFO slope this is **2.2× – 7.1×** (`docs/IDENTITY_STABILITY.md` §13,
> per-device residual 0.00511 / 0.01687 / 0.00882 against
> `BETWEEN_UNIT_SD = 0.00237`).

Reported three ways: over **all** chunk pairs, over **adjacent** chunk pairs
only (10-minute timescale), and for the **widest** pair (first chunk vs last,
≈ 6.5 h apart).

### 4.2 Thresholds, committed now

| verdict | condition | meaning |
|---|---|---|
| **STABLE — the first stable feature this project has found** | ratio **< 1.0** | per-device drift is smaller than the entire between-device spread; devices do not swap places |
| **BETTER THAN THE SLOPE, still not usable** | 1.0 ≤ ratio < 2.2 | beats the slope's best case but identity is still destroyed within the session |
| **NO BETTER THAN THE SLOPE** | ratio ≥ 2.2 | inside the slope's own 2.2–7.1× band or worse; the branch closes |

**Comparability caveat, stated before the number exists.** The slope's
2.2–7.1× is a *cross-session* residual measured with the *shipped RANSAC*
estimator on receiver blocks R3/R4/R5. This pass's ratio is *within-session*
on one session with a *deterministic* slope-removal. The two are therefore
**not the same measurement**, and to make the comparison honest the identical
within-session ratio is computed for **this pass's own deterministic slope
`m_f`** on the same chunks of the same session, and reported next to the `κ`
ratio as the internal comparator. **That comparator is not a re-derivation of
any published SFO figure** (§1.5) and is not compared to `BETWEEN_UNIT_SD`.

### 4.3 What would make this test not answer the question

- Fewer than 3 devices with ≥ 2,000 admissible frames in ≥ 5 chunks on a
  receiver → the common-mode median across devices is near-vacuous (a median
  of two points). Say so, report the ratio anyway, flag it.
- `κ` at the noise floor (§2) → the ratio measures estimator noise, not
  drift, and would be **spuriously large**. In that case the ratio is
  reported as an upper bound driven by measurement noise and **must not be
  quoted as a drift result.**
- The reverse hazard: a `κ` that is a near-constant dominated by the receiver
  would give a **spuriously small** ratio for reasons that have nothing to do
  with transmitter identity. §5 is what distinguishes that case, so §4 and §5
  are read together and neither is quoted alone.

---

## 5. Test 3 — separating transmitter imbalance from receiver imbalance

Both receivers have imbalance too. Measuring TX+RX combined would mean
fingerprinting this project's own radios.

### 5.1 The decomposition

For a source m heard by both receivers at the same time, to first order the
measured coefficient is additive:

> `κ(n, m) = ρ_n + θ_m + e(n, m)`

with `ρ_n` the receiver term (per-receiver constant across sources) and `θ_m`
the transmitter term (common across receivers). Then

- `Dm = κ(d0wd, m) − κ(s3, m) = ρ_d0wd − ρ_s3` — **free of the transmitter
  term entirely.** If the model holds, `Dm` is **constant across sources**.
- `θ_m` up to an additive constant = `½(κ(d0wd,m) + κ(s3,m))` minus its mean
  over sources.

### 5.2 What is and is not identifiable — stated before the result

**With two receivers, only the receiver *difference* is identifiable.** A
component common to both receivers cannot be told apart from a component
common to all transmitters, and is absorbed into the transmitter term. So
this test gives a **lower bound** on the receiver contribution, never an
upper bound. Any statement of the form "the receiver term is only X" would be
unsupportable and will not be made.

### 5.3 The statistics

- **Constancy of `Dm`:** `R_disp = Var_across-sources(Dm) / median_m(Var_boot(Dm))`,
  where `Var_boot` is a moving-block bootstrap over each cell's chunk series
  (B = 200, block length `max(1, n_chunks//4)`, seed 20260823) — the same form
  `docs/RECEIVER_TERM_PREREG.md` §3.3 uses, and blocks rather than iid because
  `docs/SEPARATION_SCALING.md` §0 establishes these series are not white.
  `R_disp < 2` → `Dm` is constant → the additive model holds and the receiver
  difference is a real fixed quantity.
- **Share:** `frac_rx = |ρ_d0wd − ρ_s3| / S_bd`, the receiver difference
  against the between-transmitter spread of §4.1.

### 5.4 Verdict thresholds

| verdict | condition | consequence |
|---|---|---|
| **RECEIVER-DOMINATED — feature unusable as-is** | `frac_rx ≥ 1.0` | the two receivers disagree about a source by more than the sources differ from each other. The feature fingerprints this project's own radios. **Say so.** |
| **INTERMEDIATE** | 0.5 ≤ `frac_rx` < 1.0 | reported as such, with both numbers |
| **TRANSMITTER-DOMINATED** | `frac_rx` < 0.5 AND `R_disp` < 2 | the conjugate term carries transmitter identity and the receiver term is a removable constant |

Run for `τ` as well as `κ`. **Given §1.3, `κ` is predicted
RECEIVER-DOMINATED and `τ` is predicted TRANSMITTER-DOMINATED.** Both
predictions are frozen here.

---

## 6. Test 4 — ambient sources

Reported **separately** from the beacons, never merged into a beacon figure.

### 6.1 The frame floor, stated in advance and justified

`κ`'s noise floor falls as `1/√(N · 52)`. To resolve an image ratio of
`|κ| = 0.02` (a −34 dB image, a plausible value for an uncorrected
consumer front end) at 5:1 against the null, the null must sit below 0.004,
which needs **N ≈ 2,000 admissible frames**. So:

- **Reporting floor: ≥ 20 admissible frames** on the receiver in question —
  the repo's own census floor (`pc/mac_census.py --min-frames 20`,
  `docs/COLOCATED_0823.md` §2). Every such source is listed with its
  frame count, its `|κ|`, and **its own measured null**, so the reader sees
  where the floor sits for that source.
- **Power floor: ≥ 2,000 admissible frames.** Only sources above this can
  produce an interpretable `κ`. Sources between 20 and 2,000 are listed as
  **"present but below the estimator's power floor"** — which is a capability
  statement, not an absence of data (`CLAUDE.md` failure mode **C**).

### 6.2 The pre-registered null outcome

**If no ambient source clears the power floor, this document says "no ambient
source qualified" and stops there.** No beacon number is substituted, no
claim is withdrawn silently, and the floor is not lowered after seeing the
counts — `docs/IDENTITY_STABILITY.md` §10 fired exactly this condition and
handled it exactly this way, and `docs/RECEIVER_TERM_PREREG.md` §14.1 records
declining to relax a floor to recover n. The same discipline applies here.

---

## 7. Reproduce

One script, `pc/exp_iq_imbalance.py`, from the repo root, read-only on
`data/raw/`:

```
export IQ_CACHE=/tmp/iqimb
python3 pc/exp_iq_imbalance.py selftest                      # §1.7 injection + §1.4 convention
python3 pc/exp_iq_imbalance.py scan data/raw/d0wd_20260823_014740.csv --tag d0wd
python3 pc/exp_iq_imbalance.py scan data/raw/s3_20260823_014740.csv   --tag s3
python3 pc/exp_iq_imbalance.py report --tags d0wd,s3
```

Every number in Stage 2 is from `report` unless it names another command.

---

## 8. What this pass will not do

- Not modify `pc/rff/dsp.py`; not use `pc/capture.py:compute_cfo`,
  `pc/phase_skew.py` or `pc/fingerprint.py`.
- Not open a serial port; not write anything under `data/raw/`.
- Not stage, commit or push anything; not spawn a sub-agent.
- Not fuse any `pc/rff/` (phase) number with any `pc/occ/` (amplitude) number.
- Not derive or revise a device-ID accuracy figure.
- Not cite `docs/DIRECTION.md` as capability.
- Not quote the deterministic slope `m_f` as an SFO measurement, and not
  compare it to `BETWEEN_UNIT_SD`.
- Not relabel the ~77 % same-model figure, and not quote it.

---
---

# STAGE 2 — RESULTS

*Appended after the run. Nothing above this line was edited.*

## 9.9 A late-added prediction, frozen before the files were read

`docs/B1_MOVED.md` was found **after** the `014740` run was complete. It
records that beacon **B1 `a4:f0:0f:77:91:20` was physically moved ~100 ft away
and three storeys down, outdoors**, while **B2, B3 and both receivers were not
touched** — and that the capture recording this is
`data/raw/*_20260823_141358.csv`, a **different, later** pair of files than the
`014740` session used above. B1 was in its indoor position for the whole of
`014740`, so nothing above is contaminated by the move.

That manipulation is the strongest available test of whether `κ` is silicon or
geometry, and it is the kind of controlled intervention the rest of this repo
does not have. **The prediction below was written before either `141358` file
was opened, and before any statistic was computed from them:**

> IF `κ` is analog silicon, THEN **arg(κ) for B1 is unchanged by the move**,
> within the chunk-level dispersion measured in §11, and B2's and B3's are
> unchanged too. IF `κ` is channel or geometry, THEN **B1's arg(κ) moves and
> B2's and B3's do not** — the move is the only thing that differs.
>
> **`arg(κ)`, not `|κ|`, is the test.** B1 outdoors at 100 ft is far weaker,
> and additive noise inflates the denominator of `κ` without contributing to
> its coherent numerator, so `|κ|` is *expected* to shrink for reasons that
> have nothing to do with silicon. A magnitude change is therefore not
> evidence either way and will not be read as any.
>
> If B1 fails the frame floor or the mirror-specificity test on the `141358`
> files, the answer is **"not measurable after the move"** — a capability
> limit, not an absence (`CLAUDE.md` failure mode **C**).

---

## 10. Two Stage-1 statements were wrong, and the pre-registered stop conditions are what caught them

Both are corrected here with the original left standing in §1, as the preamble
requires.

### 10.1 §1.5's de-rotation destroys the very term §1.6 measures

Stage 1 specified `G_f(k) = H_meas(k)·e^{−j(m_f·k + b_f)}` — slope **and**
intercept removed. **That is wrong, and the §1.7 injection test is what said
so**: on synthetic data with a known `ε` injected, `κ` recovered a slope of
**0.011 instead of 1.0** and the recovered phase was noise.

The physics Stage 1 did not carry through: a residual carrier phase `p`
rotates the direct term and **counter-rotates the image**,

  `Ĥ(k) = α·H(k)·e^{jp} + β·s(k)·H*(−k)·e^{−jp}`

so in `D(k)·D(−k)` the imbalance cross-terms are **phase-invariant** while the
pure-channel term carries `e^{2jp}`. Removing the intercept inverts that: it
makes the channel term coherent across frames and the imbalance term
incoherent. **Removing only the slope is correct**, and then a coherent
complex average across frames *suppresses the channel and preserves the
imbalance* — the confound separation the brief asks for, done by the averaging
itself rather than by a filter.

`pc/exp_iq_imbalance.py:deslope` implements the corrected form and its
docstring records why.

**With the correction, §1.7's two frozen predictions both pass**, on real
frames from both receivers (`selftest`, reference beacon, 8,000 frames):

| injection | `Δκ` | `Δν` | ratio | prediction |
|---|---|---|---|---|
| conjugate β = 0.010 | **0.00981** | 0.00009 | 0.009 | Δν < 0.2·Δκ ✓ |
| conjugate β = 0.050 | **0.04827** | 0.00131 | 0.027 | ✓ |
| non-conjugate γ = 0.010 | 0.00007 | **0.00807** | 0.009 | Δκ < 0.2·Δν ✓ |
| non-conjugate γ = 0.050 | 0.00036 | **0.04202** | 0.009 | ✓ |

Recovery slope `d|κ|/dβ` = **0.97–0.98** against the required 1 ± 0.15, and on
synthetic data `arg(κ)` recovers the injected 0.700 rad to three decimals at
every β. **`κ` responds to the conjugate relation and is blind to the
non-conjugate one, by a factor of 30–110.** That is the explicit separation
§1.7 demanded, and it is measured, not asserted.

### 10.2 The §1.4 convention check is decisive, and it costs `L(k)` its validation

| | `ROUGH(V₀ = buffer as-is)` | `ROUGH(V₁ = buffer × L(k))` |
|---|---|---|
| d0wd, 7,997 frames | **0.10244** | 1.91176 |
| s3, 8,000 frames | **0.05344** | 2.00483 |

`V₀` is smoother by **19× and 38×**, far past the 2× decision rule:
**the ESP32 LLTF buffer is already a channel estimate, divided by `L(k)`.**
Per §1.4 that means the standard `L(k)` sequence written into the script is
**not independently validated by this branch** — so §10.3's pattern-free route
was added, and §11 reports the sign-agreement between the *measured* pattern
and the standard one as a check rather than an assumption.

Guard bins were exactly zero on **99.96 %** (d0wd) and **100.00 %** (s3) of
sampled frames, reproducing `PROJECT_NOTES.md` §2's 99.88 %.

### 10.3 The pre-registered §2.1 rule (i) is not an existence test — declared, not quietly dropped

§2.1 required `|κ| > max_j |κ_j|` over 64 random even ±1 patterns. **That
control does not do what Stage 1 thought.** Under the model
`c(k) ≡ E_f[D̃(k)D̃(−k)] = 2αβ·s(k)·w(k)` with `w(k) ≥ 0`, a random pattern
`s_j` still projects the *same real coherent vector*, so `|κ_j|` is a fraction
of `|κ|` set by how uneven `w(k)` is — not by whether imbalance exists. It
measures "is `s(k)` the right pattern", which is a different question.

A second attempt — the pattern-free `kfree = Σ_k|c(k)|/(2p)` — **also fails as
a test, for a reason worth recording**: `Σ_k |c(k)|` throws away the phase, and
the phase is where mirror-specificity lives. Pairing `k` with a *shifted*
mirror gives `Σ_k|c(k)|` within **0.81–0.97×** of the true mirror on every
beacon cell, and a convergence sweep (F = 1,000 → 160,000) shows both plateau
rather than falling as `1/√F` — so it is a real coherent term, just not one
that distinguishes pairings.

**The statistic that does distinguish them, and the Stage-2 primary:**

> **`align = |Σ_k s(k)·c(k)| / Σ_k |c(k)|`**

Under the model every `c(k)` lies on **one** complex axis with exactly the
sign pattern `s(k)`, so `align → 1`. Under any wrong pairing the phases
scatter and `align → ~1/√52 ≈ 0.14`. The null is the **same statistic computed
on shifted-mirror pairings** (δ = 2, 5, 9, 13) — same data, same coherent
averaging, same frame-to-frame correlation structure, only the conjugate
relation destroyed. **A cell is `CONJUGATE TERM PRESENT` iff `align` exceeds
all four wrong-pairing `align`s**, and the pre-registered split-half and
coherence conditions still apply.

The alternate-frame split-half floor of §2.1 (ii) is retained but is
**optimistic**, because consecutive frames are not independent; the
wrong-pairing null is the honest one and is what the verdicts use.

### 10.4 The channel term really does average away — checked, not assumed

The whole design rests on the per-frame common phase being spread. Measured
directly on 40,000 frames of B3 on each receiver:

| | `|mean_f e^{2jb}|` | `|mean_f e^{4jb}|` | 12-bin histogram of `b` |
|---|---|---|---|
| d0wd | **0.0048** | 0.0008 | flat, 0.079–0.085 per bin |
| s3 | **0.0075** | 0.0037 | flat, 0.076–0.091 per bin |

So the channel term is suppressed by a factor of ~150–200 by the averaging. A
two-basis regression of `D̃(k)D̃(−k)` on `{1, e^{2jb}}` separates the two
explicitly: the channel component is **0.28–0.35** and the phase-invariant
component **0.008–0.018** in the same units. The confound is 20–40× the signal
in a single frame and is removed by the averaging, not by a filter.

---

## 11. What was run, and the integrity checks

```
export IQ_CACHE=/tmp/iqimb
python3 pc/exp_iq_imbalance.py selftest
python3 pc/exp_iq_imbalance.py scan data/raw/d0wd_20260823_014740.csv --tag d0wd
python3 pc/exp_iq_imbalance.py scan data/raw/s3_20260823_014740.csv   --tag s3
python3 pc/exp_iq_imbalance.py report --tags d0wd,s3
```

(`scan` takes `--seconds N --resume` to checkpoint under this host's ~110 s cap
on a shell call; the split point enters no figure and `report` re-checks the
final byte position against the file size rather than asserting it.)

**Whole files, both nodes, first row to last.** Final byte position equals the
file size **exactly** on both — **2,866,404,334** and **3,596,309,377** — and
row counts are **3,344,351** and **4,330,849**, with **0** rows having ≠ 13
fields or unparseable ints.

**§1.10's reproduction check passes to the unit:**

| | d0wd | s3 | `RECEIVER_TERM_PREREG` §10.1 |
|---|---:|---:|---|
| field screen | 187 | 1 | 187 / 1 |
| width-9 median filter | 186 | 1 | 186 / 1 |
| both | 183 | 1 | 183 / 1 |
| **union (corrupt)** | **190** | **1** | **190 / 1** |
| **median filter ONLY** | **3** | **0** | **3 / 0** |

**Independent `awk` re-derivation** sharing no code with the script:
`kept = 3,344,164`, `fieldScreened = 187`, `distinctCleanMACs = 40` — the
field-screen count matches exactly, `kept` differs from the script's clean-row
count by **exactly 3** (the three median-filter-only rows), and 40 reconciles
with `docs/COLOCATED_0823.md` §2. Per-beacon clean counts differ by exactly 1
each, summing to the same 3. **126 of the d0wd's addresses are corruption
artefacts and were screened before the census**; 129 distinct MACs appear on
d0wd corrupt rows, 1 on the S3's.

**Read-only, verified after the pass.** Both inputs unchanged
(2,866,404,334 / 3,596,309,377 bytes, mtimes `2026-08-23 08:29:44`).
`pc/rff/dsp.py` **not modified** — sha256
`f8ef124a…43dea2`, mtime still **2026-07-13 20:42:46**, the value
`docs/COLOCATED_0823.md` §1 records. `csi_to_complex` was imported and used,
and the interleave was checked end to end: `[imag=7, real=3, …] → 3+7j`, and
`frames_to_H` agrees with `dsp.csi_to_complex` on all 52 usable k. No serial
port opened. `git diff --cached --name-only` **empty**; nothing staged,
committed or pushed. No sub-agents. `pc/capture.py:compute_cfo`,
`pc/phase_skew.py`, `pc/fingerprint.py` not used.

---

## 12. TEST 0 — a conjugate term exists, on 5 of 6 beacon cells

`align` against its four wrong-pairing nulls, whole session:

| recv | beacon | admissible | **align** | wrong-pairing aligns | ratio | **\|κ\|** | image | verdict |
|---|---|---:|---:|---|---:|---:|---:|---|
| s3 | **B3** `f4:2d` | 1,485,537 | **0.9823** | 0.258 / 0.394 / 0.190 / 0.223 | **2.49×** | 0.01952 | −34.2 dB | **PRESENT** |
| d0wd | B2 `28:05` | 1,014,281 | **0.8685** | 0.182 / 0.432 / 0.141 / 0.346 | 2.01× | 0.00387 | −48.3 dB | **PRESENT** |
| s3 | B1 `a4:f0` | 1,259,749 | **0.7822** | 0.174 / 0.423 / 0.092 / 0.292 | 1.85× | 0.00973 | −40.2 dB | **PRESENT** |
| d0wd | B3 `f4:2d` | 1,478,178 | **0.6712** | 0.305 / 0.392 / 0.394 / 0.226 | 1.71× | 0.00440 | −47.1 dB | **PRESENT** |
| s3 | B2 `28:05` | 1,574,527 | **0.6097** | 0.088 / 0.258 / 0.164 / 0.132 | 2.36× | 0.01897 | −34.4 dB | **PRESENT** |
| d0wd | **B1** `a4:f0` | 845,395 | **0.1010** | 0.192 / 0.288 / **0.403** / 0.059 | **0.25×** | 0.00019 | −74.3 dB | **AT NOISE FLOOR** |

**The ESP32 does not fully correct its IQ imbalance: a residual conjugate
image of −34 dB to −48 dB is measurable in the shipped CSI.** The strongest
cell, s3/B3, puts **98.2 % of its coherent per-subcarrier mirror product on a
single complex axis** and its measured sign pattern agrees with the standard
L-LTF-derived `s(k)` on **52 of 52 subcarriers**. That is a textbook
conjugate-image signature, it independently validates the `L(k)` sequence
§10.2 could not otherwise check, and **multipath cannot produce it**: a linear
time-invariant channel scales each subcarrier independently and never couples
`k` to `−k`.

**The confound behaves completely differently, as §1.6 required.** On every
cell the non-conjugate control `ν` is **3–400× larger** than `κ` (0.026–0.166
against 0.0002–0.020) and — being a Hermitian mirror sum — is **real by
construction**, a one-dimensional quantity carrying no imbalance term. The
undemodulated conjugate `κ₀` (0.0003–0.007) sits **50–500× below** the
undemodulated non-conjugate `ν₀` (0.129–0.398), which is the coherent
averaging killing `e^{2jp}` exactly as §10.4 measured.

**`d0wd`/B1 is a clean negative and is reported as one:** its `align` of 0.101
is *below* every one of its own wrong-pairing nulls. It is the weakest source
on that receiver (mean RSSI −82.9 dB). **"No conjugate term above
|κ| = 0.0002 on this cell", not "no conjugate term."**

---

## 13. TEST 1 — the beacons separate, labels withheld

`κ` is computed per (receiver, source, 600 s chunk) with the estimator never
seeing a MAC; labels are attached only at reporting. 41 chunks per device,
123 chunk cells per receiver.

### d0wd (node 68)

| beacon | mean κ | \|mean\| | arg | dispersion | mean RSSI |
|---|---|---:|---:|---:|---:|
| B1 `a4:f0` | +0.00003 − 0.00016j | 0.00016 | −1.377 | 0.00075 | −82.95 |
| B2 `28:05` | +0.00301 + 0.00240j | 0.00385 | **+0.673** | 0.00097 | −79.14 |
| B3 `f4:2d` | −0.00430 + 0.00096j | 0.00441 | **+2.922** | 0.00125 | −74.43 |

> **sep B1–B2 4.54σ · B1–B3 4.35σ · B2–B3 6.66σ**
> blind k-means(3): **purity 0.992, ARI 0.976** → **SEPARATES**

### s3 (node 108)

| beacon | mean κ | \|mean\| | arg | dispersion | mean RSSI |
|---|---|---:|---:|---:|---:|
| B1 `a4:f0` | +0.00504 − 0.00813j | 0.00956 | **−1.016** | 0.00127 | −79.09 |
| B2 `28:05` | −0.01109 − 0.01562j | 0.01916 | **−2.188** | 0.00185 | −74.81 |
| B3 `f4:2d` | +0.00259 − 0.01927j | 0.01945 | **−1.437** | 0.00144 | −78.03 |

> **sep B1–B2 11.21σ · B1–B3 8.39σ · B2–B3 8.54σ**
> blind k-means(3): **purity 1.000, ARI 1.000** → **SEPARATES**

Both receivers clear `pc/rff_offline.py:353`'s own "> 3σ reliably separable"
rule of thumb on every pair. **For comparison and not as a merger: the same
document's slope separations on this hardware are 1.8–2.7σ for same-model
ESP32s (`PROJECT_NOTES.md` §2 claim 4, itself unverified) and 10.4–12.7σ
cross-manufacturer.**

**This is not an RSSI artefact, and the check is in the table.** Additive noise
dilutes `|κ|` (it inflates the denominator without contributing to the
coherent numerator) and the magnitudes do partly track RSSI on d0wd. But
**`arg(κ)` cannot be produced by SNR** — dilution scales a complex number, it
does not rotate it — and the three beacons sit at **+0.67, +2.92, −1.38 rad**
on d0wd and **−1.02, −2.19, −1.44 rad** on s3. On s3, B2 and B3 differ by
3.2 dB in RSSI yet have `|κ|` equal to within 1.5 % and arg differing by
0.75 rad. The separation is directional, not magnitudinal.

**`τ` (the transmitter-ripple statistic) partially separates**: 7.54σ / 0.64σ /
7.14σ on d0wd (purity 0.675) and 2.89σ / 2.59σ / 4.45σ on s3 (purity 0.935).
It is reported because §3 required it, not promoted.

---

## 14. TEST 2 — the test that decides it: `κ` is the first stable feature this project has measured

Per-device residual RMS over between-device spread, computed exactly as
`docs/IDENTITY_STABILITY.md` §13 defines it, on the **same 6.70 h session in
which the slope fell apart**, 41 × 600 s chunks, 3 devices, all 820 unordered
chunk pairs.

| receiver | feature | S_bd | residual RMS | **all pairs** | adjacent (10 min) | widest (~6.5 h) | verdict |
|---|---|---:|---:|---:|---:|---:|---|
| **d0wd** | **κ** | 0.00318 | 0.00131 | **0.41×** | 0.34× | 0.78× | **STABLE** |
| **s3** | **κ** | 0.00848 | 0.00167 | **0.20×** | 0.13× | 0.58× | **STABLE** |
| d0wd | τ | 0.05753 | 0.01915 | 0.33× | 0.20× | 1.23× | STABLE |
| s3 | τ | 0.02333 | 0.01477 | 0.63× | 0.45× | 1.89× | STABLE |
| d0wd | `kfree` | 0.00165 | 0.00186 | 1.12× | 0.92× | 2.75× | better, not usable |
| s3 | `kfree` | 0.00869 | 0.00274 | 0.32× | 0.19× | 0.63× | STABLE |
| d0wd | *deterministic slope* | 0.000349 | 0.000293 | **0.84×** | 0.60× | 0.65× | (comparator) |
| s3 | *deterministic slope* | 0.0000324 | 0.0000346 | **1.07×** | 1.00× | 0.31× | (comparator) |

> ### **κ = 0.41× (d0wd) and 0.20× (s3), against the SFO slope's 2.2×–7.1×.**
> Below 1.0 on both receivers, and below 1.0 even for chunk pairs **6.5 hours
> apart**. Per-device drift is a fifth to two-fifths of the entire
> between-device spread: **the devices do not swap places.**

**The comparability caveat §4.2 committed to in advance, honoured.** The
2.2–7.1× baseline is a **cross-session** residual measured with the **shipped
RANSAC** estimator on receiver blocks R3/R4/R5. This pass's number is
**within-session** with a **deterministic** slope removal. That is why the
identical statistic was computed for this pass's own slope on the same chunks
of the same session: it comes out at **0.84× and 1.07×**. So the like-for-like
statement is:

> **On identical data, identical chunking and an identical statistic, `κ` is
> 2.1× (d0wd) and 5.4× (s3) more stable than a phase slope.** The published
> 2.2–7.1× is a harder, cross-session measurement and `κ` has not yet been
> put through it.

`docs/IDENTITY_STABILITY.md` §12's finding — that the slope wanders by
multiples of the whole between-device spread on a timescale of tens of minutes
— is **not** contradicted: at 10-minute spacing the slope comparator here is
0.60×/1.00×, and §12's 1.0×–9.4× figures are within-session shifts of the
*shipped* estimator between a 60 % and a 40 % block, a different quantity
again. Nothing here revises any SFO figure.

**§4.3's hazards, checked rather than assumed.** `κ` is *not* at the noise
floor on 5 of 6 cells (§12), so the ratio is not measuring estimator noise;
the one cell that is — d0wd/B1 — carries the largest chunk-level dispersion
relative to its mean, which pushes the d0wd ratio **up**, not down. And the
reverse hazard, a `κ` frozen by a dominant receiver term, is exactly what §15
finds and is why §14 and §15 must be read together.

---

## 15. TEST 3 — how much is the receiver? Most of it, and the model does not decompose cleanly

Sources heard by both receivers with ≥ 2,000 admissible frames: **n = 3**, the
three beacons.

| source | κ (d0wd) | κ (s3) | D = d0wd − s3 | \|D\| |
|---|---|---|---|---:|
| B3 `f4:2d` | −0.00431+0.00090j | +0.00259−0.01935j | −0.00691+0.02025j | 0.02139 |
| B2 `28:05` | +0.00305+0.00238j | −0.01131−0.01524j | +0.01435+0.01762j | 0.02273 |
| B1 `a4:f0` | +0.00002−0.00019j | +0.00507−0.00831j | −0.00504+0.00812j | 0.00955 |

| quantity | value | threshold |
|---|---:|---|
| receiver difference \|ρ_d0wd − ρ_s3\| (median D) | **0.01833** | |
| between-transmitter spread S_bd (d0wd, 3 beacons) | 0.00320 | |
| **frac_rx** | **5.73** | ≥ 1.0 → receiver-dominated |
| Var across sources of D | 1.196 × 10⁻⁴ | |
| median block-bootstrap Var(D) (a **lower** bound) | 1.446 × 10⁻⁷ | |
| **R_disp** | **826.6** | < 2 → D constant across sources |

> **VERDICT: RECEIVER-DOMINATED, and the additive model does not hold.**
>
> The two receivers disagree about the same transmitter by **5.7× the entire
> spread between transmitters** — and `R_disp = 826.6` says that disagreement
> is **not a constant** either, so it cannot be calibrated out by subtracting
> one number. **§5.2's limit applies: with two receivers only the receiver
> *difference* is identifiable, so 5.73 is a LOWER bound on the receiver
> share.**

This is exactly the **frozen §1.3 prediction**, and it comes from the physics
rather than from the data: with a real-valued L-LTF the transmitter's image
lands on the training sequence's own image and is absorbed into the direct
term, so the conjugate coefficient is **receiver silicon by construction**.
The magnitudes say the same thing plainly — every s3 cell is 0.0097–0.0195 and
every d0wd cell is 0.0002–0.0044, i.e. **the receiver sets the scale and the
transmitter modulates it.**

**`τ`, the transmitter-side statistic, behaves as predicted too**: `frac_rx`
= **0.66**, INTERMEDIATE rather than receiver-dominated, the only statistic
here that is not. Its `R_disp` is 583, so it does not decompose additively
either.

### 15.1 The B1 move — the §9.9 prediction, answered

`data/raw/*_20260823_141358.csv`, B1 moved ~100 ft away and three storeys down,
outdoors; B2, B3 and both receivers untouched. B3 emits **< 20 admissible
frames** in either `141358` file and is **not in the class set** there — not
"measured and absent".

**These two files were being written by a live capture while this pass ran**
and are not the fixed inputs §11 verified. `d0wd_20260823_141358.csv` was
139,766,479 bytes when this session started and 265,959,999 bytes when it was
read; `s3_20260823_141358.csv` likewise grew. **Every §15.1 figure is
therefore a prefix as of the read, and the byte and row counts will not
reproduce later.** Reads were `"rb"` only and nothing was written, and the
parser reported 0 malformed rows and a final byte position equal to the size
at read time — but this is a weaker provenance than §11's and is labelled so
rather than presented as equal to it. The `014740` pair, which carries every
other number in this document, is closed and unchanged.

| recv | beacon | session | adm | RSSI | \|κ\| | **arg κ** | align | wrong-pair | mirror-specific |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| **s3** | **B1 (MOVED)** | 014740 | 1,259,749 | −79.08 | 0.00973 | **−1.023** | 0.782 | 0.423 | yes |
| **s3** | **B1 (MOVED)** | 141358 | 154,989 | −80.28 | 0.00693 | **−1.094** | 0.535 | 0.306 | yes |
| | | | | | | **Δ = 4.1°** | | | |
| s3 | B2 (untouched) | 014740 | 1,574,527 | −74.74 | 0.01897 | −2.209 | 0.610 | 0.258 | yes |
| s3 | B2 (untouched) | 141358 | 237,401 | −70.79 | 0.01822 | −2.403 | 0.952 | 0.287 | yes |
| | | | | | | Δ = 11.1° | | | |
| d0wd | B1 (MOVED) | 014740 | 845,395 | −82.87 | 0.00019 | −1.441 | 0.101 | 0.403 | **no** |
| d0wd | B1 (MOVED) | 141358 | 116,408 | −83.33 | 0.00065 | +2.075 | 0.300 | 0.395 | **no** |
| | | | | | | Δ = 158.5° | | | |
| d0wd | B2 (untouched) | 014740 | 1,014,281 | −79.06 | 0.00387 | +0.664 | 0.868 | 0.432 | yes |
| d0wd | B2 (untouched) | 141358 | 192,832 | −73.43 | 0.00347 | −2.946 | 0.757 | 0.559 | yes |
| | | | | | | Δ = 153.2° | | | |

> **On s3, `arg(κ)` for the moved beacon changed by 4.1° across a ~100 ft,
> three-storey, indoor-to-outdoor relocation — less than the 11.1° of a beacon
> that was not moved at all.** `|κ|` fell to 0.71× as §9.9 predicted it would
> from the weaker link, and was not read as evidence.
>
> **No channel or geometry quantity survives that move.** This is the
> strongest single piece of evidence in this pass that `κ` is analog silicon.

**And the counter-observation, reported rather than set aside: on d0wd both
beacons rotated by ~155° between the two captures** — B1 (moved) by 158.5° and
B2 (untouched) by 153.2°, in the same direction, roughly a half-turn. A common
rotation of every source at one receiver is a **receiver-side** change between
captures, not a transmitter one, and a π rotation of `κ` is a sign flip of
`β/α`. **What caused it is unknown and was not investigated** — nothing in this
pass or in `docs/B1_MOVED.md` records the receivers being power-cycled,
reflashed or reseated between 08:29 and 14:13, and inferring one would be
`CLAUDE.md` failure mode **G**. It is a live hazard for any cross-session use
of `κ` and §18 names it as the first thing to settle.

---

## 16. TEST 4 — ambient sources, reported separately

Floors stated in §6.1 and applied unchanged: reporting ≥ 20 admissible frames,
power ≥ 2,000.

**d0wd: 15 ambient sources clear the reporting floor. `0` clear the power
floor.** The largest is `32:c8:46:83:87:d0` at **1,354** admissible frames.
**NO AMBIENT SOURCE QUALIFIED on this receiver.** No beacon number is
substituted, the floor was not lowered after seeing the counts, and no claim is
withdrawn silently — `docs/IDENTITY_STABILITY.md` §10 and
`docs/RECEIVER_TERM_PREREG.md` §14.1 set that precedent and it is followed.

**s3: 11 clear the reporting floor, `2` clear the power floor**, and both are
mirror-specific:

| mac | adm | \|κ\| | align | wrong-pairing | ratio | mirror-specific |
|---|---:|---:|---:|---:|---:|---|
| `7e:ed:82:d6:23:e8` | 2,955 | 0.01266 | 0.394 | 0.176 | 2.25× | **yes** |
| `62:45:b4:f0:e1:97` | 2,693 | 0.01448 | 0.386 | 0.184 | 2.09× | **yes** |

Two third-party transmitters, neither an ESP32 and neither under this
project's control, **carry a measurable conjugate image term** — 0.0127 and
0.0145, sitting **inside the s3 beacon range** of 0.0097–0.0195. That is what
§15 predicts if the receiver sets the scale, and it is the first evidence in
this pass that the estimator works on hardware nobody here chose. **It is not
a separation result**: n = 2, no cross-session arm, and no stability figure is
computed for them.

Nine further s3 sources between 20 and 2,000 frames are listed with their
`align` and their own nulls in the run output — **"present but below the
estimator's power floor"**, which is a capability statement, not an absence
(`CLAUDE.md` failure mode **C**).

---

## 17. Verdicts against the Stage-1 thresholds

| § | threshold | measured | **verdict** |
|---|---|---|---|
| 1.7 | injection: Δν < 0.2·Δκ and Δκ < 0.2·Δν | 0.009–0.027 both ways; recovery slope 0.97 | **PASS** (after §10.1) |
| 1.4 | roughness ratio ≥ 2× | 19× and 38× | **already divided**; `L(k)` unvalidated by this branch, then validated by §12 |
| 2.1 | conjugate term above noise | 5 of 6 beacon cells mirror-specific at 1.71–2.49× the wrong-pairing null | **EXISTS**; d0wd/B1 at the floor |
| 3 | all pairs ≥ 3.0σ AND purity ≥ 0.90 | d0wd 4.35–6.66σ, purity 0.992; s3 8.39–11.21σ, purity 1.000 | **SEPARATES, both receivers** |
| 4.2 | ratio < 1.0 | **0.41× (d0wd), 0.20× (s3)** | **STABLE — the first stable feature this project has found** |
| 5.4 | frac_rx ≥ 1.0 → receiver-dominated | **5.73**, a lower bound; R_disp 826.6 | **RECEIVER-DOMINATED, not additively separable** |
| 5.4 | same, for τ | 0.66 | **INTERMEDIATE** |
| 6.2 | no ambient qualifies → say so | d0wd **0 of 15**; s3 **2 of 11** | **fired on d0wd, stated, nothing substituted** |
| 9.9 | arg(κ) invariant to the B1 move | s3 **4.1°** moved vs 11.1° unmoved; d0wd ~155° on *both* | **silicon on s3; a receiver-side jump on d0wd** |

---

## 18. Limitations

- **n = 3 transmitters and n = 2 receivers.** Every separation figure is about
  whether *these three units* separate. With two receivers only the receiver
  *difference* is identifiable (§5.2), so §15's 5.73 is a lower bound and no
  upper bound on the receiver share exists in this data.
- **One session for the stability number.** 6.70 h, 41 chunks. `κ` has **not**
  been put through the cross-session test that killed the slope, and §15.1's
  d0wd observation is a concrete reason to expect trouble there.
- **`arg(κ)` on d0wd rotated ~155° for both beacons between two captures 6 h
  apart, cause unknown.** Until that is explained, no cross-session claim for
  `κ` should be made.
- **`|κ|` is diluted by additive noise**, so magnitudes are not comparable
  across links of different strength. The separation results rest on the
  complex value and on `arg(κ)` in particular.
- **The deterministic slope used as the §14 comparator is not the shipped
  RANSAC estimator** and no SFO figure in this repo is re-derived from it. Its
  between-device spread on this session (0.000349 / 0.0000324) is not
  `BETWEEN_UNIT_SD` and was not compared to it.
- **`L(k)` is taken from the 802.11 standard.** §10.2's branch could not
  validate it; §12's 52-of-52 sign agreement on s3/B3 does, on one cell.
- **Ambient coverage is thin**: 0 qualifying sources on d0wd, 2 on s3, no
  stability or cross-session arm for either.
- **The `141358` files of §15.1 were live and growing during this pass**, so
  that section's counts are a prefix and are not byte-reproducible. Everything
  else comes from the closed `014740` pair.
- **One scratch artefact could not be removed**:
  `pc/__pycache__/exp_iq_imbalance.cpython-310.pyc`, created when the
  verification helpers imported the module rather than running it. `rm` on this
  mount returns `Operation not permitted`, exactly as
  `docs/RECEIVER_TERM_PREREG.md` §10 records for its own `.pyc`. It is covered
  by `.gitignore:14-15`. All other scratch is in `$IQ_CACHE` outside the repo.
- **No `pc/occ/` number was read, produced or combined with anything here.**
  No device-ID accuracy figure is derived or revised. `docs/DIRECTION.md` is
  not cited as capability. The ~77 % same-model figure is not quoted and not
  relabelled.

---

## 19. What would settle it

1. **The cross-session test.** `κ` on the same receiver across the R3/R4/R5
   session sets that `docs/IDENTITY_STABILITY.md` scored the slope on, with
   the same ordered-pair design. §14 measures within-session stability only,
   and that is the arm the slope also passed.
2. **Explain the d0wd ~155° rotation** (§15.1) before anything else. If it is
   a boot-time sign convention it is trivially correctable and `κ` survives
   cross-session; if it is silicon state that wanders, `κ` fails the same way
   the slope did. A capture pair straddling a deliberate receiver reboot,
   with the reboot written into the `label` column, decides it in one session.
3. **A third receiver** makes the common receiver component identifiable and
   turns §15's lower bound into a decomposition.
4. **`τ` deserves its own pre-registration.** It is the transmitter-side
   statistic, it is the only one that is not receiver-dominated (0.66), and it
   was secondary here.
5. **Ambient sources need a longer dwell**, exactly as
   `docs/IDENTITY_STABILITY.md` §20 item 2 already asks. At 2,000 frames the
   estimator works; the corpus supplies that for 2 sources out of 26.

---

## Files added or written by this investigation

- `pc/exp_iq_imbalance.py` — the one script; source of every number above
- `docs/IQ_IMBALANCE.md` — this file

`pc/rff/dsp.py` was **read and imported unchanged** (sha256 and mtime verified
after the run). Nothing under `data/raw/`, `firmware/`, `pc/occ/` or `site/`
was touched. `pc/rff/dsp.py` was not modified. All scratch state went to
`$IQ_CACHE = /tmp/iqimb`, outside the repo tree. Nothing was staged, committed
or pushed.
