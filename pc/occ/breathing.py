#!/usr/bin/env python3
"""Still-person presence via respiration-band spectral analysis.

Physics
-------
A motionless human is not RF-motionless: the chest wall moves ~1 cm at
0.2-0.33 Hz (12-20 breaths/min). At 2.4 GHz (wavelength 12.5 cm) that is
a periodic path-length modulation of a fraction of a wavelength —
invisible to a variance detector, but a clean narrowband line in the
amplitude spectrum of subcarriers whose multipath geometry passes near
the body.

Method: on a motion-quiet segment, per subcarrier, detrend the amplitude
time series and estimate a Welch PSD (plain numpy — no scipy on this
box). Score the respiration band (default 0.10-0.55 Hz, i.e. 6-33 bpm)
against the same subcarrier's broadband noise floor (0.7-2.5 Hz). A real
breather produces:
  1. a band peak well above the noise floor on *several* subcarriers, and
  2. *frequency consensus* — those subcarriers agree on the rate.
Noise produces occasional single-subcarrier peaks at random frequencies;
the consensus test is what separates the two.

Caveat honestly stated: any periodic mechanical process in-band (a fan
wobbling at 20 rpm, HVAC surging) will also pass. Cross-link agreement
and rate plausibility narrow it, but this detector reports "periodic
in-band modulation", and the interpretation is on us.
"""
import numpy as np

RESP_BAND = (0.10, 0.55)      # Hz: 6-33 breaths/min
NOISE_BAND = (0.70, 2.50)     # Hz: above respiration, below grid Nyquist


def welch_psd(x, fs, seg_s=60.0, overlap=0.5):
    """Welch PSD of a 1-D series (hann window, linear detrend per seg).

    Returns (freqs, psd) or (None, None) if the series is too short.
    """
    n = x.size
    nper = int(round(seg_s * fs))
    if nper < 16 or n < nper:
        return None, None
    step = max(1, int(nper * (1 - overlap)))
    win = np.hanning(nper)
    wnorm = (win * win).sum() * fs
    t = np.arange(nper, dtype=np.float64)
    acc = None
    count = 0
    for i0 in range(0, n - nper + 1, step):
        seg = x[i0:i0 + nper].astype(np.float64)
        # linear detrend: slow drift must not leak into the band
        A = np.column_stack([t, np.ones(nper)])
        coef, *_ = np.linalg.lstsq(A, seg, rcond=None)
        seg = seg - A @ coef
        spec = np.abs(np.fft.rfft(seg * win)) ** 2 / wnorm
        acc = spec if acc is None else acc + spec
        count += 1
    if not count:
        return None, None
    freqs = np.fft.rfftfreq(nper, d=1.0 / fs)
    return freqs, acc / count


def respiration_scan(A, dt, resp_band=RESP_BAND, noise_band=NOISE_BAND,
                     seg_s=60.0, top_n=10, consensus_hz=0.05):
    """Scan a quiet segment's (n, 52) filled shape matrix for breathing.

    Returns dict:
      snr_db     median band-SNR (dB) of the frequency-agreeing subcarriers
      freq_hz    consensus respiration frequency
      bpm        the same in breaths/min
      n_agree    how many of the top_n subcarriers agree on the rate
      per_sc     (52,) band SNR per subcarrier (linear)
    or None when the segment is unusable (too short / too gappy).
    """
    if A.shape[0] * dt < seg_s:
        return None
    fs = 1.0 / dt
    n_sc = A.shape[1]
    snr = np.zeros(n_sc)
    peak_f = np.full(n_sc, np.nan)
    freqs = None
    for k in range(n_sc):
        x = A[:, k]
        if not np.isfinite(x).all():
            continue
        f, p = welch_psd(x, fs, seg_s=seg_s)
        if f is None:
            continue
        freqs = f
        band = (f >= resp_band[0]) & (f <= resp_band[1])
        noise = (f >= noise_band[0]) & (f <= noise_band[1])
        if not band.any() or not noise.any():
            continue
        floor = np.median(p[noise])
        if floor <= 0:
            continue
        pb = p[band]
        i_pk = int(np.argmax(pb))
        # Edge-bin peaks are drift leakage, not respiration: a falling
        # 1/f spectrum puts argmax on the first band bin for EVERY
        # subcarrier, which fakes perfect frequency consensus. A real
        # breather produces an interior local maximum.
        if i_pk == 0 or i_pk == pb.size - 1:
            continue
        snr[k] = pb[i_pk] / floor
        peak_f[k] = f[band][i_pk]
    if freqs is None or not np.isfinite(peak_f).any():
        return None

    order = np.argsort(snr)[::-1][:top_n]
    cand_f = peak_f[order]
    cand_snr = snr[order]
    ok = np.isfinite(cand_f)
    if not ok.any():
        return None
    f0 = float(np.median(cand_f[ok]))
    agree = ok & (np.abs(cand_f - f0) <= consensus_hz)
    n_agree = int(agree.sum())
    med_snr = float(np.median(cand_snr[agree])) if n_agree else 0.0
    return {
        "snr_db": 10 * np.log10(med_snr) if med_snr > 0 else -np.inf,
        "freq_hz": f0,
        "bpm": f0 * 60.0,
        "n_agree": n_agree,
        "per_sc": snr,
    }


def presence_verdict(scan, min_snr_db=6.0, min_agree=5):
    """Conservative presence call from one link's scan result.

    Thresholds are starting points; they get calibrated against real
    empty-room segments (the false-alarm rate is the number that
    matters, and it must be measured, not assumed).
    """
    if scan is None:
        return False
    return scan["snr_db"] >= min_snr_db and scan["n_agree"] >= min_agree
