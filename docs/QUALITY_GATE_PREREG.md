# QUALITY GATE PREREG — do the headline figures survive a fit-quality filter?

> **STAGE 1. Written 2026-08-29, before any gated figure was computed.**
>
> **This is not a blinded test and does not pretend to be.** The ungated
> figures are already known and quoted throughout this repo and on a public
> site. What is frozen here is every **analysis choice** — which figures, which
> threshold, what counts as moved — made before running any of them, so the
> threshold cannot be tuned until the answer looks good.

---

## 1. Why

`B2_RSSI_COUPLING_PREREG.md` §9.4 found that the SFO–RSSI correlation exists
**only in the low-fit-quality half of every cell** and vanishes in the high half:

| beacon | quality low | quality high |
|---|---:|---:|
| B2 | −0.232 | +0.055 |
| B3 | −0.175 | +0.023 |
| B1 | +0.009 | +0.002 |

That says the slope estimate is measurably less trustworthy when the phase fit
is poor. **Every figure this project has produced pools windows across all
quality levels**, from the shipped floor of 0.60 up to 0.998.

If the headline numbers move under a quality gate, they were partly a statement
about fit quality rather than about clocks or rooms.

## 2. The threshold, chosen now and for a stated reason

**Primary gate: `quality ≥ 0.90`.**

Chosen because it is a round number near the top of the observed range
(0.620–0.998) and because it is **not** any value already used in the pipeline —
the shipped `min_inlier` floor is 0.60, so 0.90 cannot be accused of being the
gate that happened to work. It was picked before any gated figure was computed.

**Sensitivity, declared now and reported whatever they show: 0.80 and 0.95.**
All three are reported in §5. **Reporting only the flattering one is the
failure this section exists to prevent.**

## 3. The figures under test — named before running

Raw, no `--ref-mac`, both receivers computed independently, same windows as
originally published.

| # | figure | ungated value | source |
|---|---|---|---|
| F1 | B2–B3 co-located, 2026-08-28, 2400–4700 s | **0.7σ** (s3) / **0.2σ** (d0wd) | `COLOCATED_TX_0828.md` §2 |
| F2 | B2–B3 night 1, 2026-08-29, 2400–4700 s | **9.2σ** (s3) / **6.8σ** (d0wd) | `SEVEN_NIGHT_PREREG` §10 |
| F3 | B3 raw SFO, bedroom vs kitchen | **+0.0552** → **+0.0087** = 19.6σ | `ROOM_OR_RADIO.md` §6.2 |
| F4 | cross-receiver disagreement, B3, co-located vs separated | **0.0001** vs **0.0504** | `ROOM_OR_RADIO.md` §6.3 |

F1 is the load-bearing same-instant result on the portfolio page. F3 is its
headline stat.

## 4. What counts as moved — frozen

For each figure, on each receiver:

- **HOLDS** — gated value within **±30%** of ungated, and no verdict that
  depends on it changes (F1 stays under 1.0σ; F2 stays over 1.0σ).
- **MOVED** — outside ±30% but the direction of the claim survives.
- **BROKEN** — the claim it supports no longer holds. F1 rising above 1.0σ, F2
  falling below it, F3 dropping under the 2.5–4.9σ drift floor, or F4's ratio
  falling below 10×.
- **UNEVALUABLE** — fewer than 50 windows survive the gate for a required
  source. **Recorded as unevaluable, never as a null.**

## 5. Required reporting

All three thresholds for all four figures, both receivers, in one table,
**including the ones that make the project look worse.** Window counts before
and after gating for every cell, so a figure that "held" on 12 surviving
windows is visibly not the same as one that held on 900.

## 6. What this cannot do

- **It is not blinded.** The ungated numbers are known to the analyst. The
  defence is that §2–§4 were fixed first, not that anyone was ignorant.
- It does not re-run any classification accuracy, only the separations and raw
  values named in §3.
- **It cannot tell you which value is "right."** A gated figure is a different
  measurement on a different subset, not a corrected version of the ungated one.
- Nothing here licenses editing `ROOM_OR_RADIO.md` or the portfolio. If a
  figure breaks, that is a finding to write down, and what to publish is a
  separate decision made afterwards.

## 7. Stage 2 — results

> **Nothing below this line existed when §1–§6 were written.**

### 7.0 Two deviations from §2, both recorded before any verdict

**1. The gate used is `--min-inlier`, not a window-level `quality` filter.**
§2 froze a gate on window-mean quality. `quality` is `mean(inlier_ratio)`
(`pc/rff/dsp.py:194`) and the pipeline's own knob on that quantity gates **per
frame**. Same underlying measure, different level. `--min-inlier` was chosen
because it keeps the entire computation inside shipped code — see §7.0.2 for
why that mattered.

**2. A first attempt was void and is recorded rather than deleted.** The
separations were initially recomputed in a standalone script, slicing time on
`ts_us` — the node-local wifi clock — while `rff_offline` slices on
`pc_time_us`. Different clocks, different window sets. **The ungated values came
out 0.44σ and 1.41σ against published 0.7σ and 6.8σ.** Caught by checking the
ungated column against the published figures *before* looking at any gated
value. Every number from that attempt is discarded.

**3. s3 runs are on a byte-sliced copy of the window**, because the 1.9 GB file
exceeds the available run time. Slicing resets the unwrap continuity anchor, so
s3's shipped-gate value reads **0.6σ against a published 0.7σ**. Within-slice
comparisons are internally consistent; the cross-comparison to published carries
that 0.1σ offset. d0wd was run on the full file and reproduces exactly.

### 7.1 F1 — B2–B3 co-located, 2026-08-28, 2400–4700 s

| receiver | shipped gate 0.60 | gate 0.90 | change |
|---|---:|---:|---|
| d0wd | **0.2σ** *(reproduces published exactly)* | **1.9σ** | **9.5×** |
| s3 | **0.6σ** *(published 0.7σ, see 7.0.3)* | **1.0σ** | 1.7× |

**VERDICT: BROKEN on d0wd. Borderline on s3.**

§4 defines BROKEN for F1 as rising above 1.0σ. d0wd goes to 1.9σ — clearly
above. s3 lands exactly on 1.0σ, which is the boundary and is reported as such
rather than rounded to either side.

**The pair ordering also inverts on d0wd.** At the shipped gate B2–B3 is the
closest pair at 0.2σ, with B2–B1 at 2.3σ and B1–B3 at 2.1σ. At gate 0.90 the
closest pair becomes **B1–B3 at 0.4σ**, while B2–B3 opens to 1.9σ.

On s3 the ordering survives — B2–B3 stays smallest at 1.0σ against 5.5σ and
6.5σ — so the qualitative story holds on one receiver and not the other.

### 7.1a CORRECTION — the verdict above is wrong, and the pooled count hid why

The line originally written here read *"Window counts are not marginal. d0wd:
5,039 → 3,154 windows, 63% surviving. This is not a small-sample artifact."*

**That 63% is pooled across all three beacons and conceals the only thing that
matters.** Per beacon, d0wd, same window:

| beacon | windows at 0.60 | windows at 0.90 | lost |
|---|---:|---:|---:|
| **B2** | **1,521** | **61** | **−96%** |
| B3 | 2,074 | 2,074 | **0%** |

**The gate does not filter B2 and B3 alike. It annihilates B2 and leaves B3
untouched.** Nearly every B2 window sits below 0.90 quality; essentially no B3
window does.

So the 1.9σ is **61 windows of B2 against 2,074 of B3** — not a quality-gated
version of the same measurement. B2's median also shifts (+0.00854 → +0.00651)
while its spread *triples* (sd 0.00134 → 0.00276), which is what a surviving
unrepresentative remnant looks like.

**Corrected verdict for F1: UNEVALUABLE at gate 0.90 on d0wd.**

§4 sets the unevaluable bar at fewer than 50 surviving windows. B2 has 61 — it
clears the letter of the rule and violates its purpose, which is a defect in
§4's wording, not a licence to report 1.9σ. **A 25:1 imbalance in surviving
windows is not a like-for-like comparison and no separation computed across it
means anything.**

**The finding that survives is different and smaller:** B2's windows are almost
entirely low-quality on this receiver and B3's are almost entirely high-quality.
That asymmetry is real, was not previously known, and is worth its own
question — but it is not evidence that the boards are distinguishable.

**How this was caught:** by checking per-beacon window counts after the verdict
was written, not before. The pooled 63% was quoted as reassurance in the same
document that exists to stop exactly that. Logged in `.astory/ERROR_LOG.md`.

### 7.1b THE §7.1a WINDOW COUNTS DO NOT REPRODUCE — opened 2026-08-31

§7.1a overturned the BROKEN verdict to UNEVALUABLE on the strength of one
table. **That table does not reproduce.** Re-run on 2026-08-31, twice, on the
same file and the same window:

| beacon | 0.60 | 0.90 measured | §7.1a claims | claimed loss | measured loss |
|---|---:|---:|---:|---:|---:|
| B2 `28:05` | 1,521 | **646** | 61 | −96% | **−58%** |
| B3 `f4:2d` | 2,073 | **2,005** | 2,074 | 0% | **−3.3%** |
| B1 `a4:f0` | 1,444 | **502** | *not stated* | — | **−65%** |

Reproduce, ~2 minutes:

```
python pc\rff_offline.py data\raw\d0wd_20260828_022627.csv ^
       --after 2400 --before 4700 --min-inlier 0.9
```

Run both on the full 1.55 GB file and on a byte-sliced copy with a 500 s
lead-in. **Both give 646 / 2,005 / 502, identical to every digit**, so slicing
is not the difference.

**Everything in §7.1 does reproduce, exactly.** Ungated B2–B3 0.2σ, gated
1.9σ, and the pair-ordering flip to B1–B3 at 0.4σ. The measurement is sound.
It is only the per-beacon counts underneath the retraction that are wrong.

#### What that does to the verdict

§7.1a's argument was: *"the 1.9σ is 61 windows of B2 against 2,074 of B3 — a
25:1 imbalance, and no separation computed across it means anything."*

**The real ratio is 646 : 2,005, which is 3.1 : 1.** §4 sets the unevaluable
bar at fewer than 50 surviving windows; B2 has 646. §7.1a also states B2's
spread *tripled* (sd 0.00134 → 0.00276); measured, its IQR **tightens**,
0.0014 → 0.0011.

**So the stated grounds for UNEVALUABLE are gone.** On its face that returns
F1 to the §4 condition it originally met — BROKEN, F1 rising above 1.0σ.

**That is not recorded as the verdict here, and this section does not change
it.** Two reasons. First, a retraction built on numbers that do not reproduce
should not be replaced by a re-retraction written the same hour it was
noticed. Second, and more usefully: **B1 loses 65% of its windows, harder than
B2's 58%, and §7.1a never mentioned B1 at all.** A gate that removes roughly
two thirds of two beacons and 3% of the third is doing something to this
receiver that neither the original verdict nor its retraction accounted for,
and that is worth understanding before anything is called broken or not.

#### Where the wrong numbers plausibly came from

§7.0.2 records a first attempt that sliced on `ts_us` instead of `pc_time_us`,
was declared void, and whose figures were "discarded." The §7.1a table has the
shape of output from a different window than the one it names. **This is a
hypothesis and has not been tested** — the voided run's numbers were not kept,
so there is nothing to compare against. It is written down as the only
candidate, not as a finding.

#### How this was caught

Not by re-reading the document. By re-running F1 on 2026-08-31 for an
unrelated reason and noticing the counts disagreed with what was on paper.
**§7.1a had stood unchallenged for two days and is itself a correction** — the
second one in this file. A document that exists to catch this kind of error
produced one, and then held it long enough to be quoted.

Mode H in `.astory/ERROR_LOG.md`: superseded artifact asserted as current. The
general form here is narrower and worth stating on its own — **a correction
inherits no authority from being a correction.** It needs the same
re-derivation as the thing it corrects.

#### Open

- F1's verdict is **unresolved**. Not UNEVALUABLE, not confirmed BROKEN.
- Why the 0.90 gate removes ~60% of B1 and B2 on d0wd and ~3% of B3 is
  unexplained, and is the same receiver and the same shape of asymmetry as
  `SEVEN_NIGHT_PREREG.md` §10's yield finding. **Whether they are the same
  phenomenon is not established and must not be assumed.**
- F2, F3 and F4 remain uncomputed under any gate, as §7.3 already says.

### 7.2 What this means, stated narrowly

**The claim "two physically different boards four feet apart are statistically
indistinguishable" depends on which windows are included.** At the shipped
inlier floor they are indistinguishable. At a raised floor, on one of two
receivers, they are not, and a different pair becomes the close one.

**This does not show the room conclusion is wrong.** It shows the headline
figure supporting it is gate-dependent, which was not previously known and is
not stated anywhere the figure is quoted — including the portfolio.

### 7.3 Not yet run

**F2, F3 and F4 have not been computed under any gate.** They are named in §3
and remain open. Nothing about them is implied by §7.1.

**No file outside this document has been edited.** Per §6, a broken figure is a
finding to write down; what to publish is a separate decision, not taken here.
