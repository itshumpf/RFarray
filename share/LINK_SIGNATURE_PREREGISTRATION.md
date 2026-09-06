# Retrospective preregistration: link-signature feasibility in the eight-night CSI corpus

Status: frozen before running the analyses defined below. This is a retrospective
preregistration: earlier exploratory work on this corpus is known, but the specific
classification and verification results below have not yet been computed.

## Question and claim boundary

The security hypothesis is that a transmitter-receiver link can provide a repeatable
physical signature that rejects a transmitter which merely copies a digital identity.
These eight nights can test repeatability and separability of the six observed
beacon-receiver links. They cannot test spoofing cost because there is no controlled
MAC clone, displaced attacker, receiver swap, relay, replay, or channel emulator.

Accordingly, no result from this corpus will be described as proof that a link is
hard to spoof. A positive result only qualifies the representation for a prospective
spoofing experiment.

## Data and unit of analysis

- Use the already validated unwrap-free full-frame replay of the eight canonical
  paired nights and its exact 300-second robust bins.
- Exclude corrupt frames using the replay's frozen screening rules.
- Treat a 5-minute bin as one observation.
- Use only bins present for all three beacons at the receiver under test. For fused
  tests, additionally require both receivers in the same absolute-time bin.
- Labels are B1, B2, and B3. Within one receiver these are the three observed links.
- Hold out an entire night for testing. No frame or bin from a held-out night may
  estimate a labeled template, feature scale, or decision threshold.
- Report results per held-out night and macro-average nights so long sessions do not
  dominate.

## Frozen representations

All transformations are fitted on training nights only unless explicitly described
as the receiver-invariance diagnostic.

1. `slope`: arbiter slope, arbiter-slope IQR, arbiter coherence, and OLS-minus-arbiter
   slope.
2. `channel`: RSSI, log median CSI amplitude, CIR peak fraction, and log CIR RMS spread.
3. `combined`: all eight preceding features.

Packet count and k=+1 amplitude are excluded. Count is acquisition behavior, while
k=+1 directly exposes the known D0WD dead-bin receiver artifact.

Each feature is centered by the training median and divided by training MAD x 1.4826;
a zero scale is replaced by one. Classification uses the nearest training class
median in scaled Euclidean distance. This deliberately simple frozen model avoids
hyperparameter search on eight nights.

## Tests

### T1: same-receiver, held-out-night identification (primary feasibility test)

For each receiver, representation, and held-out night, fit three link templates on
the other seven nights and predict B1/B2/B3. Report balanced accuracy, confusion
counts, and a night-bootstrap 95% confidence interval for macro balanced accuracy.
Chance is 1/3.

Prerequisite pass: combined or channel representation has lower 95% night-bootstrap
bound above 1/3, median night accuracy at least 0.70, and accuracy at least 0.50 in
six of eight nights for each receiver. This is deliberately required at both
receivers; one favorable receiver is insufficient.

### T2: multi-receiver fusion

Concatenate the two receivers' representations on common absolute-time bins, keeping
receiver feature blocks separate. Repeat leave-one-night-out classification on this
aligned subset. Compare fused accuracy with each single-receiver classifier evaluated
on exactly the same observations.

Fusion pass: macro accuracy improves by at least 0.05 over the better single receiver
and improves or ties it in at least six of eight held-out nights.

### T3: claimed-link verification

For every held-out observation, calculate distance to each of the three enrolled
templates. Its correct-template distance is genuine; distances to the other two
templates are impostor claims. Pool no thresholds across the test labels. Report ROC
AUC and equal-error rate (EER), macro-averaged by held-out night and receiver.

Verification pass: combined or channel representation has macro AUC at least 0.90
and macro EER at most 0.15 at each receiver.

### T4: receiver-invariance diagnostic (not a security pass/fail test)

To remove receiver-wide offsets without using labels, robustly normalize each feature
within each receiver-night across all three beacons. Train on D0WD nights and test
the paired S3 night, and vice versa. Compare this cross-receiver accuracy with the
corresponding same-receiver result.

High transfer would indicate a beacon-associated ordering shared by receivers. Low
transfer would indicate receiver/link-specific structure. It cannot distinguish
receiver hardware from propagation because receiver positions were not swapped.

### T5: time-block sensitivity

Repeat T1 and T2 at 60-second and 600-second scales where exact aggregates can be
constructed from existing 1-minute and 5-minute products. The conclusion must not
depend on a single aggregation width. These are sensitivity results; T1 remains the
primary 300-second test.

## Uncertainty and multiplicity

- The eight nights, not individual bins, are the independent resampling units.
- Bootstrap confidence intervals resample the eight held-out-night scores with a
  fixed seed (`20260905`) and 20,000 draws.
- Report all receivers and all three frozen representations; do not select only the
  best-looking feature family.
- Pass/fail is based only on the criteria above. Other patterns are exploratory.

## Interpretation rules

- Passing T1/T3 means the stationary beacon-receiver combinations are repeatably
  distinguishable across these nights.
- Passing T2 means simultaneous receivers add discriminative information in this
  fixed deployment.
- T4 describes invariance; it does not identify the causal owner of the signal.
- Even if every test passes, the spoof-resistance hypothesis remains untested until
  prospective attacker-location, hardware substitution, replay/relay, and receiver-
  swap experiments are performed.
- Because beacon identity and beacon location never separate in this corpus, the
  observed classes are device-plus-location links, not pure spatial paths.
