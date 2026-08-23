# V2_READY — the ordered plan for the V2 build

**Date:** 2026-08-23 · **Type:** build plan and readiness audit. No firmware
was written, built or flashed by this pass. Read-only on `data/raw/` and
`firmware/`; no serial port was opened; nothing was staged, committed or
pushed. Three files in the repo were written: this one, the two marked
sections of `docs/V2_SPEC.md`, and `pc/exp_v2_pre_checks_0823.py`.

**A capture was running on COM6 and COM12 throughout.** Every reader used here
drops a final line with no trailing newline and reports the count.
`data/raw/d0wd_20260823_014740.csv` and `s3_20260823_014740.csv` grew during
the pass and were treated as live: the d0wd file read **99,497,299 B /
114,373 rows** on one scan and **296,244,117 B** at `stat` an hour later; the
s3 file read 115,680,379 B and then 355,139,912 B. No figure below rests on
either. Nothing in `data/raw/` was modified, renamed or deleted.

`docs/V2_SPEC.md` is the specification. This file is the order to do it in,
what blocks what, and the list of decisions that have to be answered before a
line of it can be written. It does not restate the spec.

---

## 0. The four §7(a) pre-V2 checks — outcomes

All four are now run and answered. The measurements, tables and commands are
in `docs/V2_SPEC.md` §7(a), "Appended 2026-08-23". One line each:

| | outcome | consequence for tomorrow |
|---|---|---|
| **(a)3** tail-drop bias | **Null, bounded at 0.13 × `BETWEEN_UNIT_SD`**, sign disagreeing across the three beacons, on all 3,564,005 rows of `s3_20260822_023034.csv` | §2.6 stays, demoted from discovery to cheap confirmation. Does **not** settle §7(b)3 — the proxy cannot see occupancy below overflow |
| **(a)4** does the dead bin predate July | **Yes — `k = +1` = 3.00 counts from 2026-07-12, in 45 of 45 files**, and on **two physically distinct receivers**, absent on the S3 in 6 of 6 | §2.8 strengthened. A per-board hardware fault now has to explain the same value on two boards; `first_word_invalid` is the better candidate |
| **(a)6** can the D0WD carry the V2 record | **Yes. Worst 60 s window in three months, at 295 B/frame, is 92.4 % of 46,080 B/s** | **One record format, not two.** §8's first bullet resolves. Budget 3.73 % more D0WD drops as the worst case |
| **(a)7** is the corrupt-row rate a link BER | **Yes within the saturated D0WD population** (χ² = 7.08 on 7 dof, λ = 5.905e−8/file byte); **no across the dataset** — era A is 0 in 3.115 GB where λ predicts 184 | §2.1 justified. §7(b)4's kill condition needs restating (see §5 below). One new §7(a) residue, one capture, no reflash |

**(a)1, (a)2, (a)5 and (a)8 were not touched by this pass** and remain as
`docs/V2_SPEC.md` leaves them. (a)5 still needs hardware and is now more
valuable than it was — see §4.

---

## 1. Decisions that must be answered before code starts

Each of these will stop a person mid-file. They are ordered by what blocks the
most. §2.10's base64 question is **D3**; the rest were found by reading the
spec as an implementer.

### Blocking the wire format — answer these first

**D1. Which CRC-16?** §2.1 says "a CRC-16 over every byte after the magic" and
names no variant. CRC-16/CCITT-FALSE, CRC-16/XMODEM, CRC-16/MODBUS and
CRC-16/ARC differ in polynomial, initial value, reflection and final XOR, and
a node and a host that pick differently will reject every frame with no
diagnostic. Two sub-questions come with it: does the checksum cover the two
magic bytes (V1's XOR does not — `telemetry.c:33-35` starts at index 2), and
is the two-byte value little-endian on the wire like every other field?
*Depends on it:* `firmware/common/telemetry/telemetry.c`, the new host parser,
and the shared test vector that proves they agree. **Nothing else can be
written until this is a named variant.**

**D2. `boot_ts_us` u64, or u32 + a u8 epoch counter?** §2.3 says the epoch
variant "is the cheaper alternative and is acceptable". §3's table then fixes
u64, a 17-byte header and 295 B/frame, and §3, §5.4, §6 and §7(a)6 all do
arithmetic on 295. The epoch variant gives a 14-byte header and **292 B**, and
+2.82 % rather than +3.87 %. Both are defensible; they are not both in the
spec. *Depends on it:* the header struct, `protocol.py`'s unpack format, every
frame-size figure, and (a)6's margin.

**D3. §2.10 — base64 payload, or a byte offset into a binary sidecar?**
The spec says explicitly it does not choose. base64 is +33 % on disk and
single-file; the sidecar is free on disk and adds a file to keep in step with
the CSV, which §2.7 part 1 and §2.9 part 2 are already adding two of. *Depends
on it:* `pc/capture.py`, and **every reader of `csi_data`** — `rff_offline.py:203`,
`occ/ingest.py:141-151`, `node_census.py:52,70` and roughly twenty `pc/exp_*.py`.
Not a wire-format decision, so it can be deferred past D1/D2, but not past the
first line of `capture.py`.

**D4. What is `flags` bit 2, `cal_gate_open`, for?** It appears in §3's table
and in no §2 subsection, with no evidence cited. As the firmware stands it
cannot vary: `firmware/csi_rx/main/main.c:328` wraps `tlm_send_csi`
(`:329-330`) in `if (cal_gate_open())`, so a frame that reaches the host was
emitted with the gate open and the bit reads 1 on every record, forever. Either the gate stops
suppressing emission and the bit starts carrying information, or the bit is
dropped and bit 2 joins the reserved range. Also: `cal_state` is a three-valued
enum (`protocol.py:39`, `CALIBRATING / DONE / BYPASS`) and one bit cannot carry
it. *Depends on it:* the `flags` byte definition, i.e. §2.8 and §2.11 as well.

**D5. Where does `csi_truncated` get set?** §2.11 cites
`telemetry.c:51-52` as the clamp. That clamp cannot fire from `csi_rx`: the
queue clamps first, at `firmware/csi_rx/main/main.c:276`
(`s.len = info->len > CSI_BUF_MAX ? CSI_BUF_MAX : info->len`), so
`telemetry.c` always receives a length already ≤ 384. The bit has to be set at
the queue — and `csi_sample_t` (`main.c:157-166`) has no field to carry it to
the drain task. *Depends on it:* the queue struct, which is also what D6 and
D7 want to change.

### Blocking the node

**D6. What `seq` goes on a frame from a source that has no ESP-NOW packet?**
§2.4 replaces the node-global `s_latest_seq` with "a small per-source table
keyed on the transmitting MAC". `s_latest_seq` is written only from the
ESP-NOW receive callback (`main.c:251`), and `RFF_PROMISCUOUS` is **1**
(`main.c:47`), so CSI fires for every decodable frame on the channel — and
ambient sources send no ESP-NOW packet at all and therefore have no counter.
Today they silently inherit whichever beacon transmitted last, which is the
bug. Under §2.4 they need a defined value: 0, a sentinel, or a `flags` bit
saying "no source cadence". `docs/AMBIENT_SEPARATION.md` is entirely about
these sources. *Also decide:* table size and eviction policy, and what `seq`
a source gets on its first frame or after eviction.

**D7. Is §2.4's table the table that already exists?** The working tree
already has one: `s_macs[MAC_TABLE_MAX]` with `MAC_TABLE_MAX 24`, beacons
pinned to reserved slots 0–2 (`main.c:145-234`). But it is filled by
`record_source()` in the **drain task** (called at `main.c:325`) and its
comment at
`main.c:194` says "Writer: csi_drain_task only. Reader: display_task only.
No lock." §2.4's `seq` must be stamped in the **CSI callback** (`main.c:270`),
before the queue. Reusing `s_macs` puts a second writer on a deliberately
lock-free structure. Two tables, or one table with a lock, or one table with
the writer moved — pick one before touching `main.c`.

**D8. `q_occupancy` — measured before or after the enqueue, and what is the
censoring?** §2.6 says "the queue depth at the moment the sample was
enqueued". `uxQueueMessagesWaiting()` before `xQueueSend` gives 0–63; after
gives 1–64. Either fits u8. The consequence is that **a frame that is dropped
produces no record at all**, so the field is censored at exactly the end
§7(b)3 cares about: full-queue events are the ones that are never observed.
Say which convention is used in the field's own definition, because the test
is a monotone dependence and the censoring is at the interesting end.

**D9. Does `agc_gain` exist?** §8 already flags this — §2.5 specifies the
field "on the strength of what it would settle, not on a verified SDK
capability", and `docs/S3_SFO_STEPS.md` §11 proposes
"`esp_wifi_sta_get_rssi`-class PHY fields" without naming one that carries a
gain index. An implementer cannot write the line. Needed: the IDF call, per
target, or a stated sentinel for "not available" so the byte is at least
reserved. §4.4 records that the D0WD may not expose one even if the S3 does.
**This is the item that most deserves the first twenty minutes of hardware
time** — see §4, phase H1.

**D10. `s_dropped` has to widen too.** §2.2 widens the per-frame `dropped`
u16 → u32 and §3 keeps STATUS's `drop_total` at its V1 u32 width. Both are
fed from `static volatile uint16_t s_dropped` (`main.c:170`, read at `:330`
and `:347`). Widening the wire field without widening the counter fixes
nothing. Trivial, and easy to miss because §2.2's requirement is phrased
about the record.

### Blocking the recorder

**D11. The STATUS sidecar's shape.** §2.7 part 1 says "a second file per
session, one row per record, with the same `pc_time_us` clock". Not specified:
the filename convention (`pc/capture.py:103` names CSI files
`f"{node.name}_{ts}.csv"`), the header row, whether the two nodes share one
file or get one each, and what the recorder does when a STATUS record arrives
before the first CSI row.

**D12. The provenance sidecar's format.** §2.9 part 2 requires
"wall-clock start, per-node `node_id` / port / link type / firmware version /
`env_id`, and a free-text position record per node and per beacon", written
before the first row. No format, no filename, no schema, and no statement of
what the recorder does when the operator declines to type the free text — the
one field that cannot be filled automatically is the one the six blocked
position-swap documents actually need.

**D13. The event-marker channel: in or out?** §9 says §2.9 part 3 "should be
widened" to an operator event-marker channel usable *during* a capture, via
the existing `label` column, zero wire bytes. It is written as a proposal, not
a requirement, and §2.9 itself was not edited. Decide, because it is the one
item with a hard interaction: `pc/capture.py` owns the terminal for its TUI
and its only input handling is the `KeyboardInterrupt` at `:193-196`. A
keypress channel is a real change to the reader loop, not a column write.
§9's own closing caution — a person absent 135 s moves a marginal cell's SFO
by 7.75 σ — is the argument for it.

**D14. What does a recorder do with `env_id == 0`?** §2.9 part 1 says it
"warns". Every row of every file in `data/raw/` reads 0, and the analysis
scripts screen on `env_id == 0` as a **validity** test
(`docs/REFERENCE_CHOICE.md` §1.2, and route 2 of the corrupt-row screen used
throughout `docs/OVERNIGHT_2026-08-22.md` §1 and reproduced in
`pc/exp_v2_pre_checks_0823.py`). The moment V2 makes `env_id` non-zero, that
screen inverts and starts flagging every clean row as corrupt. **This
breakage is not in §6's table and it is a silent one.** Decide whether the
screen becomes "`env_id` equals the file's own mode", and whether the recorder
warns or refuses.

### Bookkeeping errors found while reading

**D15. §3's STATUS arithmetic is wrong.** The seven added fields are
`resync_bytes u32` (4) + `crc_fail u32` (4) + `q_high_water u8` (1) +
`agc_gain u8` (1) + `emit_ns_accum u64` (8) + `emit_count u32` (4) +
`display_enabled u8` (1) = **23 B, not 22**. V2 STATUS is **27 + 23 = 50 B**,
not 49, and the cost at one record per 5 s is **10.0 B/s**, not 9.8. With
§4.6's optional `filter_mac[6]` + `promiscuous u8` it is 57 B.

**D16. The name "V2" is already taken.** `pc/rff/protocol.py:26-30` calls the
*current* wire format v2 — `MAGIC_V2 = b"\xc5\x52"`, `HDR_V2 = 12`,
`_try_v2()`. The spec's V2 is the third generation (§6 says so: "needs a third
parser"). Fix the naming in the same commit that adds the parser, or every
later reference to "v2" is ambiguous. Related and minor: `C5 53` shares its
first byte with both existing magics, so a resync landing inside a payload now
has three magics to false-match instead of two.

**D17. Which "Should"s are in scope for this build?** §4 is ordered by
evidence strength and never says which of §4.1–§4.6 are being done. §4.5 is
self-contradictory about its own status: it is filed under Should "only
because it is not demonstrated to be broken on the flashed S3", then states
"it becomes a Must the moment §2.9 requires `env_id` to be set per
deployment" — and §2.9 does require exactly that. So §4.5 is a Must by its own
argument and is filed as a Should.

**D18. Is `pc/rff/` frozen, or only `pc/rff/dsp.py`?** §5.5 is titled
"Anything that changes the SFO estimator" and its prohibition is on `dsp.py`.
§4.1 recommends shipping the branch-coherence detector "in `pc/rff/`", and §9
then weakens it from a per-frame flag to a cell-health monitor. Decide whether
that lands tomorrow, in `pc/rff/` but outside `dsp.py`, or waits. See §3 below
for the newly recorded reason `dsp.py` must not move.

---

## 2. Citations in the spec that no longer point where they say

`docs/V2_SPEC.md` was written **2026-08-22 20:52:05**. Two files it cites
heavily changed after that, in the working tree, uncommitted.

**`firmware/csi_rx/main/main.c` — 328 lines at git HEAD, 677 in the working
tree, mtime 2026-08-22 23:42:19.** That is 2 h 50 min after the spec. **Every
`csi_rx/main/main.c:NN` line number in the spec is stale.** The facts survive;
the addresses do not. Current addresses for what the spec cites:

| spec cites | what it is | current line |
|---|---|---|
| `:45` | `CSI_BUF_MAX 384` | **`:48`** |
| `:46` | `QUEUE_DEPTH 64` | **`:49`** |
| `:59` | `STATUS_PERIOD_MS 5000` | **`:62`** |
| `:68` | `TX_FILTER_MAC` all-zero in `csi_rx` | **`:153`** |
| `:84` | `static volatile uint32_t s_latest_seq` | **`:169`** |
| `:85` | `static volatile uint16_t s_dropped` | **`:170`** |
| `:101-103` | ESP-NOW callback writes `s_latest_seq` | **`:251`** |
| `:122` | `s.seq = s_latest_seq` on every CSI sample | **`:270`** |
| `:128` | the queue-side `csi_len` clamp | **`:276`** |
| `:131-133` | `xQueueSend` fails → `s_dropped++` | **`:279-280`** |
| `:187-205` | `status_task` | **from `:336`**, `drop_total = s_dropped` at `:347` |
| `:190` | the `STATUS_PERIOD_MS` delay | **`:339`** |
| `:208-249` | `display_task` | **from `:427`** |
| `:302-307` | `oled_init()` gate on creating `display_task` | **`:651-652`** |
| `:314` | `xQueueCreate(QUEUE_DEPTH, …)` | **`:663`** |
| `:321` | `csi_init()` | **`:670`** |

Three substantive things the rewrite changed that the spec could not know:

- A **per-source table already exists** — `s_macs`, `MAC_TABLE_MAX 24`, three
  reserved beacon slots (`:145-233`). It is the display's, not §2.4's. See D7.
- The frames the host receives are **gated on `cal_gate_open()`** at `:330`.
  See D4.
- `RFF_PROMISCUOUS` is **1** in `csi_rx` (`:47`), so the ambient population
  §2.4 and §2.10 both discuss is on the wire by default. See D6.

**`firmware/csi_rx/sdkconfig` — mtime 2026-08-22 22:17:16, 1 h 25 min after
the spec, and gitignored** (`.gitignore:3`). The console moved:

| | spec's reading | the file now |
|---|---|---|
| `:1298` | `CONFIG_ESP_CONSOLE_UART_CUSTOM=y` | **`CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`** |
| `:1301` | `CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=y` | **`CONFIG_ESP_CONSOLE_SECONDARY_NONE=y`** |
| `:1303` | `CONFIG_ESP_CONSOLE_UART=y`, `UART_NUM=0` | **`CONFIG_ESP_CONSOLE_UART_NUM=-1`** |

The old file is preserved in the tree as
`firmware/csi_rx/sdkconfig.uart-backup` (mtime 2026-08-21 12:20) and the new
one as `sdkconfig.usbjtag-working` (byte-identical to the live `sdkconfig`,
md5 `c1eef476…`). A byte-identical copy also sits at the **repo root** as
`/sdkconfig`, untracked and not ignored.

**What that invalidates.** §7(a)2's "[settled 2026-08-22 —
`docs/S3_LINK_PATH.md`]" block, §5.4's second correction, §4.5 and §8's fourth
bullet all read against a UART0-primary console. `docs/DISPLAY_LIVE_0822.md`
§5.1 measured the S3 at **96.53 fps** after the move — the 154 fps ceiling is
gone, and the S3 is now *slower* than the D0WD at 132.17 fps, with **zero
drops**, i.e. it is hearing fewer frames rather than draining fewer. The
162.25 fps UART budget no longer describes the flashed build. **§7(a)2 is not
re-opened by this pass and it is not settled either; it is asked of a
different firmware than the one that settled it.** Note the D0WD build is
unaffected — `sdkconfig.defaults:9-12` keeps its UART0 console, which is why
(a)6's 46,080 B/s budget is still the right yardstick for the D0WD and only
for the D0WD.

---

## 3. One thing recorded in `docs/V2_SPEC.md` §5.5 that changes how to test

The reproducibility §5.5 relies on holds **only because every one of those
five scripts replays from the start of a file.** `FrameEstimator` carries a
per-instance RNG (`pc/rff/dsp.py:118`) which `ransac_line` advances twice per
fitted frame (`:85-86`, `:132`), so the hypothesis set at frame N depends on
how many frames preceded N. Measured, index-aligned, on 60,000 frames: the
gate decision flips on **1.49 %** of frames, **68.5 %** of jointly-accepted
frames get a different slope (median 0.30 σ), and **99.4 %** of emitted
64-frame window medians differ (median 0.29 σ, max **5.13 σ**). The replay
origin in the shipped pipeline is the **file** —
`pc/rff_offline.py:238-239` re-creates the estimators inside the per-path
loop.

**The practical consequence for tomorrow:** when you re-derive a published
figure with the new parser, expect a disagreement of order 10⁻⁴ rad/sc and do
not read it as a regression. Verify the parser against the **decoded byte
vector**, not against a slope. Full detail and the numbers are in
`docs/V2_SPEC.md` §5.5.

---

## 4. The plan

Hardware is available; nothing is blocked on a running experiment. The order
below is by dependency, not by preference.

### D0 — before code (no hardware, ~30 min)

0.1 Answer **D1, D2, D4, D5** — the four that block the wire format. D1 and
D2 are the two that nothing can proceed past.
0.2 Answer **D6, D7, D8, D10** — the four that block the node.
0.3 Decide **D3, D11, D12, D13, D14** — the recorder set. D3 can lag D1/D2 by
an hour; the rest cannot lag the first line of `capture.py`.
0.4 Braeden's call on the working tree (§6). Nothing below depends on it, and
everything below adds to the pile.

### H1 — first, and it is hardware (≈30 min, one flash, radio off)

**Probe whether `agc_gain` exists before the record layout is frozen (D9).**
A throwaway build that calls whatever gain/PHY-state accessor the IDF exposes
on each target and logs it once a second. This is 30 minutes and it decides
whether §2.5's byte carries anything, whether §7(b)1 has an instrument at all,
and whether §4.4's worry about the D0WD is real. Doing it after the layout is
frozen means either a reserved dead byte or a second format revision.
**Everything in P2 depends on the answer; nothing in P1 does.**

### P1 — host side, no hardware, fully testable today

Can all be written and tested with no board attached, against synthetic frames
and against the V1 files already on disk.

1.1 **CRC-16 (D1), both sides, one shared test vector.** A C function and a
Python function that agree on a fixed byte string committed as a test. Write
the test first; it is the only artefact that proves D1 was answered the same
way twice.
1.2 **The third parser in `pc/rff/protocol.py` (D16).** `MAGIC_V3` /
`_try_v3` / `HDR_V3`; the `length - 15` derivation at `:123` becomes
`length - 20`; the magic dispatch at `:163-171` takes a third branch.
`pc/test_rff_synth.py` already exists as the place for the round-trip test.
1.3 **V1/V2/V3 coexistence.** Feed the parser a byte stream with all three
magics interleaved and confirm each decodes and that a resync inside a payload
does not false-match the new magic more often than the old ones. Tonight's
capture is the input for this — see §5.
1.4 **`pc/capture.py`:** the `csi_data` write (D3), the STATUS sidecar (D11,
removing the `continue` at `:123-128`), the provenance sidecar (D12), the stop
marker, and the event-marker channel if D13 says yes.
1.5 **`pc/throughput_test.py:129` and `pc/diagnose.py:217`.** The first is a
literal `CSI_FRAME_BYTES = 12 + 15 + 256 + 1  # 284`. The second is **not** a
hard-coded 284, as §6's table implies — it is
`return HDR_V2 + (rec["len"] + 15) + 1`, which hard-codes `HDR_V2` and the
15-byte payload prefix and so breaks for the same reason by a different route.
One line each, and they are the two tools whose output would otherwise be
quietly wrong.
1.6 **The `env_id` screen (D14).** Whatever D14 decides, change it in the
corrupt-row screen *at the same time* as the recorder, in the same commit.
This is the one item in P1 that breaks existing analysis if it lands alone.

*Verification for P1:* re-parse `data/raw/s3_20260822_023034.csv` with the new
parser and confirm the decoded byte vectors are identical to the old path, row
for row. Compare vectors, not slopes (§3).

### P2 — firmware, needs a flash. Depends on D0, H1 and 1.1

2.1 `firmware/common/telemetry/` — the V3 header and payload, CRC-16 replacing
the XOR at `telemetry.c:33-39`, the STATUS struct's seven new fields (**50 B**,
D15).
2.2 `firmware/csi_rx/main/main.c` — `s_dropped` u16 → u32 (D10), the per-source
`seq` table (D6, D7), `q_occupancy` on the queue path (D8), `first_word_invalid`
and `csi_truncated` into a `flags` byte carried through `csi_sample_t` (D5),
`agc_gain` if H1 found one (D9).
2.3 `emit_ns_accum` / `emit_count` and the run-time `display_task` disable
(§2.7 parts 2 and 3). The disable needs §4.5's console port on the S3, which
D17 should have promoted to a Must.
2.4 Flash **one** node first — the D0WD, because (a)6 says it is the one with
no margin and it is the one whose console has not moved.

### P3 — verification capture. Depends on P1 and P2

3.1 A short dual capture with **`env_id` set non-zero on both nodes** — that
is §2.9's whole point and it is also the first real test of §4.5's console.
3.2 Confirm on the file: STATUS rows on disk, `q_occupancy` varying,
`dropped` past 65,535 without a wrap, `agc_gain` present or explicitly
sentinel, CRC failures counted rather than silent.
3.3 Re-run `pc/exp_v2_pre_checks_0823.py a6b` against the V2 D0WD file. It
reports max-60 s sustained rate directly, so it will say within one capture
whether the 3.73 % frame-rate cost (a)6 bounds actually landed.

### P4 — the two things hardware availability makes cheap, and neither is V2

4.1 **(a)5, the throughput run.** `firmware/s3_throughput/` builds and has
never been flashed (`README.md:17`). It is the measurement that would separate
(a)6's per-byte from per-frame ceiling, and it takes the S3 off-air for
minutes.
4.2 **(a)7's new residue** — one hour of D0WD capture at under ~60 % of the
budget, counting corrupt rows per byte against λ = 5.905e−8. No reflash of the
receiver; only a reduced offered load. This is the check that would say
whether the CRC in §2.1 is fixing a link or a load.

---

## 5. Tonight's capture, as a test input

Tonight is the **last V1 capture** and it is deliberately variable-heavy: the
receivers were remounted and co-located today, and an antenna is being
reoriented mid-run. Two consequences, and they point opposite ways.

**As a test input it is the best file available.** An event-rich V1 file with
a mid-run geometry change is exactly what P1's coexistence path (1.3) and the
new parser (1.2) should be stressed against — variable `csi_len` populations,
RSSI steps, and whatever the reorientation does to the corrupt-row rate. Use
it for 1.2, 1.3 and P1's verification step. **Do not analyse it for physics.**

**As a baseline it is now a discontinuity, and nothing records it.** Every
`docs/OVERNIGHT_2026-08-22.md`-era result rests on the operator-stated
condition "receiver positions unchanged from 2026-08-21 and **not** swapped"
(§0). That is no longer true after today's remount and co-location, and the
files will not say so: `env_id` reads 0, the `label` column is `""` on every
row (`pc/capture.py:129`), and there is no provenance sidecar. Any comparison
across 2026-08-22 → 2026-08-23 now has an unrecorded geometry change in it.
That is §2.9's argument, made by events rather than by reasoning, and it is
the reason D12 should not slip.

---

## 6. Working tree — reported, not touched

Nothing here was fixed, staged or committed. `git diff --cached` is empty.
Braeden commits his own work.

**The three named in `CLAUDE.md`, all confirmed as described:**

1. **`firmware/csi_tx/main/main.c` is a BLE diagnostic**, 70 lines, mtime
   **2026-07-22 18:50:49**, modified and uncommitted. It advertises as
   `"CSI-S3-ALIVE"` and its own header comment says "Restore the beacon from
   git / scratchpad `main_beacon_norate.c` after." **`main_beacon_norate.c`
   does not exist anywhere in the repo.** The production beacon is safe —
   `git show HEAD:firmware/csi_tx/main/main.c` is the ESP-NOW beacon with
   `SEND_INTERVAL_MS 10`, which is what §5.2 cites. What is uncommitted and
   single-copy is the **diagnostic**, along with
   `firmware/csi_tx/main/CMakeLists.txt` and
   `firmware/csi_tx/sdkconfig.defaults.s3`.

2. **`firmware/csi_cfo/main/main.c` carries the uncommitted 2026-08-02
   change**, mtime **2026-08-02 23:11:29**, +20/−8 against HEAD.
   `RFF_PROMISCUOUS 0` at **`:51`** and
   `TX_FILTER_MAC = {0xA4,0xF0,0x0F,0x77,0x91,0x20}` at **`:80`** — §4.6's two
   line numbers are still correct. The failure mode §4.6 describes is intact:
   `:126-128` returns early on a MAC mismatch *before* the queue, so a MAC
   change yields zero frames **and** zero drops, and `hal_rf_liveness_kick()`
   at `:186` is the reboot path.

3. **`pc/requirements.txt` omits pandas.** Four lines: `pyserial`, `numpy`,
   `matplotlib`, `rich`. `pc/heatmap.py:17` does `import pandas as pd`. Also
   confirmed: **scipy is imported by nothing** in `pc/`, so it is correctly
   absent.

**Larger than those three, and not in `CLAUDE.md`:**

4. **`firmware/csi_rx/main/main.c` — the production receiver — is 677 lines in
   the working tree against 328 at HEAD, uncommitted, mtime 2026-08-22
   23:42:19.** It is the build that produced
   `data/raw/s3_20260822_235739.csv` and `data/raw/*_20260823_*.csv`, and it
   is the only copy of a rewrite that roughly doubled the file: the OLED panel
   sequence, `display_task`, the `s_macs` source table and the beacon-cadence
   floor. It is also the file all of P2 edits.

5. **The console `sdkconfig` is gitignored and cannot be recovered from git.**
   `firmware/csi_rx/sdkconfig` is matched by `.gitignore:3`. The two hand-made
   backups beside it — `sdkconfig.uart-backup` and `sdkconfig.usbjtag-working`
   — are **not** matched by any ignore pattern and show as untracked, as does
   `firmware/csi_rx/sdkconfig.defaults.esp32s3`. So the config exists in three
   places in the tree and zero places in git.

6. **A stray byte-identical copy of that `sdkconfig` sits at the repo root**
   (`/sdkconfig`, 75,641 B, untracked, not ignored).

7. **Every document and analysis script of the last five weeks is untracked.**
   25 files under `docs/` including `V2_SPEC.md` itself, plus `CLAUDE.md`,
   `PROJECT_NOTES.md`, `.claude/`, `git-guard/`, `firmware/i2c_scan/`,
   `firmware/s3_throughput/`, and roughly 25 `pc/exp_*.py` and `pc/*.py`
   files. `data/raw/` and `*.csv` are ignored deliberately; none of the above
   is. Two stray fragments are in there too —
   `pc/exp_poscontrol_0822.py.head` and `.tail`.

8. **Modified and uncommitted, beyond the above:** `README.md`,
   `docs/HANDOFF.md`, `pc/heatmap.py`, `pc/rff_offline.py`,
   `firmware/csi_rx/main/CMakeLists.txt`, and 13 files under
   `data/fingerprints/`.

The last commit is `9780351 docs: household ground truth — cats, family,
neighbors`. Everything in items 4–8 postdates it.

---

## 7. Commands

Everything in §0 and §3 comes from one script,
`pc/exp_v2_pre_checks_0823.py`, read-only, cache outside the repo tree:

```
python pc\exp_v2_pre_checks_0823.py a4
python pc\exp_v2_pre_checks_0823.py a67
python pc\exp_v2_pre_checks_0823.py a6b
python pc\exp_v2_pre_checks_0823.py rng
python pc\exp_v2_pre_checks_0823.py a3p 0.0 0.2
python pc\exp_v2_pre_checks_0823.py a3p 0.2 0.5
python pc\exp_v2_pre_checks_0823.py a3p 0.5 0.8
python pc\exp_v2_pre_checks_0823.py a3p 0.8 1.0
python pc\exp_v2_pre_checks_0823.py a3
```

Section to subcommand: (a)3 → `a3p` ×4 then `a3`; (a)4 → `a4`; (a)6 → `a67`
and `a6b`; (a)7 → `a67`; §3 above and `V2_SPEC.md` §5.5 → `rng`. The `a3p`
parts are split only because each has to finish inside one run; the split is
declared in `V2_SPEC.md` §7(a)3 because it changes individual slopes.

Working-tree facts in §6 come from `git status --porcelain`,
`git show HEAD:<path> | wc -l`, `git check-ignore -v <path>`,
`git diff --stat <path>`, `stat -c'%y %s' <path>` and `md5sum`. Nothing in §6
was produced by a command that writes.

Not used: `pc/rff/dsp.py` was imported and never modified — mtime still
**2026-07-13 20:42:46**. No serial port was opened. `docs/DIRECTION.md` is not
cited here and describes nothing that is built.
