# KAPPA_SLOPE_FUSION — does `κ` + slope beat either alone?

**Stage 1 (everything above the `STAGE 2` banner) was written and saved
before any statistic in this document was computed.** The inputs are the
scan caches already produced for `docs/KAPPA_CROSS_SESSION.md`; no capture
file is re-read and no new data exists.

**Date:** 2026-08-27 · **Scope:** read-only. Nothing in `pc/rff/` is
modified. No git command is run.

---

## 0. Why this test, and why it is not a re-roll

`docs/KAPPA_CROSS_SESSION.md` §8.4 measured, on the s3 receiver, N = 3, over
12 ordered session pairs and 1,293 tests:

| feature | median `A_nn` | bar 2/N |
|---|---:|---:|
| `κ`, derotated | 65.2 % | 66.7 % |
| SFO slope, same pairs | 42.2 % | 66.7 % |

Both fail. But they are **different features that were never combined**, and
two prior results say the combination is the obvious thing to try:

- `docs/BLIND_CLUSTERING.md` §9.3 measured the participation ratio of the
  standardised clock features at **1.38–1.55**. The existing feature space is
  roughly one and a half dimensions. That is a space short of an axis.
- `docs/IQ_IMBALANCE.md` §2 froze the condition under which adding one is
  legitimate: *"Adding a second feature only helps if the new one is more
  stable, not merely different. A second unstable dimension is a second way
  to be wrong."* `κ` measures **0.41× / 0.20×** against the slope's
  **2.2–7.1×** (`IQ_IMBALANCE.md` §14), so it satisfies that condition.

This is the case that document sanctioned in advance and nobody ran.

**It is not a re-roll of `KAPPA_CROSS_SESSION.md`.** That pass asked whether
`κ` alone clears a bar and answered no. This pass asks a different question —
whether two features carry non-redundant information — and it can fail
independently. The 65.2 % figure is not recomputed, re-tuned or improved
here, and nothing in this document revises it.

---

## 1. Hypothesis, frozen

**H3 — the fused feature carries information neither component carries
alone**, and therefore identifies devices across session boundaries better
than the better of `κ`-alone and slope-alone, on the same pairs.

---

## 2. The control that decides whether H3 means anything

**A three-dimensional feature will out-score a two-dimensional one for
reasons that have nothing to do with physics.** More axes is more room for
two centroids to sit apart, and Mahalanobis distance grows with dimension
under the null. Any raw comparison of `[Re κ, Im κ, sfo]` against
`[Re κ, Im κ]` is therefore uninterpretable on its own.

So the decisive comparison in this document is **not** fused-vs-`κ`. It is:

> **fused-with-slope** versus **fused-with-a-random-axis of the same
> variance.**

`NOISE` is drawn `N(0, var(sfo))` per observation, with `var(sfo)` computed
**from the enrollment half only**, seed frozen at `20260827`. It occupies
exactly the same slot, at exactly the same scale, and carries exactly no
information. Whatever accuracy it buys is the dimensionality premium, and it
is subtracted from the claim.

This is the same shape of check `KAPPA_CROSS_SESSION.md` §4.1 used when it
ran a fair 1-D arm beside the 2-D one, and it exists for the same reason.

---

## 3. Arms

| arm | fused | control | components |
|---|---|---|---|
| **F3** | `[Re κ, Im κ, sfo]` | `[Re κ, Im κ, NOISE]` | `[Re κ, Im κ]`, `[sfo]` |
| **F2** | `[arg κ, sfo]` | `[arg κ, NOISE]` | `[arg κ]`, `[sfo]` |

F2 exists because F3's components differ in dimension (2 vs 1), so an F3 gain
is partly structural. In F2 both components are 1-D and the fused feature is
2-D, so the dimensionality premium is identical on both sides of the
comparison. **F2 is the arm this document leads with if the two disagree.**

`κ` is the derotated `κ` of `KAPPA_CROSS_SESSION.md` §8.3 throughout, and the
raw variant is reported beside it.

---

## 4. Decision rules, frozen before the numbers exist

Median `A_nn` over ordered session pairs, s3 only, N = 3, with N printed
beside every figure (`IDENTITY_STABILITY.md` §1.3).

Let `Δ_info` = paired median (fused-with-slope − fused-with-NOISE), 95 % CI by
bootstrap over pairs, 4,000 resamples, seed `20260827`.

| condition | verdict |
|---|---|
| `Δ_info` CI **excludes zero** and fused median **≥ 2/N = 66.7 %** | **PASS.** The slope carries information `κ` does not, and the pair clears the bar. |
| `Δ_info` CI excludes zero, fused median **< 2/N** | **PARTIAL.** Non-redundant, still not identification. |
| `Δ_info` CI **includes zero** | **FAIL.** Any apparent gain is the dimensionality premium. The fusion branch closes. |

**Stated now:** a fused median above 66.7 % with `Δ_info` spanning zero is
**not** a pass. It would mean the number was bought with an axis, and a random
axis would have bought it too.

---

## 5. Controls carried forward

Unchanged from `KAPPA_CROSS_SESSION.md` §5, recomputed here for the fused
features: **P1** within-session (60/40 chronological) must pass or nothing is
interpretable; **N1** label shuffle must collapse to chance; **N2** no pooling
across receivers. `MIN_WIN = 10`, 600 s chunks, `detected2` admission — all
unchanged, so the cells are the same cells.

---

## 6. What this pass cannot show

- **Nothing cross-receiver.** s3 only, per §8.2 of the previous pass, whose
  floor accounting found the d0wd never clears three beacons in one session.
- **No revision of 65.2 %, 42.2 %, 99.7 %/7,497 or 95.7 %/14,234.**
- **No claim that a passing `Δ_info` makes the system work.** Non-redundancy
  is a statement about two features, not a capability.
- Nothing is fused with `pc/occ/`. The ~77 % same-model figure is not quoted
  or relabelled. `DIRECTION.md` is not cited as capability.

---

## 7. Reproduce

```
python pc\exp_kappa_cross_session.py fuse
```

Reads the same caches. `MIN_WIN`, the seed and the bars are module constants,
not CLI flags.

---

## STAGE 2 — results

**Run 2026-08-27**, `python pc\exp_kappa_cross_session.py fuse`. Same caches,
same cells, same 12 s3 pairs, 1,293 tests. Two consecutive runs
**byte-identical**. Nothing above this banner was edited after the run.

### 8. Verdict in one line

**FAIL on both arms. The SFO slope adds nothing to `κ` that a random number
of the same variance would not also add. The fusion branch closes.**

### 8.1 The measurements

s3 only, **N = 3**, 12 ordered pairs, **1,293 tests**. Chance 33.3 %, bar
2/N = 66.7 %.

| arm F3 — `κ`=[Re,Im] | `A_nn` | `A_gated` |
|---|---:|---:|
| P1 within-session, fused | 99.0 % | 97.9 % |
| **fused** `[Re κ, Im κ, sfo]` | **64.8 %** | 19.2 % |
| **NOISE control** `[Re κ, Im κ, N(0,var sfo)]` | **66.7 %** | 23.6 % |
| `κ` alone | 65.2 % | 18.4 % |
| slope alone | 35.9 % | 35.9 % |
| N1 label shuffle | 31.3 % | 1.7 % |

| arm F2 — both components 1-D | `A_nn` | `A_gated` |
|---|---:|---:|
| P1 within-session, fused | 88.2 % | 87.2 % |
| **fused** `[arg κ, sfo]` | **66.2 %** | 46.2 % |
| **NOISE control** `[arg κ, N(0,var sfo)]` | **63.4 %** | 53.8 % |
| `κ` alone | 62.5 % | 53.9 % |
| slope alone | 35.9 % | 35.9 % |
| N1 label shuffle | 30.0 % | 19.2 % |

### 8.2 `Δ_info` — the comparison the whole document turns on

Paired bootstrap over the 12 shared pairs, 4,000 resamples, seed 20260827:

| arm | fused − NOISE | 95 % CI | pairs won | verdict |
|---|---:|---|---:|---|
| **F3** | **+0.00 pp** | **[−1.80, +1.71]** | 4 / 12 | **FAIL — CI includes zero** |
| **F2** | **+0.83 pp** | **[−3.78, +7.53]** | 7 / 12 | **FAIL — CI includes zero** |

Per §4, a `Δ_info` interval spanning zero means any apparent gain is the
dimensionality premium. **Both arms span it, and F3 spans it tightly** —
±1.8 pp is a narrow interval, so this is not an underpowered result the way
`KAPPA_CROSS_SESSION.md` §8.4 was. It is a well-measured zero.

**In F3 the random axis scored 66.7 % and the real slope axis scored 64.8 %.**
The slope did not merely fail to help; it did fractionally worse than noise,
by an amount inside the interval.

### 8.3 What the control caught

This is the reason §2 exists. The comparison a less careful pass would have
reported:

| | F3 | F2 |
|---|---:|---:|
| fused − slope alone | **+24.4 pp**, CI [+6.8, +45.7], 9/12 | **+26.6 pp**, CI [+22.6, +31.2], **12/12** |

Both intervals exclude zero. Both look decisive. **Neither is a fusion
result** — they restate `KAPPA_CROSS_SESSION.md` §8.4's finding that `κ` beats
the slope, and the fused feature inherits it from its `κ` component. Against
the NOISE control, which holds dimension and scale fixed and removes only the
information, the entire gain disappears.

Without §2's control, F3's `+24.4 pp, 9/12 pairs, CI excluding zero` was
available to be published as evidence that fusing the two features works.
It is not.

### 8.4 What this means, physically

`BLIND_CLUSTERING.md` §9.3 measured the standardised clock feature space at a
participation ratio of **1.38–1.55**. This pass is consistent with that and
sharpens it: **the missing half-dimension is not supplied by the SFO slope.**

The most economical reading is the one the slope's own instability already
suggests — `LABELLED_EVENTS_0823.md` §20 measured it wandering **0.56 to 4.97
× the entire between-device spread over four untouched minutes**. A feature
that moves by multiples of the between-device spread inside the averaging
window does not carry a stable axis to contribute. That reading is
**consistent with, not established by**, this pass.

### 8.5 Controls

| control | F3 | F2 | verdict |
|---|---|---|---|
| **P1** within-session fused | 99.0 % | 88.2 % | **PASS** |
| **N1** label shuffle | 31.3 % | 30.0 % vs chance 33.3 % | **PASS** — collapses |
| **N2** no receiver pooling | s3 only throughout | | **HELD** |
| reproducibility | two runs byte-identical | | **HELD** |

### 9. What this pass does not establish

- **It does not show `κ` cannot be improved.** It shows *this* second feature,
  on *this* corpus, adds nothing. A different feature — `τ`, `|κ|`'s
  frequency structure, something not yet extracted — is untested.
- **It does not revise 65.2 %, 42.2 %, 99.7 %/7,497 or 95.7 %/14,234.**
- **It says nothing cross-receiver.** s3 only.
- **The 66.2 % in arm F2 is not "essentially at the bar."** It is below a
  frozen bar and its `Δ_info` spans zero, so the number is not attributable
  to information in the first place.
- Nothing fused with `pc/occ/`. The ~77 % same-model figure is not quoted or
  relabelled. `DIRECTION.md` is not cited as capability.

### 9.1 Temptations recorded rather than acted on

1. **Reporting `fused − slope` as the headline.** +24.4 and +26.6 pp, both
   CIs excluding zero, 12/12 pairs in F2. It is a restatement of a known
   result wearing a fusion label. §8.3 reports it only as the thing the
   control caught.
2. **Leading with F2 because 66.2 % is the largest number in the document.**
   §3 named F2 the lead arm in advance *for its dimensional symmetry*, and its
   `Δ_info` fails, which is what is reported.
3. **Calling F3's −1.9 pp "the slope actively hurts."** It is inside the
   interval. It is reported as inside the interval.
4. **Re-running with a different NOISE seed until `Δ_info` cleared zero.** The
   seed was frozen in §2 and used once.

### 10. Reproduce

```
python pc\exp_kappa_cross_session.py fuse
```

Every figure above is printed by that command. The bars, the seed, `MIN_WIN`
and the arm definitions are module constants in
`pc/exp_kappa_cross_session.py`, not CLI flags, so a run cannot be tuned from
the command line.
