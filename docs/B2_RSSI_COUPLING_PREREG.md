# B2 RSSI-COUPLING PREREG — does one beacon's clock reading track its own received power?

> **STAGE 1. Written 2026-08-29, before the held-out data was analysed.**
> The discovery set (§2) has been seen. **The held-out set (§3) has not been
> swept and no number from it exists yet.** Nothing above the Stage 2 banner
> in §9 may be edited once the held-out sweep starts.

---

## 1. Where this came from, stated plainly

`pc/exp_corpus_sweep.py` was run as an **exploratory** pass over the corpus.
Exploratory output generates hypotheses and never confirms one
(`.astory/ERROR_LOG.md` mode K). This document is that hypothesis, written down
so it can be tested on data that did not produce it.

Within a fixed `(session, node, mac)` cell — position held constant — the
Pearson correlation between a window's SFO slope and its median RSSI:

| beacon | cells | median r | IQR | cells r < −0.3 |
|---|---:|---:|---|---:|
| **B2** `28:05` | 7 | **−0.672** | −0.77 … −0.37 | **6 / 7** |
| B1 `a4:f0` | 27 | −0.207 | −0.41 … −0.03 | 10 / 27 |
| B3 `f4:2d` | 13 | −0.112 | −0.32 … +0.26 | 4 / 13 |

**B3 is the cautionary one.** Pooled across sessions it reads **−0.759**; within
cells it reads **−0.112**. Almost all of B3's apparent coupling was position
moving RSSI and SFO together. B2's survives that split, which is why it is here
and B3 is not.

**Why it matters if it's real:** a quartz oscillator's frequency offset has no
mechanism by which it should depend on how much of its own signal arrives at a
receiver, at a fixed position, within one session.

---

## 2. Discovery set — already seen, never to be used as evidence

The **40 capture files swept before this document was written**, being the 40
smallest non-empty captures. Predominantly July `desk` / `node3` / `occ` /
`rx` sessions. 12,979 windows, 6 MACs, 28 sessions.

**No number from these files may be quoted in support of H1.** They generated
it.

## 3. Held-out set — not yet swept

The **47 remaining non-empty captures, ~50.8 GB**, being every capture not in
§2. These are the larger sessions, predominantly August `s3` / `d0wd`.

**At the time of writing, `data/cache/sweep/` contains parquet for the §2 files
only.** The held-out files have never been through the DSP in this project's
history with RSSI and SFO in the same table.

---

## 4. Hypothesis and frozen thresholds

Cells are `(session, node, mac)` groups with **≥ 50 accepted windows**, raw, no
reference correction, shipped gates (`window=64`, `min_inlier=0.6`,
`max_resid=0.8`), correlation over `sfo` vs `rssi`.

**H1 — B2 couples.** On held-out cells, B2's **median within-cell r ≤ −0.30**
AND **≥ 60% of B2 cells have r < −0.30**.

**H2 — it is specific to B2, not the pipeline.** On the same held-out cells,
**B1 and B3 median within-cell r are each > −0.30.**

> **If all three beacons come back strongly negative, H1 is not supported even
> if its own numbers pass.** That pattern says the coupling is a property of the
> estimator, not of B2, and §5 gives the mechanism it would most likely be.

**H3 — permutation control.** Within each held-out cell, shuffle `rssi` across
windows and recompute. **Median shuffled |r| < 0.10.** If the shuffle also
produces strong correlation, the statistic is broken and H1 and H2 are both
void.

---

## 5. The instrumental explanation, named before it can be ignored

**Low RSSI means fewer inliers means a worse slope fit.** If the RANSAC phase
fit degrades as signal weakens, SFO and RSSI would correlate through the
estimator with no physics involved at all. This is the leading alternative and
it is not exotic.

It is testable with columns already in the sweep table: `n_frames` and
`quality` per window. **If the correlation survives conditioning on those, the
instrumental account weakens. If it vanishes, that is the answer.** Recorded as
a required follow-up, not as a prediction with a bar.

---

## 6. Verdict table — frozen

| outcome | condition |
|---|---|
| **COUPLING SUPPORTED** | H1 holds, H2 holds, H3 holds |
| **PIPELINE ARTIFACT** | H1 holds but H2 fails — all beacons couple |
| **NOT SUPPORTED** | H1 fails |
| **VOID** | H3 fails — the statistic does not survive its own control |

Anything else is reported as **MIXED**, in that word.

## 7. What this cannot answer

- **Seven discovery cells.** The effect may not survive contact with more data,
  and that is the expected outcome for most exploratory findings.
- **It says nothing about which beacon is "special."** B2 is `28:05:a5:2f:fa:48`
  and it is the unit that was mains-powered on 2026-08-28 and hardwired on
  2026-08-29. **Power source is confounded with beacon identity across much of
  this corpus** and this test does not separate them.
- Nothing here touches `SEVEN_NIGHT_PREREG`, `FAN_AB_PREREG`,
  `ROOM_OR_RADIO.md`, or any figure on the portfolio site.

## 8. Command

```
python pc\exp_corpus_sweep.py --out data\cache\sweep
```

Resumable; it skips files already written, so running it completes the held-out
set without re-touching §2.

## 9. Stage 2 — results

> **Nothing below this line existed when §1–§8 were written.**

Held-out sweep completed 2026-08-29 17:06. All 47 held-out captures processed,
**113 cells** at n ≥ 50.

## VERDICT: NOT SUPPORTED

### 9.1 H1 — FAILS

| beacon | cells | median r | frac r < −0.30 | bar |
|---|---:|---:|---:|---|
| **B2** | 34 | **−0.273** | **47%** | needed ≤ −0.30 **and** ≥ 60% |
| B1 | 47 | −0.226 | 43% | — |
| B3 | 32 | **−0.435** | 53% | — |

**B2 misses both halves of its own bar.** −0.273 is short of −0.30; 47% is short
of 60%.

**The discovery estimate was −0.672 on 7 cells. Held out, on 34 cells, it is
−0.273.** That is textbook overfitting to a small discovery set, and §7 named it
as the expected outcome before the test was run.

### 9.2 H2 — FAILS, and it fails in the most informative direction

H2 required B1 and B3 to stay above −0.30. **B3 comes in at −0.435 — stronger
than B2.**

In discovery B3 read −0.112 and was explicitly set aside as the cautionary
example of a position confound. On held-out data it is the most strongly coupled
beacon of the three. **The ordering did not survive.** Nothing about this
coupling is specific to B2, which was the entire hypothesis.

### 9.3 H3 — HOLDS

Median |r| with RSSI shuffled within each cell: **B2 0.0092, B1 0.0168,
B3 0.0084**, against a bar of 0.10. The statistic is sound. The correlation in
§9.1 is real; it is just not what H1 said it was.

### 9.4 §5's instrumental explanation is supported

Splitting each cell at its median `quality` and recomputing:

| beacon | quality **low** half | quality **high** half |
|---|---:|---:|
| B2 | **−0.232** | **+0.055** |
| B3 | **−0.175** | **+0.023** |
| B1 | +0.009 | +0.002 |

**The correlation exists only where the phase fit is poor. In the good half of
every cell it is zero.**

That is exactly the mechanism §5 named before any held-out data was seen: weak
signal → fewer RANSAC inliers → a worse slope estimate. **The estimator
degrading, not the oscillator moving.** No physics required and none implied.

*(`n_frames` turned out to be useless for this — it is fixed at the window size
of 64 for every row. The first attempt at this check split on it and produced
one bin. Recorded because a check that silently produces one bin looks like a
result.)*

### 9.5 What this closes and what it opens

**Closed:** B2 is not special. There is no beacon-specific RSSI coupling. Nothing
here supports a physical mechanism, and no number from §9 belongs on the
portfolio or in `ROOM_OR_RADIO.md`.

**Opened, and worth its own pre-registration:** the SFO estimate is **measurably
unreliable at low fit quality**, in a way that correlates with received power.
Every figure this project has produced pools windows across all quality levels.
Whether the headline results move when restricted to high-quality windows is a
real question, it is cheap to ask now that the sweep table exists, and it is
**not** answered here.

### 9.6 The method note

The hypothesis came from 7 cells and looked strong. It was frozen before the
held-out data was analysed, tested on 113 cells, and did not survive. **This is
the pre-registration working, not failing** — the alternative was a −0.672
finding written up from the data that produced it.
