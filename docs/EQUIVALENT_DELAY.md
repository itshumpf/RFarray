# Eight-night equivalent-delay findings

## Verdict

The eight paired nights contain **no evidence specific to an integer 20 MHz
sample-period STO lattice**. They do contain three persistent, receiver-local
B1 phase-ramp transitions of approximately 56--59 ns. Those transitions are
consistent with a link/receiver timing or propagation state, but this corpus
cannot identify them as STO.

## Scope and conversion

Every one of the 69,510,186 clean beacon-frame estimates in the completed
unwrap-free replay was streamed through the analysis. The phase ramp was only
re-expressed as equivalent delay:

```
tau_equiv = -slope / (2*pi*312500 Hz)
```

At 20 MHz, one sample is 50 ns and corresponds to 0.0981747704
rad/subcarrier. This conversion adds no predictive information and does not
separate SFO, STO/packet-detection delay, propagation delay, or linear channel
phase.

## Frame-level held-out lattice test

For each receiver/night/beacon series, the first chronological half fixed the
lattice origin and the second half was scored without refitting. The held-out
half contained 29,169,536 frames. Forty-six of 48 series were scoreable; B1 was
off air before the midpoint on both receivers on night 3.

| candidate spacing | median held-out occupancy | material multi-level series |
|---:|---:|---:|
| 40 ns | 91.07% | 0 / 46 |
| 45 ns | 92.35% | 0 / 46 |
| **50 ns** | **93.46%** | **0 / 46** |
| 55 ns | 94.40% | 0 / 46 |
| 60 ns | 95.17% | 0 / 46 |

The high occupancy is not sample quantization. Each link is narrowly stable
around one fitted value, so many arbitrary wide lattices fit it; the 55 and 60
ns controls fit better than the physical 50 ns candidate. No series occupies
two lattice levels with at least 5% of held-out frames in each.

The exact one-minute summaries give the same answer: 0 of 48 series has two
material 50 ns levels.

## Persistent transitions

Only three one-minute series contain a retained five-minute-before/five-minute-
after shift of at least 25 ns. All three affect B1, persist to the end of their
contiguous segment, and are reproduced by ordinary unwrapped OLS.

| night | observed link | minute | unwrap-free shift | OLS shift | simultaneous other receiver |
|---:|---|---:|---:|---:|---:|
| 3 | d0wd / B1 | 10 | -57.54 ns | -55.00 ns | -0.78 ns |
| 4 | d0wd / B1 | 346 | -55.79 ns | -53.26 ns | +0.20 ns |
| 8 | s3 / B1 | 351 | -58.76 ns | -58.44 ns | +1.12 ns |

Their contiguous post-transition durations are 20, 10, and 22 minutes. None
falls within the frozen +/-5 ns tolerance around a 50 ns multiple, none
replicates across receivers, and the other beacons on the affected receiver do
not show comparable shifts. All target frames are length 256 both before and
after the transitions.

This rules against a shared transmitter-clock change. It is compatible with a
receiver/link-local packet-detection or fractional-timing state, but equally
compatible with a change in the propagation/channel term. The CSI vectors do
not contain an independent timing observable that can choose between them.

## Alignment with SFO-only matchups

An exploratory follow-up enrolled a nearest-template classifier on the first
complete 5, 10, or 30 minutes of each receiver-night and classified every later
one-minute slope. This is deliberately simpler than the shipped discriminator:
it has no CFO, covariance model, or refusal state. Equivalent delay is merely
the slope expressed in nanoseconds.

Overall accuracy rose from 77% with five minutes of enrollment to 81% with ten
and 86% with thirty. For the ten-minute model, distance from the true beacon's
enrolled slope separated outcomes sharply:

| absolute deviation from own enrolled value | observations | correct |
|---:|---:|---:|
| <5 ns | 15,020 | 85.5% |
| 5--10 ns | 1,061 | 67.1% |
| 10--25 ns | 1,052 | 66.3% |
| 25--50 ns | 418 | 0.0% |
| >=50 ns | 21 | 0.0% |

This association is partly classifier geometry rather than an independent
causal result: the classifier chooses whichever enrolled value is closest.
Still, the event alignment shows exactly how the ~57 ns state changes act on
the identity decision.

- Night 3, d0wd/B1: median own-template deviation moved from 2.31 to 55.23 ns;
  the five-minute decisions changed from 5/5 B1 to 5/5 B3.
- Night 4, d0wd/B1: deviation moved from 44.0 to 11.8 ns. The 30-minute model
  changed from 2/5 B1 to 5/5 B1; shorter enrollment templates still called all
  five post-transition points B3.
- Night 8, s3/B1: deviation moved from 49.4 to 13.0 ns; decisions changed from
  5/5 B2 to 4/5 B1 and 1/5 B2 under every enrollment length.

Thus the repeated shift is not a one-way degradation. It can throw B1 out of
its enrolled SFO state or return it toward that state, depending on which side
of the transition was enrolled. That behavior is a direct example of why the
slope supports short-lived state matching but not durable transmitter identity.

## What follows

The defensible new hypothesis is: **B1 sometimes enters a receiver-local
equivalent-delay state about 57 ns away from its prior state.** A fresh test
should freeze that magnitude before capture, retain the CIR peak index that the
current replay computes but does not store, swap receiver positions, and add an
independent packet-timing observable if the ESP32 exposes one. Until then this
is a repeated exploratory pattern, not a measured STO mechanism.

## Reproduction

From the repository root:

```powershell
python share/analyze_equivalent_delay.py --multiscale share/deep_dive/multiscale --out share/deep_dive/equivalent_delay
python share/analyze_equivalent_delay_frames.py --replay share/deep_dive/full_arbiter_replay --out share/deep_dive/equivalent_delay
python share/compare_delay_sfo_matches.py --minute share/deep_dive/multiscale --jumps share/deep_dive/equivalent_delay/persistent_jumps.csv --out share/deep_dive/equivalent_delay
python share/validate_equivalent_delay.py
```
