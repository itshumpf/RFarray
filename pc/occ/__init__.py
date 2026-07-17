"""Occupancy sensing from CSI amplitude (Phase 3).

Complementary to rff/ (transmitter fingerprinting via phase-domain clock
artifacts): this package asks "what is happening in the space", using the
amplitude of the same captured frames. Nothing here touches or depends on
the rff pipeline's state; it only reuses the validated LLTF subcarrier
mapping from rff.dsp.

Modules:
  ingest     CSV -> per-link uniform-grid amplitude matrices (cached)
  motion     sliding-window dispersion metric + calibrated detector
  breathing  respiration-band spectral scan of quiet segments
  zones      cross-link differential response of motion events
"""

# The three beacon links (TX MAC -> short name). The collector hears all
# three on channel 6; each is an independent geometric path through the
# space.
BEACON_MACS = {
    "a4:f0:0f:77:91:20": "B1",   # reference beacon, wall outlet
    "28:05:a5:2f:fa:48": "B2",
    "f4:2d:c9:70:72:30": "B3",
}
