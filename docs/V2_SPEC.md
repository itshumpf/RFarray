# V2_SPEC — the second-generation CSI receiver: firmware and telemetry record

**Date:** 2026-08-22 · **Type:** specification, not an implementation. No
firmware was written by this pass. Read-only on `data/raw/` and `firmware/`;
no serial port was opened; nothing was staged, committed or pushed. One file
in the repo was written: this one.

**Governing rule.** Every requirement below cites the measurement that forced
it — a file, a figure, or a line of code. Requirements with no evidence behind
them are not in §2 or §3; they are in §7, split into what can be checked now
and what only the build can check. Where a premise handed to this pass could
not be located in the repo, or where the repo contradicts it, that is stated
in place rather than repeated.

Five measurements in this document were run during this session against files
already on disk, because a requirement leaned on a claim no artifact
supported. Each is marked **[measured 2026-08-22]** and carries the command
that reproduces it. Everything else names an existing document.

B1 = `a4:f0:0f:77:91:20` (reference), B2 = `28:05:a5:2f:fa:48`,
B3 = `f4:2d:c9:70:72:30` (B1's characterised clock twin,
`docs/LOT_HYPOTHESIS.md`). d0wd = `node_id` 68 (ESP32-D0WD, UART bridge),
s3 = `node_id` 108 (Heltec ESP32-S3, native USB).

---

## 1. What V2 is for

V2 is not a better fingerprinter. The 21–22 August work establishes that the
fingerprint itself is at a physical limit this hardware cannot argue with: the
SFO estimate's noise stops being white at τ ≈ 10 s and its Allan deviation
*rises* past τ ≈ 200 s, so 256× more averaging buys 20 % of separation
(`docs/SEPARATION_SCALING.md` §2.2, §3.1); the twin pair sits at 0.66–1.18σ at
174 of 175 swept configurations and a blind 60/40 holdout scores 55.2 % on a
three-class problem where chance is 33 % (§4.2, §5.1); no reference condition
reduces the receiver term without shrinking the device term by the same factor
(`docs/REFERENCE_CHOICE.md` §0). What the week *did* establish is that a large
fraction of every anomaly investigated turned out to be the instrument and not
the radio — a dead subcarrier producing 2π branch errors
(`docs/UNWRAP_DEFECT.md` §0), a one-byte checksum inventing a hundred devices
a night (`docs/OVERNIGHT_2026-08-22.md` §5.3, §6), a counter that wraps nine
times and is read as if it wrapped once (§4.2), a receiver-state change that
was invisible for two days because no field records it
(`docs/S3_SFO_STEPS.md` §10). **V2 exists to make instrument defects
self-reporting, so that the next unexplained number can be attributed instead
of investigated.** Every requirement below is a field or a behaviour that
would have shortened one of those investigations, and nothing below is
expected to move a separation figure.

---

## 2. Must

### 2.1 Frame integrity: CRC-16 replaces the one-byte XOR

`firmware/common/telemetry/telemetry.c:33-39` computes a single XOR byte over
header and payload; `pc/rff/protocol.py:99-103` checks it and
`:153-180` advances one byte on failure. A random byte sequence passes an
8-bit check with probability 2⁻⁸.

What that costs, measured on one night:

| | d0wd | s3 |
|---|---|---|
| corrupt rows | **142 of 2,983,560** | **0 of 3,564,005** |
| distinct MACs in the file | 131 | 34 |
| of those, decode artefacts | **100** | **0** |
| MACs seen exactly once | 102 | 5 |

(`docs/OVERNIGHT_2026-08-22.md` §1, §5.3, §6; the 142/0 count is reproduced
independently by `docs/REFERENCE_CHOICE.md` §1.2's `awk` and its
decomposition — 141 by field plausibility, 140 by median filter, 139 by both.)

Two properties make this a Must rather than a nuisance:

- **74 of the 100 artefact MACs have all six octets inside the int8 CSI
  range** — they are CSI sample bytes read as a MAC after a resync landed in
  the middle of a payload and the XOR passed by chance
  (`docs/OVERNIGHT_2026-08-22.md` §5.4). One, `16:fd:15:2f:fa:48`, carries
  B2's last three octets with the first three replaced by sample bytes: a
  resync three bytes early.
- **A single corrupt row moved a headline number by 65,536.** Line 95,349 of
  the d0wd file reads `dropped 15` between neighbours reading 9,743, with
  every other field plausible. Naive wrap-safe accumulation over that file
  returns 8,930,262 drops against a true 17,366 — an overstatement of **514×**
  (`docs/OVERNIGHT_2026-08-22.md` §4.2).

**Requirement.** The frame trailer becomes a CRC-16 over every byte after the
magic. Resync remains byte-at-a-time but a resync must not be silent: the
count of bytes discarded to resync and the count of CRC failures are carried
in STATUS (§2.7).

**What this does not claim.** The premise handed to this pass — "USB CDC
carries CRC16 and retransmission; UART carries nothing" — appears in no file
in this repo (`grep -rn 'CRC16\|retransmi' .` returns nothing outside
unrelated float literals). It is a true property of USB bulk transfers, but it
is not the evidence here. The evidence is the 142-against-0 asymmetry and the
100-against-0 artefact asymmetry, and `docs/DUAL_RX_2026-08-21.md` §2.1 is
explicit that attributing it to the link "is an inference from the two files,
not a measurement of either link". §7(b)4 states the prediction that decides
it.

### 2.2 `dropped` widens u16 → u32

`firmware/csi_rx/main/main.c:85` declares `static volatile uint16_t
s_dropped`, incremented at `:131-133` when `xQueueSend` into the 64-deep queue
(`:46`) fails. Measured over one 6.5 h capture
(`docs/OVERNIGHT_2026-08-22.md` §4.2, confirmed by an independent `awk` that
shares no code with the analysis script):

| | d0wd | s3 |
|---|---|---|
| queue drops, wrap-safe, corrupt rows removed | 17,366 | **624,291** |
| u16 counter wraps in the session | 0 | **9** |
| loss | 0.579 % | **14.906 %** |
| what `field_diag.py:106` / `diagnose.py:540` report | 17,366 (right by luck) | **34,467** |
| error of the shipped one-wrap estimator | none | **18.11× understatement** |

Both shipped tools compute `(last − first) & 0xFFFF`, i.e. they assume at most
one wrap, and they print the result as a finding. On the 2026-08-21 capture
the same construction understated the S3 by 4.92×
(`docs/DUAL_RX_2026-08-21.md` §2.2).

**Requirement.** `dropped` becomes u32. At the S3's measured 26.83 drops/s
(`docs/OVERNIGHT_2026-08-22.md` §4.2) a u32 wraps in 5.1 years. Cost: +2 B per
frame.

### 2.3 `boot_ts_us` widens u32 → u64

`firmware/common/telemetry/include/telemetry.h:8` and
`pc/rff/protocol.py:183-189`: the timestamp is a u32 microsecond counter that
wraps every 4,294.967 s. Each node wrapped **five times** in the 6.5 h
overnight capture (`docs/OVERNIGHT_2026-08-22.md` §4.1, with the ten
before/after value pairs listed).

The wrap is cheap on its own. What is not cheap is that **a wrap and a corrupt
row are the same observation** — both appear as a large negative step — and
disentangling them is what produced the 514× error in §2.2.

**[measured 2026-08-22]** Every negative `esp_timestamp_us` step in the four
21–22 August captures, classified:

```
awk -F, 'NR==2{p0=$1;prev=$8;next}
 NR>2{d=$8-prev; if(d<0){neg++; if(d<-2147483648){d+=4294967296;wr++}
      else {back++; backsum+=-d; d=0}} uw+=d; prev=$8; p1=$1}
 END{printf "rows=%d pc_span=%.3f esp_span=%.3f deficit=%.3f negsteps=%d wraps=%d backward=%d backtime=%.3f\n",
      NR-1,(p1-p0)/1e6,uw/1e6,(p1-p0)/1e6-uw/1e6,neg,wr,back,backsum/1e6}' FILE
```

| file | pc span | esp span | negative steps | u32 wraps | true backward | backward time |
|---|---|---|---|---|---|---|
| `s3_20260821_125017.csv` | 4212.617 s | 4212.695 s | 1 | 1 | **0** | 0.000 s |
| `desk_20260821_125017.csv` | 4212.617 s | 4212.679 s | 1 | 1 | **0** | 0.000 s |
| `s3_20260822_023034.csv` | 23267.252 s | 23267.639 s | 5 | 5 | **0** | 0.000 s |
| `d0wd_20260822_023034.csv` | 23267.365 s | 25630.685 s | 7 | 5 | **2** | 2362.608 s |

The two apparent backward steps on the d0wd are both corrupt rows, not clock
faults. Line 2,210,392 reads `rssi=11, noise_floor=−21, channel=14, len=241`
— three impossible fields, the artefact family of
`docs/OVERNIGHT_2026-08-22.md` §5.4. Line 2,959,896 is
`16:fd:15:2f:fa:48` with `len=0` and `env_id=65280`; the beacon's own
trajectory resumes on the next row (`3470272445 → 3470292452`).

**Requirement.** `boot_ts_us` becomes u64 µs. Cost: +4 B per frame. A u32 plus
a u8 epoch counter (+1 B) is the cheaper alternative and is acceptable; what
is not acceptable is a host-side reconstruction that cannot distinguish a wrap
from corruption.

**Correction to the premise.** This pass was told `esp_timestamp_us` "runs
backwards — 82 s lost over 4,212 s". No file supports that; the table above
shows the node clock agreeing with the host clock to 0.08 s over both 4,212 s
captures. The related claim that `FrameEstimator`'s `0 < dt < 1.0` guard
(`pc/rff/dsp.py:141`) means "CFO is silently thrown away" is also wrong in
magnitude — **[measured 2026-08-22]**, per beacon, consecutive-frame pairs
whose `dt` falls outside `(0, 1)` s:

| node | B1 | B2 | B3 |
|---|---|---|---|
| s3 | 6 of 1,282,393 (0.00047 %) | 6 of 830,009 (0.00072 %) | 5 of 1,449,059 (0.00035 %) |
| d0wd | 49 of 882,768 (0.00555 %) | 40 of 919,631 (0.00435 %) | 43 of 1,178,725 (0.00365 %) |

Five or six per source per night is the five wraps plus a corrupt row; the
d0wd's extra forty are its corrupt rows. The guard costs essentially nothing.
The requirement stands on the wrap/corruption ambiguity alone.

### 2.4 `seq` becomes per-source

`firmware/csi_rx/main/main.c:84` declares one node-global
`static volatile uint32_t s_latest_seq`, written at `:101-103` by the ESP-NOW
receive callback from whichever beacon transmitted most recently, and copied
at `:122` onto every CSI sample regardless of that sample's source. Directly
visible in the raw file — the first 59 rows of the d0wd overnight capture
carry three interleaved counters (≈5,682,3xx, ≈5,686,2xx, ≈129,766,2xx) with
no correspondence to the row's MAC, and over the first 200,000 rows all three
beacon MACs span the same full `seq` range
(`docs/OVERNIGHT_2026-08-22.md` §7).

Consequences, each measured:

- `pc/field_diag.py:99-101` selects the dominant MAC's rows, differences their
  `seq`, and prints "`seq gaps: N missing beacon frame(s)`". With three
  beacons on air that number is meaningless. `pc/diagnose.py:45-49` documents
  the problem and refuses to compute the figure; `pc/twin_probe.py:406`
  reports it per source anyway (`docs/CODE_INVENTORY.md` §4.2 C5).
- The header comment at
  `firmware/common/telemetry/include/telemetry.h:16-17` ("seq gaps give the
  same for RF loss") is what invites the error.
- It closed off a live question. Both receivers' delivered rate falls across
  the night — d0wd 140.2 → 121.5 fps, S3 offered 187.8 → 170.0 fps, on all
  three beacons in proportion (`docs/OVERNIGHT_2026-08-22.md` §4.3) — and §7
  of that document states that **per-beacon transmit cadence is not
  recoverable from these files**, so whether the cause is transmitter-side
  cannot be tested.
- It blocks frame-level cross-receiver alignment, which
  `docs/S3_PORT_SCOPE.md` §5.3 gap 1 names as a prerequisite for any two-node
  work: `seq` is the only token both receivers see, and it is
  cross-contaminated.

**Requirement.** `s_latest_seq` becomes a small per-source table keyed on the
transmitting MAC, so the `seq` stamped on a CSI frame is that source's own
counter. **The wire format does not change** — `seq` is already a per-frame
u32 (`telemetry.h:52-54`). Cost: 0 B, one fixed-size table in the node.

### 2.5 Receiver gain / PHY state is recorded per frame

At t = 930 s of the 2026-08-21 S3 capture, `noise_floor`, RSSI on all three
beacons, detected-frame rate and RANSAC fit residual all moved inside one 20 s
window, on the S3 only, and never returned
(`docs/S3_SFO_STEPS.md` §2, §3, §6). The largest consequence was B3/s3's SFO
moving −0.05073 rad/sc, 21× `BETWEEN_UNIT_SD`. Every candidate the data can
test was tested and excluded: not a reboot, not the 300 s calibration gate,
not a channel change, not `env_id`, not frame loss, not USB throughput, not
corrupt rows (§8, §9). The document's own conclusion (§10, "Permitted but not
established") is that an AGC or PHY gain-state change is *consistent with
every observation and inconsistent with none* — and that **nothing measures
it**: no field in the CSV and no field in `tlm_status_t`
(`telemetry.h:35-46`) carries PHY, gain or calibration state.

It was not a one-off. `docs/POSITIVE_CONTROL_0822.md` §2.1 finds the same
class of event at t ≈ 23,097 s of the overnight capture, this time on **both**
nodes: 23 of 24 monitored series leave a pre-chosen baseline by more than
6 × MAD, 20 of them inside a 70 s band, and the S3's `noise_floor` leaves the
value it held for 86.89 % of the night's 2,327 ten-second bins and never
returns in the 132 s that remain (§2.2). And 6.5 h of empty room established
that the S3 does not produce such an event spontaneously on a
tens-of-minutes timescale (`docs/OVERNIGHT_2026-08-22.md` §0), so the trigger
is external — but *what changes inside the receiver* is still unnamed.

`docs/S3_SFO_STEPS.md` §11 names the fix in one line: "Add gain/AGC state and
`esp_wifi_sta_get_rssi`-class PHY fields to `tlm_status_t` — it has no slot
for any of them today — and re-capture. This is the single measurement that
would convert §10's 'permitted' into an answer."

**Requirement.** An `agc_gain` byte (and any comparable PHY state index the
IDF exposes for the target) is carried **on every CSI record**, not only in
STATUS. Per-frame, because the event is resolved at 10 s and the analysis that
found it aligns gain against per-frame SFO; STATUS at 5 s
(`csi_rx/main/main.c:59`) is too coarse to place it against a 20 s transition
and cannot be joined to a beacon. Cost: +1 B per frame.

This field is the instrument for the primary hypothesis of V2. Its prediction
and its kill condition are stated in §7(b)1.

### 2.6 Queue occupancy is carried per frame

`dropped` counts failed `xQueueSend` (`csi_rx/main/main.c:131-133`) into a
64-deep queue (`:46`). A full FIFO tail-drops the *newest* arrival, so
survivors are conditioned on the queue having had room — they are not a
uniform sample. Both dual-receiver documents name this and both say it is
untested: `docs/DUAL_RX_2026-08-21.md` §2.6 ("This has not been tested and no
artifact in the repo tests it") and `docs/OVERNIGHT_2026-08-22.md` §9 ("Emit
queue occupancy in the STATUS frame — `tlm_status_t` has no slot for it — and
test survivor SFO against occupancy").

The exposure is large and asymmetric. The S3 loses **14.906 %** of offered
frames over 6.5 h and 20.220 % over the 08-21 session
(`docs/OVERNIGHT_2026-08-22.md` §4.2, `docs/DUAL_RX_2026-08-21.md` §2.2), and
its loss is near-continuous — 26.83 drops/s mean, only 5.1 % of seconds clean,
18.9 % of drops in the worst 10 % of seconds against 10 % for a uniform
process. The d0wd's 0.579 % is bursty: 100 % of its drops fall in the worst
10 % of seconds. Whatever bias exists, the two nodes have it in different
shapes, and cross-receiver comparison is the whole point of a two-node array.

**Requirement.** `q_occupancy`, the queue depth at the moment the sample was
enqueued, as u8 (queue depth is 64). Per frame, because the test named above
is survivor SFO against occupancy *at that frame's arrival*. Cost: +1 B.

### 2.7 STATUS frames must reach disk, and must carry drain-path instrumentation

**STATUS is emitted every 5 s (`csi_rx/main/main.c:59,187-205`) and the
recorder throws it away.** `pc/capture.py:123-128` decodes a STATUS record,
uses it to update a one-line TUI status string, and `continue`s — it is never
written to the CSV. Every field `tlm_status_t` already carries —
`reset_reason`, `cal_state`, `crash_count`, `cal_remaining_s`, `uptime_s`,
`pkt_total`, `drop_total`, `heap_free`, `noise_floor_cq8`, `rssi_avg_cq8` —
is absent from every file in `data/raw/`.

The cost is visible in the analysis. `docs/OVERNIGHT_2026-08-22.md` §4.1 and
`docs/S3_SFO_STEPS.md` §9 both had to rule out a reboot by u32 wrap
arithmetic on `esp_timestamp_us`, because `reset_reason` and `crash_count`
were emitted, decoded, and discarded five seconds at a time all night.

The second half of this requirement is the S3's service ceiling. Its delivered
rate is pinned at **153.2–153.7 fps in every 30-minute block of a 6.5 h run
while its drop rate moves by a factor of 1.9**
(`docs/OVERNIGHT_2026-08-22.md` §4.3), reproducing 154.0–154.3 fps in all ten
deciles of the 08-21 session against an offered load of 175–204 fps
(`docs/DUAL_RX_2026-08-21.md` §2.5). That is a drain-path ceiling, and its
cause is unmeasured: `docs/CODE_INVENTORY.md` §6 lists it as not checked, and
§1.3 names the two candidates — three `fwrite`s plus an `fflush` per frame
(`firmware/common/telemetry/telemetry.c:37-40`, i.e. 462 writes and 154
flushes per second at the observed rate) versus the 4 Hz full-1 KB I²C
framebuffer blast of `display_task` (`csi_rx/main/main.c:208-249`,
`ssd1306.c:114-123`). Nothing in the repo separates them.

**Requirement, three parts.**

1. The recorder writes STATUS records to a second file per session, one row
   per record, with the same `pc_time_us` clock as the CSI file so the two
   join.
2. `tlm_status_t` gains: `resync_bytes u32`, `crc_fail u32` (§2.1),
   `q_high_water u8` (§2.6), `agc_gain u8` (§2.5), `emit_ns_accum u64` and
   `emit_count u32` (mean and total time inside `emit()`), and
   `display_enabled u8`.
3. `display_task` is disableable at run time from the safe-boot console
   (`node_hal.c:132-201`), so the OLED can be removed from the ceiling
   experiment without a reflash. The console itself needs porting — see §4.5.

`emit_ns_accum` ÷ `emit_count` against `display_enabled` answers
`docs/CODE_INVENTORY.md` §6 in one pair of runs and needs no instrumented
one-off build.

### 2.8 `first_word_invalid` is carried, one bit

`wifi_csi_info_t` carries a `first_word_invalid` flag and
`firmware/csi_rx/main/main.c:109-134` never reads it
(`docs/S3_PORT_SCOPE.md` §2.1, which also measured the symptom on
`desk_20260713_104513.csv`: mean |value| 99.0 at pair 0 and **3.0 at pair 1**,
against ~32–36 for pairs 2–26, with the same step at the HT-LTF boundary).
`pc/rff/dsp.py:35` drops pair 0 as DC but **keeps pair 1** — `k = +1` is
inside `_USABLE_MASK`.

Five weeks later, on a different capture and by a different route,
`docs/UNWRAP_DEFECT.md` §2 measures the same bin on the same board:
**k = +1 has |CSI| = 3.0 counts in 100.0 % of 20,000 frames**, on every source
the node hears, against a band median of 20.0 — the only bin below 40 % of the
band median. Its phase is uniform (the wrapped step across the k = −1 → +1 gap
exceeds 2.5 rad in 20.46–20.65 % of frames against the 20.4 % a uniform phase
predicts), and that is the trigger for the entire unwrap defect (§0, §3).

So the flag that exists in the SDK and has never been read is a *candidate
explanation* for the one hardware-class defect the week found.
`docs/UNWRAP_DEFECT.md` §10 is careful about this: "That node 68's dead k = +1
bin is a hardware fault rather than a firmware or CSI-buffer artefact" is
listed as **permitted, not established**, and §12 item 1 says the cause is
unknown.

**Requirement.** One bit of a `flags` byte carries `first_word_invalid` as the
SDK reports it, per frame. Cost: 0 B beyond the flags byte specified in §3.
This does not repair the bin (§4.1) — it makes the next pass able to say
whether the bin is the first word or something else, without a soldering iron.

### 2.9 The record carries its own provenance

Six documents name the same outstanding experiment — swap the two nodes'
physical positions and repeat — and every one of them is blocked by the same
gap: `docs/DUAL_RX_2026-08-21.md` §6 ("the single most valuable next capture
and it costs one afternoon"), `docs/S3_SFO_STEPS.md` §11,
`docs/OVERNIGHT_2026-08-22.md` §9, `docs/POSITIVE_CONTROL_0822.md` §6,
`docs/SEPARATION_SCALING.md` §8.1, `docs/REFERENCE_CHOICE.md` §9.1,
`docs/AMBIENT_SEPARATION.md` §9.3. Until it is run, "the d0wd reads
differently" and "that corner of the room reads differently" are the same
hypothesis — and after it is run, nothing in the capture would record which
configuration produced which file.

Everything currently known about node and beacon position is operator
testimony recorded as testimony. `docs/OVERNIGHT_2026-08-22.md` §0:
"Operator-stated conditions, recorded here as stated and not verified by these
files: nobody was in the room…receiver positions unchanged…and **not**
swapped; beacons unmoved; the S3 had a battery attached." §6 then has to warn
"Do not read the between-session RSSI change as a receiver-state change — this
capture cannot separate the two", after per-beacon RSSI moved by up to
10.3 dB between two sessions the operator states were physically identical.
`docs/POSITIVE_CONTROL_0822.md` §0 adds a second: the operator's recollection
of entering the room "approximately five minutes" before the end is
contradicted by the data's 3 min 20 s, and the file cannot arbitrate.

Two slots already exist and are unused. `env_id` is a u16 in every frame
header (`telemetry.h:4`) and reads **0 on every row of both overnight files**
— `docs/REFERENCE_CHOICE.md` §1.2 screens on `env_id == 0` precisely because
it is invariant. The CSV's `label` column exists (`pc/capture.py:20`) and
`capture.py:129` writes `""` into it on every row; only `occ_capture.py` ever
fills it.

**Requirement.** Three parts, none of which costs a wire byte.

1. `env_id` is set from NVS per deployment via the safe-boot console
   (`node_hal.c:82-88`) and must be non-zero for any capture intended for
   analysis. A recorder that sees `env_id == 0` warns.
2. The recorder writes a per-session provenance sidecar at capture start:
   wall-clock start, per-node `node_id` / port / link type / firmware version
   / `env_id`, and a free-text position record per node and per beacon. It is
   written before the first row, not after the last.
3. The recorder writes a **stop marker** when the capture is asked to end.
   `pc/capture.py:193-196` catches `KeyboardInterrupt`, sets the stop event and
   restores the terminal without writing anything further, so
   `docs/POSITIVE_CONTROL_0822.md` §6 records that "the last seconds of every
   capture in `data/raw/` are therefore unattributable" — and §2.7 of that
   document had to leave the last ~70 s of the overnight capture unattributed
   between operator movement and shutdown for exactly this reason.

### 2.10 CSI must leave the host format as a field that cannot be split wrong

`csi_data` is a quoted comma-separated list nested inside a CSV
(`pc/capture.py:129-132`). Three known scripts have got it wrong, all of them
written in the last week:

- `pc/exp_overnight_0822.py:303-304` and `pc/exp_s3_sfo_steps.py:153-155,590-592`
  use `cs.split(",", 128)` and reject a row yielding fewer than 129 items.
  `maxsplit=128` returns **at most** 129 items, so a row carrying exactly 128
  values yields 128 and is discarded. `grep -rn 'split(",", 128)' pc/` finds
  these two files and no others (`docs/POSITIVE_CONTROL_0822.md` §1.2).
- The same two lines appear in the out-of-repo script quoted at
  `docs/DUAL_RX_2026-08-21.md` Appendix B line 695.

128 values is exactly one LLTF, and **all ambient traffic is 128-length**
(`docs/AMBIENT_SEPARATION.md` §1.1). The cost was not a wrong number, it was
an absent one: no ambient source had ever been phase-estimated in this repo
before 2026-08-22, and the first run of
`docs/POSITIVE_CONTROL_0822.md`'s analysis reported "0 usable windows for all
17 ambient sources", which looked like a property of the devices and was a
property of the parse — `CLAUDE.md` failure mode **C** exactly. No published
figure moved, because every affected document is beacon-only and all three
beacons transmit at `csi_len = 256` in 100 % of rows.

The correct reads exist and are not rare — `pc/rff_offline.py:203`
(`np.fromstring(..., sep=",")`), `pc/occ/ingest.py:141-151`, and
`pc/node_census.py:52,70` (which truncates to 100 chars before splitting,
safe because `csi_data` is field 10). The format nonetheless invites the
error, three times in one week.

**Requirement.** The V2 CSI record does not embed a variable-length
comma-separated list in a delimited text field. Either the CSI payload is
base64 of the raw int8 bytes (fixed alphabet, no delimiter, one `split(",")`
away from correct), or the CSV carries a byte offset into a binary sidecar.
The former is simpler and costs 33 % more bytes on disk; the latter costs
nothing on disk and adds a file to keep in step. **This spec does not choose
between them** — see §6.

Whichever is chosen, `csi_len` remains an explicit column and a reader must
cross-check it against the decoded length. That cross-check currently passes:
the parsed-vector histogram equals the `csi_len` column histogram row for row
on both overnight files (`docs/SEPARATION_SCALING.md` §1.1,
`docs/AMBIENT_SEPARATION.md` §1.1).

### 2.11 Silent truncation becomes a flag

`firmware/common/telemetry/telemetry.c:51-52` clamps `csi_len` to 384 and
emits the truncated payload with no indication. `csi_rx/main/main.c:128`
clamps identically into the queue. `pc/rff/protocol.py:31` admits 384 as a
valid length, and 384 is a real length from a real transmitter —
`f4:69:42:f2:d2:af` reads 100 % at 384 across 44 source sessions
(`data/fingerprints/f46942f2d2af.json`), and misclassifying it as an artefact
is a correction `docs/OVERNIGHT_2026-08-22.md` §1 had to make mid-pass. So the
host cannot distinguish "a 384-byte transmitter" from "a longer frame silently
cut to 384".

**Requirement.** One bit of the `flags` byte: `csi_truncated`, set when the
clamp fires. Cost: 0 B.

---

## 3. The telemetry record, field by field

Header, little-endian, all records:

| field | V1 | V2 | why |
|---|---|---|---|
| magic | `C5 52`, 2 B | `C5 53`, 2 B | a new magic keeps V1 and V2 decodable by one parser; `protocol.py:163-171` already dispatches on magic |
| `type` | u8 | u8 | unchanged |
| `ver` | *(absent)* | **u8, new** | a CSI frame carries no format version today. `TLM_FW_VERSION` (`telemetry.h:33`) is emitted only inside the STATUS payload (`telemetry.c:66`), so a capture containing no STATUS row — which is every capture in `data/raw/`, §2.7 — records no version at all |
| `node_id` | u8 | u8 | unchanged. Defaults to MAC byte 5 (`node_hal.c:73`), which self-distinguishes the two boards for free: 68 and 108 (`docs/S3_PORT_SCOPE.md` §1.2) |
| `env_id` | u16 | u16 | unchanged width, **must be non-zero** (§2.9). Reads 0 on 6.55 M rows today |
| `boot_ts_us` | u32 | **u64** | wraps every 4,294.967 s; 5 wraps per node per night; a wrap is indistinguishable from a corrupt row (§2.3) |
| `len` | u16 | u16 | unchanged |
| **header total** | **12 B** | **17 B** | |

CSI payload (`type = 1`):

| field | V1 | V2 | why |
|---|---|---|---|
| `seq` | u32 | u32, **per-source** | node-global today; three interleaved counters on one row's MAC (§2.4). Width unchanged |
| `mac[6]` | 6 B | 6 B | unchanged |
| `rssi` | i8 | i8 | unchanged. Quantised to 1 dB, which already bounds what can be read from it (`docs/DUAL_RX_2026-08-21.md` §2.4) |
| `noise` | i8 | i8 | unchanged width. Useless on the D0WD — `−97` on 100.000 % of 2,983,418 clean rows, zero transitions in 6.5 h (`docs/OVERNIGHT_2026-08-22.md` §2.1) — and informative on the S3, where it takes four values and is a per-node scalar agreeing across beacons to 0.02 dB (§2.2). Keep it; do not treat it as a control (§4.4) |
| `chan` | u8 | u8 | unchanged |
| `agc_gain` | *(absent)* | **u8, new** | §2.5 |
| `q_occupancy` | *(absent)* | **u8, new** | §2.6 |
| `flags` | *(absent)* | **u8, new** | bit 0 `first_word_invalid` (§2.8), bit 1 `csi_truncated` (§2.11), bit 2 `cal_gate_open`, bits 3–7 reserved and zero |
| `dropped` | u16 | **u32** | wrapped 9 times in one night; shipped readers understate by 18.11× (§2.2) |
| `csi[n]` | n B | n B | unchanged. `n ∈ {128, 256, 384}`; ceiling stays 384 (`protocol.py:31`, `csi_rx:45`, `telemetry.c:49`). A 128-length record is a valid LLTF under `dsp.py`'s mask — guard bins and DC exactly zero in 200 of 200 sampled rows of each length (`docs/AMBIENT_SEPARATION.md` §1.2) |
| **payload total** | **15 + n** | **20 + n** | |

Trailer:

| field | V1 | V2 | why |
|---|---|---|---|
| checksum | XOR u8, 1 B | **CRC-16, 2 B** | §2.1 |

**Frame size.** V1 at `n = 256` is `12 + 15 + 256 + 1` = **284 B**, which is
what `pc/throughput_test.py:129` and `pc/diagnose.py:217` assume. V2 is
`17 + 20 + 256 + 2` = **295 B**, **+11 B = +3.87 %**.

That increase is not free on the UART node, and the spec says so rather than
hiding it. At the d0wd's measured overnight rate of 128.23 fps
(`docs/OVERNIGHT_2026-08-22.md` §4.1), 284 B/frame is 36.4 KB/s = **79.0 %**
of the 46,080 B/s that 460800 8N1 carries; 295 B/frame is 37.8 KB/s =
**82.1 %**. At the 08-21 rate of 137.06 fps
(`docs/DUAL_RX_2026-08-21.md` §1) it goes 84.5 % → 87.8 %. Whether the D0WD
can carry the V2 record at its own peak rate is an open question (§6, §8).

STATUS payload (`type = 2`): all ten V1 fields retained at their V1 widths
(`telemetry.h:35-46`), plus `resync_bytes u32`, `crc_fail u32`,
`q_high_water u8`, `agc_gain u8`, `emit_ns_accum u64`, `emit_count u32`,
`display_enabled u8` (§2.7). V1 STATUS is 27 B and `protocol.py:35` parses
`"<BBBHHIIIIhh"` = 27; V2 STATUS is 27 + 22 = 49 B. At one record per 5 s the
cost is 9.8 B/s.

---

## 4. Should

Ordered by how much weaker the evidence is than §2's.

### 4.1 Emit `resid_std`-class fit quality? No — but keep the door open

`docs/UNWRAP_DEFECT.md` §7 measures a working per-frame detector for the
branch defect: branch-invariant coherence over all 52 usable bins,
`C = |Σ exp(j(φ_k − (m·k + b)))| / 52`, flagged at `C < 0.5`. It gives
100 % recall at 0.00 % false positives on the synthetic population and 92.2 %
at 0.00 % on the d0wd's real `1c:ce:51:f3:0d:fa` frames, and across 479,705
real beacon frames it flags 0.000–0.023 % in five of six cells against
**2.604 %** in d0wd/B3 — identifying, unprompted, the one beacon cell the repo
already knew was broken.

**Why this is not a node requirement.** The node does no phase fitting; `C`
needs the slope and intercept `ransac_line` returns, which exist only
host-side. The evidence supports shipping the detector in `pc/rff/`, not in
firmware. It is recorded here because it changes what the *record* has to
carry: nothing. Weaker than §2 because the detector has not been run over the
full 6.4 M-frame capture, its precision on the beacons is 54–83 % rather than
100 %, and it has not been added to `dsp.py` (`docs/UNWRAP_DEFECT.md` §7,
§11).

### 4.2 Temperature

Four documents converge on it without any of them measuring it. The correlated
component of the SFO noise has a timescale of tens to hundreds of seconds
(`docs/SEPARATION_SCALING.md` §2.2 — the Allan minimum sits at τ = 21.5–186.5 s
in five of six cells), which is the right timescale for thermal;
`docs/REFERENCE_CHOICE.md` §4.2 shows nothing is common-mode between beacons
at one receiver, which is what a *per-crystal* thermal effect would look like;
and `docs/SEPARATION_SCALING.md` §8.3 and `docs/REFERENCE_CHOICE.md` §9.4 both
list temperature logging as the outstanding measurement. **Nothing in this
repo has ever recorded a temperature.**

Weaker than §2 because no measurement in the 21–22 August window demonstrates
a thermal effect — the hypothesis is inferred from a timescale and from the
absence of common mode, and `docs/OVERNIGHT_2026-08-22.md` §3.2 found the one
available proxy (`noise_floor`) uninformative on the S3, its three per-beacon
correlations not even agreeing in sign (+0.31, +0.42, −0.28).

**Requirement if taken.** An on-die temperature read per STATUS record
(u16 c°C, +2 B per 5 s), and an external sensor if one can be fitted. On-die
temperature measures the SoC, not the crystal, and the spec should not pretend
otherwise.

### 4.3 Adaptive window length in the aggregator

`WindowAggregator` emits nothing until 64 accepted frames arrive
(`pc/rff/dsp.py:164,178`), which at observed rates is 1.1–2.0 s and makes any
shorter observation structurally impossible
(`docs/WINDOW_CONVERGENCE.md` §5.8). Ambient sources cannot fill one window at
all: the largest in the overnight capture has 932 frames and most have 20–159,
so `docs/AMBIENT_SEPARATION.md` had to work per-frame, at a cost it measured —
64-frame windowing multiplies the beacons' separations by about **6.4×**
(§4.4), a factor no ambient source can have.

Weaker than §2 because this is a host-side aggregator change with no telemetry
consequence, because `docs/WINDOW_CONVERGENCE.md` §5.3 warns that separation
*rising* as windows shrink is a sample-size artefact of the metric, and
because `docs/SEPARATION_SCALING.md` §3.1 shows the whole window-length axis
buys +20 % per 256×.

### 4.4 A receiver-state control the D0WD can actually provide

`noise_floor` on the D0WD reads `−97` on 99.9961 % of raw rows and 100.000 %
of clean rows, with zero row-to-row transitions in 6.5 h
(`docs/OVERNIGHT_2026-08-22.md` §2.1), reproducing
`docs/S3_SFO_STEPS.md` §4 on a file five times larger. Both documents say the
same thing in the same words: **"the d0wd's `noise_floor` held" is evidence of
nothing** — it could not have stepped. Anything wanting the D0WD as a control
for a receiver-state change needs a different column, and no column in the CSV
carries one.

§2.5's `agc_gain` is the intended answer. This entry exists because it is not
established that the D0WD exposes a varying gain index either — it is a
different silicon revision from the S3, and the field that ought to have
varied does not. Weaker than §2.5 by exactly that gap.

### 4.5 Port the safe-boot console off `UART_NUM_0`

`hal_diag_console()` (`node_hal.c:132-201`) hard-codes `UART_NUM_0` at lines
136, 137, 139 and 160. On a target whose console is USB-Serial-JTAG the code
compiles, runs, and talks to a peripheral nobody is attached to; the node
appears to hang at boot with BOOT held low, and **there is no way to set
`node_id` / `env_id` / `cal_seconds` on that board**, because
`hal_identity_save` (`node_hal.c:82-88`) is reachable only through that console
(`docs/S3_PORT_SCOPE.md` §1.2).

This is a Should rather than a Must only because it is not demonstrated to be
broken on the flashed S3 — the S3's `sdkconfig` keeps
`CONFIG_ESP_CONSOLE_UART_CUSTOM=y` on GPIO1/GPIO3 alongside
`CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=y`, and which of the two carries
`stdout` "is recorded nowhere in this repo and was not tested"
(`docs/CODE_INVENTORY.md` §4.4 S12). It becomes a Must the moment §2.9 requires
`env_id` to be set per deployment, since that is the console's only job.

### 4.6 A compiled-in MAC filter must be visible in STATUS

`firmware/csi_cfo/main/main.c` in the working tree sets `RFF_PROMISCUOUS 0`
and a hard-coded `TX_FILTER_MAC` (`:51`, `:80`, uncommitted, mtime
2026-08-02 23:11). If the reference beacon's MAC changes, the node queues
nothing, so `s_dropped` does not increment either — it reports zero frames
*and* zero drops, which reads as a quiet channel — and then
`hal_rf_liveness_start(120)` reboots it every 120 s, each reboot restarting
the 300 s calibration gate (`docs/CODE_INVENTORY.md` §4.4 S1). No STATUS field
carries the filter, so no host tool can tell this apart from an off-air
beacon, and the change is uncommitted, so git does not record which MAC a
flashed node is locked to.

Weaker than §2 because the committed receiver filters nothing
(`csi_rx/main/main.c:68`, all-zero = accept all) and no artifact records the
filtered build being flashed. It is in the spec because the failure is silent
in three directions at once.

**Requirement if taken.** `filter_mac[6]` and `promiscuous u8` in STATUS,
+7 B per 5 s.

---

## 5. Explicitly out of scope

### 5.1 The dead subcarrier — but not for the reason usually given

`k = +1` on node 68 reads |CSI| = 3.0 counts in 100.0 % of 20,000 sampled
frames, on every source it hears, against a band median of 20.0
(`docs/UNWRAP_DEFECT.md` §2). **[measured 2026-08-22]** it holds across the
whole night, not one chunk — see §7(a)1 for the sweep and its numbers.

Repairing it is out of scope, and `docs/UNWRAP_DEFECT.md` §8 is blunt about
why: "the thing being fixed is a hardware fault. A software change that
tolerates a dead bin also **hides** it, and this is the first artifact in the
repo that identifies it. The right first move is to find out why that bin is
at 3 counts — a board fault, a firmware CSI-buffer bug, or an antenna
front-end problem — not to make the DSP robust to it."

**The correction.** That document does *not* establish it is a hardware fault.
§10 lists "That node 68's dead k = +1 bin is a hardware fault rather than a
firmware or CSI-buffer artefact" under **permitted but not established**, and
§11 warns against quoting it as one: "What is measured is 3.0 counts in 100 %
of 20,000 frames. The cause is unknown." Meanwhile `docs/S3_PORT_SCOPE.md`
§2.1 independently measured the same bin at mean |value| 3.0 five weeks
earlier and named a specific firmware-visible candidate: the unread
`first_word_invalid` flag.

So: **repair is out of scope; carrying the flag that would discriminate the
causes is a Must (§2.8).** The distinction matters because if the bin is the
first word, it is not a fault at all, it is a documented SDK behaviour the
receiver has never read — and `dsp.py:35` includes that bin in the fit.

### 5.2 CFO recovery

Out of scope. Not because CFO is hard to measure, but because there is nothing
in it:

- Over 6.4 M frames, CFO-axis separation is **0.01σ–0.02σ** at the shipped
  configuration and 0.14σ–0.21σ at 16,384-frame windows, and all three
  per-frame beacon medians lie within **0.06 Hz of zero**
  (`docs/SEPARATION_SCALING.md` §3.3). Every 2-D Mahalanobis figure in that
  document equals its SFO-only figure to two decimals in every row of every
  table.
- That corroborates `docs/TWIN_INVESTIGATION.md` §3 (d = 0.03) on a different
  capture, a different source pair and 6.4 M frames.
- `cfo_hz` is a *residual*: `pc/rff/dsp.py:138-143` derives it from the
  frame-to-frame intercept delta, so it measures what is left after the
  radio's own frequency tracking. `docs/DUAL_RX_2026-08-21.md` §3.5 found two
  of three inter-receiver CFO differences with CIs straddling zero and the
  largest at 3 % of a single window's own spread.

**A correction to the aliasing argument.** This pass was told CFO is "aliased
at the 100 Hz beacon rate". 100 Hz is the *transmit* cadence
(`git show HEAD:firmware/csi_tx/main/main.c:17`, `SEND_INTERVAL_MS 10`). The
received per-source rate is 37.0 fps at the desk and 40.8 fps at the S3
(`docs/CODE_INVENTORY.md` §4.1 D5), and `docs/DUAL_RX_2026-08-21.md` §3.5
computes the estimator's actual representable limit from the observed
inter-arrival gaps: **25.0–40.6 Hz at the median gap and 7–12 Hz at the p95
gap** — the latter inside the observed IQRs, i.e. the CFO tail is aliased
differently on the two receivers *by construction*, since the noisier link has
longer gaps. The aliasing is roughly 2.5× worse than the premise stated. The
conclusion is unchanged and stronger.

**Consequence for the host, recorded here because it follows from the same
measurement.** The feature space is effectively one-dimensional, so the χ²
thresholds at `pc/rff/discriminator.py:23-24` — 5.991 and 9.210 — are the
2-DOF values for a 1-D problem. The 1-DOF values are **3.841 and 6.635**
(d = 1.960σ / 2.576σ), as `docs/AMBIENT_SEPARATION.md` records in its preamble.
That is a host-side constant, not a firmware or telemetry matter, and it is
listed in §6 as something V2 does not change on its own.

### 5.3 Any unwrap "fix"

Out of scope. Five repairs were built and measured against a branch-invariant
arbiter on the same 1,926 frames across two receivers
(`docs/UNWRAP_DEFECT.md` §8). Turn-out rate, against the current 6.07 %:

| | what it does | d0wd |
|---|---|---|
| — | current `np.unwrap` | **6.07 %** |
| A | rebranch about a one-lag circular-mean anchor | 13.17 % |
| B | rebranch about a one-lag anchor, amplitude-weighted | 83.13 % |
| C | drop bins under 25 % of the frame's median \|CSI\| | 8.54 % |
| D | fit inside the longest run with no `np.unwrap` correction | 63.27 % |
| E | rebranch about a zero-padded-FFT anchor (length 1024) | **1.03 %** |

Four are worse than doing nothing. C is the one that looks most obviously
right — the trigger *is* a bin at 3 counts, so mask it — and it makes things
worse, because removing k = +1 widens the DC gap to Δk = 3 and the threshold
also deletes real bins in the channel's fades.

E is better and is still not adoptable, for four measured reasons: it never
reaches zero; its benefit depends on an FFT length it has no principled value
for (10.80 % / 1.65 % / 1.03 % at 64 / 256 / 1024, and at 64 it is *worse*
than doing nothing); it is **not a no-op on the frames the current code gets
right**, changing 9.7–19.7 % of beacon frames and moving the emitted window
count by −0.5 % to −11.3 %; and it introduces a failure mode the current code
does not have, since its anchor is the strongest delay tap and this very
source has a competing tap at 0.31–0.50 of the main peak's height.

The decisive point for V2 specifically: **the defect does not reach any
published beacon figure.** Over 479,705 beacon frames and 6,515 windows across
both nodes, the number of windows sitting within 10 % of 2π/32 of their own
source's median is **zero** (`docs/UNWRAP_DEFECT.md` §6). Only the ambient
work is exposed, and the ambient work is per-frame by necessity. A change that
moves every historical SFO figure in the repo, to fix something that touches
no beacon window, is not a V2 requirement.

### 5.4 Bandwidth, as a project

Out of scope because it is not the constraint, and the number that suggested
it was does not exist in this repo.

`firmware/s3_throughput/README.md:17` is headed **"State: builds, not yet
flashed, never run"** and `:26-27` reads "A first `idf.py flash` attempt
failed… **No byte of this has run on the board, and no number it produces has
been checked against anything.**" `docs/S3_PORT_SCOPE.md` §0 records the
675 KB/s premise as "Not recorded, and the newest artifact in the repo
contradicts it", and §7 item 7 lists it among the things that could not be
determined. `docs/CODE_INVENTORY.md` §4.1 D1 notes only that the README is now
stale about the *port*, not about the throughput run.

The measured picture does not need that figure. The S3's offered load at its
peak is 187.8 fps × 284 B = **53.3 KB/s**
(`docs/OVERNIGHT_2026-08-22.md` §4.3) and it drops **14.906 %** of it. Its
delivered rate is pinned at 153.2–153.7 fps in every 30-minute block of 6.5 h
while its drop rate moves by a factor of 1.9 (§4.3), reproducing 154.0–154.3
fps in all ten deciles of a separate 70-minute session
(`docs/DUAL_RX_2026-08-21.md` §2.5). A link that is losing 15 % of a 53 KB/s
offered load is not a link problem at any plausible USB rate. **The ceiling is
in the drain path**, and §2.7 specifies the instrumentation that identifies
which part of it.

**A second correction.** The premise "the D0WD's UART runs ~86–90 % of a
46 KB/s ceiling" is high. Measured: 128.23 fps × 284 B = 36.4 KB/s = **79.0 %**
on the overnight capture (`docs/OVERNIGHT_2026-08-22.md` §4.1); 137.06 fps =
38.9 KB/s = **84.5 %** on 08-21 (`docs/DUAL_RX_2026-08-21.md` §1); 139.8 fps =
39.7 KB/s = **86.2 %** on the 26-minute live window
(`docs/CODE_INVENTORY.md` §4.1 D4). The range is 79–86 %, and on the overnight
capture the D0WD lost 0.579 % of frames — it was not against a ceiling that
night.

### 5.5 Anything that changes the SFO estimator

Out of scope for V2 as a whole, not only the unwrap. `pc/rff/dsp.py` has not
been modified since 2026-07-13 20:42:46 and every figure in every 21–22 August
document was produced by it, with reproduction checks that agree to the
printed digit across five independently written scripts
(`docs/OVERNIGHT_2026-08-22.md` §1.1, `docs/POSITIVE_CONTROL_0822.md` §1.1,
`docs/SEPARATION_SCALING.md` §0b/§0c, `docs/REFERENCE_CHOICE.md` §1.4,
`docs/AMBIENT_SEPARATION.md` §4.4). That reproducibility is the only thing
making the week's conclusions comparable to each other, and V2 is a
firmware-and-record change that must not put it at risk.

**[corrected 2026-08-23] The condition that reproducibility holds under, and
it is narrower than the sentence above implies.** Those five scripts agree
because **every one of them replays a stream from the start of a file**.
`FrameEstimator` owns a per-instance generator — `self._rng =
np.random.default_rng(rng_seed)` (`pc/rff/dsp.py:118`) — which it hands to
`ransac_line` on every frame (`:132`), and `ransac_line` draws two
`rng.integers(0, n, size=64)` per call (`:85-86`). The generator therefore
advances once per fitted frame, so **the 64 random 2-point hypotheses tried
at frame N depend on how many frames preceded N in that stream.** The one
path that does not advance it is `csi_to_complex` returning `None` for a
frame shorter than 128 ints (`:127-129`), which returns before the fit.
Nothing else in `dsp.py` is path-dependent for the *slope*:
`unwrap_continuity` (`:55-68`, `:131`) shifts the whole frame by a multiple
of 2π, which moves the intercept and leaves the slope and the inlier set
untouched. `_prev_intercept` / `_prev_ts` (`:139-145`) are path-dependent by
design, because `cfo_hz` is a finite difference.

**[measured 2026-08-23]** `python pc\exp_v2_pre_checks_0823.py rng`, on
`data/raw/d0wd_20260822_144424.csv`, B3, 60,000 len-256 frames, comparing
each file-frame against itself under two replay origins (frame 0 and
frame 1), index-aligned:

| | |
|---|---|
| gate decision (`inlier_ratio >= 0.6` and `resid_std <= 0.8`) flips | **896 of 59,999 frames, 1.49 %** — the accepted set is itself path-dependent |
| frames accepted under both (54,130): slope differs | **68.5 %** |
| median \|Δslope\| on those | **7.11e-04 rad/sc = 0.30 × `BETWEEN_UNIT_SD`** |
| p99 / max \|Δslope\| | 1.23e-02 / 4.41e-02 rad/sc |
| emitted 64-frame window medians, 852 vs 852 windows, compared in order | **99.4 % differ**, median 6.94e-04 (0.29 × SD), max 1.21e-02 (**5.13 × SD**) |

So the reproducibility §5.5 rests on is real but **conditional**: it is
bit-reproducibility of a fixed replay, not stability of the estimator. Two
consequences for V2, and only these two:

1. **The prohibition stands and is strengthened.** Any change that alters how
   many frames precede a given frame in a stream — a new `csi_len` the
   `size < N_CPLX * 2` guard rejects, a parser that admits or drops frames the
   old one did not, a per-source split that re-partitions the streams — moves
   every downstream slope by this amount without touching one line of
   `dsp.py`. The origin the shipped pipeline replays from is the **file**:
   `pc/rff_offline.py:238-239` re-creates `estimators = defaultdict(
   FrameEstimator)` inside the per-path loop and keys it on `mac` (`:256`), so
   there is one fresh generator per (file, source-MAC) and it restarts at
   every file boundary. §2.4's per-source `seq` does **not** disturb this (it
   changes a column, not the stream partition). §2.10's base64 choice does
   **not** either, provided the decoded vector is identical. A `csi_len`
   change would, and so would anything that changes where a session is cut
   into files — which §2.9 part 3's stop marker and §2.7 part 1's second
   STATUS file both touch.
2. **Do not quote a re-derived per-frame slope as agreeing "to the printed
   digit" with a published one unless it was replayed from the same file
   origin.** The window-level figures in `docs/SEPARATION_SCALING.md`,
   `docs/AMBIENT_SEPARATION.md` and `docs/REFERENCE_CHOICE.md` were, so they
   stand; a V2-era re-run that starts anywhere else will not reproduce them
   digit for digit, and that is not evidence of a regression.

Fixing this is out of scope for V2 for the same reason the unwrap is (§5.3):
seeding `ransac_line` per frame instead of per stream would move every SFO
figure in the repo. It is recorded here so the next pass does not read a
2 × 10⁻⁴ disagreement as a bug. `pc/rff/dsp.py` was not modified by this
pass; its mtime is still 2026-07-13 20:42:46.

The one gate change the evidence *does* support is a host-side analysis
choice, not a pipeline change: `min_inlier 0.6` deletes ambient sources
entirely and inconsistently — the same device is accepted at 0.0 % on one
receiver and 37.5–81 % on the other, and which receiver changes per device
(`docs/POSITIVE_CONTROL_0822.md` §3.4, `docs/AMBIENT_SEPARATION.md` §2, §3.5).
`max_resid = 0.8` rejects **zero of 6,386,119** fitted frames, the largest
`resid_std` anywhere being 0.2202 (`docs/SEPARATION_SCALING.md` §4.1). Neither
observation is a V2 requirement.

---

## 6. Migration and comparability

**What changes on the wire.** New magic `C5 53`; header 12 → 17 B; CSI payload
15 + n → 20 + n B; trailer 1 → 2 B. Frame at n = 256: 284 → 295 B (+3.87 %).
STATUS payload 27 → 49 B.

**What breaks, by name.**

| site | breakage |
|---|---|
| `pc/rff/protocol.py` | needs a third parser. `_try_v1`/`_try_v2` and the magic dispatch at `:163-171` extend cleanly; `CSI_MAX = 384` and the `length − 15` derivation at `:123` become `length − 20` |
| `pc/throughput_test.py:129`, `pc/diagnose.py:217` | both hard-code 284 B/frame |
| `pc/live_view.py:25-26` | already dead — v1-only magic and a 21-byte header, renders a blank waterfall against v2 firmware (`docs/CODE_INVENTORY.md` §4.4 S2). V2 does not make it worse |
| `pc/capture.py:20,129-132` | header row and the `csi_data` write; also the `continue` at `:123-128` that discards STATUS (§2.7) |
| every reader of `csi_data` | if §2.10 chooses base64. `pc/rff_offline.py:203`, `pc/occ/ingest.py:141-151`, `pc/node_census.py:52,70`, `pc/exp_*.py` |
| `pc/node_census.py:55,90,222`, `pc/diagnose.py:34-35` | `BEACON_MIN_LEN256 = 0.999` and literal `if ln == 256` beacon classification — unaffected by V2 as specified, but named because any future CSI-length change silently stops beacons being classified as beacons (`docs/S3_PORT_SCOPE.md` §2.2) |

**What does not break.** The CSI payload itself — same int8 interleave, same
FFT ordering, same 52-bin usable mask, same `csi_len` values. `pc/rff/dsp.py`
is untouched (§5.5), so the estimator, the gates, the aggregator and the
discriminator all behave identically on V2 records.

**Do existing captures remain analysable? Yes, without qualification.** V1 and
V2 records are distinguished by magic and can coexist in one parser and one
`data/raw/`. No column is removed and no column changes meaning; every V2
addition is a new field. The 13 GB in `data/raw/` and every figure derived
from it stay valid on their own terms.

**What would have to be re-derived, and what would not.**

- **Nothing, if V2 changes only the record.** No SFO, separation, Allan,
  accuracy or census figure in the repo depends on a field V2 alters. The drop
  totals in `docs/OVERNIGHT_2026-08-22.md` §4.2 were computed wrap-safely from
  frame-to-frame deltas and are already correct; what V2 fixes is that the two
  *shipped tools* would now also be correct.
- **Everything, if any unwrap repair ships.** Candidate E moves 9.7–19.7 % of
  beacon frames and 0.5–11.3 % of emitted windows
  (`docs/UNWRAP_DEFECT.md` §8), so every SFO number in
  `docs/SEPARATION_SCALING.md`, `docs/AMBIENT_SEPARATION.md`,
  `docs/OVERNIGHT_2026-08-22.md` and `docs/S3_SFO_STEPS.md` would need
  re-deriving on 6.39 M frames. This is the main reason §5.3 is out of scope.
- **The χ² thresholds are a separate, already-owed correction.** 5.991/9.210
  at `discriminator.py:23-24` are 2-DOF values for a 1-D feature space; 1-DOF
  is 3.841/6.635 (`docs/AMBIENT_SEPARATION.md` preamble). Changing them moves
  the anomaly-rate and stranger-rejection figures in
  `docs/TWIN_INVESTIGATION.md` and `README.md:225`, and it moves them with or
  without V2. **V2 must not be the thing that quietly changes them**; if they
  are corrected, that is its own pass with its own re-derivation.

**Cross-receiver comparability is not restored by V2 and should not be
claimed.** `docs/REFERENCE_CHOICE.md` §0 establishes that no reference
condition brings the receiver term below the device term — 1.78 with no
reference, 1.77 with the default reference — and §4.2 that reference
correction *raises* the Allan floor in six of six non-degenerate S3 cells,
because there is no measurable common short-term component to cancel. V2 adds
provenance (§2.9) and per-source `seq` (§2.4), which make the swap experiment
*possible*; it does not make two receivers comparable.

**One cost is not recovered.** The +3.87 % record widening consumes UART
headroom the D0WD may not have at its own peak rate (§3). If it does not, V2's
record is an S3-class-link format and the D0WD runs a reduced profile — which
would end simultaneous, identically-formatted dual capture, the one thing that
made this week's cross-receiver work possible. §8 lists this as unsettled.

---

## 7. Unjustified but suspected

Everything in this section is assigned. **(a)** is what can be checked before
V2 work begins, with the check named. **(b)** is what only the instrument can
check, each with a prediction stated in advance and a result that would kill
it.

### (a) To be justified BEFORE V2 work begins

**(a)1 — Is the S3 clean on all 52 bins, across the whole capture?**

*Status: partly settled during this pass; a residue remains.*
`docs/UNWRAP_DEFECT.md` §2 did sweep all 52 usable bins on both nodes, but on
**one 20,000-frame chunk per node**, on amplitude only, and §10 lists as
unknown "whether the s3 has a dead bin at any other subcarrier, or the d0wd
has more than one, outside the sampled chunks". Since V2 rests on the S3 being
a sound instrument, that is too thin.

**[measured 2026-08-22]** The sweep, extended to seven chunks of 20,000 beacon
frames spread across each overnight file (byte offsets 2 %, 15 %, 30 %, 45 %,
60 %, 75 %, 90 %) — 140,000 frames per node — reporting per-bin median |CSI|
and, per gap, the median wrapped |Δφ| and the fraction exceeding 2.5 rad. A
bin with uniform phase disturbs the gap on each side of it, and a uniform
phase exceeds 2.5 rad with probability (π − 2.5)/π = 20.4 %.

| | s3 | d0wd |
|---|---|---|
| band median \|CSI\| | 12.6–12.8 | 19.6–20.7 |
| lowest bin, every chunk | k = +26 at 8.06–8.60 | **k = +1 at exactly 3.0** |
| bins below 40 % of band median | **none, in 7 of 7 chunks** | **[+1], in 7 of 7 chunks** |
| worst of all 51 gaps, frac \|Δφ\| > 2.5 rad | **0.06 %–0.14 %** | **20.88 %–21.57 %**, always at k = +1 → +2 |

The S3 has no dead bin at any subcarrier, at any point in the night. Its three
lowest bins are k = ±24…26 at ~0.65 × the band median — a symmetric band-edge
roll-off, not a defect. The d0wd's k = +1 = 3.0 counts and its ~21 % gap
statistic reproduce at all seven points, upgrading
`docs/UNWRAP_DEFECT.md` §2's one-chunk finding to a whole-night one.

*The residue, still (a).* The sweep is 140,000 of 3.48 M / 2.90 M beacon
frames; it covers **beacon frames only** (`csi_len = 256`), so the
128-length ambient population and the 384-length source are unswept; and both
criteria are amplitude-and-adjacent-gap, so a bin dead at normal amplitude
with decorrelated phase would evade the first test and be caught by the second
only if it is badly decorrelated. **Check:** run the same sweep over the full
population of both files, including all `csi_len`, and add a per-bin
coherence-against-the-fitted-line statistic. Runs against data already on
disk; no new capture.

**(a)2 — Is the S3's 154 fps ceiling `emit()` or the OLED?**

`docs/CODE_INVENTORY.md` §6 says this "needs an instrumented build, and no
artifact in the repo measures it", and §1.3 names the two candidates. But a
cheap discriminator exists on disk and nobody has run it: `display_task` runs
at exactly 4 Hz (`csi_rx/main/main.c:247`, `pdMS_TO_TICKS(250)`). If I²C
contention is causing drops, the per-frame `dropped` deltas should carry
250 ms periodicity. **Check:** fold the per-frame drop deltas of
`s3_20260822_023034.csv` onto a 250 ms phase using `esp_timestamp_us` and test
for structure against a uniform null. Runs against data already on disk. A
positive result implicates the OLED before a single line of V2 is written; a
null result does not exonerate it and hands the question to §2.7's
instrumentation.

**[settled 2026-08-22 — `docs/S3_LINK_PATH.md`]** Neither, principally: the
ceiling is the console UART, and it is now established rather than suspected.
`telemetry.c:37-40` writes to `stdout`; `sdkconfig:1298-1310` makes the primary
console **UART0 at 460,800 baud** with USB-Serial-JTAG only as *secondary*
(`:1301`); and ESP-IDF v5.5.4 `esp_vfs_console/vfs_console.c:80-88` writes every
byte to **both**, primary first. That primary write busy-waits per byte on the
TX FIFO (`esp_driver_uart/src/uart_vfs.c:98,185-195`), which `csi_rx` never
replaces via `uart_vfs_dev_use_driver()`. Budget: 46,080 B/s = **162.25 fps** at
284 B/frame, against 154.08 / 153.18 measured — so the UART accounts for ~94.4 %
of the period and a **0.33–0.37 ms/frame residual remains unexplained**. The
S3's data does reach the host over native USB; the *rate* is set by a UART
whose pin destination on the HTIT-WB32LAF is unknown and irrelevant, since the
spin is on the FIFO. (a)2 should be restated as the residual question, and
§2.7's `emit_ns_accum` ÷ `emit_count` now has a named first suspect: the
secondary USB write runs *after* the UART write, not concurrently. Consequences
for §2.1, §2.2, §5.4, §7(a)5 and §4.5 are listed in `S3_LINK_PATH.md` §7.

**(a)3 — Does tail-drop bias the survivors?**

Named as untested in `docs/DUAL_RX_2026-08-21.md` §2.6 and
`docs/OVERNIGHT_2026-08-22.md` §9, and it sits under 14.906 % of the S3's
overnight frames. §2.6 specifies the per-frame field that answers it properly,
but a proxy exists today: the `dropped` delta immediately preceding a frame is
the number of samples the queue refused just before that frame was accepted.
**Check:** on the S3's 3.48 M overnight beacon frames, test per-frame SFO
against the preceding drop delta, controlling for the fit-quality relationship
`docs/OVERNIGHT_2026-08-22.md` §3.2 already measures (r = +0.63 to +0.84 in
six of six cells). Runs against data already on disk. If the proxy shows
nothing, §2.6 is a cheap confirmation rather than a discovery.

**(a)4 — Does the d0wd's k = +1 bin predate the S3 entirely?**

`docs/UNWRAP_DEFECT.md` §12 item 1 calls looking at the bin on the hardware
"the single highest-value action here", and it is not a software task. But its
*history* is a software task. **Check:** run (a)1's sweep against the
`desk_*` and `rx_*` captures from the same D0WD in July — including
`desk_20260713_104513.csv`, where `docs/S3_PORT_SCOPE.md` §2.1 already
measured pair 1 at mean |value| 3.0. If the bin has read 3.0 since 12 July,
it is not a recent fault and every ambient number the D0WD has ever
contributed carries the same ~6 % contamination
(`docs/UNWRAP_DEFECT.md` §4). Runs against data already on disk.

**(a)5 — What does the S3's USB link actually sustain?**

The 675 KB/s premise has no artifact (§5.4) and
`firmware/s3_throughput/README.md:17` says the test has never run.
`docs/S3_PORT_SCOPE.md` §6 step 0 already asks for exactly this and calls it
minutes of work. **Check:** flash the already-built `s3_throughput.bin` and
run `pc/throughput_test.py`. **Needs hardware, not new analysis** — no CSI
capture, no beacon, radio off. Until it exists, "bandwidth is solved" is not a
premise V2 may lean on, and §3's +3.87 % has no headroom figure to be measured
against.

**(a)6 — Can the D0WD carry the V2 record at its own peak rate?**

Arithmetic, not measurement, but it has not been done and it decides whether
V2 has one record format or two. At 295 B/frame the D0WD's measured peak of
139.8 fps (`docs/CODE_INVENTORY.md` §4.1 D4) is 41.2 KB/s = 89.5 % of 46,080.
**Check:** re-derive the peak per-second delivered rate from the raw files
rather than from block means — `docs/OVERNIGHT_2026-08-22.md` §4.3 reports
30-minute means, which understate the peak — and compare against 46,080 B/s at
295 B/frame. Runs against data already on disk.

**(a)7 — Is the corrupt-row rate a link BER?**

§2.1 rests on a 142-against-0 asymmetry, and
`docs/DUAL_RX_2026-08-21.md` §2.1 is explicit that attributing it to the link
"is an inference from the two files, not a measurement of either link".
**Check:** compute corrupt rows per byte delivered across every D0WD capture
on disk (`desk_*`, `rx_*`, `d0wd_*` — three months, ~10 GB) against both S3
captures, using the two-route screen of `docs/OVERNIGHT_2026-08-22.md` §1. A
rate constant per byte is a link BER; a rate that tracks something else is
not, and §2.1's CRC would then be treating a symptom. Runs against data
already on disk.

---

#### Appended 2026-08-22 — what a later pass moved in (a)

`docs/OLED_AND_MARGINAL_CELL.md` ran the checks named in **(a)2** and
**(a)8** against the six dual-capture files on disk. One script,
`pc/exp_oled_marginal_0822.py`; read-only on `data/raw/`; nothing staged.
The rest of §7(a) is untouched.

**(a)2 — run, and the answer is null, but the question was mis-posed.**
Two things moved.

- *The premise this item rests on is wrong for these captures.*
  `firmware/csi_rx/main/main.c:302-307` creates `display_task` **only if
  `oled_init()` returns `ESP_OK`**, and the operator states the OLED never
  came up on the S3. On a headless board `display_task` is never created and
  performs no I²C transaction, so there was no 4 Hz source in any file to
  find. The failing `oled_init()` costs one bounded 100 ms timeout
  (`ssd1306.c:53`) at `main.c:302` — before `wifi_init()` (`:309`), before
  the queue exists (`:314`) and before `csi_init()` (`:321`) — so it cannot
  contribute to `s_dropped` either.

  > **[superseded 2026-08-23 — `docs/DISPLAY_LIVE_0822.md`]** The sentence
  > above — no `display_task`, no I²C transaction, no 4 Hz source in any file
  > — was true of every capture in `data/raw/` when it was written on
  > 2026-08-22, and stopped being true that night. The S3's SSD1306 came up,
  > `display_task` was created, and `data/raw/s3_20260822_235739.csv` (started
  > 23:57:39, with `d0wd_20260822_235739.csv` as a same-process, same-host-clock,
  > no-panel control) is **the first file in this repo containing a live 4 Hz
  > display**. Do not read "there was no 4 Hz source to find" as covering it.
  >
  > What that capture measured is a **null with a stated detection ceiling,
  > not an absence of data**. Folding the S3's host inter-frame arrival gaps
  > (`diff(pc_time_us)`) onto a 250 ms node-clock (`esp_timestamp_us`) phase
  > gives R̄ = 0.002261, m = 2R̄ = 0.00452, rotation-null **p = 0.962** — the
  > least significant entry in its harmonic table — and a 240–290 ms scan in
  > 0.1 ms steps peaks at R̄ = 0.011212 at 240.3 ms against a scan-max null
  > p95 of 0.0309, **p = 1.000** (`DISPLAY_LIVE_0822.md` §0, §2.3, §2.4).
  > The ceiling is the number that matters: the 250 ms rotation null's p95 of
  > 0.020074 means **a drain stall larger than ≈ 5.02 ms per 250 ms cycle
  > would have been detected** (§2.6), against the 23.5 ms stall the question
  > was posed about — 4.7× above the ceiling. The D0WD control's ceiling is
  > *tighter* still at 2.92 ms.
  >
  > So on a board with the panel actually running, **the display is not
  > delaying frame delivery**, consistent with `display_task` at priority 3
  > against `csi_drain_task` at priority 5 and a blocking rather than spinning
  > I²C wait. Two things it does **not** settle, both from that document's own
  > §8: nothing in the record says whether the panel was refreshing during
  > that capture (no column, no STATUS field — which is exactly §2.7 part 2's
  > `display_enabled u8`), and nothing bounds the **I²C transaction itself**,
  > which can cost 23.5 ms and cost the drain nothing at priority 3. **§2.7
  > part 3 is therefore still required, and (a)2's residual question is
  > unchanged**; what has changed is that "no file contains a 4 Hz source" is
  > no longer a reason not to look.

- *The fold itself is null on the file this item names.* On
  `s3_20260822_023034.csv`, 624,290 drops, the drop rate folded on 250 ms
  gives R̄ = 0.002393 against a circular-rotation null p95 of 0.002645,
  p = 0.094; effect-size ceiling **m = 2R̄ ≈ 0.005**, i.e. no 4 Hz modulation
  above 0.5 % of the mean drop rate. Four of the other five captures are
  also null. `s3_20260822_144424.csv` does carry structure (p = 0.00050 at
  250 ms) but its **fundamental is 1000 ms**, not 250 ms, and no period in
  `firmware/` is 1 Hz. Note for anyone re-running this: **5000 = 20 × 250**,
  so `status_task` (`main.c:190`) and `rf_liveness_check`
  (`node_hal.c:256`) would both masquerade as 250 ms periodicity; that
  confound is tested and excluded there.

**(a)2 gains a third candidate.** `docs/CODE_INVENTORY.md` §1.3 lists two —
`emit()`'s three `fwrite`s plus an `fflush`, and the OLED I²C blast. Neither
is the console link itself. `firmware/csi_rx/sdkconfig:1298-1310` puts the
S3's console on **UART0 at 460,800 baud** = 46,080 B/s 8N1 = 162.25 fps at
284 B/frame, and the S3's measured on-wire rate is **94.44 %** and
**94.38 %** of that budget in its two pinned sessions, against a D0WD that
never exceeds 84.00 %. Permitted, not established. It is also the cheapest
of the three to test: rebuild with USB-Serial-JTAG as the *primary* console
and re-capture ten minutes. **§2.7 part 3 is unaffected** — nothing here
reduces the need for a run-time `display_task` disable, because no capture
on disk was taken with a working panel and none can answer the question.

**(a)8 — run; seven candidates measured, none explains it.** All eighteen
node × beacon × session reject rates rebuilt from one pipeline, reproducing
every published figure to ≤ 0.095 pp. No covariate survives correction over
the eighteen cells; the largest (cell RSSI, ρ = −0.639) collapses within
each board; node-level covariates have an effective n of 6, not 18, and none
reaches p < 0.35 there; against the movement itself the best correlate is
band tilt at p = 0.021 against a 0.0083 threshold. Each candidate has a
direct counterexample in the data. Time of day fails in the opposite
direction: the two afternoon sessions are the **most dissimilar** pair of
the three, by 4.3×. **(a)8 stays in §7(a)**, with the seven listed
candidates now excluded rather than untested.

**One thing for §5.5 and for anyone quoting a reject rate.** The shipped
`resid_std <= 0.8` gate (`pc/rff/dsp.py:164,175`) rejected **0 of 8,274,369
fitted frames, in 18 of 18 cells**. Every rejection anywhere in these six
captures is `inlier_ratio < 0.6` (`dsp.py:164,173`). One of the two gates is
currently a no-op.

---

#### Appended 2026-08-23 — (a)3, (a)4, (a)6 and (a)7 run

One script, `pc/exp_v2_pre_checks_0823.py`; read-only on `data/raw/`; no
serial port opened; nothing flashed, staged, committed or pushed. Caches went
to `$TMPDIR/v2_pre_checks_0823/`, outside the repo tree. A capture was running
on COM6/COM12 throughout, so every reader drops a final line with no trailing
newline and reports the count; `data/raw/d0wd_20260823_014740.csv` and
`s3_20260823_014740.csv` grew during the pass and are read as live.
**(a)1, (a)2, (a)5 and (a)8 are untouched by this pass.**

**(a)3 — run. The proxy is null, with the bound stated.**
`python pc\exp_v2_pre_checks_0823.py a3p 0.0 0.2` (then `0.2 0.5`, `0.5 0.8`,
`0.8 1.0`) `; ... a3`. Four byte-range parts of
`data/raw/s3_20260822_023034.csv`, each replaying its own `FrameEstimator`
from its own origin — see the §5.5 correction; that is why these slopes are
not bit-comparable to `docs/OVERNIGHT_2026-08-22.md`'s, and why the
association below is the claim rather than any individual value.

3,564,005 rows, **0 field-screen rejects** (reproducing "zero corrupt rows in
3,564,005", §2.1), 0 frames on which RANSAC returned `None`, 0 partial rows.
3,561,460 frames fitted, 3,541,742 accepted by the shipped gates. The
association is between a frame's SFO and the wrap-safe `dropped` delta on the
row immediately preceding it.

| accepted frames | n | r(SFO, drop) | r partial, controlling `resid_std` | r(drop, `resid_std`) |
|---|---:|---:|---:|---:|
| B1 | 1,273,887 | **−0.0056** | −0.0051 | −0.0133 |
| B2 | 823,417 | **−0.0058** | −0.0059 | −0.0061 |
| B3 | 1,444,438 | **+0.0114** | +0.0112 | −0.0056 |

Controlling for the `resid_std` relationship §3.2 measures changes nothing,
because the drop delta and the fit quality are themselves independent
(third column). Bucketed medians, accepted frames, against the drop-delta-0
bucket:

| drop delta before the frame | B1 n | B1 Δmedian SFO | B2 Δ | B3 Δ |
|---|---:|---:|---:|---:|
| 0 | 1,098,645 | — | — | — |
| 1 | 135,289 | −0.000089 (0.04 σ) | −0.000117 (0.05 σ) | +0.000223 (0.09 σ) |
| 2 | 33,364 | −0.000113 (0.05 σ) | −0.000106 (0.04 σ) | +0.000298 (0.13 σ) |
| 3–5 | 6,581 | −0.000180 (0.08 σ) | −0.000113 (0.05 σ) | +0.000300 (0.13 σ) |
| 6–10 | 8 | (too few) | (too few) | (too few) |

σ = `BETWEEN_UNIT_SD` = 0.00237 (`pc/exp_thermal_evidence.py:129`).

**Read it as: no effect this proxy can see, bounded at 0.13 σ, and the sign
does not agree across the three beacons** (B1 and B2 fall, B3 rises) — which
is what an artefact of three independent noisy series looks like, not a
selection effect. Note also that the proxy is exercised over almost none of
its possible range: 86.2 % of accepted frames are preceded by a delta of 0
and **eight frames in 3.5 M** by a delta above 5.

**What this does and does not settle.** §2.6 is now a **cheap confirmation
rather than a discovery**, exactly as this item said it would be if the proxy
showed nothing. It is **not** removed, and §7(b)3 is neither confirmed nor
killed: a `dropped` delta of 0 means the queue refused nothing between two
frames, which is not the same as the queue having been empty. Tail-drop
conditions survivors on the queue having had *room*, and every occupancy
below 64 is invisible to this proxy. Only §2.6's per-frame `q_occupancy`
sees it.

**(a)4 — run. Yes, and by more than the item asked.**
`python pc\exp_v2_pre_checks_0823.py a4`. (a)1's sweep, on the reference
beacon at `csi_len = 256`, 7 byte offsets × up to 2,500 frames per file,
across every capture in `data/raw/`.

`k = +1` reads a per-bin median |CSI| of **exactly 3.00 counts in 45 of the 45
files that reach 200 reference-beacon frames in any chunk** — 0.128–0.265 of
each file's own band median, and in nearly every file the only bin below 40 %
of it. The worst of the 51 gaps is adjacent to that bin (`−1 → +1` or
`+1 → +2`) in **45 of 45**, at 20.37–24.75 % of frames exceeding 2.5 rad,
against the 20.4 % a uniform phase predicts. The earliest is
`desk_20260712_101116.csv`, **2026-07-12**, on 504 frames. So the bin has read
3.0 since the first substantial capture in the dataset, five weeks before the
S3 existed, and `docs/UNWRAP_DEFECT.md` §4's ~6 % contamination applies to
every ambient number this lineage has ever contributed.

**The larger result, which this item did not ask for.** The sweep was run
against `node3_*` as an era-A contrast, and `node3_*` reads **3.00 as well**,
in 12 of 12 files with data. `docs/NODE_CENSUS.md` §4 establishes `desk` and
`node3` as two physically distinct receivers, by 15 overlapping simultaneous
sessions and by independent reception. `harvest_afternoon.csv` reads 3.00; so
do all six `rx_*`, all six `occ_*` and all five `d0wd_*` including the live
one. The S3 reads `k = +1` at **9.00–14.32, ratio 0.779–1.152, and has no bin
below 40 % of band median in 6 of 6 files**.

So the bin is present on **at least two physically distinct receivers** and
absent on the third. A per-board hardware fault would have to have produced
*the same value, 3.00 counts, on two different boards* — which makes
`docs/UNWRAP_DEFECT.md` §10's "permitted but not established" hardware-fault
reading considerably less likely, and `docs/S3_PORT_SCOPE.md` §2.1's unread
`first_word_invalid` — a part-family / SDK behaviour, not a defect —
considerably more likely. **§2.8 is strengthened; §5.1's refusal to repair
the bin is unchanged, and §5.1's sentence that the cause is unknown still
stands** — this narrows the candidates, it does not read the flag.

*The identity caveat, stated because the item's own wording assumes past it.*
This item says "the same D0WD in July". `docs/NODE_CENSUS.md` §3.3 states that
whether the era-B/C collector (`node_id` 68) is the same physical board as
era A's `desk` is "not established by anything in the data", and era A carries
no receiver identity at all (§1). The sweep therefore measures **file
lineages, not boards**. That does not weaken the finding — it is what makes
the two-receiver result available.

**(a)6 — run. V2 fits. One record format, not two.**
`python pc\exp_v2_pre_checks_0823.py a67` and `a6b`.

*First, the method the item asked for does not work.* Per-second bins on
`pc_time_us` exceed **100 % of the 46,080 B/s budget on every high-load D0WD
capture** — up to 127.6 % at V1 sizing on `rx_20260715_201703.csv` — which
cannot happen on the wire. `pc_time_us` is a per-serial-drain-batch host stamp
(`docs/OVERNIGHT_2026-08-22.md` §1), so a 1 s bin measures host batching as
much as wire rate. It overstates the peak as surely as 30-minute means
understate it. **Do not use 1 s bins for this question.**

*The measure that does work.* Maximum sustained 60-second delivered rate, on
every 13-column D0WD capture, screened by both routes:

| | max 60 s fps | max 60 s, V1 (284 B) | max 60 s, **V2 (295 B)** | whole-file loss |
|---|---:|---:|---:|---:|
| `rx_20260714_011619` | 143.27 | 88.3 % | **91.7 %** | 19.71 % |
| `rx_20260714_031131` | 144.08 | 88.8 % | **92.2 %** | 37.07 % |
| `rx_20260715_201703` | 143.98 | 88.6 % | **92.1 %** | 13.59 % |
| `rx_20260722_204658` | 143.18 | 88.2 % | **91.6 %** | 5.26 % |
| `rx_20260722_XXXXXX` | 144.62 | 89.0 % | **92.4 %** | 10.03 % |
| `desk_20260821_125017` | 144.60 | 88.5 % | **92.0 %** | 3.50 % |
| `d0wd_20260822_023034` | 143.25 | 88.3 % | **91.7 %** | **0.579 %** |
| `d0wd_20260822_144424` | 139.75 | 86.1 % | **89.4 %** | 0.84 % |
| `d0wd_20260822_235739` | 143.37 | 88.3 % | **91.8 %** | 5.32 % |
| `d0wd_20260823_013537` | 143.10 | 88.2 % | **91.6 %** | 15.43 % |
| `d0wd_20260823_014740` (live) | 143.40 | 88.3 % | **91.7 %** | 7.44 % |

**142.28–144.62 fps, 87.7–89.0 % of budget, in every capture across 40 days,
while whole-file loss ranges over a factor of 64.** A quantity that holds to
±0.8 % while the thing it would cause varies 64-fold is a ceiling, not a
coincidence. That is the peak-per-second delivered rate this item asked to be
re-derived from the raw files; the 139.8 fps this item quotes from
`docs/CODE_INVENTORY.md` §4.1 D4 is **3.4 % low**.

**Answer: the worst 60-second window in three months, re-costed at 295 B per
frame, is 92.4 % of 46,080 B/s. V2 does not overflow the D0WD's link, and
§8's "whether V2 has one record format or two" resolves to one.**

*The margin that is not recovered, stated because it is the real risk.* The
empirical ceiling sits about **11 % below** the 460,800-baud budget and
nothing in this repo explains the gap. If that ceiling is **per byte**, V2
buys fewer frames: 144.62 → 139.2 fps, a **3.73 % frame-rate cost**, landing
as additional queue drops on a node already losing 0.58–37 %. If it is **per
frame** — a fixed cost in the drain path — V2 costs nothing.
**These files cannot separate the two**, because the implied bytes-per-frame
at the ceiling is 281–284 in every file: the D0WD's traffic is essentially all
`csi_len = 256`, so bytes and frames are collinear. What separates them is
(a)5's throughput run, or §2.7's `emit_ns_accum ÷ emit_count`, or one capture
with a deliberately mixed `csi_len` population. Until then **3.73 % more D0WD
drops is the worst case V2 should be budgeted against**, and it is small
beside the loss already present and instrumented by §2.6.

*Method check.* This pipeline returns **17,366 drops and 0.579 % loss** on
`d0wd_20260822_023034.csv`, reproducing `docs/OVERNIGHT_2026-08-22.md` §4.2 to
the unit, including the single one-row `dropped` spike at line 95,349 that
only the median-filter route sees; and 11,696 on `d0wd_20260822_235739.csv`
against `docs/DISPLAY_LIVE_0822.md` §3's 11,697, the one-row difference being
a row consumed at a pipeline boundary.

**(a)7 — run. Yes within one population, and emphatically not across the
dataset.** `python pc\exp_v2_pre_checks_0823.py a67`. Corrupt rows by the
six-column field screen where the columns exist, four-column where they do
not, over every capture on disk.

*Within the modern D0WD population it is a constant per-byte rate.* Eight
13-column D0WD captures over 100 MB, 2026-07-14 → 2026-08-22,
**13,056,913,505 file bytes, 771 corrupt rows**. Against a single-rate Poisson
null, **χ² = 7.08 on 7 dof** (5 % critical value 14.07). Per-file rates
4.98 × 10⁻⁸ to 7.14 × 10⁻⁸; pooled

> **λ = 5.905 × 10⁻⁸ per file byte = 1.78 × 10⁻⁷ per wire byte
> = 1.78 × 10⁻⁸ per bit** (284 B/frame, 10 bit/byte 8N1).

Eight files spanning 40 days and a 25× range of size all sit inside the
Poisson band. **That is the link-BER signature this item asked for, and it
means §2.1's CRC-16 is treating the cause rather than a symptom.** The 14:44
capture's single data point (§9, ratio 1.27) is inside it.

*Across the dataset it is not constant, and the exception is large.*

| population | files | file bytes | corrupt | rate | expected at λ |
|---|---:|---:|---:|---|---:|
| era A `desk_*` 07-12/13 | 20 | 1,465,450,693 | **0** | — | 86.5 |
| era A `node3_*` | 15 | 1,465,929,479 | **0** | — | 86.6 |
| era A `harvest_afternoon` | 1 | 183,518,109 | **0** | — | 10.8 |
| era C `occ_*` 07-22 | 6 | 182,648,157 | 9 | 4.93e−8 | 10.8 |
| era B/C `rx_*` | 6 | 9,692,882,457 | 573 | 5.91e−8 | 572.3 |
| 2026-08-21 d0wd | 1 | 496,551,023 | 34 | 6.85e−8 | 29.3 |
| 2026-08 `d0wd_*` | 5 | 3,059,319,192 | 175 | 5.72e−8 | 180.7 |
| 2026-08 `s3_*` (native USB) | 6 | 4,020,865,197 | **0** | — | 237.4 |

Two of the rows in that table include a file that was still being written:
`d0wd_20260823_014740.csv` and `s3_20260823_014740.csv` are snapshots at
99,497,299 B and 115,680,379 B respectively. **Neither is in the χ² test**,
which admits only the eight files over 100 MB, all of them closed.

**Era A produced 0 corrupt rows in 3.115 GB where λ predicts 184, and the S3
produced 0 in 4.021 GB where λ predicts 237.** Neither is a screen artefact:
on the 13-column files the four-column screen finds **780 of the 791** the
six-column screen finds — 98.6 % sensitivity — so era A's zero survives its
two missing columns by two orders of magnitude.

*What changed on 2026-07-14, and why this dataset cannot say.* Three things
moved at once. The wire format went v1 → v2 (`pc/rff/protocol.py:26-27`,
magic `C5 51` → `C5 52`, header 21 B → 12 B); the CSV went 10 → 13 columns
(`docs/NODE_CENSUS.md` §1); and the sustained load roughly doubled — era A
runs at 11.75–68.01 fps mean against era B/C's 107.7–142.6, i.e. well clear of
the ceiling (a)6 just measured against pinned against it. A rate that is
constant per byte *within* the saturated population and zero *below* it is
consistent with a BER that is a function of load, which is not the same claim
as a BER.

**Residue, and it belongs in §7(a).** Is the 2026-07-14 step the load, the
frame format, or the host bridge? **Check:** run the D0WD deliberately below
about 60 % of the budget — a beacon at reduced cadence, or a promiscuity
setting that cuts ambient traffic — for one hour, and count corrupt rows per
byte against λ. Needs one capture; **no reflash of the receiver**, no new
analysis. Until it is run, §2.1's CRC-16 is still justified — 771 corrupt rows
against 0 on the S3 is the same asymmetry on a 28× larger sample than §2.1
quotes — but §7(b)4's *kill* condition needs restating: a V2 D0WD that still
produces corrupt rows at the same **per-byte** rate has not exonerated the
link, because V2 will also be running at the same utilisation.

---

### (b) Key hypotheses OF V2

Each of these is a reason the instrument is being built. Each is stated as a
hypothesis, with what would confirm it and what would kill it, **before** the
field exists.

**(b)1 — The t = 930 s class of event is a receiver AGC / PHY gain-state
change.** *Instrument: `agc_gain` per CSI frame (§2.5).*

The hypothesis is `docs/S3_SFO_STEPS.md` §10's, stated there as permitted and
not established: it "is consistent with every observation (per-node
`noise_floor`, all-links-simultaneous, more frames detected, different
residual on each link) and inconsistent with none. But nothing measures it…
this is a hypothesis with no contradicting evidence, which is not the same as
support." Note that the premise handed to this pass — "a gain/PHY state change
at t = 930 s was invisible for two days" — states as fact what its own source
declines to state; nothing has measured a gain change.

*Confirms it:* on a capture containing an event of this class, the reported
gain index steps within one 10 s bin of the RSSI / `noise_floor` /
reject-rate step, on the affected node and not on the other, and holds rather
than reverting — matching the 6 × MAD baseline-departure test
`docs/POSITIVE_CONTROL_0822.md` §2.1 already defines.

*Kills it:* the gain index is constant across the event, or steps at times
uncorrelated with the 24 monitored series. In that case the event is not AGC,
and the surviving candidates — multipath local to one node, a PHY
recalibration, the charge controller
(`docs/OVERNIGHT_2026-08-22.md` §0, still open because the charge LED was lit
throughout and an absent stimulus and an absent effect are not
distinguishable) — must be separated by the position swap and a
battery-state-controlled repeat, not by this field.

*Note on scope:* one confirming event is not a mechanism. It converts
"unknown" into "AGC", and leaves *why the AGC moved* open.

**(b)2 — The falling frame rate is transmitter-side, or it is not.**
*Instrument: per-source `seq` (§2.4).*

Both receivers detect fewer frames as the night goes on — d0wd 140.2 → 121.5
fps, on all three beacons in proportion; S3 offered 187.8 → 170.0 fps
(`docs/OVERNIGHT_2026-08-22.md` §4.3). "Both receivers and all three beacons"
is where a shared cause would show, and §7 records that the file "carries no
usable transmit cadence", so the obvious test is unavailable.

*Confirms transmitter-side:* per-source `seq` advances more slowly over the
night, in step with the falling received rate.

*Kills it:* per-source `seq` advances at a constant rate while frames received
per unit `seq` falls — the transmitters are exonerated and the cause is in the
channel or in both receivers at once.

*Note:* this is the cheapest hypothesis in the list. It costs zero wire bytes
and one fixed-size table.

**(b)3 — The S3's 14.9 % loss is unbiased with respect to the phase estimate.**
*Instrument: `q_occupancy` per CSI frame (§2.6).*

The null hypothesis is the convenient one, and `docs/DUAL_RX_2026-08-21.md`
§2.6 gives four measured reasons to believe it (loss is not source-selective,
±2–3 % across beacons; not RSSI-selective, 0.38 dB, below the field's
quantisation; it costs time resolution rather than estimator precision; the S3
still delivered more frames than the d0wd). It then names the one reason that
survives: tail-drop takes the *newest* arrival, so survivors are conditioned.

*Confirms the null:* survivor SFO shows no dependence on queue occupancy at
arrival, beyond the fit-quality relationship already measured at r = +0.63 to
+0.84.

*Kills it:* a monotone dependence of SFO on occupancy. If that appears, 14.9 %
of the S3's frames were removed non-randomly and **every S3 SFO figure in the
21–22 August work inherits a selection effect** — including
`docs/SEPARATION_SCALING.md`'s 0.69σ / 3.72σ / 4.68σ and every Allan curve
built on the same frames. This is the highest-consequence hypothesis in the
list, and it is why the field is per-frame rather than per-STATUS.

**(b)4 — The frame-integrity asymmetry is the link, not the board.**
*Instrument: CRC-16 on both nodes (§2.1).*

*Confirms it:* with CRC-16, the d0wd's artefact-MAC count falls to
approximately zero and the S3's stays at zero, on a capture of comparable
length. The corruption was on the wire and the 8-bit check was letting it
through.

*Kills it:* the d0wd still produces artefact MACs and corrupt rows at a
similar rate. The corruption would then be *upstream* of the frame check — in
the node's own CSI buffer, the queue, or the callback — and every figure the
D0WD has ever contributed, including the 99.7 % / 95.7 % device-ID accuracies
and the entire July dataset, is in doubt in a way this repo has never
considered.

---

## 8. What this spec cannot settle

- **Whether the D0WD stays in the array.** §3's +3.87 % and (a)6 decide
  whether V2 has one record format or two, and a reduced D0WD profile would
  end identically-formatted simultaneous dual capture — the one condition that
  made every cross-receiver result of 21–22 August possible.
- **Whether the receiver term is a receiver property at all.** Every document
  this week calls it "the receiver term" and `docs/REFERENCE_CHOICE.md` §9.1
  points out that its §4.2 finding — nothing is common-mode between beacons at
  one receiver — makes that label a hypothesis rather than a description. V2's
  provenance (§2.9) makes the swap experiment recordable. It does not run it.
- **What `min_inlier` should be.** The shipped 0.6 accepts the same ambient
  device at 0.0 % on one receiver and 81 % on the other; 0.3 admits a measured
  bias of ±0.006 to ±0.009 rad/sc, 2.5–3.8 × `BETWEEN_UNIT_SD`
  (`docs/AMBIENT_SEPARATION.md` §3.3). Both are defensible and the choice
  changes the headline answer to the ambient question by a factor of 4.5. It
  is a host-side analysis decision and V2 does not make it.
- **Whether the S3 build's `stdout` goes to USB-Serial-JTAG, the UART pins, or
  both.** `firmware/csi_rx/sdkconfig` keeps `CONFIG_ESP_CONSOLE_UART_CUSTOM=y`
  on GPIO1/GPIO3 alongside `CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=y`,
  and `docs/CODE_INVENTORY.md` §4.4 S12 records that which one carries the
  stream "is recorded nowhere in this repo and was not tested". That
  `sdkconfig` is gitignored, so no artifact records the target switch either.
  V2's §2.7 instrumentation cannot be interpreted until this is known.
- **Whether `agc_gain` exists in a usable form on either target.** §2.5
  specifies the field on the strength of what it would settle, not on a
  verified SDK capability. `docs/S3_SFO_STEPS.md` §11 proposes
  "`esp_wifi_sta_get_rssi`-class PHY fields" without naming one that carries a
  gain index. If nothing usable is exposed, (b)1 has no instrument and must be
  attacked another way.
- **Whether any of this matters to the fingerprint.** §1 says it is not
  expected to. `docs/SEPARATION_SCALING.md` §6 records that the twin pair got
  worse, not better, past τ ≈ 200 s and that an experiment at longer averaging
  "has no reason to be run"; §5.2 says what is left is a different *feature*,
  not a better instrument. V2 makes the instrument honest. It does not make
  the twins separable.

---

Nothing in this document touches the occupancy pipeline (`pc/occ/`, amplitude
domain). Device-ID and occupancy figures must not be combined
(`CLAUDE.md`).

---

## 9. Appended 2026-08-22 — what the 14:44:24 occupancy test changes

Added after the fact by the pass that wrote `docs/OCCUPANCY_TEST_0822.md`.
Nothing above this line was edited. Every figure here is from that document,
which names the command that produces it.

The capture: `data/raw/d0wd_20260822_144424.csv` and
`s3_20260822_144424.csv`, 32.4 minutes, 242,733 and 280,621 rows, one operator
departure and one return, both located from the data.

**Strengthened, all still Must.**

- **§2.5.** The S3 produced a **310 s `noise_floor` excursion at
  t = 990–1300 s (+1.032 dB)** — longer than every one of the 129 excursions in
  the 6.5 h empty-room overnight (median 10 s, max 220 s) — and it **reverted**.
  It begins 70 s after a room transition that capture locates independently,
  from RSSI variability. That pairing is the control §7(b)1 lacked: an
  externally timed room event and a receiver-state excursion 70 s later, with
  nothing in the record able to say which is which.
- **§2.7.** ~389 STATUS records per node were emitted at 5 s and discarded
  (`pc/capture.py:123-128`) during a capture that raises two receiver-state
  questions STATUS would constrain.
- **§2.9.** Three provenance failures in one run: the operator's one firm
  timestamp (t = 1040 s ± 60 s) is **120 s from the return edge the data
  locates (920 ± 10 s)**, twice his own stated uncertainty; the departure time
  was never recorded and had to be recovered from the data; and the capture ran
  1,944.7 s when 1,200 were intended, with neither number in either file.
  **Part 3 should be widened**: the recorder needs an operator event-marker
  channel usable *during* a capture, not only a start sidecar and a stop
  marker. The `label` column already exists and `pc/capture.py:129` writes `""`
  into it on every row. Zero wire bytes.
- **§2.10.** Measured directly: a naive `line.split(",")` returns 140 fields on
  the 128-length rows and 268 on the 256-length rows and 13 on **none of the
  523,354 rows** in the two files. **Correction to the text above:**
  `grep -rn 'split(",", 128)' pc/` now matches **seven** files, not "these two
  files and no others". The two defective sites are unchanged;
  `pc/exp_poscontrol_0822.py:290,400` carries the corrected `< 128`; and
  `pc/exp_ambient_separation.py:358`, `pc/exp_reference_choice.py:343` and
  `pc/exp_separation_scaling.py:232` use the broken form **deliberately**, as a
  `naive_dropped` counter. The substantive claim stands; the grep count in
  §2.10 is stale and should name the files rather than count them.
- **§2.1.** A third file pair with the same asymmetry: 15 corrupt rows on the
  d0wd, **0** on the S3; 12 of the 15 carry an impossible `noise_floor`. Per
  byte 7.14e-8 against the overnight's 5.61e-8, ratio 1.27 — one data point for
  §7(a)7, not a rate test.
- **§4.4.** Third capture, third confirmation: the d0wd reads −97 on
  **242,718 of 242,718** clean rows with **zero** transitions.
- **§5.3.** Stays out of scope, more firmly: the d0wd's `C < 0.5` rate is
  0.432 % on B3 (against 2.604 % overnight) and **0.004 % of *accepted*
  d0wd/B3 frames**.

**Weakened.**

- **§4.1** is **weakened as a per-frame flag and strengthened as a cell-health
  monitor**, and its framing should change accordingly. On 523,068 beacon
  frames, `C < 0.5` fires on **0.000–0.268 % of accepted frames and
  0.943–34.180 % of rejected frames in 6 of 6 cells** — it is very nearly
  redundant with the shipped `inlier_ratio >= 0.6` gate (`dsp.py:164,173`).
  Its largest rate, **28.449 %, is on s3/B2** — on the board §7(a)1 shows has
  **no dead subcarrier in 7 of 7 chunks** — so it is **not** measuring the
  branch defect `docs/UNWRAP_DEFECT.md` §2 identifies as its trigger. It is a
  fit-quality statistic. Its recall / false-positive figures must not be quoted
  as branch-defect-specific. It stays a **Should**, and §4.1's own conclusion —
  not a node requirement, the record carries nothing extra — is confirmed.
- **§4.3** is sharpened rather than weakened, and now has a **beacon** example
  instead of only ambient ones: s3/B2 emitted **145 windows from 55,124
  frames**, and in its last 200 s accepted 2.23 % of ~3,800 frames — about one
  window per 200 s while the radio delivered 19 frames/s.

**Untouched.** §2.2 (0 u16 `dropped` wraps in 1,944.7 s; at 5.398 drops/s a u16
wraps in 12,141 s), §2.3 (corroborated on a third pair: 1 u32 wrap on the
d0wd, 0 on the S3, **0** true backward steps, node clock within 0.14 s of host
over 1,944.7 s), §2.4, §2.6, §2.8, §2.11 (**no 384-length frame exists in
either file**, so the clamp cannot have fired), §4.2, §4.5, §4.6, §5.1, §5.2,
§5.4, §6.

One observation touching §2.6 / §7(b)3 without testing either: the S3 dropped
**5.398 /s here against 26.83 /s overnight** — a loss fraction of **3.6 %
against 14.906 %** — between two sessions the operator states were physically
identical. §7(b)3's null is neither confirmed nor killed, and the **overnight
remains the file to test it on**.

**Nothing in §7 moves to Must.** §7(a)1's residue gains a reason to be run
against *this* capture rather than the overnight (it produced the first S3 cell
in the repo with a large coherence flag rate); §7(a)7 gains one data point;
§7(b)1 gains a candidate event with an independently timed external cause and
still has no instrument.

**One item is proposed for §7(a).**

> **(a)8 — Does the marginal cell have a pattern, or does it move at random?**
> Whole-run reject rate, three dual captures: 08-21 **B3/s3 43.54 %**;
> overnight **B3/d0wd 58.814 %**; 14:44 **B2/s3 83.101 %**, with B3/d0wd
> falling to **6.239 %** in the same eight hours. Three sessions, three
> different marginal cells — it moves between boards *and* between beacons.
> The position swap that six documents call outstanding is motivated by "the
> d0wd reads differently"; this says the marginal cell is neither a board
> property nor a beacon property. **Check:** compute per-cell reject rate and
> median `inlier_ratio` for every dual capture in `data/raw/` and test whether
> the marginal cell tracks RSSI, the beacon, the board, or nothing. Runs
> against data already on disk; no new capture.

**One caution for §1.** V2 exists to make instrument defects self-reporting.
That capture measures how large a *room* confound is on the quantities V2 will
be read through: **a person absent for 135 s moves a marginal cell's SFO by
7.75 × `BETWEEN_UNIT_SD` and one link's RSSI by 6.7 dB** — against the 08:55
positive control's 22.83 × and 3.69 dB. Any V2 experiment reading `agc_gain`
against a step in RSSI or SFO needs room state recorded at better than
one-minute resolution, or the instrument and the occupant are the same
observation. That is an argument for §2.9's event-marker channel and for
nothing else.

Nothing in this appended section touches the occupancy pipeline (`pc/occ/`).
`docs/OCCUPANCY_TEST_0822.md` is a device-ID-domain analysis of an
occupancy-motivated capture; its figures must not be combined with `pc/occ/`
figures (`CLAUDE.md`).
