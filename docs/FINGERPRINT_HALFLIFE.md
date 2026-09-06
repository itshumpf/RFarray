# How long does the fingerprint last? — 2026-09-04

**Exploratory. Not pre-registered. Nothing here scores P1–P3, D1–D4 or Q1–Q6.**

Every figure is measured this session from `data/raw/` through the project's own
pipeline (`pc/rff_offline.collect_observations` and `rff.discriminator`,
imported unmodified). No new capture was taken. No git command was run.

---

## 1. The hole this fills

Before today the corpus knew two things about the fingerprint's lifetime and
nothing in between:

| timescale | evidence | source |
|---|---|---|
| 5–39 minutes | wander 0.06–0.42σ; **blind identification 95.8% median** | `SEVEN_NIGHT_REREAD.md` §9I, `SECOND_WINDOW_PREREG.md` Q1/Q3 |
| **1 hour → 20 hours** | **nothing** | — |
| next session | **29.7% against 33.3% chance** | `IDENTITY_STABILITY.md` |

Everything was either short-window or next-day. The question this document
answers is where, inside that gap, a clock signature stops being an identifier.

**The asset that makes it answerable without new hardware** is the 2026-09-01
capture: 20.19 continuous hours on one power-on, with B2 `28:05` transmitting
the entire time on both receivers, and all three beacons live for the first
5.9 h (`SEVEN_NIGHT_REREAD.md` §1). Nights 1, 5, 6 and 7 add 4–7 h each.

## 2. Method

**Sampling.** A 300 s measured block preceded by a 500 s lead-in, taken every
30–60 minutes across each capture. The lead-in is the method validated in
`SEVEN_NIGHT_REREAD.md` §9A, which reproduced `SEVEN_NIGHT_PREREG.md` §10's
table on 40 of 40 cells. **109 sample points** over 9 capture-receiver
combinations, 27 capture-beacon streams.

**Two independent readouts**, because one of them could be an artifact of the
σ yardstick and the other could not:

1. **Drift** — median |ΔSFO| between every pair of sample points, binned by
   separation, in `BETWEEN_UNIT_SD` = 0.00237 rad/sc.
2. **Identification** — enrol a `Discriminator` on a single 300 s block at
   t = 600 s, then ask it to name the transmitter in blocks 1–5 hours later.
   Same class, same code, no retraining. This measures the thing anyone
   actually cares about instead of a proxy for it.

**Scope, stated up front.** All comparisons are *within one continuous
power-on*. Three classes, so chance is 33.3%. The enrolment block is ~400
windows, thinner than the ~1,400 `rff_offline`'s 60% split uses, which makes
the covariance ellipse tighter and the rejection rate in §5 an upper bound.

## 3. The drift curve

Median |ΔSFO| within one power-on, in `BETWEEN_UNIT_SD`. 1,517 pairs.

| lag | all | s3 | d0wd | √t model |
|---|---:|---:|---:|---:|
| 5 min *(§9I)* | 0.06 | 0.06 | 0.08 | — |
| 19 min *(§9I)* | 0.15 | 0.15 | 0.21 | — |
| 39 min *(Q1)* | 0.07 | — | — | — |
| 0.5–1 h | **0.18** | 0.15 | 0.25 | 0.18 |
| 1–1.5 h | 0.29 | 0.28 | 0.30 | 0.24 |
| 1.5–2 h | 0.44 | 0.19 | 1.74 | 0.28 |
| 2–3 h | 0.33 | 0.33 | 0.33 | 0.34 |
| 3–4 h | 0.56 | 0.47 | 0.71 | 0.40 |
| 4–6 h | 0.83 | 0.81 | 0.86 | 0.48 |
| 6–9 h | **1.09** | 0.97 | 1.34 | 0.58 |
| 9–13 h | 0.89 | 0.62 | 1.13 | 0.71 |
| 13–21 h | 1.04 | 1.39 | 0.38 | 0.88 |

Per beacon, so no single stream carries the curve:

| lag | B2 | B1 | B3 |
|---|---:|---:|---:|
| 0.5–1 h | 0.15 (73) | 0.20 (71) | 0.24 (70) |
| 1–1.5 h | 0.26 (91) | 0.27 (62) | 0.33 (61) |
| 2–3 h | 0.29 (128) | 0.37 (93) | 0.53 (91) |
| 3–4 h | 0.43 (80) | 0.56 (43) | 0.83 (41) |
| 4–6 h | 0.74 (121) | 0.83 (41) | 1.02 (37) |
| 6–21 h | 0.89–1.09 | *dead* | *dead* |

**Crossings.** 0.25σ at 1–1.5 h. 0.5σ at 3–4 h. **1.0σ at 6–9 h. 2.0σ is never
reached inside 21 hours.**

**The wander saturates near 1σ and stops.** That matters more than the
crossings: an unbounded random walk keeps growing, and this does not. **A
single beacon, left alone on one power-on, drifts about as far as the typical
distance between two different beacons — and then no further.**

That is exactly the shape needed to explain `IDENTITY_STABILITY.md`'s
cross-session result being **at** chance rather than below it. A signature that
wandered without limit would eventually land systematically on a neighbour. One
that saturates at the inter-device spacing lands nowhere in particular, forever.

**Caveat that limits the last three rows:** every lag beyond 6 h comes from B2
on the 2026-09-01 capture only, because B1 and B3 are dead by then on every
night. The plateau is one beacon on two receivers, not three beacons on seven
nights.

## 4. Is the boundary elapsed time, or the power cycle?

| comparison | median | n |
|---|---:|---:|
| within one power-on, lag ≥ 6 h | **0.97σ** | 357 |
| across a power cycle, ~24 h (`SEVEN_NIGHT_PREREG.md` §11) | **2.15σ** | 32 |

Per beacon:

| beacon | within one power-on ≥ 6 h | across a power cycle |
|---|---:|---:|
| B2 | 0.97σ (n=357) | 1.40σ (n=12) |
| B1 | *no data — dies first* | 1.75σ (n=8) |
| B3 | *no data — dies first* | 7.60σ (n=12) |

**For the stable beacon, a night's sleep costs about 40% more than the same
elapsed time spent running.** Time is the larger term; the power cycle adds to
it rather than causing it. B3's 7.60σ is dominated by the d0wd pathology
documented in `RECEIVER_DIVERGENCE_PREREG.md` and is not evidence about reboots.

**This is not a controlled comparison** — the two rows differ in elapsed time
(6–21 h vs ~24 h), in beacon mix, and in n by a factor of ten. It is reported
because it is the only handle the corpus has on the question, and it points
away from the reboot being the whole story.

## 5. Identification accuracy vs hours since enrolment

**This is the result.** Enrol once on a 300 s block. Ask again later. Six
capture-receivers (nights 4, 5, 7 × both receivers), three classes, chance
33.3%.

| hours since enrolment | median accuracy | min | max |
|---:|---:|---:|---:|
| 0 *(60/40 split within the block)* | **97.5%** | 91.8% | 100.0% |
| +1 | **69.3%** | 42.0% | 99.4% |
| +2 | 64.0% | 35.2% | 99.7% |
| +3 | 69.9% | 36.8% | 98.7% |
| +4 | 54.9% | 29.3% | 74.4% |
| +5 | **53.6%** | 8.1% | 83.4% |

Per capture, because the spread is the finding as much as the median:

| night | rx | +0 h | +1 h | +2 h | +3 h | +4 h | +5 h |
|---:|---|---:|---:|---:|---:|---:|---:|
| 4 | s3 | 98.5% | 90.9% | 70.9% | 76.4% | 72.1% | 64.9% |
| 4 | d0wd | 100.0% | 99.4% | 99.7% | 98.7% | 29.3% | 8.1% |
| 5 | s3 | 95.3% | 60.5% | 52.5% | 50.1% | 48.6% | 46.5% |
| 5 | d0wd | 91.8% | 54.7% | 57.0% | 64.2% | 61.1% | 60.7% |
| 7 | s3 | 97.2% | 42.0% | 35.2% | 36.8% | 31.6% | 28.5% |
| 7 | d0wd | 97.7% | 78.0% | 78.0% | 75.5% | 74.4% | 83.4% |

**The half-life is about one hour.** The single largest drop is the first one:
97.5% → 69.3%. After that the decay is slow and the median never reaches chance
inside five hours.

**But the per-capture spread is enormous and it is not noise.** Night 4 d0wd
held **99.4%, 99.7%, 98.7% for three hours** and then fell off a cliff to 29.3%
and 8.1% — below chance, which means the centroids crossed rather than blurred.
Night 7 s3 was at 42.0% within a single hour. **There is no universal N. There
is a distribution of N, and it ranges from under an hour to over three.**

## 6. The failure is refusal, not confusion — and this is the headline

Every non-correct outcome, split by what the classifier actually did. Medians
across the six captures, so the three columns are not required to sum to 100.

| hours | correct | **names the WRONG device** | rejects as unknown |
|---:|---:|---:|---:|
| +1 | 69.3% | **2.2%** | 8.5% |
| +2 | 64.0% | **1.8%** | 15.3% |
| +3 | 69.9% | **3.9%** | 15.8% |
| +4 | 54.9% | **3.1%** | 23.6% |
| +5 | 53.6% | **1.2%** | 25.1% |

**The false-identification rate does not decay. It sits between 1.2% and 3.9%
at every lag out to five hours.** What decays is willingness to answer:
rejection climbs from 8.5% to 25.1%.

> #### CORRECTION, 2026-09-04 — the median above describes a bimodal
> distribution and should not have been reported alone
>
> Per cell rather than per median, wrong-identity at +1 h → +5 h is:
>
> | night | rx | spread at enrolment | wrong-identity | precision |
> |---:|---|---:|---|---:|
> | 4 | d0wd | 24.5σ | 0.0 / 0.0 / 0.0 / 0.0 / 0.0% | 100% |
> | 4 | s3 | 5.0σ | 0.0 / 0.0 / 0.0 / 0.0 / 0.1% | 99.9–100% |
> | 7 | d0wd | 13.8σ | 3.9 / 3.7 / 7.8 / 6.2 / 2.2% | 90.6–98.9% |
> | 7 | s3 | 6.4σ | 0.6 / 0.0 / 0.0 / 0.0 / 0.0% | 98.7–100% |
> | **5** | **d0wd** | **2.9σ** | **40.8 / 38.6 / 31.0 / 30.9 / 37.4%** | **57–67%** |
> | **5** | **s3** | **1.7σ** | **31.5 / 35.2 / 35.0 / 34.2 / 38.3%** | **55–66%** |
>
> **Four cells are at or near zero. Both night-5 cells are at 30–40%.** The
> "1.2–3.9% flat" figure is the median of a two-humped distribution and
> describes neither hump. Reporting it that way was the mistake and it is
> corrected rather than removed.
>
> **The split is not random.** Night 5 is the collapse night, independently
> identified by `SECOND_WINDOW_PREREG.md` Q4 as the minimum-spread night on
> both receivers, twice, on disjoint windows, with B2–B3 at 0.09σ. **When two
> devices genuinely share a fingerprint the classifier confuses them; when they
> do not, it refuses rather than guesses.** Every cell with spread ≥ 5.0σ has
> wrong-identity ≤ 7.8%; both cells below 3.0σ are above 30%.
>
> So the claim in §7 — *"it does not answer wrongly inside five hours"* — is
> **conditional on the devices being separable at all**, and must be quoted
> with that condition. `docs/NIGHT_EIGHT_PREREG.md` R3 freezes the conditional
> form and tests it on a night that does not exist yet.

Restated as precision — *when it does name a device, how often is it right?*

| hours | +1 | +2 | +3 | +4 | +5 |
|---|---:|---:|---:|---:|---:|
| **precision** | **96.9%** | **97.3%** | **94.7%** | **94.7%** | **97.8%** |

**Precision is flat at 95–98% for five hours. Recall is what collapses.**

The system does not become wrong. **It becomes silent.** A `d²` outside the 99%
ellipse (`rff/discriminator.py:24`, `CHI2_99 = 9.210`) is the estimator
declining to answer, which is a categorically different failure from naming a
neighbour — and for anything security-shaped it is the failure you want.

## 7. What N is, stated three ways

- **If N means "how long until it stops answering":** the half-life is about
  **one hour**, with a distribution running from under an hour to over three,
  and a floor well above chance at five hours.
- **If N means "how long until it answers wrongly":** **it does not, inside
  five hours.** 1.2–3.9% false identification, flat.
- **If N means "how long until the signature has moved as far as its
  neighbours":** **6–9 hours**, and it stops there rather than continuing.

The three answers are consistent, and together they explain the two numbers
that bracketed the gap: 95.8% at half an hour, chance the next day.

## 8. What this does not establish

- **One apartment, three ESP32s at 20 MHz, one week.** Nothing here speaks to
  other hardware, other rooms, or more than three classes.
- **Every lag beyond 6 hours is B2 alone**, on one capture, on two receivers.
- **Chance is 33.3% because there are three sources.** No accuracy figure above
  may be quoted without that, per `CLAUDE.md`.
- **The enrolment block is ~400 windows**, thinner than `rff_offline`'s default
  split. That tightens the ellipse and inflates the rejection column in §6, so
  the recall figures are a lower bound and the precision figures are the more
  robust of the two.
- **§4's time-vs-reboot comparison is not controlled** and is flagged as such
  in place.
- **Nothing here was pre-registered.** The sampling grid, the bins and the
  enrolment design were all chosen after the seven-night series was scored. A
  frozen version of §5 and §6 on a fresh capture is what would turn this from
  an observation into a result.

## 9. Reproducing it

```
python pc/sample_decay.py   <slice> --after A --before B --tag T --t T0   # sec.3
python pc/dump_windows.py   <slice> --after A --before B --tag T --out X  # sec.5-6
python pc/exp_decay.py                                                   # sec.3-4
python pc/exp_decay_accuracy.py                                          # sec.5-6
```

Sample points in `data/cache/decay/decay.jsonl`; per-window enrolment blocks in
`data/cache/decay/enr/`.
