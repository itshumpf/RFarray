#!/usr/bin/env python3
"""Source discrimination via Mahalanobis distance in (CFO, SFO) space.

Each characterized source keeps a running mean vector and covariance
(Welford update) over its accepted observations. A new observation is
scored against every centroid with the Mahalanobis distance

    d²(x, S) = (x - μ_S)ᵀ Σ_S⁻¹ (x - μ_S)

which under a Gaussian source model is χ²-distributed with 2 dof, so the
thresholds have real probabilistic meaning:

    d² <= 5.99   inside the 95% ellipse  -> consistent with the source
    d² <= 9.21   inside the 99% ellipse  -> marginal
    d²  > 9.21   outlier                 -> not this source

Covariances are regularized (floor on the diagonal) so a source observed
under unusually calm conditions can't collapse its ellipse to a sliver and
reject its own future traffic.
"""
import numpy as np

CHI2_95 = 5.991
CHI2_99 = 9.210

# variance floors: CFO in Hz², SFO in (rad/subcarrier)²
_VAR_FLOOR = np.array([1.0, 1e-8])


class SourceModel:
    """Running 2D Gaussian model (Welford) of one source's (CFO, SFO)."""

    def __init__(self, source_id):
        self.source_id = source_id
        self.n = 0
        self.mean = np.zeros(2)
        self._m2 = np.zeros((2, 2))

    def update(self, feat):
        feat = np.asarray(feat, dtype=np.float64)
        self.n += 1
        delta = feat - self.mean
        self.mean += delta / self.n
        self._m2 += np.outer(delta, feat - self.mean)

    @property
    def cov(self):
        if self.n < 2:
            c = np.diag(_VAR_FLOOR)
        else:
            c = self._m2 / (self.n - 1)
        c = c.copy()
        c[0, 0] = max(c[0, 0], _VAR_FLOOR[0])
        c[1, 1] = max(c[1, 1], _VAR_FLOOR[1])
        return c

    def mahalanobis2(self, feat):
        d = np.asarray(feat, dtype=np.float64) - self.mean
        try:
            return float(d @ np.linalg.solve(self.cov, d))
        except np.linalg.LinAlgError:
            return float("inf")

    def to_dict(self):
        return {"source_id": self.source_id, "n": self.n,
                "mean": self.mean.tolist(), "m2": self._m2.tolist()}

    @classmethod
    def from_dict(cls, d):
        m = cls(d["source_id"])
        m.n = d["n"]
        m.mean = np.array(d["mean"])
        m._m2 = np.array(d["m2"])
        return m


class Discriminator:
    """Library of source models + classification of new observations."""

    MIN_CHARACTERIZED = 5      # observations before a model may classify

    def __init__(self):
        self.models = {}       # source_id -> SourceModel

    def learn(self, source_id, feat):
        self.models.setdefault(source_id, SourceModel(source_id)).update(feat)

    def classify(self, feat, exclude=None):
        """Score feat against every characterized centroid.

        Returns (best_source_id, best_d2, verdict) where verdict is one of
        MATCH / MARGINAL / STRANGER / UNSCORED (no usable models yet).
        """
        best_id, best_d2 = None, float("inf")
        for sid, m in self.models.items():
            if sid == exclude or m.n < self.MIN_CHARACTERIZED:
                continue
            d2 = m.mahalanobis2(feat)
            if d2 < best_d2:
                best_id, best_d2 = sid, d2
        if best_id is None:
            return None, float("inf"), "UNSCORED"
        if best_d2 <= CHI2_95:
            return best_id, best_d2, "MATCH"
        if best_d2 <= CHI2_99:
            return best_id, best_d2, "MARGINAL"
        return best_id, best_d2, "STRANGER"

    def self_consistency(self, source_id, feat):
        """d² of an observation against its own claimed source, or None."""
        m = self.models.get(source_id)
        if m is None or m.n < self.MIN_CHARACTERIZED:
            return None
        return m.mahalanobis2(feat)

    def separation_matrix(self):
        """Pairwise centroid Mahalanobis distances under pooled covariance.

        The headline science number: how many 'sigmas' apart two devices'
        clock signatures sit. > ~3 means the pair is reliably separable.
        Returns (ids, matrix of d — NOT d²).
        """
        ids = [sid for sid, m in self.models.items()
               if m.n >= self.MIN_CHARACTERIZED]
        if len(ids) < 2:
            return ids, np.zeros((len(ids), len(ids)))
        pooled = np.zeros((2, 2))
        dof = 0
        for sid in ids:
            m = self.models[sid]
            pooled += m.cov * (m.n - 1)
            dof += m.n - 1
        pooled /= max(dof, 1)
        inv = np.linalg.inv(pooled)
        d = np.zeros((len(ids), len(ids)))
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                diff = self.models[ids[a]].mean - self.models[ids[b]].mean
                d[a, b] = d[b, a] = float(np.sqrt(diff @ inv @ diff))
        return ids, d
