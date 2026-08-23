# POSITIVE CONTROL — the last minutes of the 2026-08-22 overnight capture,
# and whether d0wd − s3 SFO is a receiver-pair constant

Two analyses of the capture already on disk. No new hardware run: no serial
port was opened, nothing was flashed. `data/raw/*` was opened `"rb"` only —
both files still read 2,529,534,604 and 2,962,429,711 bytes, last modified
`2026-08-22 08:58:22.55` and `08:58:22.41`, unchanged before and after
(`ls -l --time-style=full-iso`). Nothing was staged, committed or pushed.

Repo files written by this pass: this one and `pc/exp_poscontrol_0822.py`.
Caches went to `/tmp/poscontrol_0822_cache`, outside the repo tree. **Two
scratch files, `pc/exp_poscontrol_0822.py.head` and `.tail`, were created in
error while splicing the script and this session had no permission to delete
them; each has been overwritten with a one-line note saying so. They should
be deleted.**

**New information from the operator**, recorded as stated and not verified by
these files: he re-entered the room and sat at his desk **approximately five
minutes before the capture ended**. `docs/OVERNIGHT_2026-08-22.md` was written
without this and labelled the late excursions "final minutes" / shutdown.

---

## 0. The two questions, answered

**Analysis 1 — does the 2026-08-21 t = 930 s signature reappear at the end of
this capture?**

**Yes, in most of its parts, but on the other receiver, and it starts at
t = 23,067–23,137 s, which is 130–200 s before the last row, not 300.**
Something changes on **both** nodes at that moment: RSSI steps on all three
beacons on both, SFO moves on all three on both, `resid_std` and frame-reject
move with it, and on the S3 the `noise_floor` leaves the value it has held all
night and never returns to it. The largest single effect is **B3/d0wd's SFO,
−0.05410 rad/sc (22.8 × `BETWEEN_UNIT_SD`), with its reject rate collapsing
57.2 % → 22.5 %** — which is what B3/s3 did on 08-21 (51.6 % → 0.2 %, SFO
−0.05073). **The anomaly reproduces in the high-reject cell, and that cell is
on the d0wd this session** (`docs/OVERNIGHT_2026-08-22.md` §3.1). The S3's own
SFO moves are much the smaller half of the event this time: 0.68, 3.99 and
1.77 × `BETWEEN_UNIT_SD`, against 1.96, 7.54 and 21.40 × for the same three
beacons on the S3 on 08-21.

Two parts of the 08-21 signature **do not** reproduce, and they are stated
here rather than left to §2.6: the **sign is reversed on the S3** — on 08-21 it
gained 1.6–6.8 dB of RSSI and its `noise_floor` fell 0.63 dB; tonight it loses
1.5–3.7 dB and its `noise_floor` rises 0.65 dB — and **the receiver asymmetry
is gone**: on 08-21 the desk moved by ≤ 1.4 dB while the S3 moved by up to
6.8 dB, whereas tonight both nodes move and they move in **opposite
directions** (d0wd RSSI +0.3 to +1.7 dB, s3 −1.5 to −3.7 dB).

**Analysis 2 — is the d0wd − s3 SFO difference the same for every source?**

**No, and the number of sources it rests on is four, not twenty.** The
difference is +0.05314, +0.01001, +0.01501 for B3, B1, B2 and **−0.00189 for
the one ambient source that can support the estimate**, a range of
**0.05503 rad/sc = 23.2 × `BETWEEN_UNIT_SD`**, with **6 of 6 pairs of 95 % CIs
disjoint** and the ambient source's sign opposite to all three beacons. This
does not contradict `docs/DUAL_RX_2026-08-21.md` §3.4 and does not rehabilitate
the constant-offset hypothesis. **What it mostly establishes is that this
capture cannot broaden the base**: of the 17 corroborated ambient MACs, sixteen
are excluded. The four with enough traffic to matter —
`1c:ce:51:f3:0d:fa`, `ba:80:d5:0c:18:87`, `bc:96:e5:af:e5:7a`,
`1e:ce:51:f3:0d:fa`, all with 150+ frames on both nodes — are excluded because
**one receiver accepts essentially none of their frames** at the shipped
`inlier_ratio >= 0.6` gate, and which receiver that is changes per device
(0.0 % vs 37.5 % for `1c:ce:51:f3:0d:fa`; 80.6 % vs 0.0 % for
`bc:96:e5:af:e5:7a`). The remaining twelve are too sparse; three of those
(`28:f5:2b:4f:7c:6b`, `a8:6d:aa:55:0d:1b`, `10:38:1f:da:79:31`) have ~100 %
acceptance on both nodes and fail only on frame count.

---

## 1. Method

One script, `pc/exp_poscontrol_0822.py`, from the repo root:

```
D=data/raw/d0wd_20260822_023034.csv
S=data/raw/s3_20260822_023034.csv
for p in 0 1 2 3 4 5;   do python3 pc/exp_poscontrol_0822.py part $D --tag d0wd --part $p --nparts 6; done
for p in 0 1 2 3 4 5 6; do python3 pc/exp_poscontrol_0822.py part $S --tag s3   --part $p --nparts 7; done
python3 pc/exp_poscontrol_0822.py merge $D --tag d0wd --nparts 6 --expect-lines 2983560
python3 pc/exp_poscontrol_0822.py merge $S --tag s3   --nparts 7 --expect-lines 3564005

mkdir -p /tmp/amb
LC_ALL=C grep -F -v -e a4:f0:0f:77:91:20 -e 28:05:a5:2f:fa:48 -e f4:2d:c9:70:72:30 $D > /tmp/amb/d0wd_amb.csv
LC_ALL=C grep -F -v -e a4:f0:0f:77:91:20 -e 28:05:a5:2f:fa:48 -e f4:2d:c9:70:72:30 $S > /tmp/amb/s3_amb.csv
python3 pc/exp_poscontrol_0822.py ambient /tmp/amb/d0wd_amb.csv --tag d0wd
python3 pc/exp_poscontrol_0822.py ambient /tmp/amb/s3_amb.csv   --tag s3

python3 pc/exp_poscontrol_0822.py report --tags d0wd,s3
```

Every number below is from `report` unless it names another command. `report`
is deterministic: three runs under `PYTHONHASHSEED=1,2,3` give byte-identical
output (`md5sum` `e770803ff642d81db65a5199f4ec6b9f`). Every bootstrap uses
`np.random.default_rng(0)`. The
`part`/`merge` split exists only because this host kills any process when the
shell call that spawned it returns, and caps a call at ~178 s; a single pass
over the two files takes about eleven minutes. It is not an approximation —
ranges are cut on line boundaries with neither loss nor duplication, the
`FrameEstimator`/`WindowAggregator`/MAC-table state is pickled forward, and
`merge` re-checks rather than asserts: the parts' rows sum to **2,983,560 and
3,564,005**, matching `wc -l` minus the header, and **0 of 5 and 0 of 6 seams**
has `pc_time_us` going backwards.

**Phase work** is `pc/rff/dsp.py`'s `FrameEstimator` with the shipped gates
`inlier_ratio >= 0.6`, `resid_std <= 0.8` and `WindowAggregator(window=64)`.
`pc/capture.py:compute_cfo`, `pc/phase_skew.py` and `pc/fingerprint.py` were
**not** used: `docs/CODE_INVENTORY.md` §4.2 C1/C2/C3 establishes all three have
the DC/guard-band index wrong and `pc/test_rff_synth.py` test 7 shows
`phase_skew` returns the opposite sign.

**Corrupt rows** are screened by the two routes established in
`docs/OVERNIGHT_2026-08-22.md` §1, reused unchanged: a width-9 median filter on
`dropped` (tolerance 100) and field plausibility on `node_id`, `env_id`,
`channel`, `csi_len` ∈ {128, 256, 384}, `noise_floor`, `rssi`.

### 1.1 Reproduction check against the previous pass

This script shares no code with `pc/exp_overnight_0822.py` beyond the two
screen constants and the shipped `pc/rff/` library, and it reproduces that
document cell for cell:

| | d0wd | s3 |
|---|---|---|
| rows | 2,983,560 ✓ | 3,564,005 ✓ |
| span | 23,267.365 s ✓ | 23,267.252 s ✓ |
| corrupt rows | 142 ✓ | 0 ✓ |
| queue drops, wrap-safe | 17,366 ✓ (endpoint check agrees) | 624,291 ✓ (endpoint check agrees) |
| u16 wraps | 0 ✓ | 9 ✓ |
| distinct MACs | 131 ✓ | 34 ✓ |

and all six SFO cells, to the digit:

| node | b | fed | accepted | reject % | windows | SFO median | IQR |
|---|---|---|---|---|---|---|---|
| d0wd | B1 | 882,769 | 817,246 | 7.422 | 12,769 | +0.02277 | 0.00396 |
| d0wd | B2 | 919,632 | 881,797 | 4.114 | 13,778 | +0.02682 | 0.00207 |
| d0wd | B3 | 1,178,726 | 485,472 | 58.814 | 7,585 | +0.07195 | 0.00668 |
| s3 | B1 | 1,282,394 | 1,273,873 | 0.664 | 19,904 | +0.01392 | 0.00178 |
| s3 | B2 | 830,010 | 823,420 | 0.794 | 12,865 | +0.00959 | 0.00172 |
| s3 | B3 | 1,449,060 | 1,444,508 | 0.314 | 22,570 | +0.01466 | 0.00233 |

### 1.2 A defect in the inherited parse, and what it changed

`pc/exp_overnight_0822.py:303-304` reads the CSI field with
`cs.split(",", 128)` and rejects the row when the result has fewer than 129
items. `split` with `maxsplit=128` returns **at most** 129 items, so a row
carrying **exactly 128** CSI values yields 128 and is discarded. 128 values is
exactly one LLTF (64 complex int8 pairs) and is the length `csi_to_complex`
wants; `pc/rff_offline.py:203-204` reads the same field with
`np.fromstring(row["csi_data"], sep=",")` and accepts it.

**The same two lines appear in `pc/exp_s3_sfo_steps.py:153-155` and
`:590-592`**, the script behind `docs/S3_SFO_STEPS.md` — one of them carrying
the comment `# csi_to_complex uses [:128]`, which is exactly right about the
slice and one off in the test. `grep -rn 'split(",", 128)' pc/` finds these
two files and no others.

**Every `csi_len = 128` frame in both files was therefore never
phase-estimated, and that is all of the ambient traffic.** Confirmed from the
per-MAC length histogram: the three beacons are 100 % `csi_len = 256`, and
`1c:ce:51:f3:0d:fa`, `ba:80:d5:0c:18:87`, `bc:96:e5:af:e5:7a`,
`1e:ce:51:f3:0d:fa`, `76:eb:b0:c0:68:4d`, `9a:9a:4a:6a:74:f1`,
`54:6c:eb:15:e3:f7`, `62:45:b4:f0:e1:97` and every other 128-length source are
100 % `csi_len = 128`. The first run of this analysis reported **0 usable
windows for all 17 ambient sources**, which looked like a property of the
devices and was a property of the parse.

The fix is `len(vals) < 128`, in `cmd_part` and `cmd_ambient` both.

**No published phase result is affected.** Both `docs/OVERNIGHT_2026-08-22.md`
and `docs/S3_SFO_STEPS.md` report phase only for the three beacons, and all
three beacons transmit at `csi_len = 256` in every file involved — 100 % of
1,178,726 + 919,632 + 882,769 rows on the d0wd and 1,449,060 + 1,282,394 +
830,010 on the S3, from the per-MAC length histogram. What the defect cost is
the ambient population: **no ambient source has ever been phase-estimated by
either of those scripts**, and a pass that copies the parse and then looks at
ambient sources gets an empty answer and can misread it as an absence of data
(failure mode **C**). That is what happened in the first run of this analysis.

### 1.3 The ambient pass is exact, not a shortcut

`FrameEstimator` is one instance per source MAC, so the only state that
matters to a source's estimates is the order of that source's own frames, and
`grep -F -v` preserves file order. The row counts confirm the filter is exact:
2,433 non-beacon rows extracted from the d0wd, against
2,983,560 − (1,178,726 + 919,632 + 882,769) = **2,433**; 2,541 from the S3,
against 3,564,005 − (1,449,060 + 1,282,394 + 830,010) = **2,541**.

---

## 2. ANALYSIS 1 — the positive control

### 2.1 When anything changes, at 10 s resolution

`report` A1.7. Series are built from the per-frame stream kept for every
beacon over the final 1800 s. The baseline is the bins in
[t_end − 1800, t_end − 600), **chosen before looking** so that an entry five
minutes before the end cannot fall inside it; a bin is flagged when it leaves
the baseline by more than 6 × MAD.

| node | quantity | baseline | MAD | first flagged bin | value there | flagged after / total |
|---|---|---|---|---|---|---|
| d0wd | B1 rssi | −82.3452 | 0.1192 | **t = 23,067 (t_end − 200)** | −81.5604 | 16/20 |
| d0wd | B1 resid_std | +0.1614 | 0.0008 | t = 23,077 (−190) | +0.1544 | 12/19 |
| d0wd | B1 SFO | +0.0250 | 0.0012 | t = 23,077 (−190) | +0.0162 | 11/19 |
| d0wd | B3 accepted frac | +0.4238 | 0.0573 | t = 23,077 (−190) | +0.8367 | 13/19 |
| d0wd | B2 rssi | −80.0030 | 0.0611 | t = 23,097 (−170) | −80.9667 | 13/17 |
| d0wd | B2 SFO | +0.0261 | 0.0007 | t = 23,097 (−170) | +0.0212 | 9/17 |
| d0wd | B3 SFO | +0.0705 | 0.0028 | t = 23,097 (−170) | +0.0402 | 12/17 |
| d0wd | B3 rssi | −79.2392 | 0.1182 | t = 23,107 (−160) | −77.5605 | 16/16 |
| d0wd | B3 resid_std | +0.1584 | 0.0010 | t = 23,107 (−160) | +0.1463 | 9/16 |
| d0wd | B2 accepted frac | +0.9565 | 0.0154 | t = 23,107 (−160) | +0.8403 | 3/16 |
| d0wd | B1 accepted frac | +0.8539 | 0.0492 | t = 23,207 (−60) | +0.5158 | 2/6 |
| s3 | B3 resid_std | +0.1335 | 0.0009 | t = 23,007 (−260) | +0.1280 | 13/26 |
| s3 | B3 rssi | −65.9030 | 0.0619 | **t = 23,097 (−170)** | −65.4848 | 17/17 |
| s3 | B2 rssi | −73.7561 | 0.1114 | t = 23,107 (−160) | −72.0432 | 15/16 |
| s3 | B2 SFO | +0.0108 | 0.0004 | t = 23,107 (−160) | +0.0158 | 16/16 |
| s3 | B1 rssi | −68.0633 | 0.0793 | t = 23,127 (−140) | −72.1725 | 14/14 |
| s3 | B1 resid_std | +0.1419 | 0.0008 | t = 23,127 (−140) | +0.1502 | 12/14 |
| s3 | B1 SFO | +0.0138 | 0.0004 | t = 23,127 (−140) | +0.0186 | 14/14 |
| s3 | B3 accepted frac | +0.9967 | 0.0025 | t = 23,127 (−140) | +0.9572 | 1/14 |
| s3 | B2 accepted frac | +0.9923 | 0.0057 | t = 23,137 (−130) | +0.8408 | 9/13 |
| s3 | B2 resid_std | +0.1410 | 0.0018 | t = 23,137 (−130) | +0.1532 | 10/13 |
| s3 | B3 SFO | +0.0141 | 0.0004 | t = 23,137 (−130) | +0.0071 | 7/13 |
| s3 | B1 accepted frac | +0.9944 | 0.0032 | t = 23,187 (−80) | +0.9552 | 8/8 |

Twenty-four series are monitored (2 nodes × 3 beacons × 4 quantities).
**Twenty-three of them leave the baseline, and twenty of those twenty-three do
so inside t = 23,067 … 23,137 s, a 70 s band.** One series — d0wd B2
`resid_std` — never leaves its baseline at all. Of the three flags outside the
band, two are *later* (d0wd B1 accepted frac at −60 s, s3 B1 accepted frac at
−80 s) and belong to the same event. **Exactly one flag is earlier**: s3 B3
`resid_std` at t = 23,007, and it is not a step — only 13 of the 26 following
bins stay flagged, against 14/14, 16/16 and 17/17 for the quantities inside the
band.

**In wall-clock**, from the first `pc_time_us` of 1787383835186933 and the
UTC−5 offset that puts the file's first row at 02:30:35 and its last at
08:58:22 (matching both the filename and the `ls` mtime):

| t (s) | local |
|---|---|
| 22,967 (t_end − 300, "five minutes") | **08:53:32** |
| 23,067 first flag | **08:55:02** |
| 23,097 boundary used below | **08:55:32** |
| 23,135.1 S3 `noise_floor` leaves −93 for good | **08:56:10** |
| 23,197 second, larger shift begins | **08:57:12** |
| 23,267.365 last row | **08:58:22** |

**The data does not corroborate "five minutes."** Between t = 22,967 and
t = 23,067 — 08:53:32 to 08:55:02 — every one of the twenty-four series sits
inside its baseline. The first departure is **at 08:55:02, 3 min 20 s before
the last row**, and the coherent, all-beacon, both-node departure is at
**08:55:32, 2 min 50 s before it**. Two readings are open and this file cannot
choose between them: he sat down 1.5–2.5 minutes later than he recalls, or he
entered at 08:53:30 and *entering* produced no measurable change while
something he did around 08:55 did.

### 2.2 `noise_floor`

The d0wd cannot answer: it reads `-97` on 100.000 % of its 2,983,418 clean
rows across the whole night and on 100.000 % of the final 900 s, with zero
transitions (`report` A1.1; the same result as `docs/OVERNIGHT_2026-08-22.md`
§2.1 and `docs/S3_SFO_STEPS.md` §4). **"The d0wd's `noise_floor` held" remains
evidence of nothing.**

The S3 does answer. Its all-night modal value is **−93 dB**, held by 86.89 %
of the 2,327 10 s bins. Verified independently of the script, straight down
field 6:

```
awk -F, -v B=1787406932410606 -v T0=1787383835158318 'NR>1{
    if($6==-93){last93=$1} h[$6 FS (($1>=B)?"after":"before")]++
  } END{
    printf "last row reading -93 at t = %.3f s (t_end - %.1f s)\n",
           (last93-T0)/1e6, (1787407102410606-last93)/1e6
    for(x in h){split(x,a,FS); printf "  nf %s %-6s %d\n", a[1],a[2],h[x]}
  }' data/raw/s3_20260822_023034.csv
```

> `last row reading -93 at t = 23135.091 s (t_end - 132.2 s)`
> `nf -93 after 4832 · nf -92 after 15362 · nf -91 after 1995`

**The S3 reads −93 for the last time at t = 23,135.091 s and never again in
the remaining 132.2 s**; it holds −92 and then −91, ending the file at −91.
Mean over the last 170 s is **−92.057 against −92.705 over the preceding
1800 s, +0.648 dB** (A1.8). By the 10 s modal series the departure begins at
t = 23,137 and runs to the end of the file with no bin returning to −93
(A1.1).

**Compare 08-21**, where the S3 left a pinned −94 at t = 930 s, settled toward
−95, and did not return for the remaining 55 minutes (`docs/S3_SFO_STEPS.md`
§4): the same shape, **opposite sign**, and about the same size (−0.63 dB
there, +0.65 dB here).

**A necessary caveat on "persists".** The file ends 132 s after the departure.
Persistence is demonstrated **over 132 s only**, against 55 minutes on 08-21.
That is not the same strength of evidence, and this document does not claim it
is. What it does exclude is the reverting-excursion class: the night's other
excursions have a median duration of 10 s and a maximum of 220 s
(`docs/OVERNIGHT_2026-08-22.md` §2.2), so 132 s alone would not distinguish
them — the discriminator is §2.3, not the duration.

### 2.3 A control the night itself provides

The S3's `noise_floor` also leaves −93 for 220 s from t = 21,637 s and again
for 160 s from t = 21,467 s, and reverts both times. During those minutes the
per-60 s beacon RSSI is flat:

```
python3 -c "
import json
pb=json.load(open('/tmp/poscontrol_0822_cache/s3_perbeacon.json'))
for k in range(352,372):
    print(k, round(pb['B1']['rssi60'][k],2), round(pb['B2']['rssi60'][k],2),
             round(pb['B3']['rssi60'][k],2), round(pb['B1']['nf60'][k],3))"
```

> 60 s bins 352–371 (t = 21,120–22,320 s), s3:
> B1 −67.91 … −68.15   B2 −73.64 … −73.99   B3 −65.77 … −66.00
> `noise_floor` −93.000 … −91.845

`noise_floor` moves 1.155 dB while RSSI moves ≤ 0.24 dB on every beacon.
**A `noise_floor` excursion on its own is not the signature**; the signature
is `noise_floor` moving *with* RSSI, reject rate and SFO, which happens at
t = 23,097 and at no other point in the final 1800 s — and
`docs/OVERNIGHT_2026-08-22.md` §3.3 finds no SFO step anywhere earlier in the
night either, the largest adjacent-30-minute-block movement being
0.00997 rad/sc.

### 2.4 RSSI

Boundary at t = t_end − 170 s; "before" is the 1800 s preceding it (A1.8),
independently reproduced by `awk` over the raw files (the `after` column
matches to 0.01 dB on all six cells):

| node | b | before | after | Δ dB |
|---|---|---|---|---|
| d0wd | B1 | −82.32 | −82.04 | **+0.28** |
| d0wd | B2 | −80.01 | −79.58 | **+0.43** |
| d0wd | B3 | −79.29 | −77.61 | **+1.68** |
| s3 | B1 | −68.08 | −71.66 | **−3.58** |
| s3 | B2 | −73.74 | −75.21 | **−1.47** |
| s3 | B3 | −65.93 | −69.62 | **−3.69** |

```
awk -F, -v B=1787406932410606 'NR>1{k=($1>=B)?"after":"before";
    n[$4 FS k]++; r[$4 FS k]+=$5}
  END{for(x in n) if(n[x]>50){split(x,a,FS);
      printf "%-19s %-6s n=%-8d rssi=%.2f\n", a[1],a[2],n[x],r[x]/n[x]}}' \
  data/raw/s3_20260822_023034.csv
```

(the d0wd is the same command with `B=1787406932551712`, that file's own
`t_end − 170 s`). The `awk` "after" means differ from the table above only in
that `awk` weights every frame equally while `report` uses the same frames
over the same interval — they agree to 0.01 dB on all six cells.

**The two receivers step in opposite directions**, simultaneously: every
d0wd beacon gains, every S3 beacon loses. No receiver-internal state can do
that; it is a statement about the two propagation paths.

### 2.5 SFO, `resid_std` and reject rate

A1.8, same boundary. SFO is the median of 64-accepted-frame windows, CI by
bootstrap over windows (4,000 resamples, `np.random.default_rng(0)`);
`BETWEEN_UNIT_SD = 0.00237` (`pc/exp_thermal_evidence.py:129`).

| node | b | SFO before | SFO after | Δ | Δ 95 % CI | × SD | reject % | resid_std |
|---|---|---|---|---|---|---|---|---|
| d0wd | B1 | +0.02488 | +0.01737 | **−0.00751** | [−0.00838, −0.00654] | 3.17 | 14.49 → 16.17 | 0.1612 → 0.1559 |
| d0wd | B2 | +0.02595 | +0.02977 | **+0.00383** | [+0.00301, +0.00545] | 1.61 | 4.34 → 7.15 | 0.1541 → 0.1550 |
| d0wd | B3 | +0.06950 | +0.01540 | **−0.05410** | [−0.05530, −0.05057] | **22.83** | **57.23 → 22.51** | 0.1583 → 0.1442 |
| s3 | B1 | +0.01380 | +0.01800 | **+0.00420** | [+0.00317, +0.00491] | 1.77 | 0.64 → 7.10 | 0.1420 → 0.1507 |
| s3 | B2 | +0.01082 | +0.02027 | **+0.00945** | [+0.00835, +0.01114] | 3.99 | 0.85 → 9.25 | 0.1411 → 0.1506 |
| s3 | B3 | +0.01413 | +0.01251 | **−0.00162** | [−0.00277, −0.00067] | 0.68 | 0.34 → 0.71 | 0.1334 → 0.1350 |

Signs: **d0wd − + −, s3 + + −**. On 08-21 the S3 was **− + −**
(`docs/S3_SFO_STEPS.md` §6). All six CIs exclude zero. **The three beacons do
not move together on either node**, which is the property the 08-21 event had
and which a common clock or a common receiver scalar cannot produce.

Measured instead over the last 300 s against the 1800 s before it (A1.5, the
window the brief asked for), the same cells read −0.00594 (2.51 × SD),
−0.00002 (0.01 ×), −0.03496 (14.75 ×) on the d0wd and +0.00094 (0.40 ×),
+0.00226 (0.95 ×), −0.00132 (0.56 ×) on the S3. The effect is smaller in that
window **because the window is wrong**: 130 s of the 300 s precede the change.

### 2.6 Side by side with 2026-08-21

| | 08-21, t = 930 s | 08-22, t ≈ 23,097 s |
|---|---|---|
| `noise_floor`, S3 | −94 → −95, **−0.63 dB**, no return in 55 min | −93 → −92 → −91, **+0.65 dB**, no return in 132 s |
| `noise_floor`, other node | cannot move (−97 always) | cannot move (−97 always) |
| RSSI, S3 | **+3.77, +1.58, +6.79** | **−3.58, −1.47, −3.69** |
| RSSI, other node | +1.43, +0.73, +0.87 | +0.28, +0.43, +1.68 |
| SFO, S3 | −0.00464, +0.01786, **−0.05073** | +0.00420, +0.00945, −0.00162 |
| SFO, other node | not reported (`docs/S3_SFO_STEPS.md` §6 gives S3 rows only) | −0.00751, +0.00383, **−0.05410** |
| the high-reject cell | **B3/s3, 51.6 % → 0.2 %** | **B3/d0wd, 57.2 % → 22.5 %** |
| that cell on the other node | B3/desk, 49.2 % → **22.0 %** | B3/s3, 0.34 % → 0.71 % |
| onset | inside one 20 s window | inside one 70 s band, both nodes |

Two things in that table are worth naming.

**The largest effect follows the high-reject cell, not the board.** On 08-21
it was B3/s3 at 51.6 % reject; tonight it is B3/d0wd at 57.2 %. In both cases
that cell's SFO moves by ≈ 0.05 rad/sc — 21 × and 23 × `BETWEEN_UNIT_SD` — and
its reject rate collapses. This is `docs/S3_SFO_STEPS.md` §7's mechanism seen a
third time: **the SFO estimate in a marginal cell is a near-linear function of
fit quality**, so a channel change that improves the fit moves the "clock"
estimate by twenty times the between-unit yardstick without any clock moving.

**B3 on the other node lands at 22 % both times.** Desk B3 went 49.2 → 22.0 %
on 08-21; d0wd B3 went 57.2 → 22.5 % tonight. That is a coincidence of two
numbers and is offered as something to check, not as a finding.

### 2.7 Operator entering, or the capture being stopped?

The two overlap in time and the brief asks them to be separated. **They can be
separated for t ≤ 23,197 s; they cannot be for the last ~70 s.**

Evidence that what happens at t = 23,067–23,137 is not the shutdown (A1.8,
node-level rows):

| | d0wd before → after | s3 before → after |
|---|---|---|
| delivered | 120.55 → **127.04 fps** | 153.44 → **129.85 fps** |
| queue drops | 0.01 → 0.68 /s | **19.57 → 5.13 /s** |
| offered (delivered + drops) | 120.56 → **127.72 fps** | 173.01 → **134.98 fps** |

1. **The change starts 200 s before the last row** while delivery is nominal
   on both nodes.
2. **The S3's queue empties as its rate falls.** `dropped` counts failed
   `xQueueSend` into a 64-deep queue (`firmware/csi_rx/main/main.c:46`,
   `:85`, `:131-132`, `:314`), so a host-side stall backs the queue up and
   *raises* it. Here `dropped` falls by 74 % while the offered rate falls
   22 %: the node is being handed fewer frames by its own radio, not failing
   to drain them.
3. **The two nodes move in opposite directions at the same instant** — the
   d0wd's offered rate rises 6 % while the S3's falls 22 %. One host process
   ran both readers (`pc_time_us` is a shared host clock,
   `docs/OVERNIGHT_2026-08-22.md` §1); nothing host-side can raise one and
   lower the other.
4. **`rssi` and `noise_floor` are PHY fields.** A host-side shutdown cannot
   change either, and both change.

What **cannot** be separated: the stretch from **t = 23,197 s (08:57:12)** to
the end, where a second and larger shift appears — d0wd B1 −84.9, B3 −82.3,
S3 B1 −78.7 — and where a hand at the keyboard stopping the capture and a body
still moving in the room are the same event. Nothing in this document
attributes that stretch, and the boundary used throughout (t_end − 170 s)
places 70 s of it inside "after". Recomputing with the boundary at
t_end − 170 and the *last* 70 s excluded was not done; §5 lists it.

### 2.8 What Analysis 1 establishes, and what it does not

**Establishes**, from the files alone and with no attribution: in the last
200 s of an otherwise quiet 6.5-hour capture, a change occurs that moves a
marginal SFO cell by 22.8 × `BETWEEN_UNIT_SD`, steps RSSI on all three beacons
on both receivers at once in opposite directions per receiver, and pushes the
S3's `noise_floor` off the value that was modal in 86.89 % of the night's
2,327 10 s bins, with no return in the 132 s that remain. It is not the
capture being stopped (§2.7). Nothing else in the night looks like it.

**Establishes, given the operator's statement that he was the only thing in
the room and that he entered around then**: a person in the room is sufficient
to produce this. **That is the positive control `docs/OVERNIGHT_2026-08-22.md`
§9 said the project lacked** — with the caveats that it rests on the operator's
account rather than a logged entry time, and covers 200 s rather than an hour.

**Does not establish** that the 08-21 event was the operator. It is now known
that an operator *can* produce this class of signature — which was the missing
half — but the 08-21 event was strongly receiver-asymmetric (S3 up to 6.8 dB,
desk ≤ 1.4 dB) and tonight's is not (both nodes move, in opposite directions).
A person is not the only thing that changes a channel, and this file contains
one person-event, not a population.

**A hypothesis the sign reversal suggests, offered only as testable.** The S3's
RSSI on all three beacons and its `noise_floor` move tonight in the direction
opposite to 08-21: RSSI down where it went up, `noise_floor` up where it went
down. (Its SFO signs are only partly reversed — + + − tonight against − + −
then.) If the 08-21 session, which started at 12:50, had the operator
**leaving** the room at t = 930 s = 13:05, that is what the two events would
look like. The operator can check that against his own recollection; nothing in
either file records it, and it is not asserted here.

---

## 3. ANALYSIS 2 — is d0wd − s3 the same for every source?

### 3.1 What the sources can actually support

Twenty MACs are seen on both nodes — the 3 beacons and the 17 corroborated
ambient addresses of `docs/OVERNIGHT_2026-08-22.md` §5.3. `acc` is frames
passing the shipped gates:

| mac | kind | len | d0wd n | acc | acc % | rssi | s3 n | acc | acc % | rssi |
|---|---|---|---|---|---|---|---|---|---|---|
| f4:2d:c9:70:72:30 | beacon | 256 | 1,178,726 | 485,472 | 41.2 | −79.06 | 1,449,060 | 1,444,508 | 99.7 | −65.60 |
| a4:f0:0f:77:91:20 | beacon | 256 | 882,769 | 817,246 | 92.6 | −81.60 | 1,282,394 | 1,273,873 | 99.3 | −67.87 |
| 28:05:a5:2f:fa:48 | beacon | 256 | 919,632 | 881,797 | 95.9 | −79.94 | 830,010 | 823,420 | 99.2 | −73.91 |
| 1c:ce:51:f3:0d:fa | OUI | 128 | 972 | **0** | 0.0 | −34.91 | 954 | 358 | 37.5 | −36.23 |
| ba:80:d5:0c:18:87 | LAA | 128 | 276 | 8 | 2.9 | −86.36 | 971 | **0** | 0.0 | −71.81 |
| bc:96:e5:af:e5:7a | OUI | 128 | 315 | 254 | 80.6 | −77.36 | 196 | **0** | 0.0 | −68.52 |
| 1e:ce:51:f3:0d:fa | LAA | 128 | 165 | **0** | 0.0 | −34.59 | 154 | 72 | 46.8 | −35.48 |
| 76:eb:b0:c0:68:4d | LAA | 128 | 220 | 82 | 37.3 | −85.50 | 32 | 10 | 31.2 | −81.62 |
| 9a:9a:4a:6a:74:f1 | LAA | 128 | 168 | 0 | 0.0 | −89.99 | 1 | 0 | 0.0 | −88.00 |
| 64:fa:2b:6d:05:3b | OUI | 256 | 30 | 2 | 6.7 | −70.70 | 89 | 8 | 9.0 | −64.64 |
| 54:6c:eb:15:e3:f7 | OUI | 128 | 28 | 16 | 57.1 | −86.61 | 43 | 43 | 100.0 | −76.42 |
| f4:69:42:f2:d2:af | OUI | 384 | 64 | 1 | 1.6 | −72.58 | 3 | 0 | 0.0 | −70.67 |
| **62:45:b4:f0:e1:97** | LAA | 128 | 21 | **21** | 100.0 | −26.33 | 21 | **21** | 100.0 | −34.00 |
| 28:f5:2b:4f:7c:6b | OUI | 128 | 12 | 12 | 100.0 | −78.08 | 9 | 9 | 100.0 | −71.89 |
| a6:11:ed:a5:b5:75 | LAA | 128 | 1 | 0 | 0.0 | −88.00 | 17 | 0 | 0.0 | −83.00 |
| a8:6d:aa:55:0d:1b | OUI | 128 | 8 | 7 | 87.5 | −80.75 | 6 | 5 | 83.3 | −82.50 |
| 6e:0a:30:1f:ed:21 | LAA | 128 | 6 | 6 | 100.0 | −83.83 | 7 | 1 | 14.3 | −75.14 |
| fe:8f:93:36:1a:b1 | LAA | 128 | 12 | 0 | 0.0 | −88.67 | 1 | 0 | 0.0 | −85.00 |
| a8:b1:3b:00:b3:14 | OUI | 128 | 6 | 0 | 0.0 | −89.50 | 3 | 0 | 0.0 | −87.33 |
| 10:38:1f:da:79:31 | OUI | 256 | 3 | 3 | 100.0 | −82.00 | 2 | 2 | 100.0 | −78.50 |

**Inclusion rule, stated before the answer**: a source is estimated only if
**both** receivers accept ≥ 20 of its frames and under 1 % of its rows are
flagged corrupt. Twenty accepted frames is far above the two-frame convergence
floor `docs/WINDOW_CONVERGENCE.md` §4.4 measures, and at that section's own
numbers the median |ΔSFO| at 16–31 accepted frames is **0.00032** for
`62:45:b4:f0:e1:97` specifically — an eighth of `BETWEEN_UNIT_SD`.

**Four sources qualify: the three beacons and `62:45:b4:f0:e1:97`.** The other
sixteen are excluded, each with the count that excluded it (A2.1). The three
largest ambient sources fail for the worst possible reason: **one receiver
accepts none of their frames.**

### 3.2 The estimator, and its validation against the production one

Ambient sources cannot fill a 64-frame window — `62:45` has 21 accepted frames
spread over 21 different 300 s bins, i.e. about one frame per bin — so the
estimate used for every source is the **median of accepted per-frame slopes**,
with a 95 % CI by bootstrap over frames (4,000 resamples,
`np.random.default_rng(0)`; above 20,000 frames the bootstrap runs on a
without-replacement subsample, which widens the interval rather than narrowing
it). Neither this nor a bootstrap over windows accounts for autocorrelation,
so both understate; nothing below rests on the width.

That estimator must agree with the production one or the ambient rows are not
comparable to the beacon rows. On the beacons, over the same frames (A2.0):

| node | b | per-frame median | n frames | w = 64 median | n windows | difference |
|---|---|---|---|---|---|---|
| d0wd | B1 | +0.02399 | 53,046 | +0.02457 | 828 | −0.00058 |
| d0wd | B2 | +0.02628 | 64,987 | +0.02607 | 1,015 | +0.00021 |
| d0wd | B3 | +0.06713 | 40,385 | +0.06875 | 631 | **−0.00162** |
| s3 | B1 | +0.01398 | 97,554 | +0.01386 | 1,524 | +0.00012 |
| s3 | B2 | +0.01127 | 61,300 | +0.01093 | 957 | +0.00034 |
| s3 | B3 | +0.01400 | 110,804 | +0.01411 | 1,731 | −0.00011 |

Five of six agree to better than 0.00058 (0.25 × `BETWEEN_UNIT_SD`). The sixth
is B3/d0wd at 0.00162 (0.68 ×) — the 41 %-acceptance cell again, and one more
reason not to quote that cell alone.

### 3.3 The result

A2.1. Beacon rows use the final 1800 s (the stretch where per-frame records
are kept); `62:45`'s 21 frames are spread across the night.

| mac | kind | d0wd med | n acc | rssi | s3 med | n acc | rssi | **d0wd − s3** | 95 % CI | × SD |
|---|---|---|---|---|---|---|---|---|---|---|
| f4:2d:c9:70:72:30 | B3 | +0.06713 | 40,385 | −79.06 | +0.01400 | 110,804 | −65.60 | **+0.05314** | [+0.05289, +0.05339] | 22.42 |
| a4:f0:0f:77:91:20 | B1 | +0.02399 | 53,046 | −81.60 | +0.01398 | 97,554 | −67.87 | **+0.01001** | [+0.00998, +0.01042] | 4.22 |
| 28:05:a5:2f:fa:48 | B2 | +0.02628 | 64,987 | −79.94 | +0.01127 | 61,300 | −73.91 | **+0.01501** | [+0.01488, +0.01524] | 6.33 |
| 62:45:b4:f0:e1:97 | LAA | +0.00403 | 21 | −26.33 | +0.00592 | 21 | −34.00 | **−0.00189** | [−0.00287, −0.00103] | 0.80 |

- range **0.05503 rad/sc = 23.22 × `BETWEEN_UNIT_SD` = 68.8 × the twin ΔSFO**
- sd across sources 0.02379 = 10.04 × `BETWEEN_UNIT_SD`
- **6 of 6 pairs of 95 % CIs disjoint**; signs **+ + + −**
- beacons only: range 0.04313 = **18.20 ×** SD, against **6.2 ×** for the same
  three beacons on 08-21
- on whole-night 64-frame windows instead — the differences of the six §1.1
  medians, B3 0.07195 − 0.01466, B1 0.02277 − 0.01392, B2 0.02682 − 0.00959 —
  **+0.05729, +0.00885, +0.01723**, range 0.04844 = **20.44 ×** SD: same
  conclusion, and the same three numbers `docs/OVERNIGHT_2026-08-22.md` §3.4
  reports

**Sensitivity to the Analysis-1 event** (A2.3): removing the final 600 s moves
B3 by +0.00288 (1.21 × SD), B1 by +0.00106, B2 by +0.00026 and `62:45` by
0.00000. The conclusion does not depend on those minutes, though B3's shift is
not negligible and is a further reason to distrust that cell.

**The difference is not a receiver-pair constant.** It was not on 08-21 across
three beacons and it is not here across four sources. On the same three
beacons the spread is 18.2 × the yardstick against 6.2 × then — but **that
widening is not itself a result**: it is B3, and B3's difference is dominated
by the 41–59 %-reject d0wd cell that `docs/OVERNIGHT_2026-08-22.md` §3.4 and
§10 already say must not be quoted alone. Drop B3 and the remaining beacon
pair still differs by 0.00500 = 2.1 × the yardstick with disjoint CIs, and the
one non-beacon source has the **opposite sign** to all three beacons and the
smallest magnitude, 0.80 × the yardstick — which is what a source with a
100 %-accepted, tight fit on both receivers looks like, and the opposite of
what a large per-source receiver offset would look like.

### 3.4 Why sixteen sources drop out, and why that matters

The gate that removes them is `inlier_ratio >= 0.6` (`pc/rff/dsp.py:164,173`),
and it removes the **same device** at very different rates on the two
receivers (A2.2):

| mac | acc % d0wd | acc % s3 | median inlier d0wd | median inlier s3 |
|---|---|---|---|---|
| 1c:ce:51:f3:0d:fa | 0.0 | 37.5 | 0.365 | 0.577 |
| bc:96:e5:af:e5:7a | 80.6 | 0.0 | 0.673 | 0.346 |
| ba:80:d5:0c:18:87 | 2.9 | 0.0 | 0.500 | 0.385 |
| 1e:ce:51:f3:0d:fa | 0.0 | 46.8 | 0.365 | 0.596 |
| 54:6c:eb:15:e3:f7 | 57.1 | 100.0 | 0.644 | 0.846 |
| 76:eb:b0:c0:68:4d | 37.3 | 31.2 | 0.538 | 0.442 |
| 62:45:b4:f0:e1:97 | 100.0 | 100.0 | 0.981 | 1.000 |

The median `inlier_ratio` for most ambient sources sits at 0.33–0.60, i.e.
**straddling the gate**, so a small per-receiver difference in fit quality
flips a source from fully accepted to fully rejected. That is a statement
about the estimator's behaviour on non-ESP32 traffic, not about the devices:
it means **any cross-receiver comparison built on ambient sources is
conditioned on fit quality that differs per receiver**, which is precisely the
confound `docs/S3_SFO_STEPS.md` §7.2 identified and `docs/DUAL_RX_2026-08-21.md`
§3.4 named as unresolved.

### 3.5 Correlates

With four sources, the honest answer is that no correlation can be measured.
The values are reported because the brief asked, and they are descriptive
only, on n = 4:

```
r(delta, rssi on d0wd)              -0.561      r(delta, log10 frames d0wd)   +0.606
r(delta, rssi on s3)                -0.476      r(delta, accept rate d0wd)    -0.973
r(delta, rssi difference d0wd-s3)   -0.657      r(delta, accept-rate diff)    -0.970
r(delta, 300 s bins active on d0wd) +0.587
```

**None of these is a result.** At n = 4 a single source moving would change
any of them, and the seven quantities are not independent of each other. What
can be said without a correlation coefficient is the ordering: the source with
the lowest acceptance on the d0wd (B3, 41.2 %) has by far the largest
difference (+0.05314, 22.4 × `BETWEEN_UNIT_SD`), and the source with 100 %
acceptance on both nodes (`62:45`) has the smallest (−0.00189, 0.80 ×
`BETWEEN_UNIT_SD`, though still 2.4 × the twin ΔSFO yardstick). That ordering
is consistent with the fit-quality mechanism and with nothing else measured
here, and it is one ordering of four items.

### 3.6 What Analysis 2 does not settle

- **The receiver-versus-position confound is untouched.** The operator states
  the nodes were not swapped. `docs/DUAL_RX_2026-08-21.md` §6's "swap the two
  nodes and repeat" remains the outstanding experiment, and it is now more
  valuable, not less: the high-reject cell has already moved boards once.
- **`62:45:b4:f0:e1:97` is a locally-administered (randomised) address.**
  "The same device on both receivers" is inferred from the address plus the
  bin-level coincidence `docs/OVERNIGHT_2026-08-22.md` §5.2 measures
  (J = 0.826, 19 of 23 bins shared). A device that re-randomised mid-session
  would break that inference, and this file cannot exclude it. Eight of the 17
  ambient addresses are LAA; this is the general form of the problem.
- **`62:45`'s SFO here is not comparable to its recorded value elsewhere.**
  `docs/WINDOW_CONVERGENCE.md` §4.4 gives +0.00127 (IQR 0.00042) in
  `rx_20260715_201703`; this pass measures +0.00403 and +0.00592 on two
  different receivers five weeks later. Cross-session comparison was not
  attempted and no claim is made from that gap.

---

## 4. Established / permitted / unknown

**Established by this pass.**

- Something changes on **both** receivers in the band **t = 23,067–23,137 s
  (08:55:02–08:56:12 local)**, 130–200 s before the last row: of 24 monitored
  series, 23 leave a pre-chosen baseline by > 6 × MAD and 20 of those do so
  inside that 70 s band, and stay out (§2.1).
- The S3's `noise_floor` reads −93 for the last time at **t = 23,135.091 s**
  and never again in the remaining 132.2 s, ending the file at −91; mean shift
  **+0.648 dB** (§2.2, `awk`-verified).
- RSSI steps **in opposite directions on the two nodes**: d0wd +0.28/+0.43/
  +1.68 dB, s3 −3.58/−1.47/−3.69 dB (§2.4, `awk`-verified to 0.01 dB).
- SFO moves on all six cells with CIs excluding zero, in **different
  directions within a node** (d0wd − + −, s3 + + −). Largest is
  **B3/d0wd, −0.05410 rad/sc = 22.83 × `BETWEEN_UNIT_SD`**, with its reject
  rate going **57.23 % → 22.51 %** (§2.5).
- The event is **not** the capture being stopped, for t ≤ 23,197 s: the S3's
  offered rate falls 22 % while its queue drops fall 74 %, and the d0wd's
  offered rate *rises* 6 % at the same instant (§2.7).
- A `noise_floor` excursion alone is not the signature: the reverting 220 s
  excursion at t = 21,637 s moves `noise_floor` 1.155 dB while RSSI stays
  within 0.24 dB on all three beacons (§2.3).
- **d0wd − s3 SFO is not one constant across sources**: +0.05314, +0.01001,
  +0.01501, −0.00189 over four sources, range **23.22 × `BETWEEN_UNIT_SD`**,
  6 of 6 CI pairs disjoint, the ambient source's sign opposite to all three
  beacons (§3.3).
- **Only four of the twenty both-node sources can support the estimate.** The
  binding constraint is the `inlier_ratio >= 0.6` gate, which accepts the same
  ambient device at 0.0 % on one receiver and 37.5–80.6 % on the other (§3.4).
- **The CSI parse in `pc/exp_overnight_0822.py:303` and
  `pc/exp_s3_sfo_steps.py:153,590` silently discards every `csi_len = 128`
  frame**, which is 100 % of the ambient traffic in both files. No published
  figure moves — both documents are beacon-only and beacons are length 256 —
  but no ambient source has ever been phase-estimated by either script (§1.2).
- The previous pass's row, corrupt-row, drop, wrap, MAC and all six SFO cells
  reproduce exactly from an independent implementation (§1.1).

**Permitted but not established.**

- That the change at 23,067–23,137 s is the operator sitting down. It is a
  channel change, at roughly the right time, of the right kind; no field in
  either file names a person. Nothing else was in the room by the operator's
  account, and that account is what is being tested.
- That the 08-21 t = 930 s event was the operator. This pass supplies the
  missing half — a person *can* produce a signature of this class — and does
  not close the gap: 08-21 was strongly receiver-asymmetric and this is not.
- That 08-21 was the operator **leaving** rather than entering. The S3's RSSI
  on all three beacons and its `noise_floor` move in the opposite direction
  between the two events; its SFO signs are only partly reversed (§2.8). This
  is a testable recollection, not a finding.
- That the last ~70 s (t ≥ 23,197 s) is the operator reaching to stop the
  capture. A second, larger shift begins there and shutdown and movement are
  not separable in it (§2.7).
- That the ordering "lowest acceptance ↔ largest inter-receiver difference"
  is the mechanism. Four sources; the correlation coefficients in §3.5 are not
  evidence.

**Unknown.**

- **The operator's actual entry time.** The data first departs at 08:55:02;
  he says about 08:53:30. Whether he misremembers by 90 s or whether entering
  produced nothing measurable and a later movement did, this file cannot say.
- **Whether the `noise_floor` departure would have persisted.** 132 s of file
  remain after it. Persistence beyond that is not measured.
- **What produced the 08-21 event.** Unchanged from
  `docs/OVERNIGHT_2026-08-22.md` §8.
- **Why B3/d0wd rejects 41–59 % of frames** at the strongest RSSI on that
  node — and why that rate falls to 22.5 % across the change at t = 23,097 s.
- **Whether the d0wd − s3 difference is receiver or position.** The nodes were
  not swapped.
- **Whether the 16 excluded ambient sources would agree with `62:45`.** They
  are excluded because one receiver's fit fails, not because they were
  measured and disagreed.

---

## 5. Figures in this document that should not be quoted alone

- **B3/d0wd's whole-night +0.07195 and any difference built on it.** 58.8 % of
  its frames are rejected; `docs/S3_SFO_STEPS.md` §7.2 establishes that in this
  regime the reported slope is a function of fit quality. Its per-frame and
  window estimators also disagree by 0.68 × `BETWEEN_UNIT_SD` (§3.2), where
  every other cell agrees to 0.25 ×.
- **"The signature reappears."** It reappears with the RSSI and `noise_floor`
  signs reversed and without the receiver asymmetry (§2.6). Quote the
  comparison table, not the sentence.
- **The +0.648 dB `noise_floor` shift as "persistent."** It persists for the
  132 s of file that remain (§2.2).
- **The A1.5 last-300 s effect sizes.** 130 s of that window precede the
  change and dilute it; §2.5's boundary at t_end − 170 s is the one to use.
- **Any figure computed "after" the t_end − 170 s boundary.** 70 s of that
  170 s is the confounded stretch of §2.7.
- **`62:45:b4:f0:e1:97`'s −0.00189.** Twenty-one accepted frames per node, a
  randomised address, and one source.
- **The correlation coefficients in §3.5.** n = 4.
- **"Four sources" as a measurement of anything about ambient devices.** It is
  a measurement of what the shipped gate accepts.

Nothing in this document touches the occupancy pipeline (`pc/occ/`, amplitude
domain). Device-ID and occupancy figures must not be combined.

---

## 6. What would settle the rest

| question | measurement |
|---|---|
| Did the operator enter at 08:53:30 or 08:55:00? | A logged wall-clock entry time. The next positive control should have the operator note the second he opens the door and the second he sits, and stay 20+ minutes after so persistence is measurable against something longer than 132 s. |
| Was 08-21 the operator leaving? | Ask him. Then repeat with a logged exit: if leaving reproduces 08-21's signs (S3 RSSI up, `noise_floor` down) the two events are one phenomenon. |
| Is the anomalous cell the board or the position? | Swap the two nodes and repeat — still outstanding from `docs/DUAL_RX_2026-08-21.md` §6 and `docs/S3_SFO_STEPS.md` §11, and now the sharpest test available: the high-reject cell moved from B3/s3 to B3/d0wd between sessions. |
| Can ambient sources ever support a cross-receiver test? | Not at `inlier_ratio >= 0.6`. Stratify `1c:ce:51:f3:0d:fa`'s 972 d0wd frames by `inlier_ratio` as `docs/S3_SFO_STEPS.md` §7.2 did, and measure what the difference does as the gate is relaxed. If it is stable across the gate the source is usable; if it tracks the gate, the confound is fatal and should be recorded as such. |
| Does the 128-length parse defect reach anything else? | `grep -rn 'split(",", 128)' pc/` finds `pc/exp_overnight_0822.py:303` and `pc/exp_s3_sfo_steps.py:153,590`, and nothing else; `pc/rff_offline.py:203` is correct. Both affected documents are beacon-only, so no published figure moves — but any ambient-source result from either script would have been empty by construction. Fix both, or the next pass rediscovers it. |
| Is the shutdown stretch separable at all? | Emit a marker row when the capture is asked to stop. `tlm_status_t` (`firmware/common/telemetry/include/telemetry.h:35-46`) has no slot for it, and `pc/capture.py:193-196` catches `KeyboardInterrupt`, sets the stop event and restores the terminal without writing anything further to the CSV. The last seconds of every capture in `data/raw/` are therefore unattributable. |
