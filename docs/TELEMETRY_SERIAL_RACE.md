# TELEMETRY SERIAL RACE — two tasks, one unlocked stdout

**Written 2026-08-31, during the night-3 capture. Nothing was reflashed.**

Raised by an external review as P1. Verified here against the files rather
than accepted on description. It is real, it is in firmware that is running
right now, and the host silently absorbs it.

---

## 1. The defect

`emit()` — `firmware/common/telemetry/telemetry.c:37-40` — writes every frame
as **three separate `fwrite` calls followed by `fflush`**, with no lock:

```c
fwrite(hdr,     1, sizeof(hdr), stdout);
fwrite(payload, 1, len,         stdout);
fwrite(&cks,    1, 1,           stdout);
fflush(stdout);
```

Two FreeRTOS tasks reach that function on the same stream:

| task | priority | path | created |
|---|---:|---|---|
| `csi_drain_task` | 5 | `tlm_send_csi` → `emit` | `csi_rx/main/main.c:667` |
| `status_task` | 4 | `tlm_send_status` → `emit` | `csi_rx/main/main.c:668` |

**There is no mutex, semaphore or critical section anywhere in
`csi_rx/main/main.c` or `csi_cfo/main/main.c`.** A preemption between any two
of those `fwrite`s splices a STATUS frame into the middle of a CSI frame.

`csi_cfo` carries the identical pattern — same two tasks, same absence of a
lock.

## 2. The comments are the worse half

Two places in the tree assert the safety property that does not hold. Both
read as considered decisions rather than oversights, which is what makes them
dangerous — a later reader checks, finds a stated contract, and stops looking.

> `csi_rx/main/main.c:311` — *"Drain task: sole owner of stdout."*

It is not. `status_task` writes to the same stdout every `STATUS_PERIOD_MS`.

> `telemetry.c:47` — *"payload assembled in a static buffer: single-caller
> contract (one drain task) makes this safe and heap-free"*

There are two callers. The static buffer happens to survive anyway — 
`tlm_send_status` assembles into its own 27-byte stack array and never touches
`pl` — so the *buffer* claim is accidentally true while the *contract* it
rests on is false. **A correct conclusion resting on a wrong premise is not a
safe piece of code, it is a coincidence with a comment on it.**

## 3. What it costs, stated narrowly

The host recovers, and loses the frame without saying so.
`pc/rff/protocol.py:175-202`, in its own words:

> *"Corrupt frames cost one byte of resync."*

`decode_stream` scans for the next magic, and when a parse fails it simply does
not append a record. **No counter is incremented, no warning is emitted,
nothing is logged.** The frame leaves no trace of having existed.

**So: this costs coverage, not correctness.** A spliced frame is dropped
whole; it does not produce a surviving row with wrong values. Nothing in
`data/raw/` is corrupt because of this. What it can do is thin a capture by an
unknown amount.

**Do not confuse it with the `dropped` column.** That field is the firmware's
own queue-overflow counter, carried in the payload. It counts frames the node
knew it lost. This defect loses frames the node believed it had sent and the
host never records. The two are different quantities and the CSV only has the
first.

## 4. Never asked, not measured as zero

**Nothing in the pipeline can currently tell you whether this has ever
happened.** There is no resync counter on the host and no sequence-gap check
in `capture.py`. The honest statement is *not* "the splice is rare" — it is
**"the rate is unmeasured."**

That distinction is failure mode C in `.astory/ERROR_LOG.md`: an empty result
must say whether the data does not exist, could not be asked for, or was never
asked. This is the third.

**The cheapest way to find out costs no firmware change.** Every CSI frame
carries `seq`, and `seq` is already written to column 3 of every capture CSV.
Counting gaps per `(node, mac)` across the existing corpus would put a number
on it retrospectively — across all 87 captures, not just tonight. That is a
read-only query over data already on disk.

## 5. Fixes, either of which closes it

1. **One writer.** `status_task` stops calling `emit` and instead enqueues a
   STATUS event onto `s_csi_queue`; `csi_drain_task` emits everything. This
   makes the two existing comments true rather than deleting them.
2. **Lock the transaction.** A mutex taken before the first `fwrite` and given
   after the `fflush`, inside `emit()`, so every caller is covered without any
   caller having to know.

(1) matches the design the comments already describe and removes the shared
resource rather than guarding it. (2) is smaller and covers `csi_cfo` and any
future caller for free.

## 6. What must not happen next

- **Do not reflash during a capture.** `RECEIVER_DIVERGENCE_PREREG.md` §3
  requires night 3 to differ from night 2 in nothing the operator controls.
  Changing receiver firmware mid-series ends the series.
- **Do not fuse this with the d0wd/B3 divergence.** That is a stable slope
  offset measured on frames that parsed cleanly, held for six hours to battery
  death, and reproduced across five sampled windows. A splice drops a frame
  whole. **This defect cannot produce a wrong SFO value**, and it is not a
  candidate explanation for anything in `SEVEN_NIGHT_PREREG.md` §10.
- **Do not describe the splice rate as low** until §4's query has been run.
  Unmeasured is not small.

## 7. Status

Open. Firmware untouched. Fix belongs on a day with no capture running —
after the seven-night series ends, unless a measured splice rate turns out to
be high enough to threaten the series itself.
