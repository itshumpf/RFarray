"""RFF v2 — scientific CFO/SFO discrimination pipeline.

Modules:
  protocol       binary serial frame decoder (shared with capture tools)
  dsp            phase preprocessing + RANSAC slope/intercept estimation
  kalman         1D Kalman filter for per-source clock-drift tracking
  discriminator  running centroids + Mahalanobis distance classification
  reference      reference-beacon systemic-drift subtraction
  store          SQLite history of [source, CFO, SFO, timestamp, RSSI]
"""
