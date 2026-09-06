# CO-LOCATED RECEIVERS — 2026-08-23 overnight, the last V1 capture

The two receivers were remounted onto the same wall on 2026-08-22 and are now
roughly 10 inches apart chip to chip (antenna tip to the other board's chip
about 4 inches). Every prior capture in `data/raw/` had them separated. This
is the first file in the repo's history with co-located receivers, and it was
read to answer one question ahead of all others:

> `docs/SEPARATION_SCALING.md` §0 and `docs/REFERENCE_CHOICE.md` §0 establish
> an inversion — the same-beacon **receiver-to-receiver** SFO difference
> exceeds every within-receiver **beacon-to-beacon** difference on the S3.
> That inversion is why a fingerprint enrolled on one receiver does not
> transfer to the other, and it is the mechanism `CLAUDE.md` names behind the
> 99.7 % → 95.7 % device-ID drop. Ten inches apart the path geometry is
> nearly identical for both nodes. If that term is **geometric** it should
> collapse here. If it is **silicon** it should not move.

Read-only. Both CSVs were opened `"rb"` and never written; nothing in
`data/raw/` was modified, renamed or deleted. `ls -l --time-style=full-iso`
before and after reports **2,866,404,334** and **3,596,309,377** bytes, last
modified `2026-08-23 08:29:44.302952100 -0500` and `08:29:44.213825100
-0500`, unchanged across this pass. No serial port was opened, nothing was
flashed, nothing was staged, committed or pushed (`git diff --cached
--name-only` is empty, before and after). Two files in the repo were written
by this pass: **this one** and **`pc/exp_colocated_0823.py`**. All state and
report text went to `$COLO_CACHE = /tmp/colo`, outside the repo tree. **No
scratch file was left in the repo tree**, with one disclosed exception:
`pc/__pycache__/exp_colocated_0823.cpython-310.pyc`, produced when two
verification helpers imported the module rather than running it. It is
covered by `.gitignore:14` (`__pycache__/`), it matches the .pyc already
present for every other `pc/exp_*.py`, and **this pass could not delete it**
— `rm` on this mount returns `Operation not permitted`. The pre-existing
`pc/exp_poscontrol_0822.py.head` / `.tail` and `pc/_orig_check.py` were not
touched.

`pc/rff/dsp.py` was **not modified** (`docs/V2_SPEC.md` §5.5); its mtime is
still 2026-07-13 20:42:46. `pc/capture.py:compute_cfo`, `pc/phase_skew.py`
and `pc/fingerprint.py` were **not used** — `docs/CODE_INVENTORY.md` §4.2
C1/C2/C3 establishes all three have the DC/guard-band index wrong.

---

## 0. What this file is, and the span actually analysed

**The capture is not still running.** Both files stopped at
`2026-08-23 08:29:44` and did not grow across a 20 s re-`stat`; the last byte
of each is `0x0a` and the last row of each parses to a full 13 fields with
256 CSI ints. **There is no truncated final row to handle.** The
truncated-row guard (`len(row) != 13` or unparseable ints → counted, not
fed to the estimator) was in place regardless and fired **0 times on
3,344,351 rows and 0 times on 4,330,849**.

**Two file pairs match the brief's glob `data/raw/*_20260823_*.csv`.** The
one meant here is the `014740` pair; `013537` is a separate 317 s run that
ended at 01:40:54, twelve minutes before this one started. It is used below
only as a corroborating pointer, never fused with the overnight figures.

| | `d0wd_20260823_014740.csv` | `s3_20260823_014740.csv` |
|---|---|---|
| `node_id`, every row | **68** (3,344,351 / 3,344,351) | **108** (4,330,849 / 4,330,849) |
| data rows analysed | **3,344,351** | **4,330,849** |
| rows with ≠ 13 fields / unparseable | 0 | 0 |
| first `pc_time_us` | 01:47:41.178922 −05:00 | 01:47:41.112626 −05:00 |
| last `pc_time_us` | 08:29:44.301939 −05:00 | 08:29:44.212811 −05:00 |
| span analysed | **24,123.123 s = 6.7009 h** | **24,123.100 s = 6.7009 h** |
| delivered fps over span, post-screen | 138.629 | 179.531 |

**The whole file was read, both nodes, first row to last** — the `part`
loop's final byte position equals the file size exactly on both
(2,866,404,334 and 3,596,309,377). 7,675,200 rows in total.

**A small discrepancy against the brief, stated rather than explained
away.** The brief gives 3,344,365 / 4,330,866 from the live display; the
files hold **3,344,351 / 4,330,849**, i.e. **14 and 17 fewer**. Both counts
are `wc -l` minus the header and are confirmed independently by
`pc/mac_census.py`, which reports the same two totals (§2). Whether the
display's counter leads the file by a drain batch is **unknown** and was not
investigated.

---

## 1. Method, and the reproduction check

One script, `pc/exp_colocated_0823.py`, from the repo root:

```
export COLO_CACHE=/tmp/colo
D=data/raw/d0wd_20260823_014740.csv
S=data/raw/s3_20260823_014740.csv
for p in 0 1 2 3 4; do
  python3 pc/exp_colocated_0823.py part $D --tag d0wd --part $p --nparts 5 \
      --total-rows 3344351
  python3 pc/exp_colocated_0823.py part $S --tag s3   --part $p --nparts 5 \
      --total-rows 4330849
done
python3 pc/exp_colocated_0823.py merge --tag d0wd --nparts 5 --expect-rows 3344351
python3 pc/exp_colocated_0823.py merge --tag s3   --nparts 5 --expect-rows 4330849
python3 pc/exp_colocated_0823.py report --tags d0wd,s3
```

Every number in this document is from `report` unless it names another
command.

**Replay origin.** `FrameEstimator` owns a per-instance generator —
`self._rng = np.random.default_rng(rng_seed)` (`pc/rff/dsp.py:118`) — handed
to `ransac_line` on every frame (`:132`), which draws two
`rng.integers(0, n, size=64)` per call (`:85-86`). The generator advances
once per fitted frame, so the hypotheses tried at frame N depend on how many
frames preceded N in that stream (`docs/V2_SPEC.md` §5.5). **Every stream
here is replayed from the start of its file with a fresh estimator**, one
per (node, source-MAC), and no window, filter or subsample is applied ahead
of it.

**The `part`/`merge` split is not an approximation, and it was proved rather
than asserted.** The split exists because this host kills a process when the
shell call that spawned it returns and a full pass takes about nine minutes
per node. Each part pickles the estimators, aggregators, median-filter
buffer and drop state forward. Two checks:

1. `merge` reports row counts **3,344,351** and **4,330,849**, matching
   `wc -l` minus the header exactly, with `pc_time_us` monotone across all
   4 seams per file, and the screen's `node_id`/`channel` mode taken from a
   20,000-row prescan **AGREE**ing with the whole-file histogram on both
   nodes.
2. On the `013537` pair the run was done twice, once as **3 parts** and once
   as **1 part**, and the two full reports are **byte-identical** under
   `diff`. The split reproduces a single uninterrupted pass exactly.

**Phase work** is `pc/rff/dsp.py`'s `FrameEstimator` + `WindowAggregator`
with the shipped gates `inlier_ratio >= 0.6` / `resid_std <= 0.8`
(`dsp.py:164`), at two window lengths: **16,384** — the primary metric of
`docs/REFERENCE_CHOICE.md` §1.3, the longest averaging that keeps all three
beacons alive on both receivers — and **64**, the shipped configuration,
reported alongside for its much tighter CIs. **The two agree on every
conclusion below**, which is the check that the small-N long windows are not
carrying the result on their own.

**Corrupt rows are screened before the estimator and before any delta
arithmetic**, by the two independent routes `docs/OVERNIGHT_2026-08-22.md`
§1 requires: field plausibility on six columns (`node_id` against the file's
own mode, `env_id == 0`, `channel` against the file's own mode, `csi_len` in
{128, 256, 384}, `noise_floor` in [−110, −70], `rssi` in [−100, −10]), and a
width-9 median filter on `dropped` with tolerance 100, compared **circularly
mod 65536** so genuine u16 wraps are not false positives.

**`csi_data` is parsed with `csv.reader`**, never a naive comma split — it
is a quoted comma-separated list nested inside the CSV.

**`pc_time_us` is a per-serial-drain-batch host stamp**
(`pc/node_census.py:30-35`, `docs/HANDOFF.md` trap #1). It is used here only
to place bins and to measure host-side delivered rate, never as per-frame
cadence.

---

## 2. The MAC census, screened — and it reconciles

**The live display's 166 and 34 are reproduced exactly**, and they are not
the device populations. `pc/mac_census.py`, the repo's own tool, at the
repo's own floor:

```
python3 pc/mac_census.py "data/raw/d0wd_20260823_014740.csv" --min-frames 20
python3 pc/mac_census.py "data/raw/s3_20260823_014740.csv"   --min-frames 20
```

| | d0wd | s3 |
|---|---|---|
| distinct MACs, every row, no floor | **166** | **34** |
| distinct MACs, ≥ 20 frames | **18** | **14** |

**The real populations are 18 on the d0wd and 14 on the S3.** The shipped
tool and this pass's independent accounting agree to the unit on every one
of the 32 surviving MACs and on all three beacon frame counts
(1,478,550 / 1,014,694 / 845,594 on the d0wd; 1,574,578 / 1,485,873 /
1,260,401 on the S3).

**Closing the loop: does the artefact count match the corrupt-row count?
Yes, completely, with nothing left over.**

| | d0wd | s3 |
|---|---|---|
| distinct MACs, every row | 166 | 34 |
| — real, ≥ 20 frames on clean rows | **18** | **14** |
| — clean rows but below the 20-frame floor | **22** | **19** |
| — **seen only on corrupt rows** | **126** | **1** |
| sum | **166** ✓ | **34** ✓ |
| corrupt rows on the node | **190** | **1** |
| — bearing a novel (artefact) address | **141** | **1** |
| — bearing an address that also appears clean | **49** | 0 |

The 126 fabricated d0wd addresses arise on 141 corrupt rows — 116 appear
once, 8 twice, one 4× and one 5× — and the other 49 corrupt rows landed on a
beacon address that was already real (B3 20, B2 17, B1 12), corrupting some
other field and generating no new MAC. **141 + 49 = 190**, the corrupt-row
total, to the unit. On the S3 the correspondence is 1 : 1.

**Two honest qualifications.**

- **The 20-frame floor alone is sufficient on this file, but that is a
  coincidence of this file and not a general result.** Every one of the 126
  artefact MACs carries ≤ 5 frames, so the floor and the corrupt-row screen
  happen to return the same 18 and 14. A burst of corruption on one address
  would break that, and the screen is what makes the claim safe.
- **The screen slightly *under*-counts corruption; it does not over-count
  it.** At least three of the 22 "clean but sparse" d0wd addresses are
  single-frame byte-neighbours of beacon addresses —
  `fa:1e:c9:70:72:30` and `e4:21:e3:20:72:30` against B3
  `f4:2d:c9:70:72:30`, and `d9:f4:a5:2f:fa:48` against B2
  `28:05:a5:2f:fa:48`. They are more likely undetected corruption than real
  transmitters. **Nothing in the census requires a mechanism other than
  corruption to generate addresses**, which was the question asked.

**Established, and worth recording:** the S3's real population is a **strict
subset** of the d0wd's. The four sources the d0wd sees at ≥ 20 frames and
the S3 does not — `9e:38:41:e0:97:0d`, `6e:34:6f:7b:3f:81`,
`32:a7:21:0b:32:85`, `6e:0a:30:1f:ed:21` — are all present on the S3 too,
at 19, 4, 11 and 12 frames, i.e. straddling the floor rather than absent.
Ten inches apart, the two receivers hear the same room.

---

## 3. Drop rates and corrupt rows per node

### 3.1 The S3: zero drops confirmed, zero corrupt rows refuted

**Drops: zero.** `dropped` reads **0 on the first clean row and 0 on the
last**, with **0 wraps** and **0 negative deltas** in 4,330,849 rows. Every
one of the 24,124 one-second bins has zero drops (100.0 %). The premise
holds without qualification.

**Corrupt rows: one, not zero.** File **line 2,856,988** (data row
2,856,987) carries
`mac 00:00:d3:5c:f1:f3, rssi 27, noise_floor 0, channel 245, dropped 61147`
— flagged by **both** screens independently, with its neighbours reading
`dropped 0` on either side:

```
line 2856987   dropped     0   mac 28:05:a5:2f:fa:48  rssi -75  nf -95  ch 6
line 2856988   dropped 61147   mac 00:00:d3:5c:f1:f3  rssi  27  nf   0  ch 245   <-- corrupt
line 2856989   dropped     0   mac a4:f0:0f:77:91:20  rssi -78  nf -95  ch 6
```

This is the first corrupt row
recorded on the S3 since the console moved to USB-Serial-JTAG;
`docs/OVERNIGHT_2026-08-22.md` §4.2 and `docs/REFERENCE_CHOICE.md` §1.2 both
report **0 of 3,564,005** on 2026-08-22. The rate is **0.23 ppm**, against
the d0wd's 56.81 ppm — 246× lower, not zero.

**That single row is worth the whole screen.** Unscreened, its `dropped`
value of 61,147 followed by the true 0 manufactures one negative delta,
which naive wrap-safe accumulation converts into **65,536 drops on a node
that dropped nothing**. Screened, the total is 0. Independently confirmed by
`awk` sharing no code with the script (§3.3): `screened=1 first=0 last=0
wraps=0 drops=0`.

### 3.2 The d0wd: 179,609 drops, 5.10 % loss

| | value |
|---|---|
| queue drops, wrap-safe, corrupt rows removed | **179,609** |
| genuine u16 counter wraps | **2** |
| endpoint cross-check `last − first + 65536 × wraps` | `50456 − 1919 + 131072` = **179,609** ✓ |
| delivered (clean) rows | 3,344,161 |
| **loss = drops / (delivered + drops)** | **5.0971 %** |
| naive wrap-safe accumulation, **no corrupt-row screen** | **11,910,553 — overstates by 66.3×** |
| what `field_diag.py:106` / `diagnose.py:540` would report | 48,537 — **understates by 3.70×** |

Burstiness over 24,124 one-second bins: median 0, mean 7.445, p90 23, p99
43, max 280, **12,649 seconds (52.4 %) with zero drops**.

**The d0wd got worse, not better.** `docs/OVERNIGHT_2026-08-22.md` §4.2
measured **0.579 %** loss with 93.7 % zero-drop seconds on the 2026-08-22
overnight. This file is **5.097 %** with 52.4 % zero-drop seconds — an
**8.8× increase in loss** going into V2 work. Corrupt rows also rose,
142 → 190 on a comparable row count. **Why is unknown**; the remount is a
candidate but this pass has no evidence that separates it from anything else
that changed between the two nights, and `CLAUDE.md` failure mode **G**
applies — nothing in the file labels the remount.

### 3.3 Independent re-derivation, and the screen that only one route catches

Both drop totals were re-derived by an `awk` implementation that shares no
code with the script:

```
awk -F, 'NR>1{ nd=$(NF-2); ev=$(NF-1); ch=$7; ln=$9; nf=$6; rs=$5;
   ok = (nd==68 && ev==0 && ch==6 && (ln==128||ln==256||ln==384)
         && nf<=-70 && nf>=-110 && rs<=-10 && rs>=-100);
   if(!ok){screened++; next}
   d=$NF; if(seen==0){first=d;prev=d;seen=1;next}
   delta=d-prev; if(delta<0){wraps++; delta+=65536}
   tot+=delta; prev=d }
 END{print "screened="screened" first="first" last="prev" wraps="wraps" drops="tot}' \
 data/raw/d0wd_20260823_014740.csv
```

- **S3** (with `nd==108`): `screened=1 first=0 last=0 wraps=0 drops=0` —
  **identical** to the script.
- **d0wd**: `screened=187 first=1919 last=50456 wraps=5 drops=376217`. The
  `screened=187` matches the script's field-plausibility count exactly. The
  drop total does **not** match, and the reason is the point of running two
  screens: `376,217 − 179,609 = 196,608 = 3 × 65,536`. **The field screen
  alone leaves three corrupt rows in, each of which manufactures one false
  wrap.**

Those three rows, located by printing every negative delta that survives the
field screen, are lines **378,170**, **2,675,317** and **3,188,480**:

```
line 378168   dropped 34093   mac 28:05:a5:2f:fa:48  rssi -78  nf -97  ch 6  len 256
line 378169   dropped 34093   mac f4:2d:c9:70:72:30  rssi -73  nf -97  ch 6  len 256
line 378170   dropped     0   mac a4:f0:0f:77:91:20  rssi -78  nf -97  ch 6  len 256   <-- corrupt
line 378171   dropped 34093   mac a4:f0:0f:77:91:20  rssi -81  nf -97  ch 6  len 256
line 378172   dropped 34093   mac f4:2d:c9:70:72:30  rssi -73  nf -97  ch 6  len 256
```

Every other field is plausible and the neighbours resume the true trajectory
immediately — exactly the row `docs/OVERNIGHT_2026-08-22.md` §4.2 found at
line 95,349, now **three times in one file**. The other two are
`26939 → 61 → 26941` and `45881 → 0 → 45881`. The two remaining negative
deltas, at lines 1,088,010 and 1,963,768, are `65535 → 0` and are the two
**genuine** wraps.

**Neither screen alone is sufficient. This pass used both**, and this is the
third recurrence of the conflation failure mode after 514× and 101×.

---

## 4. B1 — no longer below the cadence floor, and no longer losing half its frames

B1 = `a4:f0:0f:77:91:20`, the reference beacon every device-ID figure in the
repo is anchored to. The floor is `BEACON_MIN_FPS_X10 = 100`, i.e. **10.0
fps** (`firmware/csi_rx/main/main.c:150`, mirrored by
`pc/node_census.py`'s `BEACON_MIN_FPS`).

| | s3 (108) | d0wd (68) |
|---|---|---|
| delivered fps, whole span | 179.531 | 138.629 |
| **B1** `a4:f0:0f:77:91:20` | **52.249** | 35.053 |
| B2 `28:05:a5:2f:fa:48` | 65.273 | 42.062 |
| B3 `f4:2d:c9:70:72:30` | 61.595 | 61.291 |
| mean RSSI B1 / B2 / B3 (dB) | **−79.08** / −74.74 / −77.99 | −82.87 / −79.06 / −74.44 |
| RSSI sd B1 / B2 / B3 (dB) | **0.85** / 1.35 / 1.38 | 1.49 / 1.72 / 1.17 |

**B1 is not under the floor, on either node, at any point in the file.**
Over the 80 whole 300 s blocks, **0 blocks** are under 10.0 fps for any
beacon on either node; the S3's B1 minimum block is **41.30 fps**, four
times the floor.

**The `WindowAggregator` loss is gone too.** `dsp.py:164`'s gate,
`min_inlier_ratio = 0.6` / `max_resid = 0.8`:

| node | b | frames | fitted | nofit % | **gate rej %** | inlier ≥ 0.90 % | max resid |
|---|---|---|---|---|---|---|---|
| s3 | **B1** | 1,260,401 | 1,260,400 | 0.000 | **0.294** | 76.114 | 0.2091 |
| s3 | B2 | 1,574,578 | 1,574,576 | 0.000 | 1.199 | 91.460 | 0.2171 |
| s3 | B3 | 1,485,873 | 1,485,865 | 0.001 | 1.015 | 50.922 | 0.2174 |
| d0wd | B1 | 845,582 | 845,565 | 0.002 | 7.258 | 5.950 | 0.2169 |
| d0wd | **B2** | 1,014,677 | 1,014,661 | 0.002 | **79.787** | 2.223 | 0.2233 |
| d0wd | B3 | 1,478,530 | 1,478,508 | 0.001 | 1.888 | 84.358 | 0.2094 |

Against `docs/DISPLAY_LIVE_0822.md` §5.1 / §5.3, on the 2026-08-22 23:57
capture:

| s3 / B1 | 2026-08-22 23:57 | **this file** | change |
|---|---|---|---|
| delivered fps | 9.326 (**under** the 10.0 floor) | **52.249** | **5.60× up** |
| gate rejection | **49.993 %** | **0.294 %** | **170× down** |
| mean RSSI | −81.74 dB | **−79.08 dB** | **+2.66 dB** |
| RSSI sd | 2.10 dB | **0.85 dB** | 2.5× steadier |

**What it costs downstream: nothing, in this file.** The S3's reference cell
now yields 1,260,401 frames, 99.706 % of them admissible, giving **19,635
shipped 64-frame windows and 76 windows at 16,384**. On 2026-08-22 evening
it yielded 14,688 frames with half rejected. The corroborating pointer: the
separate 317 s `013537` capture, taken 12 minutes earlier, already shows
s3/B1 at **40.53 fps** and **−80.83 dB** — so the improvement predates this
file and did not happen during it.

**`max_resid = 0.8` remains inoperative on this data.** The largest
`resid_std` anywhere is **0.2233**, 3.6× below the gate — consistent with
`docs/SEPARATION_SCALING.md` §4.1 (0.2202) and `docs/REFERENCE_CHOICE.md`
§1.4 (0.2261).

### 4.1 The pathological cell moved from B3/d0wd to B2/d0wd

`docs/OVERNIGHT_2026-08-22.md` §10 and `docs/POSITIVE_CONTROL_0822.md` §5
both rule that **B3/d0wd's 58.8 %-reject cell is an estimator-bias artefact
and must not be quoted alone**; `docs/REFERENCE_CHOICE.md` §0 adds that it
must never be used as a reference.

**In this file B3/d0wd is healthy — 1.888 % reject, 84.358 % at inlier ≥ 0.90
— and B2/d0wd carries the pathology instead, worse: 79.787 % reject,
2.223 % at inlier ≥ 0.90.** Its 64-frame windows have an IQR of **0.03249
rad/sc** against 0.00185–0.00493 for the healthy cells, 7–18× wider, and it
yields only 3,204 windows from 1,014,677 frames where B3/d0wd yields 22,665
from 1,478,530. Its RSSI (−79.06, sd 1.72) is unremarkable and close to its
own −80.85 of 2026-08-22, so this is **not** an RSSI story.

**This is the third position the cell has occupied, not the second.**
`docs/POSITIVE_CONTROL_0822.md` §6 records that it had already moved **from
B3/s3 to B3/d0wd between sessions**; this file puts it on **B2/d0wd**. So it
has now changed both receiver and beacon.

**Established:** a large per-(receiver, source) estimator bias exists, it is
not tied to a particular beacon **or to a particular receiver**, and it
survives co-location. **Unknown:** what selects which cell gets it. Nothing
in this pass investigated that.

The pre-existing rule is applied below — B2/d0wd is not rested on — and
because it is convenient to this pass's conclusion, **the B2 number is
reported in full anyway** so the reading can be judged without it.

---

## 5. The inter-receiver term under co-location

The statistic is the one `docs/SEPARATION_SCALING.md` §0 and
`docs/REFERENCE_CHOICE.md` §0 use: the **d0wd-minus-s3 same-beacon SFO
median difference, no reference correction**, at window 16,384 with
`min_inlier 0.60` / `max_resid 0.80`. σ is `BETWEEN_UNIT_SD = 0.00237`
throughout (`pc/exp_thermal_evidence.py:129`, from
`docs/LOT_HYPOTHESIS.md` §5).

### 5.1 The measurement

| b | d0wd | s3 | **diff** | **× SD** | 95 % CI of diff |
|---|---|---|---|---|---|
| B1 | +0.01599 | +0.01431 | **+0.00168** | **0.71** | [+0.00051, +0.00280] |
| B2 † | +0.04414 | +0.00544 | +0.03870 | 16.33 | [+0.02473, +0.04831] |
| B3 | +0.00921 | +0.02531 | **−0.01610** | **6.79** | [−0.01661, −0.01503] |

† B2's d0wd cell is the 79.8 %-reject cell of §4.1.

At the shipped window 64, with far tighter CIs, the same three numbers:
**+0.00175 (0.74σ)**, +0.04019 (16.96σ), **−0.01595 (6.73σ)** — agreeing to
the third decimal. The result does not depend on the window length.

Within-receiver beacon-to-beacon differences on the S3 — **the device term**
— at window 16,384: B1−B2 **+0.00887 (3.74σ)**, B1−B3 **−0.01100 (4.64σ)**,
B2−B3 **−0.01986 (8.38σ)**.

### 5.2 Only B1 is quotable on both nights, and it collapsed

This is the structural fact that governs the whole comparison. On
2026-08-22 the unusable cell was B3/d0wd; in this file it is B2/d0wd. So of
the three beacons, **exactly one — B1 — has a clean cell on both receivers
on both nights**, and B1 is also the reference beacon everything is anchored
to.

| B1 receiver term | value (rad/sc) | × SD |
|---|---|---|
| 2026-08-22, separated (`docs/REFERENCE_CHOICE.md` §0, "none" row) | 0.00900 | 3.80 |
| **2026-08-23, co-located** | **0.00168** | **0.71** |
| **change** | **5.36× smaller** | **−3.09σ** |

At 0.00168 rad/sc the same-beacon receiver-to-receiver difference is **below
one `BETWEEN_UNIT_SD`** and only **2.1× the documented clock-twin ΔSFO**
(0.00080, `docs/LOT_HYPOTHESIS.md`) — i.e. down to the scale of the smallest
real effect this project has characterised. The CI excludes zero, so a
residual remains; it is just small.

### 5.3 The inversion does not hold in this file — and both sides moved

`docs/REFERENCE_CHOICE.md` §0's ratio, smallest receiver term against the
largest within-S3 beacon-to-beacon difference under the same condition:

| | smallest receiver term | largest S3 device term | **ratio** |
|---|---|---|---|
| 2026-08-22, separated | 0.00900 | 0.00505 (B2−B3) | **1.78** |
| **2026-08-23, co-located** | **0.00168** (B1) | **0.01986** (B2−B3) | **0.085** |

**The inversion is not merely gone, it is reversed by an order of
magnitude** — a 21× swing in the ratio. But the ratio moved for **two**
reasons and only one of them is about co-location:

- the receiver term fell **5.4×** (0.00900 → 0.00168), and
- the S3 device term rose **3.9×** (0.00512 → 0.01986; that document's own
  §1.4 measures the 2026-08-22 figure as 0.00512, its §0 table as 0.00505).

Those contribute roughly equally in log terms. **Anyone quoting "the
inversion is gone" without the second line is quoting half the arithmetic.**
Why the S3's beacon-to-beacon spread quadrupled is **unknown** and was not
investigated here.

Even taking the *largest* non-artefact receiver term (B3, 0.01610) against
the largest S3 device term (0.01986), the ratio is **0.81** — still below 1.

### 5.4 Which does it look like — geometric or silicon?

**Both, and the file separates them better than it settles them.**

**The part that co-location removes looks geometric.** B1, the only cell
clean on both nights, fell from 3.80σ to 0.71σ when the two boards were put
ten inches apart. That is what a path-dependent term does when the paths are
made nearly identical. B3 is 6.79σ, but B3 has no usable 2026-08-22 baseline
to fall from, so it contributes no before/after evidence either way.

**A large part is not geometric, and it survives co-location.** At ten
inches on the same wall, on the same night, through near-identical
geometry, the three beacons read **0.71σ, 16.33σ and 6.79σ**. A purely
geometric term would move all three together; these differ by 23×. This
corroborates a suspicion already on the record:
`docs/REFERENCE_CHOICE.md` §7 wrote that **"if the receiver term is not
common-mode across beacons at one receiver, it may not be a 'receiver term'
at all."** Co-location is the sharpest test of that yet run, and it does not
become common-mode. The
outlier is the cell whose estimator rejects 79.8 % of its frames (§4.1),
which is a link-quality and per-unit-estimator property, not a path
property.

**That is not a promotion of the acceptance-ordering hypothesis, and should
not be read as one.** `docs/POSITIVE_CONTROL_0822.md` §5 lists "lowest
acceptance ↔ largest inter-receiver difference" under **permitted, not
established** — "four sources; the correlation coefficients in §3.5 are not
evidence". This file leaves it exactly there. The extreme fits: the
79.8 %-reject cell carries the 16.33σ. The middle does not: B3/d0wd has the
**lowest** rejection of the three d0wd cells (1.888 %) yet a middling 6.79σ,
while B1/d0wd rejects 7.258 % and reads 0.71σ. Three points, not monotone.

**Plainly, as asked:** on the one comparison this file can actually make,
the inter-receiver term **shrank, by 5.4×, and the term looks geometric**.
That is the direction the geometric hypothesis predicted and the silicon
hypothesis did not. It is not a clean win for "geometric", because a
23×-spread residual remains at fixed geometry that geometry cannot explain.

### 5.5 What this cannot settle, and why

**This is one session. It cannot settle the question alone.** Three reasons,
each sufficient on its own:

1. **Yesterday's remount means nothing across 22 → 23 August is a
   controlled comparison.** The remount moved *both* receivers — position
   and possibly orientation — at the same time as it co-located them. A
   receiver term that shrank could have shrunk because the boards are ten
   inches apart, or because both now sit somewhere better. **This file
   cannot separate co-location from relocation**, and no artefact in the
   repo records the remount's time, geometry or antenna state
   (`CLAUDE.md` failure mode **G**).
2. **The comparison rests on one beacon.** The artefact cell moved between
   nights, leaving B1 as the only cell clean on both. A single
   before/after pair, however large the factor, is one measurement.
3. **The denominator moved too.** §5.3 — the S3 device term rose 3.9×, for
   reasons this pass did not establish. Part of the ratio flip is not about
   the receivers at all.

**What would settle it** is the experiment `docs/REFERENCE_CHOICE.md` §7
already asks for: alternate separated and co-located captures over several
sessions with the antenna state recorded, so the term can be measured
against geometry with the session-to-session variance visible. **Do not
propagate 0.71σ into any device-ID claim on the strength of this file.**

---

## 6. The S3's antenna

**The orientation before this capture is UNKNOWN to this pass and was not
assumed either way.** Nothing in the file records antenna state: the `label`
column is empty on all 4,330,849 S3 rows and all 3,344,351 d0wd rows.

### 6.1 The file shows no event consistent with the whip being moved during it

Searched two ways over 403 60 s bins per beacon: the largest split-point
difference of means (with a 10-bin margin), and the largest single-bin jump.

| s3 | mean | sd | first 10 bins | last 10 bins | best split | largest 1-bin jump |
|---|---|---|---|---|---|---|
| B1 | −79.11 | 0.59 | −78.93 | −79.10 | 0.742 dB @ 1.367 h | 3.708 dB @ 1.150 h |
| B2 | −74.86 | 1.54 | −82.70 | −74.69 | 8.036 dB @ 0.167 h | 8.940 dB @ 0.117 h |
| B3 | −78.03 | 1.07 | −78.82 | −78.24 | 1.291 dB @ 0.233 h | 5.487 dB @ 1.267 h |

**A physical move of the S3's whip must step all three beacons at once** —
one antenna serves all three links. **No such three-beacon step occurs.** B1 is
coincident with nothing: its best split is at 1.367 h and its largest jump
at 1.150 h, against B2's 0.167 h / 0.117 h and B3's 0.233 h / 1.267 h. B2
and B3 *are* roughly coincident with each other early in the file, and that
one event is examined and excluded on independent grounds below.

**The single largest feature in the file is not an antenna event, and can be
excluded positively rather than by absence.** It sits at bin 7 → 8
(t ≈ 0.117 h ≈ 01:54:40, seven minutes after the capture started) and it
moves **both** receivers, in **opposite** directions:

| bin 7 → 8, mean RSSI | s3 | d0wd |
|---|---|---|
| B1 | −79.00 → −79.05 (**−0.05**) | −80.31 → −79.50 (+0.81) |
| B2 | −84.69 → −75.75 (**+8.94**) | −71.26 → −76.59 (**−5.33**) |
| B3 | −79.46 → −77.43 (**+2.03**) | −72.21 → −75.31 (**−3.10**) |

S3/B2's frame count per bin roughly doubles across the same boundary
(1,825 → 3,768) while the d0wd's falls (3,090 → 2,746).

**A change to the S3's antenna cannot move the d0wd at all**, and cannot
move a beacon in opposite directions on two receivers. So whatever this is —
path, transmitter, or something in the room between two boards now ten
inches apart — **it is not the S3's whip**, which is the only question §6
is asking.

**It does partly resemble a class already on the record, and partly not.**
`docs/POSITIVE_CONTROL_0822.md` §2.8 establishes an event that "steps RSSI
on all three beacons on both receivers at once in opposite directions per
receiver" and pushes the S3's `noise_floor` off its modal value. The
opposite-sign-per-receiver part matches here on B2 and B3. Two things do
not:

- **B1 does not move** (−0.05 dB on the S3), where that event moved all
  three.
- **The S3's `noise_floor` does not leave its mode.** Across the same
  boundary it reads −95 on 8,854 of 8,939 rows in bin 7 and **11,521 of
  11,521 in bin 8** — the non-modal fraction goes 0.95 % → 0.00 %:

```
head -400001 data/raw/s3_20260823_014740.csv | awk -F, -v t0=1787467661112626 \
  'NR>1{b=int(($1-t0)/60000000); if(b<15){c[b":"$6]++; tot[b]++}} END{...}'
```

**No attribution is offered.** `CLAUDE.md` failure mode **G** — the `label`
column is empty on every row of both files, so there is nothing in the
record that says what happened at 01:54, and this pass did not investigate
it further.

(The same command reproduces `docs/OVERNIGHT_2026-08-22.md` §2.1 and
`docs/DISPLAY_LIVE_0822.md` §5.2 on the other node: the d0wd reads −97 on
essentially every row, so "the d0wd's `noise_floor` held" remains evidence
of nothing about receiver state.)

**Stated as asked: the file shows no step change consistent with someone
physically moving the S3's antenna at any point during the 6.70 h span.**
S3/B1's RSSI is the steadiest series in the capture — sd 0.59 dB across
bins, range −83.1 to −78.0 — which is what a stationary antenna looks like.

### 6.2 What the file permits, and does not establish, about orientation

Against `docs/DISPLAY_LIVE_0822.md` §5.1 (2026-08-22 23:57 capture), all
three S3 links changed, in different directions:

| s3 mean RSSI | 2026-08-22 23:57 | this file | Δ |
|---|---|---|---|
| B1 | −81.74 | −79.08 | **+2.66 dB** |
| B2 | −79.66 | −74.74 | **+4.92 dB** |
| B3 | −67.00 | −77.99 | **−10.99 dB** |

**Permitted, not established:** two links improving and one degrading by
11 dB is the signature of a *re-pointing* — a directional element trades one
bearing for another — and the improvement is largest in the fractional
sense on B1, the beacon that was allegedly sitting in the null. Combined
with B1's 5.6× rate recovery and 170× drop in gate rejection (§4), the
hypothesis "the whip was turned off B1" **fits every number in this file**.

**It is not established, and this pass will not assert it.** A translation
of the board across the room produces the same signature — different
distances, different multipath, some links better and some worse — and the
remount did both at once. **No artefact records the antenna's orientation
before or after.** `CLAUDE.md` failure mode **G**: the field that would
carry this (`label`) is empty on every row, so the circumstance is inferred
and not read.

**What would resolve it cheaply**, and costs no capture: a photograph or a
one-line note of the whip's bearing, written into a `label` at the start of
the next session. §2.7 of `docs/V2_SPEC.md` already adds a STATUS record;
antenna bearing belongs in it.

---

## 7. Summary of findings, by evidential status

**Established by this file** — re-derivable right now by the commands named
in §1 and §3.3:

- The capture ran **01:47:41 to 08:29:44 local, 24,123.12 s = 6.7009 h**, is
  **complete and not still running**, and **has no truncated final row**.
  **3,344,351 + 4,330,849 = 7,675,200 rows** were read end to end on both
  nodes. §0.
- **Real MAC populations: 18 on the d0wd, 14 on the S3**, against 166 and 34
  unscreened. The artefact count reconciles exactly:
  166 = 18 + 22 + **126**, and the 126 fabricated addresses arise on 141 of
  the 190 corrupt rows, the other 49 landing on already-real beacon
  addresses. On the S3, 34 = 14 + 19 + **1**, on 1 corrupt row.
  **Nothing requires a mechanism other than corruption.** §2.
- **The S3 dropped zero frames** (0 wraps, 0 negative deltas in 4,330,849
  rows, 100 % zero-drop seconds) but **is not at zero corrupt rows** — one,
  at file line 2,856,988, the first since the console move. Unscreened, that one
  row would have reported **65,536** drops on a node that dropped none. §3.1.
- **The d0wd dropped 179,609 frames, 5.0971 % loss**, 2 genuine wraps,
  endpoint cross-check exact. Unscreened the figure would be **11,910,553
  (66.3× over)**; the shipped estimator would say **48,537 (3.70× under)**.
  Three corrupt rows are invisible to the field screen and only the median
  filter catches them, worth exactly 3 × 65,536. §3.2, §3.3.
- **The d0wd's loss is 8.8× worse than 2026-08-22** (5.097 % vs 0.579 %).
  §3.2.
- **B1 is no longer below the cadence floor**: 52.249 fps on the S3 against
  a 10.0 floor, **0 of 80** 300 s blocks under it, and gate rejection down
  from **49.993 % to 0.294 %**. §4.
- **The pathological cell is now on B2/d0wd** (79.787 % reject), its third
  position after B3/s3 and B3/d0wd. A large per-(receiver, source)
  estimator bias exists, is tied to neither a beacon nor a receiver, and
  **survives co-location**. §4.1.
- **B1's inter-receiver term fell 0.00900 → 0.00168 rad/sc, 3.80σ → 0.71σ,
  a factor of 5.36**, at both window lengths. §5.1, §5.2.
- **The receiver-over-device inversion does not hold in this file**: ratio
  **0.085** against 1.78. Both terms moved — receiver ÷5.4, S3 device ×3.9.
  §5.3.
- **No step change consistent with the S3's antenna being moved occurs
  during the capture.** The largest RSSI feature is a B2-and-B3 event at
  0.117 h that moves the **two receivers in opposite directions** — which an
  S3-side antenna change cannot do — while B1 and the S3's `noise_floor`
  stay put. §6.1.

**Permitted by this file, not established:**

- That the inter-receiver term is **geometric**. The direction and size of
  B1's collapse support it; the 23× spread across three beacons at fixed
  geometry shows a substantial non-geometric residual. §5.4.
- That the S3's whip **was turned off B1** before this capture. It fits
  every number, and a translation fits them equally well. §6.2.

**Unknown, and named as unknown:**

- Whether co-location or relocation caused the change — the remount
  confounds them and **nothing across 22 → 23 August is a controlled
  comparison**. §5.5.
- The S3 antenna's orientation, before or after. `label` is empty on every
  row of both files. §6.2.
- What selects which (receiver, source) cell carries the estimator-bias
  pathology. §4.1.
- Why the S3's beacon-to-beacon device term rose 3.9×. §5.3.
- Why the d0wd's drop rate rose 8.8×. Its corrupt rows went 142 → 190 over
  the same period, but on more rows — 47.6 → 56.8 ppm, only 1.19× — so that
  is a far smaller change than the drop figure and may be unrelated. §3.2.
- Why the file holds 14 and 17 fewer rows than the live display reported.
  §0.

**Not claimed anywhere above:** no device-ID accuracy figure is derived from
this file; no `pc/rff/` (phase) number is combined with any `pc/occ/`
(amplitude) number; and no figure here is fused with `docs/DIRECTION.md`,
which describes nothing that is built.

---

## 8. For the next pass

1. **Record the antenna bearing** in `label` or the §2.7 STATUS record
   before the next capture. It is the cheapest unknown on this list and it
   currently blocks §6.2 permanently for this file.
2. **Alternate separated and co-located captures** across several sessions
   with geometry noted, per `docs/REFERENCE_CHOICE.md` §7. §5.5 explains
   why one session cannot carry this.
3. **The d0wd's 8.8× loss regression** should be understood before V2 record
   changes land on top of it.
4. **B2/d0wd's 79.8 % rejection** deserves the treatment
   `docs/POSITIVE_CONTROL_0822.md` §6 proposes for B3/d0wd — stratify by
   `inlier_ratio` and see whether the SFO difference tracks the gate. If it
   does, the cell is confounded; if not, it is usable and §5.4's residual
   needs a different explanation.
