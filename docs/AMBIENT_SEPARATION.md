# AMBIENT SEPARATION — do genuinely heterogeneous ambient devices separate
# from each other by SFO better than three same-batch ESP32 beacons do?

One question asked of the 2026-08-22 overnight capture, over its empty-room
window only. The three beacons are probably one reel and B1/B3 are a
characterised clock twin pair (`docs/LOT_HYPOTHESIS.md`), so every separation
figure this repo has measured may describe a worst case rather than a typical
one. The ambient traffic in the same six hours is real heterogeneous hardware
and is the natural control. **No ambient source had ever been successfully
phase-estimated in this repo** before this pass and the one immediately
preceding it.

Read-only. Both CSVs were opened `"rb"` and never written; nothing in
`data/raw/` was modified, renamed or deleted; the two files still read
2,529,534,604 and 2,962,429,711 bytes, unchanged from what
`docs/SEPARATION_SCALING.md` records. No serial port was opened, nothing was
flashed, nothing was staged, committed or pushed (`git diff --cached
--name-only` is empty). Two files in the repo were written by this pass:
this one and `pc/exp_ambient_separation.py`. The frame cache went to a
directory outside the repo tree, named by `$AMBSEP_CACHE`.

Running the script left `pc/__pycache__/exp_ambient_separation.cpython-310.pyc`
(49,491 bytes, 12:55), which **this session had no permission to delete**
(`rm` returns `Operation not permitted`) — the same condition
`docs/SEPARATION_SCALING.md` records for its own `.pyc`. `__pycache__/` is in
`.gitignore`, so it is not a repo artefact, but it is there. The
pre-existing `pc/exp_poscontrol_0822.py.head` and `.tail` were not touched
and are still present.

**Something else wrote to this repo while this pass was running.**
`pc/exp_reference_choice.py` (12:34) and `docs/REFERENCE_CHOICE.md` (12:44)
both have mtimes inside this session's span and were not created by it;
`REFERENCE_CHOICE.md` was not present in `ls docs/` at the start of the
session. Nothing here reads or depends on either file, but the concurrency
is recorded because it means `git status` in this session is not a clean
account of this session alone.

**Inputs and window**

| | `s3_20260822_023034.csv` (primary) | `d0wd_20260822_023034.csv` |
|---|---|---|
| data rows | 3,564,005 | 2,983,560 |
| `node_id`, every row | 108 | 68 |
| beacon frames inside the window | 3,481,255 | 2,905,126 |
| non-beacon frames inside the window | 2,345 | 2,264 |

All six figures match `docs/SEPARATION_SCALING.md` §1/§1.1 exactly.

**The window is `300 s <= t < 23,000 s`**, half-open, `t` in seconds of
`pc_time_us` since each file's own first decodable row — the same window
`pc/exp_separation_scaling.py:85` uses, ending 67 s before the operator
re-entered the room (`docs/POSITIVE_CONTROL_0822.md` §0, §2.1). 22,700 s of
empty room, 76 bins of 300 s.

**The S3 is primary**: 0 corrupt rows against the d0wd's 142
(`docs/OVERNIGHT_2026-08-22.md` §1), and its B3 cell does not reject 59 % of
its frames.

B1 = `a4:f0:0f:77:91:20`, B2 = `28:05:a5:2f:fa:48`,
B3 = `f4:2d:c9:70:72:30` (the clock twin).

**SFO only.** CFO is established dead on this capture — 0.01σ to 0.21σ on the
CFO axis, all three per-frame medians within 0.06 Hz of zero
(`docs/SEPARATION_SCALING.md` §3.3) — so every separation below is
one-dimensional. The relevant chi-square is **χ²(1) = 3.841 / 6.635**
(d = 1.960σ / 2.576σ), **not** the 5.991 / 9.210 that
`pc/rff/discriminator.py:23-24` ships, which are the 2-dof values. No 2-D
figure is reported here; the constraint was SFO alone and the CFO axis is
dead anyway. The codebase's separate ">3σ reliably separable" rule of thumb
(`pc/rff_offline.py:322`) is a rule about effect size and is unaffected by
the dof question.

---

## 0. The question, answered

**No. On the primary node, at a defensible gate, the ambient population is
not meaningfully more separable than the three beacons, and on the reading
that survives the most checks it is less so.**

At `min_inlier 0.3`, per-frame, each group measured against **its own**
pooled sd:

| group | sources | pairs | pooled sd (rad/sc) | min | median | max | raw SFO spread |
|---|---|---|---|---|---|---|---|
| beacon–beacon | 3 | 3 | 0.009730 | **0.09σ** | **0.46σ** | 0.55σ | 0.00534 |
| ambient–ambient | 8 | 28 | 0.057455 | **0.01σ** | **0.61σ** | 1.33σ | 0.07639 |

The ambient population's **raw** SFO spread is **14.3× wider** — 0.07639
against 0.00534 rad/sc, 32× against 2.3× `BETWEEN_UNIT_SD`. And it buys
almost nothing, because the ambient sources are **5.9× noisier per frame**
(pooled sd 0.0575 against 0.0097) and the two effects very nearly cancel.
The median pairwise separation improves from 0.46σ to 0.61σ — a factor of
**1.3** — and the **minimum gets worse**, 0.09σ down to 0.01σ. Neither group's
median reaches the χ²(1) 95 % line of 1.96σ, let alone 3σ.

**The heterogeneous population contains its own twins.** Two ambient pairs
are less separable than B1/B3: `54:6c:eb:15:e3:f7` vs `62:45:b4:f0:e1:97` at
**0.01σ** (raw ΔSFO 0.00031 rad/sc, 0.13 × `BETWEEN_UNIT_SD`) and
`64:fa:2b:6d:05:3b` vs `ba:80:d5:0c:18:87` at **0.01σ**. Being different
manufacturers, if they are, did not prevent a collision.

**Most of the ambient spread that does exist is not a transmitter property.**
The two receivers disagree about an ambient source's SFO by up to
**0.20397 rad/sc = 86 × `BETWEEN_UNIT_SD`** (`1c:ce:51:f3:0d:fa`, §5), the
disagreement rank-correlates with fit quality at Spearman **−0.745**, and for
that source the d0wd's slope distribution is **bimodal with its two modes
0.195 rad/sc apart** — against 2π/32 = 0.1963, the exact size of a one-turn
RANSAC mis-unwrap over 32 subcarriers. Drop the three ambient sources whose
cross-receiver disagreement exceeds the worst beacon's, and the remaining
five give **min 0.00σ, median 0.32σ, max 0.86σ** — worse than the beacons on
the median, and worse still under median/MAD (0.09σ).

**So the beacons are not a worst case, and the pessimistic reading of
`docs/SEPARATION_SCALING.md` stands.** B1/B3 at 0.69σ was not a bad draw from
a population that is otherwise fine. The population is not otherwise fine.

**Two things that did work, and are worth keeping.** The `csi_len = 128`
parse defect is not present here and the 128-length records really are valid
LLTFs (§1.2 — this was the check that could have invalidated the whole
comparison, and it passed). And one ambient source, `62:45:b4:f0:e1:97` at
RSSI −34 dBm with 100 % inlier ratio, has a **per-frame SFO sd of 0.00116
rad/sc — 7.9× tighter than the tightest beacon** and a cross-receiver disagreement of
0.00162 rad/sc, better than any beacon's. That is 20 frames and proves
nothing on its own, but it is the only evidence in this capture that the
per-frame noise floor is a link-budget problem rather than a physical one.

---

## 1. Method

One script, `pc/exp_ambient_separation.py`, from the repo root:

```
export AMBSEP_CACHE=/some/dir/outside/the/repo
D=data/raw/d0wd_20260822_023034.csv
S=data/raw/s3_20260822_023034.csv

python3 pc/exp_ambient_separation.py lltf  $S --max-rows 400000 --per-len 200
python3 pc/exp_ambient_separation.py modes $S --max-rows 300000
python3 pc/exp_ambient_separation.py modes $D --max-rows 300000

for p in $(seq 0 15); do
    python3 pc/exp_ambient_separation.py scan $S --tag s3 \
        --part $p --nparts 16 --node-mode 108 --chan-mode 6
done
for p in $(seq 0 13); do
    python3 pc/exp_ambient_separation.py scan $D --tag d0wd \
        --part $p --nparts 14 --node-mode 68 --chan-mode 6
done
python3 pc/exp_ambient_separation.py merge --tag s3   --nparts 16 --expect-rows 3564005
python3 pc/exp_ambient_separation.py merge --tag d0wd --nparts 14 --expect-rows 2983560

python3 pc/exp_ambient_separation.py census  --tags s3,d0wd
python3 pc/exp_ambient_separation.py sweep   --tags s3,d0wd
python3 pc/exp_ambient_separation.py crossrx --tags s3,d0wd --min-inlier 0.3
python3 pc/exp_ambient_separation.py crossrx --tags s3,d0wd --min-inlier 0.6
python3 pc/exp_ambient_separation.py alias   --tags s3,d0wd \
        --mac 1c:ce:51:f3:0d:fa --min-inlier 0.3
python3 pc/exp_ambient_separation.py compare --tags s3   --min-inlier 0.3 --min-frames 20
python3 pc/exp_ambient_separation.py compare --tags s3   --min-inlier 0.4 --min-frames 20
python3 pc/exp_ambient_separation.py compare --tags s3   --min-inlier 0.6 --min-frames 20
python3 pc/exp_ambient_separation.py compare --tags d0wd --min-inlier 0.3 --min-frames 20
python3 pc/exp_ambient_separation.py compare --tags d0wd --min-inlier 0.6 --min-frames 20
python3 pc/exp_ambient_separation.py compare --tags s3   --min-inlier 0.3 --min-frames 20 \
        --drop 1c:ce:51:f3:0d:fa,1e:ce:51:f3:0d:fa,ba:80:d5:0c:18:87
python3 pc/exp_ambient_separation.py compare --tags d0wd --min-inlier 0.3 --min-frames 20 \
        --drop 1c:ce:51:f3:0d:fa,1e:ce:51:f3:0d:fa,ba:80:d5:0c:18:87
```

Every figure below is from one of those commands, named per section.

**Phase work is `pc/rff/dsp.py`'s `FrameEstimator` and `WindowAggregator`.**
`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` were
**not** used: `docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 establishes all three
have the DC/guard-band index wrong.

**The DSP runs once; every gate setting re-derives from a per-frame cache.**
The argument is `docs/SEPARATION_SCALING.md` §1's and is not re-litigated
here: `FrameEstimator` state depends only on the order of that source's own
frames and on no gate, because the gates live downstream in
`WindowAggregator.feed`. The `part`/`merge` split exists only because this
host caps a shell call at ~178 s; parts are cut on line boundaries, each part
asserts that its first byte equals the previous part's last byte, and the
`FrameEstimator` state and ambient MAC table are pickled forward. `merge`
re-checks rather than asserts: the parts' rows sum to **3,564,005** and
**2,983,560**, matching `wc -l` minus the header exactly, with **0
`pc_time_us` reversals** across the 15 and 13 seams.

**The unit of observation is the per-frame slope, not a 64-frame window.**
This is forced: the largest ambient source in the window has 932 frames and
the smallest that qualifies has 20, so most ambient sources cannot fill a
single 64-frame window, and several cannot fill the
`Discriminator.MIN_CHARACTERIZED = 5` windows a model needs. A per-frame
statistic is the only one both populations can supply.
`docs/POSITIVE_CONTROL_0822.md` §3.2 already validated a per-frame estimator
against the windowed one on the beacons and found five of six cells agreeing
to better than 0.00058 rad/sc. The cost is that every sigma figure here is
**smaller** than the equivalent windowed figure, for both groups alike — §4.4
gives the conversion measured on the beacons.

**The separation statistic** is `pc/rff/discriminator.py:116-140`'s
construction — pooled covariance weighted by (n−1), returning d not d² —
restricted to the SFO axis, with the same per-source variance floor of
1 × 10⁻⁸ (rad/sc)². It was re-derived independently from the cache without
calling the script's own `sep_matrix()`, and the two agree to every digit
printed.

### 1.1 The parse defect, and the check that it is not present here

`docs/POSITIVE_CONTROL_0822.md` §1.2 records that `cs.split(",", 128)` at
`pc/exp_overnight_0822.py:303` and `pc/exp_s3_sfo_steps.py:153,590` silently
discards every `csi_len = 128` row, because `maxsplit=128` returns **at most**
129 items and a 128-value row yields exactly 128. **All ambient traffic is
128.** This script reads the field with `np.fromstring(cs, sep=",")` — the
same read as `pc/rff_offline.py:203` — and counts what it sees (`census`
TABLE 1):

| | s3 | d0wd |
|---|---|---|
| data rows | 3,564,005 | 2,983,560 |
| rows undecodable by line / by field | 0 / 0 | 0 / 0 |
| `csi_len` column = **128** | **2,444** | **2,222** |
| `csi_len` column = 256 | 3,561,558 | 2,981,272 |
| `csi_len` column = 384 | 3 | 64 |
| other `csi_len` | — | 241: 1, 0: 1 |
| rows `split(",", 128)` would have dropped | **2,444** | **2,223** |
| parsed-vector-length histogram == `csi_len` histogram | **True** | **True** |
| `node_id` | 108, all rows | 68, all rows |
| `channel` | 6, all rows | 6 × 2,983,421; 0 × 34; 236 × 4; 24 × 4 |

**The check with teeth** is `census` TABLE 3, which reports fits, not rows: a
parser carrying the defect returns zero fits for every 128-length source.
Instead, **every** ambient source in the window is fitted at 96.9 % to
100.0 % — `1c:ce:51:f3:0d:fa` 932/932 and 947/947, `ba:80:d5:0c:18:87`
899/899 and 253/253, `bc:96:e5:af:e5:7a` 175/175 and 291/291. Those are the
sources `docs/POSITIVE_CONTROL_0822.md` §3.1 lists at `len 128`. This
reproduces that document's fix on a second, independent script.

### 1.2 Are 128-length records really valid LLTFs? — the check that could
### have invalidated the comparison

`csi_to_complex` takes the first 64 complex samples
(`pc/rff/dsp.py:43-52`), so a 128-byte record (LLTF only) and a 256-byte
record (LLTF + HT-LTF) *should* both yield a valid LLTF vector. That is an
argument, not a measurement, and if the mask or ordering differed for non-HT
frames the beacon-vs-ambient comparison would be invalid rather than merely
weak. `lltf`, on 200 sampled rows of each length from the head of the S3
file:

| | parsed length 128 | parsed length 256 |
|---|---|---|
| distinct MACs in the sample | 10 (all ambient) | 4 (3 beacons + `64:fa:2b`) |
| fraction of guard-bin samples (\|k\| > 26, 11 bins) exactly zero | **1.0000** | **1.0000** |
| fraction of DC-bin samples (k = 0) exactly zero | **1.0000** | **1.0000** |
| fraction of signal-bin samples (1 ≤ \|k\| ≤ 26, 52 bins) exactly zero | 0.0022 | 0.0002 |

**The null structure is identical.** `dsp.py:22-26`'s stated layout — buffer
index 0..31 = subcarriers 0..+31, index 32..63 = subcarriers −32..−1, signal
only on 1 ≤ |k| ≤ 26 — holds on 128-length ambient rows exactly as it holds
on 256-length beacon rows. Guard bins are exactly zero on both, DC is exactly
zero on both, and 99.8 % of signal bins are non-zero on the 128s. The command
prints one full row per length verbatim in physical-k order so the claim is
inspectable rather than asserted; the sampled `1c:ce:51:f3:0d:fa` frame
yields `inlier_ratio 0.769, resid_std 0.179`, a perfectly ordinary fit.

**384-length records were not separately checked this way.** Only 3 rows on
the S3 and 64 on the d0wd carry length 384, and the one source that produces
them (`f4:69:42:f2:d2:af`) does not qualify on the primary node (3 rows).
`pc/rff/protocol.py:31` admits 384 and `csi_to_complex` would take its first
64 complex samples, but that is the same untested argument, and no result
below rests on a 384-length source.

---

## 2. CENSUS AND ELIGIBILITY

`census` TABLE 2 and TABLE 3. The artefact screen is
`docs/OVERNIGHT_2026-08-22.md` §5.2's, applied in the same order with the
same constants copied from `pc/exp_overnight_0822.py:90-97` — X decode
artefact, R sustained, P intermittent-but-corroborated-across-receivers,
S unresolved.

| class | s3 | d0wd |
|---|---|---|
| **R** sustained | 3 | 3 |
| **P** intermittent, corroborated on both nodes | 12 | 15 |
| **S** unresolved | 19 | 13 |
| **X** decode artefact | **0** | **94** |
| MACs with traffic in the window | **34** | **125** |

**Not one MAC in the S3 file is an artefact**, reproducing
`docs/OVERNIGHT_2026-08-22.md` §5.3 on the trimmed window. The counts differ
slightly from that section's whole-file 131 / 34 / 100 because this window
drops 300 s from the head and 267 s from the tail.

R is exactly the three beacons. The sources that carry enough traffic to
matter, on the primary node, over the window:

| mac | kind | `csi_len` | rows | RSSI mean/min/max | 300 s bins | duty | fitted | fit % |
|---|---|---|---|---|---|---|---|---|
| `f4:2d:c9:70:72:30` | B3 | 256 | 1,414,268 | −65.6 / −91 / −53 | 76 | 1.00 | 1,414,268 | 100.0 |
| `a4:f0:0f:77:91:20` | B1 | 256 | 1,255,513 | −67.8 / −92 / −53 | 76 | 1.00 | 1,255,512 | 100.0 |
| `28:05:a5:2f:fa:48` | B2 | 256 | 811,474 | −73.9 / −92 / −56 | 76 | 1.00 | 811,472 | 100.0 |
| `1c:ce:51:f3:0d:fa` | OUI | 128 | 932 | −36.3 / −40 / −34 | 76 | 1.00 | 932 | 100.0 |
| `ba:80:d5:0c:18:87` | LAA | 128 | 899 | −71.8 / −79 / −69 | 27 | 0.36 | 899 | 100.0 |
| `bc:96:e5:af:e5:7a` | OUI | 128 | 175 | −68.6 / −70 / −66 | 18 | 0.24 | 175 | 100.0 |
| `64:fa:2b:6d:05:3b` | OUI | 256 | 89 | −64.6 / −69 / −60 | 44 | 0.58 | 89 | 100.0 |
| `1e:ce:51:f3:0d:fa` | LAA | 128 | 76 | −36.0 / −37 / −35 | 2 | 0.03 | 76 | 100.0 |
| `54:6c:eb:15:e3:f7` | OUI | 128 | 43 | −76.4 / −80 / −72 | 31 | 0.41 | 43 | 100.0 |
| `76:eb:b0:c0:68:4d` | LAA | 128 | 32 | −81.6 / −88 / −75 | 1 | 0.01 | 31 | 96.9 |
| `62:45:b4:f0:e1:97` | LAA | 128 | 20 | −34.0 / −36 / −33 | 20 | 0.26 | 20 | 100.0 |
| `a6:11:ed:a5:b5:75` | LAA | 128 | 17 | −83.0 / −84 / −80 | 2 | 0.03 | 17 | 100.0 |
| `28:f5:2b:4f:7c:6b` | OUI | 128 | 8 | −72.1 / −73 / −71 | 5 | 0.07 | 8 | 100.0 |
| `6e:0a:30:1f:ed:21` | LAA | 128 | 7 | −75.1 / −77 / −71 | 1 | 0.01 | 7 | 100.0 |
| `a8:6d:aa:55:0d:1b` | OUI | 128 | 6 | −82.5 / −88 / −79 | 6 | 0.08 | 6 | 100.0 |

**Which sources can support an SFO estimate, stated plainly.** The inclusion
rule, fixed before the matrices were computed, is **≥ 20 accepted frames**,
the same floor `docs/POSITIVE_CONTROL_0822.md` §3.1 used. On the S3 at
`min_inlier 0.3`, **eight ambient sources qualify**: `1c:ce:51:f3:0d:fa`
(932), `ba:80:d5:0c:18:87` (812), `bc:96:e5:af:e5:7a` (159),
`64:fa:2b:6d:05:3b` (89), `1e:ce:51:f3:0d:fa` (76), `54:6c:eb:15:e3:f7` (43),
`76:eb:b0:c0:68:4d` (30) and `62:45:b4:f0:e1:97` (20).

**And for the ones that do not, the reason, distinguished as the brief asked:**

- **Genuine sparsity, on the primary node** — `a6:11:ed:a5:b5:75` (15
  accepted of 17 fitted of 17 rows), `28:f5:2b:4f:7c:6b` (8/8/8),
  `6e:0a:30:1f:ed:21` (7/7/7), `a8:6d:aa:55:0d:1b` (6/6/6),
  `7e:6d:8c:69:13:0f` (5/6/6). Every one of these has `fitted ≈ rows`: they
  are not gated out and they are not parse casualties, they simply did not
  transmit enough. Five sources, 41 frames between them.
- **Gate exclusion, not sparsity** — this is the failure the brief named, and
  it is real. At the shipped `min_inlier 0.6`, `bc:96:e5:af:e5:7a` gets
  **0 of 175** accepted on the S3 while getting 236 of 291 on the d0wd, and
  `ba:80:d5:0c:18:87` gets **0 of 899** on the S3 while
  `1c:ce:51:f3:0d:fa` gets **0 of 947** on the d0wd and 330 of 932 on the S3.
  Same devices, same six hours, acceptance flipping between 0 % and 81 %
  depending on which board heard them. §3 is about fixing this.
- **Parse exclusion — none.** Fit percentage is 96.9 % to 100.0 % for every
  ambient source on both nodes. Nothing is lost to the parser.

**These are addresses, not devices.** Four of the eight qualifying sources
have the locally-administered bit set — `62:45:b4:f0:e1:97`,
`ba:80:d5:0c:18:87`, `76:eb:b0:c0:68:4d`, `1e:ce:51:f3:0d:fa` — i.e. they are
randomised addresses, and one physical device rotates through several over
six hours. `1e:ce:51:f3:0d:fa` is `1c:ce:51:f3:0d:fa` with exactly that bit
flipped and nothing else changed. **They are almost certainly one device
counted twice**, and this pass supplies a new reason to think so: their raw
SFO means on the S3 differ by **0.01292 rad/sc**, which is small for this
population (median ambient pair 0.03502) — and their separation under the
ambient pool is **0.22σ**, the fourth-smallest of the 28 ambient pairs. §6
carries this through.

---

## 3. THE GATE, AND WHY 0.3

`sweep`. `max_resid` is held at the shipped 0.8 throughout, because
`docs/SEPARATION_SCALING.md` §4.1 established on 6.4 M frames that it rejects
**zero** of them — the largest `resid_std` anywhere in either file is 0.2202,
against a gate at 0.8. There is nothing for a residual sweep to do here and
none was run.

### 3.1 The sweep (TABLE 4, S3)

Accepted frames as a percentage of fitted frames:

| mac | fitted | @0.6 | @0.5 | @0.4 | @0.3 | @0.2 |
|---|---|---|---|---|---|---|
| B1 | 1,255,512 | 99.4 | 99.9 | 100.0 | 100.0 | 100.0 |
| B2 | 811,472 | 99.3 | 99.8 | 100.0 | 100.0 | 100.0 |
| B3 | 1,414,268 | 99.7 | 100.0 | 100.0 | 100.0 | 100.0 |
| `1c:ce:51:f3:0d:fa` | 932 | **35.4** | 91.4 | 100.0 | 100.0 | 100.0 |
| `ba:80:d5:0c:18:87` | 899 | **0.0** | 8.7 | 47.5 | 90.3 | 100.0 |
| `bc:96:e5:af:e5:7a` | 175 | **0.0** | 0.0 | 31.4 | 90.9 | 100.0 |
| `64:fa:2b:6d:05:3b` | 89 | 9.0 | 49.4 | 94.4 | 100.0 | 100.0 |
| `1e:ce:51:f3:0d:fa` | 76 | 65.8 | 100.0 | 100.0 | 100.0 | 100.0 |
| `54:6c:eb:15:e3:f7` | 43 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `76:eb:b0:c0:68:4d` | 31 | 32.3 | 45.2 | 54.8 | 96.8 | 100.0 |
| `a6:11:ed:a5:b5:75` | 17 | **0.0** | 0.0 | 29.4 | 88.2 | 100.0 |
| `62:45:b4:f0:e1:97` | 20 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |

Ambient sources reaching the 20-frame floor: **4 at 0.6, 7 at 0.4, 8 at 0.3**
on the S3; 3 at 0.6 and 10 at 0.3 on the d0wd.

### 3.2 The gain: the estimate is not converged at 0.6, and is by 0.4

TABLE 5. Median SFO per gate, S3, rad/sc — this is the argument, because it
shows the 0.6 subset is not representative of the source:

| mac | @0.6 | @0.5 | @0.4 | @0.3 | @0.2 |
|---|---|---|---|---|---|
| B1 | +0.01397 | +0.01398 | +0.01398 | +0.01398 | +0.01398 |
| B2 | +0.00959 | +0.00958 | +0.00958 | +0.00958 | +0.00958 |
| B3 | +0.01495 | +0.01496 | +0.01496 | +0.01496 | +0.01496 |
| `1c:ce:51:f3:0d:fa` | **+0.04614** | +0.05915 | **+0.06126** | +0.06126 | +0.06126 |
| `ba:80:d5:0c:18:87` | — | +0.01111 | +0.01120 | +0.00663 | +0.00683 |
| `64:fa:2b:6d:05:3b` | **−0.04017** | −0.00789 | **+0.00173** | +0.00168 | +0.00168 |
| `1e:ce:51:f3:0d:fa` | +0.04016 | +0.04751 | +0.04751 | +0.04751 | +0.04751 |
| `54:6c:eb:15:e3:f7` | +0.00572 | +0.00572 | +0.00572 | +0.00572 | +0.00572 |
| `62:45:b4:f0:e1:97` | +0.00584 | +0.00584 | +0.00584 | +0.00584 | +0.00584 |

Two things are visible at once. **The beacons do not move**: over the whole
sweep the largest change in any beacon median is 1 × 10⁻⁵ rad/sc, 0.004 ×
`BETWEEN_UNIT_SD`. Changing the gate therefore does not move the comparison
group at all, which is the single most important property of this choice.
**The ambient sources move a lot between 0.6 and 0.4 and then stop**:
`1c:ce` moves 0.01512 (6.4 × `BETWEEN_UNIT_SD`) from 0.6 to 0.4 and 0.00000
from 0.4 to 0.2; `64:fa` moves 0.04190 and then 0.00005. At 0.6 those
estimates are built on 35 % and 9 % of the source's frames, and they are not
the same number the full population gives.

### 3.3 The cost: the bias the gate exists to stop, measured

TABLE 6 does not take on trust that loosening is free. On the beacons every
inlier stratum has enough frames to be measured on its own, so the cost of
admitting a stratum can be read directly. Offsets from the `inlier ≥ 0.9`
reference, S3, rad/sc (frame counts in parentheses):

| beacon | ref (≥0.9) | [0.4,0.5) | [0.5,0.6) | [0.6,0.7) | [0.7,0.8) | [0.8,0.9) |
|---|---|---|---|---|---|---|
| B1 | +0.01384 | +0.03036 (1k) | **+0.00905** (6k) | +0.00395 (14k) | +0.00263 (42k) | +0.00202 (137k) |
| B2 | +0.00927 | −0.00927 (1k) | **−0.00593** (4k) | +0.00134 (18k) | +0.00138 (88k) | +0.00145 (205k) |
| B3 | +0.01497 | +0.01930 (0k) | **+0.00730** (4k) | −0.00113 (15k) | −0.00114 (64k) | +0.00016 (145k) |

**This is a real cost and it is not small.** A frame drawn from the
[0.5, 0.6) stratum carries a slope biased by roughly **±0.006 to ±0.009
rad/sc**, i.e. 2.5 to 3.8 × `BETWEEN_UNIT_SD`, relative to a high-quality
frame from the same transmitter; the thinly-populated [0.3, 0.5) strata are
worse still (up to +0.066 on B3, on under 1,000 frames). The median ambient
source sits at `inlier_ratio` 0.35–0.65 — squarely in the strata that carry
that bias. **Every ambient SFO value in this document should be read with an
uncertainty of that order attached**, and that is on top of the sampling
error the bootstrap reports.

It is also the reason the ambient pooled sd *rises* as the gate loosens
(0.0112 at 0.6 → 0.0275 at 0.4 → 0.0575 at 0.3): some of that widening is
the sources and some of it is admitted fit noise, and this pass cannot
apportion it.

### 3.4 The floor beneath the sweep

TABLE 7. Over all 3,483,561 fitted frames on the S3, the **minimum
`inlier_ratio` observed is exactly 0.2500**. `pc/rff/dsp.py:97` rejects any
RANSAC hypothesis with fewer than `max(4, n // 4)` inliers, and with n = 52
usable subcarriers that is 13/52 = 0.250. **No frame can reach the aggregator
with `inlier_ratio` below 0.25**, so `min_inlier 0.2` is degenerate with 0.25
and the sweep has already hit the estimator's own floor. There is nothing
below 0.3 worth exploring except the last 0.05.

### 3.5 The choice

**`min_inlier = 0.3`, `max_resid = 0.8`, ≥ 20 accepted frames.** Against:

- it admits ≥ 88 % of the fitted frames of every source that qualifies, so no
  source's estimate is a fit-quality-selected minority of itself (§3.1);
- per-source estimates are converged by 0.4 and flat from 0.4 to 0.2 for
  seven of the nine sources with enough frames to tell (§3.2);
- it moves the beacons by ≤ 1 × 10⁻⁵ rad/sc, so it cannot manufacture a group
  difference by moving the comparison group (§3.2);
- it sits just above the estimator's hard consensus floor of 0.25 (§3.4);
- and it does not inherit 0.6, which starves 16 of 20 addresses and gives
  0 % acceptance on one node against 37.5 % on the other for the same device
  (§2, and `docs/POSITIVE_CONTROL_0822.md` §3.4).

The cost is §3.3's admitted bias of order ±0.006 to ±0.009 rad/sc on
ambient sources, and an ambient pooled sd inflated by an unknown part of the
same effect. **Both directions of the trade are shown in §4.2, at 0.6, 0.4
and 0.3, because the answer to the headline question depends on the gate and
it would be dishonest to report only one column.**

---

## 4. THE COMPARISON

`compare --tags s3 --min-inlier 0.3 --min-frames 20`. Three beacons and eight
ambient sources. Short labels are the last three MAC octets.

### 4.1 The three matrices

**Beacons only, pooled over beacons** (pooled sd 0.009730 rad/sc):

| | B1 | B2 | B3 | mean SFO | n frames |
|---|---|---|---|---|---|
| B1 | . | 0.46 | **0.09** | +0.01422 | 1,255,501 |
| B2 | 0.46 | . | 0.55 | +0.00972 | 811,455 |
| B3 | **0.09** | 0.55 | . | +0.01506 | 1,414,267 |

**Ambient only, pooled over ambient** (pooled sd 0.057455 rad/sc):

| | f3:0d:fa | af:e5:7a | 6d:05:3b | 15:e3:f7 | f0:e1:97 | 0c:18:87 | c0:68:4d | f3:0d:fa* | mean SFO | n |
|---|---|---|---|---|---|---|---|---|---|---|
| `1c:ce…f3:0d:fa` | . | 0.34 | 1.32 | 0.98 | 0.98 | 1.33 | 0.71 | 0.22 | +0.06234 | 932 |
| `bc:96…af:e5:7a` | 0.34 | . | 0.97 | 0.64 | 0.63 | 0.98 | 0.37 | 0.12 | +0.04253 | 159 |
| `64:fa…6d:05:3b` | 1.32 | 0.97 | . | 0.34 | 0.34 | **0.01** | 0.60 | 1.09 | −0.01346 | 89 |
| `54:6c…15:e3:f7` | 0.98 | 0.64 | 0.34 | . | **0.01** | 0.35 | 0.27 | 0.76 | +0.00589 | 43 |
| `62:45…f0:e1:97` | 0.98 | 0.63 | 0.34 | **0.01** | . | 0.35 | 0.26 | 0.75 | +0.00621 | 20 |
| `ba:80…0c:18:87` | 1.33 | 0.98 | **0.01** | 0.35 | 0.35 | . | 0.61 | 1.10 | −0.01405 | 812 |
| `76:eb…c0:68:4d` | 0.71 | 0.37 | 0.60 | 0.27 | 0.26 | 0.61 | . | 0.49 | +0.02127 | 30 |
| `1e:ce…f3:0d:fa`* | 0.22 | 0.12 | 1.09 | 0.76 | 0.75 | 1.10 | 0.49 | . | +0.04942 | 76 |

\* `1e:ce:51:f3:0d:fa`, the LAA-bit-flipped twin of `1c:ce:51:f3:0d:fa`,
almost certainly the same physical device (§2, §6).

**No ambient pair reaches 1.34σ.** The largest is `ba:80` vs `1c:ce` at
1.33σ, below the χ²(1) 95 % line of 1.960σ.

**Cross, beacons versus ambient.** A cross matrix has no natural single
denominator: the beacon pool is 0.009730 and the ambient pool 0.057455, a
factor of 5.9. Under one common pool over all eleven sources (0.009831
rad/sc, which is within 1 % of the beacon-only pool because the beacons
contribute 3,481,223 of the 3,483,384 frames), the cross separations run:

| | B1 | B2 | B3 |
|---|---|---|---|
| `1c:ce…f3:0d:fa` | 4.89 | 5.35 | 4.81 |
| `1e:ce…f3:0d:fa` | 3.58 | 4.04 | 3.49 |
| `bc:96…af:e5:7a` | 2.88 | 3.34 | 2.79 |
| `ba:80…0c:18:87` | 2.88 | 2.42 | 2.96 |
| `64:fa…6d:05:3b` | 2.82 | 2.36 | 2.90 |
| `76:eb…c0:68:4d` | 0.72 | 1.17 | 0.63 |
| `54:6c…15:e3:f7` | 0.85 | **0.39** | 0.93 |
| `62:45…f0:e1:97` | 0.82 | **0.36** | 0.90 |

Cross: min 0.36σ, median 2.80σ, max 5.35σ. **Divide by the same numbers
under the ambient pool instead and every entry shrinks by 5.85×** — cross
min 0.06σ, median 0.48σ, max 0.91σ. The two ambient sources that are hardest
to tell from a beacon, `54:6c` and `62:45`, are the two whose own SFO values
sit inside the beacon cluster.

### 4.2 The answer, and its dependence on the gate

Each group against **its own** pooled sd, per-frame, S3:

| gate | group | srcs | pairs | pooled sd | min | median | max | raw min | raw median | raw spread |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.6 | beacon | 3 | 3 | 0.008267 | 0.11 | 0.53 | 0.64 | 0.00087 | 0.00442 | 0.00529 |
| 0.6 | ambient | 4 | 6 | 0.011212 | 0.03 | **3.14** | 3.57 | 0.00031 | 0.03517 | 0.04008 |
| 0.4 | beacon | 3 | 3 | 0.009692 | 0.09 | 0.46 | 0.55 | 0.00084 | 0.00450 | 0.00533 |
| 0.4 | ambient | 7 | 21 | 0.027472 | 0.01 | **1.02** | 2.64 | 0.00031 | 0.02810 | 0.07247 |
| **0.3** | **beacon** | **3** | **3** | **0.009730** | **0.09** | **0.46** | **0.55** | 0.00084 | 0.00450 | **0.00534** |
| **0.3** | **ambient** | **8** | **28** | **0.057455** | **0.01** | **0.61** | **1.33** | 0.00031 | 0.03502 | **0.07639** |

**The answer depends on the gate, and this is the honest statement of it.**
At the shipped 0.6 the ambient population looks **5.9× more separable** than
the beacons (3.14σ against 0.53σ). At 0.3 it looks **1.3×** more separable
(0.61σ against 0.46σ). The 0.6 column is not usable as an answer, for the
same reason `docs/SEPARATION_SCALING.md` §4.4 rejects the d0wd's
tightened-gate numbers: the gate is not selecting good frames from a
representative population, it is **deleting the wide sources**. Four of the
sixteen addresses survive it, they survive by having the cleanest fits, and
their pooled sd (0.0112) is measured on that selection. §3.2 shows their
central values are not even converged.

**Two figures are gate-robust and should carry the weight:**

- the **raw spread**, which is denominator-free: **0.076 rad/sc ambient
  against 0.0053 beacon at gate 0.3**, and 0.040 against 0.0053 at gate 0.6 —
  the ambient population is **7.5× to 14.3× wider in rad/sc** at every gate
  swept. That is the part of the operator's hypothesis that is true.
- the **minimum**, which is what a security use case cares about: **0.01σ to
  0.03σ ambient against 0.09σ to 0.11σ beacon**, at every gate swept. The
  heterogeneous population's worst pair is worse than the clock twins at
  every gate. That is the part that is not true.

**The robustness check.** Median/MAD in place of mean/variance, each group
against its own pool, gate 0.3: beacon min 0.20σ / median 0.89σ / max 1.09σ
(pooled sd 0.004916); ambient min 0.00σ / median 0.77σ / max 2.11σ (pooled sd
0.028303). The direction is unchanged and the magnitude of the ambient
advantage shrinks further, to 0.87×— i.e. under a robust estimator the
ambient median is *below* the beacon median. Nothing here rests on a mean
being dragged by a handful of wild frames on a 20-frame source.

### 4.3 Can you actually tell the pair apart with the frames you have?

The sigma columns above divide by a population sd and charge a source nothing
for having 20 frames. This divides by the standard error of the difference of
means instead, which does:

| group | pairs | min \|t\| | median \|t\| | max \|t\| | pairs with \|t\| > 3 |
|---|---|---|---|---|---|
| beacon–beacon | 3 | 69.6 | 318.7 | 406.6 | **3 / 3** |
| ambient–ambient | 28 | 0.07 | 6.00 | 81.4 | **16 / 28** |
| beacon–ambient | 24 | 0.37 | 7.56 | 82.3 | 19 / 24 |

**All three beacon pairs are statistically distinguishable and none is
practically separable.** That contrast is the whole problem in one table: with
1.3 M frames you can establish that B1's mean differs from B3's at t = 70,
and the distributions still overlap so much that a single window cannot tell
them apart. Sixteen of 28 ambient pairs clear |t| > 3 despite having 20 to 932
frames — but their overlap is worse, not better.

### 4.4 Two controls on the comparison itself

**Matched-n.** Subsampling each beacon to 82 frames — the median qualifying
ambient count — 200 draws: B1–B2 0.47σ [0.12, 0.85], B1–B3 0.14σ [0.01, 0.40],
B2–B3 0.60σ [0.25, 1.02], against full-n 0.46 / 0.09 / 0.55. **The beacon
separations survive the subsample**, so the group difference is not an
artefact of the beacons having 40,000× more frames.

**Continuity with the windowed literature.** The same beacons, same gate,
aggregated by the real `pc/rff/dsp.py:WindowAggregator(64, 0.3, 0.8)`:
**B1–B2 2.94σ, B1–B3 0.69σ, B2–B3 3.63σ**, pooled sd 0.001500, on
19,617 / 12,678 / 22,097 windows.
`docs/SEPARATION_SCALING.md` §3.1's shipped-configuration row reads **2.93 /
0.69 / 3.62** on 19,506 / 12,588 / 22,029 windows. **Three of three
separations agree to 0.01σ**, on a different script, a different cache and a
different gate. That is the reproduction check for this whole pass, and it
also gives the conversion: 64-frame windowing multiplies the beacon
separations by about **6.4×** (0.46σ → 2.94σ median). Ambient sources cannot
be windowed, so **no ambient figure in this document has had that 6.4×
applied, and none should be compared to a windowed number** without it.

---

## 5. THE AMBIENT SPREAD IS PARTLY NOT A TRANSMITTER PROPERTY

`crossrx` and `alias`. This section is why §0's answer is stated as firmly as
it is, and it is the finding this pass did not go looking for.

A crystal property must read the same on both boards. `crossrx` at
`min_inlier 0.3`, sorted by disagreement:

| mac | kind | s3 median | n | med inlier | d0wd median | n | med inlier | diff | × `BETWEEN_UNIT_SD` |
|---|---|---|---|---|---|---|---|---|---|
| `62:45:b4:f0:e1:97` | LAA | +0.00584 | 20 | 1.000 | +0.00422 | 20 | 0.981 | **+0.00162** | **0.7** |
| `64:fa:2b:6d:05:3b` | OUI | +0.00168 | 89 | 0.481 | +0.00659 | 29 | 0.442 | −0.00491 | 2.1 |
| `a4:f0:0f:77:91:20` | B1 | +0.01398 | 1,255,501 | 0.962 | +0.02216 | 860,203 | 0.712 | −0.00818 | 3.5 |
| `76:eb:b0:c0:68:4d` | LAA | +0.00141 | 30 | 0.442 | −0.00919 | 209 | 0.538 | +0.01061 | 4.5 |
| `28:05:a5:2f:fa:48` | B2 | +0.00958 | 811,455 | 0.923 | +0.02650 | 896,065 | 0.788 | −0.01692 | 7.1 |
| `54:6c:eb:15:e3:f7` | OUI | +0.00572 | 43 | 0.846 | +0.02549 | 28 | 0.644 | −0.01978 | 8.3 |
| `bc:96:e5:af:e5:7a` | OUI | +0.02767 | 159 | 0.365 | −0.01834 | 291 | 0.673 | +0.04602 | 19.4 |
| `f4:2d:c9:70:72:30` | B3 | +0.01496 | 1,414,267 | 0.962 | +0.07074 | 1,147,687 | 0.596 | −0.05579 | 23.5 |
| `ba:80:d5:0c:18:87` | LAA | +0.00663 | 812 | 0.385 | −0.05775 | 253 | 0.500 | +0.06438 | 27.2 |
| `1e:ce:51:f3:0d:fa` | LAA | +0.04751 | 76 | 0.635 | −0.14399 | 88 | 0.365 | **+0.19150** | **80.8** |
| `1c:ce:51:f3:0d:fa` | OUI | +0.06126 | 932 | 0.577 | −0.14270 | 942 | 0.365 | **+0.20397** | **86.1** |

Spearman(min median `inlier_ratio`, |diff|) over these 11 sources: **−0.745**.
Over the four that survive `min_inlier 0.6`: −0.800.

**The mechanism, measured.** `alias --mac 1c:ce:51:f3:0d:fa`. On the S3 the
932 accepted slopes are a single unimodal distribution centred at +0.0613
(5th–95th percentile +0.0323 to +0.0956). On the d0wd the 942 accepted slopes
are **bimodal**: a dominant mode at about −0.145 carrying ~880 frames, and a
second mode at **+0.031 to +0.063 carrying 47 frames** — which is the S3's
answer. The two modes are about **0.195 rad/sc apart**.

A RANSAC consensus subset that sits one turn away from the rest shifts the
fitted slope by exactly **2π/Δk**, where Δk is the span of the subset:

| Δk | 2π/Δk |
|---|---|
| 52 (all usable subcarriers) | 0.1208 |
| 40 | 0.1571 |
| **32** | **0.1963** |
| 26 | 0.2417 |

**0.195 against 0.1963.** The d0wd's estimate for this device is dominated by
a one-turn mis-unwrap over roughly 32 subcarriers, and the tell is in the
census: its median `inlier_ratio` for this source is 0.365, meaning RANSAC's
winning consensus is about 19 of 52 points — a subset small enough to sit on
a wrong branch and still win.

**What this does and does not license.** It establishes that the largest
ambient SFO values in this capture are **not reproducible across receivers**
and that at least one of them has a specific, quantitatively matching
estimator explanation. It does **not** establish that every large ambient
slope is a mis-unwrap; only `1c:ce` was examined this way.

**The comparison with the unstable sources removed.** Dropping the three
ambient sources whose cross-receiver disagreement exceeds the worst beacon's
(0.05579) — `1c:ce`, `1e:ce`, `ba:80` — leaves five, and on the S3 at gate 0.3:

| group | srcs | pairs | pooled sd | min | median | max | raw spread |
|---|---|---|---|---|---|---|---|
| beacon | 3 | 3 | 0.009730 | 0.09 | **0.46** | 0.55 | 0.00534 |
| ambient (5, cross-rx stable) | 5 | 10 | 0.064829 | 0.00 | **0.32** | 0.86 | 0.05599 |

Robust (median/MAD): beacon median **0.89σ**, ambient median **0.09σ**.
**On the reading that survives the cross-receiver check, the ambient
population is less separable than the beacons, not more.** The raw spread
stays 10.5× the beacons', so the wide spread is not entirely an artefact —
but what is left of it does not convert into separation.

### 5.1 The secondary node agrees on the direction

`compare --tags d0wd`. Each group against its own pool:

| gate | group | srcs | pooled sd | min | median | max |
|---|---|---|---|---|---|---|
| 0.6 | beacon | 3 | 0.011450 | 0.41 | 3.85 | 4.25 |
| 0.6 | ambient | 3 | 0.016871 | 0.16 | 1.12 | 1.28 |
| 0.3 | beacon | 3 | 0.018224 | 0.27 | 2.15 | 2.41 |
| 0.3 | ambient | 10 | 0.047731 | 0.00 | 1.04 | 3.52 |
| 0.3 | ambient (7, cross-rx stable) | 7 | 0.054460 | 0.00 | 0.42 | 0.91 |

On the d0wd the ambient median is **below** the beacon median at every gate.
**But the d0wd's beacon numbers must not be quoted**: they are inflated by the
B3/d0wd cell that reads +0.0707 where the same beacon at the same moment
reads +0.0150 on the S3, which `docs/SEPARATION_SCALING.md` §3.2 and
`docs/OVERNIGHT_2026-08-22.md` §3.4 both establish is an estimator-bias
artefact. What the d0wd contributes is the *ambient* column and the
cross-receiver comparison of §5, not a second opinion on the beacons.

---

## 6. THE LIMITS

**Window counts are small and the intervals are wide.** Six of the eight
qualifying ambient sources have between 20 and 159 accepted frames. Bootstrap
95 % CIs at gate 0.3 under the common pool, for the pairs the argument uses:

| pair | n_a | n_b | d | 95 % CI |
|---|---|---|---|---|
| `54:6c` vs `62:45` | 43 | 20 | 0.03 | [0.00, 0.32] |
| `64:fa` vs `ba:80` | 89 | 812 | 0.06 | [0.03, 1.91] |
| B1 vs B3 | 1,255,501 | 1,414,267 | 0.09 | [0.06, 0.10] |
| `76:eb` vs each of its 10 partners | 30 | 20–932 | 0.63–4.18 | **[0.05, 7.44]** across the 10 |
| `1c:ce` vs `ba:80` | 932 | 812 | 7.77 | [7.19, 8.32] |

**`76:eb:b0:c0:68:4d`'s every separation has a CI spanning 0.05σ to
7.44σ.** It has 30 accepted frames with a per-frame sd of 0.093 rad/sc — the
widest source in the capture — and its 32 rows all fall in **one** 300 s bin
out of 76. It should not be read as a characterised device at all, and no
conclusion above turns on it. `64:fa:2b:6d:05:3b` (89 frames, sd 0.073) and
`bc:96:e5:af:e5:7a` (159 frames, sd 0.066) are the next weakest. The
bootstrap resamples frames and models neither autocorrelation nor §3.3's
gate-admitted bias, so **every interval here understates**.

**Duty cycle undercuts "over six hours" for most sources.** `1c:ce` is
present in all 76 bins, `64:fa` in 44, `54:6c` in 31, `ba:80` in 27,
`62:45` in 20 — but `1e:ce` in **2** and `76:eb` in **1**. A source seen in
one bin has been observed for at most five minutes of a 6.3-hour capture, and
`docs/SEPARATION_SCALING.md` §2 established that the SFO estimate drifts on
timescales of tens to hundreds of seconds. **Two of the eight "sources" are
five-minute snapshots**, and their SFO values are single points on a drifting
series, not six-hour averages like the beacons'.

**Eight of the seventeen corroborated ambient addresses are randomised**
(`docs/OVERNIGHT_2026-08-22.md` §5.3, whole-file), **and four of this pass's
eight qualifiers are.** `62:45:b4:f0:e1:97`, `ba:80:d5:0c:18:87`,
`76:eb:b0:c0:68:4d` and `1e:ce:51:f3:0d:fa` all have the
locally-administered bit set. An address is not a device: one phone rotating
its MAC appears here as several "devices", and the ambient-population
statistics are computed over **addresses**.

The concrete case is `1c:ce:51:f3:0d:fa` / `1e:ce:51:f3:0d:fa`, identical but
for that bit, both at RSSI ≈ −35 dBm, and this pass adds evidence they are
one device: their separation is **0.22σ**, fourth-smallest of 28 ambient
pairs, and they are the two sources with the largest and second-largest
cross-receiver disagreement (86.1× and 80.8× `BETWEEN_UNIT_SD`) — i.e. they
fail in the same way, which is what one device does and not what two
independent devices do. **If they are one device, the ambient population is
seven addresses over as few as five physical devices**, four of the seven
carrying randomised addresses, and the ambient matrix contains at least one
same-device pair masquerading as a cross-device separation.

**The gate-admitted bias of §3.3 sits on every ambient number.** ±0.006 to
±0.009 rad/sc at the [0.5, 0.6) stratum, worse below it, and the median
ambient source sits in exactly those strata. That is 2.5–3.8 ×
`BETWEEN_UNIT_SD` and it is comparable to several of the ambient pairwise
raw gaps. It cannot be removed by more frames.

**No device is identified.** No OUI database was consulted, no traffic
content is in these files, and nothing here says which ambient sources are
phones, laptops or anything else. "Heterogeneous hardware" is an inference
from the address space and the RSSI/duty patterns, not an observation.

**This is one room, one night, one channel, one pair of receivers.** The
receiver-versus-position confound named in `docs/DUAL_RX_2026-08-21.md` §6
is untouched; the operator states the nodes were not swapped.

---

## 7. Established / permitted / unknown

**Established by this pass, from these files:**

- A `csi_len = 128` record is a valid LLTF under `pc/rff/dsp.py`'s mask and
  ordering. Guard bins (|k| > 26) and DC are **exactly zero in 200 of 200**
  sampled 128-length rows, identically to 200 of 200 sampled 256-length rows,
  and 99.78 % of signal bins are non-zero. §1.2.
- The `split(",", 128)` defect is not present here: 2,444 and 2,222
  128-length rows parsed, parsed-length histogram equals the `csi_len`
  histogram row for row on both files, and every ambient source is fitted at
  96.9–100.0 %. §1.1.
- Over the window on the S3: 34 addresses carry traffic, of which **15 are
  classified R or P** (3 beacons + 12 ambient), 19 are unresolved and **0 are
  decode artefacts**; **8 ambient sources qualify at `min_inlier 0.3`** with 20
  to 932 accepted frames. On the d0wd, **94 of 125** addresses are decode
  artefacts. §2.
- Five ambient sources fail the 20-frame floor from **genuine sparsity**
  (fitted ≈ rows, 41 frames between them); the sources that fail at
  `min_inlier 0.6` fail from the **gate**, not sparsity and not the parser —
  0 of 175, 0 of 899 and 0 of 947 accepted on one node while the other node
  accepts 81 %, 3 % and 35 % of the same devices. §2.
- The estimator's own consensus floor is `inlier_ratio` = **0.2500** exactly,
  over all 3,483,561 fitted S3 frames, because `dsp.py:97` requires
  `max(4, n//4)` = 13 of 52 inliers. A `min_inlier` below 0.25 is degenerate.
  §3.4.
- Moving `min_inlier` from 0.6 to 0.2 moves every beacon's median SFO by
  ≤ 1 × 10⁻⁵ rad/sc, and moves ambient medians by up to 0.042 rad/sc between
  0.6 and 0.4 and by ≤ 5 × 10⁻⁵ between 0.4 and 0.2. §3.2.
- Admitting a low-inlier frame costs a measurable bias: on the beacons, the
  [0.5, 0.6) stratum's median sits **+0.00905 / −0.00593 / +0.00730 rad/sc**
  from the ≥ 0.9 reference. §3.3.
- At gate 0.3 on the S3, per-frame, each group against its own pool:
  **beacons min 0.09σ, median 0.46σ, max 0.55σ**, raw spread 0.00534 rad/sc;
  **ambient (8 sources) min 0.01σ, median 0.61σ, max 1.33σ**, raw spread
  0.07639 rad/sc. §4.2.
- The ambient population's raw SFO spread is **7.5× to 14.3×** the beacons'
  at every gate swept; its per-frame pooled sd is **1.4× to 5.9×** the
  beacons'; its **minimum** pairwise separation is **worse** than the
  beacons' at every gate swept. §4.2.
- No ambient pair reaches 1.34σ under the ambient pool; two ambient pairs
  are at 0.01σ. §4.1.
- The beacon separations survive subsampling to 82 frames (0.47 / 0.14 /
  0.60 against full-n 0.46 / 0.09 / 0.55), so the group comparison is not an
  n artefact. §4.4.
- Reproduction: the same beacons through the real `WindowAggregator(64, …)`
  give **2.94 / 0.69 / 3.63σ** against `docs/SEPARATION_SCALING.md` §3.1's
  **2.93 / 0.69 / 3.62σ**, on a different script and cache. §4.4.
- The two receivers disagree about an ambient source's SFO by up to
  **0.20397 rad/sc (86.1 × `BETWEEN_UNIT_SD`)**, and the disagreement
  rank-correlates with fit quality at Spearman **−0.745** over 11 sources.
  §5.
- `1c:ce:51:f3:0d:fa`'s d0wd slope distribution is bimodal with modes
  **≈ 0.195 rad/sc** apart, against 2π/32 = **0.1963**, at a median
  `inlier_ratio` of 0.365 (≈ 19 of 52 points in consensus). §5.
- With the three cross-receiver-unstable ambient sources removed, the ambient
  median falls to **0.32σ** (robust: 0.09σ) against the beacons' 0.46σ
  (robust: 0.89σ). §5.

**Permitted but not established:**

- That the large ambient cross-receiver disagreements are *generally*
  one-turn RANSAC mis-unwraps. The 2π/Δk arithmetic matches for `1c:ce` to
  0.7 %, and only `1c:ce` was examined this way. §5.
- That `1c:ce:51:f3:0d:fa` and `1e:ce:51:f3:0d:fa` are one physical device.
  Three independent lines point that way (one-bit address difference,
  0.22σ separation, both failing the cross-receiver check in the same
  direction and by the largest margins), and none is proof. §6.
- That the ambient population's per-frame noise is a link-budget effect
  rather than a physical one. `62:45:b4:f0:e1:97` at RSSI −34 dBm and 100 %
  inlier ratio has a per-frame sd of **0.00116** against the three beacons'
  0.01041 / 0.00956 / 0.00918 — **7.9× tighter than the tightest beacon** —
  on 20 frames. One source, 20 frames.
- That the ambient sources are heterogeneous hardware at all. No OUI lookup
  was done; the inference is from the address space. §6.
- How much of the ambient pooled sd rising from 0.0112 to 0.0575 as the gate
  loosens is the sources and how much is admitted fit noise. §3.3.

**Unknown, and not addressed by this capture:**

- Whether an ambient population *observed as long as the beacons were* would
  separate. Every ambient source here has 20–932 frames against the beacons'
  1.3 M, so the 6.4× that windowing buys the beacons (§4.4) is simply
  unavailable to them, and this pass cannot say what the ambient numbers
  would be with it.
- Whether the slope's timing-offset component can be separated from its
  sampling-frequency component. `pc/rff/dsp.py`'s own docstring says the
  slope carries both and that only the sampling part is crystal-bound; §5
  says the non-crystal part dominates on weak sources; nothing here
  decomposes it.
- Whether any of these addresses is a beacon under a different address, or
  which physical devices the 8 qualifying addresses correspond to.
- The receiver-versus-position confound. `docs/DUAL_RX_2026-08-21.md` §6's
  swap-and-repeat is still outstanding and §5 is a fresh reason to run it: the
  cross-receiver disagreements measured here cannot be attributed to the
  board rather than the corner of the room.
- Whether a different feature separates either population.
  `docs/SEPARATION_SCALING.md` §3.3 already showed the CFO axis is dead, so
  the feature space is one-dimensional, and this pass adds nothing to that.

---

## 8. Figures in this document that should not be quoted alone

- **"The ambient population is 5.9× more separable" (3.14σ vs 0.53σ, gate
  0.6).** True as arithmetic on four addresses that survive a gate that
  deletes twelve, whose central values §3.2 shows are not converged, and
  whose pooled sd is measured on that selection. This is the same failure
  mode `docs/SEPARATION_SCALING.md` §4.4 identifies on the d0wd. §4.2.
- **The cross matrix's 2.36σ–5.35σ.** Computed under a pool that the beacons
  supply 3,481,223 of 3,483,384 frames to. Under the ambient pool the same numbers
  are 0.40σ–0.91σ. A cross matrix has no single honest denominator and both
  are printed for that reason. §4.1.
- **7.77σ, 7.71σ, 6.46σ and the other large ambient–ambient figures.** All are
  under the beacon-dominated common pool, and all involve `1c:ce` or `ba:80`
  — the two sources with the largest cross-receiver disagreements (86.1× and
  27.2× `BETWEEN_UNIT_SD`). §4.1, §5.
- **Any separation involving `76:eb:b0:c0:68:4d`.** 30 frames, per-frame sd
  0.093 rad/sc, all 32 rows in one 300 s bin of 76, bootstrap CIs spanning
  0.05σ to 7.4σ. §6.
- **`62:45:b4:f0:e1:97`'s 0.00116 rad/sc per-frame sd.** Twenty frames. It is
  the most encouraging number in this capture and it is twenty frames. §0, §7.
- **The d0wd's beacon separations (3.85σ at gate 0.6, 2.15σ at 0.3).**
  Inflated by the B3/d0wd estimator-bias cell that
  `docs/SEPARATION_SCALING.md` §3.2 and `docs/OVERNIGHT_2026-08-22.md` §3.4
  both exclude. §5.1.
- **"8 ambient sources".** Eight *addresses*, four of them randomised, at
  least two of them probably one device. §6.
- **Every sigma figure in §4.** Per-frame, not windowed. The beacons'
  own windowed equivalents are 6.4× larger (§4.4), and no ambient source has
  enough frames to be windowed. Do not compare these to
  `docs/SEPARATION_SCALING.md`'s numbers without that factor.

---

## 9. What would settle the rest

1. **Decompose the slope.** §5 is the most consequential thing this pass
   found and it is half-diagnosed. `pc/rff/dsp.py`'s slope is
   timing-plus-sampling offset; if the timing part can be estimated per frame
   and removed, every ambient number here changes, and possibly the beacon
   numbers too. The frame cache this pass builds already holds per-frame
   `slope`, `inlier_ratio`, `resid_std` and RSSI for 6.4 M frames, so this
   can be tried without re-reading the CSVs.
2. **Test the mis-unwrap hypothesis properly.** Run the `alias` distribution
   check on all eight qualifying ambient sources, on both nodes, and count
   how many of the large cross-receiver disagreements land within a few
   percent of 2π/Δk for a plausible Δk. §5 did this for one source.
3. **Swap the two nodes' positions and repeat.** Still outstanding
   (`docs/DUAL_RX_2026-08-21.md` §6). §5's finding that cross-receiver
   disagreement tracks fit quality makes it more valuable, not less: it
   predicts the disagreement follows the *weaker link*, which a swap tests
   directly.
4. **Capture a cross-manufacturer source deliberately, at high RSSI, for
   hours.** The single best ambient source here — `62:45:b4:f0:e1:97`,
   −34 dBm, 100 % inlier, per-frame sd 7.9× tighter than the tightest beacon — gave 20
   frames in six hours. A known non-ESP32 device parked next to the receiver
   and made to transmit continuously would answer the headline question
   properly, with the observation time the beacons get. That is the
   experiment this document is a substitute for.
