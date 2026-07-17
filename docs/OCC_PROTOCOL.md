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
- **Both cats OUT of the sensed room, door closed**, for every `empty`
  and `still` segment. A cat near a beacon during `empty` poisons the
  false-alarm number; a cat in your lap during `still` confounds the
  breathing rate (cats: ~20-30 breaths/min, humans: 12-20).
- Household truth notes: write down where the family actually is
  during the session (which rooms), and anything known about neighbor
  activity. The array's null is "no occupant in the *sensed* room" —
  people elsewhere in the house (and, weakly, close neighbors beyond
  an exterior wall near a beacon) are potential through-wall sources,
  and the notes are what turns an odd blip into a data point instead
  of a mystery.

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
| 7 | 3 min | put ONE cat in the room, human leaves | press `5` (label `cat`) on the way out |
| 8 | 3 min | swap to the other cat if it cooperates | stay on `5`, note which cat in session notes |
| 9 | — | return, press `q` to stop | |

Use `--labels empty,walk,still,out,cat` for this script. The cat
segments measure **pet immunity** — whether a home-security deployment
can tell a cat from an intruder. Cats won't follow scripts; whatever
the cat actually does (sleeps, prowls, parkours) is the honest test,
just note it. Expected physics: much smaller RCS low to the ground →
weaker motion response; if a sleeping cat shows a respiration line it
should sit at 20-30 bpm, outside the human 12-20 band — rate is a
discriminator, not just presence.

Repeat the whole cycle a second time if patience allows — two cycles
separate "detector works" from "detector got lucky".

**Through-wall source hunt (optional, high value):** the overnight
data shows a below-threshold 10 bpm breather on B1 (03:52-04:08).
Candidates: son sleeping in an adjacent room, or (much less likely,
needs an exterior-wall path near a beacon) a neighbor. To settle it:
run a 5-min capture labeled `wall-sleeper` while your son is asleep
and you know it, with the sensed room empty and cats excluded — if
the same weak consensus line appears, the array is seeing through the
partition wall, which is worth knowing for both the security use case
and the privacy footprint.

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
- `cat` motion-flagged % and breathing-flagged % + rate — the pet
  immunity numbers. A cat that triggers motion like a human walk is a
  finding to report, not to tune away silently.

## Notes

- Fans / HVAC: if a fan runs during `empty` and the breathing scan
  flags it, that is a *real* finding (in-band mechanical modulation),
  not a bug to hide. Note appliance state in the session notes.
- Don't trust a session whose CSV mtime stopped advancing mid-run
  (dead capture process — the 14-hour lesson).
