# WEATHER_COVARIATE — does outdoor temperature explain the cross-session SFO drift?

**Stage 1 (everything above the `STAGE 2` banner) was written and saved
before any weather byte was fetched and before any capture was replayed.**
Nothing above the banner is edited once results exist. If a Stage-1
statement turns out to be wrong it is corrected *below* the banner with the
original left standing. If, after seeing results, I am tempted to add a
hypothesis or reword a prediction, the temptation is recorded in §9 instead
of acted on.

---

## 0. The question, and why it is being asked now

`docs/IDENTITY_STABILITY.md` §15 found that on receiver block **R3**
(`node_id 68`, six `rx_*` sessions, 2026-07-14 → 2026-07-23) the
within-minus-cross accuracy gap **grows with elapsed wall-clock between the
two sessions: Spearman ρ = +0.604, p = 0.017, n = 15 unordered pairs.**
Something varies across days.

`docs/THERMAL_EVIDENCE.md` exists because a previous task asserted thermal
causation without evidence. Its standing note is that **no temperature was
ever recorded anywhere in this project**, and
`docs/IDENTITY_STABILITY.md` §16 confirms there is no temperature column in
either the 10-column era-A schema or the 13-column era-B/C schema. So no
internal thermal covariate can be recovered from data already collected.

**Outdoor weather is the only temperature-like covariate that exists
retroactively for captures already on disk.** It is a poor proxy (§7) but it
is a real, independently recorded, time-resolved external variable, and it
costs nothing to test. This document tests it.

**This document does not measure temperature at any device.** It measures a
correlation against outdoor air temperature at one airport station. No
thermal causation is asserted anywhere below, and a positive result would
establish association, not mechanism.

## 1. Data sources

### 1.1 Weather

IEM ASOS archive, station **`OJC`**, variable `tmpf` (dry-bulb air
temperature, °F), for **2026-07-12 → 2026-08-24** — the full span
`data/raw/` covers, fetched in chunks because a single long request fails.
`relh` and `mslp` are fetched only if needed and only as separate requests.

**The station is referenced as `OJC` and nothing else.** No distance, no
bearing, no cross-streets, no derivation of why this station was chosen, in
this document or in the script. The repo is intended to become public.

Two properties of this feed, verified by the operator before this document
was written and re-verified in §8 by the script:

- **`OJC` reports temperature once per hour, at :53.** Every intervening
  5-minute row is `M`. **`M` rows are dropped, never interpolated.** The
  effective sampling rate of the covariate is **one point per hour**, and
  every power statement below is made at that rate, not at the row rate of
  the raw feed.
- **The timestamps are UTC.**

### 1.2 Captures

The three receiver blocks from `docs/IDENTITY_STABILITY.md` §1.1 that have a
real (N = 3) class set. Blocks are taken **verbatim** from that document and
not re-derived here:

| block | files | note |
|---|---|---|
| **R3** node 68 July | `rx_20260714_011619`, `rx_20260714_030915`, `rx_20260714_031131`, `rx_20260715_201703`, `rx_20260722_204658`, `rx_20260722_XXXXXX` | the block that produced ρ = +0.604 |
| **R4** node 68 August | `desk_20260821_125017`, `d0wd_20260822_023034`, `d0wd_20260822_144424`, `d0wd_20260822_235739`, `d0wd_20260823_013537`, `d0wd_20260823_014740` | spans the 08-22 remount |
| **R5** node 108 August | `s3_20260821_125017`, `s3_20260822_023034`, `s3_20260822_144424`, `s3_20260822_235739`, `s3_20260823_013537`, `s3_20260823_014740` | spans the 08-22 remount |

R1 `desk` and R2 `node3` (era A) are **excluded**: R2 has N = 1 and is
unscorable, and R1's class set is N = 2 with a 45 : 1 imbalance
(`IDENTITY_STABILITY` §10, §11). Excluding them is a design choice made now,
before any result, and it costs 15 sessions of temperature range.

Devices are the three beacons `a4:f0:0f:77:91:20`, `f4:2d:c9:70:72:30`,
`28:05:a5:2f:fa:48` — which, per `IDENTITY_STABILITY` §10, are the entire
class set on all three blocks anyway, because no ambient device clears the
10-window floor in two sessions on any of them.

### 1.3 The time-zone conversion, stated explicitly

Getting this wrong shifts every join by five hours and manufactures a
confident fake result, so it is written out rather than assumed.

- **`OJC` timestamps are UTC.**
- **Capture filenames are local time**, and local is **UTC−5**
  (`docs/THERMAL_EVIDENCE.md` §5, confirmed there two independent ways).
- **`pc_time_us` is Unix-epoch microseconds, i.e. already UTC.**
  `THERMAL_EVIDENCE` §5 records that `desk_20260713_104513.csv`'s first
  `pc_time_us` reads **15:45:14 UTC** against a filename of `104513` —
  which is the same fact as "filename is local, `pc_time_us` is epoch".

**Therefore the join is done on `pc_time_us` interpreted directly as UTC,
and no ±5 h arithmetic is applied to it at all.** The filename is used only
as a session label. This is deliberately the route with the fewest
conversions in it.

Two checks the script must pass before any correlation is computed, both
reported in §8 whatever they say:

1. **Feed check** — on 2026-08-22, the coolest `OJC` reading of the day must
   land at **10:53 UTC** and the warmest at **20:53 UTC** (= 05:53 and 15:53
   local). A diurnal minimum at 05:53 local and maximum at 15:53 local is
   the only reading consistent with an outdoor air temperature. If the
   extremes land elsewhere, the UTC assumption is wrong and **the analysis
   stops**.
2. **Capture check** — for every session, `datetime.utcfromtimestamp(first
   pc_time_us / 1e6)` minus 5 h must reproduce the filename's `HHMMSS` to
   within a few seconds. If any session fails, that session is dropped and
   the failure is reported; if more than one fails, the epoch assumption is
   wrong and **the analysis stops**.

## 2. Signal extraction — the pipeline is held fixed

- **`pc/rff/dsp.py` is not modified.** `FrameEstimator` and
  `WindowAggregator` are used exactly as shipped, window **64**,
  `min_inlier_ratio = 0.6`, `max_resid = 0.8` (`dsp.py:164`).
- **`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py`
  are not used** — `docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 has the DC/guard
  index wrong in all three.
- **Every stream is replayed from the start of its file with a fresh
  estimator**, one per (file, source-MAC), with no window, filter or
  subsample in front of it. `ransac_line` draws from a per-instance RNG that
  advances once per fitted frame (`dsp.py:118,132`; `docs/V2_SPEC.md` §5.5),
  so a replay that does not begin at byte one is not comparable to one that
  does.
- **Corrupt rows are screened before the estimator and before any delta
  arithmetic**, by both routes `docs/COLOCATED_0823.md` §1 requires: field
  plausibility, and a width-9 circular median filter on `dropped` compared
  mod 65536. All three blocks here are 13-column, so **both** routes exist
  for all of them — unlike era A. The screen counts are reported in §8.
- **Row cap: the first 300,000 data rows of each file**, the same
  pre-registered cap `docs/IDENTITY_STABILITY.md` §1.6 used, kept identical
  so the SFO medians here are comparable to the ones there. It is a
  **subsample** and is labelled one everywhere.
- **A (session, device) cell is kept only if it yields ≥ 10 accepted
  windows** — `MIN_WIN = 10`, the same pre-registered floor. The floor is
  not lowered afterwards for any reason.
- **`raw` SFO (`obs['sfo']`) is primary**, matching
  `IDENTITY_STABILITY` §1.4. `ref` (`obs['sfo_ref']`) is reported as a
  secondary arm, with that document's §1.4 warning still in force: the
  reference beacon's own `ref` feature is ~0-centred per file by
  construction, so any `ref`-arm effect carried by `a4:f0:0f:77:91:20` alone
  is an artifact.
- Read-only on `data/raw/`. **No serial port is opened.** Nothing is staged
  or committed.

## 3. Temperature aggregation per session

For a session spanning `[t_start, t_end]` in UTC (from the first and last
surviving `pc_time_us`):

- **`T_mean`** = mean of the `OJC` :53 readings whose UTC timestamp lies in
  `[t_start, t_end]`. This is the primary regressor.
- **`T_span`** = max − min of those readings, reported so a "mean" over an
  8-hour capture is not silently treated as a point measurement.
- **`n_obs`** = how many readings fell inside. **Printed next to every
  cell.**
- If **`n_obs` = 0** (a capture shorter than an hour that misses :53), the
  single nearest reading in time to the session midpoint is used, `n_obs` is
  recorded as **0 (nearest, Δ = … min)**, and those cells are reported both
  in and out of the primary correlation. If dropping them changes the
  verdict, that is stated as the finding rather than resolved by picking the
  more convenient set.

## 4. The tests, and the statistic

All tests are **two-tailed**, and this is a commitment, not a formality.
Crystal frequency versus temperature for an AT-cut resonator is a cubic
about a turnover point; **the turnover temperature of these boards is not
recorded anywhere in this repo and no datasheet for them has been
retrieved**, so the sign of any real effect is genuinely unpredicted — a
device operating above turnover moves the opposite way from one below it,
and three boards need not be on the same side. **Claiming a sign here would
be inventing a fact.** No one-tailed test is run, and no sign is predicted
in §5.

Statistic throughout: **Spearman ρ**, with **p from 20,000 random
permutations**, matching the method `IDENTITY_STABILITY` §15 used.
(`scipy` is deliberately not imported: `CLAUDE.md` records that nothing in
the repo imports it and `pc/requirements.txt` does not carry it. The
permutation null is exact enough and needs no distributional assumption.)

### 4.1 Primary — per (device, session) median SFO vs session mean temperature

Cell = one (block, device, session). Value = **median SFO over that cell's
accepted windows**.

Beacons sit at different mean SFO, so a correlation pooled across devices
would be driven by between-device offsets rather than by temperature.
Therefore:

- **Primary statistic:** median SFO **de-meaned within (block, device)**,
  pooled over all cells, Spearman against `T_mean`. Pre-registered as the
  headline because it is the highest-n form.
- **Also reported, always:** the Spearman for **each (block, device)
  separately**, and for **each block** pooled — so a pooled result cannot
  hide a per-device disagreement.

### 4.2 Secondary — session-pair drift vs |ΔT|, and the partial correlation

Unordered session pairs within a block (ordered pairs duplicate every
|elapsed|, so unordered is primary, as in `IDENTITY_STABILITY` §2.3).

Two drift quantities, both computed, because they answer slightly different
questions and only one of them is the quantity that produced ρ = +0.604:

- **D1 — SFO-domain drift.** RMS over the pair's devices of
  `Δ_d = median SFO in B − median SFO in A`. This is
  `IDENTITY_STABILITY` §13's "total drift". It is the natural quantity for a
  temperature test because it lives in the same units as the thing a crystal
  would move.
- **D2 — the accuracy gap.** `within − cross`, same test windows, shipped
  `Discriminator`, 60/40 split, exactly `IDENTITY_STABILITY` §1.2. **This is
  the quantity ρ = +0.604 was measured on**, and it is recomputed here so
  the partial correlation is a re-test of that finding rather than of a
  cousin of it.

For each: Spearman against **|ΔT| = |T_mean(B) − T_mean(A)|**, and

> **partial Spearman of drift with elapsed wall-clock, controlling for
> |ΔT|** — rank-transform all three, then
> `ρ(D, E | T) = (r_DE − r_DT·r_ET) / sqrt((1 − r_DT²)(1 − r_ET²))`,
> p from 20,000 permutations of the residualised elapsed ranks.

**If elapsed time survives that control, weather is not the mechanism.**

**Pre-registered gate on the secondary test.** The partial correlation only
re-tests ρ = +0.604 if the zero-order Spearman(drift, elapsed) reproduces
that finding in this run. If **Spearman(D2, elapsed) on R3 does not come
back positive and comparable to +0.604**, then this pass has not reproduced
the phenomenon and the partial correlation is uninformative about it —
**that will be stated as the result, and the partial will not be presented
as having ruled anything in or out.**

### 4.3 Scope limit — within-session drift is NOT tested against this data, deliberately

`OJC` yields **one temperature per hour**. `IDENTITY_STABILITY` §12 found
devices moving **6.3×** and **9.4×** the entire between-device spread
*inside a single session*, on a timescale of tens of minutes, and found the
within-session ceiling itself broken (53–61 % on N = 3).

**An hourly outdoor reading cannot speak to movement happening in minutes.**
Running that regression would produce a number, and the number would be
uninterpretable at best and a false null at worst. It is therefore **not
run**, and this is recorded here in advance so its absence later reads as a
scope limit rather than as an omission. §12 remains, per
`IDENTITY_STABILITY` §20 item 3, the thing to chase — and it needs a
per-frame thermometer, not this.

### 4.4 The 2026-08-22 remount

`docs/COLOCATED_0823.md` §0 and §5.5: both receivers were remounted onto the
same wall on 2026-08-22, moving position *and* separation at once. The
boundary is between `*_20260822_235739` and `*_20260823_013537`.

**Any R4 or R5 session pair straddling that boundary is not a controlled
comparison.** Straddling pairs are excluded from the secondary test's
headline and reported separately. The **primary** test is a per-cell
regression, not a differencing one, so a remount does not invalidate a cell
— but it does change the receiver's own conditions between cells, and R4/R5
primary figures are therefore flagged wherever they appear.

## 5. Predictions — frozen, and no sign claimed

Written before any fetch or replay. **No direction is predicted for any
correlation** (§4).

| # | prediction | why |
|---|---|---|
| **P1** | **Primary |ρ| will not clear the detection floor.** Point estimate |ρ| < 0.30. | `IDENTITY_STABILITY` §13: the per-device residual is **2.2×–7.1×** the entire between-device spread and the shared common-mode component removes only **7–46 %** of drift energy. Outdoor air temperature is **one scalar shared by every device in the room by construction**, so it can only ever address the minority common-mode part. `THERMAL_EVIDENCE` §6 points the same way from the other side: two receivers hearing the same beacon in the same minutes have essentially uncorrelated trajectories (median r −0.14), so the dominant movement is per-(receiver, device) and no single environmental regressor can carry it. |
| **P2** | **Secondary: |ρ(D1, \|ΔT\|)| and |ρ(D2, \|ΔT\|)| will not clear the floor.** | Same reason, plus |ΔT| between two sessions is a difference of two hour-resolution means over captures of very different length. |
| **P3** | **Elapsed time will survive the control.** Partial ρ(D2, elapsed \| \|ΔT\|) will stay within **±0.15** of the zero-order ρ(D2, elapsed). | If P1 and P2 hold, |ΔT| explains little of either variable and partialling it out cannot move much. Stated as a number so it can be scored. |
| **P4** | **D1 will reproduce the positive elapsed relationship on R3** (ρ > 0), even though D1 is not the quantity §15 measured. | `IDENTITY_STABILITY` §13 shows R3's total drift is real and §15 shows the gap grows with elapsed; a drift measure in the SFO domain should track it. **If P4 fails, §4.2's gate fires.** |
| **P5** | **The honest verdict will be "underpowered to exclude a moderate effect", not "weather is excluded."** | §6. Even at the pooled cell count, the number of **independent temperature values** is the number of distinct wall-clock sessions, and that is **12**, not 54 — R4 and R5 are the *same six wall-clock sessions* recorded by two receivers, so their temperature values are literally the same numbers used twice. |
| **P6** | **A null here will not exclude an indoor thermal mechanism**, and the document will say so in those words. | §7. |

**What would falsify P1 in the direction that matters:** a primary |ρ| above
the §6 floor *with the same sign across all three beacons and all three
blocks*. Sign consistency is required because `THERMAL_EVIDENCE` §5's
time-of-day result is uninterpretable precisely because its sign flipped
between feature spaces and receivers, and this document must not create a
second such artifact. **A significant |ρ| whose sign flips across devices or
blocks will be reported as sign-inconsistent and not as a thermal
finding** — even though, per §4, a genuine AT-cut effect *could* legitimately
flip sign between boards on opposite sides of turnover. That ambiguity is
unresolvable with three boards and is recorded here so it cannot be
resolved conveniently later.

## 6. Detection floor — computed before the data existed

The floor is the |ρ| exceeded by 5 % of random permutations at each n
(200,000 permutations per row, two-tailed α = 0.05, seed 20260823). **Below
the floor, the test cannot distinguish a real effect from noise; it is not
evidence of absence.**

| n | detection floor \|ρ\| |
|---:|---:|
| 6 | 0.829 |
| 7 | 0.750 |
| 8 | 0.714 |
| 9 | 0.683 |
| 10 | 0.636 |
| 12 | **0.580** |
| 14 | 0.534 |
| 15 | **0.518** |
| 16 | 0.500 |
| 18 | 0.470 |
| 20 | 0.447 |
| 24 | 0.404 |
| 30 | 0.362 |
| 36 | 0.330 |
| 45 | 0.294 |
| 54 | **0.268** |

**The two numbers that matter, and they disagree on purpose:**

- At the **nominal** pooled cell count (up to 3 blocks × 6 sessions ×
  3 devices = **54**), the floor is **0.268**.
- At the **effective** count — **12 distinct wall-clock sessions**, because
  R4 and R5 share all six of theirs and the three beacons in one session
  share one temperature — the floor is **0.580**.

**The honest floor for a temperature effect is the effective one, ≈ 0.58,
and it is quoted as the headline floor.** A pooled |ρ| of, say, 0.35 would
clear the nominal floor and mean nothing, because the 54 cells carry at most
12 independent values of the regressor. Writing this down now is the whole
point of Stage 1: it prevents the n = 54 floor being quoted later because it
is the one that gives a significant answer.

Consequence, accepted in advance: **this test can only detect a strong
effect (|ρ| ≳ 0.58).** A moderate one (|ρ| ≈ 0.3–0.5) is invisible to it.
If the result is null, the correct statement is "no strong effect detected,
moderate effects not excluded", and that is what will be written.

## 7. Standing limitations of the covariate itself

Stated now so they are not produced later as excuses.

1. **Outdoor air temperature is not device temperature.** The boards are
   indoors. The building envelope attenuates and lags outdoor swings, and
   HVAC actively opposes them — a hot afternoon can make an indoor room
   *cooler*. **A null at outdoor temperature therefore does not exclude an
   indoor thermal mechanism**, and a positive would not establish one
   either. `docs/THERMAL_EVIDENCE.md` §8 item 1's per-frame die-temperature
   logging at *both* ends remains the only thing that settles it, and
   nothing in this document changes that.
2. **Self-heating is invisible here.** A crystal's temperature is set partly
   by its own die dissipation and duty cycle, which no outdoor reading sees
   at all.
3. **One reading per hour**, against sessions ranging from minutes to hours.
4. **The station is not the site.** `OJC` is a separate location with its own
   microclimate.
5. **`T_mean` and elapsed time are not independent regressors.** Sessions
   hours apart differ diurnally; sessions days apart differ synoptically.
   Partialling one out of the other with 12 independent sessions is a weak
   operation and the partial correlation is reported with that attached.
6. **This is `data/raw/` re-analysed, not a designed experiment.** It cannot
   become one retroactively.

## 8. Checks the run must report regardless of outcome

- The §1.3 feed check (08-22 extremes at 10:53 / 20:53 UTC) — pass or fail.
- The §1.3 capture check (`pc_time_us` vs filename) for every session.
- `M`-row counts dropped per fetch chunk, and the count of usable :53 rows.
- Field-screen and median-filter reject counts per file.
- Windows and rows per (session, device) cell, and every cell dropped by
  `MIN_WIN`.
- `pc/rff/dsp.py`'s mtime, unchanged, before and after.
- `git diff --cached --name-only` empty before and after.

## 9. Temptation register

Kept empty until Stage 2. Anything I want to add, revise or reword after
seeing results goes here, unacted on.

## 10. Reproduce

One script, `pc/exp_weather_covariate.py`, read-only on `data/raw/`, no
serial port, nothing staged.

```
export WXC_CACHE=/tmp/wxc
python3 pc/exp_weather_covariate.py fetch                 # OJC tmpf -> data/weather_ojc_tmpf.csv
python3 pc/exp_weather_covariate.py extract <csv> --cap 300000   # per file, checkpointed
python3 pc/exp_weather_covariate.py analyze               # both tests
```

Fetched weather lands at **`data/weather_ojc_tmpf.csv`**. `.gitignore`
already carries a bare `*.csv` rule, so it is covered without editing that
file; this is verified in §11 rather than assumed. Scratch state goes to
`$WXC_CACHE`, outside the repo tree, and is removed at the end.

---
---

# STAGE 2 — results

*(appended after the run; nothing above this banner was edited)*

Run 2026-08-23. **18 capture files replayed, 4,049,349 data rows** through
`pc/rff/dsp.py` as shipped. `pc/rff/dsp.py` was not modified — its mtime is
still **2026-07-13 20:42:46**, the value `docs/COLOCATED_0823.md` §1 and
`docs/IDENTITY_STABILITY.md` §Stage-2 both record. No serial port opened,
nothing under `data/raw/` written, nothing staged (`git diff --cached
--name-only` empty before and after), nothing committed or pushed.

## 11. Verdict

**Outdoor temperature does not explain the drift, and — unusually for a
null — the test was not merely underpowered to say so.** Two things carry
that:

1. **The `ρ = +0.604` finding was reproduced exactly**, from a fresh replay
   through an independent script: `docs/IDENTITY_STABILITY.md` §15 measured
   ρ = +0.604, p = 0.017, n = 15 on R3; this pass measures **ρ = +0.604,
   p = 0.020, n = 15**. The §4.2 gate therefore **passes** — the partial
   correlation below is a re-test of that finding, not of a cousin of it.
2. **Controlling for |ΔT| moves it by −0.007**, to **+0.597, p = 0.021**.
   Elapsed time survives the control essentially untouched. On the SFO-domain
   drift measure the same thing happens more strongly: **+0.796 → +0.796**,
   a shift of **−0.001**.

**Elapsed time survives controlling for temperature. Weather is not the
mechanism.**

The primary test is the weaker half and is honestly null-with-caveats: the
pooled figure is **ρ = −0.028 (p = 0.837, n = 54 cells)**, far below both
the nominal floor (0.268) and the effective floor (0.580). The one *block*
that clears its own nominal floor — R3, +0.477 raw / +0.592 ref at n = 18 —
is **sign-inconsistent** in exactly the way §5 pre-committed to
disqualifying, and is not reported as a thermal finding (§15.2).

**What this does not say:** the boards are indoors and `OJC` is outdoors
(§7.1). A null at outdoor air temperature does **not** exclude an indoor or
on-die thermal mechanism, and nothing here revises
`docs/THERMAL_EVIDENCE.md` §8 item 1 — per-frame die temperature at *both*
ends is still the only thing that settles it.

## 12. Predictions scored

| # | prediction | outcome | **verdict** |
|---|---|---|---|
| **P1** | primary \|ρ\| below floor, point estimate < 0.30 | pooled **−0.028**, \|ρ\| = 0.028 | **HELD** |
| **P2** | \|ρ(D1,\|ΔT\|)\| and \|ρ(D2,\|ΔT\|)\| below floor | R3 **−0.077** and **−0.126**, floor 0.518 | **HELD** |
| **P3** | partial stays within ±0.15 of zero-order | D2 shift **−0.007**, D1 shift **−0.001** | **HELD** |
| **P4** | D1 reproduces positive elapsed relationship on R3 | **+0.796, p = 0.001** | **HELD** |
| **P5** | verdict will be "underpowered", not "excluded" | **partly WRONG** — see below | **FAILED, and it failed in the useful direction** |
| **P6** | a null will not exclude an indoor mechanism, said in those words | §11 and §7.1 | **HELD** |

**P5 is the prediction that was wrong, and it is left standing rather than
reworded.** I predicted the honest verdict would have to be "underpowered
to exclude a moderate effect." That is right for the *primary* test and
wrong for the *secondary* one. I did not anticipate that the secondary test
would come back as strong as it did: because ρ(D2, elapsed) reproduces at
+0.604 and |ΔT| is nearly orthogonal to elapsed (ρ = −0.131, p = 0.636),
partialling |ΔT| out is a well-conditioned operation and its near-zero
effect is a real answer, not a power failure. §7.5 pre-registered the
worry that elapsed and temperature would be too collinear to separate; in
this corpus they are not, and that worry did not materialise. **The primary
test remains underpowered exactly as predicted.**

## 13. Checks the run was required to report (§8)

**Feed check — PASS.** On 2026-08-22 the coolest `OJC` reading is **71 °F,
first at 10:53 UTC**, and the warmest is **84 °F, first at 20:53 UTC** —
05:53 and 15:53 local, the shape an outdoor air temperature must have. The
UTC assumption holds.

**Reported honestly: both extremes are ties.** The minimum 71 °F also occurs
at 11:53 and 15:53 UTC, and the maximum 84 °F also at 21:53. The check was
pre-registered on `argmin`/`argmax` and those take the first occurrence, so
it passes as written — but 2026-08-22 was a **flat, 71–84 °F day**, and a
diurnal check on a flat day is weaker evidence than one on a swinging day.
It is corroborated independently by `docs/THERMAL_EVIDENCE.md` §5's two
confirmations of local = UTC−5.

**Capture check — 0 FAIL, 17 of 18 sessions verified, 1 skipped.**
`datetime.utcfromtimestamp(first pc_time_us / 1e6) − 5 h` reproduces the
filename `HHMMSS` to within **0–1 s** on every session that has one.
`rx_20260722_XXXXXX` has no timestamp in its filename to check against and
is recorded as **skipped, not passed** (`CLAUDE.md` failure mode **C**); its
first `pc_time_us − 5 h` reads 20:53:39, consistent with its position
immediately after `rx_20260722_204658`.

**The `pc_time_us` route means no ±5 h arithmetic entered the join at all**
(§1.3). The five-hour hazard the operator flagged was avoided by
construction rather than by getting the sign right.

**Weather feed.** 1,024 hourly readings, 2026-07-12 00:53 → 2026-08-23
16:53 UTC, range 65–98 °F. **8 hours across the 43-day span have no routine
report; they are dropped, not filled.** Every `M` row of the 5-minute grid
was dropped and none was interpolated.

**Two fetch ranges were refused at the approval prompt** and are recorded
rather than worked around: `…&day1=13&day2=18` (July) and
`…&day1=31&day2=8` (July→August). Both spans were then retrieved under
different day boundaries (`13→17` + `17→18`, and `31→4` + `4→8`), so **the
span has no hole from them**. No alternative retrieval route was attempted.

**Screening.** All 18 files are 13-column, so both routes ran on all of
them:

| block | sessions | rows analysed | field-screened | median-filter-screened | unparseable |
|---|---:|---:|---:|---:|---:|
| R3 node 68 July | 6 | 1,260,871 | 59 | 0 | 0 |
| R4 node 68 August | 6 | 1,395,913 | 81 | **1** | 0 |
| R5 node 108 August | 6 | 1,392,565 | 0 | 0 | 0 |

The single median-filter catch is on `d0wd_20260822_023034` — a row the
field screen passed and only the circular median filter rejected. **This
reproduces `docs/IDENTITY_STABILITY.md` §9 exactly**, row counts and all,
which is a useful check that this script's replay is doing the same thing
that one did.

**Cells dropped by `MIN_WIN`.** One: `28:05:a5:2f:fa:48` on
`rx_20260714_030915` yields **21 windows** in `raw` — above the floor, kept.
No beacon fell below 10 windows in any session in the `raw` arm. The floor
was not lowered.

## 14. The sessions and their temperature — and the first real limitation

| block | session | start UTC | prefix h | T_mean °F | n_obs |
|---|---|---|---:|---:|---|
| R3 | `rx_20260714_011619` | 07-14 06:16 | 0.59 | 74 | 0 (nearest, 19 min) |
| R3 | `rx_20260714_030915` | 07-14 08:09 | 0.04 | 73 | 0 (nearest, 17 min) |
| R3 | `rx_20260714_031131` | 07-14 08:11 | 0.59 | 70 | 0 (nearest, 24 min) |
| R3 | `rx_20260715_201703` | 07-16 01:17 | 0.60 | 82 | 1 |
| R3 | `rx_20260722_204658` | 07-23 01:46 | 0.09 | 75 | 0 (nearest, 3 min) |
| R3 | `rx_20260722_XXXXXX` | 07-23 01:53 | 0.65 | 75 | 0 (nearest, 20 min) |
| R4 | `desk_20260821_125017` | 08-21 17:50 | 0.60 | 86 | 1 |
| R4 | `d0wd_20260822_023034` | 08-22 07:30 | 0.60 | 73 | 1 |
| R4 | `d0wd_20260822_144424` | 08-22 19:44 | 0.54 | 83 | 1 |
| R4 | `d0wd_20260822_235739` | 08-23 04:57 | 0.44 | 70 | 0 (nearest, 18 min) |
| R4 | `d0wd_20260823_013537` | 08-23 06:35 | 0.09 | 68 | 0 (nearest, 15 min) |
| R4 | `d0wd_20260823_014740` | 08-23 06:47 | 0.62 | 68 | 1 |
| R5 | `s3_20260821_125017` | 08-21 17:50 | 0.54 | 86 | 1 |
| R5 | `s3_20260822_023034` | 08-22 07:30 | 0.55 | 73 | 1 |
| R5 | `s3_20260822_144424` | 08-22 19:44 | 0.54 | 83 | 1 |
| R5 | `s3_20260822_235739` | 08-23 04:57 | 0.44 | 70 | 0 (nearest, 18 min) |
| R5 | `s3_20260823_013537` | 08-23 06:35 | 0.09 | 68 | 0 (nearest, 15 min) |
| R5 | `s3_20260823_014740` | 08-23 06:47 | 0.52 | 68 | 1 |

**`T_span` is 0.0 on every single session, and `n_obs` never exceeds 1.**
That is not a bug and it was not anticipated in §3. The 300,000-row prefix
cap (§2, inherited from `IDENTITY_STABILITY` §1.6) reduces every analysed
session to **0.04–0.65 h**, and an hourly feed puts **at most one** :53
reading inside a window that short. So:

> **"Session mean outdoor temperature" is, in this run, a single hourly
> `OJC` reading** — the one inside the analysed prefix where there is one
> (9 of 18 sessions), and the nearest one **3–24 minutes** away otherwise
> (9 of 18). It is not a mean over a session and should not be called one.

The nearest-reading fallback is the §3 rule, invoked as written, and its
offsets are all well inside one hour. The §3 sensitivity check was run:
excluding all 27 nearest-fallback cells moves the pooled primary from
**−0.028 to −0.214 (p = 0.285, n = 27)** — still nowhere near the floor,
and still the opposite sign from the R3 result below. **The verdict does not
depend on which set is used**, which is what §3 asked to be checked.

**The temperature attributed to each session is the temperature of the
analysed prefix, not of the whole capture.** For the long files that is a
much smaller slice than the filename implies.

## 15. PRIMARY — median SFO vs temperature, per (device, session)

`raw` is primary (§2). **n = 54 cells: 3 blocks × 6 sessions × 3 beacons,
with no cell lost to the window floor.**

### 15.1 Pooled, de-meaned within (block, device) — the pre-registered headline

| arm | pooled ρ | p | n cells | nominal floor | **effective floor** |
|---|---:|---:|---:|---:|---:|
| **raw** | **−0.028** | 0.837 | 54 | 0.268 | **0.580** |
| ref | +0.206 | 0.135 | 54 | 0.268 | **0.580** |

**Null on both arms, against either floor.** The effective floor is the one
that governs, for the reason §6 pre-committed: the 54 cells carry only
**12 distinct wall-clock sessions** worth of temperature, because R4 and R5
are the *same six sessions* recorded by two receivers and the three beacons
within a session share one reading.

### 15.2 Per block, and the sign inconsistency

| block | raw ρ (p, n = 18) | ref ρ (p, n = 18) | floor at n = 18 |
|---|---|---|---:|
| **R3** node 68 July | **+0.477 (p = 0.045)** | **+0.592 (p = 0.011)** | 0.470 |
| R4 node 68 August | −0.048 (p = 0.854) | −0.089 (p = 0.731) | 0.470 |
| R5 node 108 August | −0.235 (p = 0.351) | +0.318 (p = 0.198) | 0.470 |

**R3 clears its nominal n = 18 floor in both arms. It is still not a thermal
finding, and §5 said so in advance.** Three reasons, in order of force:

1. **The sign flips between blocks.** R3 is positive, R4 is negative, R5 is
   negative in `raw` and positive in `ref`. §5's falsification criterion
   required "the same sign across all three beacons **and** all three
   blocks". It is not met.
2. **The sign flips between devices inside R3 itself, in the primary arm:**

   | block | device | raw ρ (n = 6) | ref ρ (n = 6) | floor at n = 6 |
   |---|---|---:|---:|---:|
   | R3 | `a4:f0:0f:77:91:20` | **−0.406** | **+0.696** | 0.829 |
   | R3 | `f4:2d:c9:70:72:30` | +0.754 | +0.754 | 0.829 |
   | R3 | `28:05:a5:2f:fa:48` | +0.812 | +0.812 | 0.829 |
   | R4 | `a4:f0:0f:77:91:20` | −0.029 | −0.174 | 0.829 |
   | R4 | `f4:2d:c9:70:72:30` | −0.406 | −0.058 | 0.829 |
   | R4 | `28:05:a5:2f:fa:48` | −0.058 | −0.203 | 0.829 |
   | R5 | `a4:f0:0f:77:91:20` | −0.116 | −0.435 | 0.829 |
   | R5 | `f4:2d:c9:70:72:30` | **−0.986 (p = 0.006)** | +0.058 | 0.829 |
   | R5 | `28:05:a5:2f:fa:48` | **+0.928 (p = 0.022)** | **+0.841 (p = 0.046)** | 0.829 |

   **Not one per-device cell clears its own n = 6 floor of 0.829** — the two
   that reach p < 0.05 do so at |ρ| = 0.986 and 0.928, i.e. they are
   essentially perfect monotone orderings of six points, which is what a
   six-point Spearman does when it does anything at all. And they are
   **opposite in sign, on the same receiver, in the same six sessions**:
   `f4:2d` at −0.986 and `28:05` at +0.928 on R5. Two devices sitting in the
   same room breathing the same air cannot both be right about the sign of a
   shared environmental driver. **That pair is the cleanest single
   demonstration in this run that six-point correlations here are noise.**
3. **The entire R3 raw→ref improvement is the pre-registered artifact.**
   `a4:f0:0f:77:91:20` moves from **−0.406 (raw) to +0.696 (ref)** while the
   other two beacons' values do not move at all (+0.754 and +0.812 in both
   arms). §1.4 warned in advance that the reference beacon's `ref` feature
   is ~0-centred per file by construction and that any `ref`-arm improvement
   carried by it alone is an artifact. **It is carried by it alone. It is an
   artifact, and it is labelled one.**

**This reproduces `docs/THERMAL_EVIDENCE.md` §5's shape and is reported as a
reproduction, not a discovery.** That document found time-of-day
"underpowered, not measured", with r flipping sign between feature spaces
and receivers and the largest correlations sitting on the smallest n. The
same three symptoms appear here against a different regressor. **No thermal
reading is offered.**

**The ambiguity §5 flagged and left unresolvable is still unresolvable.** A
genuine AT-cut effect *could* legitimately flip sign between boards on
opposite sides of turnover (§4), so sign inconsistency does not *prove*
noise. With three boards, no recorded turnover temperature and n = 6 per
device, this corpus cannot tell the two apart, and §5 committed in advance
to reporting it as sign-inconsistent rather than resolving it conveniently.
That commitment is being kept in the direction that costs the more
interesting answer.

## 16. SECONDARY — pair drift vs |ΔT|, and the partial correlation

Unordered pairs within a block. **`raw` arm.** R3 has no remount to straddle;
R4 and R5 each contribute **7 controlled pairs, with 8 straddling pairs
excluded** per §4.4.

### 16.1 R3 — the block the ρ = +0.604 finding lives on

15 controlled unordered pairs, elapsed **0.04 h → 211.6 h**, |ΔT| **0–12 °F**.
Floor at n = 15 is **0.518**.

| quantity | vs \|ΔT\| | vs elapsed (zero-order) | **vs elapsed, controlling \|ΔT\|** | shift |
|---|---|---|---|---:|
| **D1** SFO-domain drift RMS | −0.077 (p = 0.781) | **+0.796 (p = 0.001)** | **+0.796 (p = 0.001)** | **−0.001** |
| **D2** accuracy gap | −0.126 (p = 0.651) | **+0.604 (p = 0.020)** | **+0.597 (p = 0.021)** | **−0.007** |

**The §4.2 gate passes.** `docs/IDENTITY_STABILITY.md` §15 measured the
unordered-pair gap against elapsed at **ρ = +0.604, p = 0.017, n = 15**.
This pass, from a fresh replay through a separately written script,
measures **ρ = +0.604, p = 0.020, n = 15**. Reproducing a three-decimal
figure through an independent implementation is the strongest single check
in this document, and it means the partial correlation below is testing the
actual finding.

**Elapsed time survives the control, by both drift measures, with a shift of
−0.007 and −0.001.** Neither drift measure has any relationship with |ΔT|
at all: −0.126 and −0.077, both far inside the floor.

**Why the partial is well-conditioned here rather than vacuous.** §7.5
worried that elapsed and temperature would be too entangled to separate.
They are not: **ρ(elapsed, |ΔT|) = −0.131 (p = 0.636, n = 15)** on R3. The
corpus happens to contain long-elapsed pairs with small |ΔT| (211.5 h /
1 °F) and short-elapsed pairs with large |ΔT| (0.04 h / 3 °F), which is
exactly the configuration that makes the control informative. **That is
luck, not design**, and it would not survive being asserted about a
different corpus.

`ref` arm, same block, same conclusion: D1 **+0.696 → +0.708** (shift
+0.012), D2 **+0.489 → +0.481** (shift −0.009), both vs |ΔT| null
(+0.040, −0.128).

### 16.2 R4 and R5 — below the pre-registered bar, and they disagree

Both blocks have **n = 7**, floor **0.750**. Nothing on either block clears
it, in either arm, on either drift measure.

| block | arm | D1 vs elapsed | D1 partial | D2 vs elapsed | D2 partial | D2 vs \|ΔT\| |
|---|---|---|---|---|---|---|
| R4 | raw | +0.321 (p = 0.502) | +0.264 | +0.607 (p = 0.163) | +0.635 | +0.055 |
| R5 | raw | −0.536 (p = 0.232) | −0.538 | −0.321 (p = 0.504) | **−0.745 (p = 0.057)** | +0.600 (p = 0.183) |

**R4 and R5 point in opposite directions on elapsed time**, at n = 7, in the
same six wall-clock sessions on two receivers in the same room. That is the
same disagreement `docs/IDENTITY_STABILITY.md` §15 recorded (R4 +0.607,
R5 −0.321 at n = 7) and it is **reported, not resolved** — again.

**The one cell where partialling |ΔT| does move something is R5-`raw`-D2:
−0.321 → −0.745, a shift of −0.423.** It is stated rather than buried, and
it is not evidence of a temperature effect: n = 7 against a floor of 0.750,
neither the zero-order nor the partial is significant, ρ(elapsed, |ΔT|) is
+0.382 on this block so the control is ill-conditioned, and the sign is
opposite to R4's on the same sessions. A large partial shift at n = 7 with a
correlated control is what an underdetermined system looks like.

## 17. Scope limit held — within-session drift was NOT tested

§4.3 pre-registered that the within-session question would not be run
against this data, and **it was not run**. `OJC` yields one reading per
hour; `docs/IDENTITY_STABILITY.md` §12 found devices moving **6.3×** and
**9.4×** the entire between-device spread inside a single session on a
timescale of tens of minutes. An hourly outdoor reading cannot address
movement at that rate, and a regression that produced a number anyway would
be a false null.

§14 makes this sharper than §4.3 could: **the analysed prefix of every
session in this run is 0.04–0.65 h, and carries at most one temperature
reading.** There is not one within-session temperature *pair* anywhere in
this corpus. The question is not underpowered here; it is unaskable.

## 18. Limitations

Beyond the standing ones in §7, which all still apply:

- **§3's "session mean temperature" degenerated to a single reading** (§14),
  because the row cap and the hourly feed interact in a way Stage 1 did not
  work through. `T_span` is 0.0 everywhere and `n_obs` ≤ 1 everywhere.
- **9 of 18 sessions use the nearest-reading fallback**, 3–24 min off. The
  §3 sensitivity check says the verdict does not turn on them.
- **300,000-row prefix subsample per file**, as pre-registered. The later
  hours of the long captures are not analysed, and neither is their weather.
- **N = 3 devices, the same three beacons on every block.** The primary test
  is 6 points per device.
- **Only 12 distinct wall-clock sessions exist** across 54 cells. Every
  n > 12 in this document is an inflated count and the effective floor of
  0.580 is the one that governs the primary test.
- **Temperature range is narrow where it matters.** R3's six sessions span
  70–82 °F and four of them sit at 73/74/75/75. A crystal turnover curve
  cannot be characterised over 12 °F with six points, and no attempt was
  made to.
- **`OJC` is an outdoor station and the boards are indoors** (§7.1). This is
  the limitation that bounds the whole document.
- **Nothing here is fused with `pc/occ/`.** No occupancy number was read,
  produced or cited. `docs/DIRECTION.md` is not cited as capability.
- **This does not revise any accuracy figure.** 99.7 %/7,497 and
  95.7 %/14,234 are pooled-session chronological-split numbers on a
  different split; nothing here touches them.
- **`docs/IDENTITY_STABILITY.md` is not revised either.** This pass
  reproduces its §9 screening counts and its §15 headline correlation and
  adds one covariate to it; it corrects nothing in it.

## 19. Corrections and self-reports

- **`gap_for_pair` was wrong on first run and is recorded rather than
  quietly fixed.** Its first version returned the **A → B ordered** gap
  while §4.2 specifies the **unordered** statistic, and on that version
  ρ(D2, elapsed) on R3 came back **+0.396 (p = 0.147)** — which would have
  fired the §4.2 gate and produced the report "this pass did not reproduce
  ρ = +0.604, so the partial is uninformative." Collapsing both directions
  into one value per unordered pair, which is what Stage 1 actually asked
  for, gives **+0.604 (p = 0.020)**. The fix restores the pre-registered
  definition; it does not change it. Both numbers are printed here so the
  correction can be judged.
- **The statistics were verified against independent references before
  being trusted**: the Spearman implementation reproduces a textbook
  worked example to four decimals (−0.1758), returns exactly ±1.000 on
  perfect monotone data, and averages ties correctly. The partial
  correlation returns the zero-order value when the control is independent
  noise (0.664 vs 0.659) and collapses 0.997 → 0.205 when the control
  explains both variables. `scipy` was not imported (`CLAUDE.md`).
- **The weather CSV was spot-checked back against the fetched feed** row by
  row at seven points including both irregular cases: the 2026-07-31 09:58
  off-hour report, and 2026-07-27, which has 23 rows because no routine
  report exists at 13:53.

## 20. Temptation register (§9)

Recorded, unacted on:

1. **I wanted to report R3's primary +0.477 / +0.592 as "suggestive of a
   thermal effect on the July receiver."** §5 pre-committed to calling a
   sign-inconsistent result sign-inconsistent, and the signs flip both
   between blocks and, in `raw`, between devices inside R3. Not done.
2. **I wanted to quote the n = 54 nominal floor of 0.268** when the primary
   pooled |ρ| came in at 0.028, because clearing "well under the floor"
   reads better against the smaller number. §6 pre-designated the effective
   floor of 0.580 as the headline. Both are printed; the effective one is
   quoted.
3. **I wanted to add a lag term** — regress SFO against temperature 2–4 h
   earlier, to model the building envelope's thermal lag (§7.1). It is a
   defensible physical model and it is also a second hypothesis invented
   after seeing a null. Not run. **If someone wants it, it should be
   pre-registered in its own document with its own floor**, not appended
   here.
4. **I wanted to drop `rx_20260714_030915`** (0.04 h of prefix, 21 windows
   on one device) from the primary. It clears the pre-registered `MIN_WIN`
   floor. Not dropped.
5. **I wanted to soften P5 to "underpowered on the primary, decisive on the
   secondary"** so it would score as HELD. It was written as one prediction
   about the document's overall verdict and it was wrong as written. Left
   as FAILED.

## 21. What would settle it

Unchanged from `docs/THERMAL_EVIDENCE.md` §8 and
`docs/IDENTITY_STABILITY.md` §20, and this document adds nothing to that
list — which is itself the result:

1. **Per-frame die temperature at both ends** (`THERMAL_EVIDENCE` §8 item 1).
   §16 now adds a reason beyond that document's: the drift's relationship
   with elapsed time is untouched by the one external thermal covariate that
   could be recovered, so if the mechanism is thermal it is not tracking
   outdoor air, and only an on-die measurement can see it.
2. **An indoor thermometer at the bench** would be a far cheaper
   intermediate than instrumenting firmware, and would test the §7.1
   envelope objection directly. It cannot be done retroactively for
   `data/raw/`, which is the entire reason this document had to use an
   airport station.
3. **§12 of `IDENTITY_STABILITY` remains the thing to chase.** The wander is
   sub-session and per-device; §17 explains why this corpus cannot ask that
   question of weather at all.

---

## Files added or written by this investigation

- `pc/exp_weather_covariate.py` — the one script; source of every number above
- `docs/WEATHER_COVARIATE.md` — this file
- `data/weather_ojc_tmpf_hourly.txt` — the fetched `OJC` readings, as fetched
- `data/weather_ojc_tmpf.csv` — expanded, what the analysis re-reads
- `.gitignore` — two lines added so the fetched covariate is covered
  explicitly (`*.csv` already covered the CSV; the `.txt` was not covered)

`pc/rff/dsp.py`, `pc/rff/discriminator.py`, `pc/rff/reference.py` were
**read and used unchanged**; `dsp.py`'s mtime is still 2026-07-13 20:42:46.
Nothing under `data/raw/`, `firmware/`, `pc/occ/` or `site/` was touched.
No serial port was opened. All scratch state went to `$WXC_CACHE` outside
the repo tree and was removed. **Nothing was staged, committed or pushed.**

---
---

# STAGE 3 — pre-registration: pressure and humidity

**Written and saved before `&data=relh` or `&data=mslp` was fetched**, and
before any capture was re-replayed. Same rule as Stage 1: nothing between
this banner and the `STAGE 4` banner is edited once results exist; if a
Stage-3 statement turns out wrong it is corrected below the Stage-4 banner
with the original left standing, and any post-hoc temptation goes in §32
instead of into the design.

**The Stage-1 predictions (§5) are not reused, reworded, extended or
reinterpreted here.** They were about temperature and they were scored in
§12. §26 below is a fresh set about two different covariates, with its own
floors and its own correction. Where a Stage-3 prediction happens to
resemble a Stage-1 one, that is a repeated bet, not a recycled one, and it
is scored separately.

## 22. Why these two, and why the previous pass was incomplete

The Stage-1/2 pass tested **temperature only**. §7.1 named the objection
that bounds it: the boards are indoors, `OJC` is outdoors, and a building
envelope plus HVAC attenuates, lags and can invert an outdoor temperature
swing. That objection is a real limit on the temperature result and it is
restated, not withdrawn.

**It does not apply equally to all three covariates, and that asymmetry is
the reason this stage exists:**

- **Barometric pressure passes through a building envelope essentially
  unattenuated.** A structure does not hold a static pressure differential
  against the atmosphere — it leaks, and it equalises on a timescale of
  seconds to minutes. So **indoor pressure ≈ outdoor pressure**, and `OJC`
  `mslp` is the one covariate in this family that is *not* mangled by the
  envelope. **A null on pressure is therefore a much stronger null than the
  temperature null was**: it is a null about the pressure the devices
  actually experienced, not about a proxy for it. This is the single most
  important asymmetry in this stage and §31 must state it either way the
  result falls.
  - Caveat kept in view: `mslp` is *sea-level-reduced*, not station
    pressure. The reduction is a fixed-offset function of station elevation
    and the station's own temperature, so `mslp` variation tracks synoptic
    variation faithfully but is not the absolute pressure at the bench.
    For a **correlation against Δ over time**, which is all this document
    computes, the offset cancels. This is stated now so the reduction is
    not discovered later and offered as a defect.
- **Humidity partially tracks indoors** in a leaky building, attenuated by
  the envelope and opposed by HVAC dehumidification. It sits between
  pressure and temperature on the "how mangled is this proxy" axis, and it
  is the covariate most likely to be strongly collinear with temperature
  (diurnal relative humidity is largely a restatement of diurnal
  temperature at fixed dewpoint).

**Neither is a plausible strong *direct* mechanism on a crystal.** The
resonator sits in a sealed package; ambient humidity does not reach it, and
a few hPa of barometric change is a negligible mechanical load on quartz.
**The mechanism being tested is indirect**: both are proxies for the passage
of weather systems, and therefore for **HVAC duty cycle**, which is a real
and large thermal forcing on a room. That is the hypothesis. It is weaker
than "temperature causes crystal drift" and it is stated as weak now rather
than inflated afterwards if something turns up.

## 23. The primary test is now the one that was secondary in Stage 1

Stage 1 made the per-(device, session) regression primary. That was the
wrong ordering: §15 showed it is the underpowered half (12 independent
temperature values behind 54 cells), while §16 was the half that actually
answered something.

**Primary for this stage:**

> Does the elapsed-time relationship on **R3** — reproduced in §16.1 at
> **ρ(D2, elapsed) = +0.604, p = 0.020, n = 15**, and
> **ρ(D1, elapsed) = +0.796, p = 0.001** — survive controlling for
> **Δpressure** and for **Δhumidity**, as it survived controlling for
> **|ΔT|**?

Reported for each covariate, exactly as §16.1 did for temperature:

1. `ρ(D, Δcov)` — the covariate's own association with drift.
2. `ρ(D, elapsed)` — zero-order, unchanged from §16.1 by construction.
3. `ρ(D, elapsed | Δcov)` — the partial, **and the shift from zero-order.**
4. **`ρ(elapsed, Δcov)` — the conditioning diagnostic.** §16.1's temperature
   control was well-conditioned (−0.131) **by luck, not design**, and §12
   already recorded that as luck. These two may not be so lucky, and the
   conditioning number is reported *before* the partial is interpreted, not
   after.
5. **A joint partial controlling all three covariates at once**,
   `ρ(D, elapsed | |ΔT|, Δrelh, Δmslp)`. This is the strongest available
   form of the question and it is pre-registered now so it cannot be
   omitted if it disagrees with the single-covariate partials.

**Ill-conditioning threshold, committed now:** if
**|ρ(elapsed, Δcov)| > 0.50**, the partial for that covariate is declared
**not trustworthy at n = 15** and is reported as such regardless of what
value it takes. A control that is itself a near-restatement of the variable
being controlled for cannot separate them, and at n = 15 there is no room
to argue otherwise.

**Secondary (unchanged in form from §15, not in ranking):** per
(device, session) median SFO against that session's `relh` and `mslp`,
pooled and de-meaned within (block, device), against the §6 floors. §14's
degeneracy still applies — the analysed prefix of every session is
0.04–0.65 h, so "session mean" will again be one hourly reading or the
nearest one — and this is expected in advance this time rather than
discovered.

**Not run, again and for the same reason (§4.3, §17):** within-session
drift. An hourly feed of any variable cannot address movement over tens of
minutes, and there is not one within-session covariate *pair* in this
corpus.

## 24. Multiple comparisons — the correction, committed before fetching

**This makes three covariates tested against one finding.** At α = 0.05 and
three independent shots, the chance of at least one spurious hit is
**1 − 0.95³ = 14.3 %** — roughly one in seven, as the brief says.

### 24.1 The two families, and why only one of them needs correcting

- **Family A — "does this covariate matter?"** The three tests
  `ρ(D, Δcov)` for cov ∈ {tmpf, relh, mslp}. **This is where the inflation
  lives**, because a *hit* on any one of the three would be reported as
  "weather explains something", and I get three chances at it.
  **Correction: Holm–Bonferroni across m = 3, family-wise α = 0.05.**
- **Family B — "does elapsed survive?"** The three partials. **This is a
  conjunction, not a disjunction**: the claim "elapsed survives controlling
  for weather" requires the partial to hold up under *every* control, not
  under at least one. A conjunction does not inflate the false-positive
  rate — it inflates the false-*negative* rate. **No correction is applied
  to Family B**, and applying one would make an already-conservative claim
  look stronger than it is.

**The asymmetric quoting rule, and it is the important one:**

> **Correction can only ever help a null result.** Quoting a
> multiple-comparison-corrected p-value in support of a *null* is
> self-serving — it makes a non-finding look more securely non-existent
> than the data says. Therefore: **for any Family-A result that is null,
> the UNCORRECTED p is the one quoted.** Holm is applied only to results
> that reach nominal significance, where it does real work against
> exactly the risk it exists for.
>
> Consequence, accepted now: **a covariate with an uncorrected p < 0.05
> that fails Holm is reported as "nominally significant; does not survive
> correction at m = 3" — not as absent.** It goes in the results table with
> both p-values, and it is named in §31's verdict.

### 24.2 Collinearity, `M_eff`, and the thing I am deliberately not doing

If `relh` and `mslp` are strongly correlated with `tmpf` in this corpus,
they are not three independent tests and m = 3 over-corrects. Two numbers
are therefore reported:

- **The correlation matrix** among the three Δcovariates on R3's 15 pairs,
  and among the three session-level covariates on the 12 distinct sessions.
- **`M_eff`**, the effective number of independent tests, by the
  Cheverud–Nyholt/Li–Ji eigenvalue estimator on that matrix:
  `M_eff = 1 + (M − 1)·(1 − Var(λ)/M)` with M = 3 and λ the eigenvalues of
  the 3×3 correlation matrix. `M_eff = 3` means fully independent,
  `M_eff = 1` means the three tests are one test wearing three hats.

**`M_eff` is reported for interpretation and does NOT govern the
correction. Holm at m = 3 governs.** The reason is explicit: `M_eff` is
computed *from the data*, and using a data-derived quantity to *relax* a
multiple-comparison threshold is precisely the move this document's Stage-1
discipline exists to prevent. If a result is significant under Holm at
m = 3 it is significant; if it is significant only under the looser
Šidák-at-`M_eff` threshold, **that disagreement is itself the reported
finding** and is stated in those words, not resolved in favour of the
threshold that gives an answer.

Both thresholds are printed side by side for every Family-A test.

## 25. Detection floors for this stage — computed before fetching

Partial correlations lose a degree of freedom per control, so the Stage-1
floor table (§6) does not apply to them. Floors below are the |ρ| exceeded
by 5 % of draws under a null of mutually independent rank variables,
100,000 draws per cell, seed 20260823, two-tailed α = 0.05.

| n | k = 0 (zero-order) | k = 1 control | k = 2 controls | k = 3 controls |
|---:|---:|---:|---:|---:|
| **15** (R3 pairs) | **0.518** | **0.536** | 0.557 | **0.577** |
| 7 (R4/R5 pairs) | 0.750 | 0.821 | 0.881 | **0.952** |

**The k = 0 column reproduces §6's table exactly (0.518 at n = 15, 0.750 at
n = 7) from an independently written simulation**, which is the check that
the new floors are on the same scale as the old ones.

Two things follow, and both are accepted in advance:

- **The joint three-control partial on R3 must clear 0.577 to be
  significant** — barely below the zero-order floor, so the joint test is
  affordable at n = 15.
- **R4 and R5 are hopeless for the joint test: the k = 3 floor at n = 7 is
  0.952.** A correlation of 0.95 on seven points is a perfect monotone
  ordering. The R4/R5 joint partials will be computed and printed, and they
  will be labelled **uninterpretable by construction**, not quietly
  omitted and not read as evidence of anything.

Family-A significance is assessed against the **k = 0** floor and against
Holm/Šidák on the permutation p, both.

## 26. Predictions — frozen, and no sign claimed for either covariate

Two-tailed throughout, for the same reason as §4: no defensible sign exists
for an indirect proxy mechanism, and claiming one would be inventing a fact.
Neither prediction is derived from, or is a restatement of, §5.

| # | prediction | why |
|---|---|---|
| **Q1** | **Pressure: \|ρ(D1, Δmslp)\| and \|ρ(D2, Δmslp)\| both below the 0.518 floor**, point estimates \|ρ\| < 0.40. | The mechanism is indirect (§22) and §13 of `IDENTITY_STABILITY` already shows the drift is 2.2×–7.1× per-device residual — a single room-wide scalar cannot carry a per-device quantity, whatever that scalar is. This is the same structural argument as §5's P1, applied to a different covariate; it is a repeated bet, not a copied one. |
| **Q2** | **Humidity: \|ρ(D1, Δrelh)\| and \|ρ(D2, Δrelh)\| both below the 0.518 floor**, point estimates \|ρ\| < 0.40. | Same, plus humidity reaches the resonator not at all. |
| **Q3** | **Elapsed survives both controls**: partial within **±0.15** of the zero-order on both drift measures, for both covariates — i.e. D2 stays above +0.45 and D1 above +0.65. | If Q1 and Q2 hold, the controls explain little of either variable and partialling them cannot move much. |
| **Q4** | **Elapsed survives the JOINT three-covariate control too**: `ρ(D2, elapsed \| all three)` stays **above +0.40**, and `ρ(D1, elapsed \| all three)` **above +0.55**. Weaker thresholds than Q3 because three controls at n = 15 will absorb some variance by chance alone. | The joint test is the one that could break the Stage-2 conclusion, so it gets its own number. |
| **Q5** | **At least one of Δrelh, Δmslp will be worse-conditioned against elapsed than \|ΔT\| was**, i.e. \|ρ(elapsed, Δcov)\| > 0.131 for at least one. | 0.131 was luck (§12), and luck does not repeat on demand. This is a bet that the Stage-2 result's clean conditioning was not a general property of this corpus. |
| **Q6** | **`relh` will be the most collinear with `tmpf` of the three pairs**, and `mslp` the least. `M_eff` will land **strictly between 2.0 and 3.0**. | Diurnal relative humidity is largely diurnal temperature restated at roughly fixed dewpoint; barometric pressure is set by synoptic pattern and is close to orthogonal to the diurnal cycle. |
| **Q7** | **At least one Family-A test will come back nominally p < 0.05 somewhere in the full grid** (2 drift measures × 2 new covariates × 2 feature spaces × 3 blocks = 24 new tests), **and it will fail Holm.** | This is a prediction about the *fishing surface*, made so that when it happens it is already accounted for. If nothing hits, that is recorded as Q7 failing. |
| **Q8** | **A pressure null will be reported as a stronger null than the temperature null was**, in those words, because indoor pressure ≈ outdoor pressure (§22). | Committing now to draw the asymmetry, so it is not conveniently forgotten if pressure comes back null. |

**What would falsify Q1/Q2 in the direction that matters:** a Family-A |ρ|
above the 0.518 floor **that survives Holm at m = 3**, with a
**consistent sign across both drift measures and both feature spaces**, and
a **partial shift exceeding ±0.15** on the same covariate. All three
conditions, not any one. A hit on the association without a corresponding
collapse of the partial would mean the covariate correlates with drift but
does not account for the elapsed-time relationship — which is a different
and much weaker claim, and would be reported as that.

## 27. What does not change

- `pc/rff/dsp.py` untouched and used as shipped; mtime checked before and
  after. `pc/capture.py:compute_cfo`, `pc/phase_skew.py`,
  `pc/fingerprint.py` not used.
- Every stream replayed **from byte one with a fresh estimator**; 300,000-row
  prefix cap; corrupt rows screened by **both** routes before any delta
  arithmetic; `MIN_WIN = 10`, not lowered.
- Unordered pairs; **R4/R5 pairs straddling the 2026-08-22 remount excluded**
  from the headline and reported separately.
- **Station referenced as `OJC` only** — no location, distance, elevation
  figure, cross-street or rationale, in this document or in the script.
- `M` rows dropped, never interpolated. UTC throughout; the join stays on
  `pc_time_us` interpreted directly as epoch UTC, so no ±5 h arithmetic
  enters it (§1.3).
- One script, `pc/exp_weather_covariate.py`, extended — not a second one.
- Read-only on `data/raw/`; no serial port; **nothing staged, committed or
  pushed**; fetched weather files gitignored.

---
---

# STAGE 4 — results: pressure and humidity

*(appended after the run; nothing above this banner was edited)*

Run 2026-08-23. Captures re-replayed from scratch — **18 files, 4,049,349
data rows**, identical to §13's counts including the single median-filter
catch, which is the check that this run is doing what Stage 2's run did.
`pc/rff/dsp.py` mtime still **2026-07-13 20:42:46**. No serial port,
nothing under `data/raw/` written, **nothing staged, committed or pushed**.

## 28. Verdict

**Pressure is a clean null. Humidity is not, and it is the only thing in
this document that has ever cleared a pre-registered bar. Elapsed time
survives all three controls individually and jointly in the primary arm.**

Three statements, in decreasing order of confidence:

1. **Pressure explains nothing, and per §22 this is the strong null.**
   On R3, `ρ(D1, |ΔP|) = +0.147 (p = 0.607)` and
   `ρ(D2, |ΔP|) = +0.205 (p = 0.462)`, both far under the 0.518 floor.
   Controlling for |ΔP| moves the elapsed relationship by **+0.041** and
   **−0.015**. **Because indoor barometric pressure tracks outdoor almost
   exactly (§22), this null is a null about the pressure the devices
   actually experienced** — not about a proxy that the building envelope
   might have mangled. It is the one covariate in this family whose
   negative result generalises indoors, and §26's Q8 committed in advance
   to saying so.
2. **Elapsed time survives.** On R3 raw, the joint three-covariate partial
   is **+0.859 (p < 0.001)** for D1 and **+0.655 (p = 0.008)** for D2,
   against a k = 3 floor of 0.579 — *higher* than the zero-order values of
   +0.796 and +0.604. Controlling for all the weather available does not
   weaken the elapsed-time relationship; it slightly sharpens it.
3. **Humidity is a real hit, and it is a hit on the wrong quantity in the
   wrong direction to rescue a weather explanation.**
   `ρ(D1, |ΔRH|) = +0.638 (p = 0.012)` raw and **+0.767 (p = 0.001)** ref,
   both clearing the 0.518 floor **and surviving Holm at the pre-registered
   m = 3** (adjusted 0.036 and 0.004). This is the only Family-A result in
   three covariates and four stages to do that. But:
   - **|ΔRH| is collinear with elapsed time itself**, `ρ = +0.606`, which
     trips the ill-conditioning threshold **§23 committed to in advance
     (> 0.50)**. The humidity partial is therefore declared **not
     trustworthy at n = 15**, as pre-registered, whatever value it takes.
   - **It does not appear on D2**, the accuracy gap — the quantity that
     actually produced ρ = +0.604. `ρ(D2, |ΔRH|) = +0.093` raw and
     `+0.090` ref, both null. The hit is confined to the SFO-domain measure.
   - **It fails §26's falsification triad**, which required all three of:
     Holm survival ✓, sign consistency ✓ (all four cells positive), *and* a
     partial shift exceeding ±0.15. The shifts are **−0.127** (raw D1),
     **+0.087** (raw D2), **−0.242** (ref D1), **+0.060** (ref D2). One of
     four exceeds the bar. **Three of four do not, so the triad is not
     met** — but the ref-D1 cell that does is reported in §31.3 rather than
     rounded away.

**So: weather does not explain the drift.** The strongest form of the
question this corpus can ask — does elapsed time survive controlling for
temperature, humidity and pressure simultaneously — comes back **yes, at
+0.859 / +0.655 against a floor of 0.579.**

**What this does not say:** everything in §7 still holds for temperature and
humidity. And §31.4 records one cell where the joint control *does* break
the relationship (ref, D1, +0.426 against a 0.579 floor), which is a
**Q4 failure** and is scored as one in §29.

## 29. Predictions scored

| # | prediction | outcome | **verdict** |
|---|---|---|---|
| **Q1** | pressure below the 0.518 floor, \|ρ\| < 0.40 | R3 **+0.147** (D1), **+0.205** (D2) raw | **HELD** |
| **Q2** | humidity below the 0.518 floor, \|ρ\| < 0.40 | R3 D1 **+0.638** raw / **+0.767** ref; survives Holm at m = 3 | **FAILED** |
| **Q3** | partial within ±0.15 of zero-order, both covariates, both drift measures | raw: −0.127, +0.087 (relh), +0.041, −0.015 (mslp) — all within. ref: **−0.242** (relh D1) outside | **HELD in raw (primary); FAILED in one ref cell** |
| **Q4** | joint partial: D2 > +0.40, D1 > +0.55 | raw **+0.655** / **+0.859** ✓; ref D2 +0.622 ✓, ref **D1 +0.426** ✗ | **HELD in raw (primary); FAILED in ref D1** |
| **Q5** | at least one new covariate worse-conditioned than \|ΔT\|'s 0.131 | \|ΔRH\| **+0.606**, \|ΔP\| **+0.483** — both worse | **HELD** |
| **Q6** | relh most collinear with tmpf, mslp least; `M_eff` strictly in (2, 3) | ρ(tmpf, relh) = **−0.890** is the largest pair ✓; `M_eff` = **2.221** session / **2.561** delta ✓; but ρ(tmpf, mslp) = −0.526 exceeds ρ(relh, mslp) = +0.314, so mslp is **not** the least-entangled variable | **PARTLY HELD** |
| **Q7** | at least one nominal p < 0.05 in the 24-test grid, and it will fail Holm | **two** nominal hits: R3/D1/relh (p = 0.012 raw, 0.001 ref) and R5/D2/relh (p = 0.036). R5's fails Holm (0.108). **R3's SURVIVES Holm** | **FAILED on the second clause** |
| **Q8** | a pressure null reported as the stronger null, in those words | §28 item 1 | **HELD** |

**Two predictions failed and both failed toward "weather matters more than I
expected", which is the direction that costs me the comfortable answer.**

- **Q2 failed outright.** I bet humidity would be null and it was not.
- **Q7 failed on its second clause** — I predicted a spurious-looking hit
  that would be killed by correction, and instead got a hit that correction
  did not kill. That is the more interesting failure, and the reason §24.1's
  asymmetric quoting rule mattered: **had I applied Holm at m = 6** (both
  drift measures × three covariates, which is what the first version of the
  script did), R3/D1/relh would have come back adjusted **0.072, retained** —
  a non-finding. The pre-registration said **m = 3**, m = 3 gives **0.036,
  rejected**, and the more conservative family would have been
  self-serving. §33 records that correction.
- **Q3 and Q4 held in the primary (`raw`) arm and failed in one `ref` cell
  each**, and both are scored as split rather than as clean holds.

## 30. Data and checks (§8, §27)

| covariate | readings | hours with no usable routine report | span (UTC) | range |
|---|---:|---:|---|---|
| `tmpf` | 1,024 | 8 | 07-12 00:53 → 08-23 16:53 | 65 – 98 °F |
| `relh` | 1,025 | 7 | 07-12 00:53 → 08-23 17:53 | 27.95 – 100.00 % |
| `mslp` | 1,024 | 8 | 07-12 00:53 → 08-23 17:53 | 1006.10 – 1023.00 hPa |

`M` rows dropped, never interpolated. **`mslp` carries its own `M` inside a
routine report where `tmpf` and `relh` have values** — 2026-07-31 09:58 is
the one such hour in this span — and it is dropped per-variable rather than
filled from a neighbouring hour.

**Feed check (§1.3): PASS, unchanged**, and it is *not* redefined for the new
covariates. Inventing a new pass/fail criterion for `relh`/`mslp` after
Stage 3 was frozen would be the move Stage 1 exists to prevent, so the
script prints their 2026-08-22 extremes as **descriptive only**:

- `relh` minimum **44.43 % at 20:53 UTC** — the same hour as the `tmpf`
  maximum — and maximum **93.47 % at 05:53 UTC**. Relative humidity
  anticorrelating with temperature across the diurnal cycle is an
  **independent corroboration of the UTC reading** that does not depend on
  the tmpf check at all. It is offered as corroboration, not as a second
  test.
- `mslp` minimum 1015.00 hPa at 01:53 UTC, maximum 1020.60 at 16:53 UTC.
  Barometric pressure is mostly synoptic rather than diurnal, so this
  carries no directional expectation and is recorded without interpretation.

**Capture check: 0 FAIL, 17 of 18 verified to 0–1 s, `rx_20260722_XXXXXX`
skipped** (no timestamp in its filename), exactly as §13.

**Screening reproduces §13 exactly**: R3 59 field / 0 median, R4 81 / **1**,
R5 0 / 0, 0 unparseable, on the same row counts.

**27 of 54 (session, covariate) pairs use the §3 nearest-reading fallback** —
the same 9 sessions for all three covariates, since they share the hourly
grid. §14's degeneracy is unchanged and was expected this time: the analysed
prefix is 0.04–0.65 h, so every "session covariate" is one hourly reading.

### 30.1 A capability failure that was nearly recorded as absent data

**`mslp` initially looked unavailable for `OJC` and it is available.** The
first request returned **HTTP 200 with an empty body**; two follow-ups
**timed out at 180 s**. The obvious inference — "this station reports
altimeter setting but not MSLP, as many non-first-order ASOS sites do" — is
wrong, and a fallback to `&data=alti` was already being set up when a
fourth, smaller request returned 48 rows of perfectly good `mslp`.

This is `CLAUDE.md` failure mode **C** almost exactly: an empty result being
read as *no data exists* when the truth was *the request failed*. It is
recorded because the near-miss would have silently substituted a different
variable for the pre-registered one and reported it as forced. **`mslp` is
the pre-registered covariate and `mslp` is what was used**; no `alti` value
appears anywhere in this analysis.

**Requests refused at the approval prompt**, recorded rather than routed
around: `&data=relh` day1=24&day2=5 (Jul→Aug), `&data=mslp` day1=18&day2=24
(Jul), and the `&data=alti` probe day1=22&day2=23 (Aug). Both needed spans
were retrieved under different day boundaries; **the `alti` probe was not
retried because it was no longer needed.** No alternative retrieval route
was attempted for any of them.

## 31. PRIMARY — does elapsed survive each control?

**R3, `node_id 68`, 15 controlled unordered pairs, elapsed 0.04–211.6 h.**
Floors: **k = 0 → 0.518, k = 1 → 0.536, k = 3 → 0.579** (§25).

### 31.1 `raw` — the primary arm

**D1, SFO-domain drift RMS. Zero-order vs elapsed: +0.796 (p = 0.001).**

| control | association ρ(D1, Δcov) | partial ρ(D1, elapsed \| Δcov) | shift | conditioning ρ(elapsed, Δcov) |
|---|---:|---:|---:|---|
| \|ΔT\| | −0.077 (p = 0.781) | +0.796 (p = 0.001) | **−0.001** | −0.131 · ok |
| **\|ΔRH\|** | **+0.638 (p = 0.012)** | +0.669 (p = 0.007) | −0.127 | **+0.606 · ILL-CONDITIONED** |
| \|ΔP\| | +0.147 (p = 0.607) | +0.838 (p < 0.001) | +0.041 | +0.483 · ok |
| **all three jointly** | — | **+0.859 (p < 0.001)** | **+0.063** | — |

**D2, accuracy gap. Zero-order vs elapsed: +0.604 (p = 0.020)** — the §16.1
reproduction of `IDENTITY_STABILITY` §15, unchanged.

| control | association ρ(D2, Δcov) | partial ρ(D2, elapsed \| Δcov) | shift | conditioning |
|---|---:|---:|---:|---|
| \|ΔT\| | −0.126 (p = 0.651) | +0.597 (p = 0.021) | −0.007 | −0.131 · ok |
| \|ΔRH\| | +0.093 (p = 0.736) | +0.691 (p = 0.006) | +0.087 | +0.606 · ILL-CONDITIONED |
| \|ΔP\| | +0.205 (p = 0.462) | +0.589 (p = 0.024) | −0.015 | +0.483 · ok |
| **all three jointly** | — | **+0.655 (p = 0.008)** | **+0.051** | — |

**Family A, Holm at the pre-registered m = 3** (uncorrected p quoted for
nulls per §24.1; Holm applied to hits):

| family | tmpf | relh | mslp |
|---|---|---|---|
| R3 / D1 / raw | p = 0.781, retain | **p = 0.012 → Holm 0.036, REJECT** | p = 0.607, retain |
| R3 / D2 / raw | p = 0.651, retain | p = 0.736, retain | p = 0.462, retain |

The R3/D1/relh hit **also clears the descriptive Šidák-at-`M_eff` threshold**
(α = 0.0198 at `M_eff` = 2.561), so the two corrections **agree**, and §24.2's
"report the disagreement" clause does not fire.

### 31.2 `|ΔP|`'s conditioning is closer to the line than temperature's

`ρ(elapsed, |ΔP|) = +0.483` — under the pre-registered 0.50 ill-conditioning
threshold, but **not comfortably**, and much worse than |ΔT|'s −0.131. The
pressure partial is therefore reported as trustworthy *by the rule as
written*, while noting that it sits 0.017 from the boundary. Had it landed
at 0.51 the pressure result would have been declared untrustworthy and §28
item 1 could not have been written. **That is a coin-flip's distance from a
different verdict, and it is stated rather than left for a reader to
notice.**

### 31.3 `ref` — and the humidity hit gets stronger, not weaker

| | D1 zero-order **+0.696 (p = 0.005)** | | | D2 zero-order **+0.489 (p = 0.067)** | | |
|---|---:|---:|---|---:|---:|---|
| control | assoc | partial | shift | assoc | partial | shift |
| \|ΔT\| | +0.040 (0.889) | +0.708 (0.004) | +0.012 | −0.128 (0.652) | +0.481 (0.071) | −0.009 |
| **\|ΔRH\|** | **+0.767 (0.001)** | +0.454 (0.092) | **−0.242** | +0.090 (0.745) | +0.549 (0.035) | +0.060 |
| \|ΔP\| | +0.431 (0.107) | +0.618 (0.013) | −0.078 | −0.054 (0.849) | +0.590 (0.023) | +0.100 |
| **joint** | — | **+0.426 (0.114)** | **−0.270** | — | +0.622 (0.014) | +0.133 |

**`ref` D1 / relh: ρ = +0.767, p = 0.001, Holm at m = 3 → 0.004, REJECT.**
The sign matches `raw` (+0.638), so **§26's sign-consistency condition is
met across both feature spaces and both drift measures — all four cells are
positive.** This is the strongest single association in the document.

**And `ref` D1 is the one cell where elapsed does not survive**: the joint
partial falls to **+0.426, below the 0.579 floor**, a shift of −0.270. That
is a **Q4 failure**, scored as one in §29, and it is not explained away.
Two things bound it, neither of which makes it disappear:

- `raw` is the pre-registered primary arm (§2, `IDENTITY_STABILITY` §1.4),
  and in `raw` the same cell reads **+0.859**.
- §1.4's standing warning applies to any `ref` result: the reference
  beacon's `ref` feature is ~0-centred per file by construction. D1 is an
  RMS over three devices' shifts, so it is **not** carried by the reference
  beacon alone — the warning does not dispose of this cell, and it is not
  being used to.

### 31.4 The post-hoc test that is not pre-registered, labelled as such

**Not pre-registered. Exploratory. Counted in no family, and it changes no
verdict above.** The symmetric completion of the pre-registered partial —
does the *covariate* survive controlling for *elapsed*? — is the obvious
next question and staying silent about it would be worse than running it
with a label on it:

| R3 raw | ρ(D, Δcov) | **ρ(D, Δcov \| elapsed)** |
|---|---:|---:|
| D1, \|ΔT\| | −0.077 | +0.045 (p = 0.876) |
| **D1, \|ΔRH\|** | **+0.638 (p = 0.012)** | **+0.323 (p = 0.247)** |
| D1, \|ΔP\| | +0.147 | −0.450 (p = 0.095) |
| D2, \|ΔRH\| | +0.093 | −0.429 (p = 0.111) |

**The asymmetry is the whole story of the humidity hit.** Elapsed survives
controlling humidity (+0.796 → +0.669). Humidity does **not** survive
controlling elapsed (+0.638 → +0.323, p = 0.247). Read together with
`ρ(elapsed, |ΔRH|) = +0.606`, the natural interpretation is that **|ΔRH| is
a proxy for elapsed time in this corpus rather than a driver of drift** —
sessions further apart in wall-clock span more diurnal cycles, and relative
humidity swings hard on the diurnal cycle, so a big |Δt| mechanically
implies a big |ΔRH|. That is a calendar artifact of six sessions, not a
mechanism.

**This paragraph is an interpretation of a post-hoc test and is flagged as
one.** It is consistent with the pre-registered result and is not required
by it; §28 item 3 stands on the pre-registered numbers alone.

### 31.5 R4 and R5 — below the bar, and the joint test is unusable there

Both n = 7. Floors: **k = 0 → 0.750, k = 1 → 0.818, k = 3 → 0.951.** §25
committed in advance to calling the k = 3 column unusable, and it is:

| block | D1 zero | D1 joint | D2 zero | D2 joint |
|---|---:|---:|---:|---:|
| R4 | +0.321 (0.502) | −0.021 (0.940) | +0.607 (0.163) | +0.369 (0.373) |
| R5 | −0.536 (0.232) | −0.574 (0.186) | −0.321 (0.504) | −0.783 (0.043) |

**Every joint figure here is UNINTERPRETABLE BY CONSTRUCTION**: the floor is
0.951, so only a perfect monotone ordering of seven points could register,
and R5's D2 joint of −0.783 at "p = 0.043" is **below its own floor** — a
worked illustration of why a permutation p and a detection floor are not the
same thing, and why §25 pre-committed to the label.

**R4 and R5 still disagree in sign on elapsed** (+0.607 vs −0.321 on D2), as
they did in §16.2 and in `IDENTITY_STABILITY` §15. Reported, not resolved,
for the third time.

**|ΔP| is ill-conditioned on both August blocks** (`ρ(elapsed, |ΔP|) =
+0.607`), so even the single-control pressure partials there are declared
untrustworthy by the §23 rule. **R5/D2/relh reaches p = 0.036 nominally and
fails Holm at m = 3 (adjusted 0.108)** — reported as "nominally significant,
does not survive correction", per §24.1, and not as absent.

## 32. SECONDARY — median SFO vs each covariate

Pooled, de-meaned within (block, device), n = 54 cells / **12 distinct
wall-clock sessions**. Nominal floor 0.268; **effective floor 0.580** (§6).

| arm | vs tmpf | vs relh | vs mslp |
|---|---|---|---|
| **raw** | −0.028 (0.837) | −0.057 (0.682) | −0.137 (0.319) |
| ref | +0.206 (0.135) | −0.193 (0.160) | **−0.331 (0.014)** |

**Null on every covariate against the effective floor.** The `ref`/`mslp`
cell clears the *nominal* 0.268 at p = 0.014 and is **nowhere near** the
0.580 that governs; it also flips sign against `raw` (−0.137, ns). Per
§24.1 the uncorrected p is quoted because the result is null.

Per block, n = 18, nominal floor 0.470:

| block | raw tmpf | raw relh | raw mslp | ref tmpf | ref relh | ref mslp |
|---|---|---|---|---|---|---|
| **R3** | +0.477 (0.045) | **−0.649 (0.004)** | −0.339 (0.172) | +0.592 (0.011) | **−0.662 (0.004)** | −0.436 (0.072) |
| R4 | −0.048 (0.854) | +0.029 (0.915) | −0.289 (0.243) | −0.089 (0.731) | +0.064 (0.809) | −0.095 (0.706) |
| R5 | −0.235 (0.351) | +0.146 (0.567) | +0.235 (0.354) | +0.318 (0.198) | −0.242 (0.332) | −0.299 (0.226) |

**R3's humidity figure is not an independent finding from R3's temperature
figure.** At session level `ρ(tmpf, relh) = −0.890` — the two are very
nearly the same variable with a sign flip — and R3 reads **+0.477** on tmpf
and **−0.649** on relh, which is that mirror. §15.2 already disqualified the
tmpf version as sign-inconsistent across blocks (R4 −0.048, R5 −0.235), and
**the relh version fails identically** (R4 +0.029, R5 +0.146). Counting it
as new evidence would be counting one result twice, which is exactly what
`M_eff` = 2.221 at session level is warning about.

## 33. Collinearity and `M_eff` (§24.2)

**Session level, n = 12 distinct wall-clock sessions:**

| pair | Spearman ρ |
|---|---:|
| `tmpf` – `relh` | **−0.890** |
| `tmpf` – `mslp` | −0.526 |
| `relh` – `mslp` | +0.314 |

**`M_eff` = 2.221.**

**R3 delta level, n = 15 pairs — the quantities actually used in §31:**

| pair | Spearman ρ |
|---|---:|
| \|ΔT\| – \|ΔRH\| | +0.243 |
| \|ΔT\| – \|ΔP\| | +0.483 |
| \|ΔRH\| – \|ΔP\| | +0.605 |

**`M_eff` = 2.561.** Šidák at that `M_eff` would give α = 0.0198 against
Bonferroni's 0.0167.

**Answering the question directly: yes, they are collinear, and no, they are
not three independent tests.** Two-and-a-half is the honest count at session
level and two-and-a-half at delta level. **Holm at m = 3 governed anyway, as
§24.2 committed**, and it did not matter: the two thresholds agree on every
test in the document, so the data-derived `M_eff` was never used to rescue
anything. Note the **differencing decorrelates the covariates**: `tmpf` and
`relh` are −0.890 as levels but their *absolute differences* are only +0.243
apart, because |Δ| discards sign.

## 34. Corrections and self-reports

- **The Holm family was implemented at m = 6 and the pre-registration says
  m = 3.** The first run grouped both drift measures with all three
  covariates into one six-member family per block, which gave
  R3/D1/relh **adjusted 0.072 — retained, a non-finding**. §24.1 defines
  Family A as the three covariates. At m = 3 the same p = 0.012 gives
  **adjusted 0.036 — rejected.** The fix makes the correction *less*
  conservative and the resulting hit *harder* on my own predictions, which
  is the direction §24.1's asymmetric quoting rule exists to enforce. Both
  numbers are printed here so the correction can be judged.
- **Holm, `M_eff` and the partial-correlation floors were verified against
  independent references before being trusted.** Holm reproduces the
  textbook worked example (`p = [0.01, 0.04, 0.03]` → `[0.03, 0.06, 0.06]`,
  reject only the first). `M_eff` returns exactly 3.000 on the identity
  matrix and exactly 1.000 on the all-ones matrix. **`floor_for_partial` at
  k = 0 reproduces §6's table exactly** — 0.518 at n = 15, 0.750 at n = 7 —
  from a separately written simulation, which is what puts the k = 1 and
  k = 3 floors on the same scale as the Stage-1 ones.
- **The `mslp` capability failure in §30.1** is the most serious near-miss in
  this stage and is written up there rather than here.

## 35. Temptation register (§9, continued)

Recorded, unacted on:

6. **I wanted to keep Holm at m = 6**, because it retained R3/D1/relh and let
   §28 say "no covariate survives correction" — a much cleaner verdict.
   §24.1 says m = 3. Corrected against my own interest; see §34.
7. **I wanted to report the post-hoc reverse partial (§31.4) as the answer**,
   because it dissolves the humidity hit tidily. It is not pre-registered.
   It is reported, labelled, and §28 item 3 is written to stand without it.
8. **I wanted to drop the `ref` arm's Q4 failure** (+0.426, below floor) on
   the grounds that `raw` is primary and §1.4 warns about `ref`. Neither
   reason disposes of it — D1 is an RMS over three devices, not a reference
   beacon artifact. Scored as a failure in §29 and given its own §31.3.
9. **I wanted to say `ρ(elapsed, |ΔP|) = +0.483` is "well within" the 0.50
   threshold.** It is 0.017 from the boundary. §31.2 says so instead.
10. **I wanted to add a lag term again** — regress against covariates 2–4 h
    earlier — now that humidity has produced something. Same answer as
    temptation 3: it is a hypothesis invented after seeing a result, and it
    belongs in its own pre-registered document with its own floor.
11. **I wanted to rewrite Q6 as held**, since its main clause (relh most
    collinear with tmpf; `M_eff` in (2,3)) came back right. The "mslp least"
    clause is wrong as written. Scored PARTLY HELD.

## 36. Limitations added by this stage

Everything in §7 and §18 still applies. New:

- **`mslp` is sea-level-reduced**, not station pressure (§22). For
  correlations against Δ-over-time the fixed offset cancels, which is why
  this is a caveat and not a defect — but it is not the absolute pressure at
  the bench, and no absolute-pressure claim is made anywhere.
- **`|ΔRH|` is confounded with elapsed time at +0.606** and cannot be
  disentangled from it at n = 15. That is a property of this corpus, not of
  humidity.
- **`|ΔP|`'s conditioning of +0.483 sits 0.017 under the threshold** that
  would have disqualified the pressure partial (§31.2).
- **The joint three-covariate test exists only on R3.** At n = 7 the k = 3
  floor is 0.951 and R4/R5 cannot support it.
- **Six sessions, three devices, 12 independent covariate values.** Adding
  covariates does not add sessions; it adds columns to a table that is 12
  rows tall, which is why §24's correction mattered at all.
- **This still does not exclude an indoor thermal mechanism** — but §28
  item 1 now carves out pressure specifically, because pressure is the one
  covariate for which indoor and outdoor are the same number.

## 37. What would settle it

Unchanged from §21, and this stage narrows it by one:

1. **Per-frame die temperature at both ends** (`THERMAL_EVIDENCE` §8 item 1).
   Still the only thing that settles the thermal question.
2. **An indoor thermometer and hygrometer at the bench.** §31.4 suggests
   |ΔRH| is a calendar proxy rather than a mechanism, but an *indoor*
   humidity trace would test that directly instead of by inference from a
   post-hoc partial.
3. **Pressure can now be set aside.** §22's argument plus §28 item 1 means
   the pressure hypothesis has had the fairest test this corpus can give it
   and returned +0.147 / +0.205 against a 0.518 floor, with the partial
   moving by +0.041 / −0.015. Further pressure work on `data/raw/` is not
   worth the fetch.
4. **`IDENTITY_STABILITY` §12 remains the thing to chase.** The wander is
   sub-session and per-device, and §17's scope limit applies to all three
   covariates equally: an hourly feed of anything cannot address movement
   over tens of minutes.

---

## Files added or written by this stage

- `pc/exp_weather_covariate.py` — extended, not replaced; still one script
- `docs/WEATHER_COVARIATE.md` — this file
- `data/weather_ojc_relh_hourly.txt`, `data/weather_ojc_relh.csv`
- `data/weather_ojc_mslp_hourly.txt`, `data/weather_ojc_mslp.csv`
- `.gitignore` — the two explicit Stage-2 lines replaced by
  `data/weather_ojc_*`, which covers all six fetched-covariate files

`pc/rff/dsp.py`, `pc/rff/discriminator.py`, `pc/rff/reference.py` **read and
used unchanged**; `dsp.py` mtime still 2026-07-13 20:42:46. Nothing under
`data/raw/`, `firmware/`, `pc/occ/` or `site/` touched. No serial port
opened. Scratch in `$WXC_CACHE` outside the repo tree, removed at the end.
**Nothing staged, committed or pushed.**
