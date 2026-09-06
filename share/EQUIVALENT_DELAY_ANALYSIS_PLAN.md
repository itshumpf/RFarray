# Eight-night equivalent-delay analysis plan

Frozen 2026-09-06 before running the analyses defined below. This is a
retrospective analysis of a corpus whose SFO/link-signature results were already
known. It is not a prospective preregistration and its p-values are descriptive.

## Question and naming rule

Does the unwrap-free per-frame phase ramp contain evidence consistent with
sample-period timing states across the eight paired nights?

The phase ramp is converted to

```
tau_equiv = -slope / (2*pi*312500 Hz)
```

and is always called **equivalent delay**. A single CSI vector cannot separate
packet-detection/symbol-timing offset (STO), propagation delay, SFO, and the
linear component of channel phase. No result from this analysis may be called a
measurement of STO itself.

At 20 MHz one sample is 50 ns, equivalent to `2*pi/64 = 0.0981747704`
rad/subcarrier. The primary sample lattice is fixed at that spacing.

## Input population

Use the completed `share/deep_dive/full_arbiter_replay` corpus and its exact
multiscale summaries. All 69,510,186 clean beacon frames from eight nights,
three beacons, and both receivers contribute. Analyses operate on exact 1 s,
10 s, 60 s, and 300 s medians; missing/off-air intervals are not interpolated.

## Fixed tests

1. **Scale summary.** Report the equivalent-delay median, IQR, and 5th-to-95th
   percentile span for every receiver/night/beacon at every scale.
2. **Held-out lattice occupancy.** For each 60 s series, use its chronological
   first half to estimate one lattice origin by circular mean modulo 50 ns.
   Score the second half without refitting. A point is on-lattice when it lies
   within 0.10 sample (5 ns) of the nearest lattice point. Report the fraction,
   number of occupied integer levels, and whether at least two levels each hold
   at least 5% of scored points. Repeat unchanged at 40, 45, 55, and 60 ns as
   specificity controls. A high score with only one occupied level is
   within-session stability, not evidence of timing-state quantization.
3. **Persistent jumps.** On contiguous 60 s data, compare the median of the
   five minutes before and after each boundary. Retain shifts of at least 0.50
   sample, greedily retaining the largest candidate inside each 10-minute
   exclusion radius. A jump is sample-aligned when its magnitude lies within
   0.10 sample of a nonzero integer multiple of 50 ns. Report the exact
   binomial tail against the 0.20 geometric null as descriptive only. Run the
   same calculation for the four control spacings.
4. **Cross-receiver replication.** A persistent jump replicates only if the
   other receiver shows a retained jump for the same night and beacon within
   +/-2 minutes and with the same sign. Receiver-local packet detection need
   not replicate; replication therefore does not identify STO, but its absence
   constrains a shared transmitter/environmental explanation.
5. **Classification rule.** Do not rerun identification using equivalent delay
   alone: it is a linear unit conversion of the already-tested phase slope and
   therefore contains exactly the same predictive information.

## Interpretation gates

- Evidence consistent with sample timing requires both held-out occupancy in
  at least two materially occupied levels and stronger 50 ns specificity than
  the four control lattices.
- Sample-aligned jumps without held-out multi-level occupancy are insufficient.
- Results cannot distinguish STO from any other contributor to the linear phase
  ramp without a new controlled capture or an independent timing observable.

## Disclosed extension after the aggregate pass

The aggregate pass returned no material multi-level 50 ns state. Before
examining any individual-frame lattice result, add the same chronological
first-half-origin/second-half-score calculation directly to all stored frame
estimates. This extension is necessary because a one-minute median could hide
rapid switching between sample-period states. It uses the same five spacings,
0.10-sample tolerance, 5% material-level rule, and interpretation gate above.
The aggregate result was known when this extension was added; the frame-level
result was not.
