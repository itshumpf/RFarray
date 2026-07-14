#!/usr/bin/env python3
"""1D Kalman filters for per-source clock-drift tracking.

Crystal drift is dominated by temperature, which changes over seconds to
minutes — far slower than our observation rate. A scalar random-walk
Kalman filter per tracked quantity is the right size of model: the state
IS the drift value, process noise q sets how fast we let it wander
(thermal drift), measurement noise r comes from the observed window
spread. The filtered state converges to the device's true drift while the
innovation sequence tells us whether new data still looks like this device.
"""


class Kalman1D:
    """Random-walk scalar Kalman filter.

    state:   x_k = x_{k-1} + w,  w ~ N(0, q)
    measure: z_k = x_k + v,      v ~ N(0, r)
    """

    def __init__(self, q=1e-6, r=1e-2, x0=None, p0=1.0):
        self.q = q
        self.r_default = r
        self.x = x0
        self.p = p0

    @property
    def initialized(self):
        return self.x is not None

    def update(self, z, r=None):
        """Fold in one measurement, return (state, innovation)."""
        if r is None or r <= 0:
            r = self.r_default
        if self.x is None:
            self.x, self.p = float(z), r
            return self.x, 0.0
        self.p += self.q                      # predict (state unchanged)
        innov = z - self.x
        k = self.p / (self.p + r)             # gain
        self.x += k * innov
        self.p *= (1.0 - k)
        return self.x, innov


class DriftTracker:
    """Paired CFO/SFO Kalman filters for one signal source.

    q values: SFO slope is O(0.01 rad/sc) and thermally very stable, CFO
    is O(1-50 Hz residual) and wanders more with temperature.
    """

    def __init__(self):
        self.cfo = Kalman1D(q=1e-3, r=4.0)     # Hz²
        self.sfo = Kalman1D(q=1e-9, r=1e-5)    # (rad/sc)²
        self.n = 0

    def update(self, obs):
        """Feed one WindowAggregator observation; returns (cfo, sfo) state."""
        if obs.get("sfo") is not None:
            # window IQR -> variance estimate for measurement noise
            iqr = obs.get("sfo_iqr") or 0.0
            self.sfo.update(obs["sfo"], r=max((iqr / 1.35) ** 2, 1e-8))
        if obs.get("cfo") is not None:
            iqr = obs.get("cfo_iqr") or 0.0
            self.cfo.update(obs["cfo"], r=max((iqr / 1.35) ** 2, 1e-2))
        self.n += 1
        return self.cfo.x, self.sfo.x
