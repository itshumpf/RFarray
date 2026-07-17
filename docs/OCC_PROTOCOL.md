# Scripted Ground-Truth Session Protocol (Phase 3 occupancy)

The occupancy detectors (`pc/occ/`) can only report *honest* detection
and false-alarm rates against labeled truth. Assumed labels ("the room
was probably empty overnight") are evidence, not measurement. This is
the ~20-minute scripted session that produces real numbers.

## Setup

- All three beacons powered, collector on COM3, calibration DONE
  (`python pc\field_diag.py COM3` — expect CAL DONE, ~140 fps aggregate).
- Run from a laptop or start/stop at the PC — but note that *you* are
  the test subject: time at the keyboard is labeled `still` at best,
  not `empty`.

## Session script

```
python pc\occ_capture.py COM3 --labels empty,walk,still,out
```

| step | duration | action | key |
|---|---|---|---|
| 1 | 3 min | leave the room entirely, room empty | press `1`, walk out (first ~15 s of `empty` will contain your exit — that's fine, the scorer uses interval interiors) |
| 2 | 1 min | walk a defined path through the room (door -> far corner -> desk -> door) | press `2` on entry |
| 3 | 3 min | sit motionless in a chair, normal breathing, no phone | press `3` when seated |
| 4 | 1 min | walk again, different path | press `2` |
| 5 | 3 min | sit motionless in a *different* spot | press `3` |
| 6 | 3 min | leave again, room empty | press `1` on the way out |
| 7 | — | return, press `q` to stop | |

Repeat the whole cycle a second time if patience allows — two cycles
separate "detector works" from "detector got lucky".

For **zone calibration**, add walk segments labeled per location
(`--labels empty,walk-door,walk-window,still-desk,...`) — each labeled
walk maps a cross-link profile cluster to a place.

## Scoring

```
python pc\occ_offline.py data\raw\occ_<ts>.csv --calib <empty-room-or-overnight csv>
```

The label-scoring section reports, per label, the fraction of time the
motion and breathing detectors flagged. The numbers that matter:

- `empty` motion-flagged % = **false-alarm rate** (want ~0)
- `walk` motion-flagged % = **motion detection rate**
- `still` breathing-flagged % = **still-presence detection rate**
- `still` motion-flagged % — high values mean fidgeting or an
  over-sensitive threshold; judge against how still you actually were

## Notes

- Fans / HVAC: if a fan runs during `empty` and the breathing scan
  flags it, that is a *real* finding (in-band mechanical modulation),
  not a bug to hide. Note appliance state in the session notes.
- Don't trust a session whose CSV mtime stopped advancing mid-run
  (dead capture process — the 14-hour lesson).
