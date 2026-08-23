# Node census — every node that ever appears in `data/raw/`

**Date:** 2026-08-15 · **Scope:** read-only census of `data/raw/`, all 62
files, all capture families · **Tool:** `pc/node_census.py` (new,
read-only). No existing file was modified and no hardware was touched.

---

## The count

| role | count | basis |
|---|---:|---|
| **Transmitters — Braeden's beacons** | **3** | beacon signature, proven |
| **Transmitters — third-party ambient** | **543** | everything else that ever emitted a decodable frame |
| **Receivers — distinct, proven simultaneous** | **2** | `desk` + `node3`, 2026-07-12 → 07-13 only |
| **Receivers — in service 07-14 onward** | **1** | zero simultaneity anywhere after 07-13 |
| **Inventoried boards that never appear at all** | **2** | collector `f4:2d:c9:6f:8b:44`, Heltec S3 `8c:fd:49:b7:b0:6c` |

546 distinct source MACs, 910 (file, MAC) rows, **14,986,846 frames**
across 50 files that contain data (plus 1 header-only and 11 zero-byte
files = 62).

**The array was a 1-transmitter / 2-receiver system for its first two
days, and has been a 3-transmitter / 1-receiver system since
2026-07-14.** Braeden's recollection of "one receiver, three
transmitters" is correct for the array as it stands and wrong for
2026-07-12 and 07-13, which is where both headline accuracy numbers come
from.

### Reproduce

```
python pc\node_census.py census  "data\raw\*.csv" --cache census_full.csv
python pc\node_census.py overlap --cache census_full.csv
python pc\node_census.py roles   --cache census_full.csv --top 25
python pc\node_census.py cadence data\raw\rx_20260714_031131.csv --mac a4:f0:0f:77:91:20
```

The `census` pass takes ~60 s over the full 13 GB. Its row count (910)
and MAC count (546) reproduce `docs/LOT_HYPOTHESIS.md` §3 and
`docs/WINDOW_CONVERGENCE.md` §6, which reached the same two figures by
two other routes. Three independent implementations now agree.

---

## 1. How a node is identified, and it differs by era

There is no single identification method across this dataset. The CSV
schema changed on 2026-07-14 and receiver identity is carried
differently on either side of that line.

| era | files | columns | transmitter ID | receiver ID |
|---|---|---:|---|---|
| **A** — 07-12 → 07-13 | `harvest_afternoon`, `desk_*`, `node3_*` (38 with data) | **10** | `mac` column | **filename prefix only** |
| **B** — 07-14 → 07-15 | `rx_*` (4) | **13** | `mac` column | `node_id` column |
| **C** — 07-22 | `occ_*` (6), `rx_*` (2) | **13** | `mac` column | `node_id` column |

**Era A carries no receiver identity in the data at all.** The 10-column
header is `pc_time_us,label,seq,mac,rssi,noise_floor,channel,esp_timestamp_us,len,csi_data`.
The strings `desk` and `node3` come from `pc/capture.py`, which names each
output file after the `PORT[:name]` spec typed on the command line
(`capture.py` line 103, `f"{node.name}_{ts}.csv"`). A filename prefix is a
**typed label**, not a measurement. That two physically distinct
receivers existed is nonetheless proven — by simultaneity and by
independent reception, not by the label (§4).

**Era B/C carries `node_id`, and it is a constant.** `capture.py` writes
`rec["node_id"]` straight from the firmware's status record. Across all
**10,342,823** rows in the twelve 13-column files, the trailing three
fields are `,68,0,<int>` on every row but **18**, and those 18 are
bit-corrupted records (also mangled `channel`, `seq`, `len`). So
`node_id = 68`, `env_id = 0`, everywhere.

That is weaker evidence than it looks. `node_id` is compiled into the
firmware: two different physical boards flashed from the same build would
both report 68. It shows these captures were **taken with one firmware
identity**; simultaneity (§4) is what shows there was one *radio*.

---

## 2. Transmitters — the three beacons

Applying the beacon signature `docs/TWIN_INVESTIGATION.md` §4
established — sustained high frame rate, uniformly 256-byte CSI buffers,
bulk presence — as **≥10 fps AND ≥1000 frames AND >99.9% len-256 within
a single file**:

| MAC | files pass / all | frames pass / all | fps range | mean RSSI | len-256 |
|---|---:|---:|---|---:|---:|
| `a4:f0:0f:77:91:20` | 42 / 49 | 7,015,610 / 7,016,574 | 11.6 – 66.6 | −75.8 | **100%** |
| `f4:2d:c9:70:72:30` | 12 / 12 | 4,639,517 / 4,639,517 | 37.0 – 82.5 | −71.7 | **100%** |
| `28:05:a5:2f:fa:48` | 7 / 7 | 3,274,606 / 3,274,606 | 27.2 – 49.3 | −77.9 | **100%** |

**Exactly three sources out of 546 pass. There is no fourth.** The seven
extra reference-beacon files are brief or nearly-empty sessions below the
frame threshold, accounting for the 964-frame difference.

### 2.1 `a4:f0:0f:77:91:20` — reference beacon (`B1` in `pc/occ/`)

- **Role: transmitter.** Never observed as a receiver; a receiver's own
  MAC does not appear in its own capture.
- **First:** 2026-07-12 08:53:11.700 UTC, `harvest_afternoon.csv`.
- **Last:** 2026-07-23 13:42:42 UTC, `rx_20260722_XXXXXX.csv`.
- 49 files, all three eras, the only beacon on air for the first two days.
- Mean RSSI by era: **−77.6** (A), **−67.2** (B), **−83.7** (C). It moved,
  or the collector did, between 07-15 and 07-22 — a 16.5 dB swing.
- **One documented off-air gap:** `desk_20260713_121242.csv`, 2026-07-13
  17:12:47 – 17:23:39 UTC, 939 frames of pure ambient traffic and **zero
  reference-beacon frames**. Its `node3_` partner file is 0 bytes. The
  beacon was down for ~11 minutes.

### 2.2 `f4:2d:c9:70:72:30` — second beacon (`B3`), the clock twin

- **Role: transmitter.**
- **First:** 2026-07-14 06:16:19.189 UTC — the **first data row** of
  `rx_20260714_011619.csv`.
- **Last:** 2026-07-23 13:42:42 UTC, `rx_20260722_XXXXXX.csv`.
- 12 files. **Zero occurrences in any 07-12 or 07-13 capture, on either
  receiver.**
- Highest sustained rate of the three (up to 82.5 fps) and the strongest
  mean RSSI (−71.7) — the closest of the three to the collector.
- Shares its OUI `f4:2d:c9` with the inventoried collector
  `f4:2d:c9:6f:8b:44`.

### 2.3 `28:05:a5:2f:fa:48` — third beacon (`B2`)

- **Role: transmitter.**
- **First:** 2026-07-14 06:16:19.367 UTC, `rx_20260714_011619.csv` —
  **0.177 s after** `f4:2d:c9:70:72:30`, at row 32.
- **Last:** 2026-07-23 13:42:42 UTC, `rx_20260722_XXXXXX.csv`.
- 7 files — the fewest. **Absent from the five afternoon `occ_*` captures
  of 2026-07-22** (`grep -c` = 0 in all five) and present again that
  evening. See §5.
- Lowest and most stable RSSI band (−76.0 … −79.5), lowest rate
  (27.2 – 49.3 fps).

### 2.4 Behavioural signature — what separates a beacon from ambient traffic

The discriminator that does the work is **frame format plus sustained
rate**, and the gap between the beacons and everything else is wide on
both axes at once:

| axis | the three beacons | nearest non-beacon competitor |
|---|---|---|
| frames in one file | 1,477 – 2,709,812 | `1e:ce:51:f3:0d:fa`, 20,913 — but **0% len-256** |
| sustained rate | 11.6 – 82.5 fps | `76:eb:b0:c0:68:4d`, 13.1 fps — but 238 frames total, 0% len-256 |
| CSI buffer length | **100% len-256**, all three, all files | `84:7b:57:cc:20:0e`, 81.9% len-256 — but ≤1.5 fps and mixed lengths |
| channel | 6 | 6 |

No non-beacon source is close on more than one axis. Every census row
reaching ≥10 fps with ≥1000 frames is one of the three.

**Cadence regularity is a weaker discriminator than it appears, and the
clock you use decides the answer.** `pc_time_us` is stamped per serial
drain batch, not per frame (`docs/HANDOFF.md` trap #1), so gap statistics
computed on it are batching artifacts. Measured on the per-frame
`esp_timestamp_us` instead (`node_census.py cadence`), over 200,000 gaps
in `rx_20260714_031131.csv`:

| source | median gap | fps | CV | within ±20% of median | p5 | p95 |
|---|---:|---:|---:|---:|---:|---:|
| `a4:f0:0f:77:91:20` | 0.01461 s | 68.4 | 0.70 | 14.2% | 0.00707 | 0.04752 |
| `f4:2d:c9:70:72:30` | 0.01314 s | 76.1 | 0.69 | 18.7% | 0.00630 | 0.04243 |
| `28:05:a5:2f:fa:48` | 0.02038 s | 49.1 | 0.83 | 20.9% | 0.00701 | 0.07198 |
| `84:7b:57:cc:20:0e` | 0.61442 s | 1.6 | 1.02 | 11.3% | 0.09206 | 3.33256 |

The beacons are **not** tight-cadence at the receiver: CV 0.69–0.83 and
only 14–21% of gaps within ±20% of the median. That is receive-side loss,
not transmit-side jitter — the beacons transmit at a nominal 100 Hz and
the collector captures 50–76% of frames, so observed gaps land on
multiples of the 10 ms period. What actually separates them from `84:7b`
is **scale**: a p5 gap of 6–7 ms versus 92 ms, and a median 30–47× lower.
The CV numbers are close and should not be quoted as the discriminator.

> **This contradicts `docs/TWIN_INVESTIGATION.md` §4**, which lists the
> beacons at "32–58 fps (gap median 0.0007–0.0013 s)". Those two figures
> are mutually inconsistent — a 0.0007 s median gap is 1,400 fps, not 32.
> The table was computed on `pc_time_us`, where batch stamping collapses
> gaps within a drain to near zero. §4's *conclusion* about `84:7b` is
> unaffected and stands: the rate ratio is ~30× either way, and the
> frame-format evidence is independent of any clock. Only the beacon
> gap-median column is wrong.

### 2.5 The 543 other transmitters

Ambient third-party traffic, on channel 6, in the same room. 513 of the
546 MACs contribute **fewer than 64 frames** — less than one analysis
window — and only 9 exceed 1,000 frames. Two are worth naming because
they carry the headline numbers:

- **`84:7b:57:cc:20:0e`** — 6,707 frames over 17 files, first seen
  2026-07-12 20:37:57 UTC in `desk_20260712_140038.csv`, last 2026-07-23
  12:59:24 UTC. Globally-administered OUI, ≤1.5 fps, 81.9% len-256 with a
  mixed remainder, mean RSSI −77.8. `docs/TWIN_INVESTIGATION.md` §4
  characterizes it as a stationary third-party 802.11n device; §5a proves
  it physically distinct from `f4:2d:c9:70:72:30` by 111.6 minutes of
  simultaneous transmission. **It is the single largest error source in
  the 95.7% run** (276 reference windows misassigned to it).
- **`1e:ce:51:f3:0d:fa`** — 33,021 frames over 29 files, the busiest
  non-beacon source, mean RSSI −37.5 (a close-in client), locally
  administered, **0% len-256**. Its `1c:ce:51:f3:0d:fa` counterpart is the
  same base address with the locally-administered bit cleared.

---

## 3. Receivers

### 3.1 `desk` — era A only

- **Identified by:** filename prefix, typed at the command line. Nothing
  in the CSV names it.
- **Evidence of receiver role:** it logs a multi-source population — up
  to 42 distinct source MACs in one session
  (`desk_20260713_172009.csv`) — while never appearing as a source in any
  file. That is independent reception, which is what a receiver does.
- **First:** 2026-07-12 15:11:17 UTC, `desk_20260712_101116.csv`.
- **Last:** 2026-07-14 01:42:08 UTC, `desk_20260713_194922.csv`.
- 21 files with data, 7 zero-byte, 1 header-only.
- Never observed transmitting.

### 3.2 `node3` — era A only, and it changed behaviour mid-07-13

- **Identified by:** filename prefix. Same caveat.
- **First:** 2026-07-12 15:42:06 UTC, `node3_20260712_104205.csv`.
- **Last:** 2026-07-14 01:12:30 UTC, `node3_20260713_194922.csv`.
- 16 files with data, 3 zero-byte, 1 zero-byte partner
  (`node3_20260713_121242.csv`).
- Never observed transmitting.

**In its first seven sessions `node3` logged exactly one source MAC — the
reference beacon — and nothing else:**

| session (UTC start) | node3 distinct MACs | desk distinct MACs |
|---|---:|---:|
| 07-12 15:42:06 | **1** | 9 |
| 07-12 17:41:43 | **1** | 18 |
| 07-12 19:00:38 | **1** | 17 |
| 07-13 15:45:14 | **1** | 5 |
| 07-13 16:26:18 | **1** | 7 |
| 07-13 16:54:11 | **1** | 5 |
| 07-13 17:08:28 | **1** | 2 |
| *(07-13 17:12:47 — node3 file is 0 bytes)* | — | 8 |
| 07-13 18:17:47 | **6** | 6 |
| *07-13 18:29:02 — 1 frame total* | *1* | *1* |
| *07-13 18:32:24 — 2,195 frames* | *2* | *3* |
| 07-13 18:35:56 | **14** | 6 |
| *07-13 19:46:29 — 72 frames* | *1* | *1* |
| 07-13 19:53:02 | **12** | 10 |
| 07-13 21:02:54 | **12** | 19 |
| 07-13 22:20:10 | **23** | 42 |
| 07-14 00:49:22 | **10** | 23 |

The three italicised rows are sessions of 1 to 2,195 frames — far too
short for ambient traffic at ≤3 fps to appear on *either* receiver, so
they carry no information and are shown only for completeness. Across
every session long enough to be informative, the change is sharp and
falls **between 2026-07-13 17:08 and 18:17 UTC** (12:08 – 13:17 local).
Before it, `node3` behaves exactly like a MAC-filtered capture; after it,
like a promiscuous one. This is a composition change that no filename or
note records.

### 3.3 The era B/C collector — one receiver, unattributed

- **Identified by:** `node_id = 68`, constant across all 10.3 M rows of
  eras B and C.
- **First:** 2026-07-14 06:16:19 UTC, `rx_20260714_011619.csv`.
- **Last:** 2026-07-23 13:42:42 UTC, `rx_20260722_XXXXXX.csv`.
- 12 files, **none of which overlap in time with any other file** (§4).
- Never observed transmitting.
- Whether this is the same physical board as era A's `desk` is **not
  established by anything in the data.** See §6.

### 3.4 `harvest_afternoon.csv` — unattributed

10-column, no `node_id`, and a filename that follows no receiver
convention. 2026-07-12 08:53:11 – 13:55:25 UTC, 213,031 frames, 11
distinct MACs, 11.6 fps — the earliest and slowest capture in the
dataset, and the only one whose recording node cannot be named at all. It
does not overlap any other file, so it is not evidence of a third
receiver.

### 3.5 Two inventoried boards that produced nothing

- **Collector `f4:2d:c9:6f:8b:44`** — **0 occurrences** in all 62 files.
  Expected: a receiver does not appear as a source in its own captures.
  This is consistent with it being a receiver and is not evidence that it
  is one.
- **Heltec S3 `8c:fd:49:b7:b0:6c`** — **0 occurrences** in all 62 files.
  Confirms `docs/HANDOFF.md` open thread #3 (S3 WiFi-TX inaudible) from
  the capture side. It has never contributed a frame to this project.

### 3.6 Outside `data/raw/` — two `collect.py` test files

`csi_20260713_112549.csv` (324 rows, 07-13 16:25:50 – 16:25:55 UTC) and
`csi_20260713_120849.csv` (325 rows, 17:08:50 – 17:08:56 UTC) sit in the
repo root. Both are 10-column, both auto-named by `pc/collect.py`
(`csi_%Y%m%d_%H%M%S.csv`, single node). **Neither overlaps any
`data/raw/` file** — the first ends 23 s before `desk_20260713_112617`
starts, the second starts 17 s after `desk_20260713_120828` ends. They
are sequential single-node test runs, **not a third receiver.**

---

## 4. Simultaneity — the test that decides receiver count

A single radio cannot produce two independent receptions of the same
instant. Overlapping `pc_time_us` spans between two files therefore prove
two physical receivers, and only overlap proves it.

`python pc\node_census.py overlap` finds **15 overlapping pairs in the
entire dataset. All 15 are a `desk_*` file against its `node3_*` partner.
Every one is on 07-12 or 07-13.**

| overlap | file A | file B |
|---:|---|---|
| **148.45 min** | `desk_20260713_172009.csv` | `node3_20260713_172009.csv` |
| 103.84 min | `desk_20260712_140038.csv` | `node3_20260712_140038.csv` |
| 78.84 min | `desk_20260712_124142.csv` | `node3_20260712_124142.csv` |
| 65.92 min | `desk_20260713_160253.csv` | `node3_20260713_160253.csv` |
| 39.51 min | `desk_20260713_145302.csv` | `node3_20260713_145302.csv` |
| 23.13 min | `desk_20260713_194922.csv` | `node3_20260713_194922.csv` |
| 13.75 min | `desk_20260713_133556.csv` | `node3_20260713_133556.csv` |
| 10.39 min | `desk_20260713_112617.csv` | `node3_20260713_112617.csv` |
| 9.23 min | `desk_20260713_131746.csv` | `node3_20260713_131746.csv` |
| 7.42 min | `desk_20260712_104205.csv` | `node3_20260712_104205.csv` |
| 5.06 min | `desk_20260713_115411.csv` | `node3_20260713_115411.csv` |
| 3.93 min | `desk_20260713_104513.csv` | `node3_20260713_104513.csv` |
| 0.62 / 0.08 / 0.02 min | three further pairs | |

The 148 min maximum is confirmed exactly: 2026-07-13 22:20:10 → 07-14
00:48:37 UTC.

**Among the twelve era-B/C files there are zero overlapping pairs — not
one microsecond, even at a threshold of 0 s.** They run strictly
sequentially with positive gaps throughout:

```
rx_20260714_011619   07-14 06:16:19 -> 07:02:13
rx_20260714_030915   07-14 08:09:15 -> 08:11:24   (gap 4021.7 s)
rx_20260714_031131   07-14 08:11:32 -> 13:40:43   (gap    7.4 s)
rx_20260715_201703   07-16 01:17:03 -> 05:10:28   (gap 128180.1 s)
occ_20260722_151807  07-22 20:22:26 -> 20:23:44   (gap 573117.5 s)
occ_20260722_152849  07-22 20:28:49 -> 20:38:55   (gap  305.0 s)
occ_20260722_154312  07-22 20:43:12 -> 20:44:59   (gap  257.4 s)
occ_20260722_154716  07-22 20:47:16 -> 20:52:03   (gap  137.0 s)
occ_20260722_155622  07-22 20:56:22 -> 20:59:02   (gap  259.5 s)
occ_20260722_191220  07-23 00:12:20 -> 00:22:21   (gap 11598.2 s)
rx_20260722_204658   07-23 01:46:59 -> 01:52:17   (gap 5077.3 s)
rx_20260722_XXXXXX   07-23 01:53:39 -> 13:42:42   (gap   82.6 s)
```

**The `rx_*` and `occ_*` captures are single-receiver. The naming change
from `desk_`/`node3_` to `rx_` did not signal the composition change — it
followed it, and the composition change it followed was the *loss* of the
second receiver, not the arrival of anything.**

### Corroboration — the two era-A receivers heard differently

Simultaneity alone could in principle be explained by one radio writing
two files. It is not: over the same wall-clock window the two files
record the **same beacon at different signal strength and in different
volume**.

| session | desk frames | node3 frames | ratio | desk RSSI | node3 RSSI | Δ |
|---|---:|---:|---:|---:|---:|---:|
| 07-12 104205 | 16,040 | 17,392 | 0.92 | −71.4 | −81.1 | **+9.7** |
| 07-13 104513 | 15,691 | 10,134 | 1.55 | −72.6 | −81.6 | **+9.0** |
| 07-13 133556 | 43,886 | 239,765 | **0.18** | −77.8 | −73.0 | −4.8 |
| 07-13 145302 | 138,503 | 109,145 | 1.27 | −69.5 | −76.0 | +6.5 |
| 07-13 172009 | 585,596 | 473,953 | 1.24 | −75.6 | −79.0 | +3.4 |
| 07-13 194922 | 196,758 | 73,150 | **2.69** | −76.1 | −78.9 | +2.8 |

Up to 9.7 dB apart and a 5.5× frame-count ratio, on the same transmitter
in the same minutes. Two antennas in two places.

---

## 5. Timeline of the array's composition

All times UTC. Local time is UTC−5; filenames carry local time, `pc_time_us`
carries UTC.

| date | transmitters on air | receivers logging | evidence |
|---|---|---|---|
| **07-12 08:53 – 13:55** | `a4:f0` only | **1**, unattributed (`harvest_afternoon`) | no overlap with anything |
| **07-12 15:11 – 15:42** | `a4:f0` only | **1** (`desk`) | `desk_20260712_101116` has no `node3` partner |
| **07-12 15:42 – 07-13 17:08** | `a4:f0` only | **2** (`desk` + `node3`), `node3` **beacon-filtered** | 10 overlapping pairs; node3 logs 1 MAC |
| **07-13 17:12 – 17:23** | **none** — beacon off air | 1 (`desk`; node3 file 0 bytes) | 939 frames, 0 from `a4:f0` |
| **07-13 18:17 – 07-14 01:42** | `a4:f0` only | **2**, `node3` now **promiscuous** | 5 overlapping pairs; node3 logs 6–23 MACs |
| **07-14 06:16:19.189** | `f4:2d` **first transmits** | 1 | row 1 of `rx_20260714_011619` |
| **07-14 06:16:19.367** | `28:05` **first transmits** | 1 | row 32, **0.177 s later** |
| **07-14 06:16 – 13:40** | **all 3** | **1** | zero overlap among `rx_*` |
| **07-16 01:17 – 05:10** | **all 3** | **1** | `rx_20260715_201703` |
| **07-22 20:22 – 20:59** | **2** — `a4:f0` + `f4:2d`; **`28:05` absent** | **1** | `grep -c 28:05` = 0 in all five `occ_*` |
| **07-23 00:12 – 13:42** | **all 3** | **1** | `occ_20260722_191220`, both `rx_*` |

### 07-12 and 07-13 — verified

Two receivers logging simultaneously, up to **148.45 minutes** of
overlap, with **only** `a4:f0:0f:77:91:20` transmitting. The other two
beacon MACs occur **0 times** across every `desk_2026071[23]_*` and
`node3_2026071[23]_*` file. Confirmed.

One correction to the premise: the two receivers were not equivalent.
For the first seven sessions `node3` recorded a **single-MAC** stream
(§3.2), so "two receivers logging" is true, but only one of them was
observing the ambient population until 07-13 18:17.

### 07-14 — verified

Both remaining beacons first transmit **0.177 s apart** at the very start
of the first `rx_*` capture. Two units arriving within 180 ms at a file
boundary is a deployment event. Confirmed.

**But the naming change is not what it looks like.** `rx_*` replaced
`desk_*`/`node3_*` on the same day the array went from two receivers to
one. The filename stopped carrying a node name because there was no
longer a node name to disambiguate.

### 07-15 and 07-22 — the question answered

**Both are single-receiver.** `rx_20260715_201703` is one file, alone in
its 128,180-second window. The six 07-22 `occ_*` files and two `rx_*`
files are strictly sequential with gaps of 82 s to 11,598 s. Zero
simultaneity anywhere. The `occ_*` naming denotes a *pipeline*
(`pc/occ_capture.py`, amplitude-domain occupancy), not a second node.

### 07-22 — an unrecorded change nobody has written down

`28:05:a5:2f:fa:48` is **absent from all five afternoon `occ_*` captures**
(20:22 – 20:59 UTC) and present again in `occ_20260722_191220` that
evening (00:12 UTC on 07-23) and in both `rx_*` files after it. During
that ~37-minute block the array was running **two** beacons, not three.

`pc/occ_offline.py` names its links `B1`/`B2`/`B3` from
`pc/occ/BEACON_MACS`, and `B2` **is** `28:05:a5:2f:fa:48`. Any occupancy
result computed from those five files is a two-link result. This has not
been noted in `docs/OCC_PROTOCOL.md` or `docs/HANDOFF.md`.

---

## 6. Proven versus inferred

The division below is strict. "Proven" means established by simultaneity,
frame counts, or direct measurement of the CSVs. "Inferred" means it
rests on a label, a filename, a note, or plausibility — however
reasonable.

### 6.1 Proven

| # | claim | evidence |
|---|---|---|
| P1 | **Exactly three sources have beacon character** in 14,986,846 frames from 546 MACs. | Beacon filter, §2. No fourth source is close on more than one axis. |
| P2 | **Two physically distinct receivers operated on 07-12 and 07-13.** | 15 overlapping file pairs, up to 148.45 min; same beacon at up to 9.7 dB different RSSI and 5.5× different frame count in the same minutes. |
| P3 | **From 07-14 onward there was one receiver.** | Zero overlapping pairs among all twelve era-B/C files, at a 0-second threshold. Gaps 7.4 s – 573,118 s. |
| P4 | **`f4:2d:c9:70:72:30` and `28:05:a5:2f:fa:48` first transmit on 07-14, 0.177 s apart**, at row 1 and row 32 of `rx_20260714_011619.csv`. | Direct. Zero occurrences in any 07-12/07-13 file. |
| P5 | **`node3` recorded a single-MAC stream for its first 7 sessions**, then a multi-source one from 07-13 18:17. | Census, §3.2. 1 MAC vs 6–23 MACs. |
| P6 | **The reference beacon was off air 07-13 17:12–17:23.** | `desk_20260713_121242.csv`: 939 frames, none from `a4:f0`. |
| P7 | **`28:05:a5:2f:fa:48` was off air during the five afternoon 07-22 `occ_*` captures.** | `grep -c` = 0 in all five; present before and after. |
| P8 | **The Heltec S3 `8c:fd:49:b7:b0:6c` has never transmitted a frame this project captured.** | 0 occurrences in all 62 files. |
| P9 | **The collector `f4:2d:c9:6f:8b:44` never appears as a source.** | 0 occurrences in all 62 files. |
| P10 | **`node_id = 68` on every valid row of all twelve 13-column files.** | 10,342,823 rows, 18 corrupted exceptions. |
| P11 | **All 62 files are channel 6**, apart from a ~0.005% tail of bit-corrupted rows. | e.g. `rx_20260722_XXXXXX.csv`: 5,932,303 of 5,932,599 rows read channel 6. |
| P12 | **`csi_2026071*.csv` in the repo root are sequential single-node runs, not a third receiver.** | No overlap with any `data/raw/` file. |

### 6.2 Inferred

| # | claim | what it rests on | strength |
|---|---|---|---|
| I1 | **The Heltec S3 `8c:fd:49:b7:b0:6c` is the second collector (`node3`).** | `docs/HANDOFF.md`'s "RX works; WiFi TX inaudible" plus role and timing. **Nothing in any CSV names it.** The 10-column schema carries no receiver identity at all. | **Plausible, unverified.** P8 is consistent with it but equally consistent with the board sitting on the bench doing nothing. |
| I2 | **The era-B/C collector is the same physical board as era-A `desk`.** | `node_id = 68` is constant, and HANDOFF names one collector on COM3. But `node_id` is a compiled-in firmware constant — it identifies a build, not a board. | **Plausible, unverified.** |
| I3 | **`desk` and `node3` are the names of physical positions.** | Filename prefixes typed at `capture.py`'s command line. | **Label only.** P2 proves two receivers; nothing proves which was which, or that the names were used consistently across days. |
| I4 | **The receivers sat at specific room coordinates — "Desk PC Receiver" at (14.0, 2.0) ft and "Hallway/Door Receiver" at (8.0, 14.0) ft.** | `pc/heatmap.py` `NODE_POS`. | **Unverified label. These are config values in a plotting script whose whole purpose is to let you drag the markers somewhere else** — the file binds keys `1` and `3` to click-to-relocate and prints "Relocated ... to X=… ft". They are defaults for an interactive tool, not a record of where hardware was. Braeden doubts the hallway placement was ever physically real; nothing in `data/raw/` supports or refutes it. **The RSSI evidence in §4 proves the two antennas were in different places — it says nothing about where.** |
| I5 | **`node3`'s single-MAC era was a MAC-filtered firmware build.** | The behaviour matches `RFF_PROMISCUOUS 0` + `TX_FILTER_MAC` exactly, and the transition (07-13 13:17 local) falls the same day as commit `d174b83` "RFF v2 baseline: field-hardened firmware" (23:12 local). But **both committed firmwares are promiscuous with an all-zero filter**, and the only filtered `csi_cfo` variant in the tree is an *uncommitted 2026-08-02* change. Whatever ran on 07-12 is in no commit. | **Well-supported, but the artifact is missing.** P5 is the proven part; the cause is not. |
| I6 | **The three beacons came from one purchase / one lot.** | Braeden's premise. `docs/LOT_HYPOTHESIS.md` §6.3: no purchase record, serial marking, or lot label exists anywhere in the repo. The three carry three different OUIs. | **Unsupported. Do not repeat as fact.** |
| I7 | **`harvest_afternoon.csv` was recorded by the `desk` node.** | Nothing. It is 10-column, follows no naming convention, and predates both prefixed families. | **Unknown. Do not assign it.** |
| I8 | **What Braeden has on the bench right now: 3 transmitters, 1 receiver, plus 2 idle boards.** | Last capture is 2026-07-23, 23 days ago. Everything after that date is unobserved. | **Inference from the last observation, not a current state.** Verify with a live census at the collector before relying on it. |

---

## 7. Reconciliation — what `docs/HANDOFF.md` gets right and wrong

`HANDOFF.md`'s hardware inventory is dated **2026-07-15**. Both headline
accuracy runs come from **07-13** data, and **38 of the 50 files with
data were recorded before two of the three beacons it lists as "on-air"
had ever transmitted.** It describes the bench *after* most of this
dataset was captured, and it is read as if it described the bench
throughout.

| inventory row | census verdict |
|---|---|
| `a4:f0:0f:77:91:20` — TX beacon (reference), on-air | **Confirmed.** All three eras. |
| `28:05:a5:2f:fa:48` — TX beacon, on-air | **Confirmed from 07-14 only.** Absent before, and absent again for ~37 min on 07-22. |
| `f4:2d:c9:70:72:30` — TX beacon, on-air | **Confirmed from 07-14 only.** |
| `f4:2d:c9:6f:8b:44` — collector, COM3 | **Not contradicted, not confirmed.** Never appears; that is expected of a receiver and proves nothing. |
| `8c:fd:49:b7:b0:6c` — Heltec S3, benched | **Confirmed benched.** Zero frames, ever. |
| Heltec S3 sibling, unused | **No trace.** Cannot be confirmed or refuted from captures. |
| *(nothing)* | **The inventory has no row for the second era-A receiver, and there provably was one.** |

`HANDOFF.md` open thread #5 reads "**Multi-receiver deployment** (2nd RX
exists in firmware as `csi_cfo`) … a Pi host is planned." That is
forward-looking language for something that **already ran, for two days,
producing 16 files and 1,717,532 frames** — and then stopped. A dated
correction has been added to `docs/HANDOFF.md`.

---

## 8. Confidence, and its limits

| claim | confidence | basis |
|---|---|---|
| Three transmitters, no fourth | **Very high** | Filter separates by 20×+ on two independent axes over 546 candidates. |
| Two receivers on 07-12/13 | **Very high** | Simultaneity is physical, not statistical; corroborated by RSSI and frame-count divergence. |
| One receiver from 07-14 | **Very high** | Zero overlap at a zero-second threshold across 12 files spanning 9 days. |
| Beacon first-transmit dates | **Very high** | Row-level, plus zero string occurrences earlier. |
| `node3` behaviour change | **High** | Sharp, 1 → 6+ MACs, bracketed to a 69-minute window. |
| `28:05` absent on 07-22 afternoon | **High** | Direct `grep -c`, five files. |
| The identity of any receiver | **None — see §6.2** | No receiver identity exists in era-A data, and `node_id` is a build constant in era B/C. |

### Limitations

- **Absence is established for channel 6 only.** All captures are channel
  6 (P11). A node transmitting elsewhere would be invisible. Nothing
  suggests that happened; this census cannot exclude it.
- **A receiver that recorded nothing leaves no trace.** Eleven zero-byte
  files exist. A third receiver that never produced a row would not
  appear in this census by any method.
- **`pc_time_us` is batch-stamped.** Overlap conclusions are safe at the
  minutes-to-hours scale used here; sub-second timing claims from that
  column are not, and none are made.
- **The last observation is 2026-07-23.** Everything about the present
  bench is inference (I8).
- No hardware was touched, no existing file under `data/raw/`,
  `firmware/`, `pc/rff/`, `pc/occ/` or `site/` was modified.

---

## Files added by this investigation

- `pc/node_census.py` — read-only census tool; source of every number here
- `docs/NODE_CENSUS.md` — this file
