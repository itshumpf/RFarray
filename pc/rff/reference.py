#!/usr/bin/env python3
"""Reference-beacon drift normalization.

The receiver's own crystal drifts too, and its drift is common-mode: every
CFO/SFO we measure is (TX drift - RX drift). If one source is our own TX
beacon — fixed hardware, always on, known MAC — its measured drift IS the
receiver's systemic drift plus a constant. Subtracting the beacon's
Kalman-smoothed track from every other source's measurements cancels the
RX-side thermal wander and leaves per-device offsets that are stable
across hours and reboots.

If the reference hasn't been seen yet (or ever), observations pass through
unchanged and are flagged uncorrected — honest data over silently wrong
data.
"""
from .kalman import DriftTracker


class ReferenceNormalizer:
    def __init__(self, ref_mac=None):
        self.ref_mac = ref_mac.lower() if ref_mac else None
        self.tracker = DriftTracker()

    @property
    def ready(self):
        return (self.tracker.cfo.initialized
                and self.tracker.sfo.initialized)

    def feed(self, mac, obs):
        """Feed every observation through; returns (obs, corrected: bool).

        Reference-MAC observations update the systemic-drift track and are
        returned unmodified (their corrected values would be ~0 by
        construction, which carries no information). All other sources get
        cfo_ref/sfo_ref fields added when the reference is warm.
        """
        if self.ref_mac is None:
            return obs, False
        if mac.lower() == self.ref_mac:
            self.tracker.update(obs)
            return obs, False
        if not self.ready:
            return obs, False
        out = dict(obs)
        if obs.get("cfo") is not None:
            out["cfo_ref"] = obs["cfo"] - self.tracker.cfo.x
        if obs.get("sfo") is not None:
            out["sfo_ref"] = obs["sfo"] - self.tracker.sfo.x
        return out, True
